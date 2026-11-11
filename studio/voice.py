"""Local Piper text-to-speech from explicitly supplied ONNX voice files.

This adapter never downloads a voice or calls a cloud service. It synthesizes a
chosen Piper voice; it does not clone voices or convert an existing speaker.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import wave

from .media import inspect_asset
from .providers import ModelUnavailable


MAX_TEXT_CHARACTERS = 4000


def _piper_available() -> bool:
    """Check installation without importing the optional inference runtime."""
    try:
        return importlib.util.find_spec("piper") is not None
    except (ImportError, ValueError):
        return False


def _voice_file(value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ModelUnavailable("No local voice configured. Select a Piper .onnx voice file and its matching .onnx.json config.")
    if value.startswith(("\\\\", "//")) or "://" in value:
        raise ModelUnavailable("Voice models must be local files on this computer, not URLs or network shares.")
    path = Path(value).expanduser()
    if not path.is_absolute() or path.suffix.lower() != ".onnx" or not path.is_file():
        raise ModelUnavailable("Voice model must be an existing absolute path to a local .onnx file.")
    config = Path(str(path) + ".json")
    try:
        if not 0 < config.stat().st_size <= 1024 * 1024:
            raise ValueError("Voice config exceeds its size limit.")
        metadata = json.loads(config.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("Voice config must be an object.")
        audio = metadata.get("audio")
        sample_rate = audio.get("sample_rate") if isinstance(audio, dict) else None
        if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or not 8000 <= sample_rate <= 192000:
            raise ValueError("Voice config needs an audio.sample_rate between 8000 and 192000 Hz.")
    except (OSError, ValueError, TypeError) as exc:
        raise ModelUnavailable("Voice model needs a valid matching .onnx.json config containing audio.sample_rate.") from exc
    return path.resolve()


class LocalVoice:
    """Small CPU voice model, loaded lazily and cached for subsequent requests."""

    def __init__(self, settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._voice = None
        self._loaded_key = None

    def status(self) -> dict:
        result = {"available": False, "label": "Piper local voice", "detail": ""}
        if not bool(getattr(self.settings, "enable_local_ai", True)):
            result["detail"] = "Local AI is disabled. Audio cleanup remains available."
            return result
        try:
            path = _voice_file(getattr(self.settings, "voice_model_path", ""))
            result["label"] = "Piper · " + path.stem
            if not _piper_available():
                raise ModelUnavailable("Voice files found; install the optional piper-tts dependency before going offline.")
            result.update(available=True, detail="Local Piper voice and config found. Weights are verified on first synthesis; no downloads. Voice cloning is not included.")
        except ModelUnavailable as exc:
            result["detail"] = str(exc)
        return result

    def synthesize(self, text: str, destination: Path) -> dict:
        """Synthesize an actual PCM WAV using Piper's local Python API."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Enter nonempty text for the local voice to speak.")
        if len(text) > MAX_TEXT_CHARACTERS:
            raise ValueError("Voice text must contain at most 4000 characters.")
        destination = Path(destination)
        if destination.suffix.lower() != ".wav":
            raise ValueError("Voice output must be a WAV file.")
        status = self.status()
        if not status["available"]:
            raise ModelUnavailable(status["detail"])
        path = _voice_file(self.settings.voice_model_path)
        config = Path(str(path) + ".json")
        temporary = None
        # This is deliberately an additional lock: Piper uses a native inference
        # session and may also be called outside the server's single-job queue.
        with self._lock:
            try:
                from piper.voice import PiperVoice

                key = (str(path), path.stat().st_mtime_ns, config.stat().st_mtime_ns)
                if self._voice is None or self._loaded_key != key:
                    self._voice = PiperVoice.load(str(path))
                    self._loaded_key = key
                destination.parent.mkdir(parents=True, exist_ok=True)
                handle, name = tempfile.mkstemp(prefix=".loom-voice-", suffix=".wav", dir=destination.parent)
                os.close(handle)
                temporary = Path(name)
                with wave.open(str(temporary), "wb") as wav_file:
                    self._voice.synthesize_wav(text.strip(), wav_file)
                metadata = inspect_asset(temporary)
                if metadata.get("kind") != "audio":
                    raise ValueError("Piper did not produce readable audio.")
                temporary.replace(destination)
                temporary = None
                return {**metadata, "operation": "text_to_speech", "model": path.stem}
            except Exception as exc:
                # Preserve a useful setup failure without retaining corrupt
                # files or silently replacing a failed model with demo audio.
                self._voice = None
                self._loaded_key = None
                raise ModelUnavailable("Local voice synthesis failed. Check the Piper voice/config pair, piper-tts runtime, and available memory.") from exc
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
