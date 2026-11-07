"""작은 글씨와 바짝 고른 영역: 여백, 패딩, 2배 확대, 글자별 확인 표시."""
import numpy as np
import pytest
from PySide6.QtGui import QColor, QFont, QImage, QPainter

import screen_text.engine as engine
from screen_text.engine import OcrEngine, _ctc_runs, _cut_line_boxes, _fragment_boxes, _scaled_grid, _shrunk_boxes, add_margin, double_size, resize_bilinear, rgb_from_buffer
from screen_text.layout import Cell, Grid, GridCell, TextBox, TextLine, build_blocks, plain_with_spans


def test_double_size_matches_bilinear_resize():
    rng = np.random.default_rng(3)
    image = rng.integers(0, 256, (17, 23, 3), dtype=np.uint8)
    fast = double_size(image)
    assert fast.shape == (34, 46, 3) and fast.dtype == np.uint8
    assert np.abs(fast.astype(int) - resize_bilinear(image, 46, 34)).max() <= 1


def test_add_margin_uses_edge_color_and_keeps_pixels():
    image = np.full((10, 20, 3), 240, np.uint8)
    image[4:6, 5:15] = 0
    padded = add_margin(image, 8)
    assert padded.shape == (26, 36, 3)
    assert (padded[0, 0] == 240).all()
    assert (padded[8:18, 8:28] == image).all()
    assert add_margin(image, 0) is image


def rule_row(rule=(90, 90, 90)):
    """표의 한 행만 고른 영역: 글자는 위아래가 비고 세로선은 끝에서 끝까지 이어진다."""
    image = np.full((20, 60, 3), 255, np.uint8)
    image[6:14, 8:30] = 0
    image[:, 45] = rule
    return image


def test_add_margin_continues_table_rule_past_the_selection():
    """여백에서 끊긴 세로선은 떠 있는 막대가 되어 '|'로 읽힌다(e1 한 줄 74건)."""
    padded = add_margin(rule_row(), 8)
    assert (padded[:, 8 + 45] == (90, 90, 90)).all()
    assert (padded[0, 8 + 44] == 255).all() and (padded[0, 8 + 46] == 255).all()


def test_add_margin_leaves_glyph_stems_of_tight_selection():
    """바짝 고른 글자의 세로획은 표 선이 아니다. 이어 그리면 글자가 쪼개져 두 번 읽힌다(GDI 62건이 45건이 됐다)."""
    image = np.full((14, 60, 3), 255, np.uint8)
    image[:, 45] = 0        # 위아래 끝까지 닿은 'ㅣ'
    image[0:13, 8:30] = 0   # 옆 글자도 거의 같은 높이다(GDI 바짝 고른 글자 82건 모두 차이 없음)
    padded = add_margin(image, 8)
    assert (padded[:8] == 255).all() and (padded[-8:] == 255).all()


def test_add_margin_keeps_rule_when_nothing_else_is_there():
    image = np.full((20, 30, 3), 255, np.uint8)
    image[:, 12] = 0
    assert (add_margin(image, 4)[:, 4 + 12] == 0).all()


def test_add_margin_on_dark_screen():
    image = np.full((20, 60, 3), 30, np.uint8)
    image[6:14, 8:30] = 220
    image[:, 45] = 120
    assert (add_margin(image, 8)[:, 8 + 45] == 120).all()


MARGIN = 8


def selection(*ink_rows, height=40):
    """여백을 두른 영역 이미지. ink_rows는 영역 기준 (위, 아래) 글자 픽셀 행이다."""
    image = np.full((height + 2 * MARGIN, 120 + 2 * MARGIN, 3), 255, np.uint8)
    for top, bottom in ink_rows:
        image[MARGIN + top:MARGIN + bottom, MARGIN + 10:MARGIN + 100:6] = 0   # 막대로 채우면 배경 추정이 깨진다
    return image


def box(top, bottom):
    return (MARGIN + 10, MARGIN + top, MARGIN + 100, MARGIN + bottom)


