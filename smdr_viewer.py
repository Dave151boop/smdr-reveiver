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
from PySide6.QtCore import QTimer, Qt, QFileSystemWatcher, QSettings, QByteArray, QDateTime, QDate, QTime
from PySide6.QtGui import QAction, QColor, QPalette, QBrush, QIcon, QShortcut, QKeySequence, QClipboard
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
    QMenu,
    QDateTimeEdit,
    QCheckBox,
    QComboBox,
)
import csv
from io import StringIO
import base64
import ctypes

from smdr.server import FIELD_NAMES
from smdr.config import SMDRConfig
import subprocess


class SMDRViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMDR Viewer (Service Client)")
        self.resize(900, 600)
        app_icon = self._load_app_icon()
        if app_icon:
            try:
                self.setWindowIcon(app_icon)
                app = QApplication.instance()
                if app:
                    app.setWindowIcon(app_icon)
            except Exception:
                pass
        
        # Load configuration
        self.config = SMDRConfig()
        self._shading_color = '#eaf8ea'
        
        # File tracking (will resolve to dated SMDRdataMMDDYY.log if missing)
        self.log_path = self.config.get_log_file()
        self._resolve_log_path()
        self.last_position = 0
        self.lines_displayed = 0

        # Connection/file mode tracking
        self.connection_mode = "file"  # "file" or "network"

        # Network client state
        self._net_sock = None
        self._net_thread = None
        self._net_running = threading.Event()

        # Source IP color mapping
        self._use_source_colors = bool(self.config.get('use_source_colors', False))
        # Expect a list of {"ip": str, "color1": "#RRGGBB", "color2": "#RRGGBB"}
        saved_colors = self.config.get('source_colors', []) or []
        self._source_colors = [c for c in saved_colors if isinstance(c, dict) and c.get('ip') and c.get('color1') and c.get('color2')]
        # Normalize to max 10 entries
        self._source_colors = self._source_colors[:10]
        self._rebuild_color_map()
        # Track row count per IP for alternating
        self._source_ip_count = {}

        # Source IP naming
        self._use_source_names = bool(self.config.get('use_source_names', False))
        saved_names = self.config.get('source_names', []) or []
        self._source_names = []
        for c in saved_names:
            if isinstance(c, dict) and c.get('ip') and c.get('name'):
                self._source_names.append({'ip': str(c.get('ip')).strip(), 'name': str(c.get('name')).strip()[:20]})
        self._source_names = self._source_names[:10]
        self._rebuild_name_map()

        # Row limit for memory management
        self._max_rows = int(self.config.get('max_rows', 10000))

        # Auto-reconnect settings
        self._auto_reconnect = bool(self.config.get('auto_reconnect', True))
        self._reconnect_timer = None

        # Last update timestamp
        self._last_update_time = None

        # Settings for window state and column widths
        self._settings = QSettings("SMDR", "Viewer")
        
        # Create UI
        self._create_ui()
        
        # Restore window geometry and column widths
        self._restore_window_state()
        
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

        # Prompt to connect to service on launch
        self._launch_prompt_shown = False
        QTimer.singleShot(0, self._prompt_connect_on_launch)
        
    def _create_ui(self):
        """Create the user interface."""
        # Table widget with Source IP/Name as first column
        self.table = QTableWidget()
        self.table.setColumnCount(len(FIELD_NAMES) + 1)
        headers = ['Source IP/Name'] + [n.replace('_', ' ').title() for n in FIELD_NAMES]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_context_menu)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self._apply_shading_color()
        
        # Context menu for table
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
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

        # Quick filters bar
        filters_widget = QWidget()
        filters_layout = QHBoxLayout(filters_widget)
        filters_layout.setContentsMargins(0, 0, 0, 0)

        filters_layout.addWidget(QLabel("Filters:"))

        # Direction filter
        filters_layout.addWidget(QLabel("Direction:"))
        self.filter_direction = QComboBox()
        self.filter_direction.addItems(["All", "INBOUND", "OUTBOUND"])
        filters_layout.addWidget(self.filter_direction)

        # Extension filter (matches device/name columns)
        filters_layout.addWidget(QLabel("Extension:"))
        self.filter_extension = QLineEdit()
        self.filter_extension.setPlaceholderText("e.g. 201 or E201")
        filters_layout.addWidget(self.filter_extension)

        # Date range filter
        self.filter_enable_dates = QCheckBox("Date Range")
        filters_layout.addWidget(self.filter_enable_dates)
        self.filter_start = QDateTimeEdit()
        self.filter_start.setDisplayFormat("yyyy/MM/dd HH:mm:ss")
        self.filter_start.setCalendarPopup(True)
        self.filter_end = QDateTimeEdit()
        self.filter_end.setDisplayFormat("yyyy/MM/dd HH:mm:ss")
        self.filter_end.setCalendarPopup(True)
        # Default to today's full range: 00:00:01 to 23:59:59
        try:
            today = QDate.currentDate()
            self.filter_start.setDateTime(QDateTime(today, QTime(0, 0, 1)))
            self.filter_end.setDateTime(QDateTime(today, QTime(23, 59, 59)))
        except Exception:
            pass
        filters_layout.addWidget(self.filter_start)
        filters_layout.addWidget(QLabel("to"))
        filters_layout.addWidget(self.filter_end)

        apply_filters_btn = QPushButton("Apply Filters")
        apply_filters_btn.clicked.connect(self._apply_filters)
        clear_filters_btn = QPushButton("Clear Filters")
        clear_filters_btn.clicked.connect(self._clear_filters)
        filters_layout.addWidget(apply_filters_btn)
        filters_layout.addWidget(clear_filters_btn)
        
        self._search_matches = []
        self._current_search_index = -1
        
        # Status bar
        self.status = QLabel()

        # Connection header (prominent status)
        self.header_label = QLabel("Not Connected")
        self.header_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: red; padding: 4px;")

        # Layout
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.header_label)
        layout.addWidget(search_widget)
        layout.addWidget(filters_widget)
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
        
        # Preferences import/export
        import_prefs_action = QAction("Import Preferences...", self)
        import_prefs_action.triggered.connect(self._import_preferences)
        file_menu.addAction(import_prefs_action)

        export_prefs_action = QAction("Export Preferences...", self)
        export_prefs_action.triggered.connect(self._export_preferences)
        file_menu.addAction(export_prefs_action)
        
        file_menu.addSeparator()
        
        clear_action = QAction("Clear Display", self)
        clear_action.triggered.connect(self._clear_display)
        file_menu.addAction(clear_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu with submenus for organization
        view_menu = self.menuBar().addMenu("View")

        # Table appearance submenu
        appearance_menu = view_menu.addMenu("Table Appearance")
        self._line_shading_action = QAction("Enable Line Shading", self, checkable=True)
        self._line_shading_action.setChecked(True)
        self._line_shading_action.triggered.connect(self._toggle_line_shading)
        appearance_menu.addAction(self._line_shading_action)

        shading_color_action = QAction("Shading Color...", self)
        shading_color_action.triggered.connect(self._choose_shading_color)
        appearance_menu.addAction(shading_color_action)

        # Column manager
        columns_action = QAction("Manage Columns...", self)
        columns_action.triggered.connect(self._show_column_manager)
        appearance_menu.addAction(columns_action)

        # Source ID submenu (combines colors and names)
        source_id_menu = view_menu.addMenu("Source ID")
        self._use_source_colors_action = QAction("Use Source Colors", self, checkable=True)
        self._use_source_colors_action.setChecked(self._use_source_colors)
        self._use_source_colors_action.triggered.connect(self._toggle_source_colors)
        source_id_menu.addAction(self._use_source_colors_action)

        self._use_source_names_action = QAction("Use Source Names", self, checkable=True)
        self._use_source_names_action.setChecked(self._use_source_names)
        self._use_source_names_action.triggered.connect(self._toggle_source_names)
        source_id_menu.addAction(self._use_source_names_action)

        source_colors_action = QAction("Configure Source ID...", self)
        source_colors_action.triggered.connect(self._configure_source_colors)
        source_id_menu.addAction(source_colors_action)
        
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
        
        # Keyboard shortcuts
        self._setup_shortcuts()
        
        self._update_status()
        
    def _load_existing_data(self):
        """Load existing data from log file."""
        if not self.log_path.exists():
            self._resolve_log_path()
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
        
        # Check if log file rolled to a new date
        if not self.log_path.exists():
            self._resolve_log_path()
        
        # Also periodically check for newer dated logs
        try:
            base_dir = self.log_path.parent if self.log_path.parent else Path.cwd()
            candidates = sorted(base_dir.glob("SMDRdata*.log"))
            if candidates and candidates[-1] != self.log_path:
                # Switch to newer log file
                self._resolve_log_path()
        except Exception:
            pass
        
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

    def _resolve_log_path(self):
        """If the configured log file is missing, pick the latest SMDRdata*.log in its directory."""
        try:
            old_path = self.log_path
            base_dir = self.log_path.parent if self.log_path.parent else Path.cwd()
            candidates = sorted(base_dir.glob("SMDRdata*.log"))
            if candidates:
                latest = candidates[-1]
                if latest != self.log_path:
                    self.log_path = latest
                    # Update file watcher to the new path
                    try:
                        self.file_watcher.removePaths(self.file_watcher.files())
                        if self.log_path.exists():
                            self.file_watcher.addPath(str(self.log_path))
                        self.last_position = 0
                    except Exception:
                        pass
        except Exception:
            pass

    def _load_app_icon(self) -> QIcon | None:
        """Load the application icon for window/taskbar."""
        import sys
        base_candidates = []
        # When frozen, PyInstaller extracts resources under sys._MEIPASS
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            base_candidates.append(Path(meipass))
        # Executable directory
        if getattr(sys, "frozen", False):
            base_candidates.append(Path(sys.executable).resolve().parent)
        # Source locations
        base_candidates.append(Path(__file__).resolve().parent)
        base_candidates.append(Path.cwd())

        candidates = [base / "resources" / "icon.ico" for base in base_candidates]
        for path in candidates:
            try:
                if path.exists():
                    return QIcon(str(path))
            except Exception:
                continue
        return None

    def _prompt_connect_on_launch(self):
        """Show the connect dialog once at startup."""
        if self._launch_prompt_shown:
            return
        self._launch_prompt_shown = True
        try:
            self._start_network_client()
        except Exception:
            pass

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Ctrl+F - Focus search
        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(lambda: self.search_input.setFocus())
        
        # F5 - Reconnect
        reconnect_shortcut = QShortcut(QKeySequence("F5"), self)
        reconnect_shortcut.activated.connect(self._start_network_client)
        
        # Ctrl+E - Export
        export_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        export_shortcut.activated.connect(self._export_csv)
        
        # Ctrl+L - Clear display
        clear_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        clear_shortcut.activated.connect(self._clear_display)

    def _restore_window_state(self):
        """Restore window geometry and column widths."""
        try:
            geometry = self._settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
            # Restore header state (order, visibility, sizes)
            header_state = self._settings.value("header_state")
            if header_state:
                try:
                    if isinstance(header_state, QByteArray):
                        self.table.horizontalHeader().restoreState(header_state)
                    else:
                        # QSettings may return bytes; attempt to wrap
                        self.table.horizontalHeader().restoreState(QByteArray(header_state))
                except Exception:
                    pass
            
            # Fallback: restore individual widths
            for col in range(self.table.columnCount()):
                width = self._settings.value(f"column_{col}_width")
                if width:
                    self.table.setColumnWidth(col, int(width))
        except Exception:
            pass

    def _save_window_state(self):
        """Save window geometry and column widths."""
        try:
            self._settings.setValue("geometry", self.saveGeometry())
            # Save header state (order, visibility, sizes)
            self._settings.setValue("header_state", self.table.horizontalHeader().saveState())
            
            # Save column widths
            for col in range(self.table.columnCount()):
                self._settings.setValue(f"column_{col}_width", self.table.columnWidth(col))
        except Exception:
            pass

    def closeEvent(self, event):
        """Handle window close event."""
        self._save_window_state()
        self._stop_network_client()
        event.accept()

    def _show_context_menu(self, position):
        """Show context menu on table right-click."""
        menu = QMenu(self)
        
        # Copy cell
        copy_cell_action = QAction("Copy Cell", self)
        copy_cell_action.triggered.connect(self._copy_cell)
        menu.addAction(copy_cell_action)
        
        # Copy row
        copy_row_action = QAction("Copy Row", self)
        copy_row_action.triggered.connect(self._copy_row)
        menu.addAction(copy_row_action)
        
        menu.addSeparator()
        
        # Export selected rows
        export_selected_action = QAction("Export Selected Rows...", self)
        export_selected_action.triggered.connect(self._export_selected_rows)
        menu.addAction(export_selected_action)
        
        menu.exec_(self.table.viewport().mapToGlobal(position))

    def _show_header_context_menu(self, position):
        """Show context menu on header right-click, including column manager."""
        header = self.table.horizontalHeader()
        menu = QMenu(self)

        col = header.logicalIndexAt(position)

        manage_action = QAction("Manage Columns...", self)
        manage_action.triggered.connect(self._show_column_manager)
        menu.addAction(manage_action)

        if col >= 0:
            # Hide current column
            hide_action = QAction(f"Hide '{self.table.horizontalHeaderItem(col).text()}'", self)
            hide_action.triggered.connect(lambda: self.table.setColumnHidden(col, True))
            menu.addAction(hide_action)

        show_all_action = QAction("Show All Columns", self)
        def _show_all():
            for c in range(self.table.columnCount()):
                self.table.setColumnHidden(c, False)
        show_all_action.triggered.connect(_show_all)
        menu.addAction(show_all_action)

        menu.exec_(header.viewport().mapToGlobal(position))

    def _copy_cell(self):
        """Copy current cell to clipboard."""
        try:
            current = self.table.currentItem()
            if current:
                QApplication.clipboard().setText(current.text())
        except Exception:
            pass

    def _copy_row(self):
        """Copy current row to clipboard."""
        try:
            row = self.table.currentRow()
            if row >= 0:
                row_data = []
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    row_data.append(item.text() if item else '')
                QApplication.clipboard().setText('\t'.join(row_data))
        except Exception:
            pass

    def _show_column_manager(self):
        """Show a dialog to toggle column visibility and reset layout."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Columns")
        dialog.resize(500, 500)
        form = QFormLayout(dialog)

        # Build a list of checkboxes for each column
        checkboxes = []
        for col in range(self.table.columnCount()):
            header_item = self.table.horizontalHeaderItem(col)
            title = header_item.text() if header_item else f"Column {col}"
            cb = QCheckBox(title)
            cb.setChecked(not self.table.isColumnHidden(col))
            checkboxes.append((col, cb))
            form.addRow(cb)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        reset_btn = QPushButton("Reset Layout")
        buttons.addButton(reset_btn, QDialogButtonBox.ResetRole)
        form.addRow(buttons)

        def on_reset():
            try:
                # Show all columns
                for col, cb in checkboxes:
                    cb.setChecked(True)
                # Reset header state: clear any saved state
                self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
                # Restore default order by moving sections back to logical order
                header = self.table.horizontalHeader()
                for logical in range(self.table.columnCount() - 1, -1, -1):
                    header.moveSection(header.visualIndex(logical), logical)
            except Exception:
                pass

        reset_btn.clicked.connect(on_reset)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() == QDialog.Accepted:
            # Apply visibility
            for col, cb in checkboxes:
                self.table.setColumnHidden(col, not cb.isChecked())
            # Save header state
            self._save_window_state()

    def _export_selected_rows(self):
        """Export selected rows to CSV."""
        selected_rows = set(index.row() for index in self.table.selectedIndexes())
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "No rows selected.")
            return
        
        path, _ = QFileDialog.getSaveFileName(self, "Export Selected Rows", "smdr_selected.csv", "CSV Files (*.csv)")
        if path:
            try:
                with open(path, "w", newline='', encoding="utf-8") as f:
                    writer = csv.writer(f)
                    # Write headers
                    writer.writerow(['Source IP'] + FIELD_NAMES)
                    # Write selected rows
                    for row in sorted(selected_rows):
                        row_data = []
                        for col in range(self.table.columnCount()):
                            item = self.table.item(row, col)
                            if col == 0:
                                # Export actual IP, not displayed name
                                underlying_ip = item.data(Qt.UserRole) if item else ''
                                row_data.append(underlying_ip or item.text() if item else '')
                            else:
                                row_data.append(item.text() if item else '')
                        writer.writerow(row_data)
                QMessageBox.information(self, "Success", f"Exported {len(selected_rows)} rows to {path}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not export CSV: {e}")

    def _export_preferences(self):
        """Export color/name mappings and column layout to a JSON file."""
        path, _ = QFileDialog.getSaveFileName(self, "Export Preferences", "smdr_prefs.json", "JSON Files (*.json)")
        if not path:
            return
        try:
            # Gather header state
            header_state = self.table.horizontalHeader().saveState()
            header_state_b64 = base64.b64encode(bytes(header_state)).decode('ascii') if header_state else ''

            prefs = {
                'use_source_colors': self._use_source_colors,
                'source_colors': self._source_colors,
                'use_source_names': self._use_source_names,
                'source_names': self._source_names,
                'shading_color': self._shading_color,
                'max_rows': self._max_rows,
                'auto_reconnect': self._auto_reconnect,
                'header_state': header_state_b64,
            }
            import json
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(prefs, f, indent=2)
            QMessageBox.information(self, "Preferences", f"Exported preferences to {path}")
        except Exception as e:
            QMessageBox.warning(self, "Preferences", f"Failed to export: {e}")

    def _import_preferences(self):
        """Import preferences from a JSON file and apply them."""
        path, _ = QFileDialog.getOpenFileName(self, "Import Preferences", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            import json
            with open(path, 'r', encoding='utf-8') as f:
                prefs = json.load(f)
            # Apply colors/names
            self._use_source_colors = bool(prefs.get('use_source_colors', self._use_source_colors))
            self._source_colors = list(prefs.get('source_colors', self._source_colors))
            self._rebuild_color_map()
            self._use_source_names = bool(prefs.get('use_source_names', self._use_source_names))
            self._source_names = list(prefs.get('source_names', self._source_names))
            self._rebuild_name_map()
            self._shading_color = prefs.get('shading_color', self._shading_color)
            self._max_rows = int(prefs.get('max_rows', self._max_rows))
            self._auto_reconnect = bool(prefs.get('auto_reconnect', self._auto_reconnect))
            # Restore header state
            header_state_b64 = prefs.get('header_state', '')
            if header_state_b64:
                try:
                    raw = base64.b64decode(header_state_b64)
                    self.table.horizontalHeader().restoreState(QByteArray(raw))
                except Exception:
                    pass
            # Update menu checks and visuals
            self._use_source_colors_action.setChecked(self._use_source_colors)
            self._use_source_names_action.setChecked(self._use_source_names)
            self._apply_shading_color()
            self._refresh_source_name_display()
            self._recolor_all_rows()
            # Persist to config
            try:
                self.config.set('use_source_colors', self._use_source_colors)
                self.config.set('source_colors', self._source_colors)
                self.config.set('use_source_names', self._use_source_names)
                self.config.set('source_names', self._source_names)
                self.config.save_config()
            except Exception:
                pass
            QMessageBox.information(self, "Preferences", f"Imported preferences from {path}")
        except Exception as e:
            QMessageBox.warning(self, "Preferences", f"Failed to import: {e}")
            
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
            
            # Extract source IP from ip:port format
            source_addr = addr_and_data[0]  # e.g., "192.168.1.100:12345"
            source_ip = source_addr.split(':')[0] if ':' in source_addr else source_addr
            
            csv_data = addr_and_data[1]
            
            # Parse CSV
            reader = csv.reader(StringIO(csv_data))
            parsed = next(reader, None)
            
            if parsed:
                self._add_table_row(source_ip, parsed)
                self.lines_displayed += 1
        except Exception:
            pass  # Skip malformed lines
            
    def _add_table_row(self, source_ip, parsed):
        """Add a row to the table with source IP."""
        # Enforce row limit
        if self.table.rowCount() >= self._max_rows:
            self.table.removeRow(0)
            self.lines_displayed -= 1
        
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # First column: Source IP
        display_ip = str(source_ip)
        if self._use_source_names:
            name = self._name_map.get(display_ip, display_ip)
            display_ip = name[:20]  # limit to 20 characters
        ip_item = QTableWidgetItem(display_ip)
        ip_item.setData(Qt.UserRole, str(source_ip))  # store actual IP for coloring/searching
        self.table.setItem(row, 0, ip_item)
        
        # Remaining columns: FIELD_NAMES data
        for col_index in range(len(FIELD_NAMES)):
            val = parsed[col_index] if col_index < len(parsed) else ''
            text = str(val)
            item: QTableWidgetItem
            # Map Direction: 'I' → 'INBOUND', 'O' → 'OUTBOUND' (display only)
            if col_index == 4:  # FIELD_NAMES[4] == 'direction'
                raw = (str(val).strip().upper())
                display = 'INBOUND' if raw == 'I' else ('OUTBOUND' if raw == 'O' else text)
                item = QTableWidgetItem(display)
                # Preserve raw code in UserRole for filtering/exports if needed
                item.setData(Qt.UserRole, raw if raw in ('I', 'O') else raw)
            else:
                item = QTableWidgetItem(text)
            self.table.setItem(row, col_index + 1, item)
        
        # Update last update time
        self._last_update_time = datetime.now()
        
        # Apply source IP color if enabled (alternating between color1 and color2)
        if self._use_source_colors:
            colors = self._color_map.get(source_ip)
            if colors:
                # Track row count for this IP to determine which color to use
                count = self._source_ip_count.get(source_ip, 0)
                color_hex = colors[count % 2]  # Alternate between color1 and color2
                self._source_ip_count[source_ip] = count + 1
                self._apply_row_color(row, color_hex)            
    def _update_status(self):
        """Update the status bar and connection header."""
        if self.connection_mode == "network":
            state = "Connected to SMDR Server"
            self.header_label.setText(state)
            self.header_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: green; padding: 4px;")
        else:
            state = f"LOG FILE: {self.log_path.name}"
            self.header_label.setText(state)
            self.header_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: blue; padding: 4px;")
        
        # Add last update timestamp
        timestamp_str = ""
        if self._last_update_time:
            timestamp_str = f" — Last update: {self._last_update_time.strftime('%H:%M:%S')}"
        
        self.status.setText(f"{state} — Lines displayed: {self.lines_displayed}{timestamp_str}")
        
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
                    # Write headers (with Source IP instead of name)
                    writer.writerow(['Source IP'] + FIELD_NAMES)
                    # Write rows
                    for row in range(self.table.rowCount()):
                        row_data = []
                        for col in range(self.table.columnCount()):
                            item = self.table.item(row, col)
                            if col == 0:
                                # Export actual IP, not displayed name
                                underlying_ip = item.data(Qt.UserRole) if item else ''
                                row_data.append(underlying_ip or item.text() if item else '')
                            else:
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

    def _rebuild_color_map(self):
        """Rebuild quick lookup map from list of color rules to support dual colors."""
        self._color_map = {}
        for entry in self._source_colors:
            ip = str(entry.get('ip', '')).strip()
            color1 = str(entry.get('color1', '')).strip()
            color2 = str(entry.get('color2', '')).strip()
            if ip and color1 and color2:
                self._color_map[ip] = [color1, color2]

    def _rebuild_name_map(self):
        """Rebuild IP→name map from both dedicated name entries and color entries that carry names."""
        self._name_map = {}

        def add_name(ip_val: str, name_val: str):
            ip_clean = str(ip_val or '').strip()
            name_clean = str(name_val or '').strip()
            if ip_clean and name_clean:
                self._name_map[ip_clean] = name_clean[:20]

        for entry in self._source_names:
            if isinstance(entry, dict):
                add_name(entry.get('ip'), entry.get('name'))

        for entry in self._source_colors:
            if isinstance(entry, dict):
                add_name(entry.get('ip'), entry.get('name'))

    def _refresh_source_name_display(self):
        """Refresh the first column to show either IP or mapped name based on current settings."""
        for row in range(self.table.rowCount()):
            ip_item = self.table.item(row, 0)
            if not ip_item:
                continue
            actual_ip = (ip_item.data(Qt.UserRole) if ip_item else None) or ip_item.text()
            if self._use_source_names:
                name = self._name_map.get(actual_ip, actual_ip)
                ip_item.setText(str(name)[:20])
            else:
                ip_item.setText(str(actual_ip))

    def _apply_row_color(self, row: int, color_hex: str):
        """Apply a background color to the entire row."""
        brush = QBrush(QColor(color_hex))
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item is not None:
                item.setBackground(brush)

    def _clear_row_color(self, row: int):
        """Clear any custom background colors for the row."""
        brush = QBrush()
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item is not None:
                item.setBackground(brush)

    def _recolor_all_rows(self):
        """Reapply colors to all rows based on current settings with alternating support."""
        # Reset IP counters
        self._source_ip_count = {}
        
        for row in range(self.table.rowCount()):
            if not self._use_source_colors:
                self._clear_row_color(row)
                continue
            # Source IP is in column 0
            ip_item = self.table.item(row, 0)
            ip = (ip_item.data(Qt.UserRole) if ip_item else None) or (ip_item.text().strip() if ip_item else '')
            colors = self._color_map.get(ip)
            if colors:
                # Alternate colors based on IP count
                count = self._source_ip_count.get(ip, 0)
                color_hex = colors[count % 2]
                self._source_ip_count[ip] = count + 1
                self._apply_row_color(row, color_hex)
            else:
                self._clear_row_color(row)

    def _column_index_by_header(self, header_title: str) -> int:
        """Find current column index by its header title (case-insensitive). Returns -1 if not found."""
        target = header_title.strip().lower()
        for col in range(self.table.columnCount()):
            item = self.table.horizontalHeaderItem(col)
            if item and item.text().strip().lower() == target:
                return col
        return -1

    def _apply_filters(self):
        """Apply quick filters to hide/show rows without altering data."""
        # Normalize direction filter choice
        dir_choice_ui = (self.filter_direction.currentText() or '').strip().upper()
        if dir_choice_ui == 'INBOUND':
            direction_choice = 'I'
        elif dir_choice_ui == 'OUTBOUND':
            direction_choice = 'O'
        else:
            direction_choice = ''
        ext_text = self.filter_extension.text().strip().lower()
        use_dates = self.filter_enable_dates.isChecked()
        start_dt = self.filter_start.dateTime().toPython() if use_dates else None
        end_dt = self.filter_end.dateTime().toPython() if use_dates else None

        # Sanity check date range
        if use_dates and start_dt and end_dt and start_dt > end_dt:
            QMessageBox.warning(self, "Filters", "Start date/time must be earlier than end date/time.")
            return

        # Resolve column indices by header text
        col_direction = self._column_index_by_header('Direction')
        col_device = self._column_index_by_header('Party1 Device')
        if col_device == -1:
            col_device = self._column_index_by_header('Caller')
        col_datetime = self._column_index_by_header('Call Start Time')

        for row in range(self.table.rowCount()):
            hide = False
            # Direction filter
            if direction_choice in ('I', 'O') and col_direction != -1:
                it = self.table.item(row, col_direction)
                # Prefer raw code from UserRole; fallback to mapping displayed text
                raw_dir = (it.data(Qt.UserRole) if it else None)
                if not raw_dir:
                    disp = (it.text().strip().upper() if it and it.text() else '')
                    raw_dir = 'I' if disp == 'INBOUND' else ('O' if disp == 'OUTBOUND' else disp)
                if (raw_dir or '').upper() != direction_choice:
                    hide = True

            # Extension filter (contains)
            if not hide and ext_text:
                matched = False
                if col_device != -1:
                    it = self.table.item(row, col_device)
                    if it and ext_text in it.text().strip().lower():
                        matched = True
                # Also check the first column name/IP
                if not matched:
                    ip_item = self.table.item(row, 0)
                    if ip_item and ext_text in (ip_item.text().lower()):
                        matched = True
                if not matched:
                    hide = True

            # Date range filter
            if not hide and use_dates and col_datetime != -1:
                it = self.table.item(row, col_datetime)
                try:
                    # Expect format like YYYY/MM/DD HH:MM:SS
                    from datetime import datetime as _dt
                    val = _dt.strptime(it.text().strip(), '%Y/%m/%d %H:%M:%S') if it and it.text().strip() else None
                except Exception:
                    val = None
                if val is None:
                    hide = True
                else:
                    if start_dt and val < start_dt:
                        hide = True
                    if end_dt and val > end_dt:
                        hide = True

            self.table.setRowHidden(row, hide)

    def _clear_filters(self):
        """Clear filters and show all rows."""
        self.filter_direction.setCurrentIndex(0)
        self.filter_extension.clear()
        self.filter_enable_dates.setChecked(False)
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)

    def _toggle_source_names(self):
        """Enable/disable showing mapped source names instead of IPs."""
        self._use_source_names = self._use_source_names_action.isChecked()
        try:
            self.config.set('use_source_names', self._use_source_names)
            self.config.save_config()
        except Exception:
            pass
        self._refresh_source_name_display()

    def _configure_source_names(self):
        """Configure source IP → name mappings."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Configure Source Names")
        dialog.resize(600, 450)
        form = QFormLayout(dialog)
        editors = []  # list of (ip_edit, name_edit)

        def make_row(ip_val: str = '', name_val: str = ''):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            ip_edit = QLineEdit(ip_val)
            ip_edit.setPlaceholderText("e.g. 192.168.1.10")

            name_edit = QLineEdit(name_val)
            name_edit.setPlaceholderText("Name (20 chars)")
            name_edit.setMaxLength(20)

            row_layout.addWidget(QLabel("IP:"))
            row_layout.addWidget(ip_edit, 1)
            row_layout.addWidget(QLabel("Name:"))
            row_layout.addWidget(name_edit, 1)

            editors.append((ip_edit, name_edit))
            return row_widget

        for entry in (self._source_names + [{}] * 10)[:10]:
            ip = entry.get('ip', '') if isinstance(entry, dict) else ''
            name = entry.get('name', '') if isinstance(entry, dict) else ''
            form.addRow(make_row(ip, name))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        form.addRow(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() == QDialog.Accepted:
            new_names = []
            for ip_edit, name_edit in editors:
                ip = ip_edit.text().strip()
                name = name_edit.text().strip()
                if ip and name:
                    new_names.append({'ip': ip, 'name': name[:20]})
                if len(new_names) >= 10:
                    break
            self._source_names = new_names
            self._rebuild_name_map()
            try:
                self.config.set('source_names', self._source_names)
                self.config.save_config()
            except Exception:
                pass
            self._refresh_source_name_display()

    def _toggle_source_colors(self):
        self._use_source_colors = self._use_source_colors_action.isChecked()
        # Persist
        try:
            self.config.set('use_source_colors', self._use_source_colors)
            self.config.save_config()
        except Exception:
            pass
        self._recolor_all_rows()

    def _configure_source_colors(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Configure Source Colors (2 Colors Per IP)")
        dialog.resize(650, 450)
        form = QFormLayout(dialog)
        editors = []  # list of (ip_edit, name_edit, color1_btn, color2_btn)

        # Preserve existing name mappings so we can keep names when only colors change
        existing_name_map = {}
        for entry in self._source_names:
            if isinstance(entry, dict) and entry.get('ip') and entry.get('name'):
                existing_name_map[str(entry['ip']).strip()] = str(entry['name']).strip()[:20]

        # Helper to make a row editor with 2 color buttons
        def make_row(ip_val: str = '', name_val: str = '', color1_val: str = '', color2_val: str = ''):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            ip_edit = QLineEdit(ip_val)
            ip_edit.setPlaceholderText("e.g. 192.168.1.10")

            name_edit = QLineEdit(name_val)
            name_edit.setPlaceholderText("Name (20 chars)")
            name_edit.setMaxLength(20)
            
            color1_btn = QPushButton()
            color1_btn.setText(color1_val or "Color 1")
            if color1_val:
                color1_btn.setStyleSheet(f"background-color: {color1_val}")

            color2_btn = QPushButton()
            color2_btn.setText(color2_val or "Color 2")
            if color2_val:
                color2_btn.setStyleSheet(f"background-color: {color2_val}")

            def pick_color1():
                initial = QColor(color1_val) if color1_val else QColor('#e0f7fa')
                c = QColorDialog.getColor(initial, self, "Choose Color 1")
                if c.isValid():
                    hexv = c.name()
                    color1_btn.setText(hexv)
                    color1_btn.setStyleSheet(f"background-color: {hexv}")

            def pick_color2():
                initial = QColor(color2_val) if color2_val else QColor('#b2ebf2')
                c = QColorDialog.getColor(initial, self, "Choose Color 2")
                if c.isValid():
                    hexv = c.name()
                    color2_btn.setText(hexv)
                    color2_btn.setStyleSheet(f"background-color: {hexv}")

            color1_btn.clicked.connect(pick_color1)
            color2_btn.clicked.connect(pick_color2)

            row_layout.addWidget(QLabel("IP:"))
            row_layout.addWidget(ip_edit, 1)
            row_layout.addWidget(QLabel("Name:"))
            row_layout.addWidget(name_edit, 1)
            row_layout.addWidget(color1_btn)
            row_layout.addWidget(color2_btn)

            editors.append((ip_edit, name_edit, color1_btn, color2_btn))
            return row_widget

        # Pre-fill existing up to 10 rows
        for entry in (self._source_colors + [{}] * 10)[:10]:
            ip = entry.get('ip', '') if isinstance(entry, dict) else ''
            name = entry.get('name', '') if isinstance(entry, dict) else ''
            color1 = entry.get('color1', '') if isinstance(entry, dict) else ''
            color2 = entry.get('color2', '') if isinstance(entry, dict) else ''
            form.addRow(make_row(ip, name, color1, color2))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        form.addRow(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() == QDialog.Accepted:
            new_rules = []
            merged_name_map = dict(existing_name_map)
            for ip_edit, name_edit, color1_btn, color2_btn in editors:
                ip = ip_edit.text().strip()
                name = name_edit.text().strip()
                color1 = color1_btn.text().strip()
                color2 = color2_btn.text().strip()
                if ip and color1 and color1.startswith('#') and color2 and color2.startswith('#'):
                    entry = {'ip': ip, 'color1': color1, 'color2': color2}
                    name_to_use = name or existing_name_map.get(ip, '')
                    if name_to_use:
                        name_to_use = name_to_use[:20]
                        entry['name'] = name_to_use
                        merged_name_map[ip] = name_to_use
                    new_rules.append(entry)
                if len(new_rules) >= 10:
                    break
            self._source_colors = new_rules
            self._rebuild_color_map()
            # Merge name mappings, prioritizing entries in the color list order
            ordered_names = []
            seen = set()
            for entry in new_rules:
                ip = entry.get('ip')
                name_val = entry.get('name')
                if ip and name_val and ip not in seen:
                    ordered_names.append({'ip': ip, 'name': name_val})
                    seen.add(ip)
            for ip, name_val in merged_name_map.items():
                if ip not in seen and name_val:
                    ordered_names.append({'ip': ip, 'name': name_val})
            self._source_names = ordered_names[:10]
            self._rebuild_name_map()
            # Persist
            try:
                self.config.set('source_colors', self._source_colors)
                self.config.set('source_names', self._source_names)
                self.config.save_config()
            except Exception:
                pass
            self._recolor_all_rows()
            self._refresh_source_name_display()

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
                    if item:
                        # Check displayed text
                        if search_term_lower in item.text().lower():
                            self._search_matches.append((row, col, search_term_lower))
                            continue
                        # For first column, also check underlying IP (UserRole)
                        if col == 0:
                            underlying_ip = item.data(Qt.UserRole)
                            if underlying_ip and search_term_lower in str(underlying_ip).lower():
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
        
        # Port
        port_input = QSpinBox()
        port_input.setRange(1, 65535)
        port_input.setValue(self.config.get_port())
        layout.addRow("Port:", port_input)
        
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
            new_log = Path(log_input.text())
            old_port = self.config.get_port()
            old_log = self.config.get_log_file()

            changed = (new_port != old_port) or (new_log != old_log)

            if changed or dialog._restart_requested:
                # Save configuration
                self.config.set_port(new_port)
                self.config.set_log_file(new_log)

                # Restart if requested or if settings changed
                if dialog._restart_requested or changed:
                    if self._restart_service():
                        # Update viewer to use new log file
                        self.log_path = new_log
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
    
    def _is_admin(self):
        """Check if the current process is running with administrator privileges."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    
    def _run_elevated_command(self, command_args):
        """
        Run a command with elevated privileges using UAC prompt.
        
        Args:
            command_args: List of command arguments (e.g., ["net", "stop", "SMDRReceiver"])
        
        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        try:
            # Create a batch file to run the command
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False) as bat_file:
                bat_path = bat_file.name
                # Write command to batch file
                bat_file.write('@echo off\n')
                bat_file.write(' '.join(command_args) + '\n')
                bat_file.write('exit %ERRORLEVEL%\n')
            
            # Run the batch file with elevation using ShellExecute
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,           # hwnd
                "runas",        # operation (triggers UAC)
                "cmd.exe",      # file
                f'/c "{bat_path}"',  # parameters
                None,           # directory
                1               # show window (SW_SHOWNORMAL)
            )
            
            # ShellExecuteW returns a value > 32 on success
            if ret <= 32:
                # Clean up batch file
                try:
                    Path(bat_path).unlink()
                except:
                    pass
                return False, f"Failed to elevate privileges (error code: {ret}). User may have declined UAC prompt."
            
            # Wait a bit for the command to complete
            time.sleep(3)
            
            # Clean up batch file
            try:
                Path(bat_path).unlink()
            except:
                pass
            
            return True, None
            
        except Exception as e:
            return False, f"Error running elevated command: {e}"
    
    def _restart_service(self):
        """Restart the SMDR service."""
        # Check if we're already running as admin
        if not self._is_admin():
            # Ask user if they want to elevate
            reply = QMessageBox.question(
                self,
                "Administrator Privileges Required",
                "Stopping and starting the SMDRReceiver service requires administrator privileges.\n\n"
                "Would you like to elevate privileges and continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply != QMessageBox.Yes:
                return False
            
            # Try to run elevated commands
            # Stop service
            success, error = self._run_elevated_command(["net", "stop", "SMDRReceiver"])
            if not success:
                QMessageBox.warning(
                    self,
                    "Service Control",
                    f"Failed to stop service:\n{error}"
                )
                return False
            
            # Small delay
            time.sleep(2)
            
            # Start service
            success, error = self._run_elevated_command(["net", "start", "SMDRReceiver"])
            if not success:
                QMessageBox.warning(
                    self,
                    "Service Control",
                    f"Failed to start service:\n{error}"
                )
                return False
            
            QMessageBox.information(
                self,
                "Service Control",
                "Service restarted successfully."
            )
            return True
        
        # We're already admin, run commands directly
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
                    f"Failed to stop service:\n{result.stderr}"
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
                    f"Failed to start service:\n{result.stderr}"
                )
                return False
            
            QMessageBox.information(
                self,
                "Service Control",
                "Service restarted successfully."
            )
            return True
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error restarting service:\n{e}")
            return False

    def _query_service_status(self, timeout: int = 15):
        """
        Query the SMDRReceiver service status with robust fallbacks.

        Returns tuple: (success: bool, status: str, details: str, error: str | None)
        status in {"Running", "Stopped", "Unknown"}
        """
        service_name = "SMDRReceiver"
        # Try sc.exe first
        try:
            result = subprocess.run(
                ["sc", "query", service_name],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode == 0:
                out = result.stdout or ""
                if "RUNNING" in out:
                    return True, "Running", out, None
                if "STOPPED" in out:
                    return True, "Stopped", out, None
                return True, "Unknown", out, None
            # Non-zero return: capture stderr and fall through to PS
            sc_err = (result.stderr or "").strip()
        except subprocess.TimeoutExpired as te:
            sc_err = f"sc query timed out after {timeout}s"
        except Exception as e:
            sc_err = f"sc query failed: {e}"

        # Fallback to PowerShell Get-Service (no admin required)
        try:
            ps_cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    f"$s = Get-Service -Name '{service_name}' -ErrorAction Stop;"
                    "Write-Output ('Status: ' + $s.Status);"
                    "Write-Output ('Name: ' + $s.Name);"
                    "Write-Output ('DisplayName: ' + $s.DisplayName)"
                ),
            ]
            result = subprocess.run(
                ps_cmd,
                capture_output=True,
                text=True,
                timeout=max(10, timeout // 2)
            )
            if result.returncode == 0:
                out = (result.stdout or "").strip()
                status = "Unknown"
                if "Status: Running" in out:
                    status = "Running"
                elif "Status: Stopped" in out:
                    status = "Stopped"
                return True, status, out, None
            ps_err = (result.stderr or "").strip() or (result.stdout or "").strip()
            return False, "Unknown", "", f"PowerShell Get-Service failed: {ps_err}\n(sc) {sc_err}"
        except subprocess.TimeoutExpired:
            return False, "Unknown", "", f"PowerShell Get-Service timed out. (sc) {sc_err}"
        except Exception as e:
            return False, "Unknown", "", f"PowerShell Get-Service error: {e}\n(sc) {sc_err}"
    
    def _show_service_status(self):
        """Show the current service status."""
        try:
            success, status, details, error = self._query_service_status(timeout=15)
            if success:
                if status == "Running":
                    icon = QMessageBox.Information
                elif status == "Stopped":
                    icon = QMessageBox.Warning
                else:
                    icon = QMessageBox.Information

                msg = QMessageBox(self)
                msg.setIcon(icon)
                msg.setWindowTitle("Service Status")
                msg.setText(f"SMDR Receiver Service is: {status}")
                msg.setDetailedText(details)

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
                    f"Could not query service status:\n{error}"
                )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error checking service status:\n{e}")

    def _start_network_client(self):
        """Show dialog to connect to the service's viewer broadcast."""
        if self.connection_mode == "network":
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Connect to SMDR Service")
        dialog.resize(400, 150)
        form = QFormLayout(dialog)

        # Host input
        host_input = QLineEdit()
        host_input.setText(self.config.get('service_host', 'localhost'))
        host_input.setPlaceholderText("e.g. 192.168.1.100 or localhost")
        form.addRow("Server Host:", host_input)

        # Port input
        port_input = QSpinBox()
        port_input.setRange(1, 65535)
        port_input.setValue(self.config.get('viewer_port', 7010))
        form.addRow("Port:", port_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        host = host_input.text().strip() or 'localhost'
        port = port_input.value()

        try:
            sock = socket.create_connection((host, port), timeout=5)
        except Exception as e:
            QMessageBox.warning(self, "Connection Failed", f"Could not connect to {host}:{port}\n{e}")
            return

        # Save these settings
        try:
            self.config.set('service_host', host)
            self.config.set('viewer_port', port)
            self.config.save_config()
        except Exception:
            pass

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
            # Set TCP_NODELAY on viewer socket to receive immediately
            try:
                self._net_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass
            self._net_sock.setblocking(True)
            self._net_sock.settimeout(1.0)  # 1 second timeout for recv
            
            buffer = ""
            while self._net_running.is_set():
                try:
                    data = self._net_sock.recv(4096)
                    if not data:
                        break
                    buffer += data.decode("utf-8", errors="replace")
                    
                    # Process complete lines
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        if line.strip():
                            self._process_line(line.strip())
                    self._update_status()
                except socket.timeout:
                    # Timeout is normal, just keep trying
                    continue
                except Exception:
                    break
        except Exception:
            pass
        finally:
            # Auto-switch to file mode on disconnect on the GUI thread
            QTimer.singleShot(0, self._handle_network_disconnect)

    def _handle_network_disconnect(self):
        """Handle network disconnection with optional auto-reconnect."""
        self._stop_network_client()
        
        if self._auto_reconnect and not self._reconnect_timer:
            # Schedule reconnect after 5 seconds
            self._reconnect_timer = QTimer(self)
            self._reconnect_timer.setSingleShot(True)
            self._reconnect_timer.timeout.connect(self._attempt_reconnect)
            self._reconnect_timer.start(5000)
            
    def _attempt_reconnect(self):
        """Attempt to reconnect after disconnect."""
        self._reconnect_timer = None
        try:
            # Try to reconnect with saved settings
            host = self.config.get('service_host', 'localhost')
            port = self.config.get('viewer_port', 7010)
            
            sock = socket.create_connection((host, port), timeout=5)
            
            # Successful connection
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
        except Exception:
            # Failed to reconnect, schedule another attempt if auto-reconnect is still enabled
            if self._auto_reconnect:
                self._reconnect_timer = QTimer(self)
                self._reconnect_timer.setSingleShot(True)
                self._reconnect_timer.timeout.connect(self._attempt_reconnect)
                self._reconnect_timer.start(10000)  # Try again in 10 seconds


def main():
    app = QApplication(sys.argv)
    viewer = SMDRViewer()
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
