from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import re
import time

from PySide6.QtCore import QEvent, QSettings, QThread, QTimer, QUrl, Signal, Qt
from PySide6.QtGui import (
    QCloseEvent,
    QContextMenuEvent,
    QKeySequence,
    QShortcut,
    QTextCursor,
)
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .domain import (
    SubtitleDocument,
    SubtitleLayoutSettings,
    SubtitleSegment,
    TimedWord,
    TranscriptionMode,
    TranscriptionRequest,
)
from .direction import is_rtl_text
from .media import decode_waveform
from .model_store import ModelStore, available_models, get_manifest, route_request
from .recovery import RecoveryStore
from .srt import contains_hebrew, format_timestamp, load_srt, parse_timestamp, save_ass, save_srt, save_vtt
from .readability import analyze_readability, required_reading_duration_ms, structural_issues
from .reflow import fallback_words, fit_readability_durations, reflow_subtitles
from .timeline import NUDGE_MS, Timeline, TimelineError, active_segment_index, repair_segments, retime_segment_duration
from .worker import TranscriptionJob, start_job
from .actions import SHORTCUTS, build_actions, native_shortcut
from .branding import APP_NAME, STORAGE_APPLICATION, STORAGE_ORGANIZATION, application_data_path
from .workspace import build_workspace
from .theme import apply_theme

MEDIA_FILTER = "Media (*.mp4 *.mov *.m4v *.mp3 *.wav *.m4a);;All files (*)"
SRT_FILTER = "SubRip subtitles (*.srt)"


@dataclass(slots=True)
class EditorSnapshot:
    segments: list[SubtitleSegment]
    source_words: list[TimedWord]
    selected_id: str | None = field(compare=False)
    layout_settings: SubtitleLayoutSettings
    view_state: dict = field(default_factory=dict, compare=False)


def _data_root() -> Path:
    return application_data_path()


from .ui_widgets import EditableText, TimestampEdit, SubtitleVideoWidget, FixedToolBar, SegmentCard


class ReadabilitySettingsDialog(QDialog):
    def __init__(self, settings: SubtitleLayoutSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Readability Settings")
        self.settings = SubtitleLayoutSettings.from_dict(settings.to_dict())
        self.reflow_requested = False
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.max_chars = QSpinBox(); self.max_chars.setRange(10, 100)
        self.max_lines = QSpinBox(); self.max_lines.setRange(1, 4)
        self.max_cps = QDoubleSpinBox(); self.max_cps.setRange(5, 60); self.max_cps.setDecimals(1)
        self.max_wpm = QDoubleSpinBox(); self.max_wpm.setRange(60, 400); self.max_wpm.setDecimals(0)
        self.min_duration = QDoubleSpinBox(); self.min_duration.setRange(0.05, 10); self.min_duration.setDecimals(2); self.min_duration.setSuffix(" s")
        self.max_duration = QDoubleSpinBox(); self.max_duration.setRange(0.1, 30); self.max_duration.setDecimals(2); self.max_duration.setSuffix(" s")
        self.pause_break = QSpinBox(); self.pause_break.setRange(100, 3000); self.pause_break.setSuffix(" ms")
        for label, widget in (
            ("Maximum characters per line", self.max_chars), ("Maximum lines", self.max_lines),
            ("Maximum characters per second", self.max_cps), ("Maximum words per minute", self.max_wpm),
            ("Minimum recommended duration", self.min_duration), ("Maximum recommended duration", self.max_duration),
            ("Preferred pause break", self.pause_break),
        ):
            form.addRow(label, widget)
        root.addLayout(form)
        self.warn_cps = QCheckBox("Warn about characters per second")
        self.warn_wpm = QCheckBox("Warn about words per minute")
        self.warn_line_length = QCheckBox("Warn about line length")
        self.warn_line_count = QCheckBox("Warn about line count")
        self.warn_duration = QCheckBox("Warn about cue duration")
        for widget in (self.warn_cps, self.warn_wpm, self.warn_line_length, self.warn_line_count, self.warn_duration):
            root.addWidget(widget)
        restore = QPushButton("Restore Professional Defaults")
        restore.clicked.connect(lambda: self._load(SubtitleLayoutSettings()))
        root.addWidget(restore)
        reflow = QPushButton("Reflow Current Subtitles with These Settings")
        reflow.clicked.connect(self._accept_reflow)
        root.addWidget(reflow)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._load(self.settings)

    def accept(self):
        if self.min_duration.value() > self.max_duration.value():
            QMessageBox.warning(self, "Invalid duration limits", "Minimum duration must not exceed maximum duration.")
            return
        super().accept()

    def _accept_reflow(self):
        self.reflow_requested = True
        self.accept()

    def _load(self, value):
        self.max_chars.setValue(value.max_chars_per_line); self.max_lines.setValue(value.max_lines)
        self.max_cps.setValue(value.max_cps); self.max_wpm.setValue(value.max_wpm)
        self.min_duration.setValue(value.min_duration_ms / 1000); self.max_duration.setValue(value.max_duration_ms / 1000)
        self.pause_break.setValue(value.pause_break_ms)
        self.warn_cps.setChecked(value.warn_cps); self.warn_wpm.setChecked(value.warn_wpm)
        self.warn_line_length.setChecked(value.warn_line_length); self.warn_line_count.setChecked(value.warn_line_count)
        self.warn_duration.setChecked(value.warn_duration)

    def result_settings(self):
        return SubtitleLayoutSettings(
            self.max_chars.value(), self.max_lines.value(), self.max_cps.value(), self.max_wpm.value(),
            round(self.min_duration.value() * 1000), round(self.max_duration.value() * 1000), self.pause_break.value(),
            self.warn_cps.isChecked(), self.warn_wpm.isChecked(), self.warn_line_length.isChecked(),
            self.warn_line_count.isChecked(), self.warn_duration.isChecked(),
        )


class SearchReplaceDialog(QDialog):
    def __init__(self, editor: "MainWindow"):
        super().__init__(editor)
        self.editor = editor
        self.setWindowTitle("Find and Replace")
        self.setModal(False)
        layout = QFormLayout(self)
        self.find_edit = QLineEdit()
        self.replace_edit = QLineEdit()
        self.case_sensitive = QCheckBox("Case sensitive")
        layout.addRow("Find", self.find_edit)
        layout.addRow("Replace with", self.replace_edit)
        layout.addRow("", self.case_sensitive)
        buttons = QHBoxLayout()
        find_next = QPushButton("Find next")
        replace = QPushButton("Replace match")
        replace_all = QPushButton("Replace all")
        close = QPushButton("Close")
        find_next.clicked.connect(self.find_next)
        replace.clicked.connect(self.replace_match)
        replace_all.clicked.connect(self.replace_everywhere)
        close.clicked.connect(self.close)
        for button in (find_next, replace, replace_all, close):
            buttons.addWidget(button)
        layout.addRow(buttons)
        self.find_edit.returnPressed.connect(self.find_next)

    def find_next(self):
        if not self.editor.find_next_text(self.find_edit.text(), self.case_sensitive.isChecked()):
            QMessageBox.information(self, "Find", "No matching subtitle text was found.")

    def replace_match(self):
        if self.editor.replace_selected_text(
            self.find_edit.text(), self.replace_edit.text(), self.case_sensitive.isChecked()
        ):
            self.find_next()

    def replace_everywhere(self):
        count = self.editor.replace_all_text(
            self.find_edit.text(), self.replace_edit.text(), self.case_sensitive.isChecked()
        )
        self.editor.statusBar().showMessage(f"Replaced {count} text occurrence{'s' if count != 1 else ''}.", 6000)


class QualityReportDialog(QDialog):
    def __init__(self, editor: "MainWindow"):
        super().__init__(editor)
        self.editor = editor
        self.setWindowTitle("Subtitle Quality Report")
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        count = sum(len(items) for items in editor.issues_by_id.values())
        layout.addWidget(QLabel(f"{len(editor.timeline.segments)} cues · {count} current warning{'s' if count != 1 else ''}"))
        self.list = QListWidget()
        for index, segment in enumerate(editor.timeline.segments):
            for issue in editor.issues_by_id.get(segment.id, []):
                item = self.list.addItem(f"Cue {index + 1}  ·  {issue.message}")
                list_item = self.list.item(self.list.count() - 1)
                list_item.setData(Qt.ItemDataRole.UserRole, index)
        if not count:
            self.list.addItem("No readability or structural issues were found.")
        self.list.itemDoubleClicked.connect(self._open_issue)
        layout.addWidget(self.list)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

    def _open_issue(self, item):
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int):
            self.editor._select_segment(index, seek=True)
            self.accept()


class ModelInstallThread(QThread):
    status = Signal(str)
    downloadProgress = Signal(object, object, str)
    failed = Signal(str)
    cancelled = Signal()
    installed = Signal()

    def __init__(self, store: ModelStore, manifest, parent=None):
        super().__init__(parent)
        self.store = store
        self.manifest = manifest

    def run(self):
        try:
            self.store.install(self.manifest, self._report_status, self._report_download)
            self.installed.emit()
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))

    def cancel(self):
        self.requestInterruption()

    def _report_status(self, message: str):
        if self.isInterruptionRequested():
            raise InterruptedError("Model download cancelled")
        self.status.emit(message)

    def _report_download(self, current: int, total: int | None, description: str):
        if self.isInterruptionRequested():
            raise InterruptedError("Model download cancelled")
        self.downloadProgress.emit(current, total or 0, description)


