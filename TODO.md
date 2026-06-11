# TODO

更新时间：2026-05-14

## 当前状态快照

- 线上协议已经稳定：`PlannerContext`、`party`、`budget_constraint`、酒店估价、住宿晚数、景点票价 hint、正负偏好拆分都已落地。
- 当前不启用粗糙 `route_hints`：Planner 只使用候选 POI 的 `district`、`address`、`location` 判断动线；真实路线时间留到高德路线 API 增强。
- 旧 SFT 已全量归档：不修旧数据、不复用旧 clean 子集、不导回 LLaMAFactory。
- baseline 硬协议能力已足够强，后续训练重点不再是 JSON/schema/每天景点数，而是预算合理性、餐饮 grounding、位置判断、酒店选择和偏好权衡。
- 进入 DPO 前先完成两件事：重建 realbudget-only SFT，并把 `lunch/dinner` 严格 grounded 到 `tool_snapshot.food_pois`。

## 近期行动项

- [ ] 开源教程补充图片
  - 给 `training/docs/教程/旅行助手后训练实战教程.md` 补几张读者一眼能看懂的图，不只堆指标。
  - 优先补三类：产品协议改造前后对照图、数据生成与审计流程图、Prompt/SFT/评测闭环指标变化图。
  - 图片尽量使用本地文件，统一放到教程同级图片目录或 `docs/images` 下，避免外链失效。

- [ ] 补充强化学习 / 偏好训练部分
  - 在开源教程中补一节 SFT 之后为什么还需要强化学习或偏好训练，说明它主要解决预算取舍、偏好满足、路线可执行性这类“规则过了但体验不稳”的问题。
  - 先梳理可用训练信号：规则指标、LLM judge、Best-of-N winner/loser、人工审计反馈和真实用户反馈。
  - 候选路线先写清楚即可：DPO/IPO 用于偏好对齐，GRPO 或 Agentic RL 作为后续探索，不和当前 SFT 阶段的固定评测结果混在一起比较。
  - 开始实验前先冻结 reward 口径、评测集和回放数据，避免每轮指标变化无法归因。

- [ ] realbudget-only SFT 数据重建执行
  - 顺序：smoke 20 -> 审计 -> 100 条 -> 审计 -> 1000 条。
  - 新数据不要写入旧 SFT 根目录；创建明确的 `<YYMMDD>_<run_slug>` 独立目录，通过审计后再导出 LLaMAFactory。
  - 外部强模型调用必须记录 `response.usage`，生成 run manifest，并默认关闭 thinking 或降低 reasoning，避免 token 失控。
  - 每轮审计关注：预算分档、teacher budget、候选池可达、POI/餐饮 grounding、错误分布、token 成本。

- [ ] realbudget-only SFT 通过后重新切分 train/val/eval
  - 按 `companion_type`、`budget_level`、`city_tier`、`travel_days`、`weather_bucket` 做分布审查。
  - `eval` / `eval_hard` 作为评估输入集保留；模型输出继续写到 `training/outputs/eval/by_model/<model>/<YYMMDD>_<run_slug>/`。

- [ ] 餐饮候选搜索第二档增强
  - 按每日景点区域、住宿区域、正向美食偏好和 `diet_avoid` 扩展餐饮搜索关键词。
  - 保证每个城市/区域至少有足够可用的本地菜、快餐/简餐、特色餐厅候选。
  - 对 `food_pois` 做去重、类型过滤和价格补齐，剔除非餐厅 POI；必要时按景点所在 district 追加餐饮候选。

- [ ] 餐饮 grounding 评估闭环
  - 线上和评估继续把 `lunch/dinner` 未命中 `food_pois` 作为硬错误。
  - 完成餐饮候选增强后重跑 baseline / eval_hard，重点看 `meal_specific_ok`、`meal_grounding_ok`、`meal_grounding_rate`。
  - 不让 DPO 学会接受 `附近餐厅`、`当地小吃`、`酒店晚餐`、`无` 等未 grounded 餐饮。

