"""표 칸과 글자 줄 사이의 표시(○ ● ◎ ■ ★ ▶)를 모양으로 읽는다. 위치 찾기가 상자를 내지 않아 표의 내용이 조용히 사라졌다."""
import numpy as np
import pytest
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from screen_text.cell_marks import empty_cell_boxes, gap_mark_boxes, mark_of, read_marks
from screen_text.engine import OcrEngine, rgb_from_buffer
from screen_text.layout import Grid, GridCell, Table, build_blocks
from screen_text.table_lines import _holds_text


def disc(n):
    yy, xx = np.mgrid[0:n, 0:n]
    return np.hypot(yy - (n - 1) / 2, xx - (n - 1) / 2) <= n / 2


def ring(n, stroke=2):
    yy, xx = np.mgrid[0:n, 0:n]
    radius = np.hypot(yy - (n - 1) / 2, xx - (n - 1) / 2)
    return (radius <= n / 2) & (radius > n / 2 - stroke)


def diamond(n):
    yy, xx = np.mgrid[0:n, 0:n]
    return np.abs(yy - (n - 1) / 2) + np.abs(xx - (n - 1) / 2) <= n / 2


def hollow_diamond(n):
    yy, xx = np.mgrid[0:n, 0:n]
    distance = np.abs(yy - (n - 1) / 2) + np.abs(xx - (n - 1) / 2)
    return (distance <= n / 2) & (distance > n / 2 - 2)


def hollow_square(n):
    mask = np.ones((n, n), bool)
    mask[2:-2, 2:-2] = False
    return mask


def target(n):
    yy, xx = np.mgrid[0:n, 0:n]
    return ring(n) | (np.hypot(yy - (n - 1) / 2, xx - (n - 1) / 2) <= n / 5)


def triangle(n):
    return np.array([[abs(x - (n * 1.2 - 1) / 2) <= (y + 1) * .6 for x in range(int(n * 1.2))] for y in range(n)])


@pytest.mark.parametrize("size", [11, 14, 18, 24])
@pytest.mark.parametrize("glyph, expected", [(disc, "●"), (ring, "○"), (diamond, "◆"), (hollow_diamond, "◇"), (hollow_square, "□"), (target, "◎"), (triangle, "▲")])
def test_marks_are_read_by_shape(size, glyph, expected):
    assert mark_of(glyph(size)) == expected


def test_filled_square():
    assert mark_of(np.ones((14, 14), bool)) == "■"


@pytest.mark.parametrize("name, glyph", [
    ("숫자 0처럼 좁다", ring(14)[:, 3:11]),
    ("왼쪽이 곧은 D", ring(14) | (np.arange(14)[None, :] < 2) & np.ones((14, 14), bool)),
    ("오른쪽이 트인 C", ring(14) & ~((np.arange(14)[:, None] > 4) & (np.arange(14)[:, None] < 9) & (np.arange(14)[None, :] > 8))),
])
def test_letters_are_not_marks(name, glyph):
    assert mark_of(glyph) is None


def test_too_small_to_tell():
    assert mark_of(disc(4)) is None


def sheet(cells, rows=2, columns=3, side=40):
    """rows×columns 표. cells는 {(행, 열): 글자 마스크}. (이미지, 격자)"""
    image = np.full((rows * side + 21, columns * side + 21, 3), 255, np.uint8)
    for row in range(rows + 1):
        image[10 + row * side] = 0
    for column in range(columns + 1):
        image[:, 10 + column * side] = 0
    image[:10] = image[-10:] = 255
    image[:, :10] = image[:, -10:] = 255
    for (row, column), mask in cells.items():
        y = 10 + row * side + (side - mask.shape[0]) // 2
        x = 10 + column * side + (side - mask.shape[1]) // 2
        image[y:y + mask.shape[0], x:x + mask.shape[1]][mask] = 0
    grid = Grid(rows, columns, tuple(GridCell(r, c, 1, 1, 10 + c * side, 10 + r * side, 10 + (c + 1) * side, 10 + (r + 1) * side) for r in range(rows) for c in range(columns)),
                10, 10, 10 + columns * side, 10 + rows * side)
    return image, grid


BOX = (14, 14, 44, 34)   # 첫 칸의 글자 상자


def test_empty_cell_with_a_mark_gets_a_box():
    image, grid = sheet({(0, 1): disc(16)})
    found = empty_cell_boxes(image, [grid], [BOX])
    assert len(found) == 1 and 50 <= found[0][0] <= 66 and 18 <= found[0][1] <= 30


def test_blank_cells_stay_blank():
    image, grid = sheet({})
    assert empty_cell_boxes(image, [grid], [BOX]) == []


def test_cell_with_text_is_left_to_the_model():
    image, grid = sheet({(0, 0): disc(16)})
    assert empty_cell_boxes(image, [grid], [BOX]) == []


def test_picture_filling_a_cell_is_not_a_mark():
    image, grid = sheet({(0, 1): np.ones((36, 36), bool)})
    assert empty_cell_boxes(image, [grid], [BOX]) == []


def test_narrow_cell_does_not_stop_recognition():
    """표 선을 빼면 남는 픽셀이 없는 칸에서 인식 전체가 멈췄다(ValueError)."""
    image, grid = sheet({})
    narrow = Grid(1, 1, (GridCell(0, 0, 1, 1, 10, 10, 11, 90),), 10, 10, 11, 90)
    assert empty_cell_boxes(image, [narrow], [BOX]) == []
    assert _holds_text(narrow, [], image) is False


def result(text, score=.9):
    return (text, score, 0)


