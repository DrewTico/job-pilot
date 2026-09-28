"""Synthetic application import evidence and transactional migration checks."""
import hashlib
import json
import sqlite3
from datetime import datetime

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from job_agent.application_import import import_applications
from job_agent.database import (
    ApplicationEvent, CanonicalJob, JobRepository, database_session, initialize_database,
)


@pytest.fixture
def setup(tmp_path):
    engine = initialize_database(tmp_path / 'test.sqlite')
    with database_session(engine) as session:
        repo = JobRepository(session)
        ids = []
        for source in ('greenhouse', 'lever'):
            job = repo.create_job(company='Synthetic', title='Engineer', location='Remote',
                                  posting_url='https://example.test/job')
            repo.add_identity(job.id, source=source, external_id='123',
                              posting_url='https://example.test/job')
            ids.append(job.id)
    path = tmp_path / 'applications.json'
    record = dict(company='Synthetic', title='Engineer', job_id='123', source='lever',
                  date='2026-01-02T01:00:00+01:00', status='submitted', reason='Synthetic reason',
                  attempt_id='attempt-1', notes='Synthetic notes', follow_up='2026-02-01')
    yield engine, path, record, ids
    engine.dispose()


def write(path, records):
    path.write_text(json.dumps(records, indent=2) + '\n')


def rows(engine):
    with database_session(engine) as session:
        return session.exec(select(ApplicationEvent).order_by(ApplicationEvent.record_index)).all()


def test_roundtrip_mapping_state_and_replay(setup):
    engine, path, record, ids = setup
    record['extra'] = {'original': True}
    write(path, [record])
    original = path.read_bytes()
    assert import_applications(engine, applications=path).imported == 1
    assert import_applications(engine, applications=path).skipped == 1
    row, = rows(engine)
    assert row.payload == record
    for key in ('company', 'title', 'source', 'status', 'reason', 'attempt_id', 'notes', 'follow_up'):
        assert getattr(row, key) == record[key]
    assert row.external_job_id == record['job_id']
    assert row.legacy_date == record['date']
    assert row.occurred_at == datetime(2026, 1, 2)
    assert row.job_id == ids[1]
    assert row.status_kind == 'attempt'
    assert row.provenance == 'legacy_applications_snapshot'
    assert row.file_sha256 == hashlib.sha256(original).hexdigest()
    assert row.record_index == 0
    assert path.read_bytes() == original
    with database_session(engine) as session:
        untouched = session.get(CanonicalJob, ids[0])
        job = session.get(CanonicalJob, ids[1])
        assert untouched.application_status is None
        assert (job.application_status, job.application_status_kind,
                job.application_notes, job.application_follow_up) == (
                    'submitted', 'attempt', record['notes'], record['follow_up'])


@pytest.mark.parametrize('changes', [{ 'source': ''}, {'job_id': ''},
                                      {'source': 'unknown'}, {'source': None}])
def test_unresolved_or_invalid_never_guesses(setup, changes):
    engine, path, record, ids = setup
    record.update(changes)
    write(path, [record])
    if changes.get('source', '') is None:
        with pytest.raises(ValueError):
            import_applications(engine, applications=path)
        assert not rows(engine)
    else:
        assert import_applications(engine, applications=path).unresolved
        row, = rows(engine)
        assert row.job_id is None and row.payload == record
    with database_session(engine) as session:
        assert all(session.get(CanonicalJob, i).application_status is None for i in ids)


def test_missing_optional_fields_preserved(setup):
    engine, path, _, _ = setup
    record = dict(company='Synthetic', date='2026-01-01', status='saved')
    write(path, [record])
    import_applications(engine, applications=path)
    row, = rows(engine)
    assert row.payload == record and row.job_id is None
    assert row.status_kind == 'pipeline'


