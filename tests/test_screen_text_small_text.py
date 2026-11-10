"""작은 글씨와 바짝 고른 영역: 여백, 패딩, 2배 확대, 글자별 확인 표시."""
from pathlib import Path

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


@pytest.mark.parametrize("text", ["-", ".", "ㅇ", "•", "□", "❍"])   # ❍는 모양으로 읽은 그림자 동그라미다
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
    """위치 모델 입력 크기를 적어 두는 대역. 키운 입력에서는 글자도 키운 자리에 낸다(첫 호출의 폭 대비)."""

    def __init__(self, heights):
        self.shapes, self.heights = [], list(heights)

    def run(self, _, feed):
        tensor = feed["x"]
        self.shapes.append(tensor.shape)
        scale = tensor.shape[3] / self.shapes[0][3]
        probability = np.zeros((1, 1) + tensor.shape[2:], np.float32)
        height = self.heights.pop(0)
        if height:
            top, left, right = round(40 * scale), round(40 * scale), round(200 * scale)
            probability[0, 0, top:top + height // 3, left:right] = .9
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


class InkDetector:
    """글자 픽셀이 든 줄을 그대로 글자 확률로 내는 위치 모델 대역. 배율과 무관하다.

    drops[호출 순번]에 든 줄 번호(위에서부터)는 그 호출에서 놓친다. 정확히 2배로 키운 입력에서 모델이 엑셀 표의 한 열을
    통째로 놓친 일을 흉내 낸다. fail[호출 순번]의 예외는 그 호출에서 낸다.
    """

    def __init__(self, drops=None, fail=None):
        self.calls, self.drops, self.fail = 0, drops or {}, fail or {}

    def run(self, _, feed):
        tensor = feed["x"]
        self.calls += 1
        if self.calls in self.fail:
            raise self.fail[self.calls]("bad allocation")
        dark = tensor[0].mean(axis=0) < 0.0       # 정규화한 입력에서 중간 회색보다 어두운 화소(2배로 키우면 1px 획이 회색이 된다)
        probability = np.zeros((1, 1) + tensor.shape[2:], np.float32)
        rows = np.flatnonzero(dark.any(axis=1))
        bands = np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1) if rows.size else []
        for number, band in enumerate(bands):
            if number in self.drops.get(self.calls, ()):
                continue
            columns = np.flatnonzero(dark[band].any(axis=0))
            probability[0, 0, band[0]:band[-1] + 1, columns[0]:columns[-1] + 1] = .9
        return [probability]


def two_lines(short=False):
    """작은 글씨 두 줄. 획을 띄엄띄엄 그린다(막대로 채우면 배경 추정이 깨진다). short면 아랫줄이 짧다."""
    image = np.full((60, 400, 3), 255, np.uint8)
    image[14:22, 40:360:3] = 0
    image[36:44, 40:(100 if short else 360):3] = 0
    return image


def test_line_lost_at_exact_double_size_is_found_by_a_slightly_smaller_retry():
    """정확히 2배로 키운 입력에서 위치 모델이 줄을 통째로 놓치면 입력을 조금 줄여 한 번 더 찾는다(엑셀 표 142→7자)."""
    det = InkDetector(drops={2: {0}})
    boxes = fake_engine(det).recognize(two_lines())
    assert det.calls == 3
    assert sorted(round(box.y / 10) for box in boxes) == [1, 3]       # 두 줄이 모두 남는다


def test_double_size_result_that_keeps_the_lines_is_not_retried():
    det = InkDetector()
    assert len(fake_engine(det).recognize(two_lines())) == 2
    assert det.calls == 2


def test_small_loss_at_double_size_is_not_retried():
    """짧은 줄 하나를 놓친 정도로는 다시 찾지 않는다. 표 칸을 나눠 찾은 2배 상자는 1배 상자를 다 덮지 않는 게 정상이다."""
    det = InkDetector(drops={2: {1}})
    fake_engine(det).recognize(two_lines(short=True))
    assert det.calls == 2


def test_double_size_input_already_reduced_to_the_limit_is_not_retried():
    """2배 이미지가 커서 이미 긴 변 1920px로 줄여 찾았으면 0.97배로 다시 찾아도 같은 입력이다. 헛 찾기를 하지 않는다."""
    image = np.full((60, 1000, 3), 255, np.uint8)
    image[14:22, 40:960:3] = 0
    image[36:44, 40:960:3] = 0
    det = InkDetector(drops={2: {0}})
    fake_engine(det).recognize(image)
    assert det.calls == 2


