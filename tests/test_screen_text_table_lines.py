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


def excel_sheet(rows=4, columns=3, row_height=18, column_width=70, text_gap=2):
    """연한 눈금선 표의 칸마다 숫자를 그린다. 숫자 바닥은 눈금선 text_gap 위에 한 줄로 늘어선다(엑셀 기본 행 높이)."""
    height, width = rows * row_height + 41, columns * column_width + 41
    image = np.full((height, width, 3), 255, np.uint8)
    for r in range(rows + 1):
        image[20 + r * row_height, 20:width - 20] = 224
    for c in range(columns + 1):
        image[20:height - 20, 20 + c * column_width] = 224
    boxes = []
    for r in range(rows):
        bottom = 20 + (r + 1) * row_height - text_gap - 1
        for c in range(columns):
            left = 20 + c * column_width + 4
            for k in range(8):       # 숫자 여덟 개의 몸통과 바닥 획
                x = left + k * 7
                image[bottom - 9:bottom, x:x + 1] = image[bottom - 9:bottom, x + 4:x + 5] = 40
                image[bottom - 9, x:x + 5] = 40
                image[bottom, x:x + 5] = 40
            boxes.append((left - 2, bottom - 11, left + 58, bottom + 2))
    return image, boxes


def test_text_bottom_row_next_to_a_gridline_is_not_part_of_the_line():
    """숫자 바닥 행이 길게 늘어서면 능선으로 보인다. 눈금선과 묶으면 칸 아래 끝이 글자 안쪽으로 올라가 소수점이 잘렸다(5.2 가 52 로)."""
    image, boxes = excel_sheet()
    grids = find_grids(image, boxes)
    assert len(grids) == 1
    grid = grids[0]
    assert (grid.rows, grid.columns) == (4, 3)
    first = next(cell for cell in grid.cells if cell.row == 0 and cell.column == 0)
    assert first.bottom >= 20 + 18 - 1      # 눈금선 바로 위까지다. 글자 바닥(35행)을 자르지 않는다
    assert first.top <= 21


def test_darker_text_row_does_not_hide_a_faint_gridline():
    """글자 바닥 행이 눈금선보다 훨씬 진해도 칸의 변은 눈금선이다. 눈금선과 글자 사이가 1픽셀인 작은 글씨에서 잘렸다."""
    image, boxes = excel_sheet(text_gap=1, rows=5, column_width=64)
    grids = find_grids(image, boxes)
    assert len(grids) == 1
    first = next(cell for cell in grids[0].cells if cell.row == 0 and cell.column == 0)
    assert first.bottom >= 20 + 18 - 1


def test_faint_gridline_inside_merged_boxes_is_a_column():
    """눈금선이 옅으면 위치 찾기가 옆 칸까지 한 상자로 묶는다. 상자 안을 지나도 여러 줄을 가로지르는 세로선은 글자 획이 아니다."""
    image, boxes = excel_sheet()
    merged = []
    for row in range(4):
        row_boxes = [box for box in boxes if 20 + row * 18 <= box[1] < 20 + (row + 1) * 18]
        merged.append((row_boxes[0][0], row_boxes[0][1], row_boxes[-1][2], row_boxes[0][3]))
    grids = find_grids(image, merged)
    assert len(grids) == 1 and (grids[0].rows, grids[0].columns) == (4, 3)


def test_stroke_of_one_line_is_still_a_stroke():
    """한 줄 높이의 세로획은 표 선이 아니다."""
    from screen_text.table_lines import _is_stroke
    assert _is_stroke((50, 50, 12, 24), [(10, 10, 120, 26)], True)
    assert _is_stroke((50, 50, 12, 60), [(10, 10, 120, 26), (10, 28, 120, 44), (10, 46, 120, 62)], False)  # 고르지 않으면 이어진 글자 획이다
    assert not _is_stroke((50, 50, 12, 60), [(10, 10, 120, 26), (10, 28, 120, 44), (10, 46, 120, 62)], True)


def test_columns_rise_above_the_top_line():
    """엑셀 열 머리글 띠는 위에 가로선이 없어 세로선 위끝이 뜬다. 가로선을 여럿 가로지르면 표 선이다."""
    image = canvas(300, 200)
    ys = [50, 80, 110, 140]
    for y in ys:
        hline(image, y, 20, 280, (200, 200, 200))
    for x in (20, 100, 190, 280):
        vline(image, x, 30, 140, (200, 200, 200))
    grids = find_grids(image, [(30, 58, 90, 72), (110, 58, 180, 72), (200, 58, 270, 72), (30, 88, 90, 102), (110, 88, 180, 102), (200, 88, 270, 102)])
    assert len(grids) == 1 and grids[0].columns == 3


def test_first_column_reaches_the_selection_edge():
    """엑셀 행 머리글 구분선은 왼쪽으로 갈수록 옅어져 선이 중간부터 잡힌다. 행 번호가 표 밖으로 밀렸다."""
    image = canvas(300, 170)
    for y in (40, 70, 100, 130):
        hline(image, y, 24, 280, (190, 190, 190))
    for x in (40, 160, 280):
        vline(image, x, 40, 130, (190, 190, 190))
    boxes = [(50, 48, 150, 62), (170, 48, 270, 62), (50, 78, 150, 92), (170, 78, 270, 92), (50, 108, 150, 122), (170, 108, 270, 122)]
    grids = find_grids(image, boxes, margin=8)
    assert len(grids) == 1 and grids[0].left == 8
    assert min(cell.left for cell in grids[0].cells) == 8


def test_left_border_stays_outside_the_first_column():
    """표 왼쪽에 세로선이 있으면 첫 칸을 영역 끝까지 넓히지 않는다. 표 선이 크롭에 들어가 '|'로 읽혔다."""
    xs, ys = [24, 120, 220], [40, 70, 100]
    image = grid_image(xs, ys)
    grids = find_grids(image, boxes_in(xs, ys), margin=8)
    assert len(grids) == 1 and min(cell.left for cell in grids[0].cells) == 25


def test_row_numbers_outside_the_left_border_become_a_column():
    """행 번호가 표 왼쪽 선 바깥에 있으면 표 뒤로 밀렸다."""
    xs, ys = [40, 140, 240], [20, 50, 80, 110]
    image = grid_image(xs, ys)
    inner = boxes_in(xs, ys)
    labels = [(20, y0 + 8, 30, y1 - 8) for y0, y1 in zip(ys, ys[1:])]
    grids = find_grids(image, inner + labels, margin=8)
    assert len(grids) == 1 and (grids[0].rows, grids[0].columns) == (3, 3)
    first = [cell for cell in grids[0].cells if cell.column == 0]
    assert len(first) == 3 and all(cell.right == 40 for cell in first)


def test_text_beside_only_some_rows_stays_outside():
    xs, ys = [40, 140, 240], [20, 50, 80, 110, 140]
    image = grid_image(xs, ys)
    grids = find_grids(image, boxes_in(xs, ys) + [(20, 28, 30, 42)], margin=8)
    assert len(grids) == 1 and grids[0].columns == 2


def test_left_column_of_a_two_column_page_stays_outside():
    """2단 문서에서 표 왼쪽 단의 긴 글자 줄이 표의 첫 열로 끌려 들어왔다."""
    xs, ys = [160, 240, 320], [20, 50, 80, 110]
    image = grid_image(xs, ys)
    lines = [(20, y0 + 8, 140, y1 - 8) for y0, y1 in zip(ys, ys[1:])]
    grids = find_grids(image, boxes_in(xs, ys) + lines, margin=8)
    assert len(grids) == 1 and grids[0].columns == 2
