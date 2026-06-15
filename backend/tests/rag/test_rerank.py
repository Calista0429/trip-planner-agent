import time
from app.rag.config import RAGConfig
from app.rag.models import Hit
from app.rag.rerank import rerank

CFG = RAGConfig()


def _hit(pid, score, cred, pub):
    return Hit(point_id=pid, score=score,
               payload={"post_id": pid, "title": pid, "content": "", "tags": [],
                        "credibility": cred, "publish_time": pub, "image_urls": []})


def test_higher_credibility_wins_when_sim_close():
    now = time.time()
    hits = [_hit("low_cred", 0.030, 0.66, now), _hit("high_cred", 0.029, 0.95, now)]
    out = rerank(hits, CFG)
    assert out[0].post_id == "high_cred"


def test_returns_ragresult_with_url():
    out = rerank([_hit("p1", 0.03, 0.8, None)], CFG)
    assert out[0].url.endswith("p1")
    assert 0.0 <= out[0].score
