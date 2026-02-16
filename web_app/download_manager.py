from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import HfHubHTTPError

from .model_registry import ModelRegistry
from .utils import now_iso


class DownloadManager:
    def __init__(self, model_registry: ModelRegistry) -> None:
        self.model_registry = model_registry
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start_download(self, model_set_id: str, revision: str | None = None, token: str | None = None) -> str:
        job_id = str(uuid.uuid4())
        job = {
            "job_id": job_id,
            "model_set_id": model_set_id,
            "status": "queued",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "progress": {
                "percent": 0,
                "files_total": 0,
                "files_done": 0,
                "bytes_total": 0,
                "bytes_downloaded": 0,
                "download_rate_bps": 0.0,
                "eta_seconds": None,
                "last_file": None,
                "message": "Queued",
                "started_at": now_iso(),
            },
            "error": None,
        }

        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_download,
            args=(job_id, model_set_id, revision, token),
            daemon=True,
        )
        thread.start()
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return {**job, "progress": {**job.get("progress", {})}}

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id].update(changes)
            self._jobs[job_id]["updated_at"] = now_iso()

    def _update_progress(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            progress = dict(job.get("progress", {}))
            progress.update(changes)
            job["progress"] = progress
            job["updated_at"] = now_iso()

    def _run_download(self, job_id: str, model_set_id: str, revision: str | None, token: str | None) -> None:
        model_set = self.model_registry.get(model_set_id)
        if not model_set:
            self._update(job_id, status="failed", error="Unknown model set")
            return

        repo_id = model_set["repo_id"]
        model_dir = self.model_registry.model_dir(model_set_id)
        if model_dir is None:
            self._update(job_id, status="failed", error="Invalid model path")
            return

        model_dir.mkdir(parents=True, exist_ok=True)
        self._update(job_id, status="running")
        self._update_progress(job_id, message=f"Fetching file list from {repo_id}")

        try:
            api = HfApi(token=token)
            files = api.list_repo_files(repo_id=repo_id, repo_type="model", revision=revision)
            model_info = api.model_info(
                repo_id=repo_id,
                revision=revision,
                files_metadata=True,
                token=token,
            )

            if not files:
                self._update(job_id, status="failed", error="Repository contains no files")
                return

            files = [name for name in files if not name.endswith(".gitattributes")]
            total_files = len(files)

            file_size_map: dict[str, int] = {}
            for sibling in (model_info.siblings or []):
                path = getattr(sibling, "rfilename", None)
                size = getattr(sibling, "size", None)
                if path and isinstance(size, int) and size > 0:
                    file_size_map[path] = size

            total_expected_bytes = sum(file_size_map.get(file_name, 0) for file_name in files)
            downloaded_bytes = 0
            started_at = time.monotonic()

            self._update_progress(
                job_id,
                files_total=total_files,
                bytes_total=total_expected_bytes,
                message="Starting download",
            )

            for index, file_name in enumerate(files, start=1):
                self._update_progress(
                    job_id,
                    files_done=index - 1,
                    last_file=file_name,
                    message=f"Downloading {file_name}",
                )

                resolved_path = hf_hub_download(
                    repo_id=repo_id,
                    filename=file_name,
                    repo_type="model",
                    revision=revision,
                    token=token,
                    local_dir=str(model_dir),
                )

                try:
                    downloaded_bytes += Path(resolved_path).stat().st_size
                except OSError:
                    downloaded_bytes += file_size_map.get(file_name, 0)

                elapsed = max(time.monotonic() - started_at, 1e-6)
                download_rate_bps = float(downloaded_bytes) / elapsed
                percent_by_files = (index / total_files) * 100.0
                percent_by_bytes = (
                    (downloaded_bytes / total_expected_bytes) * 100.0 if total_expected_bytes > 0 else percent_by_files
                )
                percent = round(max(percent_by_files, percent_by_bytes), 1)
                eta_seconds = None
                if total_expected_bytes > 0 and download_rate_bps > 0:
                    remaining = max(total_expected_bytes - downloaded_bytes, 0)
                    eta_seconds = round(remaining / download_rate_bps, 1)

                self._update_progress(
                    job_id,
                    percent=percent,
                    files_done=index,
                    bytes_downloaded=downloaded_bytes,
                    bytes_total=total_expected_bytes,
                    download_rate_bps=round(download_rate_bps, 1),
                    eta_seconds=eta_seconds,
                    last_file=file_name,
                    message="Downloading",
                )

            valid, reason = self.model_registry.validate(model_set_id)
            if not valid:
                self._update(job_id, status="failed", error=f"Validation failed: {reason}")
                self._update_progress(job_id, message="Validation failed")
                return

            self._update(job_id, status="done")
            self._update_progress(
                job_id,
                percent=100.0,
                files_done=total_files,
                bytes_downloaded=downloaded_bytes,
                bytes_total=total_expected_bytes,
                eta_seconds=0.0,
                message="Download completed",
            )
        except HfHubHTTPError as exc:
            reason = str(exc).split("\n", 1)[0]
            self._update(job_id, status="failed", error=reason)
            self._update_progress(job_id, message="Download failed")
        except Exception as exc:
            self._update(job_id, status="failed", error=str(exc))
            self._update_progress(job_id, message="Download failed")
