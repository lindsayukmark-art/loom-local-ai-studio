"""Bounded image/video operations. These tools work without AI model weights."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError


MAX_IMAGE_PIXELS = 20_000_000
MAX_MEDIA_BYTES = 128 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def _local_file(path: Path) -> Path:
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("The source must be an existing local file.")
    if path.stat().st_size > MAX_MEDIA_BYTES:
        raise ValueError("Media files must be at most 128 MB.")
    return path


def _number(options: dict, name: str, default: float, low: float, high: float) -> float:
    raw = options.get(name, default)
    if isinstance(raw, bool):
        raise ValueError(f"{name} must be a number between {low} and {high}.")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number between {low} and {high}.") from None
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")
    return value


def _dimension(options: dict, name: str, default: int, limit: int = 4096) -> int:
    value = _number(options, name, default, 1, limit)
    if value != int(value):
        raise ValueError(f"{name} must be a whole number.")
    return int(value)


def _bool(options: dict, name: str, default: bool = False) -> bool:
    value = options.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false.")
    return value


def _options(options: dict, allowed: set[str]) -> None:
    if not isinstance(options, dict):
        raise ValueError("Options must be an object.")
    unknown = set(options) - allowed
    if unknown:
        raise ValueError("Unknown media option(s): " + ", ".join(sorted(unknown)))


def _image(path: Path) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path, formats=("PNG", "JPEG", "WEBP", "GIF", "BMP", "TIFF")) as original:
                if original.width * original.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Images must contain no more than 20 million pixels.")
                original.load()
                return ImageOps.exif_transpose(original).copy()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Image dimensions exceed the safe processing limit.") from exc


def _media_format(path: Path) -> str:
    with path.open("rb") as handle:
        header = handle.read(32)
    if len(header) >= 12 and header[4:8] in {b"ftyp", b"moov", b"mdat", b"wide"}:
        return "mov"
    if header.startswith(b"\x1aE\xdf\xa3"):
        return "matroska"
    if header.startswith(b"RIFF") and header[8:12] == b"AVI ":
        return "avi"
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"OggS"):
        return "ogg"
    if header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0):
        return "mp3"
    raise ValueError("Upload a supported image, video, WAV, MP3, FLAC, M4A, or OGG file.")


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except FileNotFoundError as exc:
        raise ValueError("FFmpeg and ffprobe must be installed to process media.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Media processing exceeded its time limit.") from exc
    if result.returncode:
        # Keep full codec diagnostics out of API errors, including local paths.
        raise ValueError("The local media tool could not read or process this file.")
    return result


def inspect_asset(path: Path) -> dict[str, Any]:
    """Validate local image, video, or audio bytes and return bounded metadata."""
    path = _local_file(path)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path, formats=("PNG", "JPEG", "WEBP", "GIF", "BMP", "TIFF")) as original:
                if original.width * original.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Images must contain no more than 20 million pixels.")
                format_name = original.format
                width, height = original.size
                original.verify()
            # verify() checks structure, load() checks actual compressed pixels.
            decoded = _image(path)
            width, height = decoded.size
            return {"kind": "image", "mime": Image.MIME.get(format_name, "image/png"),
                    "width": width, "height": height}
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Image dimensions exceed the safe processing limit.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError):
        pass

    format_name = _media_format(path)
    result = _run([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
        "-f", format_name, "-show_entries",
        "stream=codec_type,width,height,duration,sample_rate,channels:stream_disposition=attached_pic:format=duration",
        "-of", "json", str(path),
    ], timeout=20)
    try:
        info = json.loads(result.stdout)
        streams = info["streams"]
        stream = next((entry for entry in streams if entry.get("codec_type") == "video"
                       and not entry.get("disposition", {}).get("attached_pic")), None)
        kind = "video" if stream else "audio"
        stream = stream or next(entry for entry in streams if entry.get("codec_type") == "audio")
        duration = float(info.get("format", {}).get("duration") or stream.get("duration") or 0)
    except (ValueError, KeyError, IndexError, TypeError, StopIteration, json.JSONDecodeError):
        raise ValueError("The uploaded file does not contain a readable audio or video stream.") from None
    if not math.isfinite(duration) or duration <= 0 or duration > 3600:
        raise ValueError("Audio and video must have a known duration between 0 and 3600 seconds.")
    if kind == "audio":
        try:
            sample_rate, channels = int(stream["sample_rate"]), int(stream["channels"])
        except (ValueError, KeyError, TypeError):
            raise ValueError("The uploaded file does not contain readable audio.") from None
        if not 1 <= channels <= 8 or not 8000 <= sample_rate <= 192000:
            raise ValueError("Audio must have 1–8 channels and an 8–192 kHz sample rate.")
        mime = {"mov": "audio/mp4", "matroska": "audio/webm", "wav": "audio/wav",
                "mp3": "audio/mpeg", "flac": "audio/flac", "ogg": "audio/ogg"}.get(format_name, "audio/wav")
        return {"kind": "audio", "mime": mime, "duration": duration,
                "sample_rate": sample_rate, "channels": channels}
    try:
        width, height = int(stream["width"]), int(stream["height"])
    except (ValueError, KeyError, TypeError):
        raise ValueError("The uploaded video does not contain readable dimensions.") from None
    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
        raise ValueError("Video dimensions exceed the safe processing limit.")
    mime = {"mov": "video/mp4", "matroska": "video/webm", "avi": "video/x-msvideo", "ogg": "video/ogg"}.get(format_name, "video/mp4")
    return {"kind": "video", "mime": mime, "width": width, "height": height, "duration": duration}


def edit_image(source: Path, destination: Path, options: dict) -> dict[str, Any]:
    """Apply explicit local edits; never interpret prompt text as a command."""
    options = dict(options)
    operation = options.pop("operation", None)
    angle = options.pop("angle", None)
    factor = options.pop("factor", None)
    if operation not in {None, "resize", "crop", "grayscale", "rotate", "brightness", "contrast", "sharpen"}:
        raise ValueError("Choose resize, crop, grayscale, rotate, brightness, contrast, or sharpen.")
    if angle is not None and operation != "rotate":
        raise ValueError("angle is available only for the rotate operation.")
    if factor is not None and operation not in {"brightness", "contrast", "sharpen"}:
        raise ValueError("factor is available only for brightness, contrast, or sharpen.")
    if operation == "grayscale":
        options["grayscale"] = True
    elif operation == "rotate":
        options["rotate"] = angle if angle is not None else options.get("rotate", 90)
    elif operation in {"brightness", "contrast", "sharpen"}:
        options[operation] = factor if factor is not None else options.get(operation, 1.2)
    if operation == "resize" and not ({"width", "height"} & options.keys()):
        raise ValueError("Resize requires a width or height.")
    if operation == "crop" and "crop" not in options:
        raise ValueError("Crop requires crop coordinates: left, top, right, and bottom.")
    _options(options, {"width", "height", "rotate", "brightness", "contrast", "saturation",
                       "grayscale", "blur", "flip", "crop", "sharpen"})
    source = _local_file(source)
    metadata = inspect_asset(source)
    if metadata["kind"] != "image":
        raise ValueError("Image editing requires an image upload.")
    image = _image(source).convert("RGBA")
    if "crop" in options:
        crop = options["crop"]
        if not isinstance(crop, dict) or set(crop) != {"left", "top", "right", "bottom"}:
            raise ValueError("crop must contain left, top, right, and bottom pixel coordinates.")
        coordinate_values = [_number(crop, k, 0, 0, max(image.size))
                             for k in ("left", "top", "right", "bottom")]
        if any(value != int(value) for value in coordinate_values):
            raise ValueError("Crop coordinates must be whole numbers.")
        coords = tuple(int(value) for value in coordinate_values)
        left, top, right, bottom = coords
        if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
            raise ValueError("Crop coordinates must form a rectangle inside the image.")
        image = image.crop(coords)
    if "width" in options or "height" in options:
        supplied_width = _dimension(options, "width", min(image.width, 4096)) if "width" in options else image.width
        supplied_height = _dimension(options, "height", min(image.height, 4096)) if "height" in options else image.height
        default_width = max(1, round(image.width * supplied_height / image.height))
        default_height = max(1, round(image.height * supplied_width / image.width))
        width = _dimension(options, "width", default_width)
        height = _dimension(options, "height", default_height)
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    rotate = _number(options, "rotate", 0, -360, 360)
    if rotate:
        image = image.rotate(-rotate, expand=True, resample=Image.Resampling.BICUBIC)
    flip = options.get("flip", "none")
    if flip not in {"none", "horizontal", "vertical"}:
        raise ValueError("flip must be none, horizontal, or vertical.")
    if flip == "horizontal":
        image = ImageOps.mirror(image)
    elif flip == "vertical":
        image = ImageOps.flip(image)
    for option, enhancer in (("brightness", ImageEnhance.Brightness),
                             ("contrast", ImageEnhance.Contrast),
                             ("saturation", ImageEnhance.Color)):
        image = enhancer(image).enhance(_number(options, option, 1, 0, 3))
    if _bool(options, "grayscale"):
        alpha = image.getchannel("A")
        image = ImageOps.grayscale(image).convert("RGBA")
        image.putalpha(alpha)
    blur = _number(options, "blur", 0, 0, 20)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    if "sharpen" in options:
        image = ImageEnhance.Sharpness(image).enhance(_number(options, "sharpen", 1, 0, 5))
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffix = destination.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        background.save(destination, "JPEG", quality=95)
    elif suffix == ".webp":
        image.save(destination, "WEBP", quality=95)
    else:
        image.save(destination, "PNG")
    return {**inspect_asset(destination), "operation": "image_edit"}


def render_video(source: Path, destination: Path, options: dict) -> dict[str, Any]:
    """Animate a still locally or trim/resize a video with FFmpeg."""
    _options(options, {"duration", "start", "end", "width", "height", "grayscale",
                       "speed", "muted", "animate", "denoise_audio"})
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ValueError("FFmpeg and ffprobe must be installed to process video.")
    source = _local_file(source)
    metadata = inspect_asset(source)
    if metadata["kind"] == "audio":
        raise ValueError("Video editing requires an image or video upload.")
    width = _dimension(options, "width", min(metadata["width"], 1280), 1920)
    height = _dimension(options, "height", min(metadata["height"], 720), 1920)
    # H.264 requires dimensions divisible by two.
    width, height = max(2, width - width % 2), max(2, height - height % 2)
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    filters = [f"scale={width}:{height}:force_original_aspect_ratio=increase", f"crop={width}:{height}"]
    if _bool(options, "grayscale"):
        filters.append("hue=s=0")
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-threads", "1",
            "-filter_threads", "1", "-protocol_whitelist", "file,pipe"]
    if metadata["kind"] == "image":
        duration = _number(options, "duration", 5, 0.1, 30)
        if _number(options, "start", 0, 0, 3600) != 0 or "end" in options or "speed" in options:
            raise ValueError("start, end, and speed are available only for uploaded video.")
        # Decode with Pillow, then give FFmpeg a known, single-frame PNG.
        with tempfile.TemporaryDirectory(prefix="offline-frame-") as folder:
            frame = Path(folder) / "frame.png"
            _image(source).convert("RGB").save(frame, "PNG")
            if _bool(options, "animate", True):
                filters.append(f"zoompan=z='min(1.0+on*0.0008,1.12)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps=24")
            args += ["-loop", "1", "-framerate", "24", "-i", str(frame), "-t", str(duration),
                     "-vf", ",".join(filters), "-an", "-c:v", "libx264", "-threads", "1",
                     "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination)]
            _run(args, timeout=120)
        operation = "image_animation"
    else:
        start = _number(options, "start", 0, 0, metadata["duration"])
        if start >= metadata["duration"]:
            raise ValueError("The trim start must be before the end of the source video.")
        if "end" in options:
            end = _number(options, "end", metadata["duration"], 0, metadata["duration"])
            if end <= start:
                raise ValueError("The trim end must be after the trim start.")
            if "duration" in options:
                raise ValueError("Choose duration or end, not both.")
            duration = end - start
            if duration > 120:
                raise ValueError("Video edits can contain at most 120 seconds.")
        else:
            duration = min(_number(options, "duration", min(metadata["duration"] - start, 30), 0.1, 120),
                           metadata["duration"] - start)
        speed = _number(options, "speed", 1, 0.25, 4)
        filters.append(f"setpts=PTS/{speed}")
        args += ["-ss", str(start), "-f", _media_format(source), "-i", str(source), "-t", str(duration / speed),
                 "-map", "0:v:0", "-map", "0:a:0?", "-vf", ",".join(filters)]
        audio_filters = []
        if _bool(options, "muted"):
            args += ["-an"]
        elif speed != 1:
            remaining = speed
            while remaining < 0.5:
                audio_filters.append("atempo=0.5")
                remaining /= 0.5
            while remaining > 2:
                audio_filters.append("atempo=2")
                remaining /= 2
            audio_filters.append(f"atempo={remaining}")
        if _bool(options, "denoise_audio") and not options.get("muted", False):
            audio_filters.extend(["highpass=f=80", "lowpass=f=12000", "afftdn=nr=12:tn=1"])
        if audio_filters and not options.get("muted", False):
            args += ["-af", ",".join(audio_filters)]
        args += ["-c:v", "libx264", "-threads", "1", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-movflags", "+faststart", str(destination)]
        _run(args, timeout=180)
        operation = "video_edit"
    return {**inspect_asset(destination), "operation": operation}


def clean_audio(source: Path, destination: Path, options: dict) -> dict[str, Any]:
    """Clean local audio with deterministic filters; this does not clone voices."""
    _options(options, {"noise_reduction", "highpass", "lowpass", "normalize", "start", "duration"})
    source = _local_file(source)
    metadata = inspect_asset(source)
    if metadata["kind"] not in {"audio", "video"}:
        raise ValueError("Sound cleanup requires an audio or video upload.")
    start = _number(options, "start", 0, 0, metadata["duration"])
    if start >= metadata["duration"]:
        raise ValueError("The trim start must be before the end of the audio.")
    duration = min(_number(options, "duration", min(metadata["duration"] - start, 600), 0.1, 600),
                   metadata["duration"] - start)
    highpass = _number(options, "highpass", 80, 20, 500)
    lowpass = _number(options, "lowpass", 12000, 1000, 22000)
    reduction = _number(options, "noise_reduction", 12, 0, 60)
    filters = [f"highpass=f={highpass}", f"lowpass=f={lowpass}"]
    if reduction:
        filters.append(f"afftdn=nr={max(0.01, reduction)}:tn=1")
    if _bool(options, "normalize", True):
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-threads", "1",
        "-protocol_whitelist", "file,pipe", "-ss", str(start), "-f", _media_format(source),
        "-i", str(source), "-t", str(duration), "-map", "0:a:0", "-vn", "-af", ",".join(filters),
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", "-f", "wav", str(destination),
    ], timeout=180)
    return {**inspect_asset(destination), "operation": "audio_cleanup"}


def change_voice(source: Path, destination: Path, options: dict) -> dict[str, Any]:
    """Change pitch and speaking speed locally; this is DSP, not voice cloning.

    ``duration`` selects input seconds before speed changes. Output is bounded to
    600 seconds. Pitch changes preserve duration; speed changes preserve pitch.
    """
    _options(options, {"preset", "pitch_semitones", "speed", "denoise", "normalize", "start", "duration"})
    presets = {"neutral": 0, "deep": -4, "bright": 4}
    preset = options.get("preset", "neutral")
    if not isinstance(preset, str) or preset not in presets:
        raise ValueError("Voice preset must be neutral, deep, or bright.")
    semitones = _number(options, "pitch_semitones", presets[preset], -12, 12)
    speed = _number(options, "speed", 1, 0.5, 2)
    denoise = _bool(options, "denoise")
    normalize = _bool(options, "normalize", True)
    source = _local_file(source)
    metadata = inspect_asset(source)
    if metadata["kind"] not in {"audio", "video"}:
        raise ValueError("Voice changing requires an audio or video upload.")
    start = _number(options, "start", 0, 0, metadata["duration"])
    if start >= metadata["duration"]:
        raise ValueError("The trim start must be before the end of the recording.")
    default_duration = min(metadata["duration"] - start, 600, 600 * speed)
    duration = min(_number(options, "duration", default_duration, 0.1, 600), metadata["duration"] - start)
    if duration / speed > 600:
        raise ValueError("Choose a shorter duration or a faster speed; changed voice output is limited to 600 seconds.")
    filters = ["aresample=48000"]
    if denoise:
        filters.extend(["highpass=f=80", "lowpass=f=12000", "afftdn=nr=12:tn=1"])
    if semitones:
        changed_rate = round(48000 * 2 ** (semitones / 12))
        actual_ratio = changed_rate / 48000
        filters.extend([f"asetrate={changed_rate}", "aresample=48000", f"atempo={1 / actual_ratio:.10f}"])
    if speed != 1:
        filters.append(f"atempo={speed:.10f}")
    if normalize:
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-threads", "1",
        "-protocol_whitelist", "file,pipe", "-ss", str(start), "-t", str(duration),
        "-f", _media_format(source), "-i", str(source), "-map", "0:a:0", "-vn",
        "-af", ",".join(filters), "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
        "-f", "wav", str(destination),
    ], timeout=180)
    return {**inspect_asset(destination), "operation": "voice_change", "preset": preset,
            "pitch_semitones": semitones, "speed": speed}
