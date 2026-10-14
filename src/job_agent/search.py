"""The discovery pipeline: fetch → keyword → freshness → location → seniority
→ dedup → enrichment → eligibility → experience.

The keyword pre-filter runs *before* anything expensive so we never spend an LLM
call on the hundreds of unrelated roles a company board carries. Every stage's
survivor count is returned (not hidden) so the CLI can show exactly what was
pruned — no silent truncation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict
import hashlib
import json

from job_agent.config import SearchProfile
from job_agent.eligibility import passes_eligibility
from job_agent.experience import required_years
from job_agent.geo import infer_country
from job_agent.models import (IntakeEvidence, Job, DurableObservation,
                              ObservationOccurrence, SourceSnapshot)
from job_agent.seen_cache import SeenCache
from job_agent.seniority import LEVEL_NAMES, seniority_rank
from job_agent.sources import JobSource, build_source

FRESH_WINDOW = timedelta(days=14)

# A job is dropped on experience only when its JD requires at least this many
# more years than the candidate has (so an "8+ years" role is dropped for a
# 5-year candidate, but "6+"/"7+" and reachable ranges are kept).
EXPERIENCE_GAP = 3

# Country strings (any case) we treat as the United States.
_US_ALIASES = {"US", "USA", "U.S.", "U.S.A.", "UNITED STATES", "UNITED STATES OF AMERICA"}


class StageCounts(BaseModel):
    """How many jobs survived each pipeline stage."""

    model_config = ConfigDict(frozen=True)

    fetched: int = 0
    after_keyword: int = 0
    after_fresh: int = 0
    after_location: int = 0
    after_seniority: int = 0
    after_dedup: int = 0
    after_eligibility: int = 0
    after_experience: int = 0


class SearchOutcome(BaseModel):
    """Result of a discovery run: the survivors plus visibility into pruning."""

    model_config = ConfigDict(frozen=True)

    jobs: list[Job]
    boards: list[str]                    # board token per job (parallel to jobs)
    counts: StageCounts
    per_source: dict[str, int]           # board label -> jobs fetched
    warnings: list[str] = []             # source failures, etc. (never fatal)
    first_seen: dict[str, str] = {}      # survivor job id -> first-observed ISO time
    new_job_ids: tuple[str, ...] = ()    # ids whose first-seen was recorded THIS scan
    baseline_scan: bool = False          # the seen cache was empty when the scan began
    intake_evidence: dict[str, IntakeEvidence] = {}  # source:id, including filtered observations
    observations: dict[str, DurableObservation] = {}
    source_snapshots: dict[str, SourceSnapshot] = {}
    observed_at: datetime | None = None

    @property
    def publishable(self):
        # An incomplete empty response cannot establish a useful empty search.
        return bool(self.jobs) or bool(self.source_snapshots) and all(
            s.status == 'complete' for s in self.source_snapshots.values())


def matches_keywords(title: str, keywords: list[str]) -> bool:
    """True if the title contains any keyword (case-insensitive substring)."""
    low = title.lower()
    return any(kw.lower() in low for kw in keywords)


def _country_allowed(country: str | None, allowed: list[str]) -> bool | None:
    """True/False if the job's country is known; None if unknown."""
    if country is None:
        return None
    c = country.strip().upper()
    allowed_up = {a.upper() for a in allowed}
    want_us = bool(allowed_up & {"US", "USA", "UNITED STATES"})
    if want_us and c in _US_ALIASES:
        return True
    return c in allowed_up


def passes_location(job: Job, profile: SearchProfile) -> bool:
    """Apply the location rule.

    * Known country → honor the allow-list, *even for remote roles* (a role that
      is "remote within the UK" still needs employer relocation support and
      visa sponsorship that is not explicitly denied).
    * No structured country → infer one from the location text (``geo``). A
      *clearly* foreign string ("Bengaluru, India") follows the same mobility
      exception as a structured country.
    * Still unknown → keep it: if it's remote, gate on ``remote_ok``; otherwise
      leave it for the scorer to weigh.
    """
    rule = profile.location
    country = job.country or infer_country(job.location)
    allowed = _country_allowed(country, rule.allowed_countries)
    if allowed is not None:
        return allowed or (job.relocation == "supported"
                           and job.visa_sponsorship is not False)
    if job.remote:
        return rule.remote_ok
    return True


