"""Graph state schema.

The state is the backbone of the whole pipeline: every node communicates only
through it. Fields that several iterations append to (candidates, failures) use
``operator.add`` reducers so the framework accumulates them instead of us
hand-maintaining counters the way the old retry loop did.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Optional, TypedDict

from ..models.schemas import TripPlan, TripRequest


class Candidate(TypedDict):
    """One successfully parsed+validated plan produced by a generate attempt."""

    attempt: int
    plan: TripPlan


class TripPlanState(TypedDict, total=False):
    """Shared state for the trip planning graph.

    Only ``request`` is required as input; the rest are populated by nodes.
    """

    # --- input ---
    request: TripRequest

    # --- produced by the parallel collect fan-out (each node appends one part) ---
    snapshot_parts: Annotated[list[dict[str, Any]], operator.add]

    # --- produced by collect_context / merge_context / build_query ---
    planner_context: dict[str, Any]
    planner_query: str

    # --- accumulated across generate attempts (reducers append) ---
    candidates: Annotated[list[Candidate], operator.add]
    failures: Annotated[list[dict[str, Any]], operator.add]

    # --- retry / fallback control (last-write-wins) ---
    attempt: int
    use_fallback_llm: bool

    # --- terminal output ---
    final_plan: Optional[TripPlan]
    status: str
