#define AppName "DeepRake"
#define AppVersion "1.0.0"
#define AppExe "DeepRake.exe"

[Setup]
AppId=JonD.DeepRake.V1
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=JonD
DefaultDirName={localappdata}\Programs\DeepRake
DefaultGroupName=DeepRake
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\release
OutputBaseFilename=DeepRake_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE.txt

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
Source: "..\dist\DeepRake\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DeepRake"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\DeepRake"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch DeepRake"; Flags: nowait postinstall skipifsilent
