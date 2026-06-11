# 后训练与评测说明

本目录保存旅行助手的后训练资产。公开仓库只保留当前主线：训练数据、脚本、协议文档、轻量评测报告和可复现配置。历史数据、旧脚本、废弃 prompt 消融、过程日志、模型权重、checkpoint 和大规模生成明细不会上传。

当前目标不是让模型凭空知道更多旅行事实，而是让后端先把事实和约束编译成结构化 `PlannerContext`，再让 Planner 模型稳定生成符合业务协议的 `TripPlan JSON`。

更新时间：2026-05-22。文件结构和生命周期规则见 [STRUCTURE.md](STRUCTURE.md)，长期文档索引见 [docs/README.md](docs/README.md)，本机完整后训练资产地图见 [docs/后训练产物/本地资产索引.md](docs/后训练产物/本地资产索引.md)。

## 分工

```text
前端收集用户意图
  -> 后端结构化人数、预算、偏好、住宿和工具候选
  -> PlannerContext 冻结模型可见事实
  -> Planner 模型生成 TripPlan JSON
  -> 规则评测脚本检查 schema、grounding、预算和偏好指标
```

SFT 主要学习确定性协议：

- JSON 可解析，`TripPlan` schema 通过。
- 日期、天数、天气和住宿晚数正确。
- 景点、酒店、餐饮尽量来自工具候选。
- 酒店、门票、餐饮预算口径稳定。
- `budget.total` 和预算分项关系可校验。

DPO 主要学习合法候选之间的偏好：

- 更符合预算档位。
- 更贴合同行人、饮食、节奏和负向约束。
- 更可执行、更少重复、更适合真实用户。

## 公开目录

```text
training/
├── STRUCTURE.md          # 数据、脚本、文档、报告的目录边界
├── configs/              # 按模型分组的训练配置
├── data/
│   ├── llamafactory/     # LLaMA-Factory 数据入口
│   └── planner/               # 当前训练、评估和票价数据
├── docs/                 # 教程、内部协议、指标、预算报告和 DPO 计划
├── outputs/eval/         # 轻量评测报告、comparison 和 manifest
├── prompts/              # 数据生成 prompt
├── scripts/
│   ├── shared/           # 公共 helper 和 LLM 客户端
│   ├── serving/          # 本地 Planner 模型服务
│   ├── validation/       # TripPlan schema 校验
│   └── planner/               # 当前脚本按 data/eval/audit/pricing/training 分组
└── requirements-training.txt
```

重要入口：

- `docs/教程/旅行助手后训练实战教程.md`
- `STRUCTURE.md`
- `docs/README.md`
- `docs/内部文档/SFT阶段总结.md`
- `docs/内部文档/规划上下文协议.md`
- `docs/内部文档/评测指标.md`
- `docs/内部文档/Prompt消融阶段总结.md`
- `docs/内部文档/SFT目标与边界.md`
- `docs/内部文档/SFT数据生成口径审核.md`
- `docs/内部文档/全参微调实验备忘录.md`
- `docs/内部文档/DPO分块LogProb方案说明.md`
- `docs/内部文档/典型旅游预算报告.md`
- `docs/内部文档/预算分档与实际数据预算对比.md`
- `docs/内部文档/新预算评估集重建与SFT预算审计.md`
- `data/planner/SFT已归档说明.md`
- `outputs/eval/README.md`
- `outputs/eval/reports/260512_bestofn_replay_extended_w10/bestofn_replay_extended_comparison.md`

## 环境

训练脚本会读取 `backend/.env` 或项目根 `.env`。至少需要：

```bash
AMAP_API_KEY=your_amap_api_key
```

如果要调用强模型生成 SFT 数据、估算票价或做 judge，还需要配置 OpenAI-compatible 或 DeepSeek 风格变量。推荐使用数据生成专用变量，避免影响后端服务：

```bash
DATA_GEN_API_KEY=your_data_generation_key
DATA_GEN_BASE_URL=your_openai_compatible_base_url
DATA_GEN_MODEL=your_model_name
DATA_GEN_REASONING_EFFORT=low
DATA_GEN_THINKING=false
```

安装依赖：

```bash
cd helloagents-trip-planner
python -m venv .venv-training-py311
source .venv-training-py311/bin/activate
pip install -r training/requirements-training.txt
```

如果本地已经有可用训练环境，可以把下面命令里的 `.venv-training-py311/bin/python3` 换成对应解释器。

## SFT 数据状态

2026-05-08 之前生成的 SFT 数据已经全量归档，不再作为当前训练入口：

- 旧 `training/data/planner/sft/` 和 `training/data/planner/sft_current/` 已移入 `training/data/planner/archive/`。
- 旧 LLaMAFactory SFT 导出已移入 `training/data/llamafactory/archive/`。
- `training/data/llamafactory/dataset_info.json` 只保留当前明确训练入口；大体积 train/val JSON/YAML 放在 `training/data/llamafactory/generated/`，默认由 `.gitignore` 排除。

后续 SFT 只按 realbudget 新口径重建。建议流程是：

```text
smoke 20 -> 审计 -> 100 条 -> 审计 -> 1000 条 -> 导出 LLaMAFactory
```

新数据必须写入明确的 run 目录，例如 `training/data/planner/sft_runs/<YYMMDD>_<run_slug>/`，不再混写旧 `training/data/planner/sft/`。外部强模型调用必须记录 provider 返回的 `response.usage`，并保留 run manifest，避免 token 成本不可追踪。

