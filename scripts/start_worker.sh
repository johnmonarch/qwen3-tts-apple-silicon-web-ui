#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.worker-venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "Worker virtualenv not found. Run: $ROOT_DIR/scripts/install_worker.sh"
  exit 1
fi

source "$VENV_DIR/bin/activate"

export QWEN3_DATA_DIR="${QWEN3_DATA_DIR:-$ROOT_DIR/data}"
export WORKER_HOST="${WORKER_HOST:-127.0.0.1}"
export WORKER_PORT="${WORKER_PORT:-7861}"

echo "Worker preflight:"
echo "  System arch : $(uname -m)"
echo "  Python path : $(command -v python)"
python - <<'PY'
import platform
import sys

print(f"  Python ver  : {sys.version.split()[0]}")
print(f"  Python arch : {platform.machine()}")
import uvicorn  # noqa: F401
print("  Uvicorn     : OK")
PY

python "$ROOT_DIR/worker_app_server.py"
