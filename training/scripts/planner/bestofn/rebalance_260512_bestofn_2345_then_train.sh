#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON="${PROJECT_ROOT}/.venv-training-py311/bin/python3"
RUN_TAG="${RUN_TAG:-260512_anti_leak1200_vllm23_w8}"
OUT_DIR="${OUT_DIR:-${PROJECT_ROOT}/training/data/planner/bestofn/${RUN_TAG}}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/training/outputs/eval/logs/${RUN_TAG}_rebalance2345_autotrain}"
ADAPTER_PATH="${ADAPTER_PATH:-${PROJECT_ROOT}/training/outputs/qwen25_7b/sft_260512_replay_usage700_plus_bestofn600_from_replay_r32_b32_lr1e5_ctx24576_ep2_20260512}"
LF_PREFIX="${LF_PREFIX:-trip_planner_bestofn_${RUN_TAG}}"
COMBINED_PREFIX="${COMBINED_PREFIX:-trip_planner_260513_replay_usage700_plus_bestofn1200}"
WORKERS="${WORKERS:-8}"
MAX_TOKENS="${MAX_TOKENS:-12000}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-900}"
VLLM_MAXLEN="${VLLM_MAXLEN:-32768}"
TRAIN_AFTER="${TRAIN_AFTER:-1}"
TRAIN_CUDA_VISIBLE_DEVICES="${TRAIN_CUDA_VISIBLE_DEVICES:-2,3,4,5}"

GPUS=(2 3 4 5)
PORTS=(4438 4439 4444 4445)

mkdir -p "${LOG_DIR}" "${OUT_DIR}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*" | tee -a "${LOG_DIR}/supervisor.log"
}

line_count() {
  local path="$1"
  if [[ -f "${path}" ]]; then
    wc -l < "${path}" | tr -d ' '
  else
    printf '0'
  fi
}

wait_service_ready() {
  local port="$1"
  for _ in $(seq 1 90); do
    if "${PYTHON}" - "${port}" >/dev/null 2>&1 <<'PY'
import json
import sys
import urllib.request

port = int(sys.argv[1])
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(f"http://127.0.0.1:{port}/v1/models", timeout=5) as response:
    data = json.loads(response.read().decode("utf-8"))
if not data.get("data"):
    raise SystemExit(1)
PY
    then
      log "Service on port ${port} is ready."
      return 0
    fi
    sleep 10
  done
  log "Service on port ${port} did not become ready."
  return 1
}

start_extra_services() {
  for item in "4:4444:0.75" "5:4445:0.85"; do
    IFS=: read -r gpu port util <<< "${item}"
    if "${PYTHON}" - "${port}" >/dev/null 2>&1 <<'PY'
import json
import sys
import urllib.request

port = int(sys.argv[1])
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(f"http://127.0.0.1:{port}/v1/models", timeout=5) as response:
    data = json.loads(response.read().decode("utf-8"))
if not data.get("data"):
    raise SystemExit(1)
PY
    then
      log "Reusing ready vLLM service on GPU ${gpu}, port ${port}"
      continue
    fi
    local api_model="trip-planner-bestofn1200-gpu${gpu}"
    local service_log="${LOG_DIR}/serve_gpu${gpu}_${port}.log"
    log "Starting vLLM service on GPU ${gpu}, port ${port}, util=${util}"
    "${PYTHON}" training/scripts/serving/manage_planner_service.py restart \
      --port "${port}" \
      --variant sft \
      --infer-backend vllm \
      --cuda-visible-devices "${gpu}" \
      --adapter-path "${ADAPTER_PATH}" \
      --api-model-name "${api_model}" \
      --vllm-maxlen "${VLLM_MAXLEN}" \
      --vllm-gpu-util "${util}" \
      --log-file "${service_log}" \
      | tee -a "${LOG_DIR}/supervisor.log"
    wait_service_ready "${port}"
  done

  for port in "${PORTS[@]}"; do
    wait_service_ready "${port}"
  done
}

stop_old_launcher() {
  local pids
  pids="$(pgrep -f 'training/scripts/planner/bestofn/run_260512_anti_leak1200_wait_gpu01.sh' || true)"
  if [[ -z "${pids}" ]]; then
    log "No old wait_gpu launcher found."
    return 0
  fi
  while read -r pid; do
    [[ -z "${pid}" ]] && continue
    local pgid
    pgid="$(ps -o pgid= -p "${pid}" | tr -d ' ' || true)"
    [[ -z "${pgid}" ]] && continue
    log "Stopping old launcher pid=${pid} pgid=${pgid}"
    kill -TERM "-${pgid}" || true
  done <<< "${pids}"
  sleep 5
}