def test_history_changed_snapshot_and_older_state(setup):
    engine, path, record, ids = setup
    write(path, [record])
    import_applications(engine, applications=path)
    updated = dict(record, status='interviewing', notes='New note', follow_up='',
                   date='2026-01-03T00:00:00Z')
    older = dict(record, attempt_id='earlier-attempt', status='failed', date='2026-01-01T00:00:00Z')
    write(path, [record, updated, older])
    result = import_applications(engine, applications=path)
    assert (result.imported, result.skipped) == (2, 1)
    assert import_applications(engine, applications=path).skipped == 3
    assert len(rows(engine)) == 3
    with database_session(engine) as session:
        job = session.get(CanonicalJob, ids[1])
        assert job.application_status == 'interviewing'
        assert job.application_status_kind == 'pipeline'
        assert job.application_notes == 'New note' and job.application_follow_up == ''


def test_duplicate_rows_preserved_and_replay_deduplicated(setup):
    engine, path, record, _ = setup
    write(path, [record, record])
    assert import_applications(engine, applications=path).imported == 2
    assert import_applications(engine, applications=path).skipped == 2
    assert len(rows(engine)) == 2


@pytest.mark.parametrize('bad', ['{', '{}', '[NaN]', '[{"company":"x","company":"y"}]',
                                '[null]', '[42]'])
def test_corrupt_input_zero_writes(setup, bad):
    engine, path, _, _ = setup
    path.write_text(bad)
    original = path.read_bytes()
    with pytest.raises(ValueError):
        import_applications(engine, applications=path)
    assert rows(engine) == []
    assert path.read_bytes() == original


@pytest.mark.parametrize('change', [{'status': 'unknown'}, {'notes': 42}, {'company': None},
                                     {'date': 'bad'}, {'date': '2026-01-01T00:00:00'}])
def test_late_invalid_record_zero_writes(setup, change):
    engine, path, record, ids = setup
    write(path, [record, dict(record, **change)])
    original = path.read_bytes()
    with pytest.raises(ValueError):
        import_applications(engine, applications=path)
    assert rows(engine) == []
    assert path.read_bytes() == original
    with database_session(engine) as session:
        assert session.get(CanonicalJob, ids[1]).application_status is None


def test_mid_import_failure_rolls_back_events_and_state(setup):
    engine, path, record, ids = setup
    write(path, [record, dict(record, attempt_id='two')])
    inserts = 0
    def fail(connection, cursor, statement, parameters, context, executemany):
        nonlocal inserts
        if statement.startswith('INSERT INTO application_events'):
            inserts += 1
            if inserts == 2:
                raise RuntimeError('synthetic failure')
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError):
            import_applications(engine, applications=path)
    finally:
        event.remove(engine, 'before_cursor_execute', fail)
    assert rows(engine) == []
    with database_session(engine) as session:
        assert session.get(CanonicalJob, ids[1]).application_status is None


def test_append_only_and_foreign_key(setup):
    engine, path, record, _ = setup
    write(path, [record])
    import_applications(engine, applications=path)
    for sql in ('UPDATE application_events SET notes = \'changed\'',
                'DELETE FROM application_events'):
        with pytest.raises(IntegrityError, match='append-only'):
            with engine.begin() as connection:
                connection.exec_driver_sql(sql)
    row, = rows(engine)
    with pytest.raises(IntegrityError, match='FOREIGN KEY'):
        with database_session(engine) as session:
            values = row.model_dump(exclude={'id', 'import_key'})
            values['job_id'] = 'missing'
            session.add(ApplicationEvent(**values))
            session.flush()
    assert len(rows(engine)) == 1


