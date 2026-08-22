#if PREPROCVER < 0x06000000
  #error Stage 19.1 requires Inno Setup 6.x.
#endif
#if PREPROCVER >= 0x07000000
  #error Stage 19.1 requires Inno Setup 6.x.
#endif

#ifndef BundleDir
  #error BundleDir must point at the validated Law-Rag onedir bundle.
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef MarkerFile
  #error MarkerFile must point at the Stage 19.1 installed-distribution marker.
#endif
#ifndef AppVersion
  #define AppVersion "0.8.0"
#endif
#ifndef ReleaseLabel
  #define ReleaseLabel "0.8.0-rc2"
#endif

[Setup]
AppId={{A4C6D7A1-4F8E-4E35-AB53-D19C4C06D58E}
AppName=Law-Rag
AppVersion={#AppVersion}
AppVerName=Law-Rag {#AppVersion}
AppPublisher=Law-Rag
DefaultDirName={localappdata}\Programs\Law-Rag
DefaultGroupName=Law-Rag
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir={#OutputDir}
OutputBaseFilename=Law-Rag-{#ReleaseLabel}-windows-x64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
Uninstallable=yes
CreateUninstallRegKey=yes
UninstallDisplayName=Law-Rag
UninstallDisplayIcon={app}\Law-Rag.exe
UsePreviousAppDir=yes
DirExistsWarning=no
CloseApplications=yes
RestartApplications=no
ChangesAssociations=no
ChangesEnvironment=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#MarkerFile}"; DestDir: "{app}"; DestName: ".law-rag-installed"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Law-Rag"; Filename: "{app}\Law-Rag.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Law-Rag"; Filename: "{app}\Law-Rag.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Law-Rag.exe"; Description: "Launch Law-Rag"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
