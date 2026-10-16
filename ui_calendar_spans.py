"""중간·크게 달력의 여러 날 일정 막대 (v4.1).

칸 위에 그리기만 하고 마우스는 통과시킨다. 막대 위치는 그릴 때마다 칸과 칸의 칩 자리에서
다시 읽으므로 크기·배율이 바뀌어도 칩과 같은 선(시작 6px·끝 4px)에 맞는다.
"""
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from schedule_rules import SpanSegment

BAR_RADIUS = 4.0


@dataclass(frozen=True)
class SpanBar:
    """그릴 막대 한 조각."""

    segment: SpanSegment
    text: str
    color: str


class CalendarSpanOverlay(QWidget):
    def __init__(self, section: QWidget, grid_layout):
        super().__init__(section)
        self.setObjectName("calendarSpanOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._grid = grid_layout
        self._cells: list[list[QWidget]] = []
        self._bars: list[SpanBar] = []
        self._font_px = 10
        section.installEventFilter(self)
        self.hide()

    def set_bars(self, cells, bars, *, font_px: int, visible: bool) -> None:
        """cells: 주마다 7칸(CalendarDayButton), bars: SpanBar 목록."""
        self._cells = [list(row) for row in cells]
        self._bars = list(bars)
        self._font_px = font_px
        self.setVisible(visible and bool(self._bars))
        self._sync_geometry()

    def bars(self) -> list[SpanBar]:
        return list(self._bars)

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() in (
                QEvent.Resize, QEvent.LayoutRequest, QEvent.Show):
            self._sync_geometry()
        return False

    def _sync_geometry(self) -> None:
        if self.isHidden():
            return
        self.setGeometry(self._grid.geometry())
        self.raise_()
        self.update()

    def _local(self, widget: QWidget, point: QPoint) -> QPoint:
        return widget.mapTo(self.parentWidget(), point) - self.pos()

    def bar_rects(self) -> list[tuple[SpanBar, QRectF]]:
        """지금 칸 배치에서 보이는 막대와 그 사각형(이 위젯 좌표)."""
        result = []
        for bar in self._bars:
            seg = bar.segment
            if seg.row >= len(self._cells):
                continue
            row = self._cells[seg.row]
            first, last = row[seg.first_col], row[seg.last_col]
            if seg.lane >= min(first.span_lane_cap, last.span_lane_cap):
                continue  # 칸에 자리가 없는 차선은 그날 '+N 더'로 센다.
            container = first.chips_container
            margins = first.chips_layout.contentsMargins()
            top_left = self._local(container, QPoint(0, 0))
            first_left = self._local(first, QPoint(0, 0)).x()
            last_right = self._local(last, QPoint(last.width(), 0)).x()
            last_container_right = self._local(
                last.chips_container, QPoint(last.chips_container.width(), 0)).x()
            left = top_left.x() + margins.left() if seg.starts else first_left
            right = last_container_right - margins.right() if seg.ends else last_right
            step = first.chip_height + first.chip_spacing
            top = top_left.y() + seg.lane * step
            if right - left < 4:
                continue
            result.append((bar, QRectF(left, top, right - left, first.chip_height)))
        return result

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        font = self.font()
        font.setPixelSize(self._font_px)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        for bar, rect in self.bar_rects():
            seg = bar.segment
            path = QPainterPath()
            path.addRoundedRect(rect, BAR_RADIUS, BAR_RADIUS)
            if not seg.starts:
                square = QPainterPath()
                square.addRect(QRectF(rect.left(), rect.top(), BAR_RADIUS * 2, rect.height()))
                path = path.united(square)
            if not seg.ends:
                square = QPainterPath()
                square.addRect(QRectF(rect.right() - BAR_RADIUS * 2, rect.top(), BAR_RADIUS * 2, rect.height()))
                path = path.united(square)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(bar.color))
            painter.drawPath(path)
            text_rect = rect.adjusted(4, 0, -4, 0)
            text = metrics.elidedText(bar.text, Qt.ElideRight, int(text_rect.width()))
            painter.setPen(QColor("#1A1A1A"))
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
