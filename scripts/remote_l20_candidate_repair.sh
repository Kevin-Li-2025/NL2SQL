#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
RICH_CONFIG="${RICH_CONFIG:-configs/experiment_rich_context_spider_l20_mfu.yaml}"
REPAIR_CONFIG="${REPAIR_CONFIG:-configs/experiment_candidate_repair_spider_l20_mfu.yaml}"
REPAIR_SUITE="${REPAIR_SUITE:-configs/benchmarks_candidate_repair_l20.yaml}"
RICH_ADAPTER="${RICH_ADAPTER:-outputs/rich_context_spider_qwen25_coder_7b_l20_mfu}"
TRAIN_CANDIDATES="${TRAIN_CANDIDATES:-evals/sota/candidate_repair_train/spider_train_candidates/predictions.jsonl}"
TRAIN_REPAIR_JSONL="${TRAIN_REPAIR_JSONL:-data/processed/spider_train_candidate_repair.jsonl}"
TRAIN_REPAIR_MAX_EXAMPLES="${TRAIN_REPAIR_MAX_EXAMPLES:-1800}"
SPIDER_DEV_EGS="${SPIDER_DEV_EGS:-evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_egs_n32/predictions.jsonl}"
BIRD_MINI_MCR="${BIRD_MINI_MCR:-evals/after_train/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_mcr/predictions.jsonl}"

timestamp() {
  date +"%Y%m%d_%H%M%S"
}

LOG_PATH="${LOG_PATH:-logs/remote_l20_candidate_repair_$(timestamp).log}"
mkdir -p "$(dirname "$LOG_PATH")"

wait_for_session() {
  local session="$1"
  while tmux has-session -t "$session" 2>/dev/null; do
    echo "[candidate-repair] Waiting for tmux session $session to finish..."
    sleep 300
  done
}

jsonl_count() {
  if [[ -f "$1" ]]; then
    wc -l < "$1" | tr -d ' '
  else
    echo 0
  fi
}

run_pipeline_if_needed() {
  local output="$1"
  local expected="$2"
  shift 2
  local existing
  existing="$(jsonl_count "$output")"
  if [[ "$existing" == "$expected" ]]; then
    echo "[candidate-repair] Reusing $output ($existing rows)."
    return
  fi
  echo "[candidate-repair] Building $output; found $existing rows, expected $expected."
  "$@"
}

{
  echo "[candidate-repair] Started at $(date -Is)"
  echo "[candidate-repair] Waiting behind existing experiment queue."
  wait_for_session nl2sql_grid
  wait_for_session nl2sql_sota
  wait_for_session nl2sql_egs

  export PYTHONPATH="$PWD/src:${PYTHONPATH:-}"
  export TOKENIZERS_PARALLELISM=false
  export TRANSFORMERS_VERBOSITY=error

  echo "[candidate-repair] GPU before run:"
  nvidia-smi --query-gpu=timestamp,name,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits || true

  mkdir -p "$(dirname "$TRAIN_CANDIDATES")"
  run_pipeline_if_needed "$TRAIN_CANDIDATES" "$TRAIN_REPAIR_MAX_EXAMPLES" \
    "$PYTHON_BIN" -m nl2sql_l20.pipeline \
      --config configs/pipeline_train_candidates_l20.yaml \
      --input data/processed/spider_train_no_value_hints.jsonl \
      --output "$TRAIN_CANDIDATES" \
      --adapter "$RICH_ADAPTER" \
      --architectures rich_context,decompose,query_plan,skeleton,execution_first \
      --samples-per-architecture 2 \
      --temperature 0.45 \
      --top-p 0.95 \
      --selection-strategy execution_guided_rerank \
      --max-examples "$TRAIN_REPAIR_MAX_EXAMPLES"

  echo "[candidate-repair] Building repair SFT data."
  "$PYTHON_BIN" -m nl2sql_l20.candidate_data \
    --gold data/processed/spider_train_no_value_hints.jsonl \
    --pred "$TRAIN_CANDIDATES" \
    --out "$TRAIN_REPAIR_JSONL" \
    --max-candidates 16 \
    --max-examples "$TRAIN_REPAIR_MAX_EXAMPLES" \
    --no-label-candidates

  mkdir -p "$(dirname "$SPIDER_DEV_EGS")"
  run_pipeline_if_needed "$SPIDER_DEV_EGS" 1034 \
    "$PYTHON_BIN" -m nl2sql_l20.pipeline \
      --config configs/pipeline_spider_egs_l20.yaml \
      --input data/processed/spider_dev.jsonl \
      --output "$SPIDER_DEV_EGS" \
      --adapter "$RICH_ADAPTER" \
      --architectures rich_context,execution_first,query_plan,skeleton \
      --samples-per-architecture 8 \
      --temperature 0.45 \
      --top-p 0.95 \
      --selection-strategy execution_guided_rerank

  mkdir -p "$(dirname "$BIRD_MINI_MCR")"
  run_pipeline_if_needed "$BIRD_MINI_MCR" 500 \
    "$PYTHON_BIN" -m nl2sql_l20.pipeline \
      --config configs/pipeline_mcr_l20.yaml \
      --input data/processed/bird_mini_dev.jsonl \
      --output "$BIRD_MINI_MCR" \
      --adapter "$RICH_ADAPTER" \
      --architectures rich_context,decompose,query_plan,skeleton \
      --samples-per-architecture 2 \
      --temperature 0.35 \
      --top-p 0.95 \
      --selection-strategy execution_consistency

  echo "[candidate-repair] Training candidate-repair adapter and running benchmarks."
  "$PYTHON_BIN" -m nl2sql_l20.train_lora \
    --config "$REPAIR_CONFIG" \
    --benchmark-suite "$REPAIR_SUITE"

  echo "[candidate-repair] Finished at $(date -Is)"
} 2>&1 | tee "$LOG_PATH"
