"""Offline-only model adapters.

No models are downloaded by this module. Copy complete Diffusers model folders
onto the machine and configure their absolute paths. Start Ollama with
OLLAMA_NO_CLOUD=1 and install a local (not cloud-backed) text model first.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit

# These must be set before any optional Hugging Face library is imported.
for _name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE",
              "HF_HUB_DISABLE_TELEMETRY", "DO_NOT_TRACK"):
    os.environ[_name] = "1"

import httpx


class ModelUnavailable(RuntimeError):
    """A requested local model, dependency, or compatible pipeline is missing."""


IMAGE_PIPELINES = {"StableDiffusionPipeline", "StableDiffusionXLPipeline"}
VIDEO_PIPELINES = {"TextToVideoSDPipeline", "CogVideoXPipeline", "CogVideoXImageToVideoPipeline"}


def _dependency_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _loopback_url(value: str) -> str:
    """Keep the only HTTP integration strictly on this machine."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (ValueError, TypeError) as exc:
        raise ValueError("Ollama URL must be an HTTP loopback address.") from exc
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or port is None):
        raise ValueError("Ollama URL must be http://127.0.0.1:11434 (or localhost / [::1] with a port).")
    return value.rstrip("/")


def _local_model(path_value: str, allowed: set[str]) -> tuple[Path, str]:
    if not path_value:
        raise ModelUnavailable("No local model folder configured. Add an absolute model path in settings.")
    path = Path(path_value).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ModelUnavailable("Model path must be an existing absolute folder on this computer.")
    config = path / "model_index.json"
    try:
        if config.stat().st_size > 65536:
            raise ValueError("Model index is too large.")
        metadata = json.loads(config.read_text(encoding="utf-8"))
        name = metadata.get("_class_name")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise ModelUnavailable("Model folder must contain a valid Diffusers model_index.json.") from exc
    if not isinstance(name, str) or name not in allowed:
        raise ModelUnavailable("Unsupported local pipeline. Supported: " + ", ".join(sorted(allowed)) + ".")
    return path, name


