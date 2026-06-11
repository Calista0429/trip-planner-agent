# Audit And Classification

这份参考用于指导 Planner realbudget SFT records 的完整 records 审计和可用性分类。它通常在 smoke 数据已经完成样本预览、且没有明显系统性 teacher 质量问题之后使用。

它不负责生成数据，也不负责人工预览；它负责用项目脚本检查请求预算、teacher budget、候选池可达性，并把样本分成可用、可修、仅非预算可用或应丢弃等类别。

## 什么时候读取

- 用户要求审计一批 Planner realbudget SFT records。
- smoke20 人工预览后，需要做完整 records audit。
- 100 / 1000 条生成后，需要判断哪些样本可进入训练候选池。
- 用户问“这批数据里哪些能用、哪些要修、哪些该丢”。
- 用户已经有 `records.jsonl`，需要生成 `audit_rows.jsonl`、`summary.json`、分类 ID 列表和审计报告。

## 审计输入和输出目录

输入通常是某个生成 run 的 `records.jsonl`：

```text
training/data/planner/sft/<YYMMDD>_<run_slug>/records.jsonl
```

审计输出应写入 `training/outputs/eval/audits/` 下的新目录。

推荐一轮生成 run 对应一个 records audit 总目录，再按审计类型拆子目录：

```text
training/outputs/eval/audits/<YYMMDD>_<run_slug>_records_audit/
training/outputs/eval/audits/<YYMMDD>_<run_slug>_records_audit/budget_fit/
training/outputs/eval/audits/<YYMMDD>_<run_slug>_records_audit/usability/
training/outputs/eval/audits/<YYMMDD>_<run_slug>_records_audit/previews/
training/outputs/eval/audits/<YYMMDD>_<run_slug>_records_audit/export_validation/
```

如果项目当前脚本或历史产物已经使用更短目录，也可以沿用：

```text
training/outputs/eval/audits/<YYMMDD>_<run_slug>/budget_fit/
training/outputs/eval/audits/<YYMMDD>_<run_slug>/usability/
training/outputs/eval/audits/<YYMMDD>_<run_slug>/previews/
training/outputs/eval/audits/<YYMMDD>_<run_slug>/export_validation/
```

后文用 `<audit_root>` 指代同一轮 run 的审计根目录。可以是 `<YYMMDD>_<run_slug>_records_audit/`，也可以是项目已经采用的 `<YYMMDD>_<run_slug>/`；同一轮内保持一致即可。

示例：

```text
training/outputs/eval/audits/260510_smoke20_main_records_audit/budget_fit/
training/outputs/eval/audits/260510_smoke20_main_records_audit/usability/
training/outputs/eval/audits/260510_validate100_main_records_audit/budget_fit/
training/outputs/eval/audits/260510_validate100_main_records_audit/usability/
```

目录分工：

- `records_audit/`：保存这一轮 records 的所有审计、分类、预览和导出校验派生产物。
- `budget_fit/`：保存基础 records 审计产物，例如 `audit_rows.jsonl`、`summary.json`、`sft_budget_fit_audit.md`。
- `usability/`：保存可用性分类产物，例如 `record_classification.jsonl`、`record_classification.csv`、分类 ID 列表、`summary.json`、`sft_budget_usability_audit.md`。
- `previews/`：保存人工预览用样本、抽样说明或人工检查记录。
- `export_validation/`：保存导出训练格式后的校验结果。

不要把审计产物写回原始生成 run 目录，避免混淆“原始数据”和“审计派生产物”。不要在同一轮中混用两个 audit root。


## full records audit

使用脚本：`training/scripts/planner/audit/audit_sft_budget_fit.py`

用途：对一批 Planner realbudget SFT records 做第一轮系统审计。虽然脚本名包含 `budget_fit`，但在本 skill 中它代表整批 records 的基础审计：请求预算、teacher budget、候选池预算可达性、餐饮候选数量，以及按预算档位和 strictness 的问题分布。

输入：

```text
training/data/planner/sft/<YYMMDD>_<run_slug>/records.jsonl
```

输出：

```text
training/outputs/eval/audits/<audit_root>/budget_fit/
```

示例命令：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/audit/audit_sft_budget_fit.py \
  --records training/data/planner/sft/<YYMMDD>_<run_slug>/records.jsonl \
  --output-dir training/outputs/eval/audits/<audit_root>/budget_fit
```

运行要求：

- 必须显式传入 `--records` 和 `--output-dir`；脚本不提供历史默认路径。
- `--records` 必须来自本轮生成 run 的 `records.jsonl`。
- `--output-dir` 必须写到同一轮 run 的 `<audit_root>/budget_fit/`。

主要产物：

- `audit_rows.jsonl`：逐样本审计行，后续 classification 的输入。
- `summary.json`：聚合统计。
- `sft_budget_fit_audit.md`：可读审计报告。

运行后重点看：

- 总样本数和异常规模。
- `request_budget_status`：请求预算是否符合当前预算分档。
- `teacher_budget_status`：teacher 预算是否落在目标区间。
- `candidate_reach_amount`：候选池高配估算是否能支撑用户预算。
- `food_pois_zero`：是否存在餐饮候选为空。
- 按 `budget_level`、`strictness`、城市、天数等切片是否有集中问题。
- 是否有某类样本系统性不适合继续进入训练候选池。

如果整批数据出现大面积异常，不要直接进入训练候选池；先定位是请求分布问题、teacher 生成问题、候选池可达性问题，还是某个预算档位/strictness 切片的问题。


## usability classification

使用脚本：`training/scripts/planner/audit/classify_sft_budget_usability.py`

用途：读取 full records audit 生成的 `audit_rows.jsonl`，把每条 record 切分成可直接使用、谨慎使用、需要修复、仅非预算可用或应淘汰/重做等类别。这个步骤不修改原始 `records.jsonl`，只生成分类派生产物和 ID 列表。

输入：`training/outputs/eval/audits/<audit_root>/budget_fit/audit_rows.jsonl`

输出：`training/outputs/eval/audits/<audit_root>/usability/`

运行要求：

- 必须显式传入 `--audit-rows` 和 `--output-dir`；脚本不提供历史默认路径。
- `--audit-rows` 必须来自同一轮 run 的 `<audit_root>/budget_fit/audit_rows.jsonl`。
- `--output-dir` 必须写到同一轮 run 的 `<audit_root>/usability/`。

示例命令：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/audit/classify_sft_budget_usability.py \
  --audit-rows training/outputs/eval/audits/<audit_root>/budget_fit/audit_rows.jsonl \
  --output-dir training/outputs/eval/audits/<audit_root>/usability
```

