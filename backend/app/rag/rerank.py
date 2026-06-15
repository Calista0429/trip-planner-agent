"""融合结果的轻量重排：sim(归一RRF) + credibility + freshness。确定性、无 LLM。"""
from __future__ import annotations

from datetime import datetime

from .config import RAGConfig
from .models import Hit, RAGResult


def _freshness(publish_time, max_days: int) -> float:
    if publish_time is None:
        return 0.5
    try:
        days = (datetime.now() - datetime.fromtimestamp(float(publish_time))).days
    except (TypeError, ValueError, OverflowError):
        return 0.5
    return max(0.0, 1.0 - days / max_days)


def rerank(hits: list[Hit], cfg: RAGConfig) -> list[RAGResult]:
    if not hits:
        return []
    max_score = max((h.score for h in hits), default=1.0) or 1.0
    results: list[RAGResult] = []
    for h in hits:
        sim = h.score / max_score
        cred = float(h.payload.get("credibility", 0.0) or 0.0)
        fresh = _freshness(h.payload.get("publish_time"), cfg.freshness_max_days)
        final = cfg.w_sim * sim + cfg.w_cred * cred + cfg.w_fresh * fresh
        pid = h.payload.get("post_id", h.point_id)
        results.append(RAGResult(
            post_id=pid, title=h.payload.get("title", ""), content=h.payload.get("content", ""),
            tags=h.payload.get("tags", []), score=final, credibility=cred,
            publish_time=h.payload.get("publish_time"), image_urls=h.payload.get("image_urls", []),
            url=f"https://www.xiaohongshu.com/explore/{pid}",
        ))
    results.sort(key=lambda r: r.score, reverse=True)
    return results
