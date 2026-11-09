; Instalador de Anuiki (Inno Setup 6)
#define AppName "Anuiki"
; La versión llega desde scripts/build.ps1 (/DAppVersion=...); valor por defecto:
#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#define AppExe "Anuiki.exe"
#define Root ".."

[Setup]
AppId={{C6BD9351-3890-411B-98F5-1A1D264C7CB5}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#Root}\dist\installer
OutputBaseFilename=Anuiki-Setup-{#AppVersion}
SetupIconFile={#Root}\app\assets\anuiki.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
AppMutex=Anuiki_SingleInstance_Mutex
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"
Name: "startup"; Description: "Iniciar Anuiki con Windows (queda oculto esperando Ctrl+Espacio)"; GroupDescription: "Opciones:"; Flags: unchecked

[Files]
Source: "{#Root}\dist\Anuiki\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "AVISOS.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Avisos y ayuda de {#AppName}"; Filename: "{app}\AVISOS.txt"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName} ahora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Modelo de voz descargado (~670 MB) y registro
Type: filesandordirs; Name: "{localappdata}\{#AppName}"

[Messages]
es.FinishedLabel=Anuiki se instaló correctamente.%n%nUso: pulsa Ctrl+Espacio en cualquier campo de texto para dictar, Espacio para terminar y escribir el texto, y Esc para cancelar u ocultar la barra. Los atajos se cambian en Configuración (icono de la bandeja).%n%nLa primera vez descargará el modelo de voz (~670 MB).%n%nPara anclarlo a la barra de tareas: Inicio > busca "Anuiki" > clic derecho > "Anclar a la barra de tareas".

[Code]
// "Iniciar con Windows" también puede activarse desde la configuración de la
// app (fuera del instalador): al desinstalar, borrar la entrada siempre.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#AppName}');
end;