- [ ] 决定是否进入 DPO
  - 进入条件：realbudget-only SFT 数据审计通过，餐饮 grounding 不再是主要硬错误来源。
  - DPO 重点：预算合理性、可执行性、偏好满足、工具忠实、连贯性，而不是硬 schema 修复。

- [ ] 地图版结果页暴露的召回与路线增强
  - 当前状态：结果页已支持“全程地图 + 每日地图”第一版，能按天展示住宿、景点和餐饮 POI；最后一天无 `day.hotel` 时，前端会沿用最近一晚住处作为当天出发/取行李位置。
  - 后端召回问题：餐饮、住宿、景点候选还没有充分利用每日区域、住宿位置、用户偏好、预算档位和负向约束；前端地图已经暴露出候选缺坐标、模型漏复制 `meal.address/location`、部分真实 POI 不贴近当天动线等问题。
  - 后端下一步：把候选召回从“城市级关键词池”改成“日程区域感知召回”，必要时按当天景点 cluster/district 补餐饮和附近备选；保留 deterministic repair，用候选池回填模型漏掉的 `address/location`。
  - 前端路线问题：当前地图连线只是按计划点位顺序画折线，不是真实步行/驾车/公交路线；第一版可用于位置感知展示，但不能当作真实导航路线。
  - 前端下一步：接入真实路线服务后，按每天展示住宿 -> 早餐 -> 景点 -> 午餐 -> 景点 -> 晚餐 -> 住处的真实路线 polyline、分段耗时和交通方式；在路线不可用时明确降级为“点位连线”。

## 已完成：数据与后训练闭环

- [x] 启动 PlannerContext / SFT 数据主线
  - 历史结论：当前链路能跑通 SFT/DPO/评估，但暴露出人数、总预算、酒店价格、住宿晚数、预算账本和工具字段复制等协议问题。
  - 已完成：线上 PlannerContext 协议、后端 schema、Planner prompt 和前端请求体已经接入。
  - 原则：基于线上协议重新生成 SFT 数据，不继续在历史数据上补丁式训练。

- [x] 显式化人数和预算约束
  - 已完成：前后端请求和 PlannerContext 中加入 `party`，包含 adults/children/elders/total/companion_type。
  - 已完成：前后端请求和 PlannerContext 中加入 `budget_constraint`，统一总预算语义，避免模型把总预算误解成人均或每日预算。

- [x] 补齐酒店价格和住宿晚数账本规则
  - 当前问题：高德 `hotel_pois.cost` 经常为空，模型会自行估算同一酒店的单晚价格，导致候选之间出现 `180/250/400` 等不一致价格。
  - 已完成：按用户住宿类型、城市层级和酒店 POI 类型生成确定性的 `estimated_cost_hint`，并标记 `cost_source = "rule_estimated"`。
  - 已完成：`hotel.estimated_cost` 表示元/晚；N 天行程默认住宿 N-1 晚；Planner prompt 已要求 `budget.total_hotels` 覆盖住宿晚数。

- [x] 当前主线不启用粗路线 hint
  - 当前决策：不再把直线距离估算的 `route_hints` 喂给 Planner，避免半成品路线信号误导模型。
  - 已完成：PlannerContext 继续保留完整酒店/景点/餐饮候选，并把 `district`、`address`、`location` 给到大模型。
  - 当前策略：由大模型基于候选地址、区域和经纬度自行安排动线；真实路线时间增强进入远期 TODO。

- [x] 补齐热门景点票价画像表
  - 当前问题：高德景点 `cost` 覆盖率很低，天行旅游景区大全接口主要返回景区简介，也不直接返回门票价格。
  - 已完成：对 `request_count >= 5` 的 282 个高频景点统一用强模型估算成人基础票价，并接入 `backend/app/planner/attraction_price_table.json`。
  - 当前版本口径：全部标记为 `ticket_price_source = "llm_estimated"`，并写明这是训练预算用估价，不是官方/实时票价。
  - 训练规则：数据构造脚本把画像表转换成 `ticket_price_hint`；模型必须复制该 hint 到景点费用字段，并按 `party.total` 汇总 `budget.total_attractions`。

