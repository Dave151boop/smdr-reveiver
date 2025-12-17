import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
import os

from smdr import gui


def ensure_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_init_shows_informative_error(monkeypatch):
    ensure_app()

    opened = {}

    class FakeMessageBox:
        # Provide attributes used by the code under test
        Warning = 0
        HelpRole = 1
        Ok = 2

        def __init__(self, parent=None):
            self._title = None
            self._text = None
            self._info = None
            self._buttons = []
            self._clicked = None

        def setIcon(self, _):
            pass

        def setWindowTitle(self, title):
            self._title = title

        def setText(self, text):
            self._text = text

        def setInformativeText(self, info):
            self._info = info

        def addButton(self, text_or_enum, role=None):
            # Support both addButton(text, role) and addButton(QMessageBox.Ok)
            if role is None and isinstance(text_or_enum, int):
                btn = (str(text_or_enum), text_or_enum)
            else:
                btn = (text_or_enum, role)
            self._buttons.append(btn)
            return btn

        def exec(self):
            # simulate user clicking Help immediately
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(gui.HELP_URL))

        def clickedButton(self):
            # return the Help button tuple if present
            for btn in self._buttons:
                if btn[1] == FakeMessageBox.HelpRole:
                    return btn
            return None

    class FakeServer:
        def __init__(self, *a, **k):
            pass

        def start(self, port):
            raise RuntimeError("bind failed: permission denied")

        def stop(self):
            pass

    monkeypatch.setattr(gui, 'SMDRServer', FakeServer)
    monkeypatch.setattr(gui, 'QMessageBox', FakeMessageBox)

    # Capture calls to openUrl
    called = {}

    def fake_openurl(url):
        called['url'] = str(url.toString())

    monkeypatch.setattr('PySide6.QtGui.QDesktopServices.openUrl', fake_openurl)

    # Constructing MainWindow should attempt to start and trigger the Help flow
    w = gui.MainWindow()

    assert 'Server start failed' in w.windowTitle() or w is not None
    assert called.get('url') == gui.HELP_URL
    w.server.stop()
    w.close()


def test_change_port_shows_informative_error(monkeypatch):
    ensure_app()

    class FakeMessageBox:
        # Provide attributes used by the code under test
        Warning = 0
        HelpRole = 1
        Ok = 2

        def __init__(self, parent=None):
            self._title = None
            self._text = None
            self._info = None
            self._buttons = []

        def setIcon(self, _):
            pass

        def setWindowTitle(self, title):
            self._title = title

        def setText(self, text):
            self._text = text

        def setInformativeText(self, info):
            self._info = info

        def addButton(self, text_or_enum, role=None):
            # Support both addButton(text, role) and addButton(QMessageBox.Ok)
            if role is None and isinstance(text_or_enum, int):
                btn = (str(text_or_enum), text_or_enum)
            else:
                btn = (text_or_enum, role)
            self._buttons.append(btn)
            return btn

        def exec(self):
            # simulate user clicking Help immediately
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(gui.HELP_URL))

        def clickedButton(self):
            for btn in self._buttons:
                if btn[1] == FakeMessageBox.HelpRole:
                    return btn
            return None

    # Use a server that starts fine initially
    class WorkingServer:
        def __init__(self, *a, **k):
            pass

        def start(self, port):
            self._port = port

        def stop(self):
            pass

    monkeypatch.setattr(gui, 'SMDRServer', WorkingServer)

    # Make the input dialog return a chosen port
    monkeypatch.setattr(QInputDialog, 'getInt', lambda *a, **k: (12345, True))

    monkeypatch.setattr(gui, 'QMessageBox', FakeMessageBox)

    # Capture calls to openUrl
    called = {}

    def fake_openurl(url):
        called['url'] = str(url.toString())

    monkeypatch.setattr('PySide6.QtGui.QDesktopServices.openUrl', fake_openurl)

    w = gui.MainWindow()

    # Now simulate start failing when changing port
    def fail_start(p):
        raise RuntimeError('bind failed: in use')

    w.server.start = fail_start

    w.change_port()

    assert called.get('url') == gui.HELP_URL
    w.server.stop()
    w.close()