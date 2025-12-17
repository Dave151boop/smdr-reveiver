import pytest
from PySide6.QtWidgets import QApplication

from smdr import gui


def ensure_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_format_row_aligns_to_headers(monkeypatch):
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

    # Send a CSV-like line with a few fields; others will be blank
    sample = '2025/12/17 12:34:56,00:10:23,3,12345,I,1001,1001,ACC-1,1,1001,1,DeviceA,100,DeviceB,200,John,Doe,42,00:10:23,5,1,0,USER,0,1,0,0,0,HG,Targeter,ExternalNumber,192.0.2.1,555,192.0.2.2,666,2025/12/17 12:34:56,0,A'

    # Inject into queue and poll
    w._on_data_from_server(sample, ('127.0.0.1', 7000))
    w._poll_queue()

    # Header should be in table
    header_label = w.table.horizontalHeaderItem(0).text()
    assert header_label == gui.FIELD_NAMES[0].replace('_', ' ').title()

    # Table should contain a row with data
    assert w.table.rowCount() == 1
    first_cell = w.table.item(0, 0).text()
    assert first_cell.startswith('2025/12/17 12:34:56')

    w.server.stop()
    w.close()
