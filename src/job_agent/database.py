"""Opt-in SQLite storage. Importing this module performs no filesystem IO.

Call initialize_database(path), then use database_session(engine) as a transaction.
Repository methods flush but never commit; the caller owns the unit of work.
Timestamps are stored as naive UTC because SQLite has no timezone-aware type.
Source identities must be verified by the caller; no fuzzy merging is performed.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Engine, UniqueConstraint, event
from sqlalchemy.engine import URL
from sqlmodel import Field, Session, SQLModel, create_engine, select

SCHEMA_VERSION = 3


def _utc(value: datetime | None = None) -> datetime:
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Observation timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class CanonicalJob(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    company: str
    title: str
    location: str
    posting_url: str
    apply_url: str | None = None
    first_seen: datetime = Field(sa_type=DateTime)
    last_seen: datetime = Field(sa_type=DateTime)
    # Legacy status is mixed; kind prevents treating submitted as applied.
    application_status: str | None = None
    application_status_kind: str | None = None
    application_notes: str | None = None
    application_follow_up: str | None = None
    application_updated_at: datetime | None = Field(default=None, sa_type=DateTime)


class JobIdentity(SQLModel, table=True):
    __tablename__ = "job_identities"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: int | None = Field(default=None, primary_key=True)
    job_id: str | None = Field(default=None, foreign_key="jobs.id", index=True)
    source: str
    external_id: str
    posting_url: str | None = None
    apply_url: str | None = None
    first_seen: datetime = Field(sa_type=DateTime)
    last_seen: datetime = Field(sa_type=DateTime)


class SearchRun(SQLModel, table=True):
    __tablename__ = "search_runs"

    id: str = Field(primary_key=True)  # Semantic SHA-256 of the legacy snapshot.
    generated_at: str | None = None
    total: int | None = None
    new_count: int | None = None
    sources_queried: int | None = None
    payload: dict = Field(sa_column=Column(JSON, nullable=False))


class SearchResult(SQLModel, table=True):
    __tablename__ = "search_results"
    __table_args__ = (UniqueConstraint("run_id", "legacy_key"),)

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="search_runs.id")
    legacy_key: str
    identity_id: int | None = Field(default=None, foreign_key="job_identities.id")
    unresolved: str | None = None
    # Exact persisted keys only, including explicit nulls and booleans.
    payload: dict = Field(sa_column=Column(JSON, nullable=False))


class ApplicationEvent(SQLModel, table=True):
    """Immutable evidence, including exact legacy fields and import provenance."""
    __tablename__ = "application_events"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    import_key: str | None = Field(default=None, unique=True)
    job_id: str | None = Field(default=None, foreign_key="jobs.id", index=True)
    external_job_id: str
    source: str
    company: str
    title: str
    attempt_id: str
    status: str
    status_kind: str
    reason: str
    notes: str
    follow_up: str
    occurred_at: datetime = Field(sa_type=DateTime)
    legacy_date: str | None = None
    provenance: str
    file_sha256: str | None = None
    record_index: int | None = None
    unresolved: str | None = None
    payload: dict = Field(sa_column=Column(JSON, nullable=False))


def initialize_database(path: str | Path) -> Engine:
    """Explicitly create/open a file and initialize schema v3.

    Unknown versions and nonempty unversioned databases are rejected, never
    silently adopted. Versions 1 and 2 are upgraded transactionally.
    Parent directories must already exist.
    """
    engine = create_engine(URL.create("sqlite", database=str(path)))

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    try:
        with engine.connect() as connection:
            # Explicit BEGIN also makes DDL transactional with sqlite3's legacy
            # transaction control. Serialize competing initializations.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
            if version not in (0, 1, 2, SCHEMA_VERSION):
                raise ValueError(f"Unsupported database schema version: {version}")
            if version == 0:
                tables = connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                ).all()
                if tables:
                    raise ValueError("Refusing to initialize a nonempty unversioned database")
                SQLModel.metadata.create_all(
                    connection, tables=[CanonicalJob.__table__, JobIdentity.__table__,
                                        SearchRun.__table__, SearchResult.__table__,
                                        ApplicationEvent.__table__]
                )
                connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
            if version == 1:
                # Rebuild only the identity table to permit honest seen-only rows.
                connection.exec_driver_sql(
                    "CREATE TABLE identities_v2 (id INTEGER PRIMARY KEY, "
                    "job_id VARCHAR REFERENCES jobs(id), source VARCHAR NOT NULL, "
                    "external_id VARCHAR NOT NULL, posting_url VARCHAR, apply_url VARCHAR, "
                    "first_seen DATETIME NOT NULL, last_seen DATETIME NOT NULL, "
                    "UNIQUE(source, external_id))"
                )
                connection.exec_driver_sql(
                    "INSERT INTO identities_v2 SELECT * FROM job_identities"
                )
                connection.exec_driver_sql("DROP TABLE job_identities")
                connection.exec_driver_sql("ALTER TABLE identities_v2 RENAME TO job_identities")
                connection.exec_driver_sql(
                    "CREATE INDEX ix_job_identities_job_id ON job_identities(job_id)"
                )
                SQLModel.metadata.create_all(
                    connection, tables=[SearchRun.__table__, SearchResult.__table__]
                )
                connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
            if version in (1, 2):
                for name, sql_type in (
                    ("application_status", "VARCHAR"),
                    ("application_status_kind", "VARCHAR"),
                    ("application_notes", "VARCHAR"),
                    ("application_follow_up", "VARCHAR"),
                    ("application_updated_at", "DATETIME"),
                ):
                    connection.exec_driver_sql(f"ALTER TABLE jobs ADD COLUMN {name} {sql_type}")
                ApplicationEvent.__table__.create(connection)
                connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
            # Enforce append-only history even for direct SQL/ORM callers.
            for operation in ("UPDATE", "DELETE"):
                connection.exec_driver_sql(
                    f"CREATE TRIGGER IF NOT EXISTS application_events_no_{operation.lower()} "
                    f"BEFORE {operation} ON application_events BEGIN "
                    "SELECT RAISE(ABORT, 'application_events is append-only'); END"
                )
            connection.commit()
    except Exception:
        engine.dispose()
        raise
    return engine


@contextmanager
def database_session(engine: Engine) -> Iterator[Session]:
    """Commit a complete unit of work, or roll back every write on failure."""
    with Session(engine, expire_on_commit=False) as session:
        with session.begin():
            yield session


class JobRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_job(
        self, *, company: str, title: str, location: str, posting_url: str,
        apply_url: str | None = None, seen_at: datetime | None = None,
    ) -> CanonicalJob:
        observed = _utc(seen_at)
        job = CanonicalJob(
            company=company, title=title, location=location,
            posting_url=posting_url, apply_url=apply_url,
            first_seen=observed, last_seen=observed,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def get_job(self, job_id: str) -> CanonicalJob | None:
        return self.session.get(CanonicalJob, job_id)

    def get_identity(self, source: str, external_id: str) -> JobIdentity | None:
        return self.session.exec(select(JobIdentity).where(
            JobIdentity.source == source, JobIdentity.external_id == external_id,
        )).one_or_none()

    def identities_for_job(self, job_id: str) -> list[JobIdentity]:
        return list(self.session.exec(select(JobIdentity).where(
            JobIdentity.job_id == job_id,
        ).order_by(JobIdentity.id)).all())

    def add_identity(
        self, job_id: str, *, source: str, external_id: str, posting_url: str,
        apply_url: str | None = None, seen_at: datetime | None = None,
    ) -> JobIdentity:
        """Attach a verified identity; repeats preserve its owner and URLs.

        A conflicting owner is an error, never an implicit merge or reassignment.
        """
        observed = _utc(seen_at)
        job = self.get_job(job_id)
        if job is None:
            raise ValueError(f"Unknown canonical job: {job_id}")
        identity = self.get_identity(source, external_id)
        if identity is not None:
            if identity.job_id is not None and identity.job_id != job_id:
                raise ValueError("Source identity already belongs to another job")
            if identity.job_id is None:
                identity.job_id = job_id
                identity.posting_url = posting_url
                identity.apply_url = apply_url
            identity.first_seen = min(identity.first_seen, observed)
            identity.last_seen = max(identity.last_seen, observed)
        else:
            identity = JobIdentity(
                job_id=job_id, source=source, external_id=external_id,
                posting_url=posting_url, apply_url=apply_url,
                first_seen=observed, last_seen=observed,
            )
        job.first_seen = min(job.first_seen, identity.first_seen)
        job.last_seen = max(job.last_seen, identity.last_seen)
        self.session.add(identity)
        self.session.add(job)
        self.session.flush()
        return identity

    def observe_identity(
        self, source: str, external_id: str, *, seen_at: datetime | None = None,
    ) -> JobIdentity:
        identity = self.get_identity(source, external_id)
        if identity is None:
            raise ValueError("Unknown source identity")
        if identity.job_id is None:
            observed = _utc(seen_at)
            identity.first_seen = min(identity.first_seen, observed)
            identity.last_seen = max(identity.last_seen, observed)
            self.session.add(identity)
            self.session.flush()
            return identity
        return self.add_identity(
            identity.job_id, source=source, external_id=external_id,
            posting_url=identity.posting_url, apply_url=identity.apply_url,
            seen_at=seen_at,
        )
