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

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, Engine, UniqueConstraint, event
from sqlalchemy.engine import URL
from sqlmodel import Field, Session, SQLModel, create_engine, select

SCHEMA_VERSION = 9
LEGACY_WRITING_PROMPT_VERSION = "v4-semantic-writing-cache"
STYLE_WRITING_PROMPT_VERSION = "v5-style-memory-snapshot"


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


class LLMCall(SQLModel, table=True):
    """Operational accounting only; never persist prompt or provider error bodies."""
    __tablename__ = "llm_calls"
    __table_args__ = (
        CheckConstraint("request_kind IN ('standard', 'batch')"),
        CheckConstraint("status IN ('reserved', 'succeeded', 'failed')"),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0 AND "
                        "cache_creation_input_tokens >= 0 AND cache_read_input_tokens >= 0"),
    )
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    created_at: datetime = Field(default_factory=_utc, sa_type=DateTime, index=True)
    task: str
    model: str
    prompt_name: str
    prompt_version: str
    request_kind: str = "standard"
    status: str = "reserved"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    # Decimal strings preserve exact micro-dollar arithmetic in SQLite.
    estimated_cost_usd: str = "0"
    reserved_cost_usd: str = "0"
    latency_ms: int = 0
    error_type: str | None = None
    error_message: str | None = None
    provider_request_id: str | None = None
    canonical_job_id: str | None = None
    external_job_reference: str | None = None
    operational_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class LLMBatch(SQLModel, table=True):
    __tablename__ = "llm_batches"
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    provider_id: str | None = Field(default=None, unique=True)
    status: str = "submitting"
    created_at: datetime = Field(default_factory=_utc, sa_type=DateTime)
    updated_at: datetime = Field(default_factory=_utc, sa_type=DateTime)
    provider_created_at: datetime | None = Field(default=None, sa_type=DateTime)
    expires_at: datetime | None = Field(default=None, sa_type=DateTime)
    request_count: int = 0


class ScoringWorkItem(SQLModel, table=True):
    __tablename__ = "scoring_work_items"
    __table_args__ = (CheckConstraint("state IN ('pending','submitted','succeeded','retryable','failed','submission_unknown','standard_in_progress')"),)
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    fingerprint: str = Field(unique=True)
    source: str
    external_id: str
    canonical_job_id: str | None = Field(default=None, foreign_key="jobs.id")
    search_result_id: int | None = Field(default=None, foreign_key="search_results.id", index=True)
    model: str
    prompt_name: str = "score"
    prompt_version: str = "v1"
    candidate_hash: str
    reservation_cost_usd: str = "0"
    state: str = Field(default="pending", index=True)
    created_at: datetime = Field(default_factory=_utc, sa_type=DateTime)
    updated_at: datetime = Field(default_factory=_utc, sa_type=DateTime)
    priority_at: datetime = Field(sa_type=DateTime)
    attempt_count: int = 0
    batch_id: str | None = Field(default=None, foreign_key="llm_batches.id", index=True)
    custom_id: str | None = Field(default=None, unique=True)
    llm_call_id: str | None = Field(default=None, foreign_key="llm_calls.id")
    failure: str | None = None
    result: dict | None = Field(default=None, sa_column=Column(JSON))


class CompanyFactRecord(SQLModel, table=True):
    __tablename__ = "company_facts"
    id: str = Field(primary_key=True)
    job_key: str = Field(index=True)
    company: str
    text: str
    source_url: str
    source_title: str
    category: str
    retrieved_at: datetime = Field(sa_type=DateTime)


class CompanyResearchCache(SQLModel, table=True):
    """Only three selected public facts; no provider bodies or credentials."""
    __tablename__ = "company_research_cache"
    __table_args__ = (CheckConstraint("provider = 'tavily'"),)
    fingerprint: str = Field(primary_key=True)
    provider: str = "tavily"
    researcher_version: str
    company: str
    title_context: str
    facts: list = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(sa_type=DateTime)
    refreshed_at: datetime = Field(sa_type=DateTime)
    expires_at: datetime = Field(sa_type=DateTime, index=True)


