"""Mount a release DMG, install its app in isolation, eject, and test startup."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dmg", type=Path)
    parser.add_argument("--seconds", type=float, default=8)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("The DMG installation check must run on macOS.")
    dmg = args.dmg.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="subslab-mac-install-") as temporary:
        root = Path(temporary)
        mount = root / "Disk Image"
        mount.mkdir()
        destination = root / "Applications"
        destination.mkdir()
        installed = destination / "SubsLab.app"
        subprocess.run(["hdiutil", "attach", str(dmg), "-readonly", "-nobrowse",
                        "-mountpoint", str(mount), "-quiet"], check=True)
        try:
            application_link = mount / "Applications"
            if not application_link.is_symlink() or os.readlink(application_link) != "/Applications":
                raise RuntimeError("DMG is missing its drag-to-Applications shortcut.")
            if not (mount / "READ-ME-FIRST.txt").is_file():
                raise RuntimeError("DMG is missing its installation instructions.")
            bundle = mount / "SubsLab.app"
            with (bundle / "Contents" / "Info.plist").open("rb") as stream:
                info = plistlib.load(stream)
            if info.get("CFBundleExecutable") != "SubsLab":
                raise RuntimeError("The app bundle declares an unexpected executable.")
            subprocess.run(["lipo", str(bundle / "Contents/MacOS/SubsLab"),
                            "-verify_arch", "arm64"], check=True)
            subprocess.run(["ditto", str(bundle), str(installed)], check=True)
        finally:
            detached = subprocess.run(["hdiutil", "detach", str(mount)], check=False)
            if detached.returncode:
                subprocess.run(["hdiutil", "detach", "-force", str(mount)], check=True)
        # Eject before launch so the installed copy cannot depend on mounted files.
        subprocess.run([sys.executable, str(Path(__file__).with_name("smoke_app.py")),
                        str(installed / "Contents/MacOS/SubsLab"),
                        "--seconds", str(args.seconds)], check=True)
        print("DMG installation, Apple Silicon architecture, disk ejection, and installed startup passed.")
        print(f"App version: {info.get('CFBundleShortVersionString')}; minimum macOS: {info.get('LSMinimumSystemVersion')}")


if __name__ == "__main__":
    main()