class LocalModels:
    def __init__(self, settings):
        self.settings = settings
        self.base_url = _loopback_url(settings.ollama_url)
        self._image_pipelines: dict[str, object] = {}
        self._video_pipeline = None
        self._inference_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.settings, "enable_local_ai", True))

    async def _text_status(self) -> dict:
        model = self.settings.text_model
        result = {"available": False, "label": model, "detail": ""}
        if not self.enabled:
            result["detail"] = "Local AI is disabled. Local editing tools remain available."
            return result
        if not model or "cloud" in model.casefold():
            result["detail"] = "Choose an installed local model; cloud-backed models are not allowed."
            return result
        try:
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                                         timeout=httpx.Timeout(2.0)) as client:
                response = await client.get(self.base_url + "/api/tags")
                response.raise_for_status()
                payload = response.json()
            models = payload.get("models", [])
            matching = next((item for item in models if isinstance(item, dict) and
                             (item.get("name") in {model, model + ":latest"}
                              or item.get("model") in {model, model + ":latest"})), None)
            if matching is None:
                result["detail"] = "Ollama is running, but this local model is not installed."
            elif matching.get("remote_host") or matching.get("remote_model"):
                result["detail"] = "This model uses a remote host. Select an entirely local Ollama model."
            else:
                result.update(available=True, detail="Installed local model via Ollama. Start Ollama with OLLAMA_NO_CLOUD=1.")
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            result["detail"] = "Ollama is not reachable on this computer. Start the local Ollama server."
        return result

    def _diffusion_status(self, model_type: str) -> dict:
        path_value = getattr(self.settings, model_type + "_model_path", "")
        result = {"available": False, "label": "Local " + model_type + " model", "detail": ""}
        if not self.enabled:
            result["detail"] = "Local AI is disabled."
            return result
        try:
            _, name = _local_model(path_value, IMAGE_PIPELINES if model_type == "image" else VIDEO_PIPELINES)
            result["label"] = name
            if not all(_dependency_available(dep) for dep in ("torch", "diffusers", "transformers", "accelerate", "safetensors")):
                raise ModelUnavailable("Local model folder found; install the optional torch/diffusers dependencies before going offline.")
            result.update(available=True, detail="Local folder and dependencies found. Weights are verified on first generation; no downloads.")
        except ModelUnavailable as exc:
            result["detail"] = str(exc)
        return result

    async def capabilities(self) -> dict:
        return {"reasoning": await self._text_status(),
                "image": self._diffusion_status("image"),
                "video": self._diffusion_status("video")}

    async def reason(self, system: str, prompt: str, *, max_tokens: int = 2048) -> str:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= 8192:
            raise ValueError("max_tokens must be a whole number between 1 and 8192.")
        status = await self._text_status()
        if not status["available"]:
            raise ModelUnavailable(status["detail"])
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("A nonempty prompt is required.")
        try:
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                                         timeout=httpx.Timeout(180.0, connect=3.0)) as client:
                response = await client.post(self.base_url + "/api/chat", json={
                    "model": self.settings.text_model,
                    "stream": False,
                    "think": False,
                    "messages": [{"role": "system", "content": system[:16000]},
                                 {"role": "user", "content": prompt[:24000]}],
                    "options": {"temperature": 0.6, "num_ctx": 8192, "num_predict": max_tokens},
                })
                response.raise_for_status()
                payload = response.json()
            if payload.get("done_reason") == "length":
                raise ModelUnavailable("The local model exceeded its response token limit. Ask for a smaller result and try again; the partial output was discarded.")
            content = payload.get("message", {}).get("content")
            if not isinstance(content, str) or not content.strip():
                raise ModelUnavailable("The local model returned no text. Check the Ollama model and available memory.")
            return content.strip()
        except (httpx.HTTPError, ValueError, AttributeError, TypeError) as exc:
            raise ModelUnavailable("Local reasoning failed. Check Ollama, model availability, and free memory.") from exc

    def _torch_device(self):
        import torch
        configured = getattr(self.settings, "device", "auto")
        if configured == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        elif configured in {"cpu", "cuda", "mps"}:
            device = configured
        else:
            raise ModelUnavailable("Device must be auto, cpu, cuda, or mps.")
        if device == "cuda" and not torch.cuda.is_available():
            raise ModelUnavailable("CUDA was selected, but a compatible PyTorch CUDA runtime is unavailable.")
        if device == "mps" and not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
            raise ModelUnavailable("Apple MPS was selected, but is unavailable in this PyTorch runtime.")
        return torch, device, (torch.float16 if device in {"cuda", "mps"} else torch.float32)

    @staticmethod
    def _place_pipeline(pipe, device: str):
        # Sequential CPU offload saves VRAM for consumer GPUs. It is slower than
        # keeping a whole pipeline on the GPU, but avoids assuming 12+ GB VRAM.
        if device == "cuda":
            pipe.enable_model_cpu_offload()
        else:
            pipe.to(device)
        if hasattr(pipe, "enable_attention_slicing"):
            pipe.enable_attention_slicing()
        if hasattr(pipe, "enable_vae_slicing"):
            pipe.enable_vae_slicing()
        if hasattr(pipe, "enable_vae_tiling"):
            pipe.enable_vae_tiling()
        return pipe

    def _check_diffusion(self, kind: str):
        status = self._diffusion_status(kind)
        if not status["available"]:
            raise ModelUnavailable(status["detail"])

    def generate_image(self, prompt: str, destination: Path, reference: Path | None = None) -> None:
        self._check_diffusion("image")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("A nonempty image prompt is required.")
        from PIL import Image, ImageOps
        try:
            from diffusers import AutoPipelineForImage2Image, AutoPipelineForText2Image
            torch, device, dtype = self._torch_device()
            path, class_name = _local_model(self.settings.image_model_path, IMAGE_PIPELINES)
            key = "edit" if reference is not None else "create"
            with self._inference_lock:
                # Keep only one GPU model resident at a time.
                self._video_pipeline = None
                if key not in self._image_pipelines:
                    self._image_pipelines.clear()
                    if device == "cuda":
                        torch.cuda.empty_cache()
                    loader = AutoPipelineForImage2Image if reference is not None else AutoPipelineForText2Image
                    pipe = loader.from_pretrained(str(path), torch_dtype=dtype,
                                                  local_files_only=True, use_safetensors=True,
                                                  trust_remote_code=False)
                    self._image_pipelines[key] = self._place_pipeline(pipe, device)
                pipe = self._image_pipelines[key]
                side = 768 if "XL" in class_name else 512
                kwargs = {"prompt": prompt[:8000], "num_inference_steps": 25, "guidance_scale": 7.0}
                if reference is not None:
                    with Image.open(reference) as opened:
                        kwargs["image"] = ImageOps.fit(ImageOps.exif_transpose(opened).convert("RGB"), (side, side))
                    kwargs["strength"] = 0.65
                else:
                    kwargs.update(width=side, height=side)
                with torch.inference_mode():
                    output = pipe(**kwargs)
                images = getattr(output, "images", None)
                if not images:
                    raise ModelUnavailable("The local image pipeline returned no image.")
                destination = Path(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                images[0].save(destination, format="PNG")
        except ModelUnavailable:
            raise
        except Exception as exc:
            raise ModelUnavailable("Local image generation failed. Check complete safetensors weights, pipeline compatibility, and free RAM/VRAM.") from exc

    def generate_video(self, prompt: str, destination: Path, reference: Path | None = None) -> None:
        """Generate a short clip using TextToVideoSD or CogVideoX local weights.

        TextToVideoSD produces 16 frames at 8 fps. CogVideoX produces 17 frames
        at 8 fps. These are intentionally short for consumer hardware. For an
        image reference, a CogVideoXImageToVideoPipeline folder is required.
        """
        self._check_diffusion("video")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("A nonempty video prompt is required.")
        try:
            from PIL import Image, ImageOps
            from diffusers import DiffusionPipeline
            torch, device, dtype = self._torch_device()
            path, class_name = _local_model(self.settings.video_model_path, VIDEO_PIPELINES)
            if class_name == "CogVideoXImageToVideoPipeline" and reference is None:
                raise ModelUnavailable("This local video model requires an image reference.")
            if reference is not None and class_name != "CogVideoXImageToVideoPipeline":
                raise ModelUnavailable("Image-to-video requires a local CogVideoXImageToVideoPipeline model folder.")
            with self._inference_lock:
                self._image_pipelines.clear()
                if self._video_pipeline is None:
                    if device == "cuda":
                        torch.cuda.empty_cache()
                    pipe = DiffusionPipeline.from_pretrained(str(path), torch_dtype=dtype,
                                                             local_files_only=True, use_safetensors=True,
                                                             trust_remote_code=False)
                    self._video_pipeline = self._place_pipeline(pipe, device)
                pipe = self._video_pipeline
                kwargs = {"prompt": prompt[:8000], "num_inference_steps": 25,
                          "num_frames": 16 if class_name == "TextToVideoSDPipeline" else 17}
                if class_name == "TextToVideoSDPipeline":
                    kwargs.update(width=256, height=256)
                if reference is not None:
                    with Image.open(reference) as opened:
                        kwargs["image"] = ImageOps.fit(ImageOps.exif_transpose(opened).convert("RGB"), (720, 480))
                with torch.inference_mode():
                    output = pipe(**kwargs)
                frames = getattr(output, "frames", None)
                if frames is None or len(frames) == 0:
                    raise ModelUnavailable("The local video pipeline returned no frames.")
                # Diffusers returns batch x frames, as PIL lists or numpy arrays.
                batch = frames[0]
                if len(batch) == 0:
                    raise ModelUnavailable("The local video pipeline returned an empty frame batch.")
                self._write_video_frames(batch, Path(destination), 8)
        except ModelUnavailable:
            raise
        except Exception as exc:
            raise ModelUnavailable("Local video generation failed. Check complete safetensors weights, supported pipeline, FFmpeg, and free RAM/VRAM.") from exc

    @staticmethod
    def _write_video_frames(frames, destination: Path, fps: int):
        """Encode generated frames locally without third-party download helpers."""
        import shutil
        import subprocess
        import tempfile
        from PIL import Image
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise ModelUnavailable("FFmpeg is required to encode generated video.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="offline-ai-frames-") as temporary:
            folder = Path(temporary)
            for index, frame in enumerate(frames):
                if isinstance(frame, Image.Image):
                    frame_image = frame.convert("RGB")
                else:
                    import numpy as np
                    pixels = np.asarray(frame)
                    if pixels.dtype != np.uint8:
                        pixels = (pixels.clip(0, 1) * 255).astype(np.uint8)
                    frame_image = Image.fromarray(pixels).convert("RGB")
                frame_image.save(folder / f"{index:05d}.png")
            command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                       "-protocol_whitelist", "file,pipe", "-framerate", str(fps),
                       "-i", str(folder / "%05d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                       "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-threads", "1",
                       "-filter_threads", "1", "-movflags", "+faststart", str(destination)]
            try:
                subprocess.run(command, check=True, capture_output=True, timeout=180,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (subprocess.SubprocessError, OSError) as exc:
                destination.unlink(missing_ok=True)
                raise ModelUnavailable("FFmpeg could not encode the generated local video.") from exc
