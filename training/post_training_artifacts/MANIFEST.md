# Manifest


> 历史镜像说明：这个目录是早期英文路径版产物归档，后续主入口已经迁到 `training/docs/后训练产物/`。新 DPO、Rerank 和最终结论不要再追加到这里；只把它当作旧路径兼容参考。
## 00 Overview

| Target | Source |
| --- | --- |
| `00_overview/reports/旅行助手后训练实战教程.md` | `training/docs/教程/旅行助手后训练实战教程.md` |
| `00_overview/reports/旅行助手后训练指标贡献补充.md` | `training/docs/教程/旅行助手后训练指标贡献补充.md` |
| `00_overview/reports/SFT阶段总结.md` | `training/docs/内部文档/SFT阶段总结.md` |
| `00_overview/reports/踩坑与经验总结.md` | `training/docs/教程/踩坑与经验总结.md` |

## Prompt Stage

| Step | Configs | Reports |
| --- | --- | --- |
| `01_prompt_ablation` | `training/scripts/planner/eval/build_prompt_ablation_records.py`, `build_context_ablation_records.py`, `refresh_eval_prompts.py`, `run_budget_revision_eval.py`, `generate_full_report.py` | `training/docs/内部文档/Prompt消融阶段总结.md` |
| `02_eval_sets_and_metrics` | `training/scripts/planner/eval/build_eval_set.py`, `rebuild_eval_contexts.py`, `rebase_eval_budgets.py`, `audit_relaxed_grounding.py` | `training/docs/内部文档/评测指标.md`, `training/docs/内部文档/新预算评估集重建与SFT预算审计.md`, `training/docs/内部文档/预算分档与实际数据预算对比.md`, `training/data/planner/eval*/评估集摘要.md`, `summary.json` |
| `03_historical_prompt_reports` | archived prompt/eval records | `training/archive/2026-05-05_v3_obsolete_prompt_eval_docs/`, `training/archive/2026-05-07_v3_obsolete_experiment_records/data_v3/`, and prompt/context/budget/root-report Markdown from `training/archive/2026-05-07_v3_obsolete_experiment_records/outputs_eval/` |

## SFT Stage

| Step | Configs | Reports |
| --- | --- | --- |
| `00_data_generation_and_audit` | `training/prompts/sft_generation.md`, `training/scripts/planner/data/*.py` | `training/docs/内部文档/SFT数据生成口径审核.md`, `training/docs/内部文档/SFT目标与边界.md`, `training/outputs/eval/audits/260508_sft_full_data_audit/`, `260509_v3_current_training_data_distribution_audit/`, `260509_main_clean_initial_sft_*` |
| `01_clean_sft` | `training/configs/qwen25_7b/sft_qwen25_7b_lora_260509_main_clean_*.yaml`, `training/configs/qwen25_7b/.serve_260510_valloss_gpu2_4422.yaml` | base/main-clean by-model rule eval reports and `training/outputs/eval/reports/260511_high_end_context_mainline/` |
| `02_usage700_replay` | `training/configs/qwen25_7b/sft_qwen25_7b_lora_260511_main_clean_plus_realbudget_usage700_from_lr6e5_lr2e5.yaml`, `.serve_qwen25_7b_replay_usage700_gpu4.yaml`, `run_260511_realbudget_usage_patch_from_lr6e5.sh` | usage700 by-model reports, `training/outputs/eval/reports/260511_usage700_followup_w10/`, `training/outputs/eval/comparisons/260511_usage700_followup_w10/` |
| `03_patch700_only` | `training/configs/qwen25_7b/sft_qwen25_7b_lora_260511_realbudget_usage_patch700_only_from_lr6e5_lr1e5.yaml`, `.serve_qwen25_7b_patch700_only_gpu5.yaml`, `run_260511_realbudget_usage_patch_from_lr6e5.sh` | patch700 by-model reports and `training/outputs/eval/comparisons/260511_usage700_followup_w10/` |
| `04_bestofn600_replay` | `training/configs/qwen25_7b/sft_qwen25_7b_lora_260512_replay_usage700_plus_bestofn600_from_replay_lr1e5_ep2.yaml`, `run_260512_bestofn_replay_from_usage700.sh`, `training/scripts/planner/bestofn/*` | `training/outputs/eval/reports/260512_bestofn_replay_extended_w10/` and ckpt96/ckpt192/final by-model reports |
| `05_bestofn1200_retry` | `training/configs/qwen25_7b/sft_qwen25_7b_lora_260513_replay_usage700_plus_bestofn1200_*.yaml`, `run_260513_bestofn1200_replay_from_final.sh`, `training/scripts/planner/bestofn/*` | `training/outputs/eval/reports/260513_bestofn1200_retry_checkpoints_w10/`, `260513_bestofn1200_vs_600final_w10/`, ckpt52/ckpt104/ckpt156/final by-model reports |
| `06_historical_mainline_sft_reports` | archived mainline SFT eval records | SFT docs from `training/archive/2026-05-05_v3_obsolete_prompt_eval_docs/`, `sft_cp2*` reports from `training/archive/2026-05-07_v3_obsolete_experiment_records/outputs_eval/`, and previous mainline reports from `training/outputs/eval/archive/260510_stale_current_eval_pre_realbudget/`, `260511_old_training_records_keep_baseline_v2b_lr8e5_valloss/`, `260511_pre_high_end_context_eval_outputs/` |

## Rerank Stage

| Step | Configs | Reports |
| --- | --- | --- |
| `01_multi_temperature_rerank` | `training/scripts/eval/eval_rerank_generations.py`, `eval_rule_metrics.py`, `eval_pipeline.py`, `eval_generate.py`, `eval_slice_report.py` | ckpt104/final1200/old600final standard/hard `rule_eval_report.md` and `rerank_merge_summary.json` |

## Excluded

- model checkpoints and adapter weights
- `generations.jsonl`
- vLLM service logs and long training logs
- private notes under `training/private-docs/`
