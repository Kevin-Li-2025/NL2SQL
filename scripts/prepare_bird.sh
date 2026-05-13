#!/usr/bin/env bash
set -euo pipefail

BIRD_DIR="${1:-data/raw/bird}"
SPLIT="${2:-dev}"
PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m nl2sql_l20.prepare bird \
  --bird-dir "$BIRD_DIR" \
  --split "$SPLIT" \
  --out "data/processed/bird_${SPLIT}.jsonl"