- [x] 拆分正向偏好和负向约束
  - 已完成：线上 PlannerContext 输出 `positive_preferences`、`negative_constraints`、`diet_positive`、`diet_avoid` 和 `traveler_constraints`。
  - 已完成：造数脚本在 `control_spec` 中同步落盘正向偏好、负向约束和饮食约束，便于后续审计与切片分析。
  - 训练目标：SFT 学习负向约束优先级，例如过敏/不吃/避免排队不能被正向偏好覆盖。

- [x] 对齐 request 生成阶段的预算档位
  - 当前问题：旧逻辑只按 `人均日预算 * 人数 * 天数` 生成总预算，没有纳入住宿类型、住宿晚数、交通方式和城市层级，导致部分 `standard` 请求预算虚高。
  - 已完成：造数脚本改为“非住宿人均日预算 + N-1晚住宿预算”的整趟总预算模型，并按城市层级和交通方式微调。
  - 已完成：强模型模拟用户请求 prompt 明确要求 `budget_constraint.amount` 与 `budget_level`、人数、天数和住宿类型匹配。
  - 已完成：造数链路加入 `budget_fit_policy`，按预算档位约束强模型输出的总花费区间；硬校验比 prompt 目标区间略宽，明显太省或超支的样本会重试。

- [x] 冻结 prompt baseline
  - 已完成：当前 no-route baseline 冻结为正式 baseline，替代旧的粗 `route_hints` 版本。
  - 主要规则指标：hard_pass 95.30%，JSON 可解析 99.33%，schema 通过 99.33%，attraction_count_ok 100.00%，budget_arithmetic_consistent 96.64%，weather_match 99.66%。
  - 产物：历史本地评测产物；当前公开入口见 `training/outputs/eval/reports/`。
  - 判断：当前 base + prompt 已足够强，后续不要把 SFT 主目标继续放在修 JSON/schema/每天景点数这类硬规则上。

- [x] 构建更难评估集 eval_hard
  - 已完成：冻结 300 条 hard 评估记录。
  - 目标：专门压测预算冲突、负向约束优先级、天气压力、动线可执行性、多人同行成本。
  - 当前最终 base 结果：hard_pass 95.30%，预算算术闭合 96.64%，满足进入 DPO 的硬门槛。
  - 剩余主要问题：合法计划里的预算使用、交通/位置判断、餐饮落地、酒店位置、偏好权衡质量不稳定。

- [x] 建立 baseline LLM judge 与问题画像
  - 已完成：用强模型对当前 baseline 跑 DPO 风格 LLM judge，评分维度包括偏好满足、可执行性、工具忠实、预算合理、连贯性、综合质量。
  - 已完成：强模型并发从 64 调整为 32，并加入 `--retry-failed` 失败队列重跑；no-route baseline 最终 judge 覆盖率 94.33%。
  - 当前 judge 均分：overall_quality 1.8834/5，budget_reasonableness 1.5442/5，practicality 2.1625/5，preference_satisfaction 2.4982/5。
  - 产物：历史本地评测产物；当前公开入口见 `training/outputs/eval/reports/`。
  - 判断：去掉粗路线 hint 后整体质量略升；baseline 的硬协议能力强，但真实旅行决策质量仍有明显 DPO 空间。