def test_line_cut_by_bottom_of_selection_is_dropped():
    """드래그가 아랫줄을 걸치면 윗부분만 남은 조각을 모델이 없는 글자로 읽는다."""
    image = selection((4, 24), (34, 40))
    boxes = [box(4, 24), box(32, 41)]
    assert _cut_line_boxes(image, boxes, [("정상 문장", .99, 0), ("그 수 다 OI", .40, 0)], MARGIN) == {1}


def test_line_cut_by_top_of_selection_is_dropped():
    image = selection((0, 6), (16, 36))
    boxes = [box(-1, 8), box(16, 36)]
    assert _cut_line_boxes(image, boxes, [("L 1 7 1", .40, 0), ("정상 문장", .99, 0)], MARGIN) == {0}


def test_small_mark_that_ends_before_the_edge_stays():
    """끝 행까지 닿지 않은 낮은 상자는 잘린 글자가 아니라 작은 표시다."""
    image = selection((4, 24), (30, 36))
    assert _cut_line_boxes(image, [box(4, 24), box(30, 39)], [("정상 문장", .99, 0), ("- 3 -", .40, 0)], MARGIN) == set()


def test_confident_small_line_stays():
    """바짝 고른 영역의 작은 글자는 끝 행에 닿아도 모델이 확신하면 남는다."""
    image = selection((2, 22), (30, 40))
    assert _cut_line_boxes(image, [box(2, 22), box(30, 40)], [("큰 제목", .99, 0), ("작은 글자", .98, 0)], MARGIN) == set()


def test_short_box_needs_more_confidence_than_tall_one():
    image = selection((4, 24), (30, 40))
    bottom = [box(4, 24), box(30, 40)]    # 높이비 0.5
    assert _cut_line_boxes(image, bottom, [("정상", .99, 0), ("거기", .90, 0)], MARGIN) == {1}
    image = selection((4, 24), (26, 40))
    bottom = [box(4, 24), box(26, 40)]    # 높이비 0.7
    assert _cut_line_boxes(image, bottom, [("정상", .99, 0), ("거기", .90, 0)], MARGIN) == set()
    assert _cut_line_boxes(image, bottom, [("정상", .99, 0), ("거기", .70, 0)], MARGIN) == {1}


def test_nothing_to_compare_keeps_the_box():
    """비교할 다른 줄이 없으면 조각인지 알 수 없다."""
    image = selection((0, 40))
    assert _cut_line_boxes(image, [box(0, 40)], [("한 줄", .30, 0)], MARGIN) == set()


BIG = (100, 40, 400, 120)


@pytest.mark.parametrize("text", ["−", "(", "c", "√"])
def test_low_score_scrap_beside_big_text_is_dropped(text):
    """큰 글자의 획이나 틈이 따로 찾혀 없는 글자가 됐다('있다 ( ( 그러나')."""
    results = [("있도록", .99, 0), (text, .5, 0)]
    assert _fragment_boxes([BIG, (404, 60, 412, 80)], results) == {1}


@pytest.mark.parametrize("text", ["-", ".", "ㅇ", "•", "□"])
def test_small_real_mark_stays(text):
    assert _fragment_boxes([BIG, (404, 60, 412, 80)], [("있도록", .99, 0), (text, .5, 0)]) == set()


def test_confident_short_box_stays():
    assert _fragment_boxes([BIG, (404, 60, 430, 80)], [("있도록", .99, 0), ("15", .95, 0)]) == set()


def test_scrap_away_from_big_text_stays():
    assert _fragment_boxes([BIG, (500, 60, 512, 80)], [("있도록", .99, 0), ("c", .5, 0)]) == set()


def test_scrap_needs_a_confident_neighbor():
    assert _fragment_boxes([BIG, (404, 60, 412, 80)], [("있도록", .5, 0), ("c", .5, 0)]) == set()


def test_shrunk_boxes_cover_the_doubled_box():
    assert _shrunk_boxes([(11, 21, 41, 51)], 2) == [(5, 10, 21, 26)]
    assert _shrunk_boxes([(11, 21, 41, 51)], 1) == [(11, 21, 41, 51)]


def test_scaled_grid_moves_cells_with_the_table():
    grid = Grid(1, 2, (GridCell(0, 0, 1, 1, 10, 10, 20, 20), GridCell(0, 1, 1, 1, 20, 10, 30, 20)), 10, 10, 30, 20)
    moved = _scaled_grid(grid, .5, 4)
    assert (moved.left, moved.right, moved.cells[1].left) == (1, 11, 6)


