"""표 선 격자: 선 찾기, 병합, 잘린 표, 글자 획 거르기, 격자에 글자 넣기."""
import numpy as np

from screen_text.layout import Grid, GridCell, RecognizedBoxes, Table, TextBox, TextLine, build_blocks, to_html, to_plain, to_tsv
from screen_text.table_lines import find_grids, fit_boxes

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


def canvas(width, height, color=WHITE):
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[:] = color
    return image


def hline(image, y, x0, x1, color=BLACK):
    image[y, x0:x1 + 1] = color


def vline(image, x, y0, y1, color=BLACK):
    image[y0:y1 + 1, x] = color


def grid_image(xs, ys, color=BLACK, margin=20):
    image = canvas(xs[-1] + margin, ys[-1] + margin)
    for y in ys:
        hline(image, y, xs[0], xs[-1], color)
    for x in xs:
        vline(image, x, ys[0], ys[-1], color)
    return image


def boxes_in(xs, ys):
    """칸마다 글자 상자 하나를 둔다."""
    return [(x0 + 6, y0 + 6, x1 - 6, y1 - 6) for x0, x1 in zip(xs, xs[1:]) for y0, y1 in zip(ys, ys[1:])]


def test_finds_rows_and_columns_of_plain_grid():
    xs, ys = [20, 120, 220, 320], [20, 50, 80, 110]
    grids = find_grids(grid_image(xs, ys), boxes_in(xs, ys))
    assert [(g.rows, g.columns) for g in grids] == [(3, 3)]
    assert all(cell.row_span == 1 and cell.column_span == 1 for cell in grids[0].cells)
    assert len(grids[0].cells) == 9


def test_light_gray_excel_lines_are_found():
    xs, ys = [20, 120, 220], [20, 50, 80]
    grids = find_grids(grid_image(xs, ys, color=(212, 212, 212)), boxes_in(xs, ys))
    assert [(g.rows, g.columns) for g in grids] == [(2, 2)]


def test_light_lines_on_dark_screen_are_found():
    xs, ys = [20, 120, 220], [20, 50, 80]
    image = canvas(260, 110, (30, 30, 30))
    for y in ys:
        hline(image, y, xs[0], xs[-1], (120, 120, 120))
    for x in xs:
        vline(image, x, ys[0], ys[-1], (120, 120, 120))
    assert [(g.rows, g.columns) for g in find_grids(image, boxes_in(xs, ys))] == [(2, 2)]


def test_merged_header_and_side_cells_become_spans():
    image = canvas(360, 150)
    for y in (20, 110):
        hline(image, y, 20, 320)
    hline(image, 50, 120, 320)     # 머리글 아래: 첫 열은 세로 병합이라 선이 없다
    hline(image, 80, 20, 320)
    for x in (20, 120, 320):
        vline(image, x, 20, 110)
    vline(image, 220, 50, 110)     # 위 칸은 가로 병합이라 선이 없다
    boxes = [(30, 30, 100, 70), (130, 26, 300, 44), (130, 56, 200, 74), (230, 56, 300, 74)]
    grids = find_grids(image, boxes)
    assert len(grids) == 1
    grid = grids[0]
    assert (grid.rows, grid.columns) == (3, 3)
    spans = {(c.row, c.column): (c.row_span, c.column_span) for c in grid.cells}
    assert spans[0, 0] == (2, 1)
    assert spans[0, 1] == (1, 2)
    assert spans[2, 0] == (1, 1)


def test_table_without_outer_vertical_lines():
    image = canvas(360, 130)
    for y in (20, 50, 80, 110):
        hline(image, y, 20, 320)
    for x in (120, 220):
        vline(image, x, 20, 110)
    grids = find_grids(image, boxes_in([20, 120, 220, 320], [20, 50, 80, 110]))
    assert [(g.rows, g.columns) for g in grids] == [(3, 3)]
    assert grids[0].left == 20 and grids[0].right == 320


