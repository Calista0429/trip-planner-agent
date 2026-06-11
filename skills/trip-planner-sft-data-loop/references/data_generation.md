# Data Generation

这份参考用于指导 Planner realbudget SFT 数据的生成阶段，包括请求分布 dry-run、PlannerContext smoke、小批量 teacher 生成、`budget_supplement` 预算利用型补数和后续扩量。它只覆盖“怎么生成数据”和“生成后先检查什么”，不负责 budget fit audit、usability classification、LLaMAFactory 校验或训练判断。

生成阶段的目标不是一次性跑出大量 records，而是用低风险方式确认：请求分布合理、PlannerContext 可构建、外部 API 并发可控、输出目录正确、teacher 生成没有明显系统性失败。


## 生成阶段的任务类型

- 请求分布 dry-run：只检查请求分布，不调用高德 API 或强模型。
- PlannerContext smoke：小规模构建上下文，检查候选池、天气、酒店、餐饮、价格 hint 和预算策略。
- smoke20 小批量生成：生成少量 teacher records，用于人工预览和最小验收；它主要用于发现系统性问题，不直接视为可训练数据定稿。
- 100 条验证生成：在 smoke20 通过人工预览和最小验收后，生成一轮中等规模数据，用于检查分布、失败类型、teacher 质量和审计指标是否稳定。
- 1000或更多条候选训练池生成：只有在 100 条验证结果稳定后再执行，用于形成正式训练候选池；生成后仍必须经过人工预览、审计、分类、导出和校验。
- `budget_supplement` 预算利用型补数：针对 comfortable/premium 等真实预算档位生成“soft 预算尽量用足”的补丁数据；它应按预算档位单独扩量、单独审计，不要和普通主数据口径混淆。


## 外部 API 与并发策略

不同生成任务的外部依赖不同，选择并发前先判断本轮会不会调用高德 API 或强模型 API。

- 请求分布 dry-run 不调用高德 API 或强模型，可以直接运行。
- PlannerContext smoke 会调用高德 API，但不调用强模型。
- teacher 生成会同时调用高德 API 和强模型 API，可能产生 token 成本。
- `--workers` 是样本级并发，会让多个样本同时构建 PlannerContext 和调用 teacher 强模型。
- `--amap-qps-limit` 是单进程内高德 HTTP 请求 QPS 限制，默认建议 `3`。
- `--amap-qps-limit` 对同一个造数进程内的所有 worker 共享生效；但不跨多个同时运行的进程，也不限制强模型 API。
- `--teacher-model-provider` 选择 teacher 强模型配置 profile；可选 `deepseek`、`mimo` 或 `env`。
- `--teacher-model` 可覆盖具体 model id；不传则使用所选 provider 在 `.env` 里的默认模型。
- 如果用户未给出强模型并发和成本边界，先确认再提高 `--workers`；当前 smoke20 已确认可使用 `--workers 10`。
- 扩量前先检查 smoke 或上一轮生成是否出现 429、timeout、候选池为空、强模型失败、输出截断或 token 成本异常。

高德 cache/API preflight：

- 如果用户认为高德 API 已经“全量 cache”，仍要先用小规模 context smoke 或 teacher smoke 看日志中的 cache miss/API 请求量。
- 确认高德缓存 TTL 或项目当前配置不会因为过期触发大面积重新请求；必要时先检查 `backend/app/planner/amap.py` 和 `.env` 里的缓存相关配置。
- `--amap-qps-limit` 只限制当前造数进程内的高德 HTTP cache miss；多个并行造数进程会叠加请求，扩量时不要同时跑多个生成进程。
- 如果出现大量高德 API 请求、429、timeout 或 cache miss 集中，先停下来定位，不要继续提高 `--workers`。

默认建议：

- PlannerContext smoke：`--workers 1 --amap-qps-limit 3`
- smoke20 teacher 生成：当前可使用 `--workers 10 --amap-qps-limit 3 --teacher-model-provider deepseek`
- 100 / 1000 扩量：只有在上一轮没有明显限流、超时和成本异常时，再和用户确认是否沿用或提高 `--workers`。

teacher 模型选择：

