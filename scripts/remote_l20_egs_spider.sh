#!/usr/bin/env bash
set -euo pipefail

WAIT_FOR_SESSION="${WAIT_FOR_SESSION:-nl2sql_sota}"
EXPERIMENT_CONFIG="${EXPERIMENT_CONFIG:-configs/experiment_rich_context_spider_l20_mfu.yaml}"
BENCHMARK_SUITE="${BENCHMARK_SUITE:-configs/benchmarks_spider_egs.yaml}"
ADAPTER="${ADAPTER:-outputs/rich_context_spider_qwen25_coder_7b_l20_mfu}"

export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH="${PYTHONPATH:-/home/hhai/nl2sql-l20/src}"

timestamp() {
  date +"%Y%m%d_%H%M%S"
}

mkdir -p logs
EGS_LOG="${EGS_LOG:-logs/remote_l20_egs_spider_$(timestamp).log}"
exec > >(tee -a "$EGS_LOG") 2>&1

echo "[egs] Waiting for tmux session '${WAIT_FOR_SESSION}' to finish."
while tmux has-session -t "$WAIT_FOR_SESSION" 2>/dev/null; do
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,power.draw \
    --format=csv,noheader,nounits || true
  sleep 120
done

source .venv/bin/activate

echo "[egs] Running Spider n=32 execution-guided schema rerank benchmark."
python -m nl2sql_l20.benchmark_suite \
  --experiment-config "$EXPERIMENT_CONFIG" \
  --suite "$BENCHMARK_SUITE" \
  --adapter "$ADAPTER"

echo "[egs] Done."
