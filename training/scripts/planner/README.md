# 当前脚本目录

更新时间：2026-05-12

当前脚本按 `data/`、`eval/`、`audit/`、`pricing/`、`bestofn/`、`training/` 分组；目录生命周期规则见 `training/STRUCTURE.md`。旧脚本只作为参考，不再继续堆补丁。

第一批要迁移/重写的能力：

1. `PlannerContext` 构造
   - 显式生成 `party`
   - 显式生成 `budget_constraint`
   - 显式生成 `preference_profile`
   - 显式生成 `lodging_policy`
   - 给酒店/餐饮补 `estimated_cost_hint` 和 `cost_source`

2. SFT 数据生成
   - 生成 requests
   - 获取工具快照
   - 用强模型生成 TripPlan
   - 严格校验酒店价格复制、住宿晚数和预算账本

3. SFT 数据审计和切分
   - 清洗 dirty 数据
   - 固定 train/val/eval
   - 输出 LLaMA-Factory 格式

4. DPO 数据生成
   - 复用 PlannerContext
   - 多模型自然候选
   - 规则硬过滤
   - LLM judge
   - chosen/rejected pair 构造

## 分类

- `data/`：SFT/realbudget 数据生成、预览和清洗导出。
- `pricing/`：景点候选收集、票价分桶和强模型估价。
- `eval/`：frozen eval 构建、prompt/context 刷新和预算修正实验。
- `audit/`：预算贴合度、上下文可达性和 SFT 可用性审计。
- `training/`：本地训练启动/恢复脚本。
- `bestofn/`：多候选采样、规则 reward 选择和偏好/SFT 数据导出。

## 已迁入脚本

### `data/generate_sft_data.py`

生成 SFT 数据，默认使用受控真实分布，不再复用旧数据。

先看请求分布，不调用高德和强模型：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/generate_sft_data.py \
  --count 100 \
  --request-source controlled \
  --date-mode mixed \
  --dry-run-requests \
  --dry-run-summary
```

只跑 PlannerContext smoke，不调用 Planner 强模型：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/generate_sft_data.py \
  --count 20 \
  --request-source controlled \
  --date-mode mixed \
  --workers 1 \
  --dry-run-context
```

正式小批量造 SFT：

```bash
mkdir -p training/data/planner/sft_runs/260512_example

nohup .venv-training-py311/bin/python3 -u training/scripts/planner/data/generate_sft_data.py \
  --count 100 \
  --start-index 0 \
  --request-source controlled \
  --date-mode mixed \
  --workers 2 \
  --resume \
  --output-dir training/data/planner/sft_runs/260512_example \
  > training/data/planner/sft_runs/260512_example/generate_sft.log 2>&1 &
```

输出：

- `training/data/planner/sft_runs/<YYMMDD>_<run_slug>/requests.jsonl`
- `training/data/planner/sft_runs/<YYMMDD>_<run_slug>/records.jsonl`
- `training/data/planner/sft_runs/<YYMMDD>_<run_slug>/errors.jsonl`
- `training/data/llamafactory/generated/trip_sft_train.json`
- `training/data/llamafactory/generated/trip_sft_val.json`

当前 SFT 写入前会硬校验：

- `party.total` 和预算结构必须合法。
- 中间住宿日 `hotel` 不能为空。
- `hotel.estimated_cost` 必须复制候选 `estimated_cost_hint`。
- `attraction.ticket_price` 必须复制候选 `ticket_price_hint`。
- `budget.total_hotels` 必须覆盖逐日住宿晚数。
- `budget.total_attractions` 必须按 `party.total` 汇总门票。
- `budget.total` 必须等于四个预算分项之和。

### `pricing/collect_attraction_candidates.py`

收集 PlannerContext 中出现过的景点候选，用于补本地票价表。这个脚本不调用 Planner 强模型。

从已有 records 聚合：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/pricing/collect_attraction_candidates.py \
  --records training/data/planner/eval/records.jsonl
```

直接按受控分布查询 PlannerContext，只收集景点候选：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/pricing/collect_attraction_candidates.py \
  --collect-context \
  --count 200 \
  --request-source controlled \
  --date-mode mixed \
  --workers 1
```

输出：

- `training/data/planner/attraction_prices/generated/attraction_candidates.jsonl`
- `training/data/planner/attraction_prices/reports/景点票价候选收集报告.md`
- `training/data/planner/attraction_prices/snapshots/attraction_price_table_todo.json`

判断口径：

- 高德已有 `cost` 的景点不需要进入本地表。
- 命中 `backend/app/planner/attraction_price_table.json` 的景点不需要重复补。
- 高德无 `cost` 且没有命中本地表的景点，会进入待补模板。

### `pricing/bucket_attraction_price_candidates.py`

把高频景点候选按票价处理方式分桶，方便人工审核哪些景点应进入本地票价画像表。

```bash
.venv-training-py311/bin/python3 training/scripts/planner/pricing/bucket_attraction_price_candidates.py \
  --min-request-count 5
```

输出：

- `training/data/planner/attraction_prices/generated/request_count_ge5_bucketed_candidates.jsonl`
- `training/data/planner/attraction_prices/reports/request_count_ge5_景点票价分桶审核.md`
- `training/data/planner/attraction_prices/snapshots/request_count_ge5_price_table_review_draft.json`

### `pricing/estimate_attraction_prices_with_llm.py`

对 `request_count >= 5` 的高频景点统一调用强模型估算成人全价票价，并明确标记为 `llm_estimated`。这批价格只用于 SFT 的预算账本训练，不是官方票价或实时票价。

