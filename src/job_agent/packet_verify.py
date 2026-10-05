"""Fail-closed packet truth checks in addition to existing resume gates."""
import re
import html
import unicodedata
from urllib.parse import unquote
from pydantic import BaseModel, ConfigDict
from job_agent.writing_lint import lint_writing

VERIFIER_VERSION = "m1-extractive-structural-gpa-v3"



def github_url_present(text):
    # Compare common URL/HTML encodings without changing approved visible text.
    probe = text
    for _ in range(5):
        decoded = unquote(html.unescape(probe))
        if decoded == probe:
            break
        probe = decoded
    probe = unicodedata.normalize("NFKC", probe).replace("\u3002", ".").replace("\uff61", ".")
    return bool(re.search(r"github\.com", probe, re.I))


def candidate_lines(facts):
    return [facts.summary, *facts.education,
            *(s for values in facts.skills_inventory.values() for s in values),
            *(b for e in facts.employers for b in (*e.real_bullets, *e.real_metrics)),
            *(b for p in facts.projects for b in p.real_bullets)]


def verify_text(text, facts, *, github_ready=False, gpa_required=False):
    problems = list(lint_writing(text))
    if re.search(r'\bB\.?\s*S\.?\b|Bachelor of Science', text, re.I):
        problems.append("wrong_degree")
    if re.search(r'\bGPA\b|3\.18', text, re.I):
        if not gpa_required:
            problems.append("gpa_not_required")
        elif facts.gpa != "3.18" or re.search(r'GPA\s*[:=]?\s*(?!3\.18\b)\d', text, re.I):
            problems.append("wrong_gpa")
    if not github_ready and github_url_present(text):
        problems.append("github_not_ready")
    for title in re.findall(r"(?im)^Role:\s*(.+)$", text):
        if title.strip() not in [e.title for e in facts.employers]:
            problems.append("unsupported_title")
    if re.search(r"Simpro", text, re.I):
        for title in re.findall(r"(?im)^Role:\s*(.+)\n(?:.*\n){0,2}?Company:\s*Simpro", text):
            if title.strip() != "Applied AI Intern":
                problems.append("wrong_simpro_title")
        for title in re.findall(r"(?i)(?:as (?:an? )?|title: )([A-Za-z ]+)(?= at Simpro)", text):
            if title.strip() != "Applied AI Intern":
                problems.append("wrong_simpro_title")
    corpus = facts.model_dump_json().lower()
    allowed_numbers = set(re.findall(r'\d+(?:\.\d+)?', corpus))
    if gpa_required and facts.gpa == "3.18":
        allowed_numbers.add("3.18")
    for number in re.findall(r'\d+(?:\.\d+)?', text):
        if number not in allowed_numbers:
            problems.append("unsupported_number")
    # Conservative lexical allow-list: arbitrary new tools/projects/skills cannot
    # pass just because a finite known-tool dictionary does not recognize them.
    structural = "professional summary technical skills experience education certifications role company project description duration responsibilities achievements none gpa applied ai intern bachelor of arts in computer science ba".split()
    allowed = set(re.findall(r'[a-z]+', corpus)) | set(structural)
    if set(re.findall(r'[a-z]+', text.lower())) - allowed:
        problems.append("unsupported_candidate_words")
    return sorted(set(problems))


def company_opening_references_candidate(text, name):
    """Block explicit candidate attribution from borrowing company authority.

    This is a conservative lexical boundary, not a universal semantic subject
    classifier. Candidate grounding and all other packet checks remain required.
    Company first-person plural (we/our/ours/us) is deliberately permitted.
    """
    probe = unicodedata.normalize("NFKC", text).casefold()
    if re.search(r"\b(?:candidate|applicant|job\s+seeker|jobseeker|i|me|my|mine|you|your|yours)\b", probe):
        return True
    normalized_name = unicodedata.normalize("NFKC", name).casefold()
    # Any exact nonempty name token is a candidate reference. Use the same
    # Unicode tokenizer on both sides so substrings cannot borrow authority.
    name_tokens = set(re.findall(r"\w+", normalized_name))
    opening_tokens = set(re.findall(r"\w+", probe))
    return bool(name_tokens & opening_tokens)


class CoverLetterDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    company_opening: str
    candidate_lines: list[str]
    closing: str

    def verified_text(self, facts, company_facts, *, github_ready, gpa_required):
        if self.company_opening not in [f.text for f in company_facts]:
            raise ValueError("unsourced_company_claim")
        if company_opening_references_candidate(self.company_opening, facts.name):
            raise ValueError("company_fact_cannot_authorize_candidate_claim")
        if company_facts[0].company.casefold() not in self.company_opening.casefold():
            raise ValueError("opening_not_company_specific")
        allowed = candidate_lines(facts)
        for line in self.candidate_lines:
            if line not in allowed or verify_text(line, facts, github_ready=github_ready, gpa_required=gpa_required):
                raise ValueError("unsupported_candidate_claim")
        if self.closing != "I would welcome a conversation about this role.":
            raise ValueError("unsupported_closing")
        text = "\n\n".join([self.company_opening, " ".join(self.candidate_lines), self.closing])
        if len(text.split()) > 200 or lint_writing(text):
            raise ValueError("cover_letter_lint_or_length")
        return text


def verify_resume_grounding(text, facts, *, gpa_required=False):
    """Only extractive substantive lines are admitted in this M1 slice.

    Reordering and selection tailor the resume, while arbitrary paraphrase
    remains manual-needed rather than admitting semantic fabrications.
    """
    from job_agent.tailor.textnorm import strip_markdown
    from job_agent.tailor.render_pdf import _canonical_heading
    if gpa_required and (facts.gpa != "3.18" or not re.search(r"\bGPA\s*[:=]?\s*3\.18\b", text)):
        return ["required_approved_gpa_missing"]
    section, block, lines = None, {}, []

    def flush():
        if not block and not lines:
            return True
        if section == "PROFESSIONAL EXPERIENCE":
            matches = [e for e in facts.employers if
                       block.get("Role") == e.title and block.get("Company") == e.company
                       and block.get("Duration") == e.duration]
            return any(("Project Description" not in block or block["Project Description"] == e.project_description)
                       and all(line in (*e.real_bullets, *e.real_metrics) for line in lines) for e in matches)
        if section == "PROJECTS":
            return any(block.get("header") == p.header and all(line in p.real_bullets for line in lines)
                       for p in facts.projects)
        return True

    for raw in text.splitlines():
        line = strip_markdown(raw).strip()
        heading = _canonical_heading(line) or ({"PROJECTS": "Projects", "EXPERIENCE": "Professional Experience"}.get(line.upper()))
        if heading:
            if not flush():
                return ["cross_record_provenance"]
            section, block, lines = heading.upper(), {}, []
            continue
        if not line:
            continue
        if section is None:
            if line not in (facts.name, facts.role, facts.email, facts.phone, facts.location,
                            *facts.links) and line != " | ".join((facts.email, facts.phone)):
                return ["unsupported_header"]
            continue
        if section == "PROFESSIONAL EXPERIENCE":
            if line.startswith("Role:") and block:
                if not flush():
                    return ["cross_record_provenance"]
                block, lines = {}, []
            if line in ("Responsibilities:", "Achievements:"):
                continue
            key, sep, value = line.partition(":")
            if sep and key in ("Role", "Company", "Duration", "Project Description"):
                if key in block:
                    return ["duplicate_structure"]
                block[key] = value.strip()
            else:
                lines.append(line.lstrip("-•* "))
        elif section == "PROJECTS":
            if line in [p.header for p in facts.projects]:
                if not flush():
                    return ["cross_record_provenance"]
                block, lines = {"header": line}, []
            else:
                lines.append(line.lstrip("-•* "))
        elif section == "TECHNICAL SKILLS":
            if ":" not in line:
                return ["unstructured_skills"]
            category, entries = line.split(":", 1)
            values = [v.strip() for v in entries.split(",")]
            if category.strip() not in facts.skills_inventory or any(v not in facts.skills_inventory[category.strip()] for v in values):
                return ["unsupported_skill"]
        else:
            allowed = {"PROFESSIONAL SUMMARY": [facts.summary], "EDUCATION": list(facts.education),
                       "CERTIFICATIONS": [c.name for c in facts.certifications] or ["None"]}.get(section, [])
            if section == "EDUCATION" and gpa_required and facts.gpa == "3.18":
                allowed += ["GPA: 3.18", "GPA 3.18"]
            if line.lstrip("-•* ") not in allowed:
                return ["candidate_line_requires_manual_grounding"]
    return [] if flush() else ["cross_record_provenance"]
