@echo off
REM Build script for SMDR Receiver Installer
REM This script builds the executables and creates the installer

echo ========================================
echo SMDR Receiver Build Script
echo ========================================
echo.

REM Check if running from correct directory
if not exist "smdr_service.py" (
    echo ERROR: Must run from SMDR project root directory
    pause
    exit /b 1
)

REM Step 1: Clean previous builds
echo Step 1: Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "installer\output" rmdir /s /q "installer\output"
echo Done.
echo.

REM Step 2: Build Service executable
echo Step 2: Building Service executable...
REM Include common hidden imports needed for pywin32 services
pyinstaller --onefile --name SMDRService smdr_service.py --hidden-import win32timezone --clean
if errorlevel 1 (
    echo ERROR: Failed to build service executable
    pause
    exit /b 1
)
echo Done.
echo.

REM Step 3: Build Viewer executable
echo Step 3: Building Viewer executable...
if exist "resources\icon.ico" (
    pyinstaller --onefile --windowed --name SMDRViewer smdr_viewer.py --icon resources\icon.ico --clean
) else (
    echo Warning: icon.ico not found, building without icon
    pyinstaller --onefile --windowed --name SMDRViewer smdr_viewer.py --clean
)
if errorlevel 1 (
    echo ERROR: Failed to build viewer executable
    pause
    exit /b 1
)
echo Done.
echo.

REM Step 4: Check for Inno Setup
echo Step 4: Checking for Inno Setup...
set INNO_PATH=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set INNO_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set INNO_PATH=C:\Program Files\Inno Setup 6\ISCC.exe

if "%INNO_PATH%"=="" (
    echo.
    echo Inno Setup not found. Please:
    echo 1. Install Inno Setup from https://jrsoftware.org/isinfo.php
    echo 2. Or manually compile installer\smdr_setup.iss with Inno Setup
    echo.
    echo Executables built successfully:
    echo - dist\SMDRService.exe
    echo - dist\SMDRViewer.exe
    pause
    exit /b 0
)
echo Found Inno Setup at: %INNO_PATH%
echo.

REM Step 5: Build installer
echo Step 5: Building installer with Inno Setup...
"%INNO_PATH%" "installer\smdr_setup.iss"
if errorlevel 1 (
    echo ERROR: Failed to build installer
    pause
    exit /b 1
)
echo Done.
echo.

echo ========================================
echo Build completed successfully!
echo ========================================
echo.
echo Outputs:
echo - Service: dist\SMDRService.exe
echo - Viewer: dist\SMDRViewer.exe
echo - Installer: installer\output\SMDRReceiver_Setup.exe
echo.
pause
