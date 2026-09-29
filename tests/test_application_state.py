"""Synthetic coverage for the production application persistence cutover."""
import json
from argparse import Namespace

import pytest
from fastapi.testclient import TestClient
from rich.console import Console
from sqlalchemy import text
from sqlmodel import select

from job_agent import application_state as state
from job_agent.apply.tracker import ApplicationRecord
from job_agent.database import ApplicationEvent, CanonicalJob, JobIdentity, JobRepository, database_session
from job_agent.search_state import search_database


def record(**changes):
    return ApplicationRecord(**(dict(company='Synthetic Co', title='Engineer', job_id='same',
        source='ashby', date='2026-01-01T00:00:00+00:00', status='paused') | changes))


def seed(path):
    with search_database(path) as engine, database_session(engine) as session:
        repo = JobRepository(session)
        ids = []
        for source in ('ashby', 'greenhouse'):
            job = repo.create_job(company='Synthetic Co', title='Engineer', location='Remote',
                                  posting_url=f'https://example.test/{source}')
            repo.add_identity(job.id, source=source, external_id='same', posting_url=job.posting_url)
            ids.append(job.id)
        return ids


def events(path):
    with state.application_database(path) as engine, database_session(engine) as session:
        return session.exec(select(ApplicationEvent).order_by(text('rowid'))).all()


@pytest.mark.parametrize('operation', ['attempt', 'pipeline'])
def test_contradictory_canonical_identity_writes_nothing(tmp_path, operation):
    a, b = seed(tmp_path)
    with state.application_database(tmp_path) as engine, database_session(engine) as session:
        before = {j.id: j.model_dump() for j in session.exec(select(CanonicalJob))}
        identities = [i.model_dump() for i in session.exec(select(JobIdentity))]
    with pytest.raises(ValueError, match='different canonical job'):
        if operation == 'attempt':
            state.record_attempt(tmp_path, record(source='greenhouse'), canonical_id=a)
        else:
            state.upsert_job_state(tmp_path, canonical_id=a, source='greenhouse',
                                   job_id='same', status='applied')
    assert events(tmp_path) == []
    with state.application_database(tmp_path) as engine, database_session(engine) as session:
        assert {j.id: j.model_dump() for j in session.exec(select(CanonicalJob))} == before
        assert [i.model_dump() for i in session.exec(select(JobIdentity))] == identities
        assert set(before) == {a, b}


@pytest.mark.parametrize('source,external', [('ashby', 'same'), ('ashby', 'unknown'),
                                          ('', ''), ('ashby', ''), ('', 'same')])
def test_canonical_authority_with_matching_unknown_or_absent_identity(tmp_path, source, external):
    a, _ = seed(tmp_path)
    state.record_attempt(tmp_path, record(source=source, job_id=external), canonical_id=a)
    state.upsert_job_state(tmp_path, canonical_id=a, status='interviewing')
    assert [e.job_id for e in events(tmp_path)] == [a, a]
    assert state.load_applications(tmp_path)[0].status == 'interviewing'
    with state.application_database(tmp_path) as engine, database_session(engine) as session:
        assert len(session.exec(select(JobIdentity)).all()) == 2


def test_unknown_canonical_id_is_not_replaced_by_source_identity(tmp_path):
    seed(tmp_path)
    with pytest.raises(KeyError, match='Unknown canonical job'):
        state.record_attempt(tmp_path, record(), canonical_id='missing')
    assert events(tmp_path) == []


def test_source_resolution_is_exact_and_never_company_title_based(tmp_path):
    a, b = seed(tmp_path)  # identical company/title and external IDs, different sources
    for source, external in [('ashby', 'same'), ('greenhouse', 'same'),
                             ('ashby', 'unknown'), ('unknown', 'same'), ('', 'same')]:
        state.record_attempt(tmp_path, record(source=source, job_id=external))
    assert [e.job_id for e in events(tmp_path)] == [a, b, None, None, None]
    with state.application_database(tmp_path) as engine, database_session(engine) as session:
        assert len(session.exec(select(JobIdentity)).all()) == 2


