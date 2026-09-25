"""V3: promote a recurring exploratory plan to a registered metric.

The promotion module is a direct seam for candidate grouping and for every
refusal. The end-to-end tests promote a logged plan into a temporary file,
load it the way `registry.discover` would, and ask the question again
through `ask`, which is the whole point: the same question moves from the
exploratory lane to the metric lane.
"""

from __future__ import annotations

import importlib.util
import io
import sys

import pytest

from acme import registry
from acme.domain import Answered
from acme.pipeline import ask
from acme.promote import main
from acme.promotion import Promotion, PromotionRefused, find_candidates, problems, promote, render
from acme.query_log import LogRecord, QueryLog
from tests.test_llm_router_and_refusals import StubRouterClient

LOSS_REASONS = {
    "frame": "deals_q2",
    "filters": [{"column": "stage", "op": "eq", "value": "Closed Lost"}],
    "group_by": ["loss_reason"],
    "aggregate": {"function": "count"},
    "sort_by": "result",
}
LOSS_REASONS_Q1_ENTERPRISE = {
    "frame": "deals_q1",
    "filters": [
        {"column": "segment", "op": "eq", "value": "Enterprise"},
        {"column": "stage", "op": "eq", "value": "Closed Lost"},
        {"column": "period", "op": "eq", "value": "Q1-2026"},
    ],
    "group_by": ["loss_reason"],
    "aggregate": {"function": "count"},
    "sort_by": "result",
    "descending": True,
}
TOTAL_QUOTA = {"frame": "quotas", "aggregate": {"function": "sum", "column": "quota"}}

DEFINITION = (
    "Closed-lost deals in the period, counted by the loss reason the rep "
    "recorded. A lost deal with no reason recorded is counted as blank."
)


def _answered(question: str, plan: dict) -> LogRecord:
    return LogRecord(question=question, outcome="answered", plan=plan, matched_rows=9, row_count=7)


RECORDS = [
    _answered("why are we losing deals", LOSS_REASONS),
    _answered("why are we losing deals", LOSS_REASONS),
    _answered("why did Enterprise lose deals in Q1", LOSS_REASONS_Q1_ENTERPRISE),
    _answered("how much quota do we carry", TOTAL_QUOTA),
    LogRecord(question="slack sentiment", outcome="declined", reason="no column"),
    LogRecord(question="territory", outcome="rejected", plan={"frame": "deals_q2", "group_by": ["region"]}),
]


@pytest.fixture
def clean_registry():
    """Promoted test metrics register into the process-wide registry, so put
    it back the way it was afterwards."""
    before = dict(registry._REGISTRY)
    yield
    registry._REGISTRY.clear()
    registry._REGISTRY.update(before)
    for name in [m for m in sys.modules if m.startswith("acme.metrics.promoted_test_")]:
        del sys.modules[name]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(f"acme.metrics.{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate(data, frame="deals"):
    return next(c for c in find_candidates(RECORDS, data) if c.plan["frame"] == frame)


def _promotion(**overrides) -> Promotion:
    fields = dict(
        name="promoted_test_loss_reasons",
        description=DEFINITION,
        groupings=("segment",),
        examples=("why are we losing deals",),
        definition_keys=("period_membership",),
    )
    fields.update(overrides)
    return Promotion(**fields)


# --- candidates -------------------------------------------------------------


def test_plans_that_differ_only_by_snapshot_period_and_scope_are_one_candidate(data):
    candidates = find_candidates(RECORDS, data)

    loss = _candidate(data)
    assert loss.count == 3
    assert loss.questions == ("why are we losing deals", "why did Enterprise lose deals in Q1")
    assert loss.scope_seen == {"segment": ("Enterprise",)}
    assert loss.plan["frame"] == "deals"
    assert all(f["column"] not in ("period", "segment") for f in loss.plan["filters"])
    assert candidates[0] == loss


# --- refusals ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        (dict(description=""), "write a definition"),
        (dict(description="Loss reasons."), "at least"),
        (dict(name="attainment"), "already registered"),
    ],
)
def test_a_promotion_missing_a_decision_is_refused(data, overrides, fragment):
    found = problems(_promotion(**overrides), _candidate(data), data)
    assert any(fragment in p for p in found), found


def test_a_copied_machine_description_is_refused(data):
    candidate = _candidate(data)
    found = problems(_promotion(description=candidate.description), candidate, data)
    assert any("in your own words" in p for p in found), found


