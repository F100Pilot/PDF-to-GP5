; Installer of the Windows program (Inno Setup 6). Built by packaging\build_exe.py --installer,
; which passes the version (/DMyAppVersion=…, from app/__init__.py) after building dist\PDF-to-GP5.
; Per-user install (no administrator): %LOCALAPPDATA%\Programs\PDF-to-GP5. The songs and settings
; are not in the program folder, so installing a new version over it, or removing it, keeps them.

#ifndef MyAppVersion
  #error Pass the version: ISCC /DMyAppVersion=0.9.0 installer.iss
#endif
#define MyAppName "PDF to GP5"
#define MyAppExeName "PDF-to-GP5.exe"

[Setup]
AppId={{5DBE7FBB-5F71-4D34-838E-4C996538B249}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=F100Pilot
AppPublisherURL=https://github.com/F100Pilot/PDF-to-GP5
AppSupportURL=https://github.com/F100Pilot/PDF-to-GP5/issues
AppUpdatesURL=https://github.com/F100Pilot/PDF-to-GP5/releases
DefaultDirName={localappdata}\Programs\PDF-to-GP5
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=PDF-to-GP5-Setup
SetupIconFile=pdf-to-gp5.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; The files of the version installed before: a package removed since must not stay behind.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\PDF-to-GP5\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