class StyleMemorySnapshot(SQLModel, table=True):
    """Private immutable exact canonical content, never just a digest."""
    __tablename__ = "style_memory_snapshots"
    __table_args__ = (
        CheckConstraint("typeof(hash) = 'text' AND length(hash) = 64 AND length(CAST(hash AS BLOB)) = 64 AND hash NOT GLOB '*[^0-9a-f]*'"),
        CheckConstraint("typeof(canonical_content) = 'text' AND length(CAST(canonical_content AS BLOB)) <= 65536"),
        CheckConstraint("canonicalization_version = 'style-nfc-lf-v1'"),
    )
    hash: str = Field(primary_key=True)
    canonical_content: str
    canonicalization_version: str = "style-nfc-lf-v1"
    created_at: datetime = Field(default_factory=_utc, sa_type=DateTime)


class ApplicationPacket(SQLModel, table=True):
    __tablename__ = "application_packets"
    __table_args__ = (UniqueConstraint("job_key", "version"),
        CheckConstraint("status IN ('building','packet_ready','generation_failed','research_incomplete','recovery_required')"),
        CheckConstraint("cover_letter_acceptance IN ('yes','no','unknown')"),
        CheckConstraint("verifier_status IN ('not_run','passed','failed')"),
        CheckConstraint("lint_status IN ('not_run','passed','failed')"),
        CheckConstraint("(writing_prompt_version = 'v4-semantic-writing-cache' AND style_memory_hash IS NULL) OR (writing_prompt_version = 'v5-style-memory-snapshot' AND style_memory_hash IS NOT NULL)"),
        CheckConstraint("status != 'packet_ready' OR (verifier_status = 'passed' AND lint_status = 'passed' AND length(cover_letter) > 0 AND length(scoring_fingerprint) > 0 AND length(fingerprint) > 0)"),)
    capacity_day: str | None = Field(default=None, index=True)
    # Default retains compatibility with trusted historical construction. New
    # style-aware builders must explicitly bind v5 and a non-NULL snapshot.
    writing_prompt_version: str = LEGACY_WRITING_PROMPT_VERSION
    style_memory_hash: str | None = Field(default=None, foreign_key="style_memory_snapshots.hash")
    revision_decision_id: str | None = Field(default=None, foreign_key="packet_decisions.id")
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    job_key: str = Field(index=True)
    search_result_id: int = Field(foreign_key="search_results.id")
    canonical_job_id: str | None = Field(default=None, foreign_key="jobs.id")
    fingerprint: str = Field(unique=True)
    scoring_fingerprint: str
    version: int
    status: str
    score: int
    tier: str
    company: str
    title: str
    created_at: datetime = Field(default_factory=_utc, sa_type=DateTime)
    updated_at: datetime = Field(default_factory=_utc, sa_type=DateTime)
    ready_at: datetime | None = Field(default=None, sa_type=DateTime)
    cover_letter_acceptance: str = "unknown"
    cover_letter: str = ""
    writing_fingerprints: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    artifacts: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    screening_answers: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    referral_candidates: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    referral_status: str = "not_implemented"
    company_fact_ids: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    content_flags: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    verifier_status: str = "not_run"
    lint_status: str = "not_run"
    failure_reason: str | None = None


class WritingWorkItem(SQLModel, table=True):
    __tablename__ = "writing_work_items"
    __table_args__ = (CheckConstraint("state IN ('in_progress','succeeded','failed','recovery_required')"),
                      UniqueConstraint("packet_id", "task"))
    fingerprint: str = Field(primary_key=True)
    packet_id: str | None = Field(default=None, foreign_key="application_packets.id")
    model: str = ""
    system_hash: str = ""
    user_hash: str = ""
    max_tokens: int = 0
    prompt_name: str = ""
    prompt_version: str = ""
    failure_reason: str | None = None
    updated_at: datetime = Field(default_factory=_utc, sa_type=DateTime)
    task: str
    state: str = "in_progress"
    output: str | None = None
    output_hash: str | None = None
    created_at: datetime = Field(default_factory=_utc, sa_type=DateTime)


