from __future__ import annotations

import os
from pathlib import Path

from web_app.config import DEFAULT_MODEL_REGISTRY

data_dir_env = os.getenv("QWEN3_DATA_DIR", "").strip()
DATA_DIR = Path(data_dir_env).expanduser() if data_dir_env else (Path.cwd() / "data")

CONFIG_DIR = DATA_DIR / "config"
MODELS_DIR = DATA_DIR / "models"
VOICES_DIR = DATA_DIR / "voices"
OUTPUTS_DIR = DATA_DIR / "outputs"

MODEL_REGISTRY_PATH = CONFIG_DIR / "model_registry.json"

MODE_TO_FOLDER = {
    "custom": "CustomVoice",
    "design": "VoiceDesign",
    "clone": "Clones",
}

DEFAULT_REGISTRY_MAP = {
    item["id"]: item for item in DEFAULT_MODEL_REGISTRY["model_sets"]
}
