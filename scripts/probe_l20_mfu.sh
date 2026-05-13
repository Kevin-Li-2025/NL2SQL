#!/usr/bin/env bash
set -euo pipefail

export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export TOKENIZERS_PARALLELISM=false

PYTHON_BIN="${PYTHON:-python3}"

RUN_BENCHMARKS=0 "$PYTHON_BIN" -m nl2sql_l20.train_lora \
  --config configs/experiment_rich_context_spider_l20_mfu_probe.yaml
