#!/usr/bin/env bash
set -euo pipefail
PYTHON_BIN="${PYTHON:-python3}"
BENCHMARK_SUITE="${BENCHMARK_SUITE:-configs/benchmarks_after_train.yaml}"
BENCHMARK_ARGS=()
if [[ "${RUN_BENCHMARKS:-1}" == "1" ]]; then
  BENCHMARK_ARGS=(--benchmark-suite "$BENCHMARK_SUITE")
fi

"$PYTHON_BIN" -m nl2sql_l20.train_lora \
  --config configs/experiment_direct_spider.yaml \
  "${BENCHMARK_ARGS[@]}"
