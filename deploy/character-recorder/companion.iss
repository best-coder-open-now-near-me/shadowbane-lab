; Compile with /DAppSource=... /DAppExe=... /DOutputPath=... /DConnectionFile=...
#ifndef AppSource
  #error AppSource is required
#endif
#ifndef ConnectionFile
  #error A private report connection file is required
#endif
[Setup]
AppId={{59127429-81DE-4AE8-9BB7-4E58F7A39E09}
AppName=Shadowbane Companion
AppVersion=1.1.0
AppPublisher=Shadowbane Lab
DefaultDirName={localappdata}\Programs\ShadowbaneCompanion
DefaultGroupName=Shadowbane Companion
PrivilegesRequired=lowest
DisableDirPage=yes
DisableProgramGroupPage=yes
UsePreviousAppDir=no
OutputDir={#OutputPath}
OutputBaseFilename=ShadowbaneCompanion-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Shadowbane Companion
UninstallDisplayIcon={app}\ShadowbaneCompanion.exe
CloseApplications=yes
RestartApplications=no
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: checkedonce
[Files]
Source: "{#AppSource}\{#AppExe}"; DestDir: "{app}"; DestName: "ShadowbaneCompanion.exe"; Flags: ignoreversion
Source: "{#AppSource}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppSource}\build-info.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#AppSource}\character-recorder.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ConnectionFile}"; DestDir: "{app}"; DestName: "connection.json"; Flags: ignoreversion
[Icons]
Name: "{group}\Shadowbane Companion"; Filename: "{app}\ShadowbaneCompanion.exe"
Name: "{autodesktop}\Shadowbane Companion"; Filename: "{app}\ShadowbaneCompanion.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\ShadowbaneCompanion.exe"; Description: "Open Shadowbane Companion"; Flags: nowait postinstall skipifsilent
[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var Runtime: String;
begin
  Result := '';
  Runtime := ExpandConstant('{app}\_internal');
  if DirExists(Runtime) then begin
    if not FileExists(ExpandConstant('{app}\build-info.json')) then begin
      Result := 'The installation folder contains unknown files. Please contact the server owner.';
      exit;
    end;
    if not DelTree(Runtime, True, True, True) then
      Result := 'Please close Shadowbane Companion and try installing again.';
  end;
end;
// Captures and delivery receipts live outside {app}; uninstall never removes them.
