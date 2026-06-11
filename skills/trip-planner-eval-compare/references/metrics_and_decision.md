# Metrics And Decision

## 目录

- Pass 口径
- 必看的指标组
- 判断 checkpoint 是否变好
- 失败类型解读
- Grounding 审计判断
- 汇报取舍

## Pass 口径

报告对外用 `hardpass` / `softpass`，脚本内部字段保留历史 key。

| 展示名 | 内部字段 | 解释 |
| --- | --- | --- |
| hardpass | `hard_pass` / `sft_hard_pass` | 当前主硬约束，临时等同 `sft_no_budget_sum_hard_pass` |
| hardpass_no_budget_sum | `sft_no_budget_sum_hard_pass` | 不因模型自报预算精确账本失败一票否决 |
| hardpass_strict | `sft_strict_hard_pass` | 旧严格账本硬约束，用于诊断原生预算加和能力 |
| hardpass_budget_semantic | `sft_budget_semantic_hard_pass` | 用预算关系理解替代精确账本的阶段性口径 |
| softpass | `dpo_soft_pass` | hardpass 通过后，再看景点/餐饮多样性和预算偏好 |
| softpass_recomputed_budget | `dpo_soft_recomputed_budget_pass` | 用工程重算预算贴合替代模型自报预算偏好 |
| legacy_hard_pass | `legacy_hard_pass` | 历史兼容，不作为当前主判断 |

当前 `hard_pass` 不包含模型自报 budget 精确加总、景点预算精确一致、餐饮预算精确一致、酒店预算严格覆盖和用户预算硬约束。预算仍必须单独汇报。

## 必看的指标组

协议硬指标：

- `json_extract_ok`
- `schema_ok`
- `city_ok`
- `date_range_ok`
- `days_len_ok`
- `day_dates_ok`
- `weather_dates_ok`
- `day_index_ok`
- `weather_match`
- `location_object_ok`

住宿与行程：

- `accommodation_type_ok`
- `middle_hotel_ok`
- `invalid_hotel_name_ok`
- `hotel_distance_placeholder_ok`
- `attraction_count_ok`

Grounding：

- `attraction_grounding_ok` / `attraction_grounding_rate`
- `hotel_grounding_ok` / `hotel_grounding_rate`
- `meal_grounding_ok` / `meal_grounding_rate`
- `meal_valid_semantics_ok`

软质量：

- `attraction_diversity_ok`
- `meal_diversity_ok`
- `budget_preference_aligned`
- `dpo_soft_pass`

预算：

- `budget_user_constraint_ok`
- `budget_preference_aligned`
- `budget_selection_ok`
- `recomputed_budget_hard_ok`
- `recomputed_budget_fit_ok`
- `budget_relationship_ok`
- `hotel_budget_relation_ok`
- `attraction_budget_party_relation_ok`
- `meal_cost_scale_ok`
- `budget_arithmetic_consistent`
- `attraction_budget_consistent`
- `meal_budget_consistent`
- `hotel_budget_covers_nights`

生成健康：

- API call 失败数。
- `json_extract_ok` 和 `schema_ok` 分母。
- `finish_reason=length` 数量。
- 平均 `latency_seconds` 和 `output_chars`。

## 判断 checkpoint 是否变好

先做口径闸门：

- 同一 split 使用同一个 records 文件。
- 同一轮对比使用同一 context 版本。
- 每个模型都已完成相同 standard/hard split。
- 没有明显生成失败或截断差异。
- 若某模型 schema 分母明显更低，先解释失败原因再比较后续规则指标。

再做主判断：

- standard hardpass 不应低于 base；hard hardpass 不能出现无法解释的大幅退化。
- 当前主线候选应在 hard 或 standard 至少一个 split 明确优于 base，并在另一个 split 没有主要硬指标回退。
- 与历史强对照相比，要先说明它是否来自旧数据路线或旧 context；旧路线高分只能作 reference。
- 如果 hardpass 接近，优先看 softpass、预算偏好、重算预算贴合、餐饮多样性和 hard split 切片。
- 如果 softpass 提升来自预算偏好，但 grounding、schema、天气、住宿连续性回退，则不能直接判为更好。
- 如果“不超预算”更高但预算偏好/重算预算贴合更低，通常说明模型更保守，不代表预算质量更好。

## 失败类型解读

从 `rule_eval_report.json.summary.error_types` 和 `rule_eval_report.md` 的 Failed Examples 开始定位。

常见解释：

- `meal_invalid_name`：通常是正餐写了景点、酒店、附近餐厅、当地小吃或未知食品语义；优先看 `meal_valid_semantics_ok` 与 `meal_grounding_ok`。
- `meal_grounding_miss`：餐饮名语义可能合法但不在 `food_pois`；可用 relaxed grounding 判断是否名称归一化误伤。
- `accommodation_type_mismatch`：`day.accommodation` 没复制用户住宿类型，是协议硬错。
- `middle_hotel_null`：非最后一天住宿为空，是硬错。
- `weather_mismatch`：天气没有逐日复制 `trip_weather`，通常应算硬退化。
- `budget_relationship_mismatch`：模型可能不理解住宿晚数、同行人数或餐饮人均费用尺度。
- `budget_preference_mismatch`：可能是过省、超支或没有按 budget_fit_policy 花钱；要结合 `recomputed_budget_*` 判断最终选择质量。

## Grounding 审计判断

Strict rule eval 是官方口径。Relaxed grounding 只用于诊断 evaluator false negative。

如果 relaxed audit 显示 `Recovered hard_pass = 0`，说明当前 grounding 失败大多是真失败或语义无效，不应改官方分数。

如果 relaxed audit 恢复了大量样本，下一步不是手改报告，而是：

- 查看 recovered examples 是否只是简繁、括号、空格、城市前缀或 POI 后缀差异。
- 把合理归一化补进 `name_in_candidates()` 或候选别名规则。
- 重跑官方 rule eval，并在报告中明确口径变更日期。

## 汇报取舍

面向决策的摘要优先说：

- 当前该选哪个 checkpoint。
- 选择它的主要证据来自 standard、hard、预算、softpass 还是切片。
- 哪些指标只是诊断项，不应被当成主胜负。
- 还有哪些风险需要下一轮评估或人工查看。

避免只说“平均分更高”。Planner 当前更关心能否稳定输出可解析、可 grounding、可工程重算的 TripPlan，再看预算和偏好质量。
