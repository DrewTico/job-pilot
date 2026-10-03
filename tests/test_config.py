"""SearchProfile validation for the seniority / experience knobs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from job_agent.config import SearchProfile, SourceRef


def _profile(**overrides) -> SearchProfile:
    data = dict(keywords=["data engineer"], sources=[SourceRef(ats="greenhouse", board="b")])
    data.update(overrides)
    return SearchProfile.model_validate(data)


def test_cross_company_search_ats_names_are_known():
    prof = _profile(sources=[
        SourceRef(ats="sr-search", board="machine learning engineer"),
        SourceRef(ats="remotive", board="machine learning"),
        SourceRef(ats="remoteok", board="machine-learning"),
        SourceRef(ats="freehire", board="ai engineer"),
        SourceRef(ats="freehire-relocation", board='"ai engineer"'),
        SourceRef(ats="greenhouse", board="stripe"),
    ])
    assert prof.unknown_sources() == []     # none warned about / skipped


def test_seniority_and_experience_default_to_off():
    prof = _profile()
    assert prof.max_seniority is None
    assert prof.experience_years is None


def test_max_seniority_accepts_known_level_case_insensitively():
    assert _profile(max_seniority="Senior").max_seniority == "senior"
    assert _profile(max_seniority="staff").max_seniority == "staff"


def test_max_seniority_rejects_unknown_level():
    with pytest.raises(ValidationError, match="max_seniority"):
        _profile(max_seniority="wizard")


def test_negative_experience_years_is_rejected():
    with pytest.raises(ValidationError):
        _profile(experience_years=-2)


def test_task_and_threshold_defaults():
    from job_agent.config import Settings
    settings = Settings()
    assert settings.scoring_model == settings.tailoring_model == 'claude-sonnet-5'
    assert settings.classification_model == 'claude-haiku-4-5-20251001'
    assert (settings.score_threshold, settings.max_packets_per_day) == (65, 8)


def test_environment_overrides_and_legacy_fallback(monkeypatch):
    from job_agent.config import load_settings, Settings
    import job_agent.config as config
    monkeypatch.setattr(config, 'load_dotenv', lambda: None)
    for name in ['MODEL', 'SCORING_MODEL', 'CLASSIFICATION_MODEL', 'TAILORING_MODEL',
                 'SCORE_THRESHOLD', 'MAX_PACKETS_PER_DAY']:
        monkeypatch.delenv('JOB_AGENT_' + name, raising=False)
    assert load_settings().scoring_model == 'claude-sonnet-5'
    monkeypatch.setenv('JOB_AGENT_MODEL', 'legacy')
    settings = load_settings()
    assert settings.model == settings.scoring_model == settings.classification_model == settings.tailoring_model == 'legacy'
    for name, value in [('SCORING_MODEL', 'score'), ('CLASSIFICATION_MODEL', 'classify'),
                        ('TAILORING_MODEL', 'tailor'), ('SCORE_THRESHOLD', '72'), ('MAX_PACKETS_PER_DAY', '3')]:
        monkeypatch.setenv('JOB_AGENT_' + name, value)
    settings = load_settings()
    assert (settings.scoring_model, settings.classification_model, settings.tailoring_model) == ('score', 'classify', 'tailor')
    assert (settings.score_threshold, settings.max_packets_per_day) == (72, 3)
    assert Settings(model='old').scoring_model == 'old'


@pytest.mark.parametrize('field,value', [('score_threshold', -1), ('score_threshold', 101),
                                         ('max_packets_per_day', 0)])
def test_invalid_threshold_environment(monkeypatch, field, value):
    import job_agent.config as config
    monkeypatch.setattr(config, 'load_dotenv', lambda: None)
    monkeypatch.setenv('JOB_AGENT_' + field.upper(), str(value))
    with pytest.raises(ValidationError):
        config.load_settings()
