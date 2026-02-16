from __future__ import annotations

import gc
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from web_app.utils import resolve_model_path, sanitize_name

from .config import MODELS_DIR, MODE_TO_FOLDER, OUTPUTS_DIR, VOICES_DIR
from .model_registry import WorkerModelRegistry

try:
    from mlx_audio.tts.generate import generate_audio
    from mlx_audio.tts.utils import load_model

    MLX_AUDIO_AVAILABLE = True
except ImportError:
    generate_audio = None
    load_model = None
    MLX_AUDIO_AVAILABLE = False


class InferenceEngine:
    def __init__(self) -> None:
        self.registry = WorkerModelRegistry()
        self._lock = threading.Lock()
        self._loaded_model_id: str | None = None
        self._loaded_model: Any = None

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "mlx_audio_available": MLX_AUDIO_AVAILABLE,
            "model_loaded": self._loaded_model is not None,
            "loaded_model_set_id": self._loaded_model_id,
        }

    def _get_model(self, model_set_id: str) -> Any:
        if self._loaded_model_id == model_set_id and self._loaded_model is not None:
            return self._loaded_model

        model_set = self.registry.get(model_set_id)
        if not model_set:
            raise ValueError(f"Unknown model set: {model_set_id}")

        model_dir = MODELS_DIR / str(model_set["folder"])
        resolved = resolve_model_path(model_dir)
        if not resolved:
            raise FileNotFoundError(f"Model folder not found: {model_dir}")

        if self._loaded_model is not None:
            self._loaded_model = None
            self._loaded_model_id = None
            gc.collect()

        assert load_model is not None
        self._loaded_model = load_model(str(resolved))
        self._loaded_model_id = model_set_id
        return self._loaded_model

    def _resolve_clone_reference(self, payload: dict[str, Any]) -> tuple[str, str]:
        voice_id = payload.get("voice_id")
        ref_audio_path = payload.get("ref_audio_path")
        ref_text = payload.get("ref_text")

        if voice_id:
            wav_path = VOICES_DIR / f"{voice_id}.wav"
            txt_path = VOICES_DIR / f"{voice_id}.txt"
            if not wav_path.exists():
                raise FileNotFoundError(f"Voice reference missing: {wav_path}")
            transcript = "."
            if txt_path.exists():
                transcript = txt_path.read_text(encoding="utf-8").strip() or "."
            return str(wav_path), transcript

        if ref_audio_path:
            provided_path = Path(str(ref_audio_path)).expanduser()
            if not provided_path.exists():
                raise FileNotFoundError(f"Reference audio missing: {provided_path}")
            return str(provided_path), (str(ref_text).strip() or ".") if ref_text is not None else "."

        raise ValueError("Voice clone requires voice_id or ref_audio_path")

    def infer(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not MLX_AUDIO_AVAILABLE:
            raise RuntimeError("mlx-audio is not installed in the worker environment")

        mode = str(payload.get("mode", "")).strip()
        model_set_id = str(payload.get("model_set_id", "")).strip()
        text = str(payload.get("text", "")).strip()

        if mode not in MODE_TO_FOLDER:
            raise ValueError(f"Unsupported mode: {mode}")
        if not model_set_id:
            raise ValueError("model_set_id is required")
        if not text:
            raise ValueError("text is required")

        with self._lock:
            self.registry.reload()
            model = self._get_model(model_set_id)
            started = time.time()

            temp_dir = OUTPUTS_DIR / ".tmp" / uuid.uuid4().hex
            temp_dir.mkdir(parents=True, exist_ok=True)

            params: dict[str, Any] = {
                "model": model,
                "text": text,
                "output_path": str(temp_dir),
            }

            if mode == "custom":
                params["voice"] = payload.get("voice") or "Vivian"
                params["instruct"] = payload.get("instruct") or "Normal tone"
                params["speed"] = float(payload.get("speed") or 1.0)
            elif mode == "design":
                instruct = str(payload.get("instruct") or "").strip()
                if not instruct:
                    raise ValueError("design mode requires instruct")
                params["instruct"] = instruct
            elif mode == "clone":
                ref_audio, ref_text = self._resolve_clone_reference(payload)
                params["ref_audio"] = ref_audio
                params["ref_text"] = ref_text

            try:
                assert generate_audio is not None
                generate_audio(**params)

                generated_files = list(temp_dir.glob("*.wav"))
                if not generated_files:
                    generated_files = list(temp_dir.rglob("*.wav"))
                if not generated_files:
                    raise RuntimeError("No WAV output generated")

                output_folder = OUTPUTS_DIR / MODE_TO_FOLDER[mode]
                output_folder.mkdir(parents=True, exist_ok=True)

                name = sanitize_name(text)[:24]
                filename = f"{int(time.time())}_{name}.wav"
                final_path = output_folder / filename
                shutil.move(str(generated_files[0]), final_path)

                return {
                    "status": "ok",
                    "output_rel_path": str(final_path.relative_to(OUTPUTS_DIR)),
                    "output_path": str(final_path),
                    "generation_ms": int((time.time() - started) * 1000),
                }
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
