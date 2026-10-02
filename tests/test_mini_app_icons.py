"""미니앱 SVG 아이콘 규칙(AGENTS.md 아이콘 디자인 규칙)과 실제 QtSvg 렌더를 검증한다."""
import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from app_paths import resource_root

ICON_DIR = resource_root() / "resources" / "icons" / "mini_apps"
APP_ICONS = {
    "unit_converter": ("#22B8CF", "#0B7285"),
    "date_time": ("#4C8DF6", "#1D4ED8"),
    "money_notation": ("#40C074", "#1E8E4E"),
    "document_converter": ("#9775FA", "#6741D9"),
}
ALL_ICONS = [*APP_ICONS, "upcoming", "launcher"]


@pytest.fixture(autouse=True)
def gui(qapp):
    # QPainter 렌더에는 QGuiApplication이 필요하다.
    yield


def render(name, size):
    renderer = QSvgRenderer(str(ICON_DIR / f"{name}.svg"))
    assert renderer.isValid(), name
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def distance(color, expected):
    target = QColor(expected)
    return (abs(color.red() - target.red()) + abs(color.green() - target.green())
            + abs(color.blue() - target.blue()))


def is_white(color):
    return color.alpha() == 255 and min(color.red(), color.green(), color.blue()) >= 235


@pytest.mark.parametrize("name", ALL_ICONS)
def test_icon_is_self_contained_qt_tiny_svg(name):
    path = ICON_DIR / f"{name}.svg"
    with open(path, encoding="utf-8") as stream:
        text = stream.read()
    for banned in ("<text", "<image", "<filter", "<mask", "<style", "http://w", "https://", "@import", "xlink:href"):
        if banned == "http://w":
            # SVG 네임스페이스 선언만 허용하고 다른 외부 주소는 금지한다.
            assert text.count("http://www.w3.org/2000/svg") == text.count("http://"), name
            continue
        assert banned not in text, (name, banned)
    assert QSvgRenderer(str(path)).isValid()


@pytest.mark.parametrize("name,colors", APP_ICONS.items())
@pytest.mark.parametrize("scale", [1, 1.25, 1.5])
def test_app_icon_has_gradient_rounded_corners_and_white_glyph(name, colors, scale):
    size = round(48 * scale)
    image = render(name, size)
    start, end = colors
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(size - 1, size - 1).alpha() == 0
    assert distance(image.pixelColor(round(size * .16), round(size * .10)), start) <= 90
    assert distance(image.pixelColor(round(size * .84), round(size * .90)), end) <= 90
    inner = range(round(size * .2), round(size * .8))
    white = sum(1 for x in inner for y in inner if is_white(image.pixelColor(x, y)))
    assert white >= size, (name, white)


@pytest.mark.parametrize("scale", [1, 1.25, 1.5])
def test_date_time_clock_face_is_white(scale):
    size = round(48 * scale)
    image = render("date_time", size)
    # 시계 면(24 격자 (13.5,16.5))은 흰색이다. 바늘(x=17)과 안티에일리어싱이 닿지 않는 지점.
    x = round((9.6 + 13.5 * 1.2) / 48 * size)
    y = round((9.6 + 16.5 * 1.2) / 48 * size)
    assert is_white(image.pixelColor(x, y))


@pytest.mark.parametrize("scale", [1, 1.25, 1.5])
def test_upcoming_icon_is_dashed_outline_with_transparent_body(scale):
    size = round(48 * scale)
    image = render("upcoming", size)
    corner = round(12 / 48 * size)
    assert image.pixelColor(corner, corner).alpha() == 0
    row = max(1, round(1 / 48 * size))
    x_start = round(14 / 48 * size)
    x_end = round(34 / 48 * size)
    top = [image.pixelColor(x, row).alpha() > 128 for x in range(x_start, x_end)]
    assert any(top) and not all(top)
    center = round(24 / 48 * size)
    assert image.pixelColor(center, center).alpha() == 255


@pytest.mark.parametrize("size", [20, 25, 30, 40])
def test_launcher_icon_keeps_blue_accent(size):
    image = render("launcher", size)
    center = round(17 / 24 * size)
    assert distance(image.pixelColor(center, center), "#2563EB") <= 60
    assert image.pixelColor(round(7 / 24 * size), round(7 / 24 * size)).alpha() == 0
