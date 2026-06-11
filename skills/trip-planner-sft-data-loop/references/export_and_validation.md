# Export And Validation

这份参考用于指导 Planner SFT run 做样本预览、导出训练候选子集，并完成最小格式校验。

它不负责启动训练、不负责修改 LLaMAFactory 训练配置，也不负责根据训练结果归因；它只负责把 records 变成可人工检查的预览，把已审计 records 变成明确的训练候选文件，并确认这些文件能被当前 schema 校验脚本读过。

## 什么时候读取

- 用户要求把某轮 Planner SFT records 导出成训练候选数据。
- smoke20、100 条或 1000 条生成后，需要做人工预览。
- 用户要求校验 `llamafactory_train.json` / `llamafactory_val.json` 是否能训练前使用。
- usability classification 已经产出 `record_classification.jsonl`，需要按 category 导出子集。
- 用户问“这批数据能不能进训练前文件”。

## 输入和输出目录

输入通常来自同一轮 run 的两个位置：

```text
training/data/planner/sft/<YYMMDD>_<run_slug>/records.jsonl
training/outputs/eval/audits/<audit_root>/usability/record_classification.jsonl
```

导出结果应写到 `training/data/planner/sft/` 下新的、可识别的子目录；校验报告或命令输出记录应放到同一轮 `<audit_root>/export_validation/` 下。`<audit_root>` 应与审计和分类阶段一致，可以是 `<YYMMDD>_<run_slug>_records_audit/`，也可以是项目已经采用的 `<YYMMDD>_<run_slug>/`。

推荐目录：

```text
training/data/planner/sft/<YYMMDD>_<run_slug>_<category_slug>/
training/outputs/eval/audits/<audit_root>/export_validation/
```

示例：

```text
training/data/planner/sft/260510_main1000_budget_clean/
training/data/planner/sft/260510_main1000_candidate_tight/
training/outputs/eval/audits/260510_main1000_records_audit/export_validation/
```

不要覆盖原始生成 run 目录里的 `records.jsonl`、`requests.jsonl`、`errors.jsonl` 或 `llm_usage.jsonl`。

## 样本预览

使用脚本：`training/scripts/planner/data/preview_sft_records.py`

用途：把 `records.jsonl` 和 `errors.jsonl` 转成中文 Markdown，供用户人工检查 teacher 输出质量。预览不修改原始数据，也不代表样本已经通过审计。

示例命令：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/preview_sft_records.py \
  --records training/data/planner/sft/<YYMMDD>_<run_slug>/records.jsonl \
  --errors training/data/planner/sft/<YYMMDD>_<run_slug>/errors.jsonl \
  --output training/outputs/eval/audits/<audit_root>/previews/smoke_preview.md \
  --limit 20
```

运行要求：

- 必须显式传入 `--records`、`--errors` 和 `--output`；脚本不提供历史默认路径。
- `--records` 和 `--errors` 必须来自同一轮生成 run。
- `--output` 必须写到同一轮 `<audit_root>/previews/` 下。

人工预览重点：

- teacher 是否稳定输出合法 TripPlan JSON。
- 行程是否符合用户请求、天数、同行人、节奏和预算直觉。
- 景点、酒店、餐饮是否来自候选池，是否存在泛化占位。
- 酒店是否连续合理，最后一天是否仍有完整餐饮安排。
- 预算分项和总价是否大体可信，是否有明显低配或强行凑预算。
- `errors.jsonl` 是否暴露集中失败类型。

如果 smoke 预览发现系统性 teacher 问题，不要进入审计、导出或扩量；先回到生成阶段定位。

## 可导出的类别

默认只导出 `usable_budget_clean` 作为预算主训练候选。

其他类别的处理：

- `usable_budget_candidate_tight`：只能单独导出为观察或弱预算子集，必须在汇报中标注候选偏紧。
- `repair_request_rebudget`：不导出训练；先修请求预算。
- `repair_teacher_regen`：不导出训练；先重生成 teacher。
- `nonbudget_only`：不进入预算训练主集；如用户明确需要非预算训练，再另起导出目录。
- `drop_or_full_regen`：不导出训练。

## 导出分类子集

使用脚本：`training/scripts/planner/data/export_sft_budget_clean_subset.py`

用途：读取原始 `records.jsonl` 和 `record_classification.jsonl`，按指定 category 导出完整 records 子集，同时生成 LLaMAFactory train/val 文件。

示例命令：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/export_sft_budget_clean_subset.py \
  --records training/data/planner/sft/<YYMMDD>_<run_slug>/records.jsonl \
  --classification training/outputs/eval/audits/<audit_root>/usability/record_classification.jsonl \
  --category usable_budget_clean \
  --output-dir training/data/planner/sft/<YYMMDD>_<run_slug>_budget_clean \
  --dataset-prefix trip_planner_sft_<YYMMDD>_<run_slug>_budget_clean \
  --val-ratio 0.1
```