class ModelVerificationThread(QThread):
    progress = Signal(object, object, str)
    failed = Signal(str)
    cancelled = Signal()
    verified = Signal()

    def __init__(self, store: ModelStore, manifest, parent=None):
        super().__init__(parent)
        self.store = store
        self.manifest = manifest

    def run(self):
        try:
            self.store.verify(
                self.manifest,
                progress=lambda current, total: self.progress.emit(current, total or 0, "SHA-256 verification"),
                cancelled=self.isInterruptionRequested,
            )
            self.verified.emit()
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))

    def cancel(self):
        self.requestInterruption()


class WaveformLoadThread(QThread):
    loaded = Signal(str, object, int)
    failed = Signal(str, str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            peaks, duration_ms = decode_waveform(self.path, cancelled=self.isInterruptionRequested)
            maximum = max(peaks, default=1.0) or 1.0
            self.loaded.emit(str(self.path), [value / maximum for value in peaks], duration_ms)
        except InterruptedError:
            return
        except Exception as exc:
            self.failed.emit(str(self.path), str(exc))


class ModelManagerDialog(QDialog):
    def __init__(self, store: ModelStore, parent=None, preferred_model_id: str | None = None):
        super().__init__(parent)
        self.store = store
        self.thread: ModelInstallThread | ModelVerificationThread | None = None
        self._verifying = False
        self._close_when_finished = False
        self.active_manifest = None
        self.setWindowTitle("Local AI Models")
        self.resize(620, 380)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Internet is required only while installing a model. Installed models work fully offline."))
        self.list = QListWidget()
        layout.addWidget(self.list)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setFormat("Ready")
        layout.addWidget(self.download_progress)
        buttons = QHBoxLayout()
        self.install_button = QPushButton("Install")
        self.verify_button = QPushButton("Verify integrity")
        self.remove_button = QPushButton("Remove")
        self.close_button = QPushButton("Close")
        self.install_button.clicked.connect(self.install_selected)
        self.verify_button.clicked.connect(self.verify_selected)
        self.remove_button.clicked.connect(self.remove_selected)
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.install_button)
        buttons.addWidget(self.verify_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch()
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.refresh()
        if preferred_model_id:
            for index, manifest in enumerate(available_models()):
                if manifest.id == preferred_model_id:
                    self.list.setCurrentRow(index)
                    break

    def refresh(self):
        selected = self.list.currentRow()
        self.list.clear()
        for manifest in available_models():
            if self.store.is_installed(manifest):
                state = "Installed and verified"
            elif self.store.has_model_files(manifest):
                state = "Existing files need one-time offline verification"
            else:
                state = f"Not installed · ~{manifest.approximate_size / 1e9:.1f} GB"
            self.list.addItem(f"{manifest.display_name}\n{state}")
        if self.list.count():
            self.list.setCurrentRow(max(0, min(selected, self.list.count() - 1)))

    def selected_manifest(self):
        row = self.list.currentRow()
        models = available_models()
        return models[row] if 0 <= row < len(models) else None

    def install_selected(self):
        if self.thread and self.thread.isRunning():
            self._request_cancel()
            return
        manifest = self.selected_manifest()
        if not manifest or self.store.is_installed(manifest):
            return
        self.install_button.setEnabled(True)
        self.install_button.setText("Cancel download")
        self.remove_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.download_progress.setRange(0, 0)
        self.download_progress.setFormat("Preparing download…")
        self.status.setText(
            f"Model: {manifest.display_name} ({manifest.id})\n"
            f"Source: {manifest.repository}\nStage: Checking disk space and existing files…"
        )
        self.thread = ModelInstallThread(self.store, manifest, self)
        self.active_manifest = manifest
        self.list.setEnabled(False)
        self.thread.status.connect(self._model_status_changed)
        self.thread.downloadProgress.connect(self._download_progress_changed)
        self.thread.failed.connect(self._install_failed)
        self.thread.cancelled.connect(self._install_cancelled)
        self.thread.installed.connect(self._install_finished)
        self.thread.finished.connect(self._thread_stopped)
        self.thread.start()

    def verify_selected(self):
        if self.thread and self.thread.isRunning():
            self._request_cancel()
            return
        manifest = self.selected_manifest()
        if not manifest or not self.store.has_model_files(manifest):
            return
        self._verifying = True
        self.install_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.verify_button.setText("Cancel verification")
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setFormat("Verifying…")
        self.status.setText(f"Model: {manifest.display_name}\nStage: Reading local weights and checking SHA-256…")
        self.thread = ModelVerificationThread(self.store, manifest, self)
        self.active_manifest = manifest
        self.list.setEnabled(False)
        self.thread.progress.connect(self._download_progress_changed)
        self.thread.failed.connect(self._verification_failed)
        self.thread.cancelled.connect(self._install_cancelled)
        self.thread.verified.connect(self._verification_finished)
        self.thread.finished.connect(self._thread_stopped)
        self.thread.start()

    def _verification_finished(self):
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(100)
        self.download_progress.setFormat("Verified — 100%")
        self.status.setText("Model integrity verified. The local weight file matches the pinned SHA-256 checksum.")
        self.refresh()

    def _verification_failed(self, message: str):
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setFormat("Verification failed")
        QMessageBox.critical(self, "Model integrity check failed", message)

    def _model_status_changed(self, stage: str):
        manifest = self.active_manifest or self.selected_manifest()
        if not manifest:
            self.status.setText(stage)
            return
        self.status.setText(
            f"Model: {manifest.display_name} ({manifest.id})\n"
            f"Source: {manifest.repository}\nStage: {stage}"
        )

    def _install_failed(self, message: str):
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setFormat("Download failed")
        QMessageBox.critical(self, "Model installation failed", message)

    def _install_finished(self):
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(100)
        self.download_progress.setFormat("Installed — 100%")
        self.status.setText("Model installed and ready for offline use.")
        self.refresh()

    def _install_cancelled(self):
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setFormat("Operation cancelled")
        self.status.setText(
            "Model verification cancelled." if self._verifying
            else "Download cancelled. Partial files are retained so a later install can resume."
        )

    def _thread_stopped(self):
        thread = self.thread
        self.install_button.setEnabled(True)
        self.install_button.setText("Install")
        self.remove_button.setEnabled(True)
        self.verify_button.setEnabled(True)
        self.verify_button.setText("Verify integrity")
        self.close_button.setEnabled(True)
        self._verifying = False
        self.thread = None
        self.active_manifest = None
        self.list.setEnabled(True)
        if thread:
            thread.deleteLater()
        if self._close_when_finished:
            self._close_when_finished = False
            super().reject()

    def _request_cancel(self, close_after: bool = False):
        if not self.thread or not self.thread.isRunning():
            return
        self._close_when_finished = self._close_when_finished or close_after
        self.thread.cancel()
        self.install_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.status.setText("Cancelling model operation…")
        self.download_progress.setRange(0, 0)
        self.download_progress.setFormat("Cancelling…")

    def _download_progress_changed(self, current: int, total: int, description: str):
        name = description.rsplit("/", 1)[-1]
        manifest = self.active_manifest or self.selected_manifest()
        model_name = manifest.display_name if manifest else "Selected model"
        if total <= 0:
            self.download_progress.setRange(0, 0)
            self.download_progress.setFormat(f"Downloading {name}…")
            self.status.setText(f"Model: {model_name}\nStage: Downloading {name} (size not reported)…")
            return
        percent = max(0, min(100, round(current / total * 100)))
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(percent)
        self.download_progress.setFormat(f"{name} — %p%")
        self.status.setText(
            f"Model: {model_name}\nStage: Downloading {name}\n"
            f"File progress: {current / 1_048_576:.1f} / {total / 1_048_576:.1f} MiB ({percent}%)"
        )

    def remove_selected(self):
        manifest = self.selected_manifest()
        if not manifest or not self.store.is_installed(manifest):
            return
        answer = QMessageBox.question(self, "Remove model", f"Remove {manifest.display_name} from this computer?")
        if answer == QMessageBox.StandardButton.Yes:
            self.store.remove(manifest)
            self.status.setText("Model removed.")
            self.refresh()

    def reject(self):
        if self.thread and self.thread.isRunning():
            answer = QMessageBox.question(
                self,
                "Cancel model operation?",
                "A model operation is still running. Cancel it and close this window? Partial downloads will be kept for resume.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._request_cancel(close_after=True)
            return
        super().reject()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1380, 900)
        self.setMinimumSize(1024, 720)
        if not QApplication.instance().property("subslabTheme"):
            apply_theme(QApplication.instance())
            QApplication.instance().setProperty("subslabTheme", True)
        root = _data_root()
        self.model_store = ModelStore(root / "models")
        self.recovery = RecoveryStore(root / "recovery.json")
        self.settings_store = QSettings(STORAGE_ORGANIZATION, STORAGE_APPLICATION)
        self.layout_settings = self._load_layout_settings()
        self.document = SubtitleDocument(layout_settings=self.layout_settings)
        self.timeline = Timeline()
        self.dirty = False
        self.job: TranscriptionJob | None = None
        self.active_manifest = None
        self.active_request: TranscriptionRequest | None = None
        self.segment_stop_ms: int | None = None
        self.segment_start_ms: int | None = None
        self._dead_job_polls = 0
        self.cards: list[SegmentCard] = []
        self.active_index: int | None = None
        self.selected_index: int | None = None
        self.warning_indexes: list[int] = []
        self.timing_warning_indexes: list[int] = []
        self.issues_by_id = {}
        self.undo_stack: list[EditorSnapshot] = []
        self.redo_stack: list[EditorSnapshot] = []
        self.fix_undo_stack = self.undo_stack
        self._pending_text_snapshot: EditorSnapshot | None = None
        self.issue_count = 0
        self._manual_scroll_until = 0.0
        self._has_video = False
        self._shortcuts: list[QShortcut] = []
        self._typing_sensitive_shortcuts: list[QShortcut] = []
        self._search_dialog: SearchReplaceDialog | None = None
        self._search_state: tuple[str, bool, int, int] | None = None
        self.waveform_thread: WaveformLoadThread | None = None
        self._waveform_threads: list[WaveformLoadThread] = []
        self._rendering_cards = False
        self._cancel_generation = 0
        self._job_started_at: float | None = None
        self._job_stage = "Ready"
        self._job_progress: float | None = 0.0
        self._active_device = "Detecting device"
        self._last_preview = None
        self._empty_cards_widget = None
        self._build_ui()
        self._build_actions()
        self._build_shortcuts()
        self._restore_workspace()
        QApplication.instance().focusChanged.connect(self._focus_changed)
        self.recovery_timer = QTimer(self)
        self.recovery_timer.setSingleShot(True)
        self.recovery_timer.timeout.connect(self._write_recovery)
        self.job_timer = QTimer(self)
        self.job_timer.setInterval(100)
        self.job_timer.timeout.connect(self._poll_job)
        self.issue_timer = QTimer(self)
        self.issue_timer.setSingleShot(True)
        self.issue_timer.setInterval(150)
        self.issue_timer.timeout.connect(self._refresh_issues)
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(lambda: self._set_transcription_progress(self._job_stage, self._job_progress))
        QTimer.singleShot(0, self._offer_recovery)

    def _restore_workspace(self):
        geometry = self.settings_store.value("workspace/geometry")
        splitter = self.settings_store.value("workspace/splitter")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if splitter is not None:
            self.splitter.restoreState(splitter)
        expanded = self.settings_store.value("workspace/setup", True, type=bool)
        self.setup_toggle.setChecked(expanded)
        self.setup_panel.setVisible(expanded)

    def _save_workspace(self):
        self.settings_store.setValue("workspace/geometry", self.saveGeometry())
        self.settings_store.setValue("workspace/splitter", self.splitter.saveState())
        self.settings_store.setValue("workspace/setup", self.setup_toggle.isChecked())
        self.settings_store.sync()

    def _build_ui(self):
        build_workspace(self)

    def _build_actions(self):
        build_actions(self)

    def createPopupMenu(self):
        return None

    def contextMenuEvent(self, event: QContextMenuEvent):
        event.accept()

    def _load_layout_settings(self) -> SubtitleLayoutSettings:
        raw = self.settings_store.value("readability")
        if not raw:
            return SubtitleLayoutSettings()
        try:
            return SubtitleLayoutSettings.from_dict(json.loads(str(raw)))
        except (TypeError, ValueError, json.JSONDecodeError):
            return SubtitleLayoutSettings()

    def _save_layout_settings(self):
        self.settings_store.setValue("readability", json.dumps(self.layout_settings.to_dict()))

    def _add_shortcut(self, sequence: str, callback, typing_sensitive: bool = True):
        shortcut = QShortcut(QKeySequence(sequence), self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(callback)
        self._shortcuts.append(shortcut)
        if typing_sensitive:
            self._typing_sensitive_shortcuts.append(shortcut)

    def _focus_changed(self, _old, new):
        enabled = not isinstance(new, (QLineEdit, QPlainTextEdit))
        for shortcut in self._typing_sensitive_shortcuts:
            shortcut.setEnabled(enabled)

    def _build_shortcuts(self):
        callbacks = {
            "seek_back": lambda: self._seek_relative(-5000),
            "seek_forward": lambda: self._seek_relative(5000),
            "previous_cue": lambda: self._select_relative_cue(-1),
            "next_cue": lambda: self._select_relative_cue(1),
            "set_start": lambda: self._set_selected_boundary("start"),
            "set_end": lambda: self._set_selected_boundary("end"),
            "start_back": lambda: self._nudge_selected("start", -NUDGE_MS),
            "start_forward": lambda: self._nudge_selected("start", NUDGE_MS),
            "end_back": lambda: self._nudge_selected("end", -NUDGE_MS),
            "end_forward": lambda: self._nudge_selected("end", NUDGE_MS),
            "previous_warning": lambda: self._navigate_warning(-1),
            "next_warning": lambda: self._navigate_warning(1),
        }
        for spec in SHORTCUTS:
            callback = callbacks.get(spec.callback) or getattr(self, spec.callback)
            self._add_shortcut(spec.keys, callback, spec.typing_sensitive)

    def _is_typing(self) -> bool:
        return isinstance(QApplication.focusWidget(), (QLineEdit, QPlainTextEdit))

    def _unless_typing(self, callback):
        if not self._is_typing():
            callback()

    def _context_index(self) -> int | None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState and self.active_index is not None:
            return self.active_index
        return self.selected_index if self.selected_index is not None else self.active_index

    def _play_context_cue(self):
        index = self._context_index()
        if index is not None:
            self._play_segment(index)

    def _play_context_with_handles(self):
        index = self._context_index()
        if index is None:
            return
        segment = self.timeline.segments[index]
        self._select_segment(index)
        self.segment_start_ms = max(0, segment.start_ms - 500)
        duration = self._known_duration()
        self.segment_stop_ms = min(segment.end_ms + 500, duration) if duration else segment.end_ms + 500
        self.player.setPosition(self.segment_start_ms)
        self.player.play()

    def _split_selected(self):
        if self.selected_index is not None:
            self._split_segment(self.selected_index)

    def _nudge_selected(self, boundary: str, amount: int):
        if self.selected_index is not None:
            self._nudge_segment(self.selected_index, boundary, amount)

    def _set_selected_boundary(self, boundary: str):
        if self.selected_index is None:
            return
        segment = self.timeline.segments[self.selected_index]
        position = self.player.position()
        start = position if boundary == "start" else segment.start_ms
        end = position if boundary == "end" else segment.end_ms
        self._apply_segment_update(self.selected_index, start, end, segment.text)

    def _delete_selected_confirmed(self):
        if self.selected_index is None:
            return
        self._delete_segment_confirmed(self.selected_index)

    def _delete_segment_confirmed(self, index: int):
        if not 0 <= index < len(self.timeline.segments):
            return
        answer = QMessageBox.question(self, "Delete subtitle", "Delete the selected subtitle cue?")
        if answer == QMessageBox.StandardButton.Yes:
            self._delete_segment(index)

    def _seek_relative(self, amount: int):
        self._seek(max(0, min(self.player.duration(), self.player.position() + amount)))

    def _select_relative_cue(self, amount: int):
        if not self.timeline.segments:
            return
        base = self._context_index()
        if base is None:
            base = 0 if amount > 0 else len(self.timeline.segments) - 1
        else:
            base = max(0, min(len(self.timeline.segments) - 1, base + amount))
        self._select_segment(base, seek=True)

    def show_shortcuts(self):
        lines = [f"{native_shortcut(spec.keys)}    {spec.label}" for spec in SHORTCUTS]
        lines.extend(f"{item.shortcut().toString(QKeySequence.SequenceFormat.NativeText)}    {item.text()}"
                     for item in self.actions.values() if not item.shortcut().isEmpty())
        lines.append("↑ / ↓ in a timestamp    Nudge + / −100 ms")
        QMessageBox.information(self, "Keyboard shortcuts", "\n".join(lines))

    def open_find_replace(self):
        if self._search_dialog is None:
            self._search_dialog = SearchReplaceDialog(self)
            self._search_dialog.finished.connect(lambda _result: setattr(self, "_search_dialog", None))
        self._search_dialog.show()
        self._search_dialog.raise_()
        self._search_dialog.activateWindow()
        self._search_dialog.find_edit.setFocus()

    def open_quality_report(self):
        self._refresh_issues()
        QualityReportDialog(self).exec()

    def export_additional_format(self):
        self._commit_pending_text_edit()
        self._refresh_issues()
        if not self.timeline.segments:
            QMessageBox.information(self, "Nothing to export", "There are no subtitles to export.")
            return
        if not self._prepare_export():
            return
        base = self.document.srt_path or (self.document.media_path or Path("subtitles")).with_suffix(".vtt")
        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export subtitles",
            str(base),
            "WebVTT subtitles (*.vtt);;Advanced SubStation Alpha (*.ass)",
        )
        if not filename:
            return
        destination = Path(filename)
        try:
            if destination.suffix.lower() == ".ass" or "SubStation" in selected_filter:
                destination = destination.with_suffix(".ass")
                save_ass(destination, self.timeline.segments)
            else:
                destination = destination.with_suffix(".vtt")
                save_vtt(destination, self.timeline.segments)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export subtitles", str(exc))
            return
        self.statusBar().showMessage(f"Exported {destination}", 6000)

    def find_next_text(self, needle: str, case_sensitive: bool = False) -> bool:
        if not needle or not self.timeline.segments:
            return False
        state_key = (needle, case_sensitive)
        if self._search_state and self._search_state[:2] == state_key:
            start_index, start_offset = self._search_state[2], self._search_state[3]
        else:
            start_index = self.selected_index or 0
            start_offset = 0
        target = needle if case_sensitive else needle.casefold()
        for step in range(len(self.timeline.segments) + 1):
            index = (start_index + step) % len(self.timeline.segments)
            text = self.timeline.segments[index].text
            haystack = text if case_sensitive else text.casefold()
            offset = start_offset if step == 0 else 0
            found = haystack.find(target, offset)
            if found < 0:
                continue
            self._select_segment(index, seek=True)
            cursor = self.cards[index].text_edit.textCursor()
            cursor.setPosition(found)
            cursor.setPosition(found + len(needle), QTextCursor.MoveMode.KeepAnchor)
            self.cards[index].text_edit.setTextCursor(cursor)
            self.cards[index].text_edit.setFocus()
            self._search_state = (needle, case_sensitive, index, found + len(needle))
            return True
        self._search_state = None
        return False

    def replace_selected_text(self, needle: str, replacement: str, case_sensitive: bool = False) -> bool:
        if self.selected_index is None or not needle:
            return False
        editor = self.cards[self.selected_index].text_edit
        cursor = editor.textCursor()
        selected = cursor.selectedText()
        matches = selected == needle if case_sensitive else selected.casefold() == needle.casefold()
        if not matches:
            self.find_next_text(needle, case_sensitive)
            return False
        cursor.insertText(replacement)
        self._commit_pending_text_edit()
        self._search_state = (needle, case_sensitive, self.selected_index, cursor.position())
        return True

    def replace_all_text(self, needle: str, replacement: str, case_sensitive: bool = False) -> int:
        if not needle:
            return 0
        self._commit_pending_text_edit()
        before = self._snapshot_state()
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(needle), flags)
        count = 0
        for segment in self.timeline.segments:
            segment.text, replaced = pattern.subn(lambda _match: replacement, segment.text)
            count += replaced
        if count:
            self.document.segments = self.timeline.segments
            self._record_history(before)
            self._refresh_cards_from_timeline()
            self._mark_dirty()
        self._search_state = None
        return count

    def open_readability_settings(self):
        self._commit_pending_text_edit()
        before_settings = self._snapshot_state()
        dialog = ReadabilitySettingsDialog(self.layout_settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.layout_settings = dialog.result_settings()
        self.document.layout_settings = self.layout_settings
        self._save_layout_settings()
        self._refresh_issues()
        if self.timeline.segments:
            self._mark_dirty()
        if dialog.reflow_requested:
            self.reflow_current_subtitles(before_settings)
        else:
            self._record_history(before_settings)

    def reflow_current_subtitles(self, history_before: EditorSnapshot | None = None):
        if not self.timeline.segments:
            return
        self._commit_pending_text_edit()
        self._refresh_issues()
        before_reflow = history_before or self._snapshot_state()
        selected_start = next((item.start_ms for item in before_reflow.segments if item.id == before_reflow.selected_id), 0)
        words = fallback_words(self.timeline.segments)
        try:
            segments = reflow_subtitles(words, self.layout_settings, self._known_duration())
            segments = fit_readability_durations(segments, self.layout_settings, 0, self._known_duration())
            segments, _ = repair_segments(segments, self._known_duration())
            source_index = 0
            reused_ids = set()
            for segment in segments:
                while (source_index + 1 < len(before_reflow.segments)
                       and before_reflow.segments[source_index].end_ms <= segment.start_ms):
                    source_index += 1
                original = before_reflow.segments[source_index]
                if original.id not in reused_ids:
                    segment.id = original.id
                    reused_ids.add(original.id)
            self.timeline = Timeline(segments, self._known_duration())
        except TimelineError as exc:
            QMessageBox.warning(self, "Could not reflow subtitles", str(exc))
            return
        self.document.source_words = words
        self.document.segments = self.timeline.segments
        self.selected_index = next((i for i, item in enumerate(segments) if item.id == before_reflow.selected_id),
                                   active_segment_index(segments, selected_start))
        self._record_history(before_reflow)
        self._render_segments()
        self._mark_dirty()
        remaining = self.issue_count
        suffix = f"; {remaining} warning{'s' if remaining != 1 else ''} remain" if remaining else "; all warnings fixed"
        self.statusBar().showMessage(f"Reflowed {len(segments)} subtitle cues{suffix}", 7000)

    def fix_selected_segment(self):
        self._commit_pending_text_edit()
        self._refresh_issues()
        self.issue_feedback.hide()
        context = self.selected_index if self.selected_index is not None else self.active_index
        index = context if context in self.timing_warning_indexes else (
            self.timing_warning_indexes[0] if self.timing_warning_indexes else None
        )
        if index is None or not 0 <= index < len(self.timeline.segments):
            self.statusBar().showMessage("No timing fixes are needed. Use Reflow subtitles for line-layout warnings.", 7000)
            return
        target = self.timeline.segments[index]
        before_fix = self._snapshot_state()
        original_text = target.text
        issue_codes = {item.code for item in self.issues_by_id.get(target.id, [])}
        current_duration = target.end_ms - target.start_ms
        required = required_reading_duration_ms(target, self.layout_settings)
        if self.layout_settings.warn_duration and required > self.layout_settings.max_duration_ms:
            self.issue_feedback.setText(
                f"This cue needs {required / 1000:.1f}s to meet reading-speed limits, exceeding the "
                f"{self.layout_settings.max_duration_ms / 1000:g}s maximum. Use Reflow subtitles to split it; wording is preserved.")
            self.issue_feedback.show()
            return
        if "duration_long" in issue_codes and required <= self.layout_settings.max_duration_ms:
            desired_duration = max(required, self.layout_settings.max_duration_ms)
        else:
            desired_duration = max(current_duration, required)
        try:
            repaired = retime_segment_duration(
                self.timeline.segments, index, desired_duration, self._known_duration()
            )
            self.timeline = Timeline(repaired, self._known_duration())
        except TimelineError as exc:
            self.issue_feedback.setText(str(exc) + ". Try Reflow subtitles to divide longer captions; accurate speech timing may still require a faster reading speed.")
            self.issue_feedback.show()
            return
        if self.timeline.segments[index].text != original_text:
            raise AssertionError("Timing repair must not alter subtitle text")
        self.document.segments = self.timeline.segments
        self._record_history(before_fix)
        self.selected_index = index
        self._refresh_cards_from_timeline()
        self._mark_dirty()
        remaining_codes = {item.code for item in self.issues_by_id.get(target.id, [])}
        remaining_timing = remaining_codes & {"cps", "wpm", "duration_short", "duration_long"}
        if remaining_timing:
            self.issue_feedback.setText("This cue needs more reading time than adjacent silence permits. The warning remains; try Reflow subtitles to split the caption.")
            self.issue_feedback.show()
        else:
            self.statusBar().showMessage("Timing and reading-speed warnings were fixed; subtitle text was preserved exactly.", 7000)

    def fix_all_warnings(self):
        self._commit_pending_text_edit()
        self._refresh_issues()
        self.issue_feedback.hide()
        if not self.timing_warning_indexes:
            self.statusBar().showMessage("There are no automatically fixable timing or reading-speed warnings.", 4000)
            return
        before_fix = self._snapshot_state()
        target_ids = [self.timeline.segments[index].id for index in self.timing_warning_indexes]
        fixed = 0
        for segment_id in target_ids:
            index = next((i for i, item in enumerate(self.timeline.segments) if item.id == segment_id), None)
            if index is None:
                continue
            segment = self.timeline.segments[index]
            original_texts = {item.id: item.text for item in self.timeline.segments}
            codes = {item.code for item in self.issues_by_id.get(segment_id, [])}
            required = required_reading_duration_ms(segment, self.layout_settings)
            if self.layout_settings.warn_duration and required > self.layout_settings.max_duration_ms:
                continue
            desired = (
                max(required, self.layout_settings.max_duration_ms)
                if "duration_long" in codes and required <= self.layout_settings.max_duration_ms
                else max(segment.end_ms - segment.start_ms, required)
            )
            try:
                repaired = retime_segment_duration(self.timeline.segments, index, desired, self._known_duration())
                if any(item.text != original_texts[item.id] for item in repaired):
                    raise AssertionError("Timing repair must not alter subtitle text")
                self.timeline = Timeline(repaired, self._known_duration())
                fixed += 1
            except TimelineError:
                continue
        self.document.segments = self.timeline.segments
        if fixed:
            self._record_history(before_fix)
            self._mark_dirty()
        self._refresh_cards_from_timeline()
        if self.timing_warning_indexes:
            self.issue_feedback.setText(f"{len(self.timing_warning_indexes)} cues still need more reading time than the available silence permits. Try Reflow subtitles to split longer captions.")
            self.issue_feedback.show()
        self.statusBar().showMessage(f"Fixed timing on {fixed} subtitle cue{'s' if fixed != 1 else ''}; all text was preserved.", 7000)

    def _selected_segment_id(self) -> str | None:
        if self.selected_index is not None and 0 <= self.selected_index < len(self.timeline.segments):
            return self.timeline.segments[self.selected_index].id
        return None

    def _snapshot_state(self) -> EditorSnapshot:
        return EditorSnapshot(
            self._copy_segments(self.timeline.segments),
            [TimedWord(word.text, word.start_ms, word.end_ms) for word in self.document.source_words],
            self._selected_segment_id(),
            SubtitleLayoutSettings.from_dict(self.layout_settings.to_dict()),
            self._capture_view_state(),
        )

    def _record_history(self, before: EditorSnapshot):
        if before == self._snapshot_state():
            return
        self.undo_stack.append(before)
        del self.undo_stack[:-100]
        self.redo_stack.clear()
        self._update_fix_buttons()

    def _clear_history(self):
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._pending_text_snapshot = None
        self._update_fix_buttons()

    def _clear_fix_undo(self):
        self._clear_history()

    def _begin_text_edit(self, _index: int):
        if self._rendering_cards:
            return
        if self._pending_text_snapshot is None:
            self._pending_text_snapshot = self._snapshot_state()

    def _commit_pending_text_edit(self):
        if self._pending_text_snapshot is None:
            return
        before = self._pending_text_snapshot
        self._pending_text_snapshot = None
        self._record_history(before)

    def _restore_snapshot(self, snapshot: EditorSnapshot):
        try:
            self.timeline = Timeline(self._copy_segments(snapshot.segments), self._known_duration())
        except TimelineError as exc:
            raise TimelineError(f"Could not restore subtitle history: {exc}") from exc
        self.document.source_words = [TimedWord(word.text, word.start_ms, word.end_ms) for word in snapshot.source_words]
        self.layout_settings = SubtitleLayoutSettings.from_dict(snapshot.layout_settings.to_dict())
        self.document.layout_settings = self.layout_settings
        self._save_layout_settings()
        self.document.segments = self.timeline.segments
        self.selected_index = next(
            (index for index, item in enumerate(self.timeline.segments) if item.id == snapshot.selected_id), None
        )
        self._render_segments()
        self._restore_view_state(snapshot.view_state)
        self._pending_scroll_restore = snapshot.view_state
        self._pending_text_snapshot = None

    def undo_action(self):
        self._commit_pending_text_edit()
        if not self.undo_stack:
            return
        current = self._snapshot_state()
        snapshot = self.undo_stack.pop()
        try:
            self._restore_snapshot(snapshot)
        except TimelineError as exc:
            self.undo_stack.append(snapshot)
            QMessageBox.warning(self, "Could not undo", str(exc))
            return
        self.redo_stack.append(current)
        self._update_fix_buttons()
        self._mark_dirty()
        self.statusBar().showMessage("Undid the most recent subtitle edit.", 5000)

    def redo_action(self):
        self._commit_pending_text_edit()
        if not self.redo_stack:
            return
        current = self._snapshot_state()
        snapshot = self.redo_stack.pop()
        try:
            self._restore_snapshot(snapshot)
        except TimelineError as exc:
            self.redo_stack.append(snapshot)
            QMessageBox.warning(self, "Could not redo", str(exc))
            return
        self.undo_stack.append(current)
        self._update_fix_buttons()
        self._mark_dirty()
        self.statusBar().showMessage("Redid the subtitle edit.", 5000)

    def undo_last_fix(self):
        self.undo_action()

    @staticmethod
    def _copy_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
        return [SubtitleSegment(item.id, item.start_ms, item.end_ms, item.text) for item in segments]

    @staticmethod
    def _snapshot_to_dict(snapshot: EditorSnapshot) -> dict:
        return {
            "segments": [item.to_dict() for item in snapshot.segments],
            "source_words": [item.to_dict() for item in snapshot.source_words],
            "selected_id": snapshot.selected_id,
            "layout_settings": snapshot.layout_settings.to_dict(),
            "view_state": snapshot.view_state,
        }

    @staticmethod
    def _snapshot_from_dict(value: dict) -> EditorSnapshot:
        return EditorSnapshot(
            [SubtitleSegment.from_dict(item) for item in value.get("segments", [])],
            [TimedWord.from_dict(item) for item in value.get("source_words", [])],
            value.get("selected_id"),
            SubtitleLayoutSettings.from_dict(value.get("layout_settings")),
            dict(value.get("view_state") or {}),
        )

    def open_media(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open media", "", MEDIA_FILTER)
        if filename:
            self._set_media(Path(filename))
            self._mark_dirty()

    def _set_media(self, path: Path):
        self.document.media_path = path
        self.media_label.setText(path.name)
        self.media_label.setToolTip(str(path))
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self._has_video_changed(path.suffix.lower() in {".mp4", ".mov", ".m4v"})
        if self.waveform_thread and self.waveform_thread.isRunning():
            self.waveform_thread.requestInterruption()
        self.waveform.set_waveform([], 0)
        thread = WaveformLoadThread(path, self)
        thread.loaded.connect(self._waveform_loaded)
        thread.failed.connect(self._waveform_failed)
        thread.finished.connect(lambda: self._waveform_thread_finished(thread))
        self.waveform_thread = thread
        self._waveform_threads.append(thread)
        thread.start()

    def _waveform_loaded(self, path: str, peaks: list[float], duration_ms: int):
        if self.document.media_path and str(self.document.media_path) == path:
            self.waveform.set_waveform(peaks, duration_ms)
            self.waveform.set_timeline(self.timeline.segments, self.selected_index)

    def _waveform_failed(self, path: str, message: str):
        if self.document.media_path and str(self.document.media_path) == path:
            self.statusBar().showMessage(f"Waveform unavailable: {message}", 6000)

    def _waveform_thread_finished(self, thread: WaveformLoadThread):
        if self.waveform_thread is thread:
            self.waveform_thread = None
        if thread in self._waveform_threads:
            self._waveform_threads.remove(thread)
        thread.deleteLater()

    def open_srt(self):
        if not self._confirm_replace_dirty():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Import SRT", "", SRT_FILTER)
        if not filename:
            return
        try:
            imported = load_srt(Path(filename))
            segments, repaired = repair_segments(imported, self._known_duration())
            self.timeline = Timeline(segments, self._known_duration())
        except Exception as exc:
            QMessageBox.critical(self, "Could not import SRT", str(exc))
            return
        self.document.segments = self.timeline.segments
        self.document.srt_path = Path(filename)
        self.document.language = "he" if contains_hebrew(segments) else None
        self.document.source_words = []
        self.document.layout_settings = self.layout_settings
        self._clear_fix_undo()
        self._render_segments()
        if repaired:
            self._mark_dirty()
        else:
            self._set_dirty(False)
        repair_message = f"; repaired {repaired} timing entr{'y' if repaired == 1 else 'ies'}" if repaired else ""
        self.statusBar().showMessage(f"Imported {len(segments)} subtitles{repair_message}", 7000)

    def open_models(self):
        ModelManagerDialog(self.model_store, self).exec()

    def start_transcription(self):
        if self.job:
            return
        self._commit_pending_text_edit()
        if not self.document.media_path:
            QMessageBox.information(self, "Select media", "Open an audio or video file first.")
            return
        request = TranscriptionRequest(
            media_path=self.document.media_path,
            mode=TranscriptionMode(self.mode_combo.currentData()),
            language=self.language_combo.currentData(),
            layout_settings=SubtitleLayoutSettings.from_dict(self.layout_settings.to_dict()),
            glossary=self.glossary_edit.text(),
            denoise=self.denoise_check.isChecked(),
        )
        self.document.glossary = request.glossary
        self.document.denoise = request.denoise
        try:
            manifest = route_request(request)
        except Exception as exc:
            QMessageBox.warning(self, "Unsupported configuration", str(exc))
            return
        request.model_id = manifest.id
        request.backend = manifest.backend
        if not self.model_store.is_installed(manifest):
            answer = QMessageBox.question(
                self,
                "Model required",
                f"{manifest.display_name} must be downloaded once before it can work offline. Open Models now?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                ModelManagerDialog(self.model_store, self).exec()
            if not self.model_store.is_installed(manifest):
                return
        if self.document.segments and not self._confirm_replace_dirty():
            return
        self.active_manifest = manifest
        self.active_request = request
        try:
            self.job = start_job(request, self.model_store.root)
        except Exception as exc:
            QMessageBox.critical(self, "Could not start transcription", str(exc))
            return
        self._cancel_generation += 1
        self._job_started_at = time.monotonic()
        self._active_device = "Detecting device"
        self.elapsed_timer.start()
        self._dead_job_polls = 0
        self.transcribe_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._set_job_controls(True)
        self._set_transcription_progress("Starting worker process…", 0.0)
        self.job_timer.start()

    def _set_transcription_progress(self, stage: str, value: float | None):
        self._job_stage, self._job_progress = stage, value
        lowered = stage.lower()
        if "cpu" in lowered:
            self._active_device = "CPU · int8"
        elif "cuda" in lowered:
            self._active_device = "NVIDIA CUDA"
        elif "mlx" in lowered or "apple silicon" in lowered:
            self._active_device = "Apple Silicon · MLX"
        if value is None:
            self.progress.setRange(0, 0)
            self.progress.setFormat(stage)
        else:
            percent = max(0, min(100, round(float(value) * 100)))
            self.progress.setRange(0, 100)
            self.progress.setValue(percent)
            self.progress.setFormat(f"%p% — {stage}")
        manifest = self.active_manifest
        request = self.active_request
        if manifest and request:
            language = request.language or "automatic detection"
            elapsed = max(0, int(time.monotonic() - self._job_started_at)) if self._job_started_at else 0
            elapsed_text = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
            self.progress_details.setText(
                f"Model: {manifest.display_name} ({manifest.id})  •  Engine: {manifest.backend.value}  •  "
                f"Task: {request.mode.value}  •  Language: {language}\n"
                f"Current stage: {stage}  •  Device: {self._active_device}  •  Elapsed: {elapsed_text}"
            )
        else:
            self.progress_details.setText(f"Current stage: {stage}")
        self.statusBar().showMessage(stage)

    def _set_job_controls(self, running: bool):
        self.cancel_button.setVisible(running)
        for widget in (self.mode_combo, self.language_combo, self.advanced_panel, self.cards_scroll):
            widget.setEnabled(not running)
        for key in ("open", "import", "reflow", "readability", "find", "models"):
            self.actions[key].setEnabled(not running)
        self._update_fix_buttons()

    def cancel_transcription(self):
        if not self.job:
            return
        self.job.cancel()
        self.cancel_button.setEnabled(False)
        self.statusBar().showMessage("Cancelling…")
        generation = self._cancel_generation
        QTimer.singleShot(2500, lambda: self._force_cancel(generation))

    def _force_cancel(self, generation: int | None = None):
        if generation is not None and generation != self._cancel_generation:
            return
        if self.job:
            self.job.terminate()
            self._finish_job("Transcription cancelled")

    def _poll_job(self):
        if not self.job:
            return
        events = self.job.poll()
        for event in events:
            event_type = event.get("type")
            if event_type == "progress":
                message = event["message"]
                value = event.get("progress")
                self._set_transcription_progress(message, value)
            elif event_type == "model_switch":
                self.active_manifest = get_manifest(event["model_id"])
                if self.active_request:
                    self.active_request.language = event.get("language", "he")
                    self.active_request.model_id = self.active_manifest.id
                    self.active_request.backend = self.active_manifest.backend
                language_index = self.language_combo.findData(event.get("language", "he"))
                if language_index >= 0:
                    self.language_combo.setCurrentIndex(language_index)
                self._set_transcription_progress(event["message"], 0.02)
            elif event_type == "model_required":
                message = event.get("message", "A required transcription model is not installed.")
                model_id = event.get("model_id")
                self._finish_job("Required Hebrew model is not installed")
                answer = QMessageBox.question(
                    self,
                    "Hebrew model required",
                    message + "\n\nOpen Models to install it now?",
                )
                if answer == QMessageBox.StandardButton.Yes:
                    ModelManagerDialog(self.model_store, self, preferred_model_id=model_id).exec()
                    if model_id:
                        manifest = get_manifest(model_id)
                        if self.model_store.is_installed(manifest):
                            language_index = self.language_combo.findData("he")
                            if language_index >= 0:
                                self.language_combo.setCurrentIndex(language_index)
                            QTimer.singleShot(0, self.start_transcription)
            elif event_type == "result":
                try:
                    words = [TimedWord.from_dict(item) for item in event.get("words", [])]
                    segments = [SubtitleSegment.from_dict(item) for item in event["segments"]]
                    segments, _ = repair_segments(segments, self._known_duration())
                    self.timeline = Timeline(segments, self._known_duration())
                except (ValueError, KeyError, TypeError) as exc:
                    self._finish_job("Transcription result could not be loaded")
                    QMessageBox.critical(self, "Invalid transcription result", str(exc))
                    return
                self.document.segments = self.timeline.segments
                self.document.source_words = words
                self.document.layout_settings = SubtitleLayoutSettings.from_dict(event.get("layout_settings"))
                self.layout_settings = self.document.layout_settings
                self._save_layout_settings()
                self.document.srt_path = None
                self.document.language = event.get("detected_language") or self.language_combo.currentData()
                self.document.mode = self.active_request.mode if self.active_request else TranscriptionMode(self.mode_combo.currentData())
                self.document.glossary = tuple(self.active_request.glossary) if self.active_request else ()
                self.document.denoise = bool(self.active_request.denoise) if self.active_request else False
                self._clear_fix_undo()
                self._render_segments()
                self._mark_dirty()
                self._finish_job(f"Generated {len(segments)} subtitles")
                self.setup_toggle.setChecked(False)
            elif event_type == "cancelled":
                self._finish_job("Transcription cancelled")
            elif event_type == "error":
                message = event.get("message", "Unknown transcription error")
                self._finish_job("Transcription failed")
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Critical)
                box.setWindowTitle("Transcription failed")
                box.setText(message)
                if event.get("details"):
                    box.setDetailedText(event["details"])
                box.exec()
        if self.job and not self.job.is_alive:
            self._dead_job_polls = 0 if events else self._dead_job_polls + 1
            if self._dead_job_polls >= 3:
                self._finish_job("Transcription worker stopped unexpectedly")

    def _finish_job(self, message: str):
        if self.job:
            self.job.process.join(timeout=0.2)
        self.job = None
        self._cancel_generation += 1
        self.job_timer.stop()
        self.elapsed_timer.stop()
        self.transcribe_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._set_job_controls(False)
        self.progress.setRange(0, 100)
        if message.startswith("Generated"):
            self.progress.setValue(100)
            self.progress.setFormat("Complete — 100%")
            self.progress_details.setText(self.progress_details.text().split("\nCurrent stage:")[0] + "\nCurrent stage: Complete")
        else:
            self.progress.setValue(0)
            self.progress.setFormat(message)
            self.progress_details.setText(self.progress_details.text().split("\nCurrent stage:")[0] + f"\nCurrent stage: {message}")
        self.statusBar().showMessage(message, 6000)

    def _capture_view_state(self) -> dict:
        focused = QApplication.focusWidget()
        state = {"scroll": self.cards_scroll.verticalScrollBar().value()}
        for card in self.cards:
            if focused in (card.text_edit, card.start_edit, card.end_edit):
                state["focus_id"] = card.segment_id
                if focused is card.text_edit:
                    cursor = card.text_edit.textCursor()
                    state.update(field="text", position=cursor.position(), anchor=cursor.anchor())
                else:
                    state.update(field="start" if focused is card.start_edit else "end",
                                 position=focused.cursorPosition(), anchor=focused.selectionStart(),
                                 selection_length=len(focused.selectedText()))
                break
        return state

    def _restore_view_state(self, state: dict, restore_focus: bool = True):
        self.cards_scroll.verticalScrollBar().setValue(state.get("scroll", 0))
        if not restore_focus:
            return
        card = next((item for item in self.cards if item.segment_id == state.get("focus_id")), None)
        if card is None:
            return
        if state.get("field") == "text":
            editor = card.text_edit
            cursor = editor.textCursor()
            limit = max(0, editor.document().characterCount() - 1)
            cursor.setPosition(min(state.get("anchor", 0), limit))
            cursor.setPosition(min(state.get("position", 0), limit), QTextCursor.MoveMode.KeepAnchor)
            editor.setTextCursor(cursor)
        else:
            editor = card.start_edit if state.get("field") == "start" else card.end_edit
            editor.setCursorPosition(min(state.get("position", 0), len(editor.text())))
            if state.get("anchor", -1) >= 0:
                editor.setSelection(state["anchor"], state.get("selection_length", 0))
        editor.setFocus()

    def _render_segments(self):
        """Reconcile by cue ID; existing editors keep their cursor and native history."""
        view_state = self._capture_view_state()
        selected_id = self._selected_segment_id()
        previous_index = self.selected_index
        old_cards = {card.segment_id: card for card in self.cards}
        self._rendering_cards = True
        try:
            while self.cards_layout.count():
                self.cards_layout.takeAt(0)
            if self._empty_cards_widget is not None:
                self._empty_cards_widget.deleteLater()
                self._empty_cards_widget = None
            self.cards = []
            for index, segment in enumerate(self.timeline.segments):
                card = old_cards.pop(segment.id, None)
                if card is None:
                    card = SegmentCard(index, segment)
                    card.edited.connect(self._edit_segment)
                    card.playRequested.connect(self._play_segment)
                    card.splitRequested.connect(self._split_segment)
                    card.deleteRequested.connect(self._delete_segment_confirmed)
                    card.nudgeRequested.connect(self._nudge_segment)
                    card.selected.connect(self._select_segment)
                    card.textEditedLive.connect(self._live_text_changed)
                    card.textEditStarted.connect(self._begin_text_edit)
                    card.undoRequested.connect(self.undo_action)
                    card.redoRequested.connect(self.redo_action)
                card.set_index(index)
                card.update_segment(segment)
                self.cards_layout.addWidget(card)
                self.cards.append(card)
            for card in old_cards.values():
                for signal in (card.edited, card.playRequested, card.splitRequested,
                               card.deleteRequested, card.nudgeRequested, card.selected,
                               card.textEditedLive, card.textEditStarted, card.undoRequested, card.redoRequested):
                    signal.disconnect()
                card.hide()
                card.deleteLater()
            self.selected_index = next(
                (i for i, item in enumerate(self.timeline.segments) if item.id == selected_id), None)
            if self.selected_index is None and self.cards:
                self.selected_index = min(previous_index or 0, len(self.cards) - 1)
            self.active_index = None
            for index, card in enumerate(self.cards):
                card.set_selected(index == self.selected_index)
                card.set_active(False)
            if not self.cards:
                empty = QWidget()
                layout = QVBoxLayout(empty)
                label = QLabel("Create something worth reading.\nGenerate subtitles from media, or import an existing SRT.")
                label.setObjectName("muted")
                label.setWordWrap(True)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(label)
                button = QPushButton("Import SRT…")
                button.clicked.connect(self.open_srt)
                layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
                self.cards_layout.addWidget(empty)
                self._empty_cards_widget = empty
            self.cue_count_label.setText(f"{len(self.cards)} cue{'s' if len(self.cards) != 1 else ''}")
            self._refresh_issues()
            self._position_changed(self.player.position())
            self.waveform.set_timeline(self.timeline.segments, self.selected_index)
        finally:
            self._rendering_cards = False
        self.cards_layout.activate()
        self._restore_view_state(view_state)
        self._pending_scroll_restore = view_state
        QTimer.singleShot(0, self._restore_pending_scroll)

    def _restore_pending_scroll(self):
        self._restore_view_state(self._pending_scroll_restore, restore_focus=False)

    def _refresh_cards_from_timeline(self):
        if len(self.cards) != len(self.timeline.segments) or any(
            card.segment_id != segment.id for card, segment in zip(self.cards, self.timeline.segments)
        ):
            self._render_segments()
            return
        for index, (card, segment) in enumerate(zip(self.cards, self.timeline.segments)):
            card.update_segment(segment)
            card.set_selected(index == self.selected_index)
        self._refresh_issues()
        self._position_changed(self.player.position())
        self.waveform.set_timeline(self.timeline.segments, self.selected_index)

    def _select_segment(self, index: int, seek: bool = False):
        if not 0 <= index < len(self.cards):
            return
        changed = self.selected_index != index
        if self.selected_index is not None and self.selected_index < len(self.cards):
            self.cards[self.selected_index].set_selected(False)
        self.selected_index = index
        self.cards[index].set_selected(True)
        self.waveform.set_timeline(self.timeline.segments, self.selected_index)
        if self.loop_button.isChecked():
            segment = self.timeline.segments[index]
            self.segment_start_ms = segment.start_ms
            self.segment_stop_ms = segment.end_ms
        if seek:
            self.player.setPosition(self.timeline.segments[index].start_ms)
        if (changed or seek) and not self._rendering_cards:
            self.cards_scroll.ensureWidgetVisible(self.cards[index], 20, 50)
        self._update_fix_buttons()

    def _set_active_index(self, index: int | None):
        if self.active_index == index:
            self._update_subtitle_preview()
            return
        if self.active_index is not None and self.active_index < len(self.cards):
            self.cards[self.active_index].set_active(False)
        self.active_index = index
        if index is not None and index < len(self.cards):
            self.cards[index].play_indicator.setText("PLAYING" if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState else "CURRENT")
            self.cards[index].set_active(True)
            if not self._rendering_cards and not self._is_typing() and time.monotonic() >= self._manual_scroll_until:
                self.cards_scroll.ensureWidgetVisible(self.cards[index], 20, 80)
        self._update_subtitle_preview()

    def _update_subtitle_preview(self):
        text = ""
        if self.active_index is not None and self.active_index < len(self.timeline.segments):
            text = self.timeline.segments[self.active_index].text
        direction = Qt.LayoutDirection.RightToLeft if is_rtl_text(text) else Qt.LayoutDirection.LeftToRight
        video_text = text if self.cc_button.isChecked() else ""
        state = (text, direction, video_text, self._has_video)
        if state == self._last_preview:
            return
        self._last_preview = state
        self.subtitle_overlay.setText(video_text)
        self.subtitle_overlay.setLayoutDirection(direction)
        self.video.update_overlay_layout()
        self.video.set_overlay_visible(self._has_video and bool(video_text))
        self.audio_subtitle_panel.setText(text)
        self.audio_subtitle_panel.setLayoutDirection(direction)

    def _has_video_changed(self, has_video: bool):
        self._has_video = has_video
        self.player_surface.setCurrentWidget(self.video if has_video else self.audio_subtitle_panel)
        self.cc_button.setVisible(has_video)
        self._update_subtitle_preview()

    def eventFilter(self, watched, event):
        if watched in (self.cards_scroll.viewport(), self.cards_scroll.verticalScrollBar()) and event.type() in (
            QEvent.Type.Wheel, QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress,
        ):
            self._manual_scroll_until = time.monotonic() + 3.0
        return super().eventFilter(watched, event)

    def _refresh_issues(self):
        if hasattr(self, "issue_timer"):
            self.issue_timer.stop()
        by_id = analyze_readability(self.timeline.segments, self.layout_settings)
        errors = structural_issues(self.timeline.segments, self._known_duration())
        for error in errors:
            by_id.setdefault(error.segment_id, []).append(error)
        self.issues_by_id = by_id
        self.warning_indexes = []
        self.timing_warning_indexes = []
        timing_codes = {"cps", "wpm", "duration_short", "duration_long"}
        for index, card in enumerate(self.cards):
            items = by_id.get(card.segment_id, [])
            card.set_issues([item.message for item in items], any(item.severity.value == "error" for item in items))
            if items:
                self.warning_indexes.append(index)
            if any(item.code in timing_codes for item in items):
                self.timing_warning_indexes.append(index)
        count = sum(len(items) for items in by_id.values())
        self.issue_count = count
        self.warning_summary.setText(f"{count} warning{'s' if count != 1 else ''}" if count else "No readability warnings")
        self._update_fix_buttons()

    def _update_fix_buttons(self):
        if not hasattr(self, "fix_segment_button"):
            return
        idle = self.job is None
        self.fix_segment_button.setEnabled(idle and bool(self.timing_warning_indexes))
        self.fix_all_button.setEnabled(idle and bool(self.timing_warning_indexes))
        pending = self._pending_text_snapshot is not None
        if hasattr(self, "actions"):
            self.actions["undo"].setEnabled(idle and (bool(self.undo_stack) or pending))
            self.actions["redo"].setEnabled(idle and bool(self.redo_stack))

    def _refresh_edited_cue(self, index: int):
        segment = self.timeline.segments[index]
        previous = self.issues_by_id.pop(segment.id, [])
        items = analyze_readability([segment], self.layout_settings).get(segment.id, [])
        if items:
            self.issues_by_id[segment.id] = items
        self.cards[index].set_issues([item.message for item in items])
        self.issue_count += len(items) - len(previous)
        self.issue_timer.start()
        self._update_fix_buttons()

    def _playback_state_changed(self, state):
        self.play_button.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play")
        if self.active_index is not None and self.active_index < len(self.cards):
            self.cards[self.active_index].play_indicator.setText("PLAYING" if state == QMediaPlayer.PlaybackState.PlayingState else "CURRENT")

    def _navigate_warning(self, direction: int):
        if not self.warning_indexes:
            return
        current = self.selected_index
        if current not in self.warning_indexes:
            target = self.warning_indexes[0 if direction > 0 else -1]
        else:
            position = self.warning_indexes.index(current)
            target = self.warning_indexes[(position + direction) % len(self.warning_indexes)]
        self._select_segment(target, seek=True)

    def _edit_segment(self, index: int, start_text: str, end_text: str, text: str):
        if self._rendering_cards:
            return
        try:
            self._apply_segment_update(index, parse_timestamp(start_text), parse_timestamp(end_text), text)
        except (ValueError, TimelineError) as exc:
            QMessageBox.warning(self, "Invalid subtitle timing", str(exc))

    def _live_text_changed(self, index: int, text: str):
        if self._rendering_cards:
            return
        if not 0 <= index < len(self.timeline.segments):
            return
        if self._pending_text_snapshot is None:
            self._pending_text_snapshot = self._snapshot_state()
        self.timeline.segments[index].text = text
        self.document.segments = self.timeline.segments
        if self.active_index == index:
            self._update_subtitle_preview()
        self._refresh_edited_cue(index)
        self._mark_dirty()

    def _apply_segment_update(self, index: int, start_ms: int, end_ms: int, text: str):
        before = self._pending_text_snapshot or self._snapshot_state()
        self.timeline.update(index, start_ms, end_ms, text)
        self._pending_text_snapshot = None
        self.document.segments = self.timeline.segments
        self.selected_index = index
        changed = before != self._snapshot_state()
        self._record_history(before)
        self._refresh_cards_from_timeline()
        if changed:
            self._mark_dirty()

    def _nudge_segment(self, index: int, boundary: str, amount: int):
        self._commit_pending_text_edit()
        before = self._snapshot_state()
        try:
            self.timeline.nudge(index, boundary, amount)
        except TimelineError as exc:
            QMessageBox.warning(self, "Cannot nudge subtitle", str(exc))
            return
        self._record_history(before)
        self.document.segments = self.timeline.segments
        self.selected_index = index
        self._refresh_cards_from_timeline()
        self._mark_dirty()

    def _split_segment(self, index: int):
        self._commit_pending_text_edit()
        before = self._snapshot_state()
        try:
            self.timeline.split(index, self.player.position())
        except TimelineError as exc:
            QMessageBox.information(self, "Cannot split subtitle", str(exc))
            return
        self._record_history(before)
        self.document.segments = self.timeline.segments
        self.selected_index = min(index + 1, len(self.timeline.segments) - 1)
        self._render_segments()
        self._mark_dirty()

    def _delete_segment(self, index: int):
        self._commit_pending_text_edit()
        before = self._snapshot_state()
        self.timeline.delete(index)
        self._record_history(before)
        self.document.segments = self.timeline.segments
        self.selected_index = min(index, len(self.timeline.segments) - 1) if self.timeline.segments else None
        self._render_segments()
        self._mark_dirty()

    def _play_segment(self, index: int):
        self._select_segment(index)
        segment = self.timeline.segments[index]
        self.segment_start_ms = segment.start_ms
        self.segment_stop_ms = segment.end_ms
        self.player.setPosition(segment.start_ms)
        self.player.play()

    def _loop_cue_toggled(self, enabled: bool):
        if not enabled:
            self.segment_start_ms = None
            self.segment_stop_ms = None
            return
        index = self._loop_target_index()
        if index is None:
            self.loop_button.setChecked(False)
            self.statusBar().showMessage("Select a subtitle cue before enabling loop playback.", 5000)
            return
        segment = self.timeline.segments[index]
        self.segment_start_ms = segment.start_ms
        self.segment_stop_ms = segment.end_ms
        if not segment.start_ms <= self.player.position() < segment.end_ms:
            self.player.setPosition(segment.start_ms)
        self.statusBar().showMessage(f"Looping cue {index + 1}. Press Play / Pause to start or stop.", 5000)

    def _loop_target_index(self) -> int | None:
        if self.selected_index is not None:
            return self.selected_index
        return self.active_index

    def toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.loop_button.isChecked():
                index = self._loop_target_index()
                if index is not None:
                    segment = self.timeline.segments[index]
                    self.segment_start_ms = segment.start_ms
                    self.segment_stop_ms = segment.end_ms
                    if not segment.start_ms <= self.player.position() < segment.end_ms:
                        self.player.setPosition(segment.start_ms)
            self.player.play()

    def _duration_changed(self, duration: int):
        self.position_slider.setRange(0, duration)
        self.timeline.media_duration_ms = duration or None
        if duration and self.timeline.segments:
            before_repair = self._snapshot_state()
            try:
                segments, repaired = repair_segments(self.timeline.segments, duration)
                if repaired:
                    self.timeline = Timeline(segments, duration)
                    self.document.segments = self.timeline.segments
                    self._record_history(before_repair)
                    self._refresh_cards_from_timeline()
                    self._mark_dirty()
                    self.statusBar().showMessage(f"Repaired {repaired} subtitle timing entries to fit the media", 6000)
            except TimelineError as exc:
                self.statusBar().showMessage(f"Subtitle timing needs attention: {exc}", 6000)
        self._refresh_issues()

    def _position_changed(self, position: int):
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        self.time_label.setText(
            f"{format_timestamp(position).replace(',', '.')} / {format_timestamp(self._known_duration() or 0).replace(',', '.')}"
        )
        self.waveform.set_position(position)
        if self.segment_stop_ms is not None and position >= self.segment_stop_ms:
            if self.loop_button.isChecked() and self.segment_start_ms is not None:
                self.player.setPosition(self.segment_start_ms)
                self.player.play()
            else:
                self.player.pause()
                self.segment_stop_ms = None
                self.segment_start_ms = None
        self._set_active_index(active_segment_index(self.timeline.segments, position))

    def _seek(self, position: int):
        if not self.loop_button.isChecked():
            self.segment_stop_ms = None
            self.segment_start_ms = None
        self.player.setPosition(position)

    def _waveform_boundary_moved(self, index: int, boundary: str, position: int):
        if not 0 <= index < len(self.timeline.segments):
            return
        segment = self.timeline.segments[index]
        start = position if boundary == "start" else segment.start_ms
        end = position if boundary == "end" else segment.end_ms
        try:
            self._apply_segment_update(index, start, end, segment.text)
        except TimelineError as exc:
            QMessageBox.warning(self, "Cannot move subtitle boundary", str(exc))

    def _prepare_export(self) -> bool:
        before = self._snapshot_state()
        try:
            segments, repaired = repair_segments(self.timeline.segments, self._known_duration())
            errors = structural_issues(segments, self._known_duration())
            if errors:
                raise TimelineError(errors[0].message)
            if repaired:
                self.timeline = Timeline(segments, self._known_duration())
                self.document.segments = self.timeline.segments
                self._record_history(before)
                self._render_segments()
                self._mark_dirty()
        except TimelineError as exc:
            self._refresh_issues()
            QMessageBox.critical(self, "Cannot export subtitles", str(exc))
            return False
        return True

    def save_document(self, force_copy: bool = False) -> bool:
        self._commit_pending_text_edit()
        self._refresh_issues()
        if not self.timeline.segments:
            self.statusBar().showMessage("Create or import subtitles before saving.", 6000)
            return False
        if not self._prepare_export():
            return False
        destination = self.document.srt_path
        if destination and not force_copy:
            box = QMessageBox(self)
            box.setWindowTitle("Save imported subtitle")
            box.setText("Overwrite the imported SRT or save a copy?")
            overwrite = box.addButton("Overwrite", QMessageBox.ButtonRole.AcceptRole)
            copy_button = box.addButton("Save as copy", QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is copy_button:
                force_copy = True
            elif box.clickedButton() is not overwrite:
                return False
        if destination is None or force_copy:
            suggested = str((destination or (self.document.media_path or Path("subtitles")).with_suffix(".srt")))
            filename, _ = QFileDialog.getSaveFileName(self, "Save subtitles", suggested, SRT_FILTER)
            if not filename:
                return False
            destination = Path(filename).with_suffix(".srt")
        try:
            save_srt(destination, self.timeline.segments, repair_hebrew=contains_hebrew(self.timeline.segments))
        except Exception as exc:
            QMessageBox.critical(self, "Could not save SRT", str(exc))
            return False
        self.document.srt_path = destination
        self._set_dirty(False)
        self.recovery_timer.stop()
        self.recovery.clear()
        self.statusBar().showMessage(f"Saved {destination}", 6000)
        return True

    def _mark_dirty(self):
        self._set_dirty(True)
        self.recovery_timer.start(700)

    def _set_dirty(self, dirty: bool):
        self.dirty = dirty
        name = self.document.srt_path.name if self.document.srt_path else "Untitled"
        self.setWindowTitle(f"{'*' if dirty else ''}{name} — {APP_NAME}")

    def _write_recovery(self):
        if self.dirty:
            self.document.segments = self.timeline.segments
            self.document.layout_settings = self.layout_settings
            try:
                self.recovery.save(
                    self.document,
                    {
                        "undo": [self._snapshot_to_dict(item) for item in self.undo_stack[-20:]],
                        "redo": [self._snapshot_to_dict(item) for item in self.redo_stack[-20:]],
                        "selected_id": self._selected_segment_id(),
                    },
                )
            except Exception as exc:
                self.statusBar().showMessage(f"Could not write recovery snapshot: {exc}", 6000)

    def _offer_recovery(self):
        if not self.recovery.exists():
            self._render_segments()
            return
        answer = QMessageBox.question(self, "Recover unsaved work", f"{APP_NAME} found unsaved work. Recover it?")
        if answer == QMessageBox.StandardButton.Yes:
            try:
                self.document = self.recovery.load()
                editor_state = self.recovery.load_editor_state()
                recovered, _ = repair_segments(self.document.segments)
                self.timeline = Timeline(recovered)
                self.layout_settings = self.document.layout_settings
                self.glossary_edit.setText(", ".join(self.document.glossary))
                self.denoise_check.setChecked(self.document.denoise)
                self.undo_stack[:] = [self._snapshot_from_dict(item) for item in editor_state.get("undo", [])]
                self.redo_stack[:] = [self._snapshot_from_dict(item) for item in editor_state.get("redo", [])]
                selected_id = editor_state.get("selected_id")
                self.selected_index = next(
                    (index for index, item in enumerate(self.timeline.segments) if item.id == selected_id), None
                )
                self._save_layout_settings()
                if self.document.media_path and self.document.media_path.exists():
                    self._set_media(self.document.media_path)
                self._render_segments()
                self._set_dirty(True)
                return
            except Exception as exc:
                QMessageBox.warning(self, "Recovery failed", str(exc))
        self.recovery.clear()
        self._render_segments()

    def _known_duration(self) -> int | None:
        return self.player.duration() or (self.waveform.duration_ms if self.document.media_path else 0) or None

    def _confirm_replace_dirty(self) -> bool:
        if not self.dirty:
            return True
        answer = QMessageBox.warning(
            self,
            "Unsaved changes",
            "Save your changes before replacing the current subtitles?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_document()
        if answer == QMessageBox.StandardButton.Discard:
            self.recovery.clear()
            return True
        return False

    def closeEvent(self, event: QCloseEvent):
        self._commit_pending_text_edit()
        if not getattr(self, "_close_authorized", False):
            if self.job:
                answer = QMessageBox.question(self, "Transcription running", "Cancel transcription and quit?")
                if answer != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
            if self.dirty:
                answer = QMessageBox.warning(
                    self, "Unsaved changes", "Save your subtitle changes before quitting?",
                    QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                )
                if answer == QMessageBox.StandardButton.Cancel:
                    event.ignore()
                    return
                if answer == QMessageBox.StandardButton.Save and not self.save_document():
                    event.ignore()
                    return
                if answer == QMessageBox.StandardButton.Discard:
                    self.recovery.clear()
                    self._set_dirty(False)
            self._close_authorized = True
            self.recovery_timer.stop()
            self.issue_timer.stop()
            self.elapsed_timer.stop()
            self._save_workspace()
            if self.job:
                self.job.terminate()
                self.job = None
                self.job_timer.stop()
        running = [thread for thread in self._waveform_threads if thread.isRunning()]
        if running:
            for thread in running:
                thread.requestInterruption()
                if not thread.property("closingConnection"):
                    thread.setProperty("closingConnection", True)
                    thread.finished.connect(lambda: QTimer.singleShot(0, self.close))
            self.centralWidget().setEnabled(False)
            self.statusBar().showMessage("Finishing audio cleanup before closing…")
            event.ignore()
            return
        self.player.stop()
        event.accept()
