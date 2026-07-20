from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Signal, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .domain import SubtitleSegment


class WaveformWidget(QWidget):
    seekRequested = Signal(int)
    boundaryMoved = Signal(int, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(92)
        self.setToolTip("Click to seek. Drag a subtitle boundary to retime it.")
        self.peaks: list[float] = []
        self.duration_ms = 0
        self.position_ms = 0
        self.segments: list[SubtitleSegment] = []
        self.selected_index: int | None = None
        self._drag: tuple[int, str] | None = None
        self._drag_ms: int | None = None
        self._scrubbing = False

    def set_waveform(self, peaks: list[float], duration_ms: int):
        self.peaks = [max(0.0, min(1.0, float(value))) for value in peaks]
        self.duration_ms = max(0, int(duration_ms))
        self.update()

    def set_timeline(self, segments: list[SubtitleSegment], selected_index: int | None = None):
        self.segments = segments
        self.selected_index = selected_index
        self.update()

    def set_position(self, position_ms: int):
        self.position_ms = max(0, int(position_ms))
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#161616"))
        width, height = max(1, self.width()), max(1, self.height())
        center = height / 2
        if self.peaks:
            painter.setPen(QPen(QColor("#5fa8c9"), 1))
            for x in range(width):
                index = min(len(self.peaks) - 1, int(x / width * len(self.peaks)))
                amplitude = self.peaks[index] * (height * 0.38)
                painter.drawLine(QPointF(x, center - amplitude), QPointF(x, center + amplitude))
        else:
            painter.setPen(QColor("#777777"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waveform loads when media is opened")

        if self.duration_ms > 0:
            for index, segment in enumerate(self.segments):
                left = self._time_to_x(segment.start_ms)
                right = self._time_to_x(segment.end_ms)
                color = QColor(211, 167, 47, 75) if index == self.selected_index else QColor(54, 163, 255, 42)
                painter.fillRect(QRectF(left, 2, max(1, right - left), height - 4), color)
                painter.setPen(QPen(QColor("#d3a72f") if index == self.selected_index else QColor("#4e7890"), 1))
                painter.drawLine(QPointF(left, 2), QPointF(left, height - 2))
                painter.drawLine(QPointF(right, 2), QPointF(right, height - 2))
            if self._drag_ms is not None:
                x = self._time_to_x(self._drag_ms)
                painter.setPen(QPen(QColor("#ffd166"), 2))
                painter.drawLine(QPointF(x, 0), QPointF(x, height))
            playhead = self._time_to_x(self.position_ms)
            painter.setPen(QPen(QColor("#ff5a5f"), 2))
            painter.drawLine(QPointF(playhead, 0), QPointF(playhead, height))

    def mousePressEvent(self, event: QMouseEvent):
        if self.duration_ms <= 0 or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        nearest: tuple[float, int, str] | None = None
        for index, segment in enumerate(self.segments):
            for boundary, value in (("start", segment.start_ms), ("end", segment.end_ms)):
                distance = abs(event.position().x() - self._time_to_x(value))
                candidate = (distance, index, boundary)
                if nearest is None or candidate < nearest:
                    nearest = candidate
        if nearest and nearest[0] <= 7:
            self._drag = (nearest[1], nearest[2])
            self._drag_ms = self._x_to_time(event.position().x())
            self.update()
        else:
            self._scrubbing = True
            self.position_ms = self._x_to_time(event.position().x())
            self.seekRequested.emit(self.position_ms)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag:
            self._drag_ms = self._x_to_time(event.position().x())
            self.update()
            return
        if self._scrubbing:
            self.position_ms = self._x_to_time(event.position().x())
            self.seekRequested.emit(self.position_ms)
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._drag and event.button() == Qt.MouseButton.LeftButton:
            index, boundary = self._drag
            value = self._x_to_time(event.position().x())
            self._drag = None
            self._drag_ms = None
            self.boundaryMoved.emit(index, boundary, value)
            self.update()
            return
        if self._scrubbing and event.button() == Qt.MouseButton.LeftButton:
            self._scrubbing = False
            self.position_ms = self._x_to_time(event.position().x())
            self.seekRequested.emit(self.position_ms)
            self.update()
            return
        super().mouseReleaseEvent(event)

    def _time_to_x(self, milliseconds: int) -> float:
        return max(0.0, min(float(self.width()), milliseconds / max(1, self.duration_ms) * self.width()))

    def _x_to_time(self, x: float) -> int:
        return round(max(0.0, min(float(self.width()), x)) / max(1, self.width()) * self.duration_ms)
