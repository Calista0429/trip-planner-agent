#!/usr/bin/env bash
set -euo pipefail

GPU_CSV="${GPU_CSV:-0,1,2,3}"
MEM_LIMIT_MIB="${MEM_LIMIT_MIB:-1024}"
CHECK_INTERVAL_SECONDS="${CHECK_INTERVAL_SECONDS:-60}"
RUN_SCRIPT=/work/liweihan/wyf/helloagents-trip-planner/training/scripts/planner/training/run_260520_closing_budget_clean_from_ckpt138_0123_ctx24576_nooffload.sh

IFS=',' read -r -a GPU_IDS <<< "${GPU_CSV}"

echo "[watch] $(date '+%F %T') waiting for GPUs ${GPU_CSV}; memory limit ${MEM_LIMIT_MIB} MiB"

while true; do
  mapfile -t ROWS < <(nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader,nounits)
  ready=1
  for gpu_id in "${GPU_IDS[@]}"; do
    row="${ROWS[$gpu_id]}"
    used="$(awk -F, '{gsub(/ /, "", $2); print $2}' <<< "${row}")"
    if [[ "${used}" -gt "${MEM_LIMIT_MIB}" ]]; then
      ready=0
      break
    fi
  done

  if [[ "${ready}" -eq 1 ]]; then
    echo "[watch] $(date '+%F %T') GPUs ${GPU_CSV} are free; starting training"
    exec "${RUN_SCRIPT}"
  fi

  echo "[watch] $(date '+%F %T') still busy: ${ROWS[*]}"
  sleep "${CHECK_INTERVAL_SECONDS}"
done
