"""Authenticated adapter regressions. Threaded routes use established outside split."""
import json
import logging
from pathlib import Path

import pytest
from sqlmodel import Session, select

from job_agent.database import PacketDecision, SearchResult
from job_agent.dashboard.approval_app import create_approval_app
from job_agent.dashboard.approval_security import SECURITY_HEADERS
from test_approvals import ready
from test_packets import setup
from test_approval_security import request
from test_tailscale_security import HOST, LOGIN, settings, headers
from test_approval_api import action_body


@pytest.fixture
def remote(ready, monkeypatch):
    builder = ready[1]
    configured = settings(data_dir=builder.settings.data_dir)
    application = create_approval_app(engine=builder.engine, settings=configured, access="tailscale")
    def forbidden(*args, **kwargs): raise AssertionError("outbound from authenticated approval adapter")
    for path in ("socket.socket.connect", "socket.socket.connect_ex", "socket.getaddrinfo", "socket.gethostbyname",
        "httpx.Client.send", "httpx.AsyncClient.send", "anthropic.Anthropic.__init__",
        "job_agent.tavily_research.TavilyCompanyResearcher.__init__",
        "job_agent.tavily_research.TavilyCompanyResearcher.research",
        "job_agent.revisions.RevisionProcessor.process_revision", "job_agent.packets.PacketService.build_one",
        "subprocess.Popen", "playwright.sync_api.sync_playwright"):
        monkeypatch.setattr(path, forbidden)
    monkeypatch.setattr(builder.executor, "create", forbidden)
    return application, configured


def call(application, path, *, action=None, body=None, hs=None):
    if action is None:
        return request(application, path, headers=headers() if hs is None else hs)
    if hs is None:
        token = json.loads(call(application, "/api/bootstrap")[2])["csrf_token"].encode()
        hs = [*headers(), (b"origin", b"https://" + HOST), (b"x-job-pilot-csrf", token),
              (b"content-type", b"application/json")]
    return request(application, path + "/" + action, method="POST", headers=hs,
                   body=json.dumps(body).encode())


@pytest.mark.parametrize("path", ["/", "/assets/approval.js", "/assets/approval.css", "/api/bootstrap",
    "/api/queue", "/api/packets/{id}", "/api/packets/{id}/history", "/api/packets/{id}/revision-status",
    "/api/packets/{id}/decision-detail", "/api/packets/{id}/application-destination",
    "/api/packets/{id}/diff/resume/{id}", "/api/packets/{id}/diff/cover/{id}",
    "/api/packets/{id}/artifacts/resume.pdf", "/api/packets/{id}/approve",
    "/api/packets/{id}/reject", "/api/packets/{id}/revise", "/unknown"])
@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "POST"])
def test_every_route_auth_before_routing_or_body(remote, ready, path, method, caplog):
    caplog.set_level(logging.DEBUG)
    path = path.format(id=ready[2].id)
    status, secured, content, reads = request(remote[0], path, method=method,
        headers=[(b"host", HOST)], body=b"PRIVATE_BODY")
    assert status == 401 and reads == 0
    assert json.loads(content) == {"error": {"code": "authentication_required"}}
    for k, v in SECURITY_HEADERS.items(): assert secured[k.lower().encode()] == v.encode()
    assert LOGIN.decode() not in caplog.text and HOST.decode() not in caplog.text


def test_bootstrap_auth_private_restart_no_storage(remote, ready):
    application, configured = remote
    before = (ready[4] / "test.sqlite").read_bytes()
    status, _, body, reads = call(application, "/api/bootstrap")
    assert status == 200 and reads == 0
    data = json.loads(body)
    assert set(data) == {"csrf_token", "local_only", "access_mode"}
    assert data["local_only"] is False and data["access_mode"] == "tailscale"
    assert LOGIN not in body and HOST not in body
    assert before == (ready[4] / "test.sqlite").read_bytes() and data["csrf_token"].encode() not in before
    restarted = create_approval_app(engine=ready[1].engine, settings=configured, access="tailscale")
    assert json.loads(call(restarted, "/api/bootstrap")[2])["csrf_token"] != data["csrf_token"]
    hs = [*headers(), (b"origin", b"https://" + HOST),
          (b"x-job-pilot-csrf", data["csrf_token"].encode()), (b"content-type", b"application/json")]
    assert call(restarted, f"/api/packets/{ready[2].id}", action="reject", body=action_body(ready, "reject"), hs=hs)[0] == 403
    assert request(restarted, "/api/bootstrap", headers=[(b"host", HOST)])[0] == 401


def test_authenticated_reads_outbound_isolation_schema_dtos(remote, ready):
    application = remote[0]; p = ready[2]; root = f"/api/packets/{p.id}"
    before = (ready[4] / "test.sqlite").read_bytes()
    with ready[1].engine.connect() as connection:
        schema = connection.exec_driver_sql("SELECT sql FROM sqlite_master ORDER BY name").all()
    for path in ("/", "/assets/approval.js", "/assets/approval.css", "/api/queue", root, root + "/history",
        root + "/revision-status", root + "/application-destination", root + f"/diff/resume/{p.id}",
        root + f"/diff/cover/{p.id}", root + "/artifacts/resume.pdf"):
        status, secured, body, _ = call(application, path)
        assert status == 200, body
        assert LOGIN not in body and HOST not in body and str(ready[4]).encode() not in body
        assert secured[b"cache-control"] == b"no-store"
        if path == root:
            detail = json.loads(body)
            assert detail["expected_packet_fingerprint"] == p.fingerprint
            assert detail["approval_preview"]["expected_approval_view_fingerprint"] == ready[0].preview_approval(p.id, p.fingerprint).approval_view_fingerprint
        if path.endswith("resume.pdf"):
            assert body == (ready[4] / "packets" / p.id / "resume.pdf").read_bytes()
    assert before == (ready[4] / "test.sqlite").read_bytes()
    with ready[1].engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA user_version").scalar() == 9
        assert schema == connection.exec_driver_sql("SELECT sql FROM sqlite_master ORDER BY name").all()
    assert call(application, "/unknown")[0] == 404


