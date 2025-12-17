import pytest
from smdr import gui
from PySide6.QtWidgets import QApplication, QMessageBox


def ensure_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_get_port_owners_and_kill(monkeypatch):
    ensure_app()

    fake_netstat = "  TCP    0.0.0.0:7000    0.0.0.0:0    LISTENING    1234\r\n"
    fake_tasklist = '"smdr.exe","1234","Console","1","10,000 K"\r\n'

    calls = {}

    def fake_check_output(cmd, text=True, stderr=None):
        if cmd[0] == 'netstat':
            return fake_netstat
        if cmd[0] == 'tasklist':
            return fake_tasklist
        return ''

    monkeypatch.setattr('subprocess.check_output', fake_check_output)

    w = gui.MainWindow()

    owners = w._get_port_owners(7000)
    assert len(owners) == 1
    assert owners[0]['pid'] == 1234
    assert owners[0]['name'] == 'smdr.exe'

    # test kill pids uses taskkill
    run_calls = []

    def fake_run(cmd, stdout=None, stderr=None):
        run_calls.append(cmd)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr('subprocess.run', fake_run)

    assert w._kill_pids([1234]) is True
    assert any('taskkill' in c[0].lower() for c in run_calls)

    if hasattr(w, 'server') and w.server:
        w.server.stop()
    w.hide()


def test_show_port_in_use_dialog_stops(monkeypatch):
    ensure_app()

    w = gui.MainWindow()

    owners = [{'pid': 1111, 'name': 'test.exe'}]

    # Fake QMessageBox so that clicking Stop Listener is simulated
    class FakeMB:
        Warning = 0
        AcceptRole = 1
        HelpRole = 2
        Cancel = 3

        def __init__(self, parent=None):
            self._buttons = []
            self._clicked = None
            self._info = None
            self._title = None

        def setIcon(self, _):
            pass

        def setWindowTitle(self, t):
            self._title = t

        def setText(self, t):
            self._text = t

        def setInformativeText(self, t):
            self._info = t

        def addButton(self, txt, role=None):
            btn = (txt, role)
            self._buttons.append(btn)
            return btn

        def exec(self):
            # simulate clicking Stop Listener
            for b in self._buttons:
                if b[0] == 'Stop Listener':
                    self._clicked = b

        def clickedButton(self):
            return self._clicked

    monkeypatch.setattr('PySide6.QtWidgets.QMessageBox', FakeMB)

    killed = {}

    def fake_kill(pids):
        killed['p'] = pids
        return True

    monkeypatch.setattr(gui.MainWindow, '_kill_pids', lambda self, p: fake_kill(p))

    stopped = w._show_port_in_use_dialog(7000, owners)
    assert killed['p'] == [1111]
    assert stopped is True
    if hasattr(w, 'server') and w.server:
        w.server.stop()
    w.hide()
