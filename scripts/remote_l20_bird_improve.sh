#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
RICH_CONFIG="${RICH_CONFIG:-configs/experiment_rich_context_spider_l20_mfu.yaml}"
BIRD_SUITE="${BIRD_SUITE:-configs/benchmarks_bird_improve_l20.yaml}"
RICH_ADAPTER="${RICH_ADAPTER:-outputs/rich_context_spider_qwen25_coder_7b_l20_mfu}"

timestamp() {
  date +"%Y%m%d_%H%M%S"
}

LOG_PATH="${LOG_PATH:-logs/remote_l20_bird_improve_$(timestamp).log}"
mkdir -p "$(dirname "$LOG_PATH")"

wait_for_session() {
  local session="$1"
  while tmux has-session -t "$session" 2>/dev/null; do
    echo "[bird-improve] Waiting for tmux session $session to finish..."
    sleep 300
  done
}

{
  echo "[bird-improve] Started at $(date -Is)"
  echo "[bird-improve] Waiting behind active Spider/repair queue."
  wait_for_session nl2sql_grid
  wait_for_session nl2sql_sota
  wait_for_session nl2sql_egs
  wait_for_session nl2sql_repair

  export PYTHONPATH="$PWD/src:${PYTHONPATH:-}"
  export TOKENIZERS_PARALLELISM=false
  export TRANSFORMERS_VERBOSITY=error

  echo "[bird-improve] GPU before run:"
  nvidia-smi --query-gpu=timestamp,name,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits || true

  echo "[bird-improve] Running BIRD Mini-Dev VAV n=12 and EGS n=16."
  "$PYTHON_BIN" -m nl2sql_l20.benchmark_suite \
    --experiment-config "$RICH_CONFIG" \
    --suite "$BIRD_SUITE" \
    --adapter "$RICH_ADAPTER"

  echo "[bird-improve] Finished at $(date -Is)"
} 2>&1 | tee "$LOG_PATH"
