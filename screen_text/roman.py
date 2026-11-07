"""공문서 번호의 로마 숫자 Ⅰ Ⅱ Ⅲ 을 화면의 세로획 수로 되살린다. Qt를 쓰지 않고 numpy만 쓴다.

모델은 Ⅱ 를 I·표로, Ⅲ 을 II·피로 읽거나 아예 건너뛴다. 획 하나가 사라지면 다른 번호가 된다. 번호 자리(줄 맨 앞이나 괄호 뒤이고
뒤에 . - ) 가 오는 자리)의 글자가 같은 높이의 곧은 세로획 둘이나 셋이면 그 수로 쓴다. 획 높이가 다른 '피'·'표'는 모양으로 걸러진다.
Ⅳ Ⅴ Ⅵ 은 모델이 IV V VI 로 읽어 뜻이 바뀌지 않으므로 그대로 둔다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import numpy as np

from screen_text.leading_symbols import ink_mask

NUMERALS = {1: "Ⅰ", 2: "Ⅱ", 3: "Ⅲ"}
READS = frozenset("Il|!1ㅣㅍ피표끄씨")   # 모델이 로마 숫자를 이렇게 읽는다. 대괄호는 뺀다. [Ⅰ 의 괄호 획까지 세면 Ⅱ 가 된다
OPENERS = frozenset("([<「")
FOLLOW = frozenset(".-–—)]>:장")
PLAIN_ONE = frozenset("Il1")          # 획이 하나면 뜻이 같으니 그대로 둔다
MAX_READ = 3                          # 이보다 긴 낱말은 번호가 아니다
MIN_HEIGHT = 0.6                      # 글자 높이의 하한(줄 글자 높이 대비)
MIDDLE = (0.3, 0.7)                   # 획을 세는 행(글자 높이 대비). 위아래 가로 세리프를 피한다
MIN_AGREE = 0.8                       # 가운데 행 중 이만큼이 같은 수의 획이어야 한다
MAX_STEM = 0.3                        # 획 폭의 상한(글자 높이 대비)
MIN_FILL = 0.8                        # 획은 글자 높이의 이만큼 이어진다('피'의 ㅍ 줄기는 짧다)
MAX_GAP = 1.0                         # 획 사이 거리의 상한(글자 높이 대비)


def _runs(row):
    edges = np.flatnonzero(np.diff(np.r_[0, row.astype(np.int8), 0]))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


def stroke_count(ink):
    """글자 픽셀에서 같은 높이의 곧은 세로획 수. 세로획만의 글자가 아니면 0."""
    rows = np.flatnonzero(ink.any(axis=1))
    if rows.size == 0:
        return 0
    top, bottom = int(rows[0]), int(rows[-1])
    height = bottom - top + 1
    if height < 5:
        return 0
    middle = range(top + round(MIDDLE[0] * height), max(top + round(MIDDLE[1] * height), top + round(MIDDLE[0] * height) + 1))
    found = [_runs(ink[row]) for row in middle]
    counts = [len(item) for item in found]
    best = max(set(counts), key=counts.count)
    if not 1 <= best <= 3 or counts.count(best) < MIN_AGREE * len(counts):
        return 0
    stems = next(item for item in found if len(item) == best)
    if any(end - start > max(2, MAX_STEM * height) for start, end in stems):
        return 0
    if any(b[0] - a[0] > MAX_GAP * height for a, b in zip(stems, stems[1:])):
        return 0
    inner = ink[top + 1:bottom]      # 세리프 행은 빼고 잰다
    for start, end in stems:
        if inner[:, start:end].any(axis=1).mean() < MIN_FILL:
            return 0
    return best


def _next_glyph_start(filled, x, low):
    """x의 글자가 시작하는 열. 읽은 자리는 글자 안쪽 어딘가다. 앞 글자와 붙어 있으면 x를 그대로 쓴다."""
    column = min(len(filled) - 1, int(x))
    start = column
    while start > low and filled[start - 1]:
        start -= 1
    return column if start <= low else start


def _is_slot(read, start, end):
    """read[start:end]가 번호 자리인가. 칸에 혼자 있는 '1l'은 숫자 11일 수 있어 번호로 보지 않는다."""
    before = read[start - 1][0] if start else ""
    follow = read[end][0] if end < len(read) else ""
    if before and before not in OPENERS:
        return False
    return follow in FOLLOW or (follow == "" and all(char != "1" for char, _ in read[start:end]))


def restore_roman(pieces, crop, steps, width):
    """번호 자리의 글자가 세로획 둘·셋이면 로마 숫자로 바꾼다. 없으면 받은 목록을 그대로 돌려준다."""
    read = [piece for piece in pieces if piece[0] != " "]
    if width <= 0 or not read or not any(char in READS for char, _ in read):
        return pieces
    ink = ink_mask(crop)
    rows = np.flatnonzero(ink.any(axis=1))
    if rows.size == 0:
        return pieces
    line_height = int(rows[-1] - rows[0] + 1)
    per_step = width / steps
    filled = ink.any(axis=0)
    gaps = [center for char, center in pieces if char == " "]
    put, drop = {}, set()
    index = 0
    while index < len(read):
        end = index
        while end < len(read) and read[end][0] in READS and end - index < MAX_READ:
            end += 1
        text = "".join(char for char, _ in read[index:end])
        if end == index or (end < len(read) and read[end][0] in READS) or text.strip("1") == "" or not _is_slot(read, index, end):
            index = max(end, index + 1)     # 11.6 과 페이지 번호 11 은 세로획 둘이어도 숫자다
            continue
        low = int((read[index - 1][1] + read[index][1]) / 2 * per_step) if index else 0
        high = _next_glyph_start(filled, read[end][1] * per_step, low) if end < len(read) else width
        glyph = ink[:, max(0, low):high]
        count = stroke_count(glyph)
        tall = np.flatnonzero(glyph.any(axis=1)).size >= MIN_HEIGHT * line_height
        following_space = any(read[end - 1][1] <= gap <= read[end][1] for gap in gaps) if end < len(read) else False
        if tall and (count >= 2 or (count == 1 and text not in PLAIN_ONE and not following_space and end < len(read))):
            put[read[index][1]] = NUMERALS[count]
            drop.update(center for _, center in read[index + 1:end])
        index = max(end, index + 1)
    if not put:
        return pieces
    return [(put.get(center, char), center) for char, center in pieces if center not in drop or char == " "]
