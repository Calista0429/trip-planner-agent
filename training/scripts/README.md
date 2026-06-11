# Training Scripts Index

更新时间：2026-05-12

这个目录只放当前还可能直接运行的训练、服务、校验入口。旧实验脚本默认作为本地参考或归档资产处理，不作为公开主线入口。

## 目录结构

| Path | Purpose |
| --- | --- |
| `shared/` | JSONL、路径、环境变量、LLM 客户端等公共 helper |
| `serving/` | 本地 Planner 模型服务启动、停止和 LLaMA-Factory API 配置生成 |
| `validation/` | SFT/DPO/Eval 输出 schema 校验 |
| `planner/data/` | SFT/realbudget 数据生成、预览和清洗导出 |
| `planner/pricing/` | 景点候选收集、票价分桶和强模型估价 |
| `planner/eval/` | frozen eval 构建、prompt/context 刷新和预算修正实验 |
| `planner/audit/` | SFT 预算贴合度、上下文可达性和可用性审计 |
| `planner/training/` | 本地训练启动/恢复脚本 |
| `planner/bestofn/` | 多候选采样、规则 reward 选择和偏好/SFT 数据导出 |
| `archive/` | legacy helper 和实验脚本归档，公开仓库默认忽略 |

## 当前入口

| Script | Purpose |
| --- | --- |
| `planner/data/generate_sft_data.py` | SFT / realbudget 数据生成、request dry-run 和 PlannerContext smoke |
| `planner/eval/build_eval_set.py` | 构建 standard / hard frozen eval 输入 |
| `planner/eval/rebuild_eval_contexts.py` | 保留 request 与 record id，按当前后端重建 eval context |
| `planner/eval/generate_full_report.py` | 汇总评测指标并生成报告 |
| `planner/audit/audit_sft_budget_fit.py` | SFT 预算贴合度审计 |
| `planner/audit/classify_sft_budget_usability.py` | SFT 预算可用性分类 |
| `planner/pricing/collect_attraction_candidates.py` | 从 PlannerContext 收集景点候选，用于票价表补全 |
| `planner/pricing/estimate_attraction_prices_with_llm.py` | 高频景点票价估算，只用于训练预算口径 |
| `planner/bestofn/` | Best-of-N prompt、候选生成、review 和选择流程 |
| `serving/serve_planner_model.py` | 启动本地 OpenAI-compatible Planner 推理服务，用于 base/SFT/DPO/SFT+DPO 结果对比 |
| `serving/manage_planner_service.py` | 管理本地 Planner 模型服务 |
| `validation/validate_trip_plan.py` | 校验 SFT/DPO/Eval JSONL 是否符合后端 `TripPlan` schema |

## 共享 helper

| Script | Purpose |
| --- | --- |
| `shared/common.py` | JSONL、路径、环境变量、日期等通用工具；旧数据目录常量使用前需要确认语义 |
| `shared/llm_client.py` | DeepSeek/OpenAI-compatible 数据生成客户端；可作为强模型生成和 judge 的基础封装 |

## 旧规则

旧脚本只作为工程参考或本地 helper，不要直接复用旧产物作为当前训练数据。新增能力优先放入当前脚本分组，并同步更新 `training/README.md`、`training/STRUCTURE.md` 和这份 README。
