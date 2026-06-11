#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/work/liweihan/wyf/helloagents-trip-planner}"
cd "${PROJECT_ROOT}"

PYTHON="${PYTHON:-${PROJECT_ROOT}/.venv-training-py311/bin/python3}"
MANAGER="${PROJECT_ROOT}/training/scripts/serving/manage_planner_service.py"
EVAL_PIPELINE="${PROJECT_ROOT}/training/scripts/eval/eval_pipeline.py"
FULL_REPORT="${PROJECT_ROOT}/training/scripts/planner/eval/generate_full_report.py"

MODEL_PATH="${MODEL_PATH:-${PROJECT_ROOT}/training/outputs/qwen25_7b/merged_dpo_260520_ps2400clean_ckpt138_for_closing_dpo}"
STANDARD_RECORDS="${STANDARD_RECORDS:-${PROJECT_ROOT}/training/data/planner/eval/records.jsonl}"
HARD_RECORDS="${HARD_RECORDS:-${PROJECT_ROOT}/training/data/planner/eval_hard/records.jsonl}"

RUN_GROUP="${RUN_GROUP:-dpo_260520_ckpt138_merged_gpu4_w10}"
MODEL_NAME="${MODEL_NAME:-dpo_260520_ckpt138_merged}"
API_MODEL="${API_MODEL:-trip-planner-dpo-260520-ckpt138-merged}"
EVAL_OUTPUT_DIR="${EVAL_OUTPUT_DIR:-${PROJECT_ROOT}/training/outputs/eval/by_model/${RUN_GROUP}}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/training/outputs/eval/logs/${RUN_GROUP}}"

GPU="${GPU:-4}"
PORT="${PORT:-4544}"
WORKERS="${WORKERS:-10}"
VLLM_MAXLEN="${VLLM_MAXLEN:-32768}"
VLLM_GPU_UTIL="${VLLM_GPU_UTIL:-0.85}"
READY_TIMEOUT="${READY_TIMEOUT:-900}"

EVAL_TEMPERATURE="${EVAL_TEMPERATURE:-0.2}"
EVAL_TIMEOUT="${EVAL_TIMEOUT:-900}"
EVAL_CONNECT_TIMEOUT="${EVAL_CONNECT_TIMEOUT:-10}"
EVAL_MAX_TOKENS="${EVAL_MAX_TOKENS:-0}"

mkdir -p "${EVAL_OUTPUT_DIR}" "${LOG_DIR}"

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

require_inputs() {
  [[ -x "${PYTHON}" ]] || { log "python not executable: ${PYTHON}"; return 2; }
  [[ -d "${MODEL_PATH}" ]] || { log "missing MODEL_PATH=${MODEL_PATH}"; return 2; }
  [[ -f "${MODEL_PATH}/model.safetensors.index.json" ]] || { log "MODEL_PATH does not look like a merged full model: ${MODEL_PATH}"; return 2; }
  [[ -f "${STANDARD_RECORDS}" ]] || { log "missing STANDARD_RECORDS=${STANDARD_RECORDS}"; return 2; }
  [[ -f "${HARD_RECORDS}" ]] || { log "missing HARD_RECORDS=${HARD_RECORDS}"; return 2; }
}

stop_service() {
  "${PYTHON}" "${MANAGER}" stop --port "${PORT}" --kill >/dev/null 2>&1 || true
}

cleanup() {
  local code=$?
  log "cleanup: stopping service on port ${PORT}"
  stop_service
  exit "${code}"
}
trap cleanup EXIT INT TERM

wait_service_ready() {
  local root_url="http://127.0.0.1:${PORT}"
  local base_url="${root_url}/v1"
  local deadline=$((SECONDS + READY_TIMEOUT))
  while (( SECONDS < deadline )); do
    if curl --noproxy "*" -fsS --max-time 5 "${root_url}/docs" >/dev/null 2>&1 || curl --noproxy "*" -fsS --max-time 5 "${base_url}/models" >/dev/null 2>&1; then
      log "service ready port=${PORT}"
      return 0
    fi
    sleep 10
  done
  log "service not ready after ${READY_TIMEOUT}s: port=${PORT}"
  return 1
}

start_service() {
  local serve_log="${LOG_DIR}/serve_${MODEL_NAME}_gpu${GPU}_port${PORT}.log"
  log "start vLLM model=${MODEL_NAME} gpu=${GPU} port=${PORT} path=${MODEL_PATH}"
  "${PYTHON}" "${MANAGER}" start \
    --port "${PORT}" \
    --variant base \
    --infer-backend vllm \
    --cuda-visible-devices "${GPU}" \
    --api-model-name "${API_MODEL}" \
    --model-path "${MODEL_PATH}" \
    --no-adapter \
    --vllm-maxlen "${VLLM_MAXLEN}" \
    --vllm-gpu-util "${VLLM_GPU_UTIL}" \
    --log-file "${serve_log}"
}

run_split() {
  local split="$1"
  local records="$2"
  local cmd=(
    "${PYTHON}" "${EVAL_PIPELINE}"
    --records "${records}"
    --model-name "${MODEL_NAME}_${split}"
    --api-model "${API_MODEL}"
    --base-url "http://127.0.0.1:${PORT}/v1"
    --output-dir "${EVAL_OUTPUT_DIR}"
    --workers "${WORKERS}"
    --temperature "${EVAL_TEMPERATURE}"
    --timeout "${EVAL_TIMEOUT}"
    --connect-timeout "${EVAL_CONNECT_TIMEOUT}"
    --resume
  )
  if [[ "${EVAL_MAX_TOKENS}" != "0" ]]; then
    cmd+=(--max-tokens "${EVAL_MAX_TOKENS}")
  fi
  log "eval ${split} model=${MODEL_NAME} workers=${WORKERS}"
  "${cmd[@]}"
}

write_full_report() {
  local standard_report="${EVAL_OUTPUT_DIR}/${MODEL_NAME}_standard/rule_eval_report.json"
  local hard_report="${EVAL_OUTPUT_DIR}/${MODEL_NAME}_hard/rule_eval_report.json"
  local report_dir="${EVAL_OUTPUT_DIR}/${MODEL_NAME}_report"
  log "full report ${MODEL_NAME}"
  "${PYTHON}" "${FULL_REPORT}" \
    --report "standard/${MODEL_NAME}=${standard_report}" \
    --report "hard/${MODEL_NAME}=${hard_report}" \
    --current-label "${MODEL_NAME}" \
    --standard-records "${STANDARD_RECORDS}" \
    --hard-records "${HARD_RECORDS}" \
    --output-dir "${report_dir}" \
    --comparison-slug "${MODEL_NAME}" \
    --inference-note "single full merged model eval; GPU=${GPU}; port=${PORT}; vLLM; maxlen=${VLLM_MAXLEN}; gpu_util=${VLLM_GPU_UTIL}; workers=${WORKERS}" \
    --summary-note "ckpt138 merged full model sanity eval on GPU${GPU}." \
    > "${LOG_DIR}/report_${MODEL_NAME}.log" 2>&1
}

main() {
  require_inputs
  log "begin run_group=${RUN_GROUP}"
  log "model_path=${MODEL_PATH}"
  log "records standard=${STANDARD_RECORDS} hard=${HARD_RECORDS}"
  stop_service
  start_service
  wait_service_ready
  run_split standard "${STANDARD_RECORDS}"
  run_split hard "${HARD_RECORDS}"
  write_full_report
  log "done run_group=${RUN_GROUP}"
}

main "$@"
