#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$ROOT"

export PATH="$ROOT/.venv-training-py311/bin:$PATH"
export FORCE_TORCHRUN=1
export CUDA_VISIBLE_DEVICES=0,1,2,3
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export MASTER_PORT=29610

LOG_DIR="$ROOT/training/outputs/qwen25_7b/run_logs"
mkdir -p "$LOG_DIR"

run_train() {
  local name="$1"
  local config="$2"
  local log_file="$LOG_DIR/${name}.log"

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] START ${name}"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] START ${name}" > "$log_file"
  llamafactory-cli train "$config" >> "$log_file" 2>&1
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] END ${name}"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] END ${name}" >> "$log_file"
}

run_train \
  "sft_260509_main_clean_official_r32_b32_lr8e5_ctx24576_warm10_0123_20260510" \
  "$ROOT/training/configs/qwen25_7b/sft_qwen25_7b_lora_260509_main_clean_official_lr8e5.yaml"

run_train \
  "sft_260509_main_clean_official_r32_b32_lr6e5_ctx24576_warm10_0123_20260510" \
  "$ROOT/training/configs/qwen25_7b/sft_qwen25_7b_lora_260509_main_clean_official_lr6e5.yaml"
