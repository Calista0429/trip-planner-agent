# Attraction Price Assets

更新时间：2026-05-12

景点票价目录按用途分层，避免审核报告、快照和过程产物混在一起。

```text
attraction_prices/
├── reports/       # 可读审核报告和估算说明
├── snapshots/     # 小体积 JSON 快照，可用于人工审核或合并到后端票价表
└── generated/     # ignored，候选 JSONL、估价 JSONL、运行日志
```

## 当前快照

- `snapshots/attraction_price_table_todo.json`：缺价景点待补模板。
- `snapshots/request_count_ge5_price_table_review_draft.json`：高频景点分桶后的 review draft。
- `snapshots/request_count_ge5_attraction_price_table_llm_estimated.json`：强模型估算票价表快照。

## 脚本入口

- `training/scripts/planner/pricing/collect_attraction_candidates.py`
- `training/scripts/planner/pricing/bucket_attraction_price_candidates.py`
- `training/scripts/planner/pricing/estimate_attraction_prices_with_llm.py`

估算结果只用于训练预算账本，不代表官方或实时票价。线上使用前需要人工审核并合并到 `backend/app/planner/attraction_price_table.json`。
