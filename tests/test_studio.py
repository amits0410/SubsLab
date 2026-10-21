from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings, QThread, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from subsgen import ui
from subsgen.branding import APP_NAME, STORAGE_APPLICATION, STORAGE_ORGANIZATION, application_data_path
from subsgen.domain import SubtitleSegment, TranscriptionRequest
from subsgen.model_store import get_manifest


@pytest.fixture
def editor(qtbot):
    window = ui.MainWindow()
    def cleanup(widget):
        widget.job = None
        widget._set_dirty(False)
    qtbot.addWidget(window, before_close_func=cleanup)
    window.show()
    qtbot.wait(5)
    window.timeline = ui.Timeline([
        SubtitleSegment(f"cue-{i}", i * 3000, i * 3000 + 2000, f"Caption number {i}")
        for i in range(16)
    ])
    window.document.segments = window.timeline.segments
    window._render_segments()
    yield window
    window.job = None
    window._set_dirty(False)


def test_rename_keeps_legacy_data_and_settings_identity(qapp, qtbot, monkeypatch, tmp_path):
    old_name, old_org = qapp.applicationName(), qapp.organizationName()
    try:
        from PySide6.QtCore import QStandardPaths
        qapp.setOrganizationName(STORAGE_ORGANIZATION)
        qapp.setApplicationName(STORAGE_APPLICATION)
        original = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        qapp.setApplicationName(APP_NAME)
        assert application_data_path() == original
        assert qapp.applicationName() == APP_NAME
        seen = []

        def settings_factory(*args):
            seen.append(args)
            return QSettings(str(tmp_path / "legacy.ini"), QSettings.Format.IniFormat)

        monkeypatch.setattr(ui, "QSettings", settings_factory)
        window = ui.MainWindow()
        qtbot.addWidget(window)
        assert seen == [(STORAGE_ORGANIZATION, STORAGE_APPLICATION)]
        window.close()
    finally:
        qapp.setApplicationName(old_name)
        qapp.setOrganizationName(old_org)


def test_split_undo_reuses_other_cards_and_preserves_editor_cursor(editor, qtbot, monkeypatch):
    editor._select_segment(5)
    field = editor.cards[5].text_edit
    field.setFocus()
    cursor = field.textCursor()
    cursor.setPosition(2)
    cursor.setPosition(7, QTextCursor.MoveMode.KeepAnchor)
    field.setTextCursor(cursor)
    original = editor.cards[5]
    untouched = editor.cards[10]
    monkeypatch.setattr(editor.player, "position", lambda: 15500)
    editor._split_segment(5)
    assert editor.cards[5] is original
    assert editor.cards[11] is untouched
    editor.undo_action()
    assert editor.cards[5] is original
    assert editor.cards[10] is untouched
    assert editor.selected_index == 5
    assert field.textCursor().position() == 7
    assert field.textCursor().anchor() == 2
    qtbot.wait(5)
    assert QApplication.focusWidget() is field


def test_warning_edits_validate_one_cue_then_debounce_full_scan(editor, qtbot, monkeypatch):
    calls = []
    original = ui.analyze_readability

    def analyze(segments, settings):
        calls.append(len(segments))
        return original(segments, settings)

    monkeypatch.setattr(ui, "analyze_readability", analyze)
    editor.cards[4].text_edit.setPlainText("x" * 100)
    assert calls == [1]
    assert editor.cards[4].issue_label.text()
    assert editor.issue_count > 0
    qtbot.waitUntil(lambda: len(editor.timeline.segments) in calls)
    assert 4 in editor.warning_indexes


def test_unfixable_warning_stays_visible_and_preserves_wording(editor):
    wording = "These manually corrected words need more time to read"
    editor.timeline = ui.Timeline([
        SubtitleSegment("a", 0, 1000, "Before"),
        SubtitleSegment("b", 1000, 1100, wording),
        SubtitleSegment("c", 1100, 3000, "After"),
    ])
    editor.document.segments = editor.timeline.segments
    editor._render_segments()
    editor._select_segment(1)
    editor.fix_selected_segment()
    assert editor.timeline.segments[1].text == wording
    assert editor.issues_by_id["b"]
    assert not editor.issue_feedback.isHidden()
    assert "silence" in editor.issue_feedback.text()


def test_model_progress_remains_bound_to_running_model_and_large_counters(qtbot, tmp_path):
    dialog = ui.ModelManagerDialog(ui.ModelStore(tmp_path / "models"))
    qtbot.addWidget(dialog)
    manifest = get_manifest("ivrit-whisper-large-v3-turbo-ct2")
    dialog.active_manifest = manifest
    dialog.list.setCurrentRow(0)
    dialog._model_status_changed("Checking files")
    assert manifest.display_name in dialog.status.text()
    thread = ui.ModelInstallThread(dialog.store, manifest)
    received = []
    thread.downloadProgress.connect(lambda current, total, name: received.append((current, total)))
    thread._report_download(4_000_000_000, 8_000_000_000, "weights.bin")
    assert received == [(4_000_000_000, 8_000_000_000)]
    dialog._download_progress_changed(*received[0], "weights.bin")
    assert dialog.download_progress.value() == 50
    assert manifest.display_name in dialog.status.text()


