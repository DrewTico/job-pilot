"""Read-only approval API against real local packet/domain evidence."""
import fcntl
import json
import logging

import pytest
from sqlmodel import Session, select

from job_agent.approvals import DecisionError
from job_agent.database import ApplicationPacket, CompanyFactRecord, PacketDecision, SearchResult
from job_agent.dashboard.approval_app import create_approval_app
from job_agent.dashboard.approval_security import AdapterError, SECURITY_HEADERS
from job_agent.dashboard.approval_service import ApprovalQueueService
from test_approvals import ready, approve
from test_packets import setup
from test_approval_security import request


@pytest.fixture
def app(ready, monkeypatch):
    approvals, builder, packet, row, directory = ready
    def forbidden(*args, **kwargs):
        raise AssertionError("outbound/provider/build operation in approval read")
    for path in ("socket.socket.connect", "socket.getaddrinfo", "httpx.Client.send",
                 "httpx.AsyncClient.send", "anthropic.Anthropic.__init__",
                 "job_agent.tavily_research.TavilyCompanyResearcher.__init__",
                 "job_agent.tavily_research.TavilyCompanyResearcher.research",
                 "job_agent.revisions.RevisionProcessor.process_revision",
                 "job_agent.packets.PacketService.build_one"):
        monkeypatch.setattr(path, forbidden)
    monkeypatch.setattr(builder.executor, "create", forbidden)
    return create_approval_app(engine=builder.engine, settings=builder.settings), packet


def test_read_routes_and_safe_dtos(app, ready):
    application, packet = app
    service, builder, _, row, directory = ready
    with builder.engine.connect() as conn:
        schema_before = conn.exec_driver_sql("SELECT sql FROM sqlite_master ORDER BY name").all()
        version = conn.exec_driver_sql("PRAGMA user_version").scalar()
    before = (directory / "test.sqlite").read_bytes()
    for path in ("/api/queue", f"/api/packets/{packet.id}", f"/api/packets/{packet.id}/history"):
        status, headers, body, _ = request(application, path)
        assert status == 200, body
        data = json.loads(body)
        assert "evidence_json" not in body.decode() and str(directory).encode() not in body
        assert b"style_memory_hash" not in body and b"writing_fingerprints" not in body
        assert b"prompt" not in body and b"saved" not in body
        for name, value in SECURITY_HEADERS.items():
            assert headers[name.lower().encode()] == value.encode()
        if isinstance(data, dict) and "approval_preview" in data:
            assert data["packet_id"] == packet.id and data["version"] == packet.version
            assert data["cover_text"] == packet.cover_letter and data["integrity"] == "passed"
            assert data["screening"]["answers"] == [{"question": "authorized_us", "answer": True}]
            assert data["screening"]["manual_needed"] == ["Unknown?"]
            preview = service.preview_approval(packet.id, packet.fingerprint)
            assert data["approval_preview"]["expected_approval_view_fingerprint"] == preview.approval_view_fingerprint
            with Session(builder.engine) as session:
                expected = [session.get(CompanyFactRecord, fid).text for fid in packet.company_fact_ids]
            assert [fact["text"] for fact in data["company_facts"]] == expected
    assert before == (directory / "test.sqlite").read_bytes()
    with builder.engine.connect() as conn:
        assert version == conn.exec_driver_sql("PRAGMA user_version").scalar() == 9
        assert schema_before == conn.exec_driver_sql("SELECT sql FROM sqlite_master ORDER BY name").all()


@pytest.mark.parametrize("query", ["limit=101", "limit=0", "offset=-1", "section=nope", "unknown=PRIVATE", "tier=bogus", "status=bogus"])
def test_invalid_query_never_echoes(app, query):
    status, _, body, _ = request(app[0], "/api/queue", query=query)
    assert status == 422 and json.loads(body) == {"error": {"code": "invalid_request"}}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/api/jobs", "/api/applications", "/assets/unknown.js", "/assets/facts.yaml", "/api/packets/" + "0" * 32 + "/revision-status"])
def test_unavailable_routes(app, path):
    assert request(app[0], path)[0] == 404


def test_shell_fixed_assets_no_private_content(app):
    for path, mime in (("/", b"text/html"), ("/assets/approval.js", b"text/javascript"), ("/assets/approval.css", b"text/css")):
        status, headers, body, _ = request(app[0], path)
        assert status == 200 and headers[b"content-type"].startswith(mime)
        assert app[1].id.encode() not in body and app[1].cover_letter.encode() not in body
    assert request(app[0], "/assets/../facts.yaml")[0] == 404


def test_get_cannot_mutate_and_no_cors(app, ready):
    application, packet = app
    for action in ("approve", "reject", "revise"):
        assert request(application, f"/api/packets/{packet.id}/{action}", method="POST", body=b"PRIVATE_FEEDBACK")[0] == 403
        assert request(application, f"/api/packets/{packet.id}/{action}")[0] == 405
    status, headers, _, reads = request(application, "/api/queue", method="OPTIONS", headers=[
        (b"host", b"localhost:8643"), (b"origin", b"chrome-extension://foreign"),
        (b"access-control-request-method", b"POST")])
    assert status == 405 and reads == 0
    assert not any(b"access-control" in name for name in headers)
    with Session(ready[0].engine) as session:
        assert not session.exec(select(PacketDecision)).all()


