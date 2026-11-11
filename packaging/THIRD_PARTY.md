# Bundled components

The Windows application bundles the Python runtime, FastAPI, Uvicorn, HTTPX,
Pillow, pywebview, Piper TTS, ONNX Runtime and their dependencies. The full build additionally includes
PyTorch, Diffusers, Transformers, Accelerate, Safetensors, SentencePiece
and their dependencies. Their notices and package metadata are retained by the
packager. Check each dependency's current license before publishing a release.

Loom Studio is licensed under GNU GPL version 3 or later; see LICENSE and NOTICE.
Piper 1.3.0 is GPL-3.0-or-later software from
https://github.com/OHF-voice/piper1-gpl. Its Windows wheel contains the native
espeak-ng bridge and phonemizer data, plus a small Arabic diacritizer ONNX support
model; these library assets are retained by `--collect-all piper`. ONNX Runtime
is from https://github.com/microsoft/onnxruntime under the MIT license. No separate
legacy `piper_phonemize` package is required for this Piper release. Keep Piper's
COPYING and all bundled component notices, and provide corresponding source as
required by the GPL when distributing a binary release.

The Windows build also places Microsoft's x64 Visual C++ runtime DLLs beside the
frozen Python runtime so native ONNX/Piper dependencies can load without a
separate machine-wide runtime installation. The build takes only named CRT DLLs
from the builder's Visual Studio redistributable folder, an explicit
`-VCRuntimeDirectory`, or an installed official x64 redistributable. Microsoft's
redistribution license applies to those components. Retain the matching runtime
license with a release; see Microsoft's application-local runtime deployment
documentation: https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files.

FFmpeg and FFprobe are separate executables, used through a subprocess, from
the Gyan Windows essentials distribution: https://www.gyan.dev/ffmpeg/builds/.
Those builds are GPL-licensed; retain the archive's LICENSE/README and associated
source information with each distributed release. FFmpeg source is available at
https://ffmpeg.org/download.html#get-sources and corresponding build information
at https://www.gyan.dev/ffmpeg/builds/. Record the exact downloaded archive's
SHA256 and `ffmpeg -version` output for a release. A distribution of GPL binaries
must satisfy the applicable GPL source-provision obligations; a generic link
does not replace those obligations.

An optional Microsoft Edge WebView2 Runtime offline installer remains Microsoft's
software, subject to its separate redistribution terms. It is not downloaded by
the application. The build operator can place the x64 standalone installer at
packaging/tools/MicrosoftEdgeWebView2RuntimeInstallerX64.exe.

No user voice, image, video or language model weights are included in the source
project. The packaged Piper library's internal support data described above is
distinct from a user voice model. Model licenses are separate
from the application and vary by model. Only include weights you have permission
to redistribute. Do not include a personal Hugging Face cache or access token.
