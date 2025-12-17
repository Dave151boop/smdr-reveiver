"""
SMDR Standalone - All-in-one application combining receiver and viewer.
- Receives SMDR data via TCP
- Displays received calls in real-time
- Includes port configuration, display settings, and logging dialogs
"""
import sys
import os
import socket
import threading
import queue
import logging
from pathlib import Path
from datetime import datetime
from io import StringIO

from PySide6.QtCore import QTimer, Qt, QFileSystemWatcher, QThread, Signal
from PySide6.QtGui import QAction, QColor, QPalette, QFont
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QLineEdit,
    QPushButton, QDialog, QFormLayout, QDialogButtonBox, QSpinBox,
    QDoubleSpinBox, QColorDialog, QMessageBox, QTextEdit, QTabWidget,
    QFileDialog, QComboBox
)
import csv

# Server and config imports
from smdr.server import SMDRServer, FIELD_NAMES
from smdr.config import SMDRConfig


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LogViewerDialog(QDialog):
    """Dialog to view and manage application logs."""
    def __init__(self, parent=None, log_path=None):
        super().__init__(parent)
        self.setWindowTitle("Log Viewer")
        self.resize(700, 500)
        self.log_path = log_path or Path("smdr_standalone.log")
        
        layout = QVBoxLayout(self)
        
        # Log content text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9))
        layout.addWidget(QLabel("Application Log:"))
        layout.addWidget(self.log_text)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_log)
        
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self._clear_log)
        
        export_btn = QPushButton("Export Log")
        export_btn.clicked.connect(self._export_log)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(export_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        # Auto-refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self._load_log)
        self.timer.start(1000)
        
        self._load_log()
    
    def _load_log(self):
        """Load log file content."""
        try:
            if self.log_path.exists():
                with open(self.log_path, 'r') as f:
                    content = f.read()
                    # Show last 100 lines
                    lines = content.split('\n')
                    display_content = '\n'.join(lines[-100:])
                    self.log_text.setText(display_content)
                    # Scroll to bottom
                    self.log_text.verticalScrollBar().setValue(
                        self.log_text.verticalScrollBar().maximum()
                    )
        except Exception as e:
            self.log_text.setText(f"Error reading log: {e}")
    
    def _clear_log(self):
        """Clear log file."""
        if QMessageBox.question(self, "Clear Log", "Clear all log entries?") == QMessageBox.Yes:
            try:
                with open(self.log_path, 'w') as f:
                    f.write("")
                self._load_log()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear log: {e}")
    
    def _export_log(self):
        """Export log to file."""
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", "", "Text Files (*.txt);;All Files (*)")
        if path:
            try:
                with open(self.log_path, 'r') as src:
                    content = src.read()
                with open(path, 'w') as dst:
                    dst.write(content)
                QMessageBox.information(self, "Success", f"Log exported to {path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export log: {e}")
    
    def closeEvent(self, event):
        self.timer.stop()
        event.accept()


class DisplaySettingsDialog(QDialog):
    """Dialog for display/view settings."""
    def __init__(self, parent=None, shading_enabled=True, shading_color='#eaf8ea', max_rows=1000):
        super().__init__(parent)
        self.setWindowTitle("Display Settings")
        self.resize(400, 300)
        
        self.shading_enabled = shading_enabled
        self.shading_color = shading_color
        self.max_rows = max_rows
        
        layout = QFormLayout(self)
        
        # Row shading option
        self.shading_check = QPushButton("Change Shading Color")
        self.shading_check.clicked.connect(self._pick_color)
        self.color_label = QLabel()
        self._update_color_label()
        
        shading_layout = QHBoxLayout()
        shading_layout.addWidget(self.shading_check)
        shading_layout.addWidget(self.color_label)
        layout.addRow("Alternate Row Color:", shading_layout)
        
        # Max rows to display
        self.max_rows_spin = QSpinBox()
        self.max_rows_spin.setMinimum(100)
        self.max_rows_spin.setMaximum(10000)
        self.max_rows_spin.setSingleStep(100)
        self.max_rows_spin.setValue(self.max_rows)
        layout.addRow("Max Rows to Display:", self.max_rows_spin)
        
        # Font size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setMinimum(8)
        self.font_size_spin.setMaximum(16)
        self.font_size_spin.setValue(10)
        layout.addRow("Font Size:", self.font_size_spin)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def _pick_color(self):
        """Open color picker."""
        color = QColorDialog.getColor(QColor(self.shading_color), self, "Select Shading Color")
        if color.isValid():
            self.shading_color = color.name()
            self._update_color_label()
    
    def _update_color_label(self):
        """Update color display label."""
        self.color_label.setStyleSheet(f"background-color: {self.shading_color}; border: 1px solid black; width: 30px; height: 20px;")


class PortConfigDialog(QDialog):
    """Dialog to configure listening port and log file path."""
    def __init__(self, parent=None, port=7004, log_file="smdr_standalone.log"):
        super().__init__(parent)
        self.setWindowTitle("Configuration")
        self.resize(500, 200)
        
        layout = QFormLayout(self)
        
        # Port selection
        self.port_spin = QSpinBox()
        self.port_spin.setMinimum(1024)
        self.port_spin.setMaximum(65535)
        self.port_spin.setValue(port)
        layout.addRow("Listen Port:", self.port_spin)
        
        # Port availability check
        self.check_port_btn = QPushButton("Check Availability")
        self.check_port_btn.clicked.connect(self._check_port)
        layout.addRow("", self.check_port_btn)
        
        # Log file path
        log_layout = QHBoxLayout()
        self.log_file_edit = QLineEdit(str(log_file))
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_log_file)
        log_layout.addWidget(self.log_file_edit)
        log_layout.addWidget(browse_btn)
        layout.addRow("Log File:", log_layout)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def _check_port(self):
        """Check if port is available."""
        port = self.port_spin.value()
        if SMDRServer.is_port_available(port):
            QMessageBox.information(self, "Port Available", f"Port {port} is available.")
        else:
            QMessageBox.warning(self, "Port In Use", f"Port {port} is already in use.")
    
    def _browse_log_file(self):
        """Browse for log file location."""
        path, _ = QFileDialog.getSaveFileName(self, "Log File Location", "", "Log Files (*.log);;All Files (*)")
        if path:
            self.log_file_edit.setText(path)


