"""Issue 01: the AST-validated sandbox the fallback lane runs generated
pandas expressions inside.

This is the highest-risk code in the system, so it's a direct test seam
rather than something inferred through the pipeline, per the parent spec's
testing decisions. The tests below are adversarial: each one is an attempt
to reach something the allowlist should refuse, not an illustration of the
happy path.
"""

from __future__ import annotations

import ast

import pandas as pd
import pytest

from acme.sandbox import SandboxRejection, SandboxResult, execute, run

FRAMES = {
    "deals": pd.DataFrame(
        {
            "deal_id": ["OPP-1", "OPP-2", "OPP-3"],
            "segment": ["Enterprise", "SMB", "Enterprise"],
            "deal_value": [100.0, 50.0, 25.0],
            "stage": ["Closed Won", "Closed Lost", "Closed Won"],
        }
    )
}


def test_a_valid_expression_over_an_allowlisted_frame_returns_a_result():
    outcome = run("deals['deal_value'].sum()", FRAMES)
    assert isinstance(outcome, SandboxResult)
    assert outcome.value == 175.0


def test_a_valid_groupby_expression_returns_a_series():
    outcome = run("deals.groupby('segment')['deal_value'].sum()", FRAMES)
    assert isinstance(outcome, SandboxResult)
    assert isinstance(outcome.value, pd.Series)
    assert outcome.value["Enterprise"] == 125.0


def test_a_filtered_boolean_mask_expression_returns_the_matching_rows():
    outcome = run("deals[deals['stage'] == 'Closed Won']", FRAMES)
    assert isinstance(outcome, SandboxResult)
    assert isinstance(outcome.value, pd.DataFrame)
    assert len(outcome.value) == 2


@pytest.mark.parametrize(
    "expression",
    [
        "deals.__class__",
        "deals.__class__.__bases__",
        "deals.__init__.__globals__",
        "().__class__.__bases__[0].__subclasses__()",
        "deals._data",
        "deals._internal_names",
    ],
)
def test_underscore_attribute_access_is_rejected_by_one_rule(expression):
    outcome = run(expression, FRAMES)
    assert isinstance(outcome, SandboxRejection)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hi')",
        "deals['deal_value'].apply(lambda x: x)",
        "[x for x in deals['deal_value']]",
        "{x for x in deals['deal_value']}",
        "(x for x in deals['deal_value'])",
        "(deals_walrus := deals['deal_value'].sum())",
        "x = 5",
        "import os",
    ],
)
def test_imports_lambdas_comprehensions_and_assignment_are_rejected(expression):
    outcome = run(expression, FRAMES)
    assert isinstance(outcome, SandboxRejection)


def test_a_call_to_a_method_not_on_the_allowlist_is_rejected():
    outcome = run("deals.to_csv('pwned.csv')", FRAMES)
    assert isinstance(outcome, SandboxRejection)


def test_a_bare_function_call_is_rejected():
    """Only method calls on the allowlisted frames are permitted — a bare
    call to a name, even a builtin-sounding one like `len`, is not, since
    nothing is bound into scope except the frames themselves."""
    outcome = run("len(deals)", FRAMES)
    assert isinstance(outcome, SandboxRejection)


def test_a_reference_to_a_name_that_is_not_an_allowlisted_frame_is_rejected():
    # 'sum' is on the method allowlist, so this exercises the frame-name
    # check specifically rather than being rejected for the method first.
    outcome = run("reps.sum()", FRAMES)
    assert isinstance(outcome, SandboxRejection)
    assert "reps" in outcome.reason


def test_a_rejected_expression_is_not_partially_executed():
    """One disallowed method anywhere in the expression rejects the whole
    thing outright — there is no salvaging the valid parts around it."""
    outcome = run("deals.to_csv('x')['deal_value'].sum()", FRAMES)
    assert isinstance(outcome, SandboxRejection)


def test_validation_runs_before_execution(monkeypatch):
    """`execute` must never be called for an expression `validate` rejects."""

    def _must_not_run(*args, **kwargs):
        raise AssertionError("execute() ran despite a validation failure")

    monkeypatch.setattr("acme.sandbox.execute", _must_not_run)
    outcome = run("__import__('os').system('echo hi')", FRAMES)
    assert isinstance(outcome, SandboxRejection)


def test_reaching_a_builtin_fails_even_if_validation_were_bypassed():
    """Defense in depth: a hand-built malicious tree that skips `validate`
    entirely still finds nothing reachable, because `execute` binds only the
    given frames and strips builtins before running anything."""
    tree = ast.parse("__import__('os').system('echo hi')", mode="eval")
    with pytest.raises(NameError):
        execute(tree, FRAMES)


def test_a_result_that_is_not_a_dataframe_series_or_scalar_is_rejected():
    outcome = run("deals.columns", FRAMES)
    assert isinstance(outcome, SandboxRejection)


def test_a_large_result_is_truncated_with_the_full_count_reported():
    big = pd.DataFrame({"n": list(range(500))})
    outcome = run("big", {"big": big})
    assert isinstance(outcome, SandboxResult)
    assert outcome.truncated is True
    assert outcome.row_count == 500
    assert len(outcome.value) < 500


def test_a_small_result_is_not_truncated():
    outcome = run("deals", FRAMES)
    assert isinstance(outcome, SandboxResult)
    assert outcome.truncated is False
    assert outcome.row_count == len(FRAMES["deals"])


def test_a_scalar_result_carries_no_row_count():
    outcome = run("deals['deal_value'].sum()", FRAMES)
    assert isinstance(outcome, SandboxResult)
    assert outcome.row_count is None
    assert outcome.truncated is False


def test_a_syntax_error_is_a_rejection_not_an_unhandled_exception():
    outcome = run("deals[[[[", FRAMES)
    assert isinstance(outcome, SandboxRejection)


def test_mutually_exclusive_frames_cannot_be_combined_by_any_operator():
    """The whole-tree check runs after the per-node walk, so it catches
    combination by any means: arithmetic between two aggregates, a raw
    elementwise operator between two columns, or a call chained off either
    side — not just the specific shapes exercised here."""
    two_snapshots = {
        "left": pd.DataFrame({"deal_value": [100.0]}),
        "right": pd.DataFrame({"deal_value": [500.0]}),
    }
    excl = (frozenset({"left", "right"}),)

    for expression in [
        "left['deal_value'].sum() + right['deal_value'].sum()",
        "left['deal_value'] + right['deal_value']",
        "left['deal_value'].sum() - right['deal_value'].sum()",
    ]:
        outcome = run(expression, two_snapshots, mutually_exclusive=excl)
        assert isinstance(outcome, SandboxRejection), expression


def test_mutually_exclusive_frames_still_allow_either_one_alone():
    two_snapshots = {
        "left": pd.DataFrame({"deal_value": [100.0]}),
        "right": pd.DataFrame({"deal_value": [500.0]}),
    }
    excl = (frozenset({"left", "right"}),)

    outcome = run("right['deal_value'].sum()", two_snapshots, mutually_exclusive=excl)
    assert isinstance(outcome, SandboxResult)
    assert outcome.value == 500.0


def test_negative_numbers_and_boolean_combinators_are_allowed():
    # deal_value is [100, 50, 25]; strictly between 0 and 60 matches two rows.
    outcome = run(
        "deals[(deals['deal_value'] > 0) & (deals['deal_value'] < 60)]", FRAMES
    )
    assert isinstance(outcome, SandboxResult)
    assert len(outcome.value) == 2
