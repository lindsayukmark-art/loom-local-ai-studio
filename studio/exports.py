"""Real, bounded file-format exports using only local Pillow and FFmpeg.

These are common photographic and delivery formats, not arbitrary camera RAW
formats. Format conversion never downloads a codec or changes just a filename.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError, features

from . import media


IMAGE_FORMATS = frozenset({"png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "tif", "avif"})
AUDIO_FORMATS = frozenset({"wav", "mp3", "flac", "ogg", "m4a"})
VIDEO_FORMATS = frozenset({"mp4", "webm", "mov"})
MAX_VIDEO_SECONDS = 120
MAX_AUDIO_SECONDS = 600
MAX_VIDEO_SIDE = 1920

_ALIASES = {"jpeg": "jpg", "tif": "tiff"}
_SUFFIXES = {
    "png": {".png"}, "jpg": {".jpg", ".jpeg"}, "webp": {".webp"}, "gif": {".gif"},
    "bmp": {".bmp"}, "tiff": {".tif", ".tiff"}, "avif": {".avif"},
    "wav": {".wav"}, "mp3": {".mp3"}, "flac": {".flac"}, "ogg": {".ogg"},
    "m4a": {".m4a"}, "mp4": {".mp4"}, "webm": {".webm"}, "mov": {".mov"},
}
_IMAGE_ENCODERS = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP", "gif": "GIF",
                   "bmp": "BMP", "tiff": "TIFF", "avif": "AVIF"}
_MIMES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "gif": "image/gif",
          "bmp": "image/bmp", "tiff": "image/tiff", "avif": "image/avif",
          "wav": "audio/wav", "mp3": "audio/mpeg", "flac": "audio/flac", "ogg": "audio/ogg",
          "m4a": "audio/mp4", "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime"}


def available_image_formats() -> list[str]:
    """Canonical names; AVIF appears only when this Pillow build supports it."""
    formats = ["png", "jpg", "webp", "gif", "bmp", "tiff"]
    if "avif" in features.get_supported():
        formats.append("avif")
    return formats


def _read_image(path: Path) -> tuple[Image.Image, bool]:
    """Decode known image formats with the same resource bounds as media tools."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(path, formats=tuple(_IMAGE_ENCODERS.values())) as opened:
                if opened.width * opened.height > media.MAX_IMAGE_PIXELS:
                    raise ValueError("Images must contain no more than 20 million pixels.")
                animated = getattr(opened, "n_frames", 1) > 1
                opened.load()
                return ImageOps.exif_transpose(opened).convert("RGBA"), animated
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError("Image dimensions exceed the safe processing limit.") from exc
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise ValueError("A readable PNG, JPEG, WebP, GIF, BMP, TIFF, or supported AVIF image is required.") from exc


def _source_metadata(source: Path) -> dict[str, Any]:
    # inspect_asset validates media bytes, size, stream type, duration, and
    # dimensions without trusting the file extension. The local image fallback
    # also permits reconverting BMP/TIFF/AVIF exported by this module.
    try:
        return media.inspect_asset(source)
    except ValueError as original_error:
        try:
            image, _ = _read_image(source)
        except ValueError:
            raise original_error from None
        try:
            return {"kind": "image", "width": image.width, "height": image.height}
        finally:
            image.close()


def _export_image(source: Path, temporary: Path, format: str) -> dict[str, Any]:
    if format == "avif" and "avif" not in features.get_supported():
        raise ValueError("AVIF export is unavailable in this Pillow build. Choose PNG, JPEG, WebP, GIF, BMP, or TIFF.")
    image, animated = _read_image(source)
    note = "Only the first frame is exported from an animated source." if animated else ""
    try:
        transparency = image.getchannel("A").getextrema()[0] < 255
        options: dict[str, Any] = {}
        if format in {"jpg", "bmp"}:
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            image.close()
            image = background
            if transparency:
                note = "Transparency was flattened onto white. " + note
            if format == "jpg":
                options.update(quality=95, subsampling=0)
        elif format == "webp":
            options.update(quality=92, method=4)
        elif format == "gif":
            # GIF has one transparent palette entry, not fractional alpha.
            palette = image.convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT)
            if transparency:
                mask = image.getchannel("A").point(lambda alpha: 255 if alpha < 128 else 0)
                palette.paste(255, mask)
                options.update(transparency=255, disposal=2)
                note = "GIF supports binary transparency only; partial alpha is thresholded. " + note
            image.close()
            image = palette
        elif format == "tiff":
            options["compression"] = "tiff_lzw" if "libtiff" in features.get_supported() else "raw"
        elif format == "avif":
            options.update(quality=90, speed=6)
        try:
            image.save(temporary, format=_IMAGE_ENCODERS[format], **options)
        except (OSError, ValueError, KeyError) as exc:
            raise ValueError(f"The local image encoder could not export {format.upper()}. Check Pillow format support.") from exc
    finally:
        image.close()
    if temporary.stat().st_size > media.MAX_MEDIA_BYTES:
        raise ValueError("The exported image exceeds the 128 MB file limit.")
    decoded, _ = _read_image(temporary)
    try:
        transparent = decoded.getchannel("A").getextrema()[0] < 255
        return {"kind": "image", "mime": _MIMES[format], "width": decoded.width,
                "height": decoded.height, "transparent": transparent, "note": note.strip()}
    finally:
        decoded.close()


