"""Public branding and deliberately stable installation/storage identities."""
from pathlib import Path
import sys

APP_NAME = "SubsLab"
APP_VERSION = "0.2.0"
STORAGE_ORGANIZATION = "SubsGen"
STORAGE_APPLICATION = "SubsGen Studio"
BUNDLE_IDENTIFIER = "ai.subsgen.studio"
ICON_STEM = "subslab"


def resource_path(filename: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / "assets" / filename


def application_data_path() -> Path:
    """Keep Qt's original platform-specific data location after the rename."""
    from PySide6.QtCore import QCoreApplication, QStandardPaths

    previous_name = QCoreApplication.applicationName()
    previous_organization = QCoreApplication.organizationName()
    try:
        QCoreApplication.setApplicationName(STORAGE_APPLICATION)
        QCoreApplication.setOrganizationName(STORAGE_ORGANIZATION)
        return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    finally:
        QCoreApplication.setApplicationName(previous_name)
        QCoreApplication.setOrganizationName(previous_organization)
