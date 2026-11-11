# What is in this download

This archive contains the runnable **Loom Local AI Studio source project**, tests, screenshots, and Windows desktop/installer build files.

It is **not a Windows Setup.exe**, a pretrained AI model, or a bundle of model weights.

Included:

- Offline multi-agent task workflows, local model adapters, memory, and learned task routing.
- Image/video editing, audio cleanup, voice pitch/speed changes, and media conversion.
- Optional local Piper voice synthesis and local image/video/text model integrations.
- Transparent WebM animations for OBS and playable HTML5 game projects.
- Downloadable program source snippets from local-model Task results.
- Windows desktop shell, installer script, and Windows CI build workflow.

Still required for an install-ready Windows product:

1. Build the installer on Windows and verify it on Windows with the target GPU.
2. Supply local model weights and, for text inference, a local Ollama installation/model store.
3. Test actual model inference. This Linux environment had no installed neural models or GPU.

Not implemented: song/instrumental/sung-vocal generation, neural voice cloning, native executable game export, and automatic retraining of the large AI models. Learning in this version means opt-in memory and a supervised routing classifier.

Verification: **83 core tests and 10 desktop source tests passed**, including real media conversion and transparent-alpha decoding. Browser checks passed for the implemented workflows and responsive layouts. Model inference tests use mocks when model weights are absent; those do not prove quality or GPU performance.

Start with [README.md](README.md). Windows builders should read [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md).
