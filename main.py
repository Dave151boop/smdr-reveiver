"""Entry point for the SMDR receiver GUI app."""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from smdr.gui import MainWindow
from pathlib import Path


def _resource_path(rel_path: str) -> Path:
    """Return an absolute path to a resource working both in source and bundled mode.

    PyInstaller (and similar bundlers) set `sys._MEIPASS` to the temporary extraction
    folder when running in a onefile bundle. When running from source, resources are
    available relative to the project root.
    """
    import sys
    if getattr(sys, 'frozen', False):
        base = Path(getattr(sys, '_MEIPASS', Path.cwd()))
    else:
        base = Path.cwd()
    return base / rel_path


def main():
    app = QApplication(sys.argv)
    # prefer a packaged icon if present
    ico_path = _resource_path('resources/icon.ico')
    if not ico_path.exists():
        ico_path = _resource_path('resources/icon.png')
    if ico_path.exists():
        try:
            app.setWindowIcon(QIcon(str(ico_path)))
        except Exception:
            pass

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
