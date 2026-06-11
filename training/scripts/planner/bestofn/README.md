# Best-of-N Pipeline

Best-of-N is the first RL-adjacent step for the current planner. It samples multiple TripPlan
candidates for the same `PlannerContext`, scores them with the existing rule
evaluator, and exports the best response for later SFT, SimPO, DPO, or GRPO
smoke runs.

Recommended smoke:

```bash
.venv-training-py311/bin/python3 training/scripts/planner/bestofn/build_prompts.py \
  --records training/data/planner/dpo/prompt_source/records.jsonl \
  --output training/data/planner/bestofn/260511_smoke20/prompts.jsonl \
  --limit 20 \
  --shuffle

.venv-training-py311/bin/python3 training/scripts/planner/bestofn/generate_candidates.py \
  --prompts training/data/planner/bestofn/260511_smoke20/prompts.jsonl \
  --output training/data/planner/bestofn/260511_smoke20/candidates.jsonl \
  --base-url http://127.0.0.1:4396/v1 \
  --api-model trip-planner-sft \
  --spec t02:0.2:1 \
  --spec t05:0.5:2 \
  --spec t08:0.8:1 \
  --workers 1 \
  --resume

.venv-training-py311/bin/python3 training/scripts/planner/bestofn/select_best.py \
  --prompts training/data/planner/bestofn/260511_smoke20/prompts.jsonl \
  --candidates training/data/planner/bestofn/260511_smoke20/candidates.jsonl \
  --selected-output training/data/planner/bestofn/260511_smoke20/selected.jsonl \
  --lf-sft-train training/data/llamafactory/generated/trip_bestofn_260511_smoke20_sft_train.json \
  --lf-sft-val training/data/llamafactory/generated/trip_bestofn_260511_smoke20_sft_val.json \
  --lf-pair-train training/data/llamafactory/generated/trip_bestofn_260511_smoke20_pair_train.json \
  --lf-pair-val training/data/llamafactory/generated/trip_bestofn_260511_smoke20_pair_val.json
```

Selection uses a conservative reward:

- hard protocol items are heavily penalized when false;
- `sft_hard_pass` is preferred whenever any candidate passes it;
- soft rewards include recomputed budget fit, budget relationship, meal cost
  scale, meal diversity, attraction diversity, and user budget constraints.

Do not use `eval` or `eval_hard` records as training prompts. Keep those frozen
for final comparison.
