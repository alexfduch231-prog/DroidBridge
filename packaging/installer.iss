#ifndef PayloadDir
  #error PayloadDir must be supplied by build_windows.py
#endif
#ifndef ArtifactDir
  #error ArtifactDir must be supplied by build_windows.py
#endif
[Setup]
AppId={{C4DA7A3E-0382-4A31-A965-D81455D35B1E}
AppName=DroidBridge
AppVersion=1.0.5
AppPublisher=DroidBridge contributors
DefaultDirName={localappdata}\Programs\DroidBridge
DefaultGroupName=DroidBridge
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ArtifactDir}
OutputBaseFilename=DroidBridge-1.0.5-windows-x64-setup
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\DroidBridge.exe
CloseApplications=no
RestartApplications=no
[Languages]
Name: russian; MessagesFile: compiler:Languages\Russian.isl
Name: english; MessagesFile: compiler:Default.isl
[Tasks]
Name: desktopicon; Description: Создать ярлык на рабочем столе; Flags: unchecked
[Files]
Source: {#PayloadDir}\*; DestDir: {app}; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: {group}\DroidBridge; Filename: {app}\DroidBridge.exe
Name: {autodesktop}\DroidBridge; Filename: {app}\DroidBridge.exe; Tasks: desktopicon
; Deliberately no Run, services, autorun, firewall or runtime-data uninstall actions.
