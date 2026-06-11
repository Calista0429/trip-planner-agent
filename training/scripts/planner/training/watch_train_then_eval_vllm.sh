#!/usr/bin/env bash
set -Eeuo pipefail

# Wait for a training tmux session/output dir, then serve the trained adapter with
# vLLM, run planner eval, and always release the service VRAM at the end.
#
# Typical current run:
#   bash training/scripts/planner/training/watch_train_then_eval_vllm.sh
#
# Useful overrides:
#   EVAL_TARGETS=checkpoints   # final | checkpoints | all
#   SERVE_DEVICES=4 PORT=4464
#   EVAL_WORKERS=3
#   WAIT_FOR_TRAINING=0        # evaluate existing outputs immediately

PROJECT_ROOT="${PROJECT_ROOT:-/work/liweihan/wyf/helloagents-trip-planner}"
cd "${PROJECT_ROOT}"

PYTHON="${PYTHON:-${PROJECT_ROOT}/.venv-training-py311/bin/python3}"
MANAGER="${PROJECT_ROOT}/training/scripts/serving/manage_planner_service.py"
EVAL_PIPELINE="${PROJECT_ROOT}/training/scripts/eval/eval_pipeline.py"
FULL_REPORT="${PROJECT_ROOT}/training/scripts/planner/eval/generate_full_report.py"

TRAIN_SESSION="${TRAIN_SESSION:-dpo_direct402_01234}"
TRAIN_OUTPUT_DIR="${TRAIN_OUTPUT_DIR:-${PROJECT_ROOT}/training/outputs/qwen25_7b/dpo_260518_fd600_planner_soft_direct402_r16_4epoch_z3offload_torchadam_5gpu01234}"
BASE_MODEL_PATH="${BASE_MODEL_PATH:-${PROJECT_ROOT}/training/outputs/qwen25_7b/merged_sft_260516_final1200_for_dpo}"

RUN_GROUP="${RUN_GROUP:-dpo_260518_fd600_planner_soft_direct402_auto_after_train}"
MODEL_NAME_PREFIX="${MODEL_NAME_PREFIX:-dpo_260518_fd600_planner_soft_direct402}"
EVAL_OUTPUT_DIR="${EVAL_OUTPUT_DIR:-${PROJECT_ROOT}/training/outputs/eval/by_model/${RUN_GROUP}}"
STANDARD_RECORDS="${STANDARD_RECORDS:-${PROJECT_ROOT}/training/data/planner/eval/records.jsonl}"
HARD_RECORDS="${HARD_RECORDS:-${PROJECT_ROOT}/training/data/planner/eval_hard/records.jsonl}"

EVAL_TARGETS="${EVAL_TARGETS:-final}" # final | checkpoints | all
WAIT_FOR_TRAINING="${WAIT_FOR_TRAINING:-1}"
POLL_INTERVAL="${POLL_INTERVAL:-60}"
POST_TRAIN_SETTLE_SECONDS="${POST_TRAIN_SETTLE_SECONDS:-30}"

PORT="${PORT:-4464}"
SERVE_DEVICES="${SERVE_DEVICES:-4}"
VLLM_MAXLEN="${VLLM_MAXLEN:-32768}"
VLLM_GPU_UTIL="${VLLM_GPU_UTIL:-0.85}"
READY_TIMEOUT="${READY_TIMEOUT:-1200}"

EVAL_WORKERS="${EVAL_WORKERS:-3}"
EVAL_TEMPERATURE="${EVAL_TEMPERATURE:-0.2}"
EVAL_TIMEOUT="${EVAL_TIMEOUT:-900}"
EVAL_CONNECT_TIMEOUT="${EVAL_CONNECT_TIMEOUT:-10}"
EVAL_MAX_TOKENS="${EVAL_MAX_TOKENS:-0}"
EVAL_LIMIT="${EVAL_LIMIT:-0}"
RUN_FULL_REPORT="${RUN_FULL_REPORT:-1}"

LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/training/outputs/eval/logs/${RUN_GROUP}}"
mkdir -p "${LOG_DIR}" "${EVAL_OUTPUT_DIR}"

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*" >&2
}

adapter_ready() {
  local dir="$1"
  [[ -f "${dir}/adapter_config.json" ]] && { [[ -f "${dir}/adapter_model.safetensors" ]] || [[ -f "${dir}/adapter_model.bin" ]]; }
}