def test_retry_that_does_not_recover_the_lines_keeps_the_double_size_result():
    det = InkDetector(drops={2: {0}, 3: {0}})
    boxes = fake_engine(det).recognize(two_lines())
    assert det.calls == 3
    assert [round(box.y / 10) for box in boxes] == [3]


def test_detection_input_is_padded_not_stretched():
    det = Recorder([0])
    fake_engine(det).recognize(np.full((50, 100, 3), 255, np.uint8))
    _, _, height, width = det.shapes[0]
    assert height % 32 == 0 and width % 32 == 0
    assert height >= 50 + 2 * engine.DET_MARGIN and width >= 100 + 2 * engine.DET_MARGIN


# ── 넓은 영역(2026-11-08): 같은 글자도 영역을 넓게 고르면 틀렸다(같은 쪽 7.7%가 4K 폭으로 고르면 36.6%) ──
class SeeingDetector(InkDetector):
    """모델 입력에서 글자 줄이 min_px 화소 이상일 때만 찾는 위치 모델 대역. 실제 모델처럼 많이 줄인 입력의 작은 글자를 놓친다."""

    def __init__(self, min_px):
        super().__init__()
        self.min_px, self.shapes = min_px, []

    def run(self, name, feed):
        self.shapes.append(feed["x"].shape)
        probability = super().run(name, feed)[0]
        rows = np.flatnonzero(probability[0, 0].any(axis=1))
        for band in np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1) if rows.size else []:
            if band.size < self.min_px:
                probability[0, 0, band] = 0
        return [probability]


def text_lines(height, width, tops, thickness=10):
    """흰 바탕에 tops마다 글자 줄 하나(획을 띄엄띄엄 그린다)."""
    image = np.full((height, width, 3), 255, np.uint8)
    for top in tops:
        image[top:top + thickness, 40:width - 40:3] = 0
    return image


def test_wide_selection_finds_small_text_without_shrinking_it():
    """문단을 3,840px 폭으로 고르면 위치 찾기 입력을 1,920px로 줄여 글자가 반 크기가 되고 하나도 못 찾았다."""
    det = SeeingDetector(min_px=8)
    boxes = fake_engine(det).recognize(text_lines(156, 3840, (20, 50, 80, 110)))
    assert len(boxes) == 4


def test_screen_wide_selection_is_found_in_strips_no_larger_than_a_double_size_a4_page():
    """4K 화면 한 장을 줄이지 않고 한 번에 넣으면 위치 모델 입력이 870만 화소다(A4 한 쪽 2배 입력의 세 배 넘는 메모리).
    가로 띠로 나눠 찾되 띠가 겹친 곳의 줄도 한 번씩만 나와야 한다."""
    tops = range(60, 2100, 70)
    det = SeeingDetector(min_px=8)
    boxes = fake_engine(det).recognize(text_lines(2160, 3840, tops))
    assert len(boxes) == len(tops)
    assert sorted(round((box.y + box.h / 2 - 5) / 70) for box in boxes) == [round(top / 70) for top in tops]
    assert max(height * width for _, _, height, width in det.shapes) <= 1920 * 1408


def stub_detector(results):
    """_detect 대역. 호출마다 (이미지 크기, limit)를 적고 results에서 차례로 상자를 낸다."""
    calls = []

    def detect(image, cancelled=lambda: False, limit=None):
        calls.append((image.shape[:2], limit))
        return list(results[min(len(calls), len(results)) - 1])

    return calls, detect


def test_heavily_shrunk_first_pass_is_found_again_at_full_size():
    """4K 폭으로 고른 문단 다섯 줄은 4분의 1로 줄인 첫 위치 찾기에서 높이 180px 상자 하나가 되어 큰 글씨로 보였다.
    그 상자를 통째로 읽어 아무것도 남지 않았다. 반 넘게 줄인 첫 결과는 큰 글씨로 보여도 원래 크기로 다시 찾는다."""
    five_lines = [(40, 30 + 30 * line, 700, 52 + 30 * line) for line in range(5)]
    calls, detect = stub_detector([[(40, 30, 700, 210)], five_lines])
    instance = fake_engine(None)
    instance._detect = detect
    boxes = instance.recognize(np.full((156, 3840, 3), 255, np.uint8))
    assert len(calls) == 2
    (height, width), limit = calls[1]
    assert limit >= width                            # 줄이지 않는다
    assert len(boxes) == 5