@pytest.mark.parametrize("change", ["url", "cover", "screening", "facts", "new_decision"])
def test_snapshot_reconciliation_fails_closed(ready, change):
    approvals, builder, packet, row, directory = ready
    adapter = ApprovalQueueService(builder.engine, builder.settings)
    original = adapter.approvals.preview_approval
    def racing_preview(*args):
        result = original(*args)
        with Session(builder.engine) as session:
            p = session.get(ApplicationPacket, packet.id)
            if change == "url":
                r = session.get(SearchResult, row.id)
                r.payload = {**r.payload, "apply_url": "https://example.com/changed"}
                session.add(r)
            elif change == "cover":
                p.cover_letter += " CHANGED"
                session.add(p)
            elif change == "screening":
                p.screening_answers = {**p.screening_answers, "manual_needed": ["Changed question"]}
                session.add(p)
            elif change == "facts":
                fact = session.get(CompanyFactRecord, p.company_fact_ids[0])
                fact.source_title = "Changed source title"
                session.add(fact)
            else:
                session.add(PacketDecision(packet_id=p.id, packet_fingerprint=p.fingerprint,
                    decision="reject", reason_code="other", evidence_json="{}"))
            session.commit()
        return result
    adapter.approvals.preview_approval = racing_preview
    with pytest.raises(AdapterError, match="stale_packet"):
        adapter.detail(packet.id)


def test_busy_detail_queue_history_remain_available(app, ready):
    application, packet = app
    with (ready[4] / "packets" / ".build.lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status, _, body, _ = request(application, f"/api/packets/{packet.id}")
        assert status == 503 and json.loads(body) == {"error": {"code": "packet_busy"}}
        assert request(application, "/api/queue")[0] == 200
        assert request(application, f"/api/packets/{packet.id}/history")[0] == 200


def test_historical_approve_current_validation_separate(app, ready):
    application, packet = app
    service, builder, _, row, _ = ready
    record = approve(service, packet.id, packet.fingerprint)
    detail = json.loads(request(application, f"/api/packets/{packet.id}")[2])
    assert detail["decision"] == "approve" and detail["current_authorization"] == "currently_valid"
    assert detail["approval_preview"] is None
    with Session(builder.engine) as session:
        r = session.get(SearchResult, row.id)
        r.payload = {**r.payload, "apply_url": "https://example.com/new"}
        session.add(r)
        session.commit()
    detail = json.loads(request(application, f"/api/packets/{packet.id}")[2])
    assert detail["decision"] == "approve" and detail["current_authorization"] == "evidence_changed"
    with Session(builder.engine) as session:
        assert session.get(PacketDecision, record.id).decision == "approve"


def test_read_logging_suppresses_private_sql(app, ready, caplog):
    caplog.set_level(logging.DEBUG)
    ready[0].engine.echo = True
    status, _, _, _ = request(app[0], f"/api/packets/{app[1].id}")
    assert status == 200
    assert ready[2].cover_letter not in caplog.text
    assert ready[2].fingerprint not in caplog.text
    assert str(ready[4]) not in caplog.text


def test_cli_loopback_only_and_port_bounds(ready, monkeypatch):
    import uvicorn
    from rich.console import Console
    from job_agent.cli import _build_parser, cmd_approval_queue
    parser = _build_parser()
    for values in (["--port", "0"], ["--port", "65536"], ["--host", "0.0.0.0"]):
        with pytest.raises(SystemExit):
            parser.parse_args(["approval-queue", *values])
    received = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: received.append(kwargs))
    monkeypatch.setattr("job_agent.cli.load_settings", lambda: ready[1].settings)
    monkeypatch.setattr("job_agent.dashboard.approval_app._existing_engine", lambda settings: ready[1].engine)
    args = parser.parse_args(["approval-queue", "--port", "12345"])
    assert cmd_approval_queue(Console(), args) == 0
    assert received == [{"host": "127.0.0.1", "port": 12345, "proxy_headers": False,
        "forwarded_allow_ips": "", "access_log": False, "log_level": "warning"}]


def test_direct_detail_preview_and_safe_projection(app, ready):
    approvals, builder, packet, _, directory = ready
    service = ApprovalQueueService(builder.engine, builder.settings)
    detail = service.detail(packet.id)
    preview = approvals.preview_approval(packet.id, packet.fingerprint)
    assert detail.approval_preview.expected_approval_view_fingerprint == preview.approval_view_fingerprint
    assert detail.expected_packet_fingerprint == packet.fingerprint
    assert detail.cover_text == packet.cover_letter and detail.integrity == "passed"
    assert [answer.model_dump() for answer in detail.screening.answers] == [{"question": "authorized_us", "answer": True}]
    assert detail.screening.manual_needed == ["Unknown?"]
    result = detail.model_dump_json()
    for secret in ("evidence_json", "style_memory_hash", "writing_fingerprints", "saved", str(directory), "prompt"):
        assert secret not in result
    with Session(builder.engine) as session:
        assert not session.exec(select(PacketDecision)).all()


