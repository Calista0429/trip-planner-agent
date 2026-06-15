import pytest
from qdrant_client import QdrantClient

from app.rag.config import RAGConfig
from app.rag.models import SparseVec
from app.rag.vector_store import QdrantVectorStore

CFG = RAGConfig(dense_dim=4, collection="t_posts")


def _store():
    return QdrantVectorStore(CFG, client=QdrantClient(":memory:"))


def _point(pid, dense, sparse_ids, cred, city="北京"):
    return {
        "post_id": pid, "dense": dense,
        "sparse": SparseVec(indices=sparse_ids, values=[1.0] * len(sparse_ids)),
        "payload": {"post_id": pid, "title": pid, "content": pid, "tags": [],
                    "credibility": cred, "publish_time": None, "image_urls": [], "city": city},
    }


def test_create_upsert_and_hybrid_search():
    st = _store()
    st.ensure_collection()
    st.upsert([
        _point("a", [1, 0, 0, 0], [10, 11], 0.9),
        _point("b", [0, 1, 0, 0], [11, 12], 0.8),
    ])
    hits = st.hybrid_search([1, 0, 0, 0], SparseVec([10], [1.0]), top_k=2, credibility_threshold=0.0)
    assert hits[0].point_id == "a"  # dense+sparse 都偏向 a


def test_credibility_side_filter_excludes_low():
    st = _store()
    st.ensure_collection()
    st.upsert([
        _point("hi", [1, 0, 0, 0], [10], 0.9),
        _point("lo", [1, 0, 0, 0], [10], 0.40),
    ])
    hits = st.hybrid_search([1, 0, 0, 0], SparseVec([10], [1.0]), top_k=5, credibility_threshold=0.65)
    ids = {h.payload["post_id"] for h in hits}
    assert "hi" in ids and "lo" not in ids
