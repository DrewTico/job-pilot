"""Immutable career facts — the source of truth the tailoring engine obeys.

Loaded from ``data/facts.yaml`` (gitignored), or bundled fake facts for demos. The
frozen models make employers/titles/durations/certs read-only in memory, and the
helper accessors give ``verify.py`` the exact allow-lists it enforces.
"""

from __future__ import annotations

from pathlib import Path

import hashlib
import json
import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError

from job_agent.tailor.textnorm import norm as _norm


class Certification(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    issuer: str | None = None
    year: str | None = None


class Employer(BaseModel):
    model_config = ConfigDict(frozen=True)
    company: str
    title: str
    location: str = ""
    duration: str
    project_description: str = ""
    real_bullets: tuple[str, ...] = ()
    real_metrics: tuple[str, ...] = ()
    real_skills: tuple[str, ...] = ()


class Project(BaseModel):
    model_config = ConfigDict(frozen=True)
    header: str
    real_bullets: tuple[str, ...] = ()


class CareerFacts(BaseModel):
    _source_hash: str | None = PrivateAttr(default=None)
    _raw_source_hash: str | None = PrivateAttr(default=None)

    model_config = ConfigDict(frozen=True)

    name: str
    role: str
    email: str
    phone: str
    location: str | None = None
    links: tuple[str, ...] = ()
    education: tuple[str, ...] = ()
    certifications: tuple[Certification, ...] = ()
    skills_inventory: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    employers: tuple[Employer, ...] = Field(min_length=1)
    projects: tuple[Project, ...] = ()
    summary: str = ""
    gpa: str | None = None
    citizenship: str | None = None
    requires_sponsorship: bool | None = None
    open_to_relocation: bool | None = None
    open_to_remote: bool | None = None
    honors: tuple[str, ...] = ()
    credentials: tuple[str, ...] = ()
    academic_focus: tuple[str, ...] = ()
    leadership: tuple[str, ...] = ()
    known_gaps: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    # --- allow-lists consumed by the no-drift verifier ---------------------

    def employer_companies(self) -> set[str]:
        return {_norm(e.company) for e in self.employers}

    def employer_identities(self) -> set[tuple[str, str, str]]:
        """The (company, title, duration) triples that must survive unchanged."""
        return {(_norm(e.company), _norm(e.title), _norm(e.duration)) for e in self.employers}

    def certification_names(self) -> set[str]:
        return {_norm(c.name) for c in self.certifications}

    def real_skills(self) -> set[str]:
        """Every real skill (global inventory + per-employer environments)."""
        skills = {_norm(s) for group in self.skills_inventory.values() for s in group}
        for e in self.employers:
            skills |= {_norm(s) for s in e.real_skills}
        return skills


def load_career_facts(path: str | Path) -> CareerFacts:
    """Load and validate a career-facts YAML file with a readable error on failure."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Career facts not found: {path}. Generate it from the base resume first "
            f"(job_agent.tailor.extract)."
        )
    try:
        source = path.read_text()
        raw = yaml.safe_load(source) or {}
    except yaml.YAMLError as exc:
        raise ValueError("Invalid approved input YAML; source details omitted") from None
    try:
        result = CareerFacts.model_validate(raw)
        result._raw_source_hash = hashlib.sha256(source.encode()).hexdigest()
        # Source identity commits approved parsed values, not YAML formatting.
        # Answer-bank explicitness is meaningful: defaults must stay distinguishable.
        semantic = result.model_dump(mode="json", exclude_unset=False)
        result._source_hash = hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return result
    except ValidationError as exc:
        raise ValueError("Invalid career facts; source details omitted") from None