- 默认使用 `deepseek`，读取 `.env` 中的 `DATA_GEN_MODEL`、`DEEPSEEK_API_KEY` 和 `DEEPSEEK_BASE_URL` 等配置。
- 如需试跑 Mimo，把 teacher 生成命令中的 `--teacher-model-provider deepseek` 改为 `--teacher-model-provider mimo`；默认读取 `MIMO_API_KEY`、`MIMO_OPENAI_BASE_URL` 和 `MIMO_MODEL`。
- 如果用户明确指定具体模型，再追加 `--teacher-model <model_id>`，例如 `--teacher-model mimo-legacy.5-pro`。
- 同一轮 run 不要混用不同 teacher provider；如果切换 provider，使用新的 run slug，例如 `<YYMMDD>_smoke20_mimo`。

真实预算分档红线：

- `budget_supplement` 必须沿用项目真实预算表，例如脚本里的 `PER_PERSON_DAY_BUDGETS`；不要维护一份单独、平移过的 supplement 预算表。
- 不要为了让 summary 或审计“看着好”牺牲真实预算口径。候选池不可达、premium 成功率低，是数据筛选信号，不是调窄预算档位的理由。
- dry-run 后必须检查 `amount / (party_total * travel_days)` 是否落在目标预算档位；审计后必须确认 `request_budget_status` 全部为 `ok`，否则不能作为真实预算训练数据。
- comfortable 和 premium 的真实预算区间不同，premium 在候选池可达性上通常更难；扩量计划要预留更高失败率。

## 输出目录规则

Planner SFT 原始生成 run 必须写入 `training/data/planner/sft/` 下的独立目录，不得直接把 records 或派生产物散写到 `training/data/planner/sft/` 根目录。

如果用户没有指定输出目录，先根据日期、规模和目的提出目录名，再执行会写文件的命令。

推荐目录格式：

```text
training/data/planner/sft/<YYMMDD>_<run_slug>/
```

示例：

```text
training/data/planner/sft/260510_smoke20_main/
training/data/planner/sft/260510_validate100_main/
training/data/planner/sft/260510_main1000_gate1_thinking_off/
training/data/planner/sft/260510_smoke20_retry_api_limit/
training/data/planner/sft/260510_validate100_food_fix/
```

目录分工：

- `training/data/planner/sft/`：Planner SFT 数据根目录；原始生成 run 和后续清洗、分类、切分产物都必须放在可识别的子目录下。
- `training/data/planner/archive/`：仅用于留痕；不作为当前 Planner SFT run 的输入或输出目录。

每个生成 run 目录至少关注以下产物：

- `records.jsonl`：成功生成的完整 records。
- `requests.jsonl`：对应请求。
- `errors.jsonl`：失败样本和错误原因。
- `llm_usage.jsonl`：强模型 token usage；如果缺失，最终汇报必须指出。
- `llamafactory_train.json` / `llamafactory_val.json`：如果生成脚本导出了 LLaMAFactory 格式，则检查这两个文件。
- 生成日志：如果使用 nohup 或脚本 wrapper，日志应放在 run 目录或相邻位置，并在汇报中给出路径。

执行前检查：

- 确认输出目录位于 `training/data/planner/sft/` 下的独立子目录。
- 确认不会直接把文件写到 `training/data/planner/sft/` 根目录。
- 确认目录名能看出日期、规模、目的和关键参数，例如 `w20`、`thinking_off`、`no_none`。
- 如果目录已存在，先判断是要 `--resume`、新建重跑目录，还是停止等待用户确认。
- 不要把 smoke、validate、main 等不同阶段混写到同一个 run 目录。



## 常用流程

### 请求分布 dry-run

用途：检查 controlled 请求分布、预算档位、天数、同行类型、住宿和交通分布是否符合预期。不调用高德 API 或强模型。

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/generate_sft_data.py \
  --count 100 \
  --request-source controlled \
  --date-mode mixed \
  --dry-run-requests \
  --dry-run-summary
