"""Typed, immutable domain models.

Every ATS source normalizes its raw JSON into a :class:`Job`. The scorer wraps a
``Job`` into a :class:`ScoredJob`. Both are frozen (immutable) — code creates new
objects rather than mutating existing ones.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The ATS/board a job came from. The last four are cross-company search
# sources (keyword-driven), not per-company boards.
SourceName = Literal["greenhouse", "lever", "ashby", "smartrecruiters", "demo",
                     "sr-search", "remotive", "remoteok", "freehire",
                     "simplify-newgrad", "simplify-internships"]

# The scorer's verdict. "unscored" is a distinct state used when the LLM output
# could not be parsed even after one retry (see scoring.py).
Verdict = Literal["strong", "possible", "skip", "unscored"]


class Job(BaseModel):
    """A single job posting, normalized across all ATS sources."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Stable per-source id (source-scoped, not global).")
    title: str
    company: str
    location: str = Field(description="Human-readable location, e.g. 'Remote' or 'Austin, TX'.")
    url: str = Field(description="Public posting URL a human can open.")
    source: SourceName
    apply_url: str | None = None
    # Timezone-aware. None when the source exposes no post date and no cache hit
    # exists yet (see seen_cache.py for the fallback used by the 24h filter).
    posted_at: datetime | None = None
    remote: bool | None = None
    # Best-effort country marker for the location rule; None when unknown.
    country: str | None = None
    # Employer assistance, distinct from a requirement to relocate.
    relocation: Literal["supported", "not_supported", "required"] | None = None
    visa_sponsorship: bool | None = None
    description: str = ""

    def dedup_key(self) -> str:
        """Canonical identity used to drop duplicates across boards/re-runs."""
        # README resemblance is not a verified canonical relationship. Keep
        # these offline adapters source-scoped until Run 6B durable dedupe.
        if self.source in ("simplify-newgrad", "simplify-internships"):
            return f"{self.source}:{self.id}"
        return "|".join([self.company.strip().lower(), self.title.strip().lower(),
                          self.location.strip().lower()])


class ScoredJob(BaseModel):
    """A :class:`Job` plus the LLM's fit assessment."""

    model_config = ConfigDict(frozen=True)

    job: Job
    # 0-100 fit score; None when the job could not be scored (verdict == "unscored").
    score: int | None = Field(default=None, ge=0, le=100)
    verdict: Verdict = "unscored"
    reasons: tuple[str, ...] = ()
    missing_requirements: tuple[str, ...] = ()
    matched_requirements: tuple[str, ...] = ()
    target_tier: Literal["A", "B", "C", "other"] = "other"
    content_flags: tuple[str, ...] = ()

    @property
    def sort_key(self) -> tuple[int, int]:
        """Rank strong > possible > skip > unscored, then by score (desc)."""
        verdict_rank = {"strong": 3, "possible": 2, "skip": 1, "unscored": 0}
        return (verdict_rank[self.verdict], self.score if self.score is not None else -1)


class IntakeModel(BaseModel):
    """Versioned untrusted-source evidence, separate from scoring truth."""
    model_config = ConfigDict(frozen=True, extra="forbid")


class IntakeLink(IntakeModel):
    cell: str = Field(max_length=32)
    original_url: str = Field(max_length=2048)
    normalized_url: str = Field(max_length=2048)
    label: str = Field(max_length=512)
    kind: Literal["employer_posting", "employer_application", "source_role", "source_navigation", "other"]
    # An extracted Simplify UUID is link evidence, never a proven upstream ID.
    link_identity_evidence: str | None = Field(default=None, max_length=128)


class IntakeTransformation(IntakeModel):
    field: str = Field(max_length=32)
    operation: str = Field(max_length=64)
    original: str | None = Field(default=None, max_length=16384)
    normalized: str | None = Field(default=None, max_length=2048)


