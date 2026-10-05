"""Local-only historical views/diffs and narrow revision CLI; never authorization."""
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from rich.console import Console
from sqlmodel import Session, select

from job_agent.approvals import ApprovalService
from job_agent.database import (ApplicationPacket, PacketDecision, PacketRevisionWork, WritingWorkItem,
    CanonicalJob, database_session)
from job_agent.packet_history import HistoryError, list_packet_versions, diff_resume, diff_cover, _unified
from job_agent.packets import PacketService, digest
from job_agent.revisions import RevisionProcessor
from test_packets import setup as packet_setup, add_job, NOW, RESUME
from test_revisions import offline_only, revision_setup, revision_successor, genuine_v8


@pytest.fixture
def history_pair(revision_setup):
    processor, service, calls, directory, source, decision = revision_setup
    facts = yaml.safe_load((directory / "facts.yaml").read_text())
    facts["employers"][0]["real_bullets"].append("Built Python tools.")
    (directory / "facts.yaml").write_text(yaml.safe_dump(facts))
    original = service.executor.create
    def output(**request):
        if request["task"] == "tailor_resume":
            calls.append(request)
            text = RESUME.replace("Built Python software.", "Built Python tools.")
        else:
            text = json.loads(original(**request).content[0].text)
            text["candidate_lines"] = ["Built Python tools."]
            text = json.dumps(text)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])
    processor.executor = SimpleNamespace(create=output)
    work = processor.process_revision(decision.id)
    assert work.state == "succeeded", work.failure_code
    return service, calls, directory, source, revision_successor(processor, work), processor


