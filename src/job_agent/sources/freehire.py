"""FreeHire public discovery, limited to one fresh page per query."""

from __future__ import annotations

import re

from job_agent.geo import infer_country
from job_agent.http import SourceError, get_json
from job_agent.models import Job
from job_agent.sources.base import JobSource, parse_iso, truncate

API_URL = "https://freehire.me/api/v1/agent/jobs/search"


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _country(value: object, location: str) -> str | None:
    if value is None or value == []:
        return infer_country(location)
    # Do not turn malformed or partially valid structured geography into a
    # confident single-country claim based on only part of the response.
    if not isinstance(value, list) or not all(
        isinstance(code, str) and re.fullmatch(r"[A-Za-z]{2}", code.strip())
        for code in value
    ):
        return None
    countries = {code.strip().upper() for code in value}
    if "US" in countries:
        return "US"
    return next(iter(countries)) if len(countries) == 1 else None


class FreeHireSource(JobSource):
    """``board`` is a title search query, not a company identifier."""

    ats = "freehire"

    def discovery_filter(self) -> dict[str, str]:
        return {"countries": "US"}

    def fetch(self) -> list[Job]:
        params = {
            "q": self.board,
            "q_fields": "title",
            **self.discovery_filter(),
            "description_format": "text",
            "sort": "posted_at",
            "order": "desc",
            "limit": 100,
            "offset": 0,
        }
        payload = get_json(API_URL, params=params)
        if not isinstance(payload, dict):
            raise SourceError("FreeHire search response must be an object")
        if not isinstance(payload.get("data"), list):
            raise SourceError("FreeHire search response data must be a list")
        if "meta" in payload and not isinstance(payload["meta"], dict):
            raise SourceError("FreeHire search response meta must be an object")
        ignored = payload.get("meta", {}).get("ignored_params")
        if ignored is not None:
            if not isinstance(ignored, list) or not all(
                isinstance(name, str) and name.strip() for name in ignored
            ):
                raise SourceError("FreeHire meta.ignored_params must be a list of nonempty strings")
            critical = {"q_fields"}
            if params.get("countries") == "US":
                critical.add("countries")
            if params.get("relocation") == "supported":
                critical.add("relocation")
            dropped = critical.intersection(name.strip() for name in ignored)
            if dropped:
                raise SourceError(
                    "FreeHire ignored critical discovery parameters: " + ", ".join(sorted(dropped))
                )

        jobs: list[Job] = []
        for raw in payload["data"][:100]:
            if not isinstance(raw, dict):
                continue
            if not all(_text(raw.get(key)) for key in ("public_slug", "title", "company", "url")):
                continue
            mode = _text(raw.get("work_mode")).lower()
            remote = True if mode == "remote" else False if mode in {"onsite", "hybrid"} else None
            location = _text(raw.get("location")) or ("Remote" if remote else "Unknown")
            enrichment = raw.get("enrichment")
            enrichment = enrichment if isinstance(enrichment, dict) else {}
            relocation = enrichment.get("relocation")
            visa = enrichment.get("visa_sponsorship")
            jobs.append(Job(
                id=raw["public_slug"],
                source="freehire",
                title=raw["title"].strip(),
                company=raw["company"].strip(),
                location=location,
                url=raw["url"],
                apply_url=raw["url"],
                posted_at=parse_iso(_text(raw.get("posted_at"))),
                description=truncate(_text(raw.get("description"))),
                remote=remote,
                country=_country(raw.get("countries"), location),
                relocation=(relocation if isinstance(relocation, str) and relocation in
                            {"supported", "not_supported", "required"} else None),
                visa_sponsorship=visa if isinstance(visa, bool) else None,
            ))
        return jobs


class FreeHireRelocationSource(FreeHireSource):
    """Optional secondary discovery lane: one relocation-supported page."""

    ats = "freehire-relocation"

    def discovery_filter(self) -> dict[str, str]:
        return {"relocation": "supported"}
