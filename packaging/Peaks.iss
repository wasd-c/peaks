; Peaks per-user Windows installer.
; Compile from the repository root with:
;   ISCC.exe /DMyAppVersion=0.1.0 packaging\Peaks.iss
; scripts/build.py invokes ISCC natively when --installer is requested.

#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif

#define MyAppName "Peaks"
#define MyAppPublisher "Peaks contributors"
#define MyAppExeName "Peaks.exe"

[Setup]
; This identifier must remain stable so Inno Setup upgrades the existing
; per-user installation instead of creating a second entry.
AppId={{8BFE8E35-4E4B-46DD-A4C5-3A7F34CBA6DB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableDirPage=yes
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Uninstallable=yes
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist\installer
OutputBaseFilename=Peaks-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=no
; Allow replacing files in an existing install without prompting for an
; ordinary upgrade. No user data is stored under {app}.
CloseApplications=force
RestartApplications=no
SetupLogging=yes
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Peaks Riot account companion
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startmenu"; Description: "Create a Start Menu shortcut"; GroupDescription: "Shortcuts:"

[Files]
; The frozen application is deliberately the only source tree copied here.
; Peaks stores its encrypted vault in {localappdata}\Peaks\Peaks, outside
; this install directory, so upgrades and uninstalls never remove user data.
Source: "..\dist\Peaks\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Comment: "{#MyAppName}"; Tasks: startmenu

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
