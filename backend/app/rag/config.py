"""RAG 配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RAGConfig:
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    modelscope_api_key: str | None = None
    modelscope_base_url: str = "https://api-inference.modelscope.cn/v1"
    dense_model: str = "Qwen/Qwen3-Embedding-8B"
    dense_dim: int = 4096
    collection: str = "travel_documents"
    credibility_threshold: float = 0.65
    prefetch_limit: int = 20
    # 重排权重
    w_sim: float = 0.6
    w_cred: float = 0.25
    w_fresh: float = 0.15
    freshness_max_days: int = 730

    @classmethod
    def from_env(cls) -> "RAGConfig":
        """Reads only the operational env vars QDRANT_URL, QDRANT_API_KEY, MODELSCOPE_API_KEY, RAG_COLLECTION, RAG_CREDIBILITY_THRESHOLD; the remaining fields (model id, dims, rerank weights) are intentionally kept as code-level tuning defaults."""
        return cls(
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
            modelscope_api_key=os.getenv("MODELSCOPE_API_KEY") or None,
            collection=os.getenv("RAG_COLLECTION", "travel_documents"),
            credibility_threshold=float(os.getenv("RAG_CREDIBILITY_THRESHOLD", "0.65")),
        )