先看 prompt，不调用强模型：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/pricing/estimate_attraction_prices_with_llm.py \
  --min-request-count 5 \
  --batch-size 5 \
  --limit 5 \
  --dry-run-prompt
```

正式估算：

```bash
nohup .venv-training-py311/bin/python3 -u training/scripts/planner/pricing/estimate_attraction_prices_with_llm.py \
  --min-request-count 5 \
  --batch-size 20 \
  --resume \
  > training/data/planner/attraction_prices/generated/estimate_prices_llm.log 2>&1 &
```

输出：

- `training/data/planner/attraction_prices/generated/request_count_ge5_llm_price_estimates.jsonl`
- `training/data/planner/attraction_prices/snapshots/request_count_ge5_attraction_price_table_llm_estimated.json`
- `training/data/planner/attraction_prices/reports/景点票价强模型估算说明.md`

后续如果要用于线上 Planner，需要把估价表审核后合并到：

- `backend/app/planner/attraction_price_table.json`

### `eval/build_eval_set.py`

构建 frozen 评估集。这个脚本只生成请求、获取 PlannerContext、
写入压缩上下文和最终 Planner prompt，不调用模型生成 TripPlan。

先小批量 smoke：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/eval/build_eval_set.py \
  --count 10 \
  --start-index 0 \
  --request-source controlled \
  --date-mode mixed \
  --workers 2 \
  --output-dir training/data/planner/eval_smoke
```

正式构建评估集：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/eval/build_eval_set.py \
  --count 200 \
  --start-index 0 \
  --id-prefix standard200_eval \
  --request-source controlled \
  --date-mode mixed \
  --workers 4 \
  --resume
```

构建更难的 hard eval，用于拉开 base/SFT/DPO 能力差异：

当前 hard eval 使用原 `harder` 压力分布构建，主路径统一命名为 `eval_hard`。

```bash
.venv-training-py311/bin/python3 training/scripts/planner/eval/build_eval_set.py \
  --count 300 \
  --start-index 0 \
  --id-prefix harder_eval \
  --request-source controlled \
  --date-mode mixed \
  --difficulty harder \
  --workers 2 \
  --output-dir training/data/planner/eval_hard \
  --resume
```

输出：

- `training/data/planner/eval/records.jsonl`
- `training/data/planner/eval/requests.jsonl`
- `training/data/planner/eval/errors.jsonl`
- `training/data/planner/eval/summary.json`
- `training/data/planner/eval/评估集摘要.md`
- `training/data/planner/eval_hard/records.jsonl`
- `training/data/planner/eval_hard/requests.jsonl`
- `training/data/planner/eval_hard/errors.jsonl`
- `training/data/planner/eval_hard/summary.json`
- `training/data/planner/eval_hard/评估集摘要.md`

后续所有 baseline/SFT/DPO 评估都应优先使用这两份固定输入，避免请求分布、
工具快照、天气来源变化影响模型对比。

如果后端 PlannerContext 检索能力发生变化，但仍希望保留同一批请求和
`record_id` 做横向比较，不要重采样请求，改用 context rebuild：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/eval/rebuild_eval_contexts.py \
  --input-records training/data/planner/archive/eval_pre_high_end_context_20260511/eval/records.jsonl \
  --output-dir training/data/planner/eval \
  --workers 2 \
  --source-label 260511_high_end_poi_context_rebuild

.venv-training-py311/bin/python3 training/scripts/planner/eval/rebuild_eval_contexts.py \
  --input-records training/data/planner/archive/eval_pre_high_end_context_20260511/eval_hard/records.jsonl \
  --output-dir training/data/planner/eval_hard \
  --workers 2 \
  --source-label 260511_high_end_poi_context_rebuild
```

这会保留请求分布和样本 ID，只重新调用当前后端的 POI/天气/价格 hint
链路，并重建 `compact_planner_context` 与 `planner_query`。后续同一轮
baseline/SFT/DPO 评测必须使用同一份 rebuild 后的 records，避免新旧工具
快照混在一次模型对比里。

## DPO 起步

当前 DPO 定位为偏好训练，不用于修坏 JSON 或坏 schema。DPO prompt 池使用
SFT 生成阶段留下的 records，但只取 request / PlannerContext /
planner_query，不使用 teacher answer。

先用当前最终 prompt 刷新 DPO prompt 来源：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/eval/refresh_eval_prompts.py \
  --input-records training/data/planner/sft_runs/<YYMMDD>_<run_slug>/records.jsonl \
  --output-dir training/data/planner/dpo/prompt_source
```

构造 DPO prompts：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/dpo_build_prompts.py \
  --records training/data/planner/dpo/prompt_source/records.jsonl \
  --output training/data/planner/dpo/prompts.jsonl \
  --source prompt_source
```

第一版不使用 SFT 候选，先跑 4 路候选：

- base_t02
- base_t07
- strong_t02
- strong_t07

20 条 smoke：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/dpo_generate_candidates.py \
  --prompts training/data/planner/dpo/prompts.jsonl \
  --output training/data/planner/dpo/candidates_smoke20.jsonl \
  --base-url http://127.0.0.1:4396/v1 \
  --base-api-model trip-planner-base \
  --no-sft-low \
  --include-strong-low \
  --include-strong-high \
  --workers 4 \
  --limit 20 \
  --resume
```

后续 judge、pair 构造和 best-of-n 相关流程参考：

```text
training/docs/内部文档/DPO分块LogProb方案说明.md
training/scripts/planner/bestofn/README.md
```
