"""화면 글자 따기: 고리 모양 글머리 기호는 'ㅇ'으로 내되 그 한 글자만 확인 필요로 표시한다.

고리는 ㅇ ◦ ○ o 를 모양으로 구별할 수 없다(사용자 결정 2026-11-06: 그대로 내지 않고 확인 필요로 표시).
줄 전체를 노랗게 하지 않도록 TextBox·Cell이 '앞 몇 글자가 확인 필요인가'(unsure_prefix)를 따로 가진다.
"""
import pytest
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from screen_text.engine import OcrEngine, rgb_from_buffer
from screen_text.layout import Cell, Table, TextBox, TextLine, build_blocks, plain_with_spans, to_html, to_tsv, unsure_count


def box(x, y, text, score=0.95, prefix=0, w=200, h=20):
    return TextBox(x, y, w, h, text, score, prefix)


# ── 레이아웃: 기호 한 글자만 확인 필요 ──
def test_text_box_defaults_to_no_unsure_prefix_and_cell_carries_it():
    assert TextBox(0, 0, 10, 10, "가", 0.9).unsure_prefix == 0
    (line,) = build_blocks([box(0, 0, "ㅇ 연간 배출량", prefix=1)])
    assert isinstance(line, TextLine)
    cell = line.cells[0]
    assert (cell.text, cell.unsure, cell.unsure_prefix, cell.flagged) == ("ㅇ 연간 배출량", False, 1, True)
    assert Cell("가").flagged is False and Cell("가", True).flagged is True


def test_only_the_symbol_is_marked_in_the_text_not_the_whole_line():
    text, spans = plain_with_spans(build_blocks([box(0, 0, "ㅇ 연간 배출량", prefix=1)]))
    assert text == "ㅇ 연간 배출량" and spans == [(0, 1, "ㅇ")]


