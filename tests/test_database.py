"""Synthetic tests for the opt-in SQLite repository."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from job_agent.database import (
    CanonicalJob, JobIdentity, JobRepository, database_session, initialize_database,
)

EARLY = datetime(2026, 1, 1, tzinfo=timezone.utc)
LATE = datetime(2026, 1, 3, tzinfo=timezone.utc)
POSTING = 'https://example.test/jobs/1?utm_source=board&a=1&a=2#details'
APPLY = 'https://example.test/apply?token=a%2Fb+Z&redirect=%2Fjobs%3Fx%3D1'


@pytest.fixture
def engine(tmp_path):
    result = initialize_database(tmp_path / 'jobs.sqlite')
    yield result
    result.dispose()


def create(repo):
    return repo.create_job(company='Synthetic Co', title='Engineer', location='Remote',
                           posting_url=POSTING, apply_url=APPLY, seen_at=EARLY)


def attach(repo, job, source='synthetic', external_id='123', seen_at=EARLY):
    return repo.add_identity(job.id, source=source, external_id=external_id,
                             posting_url=POSTING, apply_url=APPLY, seen_at=seen_at)


def test_persistence_and_verbatim_urls(tmp_path):
    path = tmp_path / 'jobs.sqlite'
    first = initialize_database(path)
    with database_session(first) as session:
        repo = JobRepository(session)
        job = create(repo)
        attach(repo, job)
        job_id = job.id
        assert job_id != '123'
    first.dispose()
    reopened = initialize_database(path)
    try:
        with database_session(reopened) as session:
            repo = JobRepository(session)
            job = repo.get_job(job_id)
            identity = repo.get_identity('synthetic', '123')
            assert identity.job_id == job_id
            for row in (job, identity):
                assert row.posting_url == POSTING
                assert row.apply_url == APPLY
                assert row.first_seen == EARLY.replace(tzinfo=None)
    finally:
        reopened.dispose()


def test_idempotency_and_seen_timestamps(engine):
    with database_session(engine) as session:
        repo = JobRepository(session)
        job = create(repo)
        original = attach(repo, job)
        original_id = original.id
    with database_session(engine) as session:
        repo = JobRepository(session)
        job = repo.get_job(job.id)
        repeated = attach(repo, job, seen_at=LATE)
        assert repeated.id == original_id
        repo.observe_identity('synthetic', '123', seen_at=EARLY)
        assert len(repo.identities_for_job(job.id)) == 1
        for row in (job, repeated):
            assert row.first_seen == EARLY.replace(tzinfo=None)
            assert row.last_seen == LATE.replace(tzinfo=None)


@pytest.mark.parametrize('attachment_day', [2, 4])
def test_seen_only_identity_attaches_without_losing_history(engine, attachment_day):
    attached_at = datetime(2026, 1, attachment_day, tzinfo=timezone.utc)
    with database_session(engine) as session:
        identity = JobIdentity(source='synthetic', external_id='123',
                               first_seen=EARLY, last_seen=LATE)
        session.add(identity)
        session.flush()
        identity_id = identity.id
        assert identity.job_id is None
        assert identity.posting_url is None
        assert identity.apply_url is None

    with database_session(engine) as session:
        repo = JobRepository(session)
        job = repo.create_job(company='Synthetic Co', title='Engineer', location='Remote',
                              posting_url=POSTING, seen_at=attached_at)
        attached = attach(repo, job, seen_at=attached_at)
        assert attached.id == identity_id
        job_id = job.id

    with database_session(engine) as session:
        repo = JobRepository(session)
        identity = repo.get_identity('synthetic', '123')
        job = repo.get_job(job_id)
        assert identity.job_id == job_id
        assert identity.posting_url == POSTING
        assert identity.apply_url == APPLY
        for row in (identity, job):
            assert row.first_seen == EARLY.replace(tzinfo=None)
            assert row.last_seen == max(LATE, attached_at).replace(tzinfo=None)
        other = create(repo)
        with pytest.raises(ValueError, match='already belongs'):
            attach(repo, other)
        assert identity.job_id == job_id


def test_source_scope_and_no_company_title_location_uniqueness(engine):
    with database_session(engine) as session:
        repo = JobRepository(session)
        one, two = create(repo), create(repo)
        assert one.id != two.id
        left = attach(repo, one, source='board-a')
        right = attach(repo, two, source='board-b')
        assert left.id != right.id
        assert repo.get_identity('board-a', '123').job_id == one.id
        assert repo.get_identity('board-b', '123').job_id == two.id


def test_multiple_verified_identities(engine):
    with database_session(engine) as session:
        repo = JobRepository(session)
        job = create(repo)
        one = attach(repo, job, source='board-a')
        two = attach(repo, job, source='board-b')
        assert {row.id for row in repo.identities_for_job(job.id)} == {one.id, two.id}
        assert one.job_id == two.job_id


def test_conflicting_identity_rolls_back_partial_job(engine):
    with database_session(engine) as session:
        repo = JobRepository(session)
        original = create(repo)
        attach(repo, original)
    with pytest.raises(ValueError, match='already belongs'):
        with database_session(engine) as session:
            repo = JobRepository(session)
            partial = create(repo)
            attach(repo, partial)
    with database_session(engine) as session:
        repo = JobRepository(session)
        assert repo.get_job(partial.id) is None
        assert repo.get_identity('synthetic', '123').job_id == original.id


def test_foreign_keys_on_every_connection_and_rollback(engine):
    with engine.connect() as one, engine.connect() as two:
        assert one.exec_driver_sql('PRAGMA foreign_keys').scalar_one() == 1
        assert two.exec_driver_sql('PRAGMA foreign_keys').scalar_one() == 1
    engine.dispose()  # Also verify a newly opened connection.
    with pytest.raises(IntegrityError):
        with database_session(engine) as session:
            job = create(JobRepository(session))
            session.add(JobIdentity(job_id='missing', source='synthetic', external_id='bad',
                                    posting_url=POSTING, first_seen=EARLY, last_seen=EARLY))
            session.flush()
    with database_session(engine) as session:
        assert session.get(CanonicalJob, job.id) is None
        assert session.exec(select(JobIdentity)).all() == []


def test_database_enforces_identity_uniqueness_and_restricts_job_deletion(engine):
    with database_session(engine) as session:
        repo = JobRepository(session)
        job = create(repo)
        attach(repo, job)
    with pytest.raises(IntegrityError):
        with database_session(engine) as session:
            session.add(JobIdentity(job_id=job.id, source='synthetic', external_id='123',
                                    posting_url=POSTING, first_seen=EARLY, last_seen=EARLY))
            session.flush()
    with pytest.raises(IntegrityError):
        with database_session(engine) as session:
            session.delete(session.get(CanonicalJob, job.id))
            session.flush()


def test_schema_version_and_only_requested_tables(engine):
    with engine.connect() as connection:
        assert connection.exec_driver_sql('PRAGMA user_version').scalar_one() == 2
        tables = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).scalars().all()
        assert set(tables) == {'jobs', 'job_identities', 'search_runs', 'search_results'}


@pytest.mark.parametrize('version', [3, 99])
def test_unknown_version_is_not_modified(tmp_path, version):
    path = tmp_path / 'future.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute(f'PRAGMA user_version = {version}')
    with pytest.raises(ValueError, match='Unsupported'):
        initialize_database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == version
        assert connection.execute('SELECT name FROM sqlite_master').fetchall() == []


def test_nonempty_unversioned_database_is_not_adopted(tmp_path):
    path = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE legacy (id INTEGER)')
    with pytest.raises(ValueError, match='nonempty unversioned'):
        initialize_database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 0
        assert connection.execute('SELECT name FROM sqlite_master').fetchall() == [('legacy',)]


def test_import_creates_no_file(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'),
               PYTHONDONTWRITEBYTECODE='1', HOME=str(tmp_path))
    subprocess.run([sys.executable, '-c', 'import job_agent.database'],
                   cwd=tmp_path, env=env, check=True, capture_output=True)
    assert list(tmp_path.rglob('*')) == []


def test_naive_observation_rejected(engine):
    with database_session(engine) as session:
        repo = JobRepository(session)
        with pytest.raises(ValueError, match='timezone-aware'):
            repo.create_job(company='Synthetic', title='Engineer', location='Remote',
                            posting_url=POSTING, seen_at=datetime(2026, 1, 1))
        assert session.exec(select(CanonicalJob)).all() == []
