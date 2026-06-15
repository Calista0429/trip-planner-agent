# RAG 移植 + 改进设计（Trip-planner-agent）

- 日期：2026-06-15
- 状态：待评审
- 目标：把 `travel_agent` 的 RAG 子系统在本仓库重新实现一遍，并修复其已知缺陷。

## 1. 背景与目标

`travel_agent/backend/app/services/rag/` 是一套基于 Qdrant 的小红书帖子检索系统，但分析后发现四处真实缺陷：

1. **可信度评分卡未归一化** —— 四个维度子分之和最高约 0.64，撞不过默认阈值 0.65，只能靠导入时把阈值降到 0.3 兜底。
2. **"混合检索"名不副实** —— sparse 用 md5 哈希词频（无 IDF），且根本没接进 Qdrant 查询，实际只有 dense。
3. **可信度过滤是 Python 后处理** —— 多召一倍再筛，未用 Qdrant 索引。
4. **无重排** —— 仅按向量分排序，未利用可信度/时效。

本设计在本仓库（`Trip-planner-agent/backend`）重建该系统，**忠实照搬存储与嵌入选型**（Qdrant + 远程 Qwen3-Embedding-8B），同时修复以上四点。

### 已确认决策

| 决策点 | 选择 |
|---|---|
| 存储/向量后端 | 忠实照搬：Qdrant server + 远程 embedding（Qwen3-Embedding-8B 4096 维，ModelScope OpenAI 兼容 API） |
| 改进范围 | 全部四项：真混合 dense+sparse、修可信度归一化、Qdrant 侧过滤、轻量重排 |
| 模态 | **仅文本**（不做图片/多模态，不建 images 集合） |
| 集成深度 | 独立模块 + 导入脚本 + 检索 API/CLI；**不**改动现有 LangGraph 规划器 |
| 数据源 | `scripts/xhs_to_rag.py` 产出的 `out/rag/*.json` |

## 2. 架构

新建包 `backend/app/rag/`，各文件单一职责、通过明确接口通信：

```
backend/app/rag/
  __init__.py
  config.py        # RAGConfig：collection 名、维度、权重、阈值、模型 id、Qdrant 连接（读 env/settings）
  embeddings.py    # EmbeddingService：稠密(Qwen3 远程, httpx) + 稀疏(fastembed BM25)
  credibility.py   # CredibilityCalculator：四维评分卡（★每维归一到 [0,1] 再加权）
  vector_store.py  # QdrantVectorStore：命名向量 dense+sparse；credibility/city 建索引；hybrid_search
  rerank.py        # rerank()：sim + credibility + freshness 加权重排
  importer.py      # RAGImporter：读 xhs JSON → 可信度筛 → 拼文本 → 向量 → upsert
  service.py       # RAGService：search() = 混合检索 → 重排 → 返回；单例
scripts/
  rag_import.py    # 导入 CLI
  rag_search.py    # 检索 CLI（人工验证用）
backend/app/api/routes/rag.py   # POST /rag/search
```

### 组件职责与接口

- **config.py** — `RAGConfig`（dataclass/pydantic）。字段：`qdrant_url`、`qdrant_api_key`、`modelscope_api_key`、`collection="travel_documents"`、`dense_dim=4096`、`dense_model="Qwen/Qwen3-Embedding-8B"`、`bm25_model="Qdrant/bm25"`、`credibility_threshold=0.65`、重排权重 `w_sim=0.6 / w_cred=0.25 / w_fresh=0.15`、`prefetch_limit=20`。依赖：现有 `app.config.get_settings()`。

- **embeddings.py** — `EmbeddingService`：
  - `embed_dense(texts: list[str]) -> list[list[float]]`：httpx POST ModelScope `/v1/embeddings`，model=Qwen3，返回 4096 维；支持批量；带简单重试（3 次指数退避）。
  - `embed_sparse(texts) -> list[SparseVector]` 与 `embed_sparse_query(q) -> SparseVector`：fastembed `Bm25` 本地推理，IDF 自动。
  - 接口对 `vector_store`/`importer`/`service` 稳定；dense 远程、sparse 本地的差异封装在内。

