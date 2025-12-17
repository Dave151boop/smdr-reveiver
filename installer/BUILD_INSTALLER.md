# Building the SMDR Receiver Installer

This guide explains how to build the Windows installer for the SMDR Receiver service.

## Prerequisites

1. **Python and Dependencies**
   ```bash
   pip install pyinstaller
   pip install pywin32
   pip install PySide6
   ```

2. **Inno Setup**
   - Download and install from: https://jrsoftware.org/isinfo.php
   - Version 6.0 or later recommended

3. **Create License File**
   - Create `LICENSE.txt` in the project root if it doesn't exist

## Build Steps

### Step 1: Build the Executables

Build both the service and viewer executables:

```bash
# Build the service executable (include pywin32 timezone module)
pyinstaller --onefile --name SMDRService smdr_service.py --hidden-import win32timezone

# Build the viewer executable  
pyinstaller --onefile --windowed --name SMDRViewer smdr_viewer.py --icon resources/icon.ico
```

This creates:
- `dist/SMDRService.exe` - The Windows service
- `dist/SMDRViewer.exe` - The viewer application

### Step 2: Prepare Resources

Ensure these files exist:
- `resources/icon.ico` - Application icon
- `LICENSE.txt` - License file
- `README-SERVICE.md` - Documentation

### Step 3: Build the Installer

1. Open Inno Setup Compiler

2. Load the script:
   - File → Open
   - Select `installer/smdr_setup.iss`

3. Compile:
   - Build → Compile
   - Or press Ctrl+F9

4. The installer will be created in:
   - `installer/output/SMDRReceiver_Setup.exe`

## Installer Features

The installer includes:

### Installation Options

1. **Full Installation** (default)
   - SMDR Service (receives and logs data)
   - SMDR Viewer (displays data)

2. **Viewer Only**
   - Just the viewer application
   - For viewing data from a remote service

### Configuration During Installation

The installer prompts for:

1. **Port Number** (default: 7004)
   - The port the service listens on for SMDR data
   - Range: 1-65535

2. **Log File Location** (default: C:\ProgramData\SMDR Receiver\smdr.log)
   - Where the service saves logged data
   - Can be changed later via the viewer

### Additional Options

- **Desktop Icon**: Create shortcut on desktop
- **Auto-start**: Configure service to start with Windows

## Post-Installation

After installation:

1. **Service is automatically started**
   - Listening on the configured port
   - Logging to the configured file

2. **Launch the Viewer**
   - Start Menu → SMDR Receiver → SMDR Receiver Viewer
   - Or use desktop shortcut if created

3. **Configure Service** (if needed)
   - Open viewer
   - Service → Configuration
   - Change port or log file location
   - Service will restart automatically

## Uninstallation

The uninstaller will:
1. Stop the SMDR service
2. Remove the service registration
3. Remove all installed files
4. Keep log files (manual deletion required if desired)

## Troubleshooting Build Issues

### PyInstaller Issues

If PyInstaller fails to build:
```bash
# Clean and rebuild
pyinstaller --clean --onefile --name SMDRService smdr_service.py
```

### Missing Dependencies

If the executable fails to run:
```bash
# Check for missing DLLs
# Add to spec file: hiddenimports=['module_name']
```

### Icon Issues

If icon doesn't appear:
```bash
# Ensure icon.ico exists and is valid
# Use 256x256 or multiple sizes (16, 32, 48, 256)
```

### Service Registration Fails

If service won't install:
- Run installer as Administrator
- Check Windows Event Viewer for errors
- Verify pywin32 is properly installed

### Debugging the Service

You can run the service executable in debug (console) mode to see logs directly:

```bat
cd dist
SMDRService.exe debug
```

Common issues in debug mode:
- Missing config: ensure `smdr_config.json` exists next to the EXE or in Program Files folder
- Log path permissions: choose a writable location (e.g., `C:\\ProgramData\\SMDR Receiver\\smdr.log`)
- Port in use: change port in config and restart service

## Testing the Installer

Before distribution:

1. **Test on clean VM**
   - Windows 10/11 without Python
   - Verify all features work

2. **Test both install types**
   - Full installation
   - Viewer-only installation

3. **Test configuration changes**
   - Change port via viewer
   - Change log location
   - Verify service restarts

4. **Test uninstallation**
   - Complete removal
   - Service properly removed

## Distribution

The final installer:
- `installer/output/SMDRReceiver_Setup.exe`
- Single file, ~50-100 MB
- No prerequisites required
- Silent install supported: `/SILENT` or `/VERYSILENT`

## Advanced: Silent Installation

For deployment scripts:

```cmd
REM Silent install with defaults
SMDRReceiver_Setup.exe /SILENT

REM Silent with custom parameters
SMDRReceiver_Setup.exe /SILENT /PORT=7005 /LOGFILE="D:\Logs\smdr.log"

REM Very silent (no progress window)
SMDRReceiver_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES
```

## Version Updates

When releasing new versions:

1. Update version in `installer/smdr_setup.iss`:
   ```pascal
   #define MyAppVersion "2.1"
   ```

2. Rebuild executables

3. Recompile installer

4. Test upgrade installation
