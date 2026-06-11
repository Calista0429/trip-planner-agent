#!/usr/bin/env bash
set -euo pipefail

export USE_V1=
unset USE_V1
export FORCE_TORCHRUN=1
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5
export MASTER_PORT="${MASTER_PORT:-29659}"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export LLAMAFACTORY_DPO_LABEL_LOGITS_ONLY=1
export PATH=/work/liweihan/wyf/helloagents-trip-planner/.venv-training-py311/bin:${PATH}

CONFIG=/work/liweihan/wyf/helloagents-trip-planner/training/configs/qwen25_7b/dpo_260518_core1418_plus_direct402_from_ckpt25_r16_4epoch_ctx24576_z3nooffload_label_logits_6gpu012345.yaml

cd /work/liweihan/wyf/LLaMA-Factory

echo "[run] $(date '+%F %T') starting core1418+direct402 DPO continuation on GPUs ${CUDA_VISIBLE_DEVICES}"
echo "[run] config: ${CONFIG}"
echo "[run] MASTER_PORT=${MASTER_PORT}"
echo "[run] LLAMAFACTORY_DPO_LABEL_LOGITS_ONLY=${LLAMAFACTORY_DPO_LABEL_LOGITS_ONLY}"

exec /work/liweihan/wyf/helloagents-trip-planner/.venv-training-py311/bin/llamafactory-cli train "${CONFIG}"
