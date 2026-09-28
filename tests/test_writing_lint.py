"""Shared writing rules and preservation of stricter screening behavior."""

import pytest

from job_agent.writing_lint import lint_writing


@pytest.mark.parametrize("text", ["Plain\u2014specific.", "\u2014"])
def test_explicit_u2014_em_dash_rejection(text):
    assert any("dash" in violation for violation in lint_writing(text))


@pytest.mark.parametrize("text", [
    "Plain \u2013 specific.", "Plain\u2013specific.", "2020\u20132024",
])
def test_en_dash_rejection_preserves_stricter_screening(text):
    assert any("dash" in violation for violation in lint_writing(text))


@pytest.mark.parametrize("phrase", [
    "passionate", "leverage", "synergy", "I am excited to apply", "thrilled",
    "delve", "fast-paced", "I hope this email finds you well", "cutting-edge",
    "dynamic", "go-getter",
])
def test_all_claude_banned_phrases(phrase):
    text = "Start. " + phrase.upper().replace(" ", "\n\t") + "."
    assert any("banned phrase" in violation for violation in lint_writing(text))


@pytest.mark.parametrize("text", [
    "leveraged", "spearheaded", "passionate about", "excited to", "deep dive",
    "robust", "seamless", "in today's landscape", "I thrive",
    "wealth of experience", "testament", "underscores",
    "Not only did I build it, but I maintained it.",
    "Not just scripts, but services.",
])
def test_stricter_existing_screening_rules(text):
    assert lint_writing(text)


@pytest.mark.parametrize("text", [
    "", "I build reliable data pipelines.", "A batch-based system, built in 2024.",
    "The name is biodynamic.",
])
def test_clean_prose_and_word_boundaries(text):
    assert lint_writing(text) == []
