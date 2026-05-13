#!/usr/bin/env bash
set -euo pipefail

SPIDER_REPO="${1:?path to taoyds/spider repo required}"
PRED_JSONL="${2:-evals/predictions.jsonl}"
OUT_DIR="${3:-evals/spider_official}"
SPIDER_DATA="${4:-data/raw/spider}"
PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m nl2sql_l20.export_spider \
  --gold-jsonl data/processed/spider_dev.jsonl \
  --pred-jsonl "$PRED_JSONL" \
  --out-dir "$OUT_DIR"

"$PYTHON_BIN" "$SPIDER_REPO/evaluation.py" \
  --gold "$OUT_DIR/gold.txt" \
  --pred "$OUT_DIR/pred.txt" \
  --db "$SPIDER_DATA/database" \
  --table "$SPIDER_DATA/tables.json" \
  --etype all
