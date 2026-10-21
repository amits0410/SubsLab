"""Check a packaged GUI stays alive through startup, without loading any model."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--seconds", type=float, default=5)
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    options = {}
    if sys.platform == "win32":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        options["startupinfo"] = startup
    process = subprocess.Popen([str(executable)], cwd=executable.parent,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, **options)
    try:
        time.sleep(args.seconds)
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(f"Packaged app exited early ({process.returncode}):\n{(stdout + stderr).decode(errors='replace')}")
        print(f"Startup smoke test passed: {executable.name}")
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()


if __name__ == "__main__":
    main()
