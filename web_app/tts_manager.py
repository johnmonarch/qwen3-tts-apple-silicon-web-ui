from __future__ import annotations

import gc
import os
import queue
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from .model_registry import ModelRegistry
from .output_manager import OutputManager
from .settings_manager import SettingsManager
from .utils import hash_text, now_iso, resolve_model_path, sanitize_name
from .voice_manager import VoiceManager

try:
    from mlx_audio.tts.generate import generate_audio
    from mlx_audio.tts.utils import load_model

    MLX_AUDIO_AVAILABLE = True
except ImportError:
    generate_audio = None
    load_model = None
    MLX_AUDIO_AVAILABLE = False


MODE_TO_FOLDER = {
    "custom": "CustomVoice",
    "design": "VoiceDesign",
    "clone": "Clones",
}


class TTSManager:
    def __init__(
        self,
        model_registry: ModelRegistry,
        voice_manager: VoiceManager,
        output_manager: OutputManager,
        settings_manager: SettingsManager,
        outputs_dir: Path,
    ) -> None:
        self.model_registry = model_registry
        self.voice_manager = voice_manager
        self.output_manager = output_manager
        self.settings_manager = settings_manager
        self.outputs_dir = outputs_dir

        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()

        self._loaded_model_id: str | None = None
        self._loaded_model: Any = None

        self.worker_url = (os.getenv("WORKER_URL") or "").strip().rstrip("/")
        self.runtime_mode = "remote-worker" if self.worker_url else "embedded-mlx"
        self._http = httpx.Client(timeout=httpx.Timeout(connect=5.0, read=900.0, write=900.0, pool=5.0))

        worker = threading.Thread(target=self._worker_loop, daemon=True)
        worker.start()

    def submit(self, payload: dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())
        job = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "request": payload,
            "result": None,
            "error": None,
            "cancel_requested": False,
        }

        with self._lock:
            self._jobs[job_id] = job

        self._queue.put(job_id)
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return {
                **job,
                "request": dict(job.get("request", {})),
                "result": dict(job.get("result", {})) if isinstance(job.get("result"), dict) else job.get("result"),
            }

    def cancel(self, job_id: str) -> tuple[bool, str | None]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False, "Job not found"

            if job["status"] in {"done", "failed", "cancelled"}:
                return False, f"Job already {job['status']}"

            job["cancel_requested"] = True
            job["updated_at"] = now_iso()
            if job["status"] == "queued":
                job["status"] = "cancelled"
                job["error"] = "Cancelled by user"
        return True, None

    def runtime_health(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "runtime_mode": self.runtime_mode,
            "worker_url": self.worker_url or None,
            "mlx_audio_available": MLX_AUDIO_AVAILABLE,
        }

        if not self.worker_url:
            payload["worker"] = None
            return payload

        try:
            response = self._http.get(f"{self.worker_url}/health")
            response.raise_for_status()
            worker_payload = response.json()
            payload["worker"] = {
                "reachable": True,
                "status": worker_payload.get("status", "ok"),
                "model_loaded": worker_payload.get("model_loaded"),
                "loaded_model_set_id": worker_payload.get("loaded_model_set_id"),
                "mlx_audio_available": worker_payload.get("mlx_audio_available"),
            }
        except Exception as exc:
            payload["worker"] = {
                "reachable": False,
                "status": "unreachable",
                "error": str(exc),
            }

        return payload

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id].update(changes)
            self._jobs[job_id]["updated_at"] = now_iso()

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._process(job_id)
            except Exception as exc:
                self._update(job_id, status="failed", error=str(exc))
            finally:
                self._queue.task_done()

    def _get_model(self, model_set_id: str) -> Any:
        if self._loaded_model_id == model_set_id and self._loaded_model is not None:
            return self._loaded_model

        model_dir = self.model_registry.model_dir(model_set_id)
        if not model_dir:
            raise ValueError("Unknown model set")

        resolved = resolve_model_path(model_dir)
        if not resolved:
            raise FileNotFoundError(f"Model is not installed: {model_set_id}")

        if self._loaded_model is not None:
            self._loaded_model = None
            self._loaded_model_id = None
            gc.collect()

        assert load_model is not None
        self._loaded_model = load_model(str(resolved))
        self._loaded_model_id = model_set_id
        return self._loaded_model

    def _record_success(
        self,
        job_id: str,
        payload: dict[str, Any],
        text: str,
        mode: str,
        model_set_id: str,
        final_path: Path,
        elapsed_ms: int,
    ) -> None:
        settings = self.settings_manager.get()
        log_text = settings.get("log_raw_text", False)

        record = self.output_manager.record(
            {
                "mode": mode,
                "model_set_id": model_set_id,
                "params": {
                    "voice": payload.get("voice"),
                    "instruct": payload.get("instruct"),
                    "speed": payload.get("speed"),
                    "voice_id": payload.get("voice_id"),
                },
                "text_hash": hash_text(text),
                "text": text if log_text else None,
                "output_path": str(final_path),
                "generation_ms": elapsed_ms,
                "status": "done",
            }
        )

        self._update(
            job_id,
            status="done",
            result={
                "output_id": record["id"],
                "output_path": str(final_path),
                "output_url": "/outputs/" + str(final_path.relative_to(self.outputs_dir)),
                "generation_ms": elapsed_ms,
            },
        )

    def _process_remote(
        self,
        job_id: str,
        payload: dict[str, Any],
        text: str,
        mode: str,
        model_set_id: str,
        started_at: float,
    ) -> None:
        request_payload = {
            "mode": mode,
            "model_set_id": model_set_id,
            "text": text,
            "voice": payload.get("voice"),
            "instruct": payload.get("instruct"),
            "speed": payload.get("speed"),
            "voice_id": payload.get("voice_id"),
            "ref_audio_path": payload.get("ref_audio_path"),
            "ref_text": payload.get("ref_text"),
        }

        try:
            response = self._http.post(f"{self.worker_url}/infer", json=request_payload)
            response.raise_for_status()
            result = response.json()
        except httpx.HTTPStatusError as exc:
            message = exc.response.text
            try:
                message = exc.response.json().get("detail", message)
            except Exception:
                pass
            self._update(job_id, status="failed", error=f"Worker inference failed: {message}")
            return
        except Exception as exc:
            self._update(job_id, status="failed", error=f"Worker request failed: {exc}")
            return

        output_rel_path = str(result.get("output_rel_path", "")).lstrip("/")
        if not output_rel_path:
            self._update(job_id, status="failed", error="Worker returned no output path")
            return

        final_path = self.outputs_dir / output_rel_path
        if not final_path.exists():
            self._update(job_id, status="failed", error=f"Output file missing: {final_path}")
            return

        current = self.get_job(job_id)
        if current and current.get("cancel_requested"):
            final_path.unlink(missing_ok=True)
            self._update(job_id, status="cancelled", error="Cancelled by user")
            return

        elapsed_ms = int(result.get("generation_ms") or ((time.time() - started_at) * 1000))
        self._record_success(job_id, payload, text, mode, model_set_id, final_path, elapsed_ms)

    def _process_embedded(
        self,
        job_id: str,
        payload: dict[str, Any],
        text: str,
        mode: str,
        model_set_id: str,
        started_at: float,
    ) -> None:
        temp_dir = self.outputs_dir / ".tmp" / job_id
        temp_dir.mkdir(parents=True, exist_ok=True)

        params: dict[str, Any] = {
            "model": self._get_model(model_set_id),
            "text": text,
            "output_path": str(temp_dir),
        }

        if mode == "custom":
            params["voice"] = payload.get("voice") or "Vivian"
            params["instruct"] = payload.get("instruct") or "Normal tone"
            params["speed"] = float(payload.get("speed") or 1.0)
        elif mode == "design":
            instruct = (payload.get("instruct") or "").strip()
            if not instruct:
                self._update(job_id, status="failed", error="Voice instruction is required for design mode")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return
            params["instruct"] = instruct
        elif mode == "clone":
            voice_id = payload.get("voice_id")
            ref_audio_path = payload.get("ref_audio_path")
            ref_text = payload.get("ref_text")

            if voice_id:
                ref_audio, saved_ref_text, error = self.voice_manager.get_reference(voice_id)
                if error or not ref_audio:
                    self._update(job_id, status="failed", error=error or "Invalid voice reference")
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return
                params["ref_audio"] = str(ref_audio)
                params["ref_text"] = saved_ref_text
            elif ref_audio_path:
                params["ref_audio"] = str(ref_audio_path)
                params["ref_text"] = ref_text or "."
            else:
                self._update(job_id, status="failed", error="Voice clone requires voice_id or ref_audio_path")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return

        try:
            assert generate_audio is not None
            generate_audio(**params)

            current = self.get_job(job_id)
            if current and current.get("cancel_requested"):
                self._update(job_id, status="cancelled", error="Cancelled by user")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return

            generated_files = list(temp_dir.glob("*.wav"))
            if not generated_files:
                generated_files = list(temp_dir.rglob("*.wav"))
            if not generated_files:
                raise RuntimeError("No WAV output generated")

            output_subdir = MODE_TO_FOLDER[mode]
            output_dir = self.outputs_dir / output_subdir
            output_dir.mkdir(parents=True, exist_ok=True)

            text_snippet = sanitize_name(text)[:24]
            filename = f"{int(time.time())}_{text_snippet}.wav"
            final_path = output_dir / filename
            shutil.move(str(generated_files[0]), final_path)

            elapsed_ms = int((time.time() - started_at) * 1000)
            self._record_success(job_id, payload, text, mode, model_set_id, final_path, elapsed_ms)
        except Exception as exc:
            self._update(job_id, status="failed", error=str(exc))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _process(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if not job:
            return

        if job.get("status") == "cancelled":
            return

        if job.get("cancel_requested"):
            self._update(job_id, status="cancelled", error="Cancelled by user")
            return

        payload = job["request"]

        mode = payload.get("mode")
        model_set_id = payload.get("model_set_id")
        text = (payload.get("text") or "").strip()

        if mode not in MODE_TO_FOLDER:
            self._update(job_id, status="failed", error="Unsupported mode")
            return

        if not text:
            self._update(job_id, status="failed", error="Text is required")
            return

        valid, reason = self.model_registry.validate(model_set_id)
        if not valid:
            self._update(job_id, status="failed", error=f"Model not ready: {reason}")
            return

        self._update(job_id, status="running")
        started_at = time.time()

        if self.worker_url:
            self._process_remote(job_id, payload, text, mode, model_set_id, started_at)
            return

        if not MLX_AUDIO_AVAILABLE:
            self._update(job_id, status="failed", error="mlx-audio is not installed in this environment")
            return

        self._process_embedded(job_id, payload, text, mode, model_set_id, started_at)
