# SMDR Service Version

This version separates the SMDR receiver into two components:

## Components

### 1. SMDR Service (`smdr_service.py`)
- Runs as a Windows service in the background
- Continuously receives and logs SMDR data
- Continues logging even when no viewer is open
- Automatically starts with Windows (if configured)

### 2. SMDR Viewer (`smdr_viewer.py`)
- Lightweight client application
- Displays data from the service's log file in real-time
- Multiple viewers can be opened simultaneously
- Can be closed without affecting logging

## Installation

### Prerequisites
Install required packages:
```bash
pip install pywin32
pip install PySide6
```

### Install the Service

1. **Run as Administrator** - Open PowerShell or Command Prompt as Administrator

2. **Install the service:**
   ```bash
   python service_manager.py
   ```
   Then select option 1 to install

   Or directly:
   ```bash
   python smdr_service.py install
   ```

3. **Start the service:**
   From the service manager menu (option 2) or:
   ```bash
   python smdr_service.py start
   ```

4. **Configure the service** (optional):
   - Open Windows Services (services.msc)
   - Find "SMDR Receiver Service"
   - Set startup type to "Automatic" if you want it to start with Windows
   - Configure recovery options as needed

## Usage

### Managing the Service

Use the service manager utility:
```bash
python service_manager.py
```

Or use commands directly:
```bash
# Install
python smdr_service.py install

# Start
python smdr_service.py start

# Stop
python smdr_service.py stop

# Remove
python smdr_service.py remove

# Check status
sc query SMDRReceiver
```

### Viewing Data

Simply run the viewer application:
```bash
python smdr_viewer.py
```

The viewer will:
- Automatically load existing log data
- Update in real-time as new data arrives
- Allow searching through the data
- Export data to CSV

You can:
- Open multiple viewers simultaneously
- Close viewers without affecting the service
- Open log files from different locations

## Configuration

The service uses these defaults:
- **Port:** 7004
- **Log File:** smdr.log (in current directory)

To change configuration, edit `smdr_service.py` and restart the service.

## Log File Location

By default, the service creates `smdr.log` in its working directory (usually the directory where the service was installed from).

## Benefits of Service Architecture

1. **Continuous Operation:** Service runs independently of user sessions
2. **No Data Loss:** Logging continues even if viewer is closed
3. **Multiple Viewers:** Several people can view the same data
4. **Automatic Start:** Can be configured to start with Windows
5. **System Integration:** Managed through Windows Services
6. **Lightweight Viewer:** The viewer is fast and uses minimal resources

## Troubleshooting

### Service won't install
- Make sure you're running as Administrator
- Check that pywin32 is installed: `pip install pywin32`

### Service won't start
- Check Event Viewer (Windows Logs → Application) for error messages
- Verify port 7004 is not in use: `netstat -ano | findstr 7004`

### Viewer shows no data
- Verify the service is running: `sc query SMDRReceiver`
- Check that smdr.log exists and has data
- Make sure the viewer is looking at the correct log file

### Port conflicts
- Stop the service: `python smdr_service.py stop`
- Change the port in smdr_service.py
- Restart the service: `python smdr_service.py start`

## Building Executables

To build standalone executables:

```bash
# Build the service
pyinstaller --onefile --name SMDRService smdr_service.py --hidden-import win32timezone

# Build the viewer
pyinstaller --onefile --windowed --name SMDRViewer smdr_viewer.py
```

Note: The service executable must be installed using its own install command:
```bash
SMDRService.exe install
SMDRService.exe start
```

To troubleshoot start-up issues, you can run the service in debug mode to see console output:

```bat
SMDRService.exe debug
```
