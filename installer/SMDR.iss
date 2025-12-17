; Inno Setup script to package SMDR and install it as a Windows Service using NSSM
; Requires Inno Setup installed (iscc.exe on PATH)

[Setup]
AppName=SMDR
AppVersion=0.1
DefaultDirName={pf}\SMDR
DisableProgramGroupPage=yes
OutputBaseFilename=SMDR-Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin

[Files]
; Main executable produced by PyInstaller
Source: "..\dist\SMDR.exe"; DestDir: "{app}"; Flags: ignoreversion
; Include resources so the app can run standalone with assets
Source: "..\resources\*"; DestDir: "{app}\resources"; Flags: ignoreversion recursesubdirs createallsubdirs
; Include a bundled NSSM binary (if present in tools/nssm). The build helper will download it if absent.
Source: "..\tools\nssm\nssm.exe"; DestDir: "{app}"; Flags: ignoreversion

[Run]
; Use NSSM to install the service so an arbitrary executable can run as a Windows Service
Filename: "{app}\nssm.exe"; Parameters: "install SMDR \"{app}\\SMDR.exe\""; Flags: runhidden waituntilterminated
Filename: "{app}\nssm.exe"; Parameters: "set SMDR DisplayName \"SMDR Service\""; Flags: runhidden waituntilterminated
Filename: "{app}\nssm.exe"; Parameters: "set SMDR Start SERVICE_AUTO_START"; Flags: runhidden waituntilterminated
Filename: "{app}\nssm.exe"; Parameters: "start SMDR"; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "{app}\nssm.exe"; Parameters: "stop SMDR"; Flags: runhidden waituntilterminated
Filename: "{app}\nssm.exe"; Parameters: "remove SMDR confirm"; Flags: runhidden waituntilterminated
