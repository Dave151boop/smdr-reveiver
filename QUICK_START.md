# SMDR Receiver - Quick Start Guide

## For End Users

### Installation

1. **Download** `SMDRReceiver_Setup.exe`

2. **Run the installer** (requires Administrator privileges)
   - Right-click → "Run as administrator"

3. **Choose installation type:**
   - **Full Installation** - Install both service and viewer (recommended)
   - **Viewer Only** - Just the viewer (for remote viewing)

4. **Configure the service:**
   - **Port**: Enter the port number your phone system sends SMDR data to (default: 7004)
   - **Log File**: Choose where to save the log file (default: C:\ProgramData\SMDR Receiver\smdr.log)

5. **Additional options:**
   - ☑ Create desktop icon
   - ☑ Start service automatically with Windows (recommended)

6. **Complete installation**
   - Service will start automatically
   - Launch the viewer to see incoming data

### Using the Viewer

#### Opening the Viewer

- **Start Menu**: SMDR Receiver → SMDR Receiver Viewer
- **Desktop**: Double-click SMDR Receiver Viewer icon (if created)

#### Viewing Data

The viewer automatically displays:
- All SMDR call records as they arrive
- Data in an easy-to-read table format
- Real-time updates

#### Searching

1. Enter search term in the search box at the top
2. Press Enter or click "Find Next"
3. Navigate through matches
4. Click "Clear" to reset search

#### Exporting Data

- **File → Export CSV** - Export all displayed records to a CSV file
- Can be opened in Excel or other spreadsheet applications

### Changing Configuration

If you need to change the port or log file location:

1. **Open the viewer**

2. **Service → Configuration**

3. **Change settings:**
   - Port number
   - Log file location

4. **Click OK**
   - Configuration is saved
   - Option to restart service immediately

5. **Confirm restart**
   - Service restarts with new settings
   - Viewer reloads with new log file

### Checking Service Status

1. **Open the viewer**

2. **Service → Service Status**
   - Shows if service is running or stopped
   - Displays current configuration
   - Shows detailed service information

### Restarting the Service

If the service needs to be restarted:

1. **Open the viewer**

2. **Service → Restart Service**
   - Requires Administrator privileges
   - Service stops and restarts automatically

Or use Windows Services:
1. Press Windows+R
2. Type `services.msc` and press Enter
3. Find "SMDR Receiver Service"
4. Right-click → Restart

### Troubleshooting

#### No data appearing

1. **Check service is running:**
   - Viewer → Service → Service Status
   - Should show "Running"

2. **Check port configuration:**
   - Verify phone system is sending to correct port
   - Check firewall isn't blocking the port

3. **Check phone system:**
   - Verify SMDR is enabled
   - Verify correct IP and port configured
   - Test connectivity: `telnet <server-ip> <port>`

#### Service won't start

1. **Check port availability:**
   - Another program might be using the port
   - Open Command Prompt as Administrator
   - Run: `netstat -ano | findstr :<port>`
   - Change port if needed (Service → Configuration)

2. **Check permissions:**
   - Log file directory must be writable
   - Service runs under Local System account

3. **Check Event Viewer:**
   - Windows+R → `eventvwr.msc`
   - Windows Logs → Application
   - Look for "SMDR" or "SMDRReceiver" errors

#### Can't change configuration

- **Run as Administrator:**
  - Right-click viewer shortcut
  - Select "Run as administrator"
  - Try changing configuration again

### Uninstallation

1. **Control Panel → Programs → Uninstall a program**

2. **Select "SMDR Receiver"**

3. **Click Uninstall**
   - Service is stopped and removed
   - All program files removed
   - Log files are kept (delete manually if desired)

### Log Files

Log files are stored at the location specified during installation (default: `C:\ProgramData\SMDR Receiver\smdr.log`).

**Log Format:**
```
[2025-12-17 14:30:45] 192.168.10.3:4808 2025/12/17 14:30:43,00:00:15,0,215,O,18004444444,918004444444,,0,1009508,0,E215,David Rahn,T9018,Line1
```

**Managing Log Files:**
- Logs grow continuously as calls are received
- Rotate/archive logs periodically
- Can clear viewer display without affecting log: File → Clear Display

### Multiple Viewers

You can run multiple viewers simultaneously:
- On the same computer
- On different computers (viewing same log file via network share)
- Each viewer operates independently
- Service continues regardless of viewers

### Advanced: Network Viewing

To view logs from another computer:

1. **Share the log file directory** on the service computer

2. **Map network drive** on viewer computer

3. **Install viewer-only** on viewer computer

4. **Open log file:**
   - Viewer → File → Open Log File
   - Browse to network location
   - Select the shared log file

### Support

For issues or questions:
- Check README-SERVICE.md for detailed documentation
- Review Event Viewer for service errors
- Check firewall and network settings

### Phone System Configuration

Configure your phone system to send SMDR data:
- **Protocol**: TCP/IP
- **Server IP**: IP address of computer running SMDR service
- **Port**: The port configured during installation (default: 7004)
- **Format**: CSV or raw (service accepts both)

Common phone systems:
- **Avaya IP Office**: Manager → System → Receptionist → SMDR Settings
- **Avaya Aura**: System Manager → Applications → SMDR
- **Cisco**: Call Manager → Service Parameters → CDR
- **Others**: Consult phone system documentation for "SMDR" or "CDR" output
