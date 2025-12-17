"""GUI for the SMDR receiver using PySide6."""
import os
import queue
import time
from pathlib import Path
import sys
import csv
from io import StringIO
import socket
import threading
import random
from datetime import datetime, timedelta

from PySide6.QtCore import QTimer, Qt, Slot, QUrl
from PySide6.QtGui import QAction, QIcon, QDesktopServices, QColor, QPalette, QTextCursor, QTextCharFormat, QPixmap, QPainter, QFont
from PySide6.QtWidgets import (
    QInputDialog,
    QMainWindow,
    QApplication,
    QFileDialog,
    QMessageBox,
    QTextEdit,
    QSystemTrayIcon,
    QMenu,
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
)

from smdr.server import FIELD_NAMES

from .server import SMDRServer

DEFAULT_PORT = 7000
DEFAULT_LOG = "smdr.log"
# Documentation / troubleshooting URL shown when binding fails
HELP_URL = "https://example.com/smdr/troubleshoot"


class MainWindow(QMainWindow):
    def check_port(self):
        port = self.current_port
        owners = self._get_port_owners(port)
        if not owners:
            QMessageBox.information(self, "Port Availability", f"Port {port} is available.")
        else:
            lines = [f"Port {port} is in use by:"]
            for o in owners:
                lines.append(f" - {o['name']} (PID {o['pid']})")
            QMessageBox.warning(self, "Port In Use", "\n".join(lines))
    def __init__(self):
        super().__init__()
        self.current_port = DEFAULT_PORT
        self.setWindowTitle("SMDR Receiver")
        self.resize(800, 400)

        # Store parsed rows and raw lines so we can export/copy/toggle views
        self._rows = []
        self._raw_lines = []
        self._formatted_view = True
        self._shading_color = '#eaf8ea'  # default green shading color

        # Table widget for formatted display
        self.table = QTableWidget()
        self.table.setColumnCount(len(FIELD_NAMES))
        self.table.setHorizontalHeaderLabels([n.replace('_', ' ').title() for n in FIELD_NAMES])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setAlternatingRowColors(True)
        # Use green-bar like alternate row background for easier reading
        try:
            pal = self.table.palette()
            pal.setColor(QPalette.AlternateBase, QColor('#eaf8ea'))
            self.table.setPalette(pal)
        except Exception:
            pass
        self.table.setSortingEnabled(True)
        self.table.setVisible(self._formatted_view)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setVisible(not self._formatted_view)
        self.status = QLabel()

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

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(search_widget)
        layout.addWidget(self.table)
        layout.addWidget(self.text)
        layout.addWidget(self.status)
        self.setCentralWidget(central)

        self.queue = queue.Queue()

        # Store parsed rows and raw lines so we can export/copy/toggle views
        self._rows = []  # list of parsed field lists
        self._raw_lines = []  # list of raw timestamped lines
        self._formatted_view = True

        # Insert headers for SMDR fields (one-time)
        self._headers_shown = False
        self._insert_headers()

        # Use a log file next to the executable when bundled (PyInstaller); otherwise use cwd
        import sys
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path.cwd()
        # Allow overriding the log file path via environment variable for testing or packaging
        env_log = os.environ.get("SMDR_LOG_FILE")
        if env_log:
            try:
                self.log_path = Path(env_log).resolve()
            except Exception:
                self.log_path = (base_dir / DEFAULT_LOG).resolve()
        else:
            self.log_path = (base_dir / DEFAULT_LOG).resolve()
        self.bytes_received = 0

        # Server
        self.server = SMDRServer(on_data=self._on_data_from_server)

        # Menu (moved after server init)
        file_menu = self.menuBar().addMenu("File")
        save_action = QAction("Save As…", self)
        save_action.triggered.connect(self.save_as)
        file_menu.addAction(save_action)

        export_csv_action = QAction("Export CSV…", self)
        export_csv_action.triggered.connect(self.export_csv)
        file_menu.addAction(export_csv_action)

        copy_csv_action = QAction("Copy as CSV", self)
        copy_csv_action.triggered.connect(self.copy_csv_to_clipboard)
        file_menu.addAction(copy_csv_action)

        file_menu.addSeparator()

        set_log_action = QAction("Set Log File…", self)
        set_log_action.triggered.connect(self.set_log_file)
        file_menu.addAction(set_log_action)

        change_port_action = QAction("Change Port…", self)
        change_port_action.triggered.connect(self.change_port)
        file_menu.addAction(change_port_action)

        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.exit_app)
        file_menu.addAction(exit_action)

        # View menu - line shading options
        view_menu = self.menuBar().addMenu("View")
        self._toggle_formatted_action = QAction("Show Formatted", self, checkable=True)
        self._toggle_formatted_action.setChecked(True)
        self._toggle_formatted_action.triggered.connect(self.toggle_formatted_view)
        view_menu.addAction(self._toggle_formatted_action)

        view_menu.addSeparator()
        self._line_shading_action = QAction("Enable Line Shading", self, checkable=True)
        self._line_shading_action.setChecked(True)
        self._line_shading_action.triggered.connect(self._toggle_line_shading)
        view_menu.addAction(self._line_shading_action)

        shading_color_action = QAction("Shading Color…", self)
        shading_color_action.triggered.connect(self._choose_shading_color)
        view_menu.addAction(shading_color_action)

        # Help menu
        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        
        help_menu.addSeparator()
        debug_action = QAction("Debug - Send Test Data", self)
        debug_action.triggered.connect(self._show_debug_sender)
        help_menu.addAction(debug_action)

        # Timer to poll queue - must be in __init__, not in showEvent or other methods
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_queue)
        self.timer.start(150)

    def _prompt_for_port_and_start(self):
        import traceback
        while True:
            port, ok = QInputDialog.getInt(self, "Select Port", "Enter port to listen on:", self.current_port, 1, 65535)
            if not ok:
                QMessageBox.critical(self, "No Port Selected", "A port must be selected to start the server. Exiting.")
                QApplication.quit()
                return
            try:
                if not self.server.is_port_available(port):
                    # Get process info for the port in use
                    owners = self._get_port_owners(port)
                    if owners:
                        lines = [f"Port {port} is already in use by the following process(es):"]
                        for o in owners:
                            lines.append(f" - {o['name']} (PID {o['pid']})")
                        lines.append("\nWould you like to stop these processes and use this port?")
                        
                        mb = QMessageBox(self)
                        mb.setIcon(QMessageBox.Warning)
                        mb.setWindowTitle("Port Unavailable")
                        mb.setText(f"Port {port} is in use")
                        mb.setInformativeText("\n".join(lines))
                        kill_btn = mb.addButton("Stop Processes", QMessageBox.AcceptRole)
                        choose_btn = mb.addButton("Choose Different Port", QMessageBox.RejectRole)
                        mb.addButton(QMessageBox.Cancel)
                        mb.setDefaultButton(choose_btn)
                        mb.exec()
                        
                        if mb.clickedButton() == kill_btn:
                            # User wants to kill the processes
                            pids = [o['pid'] for o in owners]
                            if self._kill_pids(pids):
                                QMessageBox.information(self, "Success", "Processes stopped. Retrying port binding...")
                                # Retry with this port
                                continue
                            else:
                                QMessageBox.warning(self, "Failed", "Could not stop one or more processes. Try running as Administrator or choose a different port.")
                                continue
                        elif mb.clickedButton() == choose_btn:
                            # User wants to choose a different port
                            continue
                        else:
                            # User cancelled
                            QMessageBox.critical(self, "Cancelled", "Port selection cancelled. Exiting.")
                            QApplication.quit()
                            return
                    else:
                        QMessageBox.warning(self, "Port Unavailable", f"Port {port} is already in use. Please choose another.")
                    continue
            except Exception as ex:
                QMessageBox.critical(self, "Error", f"Exception during port availability check:\n{ex}")
                continue
            try:
                self.server.start(port)
                self.current_port = port
                self._update_status()
                if hasattr(self, 'tray') and self.tray:
                    self.tray.showMessage("SMDR", f"Listening on port {port}")
                break
            except Exception as e:
                import traceback
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Could not start server on port {port}: {e}")
                continue

    def _show_port_owner_dialog(self):
        port = self.current_port
        owners = self._get_port_owners(port)
        if not owners:
            QMessageBox.information(self, "Port Owner", f"No process is currently listening on port {port}.")
            return
        lines = [f"Process(es) using port {port}:"]
        for o in owners:
            lines.append(f" - {o['name']} (PID {o['pid']})")
        QMessageBox.information(self, "Port Owner", "\n".join(lines))

    def _kill_port_process_dialog(self):
        port = self.current_port
        owners = self._get_port_owners(port)
        if not owners:
            QMessageBox.information(self, "Kill Port Process", f"No process is currently listening on port {port}.")
            return
        lines = [f"Process(es) using port {port}:"]
        for o in owners:
            lines.append(f" - {o['name']} (PID {o['pid']})")
        lines.append("\nDo you want to stop all these processes? This will terminate them.")
        reply = QMessageBox.question(self, "Kill Port Process", "\n".join(lines), QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            pids = [o['pid'] for o in owners]
            ok = self._kill_pids(pids)
            if ok:
                QMessageBox.information(self, "Stopped", "Listener(s) stopped. You can try the port again.")
            else:
                QMessageBox.warning(self, "Failed", "Could not stop one or more processes. Try running as Administrator.")

        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.exit_app)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = self.menuBar().addMenu("View")
        self._toggle_formatted_action = QAction("Show Formatted", self, checkable=True)
        self._toggle_formatted_action.setChecked(True)
        self._toggle_formatted_action.triggered.connect(self.toggle_formatted_view)
        view_menu.addAction(self._toggle_formatted_action)

        # Tray — use the explicit packaged icon where available
        icon = self._get_icon()
        # If an application instance exists, set its window icon too so platform
        # integrations pick up the same icon (helps with tray and taskbar).
        try:
            app = QApplication.instance()
            if app is not None and not icon.isNull():
                app.setWindowIcon(icon)
        except Exception:
            pass

        # Table context menu and persistence
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)

        # Determine settings file next to executable or cwd
        import sys as _sys
        if getattr(_sys, "frozen", False):
            base_dir = Path(_sys.executable).parent
        else:
            base_dir = Path.cwd()
        self._settings_path = base_dir / 'smdr_gui_settings.json'
        # Try to load stored table settings (column widths)
        self._load_table_settings()

        self.tray = QSystemTrayIcon(icon, self)
        tray_menu = QMenu()
        restore_action = QAction("Restore", self)
        restore_action.triggered.connect(self.restore_from_tray)
        tray_menu.addAction(restore_action)
        tray_menu.addSeparator()
        quit_tray_action = QAction("Exit", self)
        quit_tray_action.triggered.connect(self.exit_app)
        tray_menu.addAction(quit_tray_action)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        # Server - start with initial port, then prompt for user's choice
        self.server = SMDRServer(on_data=self._on_data_from_server)
        self.current_port = DEFAULT_PORT
        try:
            self.server.start(self.current_port)
        except Exception as e:
            self._show_port_bind_error("Server start failed", self.current_port, e)

        self._update_status()

    def showEvent(self, event):
        """Trigger port prompt after window is first shown."""
        super().showEvent(event)
        if not getattr(self, '_port_prompt_shown', False):
            self._port_prompt_shown = True
            # Schedule it after event processing to ensure we're in the event loop
            QTimer.singleShot(200, self._prompt_for_port_and_start)

    def _resource_path(self, rel_path: str) -> Path:
        # Return an absolute path to a resource working both in source and bundled mode.
        if getattr(sys, 'frozen', False):
            base = Path(getattr(sys, '_MEIPASS', Path.cwd()))
        else:
            base = Path.cwd()
        return base / rel_path

    def _get_icon(self) -> QIcon:
        # Create a programmatic red "A" icon
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw red "A"
        font = QFont("Arial", 48, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(220, 20, 20))  # Red color
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "A")
        
        painter.end()
        
        return QIcon(pixmap)

    def _on_data_from_server(self, text: str, addr):
        # called from server thread — enqueue to GUI thread
        self.queue.put((text, addr))

    def _format_headers(self) -> str:
        # Create a human-friendly header row from FIELD_NAMES and apply column widths
        titles = [name.replace("_", " ").title() for name in FIELD_NAMES]
        # initialize default widths on first call
        if not hasattr(self, '_field_widths'):
            # Base width per column is at least the title length and a minimum of 12.
            # Give date/time fields a larger width so timestamps are preserved.
            self._field_widths = []
            for name, t in zip(FIELD_NAMES, titles):
                if 'time' in name or 'date' in name or 'smdr' in name:
                    w = max(len(t), 19)
                else:
                    w = max(len(t), 12)
                self._field_widths.append(w)
            # Expose separator for tests and formatting
            self._col_sep = " | "
        parts = [t.ljust(w) for t, w in zip(titles, self._field_widths)]
        return self._col_sep.join(parts)

    def _insert_headers(self):
        if not getattr(self, '_headers_shown', False):
            header = self._format_headers()
            # Use rich text for visual emphasis; toPlainText will still include the header text
            try:
                self.text.append(f"<b>{header}</b>")
            except Exception:
                # Fallback to plain text if append with rich text isn't supported
                self.text.append(header)
            # add a blank line for spacing
            self.text.append("")
            self._headers_shown = True

    def _format_row(self, fields: list) -> str:
        """Format a sequence of field strings into a fixed-width, column-aligned row.

        - fields: list of strings (parsed CSV fields)
        - Returns a single-line string with columns joined by the configured separator.
        """
        # Ensure we have a list length equal to the number of FIELD_NAMES
        cols = [""] * len(FIELD_NAMES)
        for i, val in enumerate(fields[: len(FIELD_NAMES)]):
            # Normalize to str
            if val is None:
                cols[i] = ""
            else:
                cols[i] = str(val)
        # Apply widths and truncate long values with ellipsis
        parts = []
        for val, w in zip(cols, self._field_widths):
            if len(val) <= w:
                parts.append(val.ljust(w))
            else:
                # leave room for ellipsis
                if w > 3:
                    parts.append(val[: w - 3] + '...')
                else:
                    parts.append(val[:w])
        return self._col_sep.join(parts)

    @Slot()
    def _poll_queue(self):
        wrote = False
        while not self.queue.empty():
            try:
                text, addr = self.queue.get_nowait()
            except Exception as e:
                break
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            header = f"[{ts}] {addr[0]}:{addr[1]}"
            for line in text.splitlines():
                if not line:
                    continue
                # Try to parse as CSV to align fields under the headers. Fallback to raw line
                formatted = None
                try:
                    reader = csv.reader(StringIO(line))
                    parsed = next(reader, None)
                    if parsed is not None:
                        # If we got multiple fields (or even one), format into columns
                        formatted = self._format_row(parsed)
                except Exception:
                    formatted = None

                raw_out = f"[{ts}] {addr[0]}:{addr[1]} {line}"
                # store raw output for toggling/export
                self._raw_lines.append(raw_out)

                if formatted:
                    out = formatted
                    # store parsed row for CSV export/copy
                    self._rows.append(parsed)
                    # add to table if visible
                    if self._formatted_view:
                        self._append_table_row(parsed)
                else:
                    # Fallback: previous simple behaviour (timestamped raw line)
                    out = raw_out

                self.text.append(out)
                try:
                    with open(self.log_path, "a", encoding="utf-8") as f:
                        f.write(out + "\n")
                except Exception:
                    pass
                self.bytes_received += len(out) + 1
                wrote = True
        if wrote:
            self._update_status()
            # If we're in raw view, ensure green-bar styling is applied to the newly appended lines
            if not self._formatted_view:
                self._apply_green_bars_to_text()

    def _update_status(self):
        self.status.setText(f"Listening on port {self.current_port} — bytes received: {self.bytes_received} — log: {self.log_path}")

    def _append_table_row(self, parsed):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col_index in range(len(FIELD_NAMES)):
            val = parsed[col_index] if col_index < len(parsed) else ''
            item = QTableWidgetItem(str(val))
            self.table.setItem(row, col_index, item)

    def _render_content(self):
        """Re-render the main view according to current view (formatted or raw)."""
        self.table.setVisible(self._formatted_view)
        self.text.setVisible(not self._formatted_view)
        if self._formatted_view:
            # repopulate table from stored rows
            self.table.setRowCount(0)
            for parsed in self._rows:
                self._append_table_row(parsed)
            # restore any widths in case user toggled view
            self._apply_saved_column_widths()
        else:
            self.text.clear()
            self.text.append("Raw output (timestamped):")
            self.text.append("")
            for raw in self._raw_lines:
                self.text.append(raw)
            # Apply green-bar backgrounds to alternating lines for readability
            self._apply_green_bars_to_text()

    def _apply_green_bars_to_text(self):
        try:
            doc = self.text.document()
            extras = []
            block = doc.firstBlock()
            i = 0
            # Use stored color or default
            color = getattr(self, '_shading_color', '#eef9ee')
            while block.isValid():
                # highlight every odd block with a subtle background
                if i % 2 == 1:
                    sel = QTextEdit.ExtraSelection()
                    cursor = QTextCursor(block)
                    cursor.select(QTextCursor.LineUnderCursor)
                    sel.cursor = cursor
                    fmt = QTextCharFormat()
                    fmt.setBackground(QColor(color))
                    sel.format = fmt
                    extras.append(sel)
                block = block.next()
                i += 1
            self.text.setExtraSelections(extras)
        except Exception:
            # Best-effort only — ignore failures in headless tests
            pass

    def _apply_saved_column_widths(self):
        # Apply widths if present in settings file
        try:
            import json
            if not self._settings_path.exists():
                return
            with open(self._settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            widths = data.get('column_widths', [])
            for i, w in enumerate(widths[: self.table.columnCount()]):
                try:
                    self.table.setColumnWidth(i, int(w))
                except Exception:
                    pass
        except Exception:
            # ignore any problems reading the settings
            pass

    def _load_table_settings(self):
        # Ensure there is a file and call _apply_saved_column_widths during rendering
        # No-op here; actual application happens in _apply_saved_column_widths
        pass

    def _save_table_settings(self):
        try:
            import json
            widths = [self.table.columnWidth(i) for i in range(self.table.columnCount())]
            data = {'column_widths': widths}
            with open(self._settings_path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception:
            pass

    def copy_csv_to_clipboard(self, rows=None):
        # Build CSV string from FIELD_NAMES and rows (defaults to all rows)
        import csv
        from io import StringIO

        if rows is None:
            rows = self._rows

        sio = StringIO()
        writer = csv.writer(sio)
        writer.writerow([n.replace('_', ' ').title() for n in FIELD_NAMES])
        for row in rows:
            writer.writerow(row)
        csv_text = sio.getvalue()
        try:
            cb = QApplication.clipboard()
            cb.setText(csv_text)
        except Exception:
            # best effort; ignore clipboard failures in tests or headless
            pass

    def copy_selected_rows_to_clipboard(self):
        sel = self.table.selectionModel().selectedRows()
        rows = []
        for idx in sel:
            r = idx.row()
            row_vals = [self.table.item(r, c).text() if self.table.item(r, c) is not None else '' for c in range(self.table.columnCount())]
            rows.append(row_vals)
        self.copy_csv_to_clipboard(rows)

    def export_selected_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Selected CSV", str(Path.home() / "smdr_export_selected.csv"))
        if not path:
            return
        import csv
        try:
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([n.replace('_', ' ').title() for n in FIELD_NAMES])
                sel = self.table.selectionModel().selectedRows()
                for idx in sel:
                    r = idx.row()
                    row_vals = [self.table.item(r, c).text() if self.table.item(r, c) is not None else '' for c in range(self.table.columnCount())]
                    writer.writerow(row_vals)
        except Exception as e:
            QMessageBox.warning(self, "Export failed", f"Could not export selected CSV: {e}")

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", str(Path.home() / "smdr_export.csv"))
        if not path:
            return
        import csv
        try:
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([n.replace('_', ' ').title() for n in FIELD_NAMES])
                for row in self._rows:
                    writer.writerow(row)
        except Exception as e:
            QMessageBox.warning(self, "Export failed", f"Could not export CSV: {e}")

    def toggle_formatted_view(self, checked: bool):
        self._formatted_view = bool(checked)
        self._render_content()

    def _on_table_context_menu(self, pos):
        menu = QMenu(self)
        copy_sel = QAction("Copy Selected as CSV", self)
        copy_sel.triggered.connect(self.copy_selected_rows_to_clipboard)
        menu.addAction(copy_sel)

        export_sel = QAction("Export Selected as CSV…", self)
        export_sel.triggered.connect(self.export_selected_csv)
        menu.addAction(export_sel)

        copy_cell = QAction("Copy Cell", self)
        copy_cell.triggered.connect(self._copy_current_cell)
        menu.addAction(copy_cell)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _copy_current_cell(self):
        idx = self.table.currentIndex()
        if not idx.isValid():
            return
        val = self.table.item(idx.row(), idx.column())
        text = val.text() if val is not None else ''
        try:
            QApplication.clipboard().setText(text)
        except Exception:
            pass

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save data as", str(Path.home() / "smdr_saved.txt"))
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.text.toPlainText())
            except Exception as e:
                QMessageBox.warning(self, "Save failed", f"Could not save file: {e}")

    def set_log_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Set log file", str(self.log_path))
        if path:
            self.log_path = Path(path)
            # ensure it exists
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                self.log_path.touch(exist_ok=True)
            except Exception:
                pass
            self._update_status()

    def change_port(self):
        import traceback
        while True:
            port, ok = QInputDialog.getInt(self, "Change port", "Port:", self.current_port, 1, 65535)
            if not ok:
                return
            try:
                if not self.server.is_port_available(port):
                    # Get process info for the port in use
                    owners = self._get_port_owners(port)
                    if owners:
                        lines = [f"Port {port} is already in use by the following process(es):"]
                        for o in owners:
                            lines.append(f" - {o['name']} (PID {o['pid']})")
                        lines.append("\nWould you like to stop these processes and use this port?")
                        
                        mb = QMessageBox(self)
                        mb.setIcon(QMessageBox.Warning)
                        mb.setWindowTitle("Port Unavailable")
                        mb.setText(f"Port {port} is in use")
                        mb.setInformativeText("\n".join(lines))
                        kill_btn = mb.addButton("Stop Processes", QMessageBox.AcceptRole)
                        choose_btn = mb.addButton("Choose Different Port", QMessageBox.RejectRole)
                        mb.addButton(QMessageBox.Cancel)
                        mb.setDefaultButton(choose_btn)
                        mb.exec()
                        
                        if mb.clickedButton() == kill_btn:
                            # User wants to kill the processes
                            pids = [o['pid'] for o in owners]
                            if self._kill_pids(pids):
                                QMessageBox.information(self, "Success", "Processes stopped. Retrying port binding...")
                                # Retry with this port
                                continue
                            else:
                                QMessageBox.warning(self, "Failed", "Could not stop one or more processes. Try running as Administrator or choose a different port.")
                                continue
                        elif mb.clickedButton() == choose_btn:
                            # User wants to choose a different port
                            continue
                        else:
                            # User cancelled
                            return
                    else:
                        QMessageBox.warning(self, "Port Unavailable", f"Port {port} is already in use. Please choose another.")
                    continue
            except Exception as ex:
                QMessageBox.critical(self, "Error", f"Exception during port availability check:\n{ex}")
                continue
            try:
                self.server.start(port)
                self.current_port = port
                self._update_status()
                if hasattr(self, 'tray') and self.tray:
                    self.tray.showMessage("SMDR", f"Listening on port {port}")
                break
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not start server on port {port}: {e}")
                continue

    def _search_next(self):
        """Search for the next occurrence of the search term."""
        search_term = self.search_input.text().strip()
        if not search_term:
            return
        
        if self._formatted_view:
            # Search in table
            self._search_in_table(search_term)
        else:
            # Search in text widget
            self._search_in_text(search_term)
    
    def _search_in_table(self, search_term):
        """Search for text in the table widget."""
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
            self.status.setText(f"Listening on port {self.current_port} — bytes received: {self.bytes_received} — log: {self.log_path} — No matches found for '{search_term}'")
            return
        
        # Move to next match
        self._current_search_index = (self._current_search_index + 1) % len(self._search_matches)
        row, col, _ = self._search_matches[self._current_search_index]
        
        # Select and scroll to the match
        self.table.setCurrentCell(row, col)
        self.table.scrollToItem(self.table.item(row, col))
        
        # Update status
        self.status.setText(f"Listening on port {self.current_port} — bytes received: {self.bytes_received} — log: {self.log_path} — Match {self._current_search_index + 1} of {len(self._search_matches)}")
    
    def _search_in_text(self, search_term):
        """Search for text in the text widget."""
        # Use QTextEdit's built-in find function
        cursor = self.text.textCursor()
        
        # If at the end, wrap to beginning
        if cursor.atEnd():
            cursor.movePosition(QTextCursor.Start)
            self.text.setTextCursor(cursor)
        
        # Find next occurrence
        found = self.text.find(search_term)
        
        if not found:
            # Try from beginning
            cursor.movePosition(QTextCursor.Start)
            self.text.setTextCursor(cursor)
            found = self.text.find(search_term)
            
            if not found:
                self.status.setText(f"Listening on port {self.current_port} — bytes received: {self.bytes_received} — log: {self.log_path} — No matches found for '{search_term}'")
            else:
                self.status.setText(f"Listening on port {self.current_port} — bytes received: {self.bytes_received} — log: {self.log_path} — Match found (wrapped to beginning)")
        else:
            self.status.setText(f"Listening on port {self.current_port} — bytes received: {self.bytes_received} — log: {self.log_path} — Match found")
    
    def _clear_search(self):
        """Clear the search input and reset matches."""
        self.search_input.clear()
        self._search_matches = []
        self._current_search_index = -1
        self._update_status()

    def closeEvent(self, event):
        # minimize to tray instead of closing
        event.ignore()
        self.hide()
        if hasattr(self, 'tray') and self.tray:
            self.tray.showMessage("SMDR", "Application minimized to tray. Right-click the tray icon to exit.")

    def _show_port_bind_error(self, title: str, port: int, err: Exception):
        """Show an informative error dialog with a Help link when binding fails.

        The dialog includes a **Help** button that opens the online troubleshooting
        document (`HELP_URL`) so users can quickly find guidance on resolving
        common causes (port in use, insufficient permissions, firewall).
        """
        msg = (
            f"Could not bind to port {port}: {err}\n\n"
            "Possible causes:\n"
            " - Port already in use\n"
            " - Insufficient permissions (try running as administrator)\n"
            " - Firewall blocking the port\n\n"
            "Try a different port, check permissions, or consult your system firewall settings."
        )
        mb = QMessageBox(self)
        mb.setIcon(QMessageBox.Warning)
        mb.setWindowTitle(title)
        mb.setText(f"Could not bind to port {port}: {err}")
        mb.setInformativeText(msg)
        help_button = mb.addButton("Help", QMessageBox.HelpRole)
        mb.addButton(QMessageBox.Ok)
        mb.exec()
        # If the user clicked Help, open the troubleshooting URL in the default browser
        if mb.clickedButton() is help_button:
            QDesktopServices.openUrl(QUrl(HELP_URL))

    def _get_port_owners(self, port: int):
        """Return a list of dicts with process info using the given TCP port.

        Returns items like {'pid': 1234, 'name': 'smdr.exe'}.
        On platforms where netstat/tasklist aren't available, returns an empty list.
        """
        try:
            import subprocess
            out = subprocess.check_output(["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL)
            owners = []
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[0] == 'TCP':
                    local = parts[1]
                    # local can be like 0.0.0.0:7000
                    if local.endswith(f":{port}") and parts[3].upper() == 'LISTENING':
                        pid = int(parts[4])
                        # get process name via tasklist
                        try:
                            tl = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], text=True, stderr=subprocess.DEVNULL)
                            # CSV output: "Image Name","PID","Session Name","Session#","Mem Usage"
                            # parse name
                            if tl.strip():
                                name = tl.split(',')[0].strip().strip('"')
                            else:
                                name = str(pid)
                        except Exception:
                            name = str(pid)
                        owners.append({'pid': pid, 'name': name})
            return owners
        except Exception:
            return []

    def _kill_pids(self, pids):
        """Attempt to stop the given PIDs using taskkill; return True if all succeeded."""
        try:
            import subprocess
            success = True
            for pid in pids:
                res = subprocess.run(["taskkill", "/PID", str(pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if res.returncode != 0:
                    success = False
            return success
        except Exception:
            return False

    def _show_port_in_use_dialog(self, port: int, owners):
        """Show a dialog listing processes using the port and offer to stop them.

        Returns True if the process(es) were stopped, False otherwise.
        """
        # Build informative text
        lines = [f"Port {port} is in use by the following process(es):"]
        for o in owners:
            lines.append(f" - {o['name']} (PID {o['pid']})")
        lines.append("\nYou can try to stop the listener. Only do this if you're sure.")

        mb = QMessageBox(self)
        mb.setIcon(QMessageBox.Warning)
        mb.setWindowTitle("Port in use")
        mb.setText("Port is in use")
        mb.setInformativeText("\n".join(lines))
        stop_btn = mb.addButton("Stop Listener", QMessageBox.AcceptRole)
        help_btn = mb.addButton("Help", QMessageBox.HelpRole)
        mb.addButton(QMessageBox.Cancel)
        mb.exec()

        if mb.clickedButton() is help_btn:
            QDesktopServices.openUrl(QUrl(HELP_URL))
            return False
        if mb.clickedButton() is stop_btn:
            # ask for confirmation
            ans = QMessageBox.question(self, "Confirm stop", f"Stop all processes listening on port {port}? This will terminate those processes.")
            if ans == QMessageBox.Yes:
                pids = [o['pid'] for o in owners]
                ok = self._kill_pids(pids)
                if ok:
                    QMessageBox.information(self, "Stopped", "Listener stopped. You can try the port again.")
                else:
                    QMessageBox.warning(self, "Failed", "Could not stop one or more processes. Try running as Administrator.")
                return ok
        return False

    def _show_about(self):
        """Show the About dialog."""
        about_text = (
            "This program was written completely by AI with the prompting of an idiot who "
            "flunked out of a Comp-Sci degree 20+ years ago. I do not pretend to understand "
            "any of the code within. This is used completely without warranty or guarantee. "
            "It is considered unstable at best and dangerous at worst."
        )
        QMessageBox.about(self, "About SMDR Receiver", about_text)

    def _show_debug_sender(self):
        """Show dialog to send test SMDR data."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Send Test SMDR Data")
        dialog.resize(400, 200)
        
        layout = QFormLayout(dialog)
        
        # Host input
        host_input = QLineEdit("localhost")
        layout.addRow("Target Host:", host_input)
        
        # Port input
        port_input = QSpinBox()
        port_input.setRange(1, 65535)
        port_input.setValue(self.current_port)
        layout.addRow("Target Port:", port_input)
        
        # Record count input
        count_input = QSpinBox()
        count_input.setRange(1, 1000000)
        count_input.setValue(10000)
        count_input.setSingleStep(1000)
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
            
            # Run in background thread
            thread = threading.Thread(
                target=self._send_test_data,
                args=(host, port, count, delay),
                daemon=True
            )
            thread.start()
            
            QMessageBox.information(
                self,
                "Test Data Sender",
                f"Sending {count} test records to {host}:{port} in the background.\n"
                f"Check the main window to see them arrive."
            )

    def _send_test_data(self, host, port, count, delay):
        """Send test SMDR records (runs in background thread)."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            
            for i in range(count):
                record = self._generate_smdr_record(i)
                sock.sendall((record + "\n").encode('utf-8'))
                
                if delay > 0:
                    time.sleep(delay)
            
            sock.close()
        except Exception as e:
            print(f"Error sending test data: {e}")

    def _generate_smdr_record(self, index):
        """Generate a realistic SMDR record."""
        now = datetime.now() - timedelta(seconds=random.randint(0, 3600))
        date_time = now.strftime("%Y/%m/%d %H:%M:%S")
        
        duration_secs = random.randint(3, 300)
        duration = f"00:{duration_secs//60:02d}:{duration_secs%60:02d}"
        
        extension = random.randint(200, 250)
        direction = random.choice(['I', 'O'])
        
        if direction == 'O':
            called = f"{random.randint(1000000000, 9999999999)}"
            dialed = f"9{called}"
        else:
            called = f"{random.randint(1000000000, 9999999999)}"
            dialed = called
        
        call_id = 1000000 + index
        names = ["John Smith", "Jane Doe", "David Rahn", "Alice Johnson", "Bob Williams"]
        name = random.choice(names)
        trunk = f"T{random.randint(9001, 9020)}"
        
        record = f"{date_time},{duration},0,{extension},{direction},{called},{dialed},,0,{call_id},0,E{extension},{name},{trunk},Line{index % 10}"
        return record

    def _toggle_line_shading(self):
        """Toggle line shading on/off for both views."""
        enabled = self._line_shading_action.isChecked()
        if self._formatted_view:
            # Table view - enable/disable alternating row colors
            self.table.setAlternatingRowColors(enabled)
        else:
            # Text view - apply/remove green bars
            if enabled:
                self._apply_green_bars_to_text()
            else:
                self.text.setExtraSelections([])

    def _choose_shading_color(self):
        """Allow user to choose shading color."""
        from PySide6.QtWidgets import QColorDialog
        current_color = QColor('#eaf8ea')  # default green
        color = QColorDialog.getColor(current_color, self, "Choose Line Shading Color")
        if color.isValid():
            # Store the color
            self._shading_color = color.name()
            # Apply it to the current view
            if self._formatted_view:
                pal = self.table.palette()
                pal.setColor(QPalette.AlternateBase, color)
                self.table.setPalette(pal)
            else:
                self._apply_green_bars_to_text()

    def restore_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            # single click -> restore
            self.restore_from_tray()

    def exit_app(self):
        # cleanup and quit
        self.server.stop()
        # save table settings
        self._save_table_settings()
        QApplication.quit()
