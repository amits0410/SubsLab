from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QSignalBlocker, QSizeF, Signal, Qt
from PySide6.QtGui import QContextMenuEvent, QKeyEvent, QKeySequence, QTextBlockFormat, QTextCursor
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (QFrame, QGraphicsScene, QGraphicsView, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QToolBar, QVBoxLayout, QWidget)
from .domain import SubtitleSegment
from .direction import is_rtl_text
from .srt import format_timestamp
from .timeline import NUDGE_MS

class EditableText(QPlainTextEdit):
    editingStarted = Signal()
    editingFinished = Signal()
    undoRequested = Signal()
    redoRequested = Signal()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undoRequested.emit()
            event.accept()
        elif event.matches(QKeySequence.StandardKey.Redo):
            self.redoRequested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.editingStarted.emit()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit()


class TimestampEdit(QLineEdit):
    nudgeRequested = Signal(int)
    focused = Signal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setMinimumWidth(96)
        self.setMaximumWidth(124)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused.emit()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Up:
            self.nudgeRequested.emit(NUDGE_MS)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Down:
            self.nudgeRequested.emit(-NUDGE_MS)
            event.accept()
            return
        super().keyPressEvent(event)


class SubtitleVideoWidget(QGraphicsView):
    """Render video and captions in one graphics scene so captions cannot sit behind video."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QGraphicsView { background: black; }")
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.video_item = QGraphicsVideoItem()
        self.video_item.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.scene.addItem(self.video_item)
        self.overlay = QLabel()
        self.overlay.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.overlay.setWordWrap(True)
        self.overlay.setTextFormat(Qt.TextFormat.PlainText)
        self.overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.overlay.setStyleSheet(
            "QLabel { color: white; font-weight: 600; "
            "background: rgba(0, 0, 0, 165); border-radius: 5px; padding: 8px 14px; }"
        )
        self.overlay_proxy = self.scene.addWidget(self.overlay)
        self.overlay_proxy.setZValue(100)
        self.overlay_proxy.hide()
        self._overlay_geometry = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width, height = self.viewport().width(), self.viewport().height()
        self.scene.setSceneRect(0, 0, width, height)
        self.video_item.setSize(QSizeF(width, height))
        self.update_overlay_layout()

    def update_overlay_layout(self):
        width = max(1, min(self.width(), self.viewport().width()))
        height = max(1, min(self.height(), self.viewport().height()))
        overlay_width = max(1, min(width, round(width * 0.86)))
        font_size = max(14, min(28, round(width / 26)))
        font = self.overlay.font()
        if font.pixelSize() != font_size:
            font.setPixelSize(font_size)
            self.overlay.setFont(font)
        bounds = self.overlay.fontMetrics().boundingRect(
            QRect(0, 0, max(1, overlay_width - 28), 10000),
            Qt.TextFlag.TextWordWrap, self.overlay.text() or " ")
        overlay_height = max(1, min(height, bounds.height() + 20))
        geometry = (width, height, overlay_width, overlay_height, self.overlay.text())
        if geometry == self._overlay_geometry:
            return
        self._overlay_geometry = geometry
        self.overlay.setFixedSize(overlay_width, overlay_height)
        self.overlay_proxy.setPos((width - overlay_width) / 2, max(0, height - overlay_height - round(height * .06)))

    def set_overlay_visible(self, visible: bool):
        self.overlay_proxy.setVisible(visible)
        if visible:
            self.overlay_proxy.setZValue(100)


class FixedToolBar(QToolBar):
    """A permanent toolbar without Qt's visibility checkbox popup."""

    def contextMenuEvent(self, event: QContextMenuEvent):
        event.accept()


