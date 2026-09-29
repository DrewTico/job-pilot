"""Conservative, source-independent gates for clear early-career restrictions.

Ambiguous qualifications stay for scoring. These rules are intentionally not a
complete education or security-clearance parser.
"""

from __future__ import annotations

import re

from job_agent.models import Job

_TS = r"\bts\s*/\s*sci\b"
_CLEARANCE = rf"(?:\b(?:top\s+secret|secret)\s+(?:security\s+)?clearance\b|{_TS}(?:\s+clearance)?|\bsecurity\s+clearance\b)"
_GRAD = r"\b(?:phd(?:\s+degree)?|doctoral(?:\s+degree)?|doctorate|master(?:'s|s)?(?:\s+degree)?|ms(?=\s+(?:degree|program|students?)\b|\s*/\s*(?:phd|doctoral)\b)(?:\s+degree)?|msc|graduate\s+(?:degree|program|student))\b"
_BACHELOR = re.compile(r"\b(?:bachelor(?:'s|s)?|bs|ba|bsc|undergraduate)\b")
_PREFERRED = re.compile(r"\b(?:preferred|preferably|optional|ideally)\b|\b(?:a plus|not required|no .*required)\b")


def _normalize(text: str) -> str:
    text = text.lower().replace("’", "'")
    # Preserve sentence boundaries while normalizing common degree abbreviations.
    for pattern, replacement in [(r"\bph\.\s*d\.", "phd"),
                                 (r"\bm\.s\.", "ms"),
                                 (r"\bb\.s\.", "bs"),
                                 (r"\bb\.a\.", "ba")]:
        text = re.sub(pattern, replacement, text)
    return text


def _clauses(text: str) -> list[str]:
    # Coordinated requirements get separate exception scopes. Keep "or"
    # alternatives together, including bachelor/graduate pathways.
    return re.split(r"[.!?;\n]+|\band\b(?!\s+maintain\b)", _normalize(text))


def _requires_clearance(text: str) -> bool:
    for clause in _clauses(text):
        if _PREFERRED.search(clause) or re.search(
            r"\b(?:obtain|eligible|eligibility)\b", clause
        ):
            continue
        if re.search(rf"\b(?:active|current)\s+{_CLEARANCE}(?:\s+with\s+(?:a\s+)?polygraph)?\s+(?:is\s+)?required\b", clause):
            return True
        if re.search(rf"\bmust\s+(?:currently\s+)?(?:hold|possess)\s+(?:an?\s+)?(?:active\s+|current\s+)?{_CLEARANCE}", clause):
            return True
        if re.search(rf"{_TS}(?:\s+clearance)?(?:\s+with\s+(?:a\s+)?polygraph)?\s+(?:is\s+)?required\b", clause):
            return True
    return False


def _graduate_only(title: str, description: str) -> bool:
    title = _normalize(title)
    # Degree-scoped early-career titles explicitly restrict the candidate path.
    if (re.search(r"\b(?:intern(?:ship)?|new[ -]+grad(?:uate)?)\b", title) and re.search(_GRAD, title)
            and not _BACHELOR.search(title) and not _PREFERRED.search(title)
            and not re.search(r"\bor equivalent\s+(?:experience|qualification|education)", title)):
        return True
    for clause in _clauses(title + "\n" + description):
        if (_BACHELOR.search(clause) or _PREFERRED.search(clause)
                or re.search(r"\bor equivalent\s+(?:experience|qualification|education)", clause)):
            continue
        if re.search(rf"{_GRAD}\s+(?:is\s+)?required\b", clause):
            return True
        if re.search(rf"\b(?:must\s+(?:(?:currently\s+)?(?:have|hold|possess)|be\s+(?:currently\s+)?(?:pursuing|enrolled\s+in))|requires?|minimum(?:\s+of)?)\s+(?:an?\s+)?{_GRAD}", clause):
            return True
        if re.search(rf"\b(?:currently\s+)?(?:enrolled|pursuing)\b[^.!?;]{{0,40}}{_GRAD}", clause):
            return True
        if re.search(rf"(?:{_GRAD}|\bgraduate)\s+students?\s+only\b", clause):
            return True
    return False


def passes_eligibility(job: Job) -> bool:
    """Keep unless title/full JD clearly signals an incompatible requirement."""
    title = _normalize(job.title)
    if not _PREFERRED.search(title) and not re.search(r"\bobtain|\beligib", title):
        if re.search(rf"\bcleared\b|{_TS}|\bpolygraph\b", title):
            return False
    return not (_requires_clearance(job.title + "\n" + (job.description or ""))
                or _graduate_only(job.title, job.description or ""))
