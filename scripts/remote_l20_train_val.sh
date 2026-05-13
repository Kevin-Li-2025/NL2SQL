#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-python3}"
CONFIG="${CONFIG:-configs/experiment_rich_context_spider_l20_mfu.yaml}"
PROBE_CONFIG="${PROBE_CONFIG:-configs/experiment_rich_context_spider_l20_mfu_probe.yaml}"
BENCHMARK_SUITE="${BENCHMARK_SUITE:-configs/benchmarks_after_train.yaml}"
RUN_PROBE="${RUN_PROBE:-1}"
RUN_TRAIN="${RUN_TRAIN:-1}"
RUN_BENCHMARKS="${RUN_BENCHMARKS:-1}"
REQUIRE_MFU="${REQUIRE_MFU:-0.60}"
ABORT_IF_LOW_MFU="${ABORT_IF_LOW_MFU:-1}"
INSTALL_DEPS="${INSTALL_DEPS:-1}"
INSTALL_PERF_DEPS="${INSTALL_PERF_DEPS:-1}"
ALLOW_FLASH_ATTN_FAILURE="${ALLOW_FLASH_ATTN_FAILURE:-0}"
TORCH_VERSION="${TORCH_VERSION:-2.6.0+cu124}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu124}"
FLASH_ATTN_WHEEL_URL="${FLASH_ATTN_WHEEL_URL:-}"

export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export TOKENIZERS_PARALLELISM=false

timestamp() {
  date +"%Y%m%d_%H%M%S"
}

mkdir -p logs
RUN_LOG="${RUN_LOG:-logs/remote_l20_train_val_$(timestamp).log}"
exec > >(tee -a "$RUN_LOG") 2>&1

if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate

if [[ "$INSTALL_DEPS" == "1" ]]; then
  python -m pip install --upgrade pip setuptools wheel
  python -m pip install --index-url "$TORCH_INDEX_URL" "torch==$TORCH_VERSION"
  python -m pip install --no-build-isolation -e ".[train]"
  if [[ "$INSTALL_PERF_DEPS" == "1" ]]; then
    python -m pip install "liger-kernel>=0.5.0"
    if [[ -n "$FLASH_ATTN_WHEEL_URL" ]]; then
      echo "[remote] Installing flash-attn from prebuilt wheel"
      python -m pip install "$FLASH_ATTN_WHEEL_URL"
    fi
    if ! python -m pip install "flash-attn>=2.6.3" --no-build-isolation; then
      if [[ "$ALLOW_FLASH_ATTN_FAILURE" == "1" ]]; then
        echo "[remote] flash-attn install failed; continuing because ALLOW_FLASH_ATTN_FAILURE=1"
      else
        echo "[remote] flash-attn install failed; aborting because MFU config requires it"
        exit 42
      fi
    fi
  fi
fi

python - <<'PY'
import torch
print("torch", torch.__version__)
print("cuda_available", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device", torch.cuda.get_device_name(0))
    props = torch.cuda.get_device_properties(0)
    print("total_memory_gb", round(props.total_memory / 1024**3, 2))
PY

if [[ "$RUN_PROBE" == "1" ]]; then
  echo "[remote] Running MFU probe: $PROBE_CONFIG"
  RUN_BENCHMARKS=0 python -m nl2sql_l20.train_lora \
    --config "$PROBE_CONFIG" \
    2>&1 | tee "logs/probe_$(timestamp).log"

  PROBE_SUMMARY="$(python - <<'PY'
from pathlib import Path
from nl2sql_l20.config import load_config

config = load_config("configs/experiment_rich_context_spider_l20_mfu_probe.yaml")
summary = Path(config["training"]["output_dir"]) / "perf.summary.json"
print(summary)
PY
)"

  python - "$PROBE_SUMMARY" "$REQUIRE_MFU" "$ABORT_IF_LOW_MFU" <<'PY'
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
required = float(sys.argv[2])
abort = sys.argv[3] == "1"

if not summary_path.exists():
    print(f"[remote] MFU summary not found: {summary_path}")
    if abort:
        raise SystemExit(42)
    raise SystemExit(0)

summary = json.loads(summary_path.read_text())
mfu = float(summary.get("avg_tail_dense_mfu", 0.0))
tok_s = float(summary.get("avg_tail_tokens_per_second", 0.0))
print(f"[remote] Probe tail avg tok/s={tok_s:.1f}, dense_mfu={mfu:.3f}, required={required:.3f}")

if abort and mfu < required:
    print("[remote] MFU target not met; aborting full training. Tune batch/seq/kernel config first.")
    raise SystemExit(42)
PY
fi

if [[ "$RUN_TRAIN" == "1" ]]; then
  echo "[remote] Running full training: $CONFIG"
  BENCHMARK_ARGS=()
  if [[ "$RUN_BENCHMARKS" == "1" ]]; then
    BENCHMARK_ARGS=(--benchmark-suite "$BENCHMARK_SUITE")
  fi

  python -m nl2sql_l20.train_lora \
    --config "$CONFIG" \
    "${BENCHMARK_ARGS[@]}" \
    2>&1 | tee "logs/train_val_$(timestamp).log"
fi

echo "[remote] Done."
