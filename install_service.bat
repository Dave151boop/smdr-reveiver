@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Resolve script directory for reliable relative paths
set "SCRIPT_DIR=%~dp0"

REM ============================================================
REM  SMDR Receiver - Service Install Script
REM  - Prompts for port and log file path
REM  - Copies service EXE to Program Files
REM  - Writes smdr_config.json
REM  - Adds Windows Firewall rule
REM  - Installs and starts the Windows service
REM  Requires: Administrator
REM ============================================================

REM Check Administrator privileges
>nul 2>&1 net session
if not %errorlevel%==0 (
  echo.
  echo ERROR: This script must be run as Administrator.
  echo Right-click the .bat and choose "Run as administrator".
  echo.
  pause
  exit /b 1
)

set "SERVICE_NAME=SMDRReceiver"
set "SERVICE_EXE=SMDRService.exe"
set "INSTALL_DIR=%ProgramFiles%\SMDR Receiver"
set "DEFAULT_PORT=7004"
set "DEFAULT_LOGDIR=%ProgramData%\SMDR Receiver"
set "DEFAULT_VIEWER_PORT=7010"
set "DEFAULT_SERVICE_HOST=localhost"

REM Locate the built service executable
set "SOURCE_SERVICE_EXE=%SCRIPT_DIR%dist\%SERVICE_EXE%"
set "SOURCE_VIEWER_EXE=%SCRIPT_DIR%dist\SMDRViewer.exe"
if not exist "%SOURCE_SERVICE_EXE%" (
  echo.
  echo ERROR: %SOURCE_SERVICE_EXE% not found.
  echo Please build the service first: pyinstaller --onefile --name SMDRService smdr_service.py
  echo Or run build_installer.bat
  echo.
  pause
  exit /b 1
)
if not exist "%SOURCE_VIEWER_EXE%" (
  echo.
  echo WARNING: %SOURCE_VIEWER_EXE% not found. Viewer will not be installed.
  echo Build the viewer: pyinstaller --onefile --name SMDRViewer smdr_viewer.py
  echo.
)

cls
echo ============================================
echo  SMDR Receiver - Service Installer
echo ============================================
echo.
echo Install directory: %INSTALL_DIR%

REM Prompt for port
set "PORT=%DEFAULT_PORT%"
set /p PORT=Enter port to listen on [%DEFAULT_PORT%]: 
if "%PORT%"=="" set "PORT=%DEFAULT_PORT%"

REM Prompt for log directory
set "LOGDIR=%DEFAULT_LOGDIR%"
set /p LOGDIR=Enter log directory [%DEFAULT_LOGDIR%]: 
if "%LOGDIR%"=="" set "LOGDIR=%DEFAULT_LOGDIR%"

REM Prompt for viewer broadcast port
set "VIEWER_PORT=%DEFAULT_VIEWER_PORT%"
set /p VIEWER_PORT=Enter viewer broadcast port [%DEFAULT_VIEWER_PORT%]: 
if "%VIEWER_PORT%"=="" set "VIEWER_PORT=%DEFAULT_VIEWER_PORT%"

REM Prompt for service host used by viewer
set "SERVICE_HOST=%DEFAULT_SERVICE_HOST%"
set /p SERVICE_HOST=Enter service host for viewer [%DEFAULT_SERVICE_HOST%]: 
if "%SERVICE_HOST%"=="" set "SERVICE_HOST=%DEFAULT_SERVICE_HOST%"

REM Create install directory
if not exist "%INSTALL_DIR%" (
  mkdir "%INSTALL_DIR%" || (
    echo ERROR: Could not create %INSTALL_DIR%
    pause
    exit /b 1
  )
)

REM Copy service EXE
copy /y "%SOURCE_SERVICE_EXE%" "%INSTALL_DIR%\%SERVICE_EXE%" >nul || (
  echo ERROR: Failed to copy service executable.
  pause
  exit /b 1
)

REM Copy viewer EXE if available
if exist "%SOURCE_VIEWER_EXE%" (
  copy /y "%SOURCE_VIEWER_EXE%" "%INSTALL_DIR%\SMDRViewer.exe" >nul
)

REM Ensure log directory exists
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1

REM Write configuration JSON next to the EXE
set "CONFIG_FILE=%INSTALL_DIR%\smdr_config.json"
(
  echo {
  echo   "port": %PORT%,
  echo   "log_directory": "%LOGDIR:\=\\%",
  echo   "auto_start": true,
  echo   "viewer_port": %VIEWER_PORT%,
  echo   "service_host": "%SERVICE_HOST%"
  echo }
) > "%CONFIG_FILE%" || (
  echo ERROR: Failed to write configuration: %CONFIG_FILE%
  pause
  exit /b 1
)

echo.
echo Adding Windows Firewall rule for TCP %PORT% ...
netsh advfirewall firewall add rule name="SMDR Receiver (TCP %PORT%)" dir=in action=allow protocol=TCP localport=%PORT% >nul 2>&1

echo Adding Windows Firewall rule for viewer TCP %VIEWER_PORT% ...
netsh advfirewall firewall add rule name="SMDR Viewer Broadcast (TCP %VIEWER_PORT%)" dir=in action=allow protocol=TCP localport=%VIEWER_PORT% >nul 2>&1

echo.
echo Installing Windows service...
pushd "%INSTALL_DIR%"

REM Try to stop/remove existing service (ignore errors)
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorlevel%==0 (
  net stop "%SERVICE_NAME%" >nul 2>&1
  "%INSTALL_DIR%\%SERVICE_EXE%" remove >nul 2>&1
)

"%INSTALL_DIR%\%SERVICE_EXE%" install
if not %errorlevel%==0 (
  echo ERROR: Service install failed.
  popd
  pause
  exit /b 1
)

REM Set to auto-start
sc config "%SERVICE_NAME%" start= auto >nul 2>&1

echo Starting service...
net start "%SERVICE_NAME%"
if not %errorlevel%==0 (
  echo ERROR: Failed to start service. Try running:
  echo   SMDRService.exe debug
  echo to see detailed errors.
  popd
  pause
  exit /b 1
)

popd

echo.
echo ============================================
echo  Service installed and started successfully.
echo  Listening on port: %PORT%
echo  Logging to: %LOGPATH%
echo  Service name: %SERVICE_NAME%
echo  Executable: %INSTALL_DIR%\%SERVICE_EXE%
echo  Config: %CONFIG_FILE%
echo ============================================
echo.
pause
endlocal
