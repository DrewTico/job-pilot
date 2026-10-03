"""No network: exact accounting, durable admission, and privacy boundaries."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import sqlite3
import sys

import pytest
from sqlmodel import Session, select

from job_agent.config import Settings
from job_agent.database import LLMCall, initialize_database, database_session, JobRepository
from job_agent.llm import (AnthropicExecutor, LLMBudgetExceeded, UnknownModelPricing,
                           calculate_cost, normalize_usage, month_bounds, budget_state)

MODEL = 'claude-sonnet-5-5'
NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


@pytest.fixture
def engine(tmp_path):
    engine = initialize_database(tmp_path / 'test.sqlite')
    yield engine
    engine.dispose()


class Fake:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = self

    def create(self, **request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def response(**usage):
    return SimpleNamespace(usage=SimpleNamespace(**usage), _request_id='req_test',
                           content=[SimpleNamespace(type='text', text='synthetic')])


def execute(executor, **kwargs):
    return executor.create(task='test', prompt_name='synthetic', prompt_version='v1',
                           model=MODEL, max_tokens=100, messages=[{'role': 'user', 'content': 'private prompt secret'}], **kwargs)


def rows(engine):
    with Session(engine) as session:
        return session.exec(select(LLMCall)).all()


def seed(engine, cost, when=NOW):
    with database_session(engine) as session:
        session.add(LLMCall(created_at=when.replace(tzinfo=None), task='test', model=MODEL,
                            prompt_name='test', prompt_version='v1', status='succeeded',
                            estimated_cost_usd=str(cost)))


def test_exact_pricing():
    usage = dict(input_tokens=1000, output_tokens=2000, cache_read_input_tokens=3000,
                 cache_creation_input_tokens=4000)
    assert calculate_cost(MODEL, {'input_tokens': 1000, 'output_tokens': 2000}) == Decimal('.022')
    assert calculate_cost(MODEL, usage) == Decimal('.0326')
    assert calculate_cost(MODEL, usage, 'batch') == Decimal('.0163')
    with pytest.raises(UnknownModelPricing):
        calculate_cost('unknown', usage)
    with pytest.raises(ValueError):
        calculate_cost(MODEL, usage, 'invalid')


def test_normalize():
    assert normalize_usage(response(input_tokens=123, output_tokens=45)) == dict(
        input_tokens=123, output_tokens=45, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    assert normalize_usage(SimpleNamespace()) == dict.fromkeys(
        ['input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'], 0)
    assert normalize_usage(SimpleNamespace(usage={'input_tokens': 1}))['input_tokens'] == 1


def test_success_accumulation_and_cache(engine):
    fake = Fake(response(input_tokens=1000, output_tokens=2000, cache_creation_input_tokens=4000,
                         cache_read_input_tokens=3000), response(input_tokens=1000, output_tokens=2000))
    executor = AnthropicExecutor(fake, Settings(), engine=engine, clock=lambda: NOW)
    execute(executor, external_job_reference='demo:1')
    execute(executor)
    assert executor.state().spend == Decimal('.0546')
    row = rows(engine)[0]
    assert (row.task, row.model, row.prompt_name, row.prompt_version, row.status) == ('test', MODEL, 'synthetic', 'v1', 'succeeded')
    assert (row.input_tokens, row.output_tokens, row.cache_creation_input_tokens, row.cache_read_input_tokens) == (1000, 2000, 4000, 3000)
    assert row.latency_ms >= 0
    assert row.provider_request_id == 'req_test'
    assert row.external_job_reference == 'demo:1'
    assert row.reserved_cost_usd == '0'
    assert 'private prompt secret' not in row.model_dump_json()


def test_failure_sanitized(engine):
    fake = Fake(RuntimeError('API_KEY OAuth_token private resume'))
    executor = AnthropicExecutor(fake, Settings(), engine=engine, clock=lambda: NOW)
    with pytest.raises(RuntimeError):
        execute(executor)
    row = rows(engine)[0]
    assert row.status == 'failed'
    assert row.input_tokens == row.output_tokens == 0
    assert row.estimated_cost_usd == '0'
    assert row.error_type == 'provider_error'
    for secret in ('API_KEY', 'OAuth_token', 'private resume', 'private prompt secret'):
        assert secret not in row.model_dump_json()


@pytest.mark.parametrize('spend,warning,paused', [('31.99', False, False), ('32', True, False), ('39', True, False), ('40', True, True), ('41', True, True)])
def test_budget_boundaries(engine, spend, warning, paused):
    seed(engine, spend)
    fake = Fake(response(input_tokens=1))
    executor = AnthropicExecutor(fake, Settings(), engine=engine, clock=lambda: NOW)
    assert executor.state().warning == warning
    assert executor.state().paused == paused
    if paused:
        with pytest.raises(LLMBudgetExceeded):
            execute(executor)
        assert fake.requests == []
        assert len(rows(engine)) == 1
    else:
        execute(executor)
        assert len(fake.requests) == 1


def test_reservation_blocks_concurrent_admission(engine):
    seed(engine, '39.99')
    executor = AnthropicExecutor(Fake(), Settings(), engine=engine, clock=lambda: NOW)
    with pytest.raises(LLMBudgetExceeded):
        execute(executor)
    with database_session(engine) as session:
        session.add(LLMCall(created_at=NOW.replace(tzinfo=None), task='test', model=MODEL,
                            prompt_name='test', prompt_version='v1', reserved_cost_usd='40'))
    assert executor.state().paused


def test_month_rollover(engine):
    seed(engine, '40', datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc))
    seed(engine, '40', datetime(2026, 11, 1, tzinfo=timezone.utc))
    executor = AnthropicExecutor(Fake(response()), Settings(), engine=engine, clock=lambda: NOW)
    assert executor.state().spend == 0
    execute(executor)
    assert month_bounds(datetime(2026, 12, 31, tzinfo=timezone.utc)) == (datetime(2026, 12, 1), datetime(2027, 1, 1))


def test_unknown_price_before_network(engine):
    fake = Fake()
    executor = AnthropicExecutor(fake, Settings(), engine=engine)
    with pytest.raises(UnknownModelPricing):
        executor.create(task='classification', prompt_name='test', prompt_version='v1',
                        model='unknown-model', max_tokens=1, messages=[])
    assert not fake.requests
    assert rows(engine) == []


def test_malformed_attempt_counted_retry_budget_checked(engine):
    from job_agent.scoring import score_one
    from test_scoring import JOB, PROFILE, VALID
    first = response(output_tokens=100000)  # deliberately consumes $1 in fake usage
    second = response(output_tokens=1)
    second.content[0].text = VALID
    executor = AnthropicExecutor(Fake(first, second), Settings(monthly_budget_usd='1'), engine=engine, clock=lambda: NOW)
    with pytest.raises(LLMBudgetExceeded):
        score_one(executor, MODEL, JOB, PROFILE)
    assert len(executor.client.requests) == 1
    assert Decimal(rows(engine)[0].estimated_cost_usd) == Decimal('1')
    assert rows(engine)[0].status == 'succeeded'


def test_logging_independent_of_unrelated_rollback(engine):
    executor = AnthropicExecutor(Fake(response(input_tokens=1)), Settings(), engine=engine)
    with pytest.raises(RuntimeError):
        with database_session(engine) as session:
            execute(executor)
            JobRepository(session).create_job(company='Synthetic', title='Test', location='Remote', posting_url='url')
            raise RuntimeError('rollback search')
    assert len(rows(engine)) == 1
    from job_agent.database import CanonicalJob
    with Session(engine) as session:
        assert session.exec(select(CanonicalJob)).all() == []


def test_v3_upgrade_preserves_all_tables(tmp_path):
    from test_application_import import make_v2
    path = tmp_path / 'v3.sqlite'
    make_v2(path)
    engine = initialize_database(path)
    with engine.begin() as connection:
        connection.exec_driver_sql('DROP TABLE llm_calls')
        connection.exec_driver_sql('PRAGMA user_version = 3')
        connection.exec_driver_sql("INSERT INTO application_events (id, external_job_id, source, company, title, attempt_id, status, status_kind, reason, notes, follow_up, occurred_at, provenance, payload) VALUES ('event', '123', 'lever', 'Synthetic', 'Engineer', 'attempt', 'submitted', 'submission', '', '', '', '2026-01-01', 'test', '{}')")
    engine.dispose()
    tables = ('jobs', 'job_identities', 'search_runs', 'search_results', 'application_events')
    with sqlite3.connect(path) as connection:
        before = {t: connection.execute(f'SELECT * FROM {t}').fetchall() for t in tables}
    engine = initialize_database(path)
    engine.dispose()
    with sqlite3.connect(path) as connection:
        from job_agent.database import SCHEMA_VERSION
        assert connection.execute('PRAGMA user_version').fetchone() == (SCHEMA_VERSION,)
        for table in tables:
            assert connection.execute(f'SELECT * FROM {table}').fetchall() == before[table]
        assert connection.execute('SELECT * FROM llm_calls').fetchall() == []
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []


def test_screening_writing_route(engine, monkeypatch):
    from job_agent.apply.screening import make_llm_generate, DRAFT_SYSTEM
    import job_agent.llm as llm
    fake = Fake(response())
    created = []
    def client(**kwargs):
        created.append(kwargs)
        return fake
    monkeypatch.setitem(sys.modules, 'anthropic', SimpleNamespace(Anthropic=client))
    original = llm.AnthropicExecutor.__init__
    monkeypatch.setattr(llm.AnthropicExecutor, '__init__', lambda self, c, s: original(self, c, s, engine=engine))
    generate = make_llm_generate(Settings())
    assert generate('private question') == 'synthetic'
    assert fake.requests[0]['model'] == MODEL
    assert fake.requests[0]['system'] == [{'type': 'text', 'text': DRAFT_SYSTEM, 'cache_control': {'type': 'ephemeral'}}]
    assert created[0]['max_retries'] == 0
    assert rows(engine)[0].task == 'writing'


def test_sdk_cache_request_shape():
    from anthropic.types import TextBlockParam, CacheControlEphemeralParam
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    assert 'cache_control' in TextBlockParam.__annotations__
    assert 'type' in CacheControlEphemeralParam.__annotations__
    assert 'system' in MessageCreateParamsNonStreaming.__annotations__
    assert 'output_config' in MessageCreateParamsNonStreaming.__annotations__


def test_deferred_search_cache_never_commits_partial_observations(engine):
    from job_agent.search_state import SQLiteSeenCache
    from job_agent.database import JobIdentity
    with database_session(engine) as session:
        cache = SQLiteSeenCache(session, defer_writes=True)
        assert cache.first_seen('demo', '1', NOW) == (NOW, True)
        assert cache.first_seen('demo', '1', NOW) == (NOW, False)
        assert len(cache) == 1
        assert session.exec(select(JobIdentity)).all() == []
    with Session(engine) as session:
        assert session.exec(select(JobIdentity)).all() == []


def test_cli_paid_log_survives_budget_failure_without_partial_search(tmp_path, monkeypatch):
    from argparse import Namespace
    from rich.console import Console
    from job_agent import cli, search
    from job_agent.scoring import score_jobs
    from job_agent.database import JobIdentity, SearchRun
    from test_scoring import JOB, PROFILE
    settings = Settings(anthropic_api_key='synthetic', data_dir=tmp_path)
    monkeypatch.setattr(cli, 'load_settings', lambda: settings)
    monkeypatch.setattr(cli, 'load_profile', lambda _: PROFILE)
    def pipeline(*args, seen_cache, **kwargs):
        seen_cache.observe(JOB.source, JOB.id, NOW)
        return search.SearchOutcome(jobs=[
            JOB.model_copy(update={"posted_at": datetime.now(timezone.utc)}),
            JOB.model_copy(update={"id": "budget-blocked", "posted_at": datetime.now(timezone.utc)})
        ], boards=['token', 'token'], counts=search.StageCounts(),
                                    per_source={}, baseline_scan=True)
    first = response(output_tokens=4000000)  # simulate exhaustion on a returned attempt
    fake = Fake(first)
    monkeypatch.setattr(cli.search, 'run', pipeline)
    monkeypatch.setattr(cli, 'score_jobs', lambda jobs, settings, profile, **kwargs:
                        score_jobs(jobs, settings, profile, client=fake, **kwargs))
    args = Namespace(demo=False, max_age_hours=None, days=30, profile='unused', method='structured', limit=None)
    with pytest.raises(LLMBudgetExceeded):
        cli.cmd_search(Console(), args)
    engine = initialize_database(tmp_path / 'job_pilot.sqlite3')
    with Session(engine) as session:
        assert session.exec(select(JobIdentity)).all() == []
        assert session.exec(select(SearchRun)).all() == []
        logs = session.exec(select(LLMCall)).all()
        assert len(logs) == 1
        assert Decimal(logs[0].estimated_cost_usd) == Decimal('40')
    assert len(fake.requests) == 1
    engine.dispose()


@pytest.mark.parametrize('model,rates', [
    (MODEL, ('2', '10', '2.50', '.20')),
    ('claude-haiku-4-5-20251001', ('1', '5', '1.25', '.10')),
])
@pytest.mark.parametrize('field,index', [
    ('input_tokens', 0), ('output_tokens', 1),
    ('cache_creation_input_tokens', 2), ('cache_read_input_tokens', 3),
])
def test_exact_category_prices_and_batch_stacking(model, rates, field, index):
    normal = Decimal(rates[index])
    usage = {field: 1000000}
    assert calculate_cost(model, usage) == normal
    assert calculate_cost(model, usage, 'batch') == normal / 2


def test_haiku_mixed_batch_price():
    usage = dict(input_tokens=1000, output_tokens=2000,
                 cache_creation_input_tokens=4000, cache_read_input_tokens=3000)
    assert calculate_cost('claude-haiku-4-5-20251001', usage) == Decimal('.0163')
    assert calculate_cost('claude-haiku-4-5-20251001', usage, 'batch') == Decimal('.00815')


def reservation(engine, *, age=None, kind='standard', reserved='10', estimated='0'):
    from datetime import timedelta
    when = NOW - (age if age is not None else timedelta())
    with database_session(engine) as session:
        row = LLMCall(created_at=when.replace(tzinfo=None), task='test', model=MODEL,
                      prompt_name='test', prompt_version='v1', request_kind=kind,
                      reserved_cost_usd=reserved, estimated_cost_usd=estimated,
                      operational_metadata={'safe_reference': 'synthetic'})
        session.add(row)
        session.flush()
        return row.id


def reconcile(engine):
    from job_agent.llm import reconcile_stale_standard_reservations
    with Session(engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        count = reconcile_stale_standard_reservations(session, NOW)
        session.commit()
        return count


def test_fresh_standard_reservation_remains_reserved(engine):
    from datetime import timedelta
    from job_agent.llm import STALE_STANDARD_RESERVATION_AFTER
    reservation(engine, age=STALE_STANDARD_RESERVATION_AFTER - timedelta(microseconds=1))
    assert reconcile(engine) == 0
    row = rows(engine)[0]
    assert row.status == 'reserved'
    assert row.reserved_cost_usd == '10'
    assert row.estimated_cost_usd == '0'


@pytest.mark.parametrize('existing,charged', [('0', '10'), ('10', '10'), ('12', '12')])
def test_stale_standard_reservation_conservatively_finalized(engine, existing, charged):
    from job_agent.llm import STALE_STANDARD_RESERVATION_AFTER
    reservation(engine, age=STALE_STANDARD_RESERVATION_AFTER, estimated=existing)
    assert reconcile(engine) == 1
    row = rows(engine)[0]
    assert row.status == 'failed'
    assert row.reserved_cost_usd == '0'
    assert Decimal(row.estimated_cost_usd) == Decimal(charged)
    assert row.error_type == 'stale_reservation_reconciled'
    assert row.error_message == 'Stale synchronous reservation conservatively charged; usage unknown'
    assert row.operational_metadata == {'safe_reference': 'synthetic', 'stale_reservation_reconciled': True}
    assert row.input_tokens == row.output_tokens == 0
    with Session(engine) as session:
        state = budget_state(session, Decimal('40'), NOW)
        assert state.spend == Decimal(charged)
        assert state.reserved == 0
    before = row.model_dump()
    assert reconcile(engine) == 0
    assert rows(engine)[0].model_dump() == before


def test_stale_batch_reservation_remains_outstanding(engine):
    from datetime import timedelta
    reservation(engine, age=timedelta(days=1), kind='batch')
    assert reconcile(engine) == 0
    row = rows(engine)[0]
    assert row.status == 'reserved'
    assert row.reserved_cost_usd == '10'
    assert row.operational_metadata == {'safe_reference': 'synthetic'}


def test_reconciliation_before_admission_recovers_double_counted_exposure(engine):
    from job_agent.llm import STALE_STANDARD_RESERVATION_AFTER
    # Partially recorded cost plus its reservation previously blocked the cap.
    reservation(engine, age=STALE_STANDARD_RESERVATION_AFTER, reserved='25', estimated='25')
    executor = AnthropicExecutor(Fake(response(input_tokens=1)), Settings(), engine=engine, clock=lambda: NOW)
    assert executor.state().paused
    execute(executor)
    assert len(executor.client.requests) == 1
    assert executor.state().spend == Decimal('25.000002')
    assert executor.state().reserved == 0


def test_denied_admission_retains_reconciliation_and_charge(engine):
    from job_agent.llm import STALE_STANDARD_RESERVATION_AFTER
    reservation(engine, age=STALE_STANDARD_RESERVATION_AFTER, reserved='40')
    executor = AnthropicExecutor(Fake(), Settings(), engine=engine, clock=lambda: NOW)
    with pytest.raises(LLMBudgetExceeded):
        execute(executor)
    assert rows(engine)[0].status == 'failed'
    assert executor.state().spend == 40
    assert executor.state().reserved == 0
    assert executor.client.requests == []


@pytest.mark.parametrize('actual', ['1', '15', None])
def test_late_finish_never_reduces_reconciled_cost(engine, actual):
    from job_agent.llm import STALE_STANDARD_RESERVATION_AFTER
    from time import perf_counter
    row_id = reservation(engine, age=STALE_STANDARD_RESERVATION_AFTER)
    assert reconcile(engine) == 1
    executor = AnthropicExecutor(Fake(), Settings(), engine=engine, clock=lambda: NOW)
    values = {'status': 'failed' if actual is None else 'succeeded',
              'operational_metadata': {'usage_available': actual is not None}}
    if actual is not None:
        values['estimated_cost_usd'] = actual
    executor._finish(row_id, perf_counter(), **values)
    row = rows(engine)[0]
    assert Decimal(row.estimated_cost_usd) == max(Decimal('10'), Decimal(actual or '0'))
    assert row.operational_metadata['safe_reference'] == 'synthetic'
    assert row.operational_metadata['stale_reservation_reconciled'] is True


@pytest.mark.parametrize('spend,reserved,warning,paused', [
    ('20', '12', True, False), ('20', '11.99', False, False),
    ('20', '20', True, True), ('20', '21', True, True),
])
def test_budget_warning_uses_committed_exposure(engine, spend, reserved, warning, paused):
    seed(engine, spend)
    reservation(engine, reserved=reserved)
    executor = AnthropicExecutor(Fake(), Settings(), engine=engine, clock=lambda: NOW)
    state = executor.state()
    assert state.warning is warning
    assert state.paused is paused
    if paused:
        with pytest.raises(LLMBudgetExceeded):
            execute(executor)
        assert executor.client.requests == []


def test_concurrent_reconciliation_is_serialized(engine):
    from concurrent.futures import ThreadPoolExecutor
    from job_agent.llm import STALE_STANDARD_RESERVATION_AFTER
    reservation(engine, age=STALE_STANDARD_RESERVATION_AFTER)
    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _: reconcile(engine), range(2)))
    assert sorted(counts) == [0, 1]
    assert Decimal(rows(engine)[0].estimated_cost_usd) == 10
    assert rows(engine)[0].reserved_cost_usd == '0'
