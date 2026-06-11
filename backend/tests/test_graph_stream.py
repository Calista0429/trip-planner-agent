"""Tests for streaming progress from the planning graph.

Service-level tests drive ``_stream_events`` with fake runtimes (offline); the
route test exercises the SSE framing with the service stubbed.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import trip as trip_route
from app.graph import service as graph_service
from app.graph.graph import build_planner_graph
from app.graph.runtime import PlannerRuntime, default_parse_plan
from app.graph.service import _stream_events

from .builders import good_grounded_plan, make_request

MAX_ATTEMPTS = 3


class _RaisingLLM:
    def invoke(self, messages, **kwargs):
        raise RuntimeError("llm unavailable")


class _OkLLM:
    def invoke(self, messages, **kwargs):
        return "{}"


def _happy_runtime():
    llm = _OkLLM()
    return PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},
        build_query=lambda req, ctx: "QUERY",
        parse_plan=lambda resp, req, ctx: good_grounded_plan(req),
        primary_llm=llm,
        fallback_llm=llm,
        has_distinct_fallback=False,
    )


def _fallback_runtime():
    return PlannerRuntime(
        collect_context=lambda req: {"tool_snapshot": {}},
        build_query=lambda req, ctx: "QUERY",
        parse_plan=default_parse_plan,
        primary_llm=_RaisingLLM(),
        fallback_llm=_RaisingLLM(),
        has_distinct_fallback=True,
    )


def _collect(runtime):
    request = make_request(adults=2)
    compiled = build_planner_graph(runtime, max_attempts=MAX_ATTEMPTS)
    return list(_stream_events(compiled, request))


def test_stream_happy_path_phases_and_result():
    events = _collect(_happy_runtime())
    phases = [e["phase"] for e in events if e["type"] == "progress"]

    assert phases[0] == "collecting_context"
    assert "building_query" in phases
    assert "generating" in phases
    assert "reranking" in phases

    result = events[-1]
    assert result["type"] == "result"
    assert result["success"] is True
    assert result["status"] == "llm_success"
    assert result["data"]["city"] == "北京"


def test_stream_fallback_path():
    events = _collect(_fallback_runtime())
    phases = [e["phase"] for e in events if e["type"] == "progress"]

    assert "switching_model" in phases  # primary exhausted -> switch model
    assert "fallback" in phases

    result = events[-1]
    assert result["type"] == "result"
    assert result["status"] == "fallback_success"
    assert result["data"] is not None  # fallback plan is still returned


def test_stream_generating_events_carry_attempt():
    events = _collect(_happy_runtime())
    generating = [e for e in events if e.get("phase") == "generating"]
    assert generating
    assert all(isinstance(e["attempt"], int) and e["attempt"] >= 1 for e in generating)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(trip_route.router)
    return TestClient(app)


def test_stream_route_emits_sse_frames(client, monkeypatch):
    def fake_stream(request):
        yield {"type": "progress", "phase": "collecting_context", "message": "..."}
        yield {"type": "result", "success": True, "status": "llm_success",
               "message": "ok", "data": {"city": request.city}}

    # The route imports stream_trip_plan from the service module at call time.
    monkeypatch.setattr(graph_service, "stream_trip_plan", fake_stream)

    body = make_request(adults=2).model_dump()
    resp = client.post("/trip/plan/stream", json=body)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    text = resp.text
    assert "event: progress" in text
    assert "event: result" in text
    assert "collecting_context" in text