def make_v2(path):
    # Construct the previous schema directly, without using current metadata.
    with sqlite3.connect(path) as connection:
        connection.executescript('''
        CREATE TABLE jobs (id VARCHAR PRIMARY KEY, company VARCHAR NOT NULL,
          title VARCHAR NOT NULL, location VARCHAR NOT NULL, posting_url VARCHAR NOT NULL,
          apply_url VARCHAR, first_seen DATETIME NOT NULL, last_seen DATETIME NOT NULL);
        CREATE TABLE job_identities (id INTEGER PRIMARY KEY, job_id VARCHAR REFERENCES jobs(id),
          source VARCHAR NOT NULL, external_id VARCHAR NOT NULL, posting_url VARCHAR,
          apply_url VARCHAR, first_seen DATETIME NOT NULL, last_seen DATETIME NOT NULL,
          UNIQUE(source, external_id));
        CREATE TABLE search_runs (id VARCHAR PRIMARY KEY, generated_at VARCHAR,
          total INTEGER, new_count INTEGER, sources_queried INTEGER, payload JSON NOT NULL);
        CREATE TABLE search_results (id INTEGER PRIMARY KEY, run_id VARCHAR REFERENCES search_runs(id),
          legacy_key VARCHAR, identity_id INTEGER REFERENCES job_identities(id),
          unresolved VARCHAR, payload JSON NOT NULL, UNIQUE(run_id, legacy_key));
        INSERT INTO jobs VALUES ('j', 'Synthetic', 'Engineer', 'Remote', 'url', NULL,
          '2026-01-01 00:00:00', '2026-01-01 00:00:00');
        INSERT INTO job_identities VALUES (1, 'j', 'lever', '123', 'url', NULL,
          '2026-01-01 00:00:00', '2026-01-01 00:00:00');
        INSERT INTO search_runs VALUES ('r', '2026-01-01', 1, 1, 1, '{}');
        INSERT INTO search_results VALUES (1, 'r', '123', 1, NULL, '{"id":"123"}');
        PRAGMA user_version = 2;
        ''')


def test_upgrade_v2_preserves_all_rows(tmp_path):
    path = tmp_path / 'v2.sqlite'
    make_v2(path)
    with sqlite3.connect(path) as connection:
        before = {t: connection.execute(f'SELECT * FROM {t}').fetchall()
                  for t in ('jobs', 'job_identities', 'search_runs', 'search_results')}
    engine = initialize_database(path)
    engine.dispose()
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone() == (3,)
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        for table, expected in before.items():
            after = connection.execute(f'SELECT * FROM {table}').fetchall()
            assert [row[:len(expected[0])] for row in after] == expected


def test_migration_ddl_failure_is_atomic(tmp_path, monkeypatch):
    path = tmp_path / 'v2.sqlite'
    make_v2(path)
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic DDL failure')
    monkeypatch.setattr(ApplicationEvent.__table__, 'create', fail)
    with pytest.raises(RuntimeError):
        initialize_database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone() == (2,)
        columns = connection.execute('PRAGMA table_info(jobs)').fetchall()
        assert len(columns) == 8
        assert connection.execute('SELECT id FROM jobs').fetchall() == [('j',)]


@pytest.mark.parametrize('status', ['submitted', 'paused', 'failed', 'saved', 'applied',
                                    'interviewing', 'offer', 'rejected'])
def test_all_statuses_keep_their_meaning(setup, status):
    engine, path, record, ids = setup
    write(path, [dict(record, status=status)])
    import_applications(engine, applications=path)
    row, = rows(engine)
    assert row.status == status
    assert row.status_kind == ('attempt' if status in ('submitted', 'paused', 'failed')
                               else 'pipeline')
    with database_session(engine) as session:
        assert session.get(CanonicalJob, ids[1]).application_status == status


def test_unattached_identity_and_replay_remain_unresolved(setup):
    from job_agent.database import JobIdentity
    engine, path, record, ids = setup
    with database_session(engine) as session:
        session.add(JobIdentity(source='synthetic', external_id='123',
                                first_seen=datetime(2026, 1, 1), last_seen=datetime(2026, 1, 1)))
    write(path, [dict(record, source='synthetic')])
    assert import_applications(engine, applications=path).unresolved
    with database_session(engine) as session:
        JobRepository(session).add_identity(ids[0], source='synthetic', external_id='123',
                                            posting_url='https://example.test/job')
    assert import_applications(engine, applications=path).unresolved
    row, = rows(engine)
    assert row.job_id is None
    with database_session(engine) as session:
        assert session.get(CanonicalJob, ids[0]).application_status is None


def test_equal_date_edits_append_and_replay_does_not_revert(setup):
    engine, path, record, ids = setup
    write(path, [record])
    import_applications(engine, applications=path)
    write(path, [dict(record, status='offer', notes='Edited')])
    import_applications(engine, applications=path)
    write(path, [record])
    assert import_applications(engine, applications=path).skipped == 1
    assert len(rows(engine)) == 2
    with database_session(engine) as session:
        job = session.get(CanonicalJob, ids[1])
        assert job.application_status == 'offer' and job.application_notes == 'Edited'
