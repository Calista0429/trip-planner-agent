"""Expose RAG retrieval as a planner fan-out collector.

Option A (soft inspiration only): retrieved posts are surfaced to the Planner as
reference notes for prioritization, pacing, seasonal/queue tips and narration —
they never become a source of attractions/hotels/meals. Those stay grounded in
the Amap candidate buckets, so the existing grounding check, the Critic's
hallucinated-POI rule and the map all keep working unchanged.

The collector follows the same partial-snapshot contract as the Amap
sub-collectors: it returns ``{"tool_snapshot": {...}, "status": {...}}`` and is
wrapped by the graph so a failure never aborts a planning run.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from ..models.schemas import TripRequest

PLANNER_RAG_TOP_K = int(os.getenv("PLANNER_RAG_TOP_K", "5"))
PLANNER_RAG_SNIPPET_CHARS = int(os.getenv("PLANNER_RAG_SNIPPET_CHARS", "140"))


def _build_query(request: TripRequest) -> str:
    """City + preferences + free text → one retrieval query."""
    parts: list[str] = [request.city or ""]
    parts.extend(request.preferences or [])
    if request.free_text_input:
        parts.append(request.free_text_input)
    return " ".join(part for part in parts if part).strip()


def _note_from_result(result: Any) -> dict[str, Any]:
    """Trim one RAGResult into a compact, token-bounded reference note."""
    content = (result.content or "").strip().replace("\n", " ")
    if len(content) > PLANNER_RAG_SNIPPET_CHARS:
        content = content[:PLANNER_RAG_SNIPPET_CHARS] + "…"
    return {
        "title": result.title,
        "tags": (result.tags or [])[:6],
        "snippet": content,
        "credibility": round(result.credibility, 3),
    }


def build_rag_collector() -> Optional[Callable[[TripRequest], dict[str, Any]]]:
    """Build a fan-out collector backed by RAGService, or None if it can't init.

    Returning None means the planner graph simply won't wire a RAG node, so
    planning is unaffected when Qdrant/ModelScope/credentials are missing. Init
    happens once (the runtime is built once) so we don't reconnect per request.
    """
    try:
        from .service import RAGService

        service = RAGService.from_env()
    except Exception as exc:  # noqa: BLE001 - RAG is optional; degrade silently
        print(f"⚠️  RAG 接入未启用(初始化失败): {exc}", flush=True)
        return None

    def collect_rag(request: TripRequest) -> dict[str, Any]:
        query = _build_query(request)
        results = service.search(query, top_k=PLANNER_RAG_TOP_K, city=request.city)
        notes = [_note_from_result(result) for result in results]
        return {
            "tool_snapshot": {"rag_notes": notes},
            "status": {"ok": True, "detail": f"rag_notes={len(notes)}"},
        }

    return collect_rag
