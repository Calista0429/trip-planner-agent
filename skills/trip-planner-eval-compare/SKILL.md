---
name: trip-planner-eval-compare
description: 当用户要在 helloagents-trip-planner 中运行、复核或对比 Planner standard/hard eval 时使用；覆盖 base/SFT/DPO/checkpoint 单模型评测、已有 generations 的 rule eval 重算、跨模型同口径对比、slice 报告、relaxed grounding 审计、可选 LLM judge/pairwise judge、报告包整理，以及判断 checkpoint 是否真的变好。
---

# Trip Planner Eval Compare

## 职责范围

本 skill 用于旅行助手项目的 Planner 模型评估流程。关注对象是冻结 eval records 上的一组模型输出，而不是训练过程或数据生成过程。

它指导智能体使用仓库已有脚本完成单模型生成、规则评估、standard/hard 横向对比、诊断审计和结论汇报。不要复制评估脚本逻辑到 skill；脚本仍以 `training/scripts/` 为唯一实现来源。

## 不负责的范围

- 不负责启动、恢复或诊断训练任务。
- 不默认启动或停止 vLLM/LLaMAFactory 服务；只有用户明确要求或已给出端口、checkpoint、GPU 边界时才处理模型服务。
- 不负责构建或重建 eval records；若 records/context 已变更，只做口径检查并提醒同轮横评必须全部重跑。
- 不负责 SFT 数据生成、预算可用性分类或导出训练集；这些属于 `trip-planner-sft-data-loop`。

## 硬规则

- 先确认工作目录是项目根目录，并查看 `git status --short`。
- Planner 主评估集固定为 `training/data/planner/eval/records.jsonl` 和 `training/data/planner/eval_hard/records.jsonl`，除非用户明确指定历史对照集。
- 每轮横评必须使用同一个 records 文件、同一个 context 版本和同一套 rule eval 脚本；不要把旧 context、新 context、`current_*`、`realbudget_*`、`standard200_*` 等不同输入集混成一张胜负表。
- 单模型产物放在 `training/outputs/eval/by_model/<model_family>/<YYMMDD>_<run_slug>/`。调用脚本时通常传 `--output-dir training/outputs/eval/by_model/<model_family>`，传 `--model-name <YYMMDD>_<run_slug>`。
- 跨模型产物放在 `training/outputs/eval/comparisons/<YYMMDD>_<comparison_slug>/`。
- 诊断审计产物放在 `training/outputs/eval/audits/<YYMMDD>_<audit_slug>/`。
- 可提交或分享的精简报告放在 `training/outputs/eval/reports/<YYMMDD>_<report_slug>/`，不要把 `generations.jsonl`、完整 `rule_eval_report.json`、服务日志或大体积本地产物放进 reports。
- 使用外部强模型 judge 或 pairwise judge 前，确认 API 环境、并发和成本边界；不确定时先跑 `--limit` smoke。

## 开始前检查

- 明确任务类型：单模型 standard/hard 评测、只重跑 rule eval、跨模型对比、relaxed grounding 审计、LLM judge、pairwise judge、报告打包，还是只解释已有报告。
- 明确模型角色：`base`、历史强对照、当前 checkpoint、DPO 候选等。旧数据路线历史最好版本只能作 reference，不要直接替代当前主线候选。
- 检查 records 行数和 `record_id` 前缀：standard 应为 200 条且前缀 `planner_standard200_realbudget_eval_`；hard 应为 300 条且前缀 `planner_hard_realbudget_eval_`。
- 检查每个待比较 run 的 `generation_config.json`、`rule_eval_report.json` 中 `records` / `records_path` 是否指向同一个 records 文件。
- 检查 `generations.jsonl` 中失败调用、重复 record、`finish_reason=length` 或空输出；这些会影响 rule eval 分母和结论可信度。

## 默认流程

除非用户只要求其中一步，否则按这个顺序执行：

1. 做口径预检：确认 records、输出目录、模型角色、base URL、workers、是否需要 `--limit` smoke。
2. 单模型生成和规则评估：standard 与 hard 分开跑，优先用 `eval_pipeline.py` 串联生成和 rule eval；已有 generations 时只跑 `eval_rule_metrics.py`。
3. 读取规则报告：先看 call/json/schema 分母，再看 hardpass、softpass、预算、grounding、餐饮多样性和截断情况。
4. 横向对比：对每个 split 分别跑 `eval_slice_report.py`；需要偏好判断时再跑 LLM judge 或 pairwise judge。
5. 诊断支线：怀疑 strict grounding 误伤时跑 relaxed grounding audit；它只做 side-channel 估计，不改官方 hardpass。
6. 形成报告：最终给人看的默认产物是一份 full report Markdown；优先用 `training/scripts/planner/eval/generate_full_report.py` 生成，格式校验参考 `references/full_report_format.md`；必要时再把精简副本整理到 `reports/<YYMMDD>_<slug>/`。

## Reference 文件

- 需要跑单模型生成、重跑 rule eval、检查 records 或 generations 时，读取 `references/run_eval.md`。
- 需要做跨模型 slice、LLM judge、pairwise judge、relaxed grounding 或报告打包时，读取 `references/compare_and_report.md`。
- 需要产出最终给人看的全量评估报告时，读取 `references/full_report_format.md`。
- 需要解释 hardpass/softpass、预算、grounding 指标或判断 checkpoint 是否变好时，读取 `references/metrics_and_decision.md`。

## 汇报格式

完成一次评估或对比后，汇报要帮助用户做下一步判断，而不是只贴命令输出。

至少包含：

- 评估对象：模型角色、run 目录、standard/hard records 路径。
- 口径检查：records 是否一致、context 是否同轮、生成是否有失败/截断。
- 主要结论：hardpass、softpass、预算选择/重算预算、grounding、餐饮多样性和主要退化点。
- 横向判断：相对 base、历史强对照、上一 checkpoint 的提升/退化；明确哪些是当前主线，哪些只是 reference。
- 主要产物：full report、`generations.jsonl`、`rule_eval_report.md/json`、slice、audit、reports 的路径。
- 下一步建议：继续训练、改数据/召回、重跑 eval、做 pairwise judge、进入 DPO，或先修复评估口径。
