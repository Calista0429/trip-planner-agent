#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
LOG="$ROOT/training/outputs/eval/logs/260513_rerank_autostop.log"

REPORT_CKPT104="$ROOT/training/outputs/eval/by_model/sft_qwen25_7b_planner_260513_rerank_ckpt104/260513_rerank_ckpt104_hard_w10/rule_eval_report.json"
REPORT_FINAL1200="$ROOT/training/outputs/eval/by_model/sft_qwen25_7b_planner_260513_rerank_final1200/260513_rerank_final1200_hard_w10/rule_eval_report.json"
REPORT_OLD600="$ROOT/training/outputs/eval/by_model/sft_qwen25_7b_planner_260513_rerank_old600final/260513_rerank_old600final_hard_w10/rule_eval_report.json"

SERVICE_PIDS=(3500019 3500021 3500182)

echo "[start] $(date '+%F %T %z')" > "$LOG"
echo "[watch] waiting for all hard rule_eval_report.json files..." >> "$LOG"

while true; do
  if [[ -f "$REPORT_CKPT104" && -f "$REPORT_FINAL1200" && -f "$REPORT_OLD600" ]]; then
    echo "[ready] $(date '+%F %T %z') all hard reports found" >> "$LOG"
    break
  fi
  sleep 30
done

for pid in "${SERVICE_PIDS[@]}"; do
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "[stop] $(date '+%F %T %z') pid=$pid stopped" >> "$LOG"
  else
    echo "[skip] $(date '+%F %T %z') pid=$pid already exited" >> "$LOG"
  fi
done

echo "[done] $(date '+%F %T %z') auto-stop completed" >> "$LOG"
