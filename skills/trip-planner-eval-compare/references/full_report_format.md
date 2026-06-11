# Full Report Format

## 目录

- canonical example
- 文件位置
- 顶部元信息
- 口径说明
- 总结
- 生成完成情况
- 合并视图
- 指标映射和取数
- 分 split 视图
- 数据源
- 读数建议
- 写作规则

## canonical example

最终给人看的报告格式以这份历史报告为准：

```text
training/outputs/eval/archive/260511_old_training_records_keep_baseline_legacy_b_lr8e5_valloss/comparisons/260511_planner_valloss_lr6e5_vs_lr8e5_final208_legacy_b_baseline_full_report/planner_valloss_lr6e5_vs_lr8e5_final208_legacy_b_baseline_full_report.md
```

它是一份单文件 Markdown full report，不是只给机器消费的 JSON，也不是只含结论的短摘要。只参考这份文件的报告格式；输出路径规范以本 skill 的当前 `compare_and_report.md` 为准，不继承 archive 路径。

## 文件位置

默认输出到 comparison 目录：

```text
training/outputs/eval/comparisons/<YYMMDD>_<comparison_slug>/<comparison_slug>_full_report.md
```

优先用仓库脚本生成该文件：

```bash
.venv-training-py311/bin/python3 training/scripts/planner/eval/generate_full_report.py \
  --current-label <candidate_label> \
  --primary-label <main_reference_label> \
  --baseline-label <baseline_label> \
  --standard-records training/data/planner/eval/records.jsonl \
  --hard-records training/data/planner/eval_hard/records.jsonl \
  --report standard/<candidate_label>=<candidate_standard_rule_eval_report.json> \
  --report hard/<candidate_label>=<candidate_hard_rule_eval_report.json> \
  --report standard/<main_reference_label>=<main_reference_standard_rule_eval_report.json> \
  --report hard/<main_reference_label>=<main_reference_hard_rule_eval_report.json> \
  --report standard/<baseline_label>=<baseline_standard_rule_eval_report.json> \
  --report hard/<baseline_label>=<baseline_hard_rule_eval_report.json> \
  --output-dir training/outputs/eval/comparisons/<YYMMDD>_<comparison_slug> \
  --comparison-slug <comparison_slug>
```

脚本默认校验 `rule_eval_report.json.records_path` 和当前 split records 一致；这条护栏用于避免把旧 records、新 context 或 standard/hard 对调后误生成 full report。

如果需要作为提交材料或精简发布包，可以复制或改写到：

```text
training/outputs/eval/reports/<YYMMDD>_<report_slug>/<comparison_slug>_full_report.md
```

## 顶部元信息

标题使用：

```markdown
# <当前模型/候选> vs <对照模型...> 全量评估报告
```

标题下用 bullet 固定交代：

- 更新时间。
- 当前版本：checkpoint / adapter / 训练 run 名，以及 standard/hard 评估名。
- 上一版、上二版或其他 checkpoint 对照。
- 历史强对照，例如旧 `legacy_b`。
- baseline。
- 标准集和困难集 records 路径、样本数。
- 推理设置：服务/GPU/worker/分片/服务释放状态；如果未知，写明未知，不编。
- 规则口径：`eval_rule_metrics.py` 版本或本轮规则变更，例如 `meal_cost_scale_ok` 是否排除早餐。
- 命名说明：统一写“硬通过/软通过”，避免把训练阶段内部字段名直接端给读者。

## 口径说明

紧接顶部元信息写 `## 通过口径说明`。

必须说明：

- 硬通过只列当前 `hard_pass` 口径的组成项。
- 预算合计、景点预算一致、餐饮预算一致、酒店覆盖晚数、用户预算约束等放在预算部分，不混进硬通过归因。
- `软通过 = 硬通过 + 景点多样性 + 餐饮多样性 + 预算偏好贴合`。
- `重算预算软通过 = 硬通过 + 景点多样性 + 餐饮多样性 + 重算预算贴合`。
- 预算部分是诊断区，不等同于硬通过或软通过。

## 总结

写 `## 总结`，用 3 到 5 段直接给结论。

总结要覆盖：

- 当前候选在 500 条合并口径下的硬通过、相对上一版/历史强对照/baseline 的变化。
- 当前候选的主要收益。
- 当前候选的主要代价，尤其软通过、预算贴合、餐饮多样性、重算预算。
- 选型判断：如果只看硬约束怎么选；如果看软通过/预算贴合怎么选。
- 下一步建议：继续训练、补数据、改召回、做 DPO/pairwise，或停止当前方向。

## 生成完成情况

写 `## 生成完成情况`，用表格列 standard/hard 每个模型的 raw 和 unique：

