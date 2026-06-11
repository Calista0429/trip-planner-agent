# Compare And Report

## 目录

- Slice 对比
- LLM judge
- pairwise judge
- Relaxed grounding 审计
- 报告包
- full report
- 中文摘要结构

## Slice 对比

standard 与 hard 分开跑 slice，不要混用 records：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/eval_slice_report.py \
  --records training/data/planner/eval/records.jsonl \
  --model-report base=training/outputs/eval/by_model/base_qwen25_7b/260511_high_end_context_standard_w10/rule_eval_report.json \
  --model-report legacy_b=training/outputs/eval/by_model/sft_qwen25_7b_planner_1000_cp2_legacy_b/260511_high_end_context_standard_w10/rule_eval_report.json \
  --model-report lr8e5=training/outputs/eval/by_model/sft_qwen25_7b_planner_260509_main_clean_cp2_legacy_b_valloss_lr8e5/260511_high_end_context_standard_w10/rule_eval_report.json \
  --output-dir training/outputs/eval/comparisons/260511_<comparison_slug>_standard
```

hard split 示例：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/eval_slice_report.py \
  --records training/data/planner/eval_hard/records.jsonl \
  --model-report base=training/outputs/eval/by_model/base_qwen25_7b/260511_high_end_context_hard_w10/rule_eval_report.json \
  --model-report legacy_b=training/outputs/eval/by_model/sft_qwen25_7b_planner_1000_cp2_legacy_b/260511_high_end_context_hard_w10/rule_eval_report.json \
  --model-report lr8e5=training/outputs/eval/by_model/sft_qwen25_7b_planner_260509_main_clean_cp2_legacy_b_valloss_lr8e5/260511_high_end_context_hard_w10/rule_eval_report.json \
  --output-dir training/outputs/eval/comparisons/260511_<comparison_slug>_hard
```

Slice 报告默认产物：

- `slice_report.json`
- `slice_report.md`

重点看 `budget_level`、`travel_days`、`companion_type`、`city_tier`、`weather_bucket`。如果总体指标相近，优先用切片确认是否只在 hard / premium / 多人多天样本上退化。

## LLM judge

只有当规则指标不足以判断合法方案的旅行质量时才跑 judge。它依赖 `training/scripts/shared/llm_client.py` 的环境变量配置，并可能产生外部 API 成本。

单模型 judge：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/eval_llm_judge.py \
  --records training/data/planner/eval/records.jsonl \
  --generations training/outputs/eval/by_model/<model_family>/<YYMMDD>_<run_slug>/generations.jsonl \
  --model-name <YYMMDD>_<run_slug> \
  --output-dir training/outputs/eval/by_model/<model_family> \
  --workers 4 \
  --resume
```

失败重试：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/eval_llm_judge.py \
  --records <records> \
  --generations <generations.jsonl> \
  --model-name <YYMMDD>_<run_slug> \
  --output-dir training/outputs/eval/by_model/<model_family> \
  --workers 4 \
  --resume \
  --retry-failed
```

生成可读 dashboard：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/eval_judge_report.py \
  --records <records> \
  --generations <generations.jsonl> \
  --run-dir training/outputs/eval/by_model/<model_family>/<YYMMDD>_<run_slug>
```

## pairwise judge

用于 DPO 或 checkpoint 之间“都合法但哪个好”的判断。先确认两个 generations 来自同一个 records 文件。

```bash
.venv-training-py311/bin/python3 training/scripts/eval/eval_pairwise_judge.py \
  --records training/data/planner/eval_hard/records.jsonl \
  --left-generations training/outputs/eval/by_model/base_qwen25_7b/260511_high_end_context_hard_w10/generations.jsonl \
  --right-generations training/outputs/eval/by_model/<candidate_family>/<YYMMDD>_<candidate_hard_slug>/generations.jsonl \
  --left-label base \
  --right-label candidate \
  --output-dir training/outputs/eval/comparisons/<YYMMDD>_<comparison_slug> \
  --workers 4 \
  --resume
```

输出：

- `pairwise_<left>_vs_<right>.jsonl`
- `pairwise_<left>_vs_<right>_summary.json`
- `pairwise_<left>_vs_<right>_summary.md`

在 slice 报告中使用 pairwise 结果时，传 `--pairwise` 和 `--pairwise-win-label`。

## Relaxed grounding 审计

当 strict grounding 失败看起来像名称归一化误伤时，跑 side-channel 审计：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/eval/audit_relaxed_grounding.py \
  --report standard/base=training/outputs/eval/by_model/base_qwen25_7b/260511_high_end_context_standard_w10/rule_eval_report.json \
  --report standard/candidate=training/outputs/eval/by_model/<candidate_family>/<candidate_standard_slug>/rule_eval_report.json \
  --report hard/base=training/outputs/eval/by_model/base_qwen25_7b/260511_high_end_context_hard_w10/rule_eval_report.json \
  --report hard/candidate=training/outputs/eval/by_model/<candidate_family>/<candidate_hard_slug>/rule_eval_report.json \
  --output-dir training/outputs/eval/audits/<YYMMDD>_<audit_slug> \
  --example-limit 10
```

