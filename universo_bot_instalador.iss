; Instalador profissional do Universo Bot
; Gere primeiro o aplicativo com compilar_instalador_universo_bot.bat.

#define MyAppName "Universo Bot"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "Universo Bot"
#define MyAppExeName "Universo Bot.exe"
#define BuildDir "dist_installer_app\Universo Bot"

[Setup]
AppId={{8A72E1F6-4C3B-4E4A-9F4D-7C7A0D4F2B31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=instalador
OutputBaseFilename=UniversoBot-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=UniBotLogo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x86 x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Executar o {#MyAppName}"; Flags: nowait postinstall skipifsilent
