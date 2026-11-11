"""Source-level launcher checks; Windows/WebView2 still require a Windows test."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

import desktop


class DesktopTests(unittest.TestCase):
    def test_data_directory_override(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"LOOM_DATA_DIR": folder}):
                self.assertEqual(desktop.app_data_directory(), Path(folder).resolve())

    def test_offline_environment_overrides_inherited_online_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"HF_HUB_OFFLINE": "0", "TRANSFORMERS_OFFLINE": "0"}):
                with patch("desktop.logging.basicConfig"):
                    desktop.prepare_environment(Path(folder))
                self.assertEqual(os.environ["HF_HUB_OFFLINE"], "1")
                self.assertEqual(os.environ["TRANSFORMERS_OFFLINE"], "1")
                self.assertEqual(os.environ["OLLAMA_NO_CLOUD"], "1")
                self.assertEqual(os.environ["LOOM_DATA_DIR"], folder)

    def test_canceled_native_menu_does_not_change_settings(self):
        window = Mock()
        window.create_file_dialog.return_value = None
        app = types.SimpleNamespace(state=types.SimpleNamespace(engine=types.SimpleNamespace(tasks={})))
        fake_webview = types.SimpleNamespace(FileDialog=types.SimpleNamespace(FOLDER=2))
        with patch.dict(sys.modules, {"webview": fake_webview}):
            with patch("desktop.post_model_setting") as post:
                self.assertFalse(desktop.choose_model(window, app, 12345, "image_model_path"))
                post.assert_not_called()

    def test_wait_for_local_server_ignores_proxy_environment(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ready")

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}):
                desktop.wait_for_server(types.SimpleNamespace(started=True), thread, server.server_port, 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_failed_server_start_is_reported(self):
        thread = Mock()
        thread.is_alive.return_value = False
        with self.assertRaisesRegex(RuntimeError, "stopped during startup"):
            desktop.wait_for_server(types.SimpleNamespace(started=False), thread, 12345, 1)

    def test_active_model_job_prevents_window_close(self):
        app = types.SimpleNamespace(state=types.SimpleNamespace(engine=types.SimpleNamespace(tasks={"job": object()})))
        with patch("desktop.show_running_job_notice") as notice:
            self.assertFalse(desktop.can_close_window(app))
            notice.assert_called_once()
        app.state.engine.tasks.clear()
        with patch("desktop.show_running_job_notice") as notice:
            self.assertTrue(desktop.can_close_window(app))
            notice.assert_not_called()

    def test_native_voice_menu_saves_selection_without_path_in_javascript(self):
        window = Mock()
        app = types.SimpleNamespace(state=types.SimpleNamespace(engine=types.SimpleNamespace(tasks={})))
        fake_webview = types.SimpleNamespace(FileDialog=types.SimpleNamespace(OPEN=1))
        with patch.dict(sys.modules, {"webview": fake_webview}):
            with patch("desktop.post_model_setting") as post:
                window.create_file_dialog.return_value = ("voice.onnx",)
                self.assertTrue(desktop.choose_model(window, app, 12345, "voice_model_path"))
                post.assert_called_once_with(12345, "voice_model_path", "voice.onnx")
                window.run_js.assert_called_once_with("window.dispatchEvent(new Event('loom-model-settings-changed'))")

    def test_native_settings_only_support_known_local_model_fields(self):
        with self.assertRaises(ValueError):
            desktop.post_model_setting(12345, "ollama_url", "http://example.com")
        with self.assertRaises(ValueError):
            desktop.post_model_setting(12345, "voice_model_path", "https://example.com/voice.onnx")
        with self.assertRaises(ValueError):
            desktop.post_model_setting(12345, "voice_model_path", "relative.onnx")

    def test_settings_post_uses_fixed_loopback_endpoint_without_proxy(self):
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured['path'] = self.path
                captured['body'] = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"saved":true}')

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}):
                    result = desktop.post_model_setting(server.server_port, "image_model_path", folder)
                self.assertEqual(result, {"saved": True})
                self.assertEqual(captured, {'path': '/api/settings', 'body': {'image_model_path': str(Path(folder).resolve())}})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_no_custom_python_api_is_exposed_to_web_documents(self):
        tree = ast.parse(Path(desktop.__file__).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotEqual(node.func.attr, 'expose')
                if node.func.attr == 'create_window':
                    self.assertNotIn('js_api', [keyword.arg for keyword in node.keywords])


if __name__ == "__main__":
    unittest.main()