def test_direct_approved_detail_revalidates_current_evidence(app, ready):
    approvals, builder, packet, row, _ = ready
    record = approve(approvals, packet.id, packet.fingerprint)
    service = ApprovalQueueService(builder.engine, builder.settings)
    assert service.detail(packet.id).current_authorization == "currently_valid"
    with Session(builder.engine) as session:
        source = session.get(SearchResult, row.id)
        source.payload = {**source.payload, "apply_url": "https://example.com/changed"}
        session.add(source)
        session.commit()
    detail = service.detail(packet.id)
    assert detail.decision == "approve" and detail.current_authorization == "evidence_changed"
    assert detail.application_destination.authorization == "evidence_changed"
    with Session(builder.engine) as session:
        assert session.get(PacketDecision, record.id).decision == "approve"


def test_factory_only_opens_existing_v9_without_mutation(ready, tmp_path):
    from job_agent.config import Settings
    from job_agent.dashboard.approval_app import _existing_engine
    with pytest.raises(ValueError, match="approval_storage_unavailable"):
        _existing_engine(Settings(data_dir=tmp_path / "missing"))
    assert not (tmp_path / "missing").exists()
    # Open the existing synthetic v9 database under the production filename.
    copied = tmp_path / "job_pilot.sqlite3"
    copied.write_bytes((ready[4] / "test.sqlite").read_bytes())
    before = copied.read_bytes()
    engine = _existing_engine(Settings(data_dir=tmp_path))
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA user_version").scalar() == 9
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    engine.dispose()
    assert copied.read_bytes() == before


@pytest.mark.parametrize("host", [b"attacker.example:8643", b"127.0.0.1.attacker.example:8643", b"localhost:8642"])
def test_full_app_host_rejected_before_private_body(app, host):
    status, headers, body, reads = request(app[0], "/api/queue", method="POST",
        headers=[(b"host", host)], body=b"PRIVATE_VALIDATION_INPUT")
    assert status == 400 and json.loads(body) == {"error": {"code": "invalid_host"}}
    assert reads == 0 and headers[b"content-security-policy"]


def test_direct_reads_no_schema_database_or_artifact_mutation(app, ready):
    approvals, builder, packet, _, directory = ready
    before = (directory / "test.sqlite").read_bytes()
    files = {p.name: p.read_bytes() for p in (directory / "packets" / packet.id).iterdir()}
    with builder.engine.connect() as connection:
        schema = connection.exec_driver_sql("SELECT sql FROM sqlite_master ORDER BY name").all()
    service = ApprovalQueueService(builder.engine, builder.settings)
    from job_agent.dashboard.approval_models import QueueQuery
    service.queue(QueueQuery())
    service.detail(packet.id)
    service.history(packet.id)
    assert before == (directory / "test.sqlite").read_bytes()
    assert files == {p.name: p.read_bytes() for p in (directory / "packets" / packet.id).iterdir()}
    with builder.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA user_version").scalar() == 9
        assert schema == connection.exec_driver_sql("SELECT sql FROM sqlite_master ORDER BY name").all()


def test_historical_cover_reuses_authenticator_and_never_reconstructs(ready):
    from job_agent.packet_history import authenticated_cover_text
    approvals, builder, packet, _, directory = ready
    # Historical authentication is independent of mutable current candidate files.
    (directory / "facts.yaml").unlink()
    (directory / "answer_bank.yaml").unlink()
    with Session(builder.engine) as session:
        p = session.get(ApplicationPacket, packet.id)
        result = authenticated_cover_text(session, p)
        assert result.status == "available" and result.text == packet.cover_letter
        p.cover_letter += " Forged text."
        assert authenticated_cover_text(session, p).status == "integrity_failed"


def api_headers(application):
    status, _, body, _ = request(application, "/api/bootstrap")
    assert status == 200
    token = json.loads(body)["csrf_token"]
    return [(b"host", b"127.0.0.1:8643"), (b"origin", b"http://127.0.0.1:8643"),
            (b"x-job-pilot-csrf", token.encode()), (b"content-type", b"application/json")]


def mutate(application, packet, action, body, *, headers=None):
    return request(application, f"/api/packets/{packet.id}/{action}", method="POST",
        headers=headers if headers is not None else api_headers(application), body=json.dumps(body).encode())


def action_body(ready, action):
    service, _, p, _, _ = ready
    body = {"expected_packet_fingerprint": p.fingerprint}
    if action == "approve":
        body["expected_approval_view_fingerprint"] = service.preview_approval(p.id, p.fingerprint).approval_view_fingerprint
    elif action == "reject":
        body.update(reason_code="bad_fit", detail="Exact reason")
    else:
        body["feedback"] = "  Exact feedback\n\x00é😀  "
    return body


def test_bootstrap_process_token_private_free_read_only(app, ready):
    application, p = app
    before = (ready[4] / "test.sqlite").read_bytes()
    status, headers, body, reads = request(application, "/api/bootstrap")
    assert status == 200 and reads == 0
    data = json.loads(body)
    assert set(data) == {"csrf_token", "local_only", "origin"}
    assert data["origin"] == "http://127.0.0.1:8643" and data["local_only"] is True
    assert body == request(application, "/api/bootstrap")[2]
    assert p.id.encode() not in body and p.cover_letter.encode() not in body
    assert before == (ready[4] / "test.sqlite").read_bytes()
    assert data["csrf_token"].encode() not in before
    assert headers[b"cache-control"] == b"no-store" and b"set-cookie" not in headers
    restarted = create_approval_app(engine=ready[1].engine, settings=ready[1].settings)
    assert data["csrf_token"] != json.loads(request(restarted, "/api/bootstrap")[2])["csrf_token"]


