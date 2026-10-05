"""Local immutable-Revise processing; no research, approval or submission capability.

SQLite preparation precedes filesystem publication. Retained base/target content
bridges their separate commits; unknown current style is never overwritten.
"""
from datetime import datetime, timezone

from sqlmodel import Session, select

from job_agent.database import (ApplicationPacket, PacketRevisionWork, WritingWorkItem,
    STYLE_WRITING_PROMPT_VERSION, _utc)
from job_agent.packets import (PacketService, _local_verifier, _revision_source,
    _retained_packet_evidence, revision_fingerprint, saved_answers,
    verify_packet_integrity, private_packet_logs, digest, writing_fingerprint)
from job_agent.style_memory import (StyleMemoryError, style_lock, append_feedback,
    ensure_style_snapshot, load_style_snapshot)


class RevisionError(ValueError):
    """Sanitized backend error; never contains feedback or provider details."""


class RevisionProcessor:
    def __init__(self, engine, settings, *, executor=None, clock=None):
        self.engine, self.settings, self.executor = engine, settings, executor
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _boundary(self, name):
        """Deterministic crash seam; no retries or external calls."""

    def _session(self):
        return Session(self.engine, expire_on_commit=False)

    def _fail(self, decision_id, code, *, recovery=False):
        with self._session() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            work = session.get(PacketRevisionWork, decision_id)
            if work is None or work.state == "succeeded":
                raise RevisionError(code)
            if work.state != "blocked":
                work.state = "recovery_required" if recovery else "blocked"
                work.failure_code, work.updated_at = code, _utc(self.clock())
                session.add(work)
            session.commit()
            return work

    @private_packet_logs()
    def process_revision(self, decision_id):
        # No constructor can instantiate a researcher; candidate loading happens
        # only AFTER feedback persistence so damaged source artifacts/inputs do
        # not prevent recording an accepted immutable revision request.
        lock_owner = PacketService.__new__(PacketService)
        lock_owner.engine, lock_owner.settings = self.engine, self.settings
        try:
            with lock_owner._build_lock(blocking=True):
                return self._process_locked(decision_id)
        except RevisionError:
            raise
        except Exception:
            raise RevisionError("revision_storage_error") from None

    def _process_locked(self, decision_id):
        try:
            with self._session() as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    decision, source = _revision_source(session, decision_id)
                except Exception:
                    raise RevisionError("invalid_revision_decision") from None
                work = session.get(PacketRevisionWork, decision_id)
                if work is None:
                    work = PacketRevisionWork(decision_id=decision_id,
                        created_at=_utc(self.clock()), updated_at=_utc(self.clock()))
                    session.add(work)
                session.commit()
            if work.state in ("blocked", "recovery_required"):
                return work  # Manual review, not an automatic provider retry.
            if work.state in ("pending", "style_prepared"):
                self._prepare_and_publish(decision, source, work)
            return self._build_successor(decision_id)
        except RevisionError:
            raise
        except StyleMemoryError as exc:
            code = str(exc)
            if code not in {"style_conflict", "style_too_large"}:
                code = "style_storage_error"
            return self._fail(decision_id, code)
        except Exception:
            # DB/filesystem uncertainty is not an invitation to reissue paid
            # work. Preserve durable identities and require local recovery.
            return self._fail(decision_id, "revision_storage_error", recovery=True)

    def _prepare_and_publish(self, decision, source, work):
        with style_lock(self.settings.data_dir, exclusive=True) as locked:
            if work.state == "pending":
                self._boundary("before_style_preparation")
                base = locked.read()
                target = append_feedback(base,
                    timestamp_utc=decision.created_at.replace(tzinfo=timezone.utc),
                    company=source.company, title=source.title,
                    source_packet_id=source.id, source_packet_version=source.version,
                    decision_id=decision.id, feedback=decision.detail)
                with self._session() as session:
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                    ensure_style_snapshot(session, base)
                    ensure_style_snapshot(session, target)
                    work = session.get(PacketRevisionWork, decision.id)
                    if work.state != "pending":
                        raise RevisionError("revision_state_invalid")
                    work.base_style_hash, work.target_style_hash = base.hash, target.hash
                    work.state, work.updated_at = "style_prepared", _utc(self.clock())
                    session.add(work)
                    session.commit()
                self._boundary("after_style_prepared")
            # Always reload retained immutable contents. Never append on retry.
            with self._session() as session:
                work = session.get(PacketRevisionWork, decision.id)
                base = load_style_snapshot(session, work.base_style_hash)
                target = load_style_snapshot(session, work.target_style_hash)
            locked.recover_prepared(base, target)
            self._boundary("after_style_publication")
            with self._session() as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                work = session.get(PacketRevisionWork, decision.id)
                work.state, work.updated_at = "style_persisted", _utc(self.clock())
                session.add(work)
                session.commit()
            self._boundary("after_style_persisted")

    def _build_successor(self, decision_id):
        try:
            builder = _local_verifier(self.engine, self.settings)
        except Exception:
            return self._fail(decision_id, "current_candidate_inputs_invalid")
        builder.executor, builder.clock = self.executor, self.clock
        builder._boundary = self._boundary
        # Evidence validation and identity allocation share one short DB snapshot.
        # No researcher/cache TTL read, provider call or filesystem publication.
        with self._session() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                decision, source = _revision_source(session, decision_id)
                work = session.get(PacketRevisionWork, decision_id)
                row, job, facts = _retained_packet_evidence(session, self.settings, source, builder)
                if not builder._eligible(session, row):
                    raise ValueError()
                # A retained successful cover request authenticates the exact
                # public evidence/order/job context, independently of its old
                # candidate SYSTEM content and potentially damaged artifacts.
                bound = source.writing_fingerprints.get("cover_letter")
                cover_work = session.get(WritingWorkItem, bound) if bound else None
                if (cover_work is None or cover_work.state != "succeeded" or cover_work.task != "cover_letter"
                        or cover_work.user_hash != digest(builder._company_writing_user(row, facts))
                        or cover_work.fingerprint != writing_fingerprint(cover_work.task, cover_work.model,
                            cover_work.system_hash, cover_work.user_hash, cover_work.prompt_version, cover_work.max_tokens)):
                    raise ValueError()
                style = load_style_snapshot(session, work.target_style_hash)
                context = builder._context(row, facts, prompt_version=STYLE_WRITING_PROMPT_VERSION, style=style)
                fingerprint = revision_fingerprint(source, decision, context)
            except Exception:
                session.rollback()
                return self._fail(decision_id, "source_evidence_invalid")
            if work.successor_packet_id is None:
                if work.state != "style_persisted":
                    raise RevisionError("revision_state_invalid")
                prior = session.exec(select(ApplicationPacket).where(ApplicationPacket.job_key == source.job_key)).all()
                packet = ApplicationPacket(job_key=source.job_key, search_result_id=source.search_result_id,
                    canonical_job_id=source.canonical_job_id, fingerprint=fingerprint,
                    scoring_fingerprint=source.scoring_fingerprint, version=max(p.version for p in prior)+1,
                    company=job.company, title=job.title, score=source.score, tier=source.tier,
                    writing_prompt_version=STYLE_WRITING_PROMPT_VERSION, style_memory_hash=style.hash,
                    revision_decision_id=decision.id, capacity_day=None, status="building",
                    company_fact_ids=list(source.company_fact_ids), content_flags=list(source.content_flags),
                    cover_letter_acceptance=context["acceptance"],
                    screening_answers=saved_answers(builder.bank, builder._required_questions(row)))
                session.add(packet)
                session.flush()
                work.successor_packet_id = packet.id
                work.state, work.updated_at = "building", _utc(self.clock())
                session.add(work)
            else:
                packet = session.get(ApplicationPacket, work.successor_packet_id)
                if packet is not None and packet.company_fact_ids != source.company_fact_ids:
                    session.rollback()
                    return self._fail(decision_id, "source_evidence_invalid")
                if packet is None or packet.fingerprint != fingerprint:
                    session.rollback()
                    return self._fail(decision_id, "current_candidate_inputs_changed")
            session.commit()
        self._boundary("after_successor_allocation")
        if packet.status != "packet_ready":
            packet = builder._assemble_claimed_packet(row, facts, context, packet)
        if packet.status != "packet_ready":
            with self._session() as session:
                writes = [session.get(WritingWorkItem, fp) for fp in packet.writing_fingerprints.values()]
                admission = any(w and w.failure_reason == "admission_denied" for w in writes)
            code = "budget_blocked" if admission else (
                "writing_recovery_required" if packet.status == "recovery_required" else "successor_generation_failed")
            return self._fail(decision_id, code, recovery=packet.status == "recovery_required")
        self._boundary("before_revision_succeeded")
        try:
            with self._session() as session:
                # Authenticate reread surviving publication, even after ready
                # commit or when a previously succeeded request is replayed.
                packet = session.get(ApplicationPacket, packet.id)
                verify_packet_integrity(session, self.settings, packet)
        except Exception:
            return self._fail(decision_id, "successor_integrity_failed", recovery=True)
        with self._session() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            work = session.get(PacketRevisionWork, decision_id)
            if work.state != "succeeded":
                work.state, work.failure_code = "succeeded", None
                work.updated_at = _utc(self.clock())
                session.add(work)
            session.commit()
            return work


def process_revision(engine, settings, decision_id, *, executor=None, clock=None):
    """Narrow entry point; feedback authority is ONLY an immutable Revise ID."""
    return RevisionProcessor(engine, settings, executor=executor, clock=clock).process_revision(decision_id)
