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
from collections import deque

from smdr.server import SMDRServer, FIELD_NAMES
from smdr.config import SMDRConfig


class ViewerBroadcastServer:
    """Lightweight TCP broadcaster for remote viewers.

    Clients connect and receive the same log lines the service writes locally.
    A small tail of the existing log is sent on connect so new viewers have
    immediate data without waiting for the next call.
    """

    def __init__(self, log_path: Path, host: str = "0.0.0.0", port: int = 7010):
        self.log_path = Path(log_path)
        self.host = host
        self.port = int(port)
        self._sock = None
        self._clients = []  # list of socket objects
        self._accept_thread = None
        self._running = threading.Event()
        self._lock = threading.Lock()

    def start(self):
        new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        new_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        new_sock.bind((self.host, self.port))
        new_sock.listen(5)
        self._sock = new_sock
        # save actual port (handles 0/ephemeral)
        self.port = self._sock.getsockname()[1]
        self._running.set()
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

    def stop(self):
        self._running.clear()
        try:
            if self._sock:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self._sock.close()
        finally:
            self._sock = None

        with self._lock:
            for conn in self._clients:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass
            self._clients.clear()

        if self._accept_thread and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=1.0)

    def broadcast(self, line: str):
        if not line:
            return
        data = (line if line.endswith("\n") else line + "\n").encode("utf-8", errors="replace")
        dead = []
        with self._lock:
            for conn in list(self._clients):
                try:
                    conn.sendall(data)
                except Exception:
                    dead.append(conn)
            # remove dead connections
            for conn in dead:
                try:
                    conn.close()
                except Exception:
                    pass
                try:
                    self._clients.remove(conn)
                except ValueError:
                    pass

    def _accept_loop(self):
        while self._running.is_set():
            try:
                conn, addr = self._sock.accept()
            except OSError:
                break
            # send a small tail so the viewer sees immediate data
            self._send_tail(conn)
            with self._lock:
                self._clients.append(conn)

    def _send_tail(self, conn):
        try:
            if not self.log_path.exists():
                return
            from collections import deque
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                last_lines = deque(f, maxlen=200)
            if not last_lines:
                return
            payload = "".join(last_lines).encode("utf-8", errors="replace")
            if payload:
                conn.sendall(payload)
        except Exception:
            # best-effort; ignore failures so the connection can still receive new data
            pass

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
        self.viewer_server = None
        self.data_queue = queue.Queue()
        
        # Load configuration
        self.config = SMDRConfig()
        self.port = self.config.get_port()
        self.viewer_port = self.config.get_viewer_port()
        self.log_dir = self.config.get_log_directory()
        self.log_path = self.config.get_current_log_file()
        self.bytes_received = 0
        self.last_date = datetime.now().date()
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        
    def SvcStop(self):
        """Called when the service is being stopped."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.running = False
        win32event.SetEvent(self.stop_event)
        if self.server:
            self.server.stop()
        if self.viewer_server:
            self.viewer_server.stop()
        
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

            # Start viewer broadcast server for remote clients
            try:
                self.viewer_server = ViewerBroadcastServer(
                    log_path=self.log_path,
                    port=self.viewer_port,
                )
                self.viewer_server.start()
            except Exception as e:
                servicemanager.LogErrorMsg(f"Viewer broadcast start failed on {self.viewer_port}: {e}")
                self.viewer_server = None
            
            servicemanager.LogInfoMsg(f"SMDR Receiver service started on port {self.port}")
            servicemanager.LogInfoMsg(f"Logging to: {self.log_dir}")
            servicemanager.LogInfoMsg(f"Current log file: {self.log_path.name}")
            servicemanager.LogInfoMsg(f"Viewer broadcast listening on: {self.viewer_port}")
            
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
            # Check if date changed; if so, update log_path to new day's file
            self._check_date_and_rotate()
            
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            for line in text.splitlines():
                if not line.strip():
                    continue
                    
                # Format the log entry
                log_entry = f"[{ts}] {addr[0]}:{addr[1]} {line}\n"
                
                # Write to current log file
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(log_entry)
                    
                self.bytes_received += len(log_entry)

                # Send to any connected viewers
                if self.viewer_server:
                    try:
                        self.viewer_server.broadcast(log_entry)
                    except Exception:
                        # Do not let viewer broadcast failures affect logging
                        pass
                 
        except Exception as e:
            servicemanager.LogErrorMsg(f"Error writing to log: {e}")

    def _check_date_and_rotate(self):
        """Check if date changed; if so, switch to new day's log file."""
        try:
            today = datetime.now().date()
            if today != self.last_date:
                self.last_date = today
                self.log_path = self.config.get_current_log_file()
                servicemanager.LogInfoMsg(f"Date changed - switched to new log file: {self.log_path.name}")
        except Exception as e:
            servicemanager.LogErrorMsg(f"Error checking date for rotation: {e}")


if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SMDRService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SMDRService)
