"""Synthetic production cutover tests: no network, LLM, or personal data."""
import json
from argparse import Namespace
from datetime import datetime, timedelta, timezone

import pytest
from rich.console import Console
from sqlmodel import select

from job_agent import cli, search
from job_agent.config import SearchProfile, Settings, SourceRef
from job_agent.database import JobIdentity, SearchRun, SearchResult, database_session, initialize_database
from job_agent.models import Job, ScoredJob
from job_agent.search_state import (
    AmbiguousJobError, SearchRepository, SQLiteSeenCache, database_path,
    latest_search, load_job_record, search_database,
)

NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)


def job(id='1', source='greenhouse', **kw):
    return Job(id=id, source=source, title=f'Engineer {id}', company=source,
               location='US', url=f'https://example.test/{source}/{id}?x=1',
               apply_url=f'https://example.test/apply/{id}?oga=true', **kw)


def scan(directory, jobs, now=NOW):
    profile = SearchProfile(keywords=['Engineer'], sources=[SourceRef(ats='greenhouse', board='token')])
    class Source:
        def fetch(self):
            return jobs
        def enrich(self, j):
            return j
    with search_database(directory) as engine, database_session(engine) as session:
        cache = SQLiteSeenCache(session)
        outcome = search.run(profile, seen_cache=cache, now=now,
                             source_factory=lambda *a: Source())
        SearchRepository(session).record_search(
            [ScoredJob(job=j, score=91, verdict='strong', reasons=('specific reason',)) for j in outcome.jobs],
            outcome.boards, cache=cache, baseline=outcome.baseline_scan, sources_queried=1)
    return latest_search(directory)


def test_baseline_reopen_newness_and_roundtrip(tmp_path):
    original = job(description='Full description')
    first = scan(tmp_path, [original])
    assert first['meta'] == dict(total=1, new_count=None, sources_queried=1)
    record = load_job_record(tmp_path, '1')
    assert all(record[k] == v for k, v in original.model_dump(mode='json').items())
    assert record['board'] == record['token'] == 'token'
    assert (record['score'], record['verdict'], record['reasons']) == (91, 'strong', ['specific reason'])
    second = scan(tmp_path, [original, job(source='lever')], NOW + timedelta(hours=1))
    assert second['meta']['new_count'] == 1
    assert second['jobs']['greenhouse:1']['first_seen'] == record['first_seen']
    assert not second['jobs']['greenhouse:1']['first_seen_this_scan']
    assert second['jobs']['lever:1']['first_seen_this_scan']
    with pytest.raises(AmbiguousJobError, match='Ambiguous.*greenhouse:1.*lever:1'):
        load_job_record(tmp_path, '1')
    assert load_job_record(tmp_path, 'greenhouse:1') == second['jobs']['greenhouse:1']
    assert load_job_record(tmp_path, 'canonical:' + record['canonical_id']) == second['jobs']['greenhouse:1']
    assert load_job_record(tmp_path, record['canonical_id']) == second['jobs']['greenhouse:1']
    assert database_path(tmp_path).exists()
    assert not (tmp_path / 'seen.json').exists()
    assert not (tmp_path / 'last_search.json').exists()
    assert scan(tmp_path, [])['jobs'] == {}
    assert load_job_record(tmp_path, '1') is None


def test_seen_bounds_and_transaction_rollback(tmp_path):
    with search_database(tmp_path) as engine:
        with database_session(engine) as session:
            cache = SQLiteSeenCache(session)
            assert len(cache) == 0
            assert cache.first_seen('greenhouse', '1', NOW) == (NOW, True)
            cache.observe('greenhouse', '1', NOW + timedelta(days=2))
            earlier = NOW - timedelta(days=2)
            assert cache.first_seen('greenhouse', '1', earlier) == (earlier, False)
            assert len(cache) == 1
        with pytest.raises(RuntimeError), database_session(engine) as session:
            cache = SQLiteSeenCache(session)
            cache.observe('lever', '2', NOW)
            SearchRepository(session).record_search([], [], cache=cache, baseline=False)
            raise RuntimeError('scoring or persistence failed')
        with database_session(engine) as session:
            identities = session.exec(select(JobIdentity)).all()
            assert len(identities) == 1
            assert identities[0].first_seen == earlier.replace(tzinfo=None)
            assert identities[0].last_seen == (NOW + timedelta(days=2)).replace(tzinfo=None)
            assert not session.exec(select(SearchRun)).all()


