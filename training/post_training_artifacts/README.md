# Planner Post-Training Artifacts


> 历史镜像说明：这个目录是早期英文路径版产物归档，后续主入口已经迁到 `training/docs/后训练产物/`。新 DPO、Rerank 和最终结论不要再追加到这里；只把它当作旧路径兼容参考。
这个目录是旅行助手后训练阶段的集中归档，按阶段和实验步骤整理配置、脚本口径和评估报告。入口文档对应 `training/docs/教程/旅行助手后训练指标贡献补充.md` 和 `training/docs/教程/旅行助手后训练实战教程.md`。

收录原则：

- `configs/` 放训练 YAML、serve YAML、评估/数据生成脚本等可复现实验口径。
- `reports/` 放 Markdown 评估报告、摘要 JSON、审计报告和小体积指标文件。
- 不放模型权重、`generations.jsonl`、大训练产物、服务日志和私有草稿。

## 目录

| 目录 | 内容 |
| --- | --- |
| `00_overview/` | 后训练教程、指标贡献补充、SFT 阶段总结、踩坑与经验总结。 |
| `prompt_stage/01_prompt_ablation/` | Prompt 消融阶段报告，以及构建/刷新 prompt eval 的脚本口径。 |
| `prompt_stage/02_eval_sets_and_metrics/` | standard/hard 评估集说明、评测指标、预算口径和评估集构建脚本。 |
| `prompt_stage/03_historical_prompt_reports/` | 归档目录里的历史 prompt 报告记录，包括早期 V3 prompt、context ablation、预算 prompt、A/C/D 消融和 self-check。 |
| `sft_stage/00_data_generation_and_audit/` | SFT 数据生成、清洗、预算审计、分布审计和目标边界。 |
| `sft_stage/01_clean_sft/` | clean SFT/main-clean lr6e-5/lr8e-5 配置，base 与 main-clean 评估报告。 |
| `sft_stage/02_usage700_replay/` | usage700 replay 配置、serve 配置、by-model 评估和横向对比报告。 |
| `sft_stage/03_patch700_only/` | patch700-only 配置、serve 配置、by-model 评估和 usage700/patch700 对比。 |
| `sft_stage/04_bestofn600_replay/` | Best-of-N 600 replay 训练配置、Best-of-N 数据脚本、ckpt96/ckpt192/final 评估。 |
| `sft_stage/05_bestofn1200_retry/` | Best-of-N 1200 retry 配置、ckpt52/ckpt104/ckpt156/final 评估与 600 final 对比。 |
| `sft_stage/06_historical_mainline_sft_reports/` | 归档目录里的早期主线 SFT 报告记录，包括 cp2/v2a/v2b、realbudget、main-clean step/final 和 valloss 对比。 |
| `rerank_stage/01_multi_temperature_rerank/` | 多温度候选 + 规则 rerank 脚本口径，以及 ckpt104/final1200/old600final 评估。 |

## 使用建议

先读 `00_overview/reports/旅行助手后训练指标贡献补充.md`，再按阶段进入子目录看配置和报告。每个步骤的来源路径见 `MANIFEST.md`。

本目录集中整理 prompt 报告记录、主线 SFT 报告记录和最新 rerank 报告；不把无关 archive 全量搬入。
