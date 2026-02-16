#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.worker.pid"
LOG_FILE="$ROOT_DIR/.worker.log"
WORKER_HEALTH_URL="${WORKER_HEALTH_URL:-http://127.0.0.1:7861/health}"
WORKER_START_TIMEOUT_SECONDS="${WORKER_START_TIMEOUT_SECONDS:-45}"

cd "$ROOT_DIR"

if ! curl -fsS "$WORKER_HEALTH_URL" >/dev/null 2>&1; then
  echo "Starting host worker..."
  nohup "$ROOT_DIR/scripts/start_worker.sh" >"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
fi

echo "Waiting for worker health..."
WORKER_READY=0
for _ in $(seq 1 "$WORKER_START_TIMEOUT_SECONDS"); do
  if curl -fsS "$WORKER_HEALTH_URL" >/dev/null 2>&1; then
    WORKER_READY=1
    break
  fi
  sleep 1
done

if [ "$WORKER_READY" -ne 1 ]; then
  echo "Worker failed to start within ${WORKER_START_TIMEOUT_SECONDS}s. Check $LOG_FILE"
  if [ -f "$LOG_FILE" ]; then
    echo
    echo "--- Last worker log lines ---"
    tail -n 80 "$LOG_FILE" || true
    echo "--- End worker log ---"
  fi
  exit 1
fi

echo "Starting Docker UI..."
docker compose up -d --build

echo "Ready: http://127.0.0.1:7860"
