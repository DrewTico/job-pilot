"""Offline operational tests using synthetic SQLite and providers."""
from datetime import datetime, timezone
from decimal import Decimal
import multiprocessing
import threading
from types import SimpleNamespace as NS

import pytest
from sqlmodel import Session, select
from job_agent.scheduler import (TIMEZONE, Operations, build_scheduler, scheduler_lock,
                                 scheduled_discovery)
from job_agent.ops import status, local_status, STATES
from job_agent.database import ScoringWorkItem, LLMCall, LLMBatch
from test_batch import setup, queue, NOW, PROFILE


def test_schedules_and_configuration():
    scheduler = build_scheduler(Operations(lambda: 0, None))
    assert scheduler.timezone.key == "America/New_York"
    expected = {"morning": (6,30,"mon-fri"), "midday": (13,0,"mon-fri"),
                "batch": (23,0,"*"), "maintenance": ("*",10,"*")}
    for job in scheduler.get_jobs():
        fields = {f.name: str(f) for f in job.trigger.fields}
        hour, minute, days = expected[job.id]
        assert (fields['hour'], fields['minute'], fields['day_of_week']) == (str(hour),str(minute),days)
        assert job.trigger.timezone.key == TIMEZONE.key
        assert job.max_instances == 1 and job.coalesce and job.misfire_grace_time == 900
    assert expected['batch'][1] != expected['maintenance'][1]


@pytest.mark.parametrize('month,day,offset', [(3,6,-5),(3,9,-4),(10,30,-4),(11,2,-5)])
def test_dst(month, day, offset):
    job = build_scheduler(Operations(None,None)).get_job('morning')
    now = datetime(2026,month,day,0,tzinfo=TIMEZONE)
    fire = job.trigger.get_next_fire_time(None, now)
    assert (fire.hour,fire.minute,fire.weekday()) == (6,30,now.weekday())
    assert fire.utcoffset().total_seconds() == offset*3600


def _try_lock(directory, result):
    try:
        with scheduler_lock(directory):
            result.put('acquired')
    except RuntimeError:
        result.put('refused')


def test_process_lock(tmp_path):
    ctx = multiprocessing.get_context('spawn')
    result = ctx.Queue()
    with scheduler_lock(tmp_path):
        child = ctx.Process(target=_try_lock,args=(tmp_path,result))
        child.start()
        assert result.get(timeout=10) == 'refused'
        child.join(10)
        assert child.exitcode == 0
    with scheduler_lock(tmp_path):
        pass


def test_discovery_uses_cli(monkeypatch,tmp_path):
    import job_agent.cli as cli
    seen = []
    monkeypatch.setattr(cli,'cmd_search',lambda console,args: seen.append(args) or 0)
    assert scheduled_discovery('synthetic.yaml',tmp_path) == 0
    assert seen[0].profile == 'synthetic.yaml'
    assert seen[0].data_dir == tmp_path
    assert seen[0].method == 'structured' and seen[0].days == 14 and not seen[0].demo


def test_empty_nightly_no_provider(setup):
    _, provider, service = setup
    service.provider = lambda: pytest.fail('no provider expected')
    assert Operations(None,service).run('batch')
    assert not provider.calls


