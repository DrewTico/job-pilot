"""LLM fit scoring.

Turns each surviving :class:`Job` into a :class:`ScoredJob` using the configured
scoring model. The public entry point is :func:`score_jobs`; the LLM call is
isolated behind :func:`score_one` so it can be swapped or mocked.

Reliability: the model is asked for strict JSON matching a fixed schema. We parse
defensively — on malformed output we retry once, and if it still fails the job is
marked ``verdict="unscored"`` rather than crashing the run.

NOTE (verification gate): the exact request shape (structured `output_config.format`
vs. tool-use) is confirmed by a one-off smoke test before this module is relied
on — see scripts/verify note in the README. Both request shapes are implemented
here; ``method`` selects which, defaulting to the verified path.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from typing import Any, Literal

from job_agent.config import SearchProfile, Settings
from job_agent.models import Job, ScoredJob

SCORE_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "score_v1.txt"


def load_score_prompt() -> str:
    return SCORE_PROMPT_PATH.read_text(encoding="utf-8")


class ScoreAssessment(BaseModel):
    """Strict model-response contract; legacy persisted objects use ScoredJob defaults."""
    model_config = ConfigDict(extra="forbid", strict=True)
    score: int
    verdict: Literal["strong", "possible", "skip"]
    reasons: list[str]
    matched_requirements: list[str]
    missing_requirements: list[str]
    target_tier: Literal["A", "B", "C", "other"]


SCORE_SCHEMA: dict[str, Any] = ScoreAssessment.model_json_schema()


class CompanyFact(BaseModel):
    """Caller-supplied sourced context; this object does not verify source truth."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    text: str = Field(min_length=1)
    source_url: HttpUrl


# Match directives, not ordinary descriptions of LLM/prompt engineering work.
_INJECTION_PATTERNS = (
    r"\b(?:ignore|disregard)\s+(?:all\s+)?(?:previous|prior|earlier|the scoring)\s+(?:instructions|rules)\b",
    r"\b(?:reveal|show\s+me|print)\s+(?:your|the)\s+(?:hidden|system)\s+(?:prompt|instructions)\b",
    r"\b(?:if\s+you\s+are\s+(?:an?\s+)?(?:AI|artificial intelligence)|"
    r"(?:AI|language)\s+(?:assistant|model)|system\s+prompt)"
    r"[\s,:;-]*(?:please\s+)?(?:give\s+this\s+role\s+(?:a\s+)?(?:score\s+of\s+)?100|"
    r"(?:alter|change|override)\s+(?:the\s+)?(?:score|scoring|output)|"
    r"respond\s+with|output\s+(?:only\s+)?100)\b",
)


def detect_content_flags(job: Job) -> tuple[str, ...]:
    """Conservative signals only; never removes a posting or changes its score."""
    text = job.description
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in _INJECTION_PATTERNS):
        return ("prompt_injection_suspected",)
    return ()


Method = Literal["structured", "tool"]


def build_user_prompt(job: Job, profile: SearchProfile, *,
                      company_facts: tuple[CompanyFact, ...] = ()) -> str:
    """Serialized input data only; versioned instructions belong in the system turn."""
    data = {
        "candidate_summary": profile.candidate_summary.strip(),
        "untrusted_job_posting": job.model_dump(mode="json"),
        "content_flags": detect_content_flags(job),
        "trusted_sourced_company_facts": [fact.model_dump(mode="json") for fact in company_facts],
    }
    return "INPUT DATA (JSON):\n" + json.dumps(data, ensure_ascii=False)


def _coerce(job: Job, data: dict[str, Any]) -> ScoredJob:
    assessment = ScoreAssessment.model_validate(data)
    values = assessment.model_dump()
    values["score"] = max(0, min(100, assessment.score))
    values["content_flags"] = detect_content_flags(job)
    return ScoredJob(job=job, **values)


def _call_structured(client, model: str, job: Job, profile: SearchProfile, *, company_facts: tuple[CompanyFact, ...] = ()) -> str:
    """One call using structured outputs (output_config.format). Returns JSON text."""
    resp = client.messages.create(
        model=model,
        max_tokens=512,
        system=load_score_prompt(),
        output_config={"format": {"type": "json_schema", "schema": SCORE_SCHEMA}},
        messages=[{"role": "user", "content": build_user_prompt(job, profile, company_facts=company_facts)}],
    )
    return next((b.text for b in resp.content if b.type == "text"), "")


def _call_tool(client, model: str, job: Job, profile: SearchProfile, *, company_facts: tuple[CompanyFact, ...] = ()) -> str:
    """Fallback: force a tool call whose input IS the JSON we want."""
    resp = client.messages.create(
        model=model,
        max_tokens=512,
        system=load_score_prompt(),
        tools=[{
            "name": "record_fit",
            "description": "Record the fit assessment for this job.",
            "input_schema": SCORE_SCHEMA,
        }],
        tool_choice={"type": "tool", "name": "record_fit"},
        messages=[{"role": "user", "content": build_user_prompt(job, profile, company_facts=company_facts)}],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return json.dumps(block.input)
    return ""


def score_one(
    client,
    model: str,
    job: Job,
    profile: SearchProfile,
    *,
    method: Method = "structured",
    company_facts: tuple[CompanyFact, ...] = (),
) -> ScoredJob:
    """Score a single job, retrying once on unparseable output before giving up."""
    call = _call_structured if method == "structured" else _call_tool
    for attempt in (1, 2):
        try:
            raw = call(client, model, job, profile, company_facts=company_facts)
            return _coerce(job, json.loads(raw))
        except Exception:
            if attempt == 2:
                # Give up gracefully: keep the job, mark it unscored.
                return ScoredJob(job=job, verdict="unscored",
                                 reasons=("LLM output could not be parsed",),
                                 content_flags=detect_content_flags(job))
    # Unreachable, but keeps type-checkers happy.
    return ScoredJob(job=job, verdict="unscored")


def score_jobs(
    jobs: list[Job],
    settings: Settings,
    profile: SearchProfile,
    *,
    method: Method = "structured",
    client=None,
) -> list[ScoredJob]:
    """Score every job. ``client`` is injectable for tests (defaults to the real
    Anthropic client, constructed lazily so importing this module needs no key)."""
    if client is None:
        import anthropic  # imported lazily so --demo / tests need no SDK key
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return [score_one(client, settings.scoring_model, job, profile, method=method) for job in jobs]
