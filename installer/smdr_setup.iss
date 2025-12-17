; SMDR Receiver Service Installer
; Inno Setup Script
; Installs the SMDR service and viewer with configuration

#define MyAppName "SMDR Receiver"
#define MyAppVersion "2.0"
#define MyAppPublisher "Your Company"
#define MyAppURL "https://yourwebsite.com"
#define MyAppExeName "SMDRViewer.exe"
#define MyAppServiceExe "SMDRService.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE.txt
OutputDir=installer\output
OutputBaseFilename=SMDRReceiver_Setup
SetupIconFile=resources\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full"; Description: "Full installation (Service + Viewer)"
Name: "vieweronly"; Description: "Viewer only (for viewing data from another machine)"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "service"; Description: "SMDR Service (receives and logs data)"; Types: full; Flags: fixed
Name: "viewer"; Description: "SMDR Viewer (display application)"; Types: full vieweronly

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start service automatically with Windows"; GroupDescription: "Service Options:"; Components: service; Flags: checkedonce

[Files]
; Service files
Source: "dist\SMDRService.exe"; DestDir: "{app}"; Flags: ignoreversion; Components: service
Source: "smdr\*"; DestDir: "{app}\smdr"; Flags: ignoreversion recursesubdirs; Components: service

; Viewer files  
Source: "dist\SMDRViewer.exe"; DestDir: "{app}"; Flags: ignoreversion; Components: viewer

; Configuration and docs
Source: "README-SERVICE.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "resources\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName} Viewer"; Filename: "{app}\{#MyAppExeName}"; Components: viewer
Name: "{group}\Service Configuration"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--config"; Components: viewer
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName} Viewer"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Components: viewer

[Code]
var
  PortPage: TInputQueryWizardPage;
  LogFilePage: TInputQueryWizardPage;
  ConfigPort: Integer;
  ConfigLogFile: String;
  FirewallRuleName: String;

procedure InitializeWizard;
begin
  { Create custom page for port configuration }
  PortPage := CreateInputQueryPage(wpSelectComponents,
    'Service Configuration', 'Configure SMDR Service Settings',
    'Please specify the port number that the service will listen on for SMDR data.');
  PortPage.Add('Port (1-65535):', False);
  PortPage.Values[0] := '7004';

  { Create custom page for log file location }
  LogFilePage := CreateInputQueryPage(PortPage.ID,
    'Log File Location', 'Specify Log File Path',
    'Please specify where the service should save the SMDR log file.');
  LogFilePage.Add('Log file path:', False);
  LogFilePage.Values[0] := ExpandConstant('{commonappdata}\SMDR Receiver\smdr.log');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Port: Integer;
begin
  Result := True;
  
  if CurPageID = PortPage.ID then
  begin
    { Validate port number }
    if not TryStrToInt(PortPage.Values[0], Port) or (Port < 1) or (Port > 65535) then
    begin
      MsgBox('Please enter a valid port number between 1 and 65535.', mbError, MB_OK);
      Result := False;
    end
    else
    begin
      ConfigPort := Port;
    end;
  end
  else if CurPageID = LogFilePage.ID then
  begin
    { Validate log file path }
    if Trim(LogFilePage.Values[0]) = '' then
    begin
      MsgBox('Please specify a log file path.', mbError, MB_OK);
      Result := False;
    end
    else
    begin
      ConfigLogFile := LogFilePage.Values[0];
    end;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { Skip config pages if service component is not selected }
  Result := False;
  if (PageID = PortPage.ID) or (PageID = LogFilePage.ID) then
  begin
    Result := not IsComponentSelected('service');
  end;
end;

procedure CreateConfigFile();
var
  ConfigFile: String;
  ConfigContent: String;
  LogDir: String;
begin
  ConfigFile := ExpandConstant('{app}\smdr_config.json');
  
  { Create log directory if it doesn't exist }
  LogDir := ExtractFileDir(ConfigLogFile);
  if not DirExists(LogDir) then
    CreateDir(LogDir);
  
  { Create JSON configuration }
  ConfigContent := '{' + #13#10;
  ConfigContent := ConfigContent + '    "port": ' + IntToStr(ConfigPort) + ',' + #13#10;
  ConfigContent := ConfigContent + '    "log_file": "' + StringChangeEx(ConfigLogFile, '\', '\\', [rfReplaceAll]) + '",' + #13#10;
  ConfigContent := ConfigContent + '    "auto_start": true' + #13#10;
  ConfigContent := ConfigContent + '}';
  
  { Save to file }
  SaveStringToFile(ConfigFile, ConfigContent, False);
end;

procedure InstallService();
var
  ResultCode: Integer;
begin
  { Install the service }
  Exec(ExpandConstant('{app}\{#MyAppServiceExe}'), 'install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  
  { Configure auto-start if selected }
  if IsTaskSelected('autostart') then
  begin
    Exec('sc', 'config SMDRReceiver start= auto', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
  
  { Start the service }
  Exec('net', 'start SMDRReceiver', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure AddFirewallRule();
var
  ResultCode: Integer;
  Cmd: String;
begin
  FirewallRuleName := 'SMDR Receiver Service (TCP ' + IntToStr(ConfigPort) + ')';
  Cmd := 'advfirewall firewall add rule name="' + FirewallRuleName + '" dir=in action=allow protocol=TCP localport=' + IntToStr(ConfigPort);
  Exec('netsh', Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if IsComponentSelected('service') then
    begin
      { Create configuration file }
      CreateConfigFile();
      
      { Add inbound firewall rule for configured port }
      AddFirewallRule();

      { Install and start service }
      InstallService();
    end;
  end;
end;

procedure StopAndRemoveService();
var
  ResultCode: Integer;
begin
  { Stop the service }
  Exec('net', 'stop SMDRReceiver', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  
  { Remove the service }
  Exec(ExpandConstant('{app}\{#MyAppServiceExe}'), 'remove', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    { Stop and remove service before uninstalling files }
    if FileExists(ExpandConstant('{app}\{#MyAppServiceExe}')) then
    begin
      StopAndRemoveService();
    end;
  end;
end;

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')} Viewer}"; Flags: nowait postinstall skipifsilent; Components: viewer
