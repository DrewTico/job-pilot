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


# Run 3 D: real durable Run 2 services, fake provider and outbound traps.
from test_revisions import revision_setup, packet_setup, offline_only, REVISION_CRASH_PHASES
from job_agent.scheduler import RevisionOperations, build_revision_scheduler, run_revision_scheduler
from job_agent.database import PacketDecision, PacketRevisionWork, ApplicationPacket


def test_revision_schedule_registers_only_coalesced_ten_second_scan():
    scheduler = build_revision_scheduler(NS(run=lambda: True))
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1 and jobs[0].id == "revisions"
    assert jobs[0].trigger.interval.total_seconds() == 10
    assert jobs[0].max_instances == 1 and jobs[0].coalesce


def _try_revision_lock(directory, result):
    try:
        with scheduler_lock(directory, revisions_only=True):
            result.put("acquired")
    except RuntimeError:
        result.put("refused")


def test_revision_worker_process_lock_coexists_with_normal_scheduler(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    with scheduler_lock(tmp_path):
        with scheduler_lock(tmp_path, revisions_only=True):
            result = ctx.Queue()
            child = ctx.Process(target=_try_revision_lock, args=(tmp_path, result))
            child.start()
            assert result.get(timeout=10) == "refused"
            child.join(10)
            assert child.exitcode == 0
    with scheduler_lock(tmp_path, revisions_only=True):
        pass


def test_revision_cli_mode_dispatch_and_incompatible_once(monkeypatch, tmp_path):
    import job_agent.cli as cli
    import job_agent.scheduler as scheduling
    from rich.console import Console
    from io import StringIO
    seen = []
    monkeypatch.setattr(scheduling, "run_revision_scheduler", lambda settings: seen.append(settings.data_dir) or 0)
    monkeypatch.setattr(scheduling, "run_scheduler", lambda *args, **kwargs: pytest.fail("normal scheduler invoked"))
    args = cli._build_parser().parse_args(["scheduler", "--revisions-only", "--data-dir", str(tmp_path)])
    assert cli.cmd_scheduler(Console(file=StringIO()), args) == 0 and seen == [tmp_path]
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args(["scheduler", "--revisions-only", "--once", "batch"])


def test_revision_worker_startup_scan_before_interval_and_no_unrelated_services(revision_setup, monkeypatch):
    import job_agent.scheduler as scheduling
    import job_agent.revisions as revisions
    import job_agent.batch as batch
    import job_agent.search_state as search
    import job_agent.dashboard.approval_app as app
    processor, service, calls, directory, source, decision = revision_setup
    import sqlite3
    with sqlite3.connect(directory / "test.sqlite") as origin:
        with sqlite3.connect(directory / "job_pilot.sqlite3") as destination:
            origin.backup(destination)
    service.engine.dispose()
    service.engine = app._existing_engine(service.settings)
    processor.engine = service.engine
    events = []
    original = processor.process_revision
    processor.process_revision = lambda key: events.append("scan") or original(key)
    monkeypatch.setattr(revisions, "RevisionProcessor", lambda *args: processor)
    def forbidden(*args, **kwargs): pytest.fail("unrelated service started")
    monkeypatch.setattr(batch, "BatchService", forbidden)
    monkeypatch.setattr(search, "search_database", forbidden)
    monkeypatch.setattr(scheduling, "scheduled_discovery", forbidden)
    monkeypatch.setattr(scheduling, "build_revision_scheduler", lambda ops: NS(
        running=False, start=lambda: events.append("interval")))
    assert run_revision_scheduler(service.settings) == 0
    assert events == ["scan", "interval"] and len(calls) == 4
    assert RevisionOperations(service.engine, processor).run()
    assert events == ["scan", "interval"]  # Succeeded work is excluded.
    with Session(service.engine) as session:
        work = session.get(PacketRevisionWork, decision.id)
        assert work.state == "succeeded"
        assert session.exec(select(PacketDecision).where(PacketDecision.packet_id == work.successor_packet_id)).first() is None
        assert session.connection().exec_driver_sql("PRAGMA user_version").scalar() == 9


@pytest.mark.parametrize("phase", REVISION_CRASH_PHASES)
def test_revision_worker_crash_restart_discovers_durable_checkpoint(revision_setup, phase):
    from job_agent.revisions import RevisionProcessor
    processor, service, calls, directory, source, decision = revision_setup
    def crash(name):
        if name == phase: raise SystemExit("test-only crash")
    processor._boundary = crash
    with pytest.raises(SystemExit): RevisionOperations(service.engine, processor).run()
    restarted = RevisionProcessor(service.engine, service.settings, executor=service.executor, clock=processor.clock)
    assert RevisionOperations(service.engine, restarted).run()
    with Session(service.engine) as session:
        work = session.get(PacketRevisionWork, decision.id)
        assert work.state == "succeeded", work.failure_code
        assert len(session.exec(select(ApplicationPacket)).all()) == 2
    assert len(calls) == 4
    assert RevisionOperations(service.engine, restarted).run() and len(calls) == 4


def test_revision_worker_ambiguous_provider_outcome_excluded_after_restart(revision_setup):
    from job_agent.revisions import RevisionProcessor
    processor, service, calls, directory, source, decision = revision_setup
    attempted = []
    def unknown(**request):
        attempted.append(request["task"])
        raise RuntimeError("PRIVATE provider outcome")
    processor.executor = NS(create=unknown)
    assert RevisionOperations(service.engine, processor).run()
    with Session(service.engine) as session:
        work = session.get(PacketRevisionWork, decision.id)
        assert work.state == "recovery_required"
    restart = RevisionProcessor(service.engine, service.settings, executor=processor.executor, clock=processor.clock)
    assert RevisionOperations(service.engine, restart).run()
    assert attempted == ["tailor_resume"] and len(calls) == 2


def test_revision_worker_blocked_excluded_and_status_available(revision_setup):
    from job_agent.dashboard.approval_service import ApprovalQueueService
    processor, service, calls, directory, source, decision = revision_setup
    with Session(service.engine) as session:
        session.add(PacketRevisionWork(decision_id=decision.id, state="blocked", failure_code="budget_blocked"))
        session.commit()
    processor.process_revision = lambda key: pytest.fail("blocked retry")
    assert RevisionOperations(service.engine, processor).run() and len(calls) == 2
    status = ApprovalQueueService(service.engine, service.settings).revision_status(source.id)
    assert status.state == "blocked" and status.label == "Revision needs attention"


def test_revision_worker_order_sequential_overlap_and_sanitized_failure(revision_setup, caplog):
    from test_packets import add_job
    from job_agent.approvals import ApprovalService
    processor, service, calls, directory, source, decision = revision_setup
    other = service.build_one(add_job(service, "other"))
    second = ApprovalService(service.engine, service.settings).revise(other.id, other.fingerprint, "PRIVATE feedback")
    seen = []
    def fail(key):
        seen.append(key)
        raise RuntimeError("PRIVATE exception /absolute/path")
    operations = RevisionOperations(service.engine, NS(process_revision=fail))
    with Session(service.engine) as session:
        expected = session.exec(select(PacketDecision.id).order_by(PacketDecision.created_at, PacketDecision.id)).all()
    assert operations.run() and seen == expected
    assert "PRIVATE" not in caplog.text and "/absolute/path" not in caplog.text
    operations.scan_lock.acquire()
    try: assert operations.run() is False
    finally: operations.scan_lock.release()
    assert seen == expected


def test_duplicate_revision_launcher_never_opens_storage(tmp_path, monkeypatch):
    from job_agent.config import Settings
    import job_agent.dashboard.approval_app as app
    monkeypatch.setattr(app, "_existing_engine", lambda settings: pytest.fail("storage opened"))
    with scheduler_lock(tmp_path, revisions_only=True):
        with pytest.raises(RuntimeError, match="Another scheduler"):
            run_revision_scheduler(Settings(data_dir=tmp_path))



def test_revision_duplicate_scan_converges_under_domain_lock(revision_setup):
    from concurrent.futures import ThreadPoolExecutor
    processor, service, calls, directory, source, decision = revision_setup
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: RevisionOperations(service.engine, processor).run(), range(2)))
    assert results == [True, True] and len(calls) == 4
    with Session(service.engine) as session:
        assert session.get(PacketRevisionWork, decision.id).state == "succeeded"
        assert len(session.exec(select(ApplicationPacket)).all()) == 2