class PacketDecision(SQLModel, table=True):
    """One immutable user decision for one historical packet version."""
    __tablename__ = "packet_decisions"
    __table_args__ = (
        UniqueConstraint("packet_id"),
        CheckConstraint("decision IN ('approve','reject','revise')"),
        CheckConstraint("actor = 'Andrew'"),
        CheckConstraint("evidence_version = 1"),
        CheckConstraint("length(packet_fingerprint) = 64 AND packet_fingerprint NOT GLOB '*[^0-9a-f]*'"),
        CheckConstraint("length(detail) <= 4000"),
        CheckConstraint("decision != 'approve' OR (reason_code = '' AND detail = '')"),
        CheckConstraint("decision != 'revise' OR (reason_code = '' AND trim(detail, char(9)||char(10)||char(11)||char(12)||char(13)||char(28)||char(29)||char(30)||char(31)||char(32)||char(133)||char(160)||char(5760)||char(8192)||char(8193)||char(8194)||char(8195)||char(8196)||char(8197)||char(8198)||char(8199)||char(8200)||char(8201)||char(8202)||char(8232)||char(8233)||char(8239)||char(8287)||char(12288)) != '')"),
        CheckConstraint("decision != 'reject' OR reason_code IN ('not_interested','bad_fit','company','location','pay','other')"),
    )
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    packet_id: str = Field(foreign_key="application_packets.id")
    packet_fingerprint: str
    decision: str
    actor: str = "Andrew"
    reason_code: str = ""
    detail: str = ""
    created_at: datetime = Field(default_factory=_utc, sa_type=DateTime)
    evidence_version: int = 1
    evidence_json: str


class PacketRevisionWork(SQLModel, table=True):
    """Durable revision identity; operational state remains mutable."""
    __tablename__ = "packet_revision_work"
    __table_args__ = (
        CheckConstraint("state IN ('pending','style_prepared','style_persisted','building','succeeded','blocked','recovery_required')"),
        CheckConstraint("state != 'pending' OR (base_style_hash IS NULL AND target_style_hash IS NULL AND successor_packet_id IS NULL)"),
        CheckConstraint("(base_style_hash IS NULL) = (target_style_hash IS NULL)"),
        CheckConstraint("state NOT IN ('style_prepared','style_persisted','building','succeeded') OR (base_style_hash IS NOT NULL AND target_style_hash IS NOT NULL)"),
        CheckConstraint("state NOT IN ('building','succeeded') OR successor_packet_id IS NOT NULL"),
        CheckConstraint("state NOT IN ('style_prepared','style_persisted') OR successor_packet_id IS NULL"),
        CheckConstraint("successor_packet_id IS NULL OR target_style_hash IS NOT NULL"),
        CheckConstraint("failure_code IS NULL OR (length(failure_code) BETWEEN 1 AND 80 AND length(CAST(failure_code AS BLOB)) = length(failure_code) AND failure_code NOT GLOB '*[^a-z0-9_]*')"),
        CheckConstraint("state NOT IN ('pending','style_prepared','style_persisted','building','succeeded') OR failure_code IS NULL"),
        UniqueConstraint("successor_packet_id"),
    )
    decision_id: str = Field(primary_key=True, foreign_key="packet_decisions.id")
    state: str = "pending"
    base_style_hash: str | None = Field(default=None, foreign_key="style_memory_snapshots.hash")
    target_style_hash: str | None = Field(default=None, foreign_key="style_memory_snapshots.hash")
    successor_packet_id: str | None = Field(default=None, foreign_key="application_packets.id")
    created_at: datetime = Field(default_factory=_utc, sa_type=DateTime)
    updated_at: datetime = Field(default_factory=_utc, sa_type=DateTime)
    failure_code: str | None = None


def _migration_boundary(name):
    """No-op deterministic migration fault seam; no IO or retries."""