class Recorder:
    """위치 모델 입력 크기를 적어 두는 대역."""

    def __init__(self, heights):
        self.shapes, self.heights = [], list(heights)

    def run(self, _, feed):
        tensor = feed["x"]
        self.shapes.append(tensor.shape)
        probability = np.zeros((1, 1) + tensor.shape[2:], np.float32)
        height = self.heights.pop(0)
        if height:
            probability[0, 0, 40:40 + height // 3, 40:200] = .9
        return [probability]


def fake_engine(det):
    instance = object.__new__(OcrEngine)
    instance._det = det
    instance._read = lambda image, boxes, cancelled: [("글자", .99) for _ in boxes]
    return instance


def test_small_text_is_detected_again_at_double_size():
    det = Recorder([12, 24])
    image = np.full((60, 400, 3), 255, np.uint8)
    boxes = fake_engine(det).recognize(image)
    assert len(det.shapes) == 2                          # 작은 글씨: 2배로 다시 찾는다
    assert det.shapes[1][2] > det.shapes[0][2] and det.shapes[1][3] > det.shapes[0][3]
    assert boxes and boxes[0].x < 400                    # 결과는 원본 좌표다


def test_large_text_is_detected_once():
    det = Recorder([60])
    fake_engine(det).recognize(np.full((60, 400, 3), 255, np.uint8))
    assert len(det.shapes) == 1


def test_detection_input_is_padded_not_stretched():
    det = Recorder([0])
    fake_engine(det).recognize(np.full((50, 100, 3), 255, np.uint8))
    _, _, height, width = det.shapes[0]
    assert height % 32 == 0 and width % 32 == 0
    assert height >= 50 + 2 * engine.DET_MARGIN and width >= 100 + 2 * engine.DET_MARGIN


def test_ctc_runs_report_best_confidence_of_each_character():
    charset = ["가", "나", " "]
    probs = np.zeros((5, 4), np.float32)
    probs[0, 1], probs[1, 1], probs[2, 0], probs[3, 2], probs[4, 2] = .4, .9, .9, .6, .3
    assert _ctc_runs(probs, charset) == [("가", .5, pytest.approx(.4), pytest.approx(.9)), ("나", 3.5, pytest.approx(.6), pytest.approx(.6))]


def test_cell_keeps_character_marks_across_joined_boxes():
    boxes = [TextBox(0, 0, 40, 16, "가나다", .99, 0, (1,)), TextBox(50, 0, 40, 16, "라마", .99, 0, (0,))]
    from screen_text.layout import _cell
    cell = _cell(boxes)
    assert cell.text == "가나다 라마" and cell.unsure_chars == (1, 4) and cell.flagged


def test_spans_mark_only_the_unsure_characters_and_merge_neighbors():
    block = TextLine([Cell("가나다라마", unsure_chars=(1, 2, 4))])
    text, spans = plain_with_spans([block])
    assert text == "가나다라마"
    assert spans == [(1, 2, "나다"), (4, 1, "마")]


def test_whole_cell_mark_wins_over_character_marks():
    _, spans = plain_with_spans([TextLine([Cell("가나", unsure=True, unsure_chars=(0,))])])
    assert spans == [(0, 2, "가나")]


def test_prefix_and_character_marks_do_not_overlap():
    _, spans = plain_with_spans([TextLine([Cell("ㅇ 가나", unsure_prefix=1, unsure_chars=(0, 3))])])
    assert spans == [(0, 1, "ㅇ"), (3, 1, "나")]


def test_edited_cell_with_changed_spacing_skips_character_marks():
    _, spans = plain_with_spans([TextLine([Cell("가  나", unsure_chars=(3,))])])
    assert spans == []


# ── 실제 모델 ──
def render(text, pixel_size, family="Malgun Gothic", pad=2):
    font = QFont(family)
    font.setPixelSize(pixel_size)
    probe = QImage(1200, 80, QImage.Format_RGB888)
    probe.fill(QColor("white"))
    painter = QPainter(probe)
    painter.setFont(font)
    width = painter.fontMetrics().horizontalAdvance(text) + 2 * pad
    height = painter.fontMetrics().height() + 2 * pad
    painter.end()
    image = QImage(width, height, QImage.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    painter.drawText(pad, pad + painter.fontMetrics().ascent(), text)
    painter.end()
    return rgb_from_buffer(image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits()))


@pytest.fixture(scope="module")
def ocr():
    return OcrEngine()


@pytest.mark.parametrize("pixel_size", [12, 13, 14, 16])
def test_real_model_reads_a_tightly_selected_line(qapp, ocr, pixel_size):
    """글자에 바짝 붙여 고른 한 줄: 위치 찾기가 가장자리 글자를 놓치면 앞뒤 글자가 사라진다."""
    text = "대기환경보전법 시행규칙 일부개정령안"
    found = "".join(box.text for box in ocr.recognize(render(text, pixel_size))).replace(" ", "")
    assert found == text.replace(" ", ""), found


@pytest.mark.parametrize("rule", [0, 120])
def test_real_model_does_not_read_table_rules_of_a_selected_row(qapp, ocr, rule):
    """표의 한 행만 고르면 숫자 바로 뒤의 세로선이 끝에서 끝까지 이어진다. 여백에서 끊기면 '19,669|'로 읽힌다."""
    texts = ["22,168", "19,669", "19,792", "19,923"]
    cells = [render(text, 16, pad=0) for text in texts]
    row = np.full((max(cell.shape[0] for cell in cells) + 4, 20 + sum(cell.shape[1] + 24 for cell in cells), 3), 255, np.uint8)
    x = 20
    for cell in cells:
        row[2:2 + cell.shape[0], x:x + cell.shape[1]] = cell
        row[:, x + cell.shape[1] + 3] = rule
        x += cell.shape[1] + 24
    assert [box.text for box in sorted(ocr.recognize(row), key=lambda box: box.x)] == texts


def test_real_model_ignores_next_line_cut_by_the_selection(qapp, ocr):
    """영역 끝이 아랫줄을 걸치면 잘린 글자가 'OI TI 1 L' 같은 없는 글자로 나왔다."""
    text = "대기환경보전법 시행규칙 일부개정령안"
    line, next_line = render(text, 13), render("환경부령 제1000호로 공포한다 부칙 시행일 관련 규정을 준용한다", 13)
    image = np.full((line.shape[0] + 10, max(line.shape[1], next_line.shape[1]), 3), 255, np.uint8)
    image[:line.shape[0], :line.shape[1]] = line
    image[line.shape[0] + 2:, :next_line.shape[1]] = next_line[2:10]
    found = "".join(box.text for box in sorted(ocr.recognize(image), key=lambda box: box.y)).replace(" ", "")
    assert found == text.replace(" ", ""), found


def test_real_model_returns_boxes_in_source_coordinates(qapp, ocr):
    image = render("좌표 확인용 문장입니다", 14, pad=20)
    boxes = ocr.recognize(image)
    assert boxes
    for box in boxes:
        assert 0 <= box.x < image.shape[1] and 0 <= box.y < image.shape[0]
        assert box.x + box.w <= image.shape[1] + 4 and box.y + box.h <= image.shape[0] + 4


class RuntimeException(Exception):
    """onnxruntime의 할당 실패와 이름이 같은 예외."""


@pytest.mark.parametrize("error", [MemoryError, RuntimeException])
def test_out_of_memory_on_second_pass_keeps_the_first_result(error):
    class Failing(Recorder):
        def run(self, name, feed):
            if self.shapes:
                raise error("bad allocation")
            return super().run(name, feed)

    boxes = fake_engine(Failing([12])).recognize(np.full((60, 400, 3), 255, np.uint8))
    assert boxes and boxes[0].x < 400


def test_other_errors_on_second_pass_are_not_hidden():
    class Failing(Recorder):
        def run(self, name, feed):
            if self.shapes:
                raise ValueError("모델 입력 오류")
            return super().run(name, feed)

    with pytest.raises(ValueError):
        fake_engine(Failing([12])).recognize(np.full((60, 400, 3), 255, np.uint8))
