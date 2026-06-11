#!/usr/bin/env bash
set -Eeuo pipefail

# Sequentially evaluates every DPO checkpoint. For each checkpoint, start one
# vLLM service per GPU, shard standard/hard records across the services, merge
# generations, run rule metrics, then stop services before moving on.

PROJECT_ROOT="${PROJECT_ROOT:-/work/liweihan/wyf/helloagents-trip-planner}"
cd "${PROJECT_ROOT}"

PYTHON="${PYTHON:-${PROJECT_ROOT}/.venv-training-py311/bin/python3}"
MANAGER="${PROJECT_ROOT}/training/scripts/serving/manage_planner_service.py"
EVAL_GENERATE="${PROJECT_ROOT}/training/scripts/eval/eval_generate.py"
EVAL_RULE="${PROJECT_ROOT}/training/scripts/eval/eval_rule_metrics.py"
FULL_REPORT="${PROJECT_ROOT}/training/scripts/planner/eval/generate_full_report.py"

TRAIN_OUTPUT_DIR="${TRAIN_OUTPUT_DIR:-${PROJECT_ROOT}/training/outputs/qwen25_7b/dpo_260518_fd600_planner_soft_direct402_r16_4epoch_z3offload_torchadam_5gpu01234}"
BASE_MODEL_PATH="${BASE_MODEL_PATH:-${PROJECT_ROOT}/training/outputs/qwen25_7b/merged_sft_260516_final1200_for_dpo}"
STANDARD_RECORDS="${STANDARD_RECORDS:-${PROJECT_ROOT}/training/data/planner/eval/records.jsonl}"
HARD_RECORDS="${HARD_RECORDS:-${PROJECT_ROOT}/training/data/planner/eval_hard/records.jsonl}"

RUN_GROUP="${RUN_GROUP:-dpo_260518_fd600_planner_soft_direct402_ckpt_sweep_0457}"
MODEL_NAME_PREFIX="${MODEL_NAME_PREFIX:-dpo_260518_fd600_planner_soft_direct402}"
EVAL_OUTPUT_DIR="${EVAL_OUTPUT_DIR:-${PROJECT_ROOT}/training/outputs/eval/by_model/${RUN_GROUP}}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/training/outputs/eval/logs/${RUN_GROUP}}"
SHARD_ROOT="${SHARD_ROOT:-${EVAL_OUTPUT_DIR}/_record_shards}"

GPUS_CSV="${GPUS_CSV:-0,4,5,7}"
PORTS_CSV="${PORTS_CSV:-4500,4504,4505,4507}"
WORKERS_CSV="${WORKERS_CSV:-3,3,3,3}"
VLLM_MAXLEN="${VLLM_MAXLEN:-32768}"
VLLM_GPU_UTIL="${VLLM_GPU_UTIL:-0.85}"
READY_TIMEOUT="${READY_TIMEOUT:-900}"

EVAL_TEMPERATURE="${EVAL_TEMPERATURE:-0.2}"
EVAL_TIMEOUT="${EVAL_TIMEOUT:-900}"
EVAL_CONNECT_TIMEOUT="${EVAL_CONNECT_TIMEOUT:-10}"
EVAL_MAX_TOKENS="${EVAL_MAX_TOKENS:-0}"
RUN_FULL_REPORT="${RUN_FULL_REPORT:-1}"

mkdir -p "${EVAL_OUTPUT_DIR}" "${LOG_DIR}" "${SHARD_ROOT}"

IFS=',' read -r -a GPUS <<< "${GPUS_CSV}"
IFS=',' read -r -a PORTS <<< "${PORTS_CSV}"
IFS=',' read -r -a WORKERS <<< "${WORKERS_CSV}"

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

adapter_ready() {
  local dir="$1"
  [[ -f "${dir}/adapter_config.json" ]] && { [[ -f "${dir}/adapter_model.safetensors" ]] || [[ -f "${dir}/adapter_model.bin" ]]; }
}