def _install_style_revision_schema(connection, *, original_version):
    """Add v9 bindings/tables and persistent guards without rebuilding packets."""
    StyleMemorySnapshot.__table__.create(connection, checkfirst=True)
    additions = (
        ("writing_prompt_version", "VARCHAR NOT NULL DEFAULT 'v4-semantic-writing-cache'"),
        ("style_memory_hash", "VARCHAR REFERENCES style_memory_snapshots(hash)"),
        ("revision_decision_id", "VARCHAR REFERENCES packet_decisions(id)"),
    )
    columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(application_packets)")}
    for name, declaration in additions:
        if name not in columns:
            connection.exec_driver_sql(f"ALTER TABLE application_packets ADD COLUMN {name} {declaration}")
    # One explicit index works identically for additive and fresh schemas. SQLite
    # UNIQUE permits multiple NULL values, but only one successor per decision.
    connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS packet_revision_decision_unique ON application_packets(revision_decision_id)")
    PacketRevisionWork.__table__.create(connection, checkfirst=True)
    for operation in ("UPDATE", "DELETE"):
        connection.exec_driver_sql(
            f"CREATE TRIGGER IF NOT EXISTS style_memory_snapshots_no_{operation.lower()} "
            f"BEFORE {operation} ON style_memory_snapshots BEGIN "
            "SELECT RAISE(ABORT, 'style snapshots are immutable'); END")
    # REPLACE's implicit DELETE need not run DELETE triggers under SQLite's
    # default recursive_triggers setting. Reject existing identities at INSERT
    # too, rather than changing connection-wide semantics or old decision guards.
    connection.exec_driver_sql(
        "CREATE TRIGGER IF NOT EXISTS style_memory_snapshots_no_replace BEFORE INSERT ON style_memory_snapshots "
        "WHEN EXISTS (SELECT 1 FROM style_memory_snapshots WHERE hash=NEW.hash) "
        "BEGIN SELECT RAISE(ABORT, 'style snapshots are immutable'); END")
    pairing = (
        "NEW.writing_prompt_version IS NULL OR NOT ("
        "(NEW.writing_prompt_version='v4-semantic-writing-cache' AND NEW.style_memory_hash IS NULL) OR "
        "(NEW.writing_prompt_version='v5-style-memory-snapshot' AND NEW.style_memory_hash IS NOT NULL))"
    )
    revision_packet = (
        "NEW.revision_decision_id IS NOT NULL AND (NEW.writing_prompt_version!='v5-style-memory-snapshot' OR "
        "NOT EXISTS (SELECT 1 FROM packet_decisions d JOIN application_packets p ON p.id=d.packet_id "
        "WHERE d.id=NEW.revision_decision_id AND d.decision='revise' AND d.actor='Andrew' "
        "AND d.evidence_version=1 AND d.packet_fingerprint=p.fingerprint AND p.job_key=NEW.job_key "
        "AND p.canonical_job_id IS NEW.canonical_job_id AND p.version<NEW.version AND p.id!=NEW.id))"
    )
    revision_work = (
        "NOT EXISTS (SELECT 1 FROM packet_decisions d JOIN application_packets p ON p.id=d.packet_id "
        "WHERE d.id=NEW.decision_id AND d.decision='revise' AND d.actor='Andrew' "
        "AND d.evidence_version=1 AND d.packet_fingerprint=p.fingerprint) OR "
        "(NEW.successor_packet_id IS NOT NULL AND NOT EXISTS ("
        "SELECT 1 FROM application_packets successor JOIN packet_decisions d ON d.id=NEW.decision_id "
        "JOIN application_packets source ON source.id=d.packet_id WHERE successor.id=NEW.successor_packet_id "
        "AND successor.revision_decision_id=NEW.decision_id AND successor.style_memory_hash=NEW.target_style_hash "
        "AND successor.writing_prompt_version='v5-style-memory-snapshot' "
        "AND successor.job_key=source.job_key AND successor.canonical_job_id IS source.canonical_job_id "
        "AND successor.version>source.version AND successor.id!=source.id)) OR "
        "(NEW.state='succeeded' AND NOT EXISTS (SELECT 1 FROM application_packets p "
        "WHERE p.id=NEW.successor_packet_id AND p.status='packet_ready' AND p.ready_at IS NOT NULL))"
    )
    for operation in ("INSERT", "UPDATE"):
        for prefix, table, invalid in (
            ("packet_writing_binding", "application_packets", pairing),
            ("packet_revision_binding", "application_packets", revision_packet),
            ("revision_work_binding", "packet_revision_work", revision_work),
        ):
            connection.exec_driver_sql(
                f"CREATE TRIGGER IF NOT EXISTS {prefix}_{operation.lower()} BEFORE {operation} ON {table} "
                f"WHEN {invalid} BEGIN SELECT RAISE(ABORT, 'invalid style revision binding'); END")
    connection.exec_driver_sql(
        "CREATE TRIGGER IF NOT EXISTS packet_writing_identity_immutable BEFORE UPDATE ON application_packets "
        "WHEN NEW.writing_prompt_version IS NOT OLD.writing_prompt_version OR "
        "NEW.style_memory_hash IS NOT OLD.style_memory_hash OR NEW.revision_decision_id IS NOT OLD.revision_decision_id "
        "BEGIN SELECT RAISE(ABORT, 'packet writing binding is immutable'); END")
    connection.exec_driver_sql(
        "CREATE TRIGGER IF NOT EXISTS revision_work_identity_immutable BEFORE UPDATE ON packet_revision_work "
        "WHEN NEW.decision_id IS NOT OLD.decision_id OR NEW.created_at IS NOT OLD.created_at OR "
        "(OLD.base_style_hash IS NOT NULL AND NEW.base_style_hash IS NOT OLD.base_style_hash) OR "
        "(OLD.target_style_hash IS NOT NULL AND NEW.target_style_hash IS NOT OLD.target_style_hash) OR "
        "(OLD.successor_packet_id IS NOT NULL AND NEW.successor_packet_id IS NOT OLD.successor_packet_id) "
        "BEGIN SELECT RAISE(ABORT, 'revision identity is immutable'); END")
    connection.exec_driver_sql(
        "CREATE TRIGGER IF NOT EXISTS revision_work_no_delete BEFORE DELETE ON packet_revision_work "
        "BEGIN SELECT RAISE(ABORT, 'revision work cannot be deleted'); END")
    connection.exec_driver_sql(
        "CREATE TRIGGER IF NOT EXISTS revision_work_no_replace BEFORE INSERT ON packet_revision_work "
        "WHEN EXISTS (SELECT 1 FROM packet_revision_work WHERE decision_id=NEW.decision_id) "
        "BEGIN SELECT RAISE(ABORT, 'revision identity is immutable'); END")
    connection.exec_driver_sql(
        "CREATE TRIGGER IF NOT EXISTS packet_revision_no_replace BEFORE INSERT ON application_packets "
        "WHEN EXISTS (SELECT 1 FROM application_packets WHERE id=NEW.id AND revision_decision_id IS NOT NULL) OR "
        "(NEW.revision_decision_id IS NOT NULL AND EXISTS (SELECT 1 FROM application_packets "
        "WHERE revision_decision_id=NEW.revision_decision_id)) "
        "BEGIN SELECT RAISE(ABORT, 'revision successor is immutable'); END")
    connection.exec_driver_sql(
        "CREATE TRIGGER IF NOT EXISTS revision_work_transition BEFORE UPDATE ON packet_revision_work "
        "WHEN NEW.state!=OLD.state AND NOT ("
        "(OLD.state='pending' AND NEW.state IN ('style_prepared','blocked','recovery_required')) OR "
        "(OLD.state='style_prepared' AND NEW.state IN ('style_persisted','blocked','recovery_required')) OR "
        "(OLD.state='style_persisted' AND NEW.state IN ('building','blocked','recovery_required')) OR "
        "(OLD.state='building' AND NEW.state IN ('succeeded','blocked','recovery_required')) OR "
        "(OLD.state='recovery_required' AND NEW.state IN ('style_prepared','style_persisted','building','succeeded','blocked'))) "
        "BEGIN SELECT RAISE(ABORT, 'invalid revision transition'); END")
    # Validate adopted bindings too, even if opening a development/tampered file
    # with preexisting columns. Never silently repair or recompute identities.
    invalid = connection.exec_driver_sql(
        "SELECT 1 FROM application_packets WHERE writing_prompt_version IS NULL OR NOT ("
        "(writing_prompt_version='v4-semantic-writing-cache' AND style_memory_hash IS NULL) OR "
        "(writing_prompt_version='v5-style-memory-snapshot' AND style_memory_hash IS NOT NULL)) LIMIT 1").first()
    if invalid or connection.exec_driver_sql("PRAGMA foreign_key_check").first():
        raise ValueError("invalid_style_revision_schema")
    if original_version < 9 and connection.exec_driver_sql(
            "SELECT 1 FROM application_packets WHERE writing_prompt_version!='v4-semantic-writing-cache' "
            "OR style_memory_hash IS NOT NULL OR revision_decision_id IS NOT NULL LIMIT 1").first():
        raise ValueError("invalid_legacy_writing_binding")
    _migration_boundary("after_v9_schema_before_version")


