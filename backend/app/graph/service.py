"""Application-facing entry point for the LangGraph planner.

Holds a lazily-built singleton (compiled graph + runtime) mirroring the
singleton style of ``get_trip_planner_agent`` and adapts the final graph state
into the (plan, status, message) shape the API route expects.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models.schemas import TripPlan, TripRequest
from .graph import GRAPH_RECURSION_LIMIT, build_planner_graph, initial_state
from .runtime import PlannerRuntime, build_default_runtime

_compiled_graph = None
_runtime: PlannerRuntime | None = None

# User-facing messages kept in Chinese to match the rest of the product copy.
_STATUS_MESSAGES = {
    "llm_success": "旅行计划生成成功",
    "fallback_success": "Planner失败，已返回fallback计划",
}


@dataclass
class PlanResult:
    """Adapter result for the API layer."""

    plan: TripPlan
    status: str
    message: str


def _get_compiled():
    global _compiled_graph, _runtime
    if _compiled_graph is None:
        _runtime = build_default_runtime()
        _compiled_graph = build_planner_graph(_runtime)
    return _compiled_graph


def generate_trip_plan(request: TripRequest) -> PlanResult:
    """Run the planning graph and adapt its final state for the API."""
    compiled = _get_compiled()
    final_state = compiled.invoke(
        initial_state(request), config={"recursion_limit": GRAPH_RECURSION_LIMIT}
    )
    status = final_state.get("status", "unknown")
    message = _STATUS_MESSAGES.get(status, "旅行计划生成完成")
    return PlanResult(plan=final_state["final_plan"], status=status, message=message)


def reset_planner_graph() -> None:
    """Drop the cached graph/runtime (used by tests or after reconfiguration)."""
    global _compiled_graph, _runtime
    _compiled_graph = None
    _runtime = None
