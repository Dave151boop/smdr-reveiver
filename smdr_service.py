"""
SMDR Service - Runs as a Windows service to continuously receive and log SMDR data.
The service runs in the background and logs all received data to a file.
Clients can connect to view the data without stopping the service.
"""
import sys
import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import time
import csv
import queue
import threading
from pathlib import Path
from io import StringIO
from datetime import datetime

from smdr.server import SMDRServer, FIELD_NAMES
from smdr.config import SMDRConfig

SERVICE_NAME = "SMDRReceiver"
SERVICE_DISPLAY_NAME = "SMDR Receiver Service"
SERVICE_DESCRIPTION = "Receives and logs SMDR call data from phone systems"


class SMDRService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = True
        self.server = None
        self.data_queue = queue.Queue()
        
        # Load configuration
        self.config = SMDRConfig()
        self.port = self.config.get_port()
        self.log_path = self.config.get_log_file()
        self.bytes_received = 0
        
    def SvcStop(self):
        """Called when the service is being stopped."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.running = False
        win32event.SetEvent(self.stop_event)
        if self.server:
            self.server.stop()
        
    def SvcDoRun(self):
        """Main service loop."""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        
        self.main()
        
    def main(self):
        """Main service logic."""
        try:
            # Start the SMDR server
            self.server = SMDRServer(on_data=self._on_data_received)
            self.server.start(self.port)
            
            servicemanager.LogInfoMsg(f"SMDR Receiver service started on port {self.port}")
            servicemanager.LogInfoMsg(f"Logging to: {self.log_path}")
            
            # Start data processing thread
            processor_thread = threading.Thread(target=self._process_queue, daemon=True)
            processor_thread.start()
            
            # Wait for stop signal
            while self.running:
                if win32event.WaitForSingleObject(self.stop_event, 1000) == win32event.WAIT_OBJECT_0:
                    break
                    
        except Exception as e:
            servicemanager.LogErrorMsg(f"Service error: {e}")
            self.SvcStop()
            
    def _on_data_received(self, text: str, addr):
        """Called when data is received from the server."""
        self.data_queue.put((text, addr))
        
    def _process_queue(self):
        """Process received data and write to log."""
        while self.running:
            try:
                if not self.data_queue.empty():
                    text, addr = self.data_queue.get(timeout=0.1)
                    self._log_data(text, addr)
            except queue.Empty:
                pass
            except Exception as e:
                servicemanager.LogErrorMsg(f"Error processing data: {e}")
            time.sleep(0.01)
                
    def _log_data(self, text: str, addr):
        """Log received data to file."""
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            for line in text.splitlines():
                if not line.strip():
                    continue
                    
                # Format the log entry
                log_entry = f"[{ts}] {addr[0]}:{addr[1]} {line}\n"
                
                # Write to log file
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(log_entry)
                    
                self.bytes_received += len(log_entry)
                
        except Exception as e:
            servicemanager.LogErrorMsg(f"Error writing to log: {e}")


if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SMDRService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SMDRService)
