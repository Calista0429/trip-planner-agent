# RAG 移植 + 改进 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Trip-planner-agent 重建 travel_agent 的文本 RAG（Qdrant + 远程 Qwen3 稠密 embedding），并修复四处缺陷：可信度归一化、真混合 dense+sparse、Qdrant 侧过滤、轻量重排。

**Architecture:** 新建 `backend/app/rag/` 包，组件单一职责：`config`(配置) / `credibility`(评分卡，归一化修复) / `embeddings`(稠密远程 + 稀疏 jieba+IDF) / `vector_store`(Qdrant 命名向量 + RRF 融合 + 侧过滤) / `rerank`(可信度+时效重排) / `importer`(导入) / `service`(检索编排)。CLI 与 `/rag/search` API 在外层。

**Tech Stack:** Python 3.13, Qdrant (`qdrant-client`, 命名向量 dense + sparse w/ `Modifier.IDF`), jieba(中文分词), httpx(ModelScope `/v1/embeddings`), pytest。稠密向量 4096 维 Qwen3-Embedding-8B；稀疏向量为 jieba 词频 + Qdrant 服务端 IDF。

**关键约定：**
- Qdrant 点 id 必须是 int/UUID，post_id 是 hex 字符串 → 点 id 用 `uuid.uuid5(NAMESPACE_URL, post_id)`，原 post_id 存 payload。
- 稀疏 token id：`int(hashlib.md5(tok.encode()).hexdigest()[:8], 16)`（32-bit，确定性、跨进程一致）。
- 稠密 embedder 抽象成协议，便于测试注入 `FakeDenseEmbedder`；真实 ModelScope 调用仅集成测试。
- 单测用 `QdrantClient(":memory:")`，离线可跑。

---

## File Structure

```
backend/app/rag/
  __init__.py          # 导出 RAGService, RAGConfig
  config.py            # RAGConfig（from_env）
  models.py            # 数据类：SparseVec, Doc, Hit, RAGResult, CredibilityScore
  credibility.py       # CredibilityCalculator（★归一化）
  embeddings.py        # DenseEmbedder 协议 / ModelScopeDenseEmbedder / SparseEncoder / EmbeddingService
  vector_store.py      # QdrantVectorStore（★命名向量+RRF+侧过滤）
  rerank.py            # rerank()（★可信度+时效）
  importer.py          # RAGImporter
  service.py           # RAGService（单例编排）
backend/scripts/rag_import.py   # 导入 CLI
backend/scripts/rag_search.py   # 检索 CLI
backend/app/api/routes/rag.py   # POST /rag/search
backend/tests/rag/              # 单测
backend/requirements.txt        # +qdrant-client +jieba
backend/.env.example            # 文档化新增变量
```

---

### Task 1: 依赖、包骨架、配置与数据类

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/rag/__init__.py`
- Create: `backend/app/rag/models.py`
- Create: `backend/app/rag/config.py`
- Create: `backend/tests/rag/__init__.py`
- Test: `backend/tests/rag/test_config.py`

- [ ] **Step 1: 加依赖**

在 `backend/requirements.txt` 末尾追加：
```
# RAG 向量检索
qdrant-client>=1.12
jieba>=0.42.1
```
安装：`pip install "qdrant-client>=1.12" "jieba>=0.42.1"`

- [ ] **Step 2: 写数据类**

Create `backend/app/rag/models.py`:
```python
"""RAG 共享数据类。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
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
```

- [ ] **Step 3: 写配置**

Create `backend/app/rag/config.py`:
```python
"""RAG 配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RAGConfig:
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    modelscope_api_key: str | None = None
    modelscope_base_url: str = "https://api-inference.modelscope.cn/v1"
    dense_model: str = "Qwen/Qwen3-Embedding-8B"
    dense_dim: int = 4096
    collection: str = "travel_documents"
    credibility_threshold: float = 0.65
    prefetch_limit: int = 20
    # 重排权重
    w_sim: float = 0.6
    w_cred: float = 0.25
    w_fresh: float = 0.15
    freshness_max_days: int = 730

    @classmethod
    def from_env(cls) -> "RAGConfig":
        return cls(
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
            modelscope_api_key=os.getenv("MODELSCOPE_API_KEY") or None,
            collection=os.getenv("RAG_COLLECTION", "travel_documents"),
            credibility_threshold=float(os.getenv("RAG_CREDIBILITY_THRESHOLD", "0.65")),
        )