def test_stale_cancel_callback_cannot_kill_a_new_job(editor):
    killed = []
    editor.job = SimpleNamespace(terminate=lambda: killed.append(True))
    editor._cancel_generation = 3
    editor._force_cancel(2)
    assert not killed
    assert editor.job is not None


def test_job_progress_tracks_elapsed_and_actual_device(editor, monkeypatch):
    editor.active_manifest = get_manifest("whisper-small-ct2")
    editor.active_request = TranscriptionRequest(Path("clip.wav"), "transcribe", "en")
    monkeypatch.setattr(ui.time, "monotonic", lambda: 125)
    editor._job_started_at = 60
    editor._set_transcription_progress("CUDA initialization failed; loading CPU int8 fallback…", None)
    assert editor.progress.maximum() == 0
    assert "Device: CPU" in editor.progress_details.text()
    assert "01:05" in editor.progress_details.text()
    assert "Whisper Small" in editor.progress_details.text()


def test_workspace_persists_and_cards_fit_compact_window(editor, qtbot):
    editor.resize(1024, 720)
    editor.setup_toggle.setChecked(False)
    editor.splitter.setSizes([380, 600])
    editor._save_workspace()
    editor.resize(1300, 850)
    editor.setup_toggle.setChecked(True)
    editor._restore_workspace()
    qtbot.wait(5)
    assert editor.width() == 1024
    assert editor.height() == 720
    assert editor.setup_panel.isHidden()
    assert editor.cards_scroll.horizontalScrollBar().maximum() == 0


def test_playback_label_and_rtl_timestamp_direction(editor):
    editor._playback_state_changed(ui.QMediaPlayer.PlaybackState.PlayingState)
    assert editor.play_button.text() == "Pause"
    editor._playback_state_changed(ui.QMediaPlayer.PlaybackState.PausedState)
    assert editor.play_button.text() == "Play"
    editor.cards[0].text_edit.setPlainText("שלום לעולם")
    assert editor.cards[0].text_edit.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert editor.cards[0].start_edit.layoutDirection() == Qt.LayoutDirection.LeftToRight


def test_save_stops_recovery_timer_and_undo_remains_available(editor, monkeypatch, tmp_path):
    destination = tmp_path / "saved.srt"
    editor.cards[0].text_edit.setPlainText("Edited before save")
    monkeypatch.setattr(ui.QFileDialog, "getSaveFileName", lambda *_args: (str(destination), ""))
    assert editor.save_document()
    assert destination.is_file()
    assert not editor.recovery_timer.isActive()
    assert not editor.dirty
    editor.undo_action()
    assert editor.timeline.segments[0].text == "Caption number 0"


def test_reflow_preserves_words_and_existing_cue_identity(editor):
    first = editor.cards[0]
    original_words = " ".join(item.text for item in editor.timeline.segments).split()
    editor.reflow_current_subtitles()
    assert " ".join(item.text for item in editor.timeline.segments).split() == original_words
    assert editor.cards[0] is first
    editor.undo_action()
    assert " ".join(item.text for item in editor.timeline.segments).split() == original_words


def test_shortcut_reference_uses_registered_actions_and_platform_names(editor, monkeypatch):
    messages = []
    monkeypatch.setattr(ui.QMessageBox, "information", lambda _parent, _title, message: messages.append(message))
    editor.show_shortcuts()
    for action in editor.actions.values():
        if not action.shortcut().isEmpty():
            assert action.text() in messages[0]


def test_save_repair_is_undoable_and_vtt_export_validates(editor, monkeypatch, tmp_path):
    editor.timeline.segments[0].end_ms = 3500
    destination = tmp_path / "validated.vtt"
    monkeypatch.setattr(ui.QFileDialog, "getSaveFileName", lambda *_args: (str(destination), "WebVTT subtitles (*.vtt)"))
    editor.export_additional_format()
    assert destination.read_text(encoding="utf-8").startswith("WEBVTT")
    assert not ui.structural_issues(editor.timeline.segments)
    assert editor.undo_stack


def test_undo_and_redo_shortcuts_work_while_editing_text(editor, qtbot):
    field = editor.cards[0].text_edit
    field.setFocus()
    field.setPlainText("My manual edit")
    qtbot.keyClick(field, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert editor.timeline.segments[0].text == "Caption number 0"
    editor.actions["redo"].trigger()
    assert editor.timeline.segments[0].text == "My manual edit"


def test_window_close_waits_for_cooperative_waveform_shutdown(editor, qtbot):
    class CooperativeThread(QThread):
        def run(self):
            while not self.isInterruptionRequested():
                self.msleep(2)

    thread = CooperativeThread(editor)
    editor._waveform_threads.append(thread)
    thread.finished.connect(lambda: editor._waveform_thread_finished(thread))
    thread.start()
    qtbot.waitUntil(thread.isRunning)
    editor._set_dirty(False)
    editor.close()
    qtbot.waitUntil(lambda: not editor.isVisible())
    assert not editor._waveform_threads
