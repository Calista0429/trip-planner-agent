import os
from app.rag.config import RAGConfig


def test_defaults():
    c = RAGConfig()
    assert c.dense_dim == 4096
    assert c.credibility_threshold == 0.65
    assert c.collection == "travel_documents"


def test_from_env(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "https://cloud:6333")
    monkeypatch.setenv("RAG_CREDIBILITY_THRESHOLD", "0.7")
    c = RAGConfig.from_env()
    assert c.qdrant_url == "https://cloud:6333"
    assert c.credibility_threshold == 0.7
