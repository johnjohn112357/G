#define AppName "Woods Route Planner"
#define AppVersion "2.0.0"
#define AppPublisher "Woods Route Planner"
#define AppExeName "WoodsRoutePlanner.exe"

[Setup]
AppId={{9C3C9B8E-2E8B-4E1C-9DBA-7C03A6E6B44A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Woods Route Planner
DefaultGroupName={#AppName}
OutputDir=..\dist
OutputBaseFilename=WoodsRoutePlanner-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#AppExeName}

[Files]
Source: "..\dist\WoodsRoutePlanner.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Woods Route Planner"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Woods Route Planner"; Filename: "{app}\{#AppExeName}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Woods Route Planner"; Flags: postinstall nowait skipifsilent
