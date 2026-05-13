#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-100.111.150.63}"
REMOTE_PORT="${REMOTE_PORT:-22}"
REMOTE_USER="${REMOTE_USER:-hhai}"
REMOTE_DIR="${REMOTE_DIR:-/home/hhai/nl2sql-l20}"
REMOTE_KEY="${REMOTE_KEY:-}"
SESSION_NAME="${SESSION_NAME:-nl2sql_l20}"
REMOTE_BACKGROUND="${REMOTE_BACKGROUND:-1}"
START_REMOTE_JOB="${START_REMOTE_JOB:-1}"

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

SSH_OPTIONS=(
  -p "$REMOTE_PORT"
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout=20
  -o ServerAliveInterval=60
  -o ServerAliveCountMax=30
)
if [[ -n "$REMOTE_KEY" ]]; then
  SSH_OPTIONS+=(-i "$REMOTE_KEY")
fi

if [[ -n "${SSHPASS:-}" ]]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "SSHPASS is set, but sshpass is not installed locally." >&2
    exit 2
  fi
  SSH_PREFIX=(sshpass -e)
else
  SSH_PREFIX=()
fi

remote_target="${REMOTE_USER}@${REMOTE_HOST}"

remote_ssh() {
  "${SSH_PREFIX[@]}" ssh "${SSH_OPTIONS[@]}" "$remote_target" "$@"
}

remote_rsync() {
  rsync_ssh="ssh -p ${REMOTE_PORT} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20"
  if [[ -n "$REMOTE_KEY" ]]; then
    rsync_ssh="$rsync_ssh -i $REMOTE_KEY"
  fi
  "${SSH_PREFIX[@]}" rsync -az --human-readable --progress --stats \
    -e "$rsync_ssh" \
    "$@"
}

echo "[local] Creating remote directory: $remote_target:$REMOTE_DIR"
remote_ssh "mkdir -p '$REMOTE_DIR'"

echo "[local] Uploading project files and prepared data..."
remote_rsync \
  --exclude ".git/" \
  --exclude ".venv/" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude ".pytest_cache/" \
  --exclude ".ruff_cache/" \
  --exclude "outputs/" \
  --exclude "checkpoints/" \
  --exclude "runs/" \
  --exclude "wandb/" \
  --exclude "evals/after_train/" \
  .gitignore LICENSE README.md pyproject.toml \
  configs docs scripts src tests data \
  "$remote_target:$REMOTE_DIR/"

if [[ "$START_REMOTE_JOB" != "1" ]]; then
  echo "[local] Upload complete. START_REMOTE_JOB=0, so training was not started."
  exit 0
fi

remote_env=(
  "CONFIG=$CONFIG"
  "PROBE_CONFIG=$PROBE_CONFIG"
  "BENCHMARK_SUITE=$BENCHMARK_SUITE"
  "RUN_PROBE=$RUN_PROBE"
  "RUN_TRAIN=$RUN_TRAIN"
  "RUN_BENCHMARKS=$RUN_BENCHMARKS"
  "REQUIRE_MFU=$REQUIRE_MFU"
  "ABORT_IF_LOW_MFU=$ABORT_IF_LOW_MFU"
  "INSTALL_DEPS=$INSTALL_DEPS"
  "INSTALL_PERF_DEPS=$INSTALL_PERF_DEPS"
  "ALLOW_FLASH_ATTN_FAILURE=$ALLOW_FLASH_ATTN_FAILURE"
  "TORCH_VERSION=$TORCH_VERSION"
  "TORCH_INDEX_URL=$TORCH_INDEX_URL"
)
remote_env_string="${remote_env[*]}"

if [[ "$REMOTE_BACKGROUND" == "1" ]]; then
  echo "[local] Starting remote background job..."
  remote_ssh "cd '$REMOTE_DIR' && mkdir -p logs && if command -v tmux >/dev/null 2>&1; then tmux new-session -d -s '$SESSION_NAME' '$remote_env_string bash scripts/remote_l20_train_val.sh'; else nohup bash -lc '$remote_env_string bash scripts/remote_l20_train_val.sh' > logs/${SESSION_NAME}.nohup.log 2>&1 & fi"
  echo "[local] Remote job started."
  echo "[local] Tail logs:"
  echo "  ssh -p $REMOTE_PORT $remote_target \"cd '$REMOTE_DIR' && tail -f logs/*.log\""
  echo "[local] Attach tmux if available:"
  echo "  ssh -p $REMOTE_PORT $remote_target \"tmux attach -t '$SESSION_NAME'\""
else
  echo "[local] Running remote job in foreground..."
  remote_ssh "cd '$REMOTE_DIR' && $remote_env_string bash scripts/remote_l20_train_val.sh"
fi