```

Create `backend/app/rag/__init__.py`:
```python
from .config import RAGConfig

__all__ = ["RAGConfig"]
```
Create empty `backend/tests/rag/__init__.py`.

- [ ] **Step 4: 写失败测试**

Create `backend/tests/rag/test_config.py`:
```python
import os
from app.rag.config import RAGConfig


def test_defaults():
    c = RAGConfig()
    assert c.dense_dim == 4096
    assert c.credibility_threshold == 0.65
    assert c.collection == "travel_documents"


def test_from_env(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "https://cloud:6333")
    monkeypatch.setenv("RAG_CREDIBILITY_THRESHOLD", "0.7")
    c = RAGConfig.from_env()
    assert c.qdrant_url == "https://cloud:6333"
    assert c.credibility_threshold == 0.7
```

- [ ] **Step 5: 跑测试**

Run: `cd backend && python -m pytest tests/rag/test_config.py -v`
Expected: PASS（2 passed）

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/rag/__init__.py backend/app/rag/models.py backend/app/rag/config.py backend/tests/rag/__init__.py backend/tests/rag/test_config.py
git commit -m "feat(rag): scaffold rag package, config and data models"
```

---

### Task 2: 可信度评分卡（★归一化修复）

**Files:**
- Create: `backend/app/rag/credibility.py`
- Test: `backend/tests/rag/test_credibility.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/rag/test_credibility.py`:
```python
from app.rag.credibility import CredibilityCalculator

C = CredibilityCalculator()

PERFECT = {
    "is_verified": True, "followers": 100000, "report_rate": 0.0,
    "image_count": 9, "desc": "地址：北京 营业时间：9-17 " + "好玩" * 200,
    "likes": 100, "collects": 60, "comments": 30,
    "useful_comments_ratio": 0.9,
    "publish_time": __import__("time").time(),  # 当下
}


def test_perfect_post_can_pass_065_threshold():
    """★核心：修复后满分可达 1.0，0.65 阈值才有意义（原版最高≈0.64）。"""
    s = C.calculate(PERFECT)
    assert s.final > 0.65
    assert 0.0 <= s.final <= 1.0


def test_each_dimension_normalized_0_1():
    s = C.calculate(PERFECT)
    for v in (s.creator, s.content, s.community, s.freshness):
        assert 0.0 <= v <= 1.0


def test_useful_comments_ratio_default_no_longer_breaks():
    """★修复：默认 0.5 用 >=0.5 判定应得分（原版 >0.5 永远拿不到）。"""
    post = dict(PERFECT)
    post.pop("useful_comments_ratio")  # 走默认 0.5
    s = C.calculate(post)
    assert s.details["community"]["useful_ok"] is True


def test_low_quality_post_below_threshold():
    poor = {"is_verified": False, "followers": 5, "report_rate": 0.2,
            "image_count": 0, "desc": "好", "likes": 1, "collects": 0,
            "comments": 0, "useful_comments_ratio": 0.0, "publish_time": None}
    assert C.calculate(poor).final < 0.65
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/rag/test_credibility.py -v`
Expected: FAIL（`ModuleNotFoundError: app.rag.credibility`）

- [ ] **Step 3: 实现可信度**

