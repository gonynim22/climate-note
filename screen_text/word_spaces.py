"""글자 사이에 공백을 넣을지 정한다. Qt를 쓰지 않고 numpy만 쓴다.

인식 모델은 단계마다 공백 클래스의 확률도 낸다. 한글 사이에서는 이 확률이 단어 경계를 거의 그대로 가르지만, 좁게
조판한 문서에서는 낮게 나오고 문장 부호 옆에서는 흔들린다. 화면의 틈은 좁은 조판에서도 보이지만 자간이 넓은 글꼴
(돋움·굴림)에서는 음절 사이도 넓고 숫자 1 옆도 넓다. 그래서 둘을 더한 점수로 정한다. 글자는 바꾸지 않고 공백만
넣는다. 가중치는 실제 화면 글자·공문서 PDF에서 맞췄고 근거는 docs/SCREEN_TEXT.md를 따른다.
"""
import numpy as np

from screen_text.leading_symbols import ink_mask

LONG_STROKE = 2.5          # 글자 높이의 이 배수 이상 이어지는 가로 획은 밑줄·표 선이다. 빈 열을 이어 공백을 가린다
PROBABILITY_FLOOR = 1e-4   # 공백 확률의 하한(로그가 끝없이 작아지지 않게)
RELATIVE_CAP = 2.0         # 모델이 낸 공백의 틈에 견준 비율의 상한
WEIGHT_PROBABILITY = 0.944
WEIGHT_GAP = 7.619
WEIGHT_RELATIVE = 5.13
NO_MODEL_SPACE = -1.51     # 줄에 모델이 낸 공백이 없으면 틈의 자를 잃는다
INSIDE_NUMBER = -1.82      # 1,234 와 2.5 의 안쪽
NUMBER_GAP = 0.5           # 이만큼 벌어지면 수가 아니라 '1. 2026년'이다(글자 높이 대비). 실측 붙음 0.3 이하, 떨어짐 0.5 이상
AFTER_STOP = 3.19          # 낱말 뒤 마침표·쉼표 다음(모델 확률이 낮아도 '가. 목적'은 공백이다)
# 숫자는 틈보다 가운데 거리가 정확하다. '1'은 칸 가운데에 좁게 놓여 틈이 넓어 보여도 가운데 거리는 다른 숫자와 같다
# 실측(글꼴 24종·배율 4가지·2만여 쌍, 숫자 높이 대비): 같은 수 0.94 이하, 다른 수 0.93 이상. 자간을 벌린 문서가 있어 붙이는 쪽으로만 쓴다
DIGITS_TOGETHER = 0.85     # 이웃한 숫자의 가운데 거리가 이 미만이면 같은 수다
DIGIT_JITTER = 1.22        # 같은 상자의 숫자 간격보다 이 배수 안이면 같은 수다. 한글은 배율에 따라 글자 자리가 1px씩 흔들린다(공백이 끼면 1.3배 이상)
DIGIT_CELL = 0.95          # 숫자 간격이 숫자 높이의 이 배수를 넘으면 그 상자의 숫자는 모두 띄어 쓴 것이라 자로 쓰지 않는다
MARK_TOGETHER = 0.75       # 숫자 사이 '.' ','에서 뒤 숫자까지의 가운데 거리. 같은 수 0.78 이하, 다른 수 0.74 이상
MARK_WIDTH = 0.5           # 구두점만 든 묶음의 폭 상한(숫자 높이 대비). 넓으면 앞 숫자와 붙은 묶음이라 가운데를 잴 수 없다
# 글자 종류별 치우침. 여는 괄호 뒤·닫는 문장 부호 앞은 공백이 드물고, 숫자·기호 뒤는 잦다
AFTER = {"h": 0.39, "n": -0.14, "d": 1.79, "a": 0.74, "c": 0.53, "o": -1.0, "m": 2.72, "q": -1.41, "s": 1.58, "p": -1.89}
BEFORE = {"h": 0.78, "n": 0.58, "d": 1.3, "a": 0.86, "c": -0.16, "o": 0.34, "m": 0.72, "q": 0.65, "s": 0.81, "p": -1.31}
CLOSERS = frozenset(",.:;)]}」』>%”’!?")
OPENERS = frozenset("([{「『<“‘")
DOTS = frozenset("·‧ㆍ․･・")
JOINERS = frozenset("-~∼～/+=×&_|")
NUMBER_MARKS = frozenset("'‘’`´△▲▽▼")   # '25 의 앞 따옴표와 △1.2 의 증감 표시는 뒤 숫자와 붙는다
QUOTES = frozenset("'\"`´")
NARROW = frozenset("1Iil")


