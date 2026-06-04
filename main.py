import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from settings import AppSettings
from themes import THEMES
from ui.main_window import MainWindow


def _resource(name: str) -> Path:
    """Locate a bundled resource — works in dev and in a PyInstaller package."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / name
    return Path(__file__).parent / name


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("词典编辑器")

    icon_path = _resource("icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    settings = AppSettings()

    # Apply saved theme palette before any window shows
    theme = THEMES.get(settings.theme, THEMES["light"])
    app.setPalette(theme.palette)

    window = MainWindow(settings)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
