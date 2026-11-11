from pathlib import Path
import json
from types import ModuleType, SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

from studio.providers import ModelUnavailable
from studio.voice import LocalVoice


def _inspect_wav(path):
    with wave.open(str(path), "rb") as audio:
        return {"kind": "audio", "mime": "audio/wav", "sample_rate": audio.getframerate(),
                "channels": audio.getnchannels(), "duration": audio.getnframes() / audio.getframerate()}


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = self.root / "en_US-local-medium.onnx"
        self.model.write_bytes(b"mock-local-model")
        self.config = Path(str(self.model) + ".json")
        self.config.write_text(json.dumps({"audio": {"sample_rate": 16000}}))
        self.settings = SimpleNamespace(voice_model_path=str(self.model), enable_local_ai=True)

    def fake_piper(self, *, fail=False):
        voice = Mock()

        def synthesize(text, wav_file):
            if fail:
                raise RuntimeError("Bad model")
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b"\x00\x00" * 16000)

        voice.synthesize_wav.side_effect = synthesize
        piper_class = Mock()
        piper_class.load.return_value = voice
        package = ModuleType("piper")
        package.__path__ = []
        module = ModuleType("piper.voice")
        module.PiperVoice = piper_class
        return {"piper": package, "piper.voice": module}, piper_class, voice

    def test_missing_model_dependency_and_disabled_status(self):
        self.settings.voice_model_path = ""
        self.assertFalse(LocalVoice(self.settings).status()["available"])
        self.settings.voice_model_path = str(self.model)
        with patch("studio.voice._piper_available", return_value=False):
            status = LocalVoice(self.settings).status()
            self.assertFalse(status["available"])
            self.assertIn("piper-tts", status["detail"])
        self.settings.enable_local_ai = False
        self.assertIn("disabled", LocalVoice(self.settings).status()["detail"])

    def test_only_absolute_local_onnx_and_matching_config(self):
        for path in ["voice.onnx", "https://example.com/voice.onnx", "//server/share/voice.onnx", str(self.root)]:
            self.settings.voice_model_path = path
            self.assertFalse(LocalVoice(self.settings).status()["available"])
        self.settings.voice_model_path = str(self.model)
        for content in ["not json", "[]", "{}", '{"audio":{"sample_rate":true}}']:
            self.config.write_text(content)
            self.assertFalse(LocalVoice(self.settings).status()["available"])
        self.config.unlink()
        self.assertFalse(LocalVoice(self.settings).status()["available"])

    def test_status_does_not_load_model(self):
        packages, piper_class, _ = self.fake_piper()
        with patch.dict(sys.modules, packages), patch("studio.voice._piper_available", return_value=True):
            status = LocalVoice(self.settings).status()
        self.assertTrue(status["available"])
        piper_class.load.assert_not_called()

    def test_real_wav_written_through_local_piper_api_and_model_cached(self):
        packages, piper_class, voice = self.fake_piper()
        service = LocalVoice(self.settings)
        with patch.dict(sys.modules, packages), patch("studio.voice._piper_available", return_value=True), patch("studio.voice.inspect_asset", side_effect=_inspect_wav) as inspect:
            metadata = service.synthesize("  Hello offline.  ", self.root / "speech.wav")
            service.synthesize("Again.", self.root / "second.wav")
        piper_class.load.assert_called_once_with(str(self.model.resolve()))
        self.assertEqual(voice.synthesize_wav.call_args_list[0].args[0], "Hello offline.")
        self.assertEqual(inspect.call_count, 2)
        self.assertEqual(metadata["kind"], "audio")
        self.assertEqual(metadata["sample_rate"], 16000)
        self.assertEqual(metadata["duration"], 1.0)
        with wave.open(str(self.root / "speech.wav"), "rb") as wav_file:
            self.assertEqual(wav_file.getnframes(), 16000)
            self.assertEqual(wav_file.getsampwidth(), 2)
        self.assertFalse(list(self.root.glob(".loom-voice-*")))

    def test_invalid_text_and_output_refused(self):
        service = LocalVoice(self.settings)
        for text in ["", "  ", None, "x" * 4001]:
            with self.assertRaises(ValueError):
                service.synthesize(text, self.root / "bad.wav")
        with self.assertRaises(ValueError):
            service.synthesize("Text", self.root / "bad.mp3")

    def test_runtime_failure_leaves_no_partial_output(self):
        packages, _, _ = self.fake_piper(fail=True)
        target = self.root / "bad.wav"
        with patch.dict(sys.modules, packages), patch("studio.voice._piper_available", return_value=True):
            with self.assertRaises(ModelUnavailable):
                LocalVoice(self.settings).synthesize("Text", target)
        self.assertFalse(target.exists())
        self.assertFalse(list(self.root.glob(".loom-voice-*")))

    def test_missing_setup_is_model_unavailable(self):
        self.settings.voice_model_path = ""
        with self.assertRaises(ModelUnavailable):
            LocalVoice(self.settings).synthesize("Text", self.root / "missing.wav")


if __name__ == "__main__":
    unittest.main()