@pytest.mark.parametrize("action", ["approve", "reject", "revise"])
@pytest.mark.parametrize("failure", ["missing_origin", "foreign", "null", "missing_csrf", "bad_csrf", "mismatch_host"])
def test_mutation_boundary_no_private_body_read_or_decision(app, ready, action, failure):
    application, p = app
    headers = api_headers(application)
    replace = {
        "missing_origin": (b"origin", None), "foreign": (b"origin", b"http://evil.example"),
        "null": (b"origin", b"null"), "missing_csrf": (b"x-job-pilot-csrf", None),
        "bad_csrf": (b"x-job-pilot-csrf", b"BAD"), "mismatch_host": (b"host", b"localhost:8643"),
    }
    name, value = replace[failure]
    headers = [(k, v) for k, v in headers if k != name]
    if value is not None:
        headers.append((name, value))
    status, _, body, reads = request(application, f"/api/packets/{p.id}/{action}", method="POST",
        headers=headers, body=b"PRIVATE_FEEDBACK_NOT_JSON")
    assert status == 403 and reads == 0 and json.loads(body) == {"error": {"code": "csrf_failed"}}
    with Session(ready[0].engine) as session:
        assert not session.exec(select(PacketDecision)).all()


def test_previous_server_token_fails_after_restart(app, ready):
    application, p = app
    headers = api_headers(application)
    restarted = create_approval_app(engine=ready[1].engine, settings=ready[1].settings)
    assert mutate(restarted, p, "reject", action_body(ready, "reject"), headers=headers)[0] == 403


@pytest.mark.parametrize("action", ["approve", "reject", "revise"])
def test_mutation_exact_replay_and_changed_request_conflict(app, ready, action):
    application, p = app
    body = action_body(ready, action)
    status, _, content, _ = mutate(application, p, action, body)
    assert status == 200, content
    result = json.loads(content)
    assert result["packet_id"] == p.id and result["packet_version"] == p.version
    assert result["decision"] == action and result["historical"] is True
    assert result["current_authorization"] == ("currently_valid" if action == "approve" else "not_approved")
    assert "evidence_json" not in content.decode() and body.get("feedback", "NOT_PRESENT") not in content.decode()
    assert json.loads(mutate(application, p, action, body)[2])["decision_id"] == result["decision_id"]
    altered = dict(body)
    if action == "approve":
        altered["expected_approval_view_fingerprint"] = "0" * 64
        expected = "stale_approval_view"
    elif action == "reject":
        altered["detail"] = "Changed private reason"
        expected = "decision_conflict"
    else:
        altered["feedback"] = "Changed private feedback"
        expected = "decision_conflict"
    status, _, error, _ = mutate(application, p, action, altered)
    assert status == 409 and json.loads(error) == {"error": {"code": expected}}
    with Session(ready[0].engine) as session:
        records = session.exec(select(PacketDecision)).all()
        assert len(records) == 1
        if action == "revise":
            assert records[0].detail == body["feedback"]
            from job_agent.database import PacketRevisionWork
            assert not session.exec(select(PacketRevisionWork)).all()
            assert len(session.exec(select(ApplicationPacket)).all()) == 1
            assert result["revision_status_uri"] == f"/api/packets/{p.id}/revision-status"
            assert result["message"] == "Creates a new packet version. The new version needs its own approval."
            assert not (ready[4] / "style_memory.md").exists()


@pytest.mark.parametrize("action", ["approve", "reject", "revise"])
def test_stale_packet_request_is_not_refreshed(app, ready, action, monkeypatch):
    application, p = app
    body = action_body(ready, action)
    body["expected_packet_fingerprint"] = "0" * 64
    def forbidden(*args, **kwargs):
        raise AssertionError("POST may not preview")
    monkeypatch.setattr("job_agent.approvals.ApprovalService.preview_approval", forbidden)
    status, _, content, _ = mutate(application, p, action, body)
    assert status == 409 and json.loads(content) == {"error": {"code": "stale_packet"}}
    with Session(ready[0].engine) as session:
        assert not session.exec(select(PacketDecision)).all()


def test_stale_view_tab_never_substitutes_new_token(app, ready, monkeypatch):
    application, p = app
    body = action_body(ready, "approve")
    with Session(ready[0].engine) as session:
        row = session.get(SearchResult, ready[3].id)
        row.payload = {**row.payload, "apply_url": "https://example.com/changed"}
        session.add(row)
        session.commit()
    monkeypatch.setattr("job_agent.approvals.ApprovalService.preview_approval",
        lambda *args: pytest.fail("POST must not silently refresh preview"))
    status, _, content, _ = mutate(application, p, "approve", body)
    assert status == 409 and json.loads(content) == {"error": {"code": "stale_approval_view"}}
    with Session(ready[0].engine) as session:
        assert not session.exec(select(PacketDecision)).all()