运行要求：

- 必须显式传入 `--records`、`--classification`、`--output-dir` 和 `--dataset-prefix`。
- `--records` 和 `--classification` 必须来自同一轮 run。
- `--dataset-prefix` 必须能看出日期、run slug 和导出 category，避免覆盖 `dataset_info.json` 中已有数据集名。
- 导出 `usable_budget_candidate_tight` 等非默认 category 前，先让用户确认用途和命名。

主要产物：

- `records.jsonl`：导出的完整原始 records 子集。
- `record_ids.txt`：被导出的 record_id 列表。
- `summary.json`：导出摘要。
- `数据集说明.md`：可读说明。
- `training/data/llamafactory/<dataset-prefix>_train.json`：LLaMAFactory train 文件。
- `training/data/llamafactory/<dataset-prefix>_val.json`：LLaMAFactory val 文件。
- `training/data/llamafactory/dataset_info.json`：会注册 `<dataset-prefix>_train` 和 `<dataset-prefix>_val`。

## 校验 LLaMAFactory 文件

使用脚本：`training/scripts/validation/validate_trip_plan.py`

用途：逐行读取 SFT JSON，解析每条 `output` 并用后端 `TripPlan` schema 校验。这个校验只证明输出能过 schema，不证明预算贴合、候选 grounding 或人工质量通过。

示例命令：

```bash
.venv-training-py311/bin/python3 training/scripts/validation/validate_trip_plan.py \
  --sft training/data/llamafactory/trip_planner_sft_<YYMMDD>_<run_slug>_budget_clean_train.json

.venv-training-py311/bin/python3 training/scripts/validation/validate_trip_plan.py \
  --sft training/data/llamafactory/trip_planner_sft_<YYMMDD>_<run_slug>_budget_clean_val.json
```

留痕要求：

- 校验完成后，在 `training/outputs/eval/audits/<audit_root>/export_validation/validation_summary.md` 记录 train/val 的命令、路径、total 和 failed。
- 如果实际运行时使用终端日志、run log 或外部调度器日志，也要在汇报中给出路径。

校验通过标准：

- train 和 val 都输出 `failed=0`。
- 如果任一文件 failed 大于 0，不要进入训练；先根据失败行回查导出子集和原始 record。
- 如果文件为空、val 为 0 或样本数明显不符合 `summary.json`，停止并定位导出步骤。

## 导出后检查清单

导出后至少确认：

- `summary.json` 中的 `records` 等于 `record_ids.txt` 行数。
- `llamafactory_train + llamafactory_val` 等于导出 records 数。
- `record_ids.txt` 中的 ID 都存在于源 `records.jsonl`。
- `dataset-prefix` 没有覆盖其他实验的数据集名。
- train/val 的 schema 校验都为 `failed=0`。
- 汇报中写清楚导出的 category、样本数、train/val 数量、源 run、分类路径和校验结果。
- 如果用户接着问训练配比、是否混旧数据、是否从 checkpoint/adapter 继续、或存储风险，转到 `references/training_handoff.md`；不要把 schema 校验通过直接等同于“应该启动训练”。

## 常见风险

- 直接使用原始 run 自带的 `llamafactory_train.json` / `llamafactory_val.json` 训练，绕过 usability classification。
- 导出时误用其他 run 的 `record_classification.jsonl`，导致 ID 缺失或混入错误样本。
- `dataset-prefix` 太泛，覆盖已有 LLaMAFactory 数据集注册。
- 只校验 train，不校验 val。
- 把 schema 校验通过误认为预算审计、人工预览和分类都通过。
- 导出非 `usable_budget_clean` 类别时没有单独命名，后续训练归因混乱。
