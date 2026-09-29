"""Offline eligibility regressions for normalized jobs from any source."""
import pytest

from job_agent.eligibility import passes_eligibility
from job_agent.models import Job


def eligible(title="AI Engineer", description=""):
    return passes_eligibility(Job(id="1", title=title, description=description,
                                  company="Example", location="US", url="https://example.test", source="demo"))


@pytest.mark.parametrize("title", [
    "AI Engineer, PhD required", "Cleared AI/ML Engineer", "AI Engineer TS/SCI CI Poly", "AI Engineer TS/SCI/polygraph",
    "2027 Summer Intern, PhD, Machine Learning Research",
    "Hardware Machine Learning PhD Research Internship",
    "2027 Summer Intern, MS/PhD, Machine Learning",
])
def test_restricted_titles(title):
    assert not eligible(title=title)


@pytest.mark.parametrize("description", [
    "Active Secret clearance required", "Active Top Secret clearance required",
    "Must currently hold a Top Secret clearance", "Must possess an active Secret clearance",
    "TS/SCI clearance required", "Active TS/SCI with polygraph required",
    "Current Secret clearance required", "Current Top Secret clearance required",
    "PhD required", "Ph.D. required", "Doctoral degree required",
    "Must be currently pursuing a PhD", "Currently enrolled in a Master's or PhD program",
    "Master's degree required", "Candidates must be enrolled in a graduate program",
    "Graduate students only", "Master's students only", "PhD degree required", "Must have a master's degree",
])
def test_clear_requirements(description):
    assert not eligible(description=description)


@pytest.mark.parametrize("description", [
    "Must be eligible to obtain a clearance", "Ability to obtain Secret clearance",
    "Must be able to obtain and maintain a clearance", "Must be eligible for a security clearance",
    "Clearance eligibility preferred", "US citizenship required", "US citizen required",
    "Public Trust eligibility", "Ability to obtain Public Trust",
    "BS/MS/PhD students eligible", "Bachelor's, Master's, or PhD students",
    "Bachelor's or Master's degree", "Currently pursuing a Bachelor's or Master's degree",
    "Bachelor's degree required", "Bachelor's degree in Computer Science or equivalent",
    "Master's or PhD preferred", "Advanced degree preferred",
    "Our team members have PhDs", "You must collaborate with PhD researchers",
    "Our team holds active Secret clearance", "Work with PhD researchers on machine learning",
    "Research machine learning methods", "Keep our secret recipes secure. Security matters.",
    "Active Secret clearance preferred", "PhD not required",
    "B.A. or M.S. degree required", "B.S./M.S./Ph.D. students eligible",
    "Master’s or PhD preferred",
])
def test_eligible_or_ambiguous_descriptions(description):
    assert eligible(description=description)


@pytest.mark.parametrize("title", [
    "AI Engineer", "Software Engineer", "Machine Learning Intern",
    "BS/MS/PhD Machine Learning Internship", "Bachelor's/Master's/PhD Research Intern",
])
def test_eligible_titles(title):
    assert eligible(title=title, description="Bachelor's degree in Computer Science or equivalent")


@pytest.mark.parametrize("description", [
    "M.S. degree required", "MS degree required",
    "Currently enrolled in an MS/PhD program",
    "Active Secret clearance required and Python preferred",
    "Active Secret clearance required and ability to obtain TS/SCI later",
    "Active Secret clearance required and Python or equivalent experience accepted",
    "Master's degree required; Python preferred",
    "Master's degree required and AWS experience preferred",
    "Master's degree required and Python or equivalent experience accepted",
])
def test_independent_hard_requirements(description):
    assert not eligible(description=description)


@pytest.mark.parametrize("description", [
    "Requires MS Office experience", "MS Excel proficiency required",
    "Experience with MS SQL required", "Experience with MS SQL preferred",
    "MS required", "Ability to obtain and maintain a Secret clearance",
    "Secret clearance preferred",
    "Must hold a Secret clearance or be able to obtain one",
    "Bachelor's degree required; Master's preferred",
    "Master's degree or equivalent experience accepted",
])
def test_local_exceptions_and_ambiguous_ms(description):
    assert eligible(description=description)
