"""Read-only local packet metadata/diffs. Historical integrity is NOT approval.

No current candidate inputs, style file, research, OCR or provider calls. Resume
diffs use authenticated face bytes, with local PDF/DOCX consistency checks.
"""
from dataclasses import dataclass
from datetime import timezone
import difflib
import hashlib
import io
import os
from pathlib import Path
import re
import stat
import zipfile

from sqlmodel import Session, select

from job_agent.database import (ApplicationPacket, PacketDecision, WritingWorkItem, JobIdentity,
    LEGACY_WRITING_PROMPT_VERSION, STYLE_WRITING_PROMPT_VERSION)
from job_agent.packet_verify import CoverLetterDraft
from job_agent.packets import (PacketService, WRITING_LIMITS, digest, writing_fingerprint,
    private_packet_logs)

ARTIFACT_NAMES = frozenset({"resume.pdf", "resume.docx", "resume.face.txt"})
MAX_ARTIFACT_BYTES = 20_000_000
MAX_COVER_BYTES = 1_000_000


class HistoryError(ValueError):
    """Sanitized metadata error, never content or paths."""


class _ContentError(ValueError):
    pass


@dataclass(frozen=True)
class PacketDiff:
    status: str
    diff: str | None = None


@dataclass(frozen=True)
class PacketCover:
    status: str
    text: str | None = None


@private_packet_logs()
def authenticated_cover_text(session, packet):
    """Narrow historical cover view using the existing checkpoint authenticator.

    Caller owns a read snapshot. This is informational, never current approval.
    """
    if packet.ready_at is None:
        return PacketCover("unavailable")
    try:
        return PacketCover("available", _cover_text(session, packet))
    except _ContentError as exc:
        return PacketCover(str(exc))
    except Exception:
        return PacketCover("integrity_failed")


