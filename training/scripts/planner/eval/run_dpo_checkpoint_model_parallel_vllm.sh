#!/usr/bin/env bash
set -Eeuo pipefail

# Model-parallel checkpoint evaluation:
# one checkpoint per GPU, one vLLM service per GPU, full standard+hard eval per checkpoint.
# Runs checkpoints in batches of len(GPUS), then stops all services before the next batch.

PROJECT_ROOT="${PROJECT_ROOT:-/work/liweihan/wyf/helloagents-trip-planner}"
cd "${PROJECT_ROOT}"

PYTHON="${PYTHON:-${PROJECT_ROOT}/.venv-training-py311/bin/python3}"
MANAGER="${PROJECT_ROOT}/training/scripts/serving/manage_planner_service.py"
EVAL_PIPELINE="${PROJECT_ROOT}/training/scripts/eval/eval_pipeline.py"
FULL_REPORT="${PROJECT_ROOT}/training/scripts/planner/eval/generate_full_report.py"

TRAIN_OUTPUT_DIR="${TRAIN_OUTPUT_DIR:-${PROJECT_ROOT}/training/outputs/qwen25_7b/dpo_260518_fd600_planner_soft_direct402_r16_4epoch_z3offload_torchadam_5gpu01234}"
BASE_MODEL_PATH="${BASE_MODEL_PATH:-${PROJECT_ROOT}/training/outputs/qwen25_7b/merged_sft_260516_final1200_for_dpo}"
STANDARD_RECORDS="${STANDARD_RECORDS:-${PROJECT_ROOT}/training/data/planner/eval/records.jsonl}"
HARD_RECORDS="${HARD_RECORDS:-${PROJECT_ROOT}/training/data/planner/eval_hard/records.jsonl}"

RUN_GROUP="${RUN_GROUP:-dpo_260518_fd600_planner_soft_direct402_ckpt_model_parallel_2345_w10}"
MODEL_NAME_PREFIX="${MODEL_NAME_PREFIX:-dpo_260518_fd600_planner_soft_direct402}"
EVAL_OUTPUT_DIR="${EVAL_OUTPUT_DIR:-${PROJECT_ROOT}/training/outputs/eval/by_model/${RUN_GROUP}}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/training/outputs/eval/logs/${RUN_GROUP}}"

GPUS_CSV="${GPUS_CSV:-2,3,4,5}"
PORTS_CSV="${PORTS_CSV:-4522,4523,4524,4525}"
WORKERS="${WORKERS:-10}"
VLLM_MAXLEN="${VLLM_MAXLEN:-32768}"
VLLM_GPU_UTIL="${VLLM_GPU_UTIL:-0.85}"
READY_TIMEOUT="${READY_TIMEOUT:-900}"

EVAL_TEMPERATURE="${EVAL_TEMPERATURE:-0.2}"
EVAL_TIMEOUT="${EVAL_TIMEOUT:-900}"
EVAL_CONNECT_TIMEOUT="${EVAL_CONNECT_TIMEOUT:-10}"
EVAL_MAX_TOKENS="${EVAL_MAX_TOKENS:-0}"
RUN_FULL_REPORT="${RUN_FULL_REPORT:-1}"

mkdir -p "${EVAL_OUTPUT_DIR}" "${LOG_DIR}"

IFS=',' read -r -a GPUS <<< "${GPUS_CSV}"
IFS=',' read -r -a PORTS <<< "${PORTS_CSV}"

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

adapter_ready() {
  local dir="$1"
  [[ -f "${dir}/adapter_config.json" ]] && { [[ -f "${dir}/adapter_model.safetensors" ]] || [[ -f "${dir}/adapter_model.bin" ]]; }
}

stop_services() {
  local port
  for port in "${PORTS[@]}"; do
    "${PYTHON}" "${MANAGER}" stop --port "${port}" --kill >/dev/null 2>&1 || true
  done
}

cleanup() {
  local code=$?
  log "cleanup: stopping services on ports ${PORTS[*]}"
  stop_services
  exit "${code}"
}
trap cleanup EXIT INT TERM

require_inputs() {
  [[ -x "${PYTHON}" ]] || { log "python not executable: ${PYTHON}"; return 2; }
  [[ -f "${STANDARD_RECORDS}" ]] || { log "missing STANDARD_RECORDS=${STANDARD_RECORDS}"; return 2; }
  [[ -f "${HARD_RECORDS}" ]] || { log "missing HARD_RECORDS=${HARD_RECORDS}"; return 2; }
  [[ "${#GPUS[@]}" -eq "${#PORTS[@]}" ]] || { log "GPUS/PORTS length mismatch"; return 2; }
}

collect_targets() {
  find "${TRAIN_OUTPUT_DIR}" -maxdepth 1 -type d -name 'checkpoint-*' | sort -V
}

wait_service_ready() {
  local port="$1"
  local root_url="http://127.0.0.1:${port}"
  local base_url="${root_url}/v1"
  local deadline=$((SECONDS + READY_TIMEOUT))
  while (( SECONDS < deadline )); do
    if curl --noproxy "*" -fsS --max-time 5 "${root_url}/docs" >/dev/null 2>&1 || curl --noproxy "*" -fsS --max-time 5 "${base_url}/models" >/dev/null 2>&1; then
      log "service ready port=${port}"
      return 0
    fi
    sleep 10
  done
  log "service not ready after ${READY_TIMEOUT}s: port=${port}"
  return 1
}