def test_table_cut_by_selection_keeps_columns():
    """영역을 표 중간에서 고르면 세로선이 위아래 끝에서 끝나고 윗선이 없다."""
    image = canvas(360, 90)
    for y in (30, 60):
        hline(image, y, 20, 320)
    for x in (20, 120, 220, 320):
        vline(image, x, 0, 89)
    grids = find_grids(image, [(30, 36, 100, 54), (130, 36, 200, 54), (230, 36, 300, 54), (30, 66, 100, 84)])
    assert [(g.columns) for g in grids] == [3]
    assert grids[0].rows >= 2


def test_rule_continued_into_margin_does_not_add_a_row():
    """여백까지 이어 그린 세로선(add_margin)이 격자를 고른 영역 밖으로 넓히면 빈 행이 생긴다."""
    margin = 32
    image = canvas(360 + 2 * margin, 60 + 2 * margin)
    for y in (0, 30, 59):
        hline(image, margin + y, margin + 20, margin + 320)
    for x in (20, 120, 220, 320):
        vline(image, margin + x, 0, image.shape[0] - 1)
    grids = find_grids(image, [(margin + x, margin + y, margin + x + 60, margin + y + 16) for x in (30, 130, 230) for y in (6, 36)], margin)
    assert [(g.rows, g.columns) for g in grids] == [(2, 3)]
    assert grids[0].top >= margin and grids[0].bottom <= margin + 59


def header_without_rules():
    """세로선이 머리글 줄에서 끊긴 표: 머리글 아래 가로선부터만 세로선이 있다(p011)."""
    image = canvas(460, 130)
    for y in (20, 50, 110):
        hline(image, y, 20, 420)
    for x in (20, 120, 220, 320, 420):
        vline(image, x, 50, 110)
    vline(image, 20, 20, 110)
    vline(image, 120, 20, 110)
    vline(image, 420, 20, 110)
    return image


def test_header_words_spread_over_columns_are_not_a_merged_cell():
    boxes = [(30, 26, 90, 44), (150, 26, 190, 44), (250, 26, 290, 44), (350, 26, 390, 44)]
    boxes += [(x + 10, 60, x + 70, 76) for x in (20, 120, 220, 320)]
    grids = find_grids(header_without_rules(), boxes)
    assert [(g.rows, g.columns) for g in grids] == [(2, 4)]
    assert all(cell.column_span == 1 for cell in grids[0].cells)
    assert [cell.left for cell in grids[0].cells if cell.row == 0] == [cell.left for cell in grids[0].cells if cell.row == 1]


def test_one_title_over_columns_stays_merged():
    boxes = [(30, 26, 90, 44), (180, 26, 360, 44)] + [(x + 10, 60, x + 70, 76) for x in (20, 120, 220, 320)]
    grid = find_grids(header_without_rules(), boxes)[0]
    assert [(cell.column, cell.column_span) for cell in grid.cells if cell.row == 0] == [(0, 1), (1, 3)]


def test_two_words_over_two_columns_stay_merged():
    """두 칸짜리 병합은 낱말 둘이 칸마다 놓여도 구별할 수 없다(합성 표 'AI 공문서')."""
    image = canvas(360, 130)
    for y in (20, 50, 110):
        hline(image, y, 20, 320)
    for x in (20, 120, 320):
        vline(image, x, 20, 110)
    vline(image, 220, 50, 110)
    boxes = [(30, 26, 90, 44), (150, 26, 190, 44), (250, 26, 290, 44)] + [(x + 10, 60, x + 70, 76) for x in (20, 120, 220)]
    grid = find_grids(image, boxes)[0]
    assert [(cell.column, cell.column_span) for cell in grid.cells if cell.row == 0] == [(0, 1), (1, 2)]


