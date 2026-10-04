"""Public research boundary. No network implementation is enabled in M1."""
from datetime import datetime
from typing import Literal, Protocol
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import ipaddress
import re
import unicodedata
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator
from job_agent.models import Job
from job_agent.scoring import detect_content_flags


class CompanyFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    text: str = Field(min_length=1)
    source_url: str
    source_title: str = ""
    retrieved_at: datetime
    company: str = Field(min_length=1)
    category: Literal["product", "engineering", "mission", "market", "recent_public_event", "other"] = "other"

    @field_validator("text", "company")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Blank research field")
        return " ".join(unicodedata.normalize("NFC", value).split())

    @field_validator("retrieved_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Research timestamp must be timezone-aware")
        return value

    @field_validator("source_url")
    @classmethod
    def public_url(cls, value):
        value = str(TypeAdapter(HttpUrl).validate_python(value))
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
            raise ValueError("Public source URL required")
        if host.lower() == "localhost" or "." not in host or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError("Public source URL required")
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global or address.is_multicast or address.is_reserved:
                raise ValueError("Public source URL required")
        except ValueError:
            # Non-IP hostnames are valid; private numeric addresses are not.
            if host.replace(".", "").isdigit() or ":" in host:
                raise ValueError("Public source URL required") from None
        return value


class ReferralCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(min_length=1)
    current_role: str
    company: str
    source_url: str
    reason: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    _source = field_validator("source_url")(CompanyFact.public_url.__func__)


class CompanyResearcher(Protocol):
    def research(self, job: Job) -> tuple[CompanyFact, ...]: ...


class FixtureCompanyResearcher:
    """Explicit local JSON mapping company names to sourced fact objects."""
    def __init__(self, path: Path | None = None):
        self.rows = json.loads(path.read_text()) if path and path.exists() else {}

    def research(self, job):
        return tuple(CompanyFact.model_validate(row) for row in self.rows.get(job.company, []))


def usable_facts(job, facts):
    """Deduplicate either normalized text or URL; exclude injection signals."""
    result, urls, texts, flags = [], set(), set(), []
    for fact in sorted(facts, key=lambda f: json.dumps(semantic_fact(CompanyFact.model_validate(f)), sort_keys=True)):
        fact = CompanyFact.model_validate(fact)
        if fact.company.casefold() != job.company.casefold():
            continue
        if packet_content_flags(job.model_copy(update={"description": fact.text + "\n" + fact.source_title})):
            flags.append("research_prompt_injection_suspected")
            continue
        url = canonical_source_url(fact.source_url)
        text = " ".join(fact.text.casefold().split())
        if url in urls or text in texts:
            continue
        urls.add(url)
        texts.add(text)
        result.append(fact)
    return tuple(result[:3]), tuple(sorted(set(flags)))


def canonical_source_url(value):
    """Comparison only: preserve the original human-visible URL."""
    value = CompanyFact.public_url(value)
    p = urlsplit(value)
    host = p.hostname.lower().rstrip(".")
    if ":" in host:
        host = "[" + host + "]"
    port = p.port
    netloc = host + (f":{port}" if port and (p.scheme, port) not in (("http", 80), ("https", 443)) else "")
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in ("gclid", "fbclid")]
    query.sort(key=lambda item: item[0])
    return urlunsplit((p.scheme.lower(), netloc, p.path.rstrip("/"), urlencode(query), ""))


def semantic_fact(fact):
    return {"company": " ".join(fact.company.casefold().split()),
            "text": " ".join(fact.text.split()), "source_url": canonical_source_url(fact.source_url)}


def packet_content_flags(job):
    """Packet-only conservative injection gate; discovery policy is untouched."""
    flags = detect_content_flags(job)
    if flags or re.search(
        r"ignore\s+(?:the\s+)?system\s+rules|reveal\s+candidate\s+data|"
        r"change\s+(?:the\s+)?GPA|claim\s+Kubernetes|output\s+GitHub|"
        r"mark\s+(?:the\s+)?packet\s+approved|send\s+(?:an?\s+)?email|"
        r"call\s+tools|alter\s+(?:the\s+)?JSON\s+schema", job.description, re.I):
        return ("prompt_injection_suspected",)
    return ()


def semantic_fact_id(fact):
    """Stable public fact identity, independent of storage IDs and retrieval time."""
    import hashlib
    return hashlib.sha256(json.dumps(semantic_fact(fact), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
