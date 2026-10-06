"""Explicit local approval projections. Authority tokens are opaque to clients."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


Section = Literal["needs-review", "processing", "needs-attention", "history"]
PacketState = Literal["building", "packet_ready", "generation_failed", "research_incomplete", "recovery_required"]
DecisionType = Literal["approve", "reject", "revise"]
AuthorizationState = Literal["not_approved", "currently_valid", "evidence_changed", "integrity_failed", "not_checked"]
Fingerprint = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]


class QueueQuery(DTO):
    section: Section = "needs-review"
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=1_000_000)


class QueueItem(DTO):
    packet_id: str
    version: int
    company: str
    title: str
    location: str | None
    score: int
    tier: str
    status: PacketState
    ready_at: str | None
    cover_letter_acceptance: Literal["yes", "no", "unknown"]
    manual_needed_count: int
    decision: DecisionType | None
    revision_state: str | None
    integrity: Literal["not_checked"] = "not_checked"


class QueueResponse(DTO):
    section: Section
    limit: int
    offset: int
    items: list[QueueItem]


class ApprovalPreview(DTO):
    packet_id: str
    packet_version: int
    expected_packet_fingerprint: str
    expected_approval_view_fingerprint: str
    application_url: str


class ArtifactMetadata(DTO):
    kind: Literal["resume_pdf"] = "resume_pdf"
    available: bool
    size: int | None = None


class CompanyFact(DTO):
    text: str
    source_title: str
    source_url: str | None


class ScreeningAnswer(DTO):
    question: str
    answer: str | bool | int | float | None


class Screening(DTO):
    answers: list[ScreeningAnswer]
    manual_needed: list[str]


class HistoryItem(DTO):
    packet_id: str
    version: int
    status: PacketState
    created_at: str | None
    updated_at: str | None
    ready_at: str | None
    decision: DecisionType | None
    revision_decision_id: str | None
    source_packet_id: str | None
    lineage_kind: Literal["unlinked", "revision", "corruption_recovery"]
    is_latest_allocated: bool
    is_latest_ready: bool


class RevisionStatus(DTO):
    source_packet_id: str
    decision_id: str | None
    state: str
    label: str
    updated_at: str | None = None
    successor_packet_id: str | None = None
    successor_version: int | None = None
    successor_status: PacketState | None = None
    failure_category: str | None = None


class ApplicationDestination(DTO):
    url: str | None
    domain: str | None
    authorization: Literal["not_approved", "currently_valid", "evidence_changed", "integrity_failed", "not_checked"]


class PacketDetail(DTO):
    packet_id: str
    version: int
    company: str
    title: str
    location: str | None
    score: int
    tier: str
    status: PacketState
    ready_at: str | None
    expected_packet_fingerprint: str
    decision: DecisionType | None
    integrity: Literal["passed", "failed", "not_checked"]
    current_authorization: Literal["not_approved", "currently_valid", "evidence_changed", "integrity_failed", "not_checked"]
    reasons: list[str]
    matched_requirements: list[str]
    missing_requirements: list[str]
    cover_letter_acceptance: Literal["yes", "no", "unknown"]
    cover_text: str | None
    cover_integrity: Literal["available", "unavailable", "integrity_failed"]
    screening: Screening
    company_facts: list[CompanyFact]
    history: list[HistoryItem]
    revision: RevisionStatus
    artifacts: list[ArtifactMetadata]
    application_destination: ApplicationDestination
    approval_preview: ApprovalPreview | None


class DecisionResult(DTO):
    decision_id: str
    packet_id: str
    packet_version: int
    decision: DecisionType
    created_at: str
    historical: bool = True
    historical_state: Literal["approved_historically", "rejected", "revision_requested"]
    current_authorization: AuthorizationState
    current_authorization_checked_at: str | None = None
    revision_status_uri: str | None = None
    message: str | None = None


class ApproveRequest(DTO):
    expected_packet_fingerprint: Fingerprint
    expected_approval_view_fingerprint: Fingerprint


class RejectRequest(DTO):
    expected_packet_fingerprint: Fingerprint
    reason_code: Literal["not_interested", "bad_fit", "company", "location", "pay", "other"]
    detail: str = Field(default="", strict=True, max_length=4000)


class ReviseRequest(DTO):
    expected_packet_fingerprint: Fingerprint
    feedback: str = Field(strict=True, max_length=4000)


class DecisionDetail(DTO):
    decision_id: str
    decision: DecisionType
    created_at: str
    reason_code: str | None = None
    detail: str | None = None
    feedback: str | None = None


class PacketDiffResult(DTO):
    kind: Literal["resume", "cover"]
    left_packet_id: str
    left_version: int
    right_packet_id: str
    right_version: int
    status: Literal["available", "unavailable", "integrity_failed"]
    diff: str | None = None


class ErrorDetail(DTO):
    code: str


class ErrorResponse(DTO):
    error: ErrorDetail


class BootstrapResponse(DTO):
    csrf_token: str
    local_only: bool = True
    origin: str
