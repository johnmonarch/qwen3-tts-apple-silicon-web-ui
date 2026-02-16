from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import DEFAULT_MODEL_REGISTRY, MODEL_REGISTRY_PATH, MODELS_DIR
from .storage import read_json, write_json
from .utils import folder_size_bytes


class ModelRegistry:
    def __init__(self, registry_path: Path = MODEL_REGISTRY_PATH, models_dir: Path = MODELS_DIR) -> None:
        self.registry_path = registry_path
        self.models_dir = models_dir
        self._registry: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if not self.registry_path.exists():
            write_json(self.registry_path, DEFAULT_MODEL_REGISTRY)
        payload = read_json(self.registry_path, DEFAULT_MODEL_REGISTRY)
        if "model_sets" not in payload:
            payload = DEFAULT_MODEL_REGISTRY
        self._registry = payload

    @property
    def version(self) -> str:
        return str(self._registry.get("version", "unknown"))

    def available(self) -> list[dict[str, Any]]:
        return list(self._registry.get("model_sets", []))

    def get(self, model_set_id: str) -> dict[str, Any] | None:
        for item in self.available():
            if item.get("id") == model_set_id:
                return item
        return None

    def model_dir(self, model_set_id: str) -> Path | None:
        model = self.get(model_set_id)
        if not model:
            return None
        folder = model.get("folder")
        if not folder:
            return None
        return self.models_dir / folder

    def validate(self, model_set_id: str) -> tuple[bool, str]:
        model_path = self.model_dir(model_set_id)
        if not model_path:
            return False, "Unknown model set"
        if not model_path.exists():
            return False, "Model folder not found"

        file_paths = [path for path in model_path.rglob("*") if path.is_file()]
        if not file_paths:
            return False, "Model folder is empty"

        file_names = [path.name for path in file_paths]
        weight_suffixes = (
            ".safetensors",
            ".bin",
            ".gguf",
            ".mlx",
            ".npz",
            ".pt",
            ".pth",
        )
        has_weight_suffix = any(name.endswith(weight_suffixes) for name in file_names)
        has_large_artifact = False
        for path in file_paths:
            # Ignore hub cache metadata files under local_dir/.cache.
            if ".cache" in path.parts:
                continue
            try:
                if path.stat().st_size >= 50 * 1024 * 1024:
                    has_large_artifact = True
                    break
            except OSError:
                continue

        has_weights = has_weight_suffix or has_large_artifact
        has_config = any(name in {"config.json", "tokenizer.json"} for name in file_names)

        if not has_weights:
            return False, "Model weights missing (expected weight files or large model artifacts)"
        if not has_config:
            return False, "Model config/tokenizer files missing"

        return True, "OK"

    def installed(self) -> list[dict[str, Any]]:
        installed_models: list[dict[str, Any]] = []
        for model_set in self.available():
            model_set_id = model_set["id"]
            model_dir = self.model_dir(model_set_id)
            if not model_dir or not model_dir.exists():
                continue

            valid, reason = self.validate(model_set_id)
            installed_models.append(
                {
                    **model_set,
                    "path": str(model_dir),
                    "size_bytes": folder_size_bytes(model_dir),
                    "valid": valid,
                    "validation_message": reason,
                }
            )
        return installed_models

    def remove(self, model_set_id: str) -> bool:
        model_dir = self.model_dir(model_set_id)
        if not model_dir or not model_dir.exists():
            return False
        shutil.rmtree(model_dir, ignore_errors=True)
        return True
