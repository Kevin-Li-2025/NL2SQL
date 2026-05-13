#!/usr/bin/env bash
set -euo pipefail

WAIT_FOR_SESSION="${WAIT_FOR_SESSION:-nl2sql_grid}"
EXPERIMENT_CONFIG="${EXPERIMENT_CONFIG:-configs/experiment_rich_context_spider_l20_mfu.yaml}"
BENCHMARK_SUITE="${BENCHMARK_SUITE:-configs/benchmarks_spider_sota_vav.yaml}"
ADAPTER="${ADAPTER:-outputs/rich_context_spider_qwen25_coder_7b_l20_mfu}"

export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH="${PYTHONPATH:-/home/hhai/nl2sql-l20/src}"

timestamp() {
  date +"%Y%m%d_%H%M%S"
}

mkdir -p logs
SOTA_LOG="${SOTA_LOG:-logs/remote_l20_sota_spider_vav_$(timestamp).log}"
exec > >(tee -a "$SOTA_LOG") 2>&1

echo "[sota] Waiting for tmux session '${WAIT_FOR_SESSION}' to finish."
while tmux has-session -t "$WAIT_FOR_SESSION" 2>/dev/null; do
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,power.draw \
    --format=csv,noheader,nounits || true
  sleep 120
done

source .venv/bin/activate

echo "[sota] Running Spider n=30 value-aware voting benchmark."
python -m nl2sql_l20.benchmark_suite \
  --experiment-config "$EXPERIMENT_CONFIG" \
  --suite "$BENCHMARK_SUITE" \
  --adapter "$ADAPTER"

echo "[sota] Done."
