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


def _rag_runtime(received_contexts, *, rag_collector):
    """Fan-out runtime with the three Amap sources plus an injected RAG source."""
    def collector(payload):
        def _call(request):
            return {"tool_snapshot": payload, "status": {"ok": True}}

        return _call

    def empty_context(request):
        return {"tool_snapshot": {"tool_status": {}}}

    def build_query(request, context):
        received_contexts.append(context)
        return "QUERY"

    llm = _OkLLM()
    return PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},
        build_query=build_query,
        parse_plan=lambda resp, req, ctx: good_grounded_plan(req),
        primary_llm=llm,
        fallback_llm=llm,
        has_distinct_fallback=False,
        collect_attractions=collector({"classic_pois": [{"name": "故宫"}]}),
        collect_weather=collector({"weather": [{"date": "2025-06-01"}]}),
        collect_hotels=collector({"hotel_pois": [{"name": "如家"}]}),
        empty_context=empty_context,
        collect_rag=rag_collector,
    )


def test_fanout_includes_rag_notes_when_collector_present():
    received = []
    calls = {"rag": 0}

    def rag_collector(request):
        calls["rag"] += 1
        return {
            "tool_snapshot": {"rag_notes": [{"title": "故宫攻略", "snippet": "早上人少"}]},
            "status": {"ok": True, "detail": "rag_notes=1"},
        }

    state = _run(_rag_runtime(received, rag_collector=rag_collector))

    assert calls["rag"] == 1
    snapshot = received[0]["tool_snapshot"]
    # RAG notes merged alongside the Amap sources.
    assert snapshot["rag_notes"] == [{"title": "故宫攻略", "snippet": "早上人少"}]
    assert snapshot["classic_pois"] == [{"name": "故宫"}]
    assert state["status"] == "llm_success"


def test_fanout_isolates_failing_rag_source():
    received = []

    def rag_collector(request):
        raise RuntimeError("qdrant down")

    state = _run(_rag_runtime(received, rag_collector=rag_collector))

    snapshot = received[0]["tool_snapshot"]
    # RAG failure is recorded but never aborts planning; Amap sources survive.
    assert snapshot["tool_status"]["rag"]["ok"] is False
    assert snapshot["classic_pois"] == [{"name": "故宫"}]
    assert "rag_notes" not in snapshot  # nothing merged from the failed source
    assert state["status"] == "llm_success"


def test_runtime_without_rag_collector_wires_no_rag_node():
    """No collect_rag -> graph keeps the original 3-way fan-out unchanged."""
    received = []
    state = _run(_rag_runtime(received, rag_collector=None))
    snapshot = received[0]["tool_snapshot"]
    assert "rag_notes" not in snapshot
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