def test_symbol_span_offset_counts_utf16_units_of_earlier_lines():
    blocks = build_blocks([box(0, 0, "😀 가나"), box(0, 40, "ㅇ 다라", prefix=1)])
    text, spans = plain_with_spans(blocks)
    assert text == "😀 가나\nㅇ 다라"
    assert spans == [(len("😀 가나".encode("utf-16-le")) // 2 + 1, 1, "ㅇ")]


def test_whole_cell_mark_wins_over_the_symbol_mark():
    text, spans = plain_with_spans(build_blocks([box(0, 0, "ㅇ 흐린 글자", score=0.5, prefix=1)]))
    assert spans == [(0, len("ㅇ 흐린 글자"), "ㅇ 흐린 글자")]


def test_flagged_cells_are_counted_and_copy_text_is_unchanged():
    blocks = build_blocks([box(0, 0, "ㅇ 가나", prefix=1), box(0, 40, "ㅇ 다라", prefix=1), box(0, 80, "마바")])
    assert unsure_count(blocks) == 2
    assert to_tsv(blocks) == "ㅇ 가나\nㅇ 다라\n마바"
    assert "ㅇ 가나" in to_html(blocks)


def test_prefix_flag_only_applies_to_the_first_box_of_a_cell():
    # 같은 줄의 두 상자: 첫 상자의 앞글자만 표시. 둘째 상자의 prefix는 칸의 앞글자가 아니다.
    (line,) = build_blocks([box(0, 0, "ㅇ 가나", prefix=1, w=100), box(130, 0, "ㅇ 다라", prefix=1, w=100)])
    assert [(c.text, c.unsure_prefix) for c in line.cells] == [("ㅇ 가나", 1), ("ㅇ 다라", 1)]


def test_table_cell_keeps_the_prefix_flag():
    rows = [[box(0, 0, "구분", w=60), box(200, 0, "값", w=60)],
            [box(0, 30, "ㅇ 가나", prefix=1, w=60), box(200, 30, "12", w=60)],
            [box(0, 60, "다라", w=60), box(200, 60, "34", w=60)]]
    blocks = build_blocks([b for row in rows for b in row])
    table = next(b for b in blocks if isinstance(b, Table))
    assert [c.flagged for row in table.rows for c in row] == [False, False, True, False, False, False]
    assert unsure_count(blocks) == 1


# ── 실제 모델: Qt로 그린 글머리 기호 줄 ──
def render_line(text, pixel_size, width=900):
    font = QFont("Malgun Gothic")
    font.setPixelSize(pixel_size)
    image = QImage(width, pixel_size * 2 + 24, QImage.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    painter.drawText(10, 10 + pixel_size, text)
    painter.end()
    return rgb_from_buffer(image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits()))


@pytest.fixture(scope="module")
def ocr():
    return OcrEngine()


def read(ocr, text, pixel_size):
    boxes = sorted(ocr.recognize(render_line(text, pixel_size)), key=lambda b: b.x)
    return " ".join(b.text for b in boxes), boxes


@pytest.mark.parametrize("pixel_size", [14, 16])
@pytest.mark.parametrize("symbol, flagged", [("■", 0), ("□", 0), ("ㅇ", 1)])
def test_reads_leading_symbols_and_flags_only_the_ring(qapp, ocr, symbol, flagged, pixel_size):
    found, boxes = read(ocr, f"{symbol} 연간 배출량 감소 추진", pixel_size)
    assert found.startswith(f"{symbol} 연간"), found
    assert sum(b.unsure_prefix for b in boxes) == flagged


@pytest.mark.parametrize("pixel_size", [14, 16, 20])
def test_large_ring_is_not_read_as_a_square_and_stays_flagged(qapp, ocr, pixel_size):
    found, boxes = read(ocr, "○ 연간 배출량 감소 추진", pixel_size)
    assert found[:1] in "○ㅇ" and found[1:3] == " 연", found
    assert sum(b.unsure_prefix for b in boxes) == 1


@pytest.mark.parametrize("pixel_size", [13, 14, 16])
def test_no_symbol_is_added_to_ordinary_lines(qapp, ocr, pixel_size):
    for text in ("연간 배출량 감소 추진", "2026년도 추진계획", "OECD 회원국 비교", "(단위 : 억원)"):
        found, boxes = read(ocr, text, pixel_size)
        assert found[:1] not in "■□◇ㅇ", (text, found)
        assert not any(b.unsure_prefix for b in boxes)


@pytest.mark.parametrize("pixel_size", [13, 14, 16, 20])
def test_line_starting_with_a_dash_keeps_it(qapp, ocr, pixel_size):
    found, boxes = read(ocr, "- 기초연구 비전 수립 및 추진", pixel_size)
    assert found.startswith("-"), found
    assert not any(b.unsure_prefix for b in boxes)


@pytest.mark.parametrize("pixel_size", [14, 16, 20])
def test_form_checkboxes_keep_their_order_in_a_line(qapp, ocr, pixel_size):
    found, boxes = read(ocr, "현주소   □ 특별시   ■ 광역시   □ 도   □ 시   ■ 군   □ 구", pixel_size)
    assert "".join(ch for ch in found if ch in "□■") == "□■□□■□", found
    assert not any(b.unsure_prefix for b in boxes)


@pytest.mark.parametrize("pixel_size", [14, 16, 20])
def test_agree_checkboxes_are_both_read(qapp, ocr, pixel_size):
    found, _ = read(ocr, "수집·이용에 동의   □ 동의   □ 동의하지 않음", pixel_size)
    assert found.count("□") == 2, found


@pytest.mark.parametrize("pixel_size", [14, 16, 20])
def test_decrease_mark_before_a_number_is_kept(qapp, ocr, pixel_size):
    found, _ = read(ocr, "전년대비 △32% 감소", pixel_size)
    assert "△32" in found.replace(" ", ""), found                    # 모델이 사전의 ∆로 읽어도 △로 통일한다


@pytest.mark.parametrize("pixel_size", [14, 16, 20])
def test_triangle_list_marks_are_read(qapp, ocr, pixel_size):
    found, _ = read(ocr, "추진 예시 △ 선박 밀폐공간 통신 △ 독거노인 돌봄", pixel_size)
    assert found.count("△") == 2, found
    found, _ = read(ocr, "지원 대상 ▲ 투자 확대 ▲ 맞춤형 제도", pixel_size)
    assert found.count("▲") == 2, found


@pytest.mark.parametrize("pixel_size", [13, 14, 16, 20])
def test_no_triangle_is_added_to_ordinary_lines(qapp, ocr, pixel_size):
    for text in ("스마트 시스템 서비스 구축", "소스 코드 스캔 결과 시스템", "AI 글로벌 3대 강국 도약", "기술 자산 수소 사업"):
        found, _ = read(ocr, text, pixel_size)
        assert not set(found) & set("△▲"), (text, found)


@pytest.mark.parametrize("pixel_size", [13, 14, 16, 20])
def test_no_checkbox_is_added_to_ordinary_lines(qapp, ocr, pixel_size):
    for text in ("기후변화 대응 연구 추진계획", "다음 각 호의 기준에 따라 대기 환경을 개선한다", "국가 기술 표준 및 인증 절차", "(단위 : 억원) 2026년 예산"):
        found, _ = read(ocr, text, pixel_size)
        assert not set(found) & set("□■"), (text, found)


@pytest.mark.parametrize("pixel_size", [13, 14, 16])
def test_no_dash_is_added_to_ordinary_lines(qapp, ocr, pixel_size):
    for text in ("연간 배출량 감소 추진", "2026-11-06 회의", "연구-개발 연계", "(단위 : 억원)"):
        found, _ = read(ocr, text, pixel_size)
        assert not found.startswith("-"), (text, found)
