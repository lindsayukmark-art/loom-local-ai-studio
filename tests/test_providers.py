from contextlib import nullcontext
import json
import os
from pathlib import Path
import tempfile
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx

from studio.providers import LocalModels, ModelUnavailable, _loopback_url


class OfflineProviderTests(unittest.IsolatedAsyncioTestCase):
    def settings(self, **updates):
        values = dict(ollama_url="http://127.0.0.1:11434", text_model="qwen3:8b",
                      image_model_path="", video_model_path="", device="auto", enable_local_ai=True)
        values.update(updates)
        return SimpleNamespace(**values)

    def test_only_loopback_ollama_is_allowed(self):
        for forbidden in ["https://api.openai.com:443", "http://192.168.1.1:11434",
                          "http://127.0.0.1.example.com:11434", "http://user@localhost:11434",
                          "http://localhost:11434/path", "http://localhost:11434?remote=1",
                          "http://localhost", "http://localhost:11434#remote"]:
            with self.subTest(url=forbidden), self.assertRaises(ValueError):
                LocalModels(self.settings(ollama_url=forbidden))
        for allowed in ["http://127.0.0.1:11434/", "http://localhost:11434", "http://[::1]:11434"]:
            self.assertTrue(_loopback_url(allowed).startswith("http://"))

    async def test_missing_models_are_reported_without_loading_libraries(self):
        models = LocalModels(self.settings(enable_local_ai=False))
        capabilities = await models.capabilities()
        self.assertFalse(capabilities["reasoning"]["available"])
        self.assertFalse(capabilities["image"]["available"])
        self.assertFalse(capabilities["video"]["available"])
        with self.assertRaises(ModelUnavailable):
            models.generate_image("A tree", Path("unused.png"))
        with self.assertRaises(ModelUnavailable):
            models.generate_video("A tree", Path("unused.mp4"))

    async def test_reason_uses_only_installed_local_model_and_ignores_proxies(self):
        calls = []
        real_client = httpx.AsyncClient
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.host, "127.0.0.1")
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
            data = json.loads(request.content)
            self.assertFalse(data["stream"])
            self.assertFalse(data["think"])
            self.assertEqual(data["model"], "qwen3:8b")
            self.assertEqual(data["options"]["num_predict"], 2048)
            self.assertEqual(data["messages"][1]["content"], "Write a plan")
            return httpx.Response(200, json={"message": {"content": " A local plan. "}})
        def client(**kwargs):
            self.assertIs(kwargs["trust_env"], False)
            self.assertIs(kwargs["follow_redirects"], False)
            return real_client(transport=httpx.MockTransport(handler), **kwargs)
        with patch("studio.providers.httpx.AsyncClient", side_effect=client):
            answer = await LocalModels(self.settings()).reason("Be useful", "Write a plan")
        self.assertEqual(answer, "A local plan.")
        self.assertEqual([r.url.path for r in calls], ["/api/tags", "/api/chat"])

    async def test_custom_token_budget_sent_and_truncated_output_rejected(self):
        real_client = httpx.AsyncClient
        def handler(request):
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
            data = json.loads(request.content)
            self.assertEqual(data["options"]["num_predict"], 4096)
            return httpx.Response(200, json={"message": {"content": "<html>incomplete"},
                                            "done": True, "done_reason": "length"})
        with patch("studio.providers.httpx.AsyncClient", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            with self.assertRaisesRegex(ModelUnavailable, "response token limit"):
                await LocalModels(self.settings()).reason("Make a complete game", "A platformer", max_tokens=4096)

    async def test_token_budget_is_bounded_before_any_request(self):
        model = LocalModels(self.settings())
        for invalid in (0, -1, 8193, 4096.0, True, None, "4096"):
            with self.subTest(budget=invalid), patch("studio.providers.httpx.AsyncClient") as client:
                with self.assertRaisesRegex(ValueError, "max_tokens"):
                    await model.reason("", "hello", max_tokens=invalid)
                client.assert_not_called()

    async def test_cloud_tags_and_remote_models_are_rejected(self):
        models = LocalModels(self.settings(text_model="gpt-oss:120b-cloud"))
        with patch("studio.providers.httpx.AsyncClient") as client:
            with self.assertRaises(ModelUnavailable):
                await models.reason("", "hello")
            client.assert_not_called()
        real_client = httpx.AsyncClient
        def handler(request):
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b", "remote_host": "https://remote.example"}]})
        with patch("studio.providers.httpx.AsyncClient", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            with self.assertRaises(ModelUnavailable):
                await LocalModels(self.settings()).reason("", "hello")

    async def test_redirects_and_server_failures_do_not_become_false_successes(self):
        real_client = httpx.AsyncClient
        for status in (302, 500):
            def handler(request):
                return httpx.Response(status, headers={"location": "https://external.example"})
            with patch("studio.providers.httpx.AsyncClient", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
                capabilities = await LocalModels(self.settings()).capabilities()
            self.assertFalse(capabilities["reasoning"]["available"])

    def test_model_paths_require_supported_local_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            settings = self.settings(image_model_path=str(folder))
            adapter = LocalModels(settings)
            self.assertFalse(adapter._diffusion_status("image")["available"])
            for pipeline in ("CustomRemotePipeline", ["malformed"], {"name": "invalid"}, None):
                (folder / "model_index.json").write_text(json.dumps({"_class_name": pipeline}))
                with self.assertRaisesRegex(ModelUnavailable, "Unsupported local pipeline"):
                    adapter.generate_image("test", folder / "out.png")
            (folder / "model_index.json").write_text(json.dumps({"_class_name": "StableDiffusionPipeline"}))
            with patch("studio.providers._dependency_available", return_value=True):
                status = adapter._diffusion_status("image")
            self.assertTrue(status["available"])
            self.assertIn("verified on first generation", status["detail"])

    def test_image_inference_loads_only_local_safetensors(self):
        from PIL import Image
        calls = []
        class Pipeline:
            def to(self, device):
                calls.append(("device", device))
                return self
            def __call__(self, **kwargs):
                calls.append(("inference", kwargs))
                return SimpleNamespace(images=[Image.new("RGB", (32, 32), "purple")])
        class Loader:
            @staticmethod
            def from_pretrained(path, **kwargs):
                calls.append(("load", path, kwargs))
                return Pipeline()
        fake_diffusers = SimpleNamespace(AutoPipelineForText2Image=Loader, AutoPipelineForImage2Image=Loader)
        fake_torch = SimpleNamespace(inference_mode=nullcontext)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "model_index.json").write_text(json.dumps({"_class_name": "StableDiffusionPipeline"}))
            model = LocalModels(self.settings(image_model_path=str(folder)))
            with patch.dict("sys.modules", {"diffusers": fake_diffusers}), \
                 patch.object(model, "_check_diffusion"), \
                 patch.object(model, "_torch_device", return_value=(fake_torch, "cpu", "float32")):
                model.generate_image("A purple cube", folder / "output.png")
            with Image.open(folder / "output.png") as image:
                self.assertEqual(image.getpixel((0, 0)), (128, 0, 128))
        load = next(item for item in calls if item[0] == "load")
        self.assertIs(load[2]["local_files_only"], True)
        self.assertIs(load[2]["use_safetensors"], True)
        self.assertIs(load[2]["trust_remote_code"], False)
        inference = next(item[1] for item in calls if item[0] == "inference")
        self.assertEqual(inference["width"], 512)
        self.assertEqual(inference["prompt"], "A purple cube")

    def test_video_reference_must_match_local_pipeline(self):
        fake_diffusers = SimpleNamespace(DiffusionPipeline=object)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            model = LocalModels(self.settings(video_model_path=str(folder)))
            with patch.dict("sys.modules", {"diffusers": fake_diffusers}), \
                 patch.object(model, "_check_diffusion"), \
                 patch.object(model, "_torch_device", return_value=(None, "cpu", "float32")):
                (folder / "model_index.json").write_text(json.dumps({"_class_name": "CogVideoXImageToVideoPipeline"}))
                with self.assertRaisesRegex(ModelUnavailable, "requires an image"):
                    model.generate_video("A moving cube", folder / "output.mp4")
                (folder / "model_index.json").write_text(json.dumps({"_class_name": "TextToVideoSDPipeline"}))
                with self.assertRaisesRegex(ModelUnavailable, "requires a local CogVideoX"):
                    model.generate_video("A moving cube", folder / "output.mp4", reference=folder / "source.png")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_generated_frames_encode_to_real_video(self):
        from PIL import Image
        from studio.media import inspect_asset
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "frames.mp4"
            LocalModels._write_video_frames([Image.new("RGB", (32, 32), "red") for _ in range(8)], output, 8)
            metadata = inspect_asset(output)
            self.assertEqual(metadata["kind"], "video")
            self.assertEqual(metadata["width"], 32)
            self.assertAlmostEqual(metadata["duration"], 1.0, places=1)

    def test_hugging_face_network_access_is_disabled(self):
        for name in ["HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"]:
            self.assertEqual(os.environ[name], "1")


if __name__ == "__main__":
    unittest.main()
