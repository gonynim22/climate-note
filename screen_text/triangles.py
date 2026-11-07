"""모델이 건너뛰거나 닮은 글자로 읽은 △ ▲ ▽ ▼ ▷ ▶를 화면 모양으로 되살린다. Qt를 쓰지 않고 numpy만 쓴다.

모델 사전에 없는 글자라 그대로 두면 '△32%'가 '32%'로 읽혀 감소가 증가로 바뀐다. 줄 안에서 CTC 글자가 비는 자리나
모델이 닮은 글자로 읽은 자리의 글자 덩어리가 삼각형일 때만 넣거나 바꾼다. 화면 모양을 읽을 뿐 글자를
추정하지 않으며, 그 자리에 모델이 낸 다른 글자가 있으면 건드리지 않는다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import numpy as np

from screen_text.corner_brackets import components
from screen_text.leading_symbols import THIN_INK_FRACTION, ink_mask

HOLLOW = "△"
FILLED = "▲"
TURNED = {HOLLOW: "▽", FILLED: "▼"}     # 위아래로 뒤집힌 삼각형
POINTING = {HOLLOW: "▷", FILLED: "▶"}   # 오른쪽을 가리키는 삼각형
# 모델이 삼각형을 이렇게 읽은 실측. 'A'는 굵은 제목 글씨가 꽉 찬 삼각형처럼 보여 넣으면 안 된다.
# '∆'(U+2206)는 공문서 문자집합에 없어 찾기에 안 걸리고 같은 표에서 △와 섞이므로 언제나 △로 통일한다
LOOK_ALIKES = frozenset("스ㅅ!")
MODEL_TRIANGLE = "∆"
MIN_PIECE_GAP = 1.2        # 이웃한 CTC 글자가 줄 글자 높이의 이만큼 떨어져야 그 사이를 건너뛴 자리로 본다
NEXT_GLYPH = 0.35          # 건너뛴 자리 양 끝에서 이웃 글자 몫으로 빼는 폭(줄 글자 높이 대비)
PREVIOUS_GLYPH = 0.55
MIN_PX = 6                 # 이보다 작으면 모양을 말할 수 없다
MIN_LINE_RATIO = 0.45      # 줄 글자 높이 대비 삼각형 높이의 하한(실측 0.52~0.78)
MIN_ASPECT = 0.85          # 가로/세로. 삼각형은 옆으로 조금 납작하다(실측 1.1~1.3)
MAX_ASPECT = 1.75
APEX_BAND = 0.2            # 꼭짓점을 보는 위쪽 띠(높이 대비)
APEX_WIDTH = 0.4           # 그 띠의 폭 상한(폭 대비)
APEX_OFFSET = 0.25         # 꼭짓점 가운데가 폭 가운데에서 벗어나도 되는 한도(폭 대비). 잘린 쐐기 모양을 거른다
FOOT_WIDTH = 0.7           # 맨 아래 행의 폭 하한(폭 대비). 밑변이 옅어도 두 다리 끝이 벌어져 있다
SLOPE_TOLERANCE = 0.3      # 행 폭이 곧은 빗변의 폭에서 벗어나도 되는 한도(폭 대비)
BODY = (0.3, 0.8)          # 속이 찼는지 보는 행 구간(높이 대비)
SOLID = 0.9                # 모든 행의 채움이 이 이상이면 ▲. 굵은 'A'는 구멍과 다리 사이 때문에 못 미친다
OPEN = 0.75                # 모든 행의 채움이 이 이하면 △. 가로획이 있는 글자는 그 행이 찬다
BASE_FILL = 0.7            # 뒤집히거나 옆을 보는 빈 삼각형의 밑변이 폭을 덮는 비율
MAX_FOREIGN_INK = 0.1      # 덩어리가 차지한 열에 든 다른 글자 픽셀의 상한(덩어리 대비). '스'의 'ㅡ'는 훨씬 많다


def _shape(glyph):
    """딱 맞게 잘린 글자 픽셀이 위로 뾰족한 삼각형이면 그 기호(△ ▲)."""
    height, width = glyph.shape
    if height < MIN_PX or width < MIN_PX or not MIN_ASPECT <= width / height <= MAX_ASPECT:
        return None
    if not glyph.any(axis=1).all():  # 빈 행이 있으면 'ㅅ'과 'ㅡ'처럼 두 획이다
        return None
    left = glyph.argmax(axis=1)
    right = width - 1 - glyph[:, ::-1].argmax(axis=1)
    span = right - left + 1
    apex = max(1, round(height * APEX_BAND))
    if span[:apex].max() > APEX_WIDTH * width or span[-1] < FOOT_WIDTH * width:
        return None
    if abs((left[:apex].mean() + right[:apex].mean()) / 2 - (width - 1) / 2) > APEX_OFFSET * width:
        return None
    if np.abs(span - width * (np.arange(height) + .5) / height).max() > SLOPE_TOLERANCE * width:
        return None
    first, last = round(height * BODY[0]), round(height * BODY[1])
    fill = np.array([glyph[y, left[y]:right[y] + 1].mean() for y in range(first, last)])
    if fill.min() >= SOLID:
        return FILLED
    return HOLLOW if fill.max() <= OPEN else None


def _trim(glyph):
    rows = np.flatnonzero(glyph.any(axis=1))
    columns = np.flatnonzero(glyph.any(axis=0))
    return glyph[rows[0]:rows[-1] + 1, columns[0]:columns[-1] + 1] if rows.size else glyph[:0, :0]


def _cut_from_next(glyph, left, next_x, line_height):
    """뒤 글자에 붙은 덩어리에서 △ 부분을 자른 모양 또는 None. △32%는 밑변이 숫자 아랫획에 붙는다.

    ▲는 찾지 않는다. 실측에서 잘라 낸 ▲는 모두 글자 획이었고(세로획+가로획), 진짜 ▲는 목록 표시라 뒤 글자에 붙지 않는다.
    """
    longest = next_x - left
    for cut in range(longest, max(int(.6 * line_height), longest - line_height), -1):
        part = _trim(glyph[:, :cut])
        if part.size and _shape(part) == HOLLOW:
            return part
    return None


def _closed(glyph, kind):
    """속이 빈 삼각형은 밑변이 있어야 한다. 'v'와 '>'는 다리만 있다."""
    return kind == FILLED or (kind == HOLLOW and glyph[-1].mean() >= BASE_FILL)


def _any_direction(glyph):
    """위로 뾰족한 모양을 먼저 보고, 뒤집힌 ▼와 오른쪽을 가리키는 ▶도 같은 검사로 본다."""
    kind = _shape(glyph)
    if kind:
        return kind
    turned = glyph[::-1]
    kind = _shape(turned)
    if _closed(turned, kind):
        return TURNED[kind]
    rotated = np.rot90(glyph)
    kind = _shape(rotated)
    return POINTING[kind] if _closed(rotated, kind) else None


def _triangle(ink, glyph, left, used, line_height):
    """덩어리가 삼각형이고 그 열을 혼자 차지하며 다른 CTC 글자가 없으면 (기호, 가운데 x)."""
    kind = _any_direction(glyph) if glyph.shape[0] >= MIN_LINE_RATIO * line_height else None
    right = left + glyph.shape[1] - 1
    if (kind is None or any(left - 1 <= x <= right + 1 for x in used)
            or ink[:, left:right + 1].sum() - glyph.sum() > MAX_FOREIGN_INK * glyph.sum()):
        return None
    return kind, (left + right) / 2


def _skipped(ink, xs, line_height):
    """이웃한 CTC 글자 사이에서 모델이 건너뛴 삼각형의 (기호, 가운데 x) 목록."""
    width = ink.shape[1]
    found = []
    for previous, following in zip([None] + xs, xs + [None]):
        low = -1 if previous is None else int(previous)
        high = width if following is None else int(following)
        if high - low < MIN_PIECE_GAP * line_height:
            continue
        inner_low = 0 if previous is None else int(previous + PREVIOUS_GLYPH * line_height)
        inner_high = width if following is None else int(following - NEXT_GLYPH * line_height) + 1
        if not ink[:, max(0, inner_low):max(0, inner_high)].any():  # 단어 사이 빈칸: 덩어리를 추적할 필요가 없다
            continue
        middle = (max(0, low) + min(width - 1, high)) // 2
        for glyph, _, _, left in components(ink, middle, (high - low) // 2):
            if left <= low:  # 왼쪽 글자에서 시작한 덩어리
                continue
            if following is not None and left + glyph.shape[1] - 1 >= high:
                glyph = _cut_from_next(glyph, left, high, line_height)
                if glyph is None:
                    continue
            hit = _triangle(ink, glyph, left, xs, line_height)
            if hit:
                found.append(hit)
    return found


def _before_number(pieces, index):
    """다음 글자가 숫자인가. 표의 ▲1.2 는 'A1.2'로 읽힌다(모양은 ▲만 통과한다)."""
    return next((char for char, _ in pieces[index + 1:] if char != " "), "").isdigit()


def restore_triangles(pieces, crop, steps, width):
    """[(글자, CTC 위치)]에 건너뛴 △ ▲를 끼워 넣고 닮은 글자로 읽힌 것을 바꾼다. 없으면 받은 목록을 그대로 돌려준다."""
    if not pieces or width <= 0:
        return pieces
    ink = ink_mask(crop, THIN_INK_FRACTION)
    rows = np.flatnonzero(ink.any(axis=1))
    if rows.size == 0:
        return pieces
    line_height = int(rows[-1] - rows[0] + 1)
    per_step = width / steps
    xs = [center * per_step for char, center in pieces if char != " "]
    changed = False
    out = list(pieces)
    for index, (char, center) in enumerate(pieces):
        if char == MODEL_TRIANGLE:  # 모델이 이미 삼각형이라고 읽었다. 모양이 작아 재지 못해도 같은 표의 △와 맞춘다
            out[index] = (HOLLOW, center)
            changed = True
        elif char in LOOK_ALIKES or (char == "A" and _before_number(pieces, index)):
            x = int(center * per_step)
            others = [other for other in xs if other != center * per_step]
            for glyph, _, _, left in components(ink, x, 0):
                hit = _triangle(ink, glyph, left, others, line_height)
                if hit:
                    out[index] = (hit[0], center)
                    changed = True
                    break
    for kind, x in _skipped(ink, xs, line_height):
        out.append((kind, x / per_step))
        changed = True
    return sorted(out, key=lambda piece: piece[1]) if changed else pieces
