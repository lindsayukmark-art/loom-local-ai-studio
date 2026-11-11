"""Native Windows entry point. No browser, Python install, or cloud account required.

The packaged build contains Python and dependencies. Model weights and the local
Ollama server are separate, explicitly configured prerequisites.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.request
import urllib.error


APP_NAME = "Loom Studio"
_instance_handle = None


def app_data_directory() -> Path:
    override = os.environ.get("LOOM_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            raise RuntimeError("Windows LOCALAPPDATA is unavailable.")
        return Path(base) / "LoomStudio"
    return Path.home() / ".local" / "share" / "LoomStudio"


def show_error(message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
    else:
        print(message, file=sys.stderr)


def show_running_job_notice() -> None:
    message = "A local job is still running. Let it finish before closing Loom."
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x40)
    else:
        print(message, file=sys.stderr)


def can_close_window(app) -> bool:
    # Inference runs in a worker thread and cannot safely be interrupted midway
    # through a GPU call. Keep the window visible until all work has finished.
    if app.state.engine.tasks:
        show_running_job_notice()
        return False
    return True


def claim_single_instance() -> bool:
    global _instance_handle
    if sys.platform != "win32":
        return True
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    _instance_handle = kernel.CreateMutexW(None, False, "Local\\LoomStudioDesktop")
    if not _instance_handle:
        raise OSError("Could not create the desktop application lock.")
    return kernel.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def prepare_environment(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LOOM_DATA_DIR"] = str(data_dir)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        "--disable-background-networking --disable-component-update "
        "--disable-domain-reliability --disable-sync --no-first-run "
        "--disable-client-side-phishing-detection"
    )
    # A separately running Ollama server must also be started with this setting.
    os.environ["OLLAMA_NO_CLOUD"] = "1"
    os.environ.setdefault("HF_HOME", str(data_dir / "model-cache"))
    if getattr(sys, "frozen", False):
        bundle = Path(sys._MEIPASS)
        os.environ["PATH"] = str(bundle / "bin") + os.pathsep + os.environ.get("PATH", "")
    logging.basicConfig(
        filename=data_dir / "desktop.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def wait_for_server(server, thread: threading.Thread, port: int, timeout: float = 30) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not thread.is_alive():
            raise RuntimeError("The local application server stopped during startup.")
        if server.started:
            try:
                with opener.open(f"http://127.0.0.1:{port}/", timeout=1) as response:
                    if response.status == 200:
                        return
            except OSError:
                pass
        time.sleep(0.1)
    raise RuntimeError("The local application server did not start within 30 seconds.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, url):
        raise urllib.error.HTTPError(request.full_url, code, "Local settings redirects are disabled", headers, file)


def post_model_setting(port: int, setting: str, selected: str) -> dict:
    """Persist one native menu selection via the fixed loopback settings API."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid local server port.")
    if setting not in {"image_model_path", "video_model_path", "voice_model_path"}:
        raise ValueError("Unsupported model setting.")
    if selected.startswith(("\\\\", "//")) or "://" in selected:
        raise ValueError("Choose a local model path.")
    path = Path(selected).expanduser()
    if not path.is_absolute():
        raise ValueError("Choose an absolute local model path.")
    path = path.resolve()
    if setting == "voice_model_path":
        if not path.is_file() or path.suffix.lower() != ".onnx":
            raise ValueError("Choose an existing Piper .onnx voice file.")
    elif not path.is_dir():
        raise ValueError("Choose an existing model folder.")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/settings", method="POST",
        data=json.dumps({setting: str(path)}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    with opener.open(request, timeout=10) as response:
        return json.loads(response.read())


def choose_model(window, app, port: int, setting: str) -> bool:
    """Native menu callback, deliberately never exposed to page JavaScript."""
    if app.state.engine.tasks:
        show_running_job_notice()
        return False
    import webview

    if setting == "voice_model_path":
        result = window.create_file_dialog(
            webview.FileDialog.OPEN, allow_multiple=False,
            file_types=("Piper voice (*.onnx)",),
        )
    else:
        result = window.create_file_dialog(webview.FileDialog.FOLDER)
    if not result:
        return False
    try:
        post_model_setting(port, setting, result[0])
        # Fixed main-document code; no selected path or model text becomes JS.
        window.run_js("window.dispatchEvent(new Event('loom-model-settings-changed'))")
        return True
    except urllib.error.HTTPError as exc:
        logging.exception("Native model selection could not be saved")
        show_error("A local job is still running. Let it finish before changing models."
                   if exc.code == 409 else "The model setting could not be saved. Check the local model file or folder in Settings.")
    except (OSError, ValueError):
        logging.exception("Native model selection could not be saved")
        show_error("The model setting could not be saved. Check that the model path is local and valid.")
    return False


def main() -> int:
    server = None
    thread = None
    listener = None
    data_dir = app_data_directory()
    try:
        if not claim_single_instance():
            if sys.platform == "win32":
                ctypes.windll.user32.MessageBoxW(
                    None, "Loom Studio is already running. Open its existing window.", APP_NAME, 0x40
                )
            return 0
        prepare_environment(data_dir)
        import uvicorn
        import webview
        from studio.main import create_app

        webview.settings["ALLOW_DOWNLOADS"] = True

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        app = create_app()
        server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=port, log_config=None,
            access_log=False, timeout_graceful_shutdown=10,
        ))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        wait_for_server(server, thread, port)
        if "--self-test" in sys.argv[1:]:
            if sys.platform == "win32":
                # Loading webview alone does not load the native desktop
                # backend. Verify Python.NET and WinForms in the frozen build.
                import clr
                clr.AddReference("System.Windows.Forms")
            from piper.phonemize_espeak import EspeakPhonemizer

            if not EspeakPhonemizer().phonemize("en-us", "Offline voice ready."):
                raise RuntimeError("The packaged voice phonemizer did not return phonemes.")
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for resource in ("/static/app.js", "/static/styles.css", "/api/status", "/download", "/api/downloads"):
                with opener.open(f"http://127.0.0.1:{port}{resource}", timeout=10) as response:
                    if response.status != 200:
                        raise RuntimeError(f"Packaged resource check failed: {resource}")
            logging.info("Packaged application self-test passed")
            return 0
        window = webview.create_window(
            APP_NAME, f"http://127.0.0.1:{port}",
            width=1360, height=900, min_size=(900, 640),
            background_color="#101514", text_select=True,
        )
        window.events.closing += lambda: can_close_window(app)
        # Models are selected through trusted native menus. No js_api object or
        # Python functions are exposed to the UI or generated game documents.
        from webview.menu import Menu, MenuAction

        menus = [Menu("Models", [
            MenuAction("Choose image model folder…", lambda: choose_model(window, app, port, "image_model_path")),
            MenuAction("Choose video model folder…", lambda: choose_model(window, app, port, "video_model_path")),
            MenuAction("Choose Piper voice file…", lambda: choose_model(window, app, port, "voice_model_path")),
        ])]
        # Edge Chromium uses the already-installed WebView2 runtime. No
        # downloader, remote start page, or external browser is invoked.
        webview.start(gui="edgechromium" if sys.platform == "win32" else None, debug=False, menu=menus)
        return 0
    except Exception:
        logging.exception("Desktop startup failed")
        show_error(
            "Loom Studio could not start.\n\n"
            "On Windows, Microsoft Edge WebView2 Runtime must already be installed. "
            "Your installer can include its offline installer.\n\n"
            f"Details: {data_dir / 'desktop.log'}"
        )
        return 1
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=12)
        if listener is not None:
            listener.close()
        if _instance_handle and sys.platform == "win32":
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_instance_handle))


if __name__ == "__main__":
    raise SystemExit(main())