def trap_current_and_providers(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("historical_views_must_be_local_and_independent_of_current_truth")
    for target in ("job_agent.packets._local_verifier", "job_agent.packets.load_career_facts",
                   "job_agent.packets.load_answer_bank", "job_agent.packets.style_lock",
                   "job_agent.style_memory.read_style_memory", "job_agent.packets.TavilyCompanyResearcher",
                   "job_agent.packets.PacketService._write_call", "job_agent.tailor.tailor.tailor_resume"):
        monkeypatch.setattr(target, forbidden)


def test_history_v1_v2_v3_lineage_and_failed_latest_allocated(history_pair):
    service, calls, directory, first, second, processor = history_pair
    decision = ApprovalService(service.engine, service.settings).revise(second.id, second.fingerprint, "Third preference")
    # Allocate v3, but deliberately stop before generation; it then represents a
    # failed newer version without hiding the earlier latest-ready packet.
    def stop(name):
        if name == "after_successor_allocation":
            raise SystemExit()
    processor._boundary = stop
    with pytest.raises(SystemExit):
        processor.process_revision(decision.id)
    with database_session(service.engine) as session:
        work = session.get(PacketRevisionWork, decision.id)
        third = session.get(ApplicationPacket, work.successor_packet_id)
        third.status = "generation_failed"
        session.add(third)
    rows = list_packet_versions(service.engine, packet_id=first.id)
    assert [row["version"] for row in rows] == [1, 2, 3]
    assert [row["decision"] for row in rows] == ["revise", "revise", None]
    assert [row["source_packet_id"] for row in rows] == [None, first.id, second.id]
    assert [row["lineage_kind"] for row in rows] == ["unlinked", "revision", "revision"]
    assert [row["is_latest_allocated"] for row in rows] == [False, False, True]
    assert [row["is_latest_ready"] for row in rows] == [False, True, False]
    assert rows == list_packet_versions(service.engine, job_key=first.job_key)
    assert rows[0]["writing_prompt_version"] == first.writing_prompt_version
    assert rows[1]["style_memory_hash"] == second.style_memory_hash
    assert all(row["created_at"].endswith("Z") and row["updated_at"].endswith("Z") for row in rows)
    encoded = json.dumps(rows)
    assert str(directory) not in encoded and "feedback" not in encoded
    assert "Prefer specific wording" not in encoded and "cover_letter" not in encoded
    assert "artifacts" not in encoded and "screening_answers" not in encoded


def test_history_distinguishes_recovery_without_inventing_lineage(packet_setup):
    service, calls, directory = packet_setup
    row = add_job(service)
    first = service.build_one(row)
    (directory / "packets" / first.id / "resume.pdf").write_bytes(b"damaged")
    assert service.build_one(row).status == "recovery_required"
    second = service.build_one(row)
    assert second.status == "packet_ready"
    history = list_packet_versions(service.engine, job_key=first.job_key)
    assert history[0]["source_packet_id"] is None
    assert history[1]["lineage_kind"] == "corruption_recovery"
    assert history[1]["source_packet_id"] == first.id and history[1]["revision_decision_id"] is None


def test_canonical_history_and_stable_id_tiebreaker(packet_setup):
    service, calls, directory = packet_setup
    with database_session(service.engine) as session:
        session.add(CanonicalJob(id="canonical", company="Acme", title="Engineer", location="US",
            posting_url="https://example.com/job", first_seen=NOW.replace(tzinfo=None), last_seen=NOW.replace(tzinfo=None)))
    for packet_id, key in [("b" * 32, "demo:b"), ("a" * 32, "demo:a")]:
        row = add_job(service, key.split(":")[1])
        with database_session(service.engine) as session:
            session.add(ApplicationPacket(id=packet_id, job_key=key, version=1,
                search_result_id=row.id, scoring_fingerprint=row.payload["scoring_fingerprint"], status="building",
                canonical_job_id="canonical", fingerprint=hashlib.sha256(key.encode()).hexdigest(),
                company="Acme", title="Engineer", score=80, tier="A"))
    rows = list_packet_versions(service.engine, canonical_job_id="canonical")
    assert [row["packet_id"] for row in rows] == ["a" * 32, "b" * 32]
    assert rows == list_packet_versions(service.engine, packet_id="a" * 32)
    assert rows == list_packet_versions(service.engine, job_key="demo:b")
    assert [row["is_latest_allocated"] for row in rows] == [False, True]
    assert not any(row["is_latest_ready"] for row in rows)
    assert not calls


@pytest.mark.parametrize("selector", [{}, {"packet_id": "../bad"}, {"job_key": ""},
    {"job_key": "demo:1", "packet_id": "a" * 32}, {"canonical_job_id": 123}])
def test_history_invalid_selectors_are_sanitized(packet_setup, selector):
    service, calls, directory = packet_setup
    with pytest.raises(HistoryError, match="^invalid_history_reference$"):
        list_packet_versions(service.engine, **selector)


def test_history_absent_selection(packet_setup):
    service, calls, directory = packet_setup
    assert list_packet_versions(service.engine, job_key="absent") == []
    assert list_packet_versions(service.engine, canonical_job_id="absent") == []
    with pytest.raises(HistoryError, match="^packet_not_found$"):
        list_packet_versions(service.engine, packet_id="f" * 32)


def test_resume_and_cover_diffs_are_deterministic_local_and_historical(history_pair, monkeypatch, caplog):
    service, calls, directory, first, second, processor = history_pair
    # Current truth/eligibility is intentionally unavailable. Intact historical
    # content is still displayable; successful diffs cannot authorize approval.
    (directory / "facts.yaml").unlink()
    (directory / "answer_bank.yaml").unlink()
    (directory / "style_memory.md").unlink()
    trap_current_and_providers(monkeypatch)
    before_calls = len(calls)
    service.engine.echo = True
    with caplog.at_level("DEBUG"):
        resume = diff_resume(service.engine, service.settings, first.id, second.id)
        cover = diff_cover(service.engine, service.settings, first.id, second.id)
        history = list_packet_versions(service.engine, packet_id=first.id)
    assert resume.status == cover.status == "available"
    assert "-- Built Python software." in resume.diff and "+- Built Python tools." in resume.diff
    assert "-Built Python software." in cover.diff and "+Built Python tools." in cover.diff
    assert "\\ No newline at end of file" in cover.diff
    for result in (resume, cover):
        assert result.diff.startswith(f"--- packet:{first.id}/version:1\n+++ packet:{second.id}/version:2\n")
        assert str(directory) not in result.diff
        assert "Built Python" not in caplog.text
    assert "Prefer specific wording" not in caplog.text
    assert resume == diff_resume(service.engine, service.settings, first.id, second.id)
    assert cover == diff_cover(service.engine, service.settings, first.id, second.id)
    assert len(calls) == before_calls
    assert not (directory / "style_memory.md").exists()
    assert history[0]["decision"] == "revise" and history[1]["decision"] is None
    assert not hasattr(resume, "authorized") and not hasattr(cover, "approved")


@pytest.mark.parametrize("kind", ["resume", "cover"])
def test_diff_same_packet_is_empty(history_pair, kind):
    service, calls, directory, first, second, processor = history_pair
    operation = diff_resume if kind == "resume" else diff_cover
    result = operation(service.engine, service.settings, first.id, first.id)
    assert result.status == "available" and result.diff == ""


@pytest.mark.parametrize("kind", ["resume", "cover"])
@pytest.mark.parametrize("case", ["different_job", "missing", "malformed", "not_completed"])
def test_diff_invalid_or_unavailable_case(history_pair, kind, case):
    service, calls, directory, first, second, processor = history_pair
    other_id = second.id
    if case == "different_job":
        other_id = service.build_one(add_job(service, "other")).id
    elif case == "missing":
        other_id = "f" * 32
    elif case == "malformed":
        other_id = "../../private"
    else:
        with database_session(service.engine) as session:
            pending = ApplicationPacket(job_key=first.job_key, version=3, fingerprint="c" * 64,
                search_result_id=first.search_result_id, scoring_fingerprint=first.scoring_fingerprint, status="building",
                company="Acme", title="Engineer", score=80, tier="A")
            session.add(pending)
            session.flush()
            other_id = pending.id
    operation = diff_resume if kind == "resume" else diff_cover
    result = operation(service.engine, service.settings, first.id, other_id)
    assert result.status == ("invalid_request" if case in ("different_job", "malformed") else "unavailable")
    assert result.diff is None


@pytest.mark.parametrize("damage", ["missing_face", "face", "manifest", "face_rehashed", "pdf", "docx",
    "symlink_face", "symlink_directory", "symlink_root", "nonregular_face", "hardlinked_face", "extra_file"])
def test_resume_diff_rejects_damaged_historical_content(history_pair, damage):
    service, calls, directory, first, second, processor = history_pair
    published = directory / "packets" / first.id
    face = published / "resume.face.txt"
    if damage == "missing_face":
        face.unlink()
    elif damage in ("face", "face_rehashed"):
        face.write_text("tampered historical face")
        if damage == "face_rehashed":
            with database_session(service.engine) as session:
                packet = session.get(ApplicationPacket, first.id)
                packet.artifacts = {**packet.artifacts, "resume.face.txt": dict(
                    sha256=hashlib.sha256(face.read_bytes()).hexdigest(), size=face.stat().st_size)}
                session.add(packet)
    elif damage == "manifest":
        with database_session(service.engine) as session:
            packet = session.get(ApplicationPacket, first.id)
            packet.artifacts = {**packet.artifacts, "../resume.face.txt": packet.artifacts["resume.face.txt"]}
            session.add(packet)
    elif damage in ("pdf", "docx"):
        (published / f"resume.{damage}").write_bytes(b"tampered")
    elif damage == "symlink_face":
        copy = directory / "copy-face"
        copy.write_bytes(face.read_bytes())
        face.unlink()
        face.symlink_to(copy)
    elif damage in ("symlink_directory", "symlink_root"):
        original = published if damage == "symlink_directory" else directory / "packets"
        moved = directory / "moved-packets"
        original.rename(moved)
        original.symlink_to(moved, target_is_directory=True)
    elif damage == "nonregular_face":
        face.unlink()
        os.mkfifo(face)
    elif damage == "hardlinked_face":
        os.link(face, directory / "linked-face")
    else:
        (published / "unexpected.txt").write_text("extra")
    result = diff_resume(service.engine, service.settings, first.id, second.id)
    assert result.status == ("unavailable" if damage == "missing_face" else "integrity_failed")
    assert result.diff is None and len(calls) == 4


@pytest.mark.parametrize("damage", ["cover", "missing_cover", "output", "output_hash", "task", "prompt_version",
    "system_hash", "state", "missing_work", "max_tokens"])
def test_cover_diff_authenticates_bound_checkpoint_and_draft(history_pair, damage):
    service, calls, directory, first, second, processor = history_pair
    with database_session(service.engine) as session:
        packet = session.get(ApplicationPacket, first.id)
        work = session.get(WritingWorkItem, packet.writing_fingerprints["cover_letter"])
        if damage in ("cover", "missing_cover"):
            packet.cover_letter = "tampered" if damage == "cover" else ""
            if damage == "missing_cover":
                packet.status = "recovery_required"
            session.add(packet)
        elif damage == "missing_work":
            session.delete(work)
        else:
            setattr(work, damage, {"output": "tampered", "output_hash": "f" * 64, "task": "another_task",
                "prompt_version": "unsupported", "system_hash": "e" * 64, "state": "recovery_required",
                "max_tokens": 1}[damage])
            session.add(work)
    result = diff_cover(service.engine, service.settings, first.id, second.id)
    assert result.status == ("unavailable" if damage in ("missing_cover", "missing_work") else "integrity_failed")
    assert result.diff is None and len(calls) == 4


@pytest.mark.parametrize("left,right", [("old\n", "new\n"), ("old", "new"), ("same", "same\n"),
    ("same\n", "same"), ("a\nb\n", "a\nadded\nb\n"), ("a\nremoved\nb\n", "a\nb\n")])
def test_unified_diff_preserves_changes_and_terminal_newline(left, right):
    first, second = SimpleNamespace(id="a" * 32, version=1), SimpleNamespace(id="b" * 32, version=2)
    result = _unified(left, right, first, second)
    assert result == _unified(left, right, first, second)
    assert "@@" in result
    assert ("\\ No newline at end of file" in result) == (not left.endswith("\n") or not right.endswith("\n"))


def test_resume_diff_terminal_newline_is_not_hidden(history_pair):
    service, calls, directory, first, second, processor = history_pair
    # Authenticate a historical formatting-only terminal newline change using
    # consistently rendered bytes and the exact stored manifest.
    from job_agent.tailor.render_pdf import render_pdf, render_docx
    published = directory / "packets" / first.id
    original = (published / "resume.face.txt").read_bytes()
    changed = original.rstrip(b"\n") + b"\n"
    (published / "resume.face.txt").write_bytes(changed)
    render_pdf(changed.decode(), published / "resume.pdf")
    render_docx(changed.decode(), published / "resume.docx")
    with database_session(service.engine) as session:
        packet = session.get(ApplicationPacket, first.id)
        packet.artifacts = service._manifest(published)
        session.add(packet)
    result = diff_resume(service.engine, service.settings, first.id, second.id)
    assert result.status == "available"
    # The changed side retains its LF; the unmodified side has no terminal LF.
    assert "\\ No newline at end of file" in result.diff


def cli_environment(service, monkeypatch):
    from job_agent.cli import _build_parser, cmd_revision_process
    from job_agent.revisions import process_revision
    @contextmanager
    def database(data_dir):
        assert data_dir == service.settings.data_dir
        yield service.engine
    monkeypatch.setattr("job_agent.cli.search_database", database)
    monkeypatch.setattr("job_agent.cli.load_settings", lambda: service.settings)
    def local(engine, settings, decision_id):
        return process_revision(engine, settings, decision_id, executor=service.executor, clock=lambda: NOW)
    monkeypatch.setattr("job_agent.revisions.process_revision", local)
    return _build_parser(), cmd_revision_process


def test_revision_cli_processes_only_immutable_id_and_reports_safe_metadata(revision_setup, monkeypatch):
    processor, service, calls, directory, source, decision = revision_setup
    parser, handler = cli_environment(service, monkeypatch)
    args = parser.parse_args(["revision-process", "--decision-id", decision.id, "--data-dir", str(directory)])
    output = io.StringIO()
    console = Console(file=output, width=200, color_system=None)
    assert handler(console, args) == 0
    assert handler(console, args) == 0 and len(calls) == 4
    result = output.getvalue()
    assert "succeeded" in result and decision.id in result
    assert decision.detail not in result and str(directory) not in result
    with Session(service.engine) as session:
        assert len(session.exec(select(ApplicationPacket)).all()) == 2
        assert session.exec(select(PacketDecision).where(PacketDecision.packet_id != source.id)).first() is None


@pytest.mark.parametrize("flag", ["--feedback", "--bypass-capacity", "--packet-id", "--provider-url", "--apply", "--submit"])
def test_revision_cli_rejects_arbitrary_authority_or_bypass(flag):
    from job_agent.cli import _build_parser
    with pytest.raises(SystemExit) as error:
        _build_parser().parse_args(["revision-process", "--decision-id", "a" * 32, flag, "unsafe"])
    assert error.value.code == 2


def test_revision_cli_requires_decision_id():
    from job_agent.cli import _build_parser
    with pytest.raises(SystemExit) as error:
        _build_parser().parse_args(["revision-process"])
    assert error.value.code == 2


def test_revision_cli_invalid_decision_is_sanitized(revision_setup, monkeypatch):
    processor, service, calls, directory, source, decision = revision_setup
    parser, handler = cli_environment(service, monkeypatch)
    args = parser.parse_args(["revision-process", "--decision-id", "f" * 32])
    output = io.StringIO()
    assert handler(Console(file=output), args) == 1
    assert "details omitted" in output.getvalue()
    assert decision.detail not in output.getvalue() and len(calls) == 2


def test_revision_cli_blocked_returns_review_state(revision_setup, monkeypatch):
    processor, service, calls, directory, source, decision = revision_setup
    with service.engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM company_facts WHERE id=?", (source.company_fact_ids[0],))
    parser, handler = cli_environment(service, monkeypatch)
    args = parser.parse_args(["revision-process", "--decision-id", decision.id])
    output = io.StringIO()
    assert handler(Console(file=output, width=200), args) == 2
    assert "blocked" in output.getvalue() and "source_evidence_invalid" in output.getvalue()
    assert decision.detail not in output.getvalue() and len(calls) == 2


def test_revision_cli_main_dispatch(monkeypatch):
    from job_agent.cli import main
    seen = []
    def handler(console, args):
        seen.append((args.command, args.decision_id))
        return 7
    monkeypatch.setattr("job_agent.cli.cmd_revision_process", handler)
    assert main(["revision-process", "--decision-id", "a" * 32]) == 7
    assert seen == [("revision-process", "a" * 32)]


def test_genuine_legacy_history_diffs_after_migration_ignore_current_truth_and_style(genuine_v8, monkeypatch):
    from job_agent.database import initialize_database
    from test_revisions import private_file
    state = genuine_v8
    engine = initialize_database(state["path"])
    private_file(state["directory"] / "style_memory.md", "Current preferences are unrelated to legacy content.")
    (state["directory"] / "facts.yaml").unlink()
    (state["directory"] / "answer_bank.yaml").unlink()
    trap_current_and_providers(monkeypatch)
    try:
        rows = list_packet_versions(engine, packet_id=state["ready_id"])
        assert len(rows) == 1 and rows[0]["writing_prompt_version"] == "v4-semantic-writing-cache"
        assert rows[0]["style_memory_hash"] is None and rows[0]["decision"] == "approve"
        # The legacy packet has no direct canonical binding; retained JobIdentity
        # still reaches the existing canonical job relationship.
        assert rows == list_packet_versions(engine, canonical_job_id="legacy-canonical")
        resume = diff_resume(engine, state["settings"], state["ready_id"], state["ready_id"])
        cover = diff_cover(engine, state["settings"], state["ready_id"], state["ready_id"])
        assert resume.status == cover.status == "available"
        assert resume.diff == cover.diff == ""
        assert diff_resume(engine, state["settings"], state["damaged_id"], state["damaged_id"]).status == "unavailable"
    finally:
        engine.dispose()


def test_history_and_diffs_do_not_mutate_database_artifacts_or_decisions(history_pair):
    service, calls, directory, first, second, processor = history_pair
    def snapshot():
        with service.engine.connect() as connection:
            names = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").scalars().all()
            rows = {name: connection.exec_driver_sql(f'SELECT * FROM "{name}"').all() for name in names}
        files = {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*")
                 if path.is_file() and path.suffix not in (".sqlite", "-wal", "-shm")
                 and "test.sqlite" not in path.name}
        return rows, files
    before = snapshot()
    assert list_packet_versions(service.engine, packet_id=first.id)
    assert diff_resume(service.engine, service.settings, first.id, second.id).status == "available"
    assert diff_cover(service.engine, service.settings, first.id, second.id).status == "available"
    assert snapshot() == before and len(calls) == 4


@pytest.mark.parametrize("kind", ["resume", "cover"])
def test_history_diffs_ignore_current_terminal_eligibility(history_pair, kind):
    service, calls, directory, first, second, processor = history_pair
    with database_session(service.engine) as session:
        from job_agent.database import SearchResult, ScoringWorkItem
        row = session.get(SearchResult, first.search_result_id)
        row.payload = {**row.payload, "score": 0, "scoring_status": "failed"}
        session.add(row)
        work = session.exec(select(ScoringWorkItem).where(ScoringWorkItem.fingerprint == first.scoring_fingerprint)).one()
        work.state = "failed"
        session.add(work)
    operation = diff_resume if kind == "resume" else diff_cover
    assert operation(service.engine, service.settings, first.id, second.id).status == "available"
    assert len(calls) == 4


@pytest.mark.parametrize("damage", ["size", "hash", "unsafe_filename", "invalid_utf8", "unsafe_data_dir"])
def test_resume_diff_additional_storage_boundaries(history_pair, damage):
    service, calls, directory, first, second, processor = history_pair
    if damage == "unsafe_data_dir":
        alias = directory.parent / (directory.name + "-alias")
        alias.symlink_to(directory, target_is_directory=True)
        settings = service.settings.model_copy(update={"data_dir": alias})
    else:
        settings = service.settings
        with database_session(service.engine) as session:
            packet = session.get(ApplicationPacket, first.id)
            manifest = {name: dict(value) for name, value in packet.artifacts.items()}
            if damage == "size":
                manifest["resume.face.txt"]["size"] = 20_000_001
            elif damage == "hash":
                manifest["resume.face.txt"]["sha256"] = "f" * 64
            elif damage == "unsafe_filename":
                manifest["/private/resume.face.txt"] = manifest.pop("resume.face.txt")
            else:
                face = directory / "packets" / first.id / "resume.face.txt"
                face.write_bytes(b"\xffinvalid utf8")
                manifest["resume.face.txt"] = dict(sha256=hashlib.sha256(face.read_bytes()).hexdigest(), size=face.stat().st_size)
            packet.artifacts = manifest
            session.add(packet)
    result = diff_resume(service.engine, settings, first.id, second.id)
    assert result.status == "integrity_failed" and result.diff is None


def test_cover_diff_rehashed_output_still_requires_exact_stored_draft(history_pair):
    service, calls, directory, first, second, processor = history_pair
    with database_session(service.engine) as session:
        work = session.get(WritingWorkItem, first.writing_fingerprints["cover_letter"])
        draft = json.loads(work.output)
        draft["candidate_lines"] = ["Changed historical text."]
        work.output = json.dumps(draft)
        work.output_hash = digest(work.output)
        session.add(work)
    result = diff_cover(service.engine, service.settings, first.id, second.id)
    assert result.status == "integrity_failed" and result.diff is None
