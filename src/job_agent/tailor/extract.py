"""One-time extraction: base resume (.docx) → immutable career facts (YAML).

This reads the base resume with python-docx and produces the source-of-truth
``career_facts.yaml`` that the tailoring engine is constrained to. Company names,
titles, and durations are captured verbatim from the resume; only the true
metric-bearing clauses are pulled into ``real_metrics`` (nothing is invented).

Contact fields and certifications are supplied explicitly (see
``build_career_facts``); contact lines in the resume are not used as the role.

Run via the CLI (``python -m job_agent tailor extract ...``) or ``main()``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from docx import Document

# A bold header line like "JPMorgan Chase & Co. | Texas, USA| Title  Jul 2024 - Present".
_DURATION = re.compile(
    r"([A-Z][a-z]{2,8}\.?\s+\d{4}\s*[-–]\s*(?:Present|[A-Z][a-z]{2,8}\.?\s+\d{4}))\s*$"
)
_SECTION_MARKERS = ("OBJECTIVE", "PROFESSIONAL SUMMARY", "TECHNICAL SKILLS",
                    "EDUCATION", "WORK EXPERIENCE", "SKILLS", "EXPERIENCE",
                    "PROJECTS", "SUMMARY")

# Only clauses matching these are treated as real, citable metrics.
_METRIC = re.compile(
    r"\d{1,3}\s*%|\d[\d,]*\+?\s*(?:daily users|users|years|applications|records)"
    r"|minutes to seconds|tripl(?:e|ed)",
    re.IGNORECASE,
)


def _paragraphs(doc: Document) -> list[tuple[str, bool]]:
    """Non-empty paragraphs as (text, is_bold)."""
    out = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        runs = [r for r in p.runs if r.text.strip()]
        is_bold = bool(runs) and all(r.bold for r in runs)
        out.append((text, is_bold))
    return out


def _is_employer_header(text: str, is_bold: bool) -> bool:
    return is_bold and "|" in text and bool(_DURATION.search(text))


def _is_contact_line(text: str) -> bool:
    """Recognize contact indicators without relying on candidate-specific values."""
    return bool(
        re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
        or re.search(r"\b(?:www\.)?(?:linkedin\.com|github\.com)(?:/|\b)", text, re.I)
        or re.search(
            r"(?<!\w)(?:\+?\d{1,3}[ .-]?)?(?:\(\d{3}\)|\d{3})"
            r"[ .-]?\d{3}[ .-]?\d{4}(?!\w)", text
        )
        or len([part for part in text.split("|") if part.strip()]) >= 3
    )


def _split_header(text: str) -> tuple[str, str, str, str]:
    """'Company | Location | Title  Duration' → (company, location, title, duration)."""
    duration = _DURATION.search(text).group(1).strip()
    without_dur = _DURATION.sub("", text).strip()
    parts = [p.strip() for p in without_dur.split("|")]
    company = parts[0]
    if company.endswith("'s") or company.endswith("’s"):
        company = company[:-2].strip()          # "Globe Life's" -> "Globe Life"
    location = parts[1] if len(parts) > 1 else ""
    title = " ".join(parts[2:]).strip() if len(parts) > 2 else ""
    return company, location, title, duration


def _paren_aware_split(text: str) -> list[str]:
    """Split a comma list without breaking parenthesized groups."""
    items, depth, buf = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            items.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        items.append(buf.strip())
    return [i for i in items if i]


def _metric_clauses(bullets: list[str]) -> list[str]:
    """The true, metric-bearing clauses from a role's bullets (no invention)."""
    found: list[str] = []
    for bullet in bullets:
        for clause in re.split(r"[;.]", bullet):
            clause = clause.strip()
            if clause and _METRIC.search(clause) and clause not in found:
                found.append(clause)
    return found