## 数据构建脚本

请求和上下文构建脚本仍保留，用于后续 realbudget pipeline。先 dry-run 请求分布，不调用高德或强模型：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/generate_sft_data.py \
  --count 100 \
  --request-source controlled \
  --date-mode mixed \
  --dry-run-requests \
  --dry-run-summary
```

只构建 `PlannerContext` smoke，不调用 Planner 强模型：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/generate_sft_data.py \
  --count 20 \
  --request-source controlled \
  --date-mode mixed \
  --workers 1 \
  --dry-run-context
```

写入训练集前必须做硬校验，包括人数、预算结构、酒店住宿晚数、酒店价格复制、景点票价复制、门票按人数汇总、住宿预算覆盖晚数和预算分项加总。

## 票价表

高德 POI 不一定给出景点票价。当前流程会把高频候选景点收集出来，形成本地票价表候选，用于预算账本训练。

从已有 records 聚合候选：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/pricing/collect_attraction_candidates.py \
  --records training/data/planner/eval/records.jsonl
```

按请求分布直接收集候选：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/pricing/collect_attraction_candidates.py \
  --collect-context \
  --count 200 \
  --request-source controlled \
  --date-mode mixed \
  --workers 1
```

对高频候选分桶：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/pricing/bucket_attraction_price_candidates.py \
  --min-request-count 5
```

对高频景点调用强模型估算票价：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/pricing/estimate_attraction_prices_with_llm.py \
  --min-request-count 5 \
  --batch-size 20 \
  --resume
```

估算结果只用于训练预算口径，不代表官方实时票价。线上使用前需要人工审核并合并到 `backend/app/planner/attraction_price_table.json`。

## 评估集

构建 standard eval：

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

构建 hard eval：

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

公开仓库保留的评估入口：

- `training/data/planner/eval/records.jsonl`
- `training/data/planner/eval_hard/records.jsonl`

所有 baseline、SFT、DPO 对比都应复用这些冻结输入，避免请求分布、工具快照或天气来源变化影响模型对比。

## 当前评测口径

评测固定输出两层主要 pass：

- `sft_hard_pass`：线上可用的确定性协议，包括 schema、日期、天气、住宿、grounding、预算账本和硬预算约束。
- `dpo_soft_pass`：在合法输出基础上看餐饮多样性、餐饮 grounding、预算偏好和整体可用性。

阶段性还记录：

- `sft_budget_semantic_hard_pass`
- `hotel_budget_relation_ok`
- `attraction_budget_party_relation_ok`
- `meal_cost_scale_ok`
- `budget_relationship_ok`

完整口径见评测指标文档。

## 当前公开结果

当前评测输出统一按新目录组织：

```text
training/outputs/eval/by_model/<model>/<YYMMDD>_<run_slug>/
training/outputs/eval/comparisons/<YYMMDD>_<comparison_slug>/
training/outputs/eval/audits/<YYMMDD>_<audit_slug>/
training/outputs/eval/logs/<YYMMDD>_<log_slug>/
training/outputs/eval/reports/<YYMMDD>_<report_slug>/
```

当前可公开引用的报告都整理到 `reports/`：

- `outputs/eval/reports/260512_bestofn_replay_extended_w10/`：2026-05-12 Best-of-N replay 扩展对比，包含多个 checkpoint、上一轮 replay、前序 LoRA、旧路线对照与外部 Mimo reference 的 500 条合并/standard/hard 主要指标。
- `outputs/eval/reports/260511_usage700_followup_w10/`：usage700 SFT follow-up 对比。
- `outputs/eval/reports/260511_high_end_context_mainline/`：高端 POI 上下文重构后三模型主线对比。

`by_model/`、`comparisons/`、`audits/`、`logs/` 默认视为本地生成产物；需要公开的评估结论先整理成 `reports/<YYMMDD>_<slug>/`。

## DPO 状态

当前主线把 DPO 定位为偏好训练，而不是修坏 JSON 或坏 schema。DPO prompt source 来自 `PlannerContext` 和 `planner_query`，不直接使用 teacher answer。

当前 DPO prompt source 只在本地保留，不进入公开仓库：

- `training/data/planner/dpo/prompts.jsonl`
- `training/data/planner/dpo/prompt_source/records.jsonl`

公开仓库只保留 DPO 口径和轻量说明。pair 构造、judge、prompt source 和训练产物仍按本地实验资产处理；当前公开参考为 `docs/后训练产物/03_DPO阶段/README.md`、`docs/后训练产物/04_Rerank阶段/README.md`、`scripts/planner/README.md` 和 `scripts/planner/bestofn/README.md`。单生成最佳点是 `260519 checkpoint-138`；最终展示版本是 `260521 checkpoint-64 rerank n4`。

## 不上传的内容

这些内容是本地实验资产，不进入 GitHub：

- 历史数据和脚本
- 废弃 prompt 消融归档
- 推进记录、踩坑记录、面试速记、作者交流、会话记忆和临时 HTML
- `training/outputs/` 下的大规模 generations、日志和模型输出明细
- `training/data/planner/archive/` 和 `training/data/llamafactory/archive/`
- LoRA 权重、checkpoint、`.safetensors`、`.pt`、`.bin`
- `.venv-training-py311/`、`.uv-cache/` 等本地环境
