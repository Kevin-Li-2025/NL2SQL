#!/usr/bin/env bash
set -euo pipefail

EXPERIMENT_CONFIG="${1:?experiment config required}"
ADAPTER="${2:?adapter path required}"
SUITE="${3:-configs/benchmarks_after_train.yaml}"
PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m nl2sql_l20.benchmark_suite \
  --experiment-config "$EXPERIMENT_CONFIG" \
  --adapter "$ADAPTER" \
  --suite "$SUITE"
