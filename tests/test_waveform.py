from PySide6.QtCore import QPoint, Qt

from subsgen.domain import SubtitleSegment
from subsgen.waveform import WaveformWidget


def test_waveform_click_seeks_and_boundary_drag_emits_retime(qtbot):
    widget = WaveformWidget()
    qtbot.addWidget(widget)
    widget.resize(1000, 100)
    widget.set_waveform([0.2, 0.8, 0.4], 1000)
    widget.set_timeline([SubtitleSegment("a", 200, 800, "Caption")], 0)
    widget.show()
    qtbot.waitExposed(widget)

    with qtbot.waitSignal(widget.seekRequested) as seek:
        qtbot.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(500, 50))
    assert abs(seek.args[0] - 500) <= 2

    with qtbot.waitSignal(widget.boundaryMoved) as moved:
        qtbot.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(200, 50))
        qtbot.mouseMove(widget, QPoint(300, 50))
        qtbot.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(300, 50))
    assert moved.args[:2] == [0, "start"]
    assert abs(moved.args[2] - 300) <= 2


def test_waveform_drag_scrubs_continuously(qtbot):
    widget = WaveformWidget()
    qtbot.addWidget(widget)
    widget.resize(1000, 100)
    widget.set_waveform([0.2, 0.8, 0.4], 1000)
    widget.show()
    qtbot.waitExposed(widget)
    positions = []
    widget.seekRequested.connect(positions.append)
    qtbot.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(400, 50))
    qtbot.mouseMove(widget, QPoint(600, 50))
    qtbot.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(700, 50))
    assert len(positions) >= 2
    assert abs(positions[-1] - 700) <= 2