def test_revision_sigterm_during_initial_scan_does_not_start_interval(revision_setup, monkeypatch):
    import signal
    import job_agent.scheduler as scheduling
    import job_agent.revisions as revisions
    import job_agent.dashboard.approval_app as app
    processor, service, calls, directory, source, decision = revision_setup
    previous = signal.getsignal(signal.SIGTERM)
    def stopping(key): signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    processor.process_revision = stopping
    monkeypatch.setattr(revisions, "RevisionProcessor", lambda *args: processor)
    monkeypatch.setattr(app, "_existing_engine", lambda settings: service.engine)
    monkeypatch.setattr(scheduling, "build_revision_scheduler", lambda ops: NS(
        running=False, start=lambda: pytest.fail("started after termination")))
    assert run_revision_scheduler(service.settings) == 0
    assert signal.getsignal(signal.SIGTERM) == previous


@pytest.mark.parametrize("present", [False, True])
def test_revision_worker_storage_requires_existing_v9(tmp_path, present):
    from job_agent.config import Settings
    import sqlite3
    path = tmp_path / "job_pilot.sqlite3"
    if present:
        with sqlite3.connect(path) as conn: conn.execute("PRAGMA user_version=8")
    with pytest.raises(ValueError, match="approval_storage_unavailable"):
        run_revision_scheduler(Settings(data_dir=tmp_path))
    assert path.exists() == present
    if present:
        with sqlite3.connect(path) as conn: assert conn.execute("PRAGMA user_version").fetchone()[0] == 8



