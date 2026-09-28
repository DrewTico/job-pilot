"""Synthetic search-state migration coverage; no real user data."""
import json
import sqlite3
from datetime import datetime

import pytest
from sqlmodel import select

from job_agent.database import (
    CanonicalJob, JobIdentity, SearchRun, SearchResult, database_session, initialize_database,
)
from job_agent.search_import import import_search_state

EARLY = '2026-01-01T02:00:00+02:00'
LATE = '2026-01-03T00:00:00+00:00'
URL = 'https://example.test/1?a=1&a=2&token=a%2Fb+Z#details'


@pytest.fixture
def setup(tmp_path):
    engine = initialize_database(tmp_path / 'test.sqlite')
    record = dict(id='123', source='greenhouse', title='Engineer', company='Synthetic',
                  location='Remote', url=URL, apply_url=URL + '&apply=true', board='synthetic',
                  token='opaque', score=72, verdict='possible', reasons=['Relevant'],
                  first_seen=LATE, first_seen_this_scan=False, remote=True, country=None,
                  posted_at=None, description='Synthetic posting')
    data = dict(generated_at=LATE, meta=dict(total=1, new_count=None), jobs={'123': record})
    search, seen = tmp_path / 'last_search.json', tmp_path / 'seen.json'
    search.write_text(json.dumps(data))
    seen.write_text(json.dumps({'greenhouse:123': EARLY, 'lever:123': EARLY,
                                'ashby:opaque:123': EARLY}))
    yield engine, search, seen, data
    engine.dispose()


def rows(engine, model):
    with database_session(engine) as session:
        return session.exec(select(model)).all()


def test_search_roundtrip_and_idempotency(setup):
    engine, search, _, data = setup
    before = search.read_bytes()
    for _ in range(2):
        assert not import_search_state(engine, last_search=search).unresolved
    run, = rows(engine, SearchRun)
    result, = rows(engine, SearchResult)
    assert run.payload == data
    assert run.new_count is None and run.sources_queried is None
    assert result.payload == data['jobs']['123']
    assert result.payload['first_seen_this_scan'] is False
    assert 'missing_requirements' not in result.payload
    job, = rows(engine, CanonicalJob)
    assert job.posting_url == URL and job.apply_url == data['jobs']['123']['apply_url']
    assert len(rows(engine, JobIdentity)) == 1
    assert search.read_bytes() == before
    data['meta'].update(new_count=0, sources_queried=4)
    data['generated_at'] = '2026-01-04T00:00:00Z'
    data['jobs']['123']['first_seen_this_scan'] = True
    search.write_text(json.dumps(data))
    import_search_state(engine, last_search=search)
    import_search_state(engine, last_search=search)
    assert len(rows(engine, CanonicalJob)) == 1
    assert len(rows(engine, SearchRun)) == len(rows(engine, SearchResult)) == 2
    assert {r.new_count for r in rows(engine, SearchRun)} == {None, 0}
    assert rows(engine, CanonicalJob)[0].last_seen == datetime(2026, 1, 4)


@pytest.mark.parametrize('order', ['seen-first', 'search-first', 'together'])
def test_earliest_and_seen_only(setup, order):
    engine, search, seen, _ = setup
    before = seen.read_bytes()
    if order == 'together':
        import_search_state(engine, last_search=search, seen=seen)
    else:
        operations = [{'seen': seen}, {'last_search': search}]
        if order == 'search-first':
            operations.reverse()
        for kwargs in operations:
            import_search_state(engine, **kwargs)
    import_search_state(engine, seen=seen, last_search=search)
    identities = rows(engine, JobIdentity)
    assert len(identities) == 3
    assert all(i.first_seen == datetime(2026, 1, 1) for i in identities)
    orphan = next(i for i in identities if i.source == 'lever')
    assert orphan.job_id is None and orphan.posting_url is None
    assert next(i for i in identities if i.source == 'ashby').external_id == 'opaque:123'
    job, = rows(engine, CanonicalJob)
    assert job.first_seen == datetime(2026, 1, 1)
    assert job.last_seen == datetime(2026, 1, 3)
    assert seen.read_bytes() == before


@pytest.mark.parametrize('bad', ['{', '{"x":NaN}', '{"x":1,"x":2}',
                                  '{"greenhouse:123":"not a date"}'])
def test_bad_seen_zero_writes(setup, bad):
    engine, search, seen, _ = setup
    seen.write_text(bad)
    with pytest.raises(ValueError):
        import_search_state(engine, last_search=search, seen=seen)
    for model in (CanonicalJob, JobIdentity, SearchRun, SearchResult):
        assert rows(engine, model) == []


