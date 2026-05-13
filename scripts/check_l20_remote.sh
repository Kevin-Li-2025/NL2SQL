#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-100.111.150.63}"
REMOTE_PORT="${REMOTE_PORT:-22}"
REMOTE_USER="${REMOTE_USER:-hhai}"
REMOTE_DIR="${REMOTE_DIR:-/home/hhai/nl2sql-l20}"
REMOTE_KEY="${REMOTE_KEY:-}"

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
  sshpass -e ssh "${SSH_OPTIONS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" \
    "cd '$REMOTE_DIR' && echo '== GPU ==' && (nvidia-smi || true) && echo '== Logs ==' && ls -lht logs 2>/dev/null | head -20 && echo '== Perf summary ==' && (find outputs -maxdepth 3 -name 'perf.summary.json' -print -exec cat {} \\; 2>/dev/null || true)"
else
  ssh "${SSH_OPTIONS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" \
    "cd '$REMOTE_DIR' && echo '== GPU ==' && (nvidia-smi || true) && echo '== Logs ==' && ls -lht logs 2>/dev/null | head -20 && echo '== Perf summary ==' && (find outputs -maxdepth 3 -name 'perf.summary.json' -print -exec cat {} \\; 2>/dev/null || true)"
fi