- **credibility.py** — `CredibilityCalculator.calculate(post) -> CredibilityScore`。★见 §4.2。

- **vector_store.py** — `QdrantVectorStore`：
  - `ensure_collection()`：建命名向量 `dense`(4096, COSINE) + 稀疏向量 `sparse`；建 payload 索引 `credibility`(float) 与 `city`(keyword)。
  - `upsert(points)`：批量写。
  - `hybrid_search(dense_vec, sparse_vec, top_k, credibility_threshold, city=None) -> list[Hit]`：★见 §4.1/4.3，一次 Query API 完成 prefetch+RRF+过滤。

- **rerank.py** — `rerank(hits, weights) -> list[RAGResult]`：纯函数，确定性。★见 §4.4。

- **importer.py** — `RAGImporter.import_posts(posts: list[dict]) -> ImportStats`：见 §3 数据流（写入）。

- **service.py** — `RAGService.search(query, top_k=5, credibility_threshold=None, city=None) -> list[RAGResult]`；`search_by_city(query, city, top_k)`。单例，惰性初始化 embeddings + vector_store。

### 数据模型

- `RAGResult`：`post_id, title, content, tags, score, credibility, publish_time, image_urls, url, dense_score, sparse_rank`。
- `CredibilityScore`：`final, creator, content, community, freshness, details`。
- payload（存 Qdrant）：`post_id, title, content, tags, credibility, publish_time, likes, collects, comments, image_urls, city`。

## 3. 数据流

### 写入（导入）
```
out/rag/*.json (xhs_to_rag.py 产出)
  → 逐条 post：
      credibility = CredibilityCalculator.calculate(post)
      if credibility.final < threshold: skip
      text = f"{title} {desc} {' '.join(tags)}"          # 与原版一致，desc 驱动向量
      dense = embeddings.embed_dense([text])             # 4096
      sparse = embeddings.embed_sparse([text])           # BM25
      point = (id=post_id, vectors={dense, sparse}, payload={...})
  → vector_store.upsert(批量)
```
- 批量大小 20；单条失败记录并跳过，不中断整批。
- 阈值用真实的 **0.65**（归一化修好后可达），不再用 0.3 hack。

### 检索
```
query
  → q_dense = embeddings.embed_dense([query])[0]
    q_sparse = embeddings.embed_sparse_query(query)
  → hits = vector_store.hybrid_search(q_dense, q_sparse, top_k=prefetch, threshold, city)
        # Qdrant 内：prefetch(dense)+prefetch(sparse) → RRF 融合 → credibility/city 过滤
  → results = rerank(hits)                                # sim+credibility+freshness 重排
  → 取前 top_k 返回
```

## 4. 四项改进细节

### 4.1 真混合（dense + sparse + RRF）
Qdrant 命名向量 + Query API 一次完成：
```python
client.query_points(
    collection,
    prefetch=[
        Prefetch(query=q_dense,  using="dense",  limit=prefetch_limit, filter=cred_filter),
        Prefetch(query=q_sparse, using="sparse", limit=prefetch_limit, filter=cred_filter),
    ],
    query=FusionQuery(fusion=Fusion.RRF),
    limit=top_k, with_payload=True,
)
```
替换原版"假 sparse + 仅 dense 查询"。sparse 由 fastembed BM25 产出（带 IDF）。

### 4.2 修可信度归一化
四维原始满分：creator 0.6 / content 0.75 / community 0.3 / freshness 1.0。**每维除以各自满分归一到 [0,1]**，再加权：
```
final = 0.3*(creator/0.6) + 0.4*(content/0.75) + 0.2*(community/0.3) + 0.1*freshness
```
现 max=1.0，0.65 阈值真正可达。另修原版小 bug：`useful_comments_ratio` 默认 0.5 而判定用 `>0.5` 导致默认永不得分 → 改为 `>=0.5`，并消费 xhs 适配器已产出的 `useful_comments_ratio`。`report_rate`、`has_real_photos` 字段缺省（xhs 数据不含），走默认值。

