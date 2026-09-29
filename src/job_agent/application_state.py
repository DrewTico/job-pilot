"""Real application persistence in the shared SQLite database.

Legacy paths are accepted as directory locators, never as writable logs.
Native identity is canonical or exact source/external ID, never fuzzy.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import select

from job_agent.apply.tracker import ApplicationRecord, APPLIED_STATUSES
from job_agent.application_import import import_applications
from job_agent.database import ApplicationEvent, CanonicalJob, JobIdentity, database_session, _utc
from job_agent.search_state import search_database


class CurrentApplication(ApplicationRecord):
    canonical_id: str | None = None
    application_status_kind: str


def _directory(path):
    path = Path(path)
    return path.parent if path.suffix in ('.json', '.sqlite3') else path


@contextmanager
def application_database(path):
    """Open shared storage; atomically import and mark the first tracking use."""
    directory = _directory(path)
    with search_database(directory) as engine:
        with database_session(engine) as session:
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            session.execute(text('CREATE TABLE IF NOT EXISTS application_cutover (id INTEGER PRIMARY KEY CHECK (id = 1))'))
            if not session.execute(text('SELECT id FROM application_cutover')).first():
                legacy = directory / 'applications.json'
                if legacy.exists():
                    import_applications(engine, applications=legacy, session=session)
                session.execute(text('INSERT INTO application_cutover VALUES (1)'))
        yield engine


def _key(event):
    return ('canonical', event.job_id) if event.job_id else (
        ('source', event.source, event.external_job_id) if event.source and event.external_job_id
        else ('unresolved', event.attempt_id or event.id))


def _events(session):
    # Legacy dates choose the initial snapshot; native writes follow committed
    # insertion order, even if a legacy date was in the future.
    events = session.exec(select(ApplicationEvent).order_by(text('rowid'))).all()
    legacy = sorted((e for e in events if e.provenance == 'legacy_applications_snapshot'),
                    key=lambda e: e.occurred_at)
    return legacy + [e for e in events if e.provenance != 'legacy_applications_snapshot']


def _current(session):
    rows = {}
    for event in _events(session):
        rows[_key(event)] = event
    return rows


def _record(event):
    return CurrentApplication(company=event.company, title=event.title,
        job_id=event.external_job_id, source=event.source,
        date=event.occurred_at.replace(tzinfo=timezone.utc).isoformat(),
        status=event.status, reason=event.reason, attempt_id=event.attempt_id or event.id,
        notes=event.notes, follow_up=event.follow_up, canonical_id=event.job_id,
        application_status_kind=event.status_kind)


def _resolve(session, canonical_id, source, external_id):
    if canonical_id:
        if session.get(CanonicalJob, canonical_id) is None:
            raise KeyError(f'Unknown canonical job {canonical_id}')
        if source and external_id:
            identity = session.exec(select(JobIdentity).where(
                JobIdentity.source == source, JobIdentity.external_id == external_id)).one_or_none()
            if identity is not None and identity.job_id != canonical_id:
                raise ValueError('Source/external identity belongs to a different canonical job')
        return canonical_id
    if source and external_id:
        identity = session.exec(select(JobIdentity).where(
            JobIdentity.source == source, JobIdentity.external_id == external_id)).one_or_none()
        return identity.job_id if identity else None
    return None


def _append(session, record, canonical_id, provenance, now=None):
    kind = 'attempt' if record.status in ('submitted', 'paused', 'failed') else 'pipeline'
    event = ApplicationEvent(job_id=canonical_id, external_job_id=record.job_id,
        source=record.source, company=record.company, title=record.title,
        attempt_id=record.attempt_id, status=record.status, status_kind=kind,
        reason=record.reason, notes=record.notes, follow_up=record.follow_up,
        occurred_at=_utc(now), provenance=provenance,
        payload={**record.model_dump(), 'canonical_id': canonical_id,
                 'application_status_kind': kind},
        unresolved=None if canonical_id else 'No canonical relationship')
    session.add(event)
    if canonical_id:
        job = session.get(CanonicalJob, canonical_id)
        job.application_status, job.application_status_kind = record.status, kind
        job.application_notes, job.application_follow_up = record.notes, record.follow_up
        job.application_updated_at = event.occurred_at
        session.add(job)
    session.flush()
    return _record(event)


def load_applications(path):
    """Project current rows from immutable evidence, retaining unresolved rows."""
    with application_database(path) as engine, database_session(engine) as session:
        return [_record(e) for e in _current(session).values()]


def record_attempt(path, record, *, canonical_id=None):
    """Append an attempt, preserving the existing job's user-managed fields."""
    if record.status not in ('submitted', 'paused', 'failed'):
        raise ValueError('Expected an attempt outcome')
    with application_database(path) as engine, database_session(engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        canonical_id = _resolve(session, canonical_id, record.source, record.job_id)
        attempt = record.attempt_id or uuid4().hex
        candidate = record.model_copy(update={'attempt_id': attempt})
        key = ('canonical', canonical_id) if canonical_id else ('source', record.source, record.job_id)
        old = _current(session).get(key)
        if old:
            candidate = candidate.model_copy(update={'notes': old.notes, 'follow_up': old.follow_up})
        _append(session, candidate, canonical_id, 'native_attempt_started')
        return attempt


def update_status(path, attempt_id, status, reason=''):
    """Append outcome evidence for an attempt without changing earlier events."""
    if status not in ('submitted', 'paused', 'failed'):
        raise ValueError('Expected an attempt outcome')
    with application_database(path) as engine, database_session(engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        matches = [e for e in _events(session) if e.attempt_id == attempt_id]
        if not matches:
            raise KeyError(attempt_id)
        old = matches[-1]
        current = _current(session)[_key(old)]
        record = _record(old).model_copy(update=dict(status=status, reason=reason or old.reason,
            notes=current.notes, follow_up=current.follow_up))
        _append(session, record, old.job_id, 'native_attempt_outcome')


def upsert_job_state(path, *, job_id='', attempt_id='', company='', title='', source='',
                     status=None, notes=None, follow_up=None, now=None, canonical_id=None):
    """Append a pipeline edit. None preserves a field; an empty string clears it."""
    if status is not None and status not in ('saved', 'applied', 'interviewing', 'offer', 'rejected'):
        raise ValueError('Expected a pipeline state')
    with application_database(path) as engine, database_session(engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        canonical_id = _resolve(session, canonical_id, source, job_id)
        rows = _current(session)
        old = rows.get(('canonical', canonical_id) if canonical_id else ('source', source, job_id))
        if old is None and attempt_id:
            evidence = next((e for e in reversed(_events(session))
                             if (e.attempt_id or e.id) == attempt_id), None)
            old = rows.get(_key(evidence)) if evidence else None
            if old is None:
                raise KeyError(attempt_id)
        if old:
            record = _record(old)
            canonical_id = old.job_id
        else:
            if not job_id or not source:
                raise ValueError('A canonical job or source-scoped job ID is required')
            record = ApplicationRecord(company=company or 'Unknown', title=title, job_id=job_id,
                source=source, status='saved', date=datetime.now(timezone.utc).isoformat(),
                attempt_id=uuid4().hex)
        updates = {k: v for k, v in dict(status=status, notes=notes, follow_up=follow_up).items() if v is not None}
        return _append(session, record.model_copy(update=updates), canonical_id, 'native_pipeline_edit', now)


def applied_markers(path):
    """Return canonical and source-scoped markers, including verified aliases."""
    records = [r for r in load_applications(path) if r.status in APPLIED_STATUSES]
    canonical_ids = {r.canonical_id for r in records if r.canonical_id}
    with application_database(path) as engine, database_session(engine) as session:
        aliases = {(i.source, i.external_id) for i in session.exec(select(JobIdentity))
                   if i.job_id in canonical_ids}
    return {'canonical_ids': canonical_ids,
            'source_ids': aliases | {(r.source, r.job_id) for r in records if r.source and r.job_id}}


def is_already_applied(markers, *, job_id='', source='', canonical_id=None, company='', title=''):
    if 'source_ids' not in markers:  # compatibility for explicit legacy/demo markers
        from job_agent.apply.tracker import is_already_applied as legacy
        return legacy(markers, job_id=job_id, company=company, title=title)
    if canonical_id:
        return canonical_id in markers['canonical_ids']
    return (source, str(job_id)) in markers['source_ids']
