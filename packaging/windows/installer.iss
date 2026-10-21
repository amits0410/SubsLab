#define MyAppName "SubsLab"
#ifndef MyAppVersion
  #error Build using scripts/build.ps1 -Installer to supply the application version.
#endif
#define MyAppExeName "SubsLab.exe"

[Setup]
AppId={{AA9C9CF0-B910-4DDB-B556-21070A1C62AB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=SubsLab
AppPublisherURL=https://github.com/amits0410/SubsLab
AppSupportURL=https://github.com/amits0410/SubsLab/issues
AppUpdatesURL=https://github.com/amits0410/SubsLab/releases/latest
WizardStyle=modern
DefaultDirName={autopf}\SubsLab
DefaultGroupName=SubsLab
OutputDir=..\..\dist
OutputBaseFilename=SubsLab-Setup
SetupIconFile=..\..\assets\subslab.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Files]
Source: "..\..\dist\SubsLab\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\SubsLab"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch SubsLab"; Flags: nowait postinstall skipifsilent
