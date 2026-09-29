"""Pipeline filters and orchestration (deterministic, offline)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from job_agent.config import LocationRule, SearchProfile, SourceRef
from job_agent.models import Job
from job_agent.seen_cache import SeenCache
from job_agent.search import (
    is_fresh,
    matches_keywords,
    passes_experience,
    passes_location,
    passes_seniority,
    run,
)
from job_agent.sources.base import JobSource

NOW = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)


def make_job(**kw) -> Job:
    base = dict(id="1", title="t", company="c", location="l", url="http://x", source="demo")
    base.update(kw)
    return Job(**base)


def profile(**overrides) -> SearchProfile:
    data = dict(
        keywords=["data engineer", "machine learning"],
        location=LocationRule(remote_ok=True, allowed_countries=["US"]),
        sources=[SourceRef(ats="fake", board="b")],
        candidate_summary="x",
    )
    data.update(overrides)
    return SearchProfile(**data)


class FakeSource(JobSource):
    ats = "fake"

    def __init__(self, board, jobs=None, raises=False):
        super().__init__(board)
        self._jobs = jobs or []
        self._raises = raises

    def fetch(self):
        if self._raises:
            raise RuntimeError("boom")
        return self._jobs


# --- unit-level filters -----------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Senior Data Engineer", True),
    ("Machine Learning Scientist", True),
    ("Frontend Engineer", False),
])
def test_matches_keywords(title, expected):
    assert matches_keywords(title, ["data engineer", "machine learning"]) is expected


# Mirrors the profile's real keyword list (search_profile.yaml) so the intended
# coverage is pinned: research/AI engineer titles pass on their own keyword,
# while plain backend SWE titles still fail — no broad SWE term is present.
PROFILE_KEYWORDS = [
    "data scientist", "machine learning", "ml engineer", "ai engineer",
    "gen ai", "generative ai engineer", "mlops", "research engineer",
]


@pytest.mark.parametrize("title,expected", [
    ("Research Engineer", True),                       # only "research engineer" matches
    ("Senior AI Research Engineer", True),
    ("AI Engineer, Applications", True),               # only "ai engineer" matches
    ("Senior Software Engineer, Backend", False),      # backend SWE stays out
])
def test_profile_keywords_cover_research_and_ai_engineer_not_backend(title, expected):
    assert matches_keywords(title, PROFILE_KEYWORDS) is expected


@pytest.mark.parametrize("remote,country,expected", [
    (True, "US", True),
    (False, "US", True),
    (True, "GB", False),      # remote does not override a known non-US country
    (False, "GB", False),
    (True, None, True),       # unknown + remote -> keep
    (False, None, True),      # unknown + onsite -> keep for scorer
])
def test_passes_location(remote, country, expected):
    job = make_job(remote=remote, country=country)
    assert passes_location(job, profile()) is expected


@pytest.mark.parametrize("location,remote,expected", [
    # Clearly-foreign location text drops the job even with no structured
    # country and even when it's marked remote.
    ("Bengaluru, India", False, False),
    ("Bengaluru", False, False),
    ("Bengaluru, India", True, False),      # foreign + remote still drops
    ("London, UK", False, False),
    ("Remote - India", True, False),
    # US locations (and unknowns) are kept.
    ("Austin, TX", False, True),
    ("Remote (US)", True, True),
    ("Indianapolis, IN", False, True),      # not misread as India
    ("Remote", True, True),                 # unknown + remote -> keep
    ("Anywhere", False, True),              # unknown + onsite -> keep for scorer
])
def test_passes_location_infers_country_from_text(location, remote, expected):
    job = make_job(location=location, remote=remote, country=None)
    assert passes_location(job, profile()) is expected


@pytest.mark.parametrize("location,expected", [
    # The exact strings that leaked past the US-only stage (2026-07-08 run),
    # end-to-end: country stamped by the source-level guess, then the stage rule.
    ("London, UK", False),
    ("Dublin", False),
    ("Budapest, BU", False),
    ("Madrid, MD", False),
    ("Manchester, SLF", False),
    ("San Francisco, CA", True),
    ("Remote US", True),
    ("Menlo Park, CA-CA", True),
    ("Springfield", True),                  # unknown either way -> scorer decides
])
def test_leaked_foreign_locations_are_dropped_end_to_end(location, expected):
    from job_agent.sources.base import guess_us_country
    job = make_job(location=location, country=guess_us_country(location))
    assert passes_location(job, profile()) is expected


def test_is_fresh_uses_posted_at():
    assert is_fresh(make_job(posted_at=NOW - timedelta(days=13)), NOW, SeenCache("/tmp/_a.json"))
    assert not is_fresh(make_job(posted_at=NOW - timedelta(days=15)), NOW, SeenCache("/tmp/_b.json"))


def test_recency_window_is_configurable():
    # A job posted 5 days ago survives a 7-day window and is dropped by a 1-day one.
    job = make_job(posted_at=NOW - timedelta(days=5))
    assert is_fresh(job, NOW, SeenCache("/tmp/_w7.json"), timedelta(days=7)) is True
    assert is_fresh(job, NOW, SeenCache("/tmp/_w1.json"), timedelta(days=1)) is False


def test_is_fresh_falls_back_to_seen_cache(tmp_path):
    cache = SeenCache(tmp_path / "seen.json")
    job = make_job(id="42", posted_at=None, source="greenhouse")
    # First time we see a dateless job it's treated as fresh...
    assert is_fresh(job, NOW, cache) is True
    # ...but if we first saw it 15 days ago, it's stale.
    cache._first_seen["greenhouse:42"] = (NOW - timedelta(days=15)).isoformat()
    assert is_fresh(job, NOW, cache) is False


# --- seniority filter -------------------------------------------------------

@pytest.mark.parametrize("title,kept", [
    ("Data Engineer", True),
    ("Senior Data Engineer", True),
    ("Sr. Machine Learning Engineer", True),
    ("Lead Data Scientist", False),
    ("Staff ML Engineer", False),
    ("Principal AI Engineer", False),
    ("Director of Data", False),
    ("VP of Engineering", False),
])
def test_passes_seniority_ceiling_senior(title, kept):
    prof = profile(max_seniority="senior")
    assert passes_seniority(make_job(title=title), prof) is kept


def test_passes_seniority_off_when_unset():
    # No ceiling -> even a VP passes this stage.
    assert passes_seniority(make_job(title="VP of Engineering"), profile()) is True


# --- experience filter ------------------------------------------------------

@pytest.mark.parametrize("desc,kept", [
    ("8+ years of experience required.", False),      # hard 8 >= 5+3 -> drop
    ("8 years of experience required.", False),       # unambiguous "X years required"
    ("Minimum of 10 years in ML.", False),
    ("8+ years preferred (or equivalent).", True),    # soft cue -> reachable, keep
    ("10+ years of experience.", True),               # bare figure, no hard cue -> keep
    ("6+ years of experience.", True),                # reachable -> keep
    ("7+ years of experience.", True),
    ("5-8 years of experience.", True),               # lower bound 5 -> keep
    ("Join our team!", True),                         # no stated minimum -> keep
])
def test_passes_experience_gap(desc, kept):
    prof = profile(experience_years=5)
    assert passes_experience(make_job(description=desc), prof) is kept


def test_passes_experience_off_when_unset():
    assert passes_experience(make_job(description="12+ years required"), profile()) is True


# --- full pipeline ----------------------------------------------------------

def test_run_pipeline_counts_and_dedup(tmp_path):
    jobs = [
        make_job(id="1", title="Data Engineer", company="Acme", location="Remote",
                 remote=True, country="US", posted_at=NOW - timedelta(hours=1)),
        make_job(id="2", title="Frontend Engineer", company="Acme", location="Remote",
                 remote=True, country="US", posted_at=NOW - timedelta(hours=1)),          # keyword drop
        make_job(id="3", title="Machine Learning Engineer", company="Gamma", location="London",
                 remote=False, country="GB", posted_at=NOW - timedelta(hours=1)),          # location drop
        make_job(id="4", title="Data Engineer", company="Delta", location="Remote",
                 remote=True, country="US", posted_at=NOW - timedelta(days=15)),          # freshness drop
        make_job(id="5", title="Machine Learning Engineer", company="Beta", location="Remote",
                 remote=True, country="US", posted_at=NOW - timedelta(hours=1)),
        make_job(id="6", title="Machine Learning Engineer", company="Beta", location="Remote",
                 remote=True, country="US", posted_at=NOW - timedelta(hours=1)),           # dup of 5
    ]
    factory = lambda ats, board: FakeSource(board, jobs)
    out = run(profile(), seen_cache=SeenCache(tmp_path / "s.json"), now=NOW, source_factory=factory)

    assert out.counts.fetched == 6
    assert out.counts.after_keyword == 5
    assert out.counts.after_fresh == 4
    assert out.counts.after_location == 3
    assert out.counts.after_seniority == 3
    assert out.counts.after_dedup == 2
    assert out.counts.after_eligibility == 2
    assert out.counts.after_experience == 2
    assert {j.title for j in out.jobs} == {"Data Engineer", "Machine Learning Engineer"}


def test_run_pipeline_drops_over_level_and_over_experience(tmp_path):
    fresh = NOW - timedelta(hours=1)
    jobs = [
        make_job(id="1", title="Senior Data Engineer", company="Acme", location="Remote",
                 remote=True, country="US", posted_at=fresh, description="3+ years."),
        make_job(id="2", title="Staff Data Engineer", company="Acme", location="Remote",
                 remote=True, country="US", posted_at=fresh, description="3+ years."),   # seniority drop
        make_job(id="3", title="Senior Machine Learning Engineer", company="Beta", location="Remote",
                 remote=True, country="US", posted_at=fresh,
                 description="10+ years of experience required."),                       # experience drop
        make_job(id="4", title="Machine Learning Engineer", company="Gamma", location="Remote",
                 remote=True, country="US", posted_at=fresh, description="5+ years."),
    ]
    factory = lambda ats, board: FakeSource(board, jobs)
    prof = profile(max_seniority="senior", experience_years=5)
    out = run(prof, seen_cache=SeenCache(tmp_path / "s.json"), now=NOW, source_factory=factory)

    assert out.counts.after_location == 4
    assert out.counts.after_seniority == 3     # Staff dropped (title, before dedup)
    assert out.counts.after_dedup == 3
    assert out.counts.after_eligibility == 3
    assert out.counts.after_experience == 2    # "10+ years" dropped (after enrich)
    assert {j.title for j in out.jobs} == {"Senior Data Engineer", "Machine Learning Engineer"}


def test_run_source_failure_is_a_warning_not_a_crash(tmp_path):
    factory = lambda ats, board: FakeSource(board, raises=True)
    out = run(profile(), seen_cache=SeenCache(tmp_path / "s.json"), now=NOW, source_factory=factory)
    assert out.jobs == []
    assert out.warnings and "fetch failed" in out.warnings[0]


@pytest.mark.parametrize("window,expected", [(None, {"13"}), (timedelta(days=16), {"13", "15"})])
def test_pipeline_freshness_window(tmp_path, window, expected):
    jobs = [make_job(id=str(age), company=str(age), title="AI Engineer",
                     posted_at=NOW - timedelta(days=age)) for age in (13, 15)]
    kwargs = {} if window is None else {"fresh_window": window}
    out = run(profile(keywords=["engineer"]), seen_cache=SeenCache(tmp_path / "s.json"),
              now=NOW, source_factory=lambda ats, board: FakeSource(board, jobs), **kwargs)
    assert {j.id for j in out.jobs} == expected


def test_pipeline_managers_eligibility_and_enriched_experience(tmp_path):
    titles = ["AI / ML Engineer Manager", "Engineering Manager", "Software Engineering Manager",
              "Machine Learning Manager", "Managerial Analytics Engineer", "AI Engineer",
              "Software Engineer", "Machine Learning Engineer", "AI Intern", "AI Research Intern",
              "AI Applied Intern"]
    jobs = [make_job(id=str(i), title=title, company=str(i), posted_at=NOW)
            for i, title in enumerate(titles)]
    enriched = []

    class EnrichedSource(FakeSource):
        def enrich(self, job):
            enriched.append(job.id)
            descriptions = {"8": "Active Secret clearance required. 10 years required.",
                            "9": "Currently enrolled in a Master's or PhD program",
                            "10": "10 years of experience required."}
            return job.model_copy(update={"description": descriptions.get(job.id, "Bachelor's degree required")})

    out = run(profile(keywords=["engineer", "machine learning", "ai"], max_seniority="mid",
                      experience_years=0), seen_cache=SeenCache(tmp_path / "s.json"), now=NOW,
              source_factory=lambda ats, board: EnrichedSource(board, jobs))
    assert out.counts.model_dump() == dict(fetched=11, after_keyword=11, after_fresh=11,
                                         after_location=11, after_seniority=7, after_dedup=7,
                                         after_eligibility=5, after_experience=4)
    assert enriched == [str(i) for i in range(4, 11)]
    assert {j.id for j in out.jobs} == {"4", "5", "6", "7"}
    assert out.boards == ["b"] * 4


@pytest.mark.parametrize('relocation,visa,expected', [
    ('supported', True, True), ('supported', None, True),
    ('supported', False, False), ('required', True, False),
    ('not_supported', True, False), (None, True, False),
])
@pytest.mark.parametrize('country,location', [('GB', 'London'), (None, 'London, UK')])
def test_foreign_mobility(country, location, relocation, visa, expected):
    assert passes_location(make_job(country=country, location=location,
        relocation=relocation, visa_sponsorship=visa), profile()) is expected


@pytest.mark.parametrize('relocation', ['supported', 'required', 'not_supported', None])
def test_us_mobility_does_not_change_eligibility(relocation):
    assert passes_location(make_job(country='US', location='China',
        relocation=relocation, visa_sponsorship=False), profile())


def test_unknown_mobility_preserves_remote_gate():
    job = make_job(location='Remote', remote=True, relocation='supported')
    assert not passes_location(job, profile(location=LocationRule(remote_ok=False)))
