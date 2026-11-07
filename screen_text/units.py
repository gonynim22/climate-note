"""㎡ ㎥ ㎢ ℃ 를 화면 모양으로 되살린다. Qt를 쓰지 않고 numpy만 쓴다.

인식 모델 사전에 없는 단위라 ㎥ 이 m·m²·mi 로, ℃ 가 C·c·'C 로 읽힌다. 환경 문서에서 ㎍/㎥ 이 ㎍/m 이 되면 단위가 바뀐다.
㎡ ㎥ 은 m 오른쪽 위의 작은 숫자이고 ℃ 는 C 왼쪽 위의 작은 고리다. 그 덩어리가 화면에 있을 때만 바꾼다. 위 첨자 2와 3은
아래쪽 행의 무게중심이 왼쪽이냐 오른쪽이냐로 갈린다. 작아서 모양을 말할 수 없으면 모델이 읽은 숫자를 쓰고 확인 필요로
표시한다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import numpy as np

from screen_text.corner_brackets import components
from screen_text.leading_symbols import THIN_INK_FRACTION, ink_mask

SQUARE, CUBE = "㎡", "㎥"
SQUARE_KM, CUBE_KM = "㎢", "㎦"
CELSIUS = "℃"
ROUND_READS = frozenset("°'\"`´‘’ºo")      # 고리를 이렇게 읽는다
SUPER_READS = frozenset("²³23'`´\"‘’{}iz*r")   # 위 첨자를 이렇게 읽는다
STEM_EVEN = 1              # m 줄기 간격 차이의 상한(픽셀)
BODY_REACH = 0.8           # m 줄기를 찾는 거리(상자 높이 대비)
REACH = 1.2                # 단위 글자 둘레를 찾는 거리(상자 높이 대비)
MIN_MARK_ROWS = 2
SUPER_GAP = 0.45           # m 오른쪽 끝에서 위 첨자 끝까지의 폭 상한(m 높이 대비). 더 멀면 뒤 글자의 ㅇ 같은 조각이다
SHAPE_ROW = 0.7            # 2와 3이 갈리는 행(위 첨자 높이 대비). 2는 왼쪽으로 내려가고 3은 오른쪽으로 돌아온다
SHAPE_MIN_ROWS = 4         # 이보다 낮으면 모양을 말할 수 없다
SHAPE_LEFT, SHAPE_RIGHT = 0.42, 0.58
RING_BOTTOM = 0.6          # 고리 아래 끝은 C 위쪽 이 비율 안에 있다(C 높이 대비)
RING_MAX_HEIGHT = 0.65     # 고리 높이의 상한(C 높이 대비)
RING_REACH = 0.7           # C 왼쪽 끝에서 고리까지의 거리 상한(C 높이 대비)


def _glyph_at(found, x):
    """x 열을 지나는 가장 높은 덩어리."""
    over = [item for item in found if item[3] <= x < item[3] + item[0].shape[1]]
    return max(over, key=lambda item: item[0].shape[0]) if over else None


def _super_digit(mask):
    """위 첨자 모양이 2인지 3인지. 말할 수 없으면 None."""
    height, width = mask.shape
    if height < SHAPE_MIN_ROWS or width < 2:
        return None
    row = mask[round(SHAPE_ROW * (height - 1))]
    columns = np.flatnonzero(row)
    if columns.size == 0:
        return None
    place = float(columns.mean()) / (width - 1)
    return "2" if place <= SHAPE_LEFT else "3" if place >= SHAPE_RIGHT else None


def _row_runs(row, low):
    edges = np.flatnonzero(np.diff(np.r_[0, row.astype(np.int8), 0]))
    return [(low + int(a), low + int(b)) for a, b in zip(edges[::2], edges[1::2])]


def _meter_body(ink, x, reach):
    """x 둘레에서 아래 행부터 올라가며 간격이 고른 줄기 셋을 찾는다. (줄기 셋, 바닥 행)이나 None. 이웃 글자의 꼬리('g')는 바닥선 아래로 내려간다."""
    low, high = max(0, x - reach), min(ink.shape[1], x + reach + 1)
    for row in range(ink.shape[0] - 1, -1, -1):
        three = _meter_stems(_row_runs(ink[row, low:high], low), x)
        if three is not None and abs((three[0][0] + three[2][1]) / 2 - x) <= reach:
            return three, row
    return None


def _meter_stems(stems, x):
    """x에 가장 가까운, 간격이 고른 이웃한 줄기 셋. 없으면 None."""
    even = [stems[k:k + 3] for k in range(len(stems) - 2)
            if abs((stems[k + 1][0] - stems[k][0]) - (stems[k + 2][0] - stems[k + 1][0])) <= STEM_EVEN]
    return min(even, key=lambda three: abs((three[0][0] + three[2][1]) / 2 - x)) if even else None


def _superscript(ink, thin, x, box_height, limit):
    """x의 m 오른쪽 위에 놓인 작은 숫자의 픽셀. 없으면 None. 작은 글씨에서는 m에 붙거나 조각나서 덩어리로 찾을 수 없다.

    m의 첫 줄기로 x-높이를 잡는다. 그보다 위에 있는 픽셀은 m의 것이 아니다."""
    body = _meter_body(ink, x, max(4, int(BODY_REACH * box_height)))
    if body is None:
        return None
    three, bottom = body
    (first, _), (second, _), (_, right) = three
    top = bottom
    while top > 0 and ink[top - 1, first:three[0][1]].any():
        top -= 1
    height = bottom - top + 1
    if height < 4 or right - first > 2.2 * height:
        return None
    end = min(limit, right + int(SUPER_GAP * height) + 2)      # limit: 뒤 글자가 시작하는 열
    above = thin[:top, second:end]
    rows = np.flatnonzero(above.any(axis=1))
    if rows.size == 0:
        return None
    columns = np.flatnonzero(above.any(axis=0))
    start, stop = second + int(columns[0]), second + int(columns[-1]) + 1
    if _reaches_down(ink, top, bottom, start, stop, right):
        return None
    first_row, left = int(rows[0]), max(start, right)
    last_row = top       # 위 첨자 아래쪽은 m 윗줄보다 내려오기도 한다. m 오른쪽 열에서 글자가 이어지는 동안 내려간다
    while left < stop and last_row < bottom and thin[last_row + 1, left:stop].any():
        last_row += 1
    shape = thin[first_row:last_row + 1, start:stop].copy()
    shape[top - first_row:, :max(0, left - start)] = False     # m 윗줄 높이부터는 m의 몸통이 섞인다
    filled = np.flatnonzero(shape.any(axis=1))
    shape = shape[:int(filled[-1]) + 1] if filled.size else shape
    return shape if shape.shape[0] >= MIN_MARK_ROWS + 1 and shape.shape[0] <= height else None


def _reaches_down(ink, top, bottom, start, stop, right):
    """위쪽 픽셀이 m 오른쪽의 키 큰 글자('/')에서 온 것인가. 그런 글자는 아래쪽이 m 오른쪽에 있다."""
    middle = top + (bottom - top) // 2
    for column in range(start, stop):
        for glyph, glyph_top, glyph_bottom, left in components(ink, column, 0):
            if glyph_top < top and glyph_bottom >= middle and glyph[:top - glyph_top, column - left].any():
                low = np.flatnonzero(glyph[middle - glyph_top:].any(axis=0))
                if low.size and left + int(low[0]) > right:
                    return True
    return False


def _has_ring(ink, x, box_height):
    """x의 C 왼쪽 위에 작은 고리가 있는가."""
    found = list(components(ink, x, max(4, int(REACH * box_height))))
    letter = _glyph_at(found, x)
    if letter is None:
        return False
    glyph, top, _, left = letter
    height = glyph.shape[0]
    return any(item is not letter and item[2] <= top + RING_BOTTOM * height and MIN_MARK_ROWS <= item[0].shape[0] <= RING_MAX_HEIGHT * height
               and left - RING_REACH * height <= item[3] + item[0].shape[1] <= left + 1 for item in found)


def _likely_digit(before, follow):
    """모양을 말할 수 없을 때의 짐작. 확인 필요로 표시한다. ㎍/㎥ 같은 농도와 ㎥/초 같은 유량은 세제곱이다."""
    return "3" if before == "/" or follow == "/" else "2"


def _letter(char):
    return char.isascii() and char.isalpha()


def _meter_units(read, ink, thin, box_height, per_step, width):
    """[(앞 번호, 뒤 번호, 글자, 확인 필요)] 바꿀 자리를 찾는다."""
    changes = []
    for index, (char, center) in enumerate(read):
        if char != "m":
            continue
        kilo = index > 0 and read[index - 1][0] == "k"
        first = index - 1 if kilo else index
        before = read[first - 1][0] if first else ""
        if _letter(before):     # cm, mm, nm 와 낱말 안의 m 은 건드리지 않는다
            continue
        follow = read[index + 1][0] if index + 1 < len(read) else ""
        extra = bool(follow) and follow in SUPER_READS and not (index + 2 < len(read) and _letter(read[index + 2][0]))
        if _letter(follow) and not extra:
            continue
        limit = int(read[index + 1][1] * per_step) if follow and not extra else width
        mask = _superscript(ink, thin, min(width - 1, max(0, int(center * per_step))), box_height, limit)
        if mask is None:
            continue
        digit = _super_digit(mask)
        hint = {"²": "2", "³": "3"}.get(follow, follow if follow in ("2", "3") else None) if extra else None
        symbol = {"2": (SQUARE, SQUARE_KM), "3": (CUBE, CUBE_KM)}[digit or hint or _likely_digit(before, follow)][kilo]
        changes.append((first, index + 1 if extra else index, symbol, digit is None))
    return changes


def _celsius(read, ink, box_height, per_step, width):
    changes = []
    for index, (char, center) in enumerate(read):
        if char not in "Cc" or (index + 1 < len(read) and _letter(read[index + 1][0])):
            continue
        ring = index > 0 and read[index - 1][0] in ROUND_READS
        start = index - 1 if ring else index
        before = read[start - 1][0] if start else ""
        if before and not (before.isdigit() or before in "(["):    # 수 뒤나 괄호 안, 상자 맨 앞에서만 온도다
            continue
        seen = _has_ring(ink, min(width - 1, max(0, int(center * per_step))), box_height)
        if seen or (ring and read[index - 1][0] == "°"):
            changes.append((start, index, CELSIUS, False))
    return changes


def restore_units(pieces, crop, steps, width):
    """화면 모양이 ㎡ ㎥ ㎢ ℃ 인 자리를 바꾼다. (글자 목록, 확인이 필요한 CTC 위치)를 돌려주며 바꿀 것이 없으면 받은 목록 그대로다."""
    read = [piece for piece in pieces if piece[0] != " "]
    if width <= 0 or not any(char in "mCc" for char, _ in read):
        return pieces, ()
    ink = ink_mask(crop)
    if not ink.any():
        return pieces, ()
    per_step = width / steps
    box_height = crop.shape[0]
    changes = _meter_units(read, ink, ink_mask(crop, THIN_INK_FRACTION), box_height, per_step, width) + _celsius(read, ink, box_height, per_step, width)
    if not changes:
        return pieces, ()
    drop, put, doubtful = set(), {}, []
    for start, end, symbol, unsure in changes:
        put[read[start][1]] = symbol
        drop.update(read[at][1] for at in range(start, end + 1) if at != start)
        if unsure:
            doubtful.append(read[start][1])
    out = [(put.get(center, char), center) for char, center in pieces if center not in drop or char == " "]
    return out, tuple(doubtful)
