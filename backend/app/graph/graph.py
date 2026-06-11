"""Planning graph assembly.

Control flow mirrors the old ``MultiAgentTripPlanner``:

    collect_context -> build_query -> generate
        generate --(enough candidates)--> rerank -> END
        generate --(attempts left)-----> generate
        generate --(exhausted, none, has fallback model)--> switch_fallback -> generate
        generate --(exhausted, none, no fallback)--------> fallback_plan -> END
        generate --(exhausted, some candidates)----------> rerank -> END

The retry counter, candidate collection and model fallback that used to live in
one long method are now plain nodes + conditional edges.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph

from ..agents.planner_feedback import build_failure_row
from ..agents.planner_query import planner_max_output_tokens
from ..agents.prompts import PLANNER_AGENT_PROMPT
from ..models.schemas import TripPlan, TripRequest
from ..planner.output import create_fallback_plan
from ..planner.rerank import rerank_trip_plan_candidates
from .runtime import PlannerRuntime, build_default_runtime
from .state import TripPlanState

PLANNER_MAX_ATTEMPTS = int(os.getenv("PLANNER_MAX_ATTEMPTS", "5"))
PLANNER_TEMPERATURE = float(os.getenv("PLANNER_TEMPERATURE", "0.2"))
PLANNER_REQUEST_TIMEOUT = int(os.getenv("PLANNER_REQUEST_TIMEOUT", "600"))
PLANNER_ENABLE_RERANK = os.getenv("PLANNER_ENABLE_RERANK", "1") == "1"
PLANNER_RERANK_CANDIDATE_COUNT = max(1, int(os.getenv("PLANNER_RERANK_CANDIDATE_COUNT", "3")))
PLANNER_RERANK_TEMPERATURE_STEP = float(os.getenv("PLANNER_RERANK_TEMPERATURE_STEP", "0.08"))


def build_planner_graph(
    runtime: PlannerRuntime,
    *,
    max_attempts: int = PLANNER_MAX_ATTEMPTS,
):
    """Compile the planning graph for a given runtime."""
    rerank_enabled = PLANNER_ENABLE_RERANK and PLANNER_RERANK_CANDIDATE_COUNT > 1
    target_candidates = (
        min(max_attempts, PLANNER_RERANK_CANDIDATE_COUNT) if rerank_enabled else 1
    )

    def collect_context(state: TripPlanState) -> dict[str, Any]:
        context = runtime.collect_context(state["request"])
        return {"planner_context": context, "status": "context_ready"}

    def build_query(state: TripPlanState) -> dict[str, Any]:
        query = runtime.build_query(state["request"], state["planner_context"])
        return {"planner_query": query, "status": "query_ready"}

    def generate(state: TripPlanState) -> dict[str, Any]:
        request: TripRequest = state["request"]
        context = state.get("planner_context") or {}
        attempt = state.get("attempt", 0) + 1
        use_fallback = state.get("use_fallback_llm", False)
        llm = runtime.fallback_llm if use_fallback else runtime.primary_llm
        label = runtime.fallback_label if use_fallback else runtime.primary_label

        temperature = PLANNER_TEMPERATURE
        if rerank_enabled:
            temperature = min(
                0.95, max(0.0, PLANNER_TEMPERATURE + (attempt - 1) * PLANNER_RERANK_TEMPERATURE_STEP)
            )

        messages = [
            {"role": "system", "content": PLANNER_AGENT_PROMPT},
            {"role": "user", "content": state["planner_query"]},
        ]

        # 1) LLM call failure: record and let the router decide retry/fallback.
        try:
            response = llm.invoke(
                messages,
                max_tokens=planner_max_output_tokens(request),
                temperature=temperature,
                timeout=PLANNER_REQUEST_TIMEOUT,
            )
        except Exception as error:  # noqa: BLE001 - mirror old broad handling
            return {
                "attempt": attempt,
                "failures": [
                    build_failure_row(
                        label=label,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        request=request,
                        planner_query=state["planner_query"],
                        response="",
                        error=error,
                        preference_reason="planner_llm_call_failed",
                    )
                ],
            }

        # 2) Parse/validate failure: keep retrying (a clean retry often fixes it).
        try:
            plan = runtime.parse_plan(response, request, context)
        except Exception as error:  # noqa: BLE001
            return {
                "attempt": attempt,
                "failures": [
                    build_failure_row(
                        label=label,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        request=request,
                        planner_query=state["planner_query"],
                        response=response,
                        error=error,
                    )
                ],
            }

        return {"attempt": attempt, "candidates": [{"attempt": attempt, "plan": plan}]}

    def switch_fallback(state: TripPlanState) -> dict[str, Any]:
        # Reset the attempt counter and retry the whole budget on the fallback model.
        return {"use_fallback_llm": True, "attempt": 0, "status": "fallback_llm"}

    def rerank_node(state: TripPlanState) -> dict[str, Any]:
        request = state["request"]
        context = state.get("planner_context") or {}
        pairs = [(c["attempt"], c["plan"]) for c in state.get("candidates", [])]
        ranked = rerank_trip_plan_candidates(pairs, request, context)
        return {"final_plan": ranked[0].trip_plan, "status": "llm_success"}

    def fallback_plan(state: TripPlanState) -> dict[str, Any]:
        return {
            "final_plan": create_fallback_plan(state["request"]),
            "status": "fallback_success",
        }

    def route_after_generate(state: TripPlanState) -> str:
        candidates = state.get("candidates", [])
        attempt = state.get("attempt", 0)

        if len(candidates) >= target_candidates:
            return "rerank"
        if attempt < max_attempts:
            return "generate"
        # Attempt budget exhausted for this model.
        if candidates:
            return "rerank"
        if not state.get("use_fallback_llm", False) and runtime.has_distinct_fallback:
            return "switch_fallback"
        return "fallback"

    graph = StateGraph(TripPlanState)
    graph.add_node("collect_context", collect_context)
    graph.add_node("build_query", build_query)
    graph.add_node("generate", generate)
    graph.add_node("switch_fallback", switch_fallback)
    graph.add_node("rerank", rerank_node)
    graph.add_node("fallback", fallback_plan)

    graph.add_edge(START, "collect_context")
    graph.add_edge("collect_context", "build_query")
    graph.add_edge("build_query", "generate")
    graph.add_conditional_edges(
        "generate",
        route_after_generate,
        {
            "generate": "generate",
            "switch_fallback": "switch_fallback",
            "rerank": "rerank",
            "fallback": "fallback",
        },
    )
    graph.add_edge("switch_fallback", "generate")
    graph.add_edge("rerank", END)
    graph.add_edge("fallback", END)

    return graph.compile()


# Two model tiers x max_attempts plus the fixed nodes stay well under the cap,
# but keep headroom so a future wider fan-out does not trip the limit.
GRAPH_RECURSION_LIMIT = 50


def initial_state(request: TripRequest) -> TripPlanState:
    """Build the initial state dict for a planning run."""
    return {
        "request": request,
        "candidates": [],
        "failures": [],
        "attempt": 0,
        "use_fallback_llm": False,
        "status": "start",
    }


def run_planner_graph(
    request: TripRequest,
    runtime: Optional[PlannerRuntime] = None,
) -> TripPlan:
    """Convenience entry point: build (or reuse) a runtime, run, return the plan."""
    runtime = runtime or build_default_runtime()
    compiled = build_planner_graph(runtime)
    final_state = compiled.invoke(
        initial_state(request), config={"recursion_limit": GRAPH_RECURSION_LIMIT}
    )
    return final_state["final_plan"]
