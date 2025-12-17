from smdr import gui
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication


def ensure_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_tray_icon_uses_bundled_resource(tmp_path, monkeypatch):
    ensure_app()
    # Create resources/icon.png in a temporary folder
    resources = tmp_path / 'resources'
    resources.mkdir()
    icon_file = resources / 'icon.png'
    # Create a valid tiny PNG using QPixmap so Qt can load it reliably
    from PySide6.QtGui import QPixmap, QColor
    pix = QPixmap(16, 16)
    pix.fill(QColor('blue'))
    # QPixmap.save writes a valid PNG that Qt can later read via QIcon
    assert pix.save(str(icon_file), 'PNG'), 'Failed to write icon file'

    # Simulate frozen bundle by setting sys._MEIPASS to tmp_path and sys.frozen True
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)

    w = gui.MainWindow()

    # The tray's icon should be non-null because we provided resources/icon.png
    assert not w.tray.icon().isNull(), "Tray icon should be set from bundled resource"

    w.server.stop()
    w.close()