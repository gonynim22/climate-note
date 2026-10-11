"""화면 글자 따기 줄·표 재구성: 순수 Python 규칙만 검사한다."""
from collections import Counter
from dataclasses import replace

import pytest

from screen_text.layout import (
    Cell, Table, TextBox, TextLine, build_blocks, group_lines, has_table, plain_with_spans, rows_of,
    to_html, to_plain, to_tsv, unsure_count,
)


def box(x, y, text, w=None, h=16, score=0.99):
    return TextBox(x, y, w if w is not None else 10 * len(text), h, text, score)


# 테두리 없는 표: 머리글 + 3행, '충북' 위반 칸은 '51'을 '5l'로 잘못 읽은 상태
TABLE_BOXES = [
    box(10, 10, "구분", w=30), box(120, 10, "점검 사업장", w=70), box(260, 10, "위반", w=30),
    box(12, 34, "대전", w=30), box(140, 34, "42", w=16), box(265, 34, "3", w=8),
    box(12, 58, "충북", w=30), box(140, 58, "5l", w=16, score=0.95), box(265, 58, "4", w=8),
    box(12, 82, "계", w=14), box(136, 82, "176", w=24), box(262, 82, "15", w=16),
]


def texts(rows):
    return [[cell.text for cell in row] for row in rows]


def test_group_lines_orders_rows_top_to_bottom_and_left_to_right():
    lines = group_lines(list(reversed(TABLE_BOXES)))
    assert [[b.text for b in line] for line in lines] == [
        ["구분", "점검 사업장", "위반"], ["대전", "42", "3"], ["충북", "5l", "4"], ["계", "176", "15"],
    ]


def test_group_lines_keeps_slightly_offset_boxes_on_one_line():
    assert len(group_lines([box(0, 10, "가"), box(50, 14, "나")])) == 1
    assert len(group_lines([box(0, 10, "가"), box(50, 30, "나")])) == 2


def test_borderless_aligned_rows_become_table():
    blocks = build_blocks(TABLE_BOXES)
    assert len(blocks) == 1 and isinstance(blocks[0], Table)
    assert texts(blocks[0].rows) == [
        ["구분", "점검 사업장", "위반"], ["대전", "42", "3"], ["충북", "5l", "4"], ["계", "176", "15"],
    ]


def test_numeric_column_lookalike_letter_is_marked_unsure_not_corrected():
    table = build_blocks(TABLE_BOXES)[0]
    assert table.rows[2][1].text == "5l"
    assert table.rows[2][1].unsure
    assert not table.rows[2][0].unsure
    assert unsure_count([table]) == 1


def test_low_score_box_is_unsure():
    blocks = build_blocks([box(0, 0, "점검", score=0.5)])
    assert isinstance(blocks[0], TextLine) and blocks[0].cells[0].unsure


def test_paragraph_line_spanning_columns_ends_table():
    boxes = TABLE_BOXES + [box(10, 106, "붙임", w=30), box(60, 106, "점검 결과 세부 내역 1부. 끝.", w=260)]
    blocks = build_blocks(boxes)
    assert isinstance(blocks[0], Table) and len(blocks[0].rows) == 4
    assert isinstance(blocks[1], TextLine)
    assert [c.text for c in blocks[1].cells] == ["붙임", "점검 결과 세부 내역 1부. 끝."]


def test_single_row_is_not_a_table():
    assert not has_table(build_blocks([box(0, 0, "구분", w=30), box(100, 0, "위반", w=30)]))


def test_missing_cell_stays_empty_in_its_column():
    boxes = TABLE_BOXES[:3] + [box(12, 34, "대전", w=30), box(265, 34, "3", w=8)]
    table = build_blocks(boxes)[0]
    assert texts(table.rows)[1] == ["대전", "", "3"]


def test_plain_tsv_and_html_outputs():
    shifted = [TextBox(b.x, b.y + 40, b.w, b.h, b.text, b.score) for b in TABLE_BOXES]
    blocks = build_blocks([box(0, 0, "제목", w=30)] + shifted)
    assert to_plain(blocks).splitlines()[:2] == ["제목", "구분 점검 사업장 위반"]
    assert to_tsv(blocks).splitlines()[:2] == ["제목", "구분\t점검 사업장\t위반"]
    html_text = to_html(blocks)
    assert "<p>제목</p>" in html_text
    assert html_text.count("<tr>") == 4
    assert "<td>점검 사업장</td>" in html_text


def test_html_escapes_markup_and_tsv_flattens_tabs_and_newlines():
    blocks = [Table([[Cell("a<b>&c"), Cell("x\ty\nz")], [Cell("1"), Cell("2")]])]
    assert "a&lt;b&gt;&amp;c" in to_html(blocks)
    assert to_tsv(blocks).splitlines()[0] == "a<b>&c\tx y z"


def test_rows_of_and_empty_input():
    line = TextLine([Cell("가")])
    assert rows_of(line) == [[Cell("가")]]
    assert build_blocks([]) == []
    assert to_plain([]) == "" and to_tsv([]) == "" and unsure_count([]) == 0


