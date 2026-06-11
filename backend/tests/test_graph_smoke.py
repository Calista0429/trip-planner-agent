"""Offline smoke tests for the LangGraph planning pipeline.

These run the compiled graph end-to-end with fake LLMs and an injected
parse_plan, so they exercise the real retry / model-fallback / rerank control
flow without any network or model dependency.
"""

from app.graph.graph import build_planner_graph
from app.graph.runtime import PlannerRuntime, default_parse_plan
from app.models.schemas import TripPlan

from .builders import good_grounded_plan, make_request

MAX_ATTEMPTS = 3


class _RaisingLLM:
    """An LLM stub that always fails the call."""

    def __init__(self):
        self.calls = 0

    def invoke(self, messages, **kwargs):
        self.calls += 1
        raise RuntimeError("llm unavailable")


class _OkLLM:
    """An LLM stub that always returns a (here irrelevant) payload."""

    def __init__(self, payload="{}"):
        self.payload = payload
        self.calls = 0

    def invoke(self, messages, **kwargs):
        self.calls += 1
        return self.payload


def _run(runtime):
    request = make_request(adults=2)
    graph = build_planner_graph(runtime, max_attempts=MAX_ATTEMPTS)
    initial = {
        "request": request,
        "candidates": [],
        "failures": [],
        "attempt": 0,
        "use_fallback_llm": False,
        "status": "start",
    }
    return request, graph.invoke(initial, config={"recursion_limit": 50})


def test_graph_falls_back_when_all_llm_calls_fail():
    """Both model tiers exhaust their attempts -> deterministic fallback plan."""
    primary, fallback = _RaisingLLM(), _RaisingLLM()
    runtime = PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},
        build_query=lambda req, ctx: "QUERY",
        parse_plan=default_parse_plan,  # never reached; the call fails first
        primary_llm=primary,
        fallback_llm=fallback,
        has_distinct_fallback=True,
    )

    request, state = _run(runtime)

    assert state["status"] == "fallback_success"
    assert isinstance(state["final_plan"], TripPlan)
    assert len(state["final_plan"].days) == request.travel_days
    # Primary exhausts MAX_ATTEMPTS, then we switch and the fallback does too.
    assert primary.calls == MAX_ATTEMPTS
    assert fallback.calls == MAX_ATTEMPTS
    assert len(state["failures"]) == 2 * MAX_ATTEMPTS


def test_graph_reaches_rerank_on_valid_output():
    """Valid parses accumulate candidates and the rerank node selects one."""
    llm = _OkLLM(payload='{"ok": true}')
    runtime = PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},
        build_query=lambda req, ctx: "QUERY",
        # Bypass the real validator; we only care about the graph wiring here.
        parse_plan=lambda resp, req, ctx: good_grounded_plan(req),
        primary_llm=llm,
        fallback_llm=llm,
        has_distinct_fallback=False,
    )

    request, state = _run(runtime)

    assert state["status"] == "llm_success"
    assert isinstance(state["final_plan"], TripPlan)
    assert state["final_plan"].city == request.city
    # rerank target is min(MAX_ATTEMPTS, candidate_count); at least one candidate.
    assert len(state["candidates"]) >= 1
    assert state["failures"] == []


def test_graph_single_tier_fallback_without_distinct_model():
    """With no distinct fallback model, exhaustion goes straight to fallback."""
    primary = _RaisingLLM()
    runtime = PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},
        build_query=lambda req, ctx: "QUERY",
        parse_plan=default_parse_plan,
        primary_llm=primary,
        fallback_llm=primary,
        has_distinct_fallback=False,
    )

    _request, state = _run(runtime)

    assert state["status"] == "fallback_success"
    assert primary.calls == MAX_ATTEMPTS  # no second tier
    assert len(state["failures"]) == MAX_ATTEMPTS
