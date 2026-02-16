from __future__ import annotations

from pathlib import Path
from typing import Any

from web_app.storage import read_json

from .config import DEFAULT_REGISTRY_MAP, MODEL_REGISTRY_PATH


class WorkerModelRegistry:
    def __init__(self, registry_path: Path = MODEL_REGISTRY_PATH) -> None:
        self.registry_path = registry_path
        self._map: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        payload = read_json(self.registry_path, {"model_sets": []})
        model_sets = payload.get("model_sets", [])

        loaded: dict[str, dict[str, Any]] = {}
        for item in model_sets:
            item_id = item.get("id")
            if not item_id:
                continue
            loaded[str(item_id)] = item

        if loaded:
            self._map = loaded
        else:
            self._map = dict(DEFAULT_REGISTRY_MAP)

    def get(self, model_set_id: str) -> dict[str, Any] | None:
        return self._map.get(model_set_id)
