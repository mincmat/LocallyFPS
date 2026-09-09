#ifndef MyAppVersion
  #error MyAppVersion must be supplied with /DMyAppVersion=...
#endif
#ifndef SourceDir
  #error SourceDir must be supplied with /DSourceDir=...
#endif
#ifndef OutputDir
  #error OutputDir must be supplied with /DOutputDir=...
#endif
#ifndef SetupIcon
  #error SetupIcon must be supplied with /DSetupIcon=...
#endif

[Setup]
AppId={{3E944884-8917-48FC-9651-F4AFDD63C364}
AppName=LocallyFPS
AppVersion={#MyAppVersion}
AppPublisher=mincmat
AppPublisherURL=https://github.com/mincmat/LocallyFPS
AppSupportURL=https://github.com/mincmat/LocallyFPS/issues
AppUpdatesURL=https://github.com/mincmat/LocallyFPS/releases
DefaultDirName={localappdata}\Programs\LocallyFPS
DefaultGroupName=LocallyFPS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=LocallyFPS-v{#MyAppVersion}-windows-x64-setup
SetupIconFile={#SetupIcon}
UninstallDisplayIcon={app}\LocallyFPS.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ChangesAssociations=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\LocallyFPS"; Filename: "{app}\LocallyFPS.exe"
Name: "{autodesktop}\LocallyFPS"; Filename: "{app}\LocallyFPS.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Run]
Filename: "{app}\LocallyFPS.exe"; Description: "{cm:LaunchProgram,LocallyFPS}"; Flags: nowait postinstall skipifsilent
