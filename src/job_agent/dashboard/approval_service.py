"""Read adapters over trusted packet/approval services; no generation machinery."""
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import func, or_
from sqlmodel import Session, select

from job_agent.approvals import ApprovalService, DecisionError
from job_agent.database import (ApplicationPacket, CompanyFactRecord, PacketDecision,
                                PacketRevisionWork, SearchResult)
from job_agent.packet_history import (authenticated_cover_text, authenticated_resume_pdf,
                                     diff_cover, diff_resume, list_packet_versions)
from job_agent.packets import _validate_application_url, private_packet_logs
from job_agent.store import resolve_apply_url
from job_agent.dashboard.approval_models import (
    ApplicationDestination, ApprovalPreview, ArtifactMetadata, CompanyFact,
    DecisionDetail, DecisionResult, HistoryItem, PacketDetail, PacketDiffResult,
    QueueItem, QueueResponse, RevisionStatus, Screening,
    ScreeningAnswer,
)
from job_agent.dashboard.approval_security import AdapterError, probe_packet_lock


def timestamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def safe_url(value):
    try:
        return _validate_application_url(value)
    except (ValueError, TypeError):
        return None


def strings(value):
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


REVISION_LABELS = {
    "none": "No revision requested",
    "queued": "Revision queued; awaiting worker",
    "pending": "Preparing revision",
    "style_prepared": "Saving revision preferences",
    "style_persisted": "Preparing new packet",
    "building": "Generating revision",
    "succeeded": "Revision ready; open successor",
    "blocked": "Revision needs attention",
    "recovery_required": "Manual recovery required",
}


