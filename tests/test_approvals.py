"""Exact-packet decisions, real local artifacts/SQLite, zero live providers."""
import hashlib
import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest
import yaml
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from job_agent.approvals import ApprovalService, DecisionError, REJECT_REASONS
from job_agent.database import (ApplicationPacket, CompanyFactRecord, PacketDecision,
    SearchResult, WritingWorkItem, database_session, initialize_database)
from job_agent.packets import PacketService, _local_verifier, digest, verify_packet_integrity
from test_packets import setup, add_job, research_rows, FACTS, RESUME, NOW


@pytest.fixture
def ready(setup, monkeypatch):
    old, calls, directory = setup
    monkeypatch.undo()  # Real resume gates, PDF extraction and rendering throughout.
    facts = {**FACTS, "summary": "Python software.", "employers": [
        {**FACTS["employers"][0], "project_description": "Built Python software."}]}
    (directory / "facts.yaml").write_text(yaml.safe_dump(facts))
    resume = RESUME.replace("PROFESSIONAL SUMMARY\n", "PROFESSIONAL SUMMARY\nPython software.\n").replace("Duration: 2025", "Project Description: Built Python software.\nDuration: 2025")
    original = old.executor.create
    def generate(**kwargs):
        if kwargs["task"] == "tailor_resume":
            calls.append(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=resume)])
        return original(**kwargs)
    old.executor.create = generate
    builder = PacketService(old.engine, old.settings, executor=old.executor, clock=lambda: NOW)
    row = add_job(builder, required_screening_questions=["authorized_us", "Unknown?"])
    packet = builder.build_one(row)
    assert packet.status == "packet_ready", packet.failure_reason
    return ApprovalService(builder.engine, builder.settings), builder, packet, row, directory


def decisions(service):
    with Session(service.engine) as s:
        return list(s.exec(select(PacketDecision)).all())


def approve(service, packet_id, fingerprint):
    # Existing cases exercise both historical replay and damaged first approval.
    with Session(service.engine) as session:
        record = session.exec(select(PacketDecision).where(PacketDecision.packet_id == packet_id)).one_or_none()
    token = digest(json.loads(record.evidence_json)) if record and record.decision == "approve" else "0" * 64
    if not record:
        try:
            token = service.preview_approval(packet_id, fingerprint).approval_view_fingerprint
        except DecisionError:
            pass  # Still exercise Approve's own fail-closed validation.
    return service.approve(packet_id, fingerprint, token)


def test_approve_evidence_and_current_validation(ready):
    service, builder, p, row, directory = ready
    record = approve(service, p.id, p.fingerprint)
    evidence = json.loads(record.evidence_json)
    assert record.actor == "Andrew" and record.evidence_version == 1
    assert record.decision == "approve" and record.reason_code == record.detail == ""
    assert set(evidence) == {"packet_version", "scoring_fingerprint", "artifact_manifest", "company_fact_ids", "writing", "cover_letter_sha256", "application_url"}
    assert evidence["packet_version"] == p.version
    assert evidence["scoring_fingerprint"] == p.scoring_fingerprint
    assert evidence["artifact_manifest"] == p.artifacts
    assert evidence["application_url"] == row.payload["url"]
    assert evidence["cover_letter_sha256"] == hashlib.sha256(p.cover_letter.encode()).hexdigest()
    with Session(service.engine) as s:
        from job_agent.research import semantic_fact_id
        assert evidence["company_fact_ids"] == sorted(semantic_fact_id(s.get(CompanyFactRecord, fid)) for fid in p.company_fact_ids)
        for task, fp in p.writing_fingerprints.items():
            w = s.get(WritingWorkItem, fp)
            assert evidence["writing"][task] == {"task": task, "request_fingerprint": fp, "output_hash": w.output_hash}
    assert record.evidence_json == json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    assert approve(service, p.id, p.fingerprint).id == record.id
    assert service.validate_approval_for_packet(p.id, p.fingerprint).decision_id == record.id
    assert len(decisions(service)) == 1
    assert p.cover_letter not in record.evidence_json
    assert str(directory) not in record.evidence_json


@pytest.mark.parametrize("operation", ["approve", "reject", "revise", "validate"])
@pytest.mark.parametrize("reference", ["missing", "stale"])
def test_missing_and_stale_fail(ready, operation, reference):
    service, _, p, _, _ = ready
    pid, fp = ("f"*32, p.fingerprint) if reference == "missing" else (p.id, "f"*64)
    fn = {"approve": lambda: approve(service, pid, fp), "reject": lambda: service.reject(pid, fp, "pay"),
          "revise": lambda: service.revise(pid, fp, "Feedback"), "validate": lambda: service.validate_approval_for_packet(pid, fp)}[operation]
    with pytest.raises(DecisionError, match="packet_not_found|stale_packet_fingerprint"):
        fn()
    assert not decisions(service)


@pytest.mark.parametrize("state", ["building", "generation_failed", "research_incomplete", "recovery_required", "missing_ready_at"])
def test_status_alone_is_insufficient(ready, state):
    service, _, p, _, _ = ready
    with database_session(service.engine) as s:
        packet = s.get(ApplicationPacket, p.id)
        if state == "missing_ready_at":
            packet.ready_at = None
        else:
            packet.status = state
        s.add(packet)
    with pytest.raises(DecisionError, match="packet_integrity_failed"):
        approve(service, p.id, p.fingerprint)
    assert not decisions(service)