def _ffmpeg_input(source: Path) -> list[str]:
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-threads", "1", "-filter_threads", "1", "-protocol_whitelist", "file,pipe",
            "-f", media._media_format(source), "-i", str(source)]


def _export_audio(source: Path, temporary: Path, format: str, metadata: dict) -> dict[str, Any]:
    duration = min(float(metadata["duration"]), MAX_AUDIO_SECONDS)
    args = _ffmpeg_input(source) + ["-map", "0:a:0", "-vn", "-sn", "-dn", "-map_metadata", "-1",
                                     "-t", str(duration), "-ar", "48000", "-ac", "2"]
    encoders = {
        "wav": ["-c:a", "pcm_s16le", "-f", "wav"],
        "mp3": ["-c:a", "libmp3lame", "-b:a", "192k", "-id3v2_version", "3", "-f", "mp3"],
        "flac": ["-c:a", "flac", "-compression_level", "5", "-f", "flac"],
        "ogg": ["-c:a", "libvorbis", "-q:a", "5", "-f", "ogg"],
        "m4a": ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-f", "ipod"],
    }
    media._run(args + encoders[format] + ["-threads", "1", str(temporary)], timeout=180)
    result = media.inspect_asset(temporary)
    if result["kind"] != "audio":
        raise ValueError("The export did not produce a readable audio file.")
    result.update(mime=_MIMES[format], note=("Exported the first 600 seconds; trim longer recordings before exporting."
                                          if metadata["duration"] > MAX_AUDIO_SECONDS else ""))
    return result


def _export_video(source: Path, temporary: Path, format: str, metadata: dict) -> dict[str, Any]:
    if metadata["width"] < 2 or metadata["height"] < 2:
        raise ValueError("Video exports require dimensions of at least two pixels.")
    duration = min(float(metadata["duration"]), MAX_VIDEO_SECONDS)
    # Use decoded dimensions so rotation metadata does not stretch portrait clips.
    scale = (f"scale=w='min({MAX_VIDEO_SIDE},iw)':h='min({MAX_VIDEO_SIDE},ih)':"
             "force_original_aspect_ratio=decrease:force_divisible_by=2,format=yuv420p")
    args = _ffmpeg_input(source) + ["-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn",
                                     "-map_metadata", "-1", "-t", str(duration), "-vf", scale]
    if format == "webm":
        args += ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-deadline", "good", "-cpu-used", "4",
                 "-c:a", "libopus", "-b:a", "128k", "-f", "webm"]
    else:
        args += ["-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-f", format]
    media._run(args + ["-threads", "1", str(temporary)], timeout=240)
    result = media.inspect_asset(temporary)
    if result["kind"] != "video" or max(result["width"], result["height"]) > MAX_VIDEO_SIDE:
        raise ValueError("The export did not produce a video within the supported dimensions.")
    note = "This video export is opaque. Use the animation workflow for alpha-channel WebM."
    if metadata["duration"] > MAX_VIDEO_SECONDS:
        note = "Exported the first 120 seconds. " + note
    result.update(mime=_MIMES[format], transparent=False, note=note)
    return result


def export_asset(source: Path, destination: Path, format: str) -> dict[str, Any]:
    """Encode a common local format and validate the resulting bytes.

    Images export to photographic formats. Audio or a video's soundtrack can
    export to audio formats. Videos export to MP4, WebM, or MOV. Video exports
    contain at most 120 seconds; audio exports at most 600 seconds. The returned
    note reports truncation and transparency limitations. Source and destination
    paths must differ, and an existing destination is never overwritten.
    """
    if not isinstance(format, str):
        raise ValueError("Choose a supported export format.")
    format = format.strip().casefold()
    format = _ALIASES.get(format, format)
    if format not in _SUFFIXES:
        raise ValueError("Unsupported export format. Choose a common image, audio, or video format; camera RAW export is not supported.")
    source = media._local_file(Path(source))
    destination = Path(destination).resolve()
    if source == destination:
        raise ValueError("Export to a new file; the source cannot be overwritten.")
    if destination.suffix.casefold() not in _SUFFIXES[format]:
        raise ValueError("The destination file extension must match the selected export format.")
    if destination.exists():
        raise ValueError("The export destination already exists. Choose a new file.")
    metadata = _source_metadata(source)
    if format in IMAGE_FORMATS and metadata["kind"] != "image":
        raise ValueError("Photographic exports require an image source.")
    if format in AUDIO_FORMATS and metadata["kind"] not in {"audio", "video"}:
        raise ValueError("Audio exports require an audio source or a video with sound.")
    if format in VIDEO_FORMATS and metadata["kind"] != "video":
        raise ValueError("Video exports require a video source. Animate an image with the Video workflow first.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.stem}-{uuid4().hex}.partial{destination.suffix}"
    try:
        if format in IMAGE_FORMATS:
            result = _export_image(source, temporary, format)
        elif format in AUDIO_FORMATS:
            result = _export_audio(source, temporary, format, metadata)
        else:
            result = _export_video(source, temporary, format, metadata)
        result.update(operation="export", format=format, bytes=temporary.stat().st_size)
        temporary.replace(destination)
        return result
    finally:
        temporary.unlink(missing_ok=True)