def test_cutover_once_preserves_bytes_and_ignores_stale_file(tmp_path):
    seed(tmp_path)
    legacy = tmp_path / 'applications.json'
    raw = json.dumps([record(status='submitted').model_dump()], indent=3).encode()
    legacy.write_bytes(raw)
    assert state.load_applications(tmp_path)[0].status == 'submitted'
    assert legacy.read_bytes() == raw
    legacy.write_text('{broken')
    assert state.load_applications(tmp_path)[0].status == 'submitted'
    assert len(events(tmp_path)) == 1


@pytest.mark.parametrize('payload', ['{', '[{}]', json.dumps([record().model_dump(), {}])])
def test_bad_import_aborts_atomically(tmp_path, payload):
    seed(tmp_path)
    (tmp_path / 'applications.json').write_text(payload)
    with pytest.raises(ValueError):
        state.load_applications(tmp_path)
    with search_database(tmp_path) as engine, database_session(engine) as session:
        assert session.exec(select(ApplicationEvent)).all() == []
        assert all(j.application_status is None for j in session.exec(select(CanonicalJob)))
    (tmp_path / 'applications.json').write_text('[]')
    assert state.load_applications(tmp_path) == []


def test_native_history_notes_identity_and_reopen(tmp_path):
    a, b = seed(tmp_path)
    state.upsert_job_state(tmp_path, canonical_id=a, source='ashby', job_id='same',
                           status='saved', notes='Synthetic note', follow_up='2026-10-01')
    attempt = state.record_attempt(tmp_path, record(), canonical_id=a)
    state.update_status(tmp_path, attempt, 'submitted')
    history = events(tmp_path)
    assert [e.status for e in history] == ['saved', 'paused', 'submitted']
    assert [e.status_kind for e in history] == ['pipeline', 'attempt', 'attempt']
    assert all(e.job_id == a and e.source == 'ashby' and e.external_job_id == 'same' for e in history)
    assert len({e.id for e in history}) == 3
    markers = state.applied_markers(tmp_path)
    assert state.is_already_applied(markers, canonical_id=a)
    assert not state.is_already_applied(markers, canonical_id=b, source='greenhouse', job_id='same')
    state.record_attempt(tmp_path, record(source='greenhouse'), canonical_id=b)
    row = next(r for r in state.load_applications(tmp_path) if r.canonical_id == a)
    assert (row.notes, row.follow_up) == ('Synthetic note', '2026-10-01')
    assert not (tmp_path / 'applications.json').exists()
    with state.application_database(tmp_path) as engine, database_session(engine) as session:
        job = session.get(CanonicalJob, a)
        assert (job.application_status, job.application_status_kind) == ('submitted', 'attempt')
        with pytest.raises(Exception, match='append-only'):
            session.execute(text('DELETE FROM application_events'))


def test_cutover_marker_and_import_rollback_together(tmp_path, monkeypatch):
    seed(tmp_path)
    (tmp_path / 'applications.json').write_text(json.dumps([record().model_dump()]))
    original = state.import_applications

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('Synthetic interruption before marker')

    monkeypatch.setattr(state, 'import_applications', interrupted)
    with pytest.raises(RuntimeError, match='Synthetic interruption'):
        state.load_applications(tmp_path)
    with search_database(tmp_path) as engine, database_session(engine) as session:
        assert session.exec(select(ApplicationEvent)).all() == []
        assert all(j.application_status is None for j in session.exec(select(CanonicalJob)))
    monkeypatch.setattr(state, 'import_applications', original)
    assert len(state.load_applications(tmp_path)) == 1


def test_absent_legacy_is_also_a_permanent_cutover(tmp_path):
    assert state.load_applications(tmp_path) == []
    (tmp_path / 'applications.json').write_text('{broken')
    assert state.load_applications(tmp_path) == []


