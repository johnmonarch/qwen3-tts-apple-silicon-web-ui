from __future__ import annotations

import os
from pathlib import Path

APP_VERSION = "0.1.0"
WORKER_VERSION = "embedded"
MODEL_REGISTRY_VERSION = "2026.02.16"
SAMPLE_RATE = 24000

BASE_DIR = Path(os.getcwd())
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = DATA_DIR / "config"
MODELS_DIR = DATA_DIR / "models"
VOICES_DIR = DATA_DIR / "voices"
OUTPUTS_DIR = DATA_DIR / "outputs"

SETTINGS_PATH = CONFIG_DIR / "settings.json"
MODEL_REGISTRY_PATH = CONFIG_DIR / "model_registry.json"
VOICES_META_PATH = VOICES_DIR / "voices.json"
OUTPUTS_META_PATH = OUTPUTS_DIR / "outputs.jsonl"

DEFAULT_SETTINGS = {
    "default_model_tier": "Lite",
    "save_outputs": True,
    "output_directory": str(OUTPUTS_DIR),
    "sample_rate": SAMPLE_RATE,
    "bind_host": "127.0.0.1",
    "bind_port": 7860,
    "persist_hf_token": False,
    "hf_token": "",
    "log_raw_text": False,
}

DEFAULT_MODEL_REGISTRY = {
    "version": MODEL_REGISTRY_VERSION,
    "model_sets": [
        {
            "id": "lite-custom",
            "tier": "Lite",
            "capability": "Custom Voice",
            "repo_id": "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit",
            "folder": "Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit",
            "size_gb": 2.2,
            "gated": False,
        },
        {
            "id": "lite-design",
            "tier": "Lite",
            "capability": "Voice Design",
            "repo_id": "mlx-community/Qwen3-TTS-12Hz-0.6B-VoiceDesign-8bit",
            "folder": "Qwen3-TTS-12Hz-0.6B-VoiceDesign-8bit",
            "size_gb": 2.2,
            "gated": False,
        },
        {
            "id": "lite-clone",
            "tier": "Lite",
            "capability": "Base/Clone",
            "repo_id": "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
            "folder": "Qwen3-TTS-12Hz-0.6B-Base-8bit",
            "size_gb": 2.2,
            "gated": False,
        },
        {
            "id": "pro-custom",
            "tier": "Pro",
            "capability": "Custom Voice",
            "repo_id": "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
            "folder": "Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
            "size_gb": 5.8,
            "gated": False,
        },
        {
            "id": "pro-design",
            "tier": "Pro",
            "capability": "Voice Design",
            "repo_id": "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit",
            "folder": "Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit",
            "size_gb": 5.8,
            "gated": False,
        },
        {
            "id": "pro-clone",
            "tier": "Pro",
            "capability": "Base/Clone",
            "repo_id": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit",
            "folder": "Qwen3-TTS-12Hz-1.7B-Base-8bit",
            "size_gb": 5.8,
            "gated": False,
        },
    ],
}

SPEAKERS = [
    "Ryan",
    "Aiden",
    "Ethan",
    "Chelsie",
    "Serena",
    "Vivian",
    "Uncle_Fu",
    "Dylan",
    "Eric",
    "Ono_Anna",
    "Sohee",
]
