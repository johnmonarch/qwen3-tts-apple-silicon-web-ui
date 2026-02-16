from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

from .config import SAMPLE_RATE, VOICES_DIR, VOICES_META_PATH
from .storage import read_json, write_json
from .utils import now_iso, sanitize_name


class VoiceManager:
    def __init__(self, voices_dir: Path = VOICES_DIR, metadata_path: Path = VOICES_META_PATH) -> None:
        self.voices_dir = voices_dir
        self.metadata_path = metadata_path
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self._meta: list[dict[str, Any]] = self._load_meta()

    def _load_meta(self) -> list[dict[str, Any]]:
        payload = read_json(self.metadata_path, {"voices": []})
        voices = payload.get("voices", [])
        if not isinstance(voices, list):
            return []
        return voices

    def _save_meta(self) -> None:
        write_json(self.metadata_path, {"voices": self._meta})

    def _index(self, name: str) -> int | None:
        for idx, voice in enumerate(self._meta):
            if voice.get("name") == name:
                return idx
        return None

    def list(self) -> list[dict[str, Any]]:
        return sorted(self._meta, key=lambda item: item.get("created_at", ""), reverse=True)

    def _duration_seconds(self, wav_path: Path) -> float:
        try:
            with wave.open(str(wav_path), "rb") as handle:
                frames = handle.getnframes()
                rate = handle.getframerate() or SAMPLE_RATE
                return round(frames / float(rate), 2)
        except Exception:
            return 0.0

    def _ensure_wav(self, source_path: Path, target_wav: Path) -> tuple[bool, str]:
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(source_path),
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(target_wav),
        ]

        try:
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            return True, ""
        except FileNotFoundError:
            if source_path.suffix.lower() == ".wav":
                shutil.copy(source_path, target_wav)
                return True, ""
            return False, "ffmpeg is required to convert non-WAV files"
        except subprocess.CalledProcessError as exc:
            reason = exc.stderr.decode("utf-8", errors="ignore")[:400]
            return False, f"ffmpeg conversion failed: {reason}"

    def enroll(self, name: str, transcript: str, audio_bytes: bytes, original_filename: str) -> tuple[dict[str, Any] | None, str | None]:
        safe_name = sanitize_name(name)
        original_suffix = Path(original_filename).suffix.lower() or ".wav"
        temp_source = self.voices_dir / f".{safe_name}.upload{original_suffix}"
        wav_path = self.voices_dir / f"{safe_name}.wav"
        txt_path = self.voices_dir / f"{safe_name}.txt"

        temp_source.write_bytes(audio_bytes)
        ok, error = self._ensure_wav(temp_source, wav_path)
        temp_source.unlink(missing_ok=True)

        if not ok:
            return None, error

        txt_path.write_text(transcript.strip(), encoding="utf-8")

        record = {
            "name": safe_name,
            "created_at": now_iso(),
            "source_filename": original_filename,
            "path_wav": str(wav_path),
            "path_txt": str(txt_path),
            "duration_seconds": self._duration_seconds(wav_path),
        }

        existing_idx = self._index(safe_name)
        if existing_idx is None:
            self._meta.append(record)
        else:
            self._meta[existing_idx] = {**self._meta[existing_idx], **record}
        self._save_meta()
        return record, None

    def rename(self, old_name: str, new_name: str) -> tuple[bool, str | None]:
        idx = self._index(old_name)
        if idx is None:
            return False, "Voice not found"

        safe_new = sanitize_name(new_name)
        if self._index(safe_new) is not None:
            return False, "Target name already exists"

        old_wav = self.voices_dir / f"{old_name}.wav"
        old_txt = self.voices_dir / f"{old_name}.txt"
        new_wav = self.voices_dir / f"{safe_new}.wav"
        new_txt = self.voices_dir / f"{safe_new}.txt"

        if old_wav.exists():
            old_wav.rename(new_wav)
        if old_txt.exists():
            old_txt.rename(new_txt)

        self._meta[idx]["name"] = safe_new
        self._meta[idx]["path_wav"] = str(new_wav)
        self._meta[idx]["path_txt"] = str(new_txt)
        self._save_meta()

        return True, None

    def delete(self, name: str) -> tuple[bool, str | None]:
        idx = self._index(name)
        if idx is None:
            return False, "Voice not found"

        wav_path = self.voices_dir / f"{name}.wav"
        txt_path = self.voices_dir / f"{name}.txt"
        wav_path.unlink(missing_ok=True)
        txt_path.unlink(missing_ok=True)

        self._meta.pop(idx)
        self._save_meta()
        return True, None

    def get_reference(self, name: str) -> tuple[Path | None, str | None, str | None]:
        idx = self._index(name)
        if idx is None:
            return None, None, "Voice not found"

        wav_path = self.voices_dir / f"{name}.wav"
        txt_path = self.voices_dir / f"{name}.txt"

        if not wav_path.exists():
            return None, None, "Reference audio file is missing"

        ref_text = "."
        if txt_path.exists():
            ref_text = txt_path.read_text(encoding="utf-8").strip() or "."

        return wav_path, ref_text, None
