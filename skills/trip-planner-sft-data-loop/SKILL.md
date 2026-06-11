---
name: trip-planner-sft-data-loop
description: 当用户要为 helloagents-trip-planner 生成一轮 Planner realbudget SFT 数据，并按项目最小验收流程判断这轮数据是否可以扩量、修复或作为训练候选时使用；覆盖 controlled/budget_supplement 请求分布检查、PlannerContext smoke、小批量生成、预算审计、可用性分类、样本预览、导出校验和训练前 handoff。
---

# Trip Planner SFT Data Loop

## 职责范围

本 skill 用于旅行助手项目的 Planner realbudget SFT 数据流程，关注对象是一轮数据 run，而不是整个模型训练项目。

它指导智能体按仓库已有脚本和 Planner 数据口径完成数据生成前检查、小批量生成、最小验收和下一步判断。生成一批数据后，不只看是否成功写出 records，还要检查预算、候选池、teacher 输出、样本可用性和导出格式。

本 skill 不替代仓库脚本，也不重新定义 Planner 数据口径。它只负责告诉智能体：当前场景该运行哪些已有脚本，运行前后要检查什么，哪些输出可以作为继续扩量、修复或进入训练候选的依据。


## 不负责的范围

- 不负责启动模型训练、恢复训练、checkpoint 选择或训练日志诊断；但当数据 loop 已完成时，可以给出训练前 handoff 建议。
- 不负责 standard/hard eval 跑分、跨模型对比或 checkpoint 效果归因。
- 不负责 DPO prompt、candidate、judge、pair 构造或 DPO 训练。
- 不负责 PlannerContext 协议、TripPlan schema、后端 planner 逻辑或前端请求字段改造。
- 如果发现票价表、候选池或 PlannerContext 问题阻塞本轮数据生成，只做定位和记录；需要结构性改造时，让用户确认。

## 硬规则

- Planner SFT 原始生成 run 必须写入 `training/data/planner/sft/` 下带日期和 run slug 的独立目录。
- 当前 skill 只处理当前 Planner SFT run；不默认做跨口径合并。
- smoke 数据没有经过人工预览和最小验收前，不要直接扩到 100 或 1000 条。
- 不要只用生成成功数判断数据可用；至少要结合人工预览、预算审计、可用性分类和导出校验。
- 外部 API 调用要遵守用户给定的 QPS、并发和成本边界；未确认限流保护前不要盲目提高并发。
- `budget_supplement` 预算利用型补数必须沿用真实预算分档，不允许通过单独平移 comfortable/premium 预算表来提高表面通过率。
- 需要精确 comfortable/premium 样本数时，按预算档位分别跑 `--target-successes`；不要依赖混合生成后的自然成功分布。
- 高德 QPS limiter 只约束单个造数进程内的 HTTP cache miss 请求；并发扩量前要确认 cache/API 行为，不要同时开多个生成进程叠加打高德。

## 开始前检查

- 确认当前工作目录是 `helloagents-trip-planner` 项目根目录。
- 先查看 `git status --short`，不要改动无关的用户文件。
- 明确本轮目标是 dry-run、context smoke、smoke20、100 条、1000 条，还是只做审计/校验。
- 明确本轮 `request_source`：`controlled`、`budget_supplement` 或其他；如果是 `budget_supplement`，先确认真实预算表、目标预算档位/strictness 配比和是否需要精确分档计数。
- 明确输出目录，并确认原始生成 run 位于 `training/data/planner/sft/` 下带日期和 run slug 的独立目录。
- 涉及外部 API 的步骤开始前，如果用户未提供高德 API、强模型 API 的 QPS/并发限制和成本边界，先确认后再运行；据此选择 `--workers`、批量大小和是否先做 smoke。已知高德 API 按 3 QPS 保守处理，未确认限流保护前不要盲目提高并发。


## 默认流程

除非用户明确要求只做其中某一步，否则按这个顺序执行：

1. 请求分布 dry-run：先检查本轮请求分布、预算档位、天数、同行类型是否符合预期，不调用外部 API。
2. PlannerContext smoke：小规模构建上下文，检查高德候选、天气、酒店、餐饮、价格 hint 和 budget_fit_policy 是否正常。
3. 小批量生成：先生成 smoke20 或用户指定的小批量数据，输出到新的显式 run 目录。
4. 样本预览和人工检查：把 smoke 数据转成可读预览，先和用户一起看成功样本、失败样本和典型输出，判断 teacher 质量、行程合理性、风格、grounding、餐饮、酒店连续性和预算直觉是否有明显问题。
5. 预算和可用性审计：在人工预览没有明显系统性问题后，再运行 budget fit audit 和 usability classification。若用户明确要求自动完成最小验收，先生成预览文件并汇报重点，再继续审计。
6. 导出与校验：检查 LLaMAFactory train/val 文件和 TripPlan schema 校验结果。
7. 下一步判断：根据人工检查、审计和校验结论，建议扩量、修复、重生成或停止。

## Reference 文件

本 skill 的正文只保留流程和红线。具体命令、参数解释和结果解读放在 reference 文件中，按需读取。

- 需要检查请求分布、PlannerContext smoke、生成 smoke20/100/1000 数据，或选择 `--workers`、输出目录、API 并发策略时，读取 `references/data_generation.md`。
- 需要运行 budget fit audit、usability classification，或解释 `summary.json`、`audit_rows.jsonl`、分类 ID 列表时，读取 `references/audit_and_classification.md`。
- 需要把样本转成可读预览、组织人工检查、检查 LLaMAFactory train/val 文件、运行 TripPlan schema 校验，或整理最终结论时，读取 `references/export_and_validation.md`。
- 数据已经通过审计/校验，用户开始问“怎么进训练”“要不要混旧数据”“从 checkpoint 继续还是重训”“会不会爆盘”时，读取 `references/training_handoff.md`。


## 汇报格式

完成一轮数据 loop 或其中一个阶段后，汇报应优先帮助用户判断下一步，而不是只罗列命令输出。

至少包含：

- 本轮目标：dry-run、context smoke、smoke20、100 条、1000 条，还是审计/校验。
- 数据目录、审计目录和主要产物路径。
- 成功/失败样本数，以及主要失败类型。
- 人工预览结论：teacher 输出质量、行程合理性、grounding、餐饮、酒店连续性、预算直觉是否有明显系统性问题。
- 审计结论：请求预算、teacher budget、候选池可达性、可用性分类数量。
- 校验结论：LLaMAFactory 文件是否存在，TripPlan schema 是否通过。
- 下一步建议：扩量、先修复、重生成、只保留非预算样本，或停止。
- 需要用户人工确认的样本 ID、风险点或并发/成本选择。