def _ink_runs(column):
    """글자 있는 열의 묶음 [(시작, 끝)]."""
    edges = np.flatnonzero(np.diff(np.r_[0, column.astype(np.int8), 0]))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


def _run_at(runs, x):
    """x에 가장 가까운 묶음의 번호."""
    return min(range(len(runs)), key=lambda k: max(runs[k][0] - x, x - runs[k][1] + 1, 0))


def _height(ink, run):
    rows = np.flatnonzero(ink[:, run[0]:run[1]].any(axis=1))
    return int(rows[-1] - rows[0] + 1) if rows.size else 0


def _spread(ink, runs, left_x, right_x, mark=False):
    """이웃한 두 글자의 가운데 거리(뒤 숫자 높이 대비). 글자가 붙어 묶음 하나가 되었거나 사이에 다른 묶음이 있으면 0이다."""
    if not runs:    # 긴 획을 빼면 아무것도 남지 않는 줄
        return 0.0
    right = _run_at(runs, right_x)
    left = right - 1 if mark else _run_at(runs, left_x)    # 작은 구두점은 읽은 자리가 숫자 쪽으로 밀린다
    if left < 0 or right != left + 1:
        return 0.0
    height = max(_height(ink, runs[right]), 1)
    left_width, right_width = runs[left][1] - runs[left][0], runs[right][1] - runs[right][0]
    if max(left_width, right_width) > height or (mark and left_width > MARK_WIDTH * height):    # 붙은 숫자 둘은 가운데가 칸의 경계다
        return 0.0
    return (sum(runs[right]) - sum(runs[left])) / 2 / height


def _digit_advance(read, runs, ink, per_step):
    """같은 상자에서 이웃한 숫자의 가운데 거리 중앙값(숫자 높이 대비). 숫자 쌍이 둘 미만이면 0."""
    spreads = []
    for (left, a), (right, b) in zip(read, read[1:]):
        if left.isdigit() and right.isdigit():
            spread = _spread(ink, runs, a * per_step, b * per_step)
            if spread:
                spreads.append(spread)
    return float(np.median(spreads)) if len(spreads) >= 2 else 0.0


def glyph_kind(char):
    """h 한글, n 좁은 글자, d 숫자, a 영문, c 닫는 부호, o 여는 부호, p 가운뎃점, m 잇는 부호, q 따옴표, s 그 밖의 기호."""
    if "가" <= char <= "힣":
        return "h"
    if char in NARROW:
        return "n"
    if char.isdigit() or "Ⅰ" <= char <= "Ⅹ":   # 로마 숫자도 번호라 '-' '.' 와 붙는다
        return "d"
    if char.isascii() and char.isalpha():
        return "a"
    if char in CLOSERS:
        return "c"
    if char in OPENERS:
        return "o"
    if char in DOTS:
        return "p"
    if char in JOINERS:
        return "m"
    return "q" if char in QUOTES else "s"


def without_long_strokes(ink, height):
    """글자 높이보다 훨씬 긴 가로 획(밑줄·표 선)을 뺀 글자 픽셀. 남겨 두면 단어 사이의 빈 열이 사라진다."""
    limit = int(LONG_STROKE * height)
    out = ink.copy()
    for row in np.flatnonzero(ink.sum(axis=1) >= limit):
        edges = np.flatnonzero(np.diff(np.r_[0, ink[row].astype(np.int8), 0]))
        for start, end in zip(edges[::2], edges[1::2]):
            if end - start >= limit:
                out[row, start:end] = False
    return out


def _longest_empty(column):
    """열들에서 글자 없는 구간의 최대 길이."""
    filled = np.flatnonzero(column)
    if filled.size == 0:
        return column.size
    inner = int((np.diff(filled) - 1).max()) if filled.size > 1 else 0
    return max(int(filled[0]), column.size - 1 - int(filled[-1]), inner)