```markdown
| 数据集 | 当前 <label> | 上一版 <label> | 上二版 <label> | 旧 legacy_b | baseline |
|---|---:|---:|---:|---:|---:|
| 标准集 | raw=200/200, unique=200 | ... |
| 困难集 | raw=300/300, unique=300 | ... |
```

如果模型数不同，保持“当前候选在第一列，主要对照按新到旧，baseline 最后”的顺序。

## 合并视图

写 `## 500条合并视图`。如果当前不是 200+300，也把标题改成实际合并样本数，例如 `## 400条合并视图`。

合并视图固定包含这些小节：

- `### Hardpass 部分`
- `### Softpass 部分`
- `### 预算部分`
- `### 预算数值分布`
- `### <N>条合并 变化摘要`

Hardpass 表只列硬通过组成项，例如：

- 硬通过
- JSON抽取
- Schema合法
- 城市正确
- 日期范围
- 天数
- 每日日期
- 天气日期完整
- day_index正确
- 住宿类型
- 餐饮完整
- 餐饮具体化
- 餐饮语义合法
- 餐饮grounding
- 景点数量
- 景点grounding
- 中间住宿
- 无非法酒店名
- 酒店grounding
- 酒店距离占位
- 坐标对象
- 交通预算非负
- 天气匹配

Softpass 表固定列：

- 软通过
- 重算预算软通过
- 硬通过前置
- 景点多样性
- 餐饮多样性
- 预算偏好贴合
- 重算预算贴合

预算表固定列常用预算诊断项，包括：

- 预算合计一致
- 预算算术一致
- 预算关系一致
- 预算选品贴合
- 预算档位贴合
- 预算偏好贴合（软通过项）
- 用户预算约束
- 声明预算未超
- 重算预算硬约束
- 重算预算贴合（重算软通过项）
- 重算预算档位贴合
- 重算预算偏好贴合
- 重算用户预算约束
- 重算预算未超
- 酒店预算关系
- 酒店覆盖晚数
- 景点预算/人数关系
- 景点预算一致
- 餐饮尺度
- 餐饮预算一致
- 交通预算非负（硬通过项）

合并预算数值分布只列加权 avg：

- 重算总预算 avg
- 重算人日预算 avg

p50/p90 留在 standard/hard 分表。

变化摘要按每个对照单独列小表：

```markdown
相对 上一版 <label>：

| 指标 | 当前 | 对比版本 | 变化 |
|---|---:|---:|---:|
```

优先列变化绝对值最大的 8 到 12 个主要指标，变化用 `+1.4pp` / `-2.6pp`。

## 指标映射和取数

百分比表默认从 `rule_eval_report.json.summary.boolean_metrics` 取数，单元格格式为：

```text
<rate*100保留1位>% (<pass>/<total>)
```

预算数值分布从 `rule_eval_report.json.summary.numeric_metrics` 取 `avg`、`p50`、`p90`。

合并视图要按样本数加权：

- boolean 指标：把 standard/hard 的 `pass` 相加、`total` 相加后重新算 rate。
- numeric avg：按各 split 的 numeric 样本数加权；如果没有直接样本数，默认用该 split `summary.total`，并在报告中避免声称精确分位数。
- numeric p50/p90：不要合并估算；只在 standard/hard 分表展示。

常用中文指标名映射：