def test_new_box_takes_the_shape_of_its_mark():
    image, grid = sheet({(0, 1): disc(16)})
    boxes = [BOX, (56, 22, 74, 40)]
    assert read_marks(image, [grid], boxes, [result("구분"), result("")], 1)[1] == ("●", 1.0, 0)


def test_model_reading_of_a_lone_mark_gives_way_to_the_shape():
    """모델은 ▶를 →로, ◎를 ㅇ으로 읽는다."""
    image, grid = sheet({(0, 1): target(18)})
    boxes = [BOX, (56, 22, 74, 40)]
    assert read_marks(image, [grid], boxes, [result("구분"), result("ㅇ")], 2)[1][0] == "◎"


def test_ring_stays_flagged_as_unsure():
    image, grid = sheet({(0, 1): ring(16)})
    boxes = [BOX, (56, 22, 74, 40)]
    assert read_marks(image, [grid], boxes, [result("구분"), result("")], 1)[1] == ("○", 1.0, 1)


@pytest.mark.parametrize("text", ["실적", "계", "15", "V"])
def test_lone_text_in_a_cell_is_never_replaced(text):
    image, grid = sheet({(0, 1): ring(16)})
    boxes = [BOX, (56, 22, 74, 40)]
    assert read_marks(image, [grid], boxes, [result("구분"), result(text)], 2)[1][0] == text


def test_letter_a_is_not_a_hollow_star():
    """칸의 'A' 23건이 ☆로 바뀌었다. 모델이 읽은 영문자는 속이 찬 표시에만 자리를 내준다."""
    a = np.zeros((14, 14), bool)
    for y in range(14):
        half = y // 2
        a[y, max(0, 6 - half):max(0, 6 - half) + 2] = True
        a[y, min(12, 6 + half):min(12, 6 + half) + 2] = True
    a[9, 3:11] = True
    image, grid = sheet({(0, 1): a})
    boxes = [BOX, (56, 22, 74, 40)]
    assert read_marks(image, [grid], boxes, [result("구분"), result("A")], 2)[1][0] == "A"


def test_shaded_cell_does_not_turn_into_a_mark():
    """옅은 바탕의 칸 전체가 글자 픽셀로 보여 '실적'이 '-'로 바뀌었다."""
    image, grid = sheet({})
    image[11:50, 51:90] = 200
    boxes = [BOX, (56, 22, 84, 40)]
    assert read_marks(image, [grid], boxes, [result("구분"), result("계획")], 2)[1][0] == "계획"


def test_table_of_only_marks_keeps_its_grid():
    """표시 칸은 상자가 없어 글자 든 칸이 모자라 격자를 통째로 버렸다."""
    cells = {(row, column): disc(16) for row in range(4) for column in range(1, 6)}
    image, grid = sheet(cells, rows=4, columns=6)
    boxes = [(14, 14 + row * 40, 44, 34 + row * 40) for row in range(4)]
    assert _holds_text(grid, boxes, image)


def test_empty_frame_is_still_not_a_table():
    image, grid = sheet({}, rows=4, columns=6)
    assert not _holds_text(grid, [(14, 14, 44, 34)], image)


def line_of(mask, gap=20):
    image = np.full((30, 200, 3), 255, np.uint8)
    image[5:25, 10:60, :] = 255
    for x in range(10, 60, 4):
        image[5:25, x:x + 2] = 0
    for x in range(120, 180, 4):
        image[5:25, x:x + 2] = 0
    image[7:7 + mask.shape[0], 80:80 + mask.shape[1]][mask] = 0
    return image, [(10, 4, 60, 26), (120, 4, 180, 26)]


def test_mark_between_words_gets_a_box():
    """'접수 ▶ 심사'처럼 글자 사이의 표시도 상자가 없어 사라졌다."""
    image, boxes = line_of(np.rot90(triangle(16), -1))
    found = gap_mark_boxes(image, boxes)
    assert len(found) == 1 and found[0][0] >= 78


def test_bullet_of_the_next_word_is_left_to_the_leading_rule():
    """'■ 광역시'의 ■는 뒤 상자의 글머리로 읽히므로 또 내면 '■ ■'가 된다."""
    image, boxes = line_of(np.ones((16, 16), bool))
    boxes = [boxes[0], (100, 4, 180, 26)]
    assert gap_mark_boxes(image, boxes) == []


def test_hollow_shape_between_words_is_not_trusted():
    image, boxes = line_of(ring(16))
    assert gap_mark_boxes(image, boxes) == []


def render_table(mark):
    font = QFont("Malgun Gothic")
    font.setPixelSize(16)
    image = QImage(420, 130, QImage.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    for y in (6, 46, 86, 126):
        painter.drawLine(6, y, 414, y)
    for x in (6, 170, 250, 330, 414):
        painter.drawLine(x, 6, x, 126)
    for row, name in enumerate(("점검 항목", "수질 측정", "시설 관리")):
        painter.drawText(14, 32 + row * 40, name)
    for x, title in ((190, "1차"), (270, "2차"), (350, "3차")):
        painter.drawText(x, 32, title)
    for row in (1, 2):
        for x in (200, 280, 360):
            painter.drawText(x, 32 + row * 40, mark)
    painter.end()
    return rgb_from_buffer(image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits()))


@pytest.fixture(scope="module")
def ocr():
    return OcrEngine()


@pytest.mark.parametrize("mark", ["●", "■", "◆", "▲"])
def test_real_model_keeps_marks_in_a_checklist(qapp, ocr, mark):
    table = next(block for block in build_blocks(ocr.recognize(render_table(mark))) if isinstance(block, Table))
    assert [[cell.text for cell in row[1:]] for row in table.rows[1:]] == [[mark] * 3] * 2