def passes_seniority(job: Job, profile: SearchProfile) -> bool:
    """Drop titles above the profile's ceiling. ``max_seniority`` None = off.

    With ``max_seniority: senior`` this drops Lead / Manager / Staff / Principal / Director
    / VP and keeps Senior/Sr. and below — title-only, so it runs cheaply before
    dedup and enrichment.
    """
    if profile.max_seniority is None:
        return True
    return seniority_rank(job.title) <= LEVEL_NAMES[profile.max_seniority]


def passes_experience(job: Job, profile: SearchProfile) -> bool:
    """Drop jobs whose JD requires clearly more years than the candidate has.

    ``experience_years`` None = off. A JD with no stated minimum is kept (left to
    the scorer). Runs after enrichment so every source's full JD is available.
    """
    if profile.experience_years is None:
        return True
    required = required_years(job.description or "")
    if required is None:
        return True
    return required < profile.experience_years + EXPERIENCE_GAP


def is_fresh(job: Job, now: datetime, cache: SeenCache,
             window: timedelta = FRESH_WINDOW) -> bool:
    """Posted within the freshness window. Jobs without a post date fall back to
    'first observed within the window' via the seen-ids cache."""
    reference = job.posted_at or cache.observe(job.source, job.id, now)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return (now - reference) <= window


def validate_observed_job(value):
    """Offline admission boundary for every normalized adapter result."""
    from job_agent.sources.simplify import _url, _bad_controls
    try:
        job = Job.model_validate(value.model_dump() if isinstance(value, Job) else value)
        for field, limit in (('id', 128), ('title', 512), ('company', 512),
                             ('location', 2048), ('country', 128), ('description', 16384)):
            text = getattr(job, field)
            if text is not None and (len(text) > limit or _bad_controls(text)):
                raise ValueError('field_limit')
        if not job.id or not job.title or not job.company:
            raise ValueError('missing_field')
        # Demo has no production authority and existing synthetic fixtures use
        # short hosts. All production namespaces use the Run 6A URL boundary.
        if job.source != 'demo':
            _url(job.url)
            if job.apply_url is not None:
                _url(job.apply_url)
        if job.posted_at is not None and job.posted_at.utcoffset() is None:
            raise ValueError('invalid_timestamp')
        return job
    except Exception:
        raise ValueError('invalid_source_observation; details_omitted') from None


