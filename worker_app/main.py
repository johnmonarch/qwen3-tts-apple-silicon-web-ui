from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import CONFIG_DIR, DATA_DIR, MODELS_DIR, OUTPUTS_DIR, VOICES_DIR
from .engine import InferenceEngine, MLX_AUDIO_AVAILABLE


class InferRequest(BaseModel):
    mode: str
    model_set_id: str
    text: str
    voice: str | None = None
    instruct: str | None = None
    speed: float | None = None
    voice_id: str | None = None
    ref_audio_path: str | None = None
    ref_text: str | None = None


for path in [DATA_DIR, CONFIG_DIR, MODELS_DIR, VOICES_DIR, OUTPUTS_DIR]:
    path.mkdir(parents=True, exist_ok=True)

engine = InferenceEngine()
app = FastAPI(title="Qwen3 TTS Host Worker", version="0.1.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return engine.health()


@app.post("/infer")
def infer(request: InferRequest) -> dict[str, Any]:
    if not MLX_AUDIO_AVAILABLE:
        raise HTTPException(status_code=503, detail="mlx-audio is not installed in worker environment")

    try:
        return engine.infer(request.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
