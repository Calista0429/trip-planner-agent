"""RAG 检索 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...rag.service import RAGService

router = APIRouter(prefix="/rag", tags=["rag"])

_service: RAGService | None = None


def get_rag_service() -> RAGService:
    global _service
    if _service is None:
        _service = RAGService.from_env()
    return _service


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    city: str | None = None


@router.post("/search")
def search(req: SearchRequest) -> dict:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    results = get_rag_service().search(req.query, top_k=req.top_k, city=req.city)
    return {"results": [r.to_dict() for r in results], "count": len(results)}
