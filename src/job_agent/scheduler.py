"""Local, fail-closed scheduling. No application or outreach operations."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import logging
from pathlib import Path
import threading
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

TIMEZONE = ZoneInfo("America/New_York")
LOG = logging.getLogger(__name__)
SCHEDULES = {
    "morning": dict(day_of_week="mon-fri", hour=6, minute=30),
    "midday": dict(day_of_week="mon-fri", hour=13, minute=0),
    "batch": dict(hour=23, minute=0),
    "maintenance": dict(minute=10),
}


class SchedulerLocked(RuntimeError):
    """Another local scheduler already owns this data directory."""


@contextmanager
def scheduler_lock(data_dir, *, revisions_only=False):
    directory = Path(data_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    # Never unlink: replacing the inode would allow two lock owners.
    name = "revision_scheduler.lock" if revisions_only else "scheduler.lock"
    with (directory / name).open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SchedulerLocked("Another scheduler holds the data-directory lock") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def scheduled_discovery(profile, data_dir):
    """Use the CLI's production search defaults and persistence path."""
    from job_agent.cli import _build_parser, cmd_search
    from rich.console import Console
    import os
    args = _build_parser().parse_args(["search", "--profile", str(profile)])
    args.data_dir = data_dir
    # Search rendering can contain source/provider warnings. Discard it rather
    # than retain candidate data or provider bodies in scheduler logs.
    with open(os.devnull, "w") as sink:
        return cmd_search(Console(file=sink), args)


class Operations:
    def __init__(self, discovery, batch_service):
        self.discovery = discovery
        self.batch_service = batch_service
        self.search_lock = threading.Lock()
        self.batch_lock = threading.Lock()

    def run(self, name):
        lock = self.search_lock if name in ("morning", "midday") else self.batch_lock
        # Nightly submission waits before entering any service/SQLite work.
        # Maintenance and discovery may skip an overlap.
        if not lock.acquire(blocking=name == "batch"):
            LOG.info("operation=%s skipped=overlap", name)
            return False
        try:
            if name in ("morning", "midday"):
                if self.discovery() != 0:
                    raise RuntimeError("Search failed")
                LOG.info("operation=%s succeeded", name)
            else:
                maintained = self.batch_service.maintain()
                submitted = self.batch_service.submit()["submitted"] if name == "batch" else 0
                LOG.info("operation=%s succeeded reconciled=%d submitted=%d", name,
                         maintained["reconciled"], submitted)
            return True
        except Exception:
            # Do not log exception text, traceback, provider body or inputs.
            LOG.error("operation=%s failed; inspect local ops status", name)
            return False
        finally:
            lock.release()


def build_scheduler(operations):
    scheduler = BlockingScheduler(timezone=TIMEZONE)
    for name, fields in SCHEDULES.items():
        scheduler.add_job(operations.run, CronTrigger(timezone=TIMEZONE, **fields),
                          args=[name], id=name, max_instances=1, coalesce=True,
                          misfire_grace_time=900)
    return scheduler


class RevisionOperations:
    """Discover committed decisions; durable domain checkpoints own execution."""
    def __init__(self, engine, processor):
        self.engine, self.processor = engine, processor
        self.scan_lock = threading.Lock()

    def run(self):
        from sqlmodel import Session, select
        from job_agent.database import PacketDecision, PacketRevisionWork
        from job_agent.packets import private_packet_logs
        if not self.scan_lock.acquire(blocking=False):
            return False
        try:
            # Read only IDs, bounded pages. No transaction survives processing.
            cursor = None
            while True:
                with Session(self.engine) as session:
                    query = (select(PacketDecision.id, PacketDecision.created_at)
                        .outerjoin(PacketRevisionWork, PacketRevisionWork.decision_id == PacketDecision.id)
                        .where(PacketDecision.decision == "revise",
                            (PacketRevisionWork.decision_id.is_(None)) |
                            PacketRevisionWork.state.in_(("pending", "style_prepared", "style_persisted", "building"))))
                    if cursor:
                        timestamp, decision_id = cursor
                        query = query.where((PacketDecision.created_at > timestamp) |
                            ((PacketDecision.created_at == timestamp) & (PacketDecision.id > decision_id)))
                    rows = session.exec(query.order_by(PacketDecision.created_at, PacketDecision.id).limit(100)).all()
                if not rows:
                    return True
                for decision_id, timestamp in rows:
                    cursor = (timestamp, decision_id)
                    try:
                        with private_packet_logs():
                            self.processor.process_revision(decision_id)
                    except Exception:
                        # No retry/reset here. The next scan trusts domain state.
                        LOG.error("operation=revision failed decision_id=%s", decision_id)
        except Exception:
            LOG.error("operation=revision scan_failed")
            return False
        finally:
            self.scan_lock.release()


def build_revision_scheduler(operations):
    scheduler = BlockingScheduler(timezone=TIMEZONE)
    scheduler.add_job(operations.run, "interval", seconds=10, id="revisions",
                      max_instances=1, coalesce=True, misfire_grace_time=10)
    return scheduler


def run_revision_scheduler(settings):
    """Separate local worker; no discovery, profile, research or batch service."""
    import signal
    from job_agent.dashboard.approval_app import _existing_engine
    from job_agent.packets import private_packet_logs
    from job_agent.revisions import RevisionProcessor
    with scheduler_lock(settings.data_dir, revisions_only=True):
        with private_packet_logs():
            engine = _existing_engine(settings)  # Existing v9 only; no migration/import.
        try:
            operations = RevisionOperations(engine, RevisionProcessor(engine, settings))
            scheduler = build_revision_scheduler(operations)
            stopping = threading.Event()
            def terminate(*_):
                stopping.set()
                if scheduler.running:
                    scheduler.shutdown(wait=True)
            previous = signal.signal(signal.SIGTERM, terminate)
            try:
                operations.run()  # Discover durable work immediately on startup.
                if not stopping.is_set():
                    scheduler.start()
            finally:
                signal.signal(signal.SIGTERM, previous)
                if scheduler.running:
                    scheduler.shutdown(wait=True)
        finally:
            engine.dispose()
    return 0


def run_scheduler(settings, profile, *, once=None):
    from job_agent.batch import BatchService
    from job_agent.config import load_profile
    from job_agent.search_state import search_database
    with scheduler_lock(settings.data_dir):
        with search_database(settings.data_dir) as engine:
            service = BatchService(engine, settings)
            # Maintenance never needs a scoring profile.
            if once != "maintenance":
                service.profile = load_profile(profile)
            operations = Operations(lambda: scheduled_discovery(profile, settings.data_dir), service)
            scheduler = build_scheduler(operations)
            LOG.info("startup=%s timezone=%s data_dir=%s", datetime.now(timezone.utc).isoformat(),
                     TIMEZONE.key, Path(settings.data_dir).resolve())
            for job in scheduler.get_jobs():
                LOG.info("schedule=%s trigger=%s", job.id, job.trigger)
            if once:
                return 0 if operations.run(once) else 1
            # SIGTERM and Ctrl+C shut down cleanly and release the flock.
            import signal
            previous = signal.signal(signal.SIGTERM, lambda *_: scheduler.shutdown(wait=True))
            try:
                scheduler.start()
            finally:
                signal.signal(signal.SIGTERM, previous)
                if scheduler.running:
                    scheduler.shutdown(wait=True)
    return 0
