#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
LLAMAFACTORY_ROOT="${LLAMAFACTORY_ROOT:-${PROJECT_ROOT}/../LLaMA-Factory}"
VENV_BIN="${PROJECT_ROOT}/.venv-training-py311/bin"
OUTPUT_ROOT="${PROJECT_ROOT}/training/outputs/qwen25_7b"
CONFIG="${PROJECT_ROOT}/training/configs/qwen25_7b/sft_qwen25_7b_lora_260509_main_clean_cp2_legacy_b.yaml"
TRAIN_LOG="${OUTPUT_ROOT}/sft_260509_main_clean_cp2_legacy_b_2345_$(date +%Y%m%d_%H%M%S).log"

export USE_V1=1
export FORCE_TORCHRUN=1
export CUDA_VISIBLE_DEVICES=2,3,4,5
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PATH="${VENV_BIN}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*"
}

wait_for_gpus() {
  local max_used_mib="${1:-2048}"
  while true; do
    local used
    used="$(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | awk -F, '$1 ~ /^[[:space:]]*[2345]$/ {gsub(/[[:space:]]/, "", $2); print $1 ":" $2}')"
    local busy=0
    while read -r row; do
      [[ -z "${row}" ]] && continue
      local value="${row##*:}"
      if (( value > max_used_mib )); then
        busy=1
      fi
    done <<< "${used}"
    if (( busy == 0 )); then
      log "GPU 2/3/4/5 look free enough; starting CP=2 x DP=2 training."
      return 0
    fi
    log "GPU 2/3/4/5 still busy; memory.used MiB: ${used//$'\n'/, }. Waiting 60s."
    sleep 60
  done
}

main() {
  mkdir -p "${OUTPUT_ROOT}"
  log "driver started"
  log "config: ${CONFIG}"
  log "train log: ${TRAIN_LOG}"
  log "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}; dist is cp_size=2 over world size 4"
  wait_for_gpus 2048
  (
    cd "${LLAMAFACTORY_ROOT}"
    "${VENV_BIN}/llamafactory-cli" train "${CONFIG}"
  ) > "${TRAIN_LOG}" 2>&1
  log "training finished"
}

main "$@"