- [x] 修正餐饮占位和餐饮 grounding 漏评
  - 当前问题：模型会输出 `早餐推荐/午餐推荐/晚餐推荐` 这类占位餐饮，旧规则只检查三餐类型齐全，没有检查 meal.name 是否具体、是否命中 `food_pois`。
  - 已完成：Planner prompt 明确禁止餐饮占位词，要求 lunch/dinner 优先复制 `food_pois.name/address/location/meal_cost_hint`；早餐可用 `food_pois` 或酒店/民宿早餐。
  - 已完成：线上 `validate_trip_plan_shape()` 把餐饮占位词改成硬错误，触发重试。
  - 已完成：规则评估新增 `meal_specific_ok`、`meal_grounding_ok`、`meal_grounding_rate`，并纳入 `hard_pass`。
  - 严格餐饮重算结果：`meal_specific_ok=50.67%`，`meal_grounding_ok=35.23%`，旧 no-route 输出在新口径下 `hard_pass=33.56%`。
  - 产物：历史本地评测产物；当前公开入口见 `training/outputs/eval/reports/`。
  - 修正 prompt 后重跑 baseline：`meal_specific_ok=96.91%`，`meal_grounding_ok=58.42%`，说明占位餐饮基本压住，但 lunch/dinner 严格命中 `food_pois` 仍是主短板。
  - 新产物：历史本地评测产物；当前公开入口见 `training/outputs/eval/reports/`。
  - 当前协议：`lunch/dinner` 必须复制 `food_pois` 候选；不得输出 `附近餐厅/当地小吃/酒店晚餐/无` 等泛化或占位餐饮。
  - 下一步：先做餐饮候选搜索增强和餐饮 grounding 约束，再决定是否进入 DPO。

- [x] 修正酒店 distance 伪精确占位
  - 当前问题：旧 prompt 示例写了 `distance="距离景点2公里"`，模型大面积照抄，导致前端和训练数据出现看似精确但实际编造的酒店距离。
  - 已完成：Planner prompt 要求当前没有真实路线/距离工具时 `hotel.distance=""`，禁止编造“距离景点2公里”“距主要景点约X公里”等伪精确距离。
  - 已完成：线上 `validate_trip_plan_shape()` 把伪精确酒店距离作为硬错误，触发重试。
  - 已完成：规则评估新增 `hotel_distance_placeholder_ok`，并纳入 `hard_pass`。
  - 严格重算结果：旧 no-route 输出 `hotel_distance_placeholder_ok=3.36%`，说明旧输出里酒店 distance 基本不可用。
  - 产物：历史本地评测产物；当前公开入口见 `training/outputs/eval/reports/`。
  - 下一步：和餐饮修复一起重跑 no-route baseline。

- [x] 旧 SFT 数据全量归档
  - 当前决策：旧 `controlled`、`budget_supplement` 和此前派生的 clean/merged SFT 数据全部不再用于当前版本训练。
  - 原因：旧数据来自旧预算生成口径；即使局部审计为 clean，也不能代表整批数据符合新版 realbudget 训练目标。
  - 已完成：旧 SFT 目录和临时当前目录移入归档目录。
  - 已完成：LLaMAFactory 中旧 SFT 导出移入归档目录。
  - 已完成：旧全局入口已清理；当前 `training/data/llamafactory/dataset_info.json` 只保留明确训练入口，文件指向 `generated/`。
  - 说明：见训练数据归档说明。

- [x] eval 输出按模型和 run 时间整理
  - 已完成：`training/outputs/eval` 第一层只保留 `by_model/`、`comparisons/`、`audits/`、`logs/`、`README.md`、`runs_manifest.json`。
  - 新规范：单模型输出写入 `training/outputs/eval/by_model/<model>/<YYMMDD>_<run_slug>/`。
  - comparison、数据审计和日志分别进入 `comparisons/`、`audits/`、`logs/`。
  - 已迁移：34 个单模型 run、8 个 comparison、12 个 audit、2 个日志集合。
  - 说明：`training/outputs/eval/README.md`。

- [x] 现实预算 500 条评估结论归档
  - 已完成：整理 base 与若干历史 checkpoint 在 200 条 standard + 300 条 hard 上的对比结论。
  - 报告：历史本地评测产物；当前公开入口见 `training/outputs/eval/reports/`。
  - 主要结论：旧 SFT checkpoint 相比 base 在现实预算指标上明显更强。
  - 定性：这只是旧 SFT checkpoint 的参考对照，不改变旧 SFT 全量归档、不混用 clean 子集的决策。

