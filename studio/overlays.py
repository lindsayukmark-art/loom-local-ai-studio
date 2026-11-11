"""Offline transparent WebM overlays for OBS, rendered from local PNG/WebP art.

This module preserves existing image alpha or removes an explicitly selected
solid colour. It does not infer image backgrounds or generate new artwork.
"""
from __future__ import annotations

import math
import re
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError

from .media import _image, _local_file, _number, _options, _run, inspect_asset


def _integer(options: dict, name: str, default: int, low: int, high: int) -> int:
    value = _number(options, name, default, low, high)
    if value != int(value):
        raise ValueError(f'{name} must be a whole number.')
    return int(value)


def _transparent_art(source: Path, options: dict) -> Image.Image:
    source = _local_file(source)
    try:
        with Image.open(source, formats=('PNG', 'WEBP')) as original:
            if original.format not in {'PNG', 'WEBP'}:
                raise ValueError('Overlays require a PNG or WebP image.')
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValueError('Upload a PNG or WebP image for the transparent overlay.') from exc
    art = _image(source).convert('RGBA')
    key = options.get('chroma_key')
    if key is not None:
        if not isinstance(key, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', key):
            raise ValueError('chroma_key must be a colour such as #00FF00.')
        selected = tuple(int(key[index:index + 2], 16) for index in (1, 3, 5))
        tolerance = _number(options, 'tolerance', 10, 0, 100) * 2.55
        bands = art.split()
        differences = [bands[index].point(lambda value, reference=selected[index]: abs(value - reference))
                       for index in range(3)]
        distance = ImageChops.lighter(ImageChops.lighter(differences[0], differences[1]), differences[2])
        mask = distance.point(lambda value: 0 if value <= tolerance else 255)
        art.putalpha(ImageChops.multiply(bands[3], mask))
    elif 'tolerance' in options:
        raise ValueError('tolerance is available only with a selected chroma_key colour.')
    minimum, maximum = art.getchannel('A').getextrema()
    if minimum == 255:
        raise ValueError('This image has no transparency. Upload a transparent PNG/WebP, or explicitly choose a background colour to remove.')
    if maximum == 0:
        raise ValueError('The image is fully transparent. Choose artwork or a colour key that leaves visible pixels.')
    return art


def create_overlay(source: Path, destination: Path, options: dict) -> dict:
    """Render a bounded, alpha-preserving WebM loop with no network access.

    ``effect`` is float, pulse, spin, or still. Width/height are even values
    128..1024, duration 1..10 seconds, and fps 8..30, capped at 240 frames.
    A supplied chroma_key '#RRGGBB' uses explicit colour filtering; tolerance
    is a percentage of the per-channel RGB distance, from 0 through 100.
    """
    _options(options, {'effect', 'duration', 'fps', 'width', 'height', 'chroma_key', 'tolerance'})
    effect = options.get('effect', 'float')
    if not isinstance(effect, str) or effect not in {'float', 'pulse', 'spin', 'still'}:
        raise ValueError('Overlay effect must be float, pulse, spin, or still.')
    width = _integer(options, 'width', 512, 128, 1024)
    height = _integer(options, 'height', 512, 128, 1024)
    if width % 2 or height % 2:
        raise ValueError('Overlay width and height must be even numbers.')
    fps = _integer(options, 'fps', 15, 8, 30)
    duration = _number(options, 'duration', 3, 1, 10)
    frames = round(duration * fps)
    if frames > 240:
        raise ValueError('Choose a shorter duration or lower frame rate: overlays support at most 240 frames.')
    destination = Path(destination)
    if destination.suffix.lower() != '.webm':
        raise ValueError('Transparent overlays must be exported as a .webm file.')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('FFmpeg and ffprobe are required to export transparent WebM overlays.')
    art = _transparent_art(Path(source), options)
    fraction = .60 if effect == 'spin' else .75
    art = ImageOps.contain(art, (int(width * fraction), int(height * fraction)), Image.Resampling.LANCZOS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='loom-overlay-', dir=destination.parent) as directory:
        temporary = Path(directory)
        for frame in range(frames):
            phase = 2 * math.pi * frame / frames
            image = art
            offset = (0, 0)
            if effect == 'float':
                offset = (round(math.sin(phase) * width * .04), round(math.cos(phase) * height * .05))
            elif effect == 'pulse':
                scale = .90 + .10 * math.cos(phase)
                image = art.resize((max(1, round(art.width * scale)), max(1, round(art.height * scale))), Image.Resampling.LANCZOS)
            elif effect == 'spin':
                image = art.rotate(-360 * frame / frames, resample=Image.Resampling.BICUBIC, expand=True)
            canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            canvas.alpha_composite(image, ((width - image.width) // 2 + offset[0], (height - image.height) // 2 + offset[1]))
            canvas.save(temporary / f'frame-{frame:04d}.png', format='PNG')
        encoded = temporary / 'overlay.webm'
        _run([
            'ffmpeg', '-v', 'error', '-nostdin', '-y', '-protocol_whitelist', 'file,pipe',
            '-framerate', str(fps), '-i', str(temporary / 'frame-%04d.png'),
            '-frames:v', str(frames), '-an', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p',
            '-auto-alt-ref', '0', '-metadata:s:v:0', 'alpha_mode=1', '-crf', '30', '-b:v', '0',
            '-threads', '1', '-row-mt', '1', '-cpu-used', '8', str(encoded),
        ], timeout=120)
        info = inspect_asset(encoded)
        # The metadata flag alone is insufficient proof of real alpha. Tests
        # decode the exported bitstream with libvpx-vp9 and inspect its pixels.
        encoded.replace(destination)
    return info | {'transparent': True, 'frames': frames, 'fps': fps, 'operation': 'transparent_overlay'}
