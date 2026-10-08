"""화면을 멈춰 영역을 고르게 하고, 잘라낸 실제 픽셀 이미지를 넘긴다.

찍은 화면 전체는 선택하거나 취소하는 즉시 버린다. 임시 파일을 만들지 않는다.
보안 프로그램이 캡처를 막으면(거의 검은 화면) 안내만 하고 우회하지 않는다.
"""
from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

MIN_SELECTION = 8
BLOCKED_LUMA = 8
BLOCKED_RATIO = 0.98
SAMPLE_GRID = 64
DIM = QColor(6, 12, 22, 140)
ACCENT = QColor("#E8590C")


def grab_screens():
    """연결된 모든 화면을 (논리 좌표 영역, 실제 픽셀 pixmap)으로 찍는다."""
    return [(screen.geometry(), screen.grabWindow(0)) for screen in QGuiApplication.screens()]


def is_blocked(image):
    """격자 표본의 98% 이상이 거의 검은색이면 캡처가 막힌 것으로 본다."""
    if image.isNull() or image.width() == 0 or image.height() == 0:
        return True
    dark = total = 0
    for gy in range(SAMPLE_GRID):
        y = min(image.height() - 1, gy * image.height() // SAMPLE_GRID)
        for gx in range(SAMPLE_GRID):
            x = min(image.width() - 1, gx * image.width() // SAMPLE_GRID)
            color = image.pixelColor(x, y)
            luma = (color.red() * 299 + color.green() * 587 + color.blue() * 114) // 1000
            dark += luma < BLOCKED_LUMA
            total += 1
    return dark >= BLOCKED_RATIO * total


def _physical(rect, ratio):
    return QRect(round(rect.x() * ratio), round(rect.y() * ratio),
                 round(rect.width() * ratio), round(rect.height() * ratio))


def crop_physical(pixmap, rect):
    """논리 좌표 선택을 pixmap의 device pixel ratio로 바꿔 실제 픽셀로 자른다."""
    physical = _physical(rect, pixmap.devicePixelRatio()).intersected(QRect(0, 0, pixmap.width(), pixmap.height()))
    return pixmap.copy(physical).toImage().convertToFormat(QImage.Format_RGB888)


class CaptureOverlay(QWidget):
    """한 화면을 덮는 멈춘 화면. 끌어서 사각형을 고른다(그 화면 안으로 제한)."""

    selected = Signal(QRect)
    cancelled = Signal()

    def __init__(self, geometry, pixmap):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setObjectName("screenTextCaptureOverlay")
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.pixmap = pixmap
        self._origin = None
        self._current = QRect()
        self.setGeometry(geometry)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.pixmap)
        painter.fillRect(self.rect(), DIM)
        if not self._current.isEmpty():
            painter.drawPixmap(self._current, self.pixmap, _physical(self._current, self.pixmap.devicePixelRatio()))
            painter.setPen(QPen(ACCENT, 2))
            painter.drawRect(self._current.adjusted(0, 0, -1, -1))
            painter.drawText(self._current.topLeft() + QPoint(0, -6),
                             f"{self._current.width()} × {self._current.height()}")
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.cancelled.emit()
        elif event.button() == Qt.LeftButton:
            self._origin = event.position().toPoint()
            self._current = QRect(self._origin, self._origin)
            self.update()

    def mouseMoveEvent(self, event):
        if self._origin is not None:
            self._current = QRect(self._origin, event.position().toPoint()).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self._origin is None:
            return
        self._origin = None
        rect = QRect(self._current)
        if rect.width() < MIN_SELECTION or rect.height() < MIN_SELECTION:
            self._current = QRect()
            self.update()
            return
        self.selected.emit(rect)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class ScreenCapture(QObject):
    """모든 화면에 오버레이를 띄우고 한 곳의 선택 결과만 넘긴다."""

    captured = Signal(QImage)
    cancelled = Signal()
    blocked = Signal()

    def __init__(self, parent=None, grab=grab_screens):
        super().__init__(parent)
        self._grab = grab
        self.overlays = []

    def is_active(self):
        return bool(self.overlays)

    def start(self):
        self._close_overlays()
        shots = self._grab()
        if not shots or all(is_blocked(pixmap.toImage()) for _, pixmap in shots):
            self.blocked.emit()
            return
        for geometry, pixmap in shots:
            overlay = CaptureOverlay(geometry, pixmap)
            overlay.selected.connect(lambda rect, source=overlay: self._finish(source, rect))
            overlay.cancelled.connect(self.cancel)
            self.overlays.append(overlay)
            overlay.show()
        cursor = QCursor.pos()
        focus = next((o for o in self.overlays if o.geometry().contains(cursor)), self.overlays[0])
        focus.raise_()
        focus.activateWindow()
        focus.setFocus(Qt.OtherFocusReason)

    def cancel(self, notify=True):
        """오버레이를 닫고 찍은 화면을 버린다. 진행 중이었고 notify이면 cancelled를 보낸다."""
        if self._close_overlays() and notify:
            self.cancelled.emit()

    def _close_overlays(self):
        overlays, self.overlays = self.overlays, []
        for overlay in overlays:
            overlay.pixmap = QPixmap()
            overlay.hide()
            overlay.deleteLater()
        return bool(overlays)

    def _finish(self, overlay, rect):
        image = crop_physical(overlay.pixmap, rect)
        self._close_overlays()
        self.captured.emit(image)
