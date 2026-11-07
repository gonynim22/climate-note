"""모델이 놓친 문장 부호와 작은 표시를 되살린다. Qt를 쓰지 않고 numpy만 쓴다.

네 가지다. (1) 모델이 blank로 넘긴 단계에도 문장 부호의 확률이 충분하면 그 부호를 낸다(모델 자신의 판단이다). (2) 큰따옴표로
읽힌 작은 덩어리의 모양이 별표면 '*'로 바꾸고 건너뛴 별표를 넣는다. (3) 숫자로 읽힌 글자를 고리가 둘러싸고 있으면 원문자로
바꾼다. (4) 대문자 뒤의 가는 세로획을 'I'로 넣는다. 화면에 있는 모양과 모델의 확률만 읽고 글자를 추정하지 않는다.
계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import numpy as np

from screen_text.corner_brackets import components
from screen_text.leading_symbols import ink_mask

RESCUE_MARKS = "()[],.:·'*%-"   # 모델이 blank에 묻어 버리기 쉬운 부호
RESCUE_MIN = 0.3                # blank 뒤에 이 확률 이상 남아 있어야 낸다
CIRCLED = dict(zip("123456789", "①②③④⑤⑥⑦⑧⑨"))
RING_MIN_HEIGHT = 0.6           # 고리 높이의 하한(줄 글자 높이 대비)
RING_ASPECT = (0.75, 1.35)
RING_MAX_CORE = 0.12            # 고리 덩어리의 가운데는 비어 있다(숫자는 고리와 떨어진 다른 덩어리다)
RING_MIN_INSIDE = 0.12          # 고리 안쪽 칸에 든 글자 픽셀의 하한(가운데 칸 대비). 'G' 옆 '5'처럼 빈 고리를 거른다
RING_MAX_TIPS = 0.5             # 네 꼭짓점 칸이 차 있으면 네모다
TIP_SIZE = 0.1
THIN_MIN_ROOM = 0.7             # 대문자와 다음 글자가 줄 글자 높이의 이만큼 떨어져야 그 사이를 본다
THIN_LEFT_ROOM = 0.3            # 왼쪽 대문자 몫
THIN_RIGHT_ROOM = 0.2           # 오른쪽 글자 몫
THIN_MIN_HEIGHT = 0.7           # 세로획 높이의 하한(줄 글자 높이 대비)
THIN_MAX_WIDTH = 0.2            # 세로획 폭의 상한
THIN_MIN_FILL = 0.8
STAR_QUOTES = frozenset('"\'^`´“”‘’')
STAR_MAX_HEIGHT = 0.5           # 별표 높이의 상한(줄 글자 높이 대비)
STAR_MIN_HEIGHT = 0.2
STAR_ASPECT = (0.9, 1.45)
STAR_FILL = (0.4, 0.82)         # 팔이 있어 네모처럼 꽉 차지 않고, 가운데는 찬다
STAR_MIN_CORE = 0.6
STAR_MAX_TOP = 0.4              # 덩어리 위끝이 줄 위에서 이 비율 안에 있어야 위첨자 자리다
STAR_SKIP_GAP = 1.15            # 이웃한 CTC 글자가 줄 글자 높이의 이만큼 떨어져야 건너뛴 자리로 본다
STAR_LEFT_ROOM = 0.45           # 왼쪽 글자 몫(줄 글자 높이 대비)
STAR_RIGHT_ROOM = 0.35          # 오른쪽 글자 몫


def rescue_marks(pieces, probabilities, charset):
    """blank로 넘어간 단계의 문장 부호를 [(글자, 중심 단계)]에 끼워 넣는다. 없으면 받은 목록을 그대로 돌려준다."""
    classes = _rescue_classes(charset)
    if not classes.size or not pieces:  # 아무 글자도 읽지 못한 상자의 부호는 대부분 글자 조각이다('('). 맞은 것 20, 없는 글자 65
        return pieces
    best = probabilities.argmax(axis=1)
    marks = probabilities[:, classes]
    strongest = marks.max(axis=1)
    found = []
    steps = np.flatnonzero((best == 0) & (strongest >= RESCUE_MIN))
    for run in np.split(steps, np.flatnonzero(np.diff(steps) > 1) + 1) if steps.size else ():
        step = int(run[strongest[run].argmax()])
        klass = int(classes[marks[step].argmax()])
        if (step and best[step - 1] == klass) or (step + 1 < best.size and best[step + 1] == klass):
            continue    # 바로 옆 단계에서 모델이 이미 낸 글자다
        found.append((charset[klass - 1], float(step)))
    return sorted(pieces + found, key=lambda piece: piece[1]) if found else pieces


_RESCUE_CACHE = {}


def _rescue_classes(charset):
    key = id(charset)
    if key not in _RESCUE_CACHE:
        lookup = {char: index + 1 for index, char in enumerate(charset)}
        _RESCUE_CACHE[key] = np.array([lookup[char] for char in RESCUE_MARKS if char in lookup], dtype=np.int64)
    return _RESCUE_CACHE[key]


def _line_span(ink):
    rows = np.flatnonzero(ink.any(axis=1))
    return (int(rows[0]), int(rows[-1])) if rows.size else None


def _ring_inside(ink, glyph, top, left, line_height):
    """덩어리가 고리이고 그 안에 다른 글자 픽셀이 있는가."""
    height, width = glyph.shape
    if height < 6 or width < 6 or height < RING_MIN_HEIGHT * line_height or not RING_ASPECT[0] <= width / height <= RING_ASPECT[1]:
        return False
    y0, y1, x0, x1 = int(height * .3), int(height * .7), int(width * .3), int(width * .7)
    if glyph[y0:y1, x0:x1].mean() > RING_MAX_CORE:
        return False
    tip_h, tip_w = max(1, round(height * TIP_SIZE)), max(1, round(width * TIP_SIZE))
    tips = np.mean([glyph[:tip_h, :tip_w].any(), glyph[:tip_h, -tip_w:].any(), glyph[-tip_h:, :tip_w].any(), glyph[-tip_h:, -tip_w:].any()])
    if tips > RING_MAX_TIPS:
        return False
    return ink[top + y0:top + y1, left + x0:left + x1].mean() >= RING_MIN_INSIDE


def restore_circled_digits(pieces, crop, steps, width):
    """숫자로 읽힌 글자를 고리가 둘러싸고 있으면 원문자로 바꾼다. 없으면 받은 목록을 그대로 돌려준다."""
    if width <= 0 or not any(char in CIRCLED for char, _ in pieces):
        return pieces
    ink = ink_mask(crop)
    span = _line_span(ink)
    if span is None:
        return pieces
    line_height = span[1] - span[0] + 1
    out = list(pieces)
    per_step = width / steps
    for index, (char, center) in enumerate(pieces):
        if char not in CIRCLED:
            continue
        neighbors = "".join(pieces[k][0] for k in (index - 1, index + 1) if 0 <= k < len(pieces))
        if any(other.isdigit() for other in neighbors):   # 여러 자리 수는 원문자가 아니다
            continue
        x = min(width - 1, max(0, int(center * per_step)))
        for glyph, top, _, left in components(ink, x, max(2, line_height // 2)):
            if left <= x <= left + glyph.shape[1] - 1 and _ring_inside(ink, glyph, top, left, line_height):
                out[index] = (CIRCLED[char], center)
                break
    return out


def _is_star(glyph, top, span):
    """덩어리가 위첨자 자리의 별표 모양인가. 두 개가 붙은 '**'는 폭이 두 배다."""
    line_top, line_bottom = span
    line_height = line_bottom - line_top + 1
    height, width = glyph.shape
    if (top - line_top > STAR_MAX_TOP * line_height or not STAR_MIN_HEIGHT * line_height <= height <= STAR_MAX_HEIGHT * line_height
            or height < 4 or not STAR_FILL[0] <= glyph.mean() <= STAR_FILL[1]):
        return 0
    if STAR_ASPECT[0] <= width / height <= STAR_ASPECT[1]:
        count = 1
    elif 2 * STAR_ASPECT[0] <= width / height <= 2 * STAR_ASPECT[1]:
        count = 2
    else:
        return 0
    one = glyph[:, :width // count]
    y0, x0 = int(height * .3), int(one.shape[1] * .3)
    core = one[y0:max(y0 + 1, int(height * .7)), x0:max(x0 + 1, int(one.shape[1] * .7))]
    return count if core.mean() >= STAR_MIN_CORE else 0


def _star_near(ink, x, span):
    """x 가까이의 덩어리가 별표면 그 개수, 아니면 0."""
    line_height = span[1] - span[0] + 1
    reach = max(2, int(.6 * line_height))
    near = [(abs(left + glyph.shape[1] / 2 - x), glyph, top) for glyph, top, _, left in components(ink, x, reach)
            if glyph.shape[0] <= .7 * line_height and top - span[0] <= STAR_MAX_TOP * line_height and glyph.size >= 9]
    if not near:
        return 0
    near.sort(key=lambda item: item[0])
    _, glyph, top = near[0]
    if len(near) > 1 and abs(near[1][2] - top) <= max(1, .15 * line_height) and abs(near[1][1].shape[0] - glyph.shape[0]) <= max(2, .4 * glyph.shape[0])             and near[1][0] <= 1.5 * line_height * STAR_MAX_HEIGHT:
        return 0    # 나란한 둘째 획: 큰따옴표다
    return _is_star(glyph, top, span)


def _skipped_stars(ink, xs, span):
    """이웃한 CTC 글자가 벌어진 자리에서 모델이 건너뛴 별표의 (개수, 가운데 x) 목록."""
    line_height = span[1] - span[0] + 1
    found = []
    for low, high in zip(xs, xs[1:]):
        if high - low < STAR_SKIP_GAP * line_height:
            continue
        inner_low, inner_high = low + STAR_LEFT_ROOM * line_height, high - STAR_RIGHT_ROOM * line_height
        middle = int((low + high) / 2)
        for glyph, top, _, left in components(ink, middle, int((high - low) / 2)):
            if inner_low <= left and left + glyph.shape[1] - 1 <= inner_high:
                count = _is_star(glyph, top, span)
                if count:
                    found.append((count, left + glyph.shape[1] / 2))
    return found


def restore_stars(pieces, crop, steps, width):
    """따옴표로 읽힌 글자의 화면 모양이 별표면 '*'로 바꾸고, 건너뛴 별표를 끼워 넣는다. 없으면 받은 목록을 그대로 돌려준다."""
    if width <= 0:
        return pieces
    ink = ink_mask(crop)
    span = _line_span(ink)
    if span is None:
        return pieces
    per_step = width / steps
    out, changed = [], False
    for index, (char, center) in enumerate(pieces):
        following = next((other for other, _ in pieces[index + 1:] if other != " "), "")
        is_quote = char in STAR_QUOTES and not (char in "'‘’`´" and following.isdigit())  # '25 의 따옴표
        count = _star_near(ink, min(width - 1, max(0, int(center * per_step))), span) if is_quote else 0
        changed = changed or count > 0
        out.extend([("*", center + k * .01) for k in range(count)] or [(char, center)])
    for count, x in _skipped_stars(ink, [center * per_step for char, center in pieces if char != " "], span):
        out.extend(("*", x / per_step + k * .01) for k in range(count))
        changed = True
    return sorted(out, key=lambda piece: piece[1]) if changed else pieces


def restore_thin_capitals(pieces, crop, steps, width):
    """대문자 뒤에서 모델이 건너뛴 가는 세로획을 'I'로 넣는다('AI'가 'A'로 읽히곤 한다). 없으면 받은 목록을 그대로 돌려준다."""
    if width <= 0 or not any(char.isascii() and char.isupper() for char, _ in pieces):
        return pieces
    ink = ink_mask(crop)
    span = _line_span(ink)
    if span is None:
        return pieces
    line_height = span[1] - span[0] + 1
    per_step = width / steps
    read = [(char, center * per_step, center) for char, center in pieces if char != " "]
    found = []
    for (left_char, left_x, left_step), (_, right_x, right_step) in zip(read, read[1:] + [("", float(width), steps)]):
        if not (left_char.isascii() and left_char.isupper()) or right_x - left_x < THIN_MIN_ROOM * line_height:
            continue
        low, high = left_x + THIN_LEFT_ROOM * line_height, right_x - THIN_RIGHT_ROOM * line_height
        for glyph, top, bottom, column in components(ink, int((left_x + right_x) / 2), int((right_x - left_x) / 2)):
            middle = column + glyph.shape[1] / 2
            if (low <= middle <= high and glyph.shape[0] >= THIN_MIN_HEIGHT * line_height and glyph.shape[1] <= max(2, THIN_MAX_WIDTH * line_height)
                    and glyph.mean() >= THIN_MIN_FILL):
                found.append(("I", middle / per_step))
                break
    return sorted(pieces + found, key=lambda piece: piece[1]) if found else pieces