def test_notes_edits_and_retries_preserve_history(tmp_path):
    a, _ = seed(tmp_path)
    first = state.record_attempt(tmp_path, record(), canonical_id=a)
    state.upsert_job_state(tmp_path, attempt_id=first, notes='Edited during attempt',
                           follow_up='2026-12-01')
    state.update_status(tmp_path, first, 'failed')
    second = state.record_attempt(tmp_path, record(), canonical_id=a)
    state.update_status(tmp_path, second, 'submitted')
    before = [(e.id, e.status, e.notes) for e in events(tmp_path)]
    assert len(before) == 5 and first != second
    state.upsert_job_state(tmp_path, canonical_id=a, status='interviewing')
    assert [(e.id, e.status, e.notes) for e in events(tmp_path)][:5] == before
    row, = state.load_applications(tmp_path)
    assert (row.status, row.application_status_kind) == ('interviewing', 'pipeline')
    assert (row.notes, row.follow_up) == ('Edited during attempt', '2026-12-01')


def test_dashboard_join_and_tracking_with_colliding_external_ids(tmp_path):
    from job_agent.dashboard.app import create_app
    from job_agent.models import Job, ScoredJob
    from job_agent.search_state import SearchRepository, SQLiteSeenCache
    jobs = [Job(id='same', source=source, title='Engineer', company='Synthetic Co',
                location='Remote', url=f'https://example.test/{source}')
            for source in ('ashby', 'greenhouse')]
    with search_database(tmp_path) as engine, database_session(engine) as session:
        SearchRepository(session).record_search(
            [ScoredJob(job=j, score=80, verdict='strong') for j in jobs],
            ['ashby', 'greenhouse'], cache=SQLiteSeenCache(session), baseline=True)
    client = TestClient(create_app(data_dir=tmp_path))
    assert client.post('/api/track', json={'job_id': 'same', 'status': 'applied'}).status_code == 409
    result = client.post('/api/track', json={'job_id': 'ashby:same', 'status': 'applied'})
    assert result.status_code == 200
    rows = {j['source']: j for j in client.get('/api/jobs').json()['jobs']}
    assert rows['ashby']['already_applied'] is True
    assert rows['greenhouse']['already_applied'] is False
    assert rows['greenhouse']['tracked'] is None
    assert result.json()['canonical_id'] == rows['ashby']['canonical_id']
    assert not (tmp_path / 'applications.json').exists()


def test_pipeline_api_rejects_attempt_outcomes(tmp_path):
    a, _ = seed(tmp_path)
    with pytest.raises(ValueError, match='pipeline'):
        state.upsert_job_state(tmp_path, canonical_id=a, status='submitted')
    assert events(tmp_path) == []


@pytest.mark.parametrize('status,hidden', [('submitted', True), ('applied', True),
    ('interviewing', True), ('offer', True), ('saved', False), ('paused', False),
    ('failed', False), ('rejected', False)])
def test_marker_semantics(tmp_path, status, hidden):
    a, _ = seed(tmp_path)
    if status in ('submitted', 'paused', 'failed'):
        state.record_attempt(tmp_path, record(status=status), canonical_id=a)
    else:
        state.upsert_job_state(tmp_path, canonical_id=a, source='ashby', job_id='same', status=status)
    assert state.is_already_applied(state.applied_markers(tmp_path), source='ashby', job_id='same') == hidden


def test_dashboard_and_cli_read_sqlite_after_cutover(tmp_path):
    from job_agent.dashboard.app import create_app
    from job_agent.cli import cmd_applications
    a, _ = seed(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.post('/api/track', json=dict(canonical_id=a, job_id='same', source='ashby',
                                                company='Synthetic Co', status='applied'))
    assert response.status_code == 200
    assert client.get('/api/applications').json()['records'][0]['status'] == 'applied'
    console = Console(record=True)
    assert cmd_applications(console, Namespace(log=str(tmp_path / 'job_pilot.sqlite3'))) == 0
    assert 'Synthetic Co' in console.export_text()
    assert not (tmp_path / 'applications.json').exists()