@pytest.mark.parametrize("reason", sorted(REJECT_REASONS))
def test_reject_damaged_artifacts_and_exact_replay(ready, reason):
    service, _, p, _, directory = ready
    (directory / "packets" / p.id / "resume.pdf").unlink()
    record = service.reject(p.id, p.fingerprint, reason, "  Reason\ncafé  ")
    assert record.reason_code == reason and record.detail == "  Reason\ncafé  "
    assert "artifact_manifest" not in record.evidence_json
    assert service.reject(p.id, p.fingerprint, reason, record.detail).id == record.id
    with pytest.raises(DecisionError, match="packet_not_approved"):
        service.validate_approval_for_packet(p.id, p.fingerprint)


@pytest.mark.parametrize("reason", ["", "Bad Fit", "invalid", None])
def test_invalid_reject_reason(ready, reason):
    service, _, p, _, _ = ready
    with pytest.raises(DecisionError, match="invalid_reject_reason"):
        service.reject(p.id, p.fingerprint, reason)
    assert not decisions(service)


@pytest.mark.parametrize("feedback", ["text", "  café 🧑🏽‍💻  ", "\nLine 1\nLine 2\n", "界"*4000])
def test_revise_verbatim_request_only(ready, feedback, caplog):
    service, _, p, _, directory = ready
    caplog.set_level(logging.DEBUG)
    service.engine.echo = True
    before = {x.name: x.read_bytes() for x in (directory / "packets" / p.id).iterdir()}
    record = service.revise(p.id, p.fingerprint, feedback)
    assert record.detail == feedback and record.reason_code == ""
    assert service.revise(p.id, p.fingerprint, feedback).id == record.id
    assert feedback not in caplog.text
    assert not (directory / "style_memory.md").exists()
    with Session(service.engine) as s:
        assert len(s.exec(select(ApplicationPacket)).all()) == 1
    assert before == {x.name: x.read_bytes() for x in (directory / "packets" / p.id).iterdir()}


@pytest.mark.parametrize("feedback", ["", " \t\r\n", "\u2003\u00a0", "x"*4001, None])
def test_invalid_revision(ready, feedback):
    service, _, p, _, _ = ready
    with pytest.raises(DecisionError):
        service.revise(p.id, p.fingerprint, feedback)
    assert not decisions(service)


def act(service, p, decision, reason="pay", detail="Feedback"):
    if decision == "approve":
        return approve(service, p.id, p.fingerprint)
    if decision == "reject":
        return service.reject(p.id, p.fingerprint, reason, detail)
    return service.revise(p.id, p.fingerprint, detail)


@pytest.mark.parametrize("first,second", [(a,b) for a in ("approve","reject","revise") for b in ("approve","reject","revise") if a != b])
def test_conflicts(ready, first, second):
    service, _, p, _, _ = ready
    recorded = act(service, p, first)
    with pytest.raises(DecisionError, match="packet_decision_conflict"):
        act(service, p, second)
    assert [d.id for d in decisions(service)] == [recorded.id]


@pytest.mark.parametrize("kind,changed", [("reject","reason"),("reject","detail"),("revise","detail")])
def test_changed_request_conflicts(ready, kind, changed):
    service, _, p, _, _ = ready
    act(service, p, kind)
    with pytest.raises(DecisionError, match="packet_decision_conflict"):
        act(service, p, kind, "company" if changed == "reason" else "pay", "Changed" if changed == "detail" else "Feedback")
    assert len(decisions(service)) == 1


@pytest.mark.parametrize("left,right", [("approve","approve"),("approve","reject"),("approve","revise"),("reject","revise")])
@pytest.mark.parametrize("use_build_lock", [True, False])
def test_real_concurrent_connections(ready, left, right, use_build_lock, monkeypatch):
    service, _, p, _, _ = ready
    engines = [initialize_database(service.settings.data_dir / "test.sqlite") for _ in range(2)]
    with engines[0].connect() as a, engines[1].connect() as b:
        assert a.connection.driver_connection is not b.connection.driver_connection
    if not use_build_lock:
        from contextlib import nullcontext
        monkeypatch.setattr("job_agent.approvals._build_lock", lambda settings: nullcontext())
    barrier = Barrier(2)
    def run(kind, engine):
        barrier.wait(timeout=5)
        try:
            return act(ApprovalService(engine, service.settings), p, kind).id
        except DecisionError as e:
            return str(e)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(run, left, engines[0]), pool.submit(run, right, engines[1])
        results = [a.result(timeout=20), b.result(timeout=20)]
    for engine in engines:
        engine.dispose()
    assert len(decisions(service)) == 1
    if left == right:
        assert results[0] == results[1] == decisions(service)[0].id
    else:
        assert results.count("packet_decision_conflict") == 1
        assert decisions(service)[0].id in results


@pytest.mark.parametrize("reopen", [False, True])
@pytest.mark.parametrize("statement", ["UPDATE packet_decisions SET detail='changed'", "DELETE FROM packet_decisions"])
def test_append_only_direct_sql(ready, reopen, statement):
    service, _, p, _, directory = ready
    approve(service, p.id, p.fingerprint)
    engine = initialize_database(directory / "test.sqlite") if reopen else service.engine
    try:
        with pytest.raises(IntegrityError, match="packet_decisions is append-only"):
            with engine.begin() as c:
                c.exec_driver_sql(statement)
        assert len(decisions(service)) == 1
    finally:
        if reopen:
            engine.dispose()


