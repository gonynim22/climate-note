"""캘린더 날짜 칸 구분선 (v4.9 A안 · 가는 격자선, 표시 전용).

설정 스위치(`calendar_grid_lines_enabled`, 키가 없으면 꺼짐)가 켜졌을 때만 보인다. 칸과 칸 사이 1px 틈에만
선을 긋고, 바깥 틀(맨 위·맨 아래·좌우 끝)과 요일 머리줄 아래에는 긋지 않는다. 이번 달 밖의 빈 칸 사이에도
이어 그어 격자가 끊기지 않는다. 선 자리는 그릴 때마다 칸의 실제 위치에서 읽는다.

마우스는 통과하고, 칸과 여러 날 막대(`CalendarSpanOverlay`)보다 아래 층이라 아무것도 가리지 않는다.
배율이 1이 아니어도 장치 1픽셀 선으로 긋는다(1px 논리 선을 그대로 칠하면 1.25배에서 1~2 장치 픽셀로
두께가 들쭉날쭉하다). DB를 읽거나 쓰지 않는다.
"""
import math

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

LINE_COLOR = "#E3E6EA"
LINES_SPACING = 1   # 선을 켰을 때 칸 사이 틈(선이 놓이는 자리)
PLAIN_SPACING = 2   # 선을 껐을 때 칸 사이 틈(v4.8까지와 같다)


class CalendarGridLines(QWidget):
    def __init__(self, section: QWidget):
        super().__init__(section)
        self.setObjectName("calendarGridLines")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._cells: list[list[QWidget]] = []
        section.installEventFilter(self)
        self.hide()

    def set_cells(self, cells, *, visible: bool) -> None:
        """cells: 주마다 7칸(빈 칸 포함). visible: 설정 스위치가 켜졌는가."""
        self._cells = [list(row) for row in cells]
        self.setVisible(visible and bool(self._cells))
        self._sync_geometry()

    def clear(self) -> None:
        """칸을 새로 만들기 전에 옛 칸 참조를 놓는다(지워질 칸을 그리지 않는다)."""
        self.set_cells([], visible=False)

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() in (
                QEvent.Resize, QEvent.LayoutRequest, QEvent.Show):
            self._sync_geometry()
        return False

    def _sync_geometry(self) -> None:
        if self.isHidden():
            return
        # 캘린더 영역 전체를 덮는다. 격자 위치는 영역 크기가 그대로여도 옆 배치에 따라 움직이므로
        # (기본 크기의 일정 목록 등) 선 길이는 그릴 때마다 칸 위치에서 잰다.
        self.setGeometry(self.parentWidget().rect())
        self.lower()  # 칸·막대 아래. 칸은 틈에 아무것도 그리지 않으므로 선이 보인다.
        self.update()

    def _local(self, widget: QWidget, point: QPoint) -> QPoint:
        return widget.mapTo(self.parentWidget(), point) - self.pos()

    def _bounds(self) -> tuple[int, int, int, int]:
        """(왼쪽, 위, 오른쪽, 아래): 칸 전체가 차지하는 범위. 선은 이 안에서만 긋는다."""
        first, last = self._cells[0][0], self._cells[-1][-1]
        top_left = self._local(first, QPoint(0, 0))
        bottom_right = self._local(last, QPoint(last.width(), last.height()))
        return top_left.x(), top_left.y(), bottom_right.x(), bottom_right.y()

    def line_positions(self) -> tuple[list[float], list[float]]:
        """(세로선 x, 가로선 y): 이웃한 두 칸 사이 틈의 가운데(이 위젯 좌표, 논리 px)."""
        if not self._cells or not self._cells[0]:
            return [], []
        first_row = self._cells[0]
        xs = [
            (self._local(left, QPoint(left.width(), 0)).x() + self._local(right, QPoint(0, 0)).x()) / 2
            for left, right in zip(first_row, first_row[1:])
        ]
        ys = [
            (self._local(upper[0], QPoint(0, upper[0].height())).y()
             + self._local(lower[0], QPoint(0, 0)).y()) / 2
            for upper, lower in zip(self._cells, self._cells[1:])
        ]
        return xs, ys

    def paintEvent(self, event):
        xs, ys = self.line_positions()
        if not xs and not ys:
            return
        left, top, right, bottom = self._bounds()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        pen = QPen(QColor(LINE_COLOR))
        pen.setCosmetic(True)
        pen.setWidth(0)  # 배율과 무관하게 장치 1픽셀
        painter.setPen(pen)
        ratio = self.devicePixelRatioF() or 1.0

        def snap(value: float) -> float:
            # value가 들어 있는 장치 픽셀의 가운데(틈 가운데의 선, 선의 시작).
            return (math.floor(value * ratio) + 0.5) / ratio

        def last(value: float) -> float:
            # value 바로 앞 장치 픽셀의 가운데(칸 범위 끝은 포함하지 않는다).
            return (math.ceil(value * ratio) - 0.5) / ratio

        for x in xs:
            painter.drawLine(QPointF(snap(x), snap(top)), QPointF(snap(x), last(bottom)))
        for y in ys:
            painter.drawLine(QPointF(snap(left), snap(y)), QPointF(last(right), snap(y)))