def test_line_merging_two_columns_while_adding_one_ends_table():
    boxes = TABLE_BOXES + [box(10, 106, "붙임 세부 내역", w=190), box(400, 106, "2026.10.8", w=60)]
    blocks = build_blocks(boxes)
    assert isinstance(blocks[0], Table) and len(blocks[0].rows) == 4 and len(blocks[0].rows[0]) == 3
    assert texts(blocks[0].rows)[0] == ["구분", "점검 사업장", "위반"]
    assert isinstance(blocks[1], TextLine)


def test_sentence_line_above_table_is_not_absorbed():
    boxes = [box(10, -14, "붙임", w=30), box(60, -14, "점검 결과 세부 내역 1부. 끝.", w=260)] + TABLE_BOXES
    blocks = build_blocks(boxes)
    assert isinstance(blocks[0], TextLine)
    assert isinstance(blocks[1], Table) and texts(blocks[1].rows)[0] == ["구분", "점검 사업장", "위반"]


def test_small_table_lookalike_is_still_marked():
    small_table = [
        box(10, 10, "구분", w=30), box(120, 10, "위반", w=30),
        box(12, 34, "대전", w=30), box(140, 34, "42", w=16),
        box(12, 58, "충북", w=30), box(140, 58, "5l", w=16),
    ]
    table = build_blocks(small_table)[0]
    assert table.rows[2][1].text == "5l"
    assert table.rows[2][1].unsure


def test_text_column_with_letters_and_digits_is_not_marked():
    text_column = [
        box(10, 10, "비고", w=30), box(120, 10, "숫자", w=30),
        box(12, 34, "S1 구역", w=30), box(140, 34, "42", w=16),
        box(12, 58, "B2 구역", w=30), box(140, 58, "100", w=24),
        box(12, 82, "주차장", w=30), box(140, 82, "3", w=8),
    ]
    table = build_blocks(text_column)[0]
    assert not table.rows[1][0].unsure
    assert not table.rows[2][0].unsure
    assert not table.rows[3][0].unsure


def utf16_slice(text, start, length):
    """QTextCursor 위치와 같은 UTF-16 코드 단위로 잘라 되돌린다."""
    return text.encode("utf-16-le")[start * 2:(start + length) * 2].decode("utf-16-le")


def test_plain_with_spans_text_equals_to_plain_and_spans_point_at_unsure_cells():
    shifted = [TextBox(b.x, b.y + 40, b.w, b.h, b.text, b.score) for b in TABLE_BOXES]
    blocks = build_blocks([box(0, 0, "제목", w=30)] + shifted)
    text, spans = plain_with_spans(blocks)
    assert text == to_plain(blocks)
    assert [token for _, _, token in spans] == ["5l"]
    start, length, token = spans[0]
    assert utf16_slice(text, start, length) == token
    assert text[start:start + length] == token  # BMP 글자만 있으면 파이썬 위치와 같다


def test_span_marks_the_unsure_cell_not_an_earlier_substring_occurrence():
    blocks = build_blocks([box(0, 0, "합계", w=30), box(60, 0, "42", w=20), box(0, 30, "4", w=10, score=0.5)])
    text, spans = plain_with_spans(blocks)
    assert text == "합계 42\n4"
    assert spans == [(len("합계 42\n"), 1, "4")]


def test_spans_count_utf16_units_for_characters_outside_the_bmp():
    blocks = [TextLine([Cell("😀"), Cell("5l", True)]), TextLine([Cell("가", True), Cell("😀😀"), Cell("나", True)])]
    text, spans = plain_with_spans(blocks)
    assert text == "😀 5l\n가 😀😀 나"
    assert spans == [(3, 2, "5l"), (6, 1, "가"), (13, 1, "나")]
    assert [utf16_slice(text, *span[:2]) for span in spans] == ["5l", "가", "나"]


def test_spans_use_cleaned_tokens_and_skip_empty_and_sure_cells():
    blocks = [Table([[Cell("a\tb\nc", True), Cell("", True), Cell("x"), Cell("  ", True)]])]
    text, spans = plain_with_spans(blocks)
    assert text == to_plain(blocks)
    assert spans == [(0, 5, "a b c")]
    assert plain_with_spans([]) == ("", [])