Create `backend/app/rag/credibility.py`:
```python
"""帖子可信度四维评分卡（★每维归一到 [0,1] 再加权，修复原版满分撞不过阈值的 bug）。

原版各维原始满分：creator 0.6 / content 0.75 / community 0.3 / freshness 1.0，
加权后最高仅 ≈0.64，撞不过 0.65 阈值。这里每维除以各自满分归一到 [0,1]，
final = 0.3*creator + 0.4*content + 0.2*community + 0.1*freshness ∈ [0,1]。
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from .models import CredibilityScore

AD_KEYWORDS = ["合作", "赞助", "广告", "推广", "福利", "抽奖", "品牌方", "商单", "恰饭", "植入", "代言"]
STRUCTURED_PATTERNS = [
    r"地址[：:]", r"营业时间[：:]", r"票价[：:]", r"门票[：:]", r"价格[：:]",
    r"人均[：:]", r"交通[：:]", r"路线[：:]", r"\d+路[公交地]车", r"地铁\d+号线",
]

# 各维子分满分（用于归一化）
_CREATOR_MAX = 0.6
_CONTENT_MAX = 0.75
_COMMUNITY_MAX = 0.3


class CredibilityCalculator:
    def __init__(self, creator_w=0.3, content_w=0.4, community_w=0.2, freshness_w=0.1,
                 max_age_days=730, min_images=3, min_desc_len=200):
        self.creator_w, self.content_w = creator_w, content_w
        self.community_w, self.freshness_w = community_w, freshness_w
        self.max_age_days, self.min_images, self.min_desc_len = max_age_days, min_images, min_desc_len

    def calculate(self, post: dict[str, Any]) -> CredibilityScore:
        creator, cd = self._creator(post)
        content, cnd = self._content(post)
        community, cmd = self._community(post)
        freshness, fd = self._freshness(post)
        # ★归一化：每维 /各自满分
        creator_n = creator / _CREATOR_MAX
        content_n = content / _CONTENT_MAX
        community_n = community / _COMMUNITY_MAX
        final = (creator_n * self.creator_w + content_n * self.content_w
                 + community_n * self.community_w + freshness * self.freshness_w)
        return CredibilityScore(
            final=round(final, 3), creator=round(creator_n, 3), content=round(content_n, 3),
            community=round(community_n, 3), freshness=round(freshness, 3),
            details={"creator": cd, "content": cnd, "community": cmd, "freshness": fd},
        )

    def _creator(self, p):
        s, d = 0.0, {}
        if p.get("is_verified", False):
            s += 0.3
        f = p.get("followers", 0) or 0
        fs = min(0.2, 0.2 * math.log10(f + 1) / math.log10(50001))
        s += fs
        if (p.get("report_rate", 0) or 0) < 0.05:
            s += 0.1
        d["follower_score"] = round(fs, 3)
        return s, d

    def _content(self, p):
        s, d = 0.0, {}
        ic = p.get("image_count", len(p.get("image_urls", []) or []))
        if ic >= self.min_images and p.get("has_real_photos", True):
            s += 0.25
        desc = p.get("desc", "") or p.get("content", "") or ""
        if len(desc) > self.min_desc_len:
            s += 0.15
        if any(re.search(pat, desc) for pat in STRUCTURED_PATTERNS):
            s += 0.2
        if not any(k in desc.lower() for k in AD_KEYWORDS):
            s += 0.15
        d["image_count"], d["desc_len"] = ic, len(desc)
        return s, d

    def _community(self, p):
        s, d = 0.0, {}
        likes = p.get("likes", 0) or 0
        collects = p.get("collects", 0) or 0
        ratio = collects / max(likes, 1)
        if ratio > 0.3:
            s += 0.2
        useful = p.get("useful_comments_ratio", 0.5)
        useful_ok = useful >= 0.5  # ★修复：原版 >0.5 + 默认 0.5 → 永不得分
        if useful_ok:
            s += 0.1
        d["engagement_ratio"] = round(ratio, 3)
        d["useful_ok"] = useful_ok
        return s, d

    def _freshness(self, p):
        d = {}
        pt = p.get("publish_time")
        if pt is None:
            days = 365
        elif isinstance(pt, (int, float)):
            days = (datetime.now() - datetime.fromtimestamp(pt)).days
        elif isinstance(pt, datetime):
            days = (datetime.now() - pt).days
        else:
            days = 365
        score = max(0.0, 1.0 - days / self.max_age_days)
        d["days_old"] = days
        return score, d
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && python -m pytest tests/rag/test_credibility.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/credibility.py backend/tests/rag/test_credibility.py
git commit -m "feat(rag): credibility scorecard with per-dimension normalization fix"
```

---

### Task 3: Embeddings（稀疏 jieba+hash / 稠密 ModelScope 协议）

**Files:**
- Create: `backend/app/rag/embeddings.py`
- Test: `backend/tests/rag/test_embeddings.py`

- [ ] **Step 1: 写失败测试（稀疏编码可离线测）**

