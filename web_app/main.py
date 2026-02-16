from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from .config import (
    APP_VERSION,
    CONFIG_DIR,
    DATA_DIR,
    MODEL_REGISTRY_VERSION,
    MODELS_DIR,
    OUTPUTS_DIR,
    VOICES_DIR,
    WORKER_VERSION,
)
from .download_manager import DownloadManager
from .model_registry import ModelRegistry
from .output_manager import OutputManager
from .settings_manager import SettingsManager
from .storage import ensure_directories
from .tts_manager import TTSManager
from .utils import format_bytes
from .voice_manager import VoiceManager


class DownloadRequest(BaseModel):
    model_set_id: str
    revision: str | None = None
    token: str | None = None


class ModelRemoveRequest(BaseModel):
    model_set_id: str


class TTSRequest(BaseModel):
    mode: str
    model_set_id: str
    text: str
    voice: str | None = None
    instruct: str | None = None
    speed: float | None = None
    voice_id: str | None = None
    ref_audio_path: str | None = None
    ref_text: str | None = None


class VoiceDeleteRequest(BaseModel):
    name: str


class VoiceRenameRequest(BaseModel):
    old_name: str
    new_name: str


class OutputDeleteRequest(BaseModel):
    output_id: str


class OutputZipRequest(BaseModel):
    output_ids: list[str] = Field(default_factory=list)


class SettingsUpdateRequest(BaseModel):
    default_model_tier: str | None = None
    save_outputs: bool | None = None
    output_directory: str | None = None
    persist_hf_token: bool | None = None
    hf_token: str | None = None
    log_raw_text: bool | None = None


ensure_directories([DATA_DIR, CONFIG_DIR, MODELS_DIR, VOICES_DIR, OUTPUTS_DIR])

model_registry = ModelRegistry()
settings_manager = SettingsManager()
voice_manager = VoiceManager()
output_manager = OutputManager()
download_manager = DownloadManager(model_registry=model_registry)
tts_manager = TTSManager(
    model_registry=model_registry,
    voice_manager=voice_manager,
    output_manager=output_manager,
    settings_manager=settings_manager,
    outputs_dir=OUTPUTS_DIR,
)

app = FastAPI(title="Qwen3 TTS Local Web App", version=APP_VERSION)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")
app.mount("/voice-files", StaticFiles(directory=str(VOICES_DIR)), name="voice-files")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    runtime = tts_manager.runtime_health()
    return {"status": "ok", **runtime}


@app.get("/api/version")
def version() -> dict[str, str]:
    return {
        "ui_version": APP_VERSION,
        "model_registry_version": model_registry.version or MODEL_REGISTRY_VERSION,
        "worker_version": WORKER_VERSION,
    }


@app.get("/api/models/available")
def list_available_models() -> dict[str, Any]:
    installed_ids = {item["id"] for item in model_registry.installed()}
    available = []
    for model_set in model_registry.available():
        available.append({
            **model_set,
            "installed": model_set["id"] in installed_ids,
        })
    return {"models": available}


@app.get("/api/models/installed")
def list_installed_models() -> dict[str, Any]:
    installed = []
    for item in model_registry.installed():
        installed.append({
            **item,
            "size_human": format_bytes(int(item.get("size_bytes", 0))),
        })
    return {"models": installed}


@app.post("/api/models/download")
def start_model_download(request: DownloadRequest) -> dict[str, str]:
    model_set = model_registry.get(request.model_set_id)
    if not model_set:
        raise HTTPException(status_code=404, detail="Unknown model set")

    settings = settings_manager.get()
    request_token = request.token.strip() if isinstance(request.token, str) else request.token
    env_token = (os.getenv("HF_TOKEN") or "").strip()
    settings_token = str(settings.get("hf_token") or "").strip()
    token = request_token or env_token or settings_token or None
    job_id = download_manager.start_download(
        model_set_id=request.model_set_id,
        revision=request.revision,
        token=token,
    )
    return {"job_id": job_id}


@app.get("/api/models/download/{job_id}")
def get_download_status(job_id: str) -> dict[str, Any]:
    job = download_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    return job