@pytest.mark.parametrize("phase", ["after_writing_checkpoint", "after_ready_commit"])
def test_revision_worker_process_death_releases_lock_and_preserves_provider_checkpoints(revision_setup, phase):
    import os
    from job_agent.revisions import RevisionProcessor
    from job_agent.dashboard.approval_service import ApprovalQueueService
    processor, service, calls, directory, source, decision = revision_setup
    status_service = ApprovalQueueService(service.engine, service.settings)
    assert status_service.revision_status(source.id).state == "queued"
    context = multiprocessing.get_context("fork")
    paid = context.Value("i", 0)
    original = processor.executor.create
    def counted(**request):
        with paid.get_lock(): paid.value += 1
        return original(**request)
    processor.executor = NS(create=counted)
    def worker():
        service.engine.dispose()
        def crash(name):
            if name == phase: os._exit(97)
        processor._boundary = crash
        with scheduler_lock(directory, revisions_only=True):
            RevisionOperations(service.engine, processor).run()
        os._exit(98)
    child = context.Process(target=worker)
    child.start(); child.join(15)
    try: assert not child.is_alive() and child.exitcode == 97
    finally:
        if child.is_alive(): child.terminate(); child.join(5)
    assert status_service.revision_status(source.id).state == "building"
    restart = RevisionProcessor(service.engine, service.settings, executor=processor.executor, clock=processor.clock)
    with scheduler_lock(directory, revisions_only=True):
        assert RevisionOperations(service.engine, restart).run()
    status = status_service.revision_status(source.id)
    assert status.state == "succeeded" and status.successor_version == source.version + 1
    assert status.successor_status == "packet_ready" and paid.value == 2
    with Session(service.engine) as session:
        assert len(session.exec(select(ApplicationPacket)).all()) == 2
        assert session.exec(select(PacketDecision).where(PacketDecision.packet_id == status.successor_packet_id)).first() is None
    assert RevisionOperations(service.engine, restart).run() and paid.value == 2