def test_legacy_import_is_once_and_bytes_unchanged(tmp_path):
    legacy = dict(generated_at=NOW.isoformat(), jobs={'1': job().model_dump(mode='json')})
    files = {'last_search.json': json.dumps(legacy), 'seen.json': json.dumps({'greenhouse:1': NOW.isoformat()})}
    for name, content in files.items():
        (tmp_path / name).write_text(content)
    assert load_job_record(tmp_path, '1')['id'] == '1'
    latest_search(tmp_path)
    with search_database(tmp_path) as engine, database_session(engine) as session:
        assert len(session.exec(select(SearchRun)).all()) == 1
    scan(tmp_path, [job('2')], NOW + timedelta(hours=1))
    assert load_job_record(tmp_path, '1') is None
    for name, content in files.items():
        assert (tmp_path / name).read_bytes() == content.encode()
    # A completed cutover never reads the stale files again.
    (tmp_path / 'seen.json').write_text('broken')
    assert load_job_record(tmp_path, '2')['id'] == '2'


@pytest.mark.parametrize('corrupt', ['last_search.json', 'seen.json'])
def test_corrupt_import_aborts_without_partial_state(tmp_path, corrupt):
    (tmp_path / 'last_search.json').write_text(json.dumps(dict(generated_at=NOW.isoformat(), jobs={'1': job().model_dump(mode='json')})))
    (tmp_path / 'seen.json').write_text(json.dumps({'greenhouse:1': NOW.isoformat()}))
    (tmp_path / corrupt).write_text('{broken')
    with pytest.raises(ValueError):
        latest_search(tmp_path)
    engine = initialize_database(database_path(tmp_path))
    try:
        with database_session(engine) as session:
            for model in (JobIdentity, SearchRun, SearchResult):
                assert not session.exec(select(model)).all()
        with pytest.raises(ValueError):
            latest_search(tmp_path)
    finally:
        engine.dispose()


def test_real_cli_writes_db_and_demo_is_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'load_settings', lambda: Settings(data_dir=tmp_path, anthropic_api_key='synthetic'))
    monkeypatch.setattr(cli, 'load_profile', lambda _: SearchProfile(keywords=['Engineer'], sources=[SourceRef(ats='greenhouse', board='token')]))
    monkeypatch.setattr(cli.search, 'run', lambda *a, **kw: search.SearchOutcome(jobs=[job()], boards=['token'], counts=search.StageCounts(), per_source={'greenhouse/token': 1}, baseline_scan=len(kw['seen_cache']) == 0))
    monkeypatch.setattr(cli, 'score_jobs', lambda jobs, *a, **kw: [ScoredJob(job=j) for j in jobs])
    args = Namespace(demo=False, max_age_hours=None, days=30, profile='unused', method='structured', limit=None)
    assert cli.cmd_search(Console(), args) == 0
    assert latest_search(tmp_path)['meta']['new_count'] is None
    assert not (tmp_path / 'last_search.json').exists()
    assert not (tmp_path / 'seen.json').exists()
    before = database_path(tmp_path).read_bytes()
    monkeypatch.setattr(cli, 'load_settings', lambda: pytest.fail('demo loaded production settings'))
    args.demo = True
    assert cli.cmd_search(Console(), args) == 0
    assert database_path(tmp_path).read_bytes() == before


def test_dashboard_ambiguity_and_db_listing(tmp_path):
    from fastapi.testclient import TestClient
    from job_agent.dashboard.app import create_app
    scan(tmp_path, [job(), job(source='lever')])
    client = TestClient(create_app(data_dir=tmp_path, url_opener=lambda _: 'test'))
    assert len(client.get('/api/jobs').json()['jobs']) == 2
    response = client.post('/api/apply/open', json={'job_id': '1'})
    assert response.status_code == 409
    assert 'Ambiguous' in response.json()['detail']
    response = client.post('/api/apply/open', json={'job_id': 'lever:1'})
    assert response.status_code == 200
    assert response.json()['apply_url'] == job(source='lever').apply_url


def test_conflicting_board_rolls_back_native_run(tmp_path):
    scan(tmp_path, [job()])
    before = latest_search(tmp_path)
    with pytest.raises(ValueError, match='Conflicting board'):
        with search_database(tmp_path) as engine, database_session(engine) as session:
            cache = SQLiteSeenCache(session)
            cache.observe('greenhouse', '1', NOW + timedelta(days=1))
            SearchRepository(session).record_search(
                [ScoredJob(job=job())], ['different-board'], cache=cache, baseline=False)
    assert latest_search(tmp_path) == before


