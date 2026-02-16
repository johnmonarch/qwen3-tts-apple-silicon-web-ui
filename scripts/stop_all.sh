#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.worker.pid"
WORKER_PORT="${WORKER_PORT:-7861}"

cd "$ROOT_DIR"

if command -v docker >/dev/null 2>&1; then
  docker compose down >/dev/null 2>&1 || true
fi

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" >/dev/null 2>&1; then
    kill "$PID" || true
  fi
  rm -f "$PID_FILE"
fi

# Fallback: kill any remaining process bound to worker port.
REMAINING_PID="$(lsof -tiTCP:${WORKER_PORT} -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$REMAINING_PID" ]; then
  kill "$REMAINING_PID" >/dev/null 2>&1 || true
fi

echo "Stopped UI and worker processes."
