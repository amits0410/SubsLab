# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from PyInstaller.compat import is_darwin

datas = [("assets/subsgen-studio.png", "assets")]
binaries, hiddenimports = [], []
app_icon = "assets/subsgen-studio.icns" if is_darwin else "assets/subsgen-studio.ico"
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
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SubsGen Studio",
    console=False,
    disable_windowed_traceback=False,
    icon=app_icon,
    target_arch="arm64" if is_darwin else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SubsGen Studio")
if is_darwin:
    app = BUNDLE(
        coll,
        name="SubsGen Studio.app",
        icon=app_icon,
        bundle_identifier="ai.subsgen.studio",
        info_plist={"LSMinimumSystemVersion": "12.0", "NSHighResolutionCapable": True},
    )
