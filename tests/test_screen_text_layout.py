"""화면 글자 따기 줄·표 재구성: 순수 Python 규칙만 검사한다."""
from screen_text.layout import (
    Cell, Table, TextBox, TextLine, build_blocks, group_lines, has_table, rows_of,
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