class IntakeOccurrence(IntakeModel):
    locator: str = Field(max_length=128)
    raw_record: str = Field(max_length=16384)
    category: str | None = Field(default=None, max_length=512)
    lane: str = Field(min_length=1, max_length=128)
    observed_at: datetime
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision: str | None = Field(default=None, max_length=128)
    parser_version: str = Field(default="simplify-readme-v1", max_length=64)
    adapter_version: str = Field(default="simplify-offline-v1", max_length=64)
    snapshot_completeness: Literal["complete", "partial"] = "complete"
    normalized_fields: dict[str, str | bool | None]
    relative_age: str | None = Field(default=None, max_length=128)
    links: tuple[IntakeLink, ...] = ()
    inherited_fields: tuple[str, ...] = ()
    inherited_from: dict[str, str] = Field(default_factory=dict)
    transformations: tuple[IntakeTransformation, ...] = ()
    labels: tuple[str, ...] = ()


class IntakeEvidence(IntakeModel):
    evidence_version: Literal["intake-v1"] = "intake-v1"
    source_namespace: Literal["simplify-newgrad", "simplify-internships"]
    repository: str = Field(max_length=128)
    document: Literal["README.md"] = "README.md"
    source_url: str = Field(max_length=2048)
    lane: str = Field(min_length=1, max_length=128)
    source_family: Literal["newgrad", "internships"]
    observed_at: datetime
    revision: str | None = Field(default=None, max_length=128)
    parser_version: str = Field(max_length=64)
    adapter_version: str = Field(default="simplify-offline-v1", max_length=64)
    snapshot_completeness: Literal["complete", "partial"] = "complete"
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_kind: Literal["derived_source_scoped"] = "derived_source_scoped"
    identity_version: Literal["simplify-link-v1"] = "simplify-link-v1"
    identity_basis: str = Field(max_length=2048)
    source_external_id: str = Field(max_length=128)
    occurrences: tuple[IntakeOccurrence, ...]
    links: tuple[IntakeLink, ...]
    normalized_fields: dict[str, str | bool | None]
    transformations: tuple[IntakeTransformation, ...]
    inherited_fields: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    source_classifications: tuple[str, ...] = ()
    local_classifications: tuple[str, ...] = ()
    content_flags: tuple[str, ...] = ()
    relative_age: str | None = Field(default=None, max_length=128)
    employment_type: str | None = Field(default=None, max_length=128)
    eligibility: None = None
    # Admission/reasons are populated by the later durable intake milestone.
    filter_disposition: Literal["pending", "kept", "rejected"] = "pending"
    filter_reasons: tuple[str, ...] = ()

    def merge_occurrences(self, other: IntakeEvidence) -> IntakeEvidence:
        """Keep the first candidate snapshot and every query/record occurrence."""
        if (self.source_namespace, self.source_external_id) != (other.source_namespace, other.source_external_id):
            raise ValueError("Cannot merge different source identities")
        return self.model_copy(update={
            "occurrences": self.occurrences + other.occurrences,
            "links": self.links + other.links,
            "transformations": self.transformations + other.transformations,
            "inherited_fields": tuple(sorted(set(self.inherited_fields + other.inherited_fields))),
            "labels": tuple(sorted(set(self.labels + other.labels))),
            "content_flags": tuple(sorted(set(self.content_flags + other.content_flags))),
        })

    @field_validator("observed_at")
    @classmethod
    def aware_observation(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Intake observation time must be timezone-aware")
        return value


class IntakeObservation(IntakeModel):
    job: Job
    evidence: IntakeEvidence


class IntakeIssue(IntakeModel):
    code: Literal["invalid_row", "unsafe_url", "missing_link", "ambiguous_links"]
    locator: str = Field(max_length=128)


class IntakeParseResult(IntakeModel):
    observations: tuple[IntakeObservation, ...]
    issues: tuple[IntakeIssue, ...] = ()
    completeness: Literal["complete", "partial"]
    rows_observed: int
    snapshot_sha256: str