def test_promote_refuses_to_write_anything_when_there_are_problems(data, tmp_path):
    with pytest.raises(PromotionRefused):
        promote(_promotion(description=""), _candidate(data), data, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_promote_refuses_to_overwrite_an_existing_file(data, tmp_path):
    (tmp_path / "promoted_test_loss_reasons.py").write_text("# someone's work\n")
    with pytest.raises(PromotionRefused, match="already exists"):
        promote(_promotion(), _candidate(data), data, tmp_path)


# --- the generated metric ---------------------------------------------------


def test_the_generated_file_holds_the_plan_as_data_and_the_definition_verbatim(data):
    source = render(_promotion(), _candidate(data))
    compile(source, "promoted_test_loss_reasons.py", "exec")
    assert "PLAN = {" in source
    assert '"Closed Lost"' in source
    assert "eval" not in source
    joined = "".join(line.strip().strip('"') for line in source.splitlines())
    assert DEFINITION.replace(" ", "") in joined.replace(" ", "")


def test_a_promoted_question_answers_in_the_metric_lane(data, tmp_path, clean_registry):
    path = promote(_promotion(), _candidate(data), data, tmp_path)
    _load(path, "promoted_test_loss_reasons")

    client = StubRouterClient(
        tool_input=dict(
            metric="promoted_test_loss_reasons",
            grouping="overall",
            period="Q2-2026",
            restated="Reading this as loss reasons for Q2-2026.",
        )
    )
    answer = ask("why are we losing deals", data, client)

    assert isinstance(answer, Answered)
    assert answer.lane == "metric"
    assert answer.snapshot == "Q2"
    q2 = data.deals("Q2")
    lost = q2[(q2["stage"] == "Closed Lost") & (q2["period"] == "Q2-2026")]
    assert int(answer.table["count"].sum()) == len(lost)
    assert len(answer.source_rows) == len(lost)
    assert "definition:period_membership" in {f.kind for f in answer.flags}


def test_a_promoted_metric_scopes_to_the_asked_period_and_segment(data, tmp_path, clean_registry):
    path = promote(_promotion(), _candidate(data), data, tmp_path)
    _load(path, "promoted_test_loss_reasons")

    client = StubRouterClient(
        tool_input=dict(
            metric="promoted_test_loss_reasons",
            grouping="segment",
            segment="Enterprise",
            period="Q1-2026",
            restated="Reading this as Enterprise loss reasons for Q1-2026.",
        )
    )
    answer = ask("why did Enterprise lose deals in Q1", data, client)

    assert isinstance(answer, Answered)
    assert answer.snapshot == "Q1"
    assert set(answer.source_rows["segment"]) <= {"Enterprise"}
    assert set(answer.source_rows["period"]) <= {"Q1-2026"}


def test_a_promoted_metric_over_quotas_answers_without_deal_flags(data, tmp_path, clean_registry):
    promotion = _promotion(
        name="promoted_test_quota_total",
        description="Total quota carried by every rep for the period, from the quota source file.",
        groupings=("segment", "rep"),
        examples=("how much quota do we carry",),
    )
    path = promote(promotion, _candidate(data, "quotas"), data, tmp_path)
    _load(path, "promoted_test_quota_total")

    client = StubRouterClient(
        tool_input=dict(
            metric="promoted_test_quota_total",
            grouping="rep",
            rep="Marcus Rivera",
            period="Q2-2026",
            restated="Reading this as Marcus Rivera's quota for Q2-2026.",
        )
    )
    answer = ask("what is Marcus's quota", data, client)

    assert isinstance(answer, Answered)
    quotas = data.quotas
    expected = quotas[(quotas["rep_name"] == "Marcus Rivera") & (quotas["period"] == "Q2-2026")]["quota"].sum()
    assert answer.facts["result"].value == expected
    assert not {"small_sample", "changed_deals"} & {f.kind for f in answer.flags}


# --- command line -----------------------------------------------------------


def _log(tmp_path) -> QueryLog:
    log = QueryLog(tmp_path / "query_log.jsonl")
    for record in RECORDS:
        log.append(record)
    return log


def test_the_list_command_shows_candidates_with_their_questions(tmp_path):
    log = _log(tmp_path)
    out = io.StringIO()
    assert main(["list", "--log", str(log.path)], out=out) == 0
    text = out.getvalue()
    assert "asked 3 times" in text
    assert "why are we losing deals" in text
    assert "Asked scoped to: segment Enterprise" in text


def test_the_promote_command_writes_the_metric(data, tmp_path):
    log = _log(tmp_path)
    candidate_id = _candidate(data).id
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir()
    out = io.StringIO()
    code = main(
        [
            "promote", candidate_id,
            "--log", str(log.path),
            "--metrics-dir", str(metrics_dir),
            "--name", "promoted_test_loss_reasons",
            "--description", DEFINITION,
            "--grouping", "segment",
        ],
        out=out,
    )
    assert code == 0, out.getvalue()
    assert (metrics_dir / "promoted_test_loss_reasons.py").exists()
    assert "reads only the period each question asks about" in out.getvalue()