def test_late_invalid_record_zero_writes(setup):
    engine, search, seen, data = setup
    data['jobs']['bad'] = {'score': 'invalid'}
    search.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        import_search_state(engine, last_search=search, seen=seen)
    assert rows(engine, JobIdentity) == rows(engine, SearchRun) == []


def test_unresolved_and_source_scope(setup):
    engine, search, seen, data = setup
    import_search_state(engine, last_search=search)
    data['jobs']['123']['source'] = 'lever'
    search.write_text(json.dumps(data))
    import_search_state(engine, last_search=search)
    assert len(rows(engine, CanonicalJob)) == 2
    data['jobs']['123']['id'] = 'mismatch'
    search.write_text(json.dumps(data))
    assert import_search_state(engine, last_search=search).unresolved
    assert len(rows(engine, CanonicalJob)) == 2
    data['jobs']['123'].update(id='123', board='conflicting')
    search.write_text(json.dumps(data))
    assert 'Conflicting board' in import_search_state(engine, last_search=search).unresolved[0]
    seen.write_text(json.dumps({'bare-id': EARLY}))
    assert import_search_state(engine, seen=seen).unresolved


def test_transaction_failure_rolls_back(setup, monkeypatch):
    engine, search, seen, _ = setup
    import job_agent.search_import as module
    def fail(*args):
        raise RuntimeError('synthetic write failure')
    monkeypatch.setattr(module, '_observe', fail)
    with pytest.raises(RuntimeError):
        import_search_state(engine, last_search=search, seen=seen)
    for model in (CanonicalJob, JobIdentity, SearchRun, SearchResult):
        assert rows(engine, model) == []


def test_upgrade_v1_preserves_rows(tmp_path):
    path = tmp_path / 'v1.sqlite'
    with sqlite3.connect(path) as connection:
        connection.executescript('''
            CREATE TABLE jobs (id VARCHAR PRIMARY KEY, company VARCHAR NOT NULL,
              title VARCHAR NOT NULL, location VARCHAR NOT NULL, posting_url VARCHAR NOT NULL,
              apply_url VARCHAR, first_seen DATETIME NOT NULL, last_seen DATETIME NOT NULL);
            CREATE TABLE job_identities (id INTEGER PRIMARY KEY, job_id VARCHAR NOT NULL REFERENCES jobs(id),
              source VARCHAR NOT NULL, external_id VARCHAR NOT NULL, posting_url VARCHAR NOT NULL,
              apply_url VARCHAR, first_seen DATETIME NOT NULL, last_seen DATETIME NOT NULL,
              UNIQUE(source, external_id));
            INSERT INTO jobs VALUES ('j', 'Synthetic', 'Engineer', 'Remote', 'url', NULL,
              '2026-01-01 00:00:00', '2026-01-01 00:00:00');
            INSERT INTO job_identities VALUES (1, 'j', 'lever', '123', 'url', NULL,
              '2026-01-01 00:00:00', '2026-01-01 00:00:00');
            PRAGMA user_version = 1;
        ''')
    engine = initialize_database(path)
    try:
        assert rows(engine, JobIdentity)[0].job_id == 'j'
        assert rows(engine, CanonicalJob)[0].posting_url == 'url'
        with engine.connect() as connection:
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
    finally:
        engine.dispose()


def test_seen_alone_and_older_repository_observation(setup):
    engine, _, seen, _ = setup
    from datetime import timezone
    from job_agent.database import JobRepository
    import_search_state(engine, seen=seen)
    import_search_state(engine, seen=seen)
    assert rows(engine, CanonicalJob) == []
    assert rows(engine, SearchRun) == []
    assert len(rows(engine, JobIdentity)) == 3
    with database_session(engine) as session:
        identity = JobRepository(session).observe_identity(
            'lever', '123', seen_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
        assert identity.first_seen == datetime(2025, 1, 1)
        assert identity.last_seen == datetime(2026, 1, 1)


def test_absent_fields_stay_absent(setup):
    engine, search, _, data = setup
    for key in ('first_seen', 'first_seen_this_scan', 'board', 'token', 'score', 'verdict', 'reasons'):
        del data['jobs']['123'][key]
    data.pop('meta')
    search.write_text(json.dumps(data))
    import_search_state(engine, last_search=search)
    result, = rows(engine, SearchResult)
    assert result.payload == data['jobs']['123']
    run, = rows(engine, SearchRun)
    assert run.total is None and run.new_count is None and run.sources_queried is None


def test_naive_timestamp_is_rejected(setup):
    engine, search, seen, _ = setup
    seen.write_text(json.dumps({'lever:123': '2026-01-01T00:00:00'}))
    with pytest.raises(ValueError, match='timezone-aware'):
        import_search_state(engine, last_search=search, seen=seen)
    assert rows(engine, SearchRun) == []
