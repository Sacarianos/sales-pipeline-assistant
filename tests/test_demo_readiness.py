"""Issue 09: the five acceptance cases in the exact shape the demo asks them,
plus the wiring the demo depends on holding together — catalog-sourced
examples, config-pinned model IDs, and a README that makes the trust
argument.

The five cases run offline here, the same primary seam every other suite
uses, so they're fast and deterministic in CI. They also passed against the
real `claude-sonnet-5` / `claude-haiku-4-5-20251001` models by hand during
implementation — see the README for how to re-run that check locally with
an API key, since a live model call has no place in a suite that runs on
every commit without one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from acme import config
from acme.catalog import build_catalog
from acme.domain import Answered, Refused
from acme.pipeline import ask

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_enterprise_tracking_answers_end_to_end_with_prose(data):
    answer = ask("how is Enterprise tracking against quota this quarter", data)

    assert isinstance(answer, Answered)
    assert answer.intent.metric == "attainment"
    assert round(answer.facts["attainment_pct"].value, 1) == 4.5
    assert answer.prose
    assert answer.restated


def test_reps_at_risk_of_missing_q2_answers_end_to_end(data):
    answer = ask("which reps are at risk of missing Q2", data)

    assert isinstance(answer, Answered)
    assert answer.intent.metric == "risk"
    assert answer.facts["at_risk_count"].value == 8
    assert answer.prose


def test_q2_versus_same_point_in_q1_answers_end_to_end(data):
    answer = ask(
        "how does Q2 attainment compare to where we were at the same point in Q1",
        data,
    )

    assert isinstance(answer, Answered)
    assert answer.intent.metric == "comparison"
    assert round(answer.facts["attainment_pct"].value, 1) == 8.4
    assert round(answer.facts["comparison_attainment_pct"].value, 1) == 21.3
    assert answer.prose


def test_west_region_question_refuses_with_its_computed_conflict_count(data):
    answer = ask("how is the West region doing this quarter", data)

    assert isinstance(answer, Refused)
    assert str(data.region_mismatch_count) in answer.reason
    assert str(data.region_deal_count) in answer.reason


def test_slack_sentiment_question_refuses_with_the_catalog_coverage_list(data):
    catalog = build_catalog(data)
    answer = ask("what did our Slack sentiment look like this quarter", data)

    assert isinstance(answer, Refused)
    for spec in catalog.metrics:
        assert spec.name in answer.hint


def test_sidebar_examples_come_from_the_catalog_not_a_hardcoded_list(data):
    catalog = build_catalog(data)
    app_source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")

    # The sidebar loop reads spec.examples off the catalog it builds; there
    # is no separate literal list of example questions anywhere in app.py
    # for it to drift out of sync with.
    assert "catalog.metrics" in app_source
    assert "spec.examples" in app_source
    for spec in catalog.metrics:
        for example in spec.examples:
            assert example not in app_source


def test_router_and_narrator_models_come_from_a_configuration_constant():
    assert config.ROUTER_MODEL == "claude-sonnet-5"
    assert config.NARRATOR_MODEL == "claude-haiku-4-5-20251001"

    router_source = (REPO_ROOT / "acme" / "router.py").read_text(encoding="utf-8")
    narrator_source = (REPO_ROOT / "acme" / "narrator.py").read_text(encoding="utf-8")
    assert "ROUTER_MODEL" in router_source and "claude-sonnet-5" not in router_source
    assert (
        "NARRATOR_MODEL" in narrator_source
        and "claude-haiku-4-5-20251001" not in narrator_source
    )


@pytest.fixture(scope="module")
def readme_text() -> str:
    path = REPO_ROOT / "README.md"
    assert path.exists(), "README.md is required for demo readiness"
    return path.read_text(encoding="utf-8")


def test_readme_covers_the_trust_argument_and_architecture(readme_text):
    lowered = readme_text.lower()
    assert "never produces a number" in lowered or "never invents a number" in lowered
    assert "verifier" in lowered
    assert "narrator" in lowered
    assert "router" in lowered
    for name in ("claude-sonnet-5", "claude-haiku-4-5-20251001"):
        assert name in readme_text


def test_readme_carries_a_worked_example_of_adding_a_metric(readme_text):
    lowered = readme_text.lower()
    assert "acme/metrics" in readme_text or "acme\\metrics" in readme_text
    assert "@metric" in readme_text
    assert "one file" in lowered


def test_readme_documents_clean_checkout_setup(readme_text):
    lowered = readme_text.lower()
    assert "pip install" in lowered
    assert "streamlit run" in lowered
    assert "anthropic_api_key" in lowered
