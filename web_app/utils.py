from __future__ import annotations

import hashlib
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sanitize_name(value: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", value).strip().replace(" ", "_")
    return cleaned or f"item_{int(time.time())}"


def resolve_model_path(base_dir: Path) -> Path | None:
    if not base_dir.exists():
        return None

    snapshots_dir = base_dir / "snapshots"
    if snapshots_dir.exists():
        children = [child for child in snapshots_dir.iterdir() if child.is_dir()]
        if children:
            return sorted(children)[0]

    return base_dir


def folder_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for file_name in files:
            file_path = Path(root) / file_name
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total


def format_bytes(size: int) -> str:
    if size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size} B"
