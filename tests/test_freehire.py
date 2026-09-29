"""Offline FreeHire public discovery contract and conservative normalization."""

import json
import pytest
import respx

from helpers import load_fixture
from job_agent.http import SourceError
from job_agent.sources import FreeHireSource, build_source
from job_agent.sources.base import MAX_DESCRIPTION_CHARS, truncate

ENDPOINT = "https://freehire.me/api/v1/agent/jobs/search"


def fetch_payload(payload):
    with respx.mock:
        route = respx.get(ENDPOINT).respond(
            200, content=json.dumps(payload), headers={"Content-Type": "application/json"}
        )
        jobs = FreeHireSource("ai engineer").fetch()
        assert route.call_count == 1
        return jobs


def test_factory():
    source = build_source("freehire", "applied ai engineer")
    assert isinstance(source, FreeHireSource)
    assert source.board == "applied ai engineer"


@respx.mock
def test_request_and_wire_shape():
    payload = load_fixture("freehire.json")
    route = respx.get(ENDPOINT).respond(200, json=payload)
    jobs = FreeHireSource("ai engineer").fetch()
    assert route.call_count == 1  # meta.total must not trigger pagination
    request = route.calls[0].request
    assert request.url.path == "/api/v1/agent/jobs/search"
    assert dict(request.url.params) == {
        "q": "ai engineer", "q_fields": "title", "description_format": "text",
        "countries": "US",
        "sort": "posted_at", "order": "desc", "limit": "100", "offset": "0",
    }
    assert "regions" not in request.url.params
    assert "work_mode" not in request.url.params
    assert "authorization" not in request.headers
    assert len(jobs) == 1
    job = jobs[0]
    raw = payload["data"][0]
    assert job.id == raw["public_slug"]
    assert job.source == "freehire"
    assert job.title == raw["title"]
    assert job.company == raw["company"]
    assert job.location == raw["location"]
    assert job.url == job.apply_url == raw["url"]
    assert job.description == raw["description"]
    assert job.posted_at.isoformat() == "2026-09-29T12:30:00+00:00"
    assert job.remote is True
    assert job.country == "US"


@pytest.mark.parametrize("mode,expected", [
    ("remote", True), ("onsite", False), ("hybrid", False),
    ("unknown", None), (None, None), ({}, None),
])
def test_work_mode(mode, expected):
    payload = load_fixture("freehire.json")
    payload["data"][0]["work_mode"] = mode
    assert fetch_payload(payload)[0].remote is expected


@pytest.mark.parametrize("countries,location,expected", [
    (["CA", "us"], "London, UK", "US"),
    (["GB"], "Remote", "GB"),
    (["CA", "GB"], "Austin, TX", None),
    (["ca", "CA"], "Remote", "CA"),
    (None, "Austin, TX", "US"),
    ([], "London, UK", "United Kingdom"),
    (None, "Worldwide", None),
    ("US", "Remote", None),
    ([{}, "CA"], "Austin, TX", None),
    (["United States"], "Remote", None),
])
def test_country(countries, location, expected):
    payload = load_fixture("freehire.json")
    payload["data"][0].update(countries=countries, location=location)
    assert fetch_payload(payload)[0].country == expected


def test_missing_countries():
    payload = load_fixture("freehire.json")
    del payload["data"][0]["countries"]
    payload["data"][0]["location"] = "Bengaluru, India"
    assert fetch_payload(payload)[0].country == "India"


def test_description_gate():
    payload = load_fixture("freehire.json")
    description = "Full description with text such as x < y. " * 100
    payload["data"][0]["description"] = description
    job = fetch_payload(payload)[0]
    assert job.description == truncate(description)
    assert len(job.description) <= MAX_DESCRIPTION_CHARS + 2


@pytest.mark.parametrize("payload,field", [
    ([], "object"), (None, "object"), ({}, "data"),
    ({"data": {}}, "data"), ({"data": None}, "data"),
    ({"data": [], "meta": []}, "meta"),
    ({"data": [], "meta": None}, "meta"),
])
def test_malformed_envelope(payload, field):
    with pytest.raises(SourceError, match=field):
        fetch_payload(payload)


@pytest.mark.parametrize("meta", [{}, {"total": 0, "limit": 100, "offset": 0}])
def test_empty_page(meta):
    assert fetch_payload({"data": [], "meta": meta}) == []


def test_meta_is_optional():
    assert fetch_payload({"data": []}) == []


@pytest.mark.parametrize("source_name,parameter", [
    ("freehire", "countries"), ("freehire", "q_fields"),
    ("freehire-relocation", "relocation"), ("freehire-relocation", "q_fields"),
])
@respx.mock
def test_ignored_critical_discovery_parameter(source_name, parameter):
    payload = load_fixture("freehire.json")
    payload["meta"] = {"ignored_params": [parameter]}
    respx.get(ENDPOINT).respond(200, json=payload)
    with pytest.raises(SourceError, match=f"critical discovery parameters: {parameter}"):
        build_source(source_name, "ai engineer").fetch()


@pytest.mark.parametrize("source_name", ["freehire", "freehire-relocation"])
@pytest.mark.parametrize("meta", [
    None, {}, {"ignored_params": None}, {"ignored_params": []},
    {"ignored_params": ["sort", "order", "description_format"]},
])
@respx.mock
def test_ignored_params_success(source_name, meta):
    payload = load_fixture("freehire.json")
    payload.pop("meta", None)
    if meta is not None:
        payload["meta"] = meta
    respx.get(ENDPOINT).respond(200, json=payload)
    assert len(build_source(source_name, "ai engineer").fetch()) == 1


