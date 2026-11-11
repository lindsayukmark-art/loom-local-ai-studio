import math
import cmath
import json
import shutil
import tempfile
import unittest
import wave
import struct
import subprocess
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from studio.media import change_voice, clean_audio, edit_image, inspect_asset, render_video


def _peak_frequency(samples, rate):
    """Small FFT keeps audio assertions usable with only base dependencies."""
    size = min(16384, 1 << (len(samples).bit_length() - 1))
    values = [complex(samples[index] * (0.5 - 0.5 * math.cos(2 * math.pi * index / (size - 1))))
              for index in range(size)]
    reversed_index = 0
    for index in range(1, size):
        bit = size >> 1
        while reversed_index & bit:
            reversed_index ^= bit
            bit >>= 1
        reversed_index ^= bit
        if index < reversed_index:
            values[index], values[reversed_index] = values[reversed_index], values[index]
    span = 2
    while span <= size:
        multiplier = cmath.exp(-2j * math.pi / span)
        for start in range(0, size, span):
            twiddle = 1 + 0j
            for offset in range(span // 2):
                left = values[start + offset]
                right = values[start + offset + span // 2] * twiddle
                values[start + offset] = left + right
                values[start + offset + span // 2] = left - right
                twiddle *= multiplier
        span *= 2
    peak = max(range(1, size // 2), key=lambda index: abs(values[index]))
    return peak * rate / size


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.source = self.root / "source.png"
        # Non-uniform image checks image orientation and actual transformations.
        original = Image.new("RGB", (64, 32), "red")
        original.paste("blue", (32, 0, 64, 32))
        original.save(self.source)

    def tearDown(self):
        self.directory.cleanup()

    def test_inspects_bytes_without_trusting_extension(self):
        disguised = self.root / "not-a-video.mp4"
        shutil.copyfile(self.source, disguised)
        info = inspect_asset(disguised)
        self.assertEqual(info["kind"], "image")
        self.assertEqual(info["mime"], "image/png")
        self.assertEqual((info["width"], info["height"]), (64, 32))

    def test_flip_resize_and_grayscale_change_pixels(self):
        destination = self.root / "edited.png"
        info = edit_image(self.source, destination, {"width": 32, "flip": "horizontal", "grayscale": True})
        self.assertEqual((info["width"], info["height"]), (32, 16))
        with Image.open(destination) as image:
            left, right = image.getpixel((0, 0)), image.getpixel((31, 0))
            self.assertEqual(left[0], left[1])
            self.assertEqual(left[1], left[2])
            self.assertLess(left[0], right[0])

    def test_crop_and_rotate(self):
        destination = self.root / "cropped.png"
        info = edit_image(self.source, destination, {
            "crop": {"left": 0, "top": 0, "right": 32, "bottom": 16}, "rotate": 90,
        })
        self.assertEqual((info["width"], info["height"]), (16, 32))

    def test_operation_angle_and_factor_aliases(self):
        info = edit_image(self.source, self.root / "rotated.png", {"operation": "rotate", "angle": 90})
        self.assertEqual((info["width"], info["height"]), (32, 64))
        destination = self.root / "darkened.png"
        edit_image(self.source, destination, {"operation": "brightness", "factor": 0.5})
        with Image.open(destination) as image:
            self.assertIn(image.getpixel((0, 0))[0], (127, 128))

    def test_rejects_non_media_and_manifests(self):
        fake = self.root / "fake.mp4"
        fake.write_text("#EXTM3U\nhttps://example.invalid/remote.mp4")
        with self.assertRaises(ValueError):
            inspect_asset(fake)

    def test_rejects_unsafe_options(self):
        for options in ({"width": -1}, {"width": 10.5}, {"width": 100000}, {"brightness": math.nan},
                        {"grayscale": "yes"}, {"command": "echo hello"},
                        {"crop": {"left": 0, "top": 0, "right": 100, "bottom": 100}}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                edit_image(self.source, self.root / "bad.png", options)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is not installed")
    def test_image_animation_and_video_trim(self):
        animation = self.root / "animation.mp4"
        info = render_video(self.source, animation, {"duration": 1, "width": 64, "height": 32})
        self.assertEqual(info["kind"], "video")
        self.assertEqual(info["operation"], "image_animation")
        self.assertAlmostEqual(info["duration"], 1, delta=0.15)
        trimmed = self.root / "trimmed.mp4"
        info = render_video(animation, trimmed, {"start": 0.2, "duration": 0.5, "grayscale": True,
                                                 "width": 32, "height": 16})
        self.assertEqual(info["operation"], "video_edit")
        self.assertEqual((info["width"], info["height"]), (32, 16))
        self.assertAlmostEqual(info["duration"], 0.5, delta=0.15)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is not installed")
    def test_rejects_out_of_bounds_video_requests(self):
        with self.assertRaises(ValueError):
            render_video(self.source, self.root / "too-long.mp4", {"duration": 500})

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is not installed")
    def test_audio_cleanup_writes_real_audio(self):
        source = self.root / "sound.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            audio.writeframes(b"".join(struct.pack("<h", int(2000 * math.sin(2 * math.pi * 440 * n / 16000)))
                                       for n in range(16000)))
        original = inspect_asset(source)
        self.assertEqual(original["kind"], "audio")
        self.assertEqual(original["sample_rate"], 16000)
        destination = self.root / "cleaned.wav"
        info = clean_audio(source, destination, {"noise_reduction": 16, "duration": 0.5})
        self.assertEqual(info["operation"], "audio_cleanup")
        self.assertEqual(info["mime"], "audio/wav")
        self.assertEqual(info["sample_rate"], 48000)
        self.assertEqual(info["channels"], 2)
        self.assertAlmostEqual(info["duration"], 0.5, delta=0.1)
        self.assertNotEqual(source.read_bytes(), destination.read_bytes())
        with self.assertRaises(ValueError):
            clean_audio(source, self.root / "bad.wav", {"noise_reduction": 100})

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is not installed")
    def test_audio_cleanup_reduces_low_frequency_hum(self):
        source = self.root / "humming.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            audio.writeframes(b"".join(struct.pack("<h", int(
                3000 * math.sin(2 * math.pi * 50 * n / 16000)
                + 3000 * math.sin(2 * math.pi * 440 * n / 16000))) for n in range(16000)))
        destination = self.root / "less-hum.wav"
        clean_audio(source, destination, {"highpass": 150, "noise_reduction": 0, "normalize": False})
        with wave.open(str(destination), "rb") as audio:
            values = struct.unpack("<" + "h" * (audio.getnframes() * audio.getnchannels()),
                                   audio.readframes(audio.getnframes()))
            samples = values[::2]
            rate = audio.getframerate()
        # Skip the filter startup and compare surviving hum with the speech-band tone.
        samples = samples[rate // 10:]
        def magnitude(frequency):
            sine = sum(value * math.sin(2 * math.pi * frequency * n / rate) for n, value in enumerate(samples))
            cosine = sum(value * math.cos(2 * math.pi * frequency * n / rate) for n, value in enumerate(samples))
            return math.hypot(sine, cosine)
        self.assertLess(magnitude(50) / magnitude(440), 0.3)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is not installed")
    def test_audio_cover_art_is_not_classified_as_video(self):
        sound = self.root / "sound.wav"
        with wave.open(str(sound), "wb") as audio:
            audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\x00\x00" * 16000)
        covered = self.root / "covered.mp3"
        subprocess.run([
            "ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(sound), "-i", str(self.source),
            "-map", "0:a:0", "-map", "1:v:0", "-c:a", "libmp3lame", "-c:v", "png",
            "-disposition:v", "attached_pic", "-id3v2_version", "3", str(covered),
        ], check=True, capture_output=True, timeout=20)
        info = inspect_asset(covered)
        self.assertEqual(info["kind"], "audio")
        self.assertEqual(info["mime"], "audio/mpeg")
        self.assertAlmostEqual(info["duration"], 1, delta=0.2)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is not installed")
    def test_video_soundtrack_cleanup_preserves_audio(self):
        animation = self.root / "silent.mp4"
        render_video(self.source, animation, {"duration": 1, "width": 64, "height": 32})
        sound = self.root / "soundtrack.wav"
        with wave.open(str(sound), "wb") as audio:
            audio.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            audio.writeframes(b"".join(struct.pack("<h", int(2000 * math.sin(2 * math.pi * 440 * n / 48000)))
                                       for n in range(48000)))
        combined = self.root / "with-sound.mp4"
        subprocess.run([
            "ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(animation), "-i", str(sound),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", str(combined),
        ], check=True, capture_output=True, timeout=20)
        destination = self.root / "clean-video.mp4"
        info = render_video(combined, destination, {"denoise_audio": True, "start": 0.1, "duration": 0.5,
                                                   "grayscale": True, "speed": 1.25})
        self.assertEqual(info["operation"], "video_edit")
        self.assertAlmostEqual(info["duration"], 0.4, delta=0.15)
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(destination),
        ], capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual({entry["codec_type"] for entry in json.loads(result.stdout)["streams"]}, {"video", "audio"})
        changed = change_voice(combined, self.root / "voice-from-video.wav", {"preset": "bright"})
        self.assertEqual(changed["kind"], "audio")
        self.assertEqual(changed["pitch_semitones"], 4)


    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is not installed")
    def test_voice_change_shifts_pitch_and_preserves_duration(self):
        source = self.root / "voice-tone.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            audio.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(2 * math.pi * 440 * n / 16000)))
                                       for n in range(32000)))
        destination = self.root / "octave-up.wav"
        metadata = change_voice(source, destination, {"pitch_semitones": 12, "normalize": False})
        self.assertEqual(metadata["operation"], "voice_change")
        self.assertAlmostEqual(metadata["duration"], 2, delta=0.08)
        with wave.open(str(destination), "rb") as audio:
            rate = audio.getframerate()
            channels = audio.getnchannels()
            samples = struct.unpack("<" + "h" * (audio.getnframes() * channels),
                                    audio.readframes(audio.getnframes()))[::channels]
        samples = samples[rate // 4:-rate // 4]
        frequency = _peak_frequency(samples, rate)
        self.assertAlmostEqual(frequency, 880, delta=5)
        self.assertEqual(metadata["sample_rate"], 48000)
        self.assertEqual(metadata["channels"], 2)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is not installed")
    def test_voice_speed_changes_duration_without_changing_pitch(self):
        source = self.root / "speed-tone.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            audio.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(2 * math.pi * 440 * n / 16000)))
                                       for n in range(32000)))
        destination = self.root / "fast-voice.wav"
        metadata = change_voice(source, destination, {"speed": 2, "normalize": False})
        self.assertAlmostEqual(metadata["duration"], 1, delta=0.08)
        with wave.open(str(destination), "rb") as audio:
            rate = audio.getframerate()
            channels = audio.getnchannels()
            samples = struct.unpack("<" + "h" * (audio.getnframes() * channels),
                                    audio.readframes(audio.getnframes()))[::channels]
        samples = samples[rate // 10:-rate // 10]
        frequency = _peak_frequency(samples, rate)
        self.assertAlmostEqual(frequency, 440, delta=5)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is not installed")
    def test_voice_presets_and_bounded_options(self):
        source = self.root / "voice.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            audio.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(2 * math.pi * 440 * n / 16000)))
                                       for n in range(16000)))
        metadata = change_voice(source, self.root / "deep.wav", {"preset": "deep", "denoise": True})
        self.assertEqual(metadata["pitch_semitones"], -4)
        self.assertAlmostEqual(metadata["duration"], 1, delta=0.08)
        for options in ({"pitch_semitones": 13}, {"pitch_semitones": -13}, {"speed": 0.1},
                        {"speed": math.nan}, {"preset": "clone"}, {"denoise": "yes"},
                        {"normalize": 1}, {"duration": 601}, {"voice_url": "https://example.com"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                change_voice(source, self.root / "invalid-voice.wav", options)
        with self.assertRaisesRegex(ValueError, "audio or video"):
            change_voice(self.source, self.root / "no-voice.wav", {})
        with patch("studio.media.inspect_asset", return_value={"kind": "audio", "duration": 900}):
            with self.assertRaisesRegex(ValueError, "limited to 600"):
                change_voice(source, self.root / "too-long-voice.wav", {"duration": 600, "speed": 0.5})


if __name__ == "__main__":
    unittest.main()
