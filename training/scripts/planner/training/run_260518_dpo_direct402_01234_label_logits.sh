#!/usr/bin/env bash
set -euo pipefail

export USE_V1=
unset USE_V1
export FORCE_TORCHRUN=1
export CUDA_VISIBLE_DEVICES=0,1,2,3,4
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export LLAMAFACTORY_DPO_LABEL_LOGITS_ONLY=1
export PATH=/work/liweihan/wyf/helloagents-trip-planner/.venv-training-py311/bin:${PATH}

cd /work/liweihan/wyf/LLaMA-Factory

echo "[run] $(date '+%F %T') starting fd600 planner-soft direct402 DPO on GPUs ${CUDA_VISIBLE_DEVICES}"
echo "[run] config: /work/liweihan/wyf/helloagents-trip-planner/training/configs/qwen25_7b/dpo_260518_fd600_planner_soft_direct402_r16_4epoch_z3offload_torchadam_5gpu01234.yaml"
echo "[run] LLAMAFACTORY_DPO_LABEL_LOGITS_ONLY=${LLAMAFACTORY_DPO_LABEL_LOGITS_ONLY}"

exec /work/liweihan/wyf/helloagents-trip-planner/.venv-training-py311/bin/llamafactory-cli train \
  /work/liweihan/wyf/helloagents-trip-planner/training/configs/qwen25_7b/dpo_260518_fd600_planner_soft_direct402_r16_4epoch_z3offload_torchadam_5gpu01234.yaml
