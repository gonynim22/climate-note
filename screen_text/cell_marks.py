"""표 칸과 글자 줄 사이의 표시 하나(○ ● ◎ ■ ★ ▶ 등)를 모양으로 읽는다. Qt를 쓰지 않고 numpy만 쓴다.

해당 여부 표나 점검표의 칸에는 표시 하나만 든다. 위치 찾기 모델은 이런 칸을 글자로 보지 않아 상자가 없고 사전에도 대부분 없어서
표의 내용이 조용히 사라졌다(실측 ● 0/79, ■ 0/89, ◎ 0/80). 표 선이 정한 빈 칸이나 한 줄의 상자 사이에 덩어리가 있으면 상자를 만들고,
덩어리의 모양이 분명하면 그 기호로 낸다. 화면 모양을 읽을 뿐 글자를 추정하지 않는다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import numpy as np

from screen_text.leading_symbols import SEARCH_LEFT, THIN_INK_FRACTION, ink_mask
from screen_text.triangles import _any_direction

MIN_PX = 5                  # 이보다 작으면 모양을 말할 수 없다
ASPECT = (0.78, 1.28)       # 가로/세로. 숫자 0은 더 좁다
SQUARE_FILL = 0.93          # 속이 찬 네모의 채움
CIRCLE_FILL = 0.66          # 속이 찬 원의 채움 하한(π/4)
DIAMOND_FILL = 0.4          # 속이 찬 마름모의 채움 하한(1/2)
MIN_MIRROR = 0.86           # 좌우·상하 대칭의 하한. 'D'는 오른쪽만 둥글고 'ㅎ'은 위아래가 다르다
TARGET_MIRROR = 0.7         # ◎의 대칭 하한
TIP_SIZE = 0.12             # 꼭짓점 칸의 크기(폭·높이 대비)
SQUARE_TIPS = 0.75          # 네 꼭짓점 칸 중 이만큼 차 있으면 네모다
ROUND_TIPS = 0.25           # 원과 마름모의 꼭짓점은 비어 있다
CORNER_SIZE = 0.25          # 모서리 칸의 크기. 마름모는 여기가 빈다
DIAMOND_CORNERS = 0.08
DIAMOND_SIDE = 0.25         # 마름모의 왼쪽 끝은 점에 가깝다. 작은 원은 모서리가 비어도 옆이 곧다
STAR_TOP = 0.35             # 별의 맨 위 띠 폭 상한(폭 대비)
STAR_MIRROR = 0.8
STAR_SOLID = 0.8            # 가운데가 이만큼 차면 ★
MIN_HEIGHT = 0.4            # 표시 높이의 하한(줄 글자 높이 대비)
MAX_HEIGHT = 1.45           # 표시 높이의 상한. 넘으면 그림이나 표 선이다
MAX_WIDTH = 2.2             # 표시 폭의 상한(줄 글자 높이 대비)
DASH_MIN_WIDTH = 0.3        # 칸의 '-' 폭 하한(줄 글자 높이 대비)
RULE_FILL = 0.8             # 칸 가장자리에서 이 비율 이상 찬 행·열은 표 선의 찌꺼기다
INSET = 2                   # 칸 변에서 표 선 몫으로 빼는 폭
PAD = 1                     # 표시 상자의 둘레 여백
MIN_GAP = 0.7               # 상자 사이의 틈이 줄 글자 높이의 이만큼 돼야 그 사이를 본다
SAME_ROW = 0.5              # 두 상자가 낮은 쪽 높이의 이만큼 겹쳐야 같은 줄이다
RING = "○"
MODEL_KEEPS = frozenset("VvXxYy×√✓✔")  # 모델이 잘 읽고 굵은 'V'는 모양이 ▽처럼 보인다
BULLET_MARKS = frozenset("■●◆")
SOLID_MARKS = frozenset("●■◆★▶◀▲▼")  # 모델이 영문자로 읽었어도 믿는 모양. 'A'는 속이 빈 별처럼 보인다
ROUND_LETTERS = frozenset(("O", "o"))
GAP_MARKS = frozenset("●■◆★▶▲▼")  # 글자 줄 사이에서는 속이 찬 모양만 믿는다. 속이 빈 모양은 글자 조각이 흉내 낸다


def _runs(row):
    """행에서 이어진 글자 픽셀 구간의 수."""
    return int(np.count_nonzero(np.diff(np.concatenate(([0], row.astype(np.int8), [0]))) == 1))


def _tips(glyph, size):
    height, width = glyph.shape
    tall, wide = max(1, round(height * size)), max(1, round(width * size))
    return glyph[:tall, :wide], glyph[:tall, -wide:], glyph[-tall:, :wide], glyph[-tall:, -wide:]


def _is_closed(glyph):
    height, width = glyph.shape
    row, column = glyph[height // 2], glyph[:, width // 2]
    return bool(row[:width // 2].any() and row[width // 2 + 1:].any() and column[:height // 2].any() and column[height // 2 + 1:].any())


def _is_star(glyph):
    height, width = glyph.shape
    band = max(1, round(height * .12))
    top = np.flatnonzero(glyph[:band].any(axis=0))
    if top.size == 0 or top[-1] - top[0] + 1 > STAR_TOP * width:
        return False
    return _runs(glyph[-1]) >= 2 and (glyph == glyph[:, ::-1]).mean() >= STAR_MIRROR


def mark_of(glyph):
    """딱 맞게 자른 글자 픽셀이 분명한 표시면 그 기호, 아니면 None."""
    height, width = glyph.shape
    if min(height, width) < MIN_PX:
        return None
    triangle = _any_direction(glyph)
    if triangle:
        return triangle
    if not ASPECT[0] <= width / height <= ASPECT[1]:
        return None
    fill = float(glyph.mean())
    if fill >= SQUARE_FILL:
        return "■"
    if _is_star(glyph):
        core = glyph[int(height * .4):max(int(height * .4) + 1, int(height * .65)), int(width * .4):max(int(width * .4) + 1, int(width * .6))]
        return "★" if core.mean() >= STAR_SOLID else "☆"
    mirror = min((glyph == glyph[:, ::-1]).mean(), (glyph == glyph[::-1]).mean())
    tips = float(np.mean([tip.any() for tip in _tips(glyph, TIP_SIZE)]))
    runs = _runs(glyph[height // 2])
    if runs >= 3:  # 고리 둘은 획이 가늘어 대칭이 덜 맞는다
        return "◎" if mirror >= TARGET_MIRROR and tips <= ROUND_TIPS and _is_closed(glyph) else None
    if mirror < MIN_MIRROR:
        return None
    if runs == 1:
        if tips > ROUND_TIPS:
            return None
        return "●" if fill >= CIRCLE_FILL else "◆" if fill >= DIAMOND_FILL else None
    if not _is_closed(glyph):
        return None
    if tips >= SQUARE_TIPS:
        return "□"
    corners = float(np.mean([tip.mean() for tip in _tips(glyph, CORNER_SIZE)]))
    return "◇" if corners <= DIAMOND_CORNERS and glyph[:, 0].mean() < DIAMOND_SIDE else RING


def _trimmed(ink):
    rows, columns = np.flatnonzero(ink.any(axis=1)), np.flatnonzero(ink.any(axis=0))
    if rows.size == 0:
        return None
    return int(rows[0]), int(rows[-1]) + 1, int(columns[0]), int(columns[-1]) + 1


def _without_rule_scraps(ink):
    """칸 가장자리의 표 선 찌꺼기를 지운다."""
    out = ink.copy()
    height, width = ink.shape
    for edge in (0, 1, height - 2, height - 1):
        if 0 <= edge < height and ink[edge].mean() >= RULE_FILL:
            out[edge] = False
    for edge in (0, 1, width - 2, width - 1):
        if 0 <= edge < width and ink[:, edge].mean() >= RULE_FILL:
            out[:, edge] = False
    return out


def _line_height(boxes):
    return float(np.median([box[3] - box[1] for box in boxes])) if boxes else 0.0


def _inside(box, cell):
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return cell.left <= x <= cell.right and cell.top <= y <= cell.bottom


def empty_cell_boxes(image, grids, boxes):
    """글자 상자가 없는 칸에서 표시 크기의 덩어리를 찾아 상자로 낸다. image와 grids, boxes는 같은 좌표다."""
    line = _line_height(boxes)
    found = []
    if line <= 0:
        return found
    for grid in grids:
        for cell in grid.cells:
            if any(_inside(box, cell) for box in boxes):
                continue
            left, top = int(cell.left) + INSET, int(cell.top) + INSET
            right, bottom = int(cell.right) - INSET + 1, int(cell.bottom) - INSET + 1
            if right - left < 3 or bottom - top < 3:
                continue
            span = _trimmed(_without_rule_scraps(ink_mask(image[top:bottom, left:right])))
            if span is None:
                continue
            y0, y1, x0, x1 = span
            tall, wide = y1 - y0, x1 - x0
            is_dash = tall <= MIN_HEIGHT * line and wide >= DASH_MIN_WIDTH * line
            if (is_dash or MIN_HEIGHT * line <= tall <= MAX_HEIGHT * line) and wide <= MAX_WIDTH * line:
                found.append((left + x0 - PAD, top + y0 - PAD, left + x1 + PAD, top + y1 + PAD))
    return found


def _same_row(a, b):
    return min(a[3], b[3]) - max(a[1], b[1]) >= SAME_ROW * min(a[3] - a[1], b[3] - b[1])


def gap_mark_boxes(image, boxes):
    """한 줄의 상자 사이에 든 표시('접수 ▶ 심사')의 상자. 사진이나 아이콘을 읽지 않도록 모양이 분명한 것만 낸다."""
    found = []
    for box in boxes:
        height = box[3] - box[1]
        following = [other for other in boxes if other[0] > box[2] and _same_row(box, other)]
        if not following:
            continue
        right = min(other[0] for other in following)
        if right - box[2] < MIN_GAP * height:
            continue
        crop = ink_mask(image[box[1]:box[3], box[2]:right])
        span = _trimmed(crop)
        if span is None:
            continue
        y0, y1, x0, x1 = span
        if not MIN_HEIGHT * height <= y1 - y0 <= MAX_HEIGHT * height:
            continue
        kind = mark_of(crop[y0:y1, x0:x1])
        taken = kind in BULLET_MARKS and right - (box[2] + x1) <= SEARCH_LEFT * height  # 뒤 상자의 글머리로 이미 읽힌다('□ 시 ■ 군')
        if kind in GAP_MARKS and not taken:
            found.append((box[2] + x0 - PAD, box[1] + y0 - PAD, box[2] + x1 + PAD, box[1] + y1 + PAD))
    return found


def _glyph_at(image, box):
    """상자 안의 글자 픽셀을 딱 맞게 자른다. 꽉 찬 표시만 든 좁은 크롭은 중앙값이 글자 색이 되므로 둘레까지 보고 배경을 정한다."""
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return None
    reach = max(x1 - x0, y1 - y0)
    left, top = max(0, x0 - reach), max(0, y0 - reach)
    ink = ink_mask(image[top:y1 + reach, left:x1 + reach], THIN_INK_FRACTION)[y0 - top:y1 - top, x0 - left:x1 - left]
    span = _trimmed(ink)
    return None if span is None else ink[span[0]:span[1], span[2]:span[3]]


def _lone_boxes(grids, boxes, results):
    """칸에 혼자 든 상자 {번호: 칸 안쪽}. 위치 찾기는 ◎의 안쪽 고리만 잡거나 ■를 조각으로 잡기도 해서 모양은 칸 전체에서 본다."""
    lone = {}
    for grid in grids:
        for cell in grid.cells:
            inside = [index for index, box in enumerate(boxes) if _inside(box, cell)]
            read = [index for index in inside if results[index][0].strip()]
            inside = read or inside[:1]
            if len(inside) == 1:
                lone[inside[0]] = (int(cell.left) + INSET, int(cell.top) + INSET, int(cell.right) - INSET + 1, int(cell.bottom) - INSET + 1)
    return lone


def read_marks(image, grids, boxes, results, added):
    """added번 이후의 새 상자와 칸에 혼자 든 짧은 상자를 모양으로 읽는다. [(글자, 점수, 확인 필요 앞글자 수)]를 돌려준다."""
    lone = _lone_boxes(grids, boxes, results)
    out = list(results)
    for index, (text, _, _) in enumerate(results):
        text = text.strip()
        if index < added and (index not in lone or len(text) > 2 or text[:1] in MODEL_KEEPS or any("가" <= char <= "힣" or char.isdigit() for char in text)):
            continue
        glyph = _glyph_at(image, lone.get(index, boxes[index]))
        kind = None if glyph is None else mark_of(glyph)
        letter = any(char.isascii() and char.isalpha() for char in text) and text not in ROUND_LETTERS
        if kind and (index >= added or kind in SOLID_MARKS or not letter):
            out[index] = (kind, 1.0, int(kind == RING))
    return out
