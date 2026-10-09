"""화면 글자 따기 사용법 애니메이션 위젯 (QPainter 벡터 그림, 실제 화면을 찍지 않는다)."""
import numpy as np
import pytest
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest

from screen_text.guide import CAPTIONS, UsageGuide

ORANGE, YELLOW, ACCENT = "#E8590C", "#FFE58A", "#2563EB"
FRAMES = (0.15, 0.5, 0.85)


@pytest.fixture
def guide(qtbot):
    widget = UsageGuide()
    qtbot.addWidget(widget)
    widget.resize(widget.sizeHint())
    return widget


def render(widget, progress):
    widget.set_progress(progress)
    picture = widget.grab().toImage()
    assert not picture.isNull()
    return picture


def pixels(picture):
    picture = picture.convertToFormat(QImage.Format_RGB32)
    raw = np.frombuffer(bytes(picture.constBits()), dtype=np.uint8)
    rows = raw.reshape(picture.height(), picture.bytesPerLine() // 4, 4)
    return rows[:, :picture.width(), :3][:, :, ::-1].astype(int)  # BGRA -> RGB


def near(picture, color, rows=None, tolerance=30):
    """picture의 위쪽 rows줄(그림 영역)에서 color에 가까운 픽셀 수. 설명 글자의 서브픽셀 색 번짐은 제외한다."""
    target = np.array(QColor(color).getRgb()[:3])
    area = pixels(picture)[:rows]
    return int((np.abs(area - target).max(axis=2) <= tolerance).sum())


def test_three_steps_render_distinct_frames_with_step_colors(guide):
    first, second, third = (render(guide, p) for p in FRAMES)
    assert guide.step() == 2  # 마지막으로 그린 프레임은 3단계
    assert pixels(first).tobytes() != pixels(second).tobytes()
    assert pixels(second).tobytes() != pixels(third).tobytes()
    assert pixels(first).tobytes() != pixels(third).tobytes()
    rows = int(guide.scene_rect().bottom())
    assert near(second, ORANGE, rows) >= 20  # 2단계: 주황 상자
    assert near(third, YELLOW, rows) >= 100  # 3단계: 확인 필요 노란 칸
    assert near(first, YELLOW, rows) == 0 and near(second, YELLOW, rows) == 0
    assert near(first, ORANGE, rows) >= 10  # 1단계: 점선 선택 영역


def test_step_follows_progress_thirds_and_clamps(guide):
    expected = {-0.5: 0, 0.0: 0, 0.15: 0, 0.33: 0, 0.34: 1, 0.5: 1, 0.66: 1, 0.67: 2, 0.85: 2, 1.0: 2, 3.0: 2}
    for progress, step in expected.items():
        guide.set_progress(progress)
        assert guide.step() == step, progress
    guide.set_progress(7.0)
    assert guide.progress() == 1.0
    guide.set_progress(-1.0)
    assert guide.progress() == 0.0


def test_step_dots_mark_the_current_step_with_accent_color(guide):
    centers = []
    for progress in FRAMES:
        picture = render(guide, progress)
        bottom = pixels(picture)[-picture.height() // 6:]  # 아래 점 줄만
        mask = np.abs(bottom - np.array(QColor(ACCENT).getRgb()[:3])).max(axis=2) <= 30
        assert mask.sum() > 0
        centers.append(np.nonzero(mask)[1].mean())
    assert centers[0] < centers[1] < centers[2]


def test_caption_matches_each_step(guide):
    assert CAPTIONS == (
        "① 끌어서 글자가 있는 영역을 고릅니다",
        "② PC 안에서 글자를 읽습니다 (인터넷 없음)",
        "③ 표 모양 그대로 한글·엑셀에 붙여넣습니다",
    )
    for progress, text in zip(FRAMES, CAPTIONS):
        guide.set_progress(progress)
        assert guide.caption() == text


def test_widget_contract_hints_and_accessibility(qtbot):
    widget = UsageGuide()
    qtbot.addWidget(widget)
    assert abs(widget.sizeHint().width() - 420) <= 8 and abs(widget.sizeHint().height() - 236) <= 8
    assert widget.minimumSizeHint().height() <= 160 and widget.minimumSizeHint().width() <= 300
    assert widget.toolTip() == "누르면 처음부터 다시 봅니다"
    assert widget.accessibleName() == "화면 글자 따기 사용법"
    assert widget.cursor().shape() == Qt.PointingHandCursor
    assert not widget.is_running()  # 보이기 전에는 돌지 않는다


def test_runs_only_while_shown(qtbot, guide):
    guide.show()
    qtbot.waitExposed(guide)
    assert guide.is_running()
    guide.hide()
    assert not guide.is_running()
    guide.show()
    assert guide.is_running()
    guide.stop()
    assert not guide.is_running()
    guide.start()
    assert guide.is_running()


def test_animation_advances_while_running(qtbot, guide):
    guide.show()
    qtbot.waitExposed(guide)
    guide.restart()
    qtbot.waitUntil(lambda: guide.progress() > 0.05, timeout=3000)
    assert guide.is_running()


def test_set_progress_stops_the_animation(qtbot, guide):
    guide.show()
    qtbot.waitExposed(guide)
    guide.set_progress(0.6)
    assert not guide.is_running() and guide.progress() == pytest.approx(0.6)


def test_left_click_restarts_from_the_beginning(qtbot, guide):
    guide.show()
    qtbot.waitExposed(guide)
    guide.set_progress(0.8)
    assert not guide.is_running()
    QTest.mouseClick(guide, Qt.RightButton, pos=QPoint(20, 20))
    assert not guide.is_running() and guide.progress() == pytest.approx(0.8)  # 오른쪽 클릭은 무시
    QTest.mouseClick(guide, Qt.LeftButton, pos=QPoint(20, 20))
    assert guide.is_running() and guide.progress() < 0.1


@pytest.mark.parametrize("size", [(300, 160), (280, 160), (424, 236), (640, 480), (150, 90)])
def test_renders_in_compressed_and_large_sizes_without_clipping(guide, size):
    guide.resize(QSize(*size))
    for progress in (0.0, 0.15, 0.5, 0.85, 1.0):
        picture = render(guide, progress)
        assert picture.width() > 0 and picture.height() > 0
    scene, caption = guide.scene_rect(), guide.caption_rect()
    assert guide.rect().adjusted(0, 0, 1, 1).contains(scene.toAlignedRect())
    assert scene.bottom() <= caption.top() + 1
    assert scene.width() / scene.height() == pytest.approx(420 / 190, rel=0.02)


def test_scene_fills_the_width_at_the_hint_size(guide):
    guide.resize(guide.sizeHint())
    scene = guide.scene_rect()
    assert scene.width() >= guide.width() * 0.95 and scene.height() >= 150
