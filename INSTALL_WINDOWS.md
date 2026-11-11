# Windows desktop installer

The project includes a native Windows app and an installer build. This source
checkout does **not** contain a compiled or Windows-tested Setup.exe. Build on
Windows, or run the included GitHub Actions workflow to produce it. Building
does not publish anything or upload model weights.

## Using a built installer

1. Extract all installer files together, keeping every numbered `.bin` file next
   to **LoomStudio-Setup.exe**. Run **LoomStudio-Setup.exe** on Windows 10/11 x64. It installs into your user
   account and creates Start menu and desktop shortcuts; no Python installation
   or terminal is needed. Open **Loom Studio**.
2. Use the native **Models** menu to choose existing local image/video model
   folders, or paste their paths into **Settings** and save. The native menu
   saves selections through the local settings API. The app exposes no Python
   functions through a JavaScript API object.
3. For reasoning, run a local Ollama server with your installed local model.
   Use the same model tag in Settings. Start the server with
   `OLLAMA_NO_CLOUD=1`; Loom rejects cloud-backed model tags as well.
4. For spoken output, use **Models → Choose Piper voice file…**, or paste the
   path to an existing Piper `.onnx` voice file in Settings.
   Its matching `.onnx.json` configuration must be beside it. The desktop build
   includes Piper 1.3.0 and its CPU ONNX runtime, phonemizer and language data.
   Voice synthesis works offline without a GPU. Voice changing effects for
   uploaded recordings use FFmpeg and do not need a Piper model. Neural voice
   cloning or training a new speaker model is not included.

The app does not download AI models or use cloud inference. A one-click app
install does not supply model weights or install an Ollama server. To provision
a computer with no internet at all, transfer the installer, local model files,
Ollama installer/model store, and (if missing) the Microsoft WebView2 **offline
x64 standalone installer** on removable storage. Check the models' licenses.

Windows 11 normally has WebView2 already. The included Windows workflow bundles
Microsoft's signed offline x64 standalone installer, and Setup installs it only
when missing. A manual builder can also include that file; without it, Setup
stops with a clear message if the runtime is missing. The app never invokes
Microsoft's online bootstrapper.

An RTX 3060 with 32 GB system RAM is suitable for a modest quantized text model
and local images, running one generation at a time. VRAM varies by RTX 3060
variant. Local video generation is much slower and may exceed available VRAM;
image-to-video animation and regular editing use FFmpeg and work without a
generative video model. Keep expectations model-specific.

Personal files, settings, feedback and memory live at
`%LOCALAPPDATA%\LoomStudio`. Logs are in `desktop.log` there. Uninstall removes
the app and shortcuts but retains that data. Delete that folder yourself if you
also want to remove your personal data. Model folders you selected are never
deleted by the installer.

Model work currently cannot be safely canceled midway through GPU inference.
The desktop window stays open when a local job is running; let it finish before
closing. Download buttons use the native browser runtime's local save flow.

## Building the installer (developer or release builder)

The build also runs `packaging/build-source.py` to bundle the public source ZIP for the in-app Downloads page. It excludes personal data, model weights, build tools, and the release ZIP itself. The installed app can therefore offer its source and setup guide without internet access.

On Windows x64, install Python 3.11 x64 and Inno Setup 6. Put verified FFmpeg
and FFprobe Windows binaries in `packaging\tools\`, retaining their license
and source notices. Optionally put Microsoft's permitted-to-redistribute
`MicrosoftEdgeWebView2RuntimeInstallerX64.exe` in the same directory.

From PowerShell in the project folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build-windows.ps1
```

The script creates a separate build virtual environment, installs desktop and
local model engine dependencies, builds a self-contained Python app with
PyInstaller, then compiles **dist\installer\LoomStudio-Setup.exe** using Inno
Setup. A known matching PyTorch 2.6.0 / torchvision 0.21.0 CUDA 12.6 pair and
pinned Diffusers/Transformers engines are used, so the target machine needs a compatible
NVIDIA driver but does not need a CUDA developer toolkit. Building requires
internet or a pre-provisioned wheel cache; running the installed app does not.
The full installer can be multiple gigabytes because it includes local model
engines. Inno disk spanning avoids executable-size limits: **Setup.exe and all
adjacent numbered .bin files form the installer**. Keep them together when
copying or distributing it. Users still launch Setup once. A single physical
EXE is not promised for this large GPU build. It contains no user voice, language,
image or video model weights. Piper's bundled phonemizer data and small Arabic
diacritizer support model are included as library assets.
Allow roughly 20 GB of free space on the build machine for the environment,
packaged app and compressed installer; installed size depends on dependencies.

Use `-WithoutModelEngines` for a smaller editing/Ollama/Piper build. Such a build
cannot run Diffusers image/video generation, but retains the local voice engine.
Use `-SkipDependencyInstall` only
from an environment already containing the matching dependencies. You can pass
`-Python`, `-FFmpegDirectory` and `-InnoCompiler` to override tool locations.

Alternatively, put this project in a GitHub repository and run **Actions →
Build Windows installer → Run workflow**. Download the **LoomStudio-Windows-x64**
artifact after it succeeds. The workflow builds on Windows; it does not publish
a release or upload local models. Review third-party license/source obligations
before distributing the resulting installer. Dependency ranges and the current
FFmpeg release are used for this starter build; lock exact versions and archive
inputs when preparing a repeatable production release. The inference engines
are pinned, but core/transitive dependency ranges and current Microsoft/FFmpeg
installer inputs still need a release lock/archive for exact reproducibility.

## Release verification

Before calling an installer ready to share, test on a clean Windows 10/11 x64
machine with networking disabled: install, launch, choose model folders, edit an
image, export a video, exercise installed models, close, reopen, and uninstall.
Verify memory/settings persist and that the process exits when the window closes.
The source can be checked on Linux, but that cannot verify a Windows binary,
WebView2, CUDA drivers or a complete installer. The installer is unsigned until
a release builder signs it; do not claim SmartScreen reputation or a signed
publisher for this starter build.
