"""Scoring: defensive JSON parsing, retry-once, and the unscored fallback."""

from __future__ import annotations

import json
import pytest
from types import SimpleNamespace

from job_agent.config import LocationRule, SearchProfile, Settings, SourceRef
from job_agent.models import Job
from job_agent.scoring import score_jobs, score_one

PROFILE = SearchProfile(
    keywords=["data engineer"],
    location=LocationRule(),
    sources=[SourceRef(ats="fake", board="b")],
    candidate_summary="data/ML engineer",
)
JOB = Job(id="1", title="Data Engineer", company="Acme", location="Remote",
          url="http://x", source="demo", remote=True, country="US",
          description="Build pipelines.")


class FakeMessages:
    """Returns queued responses (or raises queued exceptions) per create()."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


def text_response(payload: str):
    return SimpleNamespace(stop_reason="end_turn",
                           content=[SimpleNamespace(type="text", text=payload)])


def tool_response(data: dict):
    return SimpleNamespace(stop_reason="tool_use",
                           content=[SimpleNamespace(type="tool_use", name="record_fit", input=data)])


VALID = json.dumps({"score": 82, "verdict": "strong",
                    "reasons": ["good match"], "missing_requirements": ["Kafka"]})


def test_structured_valid_output():
    client = FakeClient([text_response(VALID)])
    result = score_one(client, "m", JOB, PROFILE, method="structured")
    assert result.score == 82
    assert result.verdict == "strong"
    assert result.reasons == ("good match",)
    assert result.missing_requirements == ("Kafka",)


def test_score_is_clamped_to_0_100():
    client = FakeClient([text_response(json.dumps(
        {"score": 150, "verdict": "strong", "reasons": [], "missing_requirements": []}))])
    result = score_one(client, "m", JOB, PROFILE)
    assert result.score == 100


def test_retries_once_then_succeeds():
    client = FakeClient([text_response("not json at all"), text_response(VALID)])
    result = score_one(client, "m", JOB, PROFILE)
    assert client.messages.calls == 2
    assert result.verdict == "strong"


def test_unscored_after_two_failures():
    client = FakeClient([text_response("garbage"), text_response("still garbage")])
    result = score_one(client, "m", JOB, PROFILE)
    assert client.messages.calls == 2
    assert result.verdict == "unscored"
    assert result.score is None
    assert result.job == JOB  # the job is preserved, not dropped


def test_tool_use_method_reads_tool_input():
    client = FakeClient([tool_response(
        {"score": 70, "verdict": "possible", "reasons": ["ok"], "missing_requirements": []})])
    result = score_one(client, "m", JOB, PROFILE, method="tool")
    assert result.verdict == "possible"
    assert result.score == 70


def test_score_jobs_uses_injected_client():
    settings = Settings(anthropic_api_key="x", model="m")
    client = FakeClient([text_response(VALID), text_response(VALID)])
    results = score_jobs([JOB, JOB], settings, PROFILE, client=client)
    assert len(results) == 2
    assert all(r.verdict == "strong" for r in results)


def test_prompt_mobility_without_llm(monkeypatch):
    import job_agent.scoring as scoring
    monkeypatch.setattr(scoring, '_call_structured', lambda *a: pytest.fail('LLM called'))
    monkeypatch.setattr(scoring, '_call_tool', lambda *a: pytest.fail('LLM called'))
    for visa, value in [(True, 'true'), (False, 'false'), (None, 'unknown')]:
        prompt = scoring.build_user_prompt(JOB.model_copy(update={
            'relocation': 'supported', 'visa_sponsorship': visa}), PROFILE)
        assert 'Relocation support: supported' in prompt
        assert f'Visa sponsorship: {value}' in prompt
        for content in [PROFILE.candidate_summary, JOB.title, JOB.company, JOB.description,
                        'lower mobility friction', 'uncertainty/gap', 'deterministic filtering']:
            assert content in prompt
