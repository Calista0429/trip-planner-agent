from qdrant_client import QdrantClient

from app.rag.config import RAGConfig
from app.rag.embeddings import EmbeddingService, SparseEncoder
from app.rag.importer import RAGImporter
from app.rag.service import RAGService
from app.rag.vector_store import QdrantVectorStore

CFG = RAGConfig(dense_dim=3, collection="svc_posts", credibility_threshold=0.0)

# 概念向量：维度 = [公园, 免费/不花钱, 美食]，让 dense 能把"不花钱"≈"免费"
_CONCEPTS = {"公园": 0, "免费": 1, "不花钱": 1, "美食": 2, "citywalk": 1}


class ConceptDense:
    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0, 0.0, 0.0]
            for word, dim in _CONCEPTS.items():
                if word in t:
                    v[dim] += 1.0
            out.append(v or [0.0, 0.0, 0.0])
        return out


def _service():
    store = QdrantVectorStore(CFG, client=QdrantClient(":memory:"))
    store.ensure_collection()
    svc = EmbeddingService(dense=ConceptDense(), sparse=SparseEncoder())
    posts = [
        {"id": "5", "title": "北京最牛的公园都是免费的", "desc": "公园 免费", "tags": ["公园"],
         "image_urls": [], "likes": 1, "collects": 1, "comments": 1, "city": "北京", "publish_time": None},
        {"id": "3", "title": "北京不花钱的快乐", "desc": "不花钱 快乐", "tags": [],
         "image_urls": [], "likes": 1, "collects": 1, "comments": 1, "city": "北京", "publish_time": None},
        {"id": "1", "title": "北京美食合集", "desc": "美食 合集", "tags": [],
         "image_urls": [], "likes": 1, "collects": 1, "comments": 1, "city": "北京", "publish_time": None},
    ]
    RAGImporter(CFG, svc, store).import_posts(posts)
    return RAGService(CFG, svc, store)


def test_hybrid_retrieves_synonym_and_exact():
    svc = _service()
    results = svc.search("北京免费逛的公园", top_k=3)
    ids = [r.post_id for r in results]
    assert ids[0] == "5"          # 公园+免费 两路都强 → 第一
    assert "3" in ids             # "不花钱" 仅靠 dense 语义也被召回
    assert "1" not in ids[:1]     # 美食不该排第一


def test_empty_query_returns_list():
    assert isinstance(_service().search(""), list)