def _after_stop(left, right, before):
    if left == "." and before.isascii() and before.isalnum() and right.isascii() and right.islower():
        return False    # www.me.go.kr 의 안쪽
    return left in ".,:;" and glyph_kind(right) in "hoas" and not before.isdigit()


def _inside_number(left, right, before, after):
    return (left in ",.:" and right.isdigit() and before.isdigit()) or (right in ",.:" and left.isdigit() and after.isdigit())


def _thousands(read, index):
    """index번 쉼표가 1,234 의 자릿수 쉼표인가. 뒤에 숫자가 정확히 셋이다."""
    digits = "".join(char for char, _ in read[index + 1:index + 5])
    return read[index][0] == "," and index > 0 and read[index - 1][0].isdigit() and digits[:3].isdigit() and len(digits) >= 3 and not digits[3:4].isdigit()


def join_words(pieces, space_probabilities, crop, steps, width):
    """[(글자, CTC 위치)]를 공백을 넣은 문자열로 잇는다. space_probabilities는 단계별 공백 확률이다."""
    read = [(char, center) for char, center in pieces if char != " "]
    as_read = "".join(char for char, _ in pieces)
    if len(read) < 2 or width <= 0:
        return as_read
    ink = ink_mask(crop)
    rows = np.flatnonzero(ink.any(axis=1))
    if rows.size == 0:
        return as_read
    height = int(rows[-1] - rows[0] + 1)
    clear = without_long_strokes(ink, height)
    column = clear.any(axis=0)
    runs = _ink_runs(column)
    per_step = width / steps
    advance = _digit_advance(read, runs, clear, per_step)
    if advance > DIGIT_CELL:
        advance = 0.0
    spaced = [center for char, center in pieces if char == " "]
    gaps, gave_space = [], []
    for (_, a), (_, b) in zip(read, read[1:]):
        gaps.append(_longest_empty(column[int(a * per_step):int(b * per_step) + 1]))
        gave_space.append(any(a <= center <= b for center in spaced))
    hangul = [gap for gap, given, (x, _), (y, _) in zip(gaps, gave_space, read, read[1:]) if given and glyph_kind(x) == glyph_kind(y) == "h"]
    given = hangul or [gap for gap, given in zip(gaps, gave_space) if given]
    reference = float(np.median(given)) if given else 0.0
    out = [read[0][0]]
    for index, gap in enumerate(gaps):
        left, right = read[index][0], read[index + 1][0]
        first, last = int(read[index][1]), int(read[index + 1][1]) + 1
        probability = float(space_probabilities[first:last + 1].max()) if last >= first else 0.0
        score = (WEIGHT_PROBABILITY * np.log(probability + PROBABILITY_FLOOR) + WEIGHT_GAP * gap / height
                 + AFTER[glyph_kind(left)] + BEFORE[glyph_kind(right)])
        score += WEIGHT_RELATIVE * (min(gap / reference, RELATIVE_CAP) - 1) if reference > 0 else NO_MODEL_SPACE
        before = read[index - 1][0] if index else ""
        after = read[index + 2][0] if index + 2 < len(read) else ""
        mark = left in ",." and before.isdigit() and right.isdigit()
        spread = _spread(clear, runs, read[index][1] * per_step, read[index + 1][1] * per_step, mark) if mark or (left.isdigit() and right.isdigit()) else 0.0
        if spread and (spread < max(DIGITS_TOGETHER, DIGIT_JITTER * advance) if left.isdigit() else spread < MARK_TOGETHER):
            score = -1.0
        elif "Ⅰ" <= left <= "Ⅹ" and right in ".-)":
            score = -1.0
        elif left.isdigit() and right in ",." and after.isdigit():   # 굴림·돋움의 마침표는 칸 가운데라 앞 숫자와도 벌어진다
            score = -1.0
        elif _thousands(read, index) or (right == "," and _thousands(read, index + 1)):  # 굴림·돋움의 쉼표는 칸 가운데라 틈이 넓다
            score = -1.0
        elif _inside_number(left, right, before, after):  # '1.5'는 붙고 '1. 2026년'은 떨어진다
            score = 1.0 if gap >= NUMBER_GAP * height else score + INSIDE_NUMBER
        if _after_stop(left, right, before):
            score += AFTER_STOP
        if score > 0 and not (left in NUMBER_MARKS and right.isdigit()):
            out.append(" ")
        out.append(right)
    return "".join(out)