@pytest.mark.parametrize("left,right", [("approve", "reject"), ("approve", "revise"), ("reject", "approve"), ("revise", "approve")])
def test_two_tabs_cannot_record_different_decisions(app, ready, left, right):
    application, p = app
    bodies = {action: action_body(ready, action) for action in {left, right}}
    tab1, tab2 = api_headers(application), api_headers(application)
    assert mutate(application, p, left, bodies[left], headers=tab1)[0] == 200
    status, _, body, _ = mutate(application, p, right, bodies[right], headers=tab2)
    assert status == 409 and json.loads(body) == {"error": {"code": "decision_conflict"}}


@pytest.mark.parametrize("action,body", [
    ("approve", {}), ("approve", {"expected_packet_fingerprint": "1" * 64}),
    ("approve", {"expected_approval_view_fingerprint": "1" * 64}),
    ("reject", {"reason_code": "bad_fit"}), ("revise", {"feedback": "Private"}),
    ("reject", {"expected_packet_fingerprint": "1" * 64, "reason_code": "unknown"}),
    ("revise", {"expected_packet_fingerprint": "1" * 64, "feedback": 123}),
    ("revise", {"expected_packet_fingerprint": "1" * 64, "feedback": " \t\u2003"}),
    ("revise", {"expected_packet_fingerprint": "1" * 64, "feedback": "x" * 4001}),
    ("reject", {"expected_packet_fingerprint": "1" * 64, "reason_code": "other", "detail": "x" * 4001}),
])
def test_mutation_dto_invalid_private_inputs_not_echoed(app, ready, action, body):
    status, _, content, _ = mutate(app[0], app[1], action, body)
    assert status == 422 and json.loads(content) == {"error": {"code": "invalid_request"}}
    with Session(ready[0].engine) as session:
        assert not session.exec(select(PacketDecision)).all()


@pytest.mark.parametrize("action", ["approve", "reject", "revise"])
def test_mutation_extra_fields_forbidden(app, ready, action):
    body = {**action_body(ready, action), "packet_id": "PRIVATE_SECOND_SELECTOR", "evidence_json": "PRIVATE_FORGED_EVIDENCE"}
    status, _, content, _ = mutate(app[0], app[1], action, body)
    assert status == 422 and json.loads(content) == {"error": {"code": "invalid_request"}}


