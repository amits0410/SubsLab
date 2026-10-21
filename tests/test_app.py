import sys
from pathlib import Path

from subsgen.app import application_icon_path, ensure_standard_streams


def test_application_icon_is_available_from_source_tree():
    icon_path = application_icon_path()
    assert icon_path == Path(__file__).resolve().parents[1] / "assets" / "subslab.png"
    assert icon_path.is_file()


def test_windowed_build_gets_writable_standard_streams():
    original_stdout, original_stderr = sys.stdout, sys.stderr
    try:
        sys.stdout = None
        sys.stderr = None
        ensure_standard_streams()
        assert sys.stdout is not None
        assert sys.stderr is not None
        assert sys.stdout.write("download progress") == len("download progress")
        assert sys.stderr.write("download warning") == len("download warning")
    finally:
        if sys.stdout is not original_stdout:
            sys.stdout.close()
        if sys.stderr is not original_stderr:
            sys.stderr.close()
        sys.stdout, sys.stderr = original_stdout, original_stderr
