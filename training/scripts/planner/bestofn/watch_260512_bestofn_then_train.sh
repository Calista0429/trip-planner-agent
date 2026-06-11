#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON="${PROJECT_ROOT}/.venv-training-py311/bin/python3"
RUN_TAG="${RUN_TAG:-260512_anti_leak1200_vllm23_w8}"
OUT_DIR="${OUT_DIR:-${PROJECT_ROOT}/training/data/planner/bestofn/${RUN_TAG}}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/training/outputs/eval/logs/${RUN_TAG}_autotrain}"
LF_PREFIX="${LF_PREFIX:-trip_planner_bestofn_${RUN_TAG}}"
COMBINED_PREFIX="${COMBINED_PREFIX:-trip_planner_260513_replay_usage700_plus_bestofn1200}"
BESTOFN_OVERSAMPLE_RATIO="${BESTOFN_OVERSAMPLE_RATIO:-0.0}"
TRAIN_AFTER="${TRAIN_AFTER:-1}"
TRAIN_CUDA_VISIBLE_DEVICES="${TRAIN_CUDA_VISIBLE_DEVICES:-2,3,4,5}"
CHECK_INTERVAL_SECONDS="${CHECK_INTERVAL_SECONDS:-300}"

mkdir -p "${LOG_DIR}"

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*" | tee -a "${LOG_DIR}/watcher.log"
}

line_count() {
  local path="$1"
  if [[ -f "${path}" ]]; then
    wc -l < "${path}" | tr -d ' '
  else
    printf '0'
  fi
}

candidate_count() {
  find "${OUT_DIR}" -maxdepth 1 -name 'candidates_accel_gpu*.jsonl' -exec wc -l {} + 2>/dev/null \
    | awk '/total$/ {print $1; found=1} END {if (!found) print 0}'
}

postprocess_if_needed() {
  if [[ -s "${OUT_DIR}/bestofn_summary.json" ]]; then
    return 0
  fi
  local expected
  local current
  expected="$(line_count "${OUT_DIR}/prompts.jsonl")"
  current="$(candidate_count)"
  if [[ "${expected}" == "0" || "${current}" -lt "${expected}" ]]; then
    return 1
  fi

  log "Generation files are complete but summary is missing; running postprocess fallback."
  : > "${OUT_DIR}/candidates.jsonl"
  find "${OUT_DIR}" -maxdepth 1 -name 'candidates_accel_gpu*.jsonl' -print0 \
    | sort -z \
    | xargs -0 cat >> "${OUT_DIR}/candidates.jsonl"

  "${PYTHON}" training/scripts/planner/bestofn/select_best.py \
    --prompts "${OUT_DIR}/prompts.jsonl" \
    --candidates "${OUT_DIR}/candidates.jsonl" \
    --selected-output "${OUT_DIR}/selected.jsonl" \
    --summary-output "${OUT_DIR}/bestofn_summary.json" \
    --lf-sft-train "training/data/llamafactory/${LF_PREFIX}_sft_train.json" \
    --lf-sft-val "training/data/llamafactory/${LF_PREFIX}_sft_val.json" \
    --lf-pair-train "training/data/llamafactory/${LF_PREFIX}_pair_train.json" \
    --lf-pair-val "training/data/llamafactory/${LF_PREFIX}_pair_val.json" \
    --sft-train-name "${LF_PREFIX}_sft_train" \
    --sft-val-name "${LF_PREFIX}_sft_val" \
    --pair-train-name "${LF_PREFIX}_pair_train" \
    --pair-val-name "${LF_PREFIX}_pair_val" \
    --update-dataset-info \
    | tee "${LOG_DIR}/select_best_fallback.log"

  "${PYTHON}" training/scripts/planner/bestofn/render_review.py \
    --prompts "${OUT_DIR}/prompts.jsonl" \
    --candidates "${OUT_DIR}/candidates.jsonl" \
    --selected "${OUT_DIR}/selected.jsonl" \
    --summary "${OUT_DIR}/bestofn_summary.json" \
    --output "${OUT_DIR}/review.md" \
    | tee "${LOG_DIR}/render_review_fallback.log"
}

wait_for_bestofn() {
  local expected
  expected="$(line_count "${OUT_DIR}/prompts.jsonl")"
  while true; do
    postprocess_if_needed || true
    if [[ -s "${OUT_DIR}/bestofn_summary.json" ]]; then
      log "Best-of-N summary exists: ${OUT_DIR}/bestofn_summary.json"
      return 0
    fi
    local current
    current="$(candidate_count)"
    log "Waiting for Best-of-N: ${current}/${expected} prompt rows complete."
    sleep "${CHECK_INTERVAL_SECONDS}"
  done
}

build_training_data() {
  local sft_train="training/data/llamafactory/${LF_PREFIX}_sft_train.json"
  local sft_val="training/data/llamafactory/${LF_PREFIX}_sft_val.json"
  if [[ ! -s "${sft_train}" || ! -s "${sft_val}" ]]; then
    log "Missing Best-of-N SFT exports: ${sft_train} / ${sft_val}"
    return 1
  fi
  log "Building replay + Best-of-N training data."
  "${PYTHON}" training/scripts/planner/bestofn/build_replay_plus_bestofn_dataset.py \
    --bestofn-train "${sft_train}" \
    --bestofn-val "${sft_val}" \
    --output-prefix "${COMBINED_PREFIX}" \
    --oversample-ratio "${BESTOFN_OVERSAMPLE_RATIO}" \
    --seed 260513 \
    | tee "${LOG_DIR}/build_training_data.log"
}

stop_services_for_training() {
  log "Stopping vLLM services before training."
  for port in 4438 4439 4440 4441; do
    "${PYTHON}" training/scripts/serving/manage_planner_service.py stop --port "${port}" --kill --timeout 20 \
      | tee -a "${LOG_DIR}/watcher.log" || true
  done
}

start_training() {
  if [[ "${TRAIN_AFTER}" != "1" ]]; then
    log "TRAIN_AFTER=${TRAIN_AFTER}; skip training."
    return 0
  fi
  log "Starting fine-tuning on CUDA_VISIBLE_DEVICES=${TRAIN_CUDA_VISIBLE_DEVICES}."
  CUDA_VISIBLE_DEVICES="${TRAIN_CUDA_VISIBLE_DEVICES}" \
    MASTER_PORT="${MASTER_PORT:-29643}" \
    bash training/scripts/planner/training/run_260513_bestofn1200_replay_from_final.sh \
    | tee "${LOG_DIR}/training_driver.log"
}

main() {
  log "Watcher started for ${RUN_TAG}."
  wait_for_bestofn
  build_training_data
  stop_services_for_training
  start_training
  log "Watcher finished."
}

main "$@"