class SegmentCard(QFrame):
    edited = Signal(int, str, str, str)
    playRequested = Signal(int)
    splitRequested = Signal(int)
    deleteRequested = Signal(int)
    nudgeRequested = Signal(int, str, int)
    selected = Signal(int)
    textEditedLive = Signal(int, str)
    textEditStarted = Signal(int)
    undoRequested = Signal()
    redoRequested = Signal()

    def __init__(self, index: int, segment: SubtitleSegment, parent=None):
        super().__init__(parent)
        self.index = index
        self.segment_id = segment.id
        self._updating_direction = False
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setProperty("active", False)
        self.setProperty("selected", False)
        self.setProperty("error", False)
        self.setStyleSheet(
            "SegmentCard { border: 2px solid #2b3948; border-radius: 9px; background: #19222c; }"
            "SegmentCard[active='true'] { background: #173c3c; border-color: #3b8f85; }"
            "SegmentCard[selected='true'] { border-color: #e7bc54; }"
            "SegmentCard QLabel { border: 0; background: transparent; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(7)
        heading = QHBoxLayout()
        self.number_label = QLabel(f"{index + 1:02d}")
        self.number_label.setObjectName("muted")
        heading.addWidget(self.number_label)
        self.start_edit = TimestampEdit(format_timestamp(segment.start_ms).replace(",", "."))
        self.end_edit = TimestampEdit(format_timestamp(segment.end_ms).replace(",", "."))
        self.start_edit.setAccessibleName("Start timestamp")
        self.end_edit.setAccessibleName("End timestamp")
        heading.addWidget(self.start_edit)
        heading.addWidget(QLabel("→"))
        heading.addWidget(self.end_edit)
        heading.addStretch()
        self.duration_label = QLabel()
        self.duration_label.setObjectName("muted")
        heading.addWidget(self.duration_label)
        self.play_indicator = QLabel("PLAYING")
        self.play_indicator.setObjectName("badge")
        self.play_indicator.hide()
        heading.addWidget(self.play_indicator)
        play = QPushButton("Play")
        play.setToolTip("Play this cue · Enter")
        play.clicked.connect(lambda: self.playRequested.emit(self.index))
        heading.addWidget(play)
        root.addLayout(heading)

        self.details = QWidget()
        controls = QGridLayout(self.details)
        controls.setContentsMargins(0, 0, 0, 0)
        for column, (label, boundary, delta) in enumerate((("Start −", "start", -NUDGE_MS), ("Start +", "start", NUDGE_MS),
                                       ("End −", "end", -NUDGE_MS), ("End +", "end", NUDGE_MS))):
            button = QPushButton(label)
            button.setToolTip(f"Nudge {boundary} by {delta:+d} ms")
            button.clicked.connect(lambda _checked=False, b=boundary, d=delta: self.nudgeRequested.emit(self.index, b, d))
            controls.addWidget(button, 0, column)
        split = QPushButton("Split")
        split.setToolTip("Split this cue at the playhead · S")
        delete = QPushButton("Delete")
        delete.setObjectName("danger")
        split.clicked.connect(lambda: self.splitRequested.emit(self.index))
        delete.clicked.connect(lambda: self.deleteRequested.emit(self.index))
        hint = QLabel("Timing step · 100 ms")
        hint.setObjectName("muted")
        controls.addWidget(hint, 1, 0, 1, 2)
        controls.addWidget(split, 1, 2)
        controls.addWidget(delete, 1, 3)

        self.text_edit = EditableText(segment.text)
        self.text_edit.setMinimumHeight(64)
        self.text_edit.setMaximumHeight(96)
        self._apply_text_direction(segment.text)
        root.addWidget(self.text_edit)
        root.addWidget(self.details)
        self.details.hide()
        self.issue_label = QLabel()
        self.issue_label.setWordWrap(True)
        self.issue_label.setStyleSheet("color: #f2bd48;")
        self.issue_label.hide()
        root.addWidget(self.issue_label)
        self.start_edit.editingFinished.connect(self._emit_edit)
        self.end_edit.editingFinished.connect(self._emit_edit)
        self.text_edit.editingFinished.connect(self._emit_edit)
        self.text_edit.editingStarted.connect(self._text_edit_started)
        self.text_edit.undoRequested.connect(self.undoRequested)
        self.text_edit.redoRequested.connect(self.redoRequested)
        self.text_edit.textChanged.connect(self._text_changed)
        self.start_edit.focused.connect(lambda: self.selected.emit(self.index))
        self.end_edit.focused.connect(lambda: self.selected.emit(self.index))
        self.start_edit.nudgeRequested.connect(lambda amount: self.nudgeRequested.emit(self.index, "start", amount))
        self.end_edit.nudgeRequested.connect(lambda amount: self.nudgeRequested.emit(self.index, "end", amount))
        for child in self.findChildren(QWidget):
            child.installEventFilter(self)
        self.update_segment(segment)

    def _text_edit_started(self):
        self.selected.emit(self.index)
        self.textEditStarted.emit(self.index)

    def _emit_edit(self):
        self.edited.emit(self.index, self.start_edit.text(), self.end_edit.text(), self.text_edit.toPlainText())

    def _text_changed(self):
        if self._updating_direction:
            return
        text = self.text_edit.toPlainText()
        self._apply_text_direction(text)
        self.textEditedLive.emit(self.index, text)

    def _apply_text_direction(self, text: str):
        direction = Qt.LayoutDirection.RightToLeft if is_rtl_text(text) else Qt.LayoutDirection.LeftToRight
        if getattr(self, "_text_direction", None) == direction:
            return
        self._text_direction = direction
        alignment = Qt.AlignmentFlag.AlignRight if direction is Qt.LayoutDirection.RightToLeft else Qt.AlignmentFlag.AlignLeft
        self._updating_direction = True
        try:
            self.text_edit.setLayoutDirection(direction)
            option = self.text_edit.document().defaultTextOption()
            option.setTextDirection(direction)
            option.setAlignment(alignment)
            self.text_edit.document().setDefaultTextOption(option)
            original_cursor = self.text_edit.textCursor()
            cursor = QTextCursor(self.text_edit.document())
            cursor.select(QTextCursor.SelectionType.Document)
            block_format = QTextBlockFormat()
            block_format.setLayoutDirection(direction)
            block_format.setAlignment(alignment)
            cursor.mergeBlockFormat(block_format)
            self.text_edit.setTextCursor(original_cursor)
        finally:
            self._updating_direction = False

    def mousePressEvent(self, event):
        self.selected.emit(self.index)
        super().mousePressEvent(event)

    def eventFilter(self, watched, event):
        if watched is not self and event.type() == QEvent.Type.MouseButtonPress:
            self.selected.emit(self.index)
        return super().eventFilter(watched, event)

    def update_segment(self, segment: SubtitleSegment):
        self.segment_id = segment.id
        start = format_timestamp(segment.start_ms).replace(",", ".")
        end = format_timestamp(segment.end_ms).replace(",", ".")
        if self.start_edit.text() != start:
            with QSignalBlocker(self.start_edit):
                self.start_edit.setText(start)
        if self.end_edit.text() != end:
            with QSignalBlocker(self.end_edit):
                self.end_edit.setText(end)
        if self.text_edit.toPlainText() != segment.text:
            cursor = self.text_edit.textCursor()
            position, anchor = cursor.position(), cursor.anchor()
            with QSignalBlocker(self.text_edit):
                self.text_edit.setPlainText(segment.text)
                self._text_direction = None
                limit = max(0, self.text_edit.document().characterCount() - 1)
                cursor.setPosition(min(anchor, limit))
                cursor.setPosition(min(position, limit), QTextCursor.MoveMode.KeepAnchor)
                self.text_edit.setTextCursor(cursor)
        self._apply_text_direction(segment.text)
        self.duration_label.setText(f"{(segment.end_ms - segment.start_ms) / 1000:.2f}s")

    def set_index(self, index: int):
        self.index = index
        self.number_label.setText(f"{index + 1:02d}")

    def set_active(self, active: bool):
        if self.property("active") == active:
            return
        self.setProperty("active", active)
        self.play_indicator.setVisible(active)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_selected(self, selected: bool):
        if self.property("selected") == selected:
            return
        self.setProperty("selected", selected)
        self.details.setVisible(selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_issues(self, messages: list[str], error: bool = False):
        if self.issue_label.text() == " • ".join(messages) and self.property("error") == error:
            return
        self.setProperty("error", error)
        self.issue_label.setText(" • ".join(messages))
        self.issue_label.setStyleSheet(f"color: {'#ff7b84' if error else '#e7bc54'}; background: transparent;")
        self.issue_label.setToolTip("Fix timing / speed preserves wording. Use Tools → Reflow for line-layout issues.")
        self.issue_label.setVisible(bool(messages))
        self.style().unpolish(self)
        self.style().polish(self)


