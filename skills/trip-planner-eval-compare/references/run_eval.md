# Run Eval

## 目录

- 固定评估集
- 预检命令
- 输出目录约定
- 单模型完整评估
- 只生成或只重跑规则
- 生成参数注意
- 产物检查

## 固定评估集

当前 Planner 主评估集：

| split | records | 样本数 | record_id 前缀 |
| --- | --- | ---: | --- |
| standard | `training/data/planner/eval/records.jsonl` | 200 | `planner_standard200_realbudget_eval_` |
| hard | `training/data/planner/eval_hard/records.jsonl` | 300 | `planner_hard_realbudget_eval_` |

2026-05-11 高端 POI 召回增强后，主路径 `eval` / `eval_hard` 已重建 PlannerContext；不要和 `training/data/planner/archive/eval_pre_high_end_context_20260511/` 下的旧 context 结果混比。

## 预检命令

在项目根目录运行：

```bash
git status --short
```

检查 records 数量和前缀：

```bash
.venv-training-py311/bin/python3 - <<'PY'
import json
from pathlib import Path

for path in [
    Path("training/data/planner/eval/records.jsonl"),
    Path("training/data/planner/eval_hard/records.jsonl"),
]:
    ids = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                ids.append(json.loads(line)["record_id"])
    prefix = "planner_standard200_realbudget_eval_" if "eval_hard" not in str(path) else "planner_hard_realbudget_eval_"
    print(path, "rows", len(ids), "unique", len(set(ids)), "prefix_ok", all(item.startswith(prefix) for item in ids))
PY
```

## 输出目录约定

单模型评估目录形如：

```text
training/outputs/eval/by_model/<model_family>/<YYMMDD>_<run_slug>/
```

因为 `eval_generate.py` 和 `eval_rule_metrics.py` 会把 `--model-name` 追加到 `--output-dir` 后面，所以命令里通常这样传：

```text
--output-dir training/outputs/eval/by_model/<model_family>
--model-name <YYMMDD>_<run_slug>
```

例如 `base_qwen25_7b` 的 standard run：

```text
training/outputs/eval/by_model/base_qwen25_7b/260511_high_end_context_standard_w10/
```

## 单模型完整评估

优先用 `eval_pipeline.py` 串联生成和 rule eval：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/eval_pipeline.py \
  --records training/data/planner/eval/records.jsonl \
  --model-name 260511_high_end_context_standard_w10 \
  --api-model trip-planner-base-rebuild \
  --base-url http://127.0.0.1:4400/v1 \
  --output-dir training/outputs/eval/by_model/base_qwen25_7b \
  --workers 10 \
  --resume
```

hard split 只替换 records 和 run slug：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/eval_pipeline.py \
  --records training/data/planner/eval_hard/records.jsonl \
  --model-name 260511_high_end_context_hard_w10 \
  --api-model trip-planner-base-rebuild \
  --base-url http://127.0.0.1:4400/v1 \
  --output-dir training/outputs/eval/by_model/base_qwen25_7b \
  --workers 10 \
  --resume
```

要先 smoke，使用独立 run slug，避免把小样本配置覆盖成正式目录：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/eval_pipeline.py \
  --records training/data/planner/eval/records.jsonl \
  --model-name 260511_<slug>_standard_smoke5 \
  --api-model <api_model> \
  --base-url http://127.0.0.1:<port>/v1 \
  --output-dir training/outputs/eval/by_model/<model_family> \
  --workers 1 \
  --limit 5
```

## 只生成或只重跑规则

只生成：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/eval_generate.py \
  --records training/data/planner/eval/records.jsonl \
  --model-name <YYMMDD>_<run_slug> \
  --api-model <api_model> \
  --base-url http://127.0.0.1:<port>/v1 \
  --output-dir training/outputs/eval/by_model/<model_family> \
  --workers <n> \
  --resume
```

已有 `generations.jsonl` 时，只重跑 rule eval：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/eval_rule_metrics.py \
  --records training/data/planner/eval/records.jsonl \
  --generations training/outputs/eval/by_model/<model_family>/<YYMMDD>_<run_slug>/generations.jsonl \
  --model-name <YYMMDD>_<run_slug> \
  --output-dir training/outputs/eval/by_model/<model_family>
```

也可以用 pipeline 跳过生成：

```bash
.venv-training-py311/bin/python3 training/scripts/eval/eval_pipeline.py \
  --records training/data/planner/eval/records.jsonl \
  --model-name <YYMMDD>_<run_slug> \
  --api-model <api_model> \
  --output-dir training/outputs/eval/by_model/<model_family> \
  --skip-generate
```

## 生成参数注意

- `--resume` 默认只跳过 `ok=true` 的样本，之前失败的样本会重试；通常不要加 `--resume-include-failed`。
- `--trust-env` 会允许 HTTP proxy 环境变量影响本地请求；除非用户明确需要代理，否则不要加。
- `--max-tokens 0` 时脚本按天数估算上限；如果出现 `finish_reason=length`，优先增大 `--output-tokens-cap` 或显式 `--max-tokens` 后重跑失败样本。
- workers 要按模型服务承载能力设置。正式 200/300 条评估前，先用 smoke 验证端口、prompt、输出长度和 schema。

## 产物检查

每个单模型 run 至少应包含：

- `generation_config.json`
- `generations.jsonl`
- `rule_eval_report.json`
- `rule_eval_report.md`

检查项：

- `generation_config.json.records` 与本轮 split records 一致。
- `rule_eval_report.json.records_path` 与本轮 split records 一致。
- `rule_eval_report.json.generations_path` 指向同一 run 的 `generations.jsonl`。
- `raw_generations`、`unique_generations` 和 records 数量匹配预期；若有重试，rule eval 只使用每个 `record_id` 的最后一条生成。
- `generations.jsonl` 中 `ok=false`、空输出、`finish_reason=length` 需要单独汇报。

快速统计生成状态：

```bash
.venv-training-py311/bin/python3 - <<'PY'
import json
from collections import Counter
from pathlib import Path

path = Path("training/outputs/eval/by_model/<model_family>/<YYMMDD>_<run_slug>/generations.jsonl")
rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
print("rows", len(rows), "unique", len({row.get("record_id") for row in rows}))
print("ok", Counter(bool(row.get("ok")) for row in rows))
print("finish", Counter(row.get("finish_reason") for row in rows if row.get("ok")))
print("errors", Counter(row.get("error_type") for row in rows if not row.get("ok")))
PY
```
