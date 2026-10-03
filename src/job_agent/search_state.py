"""Production SQLite search state. JSON is read only at the initial cutover."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import warnings

from sqlalchemy import text, func
from sqlmodel import select

from job_agent.database import (
    JobIdentity, JobRepository, SearchRun, SearchResult, _utc,
    database_session, initialize_database,
)
from job_agent.search_import import import_search_state


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
    def __init__(self, session):
        self.session = session
        self.repo = JobRepository(session)
        self.inserted = set()

    def __len__(self):
        return self.session.exec(select(func.count()).select_from(JobIdentity)).one()

    def first_seen(self, source, external_id, now):
        identity = self.repo.get_identity(source, external_id)
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

    def record_search(self, scored, boards, *, cache, baseline, sources_queried=None):
        if len(scored) != len(boards):
            raise ValueError('Each search result requires a board token')
        now = datetime.now(timezone.utc)
        run_id = str(uuid4())
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
            if job.source not in ('sr-search', 'remotive', 'remoteok', 'freehire') and any(
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
            record.update(canonical_id=identity.job_id, board=board, token=board,
                          first_seen=identity.first_seen.replace(tzinfo=timezone.utc).isoformat(),
                          first_seen_this_scan=not baseline and (job.source, job.id) in cache.inserted)
            key = f'{job.source}:{job.id}'
            records[key] = record
            results.append(SearchResult(run_id=run_id, legacy_key=key,
                                        identity_id=identity.id, payload=record))
        meta = dict(total=len(records), new_count=None if baseline else sum(
            r['first_seen_this_scan'] for r in records.values()))
        if sources_queried is not None:
            meta['sources_queried'] = sources_queried
        payload = dict(generated_at=now.isoformat(), meta=meta, jobs=records)
        self.session.add(SearchRun(id=run_id, generated_at=now.isoformat(),
                                   total=meta['total'], new_count=meta['new_count'],
                                   sources_queried=sources_queried, payload=payload))
        self.session.flush()
        self.session.add_all(results)
        self.session.flush()
        return run_id

    def latest(self):
        # Only committed complete runs are visible to other connections. Insertion
        # order also handles legacy snapshots with missing or future timestamps.
        run = self.session.exec(select(SearchRun).order_by(text('rowid DESC')).limit(1)).first()
        if run is None:
            return dict(generated_at=None, meta=None, jobs={})
        records = {}
        for result in self.session.exec(select(SearchResult).where(SearchResult.run_id == run.id)):
            record = dict(result.payload)
            identity = self.session.get(JobIdentity, result.identity_id) if result.identity_id else None
            if identity:
                record['canonical_id'] = identity.job_id
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
