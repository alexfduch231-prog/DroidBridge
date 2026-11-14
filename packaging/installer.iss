#ifndef PayloadDir
  #error PayloadDir must be supplied by build_windows.py
#endif
#ifndef IconFile
  #error IconFile must be supplied by build_windows.py
#endif
#ifndef ArtifactDir
  #error ArtifactDir must be supplied by build_windows.py
#endif
[Setup]
AppId={{C4DA7A3E-0382-4A31-A965-D81455D35B1E}
AppName=PConDistance
AppVersion=1.0.11
AppPublisher=PConDistance contributors
DefaultDirName={localappdata}\Programs\DroidBridge
DefaultGroupName=PConDistance
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ArtifactDir}
OutputBaseFilename=PConDistance-1.0.11-windows-x64-setup
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#IconFile}
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
Name: {userprograms}\PConDistance\PConDistance; Filename: {app}\DroidBridge.exe; IconFilename: {app}\_internal\assets\droidbridge.ico
Name: {autodesktop}\PConDistance; Filename: {app}\DroidBridge.exe; IconFilename: {app}\_internal\assets\droidbridge.ico; Tasks: desktopicon
; Deliberately no Run, services, autorun, firewall or runtime-data uninstall actions.

[InstallDelete]
Type: files; Name: {autodesktop}\DroidBridge.lnk
Type: files; Name: {userprograms}\DroidBridge\DroidBridge.lnk
