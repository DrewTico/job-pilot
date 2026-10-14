"""Production SQLite search state. JSON is read only at the initial cutover."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import warnings

from sqlalchemy import text, func
from sqlmodel import select, Session
import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta

from job_agent.database import (
    JobIdentity, JobRepository, SearchRun, SearchResult, _utc,
    database_session, initialize_database,
)
from job_agent.search_import import import_search_state
from job_agent.models import IntakeEvidence, Job


def database_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / 'job_pilot.sqlite3'


@contextmanager
def search_database(data_dir):
    path = database_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = initialize_database(path)
    try:
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE IF NOT EXISTS search_cutover (id INTEGER PRIMARY KEY CHECK (id = 1))'))
            imported = conn.execute(text('SELECT id FROM search_cutover')).first()
        if not imported:
            directory = Path(data_dir)
            report = import_search_state(
                engine,
                last_search=(directory / 'last_search.json') if (directory / 'last_search.json').exists() else None,
                seen=(directory / 'seen.json') if (directory / 'seen.json').exists() else None,
            )
            for issue in report.unresolved:
                warnings.warn(f'Legacy search import: {issue}', stacklevel=2)
            # A crash before this marker only replays the idempotent import.
            with engine.begin() as conn:
                conn.execute(text('INSERT OR IGNORE INTO search_cutover (id) VALUES (1)'))
        yield engine
    finally:
        engine.dispose()


class SQLiteSeenCache:
    """Session-owned observations, committed with the completed search run."""
    def __init__(self, session, *, defer_writes=False):
        self.session = session
        self.repo = JobRepository(session)
        self.inserted = set()
        self.defer_writes = defer_writes
        self.observations = {}

    def __len__(self):
        persisted = self.session.exec(select(func.count()).select_from(JobIdentity)).one()
        return persisted + (len(self.inserted) if self.defer_writes else 0)

    def first_seen(self, source, external_id, now):
        identity = self.repo.get_identity(source, external_id)
        if self.defer_writes:
            key = (source, external_id)
            newly = identity is None and key not in self.observations
            first = (identity.first_seen.replace(tzinfo=timezone.utc) if identity else now)
            first = self.observations.get(key, (first, now))[0]
            self.observations[key] = (min(first, now), now)
            if newly:
                self.inserted.add(key)
            return self.observations[key][0], newly
        newly = identity is None
        if newly:
            observed = _utc(now)
            identity = JobIdentity(source=source, external_id=external_id,
                                   first_seen=observed, last_seen=observed)
            self.session.add(identity)
            self.session.flush()
            self.inserted.add((source, external_id))
        else:
            identity = self.repo.observe_identity(source, external_id, seen_at=now)
        return identity.first_seen.replace(tzinfo=timezone.utc), newly

    def observe(self, source, external_id, now):
        return self.first_seen(source, external_id, now)[0]

    def save(self):
        pass  # The caller commits or rolls back the entire search transaction.


class SearchRepository:
    def __init__(self, session):
        self.session = session
        self.jobs = JobRepository(session)

    def record_search(self, scored, boards, *, cache, baseline, sources_queried=None, deferred_profile=None, scoring_model=None, intake_evidence=None, run_id=None, observed_at=None, admission=None, intake_payload=None, scoring_plans=None):
        if len(scored) != len(boards):
            raise ValueError('Each search result requires a board token')
        evidence_payload = {}
        for key, value in (intake_evidence or {}).items():
            evidence = IntakeEvidence.model_validate(value)
            if key != f'{evidence.source_namespace}:{evidence.source_external_id}':
                raise ValueError('Intake evidence identity mismatch')
            evidence_payload[key] = evidence.model_dump(mode='json')
        for item in scored:
            job = item.job
            key = f'{job.source}:{job.id}'
            if job.source in ('simplify-newgrad', 'simplify-internships') and key not in evidence_payload:
                raise ValueError('Simplify result requires intake evidence')
            if key in evidence_payload:
                normalized = evidence_payload[key]['normalized_fields']
                if Job.model_validate({**normalized, 'location': normalized['location'] or 'Unknown'}) != job:
                    raise ValueError('Intake evidence normalized fields mismatch')
        now = observed_at or datetime.now(timezone.utc)
        run_id = run_id or str(uuid4())
        records = {}
        results = []
        for item, board in zip(scored, boards):
            job = item.job
            identity = self.jobs.get_identity(job.source, job.id)
            if identity is None:
                cache.first_seen(job.source, job.id, now)
                identity = self.jobs.get_identity(job.source, job.id)
            previous = self.session.exec(select(SearchResult).where(
                SearchResult.identity_id == identity.id)).all()
            if job.source not in ('sr-search', 'remotive', 'remoteok', 'freehire', 'simplify-newgrad', 'simplify-internships') and any(
                r.payload.get('board') not in (None, '', board) for r in previous
            ):
                raise ValueError(f'Conflicting board for source identity {job.source}:{job.id}')
            if identity.job_id is None:
                canonical = self.jobs.create_job(
                    company=job.company, title=job.title, location=job.location,
                    posting_url=job.url, apply_url=job.apply_url,
                    seen_at=identity.first_seen.replace(tzinfo=timezone.utc))
                self.jobs.add_identity(canonical.id, source=job.source, external_id=job.id,
                                       posting_url=job.url, apply_url=job.apply_url,
                                       seen_at=identity.last_seen.replace(tzinfo=timezone.utc))
            record = job.model_dump(mode='json')
            record.update(item.model_dump(mode='json', exclude={'job'}))
            if deferred_profile is not None:
                from job_agent.batch import scoring_fingerprint
                record["scoring_fingerprint"] = (scoring_plans[job.dedup_key()]["fingerprint"] if scoring_plans is not None
                    else scoring_fingerprint(job, deferred_profile, scoring_model))
            record.update(canonical_id=identity.job_id, board=board, token=board,
                          first_seen=identity.first_seen.replace(tzinfo=timezone.utc).isoformat(),
                          first_seen_this_scan=not baseline and (job.source, job.id) in cache.inserted)
            key = f'{job.source}:{job.id}'
            if key in evidence_payload:
                record['intake_evidence'] = evidence_payload[key]
            if admission is not None:
                record['intake_disposition'] = admission[key]['filter_disposition']
                record['intake_reasons'] = admission[key]['filter_reasons']
                record['identity_review_required'] = admission[key]['identity_review_required']
            records[key] = record
            results.append(SearchResult(run_id=run_id, legacy_key=key,
                                        identity_id=identity.id, payload=record))
        meta = dict(total=len(records), new_count=None if baseline else sum(
            r['first_seen_this_scan'] for r in records.values()))
        if sources_queried is not None:
            meta['sources_queried'] = sources_queried
        payload = dict(generated_at=now.isoformat(), meta=meta, jobs=records)
        if evidence_payload:
            payload['intake_evidence'] = evidence_payload
        if intake_payload:
            payload.update(intake_payload)
        self.session.add(SearchRun(id=run_id, generated_at=now.isoformat(),
                                   total=meta['total'], new_count=meta['new_count'],
                                   sources_queried=sources_queried, payload=payload))
        self.session.flush()
        self.session.add_all(results)
        self.session.flush()
        if deferred_profile is not None:
            from job_agent.batch import enqueue
            for result, item in zip(results, scored):
                if (result.payload.get('intake_disposition', 'accepted') != 'accepted'
                        or not intake_admission_allowed(self.session, item.job)):
                    result.payload = {**result.payload, 'scoring_status': 'intake_review_required'}
                    self.session.add(result)
                    continue
                if item.score is None and item.verdict == "unscored" and item.reasons == ("Scoring pending",):
                    enqueue(self.session, result, item.job, deferred_profile, scoring_model,
                            plan=scoring_plans[item.job.dedup_key()] if scoring_plans is not None else None)
                else:
                    from job_agent.database import ScoringWorkItem
                    work = self.session.exec(select(ScoringWorkItem).where(
                        ScoringWorkItem.fingerprint == result.payload["scoring_fingerprint"])).first()
                    if work:
                        if work.search_result_id is None:
                            work.search_result_id = result.id
                            work.canonical_job_id = result.payload["canonical_id"]
                            self.session.add(work)
                        result.payload = {**result.payload, **(work.result if work.state == "succeeded" else {}),
                                          "scoring_work_id": work.id, "scoring_status": work.state}
                        self.session.add(result)
        return run_id

    def latest(self):
        # Only committed complete runs are visible to other connections. Insertion
        # order also handles legacy snapshots with missing or future timestamps.
        run = self.session.exec(select(SearchRun).where(
            (SearchRun.payload['published'].as_boolean().is_(None)) |
            (SearchRun.payload['published'].as_boolean() == True)
        ).order_by(text('rowid DESC')).limit(1)).first()
        if run is None:
            return dict(generated_at=None, meta=None, jobs={})
        records = {}
        for result in self.session.exec(select(SearchResult).where(SearchResult.run_id == run.id)):
            record = dict(result.payload)
            identity = self.session.get(JobIdentity, result.identity_id) if result.identity_id else None
            if identity:
                record['canonical_id'] = identity.job_id
            if record.get('scoring_work_id'):
                from job_agent.database import ScoringWorkItem
                work = self.session.get(ScoringWorkItem, record['scoring_work_id'])
                if work and record.get('scoring_fingerprint') == work.fingerprint:
                    record['scoring_status'] = work.state
            records[result.legacy_key] = record
        return {**run.payload, 'jobs': records}


class AmbiguousJobError(ValueError):
    pass


def latest_search(data_dir):
    with search_database(data_dir) as engine, database_session(engine) as session:
        return SearchRepository(session).latest()


def load_job_record(data_dir, job_id):
    records = list(latest_search(data_dir)['jobs'].values())
    canonical = job_id.removeprefix('canonical:')
    matches = [r for r in records if r.get('canonical_id') == canonical]
    if not matches:
        matches = [r for r in records if f"{r.get('source')}:{r.get('id')}" == job_id]
    if not matches:
        matches = [r for r in records if str(r.get('id')) == job_id]
    if len(matches) > 1:
        choices = ', '.join(f"{r.get('source')}:{r.get('id')}" for r in matches)
        raise AmbiguousJobError(f'Ambiguous job ID {job_id!r}; use a source-qualified ID ({choices}) or canonical:<id>')
    return matches[0] if matches else None


MAX_INTAKE_BYTES = 16 * 1024 * 1024
MAX_INTAKE_IDENTITIES = 10000
STALE_AFTER = timedelta(days=30)


@dataclass(frozen=True)
class PreparedIntake:
    """Immutable bounded serialization produced before the writer transaction."""
    body: str
    run_id: str


def prepare_intake(outcome, scored, *, deferred_profile=None, scoring_model=None):
    from job_agent.search import SearchOutcome, validate_observed_job
    from job_agent.models import ScoredJob
    try:
        outcome = SearchOutcome.model_validate(outcome.model_dump() if isinstance(outcome, SearchOutcome) else outcome)
        if not outcome.source_snapshots or outcome.observed_at is None or outcome.observed_at.utcoffset() is None:
            raise ValueError('Missing observation clock')
        if len(outcome.observations) > MAX_INTAKE_IDENTITIES:
            raise ValueError('Observation limit')
        assessments = [ScoredJob.model_validate(s) for s in scored]
        if [s.job for s in assessments] != outcome.jobs or len(outcome.boards) != len(outcome.jobs):
            raise ValueError('Candidate write set mismatch')
        if len({j.dedup_key() for j in outcome.jobs}) != len(outcome.jobs):
            raise ValueError('Duplicate result identity')
        for key, observation in outcome.observations.items():
            job = validate_observed_job(observation.job)
            if key != job.dedup_key() or observation.observed_at > outcome.observed_at:
                raise ValueError('Observation identity or time mismatch')
            if not observation.filter_checks or not observation.filter_reasons:
                raise ValueError('Missing filter decision')
            if observation.source_state != 'unknown' and observation.filter_disposition != 'rejected':
                raise ValueError('Inactive observation cannot be admitted')
            for occurrence in observation.occurrences:
                snapshot = outcome.source_snapshots.get(occurrence.lane)
                if (snapshot is None or snapshot.status == 'unavailable' or occurrence.observed_at > observation.observed_at or
                        snapshot.observed_at != occurrence.observed_at or snapshot.snapshot_sha256 != occurrence.snapshot_sha256):
                    raise ValueError('Observation coverage mismatch')
            evidence = observation.intake_evidence
            if evidence:
                fields = evidence.normalized_fields
                if Job.model_validate({**fields, 'location': fields['location'] or 'Unknown'}) != job:
                    raise ValueError('Evidence normalized job mismatch')
                if evidence != outcome.intake_evidence.get(key):
                    raise ValueError('Evidence map mismatch')
            elif job.source in ('simplify-newgrad', 'simplify-internships'):
                raise ValueError('Simplify observation requires evidence')
        for job in outcome.jobs:
            observation = outcome.observations.get(job.dedup_key())
            if observation is None or observation.job != job or observation.filter_disposition == 'rejected':
                raise ValueError('Rejected or missing observation')
        durable_outcome = outcome.model_dump(mode='json')
        # Cache-derived hints are not replay identity or canonical authority.
        durable_outcome.update(first_seen={}, new_job_ids=[], baseline_scan=False)
        scoring_plans = {}
        scoring_context = None
        if deferred_profile is not None:
            from job_agent.batch import scoring_fingerprint
            from job_agent.scoring import build_score_request
            from job_agent.llm import reservation_cost
            scoring_context = hashlib.sha256(json.dumps(
                {'profile': deferred_profile.model_dump(mode='json'), 'model': scoring_model},
                sort_keys=True).encode()).hexdigest()
            for assessment in assessments:
                job = assessment.job
                plan = {'fingerprint': scoring_fingerprint(job, deferred_profile, scoring_model)}
                if assessment.reasons == ('Scoring pending',) and assessment.score is None:
                    plan['reservation_cost_usd'] = str(reservation_cost(
                        build_score_request(scoring_model, job, deferred_profile), 'batch'))
                scoring_plans[job.dedup_key()] = plan
        body = json.dumps({'outcome': durable_outcome,
                           'scored': [s.model_dump(mode='json') for s in assessments],
                           'scoring_context': scoring_context, 'scoring_plans': scoring_plans},
                          sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        if len(body.encode()) > MAX_INTAKE_BYTES:
            raise ValueError('Intake payload limit')
    except Exception:
        raise ValueError('Invalid prepared intake; details omitted') from None
    return PreparedIntake(body=body, run_id='intake-v1:' + hashlib.sha256(body.encode()).hexdigest())


def latest_observation(session, key):
    run = session.exec(select(SearchRun).where(
        SearchRun.payload['observations'][key].is_not(None),
        SearchRun.payload['observations'][key]['job']['id'].as_string().is_not(None)
    ).order_by(text('rowid DESC')).limit(1)).first()
    return run.payload['observations'][key] if run else None


def _same_source_claims(previous, current):
    if (previous['job'] != current['job'] or previous['source_state'] != current['source_state']
            or previous.get('content_flags') != current.get('content_flags')):
        return False
    if current['job']['source'] == 'freehire':
        def original_fields(record):
            return [json.loads(o['original_record'])['fields'] for o in record['occurrences']
                    if o.get('original_record')]
        old, new = original_fields(previous), original_fields(current)
        # Lane/duplicate-count changes are occurrence evidence, not job changes.
        if bool(old) != bool(new) or old and old[0] != new[0]:
            return False
    old_evidence, new_evidence = previous.get('intake_evidence'), current.get('intake_evidence')
    if old_evidence and new_evidence:
        if any(old_evidence.get(field) != new_evidence.get(field) for field in
               ('relative_age', 'employment_type', 'locations', 'labels', 'source_classifications')):
            return False
        if ({o.get('category') for o in old_evidence['occurrences']} !=
                {o.get('category') for o in new_evidence['occurrences']}):
            return False
    return True


def _complete_absence_after(session, key, observed_at):
    run = session.exec(select(SearchRun).where(
        SearchRun.payload['lifecycle'][key]['availability'].as_string() == 'not_observed_complete'
    ).order_by(text('rowid DESC')).limit(1)).first()
    if run is None:
        return False
    stamp = run.payload['lifecycle'][key].get('coverage_observed_at') or run.generated_at
    return stamp is not None and _utc(datetime.fromisoformat(stamp)) >= _utc(observed_at)


def intake_admission_allowed(session, job, *, now=None, _allow_rejected_recovery=False):
    """Latest deterministic evidence and immutable Reject decisions own admission."""
    from job_agent.database import ApplicationPacket, PacketDecision
    key = job.dedup_key()
    observed = latest_observation(session, key)
    if observed:
        if observed['filter_disposition'] != 'accepted' or observed.get('identity_review_required'):
            return False
        if Job.model_validate(observed['job']) != job:
            return False
        clock_value = now() if callable(now) else now
        if clock_value and _utc(clock_value) - _utc(datetime.fromisoformat(observed['observed_at'])) > STALE_AFTER:
            return False
        # Outages and historical snapshots cannot undo a newer complete
        # absence. A genuinely newer valid observation restores consideration.
        if _complete_absence_after(session, key, datetime.fromisoformat(observed['observed_at'])):
            return False
    identity = JobRepository(session).get_identity(job.source, job.id)
    if identity and identity.job_id:
        from job_agent.database import CanonicalJob
        canonical = session.get(CanonicalJob, identity.job_id)
        if (canonical.company != job.company or identity.posting_url not in (None, job.url)
                or identity.apply_url not in (None, job.apply_url)):
            return False
    if _allow_rejected_recovery:
        return True  # Only the packet builder's verified artifact-repair path.
    packets = select(ApplicationPacket.id).where(
        (ApplicationPacket.job_key == key) |
        (ApplicationPacket.canonical_job_id == identity.job_id if identity and identity.job_id else False))
    rejection = session.exec(select(PacketDecision).where(
        PacketDecision.packet_id.in_(packets), PacketDecision.decision == 'reject')).first()
    return rejection is None


def persist_intake(engine, outcome, scored, *, deferred_profile=None, scoring_model=None, fault=None):
    """Prepare first, then serialize one atomic schema-v9 write set. No IO provider."""
    return commit_intake(engine, prepare_intake(outcome, scored, deferred_profile=deferred_profile,
                         scoring_model=scoring_model), deferred_profile=deferred_profile,
                         scoring_model=scoring_model, fault=fault)


def _commit_intake(engine, prepared, *, deferred_profile=None, scoring_model=None, fault=None):
    from job_agent.search import SearchOutcome
    from job_agent.models import ScoredJob
    from job_agent.database import CanonicalJob
    try:
        if len(prepared.body.encode()) > MAX_INTAKE_BYTES:
            raise ValueError('Prepared body limit')
        data = json.loads(prepared.body)
        # Revalidation before BEGIN protects directly constructed write sets.
        outcome = SearchOutcome.model_validate(data['outcome'])
        scored = [ScoredJob.model_validate(s) for s in data['scored']]
        if prepare_intake(outcome, scored, deferred_profile=deferred_profile, scoring_model=scoring_model) != prepared:
            raise ValueError('Prepared fingerprint mismatch')
    except Exception:
        raise ValueError('Invalid prepared intake; details omitted') from None
    now = outcome.observed_at
    with Session(engine, expire_on_commit=False) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        try:
            if session.get(SearchRun, prepared.run_id):
                session.rollback()
                return prepared.run_id
            repo = JobRepository(session)
            cache = SQLiteSeenCache(session)
            baseline = session.exec(select(JobIdentity.id).limit(1)).first() is None
            observations, lifecycle = {}, {}
            temporal_incomplete = False
            for key, observation in outcome.observations.items():
                job = observation.job
                previous = latest_observation(session, key)
                identity = repo.get_identity(job.source, job.id)
                existed = identity is not None
                stamp = _utc(observation.observed_at)
                if identity and stamp < identity.last_seen:
                    raise ValueError('Out-of-order observation requires review')
                if identity is None:
                    identity = JobIdentity(source=job.source, external_id=job.id,
                                           first_seen=min(_utc(o.observed_at) for o in observation.occurrences), last_seen=stamp)
                    session.add(identity)
                    session.flush()
                    cache.inserted.add((job.source, job.id))
                else:
                    identity.last_seen = max(identity.last_seen, stamp)
                if identity.job_id is None:
                    canonical = repo.create_job(company=job.company, title=job.title, location=job.location,
                        posting_url=job.url, apply_url=job.apply_url,
                        seen_at=identity.first_seen.replace(tzinfo=timezone.utc))
                    repo.add_identity(canonical.id, source=job.source, external_id=job.id,
                        posting_url=job.url, apply_url=job.apply_url, seen_at=observation.observed_at)
                else:
                    canonical = session.get(CanonicalJob, identity.job_id)
                    canonical.last_seen = max(canonical.last_seen, stamp)
                    session.add(canonical)
                session.add(identity)
                # Strong ownership is retained, but changed identity-bearing
                # assertions cannot inherit downstream authority automatically.
                review = bool(canonical.company != job.company or
                    identity.posting_url not in (None, job.url) or
                    identity.apply_url not in (None, job.apply_url) or
                    previous and (previous['job']['company'] != job.company or
                    previous['job']['url'] != job.url or previous['job'].get('apply_url') != job.apply_url))
                if job.source in ('simplify-newgrad', 'simplify-internships'):
                    # A derived URL identity is not an immutable requisition ID.
                    # Title/location/term changes cannot prove historical reuse.
                    review = review or canonical.title != job.title or canonical.location != job.location
                    if previous and observation.intake_evidence:
                        old_evidence = previous.get('intake_evidence') or {}
                        new_evidence = observation.intake_evidence.model_dump(mode='json')
                        review = review or any(old_evidence.get(field) != new_evidence.get(field)
                            for field in ('employment_type', 'locations', 'labels', 'source_classifications'))
                        old_categories = {o.get('category') for o in old_evidence.get('occurrences', [])}
                        new_categories = {o.get('category') for o in new_evidence.get('occurrences', [])}
                        review = review or old_categories != new_categories
                record = observation.model_dump(mode='json')
                record.update(canonical_id=identity.job_id,
                    first_seen=identity.first_seen.replace(tzinfo=timezone.utc).isoformat(),
                    last_seen=identity.last_seen.replace(tzinfo=timezone.utc).isoformat(),
                    lifecycle='newly_discovered' if not existed else
                        'previously_seen' if previous is None else
                        'previously_seen' if _same_source_claims(previous, record) else 'changed',
                    identity_review_required=review or bool(previous and previous.get('identity_review_required')))
                if record['identity_review_required']:
                    record['filter_disposition'] = 'unresolved'
                    record['filter_reasons'] = list(dict.fromkeys((*record['filter_reasons'], 'identity_changed_requires_review')))
                if (record['filter_disposition'] == 'accepted' and
                        _complete_absence_after(session, key, observation.observed_at)):
                    record['filter_disposition'] = 'unresolved'
                    record['filter_reasons'] = ['historical_observation_after_absence_requires_review']
                observations[key] = record
                lifecycle[key] = dict(availability='observed',
                    freshness='stale' if _utc(now) - stamp > STALE_AFTER else 'current',
                    source_state=observation.source_state, last_seen=record['last_seen'])
            identities = session.exec(select(JobIdentity).limit(MAX_INTAKE_IDENTITIES + 1)).all()
            if len(identities) > MAX_INTAKE_IDENTITIES:
                raise ValueError('Lifecycle write set limit exceeded')
            for identity in identities:
                key = f'{identity.source}:{identity.external_id}'
                if key in observations:
                    continue
                previous = latest_observation(session, key)
                lanes = {o['lane'] for o in previous['occurrences']} if previous else set()
                statuses = [outcome.source_snapshots[lane].status for lane in lanes if lane in outcome.source_snapshots]
                complete = lanes and len(statuses) == len(lanes) and all(s == 'complete' for s in statuses)
                coverage_times = [outcome.source_snapshots[lane].observed_at for lane in lanes
                                  if lane in outcome.source_snapshots]
                coverage_stamp = max(coverage_times).isoformat() if coverage_times else None
                if complete and all(_utc(t) > identity.last_seen for t in coverage_times):
                    availability = 'not_observed_complete'
                elif complete:
                    # A historical complete document cannot contradict a
                    # newer valid observation or publish a fresh empty view.
                    temporal_incomplete = True
                    availability = 'incomplete_unknown'
                elif statuses and all(s == 'unavailable' for s in statuses):
                    availability = 'source_unavailable'
                else:
                    availability = 'incomplete_unknown'
                lifecycle[key] = dict(availability=availability, coverage_observed_at=coverage_stamp,
                    freshness='stale' if _utc(now) - identity.last_seen > STALE_AFTER else 'unknown',
                    source_state=previous['source_state'] if previous else 'unknown',
                    last_seen=identity.last_seen.replace(tzinfo=timezone.utc).isoformat())
            if fault:
                fault('after_identities')
            run_id = SearchRepository(session).record_search(scored, outcome.boards, cache=cache,
                baseline=baseline, sources_queried=len(outcome.source_snapshots),
                deferred_profile=deferred_profile, scoring_model=scoring_model,
                intake_evidence=outcome.intake_evidence, run_id=prepared.run_id, observed_at=now, admission=observations,
                intake_payload={'observations': observations, 'lifecycle': lifecycle},
                scoring_plans=data['scoring_plans'] if deferred_profile is not None else None)
            run = session.get(SearchRun, run_id)
            run.payload = {**run.payload, 'intake_version': 'durable-intake-v1',
                'published': outcome.publishable and (bool(outcome.jobs) or not temporal_incomplete), 'observations': observations, 'lifecycle': lifecycle,
                'source_snapshots': {k: v.model_dump(mode='json') for k, v in outcome.source_snapshots.items()},
                'completeness': 'complete' if not temporal_incomplete and all(s.status == 'complete' for s in outcome.source_snapshots.values()) else 'partial',
                'warnings': outcome.warnings + (['stale snapshot coverage; earlier observations retained'] if temporal_incomplete else []), 'stale_policy': {'basis': 'last_valid_observation', 'days': 30}}
            for result in session.exec(select(SearchResult).where(SearchResult.run_id == run_id)):
                decision = observations[result.legacy_key]
                result.payload = {**result.payload, 'intake_disposition': decision['filter_disposition'],
                    'intake_reasons': decision['filter_reasons'], 'observation_run_id': run_id,
                    'identity_review_required': decision['identity_review_required']}
                session.add(result)
            run.payload = {**run.payload, 'jobs': {r.legacy_key: r.payload for r in
                session.exec(select(SearchResult).where(SearchResult.run_id == run_id))}}
            session.add(run)
            session.flush()
            if len(json.dumps(run.payload, ensure_ascii=False).encode()) > MAX_INTAKE_BYTES:
                raise ValueError('Durable intake payload limit exceeded')
            if fault:
                fault('after_results')
            session.commit()
            return run_id
        except BaseException as exc:
            session.rollback()
            from sqlalchemy.exc import SQLAlchemyError
            if isinstance(exc, SQLAlchemyError):
                raise ValueError('Intake persistence failed; details omitted') from None
            raise


def commit_intake(engine, prepared, *, deferred_profile=None, scoring_model=None, fault=None):
    # Reuse the existing context-local SQL/SDK diagnostic privacy boundary.
    from job_agent.packets import private_packet_logs
    with private_packet_logs():
        return _commit_intake(engine, prepared, deferred_profile=deferred_profile,
                              scoring_model=scoring_model, fault=fault)