stop_service() {
  "${PYTHON}" "${MANAGER}" stop --port "${PORT}" --kill >/dev/null 2>&1 || true
}

cleanup() {
  local code=$?
  log "cleanup: stopping planner service on port ${PORT}"
  stop_service
  exit "${code}"
}
trap cleanup EXIT INT TERM

wait_for_training() {
  if [[ "${WAIT_FOR_TRAINING}" != "1" ]]; then
    log "WAIT_FOR_TRAINING=0, skip tmux wait"
    return
  fi

  log "waiting for training session '${TRAIN_SESSION}' to finish"
  while tmux has-session -t "${TRAIN_SESSION}" 2>/dev/null; do
    local latest_step="unknown"
    if [[ -f "${TRAIN_OUTPUT_DIR}/trainer_state.json" ]]; then
      latest_step="$(${PYTHON} -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); print(d.get("global_step", "unknown"))' "${TRAIN_OUTPUT_DIR}/trainer_state.json" 2>/dev/null || echo unknown)"
    fi
    log "training still running; latest global_step=${latest_step}"
    sleep "${POLL_INTERVAL}"
  done

  log "training session ended; settling ${POST_TRAIN_SETTLE_SECONDS}s for final files"
  sleep "${POST_TRAIN_SETTLE_SECONDS}"
}

collect_targets() {
  local -a targets=()

  case "${EVAL_TARGETS}" in
    final)
      if adapter_ready "${TRAIN_OUTPUT_DIR}"; then
        targets+=("final:${TRAIN_OUTPUT_DIR}")
      else
        local latest=""
        latest="$(find "${TRAIN_OUTPUT_DIR}" -maxdepth 1 -type d -name 'checkpoint-*' 2>/dev/null | sort -V | tail -n 1 || true)"
        if [[ -n "${latest}" ]] && adapter_ready "${latest}"; then
          log "final adapter not found; fallback to latest checkpoint: ${latest}"
          targets+=("$(basename "${latest}"):${latest}")
        fi
      fi
      ;;
    checkpoints)
      while IFS= read -r checkpoint; do
        [[ -n "${checkpoint}" ]] || continue
        if adapter_ready "${checkpoint}"; then
          targets+=("$(basename "${checkpoint}"):${checkpoint}")
        fi
      done < <(find "${TRAIN_OUTPUT_DIR}" -maxdepth 1 -type d -name 'checkpoint-*' 2>/dev/null | sort -V)
      ;;
    all)
      while IFS= read -r checkpoint; do
        [[ -n "${checkpoint}" ]] || continue
        if adapter_ready "${checkpoint}"; then
          targets+=("$(basename "${checkpoint}"):${checkpoint}")
        fi
      done < <(find "${TRAIN_OUTPUT_DIR}" -maxdepth 1 -type d -name 'checkpoint-*' 2>/dev/null | sort -V)
      if adapter_ready "${TRAIN_OUTPUT_DIR}"; then
        targets+=("final:${TRAIN_OUTPUT_DIR}")
      fi
      ;;
    *)
      log "unknown EVAL_TARGETS=${EVAL_TARGETS}; use final, checkpoints, or all"
      return 2
      ;;
  esac

  if [[ "${#targets[@]}" -eq 0 ]]; then
    log "no eval-ready adapter found under ${TRAIN_OUTPUT_DIR}"
    return 2
  fi

  printf '%s\n' "${targets[@]}"
}

wait_service_ready() {
  local root_url="http://127.0.0.1:${PORT}"
  local base_url="${root_url}/v1"
  local deadline=$((SECONDS + READY_TIMEOUT))
  log "waiting for vLLM service: ${root_url}/docs or ${base_url}/models"
  while (( SECONDS < deadline )); do
    if curl --noproxy "*" -fsS --max-time 5 "${root_url}/docs" >/dev/null 2>&1 || curl --noproxy "*" -fsS --max-time 5 "${base_url}/models" >/dev/null 2>&1; then
      log "service ready: ${base_url}"
      return 0
    fi
    sleep 10
  done
  log "service did not become ready within ${READY_TIMEOUT}s"
  return 1
}

