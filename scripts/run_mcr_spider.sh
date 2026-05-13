#!/usr/bin/env bash
set -euo pipefail

CONFIG="${1:-configs/pipeline_mcr_l20.yaml}"
ADAPTER="${2:-outputs/rich_context_spider_qwen25_coder_7b}"
PRED_OUT="${3:-evals/mcr_spider_predictions.jsonl}"
RESULT_OUT="${4:-evals/mcr_spider_results.json}"
PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m nl2sql_l20.pipeline \
  --config "$CONFIG" \
  --input data/processed/spider_dev.jsonl \
  --adapter "$ADAPTER" \
  --output "$PRED_OUT"

"$PYTHON_BIN" -m nl2sql_l20.evaluate \
  --gold data/processed/spider_dev.jsonl \
  --pred "$PRED_OUT" \
  --out "$RESULT_OUT" \
  --execute
