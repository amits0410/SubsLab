# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from PyInstaller.compat import is_darwin, is_win
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(SPECPATH) / "src"))
from subsgen.branding import APP_NAME, APP_VERSION, BUNDLE_IDENTIFIER, ICON_STEM

datas = [(f"assets/{ICON_STEM}.png", "assets")]
binaries, hiddenimports = [], []
app_icon = f"assets/{ICON_STEM}.icns" if is_darwin else f"assets/{ICON_STEM}.ico"
packages = ["av", "faster_whisper", "ctranslate2"]
if is_darwin:
    packages.append("mlx_whisper")
for package in packages:
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hidden
    except Exception:
        pass

a = Analysis(
    ["src/subsgen/__main__.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["subsgen.ui", "subsgen.worker"],
    excludes=["pytest", "_pytest", "pytestqt"],
    noarchive=False,
)
if is_win:
    # Qt uses Windows' native, unversioned ICU API. A build host can also have
    # a different ICU on PATH (e.g. Poppler's versioned ICU); bundling that DLL
    # shadows the OS API and prevents QtCore/QtGui from loading at startup.
    a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() != "icuuc.dll"]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    disable_windowed_traceback=False,
    icon=app_icon,
    target_arch="arm64" if is_darwin else None,
    codesign_identity=(os.environ.get("SUBSLAB_CODESIGN_IDENTITY") or os.environ.get("SUBSGEN_CODESIGN_IDENTITY")) if is_darwin else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME)
if is_darwin:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=app_icon,
        bundle_identifier=BUNDLE_IDENTIFIER,
        info_plist={
            "LSMinimumSystemVersion": "14.0", "NSHighResolutionCapable": True,
            "CFBundleName": APP_NAME, "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": APP_VERSION, "CFBundleVersion": APP_VERSION,
        },
    )
