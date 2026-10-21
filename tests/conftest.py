"""Desktop tests must never alter a developer's saved workspace/preferences."""
import pytest
from PySide6.QtCore import QSettings


@pytest.fixture(autouse=True)
def isolated_desktop_settings(request, monkeypatch, tmp_path):
    if request.node.path.name not in {"test_ui.py", "test_studio.py"}:
        return
    from subsgen import ui

    monkeypatch.setattr(ui, "QSettings", lambda *_args: QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path / "app-data")