@pytest.mark.parametrize("action", ["approve", "reject", "revise"])
def test_valid_mutation_busy_fails_without_decision(app, ready, action):
    body = action_body(ready, action)
    with (ready[4] / "packets" / ".build.lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status, _, content, _ = mutate(app[0], app[1], action, body)
        assert status == 503 and json.loads(content) == {"error": {"code": "packet_busy"}}
    with Session(ready[0].engine) as session:
        assert not session.exec(select(PacketDecision)).all()


def test_historical_approve_replay_needs_separate_current_check(app, ready):
    application, p = app
    body = action_body(ready, "approve")
    first = json.loads(mutate(application, p, "approve", body)[2])
    with Session(ready[0].engine) as session:
        row = session.get(SearchResult, ready[3].id)
        row.payload = {**row.payload, "apply_url": "https://example.com/changed"}
        session.add(row)
        session.commit()
    status, _, content, _ = mutate(application, p, "approve", body)
    assert status == 200
    replay = json.loads(content)
    assert replay["decision_id"] == first["decision_id"]
    assert replay["historical_state"] == "approved_historically"
    assert replay["current_authorization"] == "evidence_changed"


@pytest.mark.parametrize("action", ["approve", "reject", "revise"])
def test_artifact_failure_only_blocks_approve(app, ready, action):
    body = action_body(ready, action)
    (ready[4] / "packets" / app[1].id / "resume.pdf").write_bytes(b"TAMPERED_PRIVATE_PDF")
    status, _, content, _ = mutate(app[0], app[1], action, body)
    assert status == (409 if action == "approve" else 200)
    if action == "approve":
        assert json.loads(content) == {"error": {"code": "packet_integrity_failed"}}


def test_mutation_unexpected_error_and_storage_error_sanitized(app, ready, monkeypatch):
    from sqlalchemy.exc import OperationalError
    def fail(*args, **kwargs):
        raise OperationalError("PRIVATE_SQL", {"detail": "PRIVATE_FEEDBACK"}, RuntimeError("PRIVATE_PATH"))
    monkeypatch.setattr("job_agent.dashboard.approval_service.ApprovalQueueService.reject", fail)
    status, _, content, _ = mutate(app[0], app[1], "reject", action_body(ready, "reject"))
    assert status == 503 and json.loads(content) == {"error": {"code": "storage_unavailable"}}
    def fail_internal(*args, **kwargs):
        raise RuntimeError("PRIVATE_PATH_AND_FEEDBACK")
    monkeypatch.setattr("job_agent.dashboard.approval_service.ApprovalQueueService.reject", fail_internal)
    status, headers, content, _ = mutate(app[0], app[1], "reject", action_body(ready, "reject"))
    assert status == 500 and json.loads(content) == {"error": {"code": "internal_error"}}
    assert headers[b"x-frame-options"] == b"DENY"


def test_direct_revise_verbatim_unicode_limit_and_restart(app, ready):
    from job_agent.dashboard.approval_models import ReviseRequest
    from job_agent.database import PacketRevisionWork
    service = ApprovalQueueService(ready[0].engine, ready[1].settings)
    feedback = "😀" * 3999 + "\x00"
    body = ReviseRequest(expected_packet_fingerprint=app[1].fingerprint, feedback=feedback)
    result = service.revise(app[1].id, body)
    fresh = ApprovalQueueService(ready[0].engine, ready[1].settings)
    assert fresh.revise(app[1].id, body).decision_id == result.decision_id
    with Session(ready[0].engine) as session:
        assert session.get(PacketDecision, result.decision_id).detail == feedback
        assert not session.exec(select(PacketRevisionWork)).all()
        assert len(session.exec(select(ApplicationPacket)).all()) == 1


@pytest.mark.parametrize("action", ["approve", "reject", "revise"])
def test_direct_decisions_use_exact_domain_inputs_and_current_check(app, ready, action, monkeypatch):
    from job_agent.dashboard.approval_models import ApproveRequest, RejectRequest, ReviseRequest
    adapter = ApprovalQueueService(ready[0].engine, ready[1].settings)
    body = {"approve": ApproveRequest, "reject": RejectRequest, "revise": ReviseRequest}[action](**action_body(ready, action))
    seen = []
    original = getattr(adapter.approvals, action)
    def capture(*args):
        seen.append(args)
        return original(*args)
    monkeypatch.setattr(adapter.approvals, action, capture)
    result = getattr(adapter, action)(app[1].id, body)
    assert seen[0][0:2] == (app[1].id, app[1].fingerprint)
    assert result.current_authorization == ("currently_valid" if action == "approve" else "not_approved")
    if action == "approve":
        assert seen[0][2] == body.expected_approval_view_fingerprint
    elif action == "revise":
        assert seen[0][2] == body.feedback
    else:
        assert seen[0][2:] == (body.reason_code, body.detail)


@pytest.mark.parametrize("left,right", [("approve", "approve"), ("reject", "reject"),
    ("revise", "revise"), ("approve", "reject"), ("approve", "revise")])
def test_http_multi_tab_concurrent_actions_converge(app, ready, left, right):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    application, p = app
    bodies = {action: action_body(ready, action) for action in {left, right}}
    headers = api_headers(application)
    barrier = Barrier(2)
    def send(action):
        barrier.wait(timeout=10)
        return mutate(application, p, action, bodies[action], headers=headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, [left, right]))
    assert all(result[0] in {200, 409, 503} for result in results)
    assert any(result[0] == 200 for result in results)
    with Session(ready[0].engine) as session:
        rows = session.exec(select(PacketDecision)).all()
        assert len(rows) == 1
        winner, decision_id = rows[0].decision, rows[0].id
    # Exact explicit replay after contention; never replace expectations.
    for action in (left, right):
        status, _, content, _ = mutate(application, p, action, bodies[action], headers=headers)
        if action == winner:
            assert status == 200 and json.loads(content)["decision_id"] == decision_id
        else:
            assert status == 409 and json.loads(content) == {"error": {"code": "decision_conflict"}}


def test_revise_http_lost_response_survives_new_app(app, ready):
    from job_agent.database import PacketRevisionWork
    application, p = app
    body = action_body(ready, "revise")
    assert mutate(application, p, "revise", body)[0] == 200
    with Session(ready[0].engine) as session:
        original = session.exec(select(PacketDecision)).one()
        decision_id = original.id
    restarted = create_approval_app(engine=ready[0].engine, settings=ready[1].settings)
    status, _, content, _ = mutate(restarted, p, "revise", body)
    assert status == 200 and json.loads(content)["decision_id"] == decision_id
    with Session(ready[0].engine) as session:
        assert len(session.exec(select(PacketDecision)).all()) == 1
        assert not session.exec(select(PacketRevisionWork)).all()


def test_direct_approve_response_revalidates_after_commit(app, ready, monkeypatch):
    from job_agent.dashboard.approval_models import ApproveRequest
    adapter = ApprovalQueueService(ready[0].engine, ready[1].settings)
    body = ApproveRequest(**action_body(ready, "approve"))
    original = adapter.approvals.approve
    def approve_then_change(*args):
        record = original(*args)
        with Session(ready[0].engine) as session:
            row = session.get(SearchResult, ready[3].id)
            row.payload = {**row.payload, "apply_url": "https://example.com/after-commit"}
            session.add(row)
            session.commit()
        return record
    monkeypatch.setattr(adapter.approvals, "approve", approve_then_change)
    result = adapter.approve(app[1].id, body)
    assert result.historical_state == "approved_historically"
    assert result.current_authorization == "evidence_changed"
    assert result.current_authorization_checked_at is None