start_service() {
  local checkpoint="$1"
  local model_name="$2"
  local gpu="$3"
  local port="$4"
  local api_model="trip-planner-${model_name}"
  local serve_log="${LOG_DIR}/serve_${model_name}_gpu${gpu}_port${port}.log"

  log "start vLLM model=${model_name} gpu=${gpu} port=${port} checkpoint=${checkpoint}"
  "${PYTHON}" "${MANAGER}" start \
    --port "${port}" \
    --variant base \
    --infer-backend vllm \
    --cuda-visible-devices "${gpu}" \
    --api-model-name "${api_model}" \
    --model-path "${BASE_MODEL_PATH}" \
    --adapter-path "${checkpoint}" \
    --vllm-maxlen "${VLLM_MAXLEN}" \
    --vllm-gpu-util "${VLLM_GPU_UTIL}" \
    --log-file "${serve_log}"
}

run_split() {
  local split="$1"
  local records="$2"
  local model_name="$3"
  local port="$4"
  local api_model="trip-planner-${model_name}"
  local cmd=(
    "${PYTHON}" "${EVAL_PIPELINE}"
    --records "${records}"
    --model-name "${model_name}_${split}"
    --api-model "${api_model}"
    --base-url "http://127.0.0.1:${port}/v1"
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
  log "eval ${split} model=${model_name} port=${port} workers=${WORKERS}"
  "${cmd[@]}"
}

write_full_report() {
  local model_name="$1"
  [[ "${RUN_FULL_REPORT}" == "1" ]] || return 0
  local standard_report="${EVAL_OUTPUT_DIR}/${model_name}_standard/rule_eval_report.json"
  local hard_report="${EVAL_OUTPUT_DIR}/${model_name}_hard/rule_eval_report.json"
  local report_dir="${EVAL_OUTPUT_DIR}/${model_name}_report"
  if [[ ! -f "${standard_report}" || ! -f "${hard_report}" ]]; then
    log "skip full report for ${model_name}; missing split report"
    return 0
  fi
  log "full report ${model_name}"
  "${PYTHON}" "${FULL_REPORT}" \
    --report "standard/${model_name}=${standard_report}" \
    --report "hard/${model_name}=${hard_report}" \
    --current-label "${model_name}" \
    --standard-records "${STANDARD_RECORDS}" \
    --hard-records "${HARD_RECORDS}" \
    --output-dir "${report_dir}" \
    --comparison-slug "${model_name}" \
    --inference-note "model-parallel checkpoint sweep; one checkpoint per GPU; vLLM; gpus=${GPUS_CSV}; ports=${PORTS_CSV}; maxlen=${VLLM_MAXLEN}; workers_per_gpu=${WORKERS}" \
    --summary-note "该报告由 2/3/4/5 四卡 model-parallel checkpoint sweep 自动生成；单卡一个 checkpoint，单卡并发 ${WORKERS}。" \
    > "${LOG_DIR}/report_${model_name}.log" 2>&1
}

run_eval_job() {
  local checkpoint="$1"
  local model_name="$2"
  local gpu="$3"
  local port="$4"
  local eval_log="${LOG_DIR}/eval_${model_name}_gpu${gpu}_port${port}.log"
  {
    log "job begin model=${model_name} gpu=${gpu} port=${port}"
    run_split standard "${STANDARD_RECORDS}" "${model_name}" "${port}"
    run_split hard "${HARD_RECORDS}" "${model_name}" "${port}"
    write_full_report "${model_name}"
    log "job done model=${model_name}"
  } > "${eval_log}" 2>&1
}

run_batch() {
  local -a batch=("$@")
  local idx checkpoint ckpt_name model_name gpu port
  log "===== batch begin: ${batch[*]} ====="
  stop_services

  for idx in "${!batch[@]}"; do
    checkpoint="${batch[$idx]}"
    ckpt_name="$(basename "${checkpoint}")"
    model_name="${MODEL_NAME_PREFIX}_${ckpt_name}"
    gpu="${GPUS[$idx]}"
    port="${PORTS[$idx]}"
    start_service "${checkpoint}" "${model_name}" "${gpu}" "${port}"
  done

  for idx in "${!batch[@]}"; do
    port="${PORTS[$idx]}"
    wait_service_ready "${port}"
  done

  local -a pids=()
  for idx in "${!batch[@]}"; do
    checkpoint="${batch[$idx]}"
    ckpt_name="$(basename "${checkpoint}")"
    model_name="${MODEL_NAME_PREFIX}_${ckpt_name}"
    gpu="${GPUS[$idx]}"
    port="${PORTS[$idx]}"
    run_eval_job "${checkpoint}" "${model_name}" "${gpu}" "${port}" &
    pids+=("$!")
  done

  local failed=0 pid
  for pid in "${pids[@]}"; do
    if ! wait "${pid}"; then
      failed=1
    fi
  done
  stop_services
  if [[ "${failed}" != "0" ]]; then
    log "batch failed: ${batch[*]}"
    return 1
  fi
  log "===== batch done: ${batch[*]} ====="
}

main() {
  require_inputs
  mapfile -t targets < <(collect_targets)
  if [[ "${#targets[@]}" -eq 0 ]]; then
    log "no checkpoint-* directories found under ${TRAIN_OUTPUT_DIR}"
    return 2
  fi
  log "targets (${#targets[@]}): ${targets[*]}"
  log "gpus=${GPUS[*]} ports=${PORTS[*]} workers=${WORKERS}"

  local -a batch=()
  local target
  for target in "${targets[@]}"; do
    if ! adapter_ready "${target}"; then
      log "skip ${target}; adapter files missing"
      continue
    fi
    batch+=("${target}")
    if [[ "${#batch[@]}" -eq "${#GPUS[@]}" ]]; then
      run_batch "${batch[@]}"
      batch=()
    fi
  done
  if [[ "${#batch[@]}" -gt 0 ]]; then
    run_batch "${batch[@]}"
  fi
  log "all checkpoint evals finished"
}

main "$@"
