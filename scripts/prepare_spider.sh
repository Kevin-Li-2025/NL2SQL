#!/usr/bin/env bash
set -euo pipefail

SPIDER_DIR="${1:-data/raw/spider}"
PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m nl2sql_l20.prepare spider \
  --spider-dir "$SPIDER_DIR" \
  --split train \
  --out data/processed/spider_train_no_value_hints.jsonl \
  --max-value-hints 0

"$PYTHON_BIN" -m nl2sql_l20.prepare spider \
  --spider-dir "$SPIDER_DIR" \
  --split dev \
  --out data/processed/spider_dev.jsonl
