"""Real CLI workflows use the authoritative truth-ledger path by default."""

import pytest

from job_agent.cli import _build_parser


@pytest.mark.parametrize("command", ["tailor", "apply"])
def test_default_facts_path(command):
    assert _build_parser().parse_args([command]).facts == "data/facts.yaml"
