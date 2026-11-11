# What is in this download

This archive contains the runnable **Loom Local AI Studio source project**, tests, screenshots, and Windows desktop/installer build files.

It is **not a Windows Setup.exe**, a pretrained AI model, or a bundle of model weights. The compiled Windows installer is offered separately from the [Windows release](https://github.com/lindsayukmark-art/loom-local-ai-studio/releases/tag/v0.1.0).

Included:

- Offline multi-agent task workflows, local model adapters, memory, and learned task routing.
- Image/video editing, audio cleanup, voice pitch/speed changes, and media conversion.
- Optional local Piper voice synthesis and local image/video/text model integrations.
- Transparent WebM animations for OBS and playable HTML5 game projects.
- Downloadable program source snippets from local-model Task results.
- Windows desktop shell, installer script, and Windows CI build workflow.

Before model-assisted use:

1. Download all three installer files into one folder and run `LoomStudio-Setup.exe`.
2. Supply local model weights and, for text inference, a local Ollama installation/model store.
3. Test interactive desktop use and actual model inference on your PC. The Windows build runner had no installed neural model weights or GPU.

Not implemented: song/instrumental/sung-vocal generation, neural voice cloning, native executable game export, and automatic retraining of the large AI models. Learning in this version means opt-in memory and a supervised routing classifier.

Verification: **83 core tests, 10 desktop source tests, and 4 download tests passed**, including real media conversion and transparent-alpha decoding. Browser checks passed for the implemented workflows and responsive layouts. The installer also passed compilation, frozen native imports/startup, silent installation into a path containing spaces, installed FFmpeg/FFprobe checks, uninstall, and personal-data retention on a Windows Server 2025 runner. Interactive WebView2 use and actual model/GPU inference were not tested. Model inference tests use mocks when model weights are absent; those do not prove quality or GPU performance.

Start with [README.md](README.md). Windows builders should read [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md).
