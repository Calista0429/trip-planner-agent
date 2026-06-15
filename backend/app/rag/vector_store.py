"""Qdrant 向量库：命名向量 dense + sparse(IDF)，Query API 做 RRF 融合 + 侧过滤。"""
from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from .config import RAGConfig
from .models import Hit, SparseVec

_NS = uuid.NAMESPACE_URL


def _point_id(post_id: str) -> str:
    return str(uuid.uuid5(_NS, post_id))


def _sv(v: SparseVec) -> qm.SparseVector:
    return qm.SparseVector(indices=v.indices, values=v.values)


class QdrantVectorStore:
    def __init__(self, cfg: RAGConfig, client: QdrantClient | None = None):
        self._cfg = cfg
        self._client = client or QdrantClient(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key)

    def ensure_collection(self) -> None:
        c = self._cfg
        if self._client.collection_exists(c.collection):
            return
        self._client.create_collection(
            collection_name=c.collection,
            vectors_config={"dense": qm.VectorParams(size=c.dense_dim, distance=qm.Distance.COSINE)},
            sparse_vectors_config={"sparse": qm.SparseVectorParams(modifier=qm.Modifier.IDF)},
        )
        self._client.create_payload_index(c.collection, "credibility", qm.PayloadSchemaType.FLOAT)
        self._client.create_payload_index(c.collection, "city", qm.PayloadSchemaType.KEYWORD)

    def upsert(self, points: list[dict[str, Any]]) -> int:
        structs = [
            qm.PointStruct(
                id=_point_id(p["post_id"]),
                vector={"dense": p["dense"], "sparse": _sv(p["sparse"])},
                payload=p["payload"],
            )
            for p in points
        ]
        self._client.upsert(self._cfg.collection, points=structs)
        return len(structs)

    def _filter(self, threshold: float, city: str | None) -> qm.Filter:
        must: list[qm.FieldCondition] = [
            qm.FieldCondition(key="credibility", range=qm.Range(gte=threshold))
        ]
        if city:
            must.append(qm.FieldCondition(key="city", match=qm.MatchValue(value=city)))
        return qm.Filter(must=must)

    def hybrid_search(self, dense: list[float], sparse: SparseVec, top_k: int,
                      credibility_threshold: float, city: str | None = None) -> list[Hit]:
        flt = self._filter(credibility_threshold, city)
        plimit = self._cfg.prefetch_limit
        res = self._client.query_points(
            self._cfg.collection,
            prefetch=[
                qm.Prefetch(query=dense, using="dense", limit=plimit, filter=flt),
                qm.Prefetch(query=_sv(sparse), using="sparse", limit=plimit, filter=flt),
            ],
            query=qm.FusionQuery(fusion=qm.Fusion.RRF),
            limit=top_k, with_payload=True,
        )
        return [Hit(point_id=str(p.payload.get("post_id", p.id)), score=p.score or 0.0,
                    payload=p.payload or {}) for p in res.points]
