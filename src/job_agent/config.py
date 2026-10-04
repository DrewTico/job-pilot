"""Configuration loading and validation.

Two things live here:

* :class:`SearchProfile` — the validated contents of ``search_profile.yaml``
  (roles, location rule, boards to fetch). Validated with Pydantic so a
  malformed profile fails fast with a clear message instead of deep in a fetch.
* :class:`Settings` — runtime bits from the environment (API key, model, paths).
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from job_agent.seniority import LEVEL_NAMES

# Retained for legacy callers; task-specific defaults are defined in Settings.
DEFAULT_MODEL = "claude-haiku-4-5"

SourceName = str  # validated against the known set below


class SourceRef(BaseModel):
    """One board to fetch: which ATS, and the board/company identifier."""

    ats: str
    board: str

    model_config = {"extra": "forbid"}


class LocationRule(BaseModel):
    remote_ok: bool = True
    allowed_countries: list[str] = Field(default_factory=lambda: ["US"])

    model_config = {"extra": "forbid"}


class SearchProfile(BaseModel):
    """Validated ``search_profile.yaml``."""

    keywords: list[str] = Field(min_length=1)
    location: LocationRule = Field(default_factory=LocationRule)
    sources: list[SourceRef] = Field(min_length=1)
    candidate_summary: str = ""
    # Optional seniority ceiling: titles ranked above this are dropped before
    # scoring (see job_agent.seniority.LEVEL_NAMES). None = filter off.
    max_seniority: str | None = None
    # Optional candidate years of experience: a job whose JD requires clearly
    # more (see search.EXPERIENCE_GAP) is dropped before scoring. None = off.
    experience_years: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}

    _KNOWN_ATS = {"greenhouse", "lever", "ashby", "smartrecruiters",
                  # cross-company search sources: board = keyword query / tag
                  "sr-search", "remotive", "remoteok", "freehire", "freehire-relocation"}

    @field_validator("max_seniority")
    @classmethod
    def _known_level(cls, v: str | None) -> str | None:
        if v is None:
            return None
        level = v.strip().lower()
        if level not in LEVEL_NAMES:
            raise ValueError(
                f"max_seniority must be one of {sorted(LEVEL_NAMES)}; got {v!r}"
            )
        return level

    def unknown_sources(self) -> list[str]:
        """ATS names in the profile we don't have a source for."""
        return sorted({s.ats for s in self.sources if s.ats not in self._KNOWN_ATS})


class Settings(BaseModel):
    """Runtime settings from the environment."""

    anthropic_api_key: str | None = None
    model: str = DEFAULT_MODEL
    scoring_model: str = "claude-sonnet-5-5"
    classification_model: str = "claude-haiku-4-5-20251001"
    tailoring_model: str = "claude-sonnet-5-5"
    writing_model: str = "claude-sonnet-5-5"
    monthly_budget_usd: Decimal = Field(default=Decimal("40.00"), gt=0, allow_inf_nan=False)
    github_ready: bool = False
    score_threshold: int = Field(default=65, ge=0, le=100, strict=True)
    max_packets_per_day: int = Field(default=8, ge=1, strict=True)
    immediate_scoring_max_age_hours: float = Field(default=48, ge=0, allow_inf_nan=False)
    max_batch_items: int = Field(default=100, ge=1, le=100000)
    data_dir: Path = Path("data")

    @model_validator(mode="before")
    @classmethod
    def legacy_model_fallback(cls, values):
        # Explicit task settings win; an explicitly supplied legacy model is
        # still honored by callers migrating from Settings(model=...).
        if isinstance(values, dict) and values.get("model"):
            values = dict(values)
            for task in ("scoring_model", "classification_model", "tailoring_model", "writing_model"):
                values.setdefault(task, values["model"])
        return values


def load_settings() -> Settings:
    """Read ``.env`` (if present) and the environment into :class:`Settings`."""
    load_dotenv()  # loads .env from CWD if it exists; no-op otherwise
    values = {
        "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY") or None,
        "data_dir": Path(os.environ.get("JOB_AGENT_DATA_DIR", "data")),
    }
    values["github_ready"] = os.environ.get("JOB_AGENT_GITHUB_READY", "false").lower() == "true"
    if os.environ.get("JOB_AGENT_MODEL"):
        values["model"] = os.environ["JOB_AGENT_MODEL"]
    for field in ("scoring_model", "classification_model", "tailoring_model", "writing_model"):
        if os.environ.get(f"JOB_AGENT_{field.upper()}"):
            values[field] = os.environ[f"JOB_AGENT_{field.upper()}"]
    for field in ("score_threshold", "max_packets_per_day", "max_batch_items"):
        if f"JOB_AGENT_{field.upper()}" in os.environ:
            values[field] = int(os.environ[f"JOB_AGENT_{field.upper()}"])
    if "JOB_AGENT_MONTHLY_BUDGET_USD" in os.environ:
        values["monthly_budget_usd"] = os.environ["JOB_AGENT_MONTHLY_BUDGET_USD"]
    if "JOB_AGENT_IMMEDIATE_SCORING_MAX_AGE_HOURS" in os.environ:
        values["immediate_scoring_max_age_hours"] = os.environ["JOB_AGENT_IMMEDIATE_SCORING_MAX_AGE_HOURS"]
    return Settings(**values)


def load_profile(path: str | Path) -> SearchProfile:
    """Load and validate a search profile YAML file.

    Raises :class:`FileNotFoundError` if missing and :class:`ValueError` with a
    readable message if the YAML is malformed or fails validation.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Search profile not found: {path}. "
            f"Copy search_profile.example.yaml to {path} and edit it."
        )
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Could not parse {path} as YAML: {exc}") from exc
    try:
        return SearchProfile.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid search profile {path}:\n{exc}") from exc
