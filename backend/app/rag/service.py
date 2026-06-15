"""RAG 检索编排：embed → 混合检索 → 重排。"""
from __future__ import annotations

from .config import RAGConfig
from .embeddings import EmbeddingService, ModelScopeDenseEmbedder
from .models import RAGResult
from .rerank import rerank
from .vector_store import QdrantVectorStore


class RAGService:
    def __init__(self, cfg: RAGConfig, embeddings: EmbeddingService, store: QdrantVectorStore):
        self._cfg = cfg
        self._emb = embeddings
        self._store = store

    @classmethod
    def from_env(cls) -> "RAGService":
        cfg = RAGConfig.from_env()
        emb = EmbeddingService(dense=ModelScopeDenseEmbedder(cfg))
        store = QdrantVectorStore(cfg)
        store.ensure_collection()
        return cls(cfg, emb, store)

    def search(self, query: str, top_k: int = 5, credibility_threshold: float | None = None,
               city: str | None = None) -> list[RAGResult]:
        if not (query or "").strip():
            return []
        threshold = self._cfg.credibility_threshold if credibility_threshold is None else credibility_threshold
        dense, sparse = self._emb.embed_query(query)
        hits = self._store.hybrid_search(
            dense, sparse, top_k=max(top_k, self._cfg.prefetch_limit),
            credibility_threshold=threshold, city=city,
        )
        return rerank(hits, self._cfg)[:top_k]

    def search_by_city(self, query: str, city: str, top_k: int = 5) -> list[RAGResult]:
        return self.search(f"{city} {query}", top_k=top_k, city=city)
