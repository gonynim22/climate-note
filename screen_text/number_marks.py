"""숫자 안의 쉼표와 마침표를 화면 모양으로 가른다. Qt를 쓰지 않고 numpy만 쓴다.

작은 글씨에서 모델이 2.6 을 2,6 으로, 4,100 을 4.100 으로 읽는다(굴림 12px 소수점의 60%). 수가 조용히 바뀌는 오독이라
화면을 다시 본다. 쉼표는 숫자 바닥선 아래로 내려오거나 왼쪽 아래로 기울고 마침표는 그렇지 않다. 쉼표로 보이는 모양은
글꼴 전체(약 12,000칸)에서 마침표였던 적이 없지만, 마침표로 보이는 모양은 일부 글꼴(HY신명조)의 쉼표와 같다. 그래서
글자 배열이 쉼표일 수 없을 때만 마침표로 바꾸고, 3,852 처럼 글자로 판단할 수 없는 자리는 그대로 두고 확인 필요로 표시한다.
계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import numpy as np

from screen_text.corner_brackets import components
from screen_text.leading_symbols import THIN_INK_FRACTION, ink_mask
from screen_text.word_spaces import _height, _ink_runs, _longest_empty, _run_at, without_long_strokes

MARKS = ",."
TICK = "tick"          # 모양이 말하는 글자: 작은 글씨의 곧은 세로 2화소(실측 마침표 85%)
BELOW = 0.5            # 상자 아래로 볼 거리(상자 높이 대비). 상자는 숫자 바닥선에서 끝나기도 해 쉼표 꼬리가 그 아래에 있다
TALL = 0.6             # 숫자 덩어리의 높이 하한(가장 높은 덩어리 대비)
REACH = 1.6            # 구두점 양옆의 숫자를 찾는 거리(상자 높이 대비)
DIGITS_APART = 0.95    # 숫자 가운데 거리가 이 이상이어야 사이에 구두점이 들어갈 자리가 있다(숫자 높이 대비, 수 안의 이웃 숫자는 0.94 이하)
DIGIT_BREAK = 0.33     # 이웃한 숫자의 틈이 줄 글자 높이의 이 비율 이상이면 다른 수다(실측 같은 수 0.23 이하, 다른 수 0.36 이상)
NEAR = 0.6             # 구두점 덩어리 가운데가 읽은 자리에서 떨어져도 되는 거리(숫자 높이 대비)
LOW_PART = 0.5         # 구두점 아래 끝은 숫자 아래쪽 이 비율 안에 있다(가운뎃점·위 점을 거른다)
COMMA_DROP = 0.14      # 바닥선 아래로 숫자 높이의 이 비율 넘게 내려오면 쉼표다
COMMA_MIN_DROP = 2
COMMA_LEAN = 0.35      # 윗줄이 아랫줄보다 이 화소만큼 오른쪽이면 기운 꼬리다(실측 쉼표 0.38 이상, 큰 글자의 1화소 넘침은 0.31 이하)
TICK_LEAN = 0.3        # 곧은 세로 획의 기울기 상한
TICK_MIN_DIGIT = 10    # 굴림 12px 비트맵의 마침표는 바닥선 아래로 1화소 내려온 세로 2화소다. 이보다 작은 글씨에서는 쉼표와 모양이 같다
LOW_COLUMN = 0.35      # 구두점 열의 글자 픽셀은 바닥선에서 숫자 높이의 이 비율 안에 있다
MAX_MARK_WIDTH = 0.4   # 구두점 폭의 상한(숫자 높이 대비)
MARK_MIN_DARK = 0.6    # 건너뛴 구두점은 가장 진한 글자 픽셀의 이만큼 진해야 한다(티끌을 거른다)
PERIOD_HEIGHT = 0.25   # 마침표 높이의 상한(숫자 높이 대비)


def _lean(level):
    """맨 윗줄 무게중심이 맨 아랫줄보다 오른쪽으로 간 화소 수."""
    columns = np.arange(level.shape[1])

    def center(row):
        return float((row * columns).sum() / max(float(row.sum()), 1e-6))
    return center(level[0]) - center(level[-1])


def _shape(level, drop, digit_height):
    """구두점 덩어리의 모양이 말하는 글자. 애매하면 None. TICK은 작은 글씨에서 마침표에 가깝지만 쉼표일 수도 있는 곧은 세로 2화소다."""
    height = level.shape[0]
    lean = _lean(level)
    if drop >= max(COMMA_MIN_DROP, COMMA_DROP * digit_height) or (drop >= 1 and lean >= COMMA_LEAN):
        return ","
    if drop <= 0 and height <= max(2, PERIOD_HEIGHT * digit_height):
        return "."
    if drop == 1 and height <= 2 and abs(lean) < TICK_LEAN:
        return "." if digit_height >= TICK_MIN_DIGIT else TICK
    return None


def _seen_mark(ink, level, x, left_x, right_x, box_height, least=0.0):
    """x 자리의 구두점 모양을 읽는다. left_x·right_x는 양옆 숫자의 자리다. 그 숫자로 바닥선을 잡지 못하면 None.

    least를 주면 건너뛴 구두점을 찾는 것이라 그만큼 진하고 위쪽 열이 빈 덩어리만 본다."""
    found = list(components(ink, x, max(3, int(REACH * box_height))))
    if not found:
        return None
    tallest = max(glyph.shape[0] for glyph, _, _, _ in found)

    def beside(glyph, left):
        return left - 1 <= left_x <= left + glyph.shape[1] or left - 1 <= right_x <= left + glyph.shape[1]
    tall = [(top, bottom) for glyph, top, bottom, left in found if glyph.shape[0] >= TALL * tallest and beside(glyph, left)]
    if not tall:
        return None
    bottom_row = int(np.median([bottom for _, bottom in tall]))
    digit_height = int(np.median([bottom - top + 1 for top, bottom in tall]))
    near = [(abs(left + glyph.shape[1] / 2 - x), glyph, top, bottom, left) for glyph, top, bottom, left in found
            if glyph.shape[0] < TALL * tallest and bottom >= bottom_row - LOW_PART * digit_height and top <= bottom_row + 1]  # 그 아래는 다음 줄이다
    near = [item for item in near if item[0] <= max(2, NEAR * digit_height)]
    if digit_height < 5:
        return None
    if not near:   # 건너뛴 자리에는 쓰지 않는다. 숫자의 받침 획도 바닥선 근처에만 있다
        return None if least else _corner_mark(ink, level, left_x, right_x, bottom_row, digit_height)
    _, glyph, top, bottom, left = min(near, key=lambda item: item[0])
    shape = level[top:bottom + 1, left:left + glyph.shape[1]] * glyph
    if least and (shape.max() < least or ink[bottom_row - digit_height + 1:top, left:left + glyph.shape[1]].any()):
        return None
    return _shape(shape, bottom - bottom_row, digit_height)


def _corner_mark(ink, level, left_x, right_x, bottom_row, digit_height):
    """숫자에 대각선으로 닿아 덩어리로 안 나뉜 구두점. 두 숫자 사이에서 글자 픽셀이 바닥선 근처에만 있는 열을 본다."""
    floor = bottom_row - int(LOW_COLUMN * digit_height)
    rows_of = [np.flatnonzero(ink[:, column]) for column in range(left_x + 1, right_x)]
    columns = [left_x + 1 + k for k, rows in enumerate(rows_of) if rows.size and rows[0] >= floor]
    if not columns or columns[-1] - columns[0] + 1 != len(columns) or len(columns) > MAX_MARK_WIDTH * digit_height:
        return None
    first, last = columns[0], columns[-1] + 1
    rows = np.flatnonzero(ink[:, first:last].any(axis=1))
    digits = [column for column in range(max(0, left_x - digit_height), min(ink.shape[1], right_x + digit_height)) if column < first or column >= last]
    bottoms = [int(np.flatnonzero(ink[:, column])[-1]) for column in digits if ink[:, column].any()]
    baseline = int(np.median(bottoms)) if bottoms else bottom_row
    shape = level[int(rows[0]):int(rows[-1]) + 1, first:last] * ink[int(rows[0]):int(rows[-1]) + 1, first:last]
    return _shape(shape, int(rows[-1]) - min(baseline, bottom_row), digit_height)


def _digits(read, index, step, parted):
    """index 다음(step=1)이나 앞(step=-1)으로 이어지는 숫자 수. parted(앞 글자, 뒤 글자)가 참이면 거기서 다른 수다."""
    count, at = 0, index + step
    while 0 <= at < len(read) and read[at][0].isdigit():
        if count and parted(*sorted((at - step, at))):
            break
        count, at = count + 1, at + step
    return count


def _has_point(read, index):
    """index번 글자가 든 수에 이미 소수점이 있는가."""
    for step in (-1, 1):
        at = index + step
        while 0 <= at < len(read) and (read[at][0].isdigit() or read[at][0] in MARKS):
            if read[at][0] == ".":
                return True
            at += step
    return False


def _room_for_mark(ink, filled, left, right):
    """두 숫자 사이에 좁은 글자 묶음이 하나 있고 가운데 거리가 수 안의 간격보다 벌어져 있는가. 숫자의 끊긴 획은 가운데 거리를 벌리지 않는다."""
    runs = _ink_runs(filled)
    if not runs:
        return False
    first, last = _run_at(runs, left), _run_at(runs, right)
    if last != first + 2:
        return False
    height = max(_height(ink, runs[first]), _height(ink, runs[last]), 1)
    return (sum(runs[last]) - sum(runs[first])) / 2 / height >= DIGITS_APART


def _skipped_marks(read, pairs, ink, level, per_step, width, box_height, parted, filled):
    """이웃한 숫자 사이에서 모델이 건너뛴 구두점. 5.2 가 52 로 읽히면 수가 열 배가 된다. 옅은 티끌과 끊긴 획 조각은 거른다."""
    found = []
    peak = float(level.max())
    for index in pairs:
        left, right = read[index][1] * per_step, read[index + 1][1] * per_step
        if _has_point(read, index) or not _room_for_mark(ink[:box_height], filled, left, right):
            continue
        seen = _seen_mark(ink, level, int((left + right) / 2), min(width - 1, int(left)), min(width - 1, int(right)), box_height, MARK_MIN_DARK * peak)
        before, after = _digits(read, index + 1, -1, parted), _digits(read, index, 1, parted)
        if seen in (".", TICK):
            found.append((".", (read[index][1] + read[index + 1][1]) / 2))
        elif seen == "," and after == 3 and before <= 3 and read[index - before + 1][0] != "0":
            found.append((",", (read[index][1] + read[index + 1][1]) / 2))
    return found


def restore_number_marks(pieces, image, box, steps):
    """숫자 사이의 '.' ','를 화면 모양으로 고친다. (글자 목록, 확인이 필요한 CTC 위치)를 돌려주며 바꿀 것이 없으면 받은 목록 그대로다."""
    x0, y0, x1, y1 = box
    width = x1 - x0
    read = [piece for piece in pieces if piece[0] != " "]
    places = [index for index, (char, _) in enumerate(read) if 0 < index < len(read) - 1 and char in MARKS and read[index - 1][0].isdigit() and read[index + 1][0].isdigit()]
    pairs = [index for index in range(len(read) - 1) if read[index][0].isdigit() and read[index + 1][0].isdigit()]
    if width <= 0 or not (places or pairs):
        return pieces, ()
    box_height = y1 - y0
    crop = image[y0:y1 + max(2, int(BELOW * box_height)), x0:x1]
    ink = ink_mask(crop, THIN_INK_FRACTION)
    if not ink.any():
        return pieces, ()
    gray = crop.astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    level = np.abs(gray - np.median(gray))
    per_step = width / steps
    rows = np.flatnonzero(ink[:box_height].any(axis=1))
    if rows.size == 0:
        return pieces, ()
    line_height = int(rows[-1] - rows[0] + 1)
    filled = without_long_strokes(ink[:box_height], line_height).any(axis=0)

    def parted(left, right):
        """같은 줄의 다음 수로 넘어가는 틈인가. 상자 하나에 1,445 1,545 가 나란히 들어 있다."""
        return _longest_empty(filled[int(read[left][1] * per_step):int(read[right][1] * per_step) + 1]) >= DIGIT_BREAK * line_height
    changed, doubtful = {}, []
    for index in places:
        char, center = read[index]
        seen = _seen_mark(ink, level, *[min(width - 1, max(0, int(read[at][1] * per_step))) for at in (index, index - 1, index + 1)], box_height)
        if seen is None or seen == char or (seen == TICK and char == "."):
            continue
        after, before = _digits(read, index, 1, parted), _digits(read, index, -1, parted)
        leading_zero = before == 1 and read[index - 1][0] == "0"
        if seen in (".", TICK) and (after != 3 or leading_zero):
            changed[center] = "."
        elif seen == "," and after == 3 and before <= 3 and not leading_zero:
            changed[center] = ","
        else:
            doubtful.append(center)
    added = _skipped_marks(read, pairs, ink, level, per_step, width, box_height, parted, filled)
    out = [(changed.get(center, char), center) if char in MARKS else (char, center) for char, center in pieces] if changed else pieces
    if added:
        out = sorted(list(out) + added, key=lambda piece: piece[1])
    return out, tuple(doubtful)