@pytest.mark.parametrize("change", ["decision", "actor", "reason", "fingerprint_short", "fingerprint_upper", "fingerprint_nonhex", "evidence_version", "duplicate", "missing_fk", "approve_reason", "approve_detail", "revise_blank", "revise_long", "reject_long"])
def test_direct_insert_constraints_after_reopen(ready, change):
    service, _, p, _, directory = ready
    approve(service, p.id, p.fingerprint)
    # Another exact packet version makes constraint failure independent of unique.
    with database_session(service.engine) as s:
        clone = ApplicationPacket.model_validate({**p.model_dump(),"id": "e"*32, "version": 2, "fingerprint": "e"*64, "capacity_day": None})
        s.add(clone)
    values = dict(id="d"*32, packet_id=clone.id, packet_fingerprint=clone.fingerprint, decision="approve", actor="Andrew", reason_code="", detail="", created_at="2026-10-05", evidence_version=1, evidence_json="{}")
    overrides = {"decision":{"decision":"invalid"}, "actor":{"actor":"Someone"}, "reason":{"decision":"reject","reason_code":"invalid"}, "fingerprint_short":{"packet_fingerprint":"0"*63}, "fingerprint_upper":{"packet_fingerprint":"A"*64}, "fingerprint_nonhex":{"packet_fingerprint":"g"*64}, "evidence_version":{"evidence_version":2}, "duplicate":{"packet_id":p.id}, "missing_fk":{"packet_id":"missing"}, "approve_reason":{"reason_code":"pay"}, "approve_detail":{"detail":"text"}, "revise_blank":{"decision":"revise","detail":" \t\n\u2003"}, "revise_long":{"decision":"revise","detail":"x"*4001}, "reject_long":{"decision":"reject","reason_code":"other","detail":"x"*4001}}
    values.update(overrides[change])
    reopened = initialize_database(directory / "test.sqlite")
    try:
        with pytest.raises(IntegrityError):
            with reopened.begin() as c:
                c.exec_driver_sql(f"INSERT INTO packet_decisions ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
        with reopened.connect() as c:
            assert not c.exec_driver_sql("PRAGMA foreign_key_check").all()
    finally:
        reopened.dispose()


TAMPERS = ["missing_pdf", "pdf", "docx", "face", "symlink", "traversal", "manifest_filename", "manifest_size", "manifest_hash", "forged_content", "apply_url", "company_missing", "company_swapped", "company_text", "screening", "bank", "facts", "github", "gpa", "degree", "title", "writing_missing", "writing_failed", "writing_recovery", "writing_request", "writing_output", "writing_hash", "writing_malformed"]


def tamper(ready, kind):
    service, builder, p, row, directory = ready
    root = directory / "packets" / p.id
    if kind == "missing_pdf":
        (root / "resume.pdf").unlink()
    elif kind in ("pdf", "docx", "face"):
        name = {"pdf":"resume.pdf","docx":"resume.docx","face":"resume.face.txt"}[kind]
        path = root / name
        path.write_bytes(path.read_bytes()+b'altered')
    elif kind == "symlink":
        path = root / "resume.pdf"
        target = directory / "elsewhere.pdf"
        target.write_bytes(path.read_bytes())
        path.unlink(); path.symlink_to(target)
    elif kind.startswith("manifest") or kind == "traversal":
        with database_session(service.engine) as s:
            packet = s.get(ApplicationPacket, p.id)
            m = json.loads(json.dumps(packet.artifacts))
            if kind in ("manifest_filename","traversal"):
                m["../resume.pdf" if kind == "traversal" else "other.pdf"] = m.pop("resume.pdf")
            elif kind == "manifest_size":
                m["resume.pdf"]["size"] += 1
            else:
                m["resume.pdf"]["sha256"] = "f"*64
            packet.artifacts = m; s.add(packet)
    elif kind in ("forged_content", "github", "gpa", "degree", "title"):
        from job_agent.tailor.render_pdf import render_pdf, render_docx
        face = (root / "resume.face.txt").read_text()
        face = {"forged_content":face.replace("Languages: Python","Languages: Python, Kubernetes"),
                "github":face+"\nhttps://github.com/person", "gpa":face.replace("EDUCATION", "EDUCATION\nGPA 3.18"),
                "degree":face.replace("Bachelor of Arts","Bachelor of Science"),
                "title":face.replace("Applied AI Intern", "AI Engineer")}[kind]
        (root / "resume.face.txt").write_text(face)
        render_pdf(face, root / "resume.pdf"); render_docx(face, root / "resume.docx")
        with database_session(service.engine) as s:
            packet = s.get(ApplicationPacket, p.id)
            packet.artifacts = builder._manifest(root); s.add(packet)
    elif kind == "apply_url":
        with database_session(service.engine) as s:
            r = s.get(SearchResult, row.id)
            r.payload = {**r.payload, "apply_url":"https://example.com/changed?exact=1"}; s.add(r)
    elif kind.startswith("company"):
        with database_session(service.engine) as s:
            packet = s.get(ApplicationPacket, p.id)
            if kind == "company_swapped":
                packet.company_fact_ids = list(reversed(packet.company_fact_ids)); s.add(packet)
            else:
                f = s.get(CompanyFactRecord, packet.company_fact_ids[0])
                if kind == "company_missing":
                    s.delete(f)
                else:
                    f.text = "Acme builds different software for markets."; s.add(f)
    elif kind == "screening":
        with database_session(service.engine) as s:
            packet = s.get(ApplicationPacket, p.id)
            packet.screening_answers = {**packet.screening_answers, "manual_needed":[]}; s.add(packet)
    elif kind in ("bank", "facts"):
        name = "answer_bank.yaml" if kind == "bank" else "facts.yaml"
        path = directory / name
        data = yaml.safe_load(path.read_text())
        data["authorized_us" if kind == "bank" else "summary"] = False if kind == "bank" else "Changed incompatible facts."
        path.write_text(yaml.safe_dump(data))
    elif kind.startswith("writing"):
        with database_session(service.engine) as s:
            work = s.get(WritingWorkItem, p.writing_fingerprints["tailor_resume"])
            if kind == "writing_missing":
                s.delete(work)
            else:
                if kind == "writing_failed": work.state = "failed"
                elif kind == "writing_recovery": work.state = "recovery_required"
                elif kind == "writing_request": work.user_hash = "f"*64
                elif kind == "writing_output": work.output += "Kubernetes"
                elif kind == "writing_hash": work.output_hash = "f"*64
                elif kind == "writing_malformed": work.output = "{malformed"; work.output_hash = digest(work.output)
                s.add(work)


@pytest.mark.parametrize("kind", [k for k in TAMPERS if k != "apply_url"])
def test_integrity_red_team_no_approve(ready, kind):
    service, _, p, _, _ = ready
    tamper(ready, kind)
    with pytest.raises(DecisionError, match="packet_integrity_failed"):
        approve(service, p.id, p.fingerprint)
    assert not decisions(service)


@pytest.mark.parametrize("kind", TAMPERS)
def test_post_approval_tampering_preserves_history(ready, kind):
    service, _, p, _, _ = ready
    record = approve(service, p.id, p.fingerprint)
    tamper(ready, kind)
    assert approve(service, p.id, p.fingerprint).id == record.id  # Replay is historical.
    with pytest.raises(DecisionError):
        service.validate_approval_for_packet(p.id, p.fingerprint)
    current = decisions(service)
    assert len(current) == 1 and current[0].model_dump() == record.model_dump()


@pytest.mark.parametrize("url", ["file:///tmp/apply", "http://localhost", "http://127.0.0.1", "http://10.0.0.1", "http://[::1]", "http://192.0.2.1", "https://user:pass@example.com", "invalid", 123])
def test_invalid_application_destination(ready, url):
    service, _, p, row, _ = ready
    with database_session(service.engine) as s:
        r = s.get(SearchResult, row.id)
        r.payload = {**r.payload, "apply_url":url}; s.add(r)
    with pytest.raises(DecisionError):
        approve(service, p.id, p.fingerprint)
    assert not decisions(service)


def test_public_url_verbatim_and_retrieval_time_independence(ready):
    service, _, p, row, _ = ready
    exact = "https://example.com/apply?x=a%2Fb+Z&x=2#Original"
    with database_session(service.engine) as s:
        r = s.get(SearchResult, row.id); r.payload = {**r.payload,"apply_url":exact}; s.add(r)
    record = approve(service, p.id, p.fingerprint)
    assert json.loads(record.evidence_json)["application_url"] == exact
    with database_session(service.engine) as s:
        from datetime import timedelta
        for fid in p.company_fact_ids:
            f = s.get(CompanyFactRecord,fid); f.retrieved_at += timedelta(days=1); s.add(f)
    assert service.validate_approval_for_packet(p.id,p.fingerprint).decision_id == record.id


@pytest.mark.parametrize("claim", ["Kubernetes", "QuantumTool", "Invented Project", "Improved 99999%"])
def test_screening_truth_blocks_generation_and_forged_current_snapshot(ready, claim):
    service, builder, p, row, directory = ready
    bank = yaml.safe_load((directory / "answer_bank.yaml").read_text())
    bank["prepared_answers"] = {"Experience?":claim}
    (directory / "answer_bank.yaml").write_text(yaml.safe_dump(bank))
    current = PacketService(service.engine, service.settings, executor=builder.executor, clock=lambda: NOW)
    new_row = add_job(current,"2",required_screening_questions=["Experience?"])
    before = len(decisions(service))
    attempt = current.build_one(new_row)
    assert attempt.status == "generation_failed"
    assert attempt.writing_fingerprints == {}
    # Even recomputing input identity and snapshot cannot bless invented prose.
    with database_session(service.engine) as s:
        packet = s.get(ApplicationPacket,p.id)
        r = s.get(SearchResult,row.id)
        r.payload = {**r.payload,"required_screening_questions":["Experience?"]}; s.add(r)
        from job_agent.packets import saved_answers
        packet.screening_answers = saved_answers(current.bank,["Experience?"])
        sourced = [s.get(CompanyFactRecord,fid) for fid in packet.company_fact_ids]
        packet.fingerprint = digest(current._context(r,sourced)); s.add(packet)
        fp = packet.fingerprint
    with pytest.raises(DecisionError,match="packet_integrity_failed"):
        approve(service, p.id, fp)
    assert len(decisions(service)) == before


def test_verifier_is_read_only_and_outbound_isolated(ready, monkeypatch):
    import socket, httpx, anthropic
    from job_agent.tavily_research import TavilyCompanyResearcher
    service, _, p, _, directory = ready
    def trap(*args, **kwargs):
        pytest.fail("Forbidden external or filesystem mutation")
    monkeypatch.setattr(socket.socket,"connect",trap)
    monkeypatch.setattr(socket,"getaddrinfo",trap)
    monkeypatch.setattr(httpx.HTTPTransport,"handle_request",trap)
    monkeypatch.setattr(anthropic,"Anthropic",trap)
    monkeypatch.setattr(TavilyCompanyResearcher,"__init__",trap)
    monkeypatch.setattr(TavilyCompanyResearcher,"research",trap)
    monkeypatch.setattr(Path,"mkdir",trap)
    monkeypatch.setattr(PacketService,"_write_call",trap)
    monkeypatch.setattr(PacketService,"_publish",trap)
    monkeypatch.setattr("job_agent.apply.browser.open_browser",trap)
    monkeypatch.setattr("playwright.sync_api.sync_playwright",trap)
    monkeypatch.setattr(httpx.Client,"send",trap)
    before = {x.name:x.read_bytes() for x in (directory/"packets"/p.id).iterdir()}
    with Session(service.engine) as s:
        rows = s.connection().exec_driver_sql("SELECT * FROM application_packets").all()
        assert verify_packet_integrity(s,service.settings,s.get(ApplicationPacket,p.id))
        assert not s.dirty and not s.new and not s.deleted
    record = approve(service, p.id, p.fingerprint)
    assert service.validate_approval_for_packet(p.id,p.fingerprint).decision_id == record.id
    # Separate immutable versions exercise reject/revise under the same traps.
    with database_session(service.engine) as s:
        for version in (2,3):
            s.add(ApplicationPacket.model_validate({**p.model_dump(),"id":str(version)*32,"version":version,"fingerprint":str(version)*64,"capacity_day":None}))
    service.reject("2"*32,"2"*64,"other")
    service.revise("3"*32,"3"*64,"Private revision feedback")
    with Session(service.engine) as s:
        assert s.connection().exec_driver_sql("SELECT * FROM application_packets WHERE id=?",(p.id,)).all() == rows
    assert before == {x.name:x.read_bytes() for x in (directory/"packets"/p.id).iterdir()}


@pytest.mark.parametrize("failure", [False, True])
def test_populated_genuine_v7_migration_preserves_all_state(setup, monkeypatch, failure):
    """Use the checkpoint's actual schema, never downgrade a v7-created DB."""
    import sqlite3
    from pathlib import Path
    from sqlalchemy import create_engine, event
    from sqlalchemy.exc import IntegrityError
    from job_agent.database import (CanonicalJob, JobIdentity, ApplicationEvent, LLMCall,
        LLMBatch, ScoringWorkItem, SearchResult, database_session)
    service, _, directory = setup
    path = directory / "genuine-v7.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript((Path(__file__).parent / "fixtures/schema_v7.sql").read_text())
        assert connection.execute("PRAGMA user_version").fetchone() == (7,)
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='packet_decisions'").fetchall() == []
    old_engine = create_engine("sqlite:///" + str(path))
    @event.listens_for(old_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    old_service = PacketService(old_engine, service.settings, executor=service.executor, clock=lambda: NOW)
    first_row = add_job(old_service)
    packet = old_service.build_one(first_row)
    assert packet.status == "packet_ready"
    second_row = add_job(old_service, "2", description="Changed public product role context")
    def crash(name):
        if name == "after_writing_claim":
            raise SystemExit("Synthetic durable v7 writing claim")
    old_service._boundary = crash
    with pytest.raises(SystemExit):
        old_service.build_one(second_row)
    old_service._boundary = lambda name: None
    (directory / "packets" / packet.id / "resume.pdf").unlink()
    assert old_service.build_one(first_row).status == "recovery_required"
    successor = old_service.build_one(first_row)
    assert successor.status == "packet_ready" and successor.capacity_day is None
    with database_session(old_engine) as session:
        session.add(CanonicalJob(id="canonical", company="Acme", title="Engineer", location="US",
            posting_url="https://example.com/job", first_seen=NOW, last_seen=NOW))
        session.flush()
        identity = JobIdentity(job_id="canonical", source="demo", external_id="1", first_seen=NOW, last_seen=NOW)
        session.add(identity)
        session.flush()
        row = session.get(SearchResult, first_row.id)
        row.identity_id = identity.id
        row.payload = {**row.payload, "unicode": "café", "null": None, "explicit": False}
        session.add(row)
        session.add(ApplicationEvent(job_id="canonical", external_job_id="1", source="demo", company="Acme",
            title="Engineer", attempt_id="synthetic", status="preview", status_kind="preview", reason="offline",
            notes="synthetic history", follow_up="", occurred_at=NOW, provenance="fixture", payload={"exact": False}))
        session.add(LLMCall(id="call", task="score", model="fake", prompt_name="score", prompt_version="v1",
            status="succeeded", input_tokens=7, output_tokens=11, operational_metadata={"safe": True}))
        session.add(LLMBatch(id="batch", provider_id="fake", status="ended", request_count=1))
        session.flush()
        work = session.exec(select(ScoringWorkItem).where(ScoringWorkItem.external_id == "1")).one()
        work.llm_call_id, work.batch_id, work.canonical_job_id = "call", "batch", "canonical"
        session.add(work)
    with database_session(old_engine) as session:
        from job_agent.database import CompanyResearchCache
        from datetime import timedelta
        session.add(CompanyResearchCache(fingerprint="cache", researcher_version="test-v7", company="Acme",
            title_context="Engineer", facts=research_rows(), created_at=NOW, refreshed_at=NOW, expires_at=NOW+timedelta(days=7)))
    tables = ("jobs", "job_identities", "search_runs", "search_results", "application_events", "llm_calls",
        "scoring_work_items", "llm_batches", "company_facts", "application_packets", "writing_work_items", "company_research_cache")
    with old_engine.connect() as connection:
        before = {name: connection.exec_driver_sql(f'SELECT * FROM {name} ORDER BY 1').all() for name in tables}
        assert all(before.values())
        indexes_triggers = connection.exec_driver_sql(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('index','trigger') ORDER BY type,name").all()
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert connection.exec_driver_sql("SELECT count(*) FROM writing_work_items WHERE state='in_progress'").scalar_one() == 1
    with old_engine.connect() as connection:
        schema_before = connection.exec_driver_sql("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").all()
    old_engine.dispose()
    if failure:
        from sqlalchemy.sql.schema import Table
        original = Table.create
        def interrupted(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            if self.name == "packet_decisions":
                raise RuntimeError("Synthetic after-schema interruption")
            return result
        monkeypatch.setattr(Table, "create", interrupted)
        with pytest.raises(RuntimeError):
            initialize_database(path)
        with sqlite3.connect(path) as connection:
            assert connection.execute("PRAGMA user_version").fetchone() == (7,)
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            assert connection.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall() == [tuple(x) for x in schema_before]
            for name in tables:
                assert connection.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall() == [tuple(x) for x in before[name]]
        return
    upgraded = initialize_database(path)
    try:
        with upgraded.connect() as connection:
            for name in tables:
                assert connection.exec_driver_sql(f'SELECT * FROM {name} ORDER BY 1').all() == before[name]
            assert connection.exec_driver_sql(
                "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('index','trigger') AND tbl_name!='packet_decisions' ORDER BY type,name").all() == indexes_triggers
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            assert connection.exec_driver_sql("PRAGMA user_version").scalar_one() == 8
            assert connection.exec_driver_sql("SELECT count(*) FROM packet_decisions").scalar_one() == 0
            assert connection.exec_driver_sql("SELECT fingerprint FROM application_packets WHERE id=?", (packet.id,)).scalar_one() == packet.fingerprint
        for statement in ("UPDATE application_events SET notes='changed'", "DELETE FROM application_events",
            "UPDATE application_packets SET capacity_day='2026-10-04'", "UPDATE writing_work_items SET state='invalid'"):
            with pytest.raises(IntegrityError):
                with upgraded.begin() as connection:
                    connection.exec_driver_sql(statement)
    finally:
        upgraded.dispose()


def test_v7_migration_transactional_failure(tmp_path, monkeypatch):
    import sqlite3
    from pathlib import Path
    from sqlalchemy.sql.schema import Table
    path = tmp_path / "v7.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript((Path(__file__).parent / "fixtures/schema_v7.sql").read_text())
        before = connection.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
    original = Table.create
    def fail(self, *args, **kwargs):
        if self.name == "packet_decisions":
            original(self, *args, **kwargs)
            raise RuntimeError("Synthetic migration interruption")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Table, "create", fail)
    with pytest.raises(RuntimeError):
        initialize_database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (7,)
        assert connection.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall() == before



def test_successor_requires_independent_approval(ready):
    service,builder,p,row,directory = ready
    original = approve(service, p.id, p.fingerprint)
    (directory/"packets"/p.id/"resume.pdf").unlink()
    assert builder.build_one(row).status == "recovery_required"
    replacement = builder.build_one(row)
    assert replacement.status == "packet_ready" and replacement.version == 2
    with pytest.raises(DecisionError,match="packet_not_approved"):
        service.validate_approval_for_packet(replacement.id,replacement.fingerprint)
    independent = approve(service, replacement.id, replacement.fingerprint)
    assert independent.id != original.id
    assert service.validate_approval_for_packet(replacement.id,replacement.fingerprint)
    assert len(decisions(service)) == 2


@pytest.mark.parametrize("alteration", ["project", "employer", "date", "number", "valid_other_fact"])
def test_forged_face_with_matching_artifacts_and_manifest(ready,alteration):
    service,builder,p,_,directory = ready
    root = directory/"packets"/p.id
    face = (root/"resume.face.txt").read_text()
    replacements = {"project":("Built Python software.","Invented Project"),
        "employer":("Company: Simpro","Company: FakeEmployer"), "date":("Duration: 2025","Duration: 1999"),
        "number":("Built Python software.","Built 99999 Python software."),
        "valid_other_fact":("Python software.","Built Python software.")}
    old,new = replacements[alteration]
    face = face.replace(old,new,1)
    from job_agent.tailor.render_pdf import render_pdf,render_docx
    (root/"resume.face.txt").write_text(face)
    render_pdf(face,root/"resume.pdf");render_docx(face,root/"resume.docx")
    with database_session(service.engine) as s:
        packet=s.get(ApplicationPacket,p.id);packet.artifacts=builder._manifest(root);s.add(packet)
    with pytest.raises(DecisionError,match="packet_integrity_failed"):
        approve(service, p.id, p.fingerprint)


def test_permitted_gating_and_bounded_fit_relationship(ready):
    service,builder,p,row,directory=ready
    from job_agent.tailor.render_pdf import drop_last_responsibility, render_pdf,render_docx
    from job_agent.tailor.tailor import TailorResult
    from job_agent.cli import _gate
    with database_session(service.engine) as s:
        work=s.get(WritingWorkItem,p.writing_fingerprints["tailor_resume"])
        # Same approved qualitative bullet repeated, testing allowed fitting only.
        work.output=work.output.replace("- Built Python software.\n","- Built Python software.\n"*5)
        work.output_hash=digest(work.output);s.add(work)
        raw=work.output
    checked=_gate(builder.facts,TailorResult(resume_text=raw,notes="",raw=raw),row.payload["description"])
    fitted=drop_last_responsibility(checked.resume_text)
    assert fitted!=checked.resume_text and fitted!=raw
    root=directory/"packets"/p.id
    (root/"resume.face.txt").write_text(fitted)
    render_pdf(fitted,root/"resume.pdf");render_docx(fitted,root/"resume.docx")
    with database_session(service.engine) as s:
        packet=s.get(ApplicationPacket,p.id);packet.artifacts=builder._manifest(root);s.add(packet)
    assert approve(service, p.id, p.fingerprint)


@pytest.mark.parametrize("url",["http://127.0.0.1.nip.io","http://localtest.me","https://host.invalid"," https://example.com/apply","https://192.0.2.1.example.com"])
def test_public_looking_private_destination_aliases(ready,url):
    service,_,p,row,_=ready
    with database_session(service.engine) as s:
        r=s.get(SearchResult,row.id);r.payload={**r.payload,"apply_url":url};s.add(r)
    with pytest.raises(DecisionError):approve(service, p.id, p.fingerprint)


def test_caller_owned_dirty_session_is_not_flushed(ready):
    service,_,p,_,_=ready
    with Session(service.engine) as s:
        packet=s.get(ApplicationPacket,p.id)
        packet.failure_reason="Uncommitted synthetic marker"
        verify_packet_integrity(s,service.settings,packet)
        assert s.dirty
        assert s.connection().exec_driver_sql("SELECT failure_reason FROM application_packets WHERE id=?",(p.id,)).scalar_one() is None


def test_revision_with_embedded_nul_preserved(ready):
    service,_,p,_,_=ready
    feedback="  café\x00\nfeedback  "
    assert service.revise(p.id,p.fingerprint,feedback).detail==feedback


def test_storage_failures_do_not_expose_feedback(ready,monkeypatch):
    service,_,p,_,_=ready
    marker="PRIVATE_FEEDBACK_MARKER"
    def fail(*args,**kwargs):
        raise IntegrityError("INSERT", {"detail":marker}, RuntimeError(marker))
    monkeypatch.setattr(Session,"flush",fail)
    with pytest.raises(DecisionError,match="decision_storage_failed") as exc:
        service.revise(p.id,p.fingerprint,marker)
    assert marker not in str(exc.value)


def test_begin_immediate_precedes_decision_reads(ready):
    from sqlalchemy import event
    service,_,p,_,_=ready
    statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):
        statements.append(statement)
    event.listen(service.engine,"before_cursor_execute",record)
    try:
        service.reject(p.id,p.fingerprint,"other")
    finally:
        event.remove(service.engine,"before_cursor_execute",record)
    assert statements[0] == "BEGIN IMMEDIATE"
    assert next(i for i,x in enumerate(statements) if "packet_decisions" in x and x.startswith("SELECT")) > 0


def test_reject_and_revise_without_packet_directory(ready):
    import shutil
    service,_,p,_,directory=ready
    shutil.rmtree(directory/"packets"/p.id)
    assert service.revise(p.id,p.fingerprint,"Keep original feedback")
    assert not (directory/"packets"/p.id).exists()


@pytest.mark.parametrize("detail",["\x00"+"x"*4000,"x\x00"+"界"*4000])
def test_embedded_nul_cannot_bypass_direct_sql_character_bound(ready,detail):
    service,_,p,_,_=ready
    with pytest.raises(IntegrityError):
        with service.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO packet_decisions (id,packet_id,packet_fingerprint,decision,actor,reason_code,detail,created_at,evidence_version,evidence_json) VALUES (?,?,?,?,?,?,?,?,?,?)",("direct",p.id,p.fingerprint,"revise","Andrew","",detail,"2026-10-05",1,"{}"))
    assert not decisions(service)


def test_full_unicode_revision_bound_with_embedded_nul(ready):
    service,_,p,_,_=ready
    feedback="\x00"+"界"*3999
    assert service.revise(p.id,p.fingerprint,feedback).detail==feedback


def test_trusted_checkpoint_writing_identity_reconstructs(ready):
    """Actual checkpoint builder, not a hand-written approximation of requests."""
    import subprocess
    from types import ModuleType
    import job_agent.packets
    service,builder,_,_,_=ready
    source=subprocess.check_output(["git","show","3d802bb:src/job_agent/packets.py"],text=True)
    trusted=ModuleType("trusted_checkpoint_packets")
    trusted.__file__=job_agent.packets.__file__
    exec(compile(source,trusted.__file__,"exec"),trusted.__dict__)
    original=trusted.PacketService(service.engine,service.settings,executor=builder.executor,clock=lambda:NOW)
    row=add_job(original,"trusted-packet")
    packet=original.build_one(row)
    assert packet.status=="packet_ready"
    record=approve(service, packet.id, packet.fingerprint)
    assert service.validate_approval_for_packet(packet.id,packet.fingerprint).decision_id==record.id


@pytest.mark.parametrize("title_change", ["oversized", "key"])
def test_production_company_source_title_policy_is_revalidated(ready,title_change):
    from test_company_research import configure_packet, FakeTransport, response, result
    service,builder,_,_,_=ready
    configure_packet(builder,FakeTransport(response(result(0),result(1),result(2))))
    packet=builder.build_one(add_job(builder,"production-source"))
    assert packet.status=="packet_ready"
    service=ApprovalService(builder.engine,builder.settings)
    record=approve(service, packet.id, packet.fingerprint)
    with database_session(service.engine) as s:
        fact=s.get(CompanyFactRecord,packet.company_fact_ids[0])
        # source_title is deliberately absent from semantic_fact_id. It must
        # still rerun current local source policy during current authorization.
        fact.source_title="Acme "+"A"*300 if title_change=="oversized" else builder.settings.tavily_api_key.get_secret_value()
        s.add(fact)
    with pytest.raises(DecisionError,match="packet_integrity_failed"):
        service.validate_approval_for_packet(packet.id,packet.fingerprint)
    assert approve(service, packet.id, packet.fingerprint).id==record.id


def test_preview_deterministic_safe_read_only(ready):
    service, _, p, _, directory = ready
    with service.engine.connect() as c:
        before = c.exec_driver_sql('SELECT * FROM application_packets').all()
    first = service.preview_approval(p.id, p.fingerprint)
    assert first == service.preview_approval(p.id, p.fingerprint)
    with Session(service.engine) as s:
        evidence = verify_packet_integrity(s, service.settings, s.get(ApplicationPacket, p.id)).evidence_json
    assert first.approval_view_fingerprint == hashlib.sha256(evidence.encode()).hexdigest()
    assert first.packet_version == p.version and first.packet_fingerprint == p.fingerprint
    assert p.cover_letter not in repr(first) and str(directory) not in repr(first)
    with database_session(service.engine) as s:
        from datetime import timedelta
        for fid in p.company_fact_ids:
            fact = s.get(CompanyFactRecord, fid)
            fact.retrieved_at += timedelta(days=1)
            s.add(fact)
    assert first == service.preview_approval(p.id, p.fingerprint)
    with service.engine.connect() as c:
        assert before == c.exec_driver_sql('SELECT * FROM application_packets').all()
    assert not decisions(service)


def test_stale_url_view_and_historical_replay(ready, monkeypatch):
    service, _, p, row, _ = ready
    first = service.preview_approval(p.id, p.fingerprint)
    with database_session(service.engine) as s:
        r = s.get(SearchResult, row.id)
        r.payload = {**r.payload, 'apply_url': 'https://example.com/new-destination'}
        s.add(r)
        assert s.get(ApplicationPacket, p.id).fingerprint == p.fingerprint
    with pytest.raises(DecisionError, match='stale_approval_view'):
        service.approve(p.id, p.fingerprint, first.approval_view_fingerprint)
    assert not decisions(service)
    second = service.preview_approval(p.id, p.fingerprint)
    assert second.approval_view_fingerprint != first.approval_view_fingerprint
    record = service.approve(p.id, p.fingerprint, second.approval_view_fingerprint)
    tamper(ready, 'apply_url')
    with pytest.raises(DecisionError):
        service.validate_approval_for_packet(p.id, p.fingerprint)
    def trap(*args, **kwargs):
        pytest.fail('Historical replay must not validate current evidence')
    monkeypatch.setattr('job_agent.approvals.verify_packet_integrity', trap)
    assert service.approve(p.id, p.fingerprint, second.approval_view_fingerprint).id == record.id
    with pytest.raises(DecisionError, match='stale_approval_view'):
        service.approve(p.id, p.fingerprint, first.approval_view_fingerprint)


@pytest.mark.parametrize('kind', [k for k in TAMPERS if k != 'apply_url'])
def test_completed_evidence_change_after_preview(ready, kind):
    service, _, p, _, _ = ready
    preview = service.preview_approval(p.id, p.fingerprint)
    tamper(ready, kind)
    with pytest.raises(DecisionError):
        service.approve(p.id, p.fingerprint, preview.approval_view_fingerprint)
    assert not decisions(service)


@pytest.mark.parametrize('token', [None, '', 'f'*63, 'G'*64, '0'*64])
def test_approve_requires_completed_view(ready, token):
    service, _, p, _, _ = ready
    with pytest.raises(TypeError):
        service.approve(p.id, p.fingerprint)
    with pytest.raises(DecisionError, match='stale_approval_view'):
        service.approve(p.id, p.fingerprint, token)
    assert not decisions(service)


def test_only_selected_prepared_answers_are_truth_checked(ready):
    service, builder, _, _, directory = ready
    path = directory / 'answer_bank.yaml'
    bank = yaml.safe_load(path.read_text())
    bank['prepared_answers'] = {'Used?': 'Built Python software.', 'Unused?': 'Kubernetes'}
    path.write_text(yaml.safe_dump(bank))
    current = PacketService(service.engine, service.settings, executor=builder.executor, clock=lambda: NOW)
    row = add_job(current, 'selected-safe', required_screening_questions=['Used?'])
    packet = current.build_one(row)
    assert packet.status == 'packet_ready', packet.failure_reason
    preview = service.preview_approval(packet.id, packet.fingerprint)
    record = service.approve(packet.id, packet.fingerprint, preview.approval_view_fingerprint)
    assert service.validate_approval_for_packet(packet.id, packet.fingerprint).decision_id == record.id
    unsafe = current.build_one(add_job(current, 'selected-unsafe', required_screening_questions=['Unused?']))
    assert unsafe.status == 'generation_failed' and not unsafe.writing_fingerprints
    with database_session(service.engine) as s:
        r = s.get(SearchResult, row.id)
        r.payload = {**r.payload, 'required_screening_questions': ['Unused?']}
        s.add(r)
    with pytest.raises(DecisionError):
        service.validate_approval_for_packet(packet.id, packet.fingerprint)
    bank['prepared_answers']['Unused?'] = 'QuantumTool'
    path.write_text(yaml.safe_dump(bank))
    changed = PacketService(service.engine, service.settings, executor=builder.executor, clock=lambda: NOW)
    assert changed.bank._source_hash != current.bank._source_hash
    assert changed.input_hash != current.input_hash


def test_historical_poisoned_company_opening_fails_shared_integrity_gate(ready, monkeypatch):
    from test_packets import poison_company_opening, POISONED_OPENING
    service, builder, _, _, directory = ready
    current = poison_company_opening(builder, directory)
    row = add_job(current, "historical-poison")
    # Construct an otherwise coherent historical packet using the former boundary.
    # Only the new attribution check is bypassed during this TEST fixture build.
    with monkeypatch.context() as historical:
        historical.setattr("job_agent.packet_verify.company_opening_references_candidate", lambda *args: False)
        packet = current.build_one(row)
    assert packet.status == "packet_ready", packet.failure_reason
    assert packet.cover_letter.startswith(POISONED_OPENING)
    # Prove rejection reaches the shared truth gate, rather than a stale hash or
    # an unrelated artifact check. All historical input/output hashes are intact.
    import job_agent.packet_verify as gate
    original = gate.company_opening_references_candidate
    checked = []
    def observed(text, name):
        checked.append(text)
        return original(text, name)
    monkeypatch.setattr(gate, "company_opening_references_candidate", observed)
    with Session(current.engine) as session:
        with pytest.raises(ValueError):
            verify_packet_integrity(session, current.settings, packet)
    assert checked == [POISONED_OPENING]
    checked.clear()
    with pytest.raises(DecisionError, match="packet_integrity_failed"):
        approve(service, packet.id, packet.fingerprint)
    assert POISONED_OPENING in checked
    assert decisions(service) == []