@pytest.mark.parametrize("source_name", ["freehire", "freehire-relocation"])
@pytest.mark.parametrize("ignored", [
    "countries", {}, 1, False, [None], [{}], [1], [""], [" "], ["sort", None],
])
@respx.mock
def test_malformed_ignored_params_fails_closed(source_name, ignored):
    payload = load_fixture("freehire.json")
    payload["meta"] = {"ignored_params": ignored}
    respx.get(ENDPOINT).respond(200, json=payload)
    with pytest.raises(SourceError, match="meta.ignored_params"):
        build_source(source_name, "ai engineer").fetch()


@pytest.mark.parametrize("source_name,parameter", [
    ("freehire", "relocation"), ("freehire-relocation", "countries"),
])
@respx.mock
def test_unsent_lane_filter_is_not_critical(source_name, parameter):
    payload = load_fixture("freehire.json")
    payload["meta"] = {"ignored_params": [parameter]}
    respx.get(ENDPOINT).respond(200, json=payload)
    assert len(build_source(source_name, "ai engineer").fetch()) == 1


def test_bad_rows_do_not_discard_page():
    payload = load_fixture("freehire.json")
    good = payload["data"][0]
    malformed = [None, [], "not a job", {}]
    for field in ("public_slug", "title", "company", "url"):
        for value in (None, {}, 123, " "):
            malformed.append({**good, field: value})
    payload["data"] = malformed + [good]
    assert [job.id for job in fetch_payload(payload)] == [good["public_slug"]]


def test_optional_malformed_fields_do_not_discard_job():
    payload = load_fixture("freehire.json")
    payload["data"][0].update(
        location={}, description=[], posted_at=123, work_mode={}, countries={}
    )
    job = fetch_payload(payload)[0]
    assert job.location == "Unknown"
    assert job.description == ""
    assert job.posted_at is None
    assert job.remote is None
    assert job.country is None


def test_remote_location_fallback_and_naive_date():
    payload = load_fixture("freehire.json")
    payload["data"][0].update(location=None, posted_at="2026-09-29T12:30:00")
    job = fetch_payload(payload)[0]
    assert job.location == "Remote"
    assert job.posted_at.utcoffset().total_seconds() == 0


def test_cap_and_no_source_filtering_or_dedup():
    payload = load_fixture("freehire.json")
    row = payload["data"][0]
    row.update(title="Senior Accountant", countries=["GB"],
               posted_at="2020-01-01T00:00:00Z", description="Requires 20 years experience.")
    payload["data"] = [row] * 101
    jobs = fetch_payload(payload)
    assert len(jobs) == 100
    assert all(job.country == "GB" for job in jobs)


@respx.mock
def test_http_failure_propagates():
    respx.get(ENDPOINT).respond(403)
    with pytest.raises(SourceError, match="403"):
        FreeHireSource("ai engineer").fetch()


@respx.mock
def test_relocation_request_and_shared_identity():
    from job_agent.sources import FreeHireRelocationSource
    route = respx.get(ENDPOINT).respond(200, json=load_fixture('freehire.json'))
    us = FreeHireSource('ai engineer').fetch()[0]
    assert 'relocation' not in route.calls[0].request.url.params
    source = build_source('freehire-relocation', '"ai engineer"')
    assert isinstance(source, FreeHireRelocationSource)
    relocated = source.fetch()[0]
    assert route.call_count == 2  # exactly one request per fetch
    request = route.calls[1].request
    assert dict(request.url.params) == {
        'q': '"ai engineer"', 'q_fields': 'title', 'relocation': 'supported',
        'description_format': 'text', 'sort': 'posted_at', 'order': 'desc',
        'limit': '100', 'offset': '0',
    }
    assert 'authorization' not in request.headers
    assert (relocated.source, relocated.id) == (us.source, us.id)
    assert relocated.source == 'freehire'


@pytest.mark.parametrize('source_name', ['freehire', 'freehire-relocation'])
@pytest.mark.parametrize('enrichment,relocation,visa', [
    ({'relocation': 'supported', 'visa_sponsorship': True}, 'supported', True),
    ({'relocation': 'not_supported', 'visa_sponsorship': False}, 'not_supported', False),
    ({'relocation': 'required'}, 'required', None),
    ({}, None, None), (None, None, None), ([], None, None),
    ({'relocation': {}, 'visa_sponsorship': 'true'}, None, None),
    ({'relocation': 'unknown', 'visa_sponsorship': 1}, None, None),
])
@respx.mock
def test_mobility_normalization(source_name, enrichment, relocation, visa):
    payload = load_fixture('freehire.json')
    payload['data'][0]['enrichment'] = enrichment
    respx.get(ENDPOINT).respond(200, json=payload)
    job = build_source(source_name, 'ai engineer').fetch()[0]
    assert job.relocation == relocation
    assert job.visa_sponsorship is visa


@pytest.mark.parametrize('location', ['China', 'Seoul, Korea'])
def test_structured_us_eligibility_survives_foreign_display(location):
    from job_agent.config import SearchProfile
    from job_agent.search import passes_location
    payload = load_fixture('freehire.json')
    payload['data'][0].update(location=location, countries=['CN', 'KR', 'US'])
    assert passes_location(fetch_payload(payload)[0], SearchProfile(keywords=['ai'], sources=[{'ats': 'freehire', 'board': 'ai'}]))
