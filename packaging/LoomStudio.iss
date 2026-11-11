#define AppName "Loom Studio"
#define AppVersion "0.1.0"
#define AppExeName "LoomStudio.exe"
#define WebView2Installer AddBackslash(SourcePath) + "tools\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"

[Setup]
AppId={{52B911AF-D7EE-4BF3-9A70-E64756FDFE42}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Loom Studio
DefaultDirName={localappdata}\Programs\Loom Studio
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SourceDir=..
OutputDir=dist\installer
OutputBaseFilename=LoomStudio-Setup
; CUDA/PyTorch can exceed the practical size of a single PE executable. Keep
; numbered payload files beside Setup.exe; users still launch only Setup.exe.
DiskSpanning=yes
DiskSliceSize=2000000000
SlicesPerDisk=1
Compression=lzma2/fast
SolidCompression=yes
LZMANumBlockThreads=2
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
UninstallDisplayIcon={app}\{#AppExeName}
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Files]
#if FileExists(WebView2Installer)
; Keep prerequisites first: ExtractTemporaryFile would otherwise decompress the
; entire multi-gigabyte solid application block before installing WebView2.
Source: "{#WebView2Installer}"; Flags: dontcopy
#endif
Source: "dist\LoomStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Open {#AppName}"; Flags: nowait postinstall skipifsilent; Check: CanLaunchApp

[Code]
function HasWebView2At(Root: Integer; Key: String): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(Root, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0');
end;

function NeedsWebView2: Boolean;
var
  Key: String;
begin
  Key := 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := not (HasWebView2At(HKCU, Key) or HasWebView2At(HKLM32, Key) or HasWebView2At(HKLM64, Key));
end;

function CanLaunchApp: Boolean;
begin
  Result := not NeedsWebView2;
end;

#if FileExists(WebView2Installer)
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if not NeedsWebView2 then
    Exit;
  ExtractTemporaryFile('MicrosoftEdgeWebView2RuntimeInstallerX64.exe');
  if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'),
    '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Result := 'The bundled offline Microsoft WebView2 installer could not start. Retry Setup or install the offline x64 WebView2 runtime manually.';
    Exit;
  end;
  if (ResultCode <> 0) and (ResultCode <> 3010) then
  begin
    Result := 'Microsoft WebView2 installation failed (exit code ' + IntToStr(ResultCode) + '). Retry Setup after resolving the runtime installer error.';
    Exit;
  end;
  if ResultCode = 3010 then
    NeedsRestart := True;
  if NeedsWebView2 then
    Result := 'Microsoft WebView2 is still unavailable. Restart Windows if requested, then run Loom Studio Setup again.';
end;
#endif

function InitializeSetup: Boolean;
begin
  Result := True;
#if !FileExists(WebView2Installer)
  if NeedsWebView2 then
  begin
    MsgBox('Microsoft Edge WebView2 Runtime is required. Install its offline x64 standalone installer first, then run Loom Studio Setup again. Ask the installer provider to include it for a fully offline installation.', mbError, MB_OK);
    Result := False;
  end;
#endif
end;