def transform_boxes(boxes, scale, reverse):
    result = [replace(b, x=round(b.x * scale) - 83, y=round(b.y * scale) + 57,
                      w=round(b.w * scale), h=round(b.h * scale)) for b in boxes]
    return result[::-1] if reverse else result


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
@pytest.mark.parametrize("reverse", [False, True])
def test_merged_row_label_does_not_mix_values_from_two_rows(scale, reverse):
    boxes = [box(0, 8, "묶음", w=40, h=24),
             box(100, 0, "12", w=24, h=20), box(200, 0, "34", w=24, h=20),
             box(100, 18, "56", w=24, h=20), box(200, 18, "78", w=24, h=20)]
    actual = transform_boxes(boxes, scale, reverse)
    blocks = build_blocks(actual)
    assert len(blocks) == 1 and isinstance(blocks[0], Table)
    assert texts(blocks[0].rows) == [["묶음", "12", "34"], ["", "56", "78"]]
    assert Counter(b for line in group_lines(actual) for b in line) == Counter(actual)


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_multiline_cell_keeps_top_to_bottom_order_and_warning(scale):
    boxes = []
    for y, name, number in [(0, "첫 항목", "20"), (60, "둘째 항목", "30")]:
        boxes += [box(28, y, name, w=86, h=28),
                  box(27, y + 25, "(단위)", w=86, h=27, score=0.6),
                  box(150, y + 15, number, w=30, h=24),
                  box(250, y + 15, "기준", w=40, h=24)]
    blocks = build_blocks(transform_boxes(boxes, scale, True))
    assert len(blocks) == 1 and isinstance(blocks[0], Table)
    assert texts(blocks[0].rows) == [["첫 항목 (단위)", "20", "기준"], ["둘째 항목 (단위)", "30", "기준"]]
    text, spans = plain_with_spans(blocks)
    assert [utf16_slice(text, start, length) for start, length, _ in spans] == ["첫 항목 (단위)", "둘째 항목 (단위)"]
    assert to_tsv(blocks).splitlines()[0] == "첫 항목 (단위)\t20\t기준"


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_small_overlap_with_next_column_does_not_end_or_merge_table(scale):
    boxes = [box(10, 0, "가", w=40), box(60, 0, "나", w=50), box(140, 0, "다", w=20),
             box(10, 30, "라", w=51), box(61, 30, "마", w=49), box(140, 30, "바", w=20),
             box(10, 60, "사", w=40), box(60, 60, "아", w=50), box(140, 60, "자", w=20)]
    blocks = build_blocks(transform_boxes(boxes, scale, True))
    assert len(blocks) == 1 and isinstance(blocks[0], Table)
    assert texts(blocks[0].rows) == [["가", "나", "다"], ["라", "마", "바"], ["사", "아", "자"]]


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_centered_spanning_headers_use_first_body_column_without_extra_columns(scale):
    boxes = [box(55, 0, "상반기", w=40), box(255, 0, "하반기", w=40)]
    for y, values in [(26, ("1월", "2월", "7월", "8월")), (52, ("10", "20", "30", "40"))]:
        boxes.extend(box(10 + c * 100, y, value, w=30) for c, value in enumerate(values))
    blocks = build_blocks(transform_boxes(boxes, scale, True))
    assert len(blocks) == 1 and isinstance(blocks[0], Table)
    assert texts(blocks[0].rows) == [["상반기", "", "하반기", ""], ["1월", "2월", "7월", "8월"], ["10", "20", "30", "40"]]


def test_distant_heading_is_not_attached_to_table():
    boxes = [box(55, -100, "상반기", w=40), box(255, -100, "하반기", w=40)]
    boxes += [box(10 + c * 100, y, str(c), w=30) for y in (0, 26) for c in range(4)]
    blocks = build_blocks(boxes)
    assert isinstance(blocks[0], TextLine)
    assert isinstance(blocks[1], Table) and len(blocks[1].rows) == 2


def test_only_one_repeating_column_does_not_split_multiline_cell():
    boxes = [box(0, 0, "위", w=30, h=28), box(80, 14, "수치", w=30, h=24),
             box(0, 25, "아래", w=30, h=26)]
    assert len(group_lines(boxes)) == 1


def test_sparse_first_row_without_denser_body_is_not_reinterpreted_as_header():
    boxes = [box(10, 0, "왼쪽", w=30), box(310, 0, "오른쪽", w=30),
             box(110, 26, "중간1", w=30), box(210, 26, "중간2", w=30)]
    assert texts(build_blocks(boxes)[0].rows) == [["왼쪽", "", "", "오른쪽"], ["", "중간1", "중간2", ""]]


def test_overlapping_word_fragments_inside_one_column_stay_in_same_cell():
    boxes = [box(0, 0, "항목", w=35), box(80, 0, "내용", w=75), box(190, 0, "값", w=35),
             box(0, 30, "테마", w=35), box(81, 30, "화면", w=44),
             box(114, 30, "색상", w=41), box(190, 30, "밝게", w=35)]
    blocks = build_blocks(boxes)
    assert len(blocks) == 1 and isinstance(blocks[0], Table)
    assert texts(blocks[0].rows) == [["항목", "내용", "값"], ["테마", "화면 색상", "밝게"]]


def test_touching_paragraph_fragments_do_not_create_a_new_table():
    boxes = [box(10, y, "왼쪽 단어", w=70) for y in (0, 30)]
    boxes += [box(75, y, "오른쪽 단어", w=80) for y in (0, 30)]
    assert not has_table(build_blocks(boxes))
    assert to_plain(build_blocks(boxes)) == "왼쪽 단어 오른쪽 단어\n왼쪽 단어 오른쪽 단어"
