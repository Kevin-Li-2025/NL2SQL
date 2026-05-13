#!/usr/bin/env bash
set -euo pipefail

export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export TOKENIZERS_PARALLELISM=false

PYTHON_BIN="${PYTHON:-python3}"
BENCHMARK_SUITE="${BENCHMARK_SUITE:-configs/benchmarks_after_train.yaml}"
BENCHMARK_ARGS=()
if [[ "${RUN_BENCHMARKS:-1}" == "1" ]]; then
  BENCHMARK_ARGS=(--benchmark-suite "$BENCHMARK_SUITE")
fi

"$PYTHON_BIN" -m nl2sql_l20.train_lora \
  --config configs/experiment_rich_context_spider_l20_mfu.yaml \
  "${BENCHMARK_ARGS[@]}"
