#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
LLAMAFACTORY_ROOT="${LLAMAFACTORY_ROOT:-${PROJECT_ROOT}/../LLaMA-Factory}"
VENV_BIN="${PROJECT_ROOT}/.venv-training-py311/bin"
OUTPUT_ROOT="${PROJECT_ROOT}/training/outputs/qwen25_7b"
LOG_DIR="${OUTPUT_ROOT}/run_logs"
CONFIG="${PROJECT_ROOT}/training/configs/qwen25_7b/sft_qwen25_7b_lora_260512_replay_usage700_plus_bestofn600_from_replay_lr1e5_ep2.yaml"
RUN_NAME="sft_260512_replay_usage700_plus_bestofn600_from_replay_lr1e5_ep2"

export USE_V1=1
export FORCE_TORCHRUN=1
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3}"
export MASTER_PORT="${MASTER_PORT:-29642}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export PATH="${VENV_BIN}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*"
}

wait_for_gpus() {
  local max_used_mib="${1:-2048}"
  local gpu_regex
  gpu_regex="$(printf '%s\n' "${CUDA_VISIBLE_DEVICES}" | tr ',' '\n' | awk '{gsub(/[[:space:]]/, ""); if ($0 != "") print $0}' | paste -sd'|' -)"
  while true; do
    local used
    used="$(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | awk -F, -v gpu_regex="^(${gpu_regex})$" '{gsub(/[[:space:]]/, "", $1); gsub(/[[:space:]]/, "", $2); if ($1 ~ gpu_regex) print $1 ":" $2}')"
    local busy=0
    while read -r row; do
      [[ -z "${row}" ]] && continue
      local value="${row##*:}"
      if (( value > max_used_mib )); then
        busy=1
      fi
    done <<< "${used}"
    if (( busy == 0 )); then
      log "GPU ${CUDA_VISIBLE_DEVICES} look free enough; starting CP=2 training."
      return 0
    fi
    log "GPU ${CUDA_VISIBLE_DEVICES} still busy; memory.used MiB: ${used//$'\n'/, }. Waiting 60s."
    sleep 60
  done
}

main() {
  mkdir -p "${LOG_DIR}"
  local train_log="${LOG_DIR}/${RUN_NAME}_$(date +%Y%m%d_%H%M%S).log"
  log "driver started"
  log "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}; MASTER_PORT=${MASTER_PORT}"
  log "config: ${CONFIG}"
  log "train log: ${train_log}"
  wait_for_gpus 2048
  (
    cd "${LLAMAFACTORY_ROOT}"
    "${VENV_BIN}/llamafactory-cli" train "${CONFIG}"
  ) > "${train_log}" 2>&1
  log "finished ${RUN_NAME}"
}

main "$@"