def extract_career_facts(docx_path: str | Path) -> dict[str, Any]:
    """Parse the resume into a career-facts dict (no contact PII, no certs)."""
    paras = _paragraphs(Document(str(docx_path)))
    texts = [t for t, _ in paras]

    name = texts[0] if texts else ""
    role = texts[1] if len(texts) > 1 else ""
    if _is_contact_line(role) or role.upper().rstrip(":") in _SECTION_MARKERS:
        role = ""

    # Slice each section at the next heading, independent of section order.
    sections: dict[str, list[tuple[str, bool]]] = {}
    current_section = None
    for text, is_bold in paras:
        heading = text.upper().rstrip(":")
        if heading in _SECTION_MARKERS:
            current_section = {"SKILLS": "TECHNICAL SKILLS",
                               "EXPERIENCE": "WORK EXPERIENCE"}.get(heading, heading)
            sections.setdefault(current_section, [])
        elif current_section:
            sections[current_section].append((text, is_bold))

    education = [text for text, _ in sections.get("EDUCATION", [])]
    skills_inventory: dict[str, list[str]] = {}
    current = None
    for text, is_bold in sections.get("TECHNICAL SKILLS", []):
        inline = re.match(r"^[•●▪*\-]?\s*([^:]+):\s*(.*)$", text)
        if inline:
            current = inline.group(1).strip()
            skills_inventory.setdefault(current, []).extend(_paren_aware_split(inline.group(2)))
        elif is_bold:
            current = text
            skills_inventory[current] = []
        elif current:
            skills_inventory[current].append(text)

    # Preserve project headings verbatim, including any dates or descriptors.
    projects: list[dict[str, Any]] = []
    for text, is_bold in sections.get("PROJECTS", []):
        if is_bold:
            projects.append({"header": text, "real_bullets": []})
        elif projects:
            projects[-1]["real_bullets"].append(text)
        else:
            projects.append({"header": "", "real_bullets": [text]})

    employers: list[dict[str, Any]] = []
    work = sections.get("WORK EXPERIENCE", [])
    header_positions = [i for i, (t, b) in enumerate(work)
                        if _is_employer_header(t, b)
                        or (b and bool(_DURATION.search(t)) and "|" not in t)]
    for n, start in enumerate(header_positions):
        end = header_positions[n + 1] if n + 1 < len(header_positions) else len(work)
        block = work[start:end]
        split_layout = "|" not in block[0][0]
        if split_layout:
            header = block[0][0]
            duration = _DURATION.search(header).group(1).strip()
            company = _DURATION.sub("", header).strip()
            title, location = "", ""
            if len(block) > 1:
                # Tabs, pipes, or alignment spaces separate title and location.
                details = re.split(r"\t+|\s*\|\s*| {2,}", block[1][0], maxsplit=1)
                title = details[0].strip()
                location = details[1].strip() if len(details) > 1 else ""
            body = block[2:]
        else:
            company, location, title, duration = _split_header(block[0][0])
            body = block[1:]

        # project description = paragraphs after header until "Key Responsibilities".
        resp_at = next((i for i, (t, _) in enumerate(body)
                        if "key responsibilities" in t.lower()), len(body))
        env_at = next((i for i, (t, _) in enumerate(body)
                       if t.lower().startswith("environment")), len(body))
        project_description = " ".join(t for t, _ in body[:resp_at]).strip()
        bullets = [t for t, _ in body[resp_at + 1: env_at]
                   if "key responsibilities" not in t.lower()]
        if split_layout and resp_at == len(body):
            project_description = ""
            bullets = [t for t, _ in body[:env_at]]
        environment_raw = body[env_at][0] if env_at < len(body) else ""
        environment_raw = re.sub(r"(?i)^environment:\s*", "", environment_raw).strip()

        employers.append({
            "company": company,
            "title": title,
            "location": location,
            "duration": duration,
            "project_description": project_description,
            "real_bullets": bullets,
            "real_metrics": _metric_clauses(bullets),
            "real_skills": _paren_aware_split(environment_raw),
        })

    return {
        "name": name,
        "role": role,
        "education": education,
        "skills_inventory": skills_inventory,
        "employers": employers,
        **({"projects": projects} if "PROJECTS" in sections else {}),
    }


def build_career_facts(
    docx_path: str | Path,
    *,
    email: str,
    phone: str,
    location: str | None = None,
    links: list[str] | None = None,
    certifications: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Extraction + the explicitly-supplied contact/cert facts."""
    facts = extract_career_facts(docx_path)
    facts.update({
        "email": email,
        "phone": phone,
        "location": location,
        "links": links or [],
        "certifications": certifications or [],
    })
    # Order keys for a readable YAML file.
    order = ["name", "role", "email", "phone", "location", "links",
             "education", "certifications", "skills_inventory", "employers"]
    if "projects" in facts:
        order.append("projects")
    return {k: facts[k] for k in order}


def write_career_facts(facts: dict[str, Any], out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(facts, sort_keys=False, allow_unicode=True, width=100))
    return out_path