def test_direct_postcommit_busy_never_implies_current_validity(app, ready, monkeypatch):
    from job_agent.dashboard.approval_models import ApproveRequest
    adapter = ApprovalQueueService(ready[0].engine, ready[1].settings)
    body = ApproveRequest(**action_body(ready, "approve"))
    probes = []
    def probe(settings):
        probes.append(True)
        if len(probes) == 2:
            raise AdapterError("packet_busy", 503)
    monkeypatch.setattr("job_agent.dashboard.approval_service.probe_packet_lock", probe)
    result = adapter.approve(app[1].id, body)
    assert result.historical_state == "approved_historically" and result.current_authorization == "not_checked"
    assert result.current_authorization_checked_at is None


def test_http_mutation_private_logs_and_no_schema_change(app, ready, caplog):
    caplog.set_level(logging.DEBUG)
    ready[0].engine.echo = True
    headers = api_headers(app[0])
    token = dict(headers)[b"x-job-pilot-csrf"].decode()
    body = action_body(ready, "revise")
    body["feedback"] = "PRIVATE_FEEDBACK_SENTINEL😀\x00"
    with ready[0].engine.connect() as conn:
        before = conn.exec_driver_sql("SELECT sql FROM sqlite_master ORDER BY name").all()
    status, _, content, _ = mutate(app[0], app[1], "revise", body, headers=headers)
    assert status == 200
    for marker in (token, body["feedback"], app[1].fingerprint, str(ready[4]), "PRIVATE_FEEDBACK_SENTINEL"):
        assert marker not in caplog.text
        assert marker not in content.decode()
    with ready[0].engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA user_version").scalar() == 9
        assert conn.exec_driver_sql("SELECT sql FROM sqlite_master ORDER BY name").all() == before


@pytest.mark.parametrize("raw", [b"", b"PRIVATE_NOT_JSON", b"[]", b"{\"feedback\":", b"null"],
    ids=["empty", "malformed", "array", "incomplete", "null"])
def test_http_invalid_json_is_sanitized(app, ready, raw):
    status, _, body, _ = request(app[0], f"/api/packets/{app[1].id}/revise", method="POST",
        headers=api_headers(app[0]), body=raw)
    assert status == 422 and json.loads(body) == {"error": {"code": "invalid_request"}}
    with Session(ready[0].engine) as session:
        assert not session.exec(select(PacketDecision)).all()


def test_http_revise_4000_codepoints_fit_bounded_body(app, ready):
    body = {"expected_packet_fingerprint": app[1].fingerprint, "feedback": "😀" * 4000}
    status, _, response, _ = mutate(app[0], app[1], "revise", body)
    assert status == 200
    with Session(ready[0].engine) as session:
        record = session.get(PacketDecision, json.loads(response)["decision_id"])
        assert record.detail == body["feedback"] and len(record.detail) == 4000


def test_direct_authenticated_pdf_captured_bytes_and_no_current_truth(app, ready):
    from job_agent.packet_history import authenticated_resume_pdf
    expected = (ready[4] / "packets" / app[1].id / "resume.pdf").read_bytes()
    (ready[4] / "facts.yaml").unlink()
    (ready[4] / "answer_bank.yaml").unlink()
    version, captured = authenticated_resume_pdf(ready[0].engine, ready[1].settings, app[1].id)
    assert version == app[1].version and captured == expected
    (ready[4] / "packets" / app[1].id / "resume.pdf").write_bytes(b"CHANGED_AFTER_CAPTURE")
    assert captured == expected


@pytest.mark.parametrize("damage", ["missing_pdf", "tamper", "symlink_pdf", "symlink_directory", "wrong_size", "wrong_filename", "forged_pdf_container"])
def test_direct_pdf_authentication_fail_closed(app, ready, damage):
    import hashlib
    from job_agent.packet_history import authenticated_resume_pdf, HistoryError
    directory = ready[4] / "packets" / app[1].id
    pdf = directory / "resume.pdf"
    if damage == "missing_pdf":
        pdf.unlink()
    elif damage == "tamper":
        pdf.write_bytes(b"PRIVATE_BAD_PDF")
    elif damage == "symlink_pdf":
        pdf.unlink(); pdf.symlink_to(ready[4] / "facts.yaml")
    elif damage == "symlink_directory":
        directory.rename(directory.with_name("displaced")); directory.symlink_to(directory.with_name("displaced"), target_is_directory=True)
    else:
        with Session(ready[0].engine) as session:
            packet = session.get(ApplicationPacket, app[1].id)
            artifacts = {key: dict(value) for key, value in packet.artifacts.items()}
            if damage == "wrong_size": artifacts["resume.pdf"]["size"] += 1
            elif damage == "wrong_filename": artifacts["private.yaml"] = artifacts.pop("resume.pdf")
            else:
                forged = b"%PDF-not-a-real-container"
                pdf.write_bytes(forged)
                artifacts["resume.pdf"] = {"size": len(forged), "sha256": hashlib.sha256(forged).hexdigest()}
            packet.artifacts = artifacts; session.add(packet); session.commit()
    with pytest.raises(HistoryError) as exc:
        authenticated_resume_pdf(ready[0].engine, ready[1].settings, app[1].id)
    assert str(exc.value) == ("artifact_unavailable" if damage == "missing_pdf" else "artifact_integrity_failed")
    assert str(ready[4]) not in str(exc.value)


