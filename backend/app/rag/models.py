"""RAG 共享数据类。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SparseVec:
    """稀疏向量：token-id -> 词频。"""
    indices: list[int]
    values: list[float]


@dataclass
class Doc:
    """一条待入库文档（来自 xhs JSON，已算可信度）。"""
    post_id: str
    title: str
    content: str
    tags: list[str]
    credibility: float
    publish_time: int | None
    likes: int
    collects: int
    comments: int
    image_urls: list[str]
    city: str


@dataclass
class Hit:
    """向量检索的一条原始命中。"""
    point_id: str
    score: float           # 融合分（RRF）
    payload: dict[str, Any]


@dataclass
class RAGResult:
    """重排后返回给调用方的结果。"""
    post_id: str
    title: str
    content: str
    tags: list[str]
    score: float           # 重排后的最终分
    credibility: float
    publish_time: int | None
    image_urls: list[str]
    url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id, "title": self.title, "content": self.content,
            "tags": self.tags, "score": round(self.score, 4),
            "credibility": self.credibility, "publish_time": self.publish_time,
            "image_urls": self.image_urls, "url": self.url,
        }


@dataclass
class CredibilityScore:
    final: float
    creator: float
    content: float
    community: float
    freshness: float
    details: dict[str, Any] = field(default_factory=dict)
