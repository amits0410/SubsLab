from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path

from .branding import APP_NAME, APP_VERSION, ICON_STEM, STORAGE_ORGANIZATION, resource_path


def application_icon_path() -> Path:
    """Return the icon location in both source and PyInstaller builds."""
    return resource_path(f"{ICON_STEM}.png")


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
    except ImportError as exc:
        instruction = "Reinstall the application or rebuild its bundled libraries." if getattr(sys, "frozen", False) else "Run: python -m pip install -e ."
        print(f"{APP_NAME} could not load its user interface: {exc}\n{instruction}", file=sys.stderr)
        return 2

    from .ui import MainWindow

    multiprocessing.freeze_support()
    application = QApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    application.setApplicationDisplayName(APP_NAME)
    application.setApplicationVersion(APP_VERSION)
    application.setOrganizationName(STORAGE_ORGANIZATION)
    from .theme import apply_theme
    apply_theme(application)
    icon_path = application_icon_path()
    if icon_path.is_file():
        application.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    return application.exec()