def test_header_shading_is_not_a_line():
    """바탕색 칸의 가장자리는 능선이 아니므로 가짜 행을 만들지 않는다."""
    xs, ys = [20, 120, 220], [40, 70, 100]
    image = grid_image(xs, ys)
    image[41:70, 21:220] = (217, 217, 217)
    for x in xs:
        vline(image, x, ys[0], ys[-1])
    assert [(g.rows, g.columns) for g in find_grids(image, boxes_in(xs, ys))] == [(2, 2)]


def test_underline_and_box_around_paragraph_are_not_tables():
    image = canvas(400, 200)
    hline(image, 40, 20, 300)      # 밑줄 하나
    assert find_grids(image, [(20, 20, 300, 38)]) == []
    for y in (80, 150):
        hline(image, y, 20, 380)
    for x in (20, 380):
        vline(image, x, 80, 150)   # 문단을 두른 상자 하나는 표가 아니다
    assert find_grids(image, [(30, 90, 370, 110), (30, 115, 370, 135)]) == []


def test_glyph_strokes_inside_text_box_are_not_grid_lines():
    """큰 글자의 획이 표 선처럼 이어져도 글자 상자 안쪽이면 선이 아니다."""
    image = canvas(300, 120)
    for y in (30, 50, 70):
        hline(image, y, 40, 90)
    for x in (40, 65, 90):
        vline(image, x, 30, 70)
    assert find_grids(image, [(30, 22, 100, 78)]) == []


def test_fit_boxes_splits_box_across_rule_and_drops_empty_part():
    xs, ys = [20, 120, 220], [20, 60, 100]
    image = grid_image(xs, ys)
    image[30:50, 40:100] = BLACK    # 왼쪽 칸 글자
    image[30:50, 140:200] = BLACK   # 오른쪽 칸 글자
    grids = find_grids(image, boxes_in(xs, ys))
    fitted = fit_boxes(image, [(30, 26, 210, 54)], grids)
    assert len(fitted) == 2
    assert fitted[0][2] <= 120 < fitted[1][0]
    only_left = canvas(*image.shape[1::-1])
    only_left[:] = image
    only_left[30:50, 140:200] = WHITE
    assert len(fit_boxes(only_left, [(30, 26, 210, 54)], grids)) == 1


def test_fit_boxes_leaves_boxes_outside_tables():
    xs, ys = [20, 120, 220], [20, 60, 100]
    image = grid_image(xs, ys, margin=120)
    grids = find_grids(image, boxes_in(xs, ys))
    assert fit_boxes(image, [(30, 130, 210, 150)], grids) == [(30, 130, 210, 150)]


def sample_grid():
    cells = (GridCell(0, 0, 2, 1, 0, 0, 100, 60), GridCell(0, 1, 1, 2, 100, 0, 300, 30),
             GridCell(1, 1, 1, 1, 100, 30, 200, 60), GridCell(1, 2, 1, 1, 200, 30, 300, 60))
    return Grid(2, 3, cells, 0, 0, 300, 60)


def test_grid_table_places_text_with_spans():
    boxes = RecognizedBoxes([TextBox(10, 20, 60, 16, "구분", .99), TextBox(120, 5, 100, 16, "실적", .99),
                             TextBox(110, 35, 60, 16, "2024", .99), TextBox(210, 35, 60, 16, "2025", .99)], [sample_grid()])
    blocks = build_blocks(boxes)
    assert len(blocks) == 1 and isinstance(blocks[0], Table)
    rows = blocks[0].rows
    assert [cell.text for cell in rows[0]] == ["구분", "실적", ""]
    assert rows[0][2].covered and rows[1][0].covered
    assert (rows[0][0].row_span, rows[0][1].column_span) == (2, 2)