build_remaining_shards() {
  log "Building remaining prompt shards for GPUs ${GPUS[*]}"
  "${PYTHON}" - "${OUT_DIR}" "${GPUS[@]}" <<'PY'
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
gpus = sys.argv[2:]
completed = set()
sources = [
    out_dir / "candidates_accel_gpu2.jsonl",
    out_dir / "candidates_accel_gpu3.jsonl",
    *[out_dir / f"candidates_rebalanced_gpu{gpu}.jsonl" for gpu in gpus],
]
for path in sources:
    if not path.exists():
        continue
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            prompt_id = row.get("prompt_id")
            if prompt_id:
                completed.add(prompt_id)

handles = {
    gpu: (out_dir / f"prompts_rebalanced_gpu{gpu}.jsonl").open("w", encoding="utf-8")
    for gpu in gpus
}
counts = {gpu: 0 for gpu in gpus}
remaining = 0
try:
    with (out_dir / "prompts.jsonl").open(encoding="utf-8") as src:
        for line in src:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("prompt_id") in completed:
                continue
            gpu = gpus[remaining % len(gpus)]
            handles[gpu].write(line)
            counts[gpu] += 1
            remaining += 1
finally:
    for handle in handles.values():
        handle.close()

summary = {
    "completed": len(completed),
    "remaining": remaining,
    "shards": {f"gpu{gpu}": counts[gpu] for gpu in gpus},
}
(out_dir / "rebalance_split_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
}

run_generation() {
  log "Launching rebalanced generators."
  printf 'gpu\tport\tpid\tlog\tprompts\tstarted_at\n' > "${LOG_DIR}/rebalance_pids.tsv"
  declare -a pids=()
  for idx in "${!GPUS[@]}"; do
    local gpu="${GPUS[$idx]}"
    local port="${PORTS[$idx]}"
    local prompt_file="${OUT_DIR}/prompts_rebalanced_gpu${gpu}.jsonl"
    local candidate_file="${OUT_DIR}/candidates_rebalanced_gpu${gpu}.jsonl"
    local gen_log="${LOG_DIR}/generate_rebalanced_gpu${gpu}.log"
    local prompts
    prompts="$(line_count "${prompt_file}")"
    if [[ "${prompts}" == "0" ]]; then
      log "GPU ${gpu} has no remaining prompts; skip."
      continue
    fi
    nohup "${PYTHON}" -u training/scripts/planner/bestofn/generate_candidates.py \
      --prompts "${prompt_file}" \
      --output "${candidate_file}" \
      --base-url "http://127.0.0.1:${port}/v1" \
      --api-model "trip-planner-bestofn1200-gpu${gpu}" \
      --spec t02:0.2:2 \
      --spec t05:0.5:2 \
      --spec t08:0.8:2 \
      --workers "${WORKERS}" \
      --resume \
      --timeout "${TIMEOUT_SECONDS}" \
      --max-tokens "${MAX_TOKENS}" \
      > "${gen_log}" 2>&1 &
    local pid=$!
    pids+=("${pid}")
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "${gpu}" "${port}" "${pid}" "${gen_log}" "${prompts}" "$(date '+%F %T')" >> "${LOG_DIR}/rebalance_pids.tsv"
    log "GPU ${gpu} generation pid=${pid} prompts=${prompts} log=${gen_log}"
  done
  for pid in "${pids[@]}"; do
    log "Waiting for generation pid=${pid}"
    wait "${pid}"
  done
}

merge_and_postprocess() {
  log "Merging candidate shards and selecting winners."
  "${PYTHON}" - "${OUT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
sources = [
    out_dir / "candidates_accel_gpu2.jsonl",
    out_dir / "candidates_accel_gpu3.jsonl",
    out_dir / "candidates_rebalanced_gpu2.jsonl",
    out_dir / "candidates_rebalanced_gpu3.jsonl",
    out_dir / "candidates_rebalanced_gpu4.jsonl",
    out_dir / "candidates_rebalanced_gpu5.jsonl",
]
seen = set()
rows = []
for path in sources:
    if not path.exists():
        continue
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            prompt_id = row.get("prompt_id")
            if not prompt_id or prompt_id in seen:
                continue
            seen.add(prompt_id)
            rows.append(row)

prompt_count = sum(1 for _ in (out_dir / "prompts.jsonl").open(encoding="utf-8"))
if len(rows) != prompt_count:
    raise SystemExit(f"merged candidates incomplete: {len(rows)}/{prompt_count}")

with (out_dir / "candidates.jsonl").open("w", encoding="utf-8") as out:
    for row in rows:
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
print(json.dumps({"merged": len(rows), "expected": prompt_count}, ensure_ascii=False, indent=2))
PY

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
    | tee "${LOG_DIR}/select_best.log"

  "${PYTHON}" training/scripts/planner/bestofn/render_review.py \
    --prompts "${OUT_DIR}/prompts.jsonl" \
    --candidates "${OUT_DIR}/candidates.jsonl" \
    --selected "${OUT_DIR}/selected.jsonl" \
    --summary "${OUT_DIR}/bestofn_summary.json" \
    --output "${OUT_DIR}/review.md" \
    | tee "${LOG_DIR}/render_review.log"
}

build_training_data() {
  log "Building replay + Best-of-N training data."
  "${PYTHON}" training/scripts/planner/bestofn/build_replay_plus_bestofn_dataset.py \
    --bestofn-train "training/data/llamafactory/${LF_PREFIX}_sft_train.json" \
    --bestofn-val "training/data/llamafactory/${LF_PREFIX}_sft_val.json" \
    --output-prefix "${COMBINED_PREFIX}" \
    --oversample-ratio 0.0 \
    --seed 260513 \
    | tee "${LOG_DIR}/build_training_data.log"
}

stop_services_for_training() {
  log "Stopping vLLM services before training."
  for port in "${PORTS[@]}"; do
    "${PYTHON}" training/scripts/serving/manage_planner_service.py stop --port "${port}" --kill --timeout 20 \
      | tee -a "${LOG_DIR}/supervisor.log" || true
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
    WAIT_MAX_USED_MIB="${TRAIN_WAIT_MAX_USED_MIB:-8192}" \
    bash training/scripts/planner/training/run_260513_bestofn1200_replay_from_final.sh \
    | tee "${LOG_DIR}/training_driver.log"
}

main() {
  log "Supervisor started."
  start_extra_services
  stop_old_launcher
  build_remaining_shards
  run_generation
  merge_and_postprocess
  build_training_data
  stop_services_for_training
  start_training
  log "Supervisor finished."
}

main "$@"
