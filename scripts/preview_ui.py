"""Render isolated preview states without reading personal models or recovery."""
from pathlib import Path
import argparse
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from subsgen import ui
from subsgen.branding import APP_NAME
from subsgen.domain import SubtitleSegment, TranscriptionRequest
from subsgen.model_store import get_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="build-ui-previews")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    ui._data_root = lambda: output / "isolated-data"
    ui.QSettings = lambda *_: QSettings(str(output / "preview.ini"), QSettings.Format.IniFormat)
    window = ui.MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.resize(1380, 900)
    window.show()
    app.processEvents()
    window.grab().save(str(output / "01-empty.png"))
    window.document.media_path = Path("Interview — studio session.wav")
    window.media_label.setText(window.document.media_path.name)
    window.timeline = ui.Timeline([
        SubtitleSegment("intro", 0, 3300, "Every story starts with a conversation."),
        SubtitleSegment("hebrew", 3500, 7800, "כל סיפור מתחיל בשיחה.\nבואו נהפוך אותה לכתוביות מדויקות."),
        SubtitleSegment("fast", 8100, 9000, "A fast sentence that needs more time to read comfortably."),
        SubtitleSegment("close", 9500, 13200, "Your words. Your timing.\nAll on your computer."),
    ])
    window.document.segments = window.timeline.segments
    window.waveform.set_waveform([.15 + abs(math.sin(i * .17)) * .65 for i in range(1000)], 15000)
    window._has_video_changed(False)
    window.setup_toggle.setChecked(False)
    window._render_segments()
    window._select_segment(1)
    window._position_changed(4500)
    app.processEvents()
    window.grab().save(str(output / "02-editor.png"))
    window.resize(1024, 720)
    app.processEvents()
    window.grab().save(str(output / "03-compact.png"))
    print(f"Compact size: {window.width()}x{window.height()}; minimum hint: {window.minimumSizeHint().width()}x{window.minimumSizeHint().height()}")
    window.resize(1380, 900)
    window.active_manifest = get_manifest("ivrit-whisper-large-v3-turbo-ct2")
    window.active_request = TranscriptionRequest(Path("interview.wav"), "transcribe", "he")
    window._set_transcription_progress("Transcribing on CPU…", .42)
    app.processEvents()
    window.grab().save(str(output / "04-progress.png"))
    window._set_dirty(False)
    window.close()
    print(output)


if __name__ == "__main__":
    main()