def test_grid_table_joins_wrapped_lines_in_one_cell():
    grid = Grid(2, 2, (GridCell(0, 0, 1, 1, 0, 0, 100, 60), GridCell(0, 1, 1, 1, 100, 0, 200, 60),
                       GridCell(1, 0, 1, 1, 0, 60, 100, 90), GridCell(1, 1, 1, 1, 100, 60, 200, 90)), 0, 0, 200, 90)
    boxes = RecognizedBoxes([TextBox(10, 5, 60, 16, "여러", .99), TextBox(10, 30, 60, 16, "줄 칸", .99),
                             TextBox(110, 20, 60, 16, "오른쪽", .99), TextBox(10, 65, 60, 16, "아래", .99)], [grid])
    table = build_blocks(boxes)[0]
    assert [[cell.text for cell in row] for row in table.rows] == [["여러 줄 칸", "오른쪽"], ["아래", ""]]


def test_html_uses_rowspan_and_colspan_and_tsv_keeps_columns():
    boxes = RecognizedBoxes([TextBox(10, 20, 60, 16, "구분", .99), TextBox(120, 5, 100, 16, "실적", .99),
                             TextBox(110, 35, 60, 16, "2024", .99), TextBox(210, 35, 60, 16, "2025", .99)], [sample_grid()])
    blocks = build_blocks(boxes)
    html = to_html(blocks)
    assert '<td rowspan="2">구분</td>' in html and '<td colspan="2">실적</td>' in html
    assert html.count("<td") == 4
    assert to_tsv(blocks) == "구분\t실적\t\n\t2024\t2025"
    assert to_plain(blocks) == "구분 실적\n2024 2025"


def test_text_around_grid_keeps_reading_order():
    boxes = RecognizedBoxes([TextBox(0, -40, 100, 16, "표 위 문장", .99), TextBox(10, 20, 60, 16, "구분", .99), TextBox(120, 5, 100, 16, "실적", .99),
                             TextBox(0, 100, 100, 16, "표 아래 문장", .99)], [sample_grid()])
    blocks = build_blocks(boxes)
    assert [type(block) for block in blocks] == [TextLine, Table, TextLine]


def test_grid_with_one_box_falls_back_to_text():
    boxes = RecognizedBoxes([TextBox(10, 20, 60, 16, "하나", .99)], [sample_grid()])
    blocks = build_blocks(boxes)
    assert [type(block) for block in blocks] == [TextLine]


def test_plain_list_still_works_without_grids():
    assert [type(block) for block in build_blocks([TextBox(10, 20, 60, 16, "글자", .99)])] == [TextLine]


def one_body_row(items, height=120):
    """머리글 행과, 세로선만 있고 행 사이 가로선이 없는 본문 행 하나로 된 표."""
    cells = (GridCell(0, 0, 1, 1, 0, 0, 100, 20), GridCell(0, 1, 1, 1, 100, 0, 200, 20), GridCell(0, 2, 1, 1, 200, 0, 300, 20),
             GridCell(1, 0, 1, 1, 0, 20, 100, height), GridCell(1, 1, 1, 1, 100, 20, 200, height), GridCell(1, 2, 1, 1, 200, 20, 300, height))
    return RecognizedBoxes([TextBox(10, 2, 40, 16, "구분", .99), TextBox(110, 2, 40, 16, "24", .99), TextBox(210, 2, 40, 16, "25", .99)] + items,
                           [Grid(2, 3, cells, 0, 0, 300, height)])


def body(rows):
    """[(왼쪽 글자, 가운데 글자, 오른쪽 글자)]를 20px 간격 줄로 놓는다. 빈 글자는 상자를 만들지 않는다."""
    return [TextBox(x, 24 + 20 * line, 60, 16, text, .99) for line, row in enumerate(rows) for x, text in zip((10, 110, 210), row) if text]


def cells_of(boxes):
    return [[cell.text for cell in row] for row in build_blocks(boxes)[0].rows]


