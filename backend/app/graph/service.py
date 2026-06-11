"""Application-facing entry point for the LangGraph planner.

Holds a lazily-built singleton (compiled graph + runtime) mirroring the
singleton style of ``get_trip_planner_agent`` and adapts the final graph state
into the (plan, status, message) shape the API route expects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from ..models.schemas import TripPlan, TripRequest
from .graph import GRAPH_RECURSION_LIMIT, build_planner_graph, initial_state
from .runtime import PlannerRuntime, build_default_runtime

_compiled_graph = None
_runtime: PlannerRuntime | None = None

_STATUS_MESSAGES = {
    "llm_success": "Trip plan generated successfully",
    "fallback_success": "Planner failed; returned a fallback plan",
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


# Stable phase keys (for the frontend) + display copy, per graph node.
_PROGRESS_BY_NODE = {
    "collect_context": ("collecting_context", "Gathering attractions, weather and hotels"),
    "collect_attractions": ("collecting_attractions", "Searching attractions, food and experiences"),
    "collect_weather": ("collecting_weather", "Fetching the weather forecast"),
    "collect_hotels": ("collecting_hotels", "Recommending hotels"),
    "merge_context": ("collecting_context", "Merging tool results"),
    "build_query": ("building_query", "Assembling the planner input"),
    "switch_fallback": ("switching_model", "Personalized model failed; switching to the default model"),
    "rerank": ("reranking", "Scoring and ranking candidate plans"),
    "fallback": ("fallback", "Generation failed; returning a fallback plan"),
}


def _progress_event(node: str, update: dict[str, Any]) -> dict[str, Any] | None:
    """Map one graph node update to a progress event (or None to skip)."""
    if node == "generate":
        attempt = update.get("attempt")
        if update.get("candidates"):
            message = f"Produced candidate plan #{attempt}"
        else:
            message = f"Attempt {attempt} did not pass; retrying"
        return {"type": "progress", "phase": "generating", "attempt": attempt, "message": message}

    mapped = _PROGRESS_BY_NODE.get(node)
    if mapped is None:
        return None
    phase, message = mapped
    return {"type": "progress", "phase": phase, "message": message}


def _stream_events(compiled, request: TripRequest) -> Iterator[dict[str, Any]]:
    """Run a compiled graph and yield progress events, ending with a result.

    Kept separate from the singleton so tests can drive it with a fake runtime.
    """
    final_plan: TripPlan | None = None
    status = "unknown"

    for chunk in compiled.stream(
        initial_state(request),
        stream_mode="updates",
        config={"recursion_limit": GRAPH_RECURSION_LIMIT},
    ):
        for node, update in chunk.items():
            event = _progress_event(node, update)
            if event is not None:
                yield event
            if update.get("final_plan") is not None:
                final_plan = update["final_plan"]
            if update.get("status"):
                status = update["status"]

    yield {
        "type": "result",
        "success": final_plan is not None,
        "status": status,
        "message": _STATUS_MESSAGES.get(status, "Trip plan generation finished"),
        "data": final_plan.model_dump() if final_plan is not None else None,
    }


def stream_trip_plan(request: TripRequest) -> Iterator[dict[str, Any]]:
    """Stream progress events for a planning run using the singleton graph."""
    yield from _stream_events(_get_compiled(), request)
