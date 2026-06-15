"""稠密 + 稀疏向量化。

稠密：Qwen3-Embedding-8B，ModelScope OpenAI 兼容 /embeddings（httpx）。
稀疏：jieba 分词 → md5 哈希成 token-id → 词频稀疏向量；IDF 交给 Qdrant
      （collection 的 sparse 向量用 Modifier.IDF，服务端按文档频率加权）。
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Protocol

import httpx
import jieba

from .config import RAGConfig
from .models import SparseVec

_TOKEN_RE = re.compile(r"[一-鿿A-Za-z0-9]+")
_STOP = {"的", "了", "和", "是", "在", "我", "你", "也", "就", "都", "及", "与"}


def _token_id(tok: str) -> int:
    return int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16)


class SparseEncoder:
    """jieba 词频稀疏编码（确定性、跨进程一致；IDF 由 Qdrant 算）。"""

    def encode(self, text: str) -> SparseVec:
        freq: dict[int, float] = {}
        for raw in jieba.lcut(text or ""):
            tok = raw.strip().lower()
            if not tok or tok in _STOP or not _TOKEN_RE.match(tok):
                continue
            tid = _token_id(tok)
            freq[tid] = freq.get(tid, 0.0) + 1.0
        return SparseVec(indices=list(freq.keys()), values=list(freq.values()))


class DenseEmbedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ModelScopeDenseEmbedder:
    """Qwen3-Embedding-8B via ModelScope（OpenAI 兼容 embeddings）。"""

    def __init__(self, cfg: RAGConfig):
        if not cfg.modelscope_api_key:
            raise ValueError("缺少 MODELSCOPE_API_KEY，无法做稠密向量化")
        self._cfg = cfg

    def embed(self, texts: list[str]) -> list[list[float]]:
        url = f"{self._cfg.modelscope_base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self._cfg.modelscope_api_key}"}
        payload = {"model": self._cfg.dense_model, "input": texts}
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                r = httpx.post(url, json=payload, headers=headers, timeout=60)
                r.raise_for_status()
                data = r.json()["data"]
                return [item["embedding"] for item in data]
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"ModelScope 稠密向量化失败（已重试3次）：{last_err}")


class EmbeddingService:
    """组合稠密 + 稀疏。dense 可注入（测试用假实现）。"""

    def __init__(self, dense: DenseEmbedder, sparse: SparseEncoder | None = None):
        self._dense = dense
        self._sparse = sparse or SparseEncoder()

    def embed_dense(self, texts: list[str]) -> list[list[float]]:
        return self._dense.embed(texts)

    def embed_sparse(self, texts: list[str]) -> list[SparseVec]:
        return [self._sparse.encode(t) for t in texts]

    def embed_query(self, query: str) -> tuple[list[float], SparseVec]:
        return self._dense.embed([query])[0], self._sparse.encode(query)
