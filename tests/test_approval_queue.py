"""Bounded exact-version selection; cards are candidates, never verification."""
from datetime import timedelta

import pytest
from sqlmodel import Session, select
from sqlalchemy import event

from job_agent.database import ApplicationPacket, PacketDecision
from job_agent.dashboard.approval_models import QueueQuery
from job_agent.dashboard.approval_service import ApprovalQueueService
from test_packets import setup, add_job, NOW


def insert_packet(builder, row, *, version=1, score=80, status="packet_ready", ready=True, packet_id=None):
    with Session(builder.engine, expire_on_commit=False) as session:
        p = ApplicationPacket(job_key=f"demo:{row.legacy_key}", search_result_id=row.id,
            fingerprint=f"{row.id * 100 + version:064x}", scoring_fingerprint=f"score-{row.legacy_key}",
            version=version, status=status, score=score, tier="A", company="Acme", title="Engineer",
            verifier_status="passed", lint_status="passed", cover_letter="PRIVATE_COVER",
            screening_answers={"saved": {"secret_unused": "NEVER_RETURN"}, "answers": {}, "manual_needed": ["Unknown?"]},
            ready_at=NOW.replace(tzinfo=None) + timedelta(seconds=version) if ready else None,
            **({"id": packet_id} if packet_id else {}))
        session.add(p)
        session.commit()
        return p


def test_queue_preserves_all_undecided_and_older_ready(setup, monkeypatch):
    builder, _, _ = setup
    row = add_job(builder)
    first = insert_packet(builder, row)
    second = insert_packet(builder, row, version=2)
    insert_packet(builder, row, version=3, status="generation_failed", ready=False)
    def trap(*args, **kwargs):
        raise AssertionError("queue must not verify/read PDFs/generate")
    monkeypatch.setattr("job_agent.approvals.verify_packet_integrity", trap)
    monkeypatch.setattr("job_agent.dashboard.approval_service.authenticated_cover_text", trap)
    monkeypatch.setattr(builder.executor, "create", trap)
    result = ApprovalQueueService(builder.engine, builder.settings).queue(QueueQuery())
    assert [i.packet_id for i in result.items] == [first.id, second.id]
    assert all(i.integrity == "not_checked" and i.manual_needed_count == 1 for i in result.items)
    assert "PRIVATE_COVER" not in result.model_dump_json() and "NEVER_RETURN" not in result.model_dump_json()


def test_queue_sort_pagination_and_sql_projection(setup):
    builder, _, _ = setup
    one, two = add_job(builder, id="one"), add_job(builder, id="two")
    first = insert_packet(builder, one, score=91, packet_id="1" * 32)
    second = insert_packet(builder, two, score=91, packet_id="2" * 32)
    insert_packet(builder, one, version=2, score=85)
    statements = []
    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(builder.engine, "before_cursor_execute", capture)
    result = ApprovalQueueService(builder.engine, builder.settings).queue(QueueQuery(limit=1, offset=1))
    event.remove(builder.engine, "before_cursor_execute", capture)
    assert result.items[0].packet_id == second.id
    assert first.id != second.id
    assert len(statements) == 1 and "LIMIT" in statements[0] and "OFFSET" in statements[0]
    assert "cover_letter," not in statements[0] and "evidence_json" not in statements[0]
    assert "BEGIN IMMEDIATE" not in statements[0]


def test_queue_sections_and_exact_decision_exclusion(setup):
    builder, _, _ = setup
    row = add_job(builder)
    decided = insert_packet(builder, row)
    undecided = insert_packet(builder, row, version=2)
    building = insert_packet(builder, row, version=3, status="building", ready=False)
    failed = insert_packet(builder, row, version=4, status="generation_failed", ready=False)
    with Session(builder.engine) as session:
        session.add(PacketDecision(packet_id=decided.id, packet_fingerprint=decided.fingerprint,
            decision="revise", detail="Exact feedback", evidence_json="{}"))
        session.commit()
    service = ApprovalQueueService(builder.engine, builder.settings)
    assert [i.packet_id for i in service.queue(QueueQuery()).items] == [undecided.id]
    assert {i.packet_id for i in service.queue(QueueQuery(section="processing")).items} == {decided.id, building.id}
    assert [i.packet_id for i in service.queue(QueueQuery(section="needs-attention")).items] == [failed.id]
    assert [i.packet_id for i in service.queue(QueueQuery(section="history")).items] == [decided.id]


def test_queue_ready_at_required(setup):
    builder, _, _ = setup
    insert_packet(builder, add_job(builder), ready=False)
    assert not ApprovalQueueService(builder.engine, builder.settings).queue(QueueQuery()).items


@pytest.mark.parametrize("values", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"section": "latest"}, {"tier": "unknown"}])
def test_queue_invalid_filters(values):
    with pytest.raises(ValueError):
        QueueQuery(**values)