def initialize_database(path: str | Path) -> Engine:
    """Explicitly create/open a file and initialize schema v9.

    Unknown versions and nonempty unversioned databases are rejected, never
    silently adopted. Versions 1 through 8 are upgraded transactionally.
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
            if version not in (0, 1, 2, 3, 4, 5, 6, 7, 8, SCHEMA_VERSION):
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
                                        ApplicationEvent.__table__, LLMCall.__table__]
                )
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
            if version in (1, 2, 3):
                LLMCall.__table__.create(connection, checkfirst=True)
            SQLModel.metadata.create_all(connection, tables=[LLMBatch.__table__, ScoringWorkItem.__table__])
            # Upgrade the initial v5 work table without changing the schema version.
            # No table references work items, so rebuilding preserves all foreign keys.
            columns = connection.exec_driver_sql("PRAGMA table_info(scoring_work_items)").all()
            work_ddl = connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name='scoring_work_items'"
            ).scalar_one()
            if (any(row[1] == "search_result_id" and row[3] for row in columns)
                    or "standard_in_progress" not in work_ddl):
                from sqlalchemy.schema import CreateTable, CreateIndex
                ddl = str(CreateTable(ScoringWorkItem.__table__).compile(connection))
                connection.exec_driver_sql(ddl.replace("CREATE TABLE scoring_work_items", "CREATE TABLE scoring_work_items_nullable", 1))
                names = ", ".join(column.name for column in ScoringWorkItem.__table__.columns)
                connection.exec_driver_sql(f"INSERT INTO scoring_work_items_nullable ({names}) SELECT {names} FROM scoring_work_items")
                connection.exec_driver_sql("DROP TABLE scoring_work_items")
                connection.exec_driver_sql("ALTER TABLE scoring_work_items_nullable RENAME TO scoring_work_items")
                for index in ScoringWorkItem.__table__.indexes:
                    connection.execute(CreateIndex(index))

            SQLModel.metadata.create_all(connection, tables=[CompanyFactRecord.__table__, StyleMemorySnapshot.__table__, ApplicationPacket.__table__, WritingWorkItem.__table__])
            # Existing development v6 files predate packet hardening. Additive
            # upgrade preserves every prior row and fails closed on legacy claims.
            for table, additions in {
                "application_packets": [("capacity_day", "VARCHAR"), ("writing_fingerprints", "JSON NOT NULL DEFAULT '{}'")],
                "writing_work_items": [("packet_id", "VARCHAR REFERENCES application_packets(id)"),
                    ("model", "VARCHAR NOT NULL DEFAULT ''"), ("system_hash", "VARCHAR NOT NULL DEFAULT ''"),
                    ("user_hash", "VARCHAR NOT NULL DEFAULT ''"), ("max_tokens", "INTEGER NOT NULL DEFAULT 0"),
                    ("output_hash", "VARCHAR"),
                    ("prompt_name", "VARCHAR NOT NULL DEFAULT ''"),
                    ("prompt_version", "VARCHAR NOT NULL DEFAULT ''"), ("failure_reason", "VARCHAR"),
                    ("updated_at", "DATETIME")],
            }.items():
                existing_columns = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}
                for name, declaration in additions:
                    if name not in existing_columns:
                        connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_application_packets_capacity_day ON application_packets(capacity_day)")
            connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS writing_packet_task ON writing_work_items(packet_id,task)")
            # Only legacy reservations lacking a date are backfilled from their
            # original claim timestamp, never moved to the migration/current day.
            from zoneinfo import ZoneInfo
            legacy = connection.exec_driver_sql(
                "SELECT id,created_at FROM application_packets WHERE capacity_day IS NULL AND status != 'research_incomplete'"
            ).all()
            for packet_id, created in (legacy if version < 7 else ()):
                claimed = datetime.fromisoformat(created).replace(tzinfo=timezone.utc)
                day = claimed.astimezone(ZoneInfo("America/New_York")).date().isoformat()
                connection.exec_driver_sql("UPDATE application_packets SET capacity_day=? WHERE id=?", (day, packet_id))
            connection.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS packet_capacity_day_immutable BEFORE UPDATE ON application_packets "
                "WHEN OLD.capacity_day IS NOT NULL AND (NEW.capacity_day IS NULL OR NEW.capacity_day != OLD.capacity_day) "
                "BEGIN SELECT RAISE(ABORT, 'capacity reservation is immutable'); END")
            # SQLite cannot add CHECK constraints in place. Equivalent triggers
            # protect upgraded v6 tables as well as fresh schema CHECK constraints.
            enums = {"application_packets": {
                "status": ("building", "packet_ready", "generation_failed", "research_incomplete", "recovery_required"),
                "cover_letter_acceptance": ("yes", "no", "unknown"),
                "verifier_status": ("not_run", "passed", "failed"), "lint_status": ("not_run", "passed", "failed")},
                "writing_work_items": {"state": ("in_progress", "succeeded", "failed", "recovery_required")}}
            for table, fields in enums.items():
                for name, choices in fields.items():
                    literals = ",".join("'" + choice + "'" for choice in choices)
                    for operation in ("INSERT", "UPDATE"):
                        connection.exec_driver_sql(
                            f"CREATE TRIGGER IF NOT EXISTS {table}_{name}_{operation.lower()} "
                            f"BEFORE {operation} ON {table} WHEN NEW.{name} IS NULL OR NEW.{name} NOT IN ({literals}) "
                            "BEGIN SELECT RAISE(ABORT, 'invalid safety state'); END")
            for operation in ("INSERT", "UPDATE"):
                connection.exec_driver_sql(
                    f"CREATE TRIGGER IF NOT EXISTS packet_ready_invariants_{operation.lower()} "
                    f"BEFORE {operation} ON application_packets WHEN NEW.status='packet_ready' AND "
                    "(NEW.verifier_status!='passed' OR NEW.lint_status!='passed' OR length(NEW.cover_letter)=0 "
                    "OR length(NEW.scoring_fingerprint)=0 OR length(NEW.fingerprint)=0) "
                    "BEGIN SELECT RAISE(ABORT, 'invalid ready packet'); END")
            CompanyResearchCache.__table__.create(connection, checkfirst=True)
            # Enforce append-only history even for direct SQL/ORM callers.
            for operation in ("UPDATE", "DELETE"):
                connection.exec_driver_sql(
                    f"CREATE TRIGGER IF NOT EXISTS application_events_no_{operation.lower()} "
                    f"BEFORE {operation} ON application_events BEGIN "
                    "SELECT RAISE(ABORT, 'application_events is append-only'); END"
                )
            PacketDecision.__table__.create(connection, checkfirst=True)
            # SQLite length(TEXT) stops at embedded NUL. Count UTF-8 leading
            # bytes for that exceptional case so the Unicode bound also holds
            # for direct SQL, without excluding accepted original feedback.
            connection.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS packet_decisions_detail_length BEFORE INSERT ON packet_decisions "
                "WHEN instr(NEW.detail,char(0)) > 0 BEGIN "
                "WITH RECURSIVE counter(body,pos,n) AS ("
                "SELECT hex(CAST(NEW.detail AS BLOB)),1,0 UNION ALL "
                "SELECT body,pos+2,n+(substr(body,pos,1) NOT IN ('8','9','A','B')) FROM counter "
                "WHERE pos<=length(body) AND n<=4000) "
                "SELECT RAISE(ABORT,'decision detail exceeds 4000 characters') FROM counter WHERE n>4000; END")
            for operation in ("UPDATE", "DELETE"):
                connection.exec_driver_sql(
                    f"CREATE TRIGGER IF NOT EXISTS packet_decisions_no_{operation.lower()} "
                    f"BEFORE {operation} ON packet_decisions BEGIN "
                    "SELECT RAISE(ABORT, 'packet_decisions is append-only'); END")
            _install_style_revision_schema(connection, original_version=version)
            connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
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