@pytest.mark.parametrize("height, doubled", [(17, True), (19, True), (20, False), (21, False)])
def test_full_size_height_decides_double_size_after_a_shrunk_first_pass(height, doubled):
    """줄여 찾은 첫 상자는 높이가 부풀어(17px 글자가 22px) 넓게 고른 작은 글씨를 2배로 읽지 않았다. 원래 크기로 다시 찾은
    상자로 한 번 더 판단한다. 20~21px는 2배로 읽어도 득실이 반반이고 ②③을 2·3으로 읽는 일이 잦아 그대로 둔다
    (평가 자료 15,889장, 2026-11-08)."""
    calls, detect = stub_detector([[(40, 40, 700, 70)], [(40, 40, 700, 40 + height)], [(80, 80, 1400, 80 + 2 * height)]])
    instance = fake_engine(None)
    instance._detect = detect
    instance.recognize(np.full((300, 1400, 3), 255, np.uint8))
    assert (len(calls) == 3) == doubled
    if doubled:
        assert calls[2][0] == (2 * calls[1][0][0], 2 * calls[1][0][1])


def test_wide_small_text_is_doubled_at_least_one_point_six_times():
    """2배로 다시 찾는 입력을 긴 변 1,920px로 줄이면 1,500px 폭 영역은 원래의 1.23배밖에 안 된다. A4 한 쪽 100%를 고를 때
    (1,920/1,185≈1.62배)보다 작게 줄이지 않는다."""
    det = Recorder([12, 24])
    fake_engine(det).recognize(np.full((200, 1500, 3), 255, np.uint8))
    assert len(det.shapes) == 2
    assert det.shapes[1][3] >= 1.6 * (1500 + 2 * engine.DET_MARGIN)


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


def paragraph(texts, family, pixel_size, pitch, width):
    """흰 바탕 왼쪽에 pitch 간격으로 쓴 문단. 화면 폭(width)만큼 고른 영역이다."""
    font = QFont(family)
    font.setPixelSize(pixel_size)
    image = QImage(width, 32 + pitch * len(texts), QImage.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    for number, text in enumerate(texts):
        painter.drawText(40, 20 + pitch * number + painter.fontMetrics().ascent(), text)
    painter.end()
    return rgb_from_buffer(image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits()))


@pytest.mark.parametrize("family, pitch", [("Malgun Gothic", 17), ("Gulim", 21)])
def test_real_model_reads_a_paragraph_selected_across_a_4k_screen(qapp, ocr, family, pitch):
    """문단 하나를 4K 화면 폭으로 고르면 한 글자도 못 읽었다(2026-11-08). 같은 문단을 700px 폭으로 고르면 다 읽는다."""
    texts = ["대기환경보전법 시행규칙 일부개정령안", "환경부령 제1000호로 공포한다", "부칙 시행일 관련 규정을 준용한다",
             "배출시설 설치 허가 기준을 정한다", "측정 결과는 매월 보고한다"]
    found = "".join(box.text for box in ocr.recognize(paragraph(texts, family, 13, pitch, 3840))).replace(" ", "")
    for text in texts:
        assert text.replace(" ", "") in found, found


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


@pytest.mark.parametrize("error", [MemoryError, RuntimeException])
def test_out_of_memory_on_retry_keeps_the_double_size_result(error):
    det = InkDetector(drops={2: {0}}, fail={3: error})
    boxes = fake_engine(det).recognize(two_lines())
    assert det.calls == 3
    assert [round(box.y / 10) for box in boxes] == [3]


def test_other_errors_on_retry_are_not_hidden():
    with pytest.raises(ValueError):
        fake_engine(InkDetector(drops={2: {0}}, fail={3: ValueError})).recognize(two_lines())


def load_fixture(name):
    image = QImage(str(Path(__file__).parent / "fixtures" / name)).convertToFormat(QImage.Format_RGB888)
    return rgb_from_buffer(image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits()))


def test_real_model_reads_excel_table_whose_column_vanishes_at_exact_double_size(qapp, ocr):
    """실제 엑셀 창(굴림, 100%)의 5열 표. 정확히 2배로 키운 입력에서 위치 모델이 제목 열을 거의 다 놓쳤고,
    상자가 없는 칸의 글자 획이 표 선으로 잡혀 12행 20열 격자가 됐다('문 정보통신 역량 향상과정'→'략 상과정', 142/381자)."""
    from screen_text.layout import build_blocks, to_plain
    found = ocr.recognize(load_fixture("screen_text_excel_table.png"))
    assert [(grid.rows, grid.columns) for grid in found.grids] == [(12, 5)]     # 끝 글자 'ㅣ'가 열이 되면 6열이다
    text = to_plain(build_blocks(found))
    for phrase in ("정보통신 역량 향상과정", "우수부서 인센티브", "디지털트", "평가 기준 및 방법", "슈퍼컴퓨터 프로그",
                   "직무-23 이해하기", "탄소중립포인트제 목표물량", "국제업무에", "총 작품 내외 선", "막으로 도출된", "영향을"):
        assert phrase in text, text
