"""Route-level tests for /trip/plan backend selection.

The flag chooses between the legacy agent and the LangGraph pipeline. We stub the
two planner callables so the route is tested (flag branch, threading, response
shape) without any LLM or network call.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import trip as trip_route
from app.config import settings

from .builders import good_grounded_plan, make_request


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(trip_route.router)
    return TestClient(app)


@pytest.fixture
def request_body():
    return make_request(adults=2).model_dump()


@pytest.fixture(autouse=True)
def restore_flag():
    original = settings.use_langgraph_planner
    yield
    settings.use_langgraph_planner = original


def test_route_uses_graph_when_flag_on(client, request_body, monkeypatch):
    settings.use_langgraph_planner = True
    called = {"graph": 0, "legacy": 0}

    def fake_graph(request):
        called["graph"] += 1
        return good_grounded_plan(request), "llm_success", "ok-graph"

    def fake_legacy(request):
        called["legacy"] += 1
        raise AssertionError("legacy planner must not run when flag is on")

    monkeypatch.setattr(trip_route, "_plan_with_graph", fake_graph)
    monkeypatch.setattr(trip_route, "_plan_with_legacy_agent", fake_legacy)

    resp = client.post("/trip/plan", json=request_body)

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "ok-graph"
    assert body["data"]["city"] == request_body["city"]
    assert called == {"graph": 1, "legacy": 0}


def test_route_uses_legacy_when_flag_off(client, request_body, monkeypatch):
    settings.use_langgraph_planner = False
    called = {"graph": 0, "legacy": 0}

    def fake_graph(request):
        called["graph"] += 1
        raise AssertionError("graph planner must not run when flag is off")

    def fake_legacy(request):
        called["legacy"] += 1
        return good_grounded_plan(request), "llm_success", "ok-legacy"

    monkeypatch.setattr(trip_route, "_plan_with_graph", fake_graph)
    monkeypatch.setattr(trip_route, "_plan_with_legacy_agent", fake_legacy)

    resp = client.post("/trip/plan", json=request_body)

    assert resp.status_code == 200
    assert resp.json()["message"] == "ok-legacy"
    assert called == {"graph": 0, "legacy": 1}


def test_route_returns_500_on_planner_error(client, request_body, monkeypatch):
    settings.use_langgraph_planner = True

    def boom(request):
        raise RuntimeError("planner exploded")

    monkeypatch.setattr(trip_route, "_plan_with_graph", boom)

    resp = client.post("/trip/plan", json=request_body)

    assert resp.status_code == 500