class SMDRStandalone(QMainWindow):
    """All-in-one SMDR Receiver and Viewer."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMDR Standalone - Receiver & Viewer")
        self.resize(1000, 700)
        
        # Configuration
        self.config = SMDRConfig()
        self.port = self.config.get_port()
        self.log_file = Path(self.config.get_log_file())
        self.shading_color = '#eaf8ea'
        self.max_rows_display = 1000
        
        # Server and data
        self.server = None
        self.data_queue = queue.Queue()
        self._rows = []
        self._raw_lines = []
        
        # Setup logging to file
        self._setup_file_logging()
        
        # Create UI
        self._create_ui()
        
        # Start server
        self._start_server()
        
        # Timer to process queued data
        self.timer = QTimer()
        self.timer.timeout.connect(self._process_queue)
        self.timer.start(100)
    
    def _setup_file_logging(self):
        """Configure file logging."""
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(self.log_file)
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not set up file logging: {e}")
    
    def _create_ui(self):
        """Create user interface."""
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        main_layout = QVBoxLayout(central)
        
        # Status bar
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.port_label = QLabel(f"Port: {self.port}")
        self.connection_label = QLabel("Connections: 0")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.port_label)
        status_layout.addWidget(self.connection_label)
        main_layout.addLayout(status_layout)
        
        # Tabs for different views
        self.tabs = QTabWidget()
        
        # Tab 1: Data Table
        self.table = QTableWidget()
        self.table.setColumnCount(len(FIELD_NAMES))
        self.table.setHorizontalHeaderLabels([n.replace('_', ' ').title() for n in FIELD_NAMES])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self._apply_shading()
        self.tabs.addTab(self.table, "Data Table")
        
        # Tab 2: Raw Log
        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setFont(QFont("Courier", 9))
        self.tabs.addTab(self.raw_text, "Raw Log")
        
        main_layout.addWidget(self.tabs)
        
        # Control buttons
        ctrl_layout = QHBoxLayout()
        
        config_btn = QPushButton("Configuration")
        config_btn.clicked.connect(self._show_config_dialog)
        
        settings_btn = QPushButton("Display Settings")
        settings_btn.clicked.connect(self._show_display_settings)
        
        log_btn = QPushButton("View Logs")
        log_btn.clicked.connect(self._show_log_viewer)
        
        clear_btn = QPushButton("Clear Data")
        clear_btn.clicked.connect(self._clear_data)
        
        export_btn = QPushButton("Export as CSV")
        export_btn.clicked.connect(self._export_csv)
        
        ctrl_layout.addWidget(config_btn)
        ctrl_layout.addWidget(settings_btn)
        ctrl_layout.addWidget(log_btn)
        ctrl_layout.addWidget(clear_btn)
        ctrl_layout.addWidget(export_btn)
        ctrl_layout.addStretch()
        
        main_layout.addLayout(ctrl_layout)
        
        # Menu bar
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        file_menu.addAction("Export CSV", self._export_csv)
        file_menu.addAction("Exit", self.close)
        
        config_menu = menu.addMenu("Configuration")
        config_menu.addAction("Port & Logging", self._show_config_dialog)
        config_menu.addAction("Display Settings", self._show_display_settings)
        
        tools_menu = menu.addMenu("Tools")
        tools_menu.addAction("View Logs", self._show_log_viewer)
        tools_menu.addAction("Clear Data", self._clear_data)
    
    def _apply_shading(self):
        """Apply row shading to table."""
        try:
            pal = self.table.palette()
            pal.setColor(QPalette.AlternateBase, QColor(self.shading_color))
            self.table.setPalette(pal)
        except Exception as e:
            logger.warning(f"Could not apply shading: {e}")
    
    def _start_server(self):
        """Start the SMDR receiver server."""
        def on_data(data, addr):
            """Callback when data is received."""
            self.data_queue.put((data, addr))
        
        try:
            self.server = SMDRServer(on_data=on_data)
            self.server.start(self.port)
            logger.info(f"Server started on port {self.port}")
            self.status_label.setText(f"Listening on port {self.port}")
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            QMessageBox.critical(self, "Server Error", f"Failed to start server: {e}")
    
    def _process_queue(self):
        """Process queued data from server."""
        processed = False
        while not self.data_queue.empty():
            try:
                data, addr = self.data_queue.get_nowait()
                self._handle_smdr_data(data)
                processed = True
            except queue.Empty:
                break
        
        if processed:
            self.connection_label.setText(f"Connections: {len(self.server._clients) if self.server else 0}")
    
    def _handle_smdr_data(self, data):
        """Process received SMDR data."""
        try:
            lines = data.strip().split('\n')
            for line in lines:
                if not line:
                    continue
                
                # Add timestamp and store raw line
                timestamped_line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {line}"
                self._raw_lines.append(timestamped_line)
                
                # Try to parse as CSV
                try:
                    reader = csv.reader(StringIO(line))
                    row = next(reader)
                    if len(row) >= len(FIELD_NAMES):
                        self._rows.append(row[:len(FIELD_NAMES)])
                except Exception as e:
                    logger.debug(f"Could not parse line as CSV: {e}")
                    continue
            
            # Limit displayed rows
            if len(self._rows) > self.max_rows_display:
                self._rows = self._rows[-self.max_rows_display:]
                self._raw_lines = self._raw_lines[-self.max_rows_display:]
            
            # Update UI
            self._update_table()
            self._update_raw_log()
            
        except Exception as e:
            logger.error(f"Error processing data: {e}")
    
    def _update_table(self):
        """Update data table with current rows."""
        self.table.setRowCount(len(self._rows))
        for row_idx, row in enumerate(self._rows):
            for col_idx, value in enumerate(row[:len(FIELD_NAMES)]):
                item = QTableWidgetItem(str(value)[:100])  # Truncate long values
                self.table.setItem(row_idx, col_idx, item)
    
    def _update_raw_log(self):
        """Update raw log display."""
        self.raw_text.setText('\n'.join(self._raw_lines[-100:]))  # Show last 100 lines
        self.raw_text.verticalScrollBar().setValue(self.raw_text.verticalScrollBar().maximum())
    
    def _show_config_dialog(self):
        """Show port configuration dialog."""
        dialog = PortConfigDialog(self, self.port, str(self.log_file))
        if dialog.exec():
            self.port = dialog.port_spin.value()
            self.log_file = Path(dialog.log_file_edit.text())
            
            # Save to config
            self.config.set_port(self.port)
            self.config.set_log_file(self.log_file)
            self.config.save_config()
            
            # Restart server with new port
            if self.server:
                self.server.stop()
            self._start_server()
            
            self.port_label.setText(f"Port: {self.port}")
            self.status_label.setText("Configuration updated")
            logger.info(f"Configuration updated: port={self.port}, log={self.log_file}")
    
    def _show_display_settings(self):
        """Show display settings dialog."""
        dialog = DisplaySettingsDialog(self, True, self.shading_color, self.max_rows_display)
        if dialog.exec():
            self.shading_color = dialog.shading_color
            self.max_rows_display = dialog.max_rows_spin.value()
            self._apply_shading()
            logger.info(f"Display settings updated: color={self.shading_color}, max_rows={self.max_rows_display}")
    
    def _show_log_viewer(self):
        """Show log viewer dialog."""
        dialog = LogViewerDialog(self, self.log_file)
        dialog.exec()
    
    def _clear_data(self):
        """Clear all displayed data."""
        if QMessageBox.question(self, "Clear Data", "Clear all displayed data?") == QMessageBox.Yes:
            self._rows = []
            self._raw_lines = []
            self._update_table()
            self._update_raw_log()
            self.status_label.setText("Data cleared")
    
    def _export_csv(self):
        """Export data as CSV."""
        if not self._rows:
            QMessageBox.warning(self, "No Data", "No data to export")
            return
        
        path, _ = QFileDialog.getSaveFileName(self, "Export Data", "", "CSV Files (*.csv);;All Files (*)")
        if path:
            try:
                with open(path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(FIELD_NAMES)
                    writer.writerows(self._rows)
                QMessageBox.information(self, "Success", f"Exported {len(self._rows)} records to {path}")
                logger.info(f"Exported {len(self._rows)} records to {path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {e}")
                logger.error(f"Export failed: {e}")
    
    def closeEvent(self, event):
        """Clean up on exit."""
        if self.server:
            self.server.stop()
        self.timer.stop()
        logger.info("Application closed")
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SMDRStandalone()
    window.show()
    sys.exit(app.exec())
