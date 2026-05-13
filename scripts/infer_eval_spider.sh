#!/usr/bin/env bash
set -euo pipefail

CONFIG="${1:?config yaml required}"
ADAPTER="${2:?adapter path required}"
PRED_OUT="${3:-evals/predictions.jsonl}"
RESULT_OUT="${4:-evals/results.json}"
PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m nl2sql_l20.infer \
  --config "$CONFIG" \
  --input data/processed/spider_dev.jsonl \
  --adapter "$ADAPTER" \
  --output "$PRED_OUT"

"$PYTHON_BIN" -m nl2sql_l20.evaluate \
  --gold data/processed/spider_dev.jsonl \
  --pred "$PRED_OUT" \
  --out "$RESULT_OUT" \
  --execute
