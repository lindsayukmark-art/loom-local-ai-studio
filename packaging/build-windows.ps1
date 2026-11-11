param(
    [string]$FFmpegDirectory = "$PSScriptRoot\tools",
    [string]$Python = "python",
    [string]$InnoCompiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    [string]$VCRuntimeDirectory = "",
    [switch]$SkipDependencyInstall,
    [switch]$WithoutModelEngines
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'Build this installer on Windows 10/11 x64.' }
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $ProjectRoot
try {
    foreach ($tool in @('ffmpeg.exe', 'ffprobe.exe')) {
        if (-not (Test-Path (Join-Path $FFmpegDirectory $tool))) {
            throw "Missing $tool. Extract the official FFmpeg Windows distribution into $FFmpegDirectory (or pass -FFmpegDirectory)."
        }
    }
    if (-not (Test-Path $InnoCompiler)) { throw "Inno Setup 6 compiler not found at $InnoCompiler." }
    & $Python -c "import struct; assert struct.calcsize('P') == 8, 'Use 64-bit Python to build this x64 app.'"
    if ($LASTEXITCODE -ne 0) { throw 'A working 64-bit Python installation is required.' }
    if (-not $SkipDependencyInstall) {
        & $Python -m venv .venv-build
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the build virtual environment.' }
        $Python = Join-Path $ProjectRoot '.venv-build\Scripts\python.exe'
        & $Python -m pip install --no-cache-dir --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
        & $Python -m pip install --no-cache-dir -r requirements-desktop.txt
        if ($LASTEXITCODE -ne 0) { throw 'Desktop dependency installation failed.' }
        if (-not $WithoutModelEngines) {
            & $Python -m pip install --no-cache-dir torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu126
            if ($LASTEXITCODE -ne 0) { throw 'CUDA PyTorch installation failed.' }
            & $Python -m pip install --no-cache-dir -r packaging/requirements-models.txt
            if ($LASTEXITCODE -ne 0) { throw 'Local model engine dependency installation failed.' }
        }
    }
    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Installed Python package dependencies are inconsistent.' }
    & $Python -c "from piper.voice import PiperVoice; from piper.phonemize_espeak import EspeakPhonemizer; import onnxruntime; assert 'CPUExecutionProvider' in onnxruntime.get_available_providers(); assert EspeakPhonemizer().phonemize('en-us','Offline voice ready.'); print('Local Piper voice engine and native phonemizer check passed')"
    if ($LASTEXITCODE -ne 0) { throw 'Local voice engine import/phonemizer check failed.' }
    if (-not $WithoutModelEngines) {
        & $Python -c "import os; os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'; import torch,torchvision; assert torch.__version__.split('+')[0]=='2.6.0'; assert torchvision.__version__.split('+')[0]=='0.21.0'; from diffusers import AutoPipelineForText2Image,AutoPipelineForImage2Image,TextToVideoSDPipeline,CogVideoXPipeline,CogVideoXImageToVideoPipeline; print('Local model engine import check passed')"
        if ($LASTEXITCODE -ne 0) { throw 'Local model engine import/version check failed.' }
    }
    & $Python packaging/build-source.py
    if ($LASTEXITCODE -ne 0) { throw 'Source download bundle build failed.' }
    # ONNX/Piper native modules need the Microsoft C++ runtime even when Python
    # itself works. Ship these DLLs app-locally so end users need no admin-level
    # VC++ redistributable install. Prefer the licensed Visual Studio redist
    # folder; a builder can explicitly provide an extracted official redist.
    if (-not $VCRuntimeDirectory) {
        $VSWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
        if (Test-Path $VSWhere) {
            $VSRoot = & $VSWhere -latest -products '*' -property installationPath
            if ($VSRoot) {
                $RedistRoot = Join-Path $VSRoot 'VC\Redist\MSVC'
                if (Test-Path $RedistRoot) {
                    $Candidates = Get-ChildItem $RedistRoot -Directory | Sort-Object Name -Descending | ForEach-Object {
                        Get-ChildItem (Join-Path $_.FullName 'x64') -Directory -Filter 'Microsoft.VC*.CRT' -ErrorAction SilentlyContinue
                    }
                    $Candidate = $Candidates | Select-Object -First 1
                    if ($Candidate) { $VCRuntimeDirectory = $Candidate.FullName }
                }
            }
        }
        if (-not $VCRuntimeDirectory) {
            # Also supports Windows/Wine builders that installed Microsoft's
            # official x64 VC++ redistributable without Visual Studio.
            $VCRuntimeDirectory = Join-Path $env:WINDIR 'System32'
        }
    }
    $RuntimeNames = @('msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','concrt140.dll',
        'msvcp140_1.dll','msvcp140_2.dll','msvcp140_atomic_wait.dll','msvcp140_codecvt_ids.dll',
        'vcruntime140_threads.dll')
    foreach ($RequiredRuntime in @('msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll')) {
        if (-not (Test-Path (Join-Path $VCRuntimeDirectory $RequiredRuntime))) {
            throw "Missing Microsoft x64 C++ runtime $RequiredRuntime. Install the official x64 VC++ redistributable on the build machine or provide -VCRuntimeDirectory with its app-local DLLs."
        }
    }
    $Arguments = @(
        '--noconfirm', '--clean', '--noupx', '--onedir', '--windowed', '--name', 'LoomStudio',
        '--add-data', 'studio/static;studio/static',
        '--add-data', 'packaging/THIRD_PARTY.md;.',
        '--add-data', 'INSTALL_WINDOWS.md;.',
        '--add-data', 'README.md;.',
        '--add-data', 'LICENSE;.',
        '--add-data', 'NOTICE;.',
        '--add-binary', "$(Join-Path $FFmpegDirectory 'ffmpeg.exe');bin",
        '--add-binary', "$(Join-Path $FFmpegDirectory 'ffprobe.exe');bin",
        '--collect-all', 'webview', '--collect-all', 'pythonnet',
        '--collect-all', 'piper', '--collect-all', 'onnxruntime',
        '--copy-metadata', 'piper-tts', '--copy-metadata', 'onnxruntime',
        '--hidden-import', 'uvicorn.logging', '--hidden-import', 'uvicorn.loops.auto',
        '--hidden-import', 'uvicorn.protocols.http.auto',
        '--hidden-import', 'uvicorn.protocols.websockets.auto',
        '--hidden-import', 'uvicorn.lifespan.on'
    )
    foreach ($RuntimeName in $RuntimeNames) {
        $RuntimePath = Join-Path $VCRuntimeDirectory $RuntimeName
        if (Test-Path $RuntimePath) { $Arguments += @('--add-binary', "$RuntimePath;.") }
    }
    if (-not $WithoutModelEngines) {
        foreach ($package in @('diffusers','transformers','accelerate','safetensors','tokenizers','huggingface_hub','sentencepiece','torchvision')) {
            $Arguments += @('--collect-all', $package)
        }
        foreach ($distribution in @('torch','torchvision','numpy','packaging','filelock','requests','tqdm','regex','PyYAML','Pillow','protobuf','scipy','psutil')) {
            $Arguments += @('--copy-metadata', $distribution)
        }
    }
    Get-ChildItem $FFmpegDirectory -File | Where-Object { $_.Name -match '^(LICENSE|README|ffmpeg-version|ffmpeg\.sha256)' } | ForEach-Object {
        $Arguments += @('--add-data', "$($_.FullName);third_party/ffmpeg")
    }
    $Arguments += 'desktop.py'
    & $Python -m PyInstaller @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    & $InnoCompiler packaging/LoomStudio.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
    Write-Host "Installer created: $ProjectRoot\dist\installer\LoomStudio-Setup.exe"
    Write-Host 'Test it on a clean Windows machine before distributing it.'
} finally {
    Pop-Location
}
