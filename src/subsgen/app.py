from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path


def application_icon_path() -> Path:
    """Return the icon location in both source and PyInstaller builds."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return bundle_root / "assets" / "subsgen-studio.png"


def ensure_standard_streams() -> None:
    """Give windowed PyInstaller builds writable streams for native libraries.

    PyInstaller deliberately sets stdout/stderr to None for console-free Windows
    applications. Hugging Face/tqdm and some media libraries still call write(),
    so a null sink is safer than allowing a background download to crash.
    """
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main() -> int:
    ensure_standard_streams()
    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is not installed. Run: python -m pip install -e .", file=sys.stderr)
        return 2

    from .ui import MainWindow

    multiprocessing.freeze_support()
    application = QApplication(sys.argv)
    application.setApplicationName("SubsGen Studio")
    application.setOrganizationName("SubsGen")
    application.setStyle("Fusion")
    icon_path = application_icon_path()
    if icon_path.is_file():
        application.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    return application.exec()