@pytest.mark.parametrize('once', [False, True], ids=['scheduled', 'once-batch'])
def test_batch_waits_for_maintenance_and_submits_once(setup, monkeypatch, once):
    from contextlib import nullcontext
    import job_agent.scheduler as scheduling
    import job_agent.batch as batch
    import job_agent.config as config
    import job_agent.search_state as state

    engine, provider, service = setup
    queue(engine)
    maintenance_entered = threading.Event()
    release_maintenance = threading.Event()
    batch_acquiring = threading.Event()
    calls, results = [], {}
    maintain, submit = service.maintain, service.submit

    def tracked_maintain():
        calls.append('maintain')
        if threading.current_thread().name == 'maintenance':
            maintenance_entered.set()
            assert release_maintenance.wait(10)
        return maintain()

    def tracked_submit():
        calls.append('submit')
        return submit()

    class ObservedLock:
        def __init__(self):
            self.lock = threading.Lock()

        def acquire(self, blocking=True):
            if threading.current_thread().name == 'nightly':
                batch_acquiring.set()
            return self.lock.acquire(blocking=blocking)

        def release(self):
            self.lock.release()

    monkeypatch.setattr(service, 'maintain', tracked_maintain)
    monkeypatch.setattr(service, 'submit', tracked_submit)
    operations = Operations(None, service)
    operations.batch_lock = ObservedLock()
    if once:
        monkeypatch.setattr(state, 'search_database', lambda *_: nullcontext(engine))
        monkeypatch.setattr(batch, 'BatchService', lambda *_: service)
        monkeypatch.setattr(config, 'load_profile', lambda *_: PROFILE)
        monkeypatch.setattr(scheduling, 'Operations', lambda *_: operations)

    def run_batch():
        results['batch'] = (scheduling.run_scheduler(service.settings, 'synthetic.yaml', once='batch')
                            if once else operations.run('batch'))

    maintenance = threading.Thread(target=lambda: results.update(maintenance=operations.run('maintenance')),
                                   name='maintenance')
    nightly = threading.Thread(target=run_batch, name='nightly')
    maintenance.start()
    try:
        assert maintenance_entered.wait(10)
        nightly.start()
        assert batch_acquiring.wait(10)
        nightly.join(0.1)
        assert nightly.is_alive()
        assert calls == ['maintain'] and not provider.calls
    finally:
        release_maintenance.set()
        maintenance.join(10)
        if nightly.ident is not None:
            nightly.join(10)
    assert not maintenance.is_alive() and not nightly.is_alive()
    assert results == {'maintenance': True, 'batch': 0 if once else True}
    assert calls == ['maintain', 'maintain', 'submit']
    assert len(provider.calls) == 1
    assert operations.run('batch')
    assert len(provider.calls) == 1


def test_maintenance_skips_batch_overlap_and_never_submits(setup, monkeypatch):
    _, _, service = setup
    monkeypatch.setattr(service, 'submit', lambda: pytest.fail('maintenance cannot submit'))
    operations = Operations(None, service)
    with operations.batch_lock:
        assert operations.run('maintenance') is False
    assert operations.run('maintenance') is True


@pytest.mark.parametrize('state',['standard_in_progress','retryable','failed','submission_unknown'])
def test_nightly_excludes_recovery(setup,state):
    engine,_,service = setup
    wid = queue(engine)
    with Session(engine) as session:
        work = session.get(ScoringWorkItem,wid)
        work.state = state
        session.add(work); session.commit()
    service.provider = lambda: pytest.fail('no provider expected')
    assert Operations(None,service).run('batch')
    with Session(engine) as session:
        assert session.get(ScoringWorkItem,wid).state == state


def test_maintenance_reconciles_without_create(setup):
    engine,provider,service = setup
    queue(engine)
    service.submit()
    provider.create = lambda **kw: pytest.fail('maintenance cannot create')
    provider.processing_status = 'ended'
    with Session(engine) as session:
        work = session.exec(select(ScoringWorkItem)).one()
        provider.entries = [NS(custom_id=work.custom_id,result=NS(type='expired'))]
    assert service.maintain() == {'reconciled':1}
    service.provider = lambda: pytest.fail('fully reconciled batch must not be polled')
    assert service.maintain() == {'reconciled':0}


def test_maintenance_unknown_no_poll(setup):
    engine,_,service = setup
    with Session(engine) as session:
        session.add(LLMBatch(status='submission_unknown'))
        session.commit()
    service.provider = lambda: pytest.fail('unknown must not be polled')
    assert service.maintain()['reconciled'] == 0