def test_revision_cli_and_scheduler_process_consumers_converge(revision_setup, monkeypatch, request):
    from contextlib import contextmanager
    import sqlite3
    from job_agent.cli import main
    from job_agent.dashboard.approval_app import _existing_engine
    from job_agent.database import WritingWorkItem, StyleMemorySnapshot
    from job_agent.llm import AnthropicExecutor
    from job_agent.packets import PacketService, verify_packet_integrity
    from job_agent.revisions import RevisionProcessor, process_revision
    from job_agent.style_memory import LockedStyleMemory, read_style_memory
    from test_revisions import source_state
    processor, service, calls, directory, source, decision = revision_setup
    with sqlite3.connect(service.engine.url.database) as old:
        with sqlite3.connect(directory / "job_pilot.sqlite3") as target:
            old.backup(target)
    engine = _existing_engine(service.settings)
    request.addfinalizer(engine.dispose)
    monkeypatch.setattr(service, "engine", engine)
    before = source_state(service, source, directory)
    context = multiprocessing.get_context("fork")
    start = context.Barrier(3)
    attempts, results = context.Queue(), context.Queue()
    allocated, release = context.Event(), context.Event()
    paid = context.Value("i", 0)
    publications = context.Value("i", 0)
    original_publish = LockedStyleMemory.publish
    def counted_publish(locked, *args, **kwargs):
        result = original_publish(locked, *args, **kwargs)
        with publications.get_lock(): publications.value += 1
        return result
    monkeypatch.setattr(LockedStyleMemory, "publish", counted_publish)
    original = service.executor.create
    class Provider:
        def __init__(self): self.messages = self
        def create(self, **kwargs):
            with paid.get_lock():
                paid.value += 1
                number = paid.value
            assert number <= 2, "duplicate_provider_work"
            response = original(task="tailor_resume" if number == 1 else "cover_letter", **kwargs)
            response.usage = NS(input_tokens=10, output_tokens=20,
                cache_read_input_tokens=30, cache_creation_input_tokens=40)
            return response
    original_lock = PacketService._build_lock
    @contextmanager
    def observed_lock(owner, **kwargs):
        attempts.put(True)
        with original_lock(owner, **kwargs):
            yield
    monkeypatch.setattr(PacketService, "_build_lock", observed_lock)
    def boundary(name):
        if name == "after_successor_allocation":
            allocated.set()
            assert release.wait(15), "contention_release_timeout"
    monkeypatch.setattr(RevisionProcessor, "_boundary", lambda self, name: boundary(name))
    monkeypatch.setattr("job_agent.cli.load_settings", lambda: service.settings)
    def local(cli_engine, settings, decision_id):
        executor = AnthropicExecutor(Provider(), settings, engine=cli_engine, clock=lambda: NOW)
        return process_revision(cli_engine, settings, decision_id, executor=executor, clock=lambda: NOW)
    monkeypatch.setattr("job_agent.revisions.process_revision", local)
    def consumer(kind):
        # Discard inherited pooled handles; each process opens its own engine.
        service.engine.dispose()
        child_engine = _existing_engine(service.settings)
        try:
            start.wait(timeout=15)
            if kind == "cli":
                result = main(["revision-process", "--decision-id", decision.id, "--data-dir", str(directory)])
                assert result == 0
            else:
                executor = AnthropicExecutor(Provider(), service.settings, engine=child_engine, clock=lambda: NOW)
                worker = RevisionProcessor(child_engine, service.settings, executor=executor, clock=lambda: NOW)
                assert RevisionOperations(child_engine, worker).run()
            results.put(kind)
        finally:
            child_engine.dispose()
    children = [context.Process(target=consumer, args=(kind,)) for kind in ("cli", "scheduler")]
    for child in children: child.start()
    try:
        start.wait(timeout=15)
        assert attempts.get(timeout=15) and attempts.get(timeout=15)
        assert allocated.wait(15)
        # Both consumers reached the real build lock while the winner holds it.
        assert paid.value == 0
        release.set()
        for child in children:
            child.join(20)
            assert not child.is_alive() and child.exitcode == 0
        assert {results.get(timeout=5), results.get(timeout=5)} == {"cli", "scheduler"}
    finally:
        release.set()
        for child in children:
            if child.is_alive(): child.terminate(); child.join(5)
        attempts.close(); results.close()
    with Session(service.engine) as session:
        works = session.exec(select(PacketRevisionWork)).all()
        assert len(works) == 1 and works[0].decision_id == decision.id and works[0].state == "succeeded"
        successor = session.get(ApplicationPacket, works[0].successor_packet_id)
        assert successor.revision_decision_id == decision.id and successor.version == source.version + 1
        packets = session.exec(select(ApplicationPacket)).all()
        assert len(packets) == 2 and len({p.version for p in packets}) == 2
        assert len({p.fingerprint for p in packets}) == 2
        assert len(session.exec(select(PacketDecision)).all()) == 1
        assert session.exec(select(PacketDecision).where(PacketDecision.packet_id == successor.id)).first() is None
        assert len(session.exec(select(StyleMemorySnapshot)).all()) == 2
        writes = session.exec(select(WritingWorkItem).where(WritingWorkItem.packet_id == successor.id)).all()
        accounting = session.exec(select(LLMCall)).all()
        assert len(writes) == len(accounting) == paid.value == 2
        assert all(w.state == "succeeded" for w in writes)
        assert {call.task for call in accounting} == {"tailor_resume", "cover_letter"}
        assert all(call.status == "succeeded" and call.cache_read_input_tokens == 30 for call in accounting)
        verify_packet_integrity(session, service.settings, successor)
    assert source_state(service, source, directory) == before
    assert read_style_memory(directory).hash == works[0].target_style_hash
    assert read_style_memory(directory).canonical_content.count(decision.id) == 1
    assert publications.value == 1
    with service.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM application_events").scalar() == 0
        assert connection.exec_driver_sql("SELECT count(*) FROM jobs WHERE application_status IS NOT NULL").scalar() == 0
