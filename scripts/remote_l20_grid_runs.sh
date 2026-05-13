#!/usr/bin/env bash
set -euo pipefail

BENCHMARK_SUITE="${BENCHMARK_SUITE:-configs/benchmarks_after_train.yaml}"
WAIT_FOR_SESSION="${WAIT_FOR_SESSION:-nl2sql_followup}"
WAIT_FOR_DIRECT_SUMMARY="${WAIT_FOR_DIRECT_SUMMARY:-evals/after_train/direct_spider_qwen25_coder_7b_l20_mfu/summary.json}"
STOP_WAIT_SESSION_AFTER_DIRECT="${STOP_WAIT_SESSION_AFTER_DIRECT:-1}"
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

source .venv/bin/activate

echo "[grid] Waiting for direct Spider/BIRD summary at ${WAIT_FOR_DIRECT_SUMMARY}."
while true; do
  if python - "$WAIT_FOR_DIRECT_SUMMARY" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(1)
summary = json.loads(path.read_text())
benchmarks = summary.get("benchmarks", {})
required = ["spider_dev", "bird_mini_dev"]
if all(benchmarks.get(name, {}).get("status") == "completed" for name in required):
    raise SystemExit(0)
raise SystemExit(1)
PY
  then
    echo "[grid] Direct Spider/BIRD summary is complete."
    break
  fi
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,power.draw \
    --format=csv,noheader,nounits || true
  sleep 120
done

if [[ "$STOP_WAIT_SESSION_AFTER_DIRECT" == "1" ]]; then
  if tmux has-session -t "$WAIT_FOR_SESSION" 2>/dev/null; then
    echo "[grid] Stopping ${WAIT_FOR_SESSION} after direct results to prioritize requested grid."
    tmux kill-session -t "$WAIT_FOR_SESSION"
  fi
fi

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
