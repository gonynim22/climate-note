"""화면 글자 따기 화면 멈춤·영역 선택 (가짜 스크린샷만 사용, 실제 화면을 찍지 않는다)."""
import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from screen_text.capture import ScreenCapture, crop_physical, is_blocked


def fake_shot(geometry, ratio=1.0, fill="white"):
    """논리 (40, 20, 30×10) 위치에 검은 사각형이 있는 화면."""
    pixmap = QPixmap(round(geometry.width() * ratio), round(geometry.height() * ratio))
    pixmap.fill(QColor(fill))
    painter = QPainter(pixmap)
    painter.fillRect(QRect(round(40 * ratio), round(20 * ratio), round(30 * ratio), round(10 * ratio)), QColor("black"))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return geometry, pixmap


def drag(qtbot, overlay, start, end):
    qtbot.mousePress(overlay, Qt.LeftButton, pos=start)
    qtbot.mouseMove(overlay, end)
    qtbot.mouseRelease(overlay, Qt.LeftButton, pos=end)


def started(qtbot, shots):
    capture = ScreenCapture(grab=lambda: shots)
    got = {"captured": [], "cancelled": 0, "blocked": 0}
    capture.captured.connect(got["captured"].append)
    capture.cancelled.connect(lambda: got.__setitem__("cancelled", got["cancelled"] + 1))
    capture.blocked.connect(lambda: got.__setitem__("blocked", got["blocked"] + 1))
    capture.start()
    for overlay in capture.overlays:
        qtbot.waitExposed(overlay)
    return capture, got


@pytest.mark.parametrize("ratio", [1.0, 1.25, 1.5])
def test_drag_selection_crops_physical_pixels_on_scaled_screen(qtbot, ratio):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 400, 300), ratio)])
    drag(qtbot, capture.overlays[0], QPoint(40, 20), QPoint(69, 29))
    image = got["captured"][0]
    assert image.size() == QSize(round(30 * ratio), round(10 * ratio))
    assert image.format() == QImage.Format_RGB888
    assert image.pixelColor(image.width() // 2, image.height() // 2) == QColor("black")
    assert not capture.is_active()


def test_drag_past_screen_edge_is_clipped_to_that_screen(qtbot):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 400, 300))])
    drag(qtbot, capture.overlays[0], QPoint(390, 290), QPoint(500, 420))
    assert got["captured"][0].size() == QSize(10, 10)


def test_crop_physical_rounds_fractional_ratio_and_clips():
    _, pixmap = fake_shot(QRect(0, 0, 100, 80), 1.25)
    assert crop_physical(pixmap, QRect(10, 10, 9, 7)).size() == QSize(11, 9)
    # (112, 88, 62, 62)를 125×100 pixmap 경계로 자른다 (Python round는 .5를 짝수로)
    assert crop_physical(pixmap, QRect(90, 70, 50, 50)).size() == QSize(13, 12)


def test_second_screen_selection_uses_its_own_pixmap(qtbot):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 200, 150), 1.0),
                                   fake_shot(QRect(0, 0, 200, 150), 1.5, fill="#DDDDDD")])
    assert len(capture.overlays) == 2
    # QTest는 널 좌표 QPoint(0, 0)을 "위젯 중앙"으로 바꿔 보내므로 모서리 대신 (10, 10)에서 시작한다.
    drag(qtbot, capture.overlays[1], QPoint(10, 10), QPoint(29, 19))
    assert got["captured"][0].size() == QSize(30, 15)
    assert got["captured"][0].pixelColor(1, 1) == QColor("#DDDDDD")
    assert not capture.overlays


def test_small_drag_is_ignored_then_escape_cancels_and_discards(qtbot):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 400, 300))])
    overlay = capture.overlays[0]
    drag(qtbot, overlay, QPoint(10, 10), QPoint(14, 13))
    assert got["captured"] == [] and capture.is_active()
    qtbot.keyClick(overlay, Qt.Key_Escape)
    assert got["cancelled"] == 1
    assert overlay.pixmap.isNull()
    assert not capture.is_active()


def test_right_click_cancels(qtbot):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 400, 300))])
    qtbot.mouseClick(capture.overlays[0], Qt.RightButton, pos=QPoint(5, 5))
    assert got["cancelled"] == 1 and not capture.is_active()


def test_cancel_without_notify_and_twice_is_quiet(qtbot):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 400, 300))])
    capture.cancel(notify=False)
    capture.cancel()
    assert got["cancelled"] == 0 and not capture.is_active()


def test_black_screen_is_blocked_without_overlay(qtbot):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 400, 300), fill="black")])
    assert got["blocked"] == 1 and not capture.overlays


def test_is_blocked_threshold():
    image = QImage(100, 100, QImage.Format_RGB888)
    image.fill(QColor("black"))
    assert is_blocked(image)
    painter = QPainter(image)
    painter.fillRect(QRect(0, 0, 100, 5), QColor("white"))   # 표본의 약 5%가 밝다
    painter.end()
    assert not is_blocked(image)
    assert is_blocked(QImage())
