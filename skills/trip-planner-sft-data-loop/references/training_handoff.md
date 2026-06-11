# Training Handoff

这份参考用于数据 loop 完成后的训练前交接。它不负责启动训练，也不替代训练 skill；只帮助判断一批已审计、已校验的 Planner SFT 数据应该如何进入下一步训练候选。

## 什么时候读取

- 用户问“这批数据接下来怎么训”。
- 用户问“整集合起来训，还是从 checkpoint 继续训”。
- 用户问预算补丁数据能不能单独训练。
- 用户担心 LLaMAFactory 数据合并、`.gitignore`、中间 checkpoint 或存储空间。

## 先判断数据类型

训练建议取决于数据来源和意图：

- 主数据：普通 `controlled` / realbudget 主训练数据，覆盖广泛 planner 行为。
- 预算补丁：`budget_supplement` 预算利用型数据，通常全是 soft 预算，prompt 会要求尽量用足预算。
- 诊断数据：为了测某个能力上限或 failure mode 专门生成，不一定适合作为部署候选。
- 修复数据：针对某个错误切片生成，通常需要 replay 旧主数据以防遗忘。

如果是 `budget_supplement`：

- 不建议只用这批数据训练最终模型；它的信号很强，可能让模型学成“soft 预算总要花满”。
- 优先作为 targeted supplement 混进旧主训练集，做 replay 微调。
- 可以额外跑 patch-only 诊断实验，但应标注“不作为首选部署候选”。

## 训练数据组织建议

最稳妥的默认方案：

1. 保留旧主训练集 train/val。
2. 把 `usable_budget_clean` 预算补丁 train/val 合并进去。
3. train/val 都显式写出新的 LLaMAFactory JSON/YAML，避免覆盖旧数据。
4. 写一个 manifest，记录每个源文件路径、行数、输出行数和去重结果。
5. 对新 train/val 都跑 `validate_trip_plan.py --sft`，要求 `failed=0`。

合并时注意：

- 不要把 raw run 自带的 `llamafactory_train.json` 直接当最终训练集，除非它已经通过审计/分类。
- 不要把 `usable_budget_candidate_tight` 和 `usable_budget_clean` 混成同一主口径，除非用户明确接受候选偏紧风险。
- 如果需要精确 comfortable/premium 数量，先在生成阶段分档跑，合并阶段不要靠随机抽样补救。

## 从哪继续训

数据补丁场景一般优先顺序：

1. 从当前 best LoRA adapter warm-start，使用旧主数据 + 新补丁 replay 微调。
2. 若要看补丁上限，再从同一 adapter 跑 patch-only 诊断实验。
3. 只有当 replay 实验有效且要做最终复现实验时，再考虑从 base 重新跑完整混合训练。

如果项目只有导出的 LoRA adapter，而没有完整 optimizer checkpoint：

- 使用 `adapter_name_or_path` warm-start。
- 不要写成 `resume_from_checkpoint`，除非目录里确实是完整训练 checkpoint。

## 存储和 checkpoint

用户存储紧张时，默认不要保存中间 checkpoint：

- 不设置 `save_steps`。
- 不设置 `save_epochs`。
- 不设置 `save_ckpt_as_hf: true`。
- 只保留最终 LoRA adapter 和训练日志。

代价是中断后不能从中间 step 恢复，只能重跑本轮短训。对于小步补丁微调通常可以接受。

生成或合并出的 LLaMAFactory 大 JSON 通常应进入 `.gitignore`。需要保留可复现信息时，保留小的 YAML 配置、manifest、脚本和审计报告，不把大 JSON 默认纳入 git。

## 推荐汇报格式

训练前 handoff 至少汇报：

- 数据类型：主数据、预算补丁、诊断数据或修复数据。
- 源数据路径、train/val 行数、去重情况和 schema 校验结果。
- 建议训练策略：replay 混合、patch-only 诊断、还是完整重训。
- warm-start 来源：base、LoRA adapter，或完整 checkpoint。
- 主要超参建议：学习率、epoch、是否保存中间 checkpoint。
- 存储风险：预计新增数据大小、最终 adapter 大小、中间 checkpoint 是否关闭。
- 评测护栏：旧 standard/hard、真实预算 hard、普通 soft 预算反退化检查。
