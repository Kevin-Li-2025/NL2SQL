#!/usr/bin/env bash
set -euo pipefail

WAIT_FOR_SESSION="${WAIT_FOR_SESSION:-nl2sql_l20}"
BENCHMARK_SUITE="${BENCHMARK_SUITE:-configs/benchmarks_after_train.yaml}"

export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH="${PYTHONPATH:-/home/hhai/nl2sql-l20}"

timestamp() {
  date +"%Y%m%d_%H%M%S"
}

mkdir -p logs
FOLLOWUP_LOG="${FOLLOWUP_LOG:-logs/remote_l20_followup_runs_$(timestamp).log}"
exec > >(tee -a "$FOLLOWUP_LOG") 2>&1

echo "[followup] Waiting for tmux session '${WAIT_FOR_SESSION}' to finish."
while tmux has-session -t "$WAIT_FOR_SESSION" 2>/dev/null; do
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,power.draw \
    --format=csv,noheader,nounits || true
  sleep 120
done

source .venv/bin/activate

run_experiment() {
  local config="$1"
  echo "[followup] Starting ${config}"
  CONFIG="$config" \
    BENCHMARK_SUITE="$BENCHMARK_SUITE" \
    RUN_PROBE=0 \
    RUN_TRAIN=1 \
    RUN_BENCHMARKS=1 \
    INSTALL_DEPS=0 \
    INSTALL_PERF_DEPS=0 \
    bash scripts/remote_l20_train_val.sh
  echo "[followup] Finished ${config}"
}

run_experiment configs/experiment_direct_spider_l20_mfu.yaml
run_experiment configs/experiment_rich_context_spider_l20_mfu_v2.yaml

echo "[followup] All queued experiments finished."
