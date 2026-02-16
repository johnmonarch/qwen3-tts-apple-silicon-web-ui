# Qwen3-TTS for Mac (Apple Silicon)

Run Qwen3-TTS locally on macOS with a browser UI.

This project uses a split runtime:
- Docker container: web UI + API + model downloads
- Host macOS process: MLX inference worker

## Why this setup?

MLX needs native macOS/Metal. Docker Desktop runs Linux containers, so inference runs on the host while the UI/API runs in Docker.

## Quick Start (copy/paste)

```bash
cd /path/to/qwen3-tts-apple-silicon
brew install ffmpeg
./scripts/install_everything.sh
```

Then open [http://127.0.0.1:7860](http://127.0.0.1:7860).

## First-Time Setup (Detailed)

### 1) Install prerequisites

- macOS on Apple Silicon (M1/M2/M3/M4)
- Docker Desktop installed and running
- Homebrew installed

Install required tools:

```bash
brew install ffmpeg python@3.11
```

Important on Apple Silicon:
- Use an arm64 terminal session (not Rosetta).
- `python3.11` must report `arm64`, not `x86_64`.

### 2) Go to this repo

```bash
cd /path/to/qwen3-tts-apple-silicon
```

### 3) Ensure scripts are executable (safe to run)

```bash
chmod +x ./scripts/*.sh
```

### 4) Install worker environment (one-time)

```bash
./scripts/install_worker.sh
```

If you get `Python 3.10+ is required for the worker`, run:

```bash
PYTHON_BIN="$(brew --prefix python@3.11)/bin/python3.11" ./scripts/install_worker.sh
```

If needed, discover Python paths:

```bash
which -a python3 python3.11
```

Check Python architecture:

```bash
python3.11 -c "import platform; print(platform.machine())"
```

### 5) Start everything

```bash
./scripts/start_all.sh
```

Open [http://127.0.0.1:7860](http://127.0.0.1:7860).

## Daily Use

Start app stack:

```bash
cd /path/to/qwen3-tts-apple-silicon
./scripts/start_all.sh
```

Stop app stack:

```bash
cd /path/to/qwen3-tts-apple-silicon
./scripts/stop_all.sh
```

## One-command first install + start

```bash
cd /path/to/qwen3-tts-apple-silicon
./scripts/install_everything.sh
```

## Manual Start (if you want separate control)

Start worker only:

```bash
./scripts/start_worker.sh
```

Start Docker UI/API only:

```bash
docker compose up -d --build
```

Stop Docker UI/API only:

```bash
docker compose down
```

## What to do in the UI

- `Models`: download Lite/Pro model sets from Hugging Face
- `Generate`: Custom Voice, Voice Design, Voice Clone
- `Voices`: enroll / rename / delete saved references
- `Outputs`: replay WAV, delete, ZIP export
- `Settings`: default tier and token behavior

## Data location

All local data is stored in:

```text
data/
  config/
  models/
  voices/
  outputs/
```

## Troubleshooting

`Python 3.10+ is required for the worker`
- Install modern Python: `brew install python@3.11`
- Re-run with explicit interpreter:
  - `PYTHON_BIN="$(brew --prefix python@3.11)/bin/python3.11" ./scripts/install_worker.sh`

`mlx==0.30.3` no matching distribution (or Python shows `x86_64` on Apple Silicon)
- You are using an x86 (Rosetta) Python. MLX requires arm64 Python.
- Check machine and python architecture:
  - `uname -m`
  - `python3.11 -c "import platform; print(platform.machine())"`
- Install/use arm64 Python and rerun:
  - `brew install python@3.11`
  - `PYTHON_BIN=/opt/homebrew/bin/python3.11 ./scripts/install_worker.sh`
- If `/opt/homebrew/bin/python3.11` is missing, install arm64 Homebrew first.
  - `arch -arm64 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
  - `eval "$(/opt/homebrew/bin/brew shellenv)"`
  - `/opt/homebrew/bin/brew install python@3.11 ffmpeg`

`No matching distribution found for audioop-lts==0.2.2`
- Pull latest repo changes (requirements now include Python-version markers)
- Re-run worker install:
  - `PYTHON_BIN="$(brew --prefix python@3.11)/bin/python3.11" ./scripts/install_worker.sh`

`Worker offline` in sidebar
- Ensure worker is running: `./scripts/start_worker.sh`
- Check health endpoint: `curl http://127.0.0.1:7861/health`

UI not reachable
- Check container logs:
  - `docker compose logs -f ui`

`Python quit unexpectedly` with stack trace in `libmlx.dylib` / `NSRangeException`
- This is an MLX Metal initialization crash, not a regular Python package install error.
- If crash report shows `Responsible Process: Codex`, run setup/start commands from macOS Terminal.app (or iTerm), not from an embedded/sandboxed shell.
- In a normal terminal session, re-run:
  - `PYTHON_BIN=/opt/homebrew/bin/python3.11 ./scripts/install_worker.sh`
  - `./scripts/start_all.sh`
- If it still crashes in normal terminal, try MLX upgrades inside `.worker-venv`:
  - `source .worker-venv/bin/activate`
  - `pip install -U mlx mlx-metal mlx-lm mlx-audio`

Model download fails
- Add HF token in Models tab or set `HF_TOKEN`
- Check internet access to Hugging Face

`mlx-audio is not installed in worker environment`
- Re-run worker installer:
  - `./scripts/install_worker.sh`

## Optional: Local non-Docker UI mode

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python web_app_server.py
```

## Legacy CLI mode

```bash
source .venv/bin/activate
python main.py
```

## Related Projects

- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)
- [MLX Audio](https://github.com/Blaizzy/mlx-audio)
- [MLX Community](https://huggingface.co/mlx-community)
