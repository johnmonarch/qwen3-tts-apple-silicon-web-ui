from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import DEFAULT_SETTINGS, SETTINGS_PATH
from .storage import read_json, write_json


class SettingsManager:
    def __init__(self, settings_path: Path = SETTINGS_PATH) -> None:
        self.settings_path = settings_path
        self._settings: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if not self.settings_path.exists():
            write_json(self.settings_path, DEFAULT_SETTINGS)
        payload = read_json(self.settings_path, deepcopy(DEFAULT_SETTINGS))
        merged = deepcopy(DEFAULT_SETTINGS)
        merged.update(payload)
        self._settings = merged

    def get(self) -> dict[str, Any]:
        return deepcopy(self._settings)

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        new_settings = deepcopy(self._settings)
        new_settings.update(changes)

        # Avoid persisting token unless explicitly requested.
        if not new_settings.get("persist_hf_token", False):
            new_settings["hf_token"] = ""

        self._settings = new_settings
        write_json(self.settings_path, self._settings)
        return self.get()