run_eval_split() {
  local split="$1"
  local records="$2"
  local model_name="$3"
  local api_model="$4"

  local cmd=(
    "${PYTHON}" "${EVAL_PIPELINE}"
    --records "${records}"
    --model-name "${model_name}_${split}"
    --api-model "${api_model}"
    --base-url "http://127.0.0.1:${PORT}/v1"
    --output-dir "${EVAL_OUTPUT_DIR}"
    --workers "${EVAL_WORKERS}"
    --temperature "${EVAL_TEMPERATURE}"
    --timeout "${EVAL_TIMEOUT}"
    --connect-timeout "${EVAL_CONNECT_TIMEOUT}"
    --resume
  )
  if [[ "${EVAL_MAX_TOKENS}" != "0" ]]; then
    cmd+=(--max-tokens "${EVAL_MAX_TOKENS}")
  fi
  if [[ "${EVAL_LIMIT}" != "0" ]]; then
    cmd+=(--limit "${EVAL_LIMIT}")
  fi

  log "eval ${split}: model=${model_name}_${split}, records=${records}"
  "${cmd[@]}"
}

write_full_report() {
  local model_name="$1"
  local report_dir="${EVAL_OUTPUT_DIR}/${model_name}_report"
  local standard_report="${EVAL_OUTPUT_DIR}/${model_name}_standard/rule_eval_report.json"
  local hard_report="${EVAL_OUTPUT_DIR}/${model_name}_hard/rule_eval_report.json"

  if [[ "${RUN_FULL_REPORT}" != "1" ]]; then
    return
  fi
  if [[ ! -f "${standard_report}" || ! -f "${hard_report}" ]]; then
    log "skip full report; missing rule report(s) for ${model_name}"
    return
  fi

  log "writing full report for ${model_name}"
  "${PYTHON}" "${FULL_REPORT}" \
    --report "standard/${model_name}=${standard_report}" \
    --report "hard/${model_name}=${hard_report}" \
    --current-label "${model_name}" \
    --standard-records "${STANDARD_RECORDS}" \
    --hard-records "${HARD_RECORDS}" \
    --output-dir "${report_dir}" \
    --comparison-slug "${model_name}" \
    --inference-note "auto watcher; vLLM; devices=${SERVE_DEVICES}; port=${PORT}; maxlen=${VLLM_MAXLEN}; workers=${EVAL_WORKERS}" \
    --summary-note "该报告由训练完成后的自动 watcher 生成；服务在评估结束后会自动 stop --kill 释放显存。"
}

serve_and_eval_one() {
  local target_name="$1"
  local adapter_path="$2"
  local model_name="${MODEL_NAME_PREFIX}_${target_name}"
  local api_model="trip-planner-${model_name}"
  local serve_log="${LOG_DIR}/serve_${model_name}_port${PORT}.log"

  log "stopping any existing managed planner service on port ${PORT}"
  stop_service

  log "starting vLLM: adapter=${adapter_path}, base=${BASE_MODEL_PATH}, devices=${SERVE_DEVICES}, port=${PORT}"
  "${PYTHON}" "${MANAGER}" start \
    --port "${PORT}" \
    --variant base \
    --infer-backend vllm \
    --cuda-visible-devices "${SERVE_DEVICES}" \
    --api-model-name "${api_model}" \
    --model-path "${BASE_MODEL_PATH}" \
    --adapter-path "${adapter_path}" \
    --vllm-maxlen "${VLLM_MAXLEN}" \
    --vllm-gpu-util "${VLLM_GPU_UTIL}" \
    --log-file "${serve_log}"

  wait_service_ready
  run_eval_split standard "${STANDARD_RECORDS}" "${model_name}" "${api_model}"
  run_eval_split hard "${HARD_RECORDS}" "${model_name}" "${api_model}"
  write_full_report "${model_name}"

  log "eval done for ${model_name}; releasing vLLM VRAM"
  stop_service
}

main() {
  if [[ ! -x "${PYTHON}" ]]; then
    log "python not executable: ${PYTHON}"
    return 2
  fi
  if [[ ! -f "${STANDARD_RECORDS}" ]]; then
    log "missing STANDARD_RECORDS=${STANDARD_RECORDS}"
    return 2
  fi
  if [[ ! -f "${HARD_RECORDS}" ]]; then
    log "missing HARD_RECORDS=${HARD_RECORDS}"
    return 2
  fi

  wait_for_training

  mapfile -t targets < <(collect_targets)
  log "eval targets (${#targets[@]}): ${targets[*]}"

  for item in "${targets[@]}"; do
    local target_name="${item%%:*}"
    local adapter_path="${item#*:}"
    serve_and_eval_one "${target_name}" "${adapter_path}"
  done

  log "all eval targets finished"
}

main "$@"