Create `backend/tests/rag/test_embeddings.py`:
```python
from app.rag.embeddings import SparseEncoder


def test_sparse_encoder_tokenizes_chinese():
    enc = SparseEncoder()
    v = enc.encode("北京免费的公园")
    # 至少切出 公园/免费/北京 这类词，indices 与 values 等长
    assert len(v.indices) == len(v.values)
    assert len(v.indices) >= 2


def test_sparse_same_token_same_id_cross_call():
    enc = SparseEncoder()
    a = enc.encode("公园")
    b = enc.encode("公园 公园")
    assert a.indices[0] == b.indices[0]          # 确定性 id
    assert b.values[0] == 2.0                      # 词频累加


def test_sparse_empty_text():
    assert SparseEncoder().encode("").indices == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/rag/test_embeddings.py -v`
Expected: FAIL（`ImportError: SparseEncoder`）

- [ ] **Step 3: 实现 embeddings**

Create `backend/app/rag/embeddings.py`:
```python
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
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && python -m pytest tests/rag/test_embeddings.py -v`
Expected: PASS（3 passed；首次会触发 jieba 词典加载）

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/embeddings.py backend/tests/rag/test_embeddings.py
git commit -m "feat(rag): jieba sparse encoder + ModelScope dense embedder"
```

---

### Task 4: Qdrant 向量库（★命名向量 + RRF + 侧过滤）

**Files:**
- Create: `backend/app/rag/vector_store.py`
- Test: `backend/tests/rag/test_vector_store.py`

- [ ] **Step 1: 写失败测试（用 :memory: + 假稠密）**

Create `backend/tests/rag/test_vector_store.py`:
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/rag/test_vector_store.py -v`
Expected: FAIL（`ImportError: QdrantVectorStore`）

- [ ] **Step 3: 实现 vector_store**

Create `backend/app/rag/vector_store.py`:
```python
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
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && python -m pytest tests/rag/test_vector_store.py -v`
Expected: PASS（2 passed）

> 若 `:memory:` 报不支持 `Modifier.IDF`/Fusion，升级 `qdrant-client`；仍不行则在测试里改用 `QDRANT_URL` 指向云实例（注释说明）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/vector_store.py backend/tests/rag/test_vector_store.py
git commit -m "feat(rag): qdrant store with named vectors, RRF fusion, server-side credibility filter"
```

---

### Task 5: 轻量重排（★可信度 + 时效）

**Files:**
- Create: `backend/app/rag/rerank.py`
- Test: `backend/tests/rag/test_rerank.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/rag/test_rerank.py`:
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/rag/test_rerank.py -v`
Expected: FAIL（`ImportError: rerank`）

- [ ] **Step 3: 实现 rerank**

Create `backend/app/rag/rerank.py`:
```python
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
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && python -m pytest tests/rag/test_rerank.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/rerank.py backend/tests/rag/test_rerank.py
git commit -m "feat(rag): lightweight rerank by similarity + credibility + freshness"
```

---

### Task 6: 导入器

**Files:**
- Create: `backend/app/rag/importer.py`
- Test: `backend/tests/rag/test_importer.py`

- [ ] **Step 1: 写失败测试（fake dense + :memory:）**

Create `backend/tests/rag/test_importer.py`:
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/rag/test_importer.py -v`
Expected: FAIL（`ImportError: RAGImporter`）

- [ ] **Step 3: 实现 importer**

Create `backend/app/rag/importer.py`:
```python
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
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && python -m pytest tests/rag/test_importer.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/importer.py backend/tests/rag/test_importer.py
git commit -m "feat(rag): importer with credibility gating and batched upsert"
```

---

### Task 7: 检索服务（端到端编排 + §4 例子）

**Files:**
- Create: `backend/app/rag/service.py`
- Modify: `backend/app/rag/__init__.py`
- Test: `backend/tests/rag/test_service.py`

- [ ] **Step 1: 写失败测试（复现 §4 "北京免费逛的公园" 例子）**

Create `backend/tests/rag/test_service.py`:
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/rag/test_service.py -v`
Expected: FAIL（`ImportError: RAGService`）

- [ ] **Step 3: 实现 service**