def test_rows_without_rules_are_split_by_stacked_numbers():
    """세로선과 머리글 선만 있는 표의 본문이 한 행의 칸에 몰리면 안 된다(성과계획서 p011: 33줄이 3줄이 됐다)."""
    table = cells_of(one_body_row(body([("총지출", "22,168", "19,669"), ("증가율", "(24.4)", "(△9.6)"), ("기금", "", ""), ("총계", "26,128", "24,164")])))
    assert table == [["구분", "24", "25"], ["총지출", "22,168", "19,669"], ["증가율", "(24.4)", "(△9.6)"], ["기금", "", ""], ["총계", "26,128", "24,164"]]


def test_small_dash_stays_on_its_row():
    """'-' 상자는 낮아서 위치가 조금 어긋나도 그 행에 든다."""
    items = body([("가", "1", "2"), ("나", "3", ""), ("다", "5", "6")]) + [TextBox(230, 50, 8, 4, "-", .99)]
    assert cells_of(one_body_row(items))[2] == ["나", "3", "-"]


def test_two_line_number_cells_are_split_when_labels_line_up():
    table = cells_of(one_body_row(body([("총지출", "22,168", "19,669"), ("증가율", "(24.4)", "(△9.6)")]), height=64))
    assert table[1:] == [["총지출", "22,168", "19,669"], ["증가율", "(24.4)", "(△9.6)"]]


def test_value_and_share_stay_in_one_cell_beside_a_centered_label():
    """값과 비율을 두 줄로 쓴 칸은 한 행이다. 왼쪽 글자가 가운데 놓이면 줄마다 나누면 안 된다(p501)."""
    items = body([("", "2", "85"), ("", "(0.9%)", "(37.4%)")]) + [TextBox(10, 34, 60, 16, "관리과제", .99)]
    assert cells_of(one_body_row(items, height=64))[1:] == [["관리과제", "2 (0.9%)", "85 (37.4%)"]]


def test_wrapped_text_cells_stay_in_one_row():
    """글자만 있는 여러 줄 칸은 줄 높이가 옆 칸과 맞아도 한 칸이다."""
    table = cells_of(one_body_row(body([("초격차 분야", "관련 분야 논문 중", "조사 결과"), ("우수성과", "상위 1% 비율보다", "내부 자료"), ("창출 실적", "상향한 목표치", "활용")])))
    assert table[1:] == [["초격차 분야 우수성과 창출 실적", "관련 분야 논문 중 상위 1% 비율보다 상향한 목표치", "조사 결과 내부 자료 활용"]]


def test_one_cell_with_two_numbers_is_not_split():
    """숫자 두 줄이 한 칸에만 있으면 그 칸의 내용이다(합성 표의 여러 줄 칸)."""
    table = cells_of(one_body_row(body([("매출", "90.2", "강화"), ("제공", "1,392", "등에")]), height=64))
    assert table[1:] == [["매출 제공", "90.2 1,392", "강화 등에"]]


def test_merged_cell_beside_split_rows_spans_them():
    cells = (GridCell(0, 0, 2, 1, 0, 0, 100, 100), GridCell(0, 1, 1, 1, 100, 0, 200, 20), GridCell(0, 2, 1, 1, 200, 0, 300, 20),
             GridCell(1, 1, 1, 1, 100, 20, 200, 100), GridCell(1, 2, 1, 1, 200, 20, 300, 100))
    items = [TextBox(10, 40, 40, 16, "구분", .99), TextBox(110, 2, 40, 16, "24", .99), TextBox(210, 2, 40, 16, "25", .99)]
    items += [TextBox(x, 24 + 20 * line, 60, 16, text, .99) for line, row in enumerate([("1", "2"), ("3", "4"), ("5", "6")]) for x, text in zip((110, 210), row)]
    table = build_blocks(RecognizedBoxes(items, [Grid(2, 3, cells, 0, 0, 300, 100)]))[0]
    assert len(table.rows) == 4 and table.rows[0][0].row_span == 4
    assert all(row[0].covered for row in table.rows[1:])
    assert [row[1].text for row in table.rows] == ["24", "1", "3", "5"]
