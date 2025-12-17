import os
import csv
import tempfile
from PySide6.QtWidgets import QApplication

from smdr import gui


def ensure_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_copy_and_export_csv(monkeypatch, tmp_path):
    ensure_app()

    # Working server stub
    class WorkingServer:
        def __init__(self, *a, **k):
            pass

        def start(self, port):
            self._port = port

        def stop(self):
            pass

    monkeypatch.setattr(gui, 'SMDRServer', WorkingServer)

    w = gui.MainWindow()

    sample = '2025/12/17 12:34:56,00:10:23,3,12345,I,1001,1001,ACC-1,1,1001,1,DeviceA,100,DeviceB,200,John,Doe,42,00:10:23,5,1,0,USER,0,1,0,0,0,HG,Targeter,ExternalNumber,192.0.2.1,555,192.0.2.2,666,2025/12/17 12:34:56,0,A'

    w._on_data_from_server(sample, ('127.0.0.1', 7000))
    w._poll_queue()

    # Monkeypatch clipboard
    captured = {}

    class FakeClipboard:
        def setText(self, text):
            captured['text'] = text

    monkeypatch.setattr('PySide6.QtWidgets.QApplication.clipboard', lambda : FakeClipboard())

    # Test copy
    w.copy_csv_to_clipboard()
    assert 'text' in captured
    # Check header and first cell exist
    assert 'Call Start Time' in captured['text']
    assert '2025/12/17 12:34:56' in captured['text']

    # Test export
    tmpfile = tmp_path / "out.csv"
    monkeypatch.setattr('PySide6.QtWidgets.QFileDialog.getSaveFileName', lambda *a, **k: (str(tmpfile), ''))
    w.export_csv()

    # read the file and validate
    with open(tmpfile, newline='') as f:
        rdr = csv.reader(f)
        rows = list(rdr)
    assert rows[0][0] == 'Call Start Time'
    assert '2025/12/17 12:34:56' in rows[1][0]

    w.server.stop()
    w.close()


def test_toggle_view_shows_raw_and_formatted(monkeypatch):
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

    sample = 'field1,field2,field3'
    w._on_data_from_server(sample, ('127.0.0.1', 7000))
    w._poll_queue()

    # By default formatted view is shown
    assert w.table.rowCount() >= 1
    assert 'field1' in w.table.item(0, 0).text()

    # Switch to raw view
    w.toggle_formatted_view(False)
    txt = w.text.toPlainText()
    assert 'Raw output' in txt
    assert '[' in txt and '127.0.0.1' in txt

    # Back to formatted
    w.toggle_formatted_view(True)
    # ensure table still contains the data
    assert w.table.rowCount() >= 1
    assert 'field1' in w.table.item(0, 0).text()

    w.server.stop()
    w.close()
