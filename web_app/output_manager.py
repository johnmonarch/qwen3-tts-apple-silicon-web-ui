from __future__ import annotations

import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from .config import OUTPUTS_DIR, OUTPUTS_META_PATH
from .storage import append_jsonl, read_jsonl
from .utils import now_iso


class OutputManager:
    def __init__(self, outputs_dir: Path = OUTPUTS_DIR, metadata_path: Path = OUTPUTS_META_PATH) -> None:
        self.outputs_dir = outputs_dir
        self.metadata_path = metadata_path
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict[str, Any]]:
        records = read_jsonl(self.metadata_path)
        return sorted(records, key=lambda item: item.get("timestamp", ""), reverse=True)

    def record(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "id": payload.get("id") or str(uuid.uuid4()),
            "timestamp": payload.get("timestamp") or now_iso(),
            **payload,
        }
        append_jsonl(self.metadata_path, event)
        return event

    def delete(self, output_id: str) -> tuple[bool, str | None]:
        records = self.list()
        match = None
        for item in records:
            if item.get("id") == output_id:
                match = item
                break

        if not match:
            return False, "Output not found"

        output_path = Path(match.get("output_path", ""))
        if output_path.exists() and output_path.is_file():
            output_path.unlink(missing_ok=True)

        remaining = [item for item in records if item.get("id") != output_id]
        self._rewrite(remaining)
        return True, None

    def zip_outputs(self, output_ids: list[str]) -> Path:
        export_dir = self.outputs_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        zip_path = export_dir / f"outputs_{uuid.uuid4().hex[:8]}.zip"

        index = {item.get("id"): item for item in self.list()}
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for output_id in output_ids:
                item = index.get(output_id)
                if not item:
                    continue
                output_path = Path(item.get("output_path", ""))
                if output_path.exists() and output_path.is_file():
                    arcname = f"{item.get('mode', 'audio')}/{output_path.name}"
                    archive.write(output_path, arcname=arcname)

        return zip_path

    def cleanup_exports(self) -> None:
        export_dir = self.outputs_dir / "exports"
        if not export_dir.exists():
            return

        for path in export_dir.iterdir():
            if path.is_file() and path.suffix == ".zip":
                try:
                    path.unlink()
                except OSError:
                    continue
            elif path.is_dir():
                shutil.rmtree(path, ignore_errors=True)

    def _rewrite(self, records: list[dict[str, Any]]) -> None:
        if self.metadata_path.exists():
            self.metadata_path.unlink()
        for item in records:
            append_jsonl(self.metadata_path, item)
