# 用户画像生成目标

用 DeepSeek 生成多样化的中文旅行用户画像。画像用于后续生成 `TripRequest`，不是最终训练输出。

每条画像至少覆盖：

- 预算：`budget_level`、`daily_budget`
- 节奏：`pace`
- 住宿：`hotel_preference`
- 饮食：`diet_limit`
- 兴趣：`interests`
- 避雷：`avoid`
- 同行人：`companion`

画像可以由 AI 合成，不需要真实用户数据。