stop_services() {
  local idx port
  for idx in "${!PORTS[@]}"; do
    port="${PORTS[$idx]}"
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
  [[ "${#GPUS[@]}" -eq "${#WORKERS[@]}" ]] || { log "GPUS/WORKERS length mismatch"; return 2; }
}

make_record_shards() {
  log "writing record shards to ${SHARD_ROOT}"
  "${PYTHON}" - "${STANDARD_RECORDS}" "${SHARD_ROOT}/standard" "${GPUS[@]}" <<'PY'
import sys
from pathlib import Path
src = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
labels = sys.argv[3:]
out_dir.mkdir(parents=True, exist_ok=True)
handles = {label: (out_dir / f"gpu{label}.jsonl").open("w", encoding="utf-8") for label in labels}
try:
    rows = [line for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    for idx, line in enumerate(rows):
        handles[labels[idx % len(labels)]].write(line + "\n")
finally:
    for handle in handles.values():
        handle.close()
PY
  "${PYTHON}" - "${HARD_RECORDS}" "${SHARD_ROOT}/hard" "${GPUS[@]}" <<'PY'
import sys
from pathlib import Path
src = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
labels = sys.argv[3:]
out_dir.mkdir(parents=True, exist_ok=True)
handles = {label: (out_dir / f"gpu{label}.jsonl").open("w", encoding="utf-8") for label in labels}
try:
    rows = [line for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    for idx, line in enumerate(rows):
        handles[labels[idx % len(labels)]].write(line + "\n")
finally:
    for handle in handles.values():
        handle.close()
PY
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

start_services_for_checkpoint() {
  local checkpoint="$1"
  local model_name="$2"
  local api_model="trip-planner-${model_name}"
  local idx gpu port log_file

  log "stopping stale services before ${model_name}"
  stop_services

  for idx in "${!GPUS[@]}"; do
    gpu="${GPUS[$idx]}"
    port="${PORTS[$idx]}"
    log_file="${LOG_DIR}/serve_${model_name}_gpu${gpu}_port${port}.log"
    log "start vLLM gpu=${gpu} port=${port} checkpoint=${checkpoint}"
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
      --log-file "${log_file}"
  done

  for idx in "${!PORTS[@]}"; do
    wait_service_ready "${PORTS[$idx]}"
  done
}

run_split_generate() {
  local split="$1"
  local records="$2"
  local model_name="$3"
  local api_model="trip-planner-${model_name}"
  local run_dir="${EVAL_OUTPUT_DIR}/${model_name}_${split}"
  local shard_dir="${run_dir}/shards"
  local meta_dir="${run_dir}/shard_meta"
  mkdir -p "${shard_dir}" "${meta_dir}"

  local -a pids=()
  local -a shard_outputs=()
  local idx gpu port workers shard_records shard_output gen_log

  for idx in "${!GPUS[@]}"; do
    gpu="${GPUS[$idx]}"
    port="${PORTS[$idx]}"
    workers="${WORKERS[$idx]}"
    shard_records="${SHARD_ROOT}/${split}/gpu${gpu}.jsonl"
    shard_output="${shard_dir}/gpu${gpu}.jsonl"
    gen_log="${LOG_DIR}/generate_${model_name}_${split}_gpu${gpu}.log"
    shard_outputs+=("${shard_output}")
    log "generate ${split} gpu=${gpu} port=${port} workers=${workers} records=${shard_records}"
    cmd=(
      "${PYTHON}" "${EVAL_GENERATE}"
      --records "${shard_records}"
      --model-name "${model_name}_${split}_gpu${gpu}_shard"
      --api-model "${api_model}"
      --base-url "http://127.0.0.1:${port}/v1"
      --output-dir "${meta_dir}"
      --output-file "${shard_output}"
      --workers "${workers}"
      --temperature "${EVAL_TEMPERATURE}"
      --timeout "${EVAL_TIMEOUT}"
      --connect-timeout "${EVAL_CONNECT_TIMEOUT}"
      --resume
    )
    if [[ "${EVAL_MAX_TOKENS}" != "0" ]]; then
      cmd+=(--max-tokens "${EVAL_MAX_TOKENS}")
    fi
    "${cmd[@]}" > "${gen_log}" 2>&1 &
    pids+=("$!")
  done

  local failed=0 pid
  for pid in "${pids[@]}"; do
    if ! wait "${pid}"; then
      failed=1
    fi
  done
  if [[ "${failed}" != "0" ]]; then
    log "generation failed for ${model_name}_${split}; see ${LOG_DIR}/generate_${model_name}_${split}_gpu*.log"
    return 1
  fi

  local final_generations="${run_dir}/generations.jsonl"
  log "merge ${split} generations -> ${final_generations}"
  "${PYTHON}" - "${records}" "${final_generations}" "${shard_outputs[@]}" <<'PY'
import json
import sys
from pathlib import Path
records = Path(sys.argv[1])
out = Path(sys.argv[2])
shards = [Path(p) for p in sys.argv[3:]]
order = {}
for idx, line in enumerate(records.read_text(encoding="utf-8").splitlines()):
    if not line.strip():
        continue
    row = json.loads(line)
    order[row["record_id"]] = idx
rows = {}
for shard in shards:
    if not shard.exists():
        continue
    for line in shard.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = row.get("record_id")
        if rid:
            rows[rid] = row
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", encoding="utf-8") as f:
    for rid, _idx in sorted(order.items(), key=lambda item: item[1]):
        row = rows.get(rid)
        if row is not None:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
missing = [rid for rid in order if rid not in rows]
if missing:
    raise SystemExit(f"missing {len(missing)} generations; first={missing[:5]}")
PY

  local rule_log="${LOG_DIR}/rule_${model_name}_${split}.log"
  log "rule eval ${model_name}_${split}"
  "${PYTHON}" "${EVAL_RULE}" \
    --records "${records}" \
    --generations "${final_generations}" \
    --model-name "${model_name}_${split}" \
    --output-dir "${EVAL_OUTPUT_DIR}" > "${rule_log}" 2>&1
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
    --inference-note "checkpoint sweep; vLLM; gpus=${GPUS_CSV}; ports=${PORTS_CSV}; maxlen=${VLLM_MAXLEN}; workers=${WORKERS_CSV}" \
    --summary-note "该报告由 0/4/5/7 四卡 checkpoint sweep 自动生成；每个 checkpoint 评估完成后会停止对应 vLLM 服务释放显存。" \
    > "${LOG_DIR}/report_${model_name}.log" 2>&1
}

run_checkpoint() {
  local checkpoint="$1"
  local ckpt_name
  ckpt_name="$(basename "${checkpoint}")"
  local model_name="${MODEL_NAME_PREFIX}_${ckpt_name}"

  if ! adapter_ready "${checkpoint}"; then
    log "skip ${checkpoint}; adapter files missing"
    return 0
  fi

  log "===== begin ${model_name} ====="
  start_services_for_checkpoint "${checkpoint}" "${model_name}"
  run_split_generate standard "${STANDARD_RECORDS}" "${model_name}"
  run_split_generate hard "${HARD_RECORDS}" "${model_name}"
  write_full_report "${model_name}"
  log "===== done ${model_name}; stopping services ====="
  stop_services
}

main() {
  require_inputs
  make_record_shards
  mapfile -t targets < <(collect_targets)
  if [[ "${#targets[@]}" -eq 0 ]]; then
    log "no checkpoint-* directories found under ${TRAIN_OUTPUT_DIR}"
    return 2
  fi
  log "targets (${#targets[@]}): ${targets[*]}"
  log "gpus=${GPUS[*]} ports=${PORTS[*]} workers=${WORKERS[*]}"

  local target
  for target in "${targets[@]}"; do
    run_checkpoint "${target}"
  done
  log "all checkpoint evals finished"
}

main "$@"
