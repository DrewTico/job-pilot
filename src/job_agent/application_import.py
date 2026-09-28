"""Explicit opt-in import of legacy applications.json; never used by production.

Validate the entire input before a serialized, atomic write. Original payloads
retain missing fields and unknown extra fields. A record's semantic hash plus
its duplicate ordinal deduplicates unchanged records even in changed files.
Changed snapshots (including changes to one attempt) append evidence, not a
claim that a new submission occurred. Provenance describes the first import.

Legacy dates are attempt dates, not reliable dashboard edit timestamps. Newer
record dates win current state; equal dates use the last newly imported record.
Replay never updates current state or retroactively remaps unresolved evidence.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import select

from job_agent.apply.tracker import ApplicationRecord
from job_agent.database import ApplicationEvent, CanonicalJob, JobIdentity, _utc, database_session


@dataclass
class ApplicationImportReport:
    imported: int = 0
    skipped: int = 0
    unresolved: list[str] = field(default_factory=list)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f'Invalid JSON constant: {value}')


def _occurred_at(value):
    # Date-only evidence retains its precision in legacy_date/payload. Midnight
    # is only an ordering convention. Datetimes must declare their timezone.
    if len(value) == 10:
        return datetime.combine(date.fromisoformat(value), datetime.min.time())
    return _utc(datetime.fromisoformat(value))


def import_applications(engine: Engine, *, applications: str | Path) -> ApplicationImportReport:
    """Import one explicit path, raising on missing, corrupt or invalid input.

    No canonical jobs/identities are created. Exact source + external ID is the
    only mapping evidence; absent or unattached identities remain unresolved.
    """
    raw = Path(applications).read_bytes()
    data = json.loads(raw, object_pairs_hook=_object, parse_constant=_invalid_constant)
    if not isinstance(data, list):
        raise ValueError('Expected an applications array')
    validated = []
    for index, payload in enumerate(data):
        if not isinstance(payload, dict):
            raise ValueError(f'Application record {index}: expected an object')
        record = ApplicationRecord.model_validate(payload, strict=True)
        validated.append((payload, record, _occurred_at(record.date)))
    file_hash = hashlib.sha256(raw).hexdigest()
    report = ApplicationImportReport()
    counts = Counter()
    with database_session(engine) as session:
        # Serialize the deduplication check and insert across concurrent imports.
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        for index, (payload, record, occurred) in enumerate(validated):
            digest = hashlib.sha256(json.dumps(
                payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
            ).encode()).hexdigest()
            ordinal = counts[digest]
            counts[digest] += 1
            key = f'applications.json:v1:{digest}:{ordinal}'
            existing = session.exec(select(ApplicationEvent).where(
                ApplicationEvent.import_key == key)).one_or_none()
            if existing:
                report.skipped += 1
                if existing.unresolved:
                    report.unresolved.append(f'{index}: {existing.unresolved}')
                continue
            matches = []
            if record.source and record.job_id:
                matches = session.exec(select(JobIdentity).where(
                    JobIdentity.source == record.source,
                    JobIdentity.external_id == record.job_id,
                )).all()
            job_id = matches[0].job_id if len(matches) == 1 else None
            problem = None if job_id else 'Missing, ambiguous or unattached source-scoped identity'
            kind = 'attempt' if record.status in ('submitted', 'paused', 'failed') else 'pipeline'
            session.add(ApplicationEvent(
                import_key=key, job_id=job_id, external_job_id=record.job_id,
                source=record.source, company=record.company, title=record.title,
                attempt_id=record.attempt_id, status=record.status, status_kind=kind,
                reason=record.reason, notes=record.notes, follow_up=record.follow_up,
                occurred_at=occurred, legacy_date=record.date,
                provenance='legacy_applications_snapshot', file_sha256=file_hash,
                record_index=index, unresolved=problem, payload=payload,
            ))
            if job_id:
                job = session.get(CanonicalJob, job_id)
                if job.application_updated_at is None or occurred >= job.application_updated_at:
                    job.application_status = record.status
                    job.application_status_kind = kind
                    job.application_notes = record.notes
                    job.application_follow_up = record.follow_up
                    job.application_updated_at = occurred
                    session.add(job)
            else:
                report.unresolved.append(f'{index}: {problem}')
            session.flush()
            report.imported += 1
    return report
