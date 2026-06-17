"""Reflection loop wiring tests (offline, fake critic + fake LLM).

Exercises generate -> rerank -> critic -> revise -> critic -> finalize without
any network. The critic is duck-typed (any object with .review(...)).
"""

from app.agents.critic import CritiqueReport, Violation
from app.graph.graph import build_planner_graph
from app.graph.runtime import PlannerRuntime
from app.models.schemas import TripPlan

from .builders import good_grounded_plan, make_request


class _OkLLM:
    def __init__(self, payload='{"ok": true}'):
        self.payload = payload
        self.calls = 0

    def invoke(self, messages, **kwargs):
        self.calls += 1
        return self.payload


def _runtime(critic, llm):
    return PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},
        build_query=lambda req, ctx: "QUERY",
        parse_plan=lambda resp, req, ctx: good_grounded_plan(req),
        primary_llm=llm,
        fallback_llm=llm,
        has_distinct_fallback=False,
        critic=critic,
    )


def _run(runtime):
    request = make_request(adults=2)
    graph = build_planner_graph(runtime, max_attempts=3)
    initial = {
        "request": request,
        "candidates": [],
        "failures": [],
        "attempt": 0,
        "use_fallback_llm": False,
        "status": "start",
    }
    return request, graph.invoke(initial, config={"recursion_limit": 50})


class _ReviseOnceCritic:
    """round 0 -> 一个 blocking；round>=1 -> pass。"""

    def __init__(self):
        self.calls = 0

    def review(self, plan, request, context, *, round=0):
        self.calls += 1
        if round == 0:
            return CritiqueReport(
                verdict="revise", score=10.0, round=round,
                violations=[Violation(code="persona_unfit", severity="blocking",
                                      detail="带娃不适配", fix_hint="换亲子点")],
            )
        return CritiqueReport(verdict="pass", score=50.0, round=round, violations=[])


class _AlwaysBadCritic:
    """每轮都 blocking，但换不同 code（避免提前防震荡），用于测 MAX_REVISE 止损。"""

    def __init__(self):
        self.calls = 0

    def review(self, plan, request, context, *, round=0):
        self.calls += 1
        code = "geo_detour" if round % 2 else "pacing_overload"
        return CritiqueReport(
            verdict="revise", score=0.0, round=round,
            violations=[Violation(code=code, severity="blocking", detail="x")],
        )


def test_reflection_loop_revises_then_finalizes():
    critic = _ReviseOnceCritic()
    llm = _OkLLM()
    _request, state = _run(_runtime(critic, llm))

    assert state["status"] == "critic_passed"
    assert state["revise_round"] == 1   # 修订了一次
    assert critic.calls == 2            # round0(blocking) + round1(pass)
    assert isinstance(state["final_plan"], TripPlan)


def test_reflection_loop_stops_at_max_revise():
    critic = _AlwaysBadCritic()
    llm = _OkLLM()
    _request, state = _run(_runtime(critic, llm))

    assert state["status"] == "critic_exhausted"
    assert state["revise_round"] == 2  # PLANNER_MAX_REVISE 默认 2


def test_critic_disabled_keeps_legacy_terminal():
    """无 critic（默认）→ 流程在 rerank 后结束，状态仍是 llm_success。"""
    llm = _OkLLM()
    runtime = _runtime(critic=None, llm=llm)
    _request, state = _run(runtime)

    assert state["status"] == "llm_success"
    assert "revise_round" not in state