Create `backend/app/rag/service.py`:
```python
"""RAG 检索编排：embed → 混合检索 → 重排。"""
from __future__ import annotations

from .config import RAGConfig
from .embeddings import EmbeddingService, ModelScopeDenseEmbedder
from .models import RAGResult
from .rerank import rerank
from .vector_store import QdrantVectorStore


class RAGService:
    def __init__(self, cfg: RAGConfig, embeddings: EmbeddingService, store: QdrantVectorStore):
        self._cfg = cfg
        self._emb = embeddings
        self._store = store

    @classmethod
    def from_env(cls) -> "RAGService":
        cfg = RAGConfig.from_env()
        emb = EmbeddingService(dense=ModelScopeDenseEmbedder(cfg))
        store = QdrantVectorStore(cfg)
        store.ensure_collection()
        return cls(cfg, emb, store)

    def search(self, query: str, top_k: int = 5, credibility_threshold: float | None = None,
               city: str | None = None) -> list[RAGResult]:
        if not (query or "").strip():
            return []
        threshold = self._cfg.credibility_threshold if credibility_threshold is None else credibility_threshold
        dense, sparse = self._emb.embed_query(query)
        hits = self._store.hybrid_search(
            dense, sparse, top_k=max(top_k, self._cfg.prefetch_limit),
            credibility_threshold=threshold, city=city,
        )
        return rerank(hits, self._cfg)[:top_k]

    def search_by_city(self, query: str, city: str, top_k: int = 5) -> list[RAGResult]:
        return self.search(f"{city} {query}", top_k=top_k, city=city)
```

Modify `backend/app/rag/__init__.py`:
```python
from .config import RAGConfig
from .service import RAGService

__all__ = ["RAGConfig", "RAGService"]
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && python -m pytest tests/rag/test_service.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/service.py backend/app/rag/__init__.py backend/tests/rag/test_service.py
git commit -m "feat(rag): retrieval service orchestrating hybrid search + rerank"
```

---

### Task 8: CLI 脚本（导入 / 检索）

> 纯逻辑（`load_posts` / 导入 / 检索）已在 Task 6-7 测过；CLI 是薄 I/O 封装，由 Task 10 端到端冒烟覆盖，不再单测。

**Files:**
- Create: `backend/scripts/rag_import.py`
- Create: `backend/scripts/rag_search.py`

- [ ] **Step 1: 实现导入 CLI**

