#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
LLAMAFACTORY_ROOT="${LLAMAFACTORY_ROOT:-${PROJECT_ROOT}/../LLaMA-Factory}"
VENV_BIN="${PROJECT_ROOT}/.venv-training-py311/bin"
OUTPUT_ROOT="${PROJECT_ROOT}/training/outputs/qwen25_7b"
OUTPUT_DIR="${OUTPUT_ROOT}/sft_260509_main_clean_cp2_legacy_b_r32_b32_lr8e5_ctx24576_20260509"
CURRENT_LOG="${OUTPUT_ROOT}/sft_260509_main_clean_cp2_legacy_b_2345_20260509_215302.log"
RESUME_CONFIG="${PROJECT_ROOT}/training/configs/qwen25_7b/sft_qwen25_7b_lora_260509_main_clean_cp2_legacy_b_resume28.yaml"
RESUME_LOG="${OUTPUT_ROOT}/sft_260509_main_clean_cp2_legacy_b_2345_resume28_save104_$(date +%Y%m%d_%H%M%S).log"
CURRENT_PGID="9367"
CHECKPOINT="${OUTPUT_DIR}/checkpoint-28"

export USE_V1=1
export FORCE_TORCHRUN=1
export CUDA_VISIBLE_DEVICES=2,3,4,5
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PATH="${VENV_BIN}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*"
}

wait_for_checkpoint_28() {
  while true; do
    if [[ -d "${CHECKPOINT}" ]] && grep -q "Checkpoint saved to ${CHECKPOINT}" "${CURRENT_LOG}"; then
      log "detected completed checkpoint-28: ${CHECKPOINT}"
      return 0
    fi
    local last_step
    last_step="$(grep -E 'epoch: .*step:' "${CURRENT_LOG}" | tail -1 || true)"
    log "waiting for checkpoint-28; latest: ${last_step:-no step yet}"
    sleep 30
  done
}

stop_current_train() {
  log "stopping current training process group -${CURRENT_PGID}"
  if kill -0 "-${CURRENT_PGID}" 2>/dev/null; then
    kill -TERM "-${CURRENT_PGID}" 2>/dev/null || true
    for _ in {1..40}; do
      if ! kill -0 "-${CURRENT_PGID}" 2>/dev/null; then
        log "current training process group stopped"
        return 0
      fi
      sleep 3
    done
    log "current training did not exit after TERM; sending KILL"
    kill -KILL "-${CURRENT_PGID}" 2>/dev/null || true
  else
    log "current training process group already gone"
  fi
}

start_resume_train() {
  log "starting resume with save_steps=104"
  log "config: ${RESUME_CONFIG}"
  log "resume log: ${RESUME_LOG}"
  (
    cd "${LLAMAFACTORY_ROOT}"
    "${VENV_BIN}/llamafactory-cli" train "${RESUME_CONFIG}"
  ) > "${RESUME_LOG}" 2>&1
  log "resume training finished"
}

main() {
  log "watcher started"
  wait_for_checkpoint_28
  stop_current_train
  start_resume_train
}

main "$@"