class ApprovalQueueService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.approvals = ApprovalService(engine, settings)

    def _revision_summary(self, session, packet_id):
        decision = session.exec(select(PacketDecision.id, PacketDecision.created_at).where(
            PacketDecision.packet_id == packet_id, PacketDecision.decision == "revise")).one_or_none()
        work = session.get(PacketRevisionWork, decision.id) if decision else None
        successor = session.exec(select(ApplicationPacket.id, ApplicationPacket.version, ApplicationPacket.status).where(
            ApplicationPacket.id == work.successor_packet_id)).one_or_none() if work and work.successor_packet_id else None
        state = work.state if work else "queued" if decision else "none"
        # Allowlisted display category only. No stored raw provider/failure text.
        categories = {"budget_blocked": "budget", "current_candidate_inputs_invalid": "candidate_inputs",
            "current_candidate_inputs_changed": "candidate_inputs", "source_evidence_invalid": "source_evidence",
            "successor_integrity_failed": "integrity", "writing_recovery_required": "manual_recovery"}
        return RevisionStatus(source_packet_id=packet_id, decision_id=decision.id if decision else None,
            state=state, label=REVISION_LABELS[state],
            updated_at=timestamp(work.updated_at) if work else timestamp(decision.created_at) if decision else None,
            successor_packet_id=successor.id if successor else None,
            successor_version=successor.version if successor else None,
            successor_status=successor.status if successor else None,
            failure_category=categories.get(work.failure_code, "manual_review") if work and state in {"blocked", "recovery_required"} else None)

    @private_packet_logs()
    def revision_status(self, packet_id):
        with Session(self.engine) as session:
            session.connection().exec_driver_sql("BEGIN")
            if session.exec(select(ApplicationPacket.id).where(ApplicationPacket.id == packet_id)).first() is None:
                raise AdapterError("not_found", 404)
            return self._revision_summary(session, packet_id)

    @private_packet_logs()
    def decision_detail(self, packet_id):
        with Session(self.engine) as session:
            row = session.exec(select(PacketDecision.id, PacketDecision.decision, PacketDecision.created_at,
                PacketDecision.reason_code, PacketDecision.detail).where(PacketDecision.packet_id == packet_id)).one_or_none()
            if row is None:
                raise AdapterError("not_found", 404)
            return DecisionDetail(decision_id=row.id, decision=row.decision, created_at=timestamp(row.created_at),
                reason_code=row.reason_code if row.decision == "reject" else None,
                detail=row.detail if row.decision == "reject" else None,
                feedback=row.detail if row.decision == "revise" else None)

    @private_packet_logs()
    def packet_diff(self, left_id, right_id, kind):
        function = diff_resume if kind == "resume" else diff_cover
        result = function(self.engine, self.settings, left_id, right_id)
        if result.status == "invalid_request":
            raise AdapterError("invalid_request", 422)
        with Session(self.engine) as session:
            rows = session.exec(select(ApplicationPacket.id, ApplicationPacket.version).where(
                ApplicationPacket.id.in_((left_id, right_id)))).all()
        versions = {r.id: r.version for r in rows}
        if left_id not in versions or right_id not in versions:
            raise AdapterError("not_found", 404)
        return PacketDiffResult(kind=kind, left_packet_id=left_id, left_version=versions[left_id],
            right_packet_id=right_id, right_version=versions[right_id], status=result.status, diff=result.diff)

    def resume_pdf(self, packet_id):
        return authenticated_resume_pdf(self.engine, self.settings, packet_id)

    def application_destination(self, packet_id):
        # Same coherent exact preview/current approval validation as detail.
        return self.detail(packet_id).application_destination

    @private_packet_logs()
    def approve(self, packet_id, body):
        probe_packet_lock(self.settings)
        # Never preview or refresh either expected token during a POST.
        record = self.approvals.approve(packet_id, body.expected_packet_fingerprint,
                                       body.expected_approval_view_fingerprint)
        return self._decision_result(record)

    @private_packet_logs()
    def reject(self, packet_id, body):
        probe_packet_lock(self.settings)
        record = self.approvals.reject(packet_id, body.expected_packet_fingerprint,
                                      body.reason_code, body.detail)
        return self._decision_result(record)

    @private_packet_logs()
    def revise(self, packet_id, body):
        probe_packet_lock(self.settings)
        # Only durable decision creation. No processor, style write or generation.
        record = self.approvals.revise(packet_id, body.expected_packet_fingerprint, body.feedback)
        return self._decision_result(record)

    def _decision_result(self, record):
        with Session(self.engine) as session:
            packet = session.exec(select(ApplicationPacket.version, ApplicationPacket.fingerprint).where(
                ApplicationPacket.id == record.packet_id)).one_or_none()
        if packet is None:
            raise AdapterError("not_found", 404)
        authorization, checked_at = "not_approved", None
        if record.decision == "approve":
            authorization = "not_checked"
            try:
                probe_packet_lock(self.settings)
                self.approvals.validate_approval_for_packet(record.packet_id, record.packet_fingerprint)
                authorization = "currently_valid"
                checked_at = timestamp(datetime.now(timezone.utc))
            except AdapterError as exc:
                if exc.code != "packet_busy":
                    raise
                # Decision already committed. Report history without asserting validity.
            except DecisionError as exc:
                if str(exc) == "approval_evidence_changed":
                    authorization = "evidence_changed"
                elif str(exc) == "packet_integrity_failed":
                    authorization = "integrity_failed"
                elif str(exc) not in {"stale_packet_fingerprint", "packet_not_approved"}:
                    raise
        if packet.fingerprint != record.packet_fingerprint:
            authorization = "not_checked"
        return DecisionResult(decision_id=record.id, packet_id=record.packet_id,
            packet_version=packet.version, decision=record.decision, created_at=timestamp(record.created_at),
            historical_state={"approve": "approved_historically", "reject": "rejected", "revise": "revision_requested"}[record.decision],
            current_authorization=authorization, current_authorization_checked_at=checked_at,
            revision_status_uri=f"/api/packets/{record.packet_id}/revision-status" if record.decision == "revise" else None,
            message="Creates a new packet version. The new version needs its own approval." if record.decision == "revise" else None)

    @private_packet_logs()
    def queue(self, query):
        p, d, w = ApplicationPacket, PacketDecision, PacketRevisionWork
        # Explicit card columns: never select cover, evidence, feedback or saved bank.
        statement = (select(p.id, p.version, p.company, p.title,
            func.json_extract(SearchResult.payload, "$.location").label("location"),
            p.score, p.tier, p.status, p.ready_at, p.cover_letter_acceptance,
            func.coalesce(func.json_array_length(p.screening_answers, "$.manual_needed"), 0).label("manual_count"),
            d.decision, w.state)
            .outerjoin(SearchResult, p.search_result_id == SearchResult.id)
            .outerjoin(d, p.id == d.packet_id).outerjoin(w, d.id == w.decision_id))
        active_revision = (d.decision == "revise") & or_(w.state.is_(None),
            w.state.in_(("pending", "style_prepared", "style_persisted", "building")))
        conditions = {
            "needs-review": (p.status == "packet_ready") & p.ready_at.is_not(None) & d.id.is_(None),
            "processing": ((p.status == "building") & d.id.is_(None)) | active_revision,
            "needs-attention": p.status.in_(("generation_failed", "research_incomplete", "recovery_required")) |
                ((d.decision == "revise") & w.state.in_(("blocked", "recovery_required"))),
            "history": d.id.is_not(None),
        }
        statement = statement.where(conditions[query.section])
        if query.section == "needs-review":
            statement = statement.order_by(p.score.desc(), p.ready_at.asc(), p.id.asc())
        else:
            statement = statement.order_by(p.updated_at.desc(), p.id.asc())
        statement = statement.limit(query.limit).offset(query.offset)
        with Session(self.engine) as session:
            rows = session.exec(statement).all()
            items = [QueueItem(packet_id=r.id, version=r.version, company=r.company,
                title=r.title, location=r.location if isinstance(r.location, str) else None,
                score=r.score, tier=r.tier, status=r.status, ready_at=timestamp(r.ready_at),
                cover_letter_acceptance=r.cover_letter_acceptance, manual_needed_count=r.manual_count,
                decision=r.decision, revision_state=(r.state or "queued") if r.decision == "revise" else None)
                for r in rows]
        return QueueResponse(section=query.section, limit=query.limit, offset=query.offset, items=items)

    @private_packet_logs()
    def history(self, packet_id):
        return [HistoryItem(**{key: row[key] for key in HistoryItem.model_fields})
                for row in list_packet_versions(self.engine, packet_id=packet_id)]

    def _projection(self, packet_id):
        """Capture a coherent DB-only read snapshot, closing it before build lock IO.

        The internal binding comparison is not an alternative approval identity.
        It conservatively reconciles all row/required detail semantics, including
        exact fact order, URL, screening and derived domain history.
        """
        history = self.history(packet_id)
        with Session(self.engine) as session:
            session.connection().exec_driver_sql("BEGIN")  # Read-only SQLite snapshot.
            packet = session.get(ApplicationPacket, packet_id)
            if packet is None:
                raise AdapterError("not_found", 404)
            row = session.get(SearchResult, packet.search_result_id)
            payload = row.payload if row else {}
            decision = session.exec(select(PacketDecision.id, PacketDecision.decision,
                PacketDecision.created_at).where(PacketDecision.packet_id == packet_id)).one_or_none()
            work = session.get(PacketRevisionWork, decision.id) if decision and decision.decision == "revise" else None
            revision = self._revision_summary(session, packet_id)
            facts, bound_facts = [], []
            for fact_id in packet.company_fact_ids:
                fact = session.get(CompanyFactRecord, fact_id)
                if fact is None:
                    bound_facts.append(None)
                    continue  # No invented/substituted fact; preview fails closed.
                bound_facts.append(fact.model_dump())
                facts.append(CompanyFact(text=fact.text, source_title=fact.source_title,
                                         source_url=safe_url(fact.source_url)))
            screening = packet.screening_answers
            answers = screening.get("answers", {})
            if not isinstance(answers, dict) or not isinstance(screening.get("manual_needed", []), list):
                raise AdapterError("packet_integrity_failed")
            cover = authenticated_cover_text(session, packet)
            artifact = packet.artifacts.get("resume.pdf")
            url = safe_url(resolve_apply_url(payload))
            detail = PacketDetail(packet_id=packet.id, version=packet.version,
                company=packet.company, title=packet.title, location=payload.get("location"),
                score=packet.score, tier=packet.tier, status=packet.status, ready_at=timestamp(packet.ready_at),
                expected_packet_fingerprint=packet.fingerprint,
                decision=decision.decision if decision else None, integrity="not_checked",
                current_authorization="not_checked" if decision and decision.decision == "approve" else "not_approved",
                reasons=strings(payload.get("reasons")), matched_requirements=strings(payload.get("matched_requirements")),
                missing_requirements=strings(payload.get("missing_requirements")),
                cover_letter_acceptance=packet.cover_letter_acceptance, cover_text=cover.text, cover_integrity=cover.status,
                screening=Screening(answers=[ScreeningAnswer(question=k, answer=v) for k, v in answers.items()],
                                    manual_needed=strings(screening.get("manual_needed"))),
                company_facts=facts, history=history, revision=revision,
                artifacts=[ArtifactMetadata(available=packet.ready_at is not None and isinstance(artifact, dict),
                    size=artifact.get("size") if isinstance(artifact, dict) else None)],
                application_destination=ApplicationDestination(url=url, domain=urlsplit(url).hostname if url else None,
                    authorization="not_checked" if decision and decision.decision == "approve" else "not_approved"),
                approval_preview=None)
            # Kept only in Python memory for reconciliation; never serialized to API.
            bindings = {"packet": packet.model_dump(), "payload": payload, "facts": bound_facts,
                "decision": tuple(decision) if decision else None,
                "work": work.model_dump() if work else None,
                "detail": detail.model_dump()}
        return detail, bindings

    @private_packet_logs()
    def detail(self, packet_id):
        before, bindings = self._projection(packet_id)
        preview = None
        authorization, integrity = before.current_authorization, before.integrity
        eligible = before.status == "packet_ready" and before.ready_at is not None
        if eligible and before.decision is None:
            probe_packet_lock(self.settings)
            try:
                result = self.approvals.preview_approval(packet_id, before.expected_packet_fingerprint)
            except DecisionError as exc:
                if str(exc) != "packet_integrity_failed":
                    raise
                result, integrity = None, "failed"
            if result is not None and (result.packet_id != packet_id or result.packet_version != before.version
                    or result.packet_fingerprint != before.expected_packet_fingerprint
                    or result.application_url != before.application_destination.url):
                raise AdapterError("stale_packet")
            if result is not None:
                preview = ApprovalPreview(packet_id=result.packet_id, packet_version=result.packet_version,
                    expected_packet_fingerprint=result.packet_fingerprint,
                    expected_approval_view_fingerprint=result.approval_view_fingerprint,
                    application_url=result.application_url)
                integrity = "passed"
        elif before.decision == "approve":
            probe_packet_lock(self.settings)
            try:
                self.approvals.validate_approval_for_packet(packet_id, before.expected_packet_fingerprint)
                authorization, integrity = "currently_valid", "passed"
            except DecisionError as exc:
                if str(exc) == "approval_evidence_changed":
                    authorization, integrity = "evidence_changed", "passed"
                elif str(exc) == "packet_integrity_failed":
                    authorization, integrity = "integrity_failed", "failed"
                else:
                    raise
        after, current = self._projection(packet_id)
        if bindings != current:
            raise AdapterError("stale_packet")
        after.approval_preview = preview
        after.integrity, after.current_authorization = integrity, authorization
        after.application_destination.authorization = authorization
        if before.decision is None and preview is None:
            after.application_destination.url = after.application_destination.domain = None
        return after
