"""Tests for the graph's observability sinks (failure log + DPO preferences).

The sinks are injected, so these spies capture what the real
append_jsonl / log_preference_candidates would receive, without touching disk.
"""

from app.graph.graph import build_planner_graph
from app.graph.runtime import PlannerRuntime
from app.graph.state import TripPlanState
from app.models.schemas import TripPlan

from .builders import good_grounded_plan, make_request


class _RaisingLLM:
    def invoke(self, messages, **kwargs):
        raise RuntimeError("llm unavailable")


class _OkLLM:
    def invoke(self, messages, **kwargs):
        return "{}"


class _EmptyLLM:
    """Mimics a reasoning model: the call succeeds but content is empty."""

    def invoke(self, messages, **kwargs):
        return "   \n  "


def _run(runtime, *, max_attempts):
    request = make_request(adults=2)
    compiled = build_planner_graph(runtime, max_attempts=max_attempts)
    initial: TripPlanState = {
        "request": request,
        "snapshot_parts": [],
        "candidates": [],
        "failures": [],
        "attempt": 0,
        "use_fallback_llm": False,
        "status": "start",
    }
    return request, compiled.invoke(initial, config={"recursion_limit": 50})


def test_records_each_failure():
    """Every failed attempt persists one failure row; no preferences on total failure."""
    failure_rows = []
    pref_calls = []
    runtime = PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},
        build_query=lambda req, ctx: "QUERY",
        parse_plan=lambda resp, req, ctx: good_grounded_plan(req),
        primary_llm=_RaisingLLM(),
        fallback_llm=_RaisingLLM(),
        has_distinct_fallback=False,
        record_failure=failure_rows.append,
        record_preferences=lambda *args: pref_calls.append(args),
    )

    _request, state = _run(runtime, max_attempts=2)

    assert state["status"] == "fallback_success"
    assert len(failure_rows) == 2  # one per attempt
    assert failure_rows[0]["preference_reason"] == "planner_llm_call_failed"
    assert pref_calls == []  # no chosen plan -> nothing to prefer


def test_logs_preferences_after_recovering_from_failure():
    """A parse failure followed by successes yields one DPO preference log call."""
    failure_rows = []
    pref_calls = []
    parse_count = {"n": 0}

    def flaky_parse(resp, req, ctx):
        parse_count["n"] += 1
        if parse_count["n"] == 1:
            raise ValueError("bad json")
        return good_grounded_plan(req)

    runtime = PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},
        build_query=lambda req, ctx: "QUERY",
        parse_plan=flaky_parse,
        primary_llm=_OkLLM(),
        fallback_llm=_OkLLM(),
        has_distinct_fallback=False,
        record_failure=failure_rows.append,
        record_preferences=lambda *args: pref_calls.append(args),
    )

    _request, state = _run(runtime, max_attempts=5)

    assert state["status"] == "llm_success"
    assert len(failure_rows) == 1  # the single parse failure
    assert failure_rows[0]["preference_reason"] == "planner_schema_invalid"

    assert len(pref_calls) == 1
    query, _req, chosen, failures, label = pref_calls[0]
    assert query == "QUERY"
    assert isinstance(chosen, TripPlan)
    assert len(failures) == 1  # the failures collected along the way
    assert isinstance(label, str)


def test_empty_content_is_flagged_clearly():
    """Empty LLM content fails fast with an actionable reason, not a parse error."""
    failure_rows = []
    parsed = {"n": 0}

    def counting_parse(resp, req, ctx):
        parsed["n"] += 1
        return good_grounded_plan(req)

    runtime = PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},
        build_query=lambda req, ctx: "QUERY",
        parse_plan=counting_parse,
        primary_llm=_EmptyLLM(),
        fallback_llm=_EmptyLLM(),
        has_distinct_fallback=False,
        record_failure=failure_rows.append,
    )

    _request, state = _run(runtime, max_attempts=2)

    assert state["status"] == "fallback_success"
    assert parsed["n"] == 0  # parser is never reached on empty content
    assert len(failure_rows) == 2
    assert failure_rows[0]["preference_reason"] == "planner_empty_response"
    assert failure_rows[0]["error_type"] == "EmptyLLMResponseError"


def test_sinks_optional_no_crash_without_them():
    """A runtime without sinks runs fine (sinks default to None)."""
    runtime = PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},
        build_query=lambda req, ctx: "QUERY",
        parse_plan=lambda resp, req, ctx: good_grounded_plan(req),
        primary_llm=_OkLLM(),
        fallback_llm=_OkLLM(),
    )
    _request, state = _run(runtime, max_attempts=3)
    assert state["status"] == "llm_success"