def test_real_cli_scoring_failure_rolls_back_seen(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'load_settings', lambda: Settings(data_dir=tmp_path, anthropic_api_key='synthetic'))
    monkeypatch.setattr(cli, 'load_profile', lambda _: SearchProfile(keywords=['Engineer'], sources=[SourceRef(ats='greenhouse', board='token')]))
    def pipeline(*args, seen_cache, **kwargs):
        seen_cache.observe('greenhouse', '1', NOW)
        return search.SearchOutcome(jobs=[job(posted_at=datetime.now(timezone.utc))], boards=['token'], counts=search.StageCounts(), per_source={}, baseline_scan=True)
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic scoring failure')
    monkeypatch.setattr(cli.search, 'run', pipeline)
    monkeypatch.setattr(cli, 'score_jobs', fail)
    args = Namespace(demo=False, max_age_hours=None, days=30, profile='unused', method='structured', limit=None)
    with pytest.raises(RuntimeError, match='scoring failure'):
        cli.cmd_search(Console(), args)
    with search_database(tmp_path) as engine, database_session(engine) as session:
        assert len(SQLiteSeenCache(session)) == 0
        assert SearchRepository(session).latest()['jobs'] == {}


@pytest.mark.parametrize("flags, expected", [
    ([], timedelta(days=14)),
    (["--days", "23"], timedelta(days=23)),
    (["--days", "23", "--max-age-hours", "9"], timedelta(hours=9)),
])
def test_production_cli_effective_window(tmp_path, monkeypatch, flags, expected):
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(
        data_dir=tmp_path, anthropic_api_key="synthetic"))
    monkeypatch.setattr(cli, "load_profile", lambda _: SearchProfile(
        keywords=["Engineer"], sources=[SourceRef(ats="greenhouse", board="token")]))
    windows = []

    def pipeline(*args, **kwargs):
        windows.append(kwargs["fresh_window"])
        return search.SearchOutcome(jobs=[], boards=[], counts=search.StageCounts(),
                                    per_source={}, baseline_scan=True)

    monkeypatch.setattr(cli.search, "run", pipeline)
    args = cli._build_parser().parse_args(["search", *flags])
    assert cli.cmd_search(Console(), args) == 0
    assert windows == [expected]


@pytest.mark.parametrize('relocation,visa', [('supported', True), ('not_supported', False), ('required', None)])
def test_freehire_keyword_board_change_and_mobility_roundtrip(tmp_path, relocation, visa):
    original = job(source='freehire', relocation=relocation, visa_sponsorship=visa)
    scan(tmp_path, [original])
    before = load_job_record(tmp_path, 'freehire:1')
    with search_database(tmp_path) as engine, database_session(engine) as session:
        cache = SQLiteSeenCache(session)
        SearchRepository(session).record_search([ScoredJob(job=original)],
            ['freehire-relocation/"new grad engineer"'], cache=cache, baseline=False)
    after = load_job_record(tmp_path, 'freehire:1')
    assert after['canonical_id'] == before['canonical_id']
    assert after['first_seen'] == before['first_seen']
    assert after['board'] == 'freehire-relocation/"new grad engineer"'
    assert Job.model_validate(after) == original
    with search_database(tmp_path) as engine, database_session(engine) as session:
        assert len(session.exec(select(JobIdentity)).all()) == 1


@pytest.mark.parametrize('sequence', [list, tuple])
def test_complete_assessment_roundtrip(tmp_path, sequence):
    original = job(relocation='supported', visa_sponsorship=None)
    assessment = ScoredJob(job=original, score=78, verdict='possible',
        reasons=sequence(['reason']), matched_requirements=sequence(['Python']),
        missing_requirements=sequence(['required skill unknown']), target_tier='A',
        content_flags=sequence(['prompt_injection_suspected']))
    scan(tmp_path, [original])
    identity = load_job_record(tmp_path, '1')['canonical_id']
    with search_database(tmp_path) as engine, database_session(engine) as session:
        SearchRepository(session).record_search([assessment], ['token'],
            cache=SQLiteSeenCache(session), baseline=False)
    latest = latest_search(tmp_path)['jobs']['greenhouse:1']
    loaded = load_job_record(tmp_path, 'canonical:' + identity)
    assert latest == loaded
    for field, value in assessment.model_dump(mode='json', exclude={'job'}).items():
        assert loaded[field] == value
    assert loaded['canonical_id'] == identity
    assert loaded['relocation'] == 'supported'
    assert loaded['visa_sponsorship'] is None


def test_legacy_assessment_defaults(tmp_path):
    payload = {**job().model_dump(mode='json'), 'score': 70, 'verdict': 'possible', 'reasons': ['old']}
    (tmp_path / 'last_search.json').write_text(json.dumps({'generated_at': NOW.isoformat(), 'jobs': {'1': payload}}))
    record = load_job_record(tmp_path, '1')
    assessment = ScoredJob(job=Job.model_validate(record), **{k: record[k] for k in ('score', 'verdict', 'reasons')})
    assert assessment.matched_requirements == assessment.missing_requirements == assessment.content_flags == ()
    assert assessment.target_tier == 'other'
