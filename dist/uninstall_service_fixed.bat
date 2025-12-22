@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM  SMDR Receiver - Service Uninstall Script
REM  - Stops the Windows service
REM  - Uninstalls/removes the service
REM  - Removes Windows Firewall rule
REM  - Optionally removes service files and configuration
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
set "CONFIG_FILE=%INSTALL_DIR%\smdr_config.json"
set "DATA_DIR=%ProgramData%\SMDR Receiver"

cls
echo ============================================
echo  SMDR Receiver - Service Uninstaller
echo ============================================
echo.

REM Check if service exists
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorlevel% neq 0 (
  echo Service "%SERVICE_NAME%" is not installed.
  echo.
)^n) else (
  echo Stopping service "%SERVICE_NAME%"...
  net stop "%SERVICE_NAME%" >nul 2>&1
  timeout /t 2 /nobreak >nul

  echo Uninstalling service "%SERVICE_NAME%"...
  if exist "%INSTALL_DIR%\%SERVICE_EXE%" (
    "%INSTALL_DIR%\%SERVICE_EXE%" remove >nul 2>&1
  ) else (
    sc delete "%SERVICE_NAME%" >nul 2>&1
  )
  
  if %errorlevel%==0 (
    echo Service uninstalled successfully.
  ) else (
    echo Warning: Service removal may have failed. Trying sc delete...
    sc delete "%SERVICE_NAME%" >nul 2>&1
  )
  echo.
)

REM Read port from config if it exists
set "PORT="
if exist "%CONFIG_FILE%" (
  for /f "tokens=2 delims=: " %%a in ('type "%CONFIG_FILE%" ^| findstr /i "port"') do (
    set "PORT_LINE=%%a"
    set "PORT=!PORT_LINE:~0,-1!"
  )
)

REM Remove firewall rules (try default port and configured port)
echo Removing Windows Firewall rules...
if defined PORT (
  netsh advfirewall firewall delete rule name="SMDR Receiver (TCP !PORT!)" >nul 2>&1
)
netsh advfirewall firewall delete rule name="SMDR Receiver (TCP 7004)" >nul 2>&1
echo.

REM Ask about removing files
set "REMOVE_FILES=N"
echo Do you want to remove the service files from:
echo   %INSTALL_DIR%
if exist "%DATA_DIR%" (
  echo   %DATA_DIR% (logs and data^)
)
echo.
set /p REMOVE_FILES=Remove files? (Y/N) [N]: 
if /i "%REMOVE_FILES%"=="Y" (
  echo.
  echo Removing service files...
  if exist "%INSTALL_DIR%" (
    rd /s /q "%INSTALL_DIR%" >nul 2>&1
    if exist "%INSTALL_DIR%" (
      echo Warning: Could not fully remove %INSTALL_DIR%
      echo Some files may be in use. Try rebooting and deleting manually.
    ) else (
      echo Removed: %INSTALL_DIR%
    )
  )
  
  if exist "%DATA_DIR%" (
    echo.
    set "REMOVE_DATA=N"
    echo This will delete all log files and data in:
    echo   %DATA_DIR%
    set /p REMOVE_DATA=Are you sure? (Y/N) [N]: 
    if /i "!REMOVE_DATA!"=="Y" (
      rd /s /q "%DATA_DIR%" >nul 2>&1
      if exist "%DATA_DIR%" (
        echo Warning: Could not fully remove %DATA_DIR%
      ) else (
        echo Removed: %DATA_DIR%
      )
    )
  )
`n) else (
  echo Service files kept. Manual removal:
  echo   del "%INSTALL_DIR%"
  if exist "%DATA_DIR%" echo   del "%DATA_DIR%"
)

echo.
echo ============================================
echo  Uninstall complete.
echo ============================================
echo.
pause
endlocal
