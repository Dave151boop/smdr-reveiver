from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette

from smdr import gui


def ensure_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_table_alternate_color_and_text_extras(monkeypatch):
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

    # table alternate base color should be set
    pal = w.table.palette()
    alt_color = pal.color(QPalette.AlternateBase).name().lower()
    assert alt_color in ('#eaf8ea', '#eef9ee')

    # raw text view should apply extra selections for multiple lines
    sample = 'line1\nline2\nline3\nline4'
    w._on_data_from_server(sample, ('127.0.0.1', 7000))
    # show raw view
    w.toggle_formatted_view(False)
    w._poll_queue()

    extras = w.text.extraSelections()
    # Should have at least one extra selection (for line 2 or 4)
    assert len(extras) >= 1

    w.server.stop()
    w.close()
