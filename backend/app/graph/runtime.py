"""Runtime dependencies for the planning graph.

Everything the graph nodes need from the outside world is injected through a
``PlannerRuntime``. Production wires the real amap context builder, LLMs and
parse/validate pipeline; tests inject fakes so the whole graph runs offline and
deterministically.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

from ..agents.planner_query import build_planner_query
from ..models.schemas import TripPlan, TripRequest
from ..planner.output import (
    enrich_trip_plan_poi_details,
    extract_json_object,
    validate_trip_plan_shape,
)


class SupportsInvoke(Protocol):
    """Minimal LLM contract the generate node relies on."""

    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str: ...


@dataclass
class PlannerRuntime:
    """Injectable dependencies for the planning graph."""

    # Fetch the structured tool snapshot (amap POIs / weather / hotels).
    collect_context: Callable[[TripRequest], dict[str, Any]]
    # Turn request + context into the planner prompt input.
    build_query: Callable[[TripRequest, dict[str, Any]], str]
    # Parse + enrich + validate one raw LLM response into a TripPlan (raises on failure).
    parse_plan: Callable[[str, TripRequest, dict[str, Any]], TripPlan]
    # Primary (optionally personalized) planner LLM and the default fallback LLM.
    primary_llm: SupportsInvoke
    fallback_llm: SupportsInvoke
    primary_label: str = "primary planner"
    fallback_label: str = "default planner"
    # Whether the fallback LLM is actually a different model worth retrying with.
    has_distinct_fallback: bool = False

    # Optional per-subtask collectors enabling graph-native parallel fan-out.
    # Each returns a partial snapshot {"tool_snapshot": {...}, "status": {...}}.
    # When all of these (plus empty_context) are present the graph splits context
    # collection into three parallel nodes; otherwise it falls back to the single
    # collect_context node.
    collect_attractions: Optional[Callable[[TripRequest], dict[str, Any]]] = None
    collect_weather: Optional[Callable[[TripRequest], dict[str, Any]]] = None
    collect_hotels: Optional[Callable[[TripRequest], dict[str, Any]]] = None
    empty_context: Optional[Callable[[TripRequest], dict[str, Any]]] = None

    # Optional observability sinks. Persist one online-feedback failure row, and
    # log DPO preference candidates (rejected failures vs the chosen plan). Left
    # as None in tests so the graph stays side-effect free.
    record_failure: Optional[Callable[[dict[str, Any]], None]] = None
    record_preferences: Optional[
        Callable[[str, TripRequest, TripPlan, list[dict[str, Any]], str], None]
    ] = None

    def supports_fanout(self) -> bool:
        """True when the runtime can drive the parallel context fan-out."""
        return all(
            (
                self.collect_attractions,
                self.collect_weather,
                self.collect_hotels,
                self.empty_context,
            )
        )


def default_parse_plan(
    response: str, request: TripRequest, context: dict[str, Any]
) -> TripPlan:
    """Mirror of the old ``_parse_response(use_fallback=False)`` path."""
    data = extract_json_object(response)
    plan = TripPlan(**data)
    if context:
        enrich_trip_plan_poi_details(plan, context)
    validate_trip_plan_shape(plan, request, context)
    return plan


def build_default_runtime() -> PlannerRuntime:
    """Wire the real services. Imported lazily to keep the graph import light."""
    from ..agents.planner_feedback import (
        PLANNER_FAILURE_LOG,
        append_jsonl,
        log_preference_candidates,
    )
    from ..config import get_settings
    from ..planner.context import PlannerContextBuilder
    from ..services.llm_service import get_llm, get_planner_llm

    settings = get_settings()
    amap_key = (
        settings.amap_api_key
        or os.getenv("AMAP_MAPS_API_KEY")
        or os.getenv("AMAP_API_KEY")
    )
    builder = PlannerContextBuilder(amap_key)
    primary_llm = get_planner_llm()
    fallback_llm = get_llm()

    return PlannerRuntime(
        collect_context=builder.collect,
        build_query=lambda request, context: build_planner_query(
            builder, request, context
        ),
        parse_plan=default_parse_plan,
        primary_llm=primary_llm,
        fallback_llm=fallback_llm,
        primary_label=(
            "personalized planner" if primary_llm is not fallback_llm else "default planner"
        ),
        has_distinct_fallback=primary_llm is not fallback_llm,
        collect_attractions=builder._collect_attraction_snapshot,
        collect_weather=builder._collect_weather_snapshot,
        collect_hotels=builder._collect_hotel_snapshot,
        empty_context=builder.empty_context,
        record_failure=lambda row: append_jsonl(PLANNER_FAILURE_LOG, row),
        record_preferences=log_preference_candidates,
    )