def test_ops_all_states_budget_readonly(setup,tmp_path,monkeypatch):
    engine,_,service = setup
    with Session(engine) as session:
        for i,state in enumerate(STATES):
            session.add(ScoringWorkItem(fingerprint=str(i),source='demo',external_id=str(i),
                        model='claude-sonnet-5-5',candidate_hash='hash',priority_at=NOW,state=state))
        session.add(LLMCall(created_at=NOW,task='scoring',model='claude-sonnet-5-5',prompt_name='score',prompt_version='v1',
                            estimated_cost_usd='32',reserved_cost_usd='8'))
        session.add(LLMBatch(provider_id='known',status='in_progress'))
        session.add(LLMBatch(id='ended',provider_id='ended-provider',status='ended'))
        session.add(LLMCall(created_at=NOW,task='scoring',model='claude-sonnet-5-5',prompt_name='score',prompt_version='v1',
                           operational_metadata={'batch_id':'ended'}))
        session.commit()
    service.provider = lambda: pytest.fail('ops cannot call provider')
    report = status(engine,service.settings,now=NOW)
    assert report['scoring'] == dict.fromkeys(STATES,1)
    assert report['operator_review'] == {'submission_unknown':1,'standard_in_progress':1}
    assert report['provider_batches_in_progress'] == 1
    assert report['provider_batches_ended_unreconciled'] == 1
    assert Decimal(report['monthly_spend']) == 32
    assert Decimal(report['reserved_exposure']) == 8
    assert report['warning'] and report['paused']
    engine.dispose()
    (tmp_path/'test.sqlite').rename(tmp_path/'job_pilot.sqlite3')
    before = (tmp_path/'job_pilot.sqlite3').read_bytes()
    assert local_status(service.settings)['scoring'] == report['scoring']
    assert (tmp_path/'job_pilot.sqlite3').read_bytes() == before


def test_overlap_and_redacted_logs(caplog):
    def fail():
        raise RuntimeError('API_KEY private candidate provider body')
    operations = Operations(fail,None)
    with caplog.at_level('INFO'):
        assert not operations.run('morning')
        operations.search_lock.acquire()
        try:
            assert not operations.run('midday')
        finally:
            operations.search_lock.release()
    assert 'failed' in caplog.text and 'overlap' in caplog.text
    for secret in ('API_KEY','private candidate','provider body'):
        assert secret not in caplog.text


@pytest.mark.parametrize('spend,reserved,warning,paused', [('10','1',False,False),('30','2',True,False)])
def test_ops_budget_flags(setup,spend,reserved,warning,paused):
    engine,_,service = setup
    with Session(engine) as session:
        session.add(LLMCall(created_at=NOW,task='scoring',model='claude-sonnet-5-5',
                           prompt_name='score',prompt_version='v1',estimated_cost_usd=spend,
                           reserved_cost_usd=reserved))
        # Prior-month spend is excluded; outstanding reservations stay included.
        session.add(LLMCall(created_at=datetime(2026,9,1,tzinfo=timezone.utc),task='scoring',
                           model='claude-sonnet-5-5',prompt_name='score',prompt_version='v1',
                           status='succeeded',estimated_cost_usd='100'))
        session.commit()
    report = status(engine,service.settings,now=NOW)
    assert Decimal(report['monthly_spend']) == Decimal(spend)
    assert report['warning'] is warning and report['paused'] is paused


def test_cli_ops_offline(setup,tmp_path,monkeypatch):
    import anthropic
    import job_agent.cli as cli
    from rich.console import Console
    from io import StringIO
    engine,_,service = setup
    engine.dispose()
    (tmp_path/'test.sqlite').rename(tmp_path/'job_pilot.sqlite3')
    monkeypatch.setattr(cli,'load_settings',lambda: service.settings)
    monkeypatch.setattr(anthropic,'Anthropic',lambda **kw: pytest.fail('no provider construction'))
    output = StringIO()
    args = cli._build_parser().parse_args(['ops','status','--data-dir',str(tmp_path)])
    assert cli.cmd_ops(Console(file=output,width=120),args) == 0
    assert 'submission_unknown' in output.getvalue() and 'standard_in_progress' in output.getvalue()


def test_locked_scheduler_never_initializes_services(tmp_path,monkeypatch):
    from job_agent.scheduler import run_scheduler
    from job_agent.config import Settings
    import job_agent.search_state as state
    monkeypatch.setattr(state,'search_database',lambda *_: pytest.fail('lock must precede services'))
    with scheduler_lock(tmp_path):
        with pytest.raises(RuntimeError,match='Another scheduler'):
            run_scheduler(Settings(data_dir=tmp_path),'unused',once='maintenance')
