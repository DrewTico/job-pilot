"""Durable scoring and manually operated Message Batches. No scheduling or retries."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import re

from sqlmodel import Session, select

from job_agent.database import LLMBatch, LLMCall, ScoringWorkItem, SearchResult, _utc
from job_agent.llm import (budget_state, reconcile_stale_standard_reservations,
                           reservation_cost, normalize_usage, calculate_cost)
from job_agent.models import Job, ScoredJob
from job_agent.scoring import build_score_request, parse_score_message, load_score_prompt


def scoring_route(posted_at, now, *, first_observed=None, max_age_hours=48):
    if max_age_hours < 0:
        raise ValueError("Age threshold must be nonnegative")
    reference = posted_at or first_observed
    if reference is None:
        return "deferred"
    reference = reference.replace(tzinfo=timezone.utc) if reference.tzinfo is None else reference
    return "immediate" if now - reference < timedelta(hours=max_age_hours) else "deferred"


def candidate_hash(profile):
    return hashlib.sha256(profile.candidate_summary.strip().encode()).hexdigest()


def scoring_fingerprint(job, profile, model, *, prompt_version="v1", company_facts=()):
    data = dict(job=job.model_dump(mode="json"), model=model, prompt_name="score",
                prompt_version=prompt_version, prompt_hash=hashlib.sha256(load_score_prompt().encode()).hexdigest(),
                candidate_hash=candidate_hash(profile),
                company_facts=[f.model_dump(mode="json") for f in company_facts])
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def custom_id(work_id, attempt):
    if not isinstance(attempt, int) or attempt < 1:
        raise ValueError("Invalid batch attempt")
    value = f"sw_{work_id}_{attempt}"
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value):
        raise ValueError("Invalid batch custom ID")
    return value


def plan_search_scoring(session, jobs, profile, settings, now):
    """Read-only plan. Existing work always wins over a new paid request."""
    from job_agent.database import JobRepository
    immediate, reused = [], {}
    repo = JobRepository(session)
    for job in jobs:
        fingerprint = scoring_fingerprint(job, profile, settings.scoring_model)
        work = session.exec(select(ScoringWorkItem).where(ScoringWorkItem.fingerprint == fingerprint)).first()
        if work:
            if work.state == "succeeded":
                reused[(job.source, job.id)] = ScoredJob(job=job, **work.result)
            continue
        prior = session.exec(select(SearchResult).where(
            SearchResult.payload["scoring_fingerprint"].as_string() == fingerprint
        ).order_by(SearchResult.id.desc())).all()
        match = next((r for r in prior if r.payload.get("score") is not None), None)
        if match:
            fields = {key: value for key, value in match.payload.items()
                      if key in ScoredJob.model_fields and key != "job"}
            reused[(job.source, job.id)] = ScoredJob(job=job, **fields)
            continue
        identity = repo.get_identity(job.source, job.id)
        first = identity.first_seen if identity else None
        if scoring_route(job.posted_at, now, first_observed=first,
                         max_age_hours=settings.immediate_scoring_max_age_hours) == "immediate":
            immediate.append(job)
    return immediate, reused


def claim_standard_score(engine, job, profile, model):
    """Serialize claim acquisition; return (canonical work, owned by this caller).

    ON CONFLICT is the final uniqueness guard. No provider IO occurs here.
    Existing work, including failed or unknown work, is never auto-requeued.
    """
    from sqlalchemy.dialects.sqlite import insert
    fingerprint = scoring_fingerprint(job, profile, model)
    proposed = ScoringWorkItem(
        fingerprint=fingerprint, source=job.source, external_id=job.id,
        model=model, candidate_hash=candidate_hash(profile),
        state="standard_in_progress", priority_at=_utc())
    with Session(engine, expire_on_commit=False) as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        canonical = session.exec(select(ScoringWorkItem).where(
            ScoringWorkItem.fingerprint == fingerprint)).first()
        if canonical is None:
            session.execute(insert(ScoringWorkItem).values(**proposed.model_dump())
                            .on_conflict_do_nothing(index_elements=["fingerprint"]))
            canonical = session.exec(select(ScoringWorkItem).where(
                ScoringWorkItem.fingerprint == fingerprint)).one()
        owned = canonical.id == proposed.id
        session.commit()
        return canonical, owned


def _finish_standard_claim(engine, claim_id, *, scored=None, failure=None):
    with Session(engine) as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        work = session.get(ScoringWorkItem, claim_id)
        if work.state == "standard_in_progress":
            work.updated_at = _utc()
            if scored is not None and scored.score is not None and scored.verdict != "unscored":
                work.state = "succeeded"
                from job_agent.scoring import detect_content_flags
                work.result = {**scored.model_dump(mode="json", exclude={"job"}),
                               "content_flags": list(detect_content_flags(scored.job))}
            else:
                work.state = "failed"
                work.failure = failure or "standard_scoring_unscored"
            session.add(work)
        session.commit()
        if work.state == "succeeded":
            return ScoredJob(job=scored.job, **work.result)
        return scored


def score_claimed_standard(engine, job, profile, model, score):
    """Durably claim before invoking the injected synchronous scorer once."""
    from job_agent.scoring import detect_content_flags
    work, owned = claim_standard_score(engine, job, profile, model)
    if not owned:
        if work.state == "succeeded":
            return ScoredJob(job=job, **work.result)
        return ScoredJob(job=job, reasons=("Scoring recovery required",),
                         content_flags=detect_content_flags(job))
    try:
        scored = score()
    except Exception as exc:
        # Store only an exception class, never provider text or candidate content.
        _finish_standard_claim(engine, work.id, failure=type(exc).__name__)
        raise
    return _finish_standard_claim(engine, work.id, scored=scored)


def checkpoint_immediate_score(engine, scored, profile, model):
    """Commit reusable paid work independently of the atomic search transaction."""
    if scored.score is None or scored.verdict == "unscored":
        return scored
    from sqlalchemy.dialects.sqlite import insert
    fingerprint = scoring_fingerprint(scored.job, profile, model)
    work = ScoringWorkItem(
        fingerprint=fingerprint, source=scored.job.source, external_id=scored.job.id,
        model=model, candidate_hash=candidate_hash(profile), state="succeeded",
        priority_at=_utc(), result=scored.model_dump(mode="json", exclude={"job"}))
    with Session(engine) as session:
        # A competing completion wins; never overwrite a canonical assessment.
        session.execute(insert(ScoringWorkItem).values(**work.model_dump()).on_conflict_do_nothing(
            index_elements=["fingerprint"]))
        session.commit()
        canonical = session.exec(select(ScoringWorkItem).where(
            ScoringWorkItem.fingerprint == fingerprint)).one()
        if canonical.state == "succeeded":
            return ScoredJob(job=scored.job, **canonical.result)
    return scored


def enqueue(session, result, job, profile, model):
    fingerprint = scoring_fingerprint(job, profile, model)
    work = session.exec(select(ScoringWorkItem).where(ScoringWorkItem.fingerprint == fingerprint)).first()
    if work is None:
        observed = result.payload.get("first_seen")
        reference = job.posted_at or (datetime.fromisoformat(observed) if observed else None)
        priority = _utc(reference.replace(tzinfo=timezone.utc) if reference.tzinfo is None else reference) if reference else _utc()
        work = ScoringWorkItem(fingerprint=fingerprint, source=job.source, external_id=job.id,
                              canonical_job_id=result.payload.get("canonical_id"), search_result_id=result.id,
                              model=model, candidate_hash=candidate_hash(profile),
                              reservation_cost_usd=str(reservation_cost(build_score_request(model, job, profile), "batch")),
                              priority_at=priority)
        session.add(work)
        session.flush()
    if work.search_result_id is None:
        work.search_result_id = result.id
        work.canonical_job_id = result.payload.get("canonical_id")
        session.add(work)
    payload = {**result.payload, "scoring_fingerprint": fingerprint, "scoring_work_id": work.id,
               "scoring_status": work.state}
    if work.state == "succeeded":
        payload.update(work.result)
    result.payload = payload
    session.add(result)
    return work


class BatchService:
    def __init__(self, engine, settings, profile=None, *, client=None, clock=None):
        self.engine, self.settings, self.profile = engine, settings, profile
        self.client = client
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def provider(self):
        if self.client is None:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key, max_retries=0)
        return self.client.messages.batches

    def pending(self):
        with Session(self.engine) as session:
            rows = session.exec(select(ScoringWorkItem).where(ScoringWorkItem.state == "pending")).all()
            state = budget_state(session, self.settings.monthly_budget_usd, self.clock())
            ordered = sorted(rows, key=lambda r: (r.created_at, r.id))
            ordered.sort(key=lambda r: r.priority_at, reverse=True)
            head_blocked = bool(ordered) and Decimal(ordered[0].reservation_cost_usd) > state.budget - state.spend - state.reserved
            outstanding = session.exec(select(ScoringWorkItem).where(ScoringWorkItem.state.in_(["submitted", "submission_unknown"]))).all()
            unknown_batches = {b.id for b in session.exec(select(LLMBatch).where(LLMBatch.status.in_(["submitting", "submission_unknown"])))}
            return dict(waiting=len(rows), oldest=min((r.created_at for r in rows), default=None),
                        newest=max((r.created_at for r in rows), default=None),
                        spend=str(state.spend), reserved=str(state.reserved), warning=state.warning,
                        budget_blocked=state.paused or head_blocked, outstanding=len(outstanding),
                        recovery_required=sum(1 for r in outstanding if r.batch_id in unknown_batches))

    def submit(self):
        requests = []
        now = self.clock()
        with Session(self.engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            reconcile_stale_standard_reservations(session, now)
            state = budget_state(session, self.settings.monthly_budget_usd, now)
            remaining = state.budget - state.spend - state.reserved
            rows = session.exec(select(ScoringWorkItem).where(ScoringWorkItem.state == "pending")
                                .order_by(ScoringWorkItem.priority_at.desc(), ScoringWorkItem.created_at, ScoringWorkItem.id)
                                .limit(self.settings.max_batch_items)).all()
            prepared = []
            payload_bytes = 0
            blocked = None
            for work in rows:
                target = session.get(SearchResult, work.search_result_id)
                job = Job.model_validate(target.payload)
                if self.profile is None:
                    raise ValueError("Scoring profile required for submission")
                if scoring_fingerprint(job, self.profile, work.model, prompt_version=work.prompt_version) != work.fingerprint:
                    work.failure = "scoring_inputs_changed"
                    session.add(work)
                    continue
                params = build_score_request(work.model, job, self.profile)
                reserve = reservation_cost(params, "batch")
                size = len(json.dumps(params, ensure_ascii=False).encode("utf-8"))
                if payload_bytes + size > 20 * 1024 * 1024:
                    blocked = "payload_limit"
                    break
                if reserve > remaining:
                    blocked = "budget"
                    break  # Largest priority prefix, never skip an expensive head.
                remaining -= reserve
                payload_bytes += size
                prepared.append((work, params, reserve, custom_id(work.id, work.attempt_count + 1)))
            if not prepared:
                session.commit()
                return dict(submitted=0, budget_blocked=blocked == "budget", blocked_reason=blocked or ("scoring_inputs_changed" if rows else None))
            batch = LLMBatch(created_at=_utc(now), updated_at=_utc(now), request_count=len(prepared))
            session.add(batch)
            session.flush()
            for work, params, reserve, cid in prepared:
                call = LLMCall(created_at=_utc(now), task="scoring", model=work.model,
                               prompt_name=work.prompt_name, prompt_version=work.prompt_version,
                               request_kind="batch", reserved_cost_usd=str(reserve),
                               external_job_reference=f"{work.source}:{work.external_id}",
                               canonical_job_id=work.canonical_job_id,
                               operational_metadata={"custom_id": cid, "batch_id": batch.id})
                session.add(call)
                session.flush()
                work.state, work.batch_id, work.custom_id, work.llm_call_id = "submitted", batch.id, cid, call.id
                work.attempt_count += 1
                work.updated_at = _utc(now)
                session.add(work)
                requests.append(dict(custom_id=cid, params=params))
            if not 1 <= len(requests) <= 100000 or len({r['custom_id'] for r in requests}) != len(requests):
                raise ValueError("Invalid batch requests")
            session.commit()
        # A crash from this point is conservatively outstanding, including before IO.
        try:
            response = self.provider().create(requests=requests)
            if not response.id:
                raise ValueError("Missing provider batch ID")
        except Exception:
            with Session(self.engine) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                local = session.get(LLMBatch, batch.id)
                local.status = "submission_unknown"
                local.updated_at = _utc(self.clock())
                session.add(local)
                for work in session.exec(select(ScoringWorkItem).where(ScoringWorkItem.batch_id == batch.id)):
                    work.state, work.failure = "submission_unknown", "submission_outcome_unknown"
                    work.updated_at = _utc(self.clock())
                    call = session.get(LLMCall, work.llm_call_id)
                    call.operational_metadata = {**call.operational_metadata, "submission_outcome_unknown": True}
                    session.add(call)
                    session.add(work)
                session.commit()
            raise RuntimeError("Batch submission outcome unknown; reservations retained") from None
        with Session(self.engine) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            local = session.get(LLMBatch, batch.id)
            local.provider_id = response.id
            self._status(local, response)
            session.add(local)
            for work in session.exec(select(ScoringWorkItem).where(ScoringWorkItem.batch_id == batch.id)):
                call = session.get(LLMCall, work.llm_call_id)
                call.operational_metadata = {**call.operational_metadata, "provider_batch_id": response.id}
                session.add(call)
            session.commit()
        return dict(submitted=len(requests), batch_id=response.id)

    def _status(self, local, response):
        local.status = response.processing_status
        local.updated_at = _utc(self.clock())
        created = getattr(response, "created_at", None)
        if created:
            local.provider_created_at = _utc(datetime.fromisoformat(created.replace("Z", "+00:00")) if isinstance(created, str) else created)
        expires = getattr(response, "expires_at", None)
        if expires:
            local.expires_at = _utc(datetime.fromisoformat(expires.replace("Z", "+00:00")) if isinstance(expires, str) else expires)

    def status(self):
        with Session(self.engine) as session:
            batches = session.exec(select(LLMBatch).where(LLMBatch.provider_id != None)).all()
        statuses = []
        for batch in batches:
            response = self.provider().retrieve(batch.provider_id)
            with Session(self.engine) as session:
                local = session.get(LLMBatch, batch.id)
                self._status(local, response)
                session.add(local)
                session.commit()
            statuses.append(dict(batch_id=batch.provider_id, status=response.processing_status))
        return statuses

    def reconcile(self):
        with Session(self.engine) as session:
            batches = session.exec(select(LLMBatch).where(LLMBatch.status == "ended", LLMBatch.provider_id != None)).all()
        count = 0
        for batch in batches:
            for entry in self.provider().results(batch.provider_id):
                count += self._reconcile_item(batch.id, entry)
        return dict(reconciled=count)

    def _reconcile_item(self, batch_id, entry):
        with Session(self.engine) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            work = session.exec(select(ScoringWorkItem).where(ScoringWorkItem.batch_id == batch_id,
                                                            ScoringWorkItem.custom_id == entry.custom_id)).first()
            if work is None:
                raise ValueError("Unknown batch custom ID; reservations retained")
            call = session.get(LLMCall, work.llm_call_id)
            if call.status != "reserved":
                return 0
            result = entry.result
            kind = result.type
            if kind not in ("succeeded", "errored", "canceled", "expired"):
                work.failure = "unknown_result_type"
                session.add(work)
                session.commit()
                return 0
            if kind == "succeeded":
                message = result.message
                if getattr(message, "usage", None) is None:
                    work.failure = "missing_paid_usage"
                    session.add(work)
                    session.commit()
                    return 0
                usage = normalize_usage(message)
                if any(v < 0 for v in usage.values()):
                    raise ValueError("Invalid usage; reservation retained")
                for field, value in usage.items():
                    setattr(call, field, value)
                call.estimated_cost_usd = str(max(Decimal(call.estimated_cost_usd), calculate_cost(work.model, usage, "batch")))
                call.status = "succeeded"
                try:
                    target = session.get(SearchResult, work.search_result_id)
                    score = parse_score_message(Job.model_validate(target.payload), message)
                    work.result = score.model_dump(mode="json", exclude={"job"})
                    work.state, work.failure = "succeeded", None
                except (ValueError, TypeError, AttributeError):
                    work.state, work.failure = "retryable", "malformed_paid_output"
            else:
                call.status = "failed"
                call.error_type = kind
                work.state, work.failure = "retryable", kind
                if kind == "errored":
                    # Stable SDK wraps ErrorObject inside ErrorResponse.
                    error_response = getattr(result, "error", None)
                    error_type = getattr(getattr(error_response, "error", None), "type", None)
                    if error_type in {"invalid_request_error", "authentication_error", "permission_error", "billing_error", "not_found_error"}:
                        work.state, work.failure = "failed", error_type
                    else:
                        work.failure = "provider_error"
            call.reserved_cost_usd = "0"
            call.operational_metadata = {**call.operational_metadata, "result_type": kind}
            work.updated_at = _utc(self.clock())
            session.add(call)
            session.add(work)
            # Only exact input matches and still-unscored results may receive this score.
            for target in session.exec(select(SearchResult).where(
                    SearchResult.payload["scoring_fingerprint"].as_string() == work.fingerprint)):
                if target.payload.get("scoring_fingerprint") != work.fingerprint or target.payload.get("score") is not None:
                    continue
                payload = {**target.payload, "scoring_status": work.state}
                if work.state == "succeeded":
                    payload.update(work.result)
                target.payload = payload
                session.add(target)
            session.commit()
            return 1
