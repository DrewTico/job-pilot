"""Idempotent legacy import, also used at the first production SQLite cutover.

All supplied files are read and validated before opening the single write
transaction. No file is rewritten. Snapshots retain absent versus null fields.
Unresolvable records are retained in search_results and returned to the caller.
"""

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import get_args

from sqlalchemy import Engine
from sqlmodel import select

from job_agent.database import (
    CanonicalJob, JobIdentity, JobRepository, SearchResult, SearchRun,
    _utc, database_session,
)

from job_agent.models import SourceName, Verdict

LEGACY_SOURCES = set(get_args(SourceName)) - {"demo"}


@dataclass
class ImportReport:
    unresolved: list[str] = field(default_factory=list)


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Expected an ISO timestamp string')
    return _utc(datetime.fromisoformat(value))


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _read(path):
    def invalid(value):
        raise ValueError(f'Invalid JSON constant: {value}')
    value = json.loads(Path(path).read_bytes(), object_pairs_hook=_object,
                       parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value


def _validate_search(data):
    if 'generated_at' in data and data['generated_at'] is not None:
        _timestamp(data['generated_at'])
    meta = data.get('meta', {})
    if not isinstance(meta, dict) or not isinstance(data.get('jobs'), dict):
        raise ValueError('Expected meta and jobs objects')
    for key in ('total', 'new_count', 'sources_queried'):
        value = meta.get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f'Invalid {key}')
    for record in data['jobs'].values():
        if not isinstance(record, dict):
            raise ValueError('Expected job object')
        for key in ('id', 'source', 'company', 'title', 'location', 'url',
                    'apply_url', 'board', 'token', 'country', 'description', 'verdict'):
            if key in record and record[key] is not None and not isinstance(record[key], str):
                raise ValueError(f'Invalid {key}')
        for key in ('first_seen', 'posted_at'):
            if record.get(key) is not None:
                _timestamp(record[key])
        for key in ('remote', 'first_seen_this_scan'):
            if record.get(key) is not None and type(record[key]) is not bool:
                raise ValueError(f'Invalid {key}')
        if record.get('verdict') is not None and record['verdict'] not in get_args(Verdict):
            raise ValueError('Invalid verdict')
        score = record.get('score')
        if score is not None and (type(score) is not int or not 0 <= score <= 100):
            raise ValueError('Invalid score')
        if 'reasons' in record and (not isinstance(record['reasons'], list)
                                   or not all(isinstance(x, str) for x in record['reasons'])):
            raise ValueError('Invalid reasons')


def _mapping(key, record):
    source, external = record.get('source'), record.get('id')
    if not source or not external or ':' in source or external != key:
        return 'Missing or inconsistent source identity'
    if source not in LEGACY_SOURCES:
        return 'Unsupported source (demo is outside this import)'
    if any(not isinstance(record.get(k), str) for k in ('company', 'title', 'location', 'url')):
        return 'Missing normalized posting fields'
    return None


def _observe(session, identity, first, last):
    identity.first_seen = min(identity.first_seen, first)
    identity.last_seen = max(identity.last_seen, last)
    session.add(identity)
    if identity.job_id:
        job = session.get(CanonicalJob, identity.job_id)
        job.first_seen = min(job.first_seen, identity.first_seen)
        job.last_seen = max(job.last_seen, identity.last_seen)
        session.add(job)


def import_search_state(engine: Engine, *, last_search: str | Path | None = None,
                        seen: str | Path | None = None) -> ImportReport:
    """Import either or both files atomically; raise on malformed input.

    Replaying the same semantic search snapshot reuses its run/results. A new
    snapshot represents a new run. Seen timestamps are first observations, not
    evidence that the identity was observed at the time this importer runs.
    Naive timestamps are rejected rather than assigning an invented timezone.
    """
    search = _read(last_search) if last_search is not None else None
    cache = _read(seen) if seen is not None else None
    if search is not None:
        _validate_search(search)
    if cache is not None:
        for timestamp in cache.values():
            _timestamp(timestamp)
    report = ImportReport()
    with database_session(engine) as session:
        repo = JobRepository(session)
        if cache is not None:
            for key, timestamp in cache.items():
                source, separator, external = key.partition(':')
                if not separator or source not in LEGACY_SOURCES or not external:
                    report.unresolved.append(f'seen:{key}: Unresolvable source identity')
                    continue
                first = _timestamp(timestamp)
                identity = repo.get_identity(source, external)
                if identity is None:
                    identity = JobIdentity(source=source, external_id=external,
                                           first_seen=first, last_seen=first)
                    session.add(identity)
                else:
                    _observe(session, identity, first, first)
                session.flush()
        if search is not None:
            digest = hashlib.sha256(json.dumps(search, sort_keys=True,
                                               separators=(',', ':')).encode()).hexdigest()
            existing = session.get(SearchRun, digest)
            if existing is not None:
                report.unresolved.extend(
                    f'last_search:{r.legacy_key}: {r.unresolved}' for r in
                    session.exec(select(SearchResult).where(SearchResult.run_id == digest))
                    if r.unresolved
                )
                return report
            meta = search.get('meta', {})
            session.add(SearchRun(id=digest, generated_at=search.get('generated_at'),
                                  total=meta.get('total'), new_count=meta.get('new_count'),
                                  sources_queried=meta.get('sources_queried'), payload=search))
            session.flush()
            for key, record in search['jobs'].items():
                problem = _mapping(key, record)
                identity = None
                observed = search.get('generated_at') or record.get('first_seen')
                if not observed:
                    problem = problem or 'No supported observation timestamp'
                if problem is None:
                    identity = repo.get_identity(record['source'], record['id'])
                    # A conflicting board for the same source/id is not proof of ownership.
                    if identity and record.get('board') and record['source'] not in (
                            'sr-search', 'remotive', 'remoteok'):
                        previous = session.exec(select(SearchResult).where(
                            SearchResult.identity_id == identity.id)).all()
                        if any(r.payload.get('board') not in (None, '', record['board'])
                               for r in previous):
                            problem = 'Conflicting board for source identity'
                if problem is None:
                    last = _timestamp(observed)
                    first = min(_timestamp(record.get('first_seen') or observed), last)
                    if identity is None:
                        identity = JobIdentity(source=record['source'], external_id=record['id'],
                                               first_seen=first, last_seen=last)
                    if identity.job_id is None:
                        job = CanonicalJob(company=record['company'], title=record['title'],
                                           location=record['location'], posting_url=record['url'],
                                           apply_url=record.get('apply_url'),
                                           first_seen=min(identity.first_seen, first),
                                           last_seen=max(identity.last_seen, last))
                        session.add(job)
                        session.flush()
                        identity.job_id = job.id
                        identity.posting_url = record['url']
                        identity.apply_url = record.get('apply_url')
                    _observe(session, identity, first, last)
                    session.flush()
                else:
                    report.unresolved.append(f'last_search:{key}: {problem}')
                session.add(SearchResult(run_id=digest, legacy_key=key, payload=record,
                                         identity_id=identity.id if identity and not problem else None,
                                         unresolved=problem))
    return report