- [x] 加强餐饮候选搜索与餐饮 grounding
  - 当前问题：修正 prompt 后，餐饮占位明显减少，但模型仍会输出 `某景点附近餐厅`、`当地小吃`、`酒店晚餐`、`无` 或自行编造餐厅名，`meal_grounding_ok` 只有 58.42%。
  - 协议约束：`lunch/dinner` 必须从 `tool_snapshot.food_pois` 选择并复制候选字段；早餐可使用 `food_pois` 或合法住宿早餐 fallback。
  - 已完成第一档：餐饮搜索从单一关键词列表升级为分桶召回，包含 `food_base`、`food_preference`、`food_diet`、`food_companion`、`food_budget`。
  - 已完成第一档：`food_pois` 增加 `meal_roles`、`cuisine_tags`、`diet_tags`、`avoid_risk_keywords`、`price_level`、`source_bucket` 等字段，便于 Planner 选择和后续审计。
  - 已完成第一档：默认餐饮候选上限从 12 提升到 32；每个分桶最多保留 8 条，避免上下文无限膨胀。
  - 工程方向：按每日景点区域、住宿区域、正向美食偏好和 `diet_avoid` 扩展餐饮搜索关键词，保证每个城市/区域至少有足够可用的本地菜、快餐/简餐、特色餐厅候选。
  - 工程方向：对 `food_pois` 做去重、类型过滤和价格补齐，剔除非餐厅 POI；必要时按景点所在 district 追加餐饮候选。
  - 校验方向：线上和评估继续把 lunch/dinner 未命中 `food_pois` 作为硬错误；不要让 DPO 学会接受未 grounded 餐饮。

- [x] realbudget-only SFT 数据重建方案确定
  - 当前决策：旧 SFT 全部归档，不再修旧数据，也不复用旧 clean 子集。
  - 目标：重新按真实预算分布造一版 SFT，先形成高置信预算主训练池，再决定是否与 DPO 主线配合。
  - 前置必做：外部强模型调用记录 `response.usage`，生成 run manifest，默认关闭 thinking 或降低 reasoning，避免再次 token 失控。
  - 执行顺序：smoke 20 -> 审计 -> 100 条 -> 审计 -> 1000 条。
  - 每轮审计：预算分档、teacher budget、候选池可达、POI/餐饮 grounding、错误分布、token 成本。
  - 输出规范：新数据不要写入旧 SFT 根目录；应创建新的 run 目录并在通过审计后再导出 LLaMAFactory。

- [x] 建立 SFT 数据审计和分类流程
  - 已完成：对 active raw SFT 做全量分类，输出 `usable_budget_clean`、`repair_request_rebudget`、`repair_teacher_regen`、`nonbudget_only`、`drop_or_full_regen` 等类别。
  - 已完成：识别旧数据生成口径问题，并据此将全部旧 SFT 归档。
  - 审计产物已归档在评测审计目录。
  - 后续新 realbudget SFT 仍复用这套审计思路，但不能复用旧数据。

- [x] 重新切分 train/val/eval 策略确定
  - 旧 SFT 已归档，不再切分。
  - 新 realbudget SFT 生成后再按 companion_type、budget_level、city_tier、travel_days、weather_bucket 等控制变量做分布审查。
  - eval/eval_hard 作为评估输入集保留；模型输出统一按 `training/outputs/eval/by_model/<model>/<YYMMDD>_<run_slug>/` 保存。

## 远期增强：真实业务能力与产品质感

- [ ] route_hints 接入高德路线 API
  - 当前主线已停用粗糙的 `haversine_estimated` route_hints，只让 Planner 使用候选 POI 的 `district/address/location` 自行判断动线。
  - 后续方向：只对少量必要候选调用高德路线 API，生成可信 `route_hints`，并缓存结果，避免 QPS 和上下文长度失控。
  - 酒店真实距离也放在这条增强里：当前没有真实路线/距离工具时，`hotel.distance` 必须留空，不能让模型编“距离景点2公里”；后续由高德路线 API 按酒店到当日首个/主要景点计算真实距离或耗时。

