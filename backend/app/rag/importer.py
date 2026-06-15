"""把 xhs_to_rag.py 产出的 JSON 帖子导入 Qdrant。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from .config import RAGConfig
from .credibility import CredibilityCalculator
from .embeddings import EmbeddingService
from .vector_store import QdrantVectorStore


def load_posts(path: str) -> list[dict[str, Any]]:
    """从 JSON 文件或目录（*.json）读取帖子列表。"""
    p = Path(path)
    files = sorted(p.glob("*.json")) if p.is_dir() else [p]
    posts: list[dict[str, Any]] = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        posts.extend(data if isinstance(data, list) else [data])
    return posts


class RAGImporter:
    def __init__(self, cfg: RAGConfig, embeddings: EmbeddingService, store: QdrantVectorStore,
                 calculator: CredibilityCalculator | None = None):
        self._cfg = cfg
        self._emb = embeddings
        self._store = store
        self._cred = calculator or CredibilityCalculator()

    @staticmethod
    def _enriched_text(post: dict[str, Any]) -> str:
        desc = post.get("desc") or post.get("content") or ""
        tags = " ".join(post.get("tags", []) or [])
        return f"{post.get('title', '')} {desc} {tags}".strip()

    def import_posts(self, posts: list[dict[str, Any]], batch_size: int = 20) -> dict[str, int]:
        stats = {"total": len(posts), "indexed": 0, "skipped": 0, "failed": 0}
        batch: list[dict[str, Any]] = []
        for post in posts:
            try:
                cred = self._cred.calculate(post)
                if cred.final < self._cfg.credibility_threshold:
                    stats["skipped"] += 1
                    continue
                text = self._enriched_text(post)
                dense = self._emb.embed_dense([text])[0]
                sparse = self._emb.embed_sparse([text])[0]
                batch.append({
                    "post_id": post.get("id", ""),
                    "dense": dense, "sparse": sparse,
                    "payload": {
                        "post_id": post.get("id", ""), "title": post.get("title", ""),
                        "content": post.get("content") or post.get("desc", ""),
                        "tags": post.get("tags", []), "credibility": cred.final,
                        "publish_time": post.get("publish_time"),
                        "likes": post.get("likes", 0), "collects": post.get("collects", 0),
                        "comments": post.get("comments", 0),
                        "image_urls": post.get("image_urls", []),
                        "city": post.get("city", ""),
                    },
                })
            except Exception as e:  # noqa: BLE001
                logger.warning(f"导入失败 {post.get('id')}: {e}")
                stats["failed"] += 1
            if len(batch) >= batch_size:
                stats["indexed"] += self._store.upsert(batch)
                batch = []
        if batch:
            stats["indexed"] += self._store.upsert(batch)
        return stats
