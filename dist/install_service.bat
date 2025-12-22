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
set "DEFAULT_VIEWER_PORT=7010"
set "DEFAULT_LOG=%ProgramData%\SMDR Receiver\SMDRdata.log"

REM Locate the built service executable (script already sits in dist/)
set "SOURCE_EXE=%SCRIPT_DIR%%SERVICE_EXE%"
if not exist "%SOURCE_EXE%" (
  echo.
  echo ERROR: %SOURCE_EXE% not found.
  echo Please build the service first: pyinstaller --onefile --name SMDRService smdr_service.py
  echo Or run build_installer.bat
  echo.
  pause
  exit /b 1
)

cls
echo ============================================
echo  SMDR Receiver - Service Installer
echo ============================================
echo.
echo Install directory: %INSTALL_DIR%

REM Prompt for receiver port
set "PORT=%DEFAULT_PORT%"
set /p PORT=Enter port to listen on [%DEFAULT_PORT%]: 
if "%PORT%"=="" set "PORT=%DEFAULT_PORT%"

REM Prompt for viewer broadcast port
set "VIEWER_PORT=%DEFAULT_VIEWER_PORT%"
set /p VIEWER_PORT=Enter viewer broadcast port [%DEFAULT_VIEWER_PORT%]: 
if "%VIEWER_PORT%"=="" set "VIEWER_PORT=%DEFAULT_VIEWER_PORT%"

REM Prompt for log path
set "LOGPATH=%DEFAULT_LOG%"
set /p LOGPATH=Enter log file path [%DEFAULT_LOG%]: 
if "%LOGPATH%"=="" set "LOGPATH=%DEFAULT_LOG%"

REM Create install directory
if not exist "%INSTALL_DIR%" (
  mkdir "%INSTALL_DIR%" || (
    echo ERROR: Could not create %INSTALL_DIR%
    pause
    exit /b 1
  )
)

REM Copy service EXE
copy /y "%SOURCE_EXE%" "%INSTALL_DIR%\%SERVICE_EXE%" >nul || (
  echo ERROR: Failed to copy service executable.
  pause
  exit /b 1
)

REM Ensure log directory exists
for %%I in ("%LOGPATH%") do set "LOGDIR=%%~dpI"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1

REM Write configuration JSON next to the EXE
set "CONFIG_FILE=%INSTALL_DIR%\smdr_config.json"
(
  echo {
  echo   "port": %PORT%,
  echo   "viewer_port": %VIEWER_PORT%,
  echo   "log_file": "%LOGPATH:\=\\%",
  echo   "auto_start": true
  echo }
) > "%CONFIG_FILE%" || (
  echo ERROR: Failed to write configuration: %CONFIG_FILE%
  pause
  exit /b 1
)

echo.
echo Adding Windows Firewall rule for TCP %PORT% ...
netsh advfirewall firewall add rule name="SMDR Receiver (TCP %PORT%)" dir=in action=allow protocol=TCP localport=%PORT% >nul 2>&1

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
