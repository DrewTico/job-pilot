"""Read-only local operational visibility. No schema migration or provider IO."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from sqlalchemy import create_engine
from sqlmodel import Session, select

from job_agent.database import LLMBatch, LLMCall, ScoringWorkItem
from job_agent.llm import budget_state

STATES = ("pending", "submitted", "succeeded", "retryable", "failed",
          "submission_unknown", "standard_in_progress")


def status(engine, settings, *, now=None):
    with Session(engine) as session:
        counts = dict.fromkeys(STATES, 0)
        work = session.exec(select(ScoringWorkItem)).all()
        for row in work:
            counts[row.state] += 1
        batches = session.exec(select(LLMBatch)).all()
        reserved = session.exec(select(LLMCall).where(LLMCall.status == "reserved")).all()
        unresolved = {r.operational_metadata.get("batch_id") for r in reserved}
        unresolved.update(r.batch_id for r in work if r.state == "submitted")
        budget = budget_state(session, settings.monthly_budget_usd, now or datetime.now(timezone.utc))
        return dict(scoring=counts,
                    provider_batches_in_progress=sum(b.provider_id is not None and b.status != "ended" for b in batches),
                    provider_batches_ended_unreconciled=sum(b.provider_id is not None and b.status == "ended" and b.id in unresolved for b in batches),
                    batches_without_trusted_provider_id=sum(b.provider_id is None for b in batches),
                    monthly_spend=str(budget.spend), reserved_exposure=str(budget.reserved),
                    monthly_budget=str(budget.budget), warning=budget.warning, paused=budget.paused,
                    operator_review={s: counts[s] for s in ("submission_unknown", "standard_in_progress")})


def local_status(settings):
    path = (Path(settings.data_dir) / "job_pilot.sqlite3").resolve()
    engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(path.as_uri() + "?mode=ro", uri=True))
    try:
        return status(engine, settings)
    finally:
        engine.dispose()
