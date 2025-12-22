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
        self.viewer_port = self.config.get_viewer_port()
        self.log_path = self.config.get_log_file()
        self.log_dir = self.log_path.parent if self.log_path.parent else Path.cwd()
        # Always write to dated files: SMDRdataMMDDYY.log in the configured directory
        self.log_prefix = "SMDRdata"
        self.bytes_received = 0
        # Viewer broadcast state
        self.viewer_sock = None
        self.viewer_clients = []  # list of sockets
        self.viewer_thread = None
        
    def SvcStop(self):
        """Called when the service is being stopped."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.running = False
        win32event.SetEvent(self.stop_event)
        if self.server:
            self.server.stop()
        self._stop_viewer_broadcast()
        
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

            # Start viewer broadcast socket
            self._start_viewer_broadcast()
            
            servicemanager.LogInfoMsg(f"SMDR Receiver service started on port {self.port}")
            servicemanager.LogInfoMsg(f"Logging to: {self._get_current_log_path()}")
            
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

                # Resolve dated log path e.g., SMDRdataMMDDYY.log
                log_path = self._get_current_log_path()

                # Write to log file
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(log_entry)

                # Track last path and bytes
                self.log_path = log_path
                self.bytes_received += len(log_entry)

                # Broadcast live to connected viewers
                self._broadcast_to_viewers(log_entry)
                
        except Exception as e:
            servicemanager.LogErrorMsg(f"Error writing to log: {e}")

    def _start_viewer_broadcast(self):
        """Start a TCP server to stream log lines to connected viewers."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", int(self.viewer_port)))
            sock.listen(5)
            self.viewer_sock = sock

            def accept_loop():
                while self.running:
                    try:
                        conn, _ = sock.accept()
                        # Disable Nagle's algorithm for immediate sends
                        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        conn.setblocking(True)
                        self.viewer_clients.append(conn)
                    except OSError:
                        break
                    except Exception:
                        break

            self.viewer_thread = threading.Thread(target=accept_loop, daemon=True)
            self.viewer_thread.start()
            servicemanager.LogInfoMsg(f"Viewer broadcast listening on port {self.viewer_port}")
        except Exception as e:
            servicemanager.LogErrorMsg(f"Could not start viewer broadcast on port {self.viewer_port}: {e}")
            try:
                if self.viewer_sock:
                    self.viewer_sock.close()
            except Exception:
                pass
            self.viewer_sock = None

    def _stop_viewer_broadcast(self):
        """Stop viewer broadcast server and close client sockets."""
        try:
            if self.viewer_sock:
                try:
                    self.viewer_sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self.viewer_sock.close()
        except Exception:
            pass
        self.viewer_sock = None

        # Close clients
        dead = list(self.viewer_clients)
        for conn in dead:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
        self.viewer_clients = []

        # Join accept thread
        try:
            if self.viewer_thread and self.viewer_thread.is_alive():
                self.viewer_thread.join(timeout=1.0)
        except Exception:
            pass
        self.viewer_thread = None

    def _broadcast_to_viewers(self, text: str):
        """Send a log line to all connected viewer clients."""
        data = text.encode("utf-8", errors="replace")
        dead = []
        for conn in list(self.viewer_clients):
            try:
                conn.sendall(data)
            except Exception:
                dead.append(conn)
        # Remove dead connections
        for conn in dead:
            try:
                self.viewer_clients.remove(conn)
            except ValueError:
                pass
            try:
                conn.close()
            except Exception:
                pass

    def _get_current_log_path(self) -> Path:
        """Return the current dated log path (SMDRdataMMDDYY.log)."""
        today = datetime.now().strftime("%m%d%y")
        return self.log_dir / f"{self.log_prefix}{today}.log"


if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SMDRService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SMDRService)
