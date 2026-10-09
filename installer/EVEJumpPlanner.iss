#define MyAppName "New Eden Command"
#ifndef MyAppVersion
  #define MyAppVersion "3.5.1"
#endif
#define MyAppExeName "EVE Jump Planner.exe"

[Setup]
AppId={{7D2A4780-BEEE-4B17-B1FC-6F73E21560C3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
; Keep the existing install path so v3.4.3 upgrades in place without moving user-facing runtime files.
DefaultDirName={localappdata}\Programs\EVE Jump Planner
DefaultGroupName=New Eden Command
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\releases
OutputBaseFilename=New_Eden_Command_Setup_v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\app\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoDescription=New Eden capital navigation, operations, logistics and character command center for EVE Online
SetupIconFile=..\assets\new_eden_command.ico
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[InstallDelete]
; v3.4.3 transitions from the old one-file layout to a reliable onedir runtime.
; Remove only the old root EXE; the Inno uninstaller and all user data are preserved.
Type: files; Name: "{app}\{#MyAppExeName}"
Type: files; Name: "{autoprograms}\EVE Jump Planner.lnk"
Type: files; Name: "{autodesktop}\EVE Jump Planner.lnk"

[Files]
Source: "..\dist\EVE Jump Planner\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\New Eden Command"; Filename: "{app}\app\{#MyAppExeName}"
Name: "{autodesktop}\New Eden Command"; Filename: "{app}\app\{#MyAppExeName}"; Tasks: desktopicon


[Registry]
; Associate .ejpupdate files with the installed planner so an update can be
; installed by double-clicking it in Explorer. Per-user registration matches
; the per-user installer and does not require administrator privileges.
Root: HKCU; Subkey: "Software\Classes\.ejpupdate"; ValueType: string; ValueData: "EVEJumpPlanner.Update"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\EVEJumpPlanner.Update"; ValueType: string; ValueData: "New Eden Command Update"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\EVEJumpPlanner.Update\DefaultIcon"; ValueType: string; ValueData: "{app}\app\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\EVEJumpPlanner.Update\shell\open\command"; ValueType: string; ValueData: """{app}\app\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\app\{#MyAppExeName}"; Description: "Launch New Eden Command"; Flags: nowait postinstall skipifsilent
