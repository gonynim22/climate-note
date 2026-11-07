"""화면의 표 선을 찾아 칸 격자를 만든다. Qt를 쓰지 않고 numpy만 쓴다.

글자 상자의 위치만으로는 가운데 정렬 머리글과 왼쪽 정렬 본문이 다른 열로 갈리고, 여러 줄로 감긴 칸과 병합 칸을 알 수
없다. 표 선은 화면에 그대로 있으므로 선을 읽어 행·열과 병합을 정한다. 가늘고 긴 밝기 능선만 선으로 보므로 머리글의
바탕색이나 글자 획은 선이 되지 않는다. 선이 없는 표는 격자를 내지 않고 기존 글자 위치 규칙이 맡는다.
글자는 읽지도 바꾸지도 않는다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
from dataclasses import replace

import numpy as np

from screen_text.layout import Grid, GridCell
from screen_text.leading_symbols import ink_mask

RIDGE_REACHES = (2, 4)     # 선 양쪽으로 이만큼 떨어진 픽셀과 견준다. 굵기 2×거리-1 까지의 선이 능선으로 보인다
RIDGE_CONTRAST = 16        # 양쪽 모두와 이만큼(0~255) 달라야 선이다. 엑셀 눈금선(#D4D4D4 안팎)이 잡힐 만큼 낮다
STEP_CONTRAST = 24         # 바탕색 경계로 볼 위아래 밝기 차이
STEP_LENGTH = 48           # 밝기 계단을 선으로 믿는 최소 길이
STEP_FILL = 0.95
RIDGE_FILL = 0.7           # 능선 구간의 이 비율 이상이 칠해져야 선이다(짧은 끊김은 이어 붙였다)
MIN_H_LENGTH = 18          # 가로선의 최소 길이(픽셀)
MIN_V_LENGTH = 12          # 세로선의 최소 길이. 글자 획은 양 끝이 가로선에 닿지 않아 걸러진다
MAX_THICKNESS = 8          # 이보다 두꺼우면 선이 아니라 채운 띠다
SAME_LENGTH = 0.5          # 묶인 평행선에서 긴 선의 이 비율 이상 길어야 표 선의 일부로 친다(이중선)
SAME_LINE = 0.8            # 이웃 행의 구간이 긴 쪽의 이 비율 이상 겹쳐야 같은 선이다
BRIDGE_GAP = 3             # 한 선 안에서 이만큼의 끊김은 잇는다(교차점, 점선)
JOIN_TOLERANCE = 3         # 선끼리 닿았다고 보는 거리
END_TOLERANCE = 3          # 세로선 끝과 가로선의 거리. 교차점 옆은 능선이 끊겨 선이 조금 짧게 잡힌다
CLUSTER_GAP = 7            # 이보다 가까운 평행선은 한 선이다(이중선)
MIN_COVER = 0.6            # 칸 경계의 이 비율 이상을 선이 덮어야 경계가 있다고 본다
MIN_ROWS, MIN_COLUMNS = 2, 2
MIN_FILLED_CELLS = 0.3     # 글자가 든 칸의 하한(칸 수 대비). 실측 표 0.77 이상, 그래프 틀 0.25 이하
MIN_INKED_CELLS = 0.7      # 상자가 모자랄 때 글자 픽셀이 든 칸의 하한. 표시만 든 표는 칸이 찼고 그래프 틀은 비어 있다
MAX_CELL_SHARE = 0.6       # 한 칸에 몰린 글자 상자의 상한
CROWD_MIN_BOXES = 6        # 상자가 이보다 적으면 몰림을 말할 수 없다
STROKE_EDGE = 0.2          # 글자 상자의 위아래 이 비율 안쪽을 지나는 가로 선분이 글자 획이다
STROKE_SHARE = 0.5         # 그 길이가 선분의 이 비율 이상이면
MIN_PART_HEIGHT = 0.4      # 칸으로 나눈 조각의 높이 하한(상자 높이 대비). 옆 행을 살짝 건드린 자투리는 글자가 아니다
GRID_MIN_LINES = 1.8       # 표 높이는 글자 상자 높이의 이 배수 이상이다(글자 획이 만든 격자를 거른다)
SPREAD_MIN_COLUMNS = 3     # 이만큼 넓은 병합 칸의 글자가 열마다 하나씩 놓이면 병합이 아니다(두 칸은 낱말 둘과 구별되지 않는다)


def _gray(image):
    return image.astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def _ridges(gray):
    """위아래 양쪽과 같은 방향으로 달라지는 가로 능선 픽셀."""
    mask = np.zeros(gray.shape, dtype=bool)
    for reach in RIDGE_REACHES:
        if gray.shape[0] <= 2 * reach:
            continue
        up = gray[reach:-reach] - gray[:-2 * reach]
        down = gray[reach:-reach] - gray[2 * reach:]
        mask[reach:-reach] |= ((up > RIDGE_CONTRAST) & (down > RIDGE_CONTRAST)) | ((up < -RIDGE_CONTRAST) & (down < -RIDGE_CONTRAST))
    return mask


def _steps(gray):
    """머리글 바탕색의 경계처럼 선 없이 밝기만 바뀌는 곳. 글자 획의 위아래도 여기 걸리므로 길게 이어질 때만 쓴다."""
    mask = np.zeros(gray.shape, dtype=bool)
    if gray.shape[0] > 2:
        mask[1:-1] = np.abs(gray[2:] - gray[:-2]) > STEP_CONTRAST
    return mask


def _runs(row, length):
    """한 행의 True 구간 중 작은 끊김을 이은 뒤 length 이상인 (시작, 끝) 목록(끝 포함)."""
    edges = np.flatnonzero(np.diff(np.concatenate(([0], row.astype(np.int8), [0]))))
    spans, start, end = [], None, None
    for a, b in zip(edges[0::2].tolist(), (edges[1::2] - 1).tolist()):
        if start is not None and a - end - 1 <= BRIDGE_GAP:
            end = b
            continue
        if start is not None and end - start + 1 >= length:
            spans.append((start, end))
        start, end = a, b
    if start is not None and end - start + 1 >= length:
        spans.append((start, end))
    return spans


def _segments(mask, length):
    """가로 선분 [(위, 아래, 왼쪽, 오른쪽)]. 이어진 행의 긴 구간을 한 선분으로 묶는다."""
    finished, active = [], []
    for y in np.flatnonzero(mask.sum(axis=1) >= length).tolist():
        spans = _runs(mask[y], length)
        carried = []
        for segment in active:
            if segment[1] < y - 1:
                finished.append(segment)
            else:
                carried.append(segment)
        active = carried
        for x0, x1 in spans:
            for segment in active:
                # 굵은 선의 이웃 행만 잇는다. 길이가 다른 구간까지 이으면 대각선이 표 선을 삼켜 너무 두꺼운 띠가 된다
                if min(segment[3], x1) - max(segment[2], x0) >= SAME_LINE * (max(segment[3] - segment[2], x1 - x0) + 1):
                    segment[1] = y
                    segment[2], segment[3] = min(segment[2], x0), max(segment[3], x1)
                    break
            else:
                active.append([y, y, x0, x1])
    finished.extend(active)
    return [tuple(s) for s in finished if s[1] - s[0] + 1 <= MAX_THICKNESS]


def _filled(mask, segment, fill):
    """선분의 한 행이 길이의 fill 이상 칠해졌는가. 글자 획을 이은 구간은 어느 행도 빈 곳이 많다."""
    top, bottom, left, right = segment
    return mask[top:bottom + 1, left:right + 1].mean(axis=1).max() >= fill


def _lines(gray, length):
    """표 선 후보(위, 아래, 왼쪽, 오른쪽). 능선은 짧아도 믿고, 밝기 계단은 길고 빈틈없을 때만 믿는다."""
    ridges = _ridges(gray)
    found = [s for s in _segments(ridges, length) if _filled(ridges, s, RIDGE_FILL)]
    steps = _steps(gray)
    found += [s for s in _segments(steps, STEP_LENGTH) if _filled(steps, s, STEP_FILL)]
    return [_tight(gray, segment) for segment in found]


def _tight(gray, segment):
    """선분의 두께를 실제 밝기로 좁힌다. 능선·계단 표시는 선 옆 한 줄까지 번지는데, 글자가 표 선에 붙은 표에서는 그 한 줄이 글자다."""
    top, bottom, left, right = segment
    first, last = max(0, top - 2), min(gray.shape[0], bottom + 3)
    profile = gray[first:last, left:right + 1].mean(axis=1)
    contrast = np.abs(profile - np.median(profile))
    peak = float(contrast.max())
    if peak <= 0:
        return segment
    rows = np.flatnonzero(contrast >= .5 * peak)
    return first + int(rows[0]), first + int(rows[-1]), left, right


def _touches(line, column):
    """가로 선분 line과 세로 선분 column이 닿는가."""
    top, bottom, left, right = line
    v_left, v_right, v_top, v_bottom = column
    return (left - JOIN_TOLERANCE <= v_right and v_left <= right + JOIN_TOLERANCE
            and v_top - JOIN_TOLERANCE <= bottom and top <= v_bottom + JOIN_TOLERANCE)


def _spans_between(column, lines, area):
    """세로 선분의 위아래 끝이 모두 가로선이나 고른 영역의 끝에 닿는가. 글자 획은 한쪽 끝이 닿아도 다른 쪽이 비어 있다."""
    v_left, v_right, v_top, v_bottom = column

    def reaches(y):
        return (y <= area[0] + JOIN_TOLERANCE or y >= area[1] - JOIN_TOLERANCE
                or any(left - JOIN_TOLERANCE <= v_right and v_left <= right + JOIN_TOLERANCE
                       and top - END_TOLERANCE <= y <= bottom + END_TOLERANCE for top, bottom, left, right in lines))
    return reaches(v_top) and reaches(v_bottom)


def _groups(horizontal, vertical, area):
    """서로 닿은 가로·세로 선분 묶음 [(가로 선분들, 세로 선분들)]. 양 끝이 가로선에 닿는 세로선과 그런 세로선을 둘 이상 만나는 가로선만 남긴다."""
    lines, columns = list(horizontal), list(vertical)
    while True:
        kept_columns = [column for column in columns if _spans_between(column, lines, area)]
        kept_lines = [line for line in lines if sum(_touches(line, column) for column in kept_columns) >= 2]
        if len(kept_columns) == len(columns) and len(kept_lines) == len(lines):
            break
        lines, columns = kept_lines, kept_columns
    parent = list(range(len(lines) + len(columns)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, line in enumerate(lines):
        for j, column in enumerate(columns):
            if _touches(line, column):
                parent[find(i)] = find(len(lines) + j)
    groups = {}
    for i in range(len(parent)):
        group = groups.setdefault(find(i), ([], []))
        if i < len(lines):
            group[0].append(lines[i])
        else:
            group[1].append(columns[i - len(lines)])
    return [group for group in groups.values() if group[0] and group[1]]


def _cluster(lines):
    """평행선을 긴 선부터 묶은 (가운데, 낮은 끝, 높은 끝) 목록. lines는 (낮은 끝, 높은 끝, 길이).

    짧은 조각은 가까운 긴 선에 흡수만 되고 끝을 넓히지 않는다. 표 선 옆 글자 획이 칸을 좁히지 않게 하려는 것이다.
    """
    groups = []
    for low, high, length in sorted(lines, key=lambda line: -line[2]):
        center = (low + high) / 2
        group = next((g for g in groups if abs(g[0] - center) <= CLUSTER_GAP), None)
        if group is None:
            groups.append([center, low, high, length])
        elif length >= SAME_LENGTH * group[3]:
            group[1], group[2] = min(group[1], low), max(group[2], high)
            group[0] = (group[1] + group[2]) / 2
    return sorted((center, low, high) for center, low, high, _ in groups)


def _covered(segments, start, end):
    """[start, end] 구간을 선분들이 덮는 비율. segments는 (시작, 끝)."""
    length = max(1.0, end - start)
    total, reach = 0.0, start
    for a, b in sorted(segments):
        a, b = max(a, reach), min(b, end)
        if b > a:
            total += b - a
            reach = b
    return total / length


def _edges(positions, lines, cross):
    """positions[k]의 경계가 교차 구간 cross[c]~cross[c+1]을 덮는가. lines는 (가운데, 시작, 끝)."""
    table = []
    for position in positions:
        near = [(a, b) for center, a, b in lines if abs(center - position) <= CLUSTER_GAP]
        table.append([_covered(near, cross[c], cross[c + 1]) >= MIN_COVER for c in range(len(cross) - 1)])
    return table


def _merged_cells(rows, columns, right_open, down_open):
    """경계가 없는 이웃 칸을 묶어 직사각형 칸으로. right_open[r][c]: (r,c)와 (r,c+1) 사이가 열려 있다."""
    label = [[r * columns + c for c in range(columns)] for r in range(rows)]
    parent = list(range(rows * columns))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for r in range(rows):
        for c in range(columns):
            if c + 1 < columns and right_open[r][c]:
                parent[find(label[r][c])] = find(label[r][c + 1])
            if r + 1 < rows and down_open[r][c]:
                parent[find(label[r][c])] = find(label[r + 1][c])
    areas = {}
    for r in range(rows):
        for c in range(columns):
            areas.setdefault(find(label[r][c]), []).append((r, c))
    cells = []
    for members in areas.values():
        top, left = min(r for r, _ in members), min(c for _, c in members)
        bottom, right = max(r for r, _ in members), max(c for _, c in members)
        if len(members) != (bottom - top + 1) * (right - left + 1):  # ㄱ자로 열린 칸: 표가 아니라 그래프나 그림의 선이다
            return None
        cells.append((top, left, bottom - top + 1, right - left + 1))
    return cells


def _grid(horizontal, vertical):
    h_lines = [((top + bottom) / 2, left, right) for top, bottom, left, right in horizontal]
    v_lines = [((left + right) / 2, top, bottom) for left, right, top, bottom in vertical]
    left, right = min(line[1] for line in h_lines), max(line[2] for line in h_lines)
    top, bottom = min(line[1] for line in v_lines), max(line[2] for line in v_lines)
    xs = _cluster([(a, b, y1 - y0) for a, b, y0, y1 in vertical if left - CLUSTER_GAP <= (a + b) / 2 <= right + CLUSTER_GAP])
    ys = _cluster([(a, b, x1 - x0) for a, b, x0, x1 in horizontal if top - CLUSTER_GAP <= (a + b) / 2 <= bottom + CLUSTER_GAP])
    # 바깥 세로선(또는 가로선)이 없는 표는 맞닿은 선의 끝을 경계로 쓴다
    if xs[0][0] - left > CLUSTER_GAP:
        xs.insert(0, (float(left), left, left))
    if right - xs[-1][0] > CLUSTER_GAP:
        xs.append((float(right), right, right))
    if ys[0][0] - top > CLUSTER_GAP:
        ys.insert(0, (float(top), top, top))
    if bottom - ys[-1][0] > CLUSTER_GAP:
        ys.append((float(bottom), bottom, bottom))
    # 어느 칸의 변도 되지 못한 위치는 글자 획이나 작은 조각이다
    for _ in range(4):
        x_centers, y_centers = [x[0] for x in xs], [y[0] for y in ys]
        across = _edges(x_centers[1:-1], v_lines, y_centers)   # across[k][r]: k+1번 세로 경계가 r행을 덮는다
        down = _edges(y_centers[1:-1], h_lines, x_centers)     # down[k][c]: k+1번 가로 경계가 c열을 덮는다
        keep_x = [0] + [k + 1 for k, column in enumerate(across) if any(column)] + [len(xs) - 1]
        keep_y = [0] + [k + 1 for k, row in enumerate(down) if any(row)] + [len(ys) - 1]
        if len(keep_x) == len(xs) and len(keep_y) == len(ys):
            break
        xs, ys = [xs[k] for k in keep_x], [ys[k] for k in keep_y]
    rows, columns = len(ys) - 1, len(xs) - 1
    if rows < MIN_ROWS or columns < MIN_COLUMNS:
        return None
    right_open = [[not across[c][r] for c in range(columns - 1)] for r in range(rows)]
    down_open = [[not down[r][c] for c in range(columns)] for r in range(rows - 1)]
    merged = _merged_cells(rows, columns, right_open, down_open)
    if merged is None or len(merged) < 2:
        return None
    # 칸의 네 변은 표 선 바로 안쪽이다. 글자가 표 선에 붙은 표가 있어 한 픽셀도 더 먹어 들어가지 않는다
    cells = [GridCell(r, c, rs, cs, xs[c][2] + 1, ys[r][2] + 1, xs[c + cs][1], ys[r + rs][1]) for r, c, rs, cs in merged]
    return Grid(rows, columns, tuple(sorted(cells, key=lambda cell: (cell.row, cell.column))), xs[0][1], ys[0][1], xs[-1][2], ys[-1][2])


def _keep_real(grids, boxes, image):
    """글자 획이 격자처럼 보인 것을 버린다. 진짜 표는 글자 줄 두 줄 이상의 높이이고 글자 상자가 표를 덮지 않는다."""
    if not boxes:
        return []
    heights = sorted(y1 - y0 for _, y0, _, y1 in boxes)
    line = heights[len(heights) // 2]
    kept = []
    for grid in grids:
        width, height = grid.right - grid.left, grid.bottom - grid.top
        if height < GRID_MIN_LINES * line or width < 3 * line:
            continue
        area = width * height
        covered = any((min(x1, grid.right) - max(x0, grid.left)) * (min(y1, grid.bottom) - max(y0, grid.top)) >= .6 * area
                      for x0, y0, x1, y1 in boxes if x1 > grid.left and x0 < grid.right and y1 > grid.top and y0 < grid.bottom)
        if not covered and _holds_text(grid, boxes, image):
            kept.append(grid)
    return kept


def _holds_text(grid, boxes, image):
    """글자가 칸에 고루 들어야 표다. 그래프 틀과 머리선이 만든 격자는 칸 대부분이 비거나 한 칸에 쪽 전체가 몰린다.

    표시만 든 칸(○ ● ■)은 글자 상자가 없다. 상자로 모자라면 칸의 글자 픽셀까지 센다.
    """
    counts = {}
    for x0, y0, x1, y1 in boxes:
        x, y = (x0 + x1) / 2, (y0 + y1) / 2
        if grid.left <= x <= grid.right and grid.top <= y <= grid.bottom:
            cell = next((c for c in grid.cells if c.left <= x <= c.right and c.top <= y <= c.bottom), None)
            counts[cell] = counts.get(cell, 0) + 1
    total = sum(counts.values())
    if len(counts) < MIN_FILLED_CELLS * len(grid.cells):
        marked = sum(cell not in counts and ink_mask(image[int(cell.top) + 2:int(cell.bottom) - 1, int(cell.left) + 2:int(cell.right) - 1]).any() for cell in grid.cells)
        if len(counts) + marked < MIN_INKED_CELLS * len(grid.cells):
            return False
    return total < CROWD_MIN_BOXES or max(counts.values()) <= MAX_CELL_SHARE * total


def _spread_over_columns(cell, edges, boxes):
    """병합 칸의 글자 상자가 아래 열마다 하나씩 놓였는가."""
    columns = range(cell.column, cell.column + cell.column_span)
    inside = [box for box in boxes if cell.left <= (box[0] + box[2]) / 2 <= cell.right and cell.top <= (box[1] + box[3]) / 2 <= cell.bottom]
    return (len(inside) == cell.column_span and all(column in edges for column in columns)
            and all(sum(edges[column][0] <= x0 and x1 <= edges[column][1] for x0, _, x1, _ in inside) == 1 for column in columns))


def _open_spread_cells(grid, boxes):
    """머리글에서 세로선이 끊긴 표를 고친다. 넓은 병합 칸의 글자가 열마다 하나씩 놓이면 병합이 아니라 각 열의 칸이다."""
    edges = {}
    for cell in grid.cells:
        if cell.column_span == 1:
            left, right = edges.get(cell.column, (cell.left, cell.right))
            edges[cell.column] = (min(left, cell.left), max(right, cell.right))
    cells = []
    for cell in grid.cells:
        if cell.column_span >= SPREAD_MIN_COLUMNS and cell.row_span == 1 and _spread_over_columns(cell, edges, boxes):
            cells.extend(GridCell(cell.row, column, 1, 1, edges[column][0], cell.top, edges[column][1], cell.bottom)
                         for column in range(cell.column, cell.column + cell.column_span))
        else:
            cells.append(cell)
    return replace(grid, cells=tuple(sorted(cells, key=lambda cell: (cell.row, cell.column))))


def _is_stroke(column, boxes):
    """세로 선분 대부분이 글자 상자 안쪽에 있으면 글자 획이다. 표 선은 글자를 가로지르지 않는다."""
    left, right, top, bottom = column
    inside = 0
    for x0, y0, x1, y1 in boxes:
        reach = 0
        if x0 + reach < left and right < x1 - reach:
            inside += max(0, min(bottom + 1, y1) - max(top, y0))
    return inside >= .9 * (bottom - top + 1)


def _in_text_row(line, boxes):
    """가로 선분이 글자 상자의 위아래 안쪽을 지나면 글자 획이다. 한글 가로획은 한 행에 나란히 놓여 표 선처럼 길게 이어진다."""
    top, bottom, left, right = line
    inside = 0
    for x0, y0, x1, y1 in boxes:
        reach = STROKE_EDGE * (y1 - y0)
        if y0 + reach < top and bottom < y1 - reach:
            inside += max(0, min(right + 1, x1) - max(left, x0))
    return inside >= STROKE_SHARE * (right - left + 1)


def find_grids(image, boxes, margin=0):
    """RGB 이미지에서 표 격자 목록. 좌표는 이미지 픽셀이고, 표 선이 없으면 빈 목록이다.

    boxes는 위치 찾기 상자, margin은 이미지 둘레에 두른 여백이다. 영역을 표 중간에서 잘라 고른 세로선은 고른 영역의 끝에서 끝난다
    (여백까지 이어 그린 선도 그 끝에서 자른다).
    """
    if min(image.shape[:2]) < 2 * max(RIDGE_REACHES) + 1:
        return []
    gray = _gray(image)
    horizontal = [line for line in _lines(gray, MIN_H_LENGTH) if not _in_text_row(line, boxes)]
    if len(horizontal) < 2:
        return []
    area = (margin, image.shape[0] - 1 - margin)
    vertical = [(left, right, max(top, area[0]), min(bottom, area[1])) for left, right, top, bottom in _lines(gray.T, MIN_V_LENGTH)
                if not _is_stroke((left, right, top, bottom), boxes)]
    grids = []
    for lines, columns in _groups(horizontal, vertical, area):
        grid = _grid(lines, columns)
        if grid is not None:
            grids.append(grid)
    return sorted((_open_spread_cells(grid, boxes) for grid in _keep_real(grids, boxes, image)), key=lambda grid: grid.top)


def fit_boxes(image, boxes, grids, factor=1):
    """표 안의 글자 상자를 칸 안쪽으로 맞춘다. 칸을 가로지른 상자는 칸별로 나누고, 표 선이 든 쪽은 잘라낸다.

    표 선이 크롭에 들어가면 모델이 '|', '1', 'I'로 읽는다. 글자 없는 조각은 버리고 표 밖 상자는 그대로 둔다.
    factor는 image가 격자를 찾은 이미지의 몇 배인지다(격자 좌표는 이미 image 좌표다).
    """
    out = []
    for box in boxes:
        x0, y0, x1, y1 = box
        center_x, center_y = (x0 + x1) / 2, (y0 + y1) / 2
        grid = next((g for g in grids if g.left <= center_x <= g.right and g.top <= center_y <= g.bottom), None)
        if grid is None:
            out.append(box)
            continue
        parts = []
        inset = factor - 1   # 2배 이미지는 표 선이 옆 픽셀로 번져 있다
        for cell in grid.cells:
            left, top = int(max(x0, cell.left + inset)), int(max(y0, cell.top + inset))
            right, bottom = int(min(x1, cell.right - inset)), int(min(y1, cell.bottom - inset))
            if (right - left >= 3 and bottom - top >= max(4 * factor, MIN_PART_HEIGHT * (y1 - y0))
                    and ink_mask(image[top:bottom, left:right]).any()):
                parts.append((left, top, right, bottom))
        out.extend(parts or [box])
    return out