@pytest.mark.parametrize("action", ["approve", "reject", "revise"])
def test_exact_fingerprints_replay_conflict_outbound(remote, ready, action, caplog):
    caplog.set_level(logging.DEBUG); ready[1].engine.echo = True
    application = remote[0]; p = ready[2]; path = f"/api/packets/{p.id}"
    body = action_body(ready, action)
    for key in body:
        if "fingerprint" in key:
            invalid = {k: v for k, v in body.items() if k != key}
            assert call(application, path, action=action, body=invalid)[0] == 422
            invalid = {**body, key: "0" * 64}
            status, _, output, _ = call(application, path, action=action, body=invalid)
            expected = "stale_packet" if key == "expected_packet_fingerprint" else "stale_approval_view"
            assert status == 409 and json.loads(output)["error"]["code"] == expected
    status, _, output, _ = call(application, path, action=action, body=body)
    assert status == 200, output
    result = json.loads(output)
    assert result["current_authorization"] == ("currently_valid" if action == "approve" else "not_approved")
    assert json.loads(call(application, path, action=action, body=body)[2])["decision_id"] == result["decision_id"]
    other = "reject" if action != "reject" else "revise"
    assert call(application, path, action=other, body=action_body(ready, other))[0] == 409
    if action != "approve":
        changed = {**body, "detail" if action == "reject" else "feedback": "Changed private text"}
        assert call(application, path, action=action, body=changed)[0] == 409
        detail = json.loads(call(application, path + "/decision-detail")[2])
        assert detail["detail" if action == "reject" else "feedback"] == body["detail" if action == "reject" else "feedback"]
    with Session(ready[1].engine) as session:
        records = session.exec(select(PacketDecision)).all()
        assert len(records) == 1
        assert LOGIN.decode() not in records[0].model_dump_json() and HOST.decode() not in records[0].model_dump_json()
    for private in (LOGIN.decode(), HOST.decode(), p.fingerprint, p.cover_letter, str(ready[4]), body.get("feedback", "UNUSED_MARKER")):
        assert private not in caplog.text


def test_stale_view_history_and_destination_revalidation(remote, ready):
    application = remote[0]; p = ready[2]; path = f"/api/packets/{p.id}"
    stale = action_body(ready, "approve")
    def change_url(value):
        with Session(ready[1].engine) as session:
            row = session.get(SearchResult, ready[3].id)
            row.payload = {**row.payload, "apply_url": value}
            session.add(row); session.commit()
    change_url("https://example.com/new")
    assert call(application, path, action="approve", body=stale)[0] == 409
    current = action_body(ready, "approve")
    first = json.loads(call(application, path, action="approve", body=current)[2])
    assert json.loads(call(application, path + "/application-destination")[2])["authorization"] == "currently_valid"
    change_url("https://example.com/changed")
    replay = json.loads(call(application, path, action="approve", body=current)[2])
    assert replay["decision_id"] == first["decision_id"] and replay["historical_state"] == "approved_historically"
    assert replay["current_authorization"] == "evidence_changed"
    assert json.loads(call(application, path + "/application-destination")[2])["authorization"] == "evidence_changed"


def test_successor_independent_http_approval(ready, monkeypatch):
    # Build the synthetic recovery successor BEFORE outbound/build traps.
    p = ready[2]; builder = ready[1]
    ready[0].reject(p.id, p.fingerprint, "other")
    (ready[4] / "packets" / p.id / "resume.pdf").unlink()
    assert builder.build_one(ready[3]).status == "recovery_required"
    successor = builder.build_one(ready[3])
    assert successor.status == "packet_ready" and successor.version == 2
    def forbidden(*a, **k): raise AssertionError("provider/network")
    for target in ("socket.socket.connect", "socket.getaddrinfo", "httpx.Client.send", "httpx.AsyncClient.send",
                   "anthropic.Anthropic.__init__", "job_agent.tavily_research.TavilyCompanyResearcher.research"):
        monkeypatch.setattr(target, forbidden)
    application = create_approval_app(engine=builder.engine, settings=settings(data_dir=builder.settings.data_dir), access="tailscale")
    path = f"/api/packets/{successor.id}"
    detail = json.loads(call(application, path)[2])
    assert detail["decision"] is None and detail["current_authorization"] == "not_approved"
    body = {"expected_packet_fingerprint": successor.fingerprint,
            "expected_approval_view_fingerprint": detail["approval_preview"]["expected_approval_view_fingerprint"]}
    assert call(application, path, action="approve", body={**body, "expected_packet_fingerprint": p.fingerprint})[0] == 409
    assert call(application, path, action="approve", body=body)[0] == 200
    history = json.loads(call(application, path + "/history")[2])
    assert [item["decision"] for item in history] == ["reject", "approve"]


def test_no_tailscale_management_in_approval_code():
    root = Path(__file__).resolve().parents[1] / "src/job_agent/dashboard"
    source = "\n".join(p.read_text() for p in root.glob("approval_*.py"))
    for forbidden in ("subprocess", "api.tailscale", "tailscale up", "tailscale serve", "tailscale funnel", "requests.", "httpx."):
        assert forbidden not in source
