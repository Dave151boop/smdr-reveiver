# SMDR Receiver Windows Service Package

Complete Windows installer package for the SMDR Receiver service-based application.

## Package Contents

### Core Components

1. **SMDR Service** (`smdr_service.py`)
   - Windows service that runs in background
   - Receives SMDR data via TCP
   - Logs continuously to file
   - Configurable port and log location

2. **SMDR Viewer** (`smdr_viewer.py`)
   - GUI application for viewing logged data
   - Real-time updates as data arrives
   - Search, filter, and export capabilities
   - Service configuration and management

3. **Configuration System** (`smdr/config.py`)
   - JSON-based configuration
   - Port and log file settings
   - Persistent across restarts

### Installer

**Inno Setup Script** (`installer/smdr_setup.iss`)
- Professional Windows installer
- Prompts for port and log file during installation
- Automatically installs and starts service
- Creates shortcuts and uninstaller
- Admin privileges required

### Build System

**Build Script** (`build_installer.bat`)
- Automated build process
- Builds both executables with PyInstaller
- Compiles installer with Inno Setup
- One-click build solution

### Documentation

- **BUILD_INSTALLER.md** - Developer guide for building installer
- **QUICK_START.md** - End user installation and usage guide
- **README-SERVICE.md** - Technical documentation
- **LICENSE.txt** - Software license

## Key Features

### Installation Features

✓ **Interactive Configuration**
- Prompts for port number (1-65535)
- Prompts for log file location
- Validates input during installation

✓ **Flexible Installation**
- Full: Service + Viewer
- Viewer Only: For remote viewing

✓ **Auto-Configuration**
- Service automatically installed
- Service automatically started
- Optional auto-start with Windows

### Runtime Features

✓ **Service Management from Viewer**
- View current configuration
- Change port and log file
- Restart service when config changes
- Check service status

✓ **Continuous Logging**
- Service runs independently
- Logs even when viewer closed
- Never loses data
- Configurable log location

✓ **Real-Time Viewing**
- Automatic updates as data arrives
- Multiple viewers supported
- Search across all data
- Export to CSV

## Building the Installer

### Prerequisites

```bash
pip install pyinstaller pywin32 PySide6
```

Install Inno Setup from: https://jrsoftware.org/isinfo.php

### Build Steps

**Option 1: Automated Build**
```bash
build_installer.bat
```

**Option 2: Manual Build**
```bash
# Build service
pyinstaller --onefile --name SMDRService smdr_service.py

# Build viewer
pyinstaller --onefile --windowed --name SMDRViewer smdr_viewer.py --icon resources/icon.ico

# Compile installer (open in Inno Setup)
installer/smdr_setup.iss
```

**Output:**
- `dist/SMDRService.exe` - Service executable
- `dist/SMDRViewer.exe` - Viewer executable
- `installer/output/SMDRReceiver_Setup.exe` - Final installer

## Installation Flow

1. **User runs installer**
2. **Installer prompts for:**
   - Installation type (Full/Viewer Only)
   - Port number (if service selected)
   - Log file location (if service selected)
   - Auto-start option
3. **Installer:**
   - Copies files to Program Files
   - Creates configuration file
   - Registers Windows service
   - Starts service
   - Creates Start Menu shortcuts
4. **User launches viewer**
5. **Viewer displays incoming data**

## Configuration Management

### Initial Configuration (Install Time)

Set during installation via prompts:
```json
{
    "port": 7004,
    "log_file": "C:\\ProgramData\\SMDR Receiver\\smdr.log",
    "auto_start": true
}
```

### Runtime Configuration Changes

Via Viewer → Service → Configuration:
1. User changes port or log file
2. Configuration saved to `smdr_config.json`
3. Service automatically restarted
4. Viewer reloads with new settings

### Configuration File Location

Checked in order:
1. Current directory
2. `C:\Program Files\SMDR Receiver\`
3. `%LOCALAPPDATA%\SMDR Receiver\`

## Service Management

### From Viewer

- **Service → Configuration** - Change settings
- **Service → Restart Service** - Restart service
- **Service → Service Status** - Check if running

### From Windows

- **services.msc** - Windows Services Manager
- **sc query SMDRReceiver** - Command line status
- **net start/stop SMDRReceiver** - Command line control

### Event Logging

Service logs to Windows Event Log:
- Application Log → Source: SMDRReceiver
- Startup/shutdown events
- Error messages
- Configuration changes

## Deployment Scenarios

### Single Computer

Install full package:
- Service receives and logs data
- Viewer displays data locally
- Both on same machine

### Multiple Viewers

Install full on server:
- Service runs on server
- Share log file directory

Install viewer-only on clients:
- Each client can view same data
- Open shared log file path
- Real-time updates for all

### Remote Phone System

Install full on network-accessible server:
- Configure phone system to send to server IP:port
- Install viewer-only on admin workstations
- Central logging with distributed viewing

## Distribution

### Single-File Installer

`SMDRReceiver_Setup.exe` (~50-100 MB)
- No prerequisites required
- Self-contained
- All dependencies included

### Silent Installation

For deployment systems:

```cmd
SMDRReceiver_Setup.exe /SILENT /COMPONENTS="service,viewer" /PORT=7004
```

### Network Distribution

Share installer on network:
```
\\server\software\SMDRReceiver_Setup.exe
```

Group Policy or deployment tool can push installation.

## Support and Troubleshooting

### Common Issues

**Service won't start**
- Check port not in use
- Verify log directory writable
- Check Event Viewer for errors

**No data appearing**
- Verify phone system configured correctly
- Check firewall allows port
- Test with telnet: `telnet <ip> <port>`

**Can't change configuration**
- Run viewer as Administrator
- Check service is stopped before changes
- Verify write permissions on config file

### Log Files

**Service Log** (configurable location)
- All received SMDR data
- Timestamped entries
- Never automatically deleted

**Event Log** (Windows Event Viewer)
- Service lifecycle events
- Errors and warnings
- Configuration changes

## Updating

### Version Updates

1. Build new executables with updated code
2. Update version in `smdr_setup.iss`
3. Rebuild installer
4. Distribute new installer

### Upgrade Installation

Running new installer over old:
- Service automatically stopped
- Files updated
- Configuration preserved
- Service restarted with new version

## Uninstallation

Uninstaller:
1. Stops service
2. Removes service registration
3. Deletes program files
4. Removes shortcuts
5. **Keeps** log files and configuration

Manual cleanup if needed:
- Delete log files manually
- Remove configuration from ProgramData

## Security Considerations

### Service Account

Service runs as:
- **Local System** account (default)
- Full system privileges
- Can access network

Alternative: Configure to run as specific user account via Services MMC.

### Permissions Required

**Installation:**
- Administrator (to install service)

**Configuration Changes:**
- Administrator (to restart service)

**Viewing Only:**
- Standard user (read access to log file)

### Firewall

**Inbound port** must be open:
- Port specified during installation
- TCP protocol
- From phone system IP

Windows Firewall rule created automatically by installer.

## License

See LICENSE.txt - MIT License

## Credits

Service-based architecture provides:
- Reliable continuous logging
- No data loss
- Multiple simultaneous viewers
- Professional Windows service integration
- Easy deployment and management