@pytest.mark.parametrize("state", ["queued", "pending", "style_prepared", "style_persisted", "blocked", "recovery_required"])
def test_direct_revision_status_db_only_during_busy(app, ready, state, monkeypatch):
    from job_agent.database import PacketRevisionWork
    service = ApprovalQueueService(ready[0].engine, ready[1].settings)
    decision = ready[0].revise(app[1].id, app[1].fingerprint, "PRIVATE_FEEDBACK")
    if state != "queued":
        with Session(ready[0].engine) as session:
            work = PacketRevisionWork(decision_id=decision.id)
            session.add(work); session.commit()
            work.state = "style_prepared" if state == "style_persisted" else state
            if state in {"style_prepared", "style_persisted"}:
                work.base_style_hash = work.target_style_hash = app[1].style_memory_hash
            if state in {"blocked", "recovery_required"}: work.failure_code = "source_evidence_invalid"
            session.add(work); session.commit()
            if state == "style_persisted":
                work.state = state
                session.add(work); session.commit()
    monkeypatch.setattr(service, "_projection", lambda *args: pytest.fail("status must not load artifacts/detail"))
    with (ready[4] / "packets" / ".build.lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status = service.revision_status(app[1].id)
    assert status.state == state and status.decision_id == decision.id
    assert status.successor_packet_id is None
    assert "PRIVATE_FEEDBACK" not in status.model_dump_json()
    assert "source_evidence_invalid" not in status.model_dump_json()


def test_direct_decision_detail_exact_private_text_separate(app, ready):
    service = ApprovalQueueService(ready[0].engine, ready[1].settings)
    with pytest.raises(AdapterError): service.decision_detail(app[1].id)
    feedback = "\x00  <script>private</script>😀\n"
    decision = ready[0].revise(app[1].id, app[1].fingerprint, feedback)
    result = service.decision_detail(app[1].id)
    assert result.feedback == feedback and result.decision_id == decision.id
    assert "evidence_json" not in result.model_dump_json()
    assert result.reason_code is None and result.detail is None


def test_direct_destination_gates_current_approval_and_damaged_detail(app, ready):
    service = ApprovalQueueService(ready[0].engine, ready[1].settings)
    before = service.application_destination(app[1].id)
    assert before.authorization == "not_approved" and before.url == ready[3].payload["url"]
    body = action_body(ready, "approve")
    ready[0].approve(app[1].id, body["expected_packet_fingerprint"], body["expected_approval_view_fingerprint"])
    assert service.application_destination(app[1].id).authorization == "currently_valid"
    (ready[4] / "packets" / app[1].id / "resume.pdf").write_bytes(b"BAD")
    detail = service.detail(app[1].id)
    assert detail.decision == "approve" and detail.current_authorization == "integrity_failed"
    assert service.application_destination(app[1].id).authorization == "integrity_failed"


def test_direct_failed_preview_allows_reject_revise_identity_without_approve(app, ready):
    service = ApprovalQueueService(ready[0].engine, ready[1].settings)
    (ready[4] / "packets" / app[1].id / "resume.pdf").write_bytes(b"BAD")
    detail = service.detail(app[1].id)
    assert detail.integrity == "failed" and detail.approval_preview is None
    assert detail.expected_packet_fingerprint == app[1].fingerprint
    assert detail.application_destination.url is None


def test_direct_diffs_use_existing_domain_reader(app, ready):
    service = ApprovalQueueService(ready[0].engine, ready[1].settings)
    for kind in ("resume", "cover"):
        result = service.packet_diff(app[1].id, app[1].id, kind)
        assert result.status == "available" and result.diff == ""
        assert result.left_version == result.right_version == app[1].version


def test_http_pdf_headers_bytes_and_no_path_selector(app, ready):
    path = f"/api/packets/{app[1].id}/artifacts/resume.pdf"
    status, headers, body, _ = request(app[0], path)
    assert status == 200 and headers[b"content-type"] == b"application/pdf"
    assert headers[b"content-disposition"] == f'inline; filename="resume-v{app[1].version}.pdf"'.encode()
    assert body == (ready[4] / "packets" / app[1].id / "resume.pdf").read_bytes()
    for name, value in SECURITY_HEADERS.items(): assert headers[name.lower().encode()] == value.encode()
    assert request(app[0], path, query="path=../facts.yaml")[0] == 422
    for artifact in ("resume.docx", "resume.face.txt", "facts.yaml"):
        assert request(app[0], path.replace("resume.pdf", artifact))[0] == 404


def test_http_c_read_routes_provider_isolation(app, ready):
    p = app[1]
    ready[0].revise(p.id, p.fingerprint, "EXACT_PRIVATE_FEEDBACK")
    paths = [f"/api/packets/{p.id}/revision-status", f"/api/packets/{p.id}/decision-detail",
        f"/api/packets/{p.id}/application-destination", f"/api/packets/{p.id}/diff/resume/{p.id}",
        f"/api/packets/{p.id}/diff/cover/{p.id}"]
    for path in paths:
        status, _, body, _ = request(app[0], path)
        assert status == 200, body
        assert "evidence_json" not in body.decode() and str(ready[4]).encode() not in body
        if not path.endswith("decision-detail"): assert b"EXACT_PRIVATE_FEEDBACK" not in body