def run(
    profile: SearchProfile,
    *,
    seen_cache: SeenCache,
    now: datetime | None = None,
    fresh_window: timedelta = FRESH_WINDOW,
    source_factory=build_source,
) -> SearchOutcome:
    """Prepare validated observations; production uses a buffered SQLite cache."""
    from job_agent.research import packet_content_flags
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None or fresh_window.total_seconds() < 0:
        raise ValueError('Invalid intake clock or freshness window')
    baseline_scan = len(seen_cache) == 0
    warnings, per_source, sources = [], {}, {}
    all_jobs, observations, intake_evidence, snapshots = [], {}, {}, {}

    for ref in profile.sources:
        label = f"{ref.ats}/{ref.board}"
        try:
            source = source_factory(ref.ats, ref.board)
            fetched = source.fetch()
            if not isinstance(fetched, (list, tuple)) or len(fetched) > 10000:
                raise ValueError('snapshot_limit')
            fetched = [validate_observed_job(j) for j in fetched]
            unique = {}
            for job in fetched:
                key = job.dedup_key()
                if key in unique and unique[key] != job:
                    raise ValueError('identity_conflict')
                unique[key] = job
            parsed = getattr(source, 'parse_result', None)
            coverage = parsed.completeness if parsed is not None else getattr(
                source, 'snapshot_completeness', 'unknown')
            if coverage not in ('complete', 'partial', 'unknown'):
                raise ValueError('invalid_completeness')
            source_evidence = {f'{e.source_namespace}:{e.source_external_id}': e
                               for e in getattr(source, 'intake_evidence', ())}
            snapshot_hash = (parsed.snapshot_sha256 if parsed is not None else
                getattr(source, 'snapshot_sha256', None) or hashlib.sha256(json.dumps(
                    [j.model_dump(mode='json') for j in fetched], sort_keys=True).encode()).hexdigest())
            markers = getattr(source, 'source_states', {})
            if any(value not in ('unknown', 'closed', 'inactive') for value in markers.values()):
                raise ValueError('invalid_source_state')
            observation_time = getattr(getattr(source, 'snapshot', None), 'observed_at', now)
            if observation_time > now:
                raise ValueError('future_observation')
            snapshot = SourceSnapshot(status=coverage, observed_at=observation_time, count=len(fetched),
                rejected_rows=len(parsed.issues) if parsed is not None else getattr(source, 'rejected_rows', 0),
                issues=parsed.issues if parsed is not None else tuple(getattr(source, 'issues', ())),
                snapshot_sha256=snapshot_hash, coverage_reason=getattr(source, 'coverage_reason',
                    'validated_offline_snapshot' if parsed is not None else 'adapter_did_not_assert_completeness'))
        except Exception as exc:
            # Never include exception bodies, source text or credential URLs.
            from job_agent.sources.simplify import SimplifyFailure, FailureCode
            from typing import get_args
            reason = exc.code if isinstance(exc, SimplifyFailure) and exc.code in get_args(FailureCode) else ('identity_conflict' if isinstance(exc, ValueError) and str(exc) == 'identity_conflict' else type(exc).__name__)
            warnings.append(f"{label}: fetch failed ({reason}; details omitted)")
            snapshots[label] = SourceSnapshot(status='unavailable', observed_at=now,
                                             count=0, failure=reason)
            per_source[label] = 0
            continue
        sources[label] = source
        snapshots[label] = snapshot
        per_source[label] = len(fetched)
        if coverage != 'complete':
            warnings.append(f'{label}: {coverage} snapshot; coverage incomplete' +
                (f' ({len(parsed.issues)} rejected rows)' if parsed is not None else ''))
        for index, job in enumerate(fetched):
            key = job.dedup_key()
            previous = observations.get(key)
            if previous and (previous.job != job or previous.source_state != markers.get(job.id, 'unknown')):
                raise ValueError('Conflicting source identity across query lanes; details omitted')
            original = getattr(source, 'original_records', {}).get(index)
            if job.source == 'freehire' and previous and original and previous.occurrences[0].original_record:
                # Query metadata can differ; full source listing claims cannot
                # be resolved by a truncated description or first-row wins.
                if json.loads(original)['fields'] != json.loads(previous.occurrences[0].original_record)['fields']:
                    raise ValueError('Conflicting source identity across query lanes; details omitted')
            evidence = source_evidence.get(key)
            if evidence and key not in intake_evidence:
                intake_evidence[key] = evidence
            elif evidence and not any(o.lane == evidence.lane for o in intake_evidence[key].occurrences):
                intake_evidence[key] = intake_evidence[key].merge_occurrences(evidence)
            occurrence = ObservationOccurrence(lane=label, locator=str(index), observed_at=observation_time,
                snapshot_sha256=snapshot_hash,
                original_record=original)
            observations[key] = DurableObservation(job=job, observed_at=max(previous.observed_at, observation_time) if previous else observation_time,
                occurrences=(*previous.occurrences, occurrence) if previous else (occurrence,),
                source_state=markers.get(job.id, 'unknown'), intake_evidence=intake_evidence.get(key),
                freshness_basis='posted_at' if job.posted_at else 'first_observed',
                content_flags=tuple(sorted(set(packet_content_flags(job)) |
                    set(packet_content_flags(job.model_copy(update={'description': occurrence.original_record or ''}))) |
                    set(previous.content_flags if previous else ()) |
                    set(evidence.content_flags if evidence else ()))))
        all_jobs.extend((job, label) for job in fetched)
    if len(all_jobs) > 10000:
        raise ValueError('Intake observation limit exceeded')

    def filter_stage(pairs, predicate, reason):
        kept = []
        for job, label in pairs:
            key = job.dedup_key()
            observation = observations[key]
            checks = tuple(dict.fromkeys((*observation.filter_checks, reason)))
            if predicate(job):
                kept.append((job, label))
                observations[key] = observation.model_copy(update={'filter_checks': checks})
            else:
                observations[key] = observation.model_copy(update={'filter_checks': checks,
                    'filter_disposition': 'rejected', 'filter_reasons': (reason,)})
        return kept

    kept = filter_stage(all_jobs, lambda j: matches_keywords(j.title, profile.keywords), 'keyword')
    first_seen, newly_seen = {}, set()
    for j, _ in kept:
        key = j.dedup_key()
        stamp, newly = seen_cache.first_seen(j.source, j.id, observations[key].observed_at)
        first_seen[key] = stamp.isoformat()
        if newly:
            newly_seen.add(key)

    after_keyword = len(kept)
    kept = filter_stage(kept, lambda j: is_fresh(j, now, seen_cache, fresh_window), 'freshness')
    after_fresh = len(kept)
    kept = filter_stage(kept, lambda j: passes_location(j, profile), 'location')
    after_location = len(kept)
    kept = filter_stage(kept, lambda j: passes_seniority(j, profile), 'seniority')
    after_seniority = len(kept)
    unique_pairs = {}
    for j, lbl in kept:
        unique_pairs.setdefault(j.dedup_key(), (j, lbl))
    deduped = list(unique_pairs.values())
    after_dedup = len(deduped)
    enriched = []
    for job, label in deduped:
        key = job.dedup_key()
        try:
            candidate = validate_observed_job(sources[label].enrich(job))
            if candidate.dedup_key() != key:
                raise ValueError('Enrichment identity changed')
            enriched.append((candidate, label))
            observations[key] = observations[key].model_copy(update={'job': candidate,
                'content_flags': tuple(sorted(set(observations[key].content_flags) | set(packet_content_flags(candidate))))})
        except Exception:
            warnings.append(f'{label}: enrich failed (details omitted)')
            enriched.append((job, label))
            observations[key] = observations[key].model_copy(update={'filter_reasons': ('enrichment_unavailable',)})
    def filter_job(job):
        # Deterministic gates use the bounded full description when retained.
        # Keep the normalized Job/scoring input cap and fingerprints unchanged.
        if job.source == 'freehire':
            for occurrence in observations[job.dedup_key()].occurrences:
                if occurrence.original_record:
                    description = json.loads(occurrence.original_record)['fields'].get('description')
                    if isinstance(description, str):
                        return job.model_copy(update={'description': description})
        return job

    enriched = filter_stage(enriched, lambda j: passes_eligibility(filter_job(j)), 'eligibility_restriction')
    after_eligibility = len(enriched)
    enriched = filter_stage(enriched, lambda j: passes_experience(filter_job(j), profile), 'experience')
    after_experience = len(enriched)
    enriched = filter_stage(enriched, lambda j: observations[j.dedup_key()].source_state == 'unknown', 'source_inactive')
    for job, _ in enriched:
        key = job.dedup_key()
        o = observations[key]
        unresolved = bool(o.content_flags or o.filter_reasons)
        observations[key] = o.model_copy(update={'filter_disposition': 'unresolved' if unresolved else 'accepted',
            'filter_reasons': o.filter_reasons or (('untrusted_content_review',) if o.content_flags else ('deterministic_filters_passed',))})
    for key, evidence in intake_evidence.items():
        o = observations[key]
        intake_evidence[key] = evidence.model_copy(update={
            'filter_disposition': 'rejected' if o.filter_disposition == 'rejected' else 'kept',
            'filter_reasons': o.filter_reasons})
        observations[key] = o.model_copy(update={'intake_evidence': intake_evidence[key]})
    seen_cache.save()
    jobs = [j for j, _ in enriched]
    return SearchOutcome(jobs=jobs, boards=[lbl.split('/', 1)[1] for _, lbl in enriched],
        counts=StageCounts(fetched=len(all_jobs), after_keyword=after_keyword, after_fresh=after_fresh,
            after_location=after_location, after_seniority=after_seniority, after_dedup=after_dedup,
            after_eligibility=after_eligibility, after_experience=after_experience),
        per_source=per_source, warnings=warnings, first_seen={j.id: first_seen[j.dedup_key()] for j in jobs},
        new_job_ids=tuple(j.id for j in jobs if j.dedup_key() in newly_seen), baseline_scan=baseline_scan,
        intake_evidence=intake_evidence, observations=observations, source_snapshots=snapshots, observed_at=now)
