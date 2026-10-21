from pathlib import Path
import time

from subsgen import ui
from subsgen.domain import SubtitleSegment, TranscriptionMode, TranscriptionRequest
from subsgen.model_store import get_manifest
from PySide6.QtWidgets import QLineEdit


def test_main_window_smoke(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    assert window.windowTitle().endswith("SubsLab")
    assert window.mode_combo.count() == 2
    assert window.language_combo.findData("he") >= 0
    qtbot.waitUntil(lambda: window.cards_layout.count() == 1)
    assert window.cards_layout.count() == 1


def test_model_manager_lists_platform_models(qtbot, tmp_path):
    dialog = ui.ModelManagerDialog(ui.ModelStore(tmp_path / "models"))
    qtbot.addWidget(dialog)
    assert dialog.list.count() >= 2
    dialog._download_progress_changed(50, 100, "folder/model.bin")
    assert dialog.download_progress.value() == 50
    assert "model.bin" in dialog.download_progress.format()


def test_model_install_thread_can_cancel(qtbot):
    class SlowStore:
        def install(self, _manifest, status, download_progress):
            status("Preparing")
            while True:
                download_progress(1, 100, "model.bin")
                time.sleep(0.01)

    thread = ui.ModelInstallThread(SlowStore(), object())
    with qtbot.waitSignal(thread.cancelled, timeout=2000):
        thread.start()
        qtbot.waitUntil(thread.isRunning)
        thread.cancel()
    thread.wait(2000)
    assert not thread.isRunning()


def test_active_card_boundaries_gap_and_audio_preview(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([
        SubtitleSegment("a", 100, 200, "שלום"),
        SubtitleSegment("b", 300, 400, "Second"),
    ])
    window.document.segments = window.timeline.segments
    window._render_segments()
    window._has_video_changed(False)
    window._position_changed(100)
    assert window.active_index == 0
    assert window.audio_subtitle_panel.text() == "שלום"
    assert window.audio_subtitle_panel.layoutDirection() == ui.Qt.LayoutDirection.RightToLeft
    window._position_changed(200)
    assert window.active_index is None
    assert window.subtitle_overlay.text() == ""


def test_video_cc_toggle_hides_preview(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([SubtitleSegment("a", 0, 1000, "Preview")])
    window.document.segments = window.timeline.segments
    window._render_segments()
    window._has_video_changed(True)
    window._position_changed(10)
    assert window.subtitle_overlay.text() == "Preview"
    assert window.video.overlay_proxy.isVisible()
    window.cc_button.setChecked(False)
    assert window.subtitle_overlay.text() == ""
    assert not window.video.overlay_proxy.isVisible()


def test_shortcuts_disable_while_typing(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    editor = QLineEdit(window)
    qtbot.addWidget(window)
    window._focus_changed(None, editor)
    assert window._typing_sensitive_shortcuts
    assert all(not shortcut.isEnabled() for shortcut in window._typing_sensitive_shortcuts)
    window._focus_changed(editor, window.play_button)
    assert all(shortcut.isEnabled() for shortcut in window._typing_sensitive_shortcuts)


def test_warning_summary_and_navigation(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([SubtitleSegment("a", 0, 100, "x" * 100)])
    window.document.segments = window.timeline.segments
    window._render_segments()
    assert window.warning_indexes == [0]
    assert "warning" in window.warning_summary.text()
    window._navigate_warning(1)
    assert window.selected_index == 0


def test_fix_segment_preserves_manual_text_exactly_and_clears_timing_warning(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    original = "Manually corrected subtitle"
    window.timeline = ui.Timeline([SubtitleSegment("a", 0, 100, original)])
    window.document.segments = window.timeline.segments
    window.document.source_words = [ui.TimedWord("Incorrect", 0, 50), ui.TimedWord("original", 50, 100)]
    window._render_segments()
    window._select_segment(0)
    assert window.fix_segment_button.isEnabled()
    window.fix_selected_segment()
    assert len(window.timeline.segments) == 1
    assert window.timeline.segments[0].text == original
    assert window.issue_count == 0
    assert window.undo_fix_button.isEnabled()
    window.undo_last_fix()
    assert window.timeline.segments[0].text == original
    assert (window.timeline.segments[0].start_ms, window.timeline.segments[0].end_ms) == (0, 100)
    assert window.issue_count > 0
    assert not window.undo_fix_button.isEnabled()
    window._set_dirty(False)


def test_progress_details_identify_model_backend_task_and_stage(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.active_manifest = get_manifest("whisper-small-ct2")
    window.active_request = TranscriptionRequest(tmp_path / "media.wav", TranscriptionMode.TRANSLATE, "he")
    window._set_transcription_progress("Decoding audio…", 0.25)
    details = window.progress_details.text()
    assert "Whisper Small" in details
    assert "faster-whisper" in details
    assert "translate" in details
    assert "Decoding audio" in details
    assert window.progress.value() == 25


def test_video_overlay_is_a_child_of_video_surface(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    assert window.player.videoOutput() is window.video.video_item
    assert window.video.overlay_proxy.zValue() > window.video.video_item.zValue()
    window.video.resize(640, 360)
    window.video.update_overlay_layout()
    assert window.video.overlay_proxy.pos().y() < window.video.height()


def test_fix_segment_uses_first_warning_when_an_unwarned_cue_is_selected(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    warned = "Corrected wording"
    window.timeline = ui.Timeline([
        SubtitleSegment("ok", 0, 2000, "Fine"),
        SubtitleSegment("bad", 3000, 3100, warned),
    ])
    window.document.segments = window.timeline.segments
    window._render_segments()
    window._select_segment(0)
    assert window.fix_segment_button.isEnabled()
    window.fix_selected_segment()
    assert window.timeline.segments[1].text == warned
    assert window.timeline.segments[0].text == "Fine"
    assert window.issue_count == 0
    window._set_dirty(False)


def test_manual_text_changes_recalculate_warnings_live(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([SubtitleSegment("a", 0, 2000, "Fine")])
    window.document.segments = window.timeline.segments
    window._render_segments()
    assert window.issue_count == 0
    window.cards[0].text_edit.setPlainText("x" * 100)
    assert window.issue_count > 0
    window.cards[0].text_edit.setPlainText("Fine")
    assert window.issue_count == 0
    window._set_dirty(False)


def test_segment_text_supports_hebrew_arabic_and_ltr_direction(qtbot):
    hebrew = ui.SegmentCard(0, SubtitleSegment("he", 0, 1000, "שלום עולם"))
    arabic = ui.SegmentCard(1, SubtitleSegment("ar", 1000, 2000, "مرحبا بالعالم"))
    english = ui.SegmentCard(2, SubtitleSegment("en", 2000, 3000, "Hello world"))
    for card in (hebrew, arabic, english):
        qtbot.addWidget(card)
    assert hebrew.text_edit.layoutDirection() == ui.Qt.LayoutDirection.RightToLeft
    assert arabic.text_edit.layoutDirection() == ui.Qt.LayoutDirection.RightToLeft
    assert english.text_edit.layoutDirection() == ui.Qt.LayoutDirection.LeftToRight
    assert arabic.text_edit.document().defaultTextOption().alignment() & ui.Qt.AlignmentFlag.AlignRight
    arabic_block = ui.QTextCursor(arabic.text_edit.document().firstBlock()).blockFormat()
    hebrew_block = ui.QTextCursor(hebrew.text_edit.document().firstBlock()).blockFormat()
    assert arabic_block.layoutDirection() == ui.Qt.LayoutDirection.RightToLeft
    assert hebrew_block.layoutDirection() == ui.Qt.LayoutDirection.RightToLeft


def test_mixed_caption_uses_dominant_rtl_direction(qtbot):
    card = ui.SegmentCard(0, SubtitleSegment("mixed", 0, 1000, "OpenAI שלום עולם יפה"))
    qtbot.addWidget(card)
    assert card.text_edit.layoutDirection() == ui.Qt.LayoutDirection.RightToLeft


def test_toolbar_context_menu_is_disabled(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    toolbar = window.findChild(ui.QToolBar)
    assert toolbar.contextMenuPolicy() == ui.Qt.ContextMenuPolicy.PreventContextMenu
    assert window.contextMenuPolicy() == ui.Qt.ContextMenuPolicy.PreventContextMenu
    assert not toolbar.toggleViewAction().isVisible()
    assert not toolbar.toggleViewAction().isEnabled()
    assert window.createPopupMenu() is None


def test_manual_edit_and_fix_are_independently_undoable_and_redoable(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([SubtitleSegment("a", 0, 100, "Corrected text")])
    window.document.segments = window.timeline.segments
    window._render_segments()
    window.fix_selected_segment()
    fixed_range = (window.timeline.segments[0].start_ms, window.timeline.segments[0].end_ms)
    assert window.undo_stack
    window.cards[0].text_edit.setPlainText("Newer manual edit")
    window._commit_pending_text_edit()
    assert len(window.undo_stack) == 2
    window.undo_action()
    assert window.timeline.segments[0].text == "Corrected text"
    assert (window.timeline.segments[0].start_ms, window.timeline.segments[0].end_ms) == fixed_range
    window.undo_action()
    assert (window.timeline.segments[0].start_ms, window.timeline.segments[0].end_ms) == (0, 100)
    window.redo_action()
    assert (window.timeline.segments[0].start_ms, window.timeline.segments[0].end_ms) == fixed_range
    window.redo_action()
    assert window.timeline.segments[0].text == "Newer manual edit"
    window._set_dirty(False)


def test_fix_button_click_preserves_live_manual_text_and_undo_restores_timing(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([SubtitleSegment("a", 0, 100, "Original ASR")])
    window.document.segments = window.timeline.segments
    window.document.source_words = [ui.TimedWord("Original", 0, 50), ui.TimedWord("ASR", 50, 100)]
    window._render_segments()
    manual = "תיקון ידני שנשמר"
    window.cards[0].text_edit.setPlainText(manual)
    assert window.timeline.segments[0].text == manual
    qtbot.mouseClick(window.fix_segment_button, ui.Qt.MouseButton.LeftButton)
    assert window.timeline.segments[0].text == manual
    assert window.issue_count == 0
    assert window.undo_fix_button.isEnabled()
    qtbot.mouseClick(window.undo_fix_button, ui.Qt.MouseButton.LeftButton)
    assert window.timeline.segments[0].text == manual
    assert (window.timeline.segments[0].start_ms, window.timeline.segments[0].end_ms) == (0, 100)
    window._set_dirty(False)


def test_fix_all_click_preserves_every_manual_edit_and_can_be_undone(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([
        SubtitleSegment("a", 0, 100, "Old one"),
        SubtitleSegment("b", 2000, 2100, "Old two"),
    ])
    window.document.segments = window.timeline.segments
    window._render_segments()
    edited = ["עריכה ידנית אחת", "עריכה ידנית שנייה"]
    window.cards[0].text_edit.setPlainText(edited[0])
    window.cards[1].text_edit.setPlainText(edited[1])
    qtbot.mouseClick(window.fix_all_button, ui.Qt.MouseButton.LeftButton)
    assert [item.text for item in window.timeline.segments] == edited
    assert window.issue_count == 0
    qtbot.mouseClick(window.undo_fix_button, ui.Qt.MouseButton.LeftButton)
    assert [item.text for item in window.timeline.segments] == edited
    assert [(item.start_ms, item.end_ms) for item in window.timeline.segments] == [(0, 100), (2000, 2100)]
    window._set_dirty(False)


def test_reflow_uses_edited_text_and_supports_undo_redo(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    edited = "These are manually corrected words that must survive the complete subtitle reflow operation exactly"
    original = SubtitleSegment("a", 0, 8000, edited)
    window.timeline = ui.Timeline([original])
    window.document.segments = window.timeline.segments
    window.document.source_words = [ui.TimedWord("wrong", 0, 4000), ui.TimedWord("original", 4000, 8000)]
    window._render_segments()
    window.reflow_current_subtitles()
    reflowed = [(item.start_ms, item.end_ms, item.text) for item in window.timeline.segments]
    assert " ".join(item.text.replace("\n", " ") for item in window.timeline.segments).split() == edited.split()
    assert "wrong" not in " ".join(item.text for item in window.timeline.segments)
    window.undo_action()
    assert len(window.timeline.segments) == 1
    assert window.timeline.segments[0].text == edited
    assert (window.timeline.segments[0].start_ms, window.timeline.segments[0].end_ms) == (0, 8000)
    window.redo_action()
    assert [(item.start_ms, item.end_ms, item.text) for item in window.timeline.segments] == reflowed
    window._set_dirty(False)


def test_nudge_and_delete_support_undo_redo(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([
        SubtitleSegment("a", 100, 1000, "First"),
        SubtitleSegment("b", 2000, 3000, "Second"),
    ])
    window.document.segments = window.timeline.segments
    window._render_segments()
    window._nudge_segment(0, "start", 100)
    assert window.timeline.segments[0].start_ms == 200
    window.undo_action()
    assert window.timeline.segments[0].start_ms == 100
    window.redo_action()
    assert window.timeline.segments[0].start_ms == 200
    window._delete_segment(1)
    assert len(window.timeline.segments) == 1
    window.undo_action()
    assert [item.text for item in window.timeline.segments] == ["First", "Second"]
    window.redo_action()
    assert len(window.timeline.segments) == 1
    window._set_dirty(False)


def test_child_editor_focus_selects_its_card_and_edit_does_not_rebuild_cards(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([
        SubtitleSegment("a", 0, 1000, "First"),
        SubtitleSegment("b", 1500, 2500, "Second"),
    ])
    window.document.segments = window.timeline.segments
    window._render_segments()
    original_cards = tuple(window.cards)
    window._select_segment(0)
    window.cards[1].text_edit.editingStarted.emit()
    assert window.selected_index == 1
    window.cards[1].text_edit.setPlainText("Edited second")
    window.cards[1].text_edit.editingFinished.emit()
    assert tuple(window.cards) == original_cards
    assert window.timeline.segments[1].text == "Edited second"
    window._set_dirty(False)


def test_clicking_any_child_control_gives_card_yellow_selection(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([
        SubtitleSegment("a", 0, 1000, "First"),
        SubtitleSegment("b", 1500, 2500, "Second"),
    ])
    window.document.segments = window.timeline.segments
    window._render_segments()
    window._select_segment(0)
    qtbot.mouseClick(window.cards[1].text_edit.viewport(), ui.Qt.MouseButton.LeftButton)
    assert window.selected_index == 1
    assert window.cards[1].property("selected") is True
    assert window.cards[0].property("selected") is False


def test_media_duration_repair_is_undoable(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([SubtitleSegment("a", 500, 2000, "Long")])
    window.document.segments = window.timeline.segments
    window._render_segments()
    window._duration_changed(1000)
    assert window.timeline.segments[0].end_ms == 1000
    assert window.undo_stack
    window.undo_action()
    assert window.timeline.segments[0].end_ms == 2000
    window._set_dirty(False)


def test_find_replace_all_rechecks_quality_and_is_undoable(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([
        SubtitleSegment("a", 0, 2000, "foo first"),
        SubtitleSegment("b", 2500, 4500, "Foo second foo"),
    ])
    window.document.segments = window.timeline.segments
    window._render_segments()
    assert window.find_next_text("foo")
    assert window.selected_index == 0
    count = window.replace_all_text("foo", "corrected")
    assert count == 3
    assert [item.text for item in window.timeline.segments] == ["corrected first", "corrected second corrected"]
    window.undo_action()
    assert [item.text for item in window.timeline.segments] == ["foo first", "Foo second foo"]
    window._set_dirty(False)


def test_playback_speed_and_quality_report(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.speed_combo.setCurrentIndex(window.speed_combo.findData(1.5))
    assert window.player.playbackRate() == 1.5
    window.timeline = ui.Timeline([SubtitleSegment("a", 0, 100, "x" * 100)])
    window.document.segments = window.timeline.segments
    window._render_segments()
    report = ui.QualityReportDialog(window)
    qtbot.addWidget(report)
    assert report.list.count() >= 1
    assert "Cue 1" in report.list.item(0).text()


def test_loop_selected_cue_sets_and_updates_loop_boundaries(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    window.timeline = ui.Timeline([
        SubtitleSegment("a", 100, 900, "First"),
        SubtitleSegment("b", 1200, 2000, "Second"),
    ])
    window.document.segments = window.timeline.segments
    window._render_segments()
    window._select_segment(0)
    window.loop_button.setChecked(True)
    assert (window.segment_start_ms, window.segment_stop_ms) == (100, 900)
    window._select_segment(1)
    assert (window.segment_start_ms, window.segment_stop_ms) == (1200, 2000)
    window.loop_button.setChecked(False)
    assert window.segment_start_ms is None
    assert window.segment_stop_ms is None


def test_recovery_round_trips_editor_undo_history(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_data_root", lambda: tmp_path)
    window = ui.MainWindow()
    qtbot.addWidget(window)
    qtbot.wait(1)
    window.timeline = ui.Timeline([SubtitleSegment("a", 0, 1000, "Before")])
    window.document.segments = window.timeline.segments
    window._render_segments()
    window.cards[0].text_edit.setPlainText("After")
    window._commit_pending_text_edit()
    window._write_recovery()
    state = window.recovery.load_editor_state()
    assert state["undo"]
    restored = window._snapshot_from_dict(state["undo"][-1])
    assert restored.segments[0].text == "Before"
    window.recovery.clear()
    window._set_dirty(False)
