import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave

from PIL import Image, features

from studio.exports import available_image_formats, export_asset


FFMPEG_AVAILABLE = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source.png"
        image = Image.new("RGBA", (16, 8), (255, 0, 0, 0))
        image.paste((0, 255, 0, 128), (4, 0, 8, 8))
        image.paste((0, 0, 255, 255), (8, 0, 16, 8))
        image.save(self.source)

    def make_sound(self):
        source = self.root / "sound.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            audio.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * index / 16000)))
                                       for index in range(8000)))
        return source

    @staticmethod
    def probe(path):
        result = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams",
                                 "-show_format", "-of", "json", str(path)],
                                capture_output=True, text=True, check=True, timeout=20)
        return json.loads(result.stdout)

    def make_video(self):
        video = self.root / "source-video.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-threads", "1", "-filter_threads", "1",
                        "-f", "lavfi", "-i", "color=c=blue:s=80x40:r=12:d=0.5",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.5",
                        "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-shortest", str(video)], capture_output=True, check=True, timeout=30)
        return video

    def test_photographic_exports_encode_real_formats(self):
        expected = {
            "png": ("PNG", b"\x89PNG\r\n\x1a\n"), "jpg": ("JPEG", b"\xff\xd8"),
            "webp": ("WEBP", b"RIFF"), "gif": ("GIF", b"GIF8"),
            "bmp": ("BMP", b"BM"), "tiff": ("TIFF", b"II"),
        }
        for format, (pil_format, magic) in expected.items():
            with self.subTest(format=format):
                target = self.root / ("exported." + format)
                metadata = export_asset(self.source, target, format)
                self.assertTrue(target.read_bytes().startswith(magic))
                self.assertEqual(metadata["kind"], "image")
                self.assertEqual(metadata["format"], format)
                self.assertEqual(metadata["operation"], "export")
                self.assertEqual(metadata["bytes"], target.stat().st_size)
                with Image.open(target) as image:
                    self.assertEqual(image.format, pil_format)
                    self.assertEqual(image.size, (16, 8))
                    image.load()

    def test_jpeg_and_bmp_flatten_transparency_onto_white(self):
        for format in ("jpg", "bmp"):
            with self.subTest(format=format):
                target = self.root / ("white." + format)
                metadata = export_asset(self.source, target, format)
                self.assertFalse(metadata["transparent"])
                self.assertIn("flattened onto white", metadata["note"])
                with Image.open(target) as image:
                    pixel = image.convert("RGB").getpixel((0, 0))
                    self.assertTrue(all(channel >= 245 for channel in pixel), pixel)

    def test_alpha_survives_png_webp_tiff_and_binary_gif(self):
        for format in ("png", "webp", "tiff", "gif"):
            with self.subTest(format=format):
                target = self.root / ("alpha." + format)
                metadata = export_asset(self.source, target, format)
                self.assertTrue(metadata["transparent"])
                with Image.open(target) as image:
                    rgba = image.convert("RGBA")
                    self.assertEqual(rgba.getpixel((0, 0))[3], 0)
                    self.assertEqual(rgba.getpixel((15, 0))[3], 255)
                    if format != "gif":
                        self.assertEqual(rgba.getpixel((5, 0))[3], 128)
                if format == "gif":
                    self.assertIn("binary transparency", metadata["note"])

    def test_exif_orientation_applies_to_dimensions(self):
        source = self.root / "rotated-camera.jpg"
        image = Image.new("RGB", (16, 8), "red")
        exif = Image.Exif()
        exif[274] = 6
        image.save(source, exif=exif)
        target = self.root / "oriented.png"
        metadata = export_asset(source, target, "png")
        self.assertEqual((metadata["width"], metadata["height"]), (8, 16))

    def test_jpeg_and_tiff_aliases_and_reconversion(self):
        jpeg = self.root / "export.jpeg"
        self.assertEqual(export_asset(self.source, jpeg, "jpeg")["format"], "jpg")
        tiff = self.root / "export.tif"
        self.assertEqual(export_asset(self.source, tiff, "tif")["format"], "tiff")
        restored = self.root / "restored.png"
        self.assertTrue(export_asset(tiff, restored, "png")["transparent"])

    def test_avif_is_optional_and_capability_checked(self):
        if "avif" in features.get_supported():
            target = self.root / "export.avif"
            metadata = export_asset(self.source, target, "avif")
            self.assertEqual(metadata["mime"], "image/avif")
            self.assertTrue(metadata["transparent"])
            with Image.open(target) as image:
                self.assertEqual(image.format, "AVIF")
                image.load()
        with patch("studio.exports.features.get_supported", return_value=["jpg", "zlib"]):
            self.assertNotIn("avif", available_image_formats())
            with self.assertRaisesRegex(ValueError, "AVIF export is unavailable"):
                export_asset(self.source, self.root / "unsupported.avif", "avif")
        self.assertFalse((self.root / "unsupported.avif").exists())

    def test_invalid_combinations_raw_and_overwrites_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "extension"):
            export_asset(self.source, self.root / "wrong.png", "jpg")
        with self.assertRaisesRegex(ValueError, "RAW"):
            export_asset(self.source, self.root / "camera.cr3", "cr3")
        with self.assertRaisesRegex(ValueError, "source cannot be overwritten"):
            export_asset(self.source, self.source, "png")
        existing = self.root / "existing.png"
        existing.write_bytes(b"preserve this file")
        with self.assertRaisesRegex(ValueError, "already exists"):
            export_asset(self.source, existing, "png")
        self.assertEqual(existing.read_bytes(), b"preserve this file")
        with self.assertRaisesRegex(ValueError, "Audio exports require"):
            export_asset(self.source, self.root / "fake.mp3", "mp3")
        with self.assertRaisesRegex(ValueError, "Video exports require"):
            export_asset(self.source, self.root / "fake.mp4", "mp4")
        self.assertFalse((self.root / "fake.mp3").exists())
        self.assertFalse((self.root / "fake.mp4").exists())

    def test_manifest_is_not_treated_as_remote_media(self):
        source = self.root / "playlist.mp4"
        source.write_text("#EXTM3U\nhttps://example.invalid/movie.mp4")
        with self.assertRaises(ValueError):
            export_asset(source, self.root / "downloaded.mp4", "mp4")

    @unittest.skipUnless(FFMPEG_AVAILABLE, "FFmpeg is unavailable")
    def test_audio_exports_have_real_codecs_and_readable_durations(self):
        source = self.make_sound()
        expected = {"wav": "pcm_s16le", "mp3": "mp3", "flac": "flac", "ogg": "vorbis", "m4a": "aac"}
        for format, codec in expected.items():
            with self.subTest(format=format):
                target = self.root / ("export-audio." + format)
                metadata = export_asset(source, target, format)
                info = self.probe(target)
                streams = info["streams"]
                self.assertEqual([stream["codec_type"] for stream in streams], ["audio"])
                self.assertEqual(streams[0]["codec_name"], codec)
                self.assertEqual(metadata["kind"], "audio")
                self.assertAlmostEqual(metadata["duration"], 0.5, delta=0.15)
                self.assertNotEqual(source.read_bytes(), target.read_bytes())

    @unittest.skipUnless(FFMPEG_AVAILABLE, "FFmpeg is unavailable")
    def test_video_exports_are_playable_and_sound_is_retained(self):
        source = self.make_video()
        for format, codec in (("mp4", "h264"), ("webm", "vp9"), ("mov", "h264")):
            with self.subTest(format=format):
                target = self.root / ("export-video." + format)
                metadata = export_asset(source, target, format)
                info = self.probe(target)
                self.assertEqual({stream["codec_type"] for stream in info["streams"]}, {"video", "audio"})
                video_stream = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
                self.assertEqual(video_stream["codec_name"], codec)
                self.assertEqual((metadata["width"], metadata["height"]), (80, 40))
                self.assertFalse(metadata["transparent"])
                self.assertAlmostEqual(metadata["duration"], 0.5, delta=0.15)
                # Decode actual frames, rather than accepting container headers.
                subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-threads", "1", "-protocol_whitelist", "file,pipe",
                                "-i", str(target), "-frames:v", "1", "-f", "null", "-"],
                               capture_output=True, check=True, timeout=20)

    @unittest.skipUnless(FFMPEG_AVAILABLE, "FFmpeg is unavailable")
    def test_video_soundtrack_exports_to_mp3(self):
        source = self.make_video()
        metadata = export_asset(source, self.root / "soundtrack.mp3", "mp3")
        self.assertEqual(metadata["kind"], "audio")
        info = self.probe(self.root / "soundtrack.mp3")
        self.assertEqual([stream["codec_type"] for stream in info["streams"]], ["audio"])
        self.assertEqual(info["streams"][0]["codec_name"], "mp3")

    @unittest.skipUnless(FFMPEG_AVAILABLE, "FFmpeg is unavailable")
    def test_video_export_downscales_large_dimensions(self):
        source = self.root / "large.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-threads", "1", "-filter_threads", "1",
                        "-f", "lavfi", "-i", "color=c=blue:s=2560x1440:r=4:d=0.25",
                        "-c:v", "libx264", "-threads", "1", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(source)],
                       capture_output=True, check=True, timeout=30)
        metadata = export_asset(source, self.root / "bounded.mp4", "mp4")
        self.assertEqual((metadata["width"], metadata["height"]), (1920, 1080))

    @unittest.skipUnless(FFMPEG_AVAILABLE, "FFmpeg is unavailable")
    def test_long_video_export_is_bounded_and_reports_truncation(self):
        source = self.root / "long.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-threads", "1", "-filter_threads", "1",
                        "-f", "lavfi", "-i", "color=c=blue:s=32x16:r=1:d=121",
                        "-c:v", "libx264", "-threads", "1", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(source)],
                       capture_output=True, check=True, timeout=30)
        metadata = export_asset(source, self.root / "two-minutes.mp4", "mp4")
        self.assertLessEqual(metadata["duration"], 120)
        self.assertIn("first 120 seconds", metadata["note"])

    @unittest.skipUnless(FFMPEG_AVAILABLE, "FFmpeg is unavailable")
    def test_failed_transcode_leaves_no_partial_export(self):
        source = self.make_sound()
        target = self.root / "failed.mp3"
        with patch("studio.exports.media._run", side_effect=ValueError("Encoder unavailable")):
            with self.assertRaisesRegex(ValueError, "Encoder unavailable"):
                export_asset(source, target, "mp3")
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.glob("*.partial*")), [])


if __name__ == "__main__":
    unittest.main()