Create `backend/scripts/rag_import.py`:
```python
#!/usr/bin/env python
"""把 xhs JSON 导入 Qdrant。用法：python scripts/rag_import.py --data out/rag/xhs_beijing.json"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="JSON 文件或目录")
    args = ap.parse_args()

    from app.rag.config import RAGConfig
    from app.rag.embeddings import EmbeddingService, ModelScopeDenseEmbedder
    from app.rag.importer import RAGImporter, load_posts
    from app.rag.vector_store import QdrantVectorStore

    cfg = RAGConfig.from_env()
    store = QdrantVectorStore(cfg)
    store.ensure_collection()
    emb = EmbeddingService(dense=ModelScopeDenseEmbedder(cfg))
    stats = RAGImporter(cfg, emb, store).import_posts(load_posts(args.data))
    print(f"导入完成：{stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 实现检索 CLI**

Create `backend/scripts/rag_search.py`:
```python
#!/usr/bin/env python
"""检索验证。用法：python scripts/rag_search.py --query "北京免费公园" --top-k 5"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--city", default=None)
    args = ap.parse_args()

    from app.rag.service import RAGService
    svc = RAGService.from_env()
    for r in svc.search(args.query, top_k=args.top_k, city=args.city):
        print(f"[{r.score:.3f}] cred={r.credibility} | {r.title}  {r.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 手动冒烟（导入逻辑已测，这里仅验证 CLI 能起；真实跑见 Task 10）**

Run: `cd backend && python scripts/rag_import.py --help && python scripts/rag_search.py --help`
Expected: 两个脚本各打印 usage，无 import 错误。

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/rag_import.py backend/scripts/rag_search.py
git commit -m "feat(rag): import and search CLI scripts"
```

---

### Task 9: 检索 API（POST /rag/search）

**Files:**
- Create: `backend/app/api/routes/rag.py`
- Modify: `backend/app/api/main.py`（注册路由）
- Test: `backend/tests/rag/test_api.py`

- [ ] **Step 1: 看现有路由注册方式**

Run: `cd backend && grep -n "include_router\|APIRouter" app/api/main.py app/api/routes/trip.py | head`
Expected: 看到 `app.include_router(...)` 与 `router = APIRouter(...)` 的现有写法，照搬同样风格。

- [ ] **Step 2: 写失败测试（monkeypatch RAGService）**

Create `backend/tests/rag/test_api.py`:
```python
from fastapi.testclient import TestClient

import app.api.routes.rag as rag_route
from app.api.main import app
from app.rag.models import RAGResult


def test_search_endpoint(monkeypatch):
    def fake_get_service():
        class S:
            def search(self, query, top_k=5, city=None):
                return [RAGResult("p1", "标题", "正文", ["北京"], 0.9, 0.8, None, [], "u")]
        return S()
    monkeypatch.setattr(rag_route, "get_rag_service", fake_get_service)

    client = TestClient(app)
    r = client.post("/rag/search", json={"query": "北京公园", "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["post_id"] == "p1"


def test_search_empty_query_400(monkeypatch):
    monkeypatch.setattr(rag_route, "get_rag_service", lambda: None)
    client = TestClient(app)
    r = client.post("/rag/search", json={"query": "  "})
    assert r.status_code == 400
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/rag/test_api.py -v`
Expected: FAIL（`404` 或导入错误，路由未注册）

- [ ] **Step 4: 实现路由**

Create `backend/app/api/routes/rag.py`:
```python
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
```

- [ ] **Step 5: 注册路由**

在 `backend/app/api/main.py` 中，仿照现有 `include_router` 处加入：
```python
from .routes import rag as rag_routes  # 顶部 import 区
app.include_router(rag_routes.router)   # 与其它 include_router 并列
```

- [ ] **Step 6: 跑测试**

Run: `cd backend && python -m pytest tests/rag/test_api.py -v`
Expected: PASS（2 passed）

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/rag.py backend/app/api/main.py backend/tests/rag/test_api.py
git commit -m "feat(rag): POST /rag/search endpoint"
```

---

### Task 10: 文档化环境变量 + 全量回归 + 端到端冒烟

**Files:**
- Modify: `backend/.env.example`

- [ ] **Step 1: 补 .env.example（占位，不含真值）**

在 `backend/.env.example` 末尾追加：
```
# RAG: ModelScope 稠密 embedding
MODELSCOPE_API_KEY=your-modelscope-key
# RAG: Qdrant 向量库
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
RAG_COLLECTION=travel_documents
RAG_CREDIBILITY_THRESHOLD=0.65
```

- [ ] **Step 2: 全量单测回归**

Run: `cd backend && python -m pytest tests/rag/ -v`
Expected: 全 PASS（config/credibility/embeddings/vector_store/rerank/importer/service/api）

- [ ] **Step 3: 端到端冒烟（连真实云 Qdrant + ModelScope，需 .env）**

Run:
```bash
cd backend
python scripts/rag_import.py --data ../out/rag/xhs_beijing.json
python scripts/rag_search.py --query "北京免费逛的公园" --top-k 5
```
Expected: 导入打印 `{'total':5,'indexed':..,'skipped':..}`；检索打印按分排序的标题，公园/免费类排前。

> 若 `indexed=0`：多半是可信度阈值偏高（xhs 样本可信度字段不全）。临时用 `RAG_CREDIBILITY_THRESHOLD=0.5` 重试，并在结果中确认归一化生效。

- [ ] **Step 4: Commit**

```bash
git add backend/.env.example
git commit -m "docs(rag): document RAG env vars in .env.example"
```

---

## 备注：执行前提

- 单测（Task 1-9）离线可跑：Qdrant `:memory:` + jieba 本地 + FakeDense。
- 仅 Task 10 Step 3 端到端需要真实 `MODELSCOPE_API_KEY` 与 Qdrant Cloud（均已在 `backend/.env`）。
- 若 `qdrant-client` 本地模式不支持 `Modifier.IDF` 或 RRF，Task 4 的 `:memory:` 测试改指向云实例（环境变量切换），其余不变。
