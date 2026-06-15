from qdrant_client import QdrantClient

from app.rag.config import RAGConfig
from app.rag.embeddings import EmbeddingService, SparseEncoder
from app.rag.importer import RAGImporter, load_posts
from app.rag.vector_store import QdrantVectorStore

CFG = RAGConfig(dense_dim=4, collection="imp_posts")


class FakeDense:
    def embed(self, texts):
        return [[float(len(t) % 7), 1.0, 0.0, 0.0] for t in texts]


def _svc():
    return EmbeddingService(dense=FakeDense(), sparse=SparseEncoder())


GOOD = {"id": "p_good", "title": "北京三天攻略", "desc": "地址：天安门 " + "好玩" * 200,
        "tags": ["北京", "攻略"], "image_urls": ["u"] * 9, "likes": 100, "collects": 60,
        "comments": 30, "followers": 100000, "is_verified": True,
        "useful_comments_ratio": 0.9, "publish_time": __import__("time").time(), "city": "北京"}
BAD = {"id": "p_bad", "title": "x", "desc": "好", "tags": [], "image_urls": [],
       "likes": 1, "collects": 0, "comments": 0, "followers": 3,
       "useful_comments_ratio": 0.0, "publish_time": None, "city": "北京"}


def test_imports_good_skips_low_credibility():
    store = QdrantVectorStore(CFG, client=QdrantClient(":memory:"))
    store.ensure_collection()
    imp = RAGImporter(CFG, _svc(), store)
    stats = imp.import_posts([GOOD, BAD])
    assert stats["indexed"] == 1
    assert stats["skipped"] == 1


def test_load_posts_from_dir_and_file(tmp_path):
    import json
    (tmp_path / "a.json").write_text(json.dumps([{"id": "1"}, {"id": "2"}]), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps([{"id": "3"}]), encoding="utf-8")
    assert {p["id"] for p in load_posts(str(tmp_path))} == {"1", "2", "3"}
    assert len(load_posts(str(tmp_path / "b.json"))) == 1
