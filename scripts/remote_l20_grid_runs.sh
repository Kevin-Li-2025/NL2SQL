#!/usr/bin/env bash
set -euo pipefail

WAIT_FOR_SESSION="${WAIT_FOR_SESSION:-nl2sql_followup}"
BENCHMARK_SUITE="${BENCHMARK_SUITE:-configs/benchmarks_after_train.yaml}"
RICH_CONTEXT_CONFIG="${RICH_CONTEXT_CONFIG:-configs/experiment_rich_context_spider_l20_mfu.yaml}"
RICH_CONTEXT_ADAPTER="${RICH_CONTEXT_ADAPTER:-outputs/rich_context_spider_qwen25_coder_7b_l20_mfu}"

export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH="${PYTHONPATH:-/home/hhai/nl2sql-l20/src}"

timestamp() {
  date +"%Y%m%d_%H%M%S"
}

mkdir -p logs
GRID_LOG="${GRID_LOG:-logs/remote_l20_grid_runs_$(timestamp).log}"
exec > >(tee -a "$GRID_LOG") 2>&1

echo "[grid] Waiting for tmux session '${WAIT_FOR_SESSION}' to finish."
while tmux has-session -t "$WAIT_FOR_SESSION" 2>/dev/null; do
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,power.draw \
    --format=csv,noheader,nounits || true
  sleep 120
done

source .venv/bin/activate

echo "[grid] Verifying benchmark inputs."
python - <<'PY'
from pathlib import Path
for path in [
    "data/processed/spider_dev.jsonl",
    "data/processed/bird_mini_dev.jsonl",
    "outputs/rich_context_spider_qwen25_coder_7b_l20_mfu",
]:
    p = Path(path)
    print(path, "ok" if p.exists() else "missing")
    if not p.exists():
        raise SystemExit(2)
PY

echo "[grid] Running schema-aware Spider training and Spider/BIRD benchmarks."
CONFIG="configs/experiment_schema_aware_spider_l20_mfu.yaml" \
  BENCHMARK_SUITE="$BENCHMARK_SUITE" \
  RUN_PROBE=0 \
  RUN_TRAIN=1 \
  RUN_BENCHMARKS=1 \
  INSTALL_DEPS=0 \
  INSTALL_PERF_DEPS=0 \
  bash scripts/remote_l20_train_val.sh

echo "[grid] Running rich-context benchmark suite to add BIRD Mini-Dev and BIRD Mini-Dev MCR."
python -m nl2sql_l20.benchmark_suite \
  --experiment-config "$RICH_CONTEXT_CONFIG" \
  --suite "$BENCHMARK_SUITE" \
  --adapter "$RICH_CONTEXT_ADAPTER"

echo "[grid] All requested grid experiments finished."