| 报告中文名 | JSON key | 来源 |
| --- | --- | --- |
| 硬通过 | `hard_pass` | boolean_metrics |
| JSON抽取 | `json_extract_ok` | boolean_metrics |
| Schema合法 | `schema_ok` | boolean_metrics |
| 城市正确 | `city_ok` | boolean_metrics |
| 日期范围 | `date_range_ok` | boolean_metrics |
| 天数 | `days_len_ok` | boolean_metrics |
| 每日日期 | `day_dates_ok` | boolean_metrics |
| 天气日期完整 | `weather_dates_ok` | boolean_metrics |
| day_index正确 | `day_index_ok` | boolean_metrics |
| 住宿类型 | `accommodation_type_ok` | boolean_metrics |
| 餐饮完整 | `meal_complete` | boolean_metrics |
| 餐饮具体化 | `meal_specific_ok` | boolean_metrics |
| 餐饮语义合法 | `meal_valid_semantics_ok` | boolean_metrics |
| 餐饮grounding | `meal_grounding_ok` | boolean_metrics |
| 景点数量 | `attraction_count_ok` | boolean_metrics |
| 景点grounding | `attraction_grounding_ok` | boolean_metrics |
| 中间住宿 | `middle_hotel_ok` | boolean_metrics |
| 无非法酒店名 | `invalid_hotel_name_ok` | boolean_metrics |
| 酒店grounding | `hotel_grounding_ok` | boolean_metrics |
| 酒店距离占位 | `hotel_distance_placeholder_ok` | boolean_metrics |
| 坐标对象 | `location_object_ok` | boolean_metrics |
| 交通预算非负 | `transportation_budget_nonnegative` | boolean_metrics |
| 天气匹配 | `weather_match` | boolean_metrics |
| 软通过 | `dpo_soft_pass` | boolean_metrics |
| 重算预算软通过 | `dpo_soft_recomputed_budget_pass` | boolean_metrics |
| 硬通过前置 | `hard_pass` | boolean_metrics |
| 景点多样性 | `attraction_diversity_ok` | boolean_metrics |
| 餐饮多样性 | `meal_diversity_ok` | boolean_metrics |
| 预算偏好贴合 | `budget_preference_aligned` | boolean_metrics |
| 重算预算贴合 | `recomputed_budget_fit_ok` | boolean_metrics |
| 预算合计一致 | `budget_consistent` | boolean_metrics |
| 预算算术一致 | `budget_arithmetic_consistent` | boolean_metrics |
| 预算关系一致 | `budget_relationship_ok` | boolean_metrics |
| 预算选品贴合 | `budget_selection_ok` | boolean_metrics |
| 预算档位贴合 | `budget_level_aligned` | boolean_metrics |
| 预算偏好贴合（软通过项） | `budget_preference_aligned` | boolean_metrics |
| 用户预算约束 | `budget_user_constraint_ok` | boolean_metrics |
| 声明预算未超 | `budget_within_user_budget` | boolean_metrics |
| 重算预算硬约束 | `recomputed_budget_hard_ok` | boolean_metrics |
| 重算预算贴合（重算软通过项） | `recomputed_budget_fit_ok` | boolean_metrics |
| 重算预算档位贴合 | `recomputed_budget_level_aligned` | boolean_metrics |
| 重算预算偏好贴合 | `recomputed_budget_preference_aligned` | boolean_metrics |
| 重算用户预算约束 | `recomputed_budget_user_constraint_ok` | boolean_metrics |
| 重算预算未超 | `recomputed_budget_within_user_budget` | boolean_metrics |
| 酒店预算关系 | `hotel_budget_relation_ok` | boolean_metrics |
| 酒店覆盖晚数 | `hotel_budget_covers_nights` | boolean_metrics |
| 景点预算/人数关系 | `attraction_budget_party_relation_ok` | boolean_metrics |
| 景点预算一致 | `attraction_budget_consistent` | boolean_metrics |
| 餐饮尺度 | `meal_cost_scale_ok` | boolean_metrics |
| 餐饮预算一致 | `meal_budget_consistent` | boolean_metrics |
| 重算总预算 | `recomputed_budget_total` | numeric_metrics |
| 重算人日预算 | `recomputed_budget_per_person_day` | numeric_metrics |

## 分 split 视图

分别写：

```markdown
## 标准集

- 数据：`training/data/planner/eval/records.jsonl`，200 条
```

和：

```markdown
## 困难集

- 数据：`training/data/planner/eval_hard/records.jsonl`，300 条
```

每个 split 固定包含：

- `### Hardpass 部分`
- `### Softpass 部分`
- `### 预算部分`
- `### 预算数值分布`
- `### 标准集 变化摘要` 或 `### 困难集 变化摘要`

分 split 的预算数值分布列：

- 重算总预算 avg
- 重算总预算 p50
- 重算总预算 p90
- 重算人日预算 avg
- 重算人日预算 p50
- 重算人日预算 p90

## 数据源

报告末尾写 `## 数据源`，用表格列每个模型的 standard/hard rule report 路径：

```markdown
| 版本 | 标准集报告 | 困难集报告 |
|---|---|---|
| 当前 <label> | `<path>` | `<path>` |
```

路径要指向 `rule_eval_report.json`，不要只指目录。

## 读数建议

最后写 `## 读数建议`，用编号列表告诉读者怎么解读。

必须提醒：

1. 读硬通过时只看 Hardpass 部分；预算合计类失败不要混进硬通过归因。
2. 读软通过时重点看 Softpass 部分里的景点多样性、餐饮多样性、预算偏好贴合和重算预算贴合。
3. Budget 部分用于解释预算问题，不要把每个预算诊断项都当成 hardpass/softpass 的组成项。
4. 对长期接近 0 或规则口径可疑的指标，明确它更像字段口径/规则口径问题，避免误导选型。
5. 用一句话给当前候选的真实取舍和下一步建议。

## 写作规则

- 使用中文指标名，例如“硬通过”“软通过”“餐饮grounding”“预算选品贴合”。
- 当前候选永远放第一列；上一版、上二版、历史强对照、baseline 依次向右。
- 所有百分比表都写成 `96.2% (481/500)`。
- 合并视图按样本数加权，不做简单平均。
- 不把 archive/旧 records 的结果和新 context 结果混成“当前主线”结论；如果必须引用，明确写成历史 reference。
- 表格多一点可以接受；最终报告宁可完整，也不要只给一句结论。