主要产物：

- `record_classification.jsonl`：逐样本分类、决策和原因。
- `record_classification.csv`：同内容表格版，便于人工筛选。
- `summary.json`：分类聚合统计。
- `sft_budget_usability_audit.md`：可读分类报告。
- `*_ids.txt`：按分类拆出的 record_id 列表，可用于后续抽样、修复或导出。

## 分类结果怎么看

分类完成后，优先看 `sft_budget_usability_audit.md` 和 `summary.json`，再按需要打开 `record_classification.csv` 做表格筛选。

读取顺序：

- 先看 `summary.json`：确认总样本数、各 category 数量和比例。
- 再看 `sft_budget_usability_audit.md`：检查按 `budget_level`、`strictness` 的切片分布，以及报告里的样本示例。
- 最后看 `record_classification.csv`：按 `record_id`、城市、预算档位、strictness、category 和 reason 做人工抽查。
- 需要抽样、修复或导出时，再使用 `*_ids.txt` 里的分类 ID 列表。

主要类别：

- `usable_budget_clean`：预算主集可用。请求预算符合当前预算分档，teacher budget 落在目标区间，候选池高配预算可达请求金额。
- `usable_budget_candidate_tight`：预算可用但候选偏紧。请求和 teacher 都合格，但候选池高配估算低于请求金额；不要和完全干净样本混成同一口径。
- `repair_request_rebudget`：需重标请求预算。teacher 能贴合原目标，但 amount/free_text 和当前预算分档不一致。
- `repair_teacher_regen`：需重生成 teacher。请求预算合理，但 teacher budget 明显偏低。
- `nonbudget_only`：仅适合非预算 SFT。通常是没有明确预算目标区间的样本，不进入预算训练主集。
- `drop_or_full_regen`：预算训练淘汰或整条重做。请求预算和 teacher budget 至少两侧不匹配，不建议直接进入训练候选池。

不要只看总通过率。若某个 `budget_level` 或 `strictness` 集中进入 `repair_teacher_regen`、`repair_request_rebudget` 或 `drop_or_full_regen`，应把它视为一个切片问题，而不是简单把坏样本过滤掉。

## 决策建议

本节只给出数据 loop 的下一步建议，不直接决定训练。训练是否启动仍要结合导出校验、用户目标和训练配置确认。

对 smoke20：

- 如果人工预览正常，`usable_budget_clean` 占比高，且没有集中 API / 候选池 / teacher 失败，可以进入 100 条验证生成。
- 如果 `repair_teacher_regen` 集中，优先检查 teacher prompt、模型 provider、输出截断和预算约束，不要直接扩量。
- 如果 `repair_request_rebudget` 集中，优先检查请求生成的预算金额、free_text 和结构化 budget 字段是否一致。
- 如果 `drop_or_full_regen` 较多，先回到生成阶段定位系统性问题；smoke20 不是靠过滤坏样本来“凑通过”的阶段。

对 100 条验证：

- 如果分类分布和人工预览都稳定，可以建议进入 1000 条主生成。
- 如果只有少量 `usable_budget_candidate_tight`，可以保留为单独观察子集，但不要把它和 `usable_budget_clean` 混成同一主集口径。
- 如果某个预算档位、strictness、城市或天数切片明显坏掉，先修该切片，再重新跑 100 条验证。
- 如果强模型 provider 发生变化，例如从 deepseek 切到 mimo，必须重新从 smoke 开始判断，不要沿用上一 provider 的分类结论直接扩量。

对 1000 条主生成：

- `usable_budget_clean` 是预算主训练候选。
- `usable_budget_candidate_tight` 只能作为谨慎使用或单独分析子集，是否导出给用户确认。
- `repair_request_rebudget` 和 `repair_teacher_regen` 进入修复队列，不直接导出训练。
- `nonbudget_only` 不进入预算训练主集；如用户需要非预算 schema/grounding 训练，再单独确认。
- `drop_or_full_regen` 不进入训练候选池。

## 常见风险

- 审计和分类使用的 `records.jsonl` 不是同一轮 run，导致 `record_id` 对不上。
- 审计或分类命令误传其他 run 的 `records.jsonl` / `audit_rows.jsonl`。
- 只看 `usable_budget_clean` 总数，不看 `budget_level`、`strictness` 等切片分布。
- 把 `usable_budget_candidate_tight` 当成完全干净样本，训练出“预算不可达但仍承诺满足”的行为。
- smoke20 分类勉强可用时直接扩到 1000，放大 teacher 或候选池系统性问题。
- 切换 teacher provider 后不重新做 smoke，混淆不同 provider 的质量和成本结论。
- 把审计派生产物写回原始生成 run 目录，导致后续导出时混淆原始数据和派生数据。