@app.post("/api/models/remove")
def remove_model(request: ModelRemoveRequest) -> dict[str, Any]:
    deleted = model_registry.remove(request.model_set_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Model is not installed")
    return {"ok": True}


@app.get("/api/voices")
def list_voices() -> dict[str, Any]:
    voices = []
    for voice in voice_manager.list():
        wav_path = Path(voice.get("path_wav", ""))
        audio_url = None
        if wav_path.exists() and wav_path.is_file():
            audio_url = "/voice-files/" + wav_path.name

        voices.append({
            **voice,
            "audio_url": audio_url,
        })
    return {"voices": voices}


@app.post("/api/voices/enroll")
async def enroll_voice(
    name: str = Form(...),
    transcript: str = Form(""),
    audio: UploadFile = File(...),
) -> dict[str, Any]:
    body = await audio.read()
    if not body:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    record, error = voice_manager.enroll(
        name=name,
        transcript=transcript,
        audio_bytes=body,
        original_filename=audio.filename or "upload",
    )

    if error:
        raise HTTPException(status_code=400, detail=error)

    return {"ok": True, "voice": record}


@app.post("/api/voices/delete")
def delete_voice(request: VoiceDeleteRequest) -> dict[str, Any]:
    ok, error = voice_manager.delete(request.name)
    if not ok:
        raise HTTPException(status_code=404, detail=error or "Voice not found")
    return {"ok": True}


@app.post("/api/voices/rename")
def rename_voice(request: VoiceRenameRequest) -> dict[str, Any]:
    ok, error = voice_manager.rename(request.old_name, request.new_name)
    if not ok:
        raise HTTPException(status_code=400, detail=error or "Rename failed")
    return {"ok": True}


@app.post("/api/tts")
def create_tts_job(request: TTSRequest) -> dict[str, str]:
    job_id = tts_manager.submit(request.model_dump())
    return {"job_id": job_id}


@app.get("/api/tts/{job_id}")
def get_tts_job(job_id: str) -> dict[str, Any]:
    job = tts_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="TTS job not found")
    return job


@app.post("/api/tts/{job_id}/cancel")
def cancel_tts_job(job_id: str) -> dict[str, Any]:
    ok, error = tts_manager.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail=error or "Cancel failed")
    return {"ok": True}


@app.get("/api/outputs")
def list_outputs() -> dict[str, Any]:
    outputs = []
    for item in output_manager.list():
        output_path = Path(item.get("output_path", ""))
        if output_path.exists() and output_path.is_file():
            item = {
                **item,
                "output_url": "/outputs/" + str(output_path.relative_to(OUTPUTS_DIR)),
            }
        outputs.append(item)
    return {"outputs": outputs}


@app.post("/api/outputs/delete")
def delete_output(request: OutputDeleteRequest) -> dict[str, Any]:
    ok, error = output_manager.delete(request.output_id)
    if not ok:
        raise HTTPException(status_code=404, detail=error or "Output not found")
    return {"ok": True}


@app.post("/api/outputs/zip")
def zip_outputs(request: OutputZipRequest) -> FileResponse:
    if not request.output_ids:
        raise HTTPException(status_code=400, detail="No outputs selected")

    zip_path = output_manager.zip_outputs(request.output_ids)
    background_task = BackgroundTask(zip_path.unlink, missing_ok=True)

    return FileResponse(
        path=zip_path,
        filename=zip_path.name,
        media_type="application/zip",
        background=background_task,
    )


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    settings = settings_manager.get()
    return {
        **settings,
        "has_hf_token": bool(os.getenv("HF_TOKEN") or settings.get("hf_token")),
        "hf_token": settings.get("hf_token") if settings.get("persist_hf_token") else "",
    }


@app.post("/api/settings")
def update_settings(request: SettingsUpdateRequest) -> dict[str, Any]:
    changes = {key: value for key, value in request.model_dump().items() if value is not None}
    updated = settings_manager.update(changes)
    return {
        "ok": True,
        "settings": {
            **updated,
            "has_hf_token": bool(os.getenv("HF_TOKEN") or updated.get("hf_token")),
            "hf_token": updated.get("hf_token") if updated.get("persist_hf_token") else "",
        },
    }
