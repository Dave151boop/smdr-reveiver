import json
from pathlib import Path
from PySide6.QtWidgets import QApplication

from smdr import gui


def ensure_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_copy_selected_to_clipboard(monkeypatch):
    ensure_app()

    class WorkingServer:
        def __init__(self, *a, **k):
            pass
        def start(self, port):
            self._port = port
        def stop(self):
            pass

    monkeypatch.setattr(gui, 'SMDRServer', WorkingServer)

    w = gui.MainWindow()

    sample = 'A,B,C'
    w._on_data_from_server(sample, ('127.0.0.1', 7000))
    w._poll_queue()

    # select the first row
    w.table.selectRow(0)

    captured = {}
    class FakeClipboard:
        def setText(self, t):
            captured['text'] = t
    monkeypatch.setattr('PySide6.QtWidgets.QApplication.clipboard', lambda : FakeClipboard())

    w.copy_selected_rows_to_clipboard()
    assert 'A' in captured['text']

    w.server.stop()
    w.close()


def test_export_selected_csv(monkeypatch, tmp_path):
    ensure_app()

    class WorkingServer:
        def __init__(self, *a, **k):
            pass
        def start(self, port):
            self._port = port
        def stop(self):
            pass

    monkeypatch.setattr(gui, 'SMDRServer', WorkingServer)

    w = gui.MainWindow()
    sample = 'X,Y,Z'
    w._on_data_from_server(sample, ('127.0.0.1', 7000))
    w._poll_queue()

    w.table.selectRow(0)
    out = tmp_path / 'sel.csv'
    monkeypatch.setattr('PySide6.QtWidgets.QFileDialog.getSaveFileName', lambda *a, **k: (str(out), ''))
    w.export_selected_csv()

    data = out.read_text(encoding='utf-8')
    assert 'X' in data and 'Y' in data and 'Z' in data

    w.server.stop()
    w.close()


def test_persist_column_widths(tmp_path, monkeypatch):
    ensure_app()

    class WorkingServer:
        def __init__(self, *a, **k):
            pass
        def start(self, port):
            self._port = port
        def stop(self):
            pass

    monkeypatch.setattr(gui, 'SMDRServer', WorkingServer)

    # Use a temp settings file path
    w = gui.MainWindow()
    # override settings path to temp file
    w._settings_path = tmp_path / 'gui_settings.json'

    # set a column width and save
    w.table.setColumnWidth(0, 333)
    w._save_table_settings()
    w.server.stop()
    w.close()

    # New window should load the settings from same path
    w2 = gui.MainWindow()
    w2._settings_path = tmp_path / 'gui_settings.json'
    # force apply
    w2._apply_saved_column_widths()
    assert w2.table.columnWidth(0) == 333
    w2.server.stop()
    w2.close()