def _id(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _job_mapping(session):
    identities = session.exec(select(JobIdentity.source, JobIdentity.external_id, JobIdentity.job_id)).all()
    mapping = {}
    for identity in identities:
        key = f"{identity.source}:{identity.external_id}"
        if key in mapping and mapping[key] != identity.job_id:
            raise HistoryError("history_integrity_failed")
        mapping[key] = identity.job_id
    return mapping


def _canonical(packet, mapping):
    return packet.canonical_job_id or mapping.get(packet.job_key)


def _same_job(left, right, mapping=None):
    mapping = mapping or {}
    canonical = _canonical(left, mapping)
    return left.job_key == right.job_key or (canonical is not None and canonical == _canonical(right, mapping))


def _timestamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if value is not None else None


@private_packet_logs()
def list_packet_versions(engine, *, packet_id=None, job_key=None, canonical_job_id=None):
    """Select by exactly one stored packet/job relationship; no authorization check.

    Canonical aliases share history; older NULL-canonical packets with the same
    stored job key remain visible. No linkage is inferred from prose or paths.
    """
    if sum(value is not None for value in (packet_id, job_key, canonical_job_id)) != 1:
        raise HistoryError("invalid_history_reference")
    if (packet_id is not None and not _id(packet_id)) or any(
        value is not None and (not isinstance(value, str) or not value or len(value) > 1024)
        for value in (job_key, canonical_job_id)):
        raise HistoryError("invalid_history_reference")
    try:
        with Session(engine) as session:
            packets = list(session.exec(select(ApplicationPacket)).all())
            mapping = _job_mapping(session)
            seeds = [p for p in packets if (p.id == packet_id if packet_id is not None else
                p.job_key == job_key if job_key is not None else _canonical(p, mapping) == canonical_job_id)]
            if packet_id is not None and not seeds:
                raise HistoryError("packet_not_found")
            keys = {p.job_key for p in seeds}
            canonical = {_canonical(p, mapping) for p in seeds if _canonical(p, mapping) is not None}
            if job_key in mapping:
                canonical.add(mapping[job_key])
            rows = sorted((p for p in packets if p.job_key in keys or _canonical(p, mapping) in canonical),
                          key=lambda p: (p.version, p.id))
            # Only decision metadata is read; never feedback/evidence bodies.
            decisions = session.exec(select(PacketDecision.id, PacketDecision.packet_id,
                PacketDecision.decision, PacketDecision.packet_fingerprint)).all()
            if any(not _id(d.id) or not _id(d.packet_id) or not _hash(d.packet_fingerprint)
                   or d.decision not in {"approve", "reject", "revise"} for d in decisions):
                raise HistoryError("history_integrity_failed")
            by_id, by_packet = {d.id: d for d in decisions}, {d.packet_id: d for d in decisions}
            latest = rows[-1].id if rows else None
            ready = [p for p in rows if p.status == "packet_ready" and p.ready_at is not None]
            latest_ready = ready[-1].id if ready else None
            result = []
            for packet in rows:
                if (packet.writing_prompt_version not in {LEGACY_WRITING_PROMPT_VERSION, STYLE_WRITING_PROMPT_VERSION}
                        or (packet.writing_prompt_version == LEGACY_WRITING_PROMPT_VERSION) != (packet.style_memory_hash is None)
                        or packet.writing_prompt_version == LEGACY_WRITING_PROMPT_VERSION and packet.revision_decision_id is not None
                        or packet.status not in {"building", "packet_ready", "generation_failed", "research_incomplete", "recovery_required"}
                        or not _id(packet.id) or not _hash(packet.fingerprint)
                        or type(packet.version) is not int or packet.version < 1
                        or packet.style_memory_hash is not None and not _hash(packet.style_memory_hash)
                        or packet.revision_decision_id is not None and not _id(packet.revision_decision_id)):
                    raise HistoryError("history_integrity_failed")
                predecessor, kind = None, "unlinked"
                if packet.revision_decision_id is not None:
                    decision = by_id.get(packet.revision_decision_id)
                    source = next((p for p in rows if decision and p.id == decision.packet_id), None)
                    if (decision and decision.decision == "revise" and source and _same_job(source, packet, mapping)
                            and source.version < packet.version and source.fingerprint == decision.packet_fingerprint):
                        predecessor, kind = source.id, "revision"
                else:
                    matches = [p for p in rows if p.job_key == packet.job_key and p.version < packet.version
                        and p.ready_at is not None and packet.fingerprint == digest({
                            "recovery_of": p.id, "packet_fingerprint": p.fingerprint})]
                    if len(matches) == 1:
                        predecessor, kind = matches[0].id, "corruption_recovery"
                own_decision = by_packet.get(packet.id)
                result.append({"packet_id": packet.id, "version": packet.version,
                    "created_at": _timestamp(packet.created_at), "updated_at": _timestamp(packet.updated_at),
                    "ready_at": _timestamp(packet.ready_at), "status": packet.status,
                    "fingerprint": packet.fingerprint, "writing_prompt_version": packet.writing_prompt_version,
                    "style_memory_hash": packet.style_memory_hash, "revision_decision_id": packet.revision_decision_id,
                    "source_packet_id": predecessor, "lineage_kind": kind,
                    "decision": own_decision.decision if own_decision else None,
                    "is_latest_allocated": packet.id == latest, "is_latest_ready": packet.id == latest_ready})
            return result
    except HistoryError:
        raise
    except Exception:
        raise HistoryError("history_storage_error") from None


def _cover_text(session, packet):
    if not packet.cover_letter:
        raise _ContentError("unavailable")
    PacketService._bound_style(session, packet)  # Retained binding only, never current file.
    reference = packet.writing_fingerprints.get("cover_letter")
    work = session.get(WritingWorkItem, reference) if _hash(reference) else None
    if work is None or work.output is None:
        raise _ContentError("unavailable")
    if (work.task != "cover_letter" or work.state != "succeeded" or not isinstance(work.output, str)
            or not work.output or len(work.output.encode("utf-8")) > MAX_COVER_BYTES
            or not isinstance(packet.cover_letter, str) or len(packet.cover_letter.encode("utf-8")) > MAX_COVER_BYTES
            or work.output_hash != digest(work.output) or not _hash(work.system_hash) or not _hash(work.user_hash)
            or work.prompt_name != "cover_letter" or work.prompt_version != packet.writing_prompt_version
            or work.max_tokens != WRITING_LIMITS["cover_letter"] or not work.model
            or work.fingerprint != reference or work.fingerprint != writing_fingerprint(work.task, work.model,
                work.system_hash, work.user_hash, work.prompt_version, work.max_tokens)):
        raise _ContentError("integrity_failed")
    draft = CoverLetterDraft.model_validate_json(work.output)
    expected = "\n\n".join((draft.company_opening, " ".join(draft.candidate_lines), draft.closing))
    if draft.closing != "I would welcome a conversation about this role." or packet.cover_letter != expected:
        raise _ContentError("integrity_failed")
    # ready_at is historical completion evidence. Current truth/lint status can
    # change later; displaying intact historical text makes no policy assertion.
    return packet.cover_letter


def _resume_artifacts(settings, packet):
    if not packet.artifacts:
        raise _ContentError("unavailable")
    if not isinstance(packet.artifacts, dict) or set(packet.artifacts) != ARTIFACT_NAMES:
        raise _ContentError("integrity_failed")
    descriptors, contents = [], {}
    try:
        directory = Path(settings.data_dir).absolute()
        if directory.resolve() != directory:
            raise _ContentError("integrity_failed")
        data = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(data)
        root = os.open("packets", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=data)
        descriptors.append(root)
        published = os.open(packet.id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        descriptors.append(published)
        if set(os.listdir(published)) != ARTIFACT_NAMES:
            if not ARTIFACT_NAMES.issubset(os.listdir(published)):
                raise _ContentError("unavailable")
            raise _ContentError("integrity_failed")
        for name in sorted(ARTIFACT_NAMES):
            entry = packet.artifacts[name]
            if (not isinstance(entry, dict) or set(entry) != {"sha256", "size"} or not _hash(entry["sha256"])
                    or type(entry["size"]) is not int or not 0 < entry["size"] <= MAX_ARTIFACT_BYTES):
                raise _ContentError("integrity_failed")
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=published)
            try:
                before = os.fstat(descriptor)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != entry["size"]:
                    raise _ContentError("integrity_failed")
                with os.fdopen(os.dup(descriptor), "rb") as stream:
                    body = stream.read(MAX_ARTIFACT_BYTES + 1)
                after = os.fstat(descriptor)
                if ((before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                        (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                        or len(body) != entry["size"] or hashlib.sha256(body).hexdigest() != entry["sha256"]):
                    raise _ContentError("integrity_failed")
                contents[name] = body
            finally:
                os.close(descriptor)
        if not contents["resume.pdf"].startswith(b"%PDF-"):
            raise _ContentError("integrity_failed")
        with zipfile.ZipFile(io.BytesIO(contents["resume.docx"])) as archive:
            if (sum(item.file_size for item in archive.infolist()) > 100_000_000 or archive.testzip() is not None
                    or "word/document.xml" not in archive.namelist()):
                raise _ContentError("integrity_failed")
        face = contents["resume.face.txt"].decode("utf-8", errors="strict")
        checker = PacketService.__new__(PacketService)
        checker._verify_artifact_content(None, face, artifact_bytes=contents)
        return contents
    except FileNotFoundError:
        raise _ContentError("unavailable") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _resume_text(settings, packet):
    return _resume_artifacts(settings, packet)["resume.face.txt"].decode("utf-8", errors="strict")


@private_packet_logs()
def authenticated_resume_pdf(engine, settings, packet_id):
    """Return captured fixed PDF bytes using the existing historical reader.

    Never reopen a path for serving. Historical completion/integrity is not
    current approval. No caller filename/path or alternate artifact is accepted.
    """
    if not _id(packet_id):
        raise HistoryError("invalid_history_reference")
    try:
        with Session(engine) as session:
            packet = session.get(ApplicationPacket, packet_id)
            if packet is None:
                raise HistoryError("packet_not_found")
            if packet.ready_at is None:
                raise HistoryError("artifact_unavailable")
            if type(packet.version) is not int or packet.version < 1:
                raise HistoryError("artifact_integrity_failed")
            return packet.version, _resume_artifacts(settings, packet)["resume.pdf"]
    except HistoryError:
        raise
    except _ContentError as exc:
        raise HistoryError("artifact_unavailable" if str(exc) == "unavailable" else "artifact_integrity_failed") from None
    except Exception:
        raise HistoryError("artifact_integrity_failed") from None


def _unified(left, right, left_packet, right_packet):
    lines = difflib.unified_diff(left.splitlines(keepends=True), right.splitlines(keepends=True),
        fromfile=f"packet:{left_packet.id}/version:{left_packet.version}",
        tofile=f"packet:{right_packet.id}/version:{right_packet.version}", lineterm="\n")
    # Explicit missing-LF markers avoid accidentally joining two diff lines or
    # hiding a terminal-newline difference. Source text is never normalized.
    return "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines)


@private_packet_logs()
def _diff(engine, settings, left_packet_id, right_packet_id, kind):
    if not _id(left_packet_id) or not _id(right_packet_id):
        return PacketDiff("invalid_request")
    try:
        with Session(engine) as session:
            left, right = session.get(ApplicationPacket, left_packet_id), session.get(ApplicationPacket, right_packet_id)
            if left is None or right is None:
                return PacketDiff("unavailable")
            if any(type(p.version) is not int or p.version < 1 for p in (left, right)):
                return PacketDiff("integrity_failed")
            if not _same_job(left, right, _job_mapping(session)):
                return PacketDiff("invalid_request")
            if left.ready_at is None or right.ready_at is None:
                return PacketDiff("unavailable")
            if kind == "resume":
                before, after = _resume_text(settings, left), _resume_text(settings, right)
            else:
                before, after = _cover_text(session, left), _cover_text(session, right)
            return PacketDiff("available", _unified(before, after, left, right))
    except _ContentError as exc:
        return PacketDiff(str(exc))
    except Exception:
        return PacketDiff("integrity_failed")


def diff_resume(engine, settings, left_packet_id, right_packet_id):
    return _diff(engine, settings, left_packet_id, right_packet_id, "resume")


def diff_cover(engine, settings, left_packet_id, right_packet_id):
    return _diff(engine, settings, left_packet_id, right_packet_id, "cover")