```

运行后重点看：

- budget_level 分布是否符合当前目标。
- travel_days、companion_type、city_tier 是否有明显偏斜。
- 是否出现不应该进入当前主线的字段或请求口径。
- 如果 dry-run 分布不合理，先停下来调整请求生成逻辑，不进入 PlannerContext smoke。

`budget_supplement` dry-run 示例：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/generate_sft_data.py \
  --count 700 \
  --request-source budget_supplement \
  --date-mode mixed \
  --target-budget-mix comfortable/soft=500,premium/soft=200 \
  --dry-run-requests \
  --dry-run-summary
```

运行后除常规分布外，额外看：

- comfortable/premium 数量是否等于目标 mix。
- strictness 是否符合目标，例如预算利用型补数通常是 `soft`。
- 人日预算是否沿用真实预算表，而不是 supplement 专用平移表。
- 如果 request 预算本身不合法，先修请求生成，不进入 context smoke 或 teacher 生成。


### PlannerContext smoke 检查

用途：小规模构建 PlannerContext，检查候选池、天气、酒店、餐饮、价格 hint、budget_fit_policy 和上下文压缩是否正常。不调用 Planner teacher 强模型，不写训练 records。

运行前确认：

- 已配置 `AMAP_MAPS_API_KEY` 或 `AMAP_API_KEY`。
- 已确认高德 API QPS/并发边界；当前按 3 QPS 保守处理。
- 使用 `--amap-qps-limit 3` 时，单个造数进程内的高德 HTTP cache miss 请求按 3 QPS 节流。
- 优先小规模、低并发运行。

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/generate_sft_data.py \
  --count 20 \
  --request-source controlled \
  --date-mode mixed \
  --workers 1 \
  --dry-run-context \
  --amap-qps-limit 3
```

运行后重点看：

- 是否有高德 API 失败、429、timeout 或 key 缺失。
- `classic_pois`、`hotel_pois`、`food_pois` 是否为空或明显不足。
- 酒店是否有 `estimated_cost_hint`。
- 景点是否有 `ticket_price_hint` 或合理 fallback。
- 餐饮是否有 `meal_cost_hint`、`meal_roles`、`price_level`、`source_bucket`。
- `budget_fit_policy` 是否存在且目标区间合理。
- 如果候选池或预算可达性明显不足，先停下来定位，不进入 teacher 生成。

`budget_supplement` context smoke 示例：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/generate_sft_data.py \
  --count 20 \
  --request-source budget_supplement \
  --date-mode mixed \
  --target-budget-mix comfortable/soft=10,premium/soft=10 \
  --workers 1 \
  --dry-run-context \
  --amap-qps-limit 3
```

额外检查：

- `budget_fit_policy_override` 是否要求 soft 预算尽量贴近用户总预算，而不是低配省钱。
- 高配候选池估算是否能覆盖目标预算；premium 出现一定比例不可达是正常信号，但不能忽略集中不可达城市/场景。
- 高德 cache 命中/请求日志是否符合预期。


### budget_supplement 预算利用型补数

用途：生成真实预算口径下的 soft 预算利用型补丁数据，让 teacher 在真实候选池内通过选择更高价酒店、餐饮、体验来贴近用户预算。它不是普通主数据生成流程；使用时要明确 `request_source=budget_supplement`、预算档位 mix、teacher provider 和精确目标条数。

适用场景：

- 已确认主数据在预算利用、comfortable/premium 或高预算场景上有短板。
- 用户明确要造 comfortable、premium 等指定预算档位数据。
- 已通过 dry-run、context smoke 和小批量人工预览，确认 teacher 质量和预算直觉可接受。

主要原则：

- 精确目标数按档位分开跑。例如要 500 comfortable + 200 premium，应分别跑两个 `--target-successes`，不要混跑 700 后期待成功样本自然按 500/200 分布。
- `--count` 在目标成功模式下应理解为最大提交上限；premium 失败率可能更高，`--count` 要明显大于 `--target-successes`。
- 不同批次使用不重叠的 `--start-index`，避免 `record_id` 撞车。
- Mimo 等 teacher provider 的高并发只限制强模型请求；高德请求仍靠 `--amap-qps-limit` 和 cache 控制。
- 扩量前先跑 20 或 100 条预览/审计，不要第一次就直接造正式规模。