- [ ] OTA 酒店实时价格增强
  - 背景：真实酒店价格依赖入住日期、离店日期、人数、房间数、币种、税费和取消政策，地图 POI API 很难直接给出可用价格。
  - 后续方向：调研并可选接入 Amadeus / Expedia Rapid / Booking 第三方接口，把 OTA live rate 写入 `estimated_cost_hint`，并标记 `cost_source = "ota_live_rate"`。
  - 注意：这不是当前版本主线；个人开发阶段先使用规则估价，保证预算协议稳定。

- [ ] 高预算候选池增强：高端餐饮、体验和酒店
  - 背景：当前 `premium` 评估样本已按候选池可达预算 100% 重标，但部分样本只是刚刚可达，模型一旦没有选到最高价候选就容易预算利用不足。
  - 后续方向：补强高端酒店候选、黑珍珠/米其林/精致餐厅候选，以及演出、游船、温泉、主题乐园、度假区等高价体验候选。
  - 评估目标：补强后重新审计 `high_budget_ratio`，从“刚好 >= 1.0”提升到多数高预算样本 `>= 1.1`，给模型留下真实选择余量。
  - 注意：这是检索侧增强，不作为当前 SFT 或评估集重标的阻塞项。

- [ ] 景区开放时间和闭馆日增强
  - 背景：真实旅行中景区闭馆、夜间不可入园、临时关闭会直接影响可执行性。
  - 后续方向：为景点候选补 `opening_hours`、`closed_days`、`last_entry_time`，并在后置校验里检查当天是否可游览。
  - 注意：不进入当前主线，避免协议一次性过重。

- [ ] 景区预约和余票状态增强
  - 背景：热门景点可能需要预约，且节假日余票会影响实际可行性。
  - 后续方向：为候选补 `reservation_required`、`availability_status`、`availability_source`。
  - 注意：当前阶段只做路线时间、人数和预算，预约状态先作为真实业务增强。

- [ ] 更细粒度票价人群增强
  - 背景：真实票价常区分成人、学生、儿童、老人、军人等。
  - 后续方向：把热门景点票价画像从成人全价扩展为 `ticket_price_profile_by_traveler_type`。
  - 注意：当前口径仍按成人全价乘 `party.total`，保证预算账本简单稳定。

- [ ] 高频景点票价人工/官方核验
  - 背景：当前票价表已经能支撑预算训练，但来源仍是强模型估算。
  - 后续方向：把 TOP 高频景点逐步人工核验或接入官网/OTA/官方小程序票价，升级为 `manual_verified`。
  - 注意：这不阻塞当前 SFT 主线。

- [ ] 正负偏好约束抽取升级为规则 + LLM parser 双轨
  - 背景：当前使用规则抽取正向偏好、负向约束、饮食忌口和同行人约束，稳定可审计，适合训练数据主线。
  - 后续方向：保留规则作为硬约束解析器，再增加 LLM parser 处理更复杂的自然语言偏好，例如“别太网红但也不要太冷门”“想吃本地菜但不想排队太久”。
  - 冲突策略：规则结果优先，LLM parser 只能补充软偏好，不能覆盖过敏、忌口、行动不便等硬约束。

## 已完成归档：前后端体验

- [x] 前端请求体升级
  - 已完成：表单显式提交 `party` 和 `budget_constraint`。
  - 已完成：交通方式、住宿偏好和旅行偏好标签扩展到更真实的使用场景。

- [x] 首页和结果页视觉统一
  - 已完成：首页和结果页统一为蓝白灰、细边框、轻阴影的产品风格。
  - 已完成：结果页旧紫色渐变、大圆角、玩具感样式已移除。

- [x] 天气展示修正
  - 已完成：天气图标按文本判断晴、云、雨、雷、雪、雾霾、未知，不再固定太阳图标。
