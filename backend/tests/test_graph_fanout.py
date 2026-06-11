"""Tests for the parallel context fan-out path.

When the runtime exposes per-subtask collectors, context collection splits into
three concurrent nodes that merge into one planner_context. These tests run that
path offline and check the merge plus per-source error isolation.
"""

from app.graph.graph import build_planner_graph
from app.graph.runtime import PlannerRuntime
from app.graph.state import TripPlanState

from .builders import good_grounded_plan, make_request

MAX_ATTEMPTS = 2


class _OkLLM:
    def invoke(self, messages, **kwargs):
        return "{}"


def _fanout_runtime(received_contexts, *, fail=None):
    """Build a fan-out runtime; `fail` names a source that should raise."""
    calls = {"attractions": 0, "weather": 0, "hotels": 0}

    def collector(name, payload):
        def _call(request):
            calls[name] += 1
            if fail == name:
                raise RuntimeError(f"{name} source down")
            return {"tool_snapshot": payload, "status": {"ok": True}}

        return _call

    def empty_context(request):
        return {"tool_snapshot": {"tool_status": {}}}

    def build_query(request, context):
        received_contexts.append(context)
        return "QUERY"

    llm = _OkLLM()
    runtime = PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},  # unused on fan-out path
        build_query=build_query,
        parse_plan=lambda resp, req, ctx: good_grounded_plan(req),
        primary_llm=llm,
        fallback_llm=llm,
        has_distinct_fallback=False,
        collect_attractions=collector("attractions", {"classic_pois": [{"name": "故宫"}]}),
        collect_weather=collector("weather", {"weather": [{"date": "2025-06-01"}]}),
        collect_hotels=collector("hotels", {"hotel_pois": [{"name": "如家"}]}),
        empty_context=empty_context,
    )
    return runtime, calls


def _run(runtime):
    request = make_request(adults=2)
    compiled = build_planner_graph(runtime, max_attempts=MAX_ATTEMPTS)
    initial: TripPlanState = {
        "request": request,
        "snapshot_parts": [],
        "candidates": [],
        "failures": [],
        "attempt": 0,
        "use_fallback_llm": False,
        "status": "start",
    }
    return compiled.invoke(initial, config={"recursion_limit": 50})


def test_fanout_runs_all_three_and_merges():
    received = []
    runtime, calls = _fanout_runtime(received)

    state = _run(runtime)

    # All three collectors ran exactly once.
    assert calls == {"attractions": 1, "weather": 1, "hotels": 1}

    # build_query saw a merged snapshot containing every source's payload.
    snapshot = received[0]["tool_snapshot"]
    assert snapshot["classic_pois"] == [{"name": "故宫"}]
    assert snapshot["weather"] == [{"date": "2025-06-01"}]
    assert snapshot["hotel_pois"] == [{"name": "如家"}]
    assert snapshot["route_hints"] == []
    assert state["status"] == "llm_success"


def test_fanout_isolates_a_failing_source():
    received = []
    runtime, _calls = _fanout_runtime(received, fail="weather")

    state = _run(runtime)

    snapshot = received[0]["tool_snapshot"]
    # Surviving sources still merged.
    assert snapshot["classic_pois"] == [{"name": "故宫"}]
    assert snapshot["hotel_pois"] == [{"name": "如家"}]
    # Failed source recorded but did not abort the run.
    assert snapshot["tool_status"]["weather"]["ok"] is False
    assert state["status"] == "llm_success"


def test_runtime_without_subcollectors_uses_single_node():
    """Backward compat: a runtime lacking sub-collectors keeps the single node."""
    runtime = PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},
        build_query=lambda req, ctx: "QUERY",
        parse_plan=lambda resp, req, ctx: good_grounded_plan(req),
        primary_llm=_OkLLM(),
        fallback_llm=_OkLLM(),
    )
    assert runtime.supports_fanout() is False
    state = _run(runtime)
    assert state["status"] == "llm_success"