审计会输出：

- `relaxed_grounding_audit.json`
- `relaxed_grounding_audit.md`

注意：relaxed audit 不修改 `rule_eval_report.json`，也不改变官方 hardpass。它只回答“严格匹配错杀了多少”的诊断问题。

## 报告包

最终给人看的主报告优先做成单文件 full report，格式见 `full_report_format.md`。需要提交或分享精简版时，再整理到：

```text
training/outputs/eval/reports/<YYMMDD>_<report_slug>/
```

建议包含：

- `README.md`：文件说明、模型角色、提交边界。
- `<comparison_slug>_full_report.md`：主结论和完整指标表；若目录名较长，文件名保持和目录 slug 一致。
- `中文结果摘要.md`：可选精简摘要，不替代 full report。
- `mainline_comparison.md` 和 `mainline_comparison.json`：结构化横评摘要；没有专用脚本时可由 rule report 汇总后手写。
- `slice_standard.md/json` 与 `slice_hard.md/json`。
- `relaxed_grounding_audit.md`：如果本轮跑了该审计。

不要放入：

- `generations.jsonl`
- 完整 `rule_eval_report.json`
- vLLM/LLaMAFactory 服务日志
- 大体积 audit 原始 JSONL

## full report

人读主报告默认写成一份完整 Markdown，位置优先使用：

```text
training/outputs/eval/comparisons/<YYMMDD>_<comparison_slug>/<comparison_slug>_full_report.md
```

如果这一轮已经归档或需要对外提交，可以把同一份 Markdown 复制或精简到：

```text
training/outputs/eval/reports/<YYMMDD>_<report_slug>/<comparison_slug>_full_report.md
```

报告结构、标题、元信息、合并视图、分 split 视图和读数建议见 `full_report_format.md`。不要只输出分散的 slice report 或简短中文摘要作为最终报告。

优先用脚本生成：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/eval/generate_full_report.py \
  --current-label candidate \
  --primary-label legacy_b \
  --baseline-label baseline \
  --title "Candidate vs legacy_b / Baseline 全量评估报告" \
  --standard-records training/data/planner/eval/records.jsonl \
  --hard-records training/data/planner/eval_hard/records.jsonl \
  --report standard/candidate=training/outputs/eval/by_model/<candidate_family>/<candidate_standard_slug>/rule_eval_report.json \
  --report hard/candidate=training/outputs/eval/by_model/<candidate_family>/<candidate_hard_slug>/rule_eval_report.json \
  --report standard/legacy_b=training/outputs/eval/by_model/sft_qwen25_7b_planner_1000_cp2_legacy_b/260511_high_end_context_standard_w10/rule_eval_report.json \
  --report hard/legacy_b=training/outputs/eval/by_model/sft_qwen25_7b_planner_1000_cp2_legacy_b/260511_high_end_context_hard_w10/rule_eval_report.json \
  --report standard/baseline=training/outputs/eval/by_model/base_qwen25_7b/260511_high_end_context_standard_w10/rule_eval_report.json \
  --report hard/baseline=training/outputs/eval/by_model/base_qwen25_7b/260511_high_end_context_hard_w10/rule_eval_report.json \
  --output-dir training/outputs/eval/comparisons/<YYMMDD>_<comparison_slug> \
  --comparison-slug <comparison_slug>
```

常用可选项：

- `--primary-label label`：指定总结中的主要强对照；不要让脚本靠 `--report` 顺序猜。
- `--baseline-label label`：指定 baseline 对照；默认按 `base` / `baseline` 名称推断。
- 表格列顺序会按“当前候选、primary、其他对照、baseline”重排。
- `--model-note label=说明`：覆盖顶部元信息里的对照版本说明。
- `--inference-note "..."`：写明服务、GPU、workers、分片和生成健康情况；不知道时不要编。
- `--rule-note "..."`：写明本轮规则口径，例如 `meal_cost_scale_ok` 是否排除早餐。
- `--summary-note "..."`：在自动总结中追加一段人工判断。
- `--output-json path`：额外输出机器可读汇总。

脚本默认会校验每个 `rule_eval_report.json.records_path` 是否匹配对应的 `--standard-records` / `--hard-records`。只有核对历史归档且确认口径风险可接受时，才使用 `--allow-records-mismatch`。

## 中文摘要结构

推荐结构：

1. 总体判断：当前主线是谁，历史强对照如何定位。
2. Hard Pass 展开：standard 与 hard 分表，看 JSON/schema/date/weather/grounding/住宿/餐饮/位置对象/交通预算。
3. Soft Pass 展开：景点多样性、餐饮多样性、预算偏好、重算预算版 softpass。
4. 预算展开：不超预算、预算偏好、重算预算贴合、预算结构关系、精确账本诊断。
5. Grounding 审计：strict 与 relaxed 是否有差异，是否存在 evaluator false negative。
6. 切片风险：指出 premium、多人、多天、特定天气或住宿类型上的退化。
7. 下一步：继续训练、选 checkpoint、重跑 hard、做 pairwise、改召回或修评估口径。
