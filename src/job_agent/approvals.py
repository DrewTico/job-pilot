"""Local exact-packet decisions. No submission, regeneration or provider work."""
import fcntl
import json
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import dataclass

from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError
from job_agent.database import ApplicationPacket, PacketDecision
from job_agent.packets import digest, private_packet_logs, verify_packet_integrity

REJECT_REASONS = frozenset({"not_interested", "bad_fit", "company", "location", "pay", "other"})


class DecisionError(ValueError):
    """Sanitized domain failure, containing only a machine code."""


@dataclass(frozen=True)
class ValidatedApproval:
    decision_id: str
    packet_id: str
    packet_fingerprint: str
    evidence_version: int
    evidence_json: str


@dataclass(frozen=True)
class ApprovalPreview:
    packet_id: str
    packet_version: int
    packet_fingerprint: str
    approval_view_fingerprint: str
    application_url: str


def _view_fingerprint(evidence_json):
    return digest(json.loads(evidence_json))


@contextmanager
def _build_lock(settings):
    root = settings.data_dir.resolve() / "packets"
    # No mkdir or recovery. Reject/revise can survive missing deliverables; the
    # cooperating-process lock/root itself must remain present and trustworthy.
    if root.is_symlink() or not root.is_dir():
        raise DecisionError("packet_lock_unavailable")
    fd = None
    try:
        fd = os.open(root / ".build.lock", os.O_RDWR | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise DecisionError("packet_lock_unavailable")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    except OSError:
        raise DecisionError("packet_lock_unavailable") from None
    finally:
        if fd is not None:
            os.close(fd)


def _packet(session, packet_id, expected_packet_fingerprint):
    if not isinstance(packet_id, str) or not isinstance(expected_packet_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_packet_fingerprint):
        raise DecisionError("invalid_packet_reference")
    packet = session.get(ApplicationPacket, packet_id)
    if packet is None:
        raise DecisionError("packet_not_found")
    if packet.fingerprint != expected_packet_fingerprint:
        raise DecisionError("stale_packet_fingerprint")
    return packet


class ApprovalService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings

    def approve(self, packet_id, expected_packet_fingerprint, expected_approval_view_fingerprint):
        if (not isinstance(expected_approval_view_fingerprint, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected_approval_view_fingerprint)):
            raise DecisionError("stale_approval_view")
        return self._decide(packet_id, expected_packet_fingerprint, "approve", "", "", expected_approval_view_fingerprint)

    @private_packet_logs()
    def preview_approval(self, packet_id, expected_packet_fingerprint):
        try:
            with _build_lock(self.settings), Session(self.engine) as session:
                packet = _packet(session, packet_id, expected_packet_fingerprint)
                try:
                    evidence = verify_packet_integrity(session, self.settings, packet).evidence_json
                except ValueError:
                    raise DecisionError("packet_integrity_failed") from None
                return ApprovalPreview(packet.id, packet.version, packet.fingerprint,
                    _view_fingerprint(evidence), json.loads(evidence)["application_url"])
        except (SQLAlchemyError, UnicodeError):
            raise DecisionError("decision_storage_failed") from None

    def reject(self, packet_id, expected_packet_fingerprint, reason_code, detail=""):
        if not isinstance(reason_code, str) or reason_code not in REJECT_REASONS:
            raise DecisionError("invalid_reject_reason")
        self._detail(detail)
        return self._decide(packet_id, expected_packet_fingerprint, "reject", reason_code, detail)

    def revise(self, packet_id, expected_packet_fingerprint, feedback):
        self._detail(feedback)
        if not feedback.strip():
            raise DecisionError("revision_feedback_required")
        return self._decide(packet_id, expected_packet_fingerprint, "revise", "", feedback)

    @staticmethod
    def _detail(value):
        if not isinstance(value, str) or len(value) > 4000:
            raise DecisionError("invalid_decision_detail")

    @private_packet_logs()
    def _decide(self, packet_id, expected, decision, reason, detail, expected_view=None):
        try:
            return self._record_decision(packet_id, expected, decision, reason, detail, expected_view)
        except (SQLAlchemyError, UnicodeError):
            raise DecisionError("decision_storage_failed") from None

    @private_packet_logs()
    def _record_decision(self, packet_id, expected, decision, reason, detail, expected_view):
        with _build_lock(self.settings), Session(self.engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            packet = _packet(session, packet_id, expected)
            existing = session.exec(select(PacketDecision).where(PacketDecision.packet_id == packet.id)).one_or_none()
            if existing:
                if (existing.packet_fingerprint, existing.decision, existing.actor, existing.reason_code, existing.detail) != (expected, decision, "Andrew", reason, detail):
                    raise DecisionError("packet_decision_conflict")
                if decision == "approve" and _view_fingerprint(existing.evidence_json) != expected_view:
                    raise DecisionError("stale_approval_view")
                session.commit()
                return existing
            if decision == "approve":
                try:
                    evidence = verify_packet_integrity(session, self.settings, packet).evidence_json
                except ValueError:
                    raise DecisionError("packet_integrity_failed") from None
                if _view_fingerprint(evidence) != expected_view:
                    raise DecisionError("stale_approval_view")
            else:
                # Explicit audit snapshot, never an integrity assertion.
                evidence = json.dumps({"packet_version": packet.version, "packet_status": packet.status}, sort_keys=True, separators=(",", ":"))
            record = PacketDecision(packet_id=packet.id, packet_fingerprint=expected,
                decision=decision, reason_code=reason, detail=detail, evidence_json=evidence)
            session.add(record)
            session.flush()
            session.commit()
            return record

    @private_packet_logs()
    def validate_approval_for_packet(self, packet_id, expected_packet_fingerprint):
        with _build_lock(self.settings), Session(self.engine) as session:
            packet = _packet(session, packet_id, expected_packet_fingerprint)
            record = session.exec(select(PacketDecision).where(PacketDecision.packet_id == packet.id)).one_or_none()
            if (record is None or record.decision != "approve" or record.actor != "Andrew"
                    or record.evidence_version != 1 or record.packet_fingerprint != packet.fingerprint):
                raise DecisionError("packet_not_approved")
            try:
                evidence = verify_packet_integrity(session, self.settings, packet).evidence_json
            except ValueError:
                raise DecisionError("packet_integrity_failed") from None
            if evidence != record.evidence_json:
                raise DecisionError("approval_evidence_changed")
            return ValidatedApproval(record.id, packet.id, packet.fingerprint, 1, evidence)


def validate_approval_for_packet(engine, settings, packet_id, expected_packet_fingerprint):
    return ApprovalService(engine, settings).validate_approval_for_packet(packet_id, expected_packet_fingerprint)
