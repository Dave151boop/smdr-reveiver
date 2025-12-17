import pytest
from PySide6.QtWidgets import QApplication

from smdr import gui


def ensure_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_headers_present(monkeypatch):
    ensure_app()

    # Make server that starts successfully so MainWindow won't pop an error dialog
    class WorkingServer:
        def __init__(self, *a, **k):
            pass

        def start(self, port):
            self._port = port

        def stop(self):
            pass

    monkeypatch.setattr(gui, 'SMDRServer', WorkingServer)

    w = gui.MainWindow()

    # Compute expected header text from FIELD_NAMES
    expected_first = gui.FIELD_NAMES[0].replace('_', ' ').title()
    assert w.table.horizontalHeaderItem(0).text() == expected_first

    w.server.stop()
    w.close()