### 4.3 Qdrant 侧过滤
建 `credibility` 浮点 payload 索引，过滤条件进 prefetch：
```python
cred_filter = Filter(must=[FieldCondition(key="credibility", range=Range(gte=threshold))])
# city 可选：再 must 一条 FieldCondition(key="city", match=MatchValue(city))
```
取消原版"多召一倍再 Python 筛"。

### 4.4 轻量重排
对融合结果重打分（确定性、无 LLM）：
```
freshness = max(0, 1 - days_old/730)
final_score = w_sim*norm(rrf_score) + w_cred*credibility + w_fresh*freshness
```
按 `final_score` 降序。权重默认 0.6/0.25/0.15，可配。

## 5. 配置（env / settings）

| 变量 | 用途 | 默认 |
|---|---|---|
| `QDRANT_URL` | Qdrant 地址 | `http://localhost:6333` |
| `QDRANT_API_KEY` | Qdrant key（云端） | 空 |
| `MODELSCOPE_API_KEY` | 稠密 embedding | 必填（检索/导入时） |
| `RAG_COLLECTION` | 集合名 | `travel_documents` |
| `RAG_CREDIBILITY_THRESHOLD` | 入库/检索阈值 | `0.65` |

接入现有 `app/config.py` 的 settings；缺失 key 时给出明确报错。

## 6. 错误处理

- **稠密 embedding 失败**：重试 3 次；导入时跳过该条并计数，检索时抛出可读错误（提示检查 `MODELSCOPE_API_KEY` / 网络）。
- **Qdrant 不可达**：初始化即抛清晰错误（提示启动 Qdrant 或检查 `QDRANT_URL`）。
- **集合不存在时检索**：提示先运行 `rag_import.py`。
- **空查询 / 无结果**：返回 `[]`，不报错。
- **单条导入失败**：记录到 `ImportStats.errors`，继续。

## 7. 测试策略

可离线覆盖大部分逻辑（Qdrant `:memory:` 模式 + fastembed 本地 + 假 dense embedder）：

- `test_credibility.py`：每维打分 + 归一化；断言满分=1.0、0.65 阈值可达、`useful_comments_ratio` bug 已修。**离线**。
- `test_importer.py`：喂样本 xhs post（用 `out/rag/xhs_beijing.json` 真实样本）→ 断言 payload/文本/可信度/跳过逻辑。stub embedders，**离线**。
- `test_vector_store.py` / `test_service.py`：Qdrant `:memory:` + fastembed BM25 + `FakeDenseEmbedder`（确定性向量）→ 断言混合检索顺序、credibility 过滤排除低质、重排改变顺序、§4 例子（"北京免费逛的公园"→ #5>#4>#3>#2）。**离线**。
- 真实 ModelScope 稠密 embedding：薄封装，仅集成测试（需 key），不进单测。

测试框架沿用仓库现有 pytest 约定（`backend/tests/`）。

## 8. 依赖

新增到 `backend/requirements.txt`：
- `qdrant-client>=1.12`（含本地 `:memory:` 与 Query API/RRF/sparse）
- `fastembed>=0.4`（BM25 稀疏，IDF 自动；本地推理）

稠密 embedding 复用现有 `httpx`，不引 `openai`/`dashscope`。

## 9. 不在范围内（YAGNI）

- 图片/多模态（images 集合、跨模态检索、图文融合）。
- 接入 LangGraph 规划器（STEP0 检索节点）—— 后续单独议。
- 小红书爬取 —— 复用已完成的 `scripts/xhs_to_rag.py`。
- SPLADE 等学习型稀疏。
- credibility 的 `report_rate` / `has_real_photos` 真值采集。

## 10. 风险 / 待确认

- ModelScope 是否稳定提供 `Qwen/Qwen3-Embedding-8B` 的 embeddings 接口（与 travel_agent 一致，假定可用）。
- 安装版 `qdrant-client` 的 `:memory:` 是否完整支持 sparse + RRF 融合（需在实现首步用冒烟测试确认；若不支持，测试退化为连本地 Qdrant 容器）。
- `fastembed` 首次会下载 BM25 模型（体积小），CI 需联网或预缓存。
