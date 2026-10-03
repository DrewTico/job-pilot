"""Offline-testable Anthropic execution with independent durable accounting.

Reservations serialize admission, not application transactions. A crashed process
leaves its reservation conservatively charged after automatic reconciliation.
Calendar months are UTC, matching persisted database timestamps.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from time import perf_counter

from sqlmodel import Session, select

from job_agent.config import Settings
from job_agent.database import LLMCall, initialize_database


class LLMBudgetExceeded(RuntimeError):
    pass


class UnknownModelPricing(ValueError):
    pass


@dataclass(frozen=True)
class Pricing:
    input: Decimal
    output: Decimal
    cache_read: Decimal
    cache_write: Decimal


PRICING = {
    "claude-sonnet-5-5": Pricing(*(Decimal(v) for v in ("2", "10", ".20", "2.50"))),
    "claude-haiku-4-5-20251001": Pricing(*(Decimal(v) for v in ("1", "5", ".10", "1.25"))),
}
TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
# Synchronous requests normally finish within minutes, unlike outstanding batches.
STALE_STANDARD_RESERVATION_AFTER = timedelta(hours=1)


def normalize_usage(response):
    usage = getattr(response, "usage", None)
    return {name: int((usage.get(name, 0) if isinstance(usage, dict)
                       else getattr(usage, name, 0)) or 0) for name in TOKEN_FIELDS}


def calculate_cost(model, usage, request_kind="standard"):
    if model not in PRICING:
        raise UnknownModelPricing(f"No verified pricing for model {model}")
    if request_kind not in ("standard", "batch"):
        raise ValueError("Invalid request kind")
    p = PRICING[model]
    discount = Decimal(".5") if request_kind == "batch" else Decimal(1)
    return discount * (usage.get("input_tokens", 0) * p.input
                       + usage.get("output_tokens", 0) * p.output
                       + usage.get("cache_creation_input_tokens", 0) * p.cache_write
                       + usage.get("cache_read_input_tokens", 0) * p.cache_read) / Decimal(1000000)


def month_bounds(now):
    start = now.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start.replace(tzinfo=None), end.replace(tzinfo=None)


@dataclass(frozen=True)
class BudgetState:
    spend: Decimal
    reserved: Decimal
    budget: Decimal

    @property
    def warning(self):
        return self.spend + self.reserved >= self.budget * Decimal(".8")

    @property
    def paused(self):
        return self.spend + self.reserved >= self.budget


def budget_state(session, budget, now):
    start, end = month_bounds(now)
    rows = session.exec(select(LLMCall).where(LLMCall.created_at >= start, LLMCall.created_at < end)).all()
    return BudgetState(sum((Decimal(r.estimated_cost_usd) for r in rows), Decimal(0)),
                       sum((Decimal(r.reserved_cost_usd) for r in session.exec(select(LLMCall).where(LLMCall.status == "reserved"))), Decimal(0)), budget)


def cached_system(text):
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def reconcile_stale_standard_reservations(session, now):
    """Finalize stale reservations; caller must hold a BEGIN IMMEDIATE transaction.

    Flush without committing so reconciliation and admission share one lock.
    No usage is inferred, and the charged estimate can only increase.
    """
    cutoff = (now.astimezone(timezone.utc) - STALE_STANDARD_RESERVATION_AFTER).replace(tzinfo=None)
    rows = session.exec(select(LLMCall).where(
        LLMCall.status == "reserved", LLMCall.request_kind == "standard",
        LLMCall.created_at <= cutoff)).all()
    for row in rows:
        row.estimated_cost_usd = str(max(Decimal(row.estimated_cost_usd), Decimal(row.reserved_cost_usd)))
        row.reserved_cost_usd = "0"
        row.status = "failed"
        row.error_type = "stale_reservation_reconciled"
        row.error_message = "Stale synchronous reservation conservatively charged; usage unknown"
        row.operational_metadata = {**(row.operational_metadata or {}), "stale_reservation_reconciled": True}
        session.add(row)
    session.flush()
    return len(rows)


def reservation_cost(request, request_kind="standard"):
    model = request["model"]
    calculate_cost(model, {}, request_kind)
    bound = len(json.dumps(request, ensure_ascii=False).encode("utf-8")) + 4096
    p = PRICING[model]
    return (bound * max(p.input, p.cache_write) + request["max_tokens"] * p.output) / Decimal(1000000) * (Decimal(".5") if request_kind == "batch" else Decimal(1))


class AnthropicExecutor:
    def __init__(self, client, settings: Settings, *, engine=None, clock=None):
        self.client = client
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        if engine is None:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            engine = initialize_database(settings.data_dir / "job_pilot.sqlite3")
        self.engine = engine

    def state(self):
        with Session(self.engine) as session:
            return budget_state(session, self.settings.monthly_budget_usd, self.clock())

    def create(self, *, task, prompt_name, prompt_version, external_job_reference=None,
               canonical_job_id=None, **request):
        model = request["model"]
        calculate_cost(model, {})  # Unknown price blocks before IO/network.
        # Upper bound for text-only requests: each UTF-8 byte can be a token.
        # Include schemas and framing allowance; reserve worst-case cache writes.
        # This is admission sizing, never reported as actual token usage.
        reserve = reservation_cost(request)
        now = self.clock()
        row = LLMCall(created_at=now.astimezone(timezone.utc).replace(tzinfo=None), task=task,
                      model=model, prompt_name=prompt_name, prompt_version=prompt_version,
                      external_job_reference=external_job_reference, canonical_job_id=canonical_job_id,
                      reserved_cost_usd=str(reserve))
        with Session(self.engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            reconcile_stale_standard_reservations(session, now)
            state = budget_state(session, self.settings.monthly_budget_usd, now)
            if state.paused or state.spend + state.reserved + reserve > state.budget:
                session.commit()  # Retain reconciliation even when admission is denied.
                raise LLMBudgetExceeded("Monthly LLM budget cannot cover this request")
            session.add(row)
            session.commit()
        started = perf_counter()
        try:
            response = self.client.messages.create(**request)
        except Exception:
            # Exception messages can include prompts, credentials, or response bodies.
            self._finish(row.id, started, status="failed", error_type="provider_error",
                         error_message="Anthropic request failed; provider details omitted",
                         operational_metadata={"usage_available": False})
            raise
        usage = normalize_usage(response)
        self._finish(row.id, started, status="succeeded", **usage,
                     estimated_cost_usd=str(calculate_cost(model, usage)),
                     provider_request_id=getattr(response, "_request_id", None),
                     operational_metadata={"usage_available": getattr(response, "usage", None) is not None})
        return response

    def _finish(self, row_id, started, **values):
        with Session(self.engine) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            row = session.get(LLMCall, row_id)
            if (row.operational_metadata or {}).get("stale_reservation_reconciled"):
                # A delayed live request must never undo the conservative charge.
                values["estimated_cost_usd"] = str(max(
                    Decimal(row.estimated_cost_usd), Decimal(values.get("estimated_cost_usd", "0"))))
                values["operational_metadata"] = {
                    **row.operational_metadata, **values.get("operational_metadata", {}),
                    "stale_reservation_reconciled": True}
            for name, value in values.items():
                setattr(row, name, value)
            row.reserved_cost_usd = "0"
            row.latency_ms = max(0, int((perf_counter() - started) * 1000))
            session.add(row)
            session.commit()
