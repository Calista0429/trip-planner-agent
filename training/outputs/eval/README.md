# Eval Outputs

更新时间：2026-05-12

当前 eval 输出按模型和 run 时间组织。新结果请不要再直接写在本目录第一层。

## 目录约定

- `by_model/<model>/<YYMMDD>_<run_slug>/`: 单模型评估结果，包含 `generations.jsonl`、`rule_eval_report.*`、`generation_config.json` 等。
- `comparisons/<YYMMDD>_<comparison_slug>/`: 跨模型对比报告。
- `audits/<YYMMDD>_<audit_slug>/`: 数据/预算/teacher 审计，不属于单个模型。
- `logs/<YYMMDD>_<log_slug>/`: vLLM serve/generate 日志集合。
- `reports/<YYMMDD>_<report_slug>/`: 适合提交到 GitHub 的精简报告包，只包含 Markdown 和小体积指标 JSON。

`by_model/`、`comparisons/`、`audits/`、`logs/` 默认视为本地生成产物；需要公开的评估结论请整理到 `reports/` 后再提交。

## 时间戳

- run 文件夹必须以 `YYMMDD` 开头，例如 `260506_A_C_w10`。
- 如果原始名字里有 `20260506`，折叠为 `260506`；否则按文件修改时间推断。

## manifest

- `runs_manifest.json` 记录了本次整理的来源路径和目标路径。

## 当前报告

- `reports/260512_bestofn_replay_extended_w10/`: 2026-05-12 Best-of-N replay 扩展对比。包含最新 `final`、中间点 `ckpt96`/`ckpt192`、上一轮 `replay_usage700`、前序 `lr8e-5`、旧路线 `legacy_b` 与外部 Mimo reference 的 500 条合并/standard/hard 主要指标。当前结论：`final` 作为硬约束主线，`replay_usage700` 继续保留为预算偏好与 hard split softpass 对照，`lr8e-5` 保留为预算算术/重算预算贴合节点对照。
- `reports/260511_high_end_context_mainline/`: 高端 POI 上下文重构后三模型主线对比。包含中文摘要、Hard/Soft/Budget 展开、切片报告和 grounding 审计摘要。`legacy_b` 作为旧数据路线历史最好对照，`valloss_lr8e5` 作为当前新上下文/新数据路线候选。
- `comparisons/260510_planner_valloss_lr8e5_vs_legacy_b_prev_baseline_full_report/`: Planner main-clean lr8e-5 valloss 与上一轮、旧 legacy_b、baseline 的 500 条全量对比。当前选择 lr8e-5 valloss 作为继续迭代基准；旧 legacy_b 和 baseline 仅作为固定 reference。
- `by_model/base_qwen25_7b/260507_realbudget_*_w10/`: baseline reference 报告。
- `by_model/sft_qwen25_7b_planner_1000_cp2_legacy_b/260507_realbudget_*_w10/`: 旧 legacy_b reference 报告。
