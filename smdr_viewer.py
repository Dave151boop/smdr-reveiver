"""
SMDR Viewer - Client application to view SMDR data logged by the service.
This is a lightweight viewer that reads the log file and displays it.
"""
import sys
import time
import socket
import threading
import random
from datetime import datetime, timedelta
from pathlib import Path
from PySide6.QtCore import QTimer, Qt, QFileSystemWatcher
from PySide6.QtGui import QAction, QColor, QPalette
from PySide6.QtWidgets import (
    QMainWindow,
    QApplication,
    QFileDialog,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QSpinBox,
    QDoubleSpinBox,
    QColorDialog,
)
import csv
from io import StringIO

from smdr.server import FIELD_NAMES
from smdr.config import SMDRConfig
import subprocess


class SMDRViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMDR Viewer (Service Client)")
        self.resize(900, 600)
        
        # Load configuration
        self.config = SMDRConfig()
        self._shading_color = '#eaf8ea'
        
        # Connection/file mode tracking
        self.connection_mode = "file"  # "file" or "network"

        # File tracking
        self.log_path = self.config.get_log_file()
        self.last_position = 0
        self.lines_displayed = 0

        # Network client state
        self._net_sock = None
        self._net_thread = None
        self._net_running = threading.Event()
        
        # Create UI
        self._create_ui()
        
        # File watcher to detect changes
        self.file_watcher = QFileSystemWatcher()
        if self.log_path.exists():
            self.file_watcher.addPath(str(self.log_path))
        self.file_watcher.fileChanged.connect(self._on_file_changed)
        
        # Timer to check for new data
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check_for_updates)
        self.timer.start(1000)  # Check every second
        
        # Load existing data
        self._load_existing_data()
        
    def _create_ui(self):
        """Create the user interface."""
        # Connection status header
        self.header_label = QLabel("Disconnected from SMDR Server")
        self.header_label.setStyleSheet("font-weight: bold; color: red;")
        # Table widget
        self.table = QTableWidget()
        self.table.setColumnCount(len(FIELD_NAMES))
        self.table.setHorizontalHeaderLabels([n.replace('_', ' ').title() for n in FIELD_NAMES])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self._apply_shading_color()
        
        # Green shading
        try:
            pal = self.table.palette()
            pal.setColor(QPalette.AlternateBase, QColor('#eaf8ea'))
            self.table.setPalette(pal)
        except Exception:
            pass
            
        # Search bar
        search_widget = QWidget()
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(0, 0, 0, 0)
        
        search_label = QLabel("Search:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search term...")
        self.search_input.returnPressed.connect(self._search_next)
        
        search_btn = QPushButton("Find Next")
        search_btn.clicked.connect(self._search_next)
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_search)
        
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_btn)
        search_layout.addWidget(clear_btn)
        
        self._search_matches = []
        self._current_search_index = -1
        
        # Status bar
        self.status = QLabel()
        
        # Layout
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.header_label)
        layout.addWidget(search_widget)
        layout.addWidget(self.table)
        layout.addWidget(self.status)
        self.setCentralWidget(central)
        
        # Menu
        file_menu = self.menuBar().addMenu("File")
        
        open_action = QAction("Open Log File...", self)
        open_action.triggered.connect(self._open_log_file)
        file_menu.addAction(open_action)
        
        export_action = QAction("Export CSV...", self)
        export_action.triggered.connect(self._export_csv)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        clear_action = QAction("Clear Display", self)
        clear_action.triggered.connect(self._clear_display)
        file_menu.addAction(clear_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = self.menuBar().addMenu("View")

        self._line_shading_action = QAction("Enable Line Shading", self, checkable=True)
        self._line_shading_action.setChecked(True)
        self._line_shading_action.triggered.connect(self._toggle_line_shading)
        view_menu.addAction(self._line_shading_action)

        shading_color_action = QAction("Shading Color...", self)
        shading_color_action.triggered.connect(self._choose_shading_color)
        view_menu.addAction(shading_color_action)
        
        # Service menu
        service_menu = self.menuBar().addMenu("Service")
        
        config_action = QAction("Configuration...", self)
        config_action.triggered.connect(self._show_config_dialog)
        service_menu.addAction(config_action)
        
        service_menu.addSeparator()
        
        connect_action = QAction("Connect to Service", self)
        connect_action.triggered.connect(self._start_network_client)
        service_menu.addAction(connect_action)

        disconnect_action = QAction("Disconnect", self)
        disconnect_action.triggered.connect(self._stop_network_client)
        service_menu.addAction(disconnect_action)

        service_menu.addSeparator()

        restart_action = QAction("Restart Service", self)
        restart_action.triggered.connect(self._restart_service)
        service_menu.addAction(restart_action)
        
        status_action = QAction("Service Status", self)
        status_action.triggered.connect(self._show_service_status)
        service_menu.addAction(status_action)

        # Help menu
        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        help_menu.addSeparator()
        debug_action = QAction("Debug - Send Test Data", self)
        debug_action.triggered.connect(self._show_debug_sender)
        help_menu.addAction(debug_action)
        
        self._update_status()
        
    def _load_existing_data(self):
        """Load existing data from log file."""
        if not self.log_path.exists():
            self.status.setText(f"Waiting for log file: {self.log_path}")
            return
            
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    self._process_line(line.strip())
            self.last_position = self.log_path.stat().st_size
            self._update_status()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not read log file: {e}")
            
    def _on_file_changed(self, path):
        """Called when the log file changes."""
        self._check_for_updates()
        
    def _check_for_updates(self):
        """Check for new data in the log file."""
        if self.connection_mode == "network":
            return  # network mode reads from socket
        if not self.log_path.exists():
            return
            
        try:
            current_size = self.log_path.stat().st_size
            if current_size > self.last_position:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    f.seek(self.last_position)
                    for line in f:
                        self._process_line(line.strip())
                self.last_position = current_size
                self._update_status()
        except Exception as e:
            pass  # File might be locked, try again later
            
    def _process_line(self, line):
        """Process a line from the log file."""
        if not line:
            return
            
        # Parse the log format: [timestamp] ip:port data
        try:
            # Extract the CSV data part (after the address)
            parts = line.split('] ', 1)
            if len(parts) < 2:
                return
            addr_and_data = parts[1].split(' ', 1)
            if len(addr_and_data) < 2:
                return
            csv_data = addr_and_data[1]
            
            # Parse CSV
            reader = csv.reader(StringIO(csv_data))
            parsed = next(reader, None)
            
            if parsed:
                self._add_table_row(parsed)
                self.lines_displayed += 1
        except Exception:
            pass  # Skip malformed lines
            
    def _add_table_row(self, parsed):
        """Add a row to the table."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col_index in range(len(FIELD_NAMES)):
            val = parsed[col_index] if col_index < len(parsed) else ''
            item = QTableWidgetItem(str(val))
            self.table.setItem(row, col_index, item)
            
    def _update_status(self):
        """Update the status bar."""
        state = (
            "Connected to SMDR Server"
            if self.connection_mode == "network"
            else f"LOG FILE: {self.log_path.name}"
        )
        self.status.setText(f"{state} — Lines displayed: {self.lines_displayed}")
        # Keep header in sync
        if self.connection_mode == "network":
            self.header_label.setText("Connected to SMDR Server")
            self.header_label.setStyleSheet("font-weight: bold; color: blue;")
        else:
            self.header_label.setText(f"LOG FILE: {self.log_path.name}")
            self.header_label.setStyleSheet("font-weight: bold; color: green;")
        
    def _open_log_file(self):
        """Open a different log file."""
        path, _ = QFileDialog.getOpenFileName(self, "Open Log File", str(Path.cwd()), "Log Files (*.log);;All Files (*.*)")
        if path:
            self.log_path = Path(path)
            self.last_position = 0
            self.lines_displayed = 0
            self.table.setRowCount(0)
            
            # Update file watcher
            self.file_watcher.removePaths(self.file_watcher.files())
            if self.log_path.exists():
                self.file_watcher.addPath(str(self.log_path))
            
            self._load_existing_data()
            
    def _export_csv(self):
        """Export displayed data to CSV."""
        if self.table.rowCount() == 0:
            QMessageBox.information(self, "No Data", "No data to export.")
            return
            
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "smdr_export.csv", "CSV Files (*.csv)")
        if path:
            try:
                with open(path, "w", newline='', encoding="utf-8") as f:
                    writer = csv.writer(f)
                    # Write headers
                    writer.writerow(FIELD_NAMES)
                    # Write rows
                    for row in range(self.table.rowCount()):
                        row_data = []
                        for col in range(self.table.columnCount()):
                            item = self.table.item(row, col)
                            row_data.append(item.text() if item else '')
                        writer.writerow(row_data)
                QMessageBox.information(self, "Success", f"Exported {self.table.rowCount()} rows to {path}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not export CSV: {e}")
                
    def _clear_display(self):
        """Clear the display (doesn't affect log file)."""
        reply = QMessageBox.question(self, "Clear Display", 
                                     "Clear the displayed data?\n(Log file will not be affected)",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.table.setRowCount(0)
            self.lines_displayed = 0
            self.last_position = self.log_path.stat().st_size if self.log_path.exists() else 0
            self._update_status()

    def _toggle_line_shading(self):
        """Toggle alternating row colors."""
        enabled = self._line_shading_action.isChecked()
        self.table.setAlternatingRowColors(enabled)
        if enabled:
            self._apply_shading_color()

    def _choose_shading_color(self):
        """Pick a custom shading color and apply it."""
        color = QColorDialog.getColor()
        if color.isValid():
            self._shading_color = color.name()
            self._apply_shading_color()

    def _apply_shading_color(self):
        """Apply the current shading color to the table alternate rows."""
        try:
            pal = self.table.palette()
            pal.setColor(QPalette.AlternateBase, QColor(self._shading_color))
            self.table.setPalette(pal)
        except Exception:
            pass

    def _show_about(self):
        """Show an About dialog."""
        about_text = (
            "SMDR Viewer\n\n"
            "Displays SMDR call data logged by the SMDR Receiver Service.\n"
            "Use the Service menu to view status, change configuration,\n"
            "or restart the service after changes.\n\n"
            "Provided without warranty or guarantee.\n"
            "Programmed by AI with guidance from an idiot who failed comp-sci 20+ years ago."
        )
        QMessageBox.about(self, "About SMDR Viewer", about_text)

    def _show_debug_sender(self):
        """Show dialog to send test SMDR data to the service."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Send Test SMDR Data")
        dialog.resize(420, 220)

        layout = QFormLayout(dialog)

        # Host input (default localhost)
        host_input = QLineEdit("localhost")
        layout.addRow("Target Host:", host_input)

        # Port input (default from config)
        port_input = QSpinBox()
        port_input.setRange(1, 65535)
        port_input.setValue(self.config.get_port())
        layout.addRow("Target Port:", port_input)

        # Record count input
        count_input = QSpinBox()
        count_input.setRange(1, 1000000)
        count_input.setValue(1000)
        count_input.setSingleStep(100)
        layout.addRow("Number of Records:", count_input)

        # Delay input
        delay_input = QDoubleSpinBox()
        delay_input.setRange(0, 10)
        delay_input.setValue(0.01)
        delay_input.setSingleStep(0.01)
        delay_input.setDecimals(3)
        layout.addRow("Delay (seconds):", delay_input)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.Accepted:
            host = host_input.text().strip() or "localhost"
            port = port_input.value()
            count = count_input.value()
            delay = delay_input.value()

            thread = threading.Thread(
                target=self._send_test_data,
                args=(host, port, count, delay),
                daemon=True,
            )
            thread.start()

            QMessageBox.information(
                self,
                "Test Data Sender",
                f"Sending {count} test records to {host}:{port} in the background.\n"
                f"Check the viewer to see them appear in the log."
            )

    def _send_test_data(self, host, port, count, delay):
        """Send test SMDR records (runs in background thread)."""
        try:
            with socket.create_connection((host, port), timeout=5) as sock:
                for i in range(count):
                    record = self._generate_smdr_record(i)
                    sock.sendall((record + "\n").encode("utf-8"))
                    if delay > 0:
                        time.sleep(delay)
        except Exception:
            # Avoid noisy GUI errors; viewing/log will reflect any issues
            pass

    def _generate_smdr_record(self, index):
        """Generate a realistic SMDR record matching the viewer's table columns."""
        now = datetime.now() - timedelta(seconds=random.randint(0, 3600))
        date_time = now.strftime("%Y/%m/%d %H:%M:%S")

        duration_secs = random.randint(3, 300)
        duration = f"00:{duration_secs//60:02d}:{duration_secs%60:02d}"

        extension = random.randint(200, 250)
        direction = random.choice(["I", "O"])

        if direction == "O":
            called = f"{random.randint(1000000000, 9999999999)}"
            dialed = f"9{called}"
        else:
            called = f"{random.randint(1000000000, 9999999999)}"
            dialed = called

        call_id = 1000000 + index
        names = ["John Smith", "Jane Doe", "David Rahn", "Alice Johnson", "Bob Williams"]
        name = random.choice(names)
        trunk = f"T{random.randint(9001, 9020)}"

        record = (
            f"{date_time},{duration},0,{extension},{direction},{called},{dialed},,0,{call_id},0,"
            f"E{extension},{name},{trunk},Line{index % 10}"
        )
        return record
            
    def _search_next(self):
        """Search for the next occurrence of the search term."""
        search_term = self.search_input.text().strip()
        if not search_term:
            return
        
        search_term_lower = search_term.lower()
        
        # If this is a new search, find all matches
        if not self._search_matches or self._search_matches[0][2] != search_term_lower:
            self._search_matches = []
            for row in range(self.table.rowCount()):
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    if item and search_term_lower in item.text().lower():
                        self._search_matches.append((row, col, search_term_lower))
            self._current_search_index = -1
        
        if not self._search_matches:
            self.status.setText(f"Log file: {self.log_path} — Lines displayed: {self.lines_displayed} — No matches found")
            return
        
        # Move to next match
        self._current_search_index = (self._current_search_index + 1) % len(self._search_matches)
        row, col, _ = self._search_matches[self._current_search_index]
        
        # Select and scroll to the match
        self.table.setCurrentCell(row, col)
        self.table.scrollToItem(self.table.item(row, col))
        
        # Update status
        self.status.setText(f"Log file: {self.log_path} — Lines displayed: {self.lines_displayed} — Match {self._current_search_index + 1} of {len(self._search_matches)}")
    
    def _clear_search(self):
        """Clear the search input and reset matches."""
        self.search_input.clear()
        self._search_matches = []
        self._current_search_index = -1
        self._update_status()
    
    def _show_config_dialog(self):
        """Show configuration dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Service Configuration")
        dialog.resize(500, 200)
        
        layout = QFormLayout(dialog)
        
        # Port (SMDR receiver port)
        port_input = QSpinBox()
        port_input.setRange(1, 65535)
        port_input.setValue(self.config.get_port())
        layout.addRow("Receiver Port:", port_input)

        # Viewer broadcast port
        viewer_port_input = QSpinBox()
        viewer_port_input.setRange(1, 65535)
        viewer_port_input.setValue(self.config.get_viewer_port())
        layout.addRow("Viewer Port:", viewer_port_input)

        # Service host for viewer
        host_input = QLineEdit(self.config.get_service_host())
        layout.addRow("Service Host:", host_input)
        
        # Log file
        log_widget = QWidget()
        log_layout = QHBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        
        log_input = QLineEdit(str(self.config.get_log_file()))
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_log_file(log_input))
        
        log_layout.addWidget(log_input)
        log_layout.addWidget(browse_btn)
        layout.addRow("Log File:", log_widget)
        
        # Info label
        info_label = QLabel(
            "Note: Changing these settings requires restarting the service.\n"
            "The service will be automatically restarted when you click OK.\n"
            "You must run this viewer as Administrator to save and restart the service."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 9pt;")
        layout.addRow(info_label)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        restart_btn = QPushButton("Save && Restart Service")
        buttons.addButton(restart_btn, QDialogButtonBox.AcceptRole)

        # Track whether restart was explicitly requested
        dialog._restart_requested = False

        def on_clicked(btn):
            if btn == restart_btn:
                dialog._restart_requested = True
                dialog.accept()

        buttons.clicked.connect(on_clicked)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.Accepted:
            new_port = port_input.value()
            new_viewer_port = viewer_port_input.value()
            new_host = host_input.text().strip() or "localhost"
            new_log = Path(log_input.text())

            old_port = self.config.get_port()
            old_viewer_port = self.config.get_viewer_port()
            old_host = self.config.get_service_host()
            old_log = self.config.get_log_file()

            changed = (
                (new_port != old_port) or
                (new_viewer_port != old_viewer_port) or
                (new_host != old_host) or
                (new_log != old_log)
            )

            if changed or dialog._restart_requested:
                # Save configuration
                self.config.set_port(new_port)
                self.config.set_viewer_port(new_viewer_port)
                self.config.set_service_host(new_host)
                self.config.set_log_file(new_log)

                # Restart if requested or if settings changed
                if dialog._restart_requested or changed:
                    if self._restart_service():
                        # Update viewer to use new log file
                        self.log_path = self.config.get_log_file()
                        self.last_position = 0
                        self.lines_displayed = 0
                        self.table.setRowCount(0)

                        # Update file watcher
                        self.file_watcher.removePaths(self.file_watcher.files())
                        if self.log_path.exists():
                            self.file_watcher.addPath(str(self.log_path))

                        self._load_existing_data()
                        QMessageBox.information(self, "Success", "Service restarted with new configuration.")
                else:
                    QMessageBox.information(self, "Saved", "Configuration saved. Restart the service to apply changes.")

    def _start_network_client(self):
        """Connect to the service's viewer broadcast and stream live data."""
        if self.connection_mode == "network":
            return
        host = self.config.get_service_host()
        port = self.config.get_viewer_port()
        try:
            sock = socket.create_connection((host, port), timeout=5)
        except Exception as e:
            QMessageBox.warning(self, "Connection Failed", f"Could not connect to {host}:{port}\n{e}")
            return

        # Switch to network mode: stop file polling
        self.connection_mode = "network"
        try:
            self.timer.stop()
        except Exception:
            pass
        try:
            self.file_watcher.removePaths(self.file_watcher.files())
        except Exception:
            pass

        self._net_sock = sock
        self._net_running.set()
        self._net_thread = threading.Thread(target=self._network_loop, daemon=True)
        self._net_thread.start()
        self._update_status()

    def _stop_network_client(self):
        """Disconnect from the service and return to file mode."""
        if self.connection_mode != "network":
            return
        self._net_running.clear()
        try:
            if self._net_sock:
                try:
                    self._net_sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self._net_sock.close()
        except Exception:
            pass
        self._net_sock = None
        try:
            if self._net_thread and self._net_thread.is_alive():
                self._net_thread.join(timeout=1.0)
        except Exception:
            pass
        self._net_thread = None

        # Return to file mode
        self.connection_mode = "file"
        if self.log_path.exists():
            try:
                self.file_watcher.addPath(str(self.log_path))
            except Exception:
                pass
        try:
            self.timer.start(1000)
        except Exception:
            pass
        self._update_status()

    def _network_loop(self):
        """Read lines from the network socket and process them."""
        try:
            f = self._net_sock.makefile("r", encoding="utf-8", errors="replace")
            while self._net_running.is_set():
                line = f.readline()
                if not line:
                    break
                self._process_line(line.strip())
                self.lines_displayed += 1
                self._update_status()
        except Exception:
            pass
        finally:
            # Auto-switch to file mode on disconnect on the GUI thread
            QTimer.singleShot(0, self._stop_network_client)
    
    def _browse_log_file(self, line_edit):
        """Browse for log file location."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Log File Location",
            str(self.config.get_log_file()),
            "Log Files (*.log);;All Files (*.*)"
        )
        if path:
            line_edit.setText(path)
    
    def _restart_service(self):
        """Restart the SMDR service."""
        try:
            # Stop service
            result = subprocess.run(
                ["net", "stop", "SMDRReceiver"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                QMessageBox.warning(
                    self,
                    "Service Control",
                    f"Failed to stop service:\n{result.stderr}\n\nRun the viewer as Administrator (right-click → Run as administrator)."
                )
                return False
            
            # Small delay
            time.sleep(2)
            
            # Start service
            result = subprocess.run(
                ["net", "start", "SMDRReceiver"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                QMessageBox.warning(
                    self,
                    "Service Control",
                    f"Failed to start service:\n{result.stderr}\n\nRun the viewer as Administrator (right-click → Run as administrator)."
                )
                return False
            
            return True
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error restarting service:\n{e}")
            return False
    
    def _show_service_status(self):
        """Show the current service status."""
        try:
            result = subprocess.run(
                ["sc", "query", "SMDRReceiver"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # Parse status
                status_text = result.stdout
                if "RUNNING" in status_text:
                    status = "Running"
                    icon = QMessageBox.Information
                elif "STOPPED" in status_text:
                    status = "Stopped"
                    icon = QMessageBox.Warning
                else:
                    status = "Unknown"
                    icon = QMessageBox.Information
                
                msg = QMessageBox(self)
                msg.setIcon(icon)
                msg.setWindowTitle("Service Status")
                msg.setText(f"SMDR Receiver Service is: {status}")
                msg.setDetailedText(status_text)
                
                # Add current configuration info
                info = (
                    f"\nCurrent Configuration:\n"
                    f"Port: {self.config.get_port()}\n"
                    f"Log File: {self.config.get_log_file()}\n"
                )
                msg.setInformativeText(info)
                msg.exec()
            else:
                QMessageBox.warning(
                    self,
                    "Service Status",
                    f"Could not query service status:\n{result.stderr}"
                )
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error checking service status:\n{e}")


def main():
    app = QApplication(sys.argv)
    viewer = SMDRViewer()
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