100 条 Mimo 验证示例：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/generate_sft_data.py \
  --count 180 \
  --target-successes 100 \
  --start-index <unique_start_index> \
  --request-source budget_supplement \
  --date-mode mixed \
  --target-budget-mix comfortable/soft=80,premium/soft=20 \
  --workers 50 \
  --sample-retries 3 \
  --teacher-model-provider mimo \
  --amap-qps-limit 3 \
  --output-dir training/data/planner/sft/<YYMMDD>_mimo_realbudget_usage_validate100_w50
```

正式 comfortable 单档扩量示例：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/generate_sft_data.py \
  --count 900 \
  --target-successes 500 \
  --start-index <comfortable_start_index> \
  --request-source budget_supplement \
  --date-mode mixed \
  --target-budget-mix comfortable/soft=500 \
  --workers 50 \
  --sample-retries 3 \
  --teacher-model-provider mimo \
  --amap-qps-limit 3 \
  --output-dir training/data/planner/sft/<YYMMDD>_mimo_realbudget_usage_comfortable500_w50
```

正式 premium 单档扩量示例：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/generate_sft_data.py \
  --count 900 \
  --target-successes 200 \
  --start-index <premium_start_index> \
  --request-source budget_supplement \
  --date-mode mixed \
  --target-budget-mix premium/soft=200 \
  --workers 50 \
  --sample-retries 3 \
  --teacher-model-provider mimo \
  --amap-qps-limit 3 \
  --output-dir training/data/planner/sft/<YYMMDD>_mimo_realbudget_usage_premium200_w50
```

生成后先做的轻量检查：

- `records.jsonl` 行数是否等于 `--target-successes`。
- `record_id` 是否唯一，且不同档位批次之间没有重复。
- `budget_level` 和 `strictness` 是否只有目标档位，例如 `comfortable/soft` 或 `premium/soft`。
- `errors.jsonl` 中 premium 的 `budget_supplement上下文预算不可达` 可以是预期损耗，但要汇报比例和金额范围。
- 先生成 preview，再跑 budget fit audit 和 usability classification；不能只凭成功条数进入训练。


### smoke20 小批量生成

用途：生成少量 Planner realbudget teacher records，用于人工预览和最小验收。smoke20 的目标是发现系统性问题，不直接视为可训练数据定稿。

运行前确认：

- 已确认输出目录位于 `training/data/planner/sft/` 下的独立子目录。
- 已确认高德 API 和强模型 API 的 QPS、并发和成本边界。
- 已完成请求分布 dry-run 和 PlannerContext smoke，且没有明显系统性问题。
- 生成 wrapper 只写本轮 run 的 records、errors、requests、summary 和 LLaMAFactory 文件，不合并历史数据。

示例命令：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/run_sft_realistic_budget_generation.py \
  --count 20 \
  --target-successes 20 \
  --max-submissions 80 \
  --date-mode mixed \
  --workers 10 \
  --teacher-model-provider deepseek \
  --output-dir training/data/planner/sft/<YYMMDD>_smoke20_main \
  --amap-qps-limit 3
```

参数说明：

- `--target-successes 20`：目标成功生成 20 条。
- `--max-submissions 80`：最多尝试 80 个 base 请求，避免候选池预算不可达时无限重试。
- `--workers 10`：当前 smoke20 已确认可用的样本级并发；它也会间接控制强模型 teacher 并发。
- `--teacher-model-provider deepseek`：本轮 teacher 强模型 profile；试跑 Mimo 时改为 `mimo`，并使用新的 run 目录。
- `--output-dir`：必须是 `training/data/planner/sft/` 下的独立 run 目录，不得直接写入 `training/data/planner/sft/` 根目录。

生成后先看：

- `records.jsonl` 成功条数是否接近目标。
- `errors.jsonl` 是否有集中失败类型，例如 API 限流、timeout、候选池不足、预算不可达、teacher 输出无法解析。
- `summary.json` 中 `ok`、`failed`、`launched`、预算档位和 strictness 分布是否合理。
- `llamafactory_train.json` / `llamafactory_val.json` 是否被写出。
- 如果有 `llm_usage.jsonl`，检查 token 成本是否异常；如果没有 usage 记录，最终汇报中要指出。
- 生成后不要立刻扩量，先进入样本预览和人工检查。


