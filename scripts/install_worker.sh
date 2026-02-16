#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$ROOT_DIR/.worker-venv"
SYSTEM_ARCH="$(uname -m)"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="python3.11"
  elif [ -x /opt/homebrew/bin/python3.11 ]; then
    PYTHON_BIN="/opt/homebrew/bin/python3.11"
  elif command -v brew >/dev/null 2>&1; then
    BREW_PYTHON_BIN="$(brew --prefix python@3.11 2>/dev/null)/bin/python3.11"
    if [ -x "$BREW_PYTHON_BIN" ]; then
      PYTHON_BIN="$BREW_PYTHON_BIN"
    fi
  fi
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python not found: $PYTHON_BIN"
  echo "Install Python 3.11 with: brew install python@3.11"
  exit 1
fi

PYTHON_ARCH="$("$PYTHON_BIN" -c 'import platform; print(platform.machine())')"
if [ "$SYSTEM_ARCH" = "arm64" ] && [ "$PYTHON_ARCH" != "arm64" ]; then
  echo "Detected architecture mismatch:"
  echo "  Machine architecture: $SYSTEM_ARCH"
  echo "  Python architecture : $PYTHON_ARCH"
  echo
  echo "mlx requires arm64 Python on Apple Silicon."
  echo "Install an arm64 Homebrew Python and rerun:"
  echo "  brew install python@3.11"
  echo "  PYTHON_BIN=/opt/homebrew/bin/python3.11 ./scripts/install_worker.sh"
  echo
  echo "If /opt/homebrew/bin/python3.11 does not exist, install arm64 Homebrew first."
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required for the worker")
PY

echo "Using Python: $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$ROOT_DIR/requirements.txt"

echo
echo "Worker environment is ready."
echo "Start it with: $ROOT_DIR/scripts/start_worker.sh"
echo "Then launch the UI with: docker compose up --build"
