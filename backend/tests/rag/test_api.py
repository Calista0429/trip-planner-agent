from fastapi.testclient import TestClient

import app.api.routes.rag as rag_route
from app.api.main import app
from app.rag.models import RAGResult


def test_search_endpoint(monkeypatch):
    def fake_get_service():
        class S:
            def search(self, query, top_k=5, city=None):
                return [RAGResult("p1", "标题", "正文", ["北京"], 0.9, 0.8, None, [], "u")]
        return S()
    monkeypatch.setattr(rag_route, "get_rag_service", fake_get_service)

    client = TestClient(app)
    r = client.post("/api/rag/search", json={"query": "北京公园", "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["post_id"] == "p1"


def test_search_empty_query_400(monkeypatch):
    monkeypatch.setattr(rag_route, "get_rag_service", lambda: None)
    client = TestClient(app)
    r = client.post("/api/rag/search", json={"query": "  "})
    assert r.status_code == 400