### 100 / 1000 条扩量

用途：在 smoke20 通过人工预览和最小验收后，逐步扩大数据规模。100 条主要用于验证质量和分布是否稳定；1000 条用于形成正式训练候选池。

扩量前必须确认：

- smoke20 已完成样本预览，且没有明显系统性 teacher 质量问题。
- smoke20 的主要失败类型已经理解，不存在大面积 API 限流、timeout、候选池为空、预算不可达或输出无法解析。
- 已运行必要的最小验收，用户同意进入下一档规模。
- 已确认外部 API 的 QPS、并发和成本边界。
- 本轮输出目录位于 `training/data/planner/sft/` 下的独立子目录，并且不与 smoke20 混写。

100 条验证示例：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/run_sft_realistic_budget_generation.py \
  --count 100 \
  --target-successes 100 \
  --max-submissions 300 \
  --date-mode mixed \
  --workers 10 \
  --teacher-model-provider deepseek \
  --output-dir training/data/planner/sft/<YYMMDD>_validate100_main \
  --amap-qps-limit 3
```

1000 条候选训练池示例：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/data/run_sft_realistic_budget_generation.py \
  --count 1000 \
  --target-successes 1000 \
  --max-submissions 3000 \
  --date-mode mixed \
  --workers 10 \
  --teacher-model-provider deepseek \
  --output-dir training/data/planner/sft/<YYMMDD>_main1000 \
  --amap-qps-limit 3
```

参数调整原则：

- `--workers` 不固定追求最大值；按高德 API、强模型 API、成本和上一轮失败率决定。
- `--teacher-model-provider` 切换会改变 teacher 风格和成本口径；切换后先重新跑 smoke，不要直接扩量。
- `--max-submissions` 应明显大于 `--target-successes`，给预算候选池不可达、API 失败和 teacher 失败留余量。
- 如果用户指定预算档位配比或 strictness 策略，优先确认脚本是否支持对应参数，不要临时改 records。
- 如果扩量过程中失败类型集中，先停止分析，不要继续堆提交数。

扩量后先看：

- `summary.json` 的 `ok`、`failed`、`launched`。
- 预算档位、strictness、金额分布是否符合本轮目标。
- `errors.jsonl` 是否集中在某类城市、预算档位、天数或 API 错误。
- token usage 是否在用户可接受范围内。
- 不要只因为成功条数达标就进入训练；扩量后仍要走预览、审计、分类、导出和校验。


## 生成后先看什么

生成命令完成后，先做轻量健康检查，再决定是否进入样本预览、审计或扩量。

优先检查：

- `records.jsonl`：成功样本数是否符合本轮目标，记录结构是否完整。
- `errors.jsonl`：失败样本数和主要失败类型，是否集中在某类城市、预算档位、天数或 API 错误。
- `requests.jsonl`：请求数量、预算档位、strictness、同行类型和天数分布是否符合预期。
- `summary.json`：`ok`、`failed`、`launched`、预算金额范围、budget_level 和 strictness 分布是否合理。
- `llm_usage.jsonl` 或 records metadata 中的 usage：强模型 token 成本是否异常；如果缺失 usage 记录，最终汇报要明确指出。
- `llamafactory_train.json` / `llamafactory_val.json`：如果生成脚本已导出，确认文件存在但不要只凭存在就判断可训练。

先不要做的事：

- 不要只因为 `records.jsonl` 数量达标就扩量。
- 不要跳过人工预览直接进入训练数据定稿。
- 不要把 `errors.jsonl` 里的集中失败当作正常随机失败忽略。


## 常见失败信号

遇到以下情况时，先停止扩量并定位原因：

- 高德 API 失败、429、timeout 或 key 缺失。
- `food_pois`、`hotel_pois`、`classic_pois` 大面积为空。
- 候选池预算不可达，`BudgetContextUnreachableError` 集中出现。
- teacher 输出无法解析、schema 校验失败或大量样本生成失败。
- 输出明显截断，或 travel_days 越长失败率越高。
- 餐饮占位、酒店不连续、预算明显不符合直觉等问题在 smoke 中重复出现。
- token usage 明显高于预期，或 usage 缺失导致成本不可追踪。
