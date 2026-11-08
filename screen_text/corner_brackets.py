"""'[' ']'로 읽힌 조각의 화면 모양이 낫표면 「 」로, 검은 렌즈 괄호면 【 】로 바꾼다. Qt를 쓰지 않고 numpy만 쓴다.

인식 모델 사전에 낫표와 렌즈 괄호가 없어 공문서의 법령명 표기와 항목 머리가 [ ]로 읽힌다. 낫표는 ┌ ┘ 꺾임 하나뿐이라
위아래 가로획이 모두 있는 [ ]와 모양으로 갈린다. 떨어져 있는 낫표는 덩어리로 보고, 옆 글자에 붙거나 줄 높이만큼 긴
낫표는 세로획을 기준으로 본다(꺾임 안쪽과 반대쪽 끝이 비어야 한다). 렌즈 괄호는 가로획에서 세로획까지 굵기가 여러 줄에
걸쳐 줄어드는 쐐기이고, [ ]는 굵은 글꼴이라도 가로획 바로 다음에 세로획 굵기로 떨어진다. 화면 모양을 읽을 뿐 글자를
추정하지 않으며, 모델이 읽은 방향을 뒤집지 않고, 애매하면 바꾸지 않는다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import numpy as np

from screen_text.leading_symbols import THIN_INK_FRACTION, ink_mask

CORNERS = {"[": "「", "]": "」"}
LENSES = {"[": "【", "]": "】"}
MIN_HEIGHT_PX = 4        # 이보다 작으면 모양을 말할 수 없다
MIN_WIDTH_PX = 3
MIN_ASPECT = 0.3         # 가로/세로. 낫표는 0.4~1.0
MAX_ASPECT = 1.3
MAX_LINE_RATIO = 0.72    # 줄 글자 높이 대비 상한(낫표 0.43~0.6, [ ] 0.9 안팎). 큰 제목 글꼴의 긴 낫표는 [ ]와 헷갈려 놓아 둔다
MIN_ROOM_RATIO = 0.3     # 「 아래, 」 위로 비어 있어야 하는 줄 글자 높이 대비 비율(낫표는 0.47 안팎, 줄 가운데 뜬 꺾임은 0.25)
ARM_BAND = 0.25          # 가로획을 찾는 위아래 띠(글자 높이 대비)
STEM_BAND = 0.34         # 세로획을 찾는 옆 띠(글자 폭 대비)
MIN_ARM = 0.5            # 위쪽 가로획이 폭의 이만큼
MAX_OTHER_ARM = 0.55     # 아래쪽 띠는 세로획 굵기뿐이다([ ]는 1.0)
MIN_STEM = 0.7           # 세로획이 높이의 이만큼
MAX_EMPTY_FILL = 0.08    # 꺾임 맞은편 사분면은 비어 있다
# 세로획 기준(옆 글자에 붙거나 줄 높이만큼 긴 낫표, 2026-11-08). ┌ 방향으로 잰다(」는 돌려서 같은 검사)
STEM_MIN = 0.3           # 세로획 길이 하한(줄 글자 높이 대비)
STEM_TOP = 0.2           # 꺾임이 줄 윗변에서 떨어질 수 있는 거리(줄 글자 높이 대비). 'r'처럼 줄 가운데서 시작하면 낫표가 아니다(0.15면 낫표 10개를 잃었다)
STEM_GAP = 2             # 세로획 바깥과 가로획 위로 비어 있어야 하는 화소(이웃 글자의 획, 둥근 괄호의 곡선을 거른다)
STEM_ARM = 0.35          # 위 가로획이 한 줄 안에서 끊기지 않고 이어지는 길이 하한(세로획 길이 대비)
STEM_ARM_ROW = 0.6       # 가로획은 꺾임의 맨 윗줄이다. 그 줄이 이만큼 차야 한다
STEM_INSIDE = 0.3        # 비어 있어야 하는 꺾임 안쪽 폭(세로획 길이 대비)
STEM_INSIDE_FILL = 0.06  # 꺾임 안쪽 잉크 비율 상한. 세로획 아래 끝에서는 세로획 굵기 밖으로 1화소도 뻗으면 [ ]다
# 렌즈 괄호(2026-11-08): 평가 자료 【 】 308개 중 279개가 쐐기였고 [ ] 603개 중 0개였다
LENS_MIN_HEIGHT_PX = 8   # 이보다 작으면 쐐기를 말할 수 없다
LENS_MAX_ASPECT = 0.8    # 가로/세로 상한
LENS_LINE_RATIO = 0.6    # 렌즈 괄호는 줄 높이에 가깝다(0.91~1.0)
LENS_TAPER_ROWS = 4      # 가로획과 세로획 사이 중간 굵기 줄이 위아래 합쳐 이만큼
LENS_END_ROWS = 2        # 그리고 양끝 각각 이만큼. 스캔으로 흐려진 [ 의 둥근 모서리는 한쪽에 한 줄뿐이었다(진짜 【 】는 모두 2줄 이상)


def components(ink, x, reach):
    """x에서 가까운 열부터 만나는 글자 덩어리(8방향 연결)를 (모양, 위 행, 아래 행, 왼쪽 열)로 낸다."""
    height, width = ink.shape
    seen = np.zeros(ink.shape, dtype=bool)
    for distance in range(reach + 1):
        for column in {x - distance, x + distance}:
            if not 0 <= column < width:
                continue
            for row in np.flatnonzero(ink[:, column] & ~seen[:, column]):
                if seen[row, column]:  # 앞선 덩어리가 이미 지나간 칸
                    continue
                seen[row, column] = True
                stack, points = [(int(row), column)], []
                while stack:
                    y, c = stack.pop()
                    points.append((y, c))
                    for ny in range(max(0, y - 1), min(height, y + 2)):
                        for nc in range(max(0, c - 1), min(width, c + 2)):
                            if ink[ny, nc] and not seen[ny, nc]:
                                seen[ny, nc] = True
                                stack.append((ny, nc))
                rows, columns = zip(*points)
                top, left = min(rows), min(columns)
                glyph = np.zeros((max(rows) - top + 1, max(columns) - left + 1), dtype=bool)
                glyph[np.array(rows) - top, np.array(columns) - left] = True
                yield glyph, top, max(rows), left


def _is_open_corner(glyph):
    """┌ 꺾임 하나인가. ] 쪽은 180도 돌려서 같은 검사를 쓴다."""
    height, width = glyph.shape
    if height < MIN_HEIGHT_PX or width < MIN_WIDTH_PX or not MIN_ASPECT <= width / height <= MAX_ASPECT:
        return False
    band = max(1, round(height * ARM_BAND))
    stem = max(1, round(width * STEM_BAND))
    return (glyph[:band].any(axis=0).mean() >= MIN_ARM
            and glyph[-band:].any(axis=0).mean() <= MAX_OTHER_ARM
            and glyph[:, :stem].any(axis=1).mean() >= MIN_STEM
            and glyph[height // 2:, width // 2:].mean() <= MAX_EMPTY_FILL)


def _corner_near(ink, x, line_top, line_bottom, char):
    line_height = line_bottom - line_top + 1
    for glyph, top, bottom, _ in components(ink, x, max(2, line_height // 2)):
        room = (line_bottom - bottom) if char == "[" else (top - line_top)
        if (glyph.shape[0] <= MAX_LINE_RATIO * line_height and room >= MIN_ROOM_RATIO * line_height
                and _is_open_corner(glyph if char == "[" else glyph[::-1, ::-1])):
            return True
    return False


def _runs_from_left(block):
    """행마다 왼쪽 끝부터 끊기지 않고 이어진 잉크 길이."""
    return np.cumprod(block, axis=1).sum(axis=1)


def _stem_corner(ink, x, line_top, line_height):
    """x 가까이에서 ┌ 꺾임을 세로획 기준으로 찾는다. 옆 글자에 붙은 덩어리이거나 줄 높이만큼 길어도 낫표면 참.

    세로획은 줄 윗변 가까이에서 시작하고 바깥이 비어 있다. 맨 윗줄에서 끊기지 않는 긴 가로획이 뻗고 그 위는 비어 있다.
    꺾임 안쪽은 비고, 세로획 아래 끝은 세로획 굵기 밖으로 뻗지 않는다(뻗으면 아래 가로획이 있는 [ ]다).
    """
    height, width = ink.shape
    for distance in range(max(2, line_height // 2) + 1):
        for c in sorted({x - distance, x + distance}):
            if not 0 <= c < width - 2:
                continue
            rows = np.flatnonzero(ink[:, c])
            if rows.size == 0:
                continue
            breaks = np.flatnonzero(np.diff(rows) > 1)
            for r0, r1 in zip(np.r_[rows[0], rows[breaks + 1]].tolist(), np.r_[rows[breaks], rows[-1]].tolist()):
                h = r1 - r0 + 1
                if h < max(MIN_HEIGHT_PX, STEM_MIN * line_height) or r0 - line_top > STEM_TOP * line_height:
                    continue
                if ink[r0:r1 + 1, max(0, c - STEM_GAP):c].any():   # 세로획 바깥이 비어야 한다
                    continue
                arm = max(2, round(STEM_ARM * h))
                if c + arm > width or ink[r0, c:c + arm].mean() < STEM_ARM_ROW:
                    continue
                if ink[max(0, r0 - STEM_GAP):r0, max(0, c - 1):c + arm + 1].any():   # 가로획 위가 비어야 한다
                    continue
                thick = 1
                while c + thick < width and thick < max(2, round(0.25 * h)) and ink[r0:r1 + 1, c + thick].mean() >= 0.7:
                    thick += 1
                band = max(1, round(0.2 * h))
                left, right = c + thick, min(width, c + thick + max(2, round(STEM_INSIDE * h)))
                if right - left < 2:
                    continue
                if r1 + 1 - band > r0 + band and ink[r0 + band:r1 + 1 - band, left:right].mean() > STEM_INSIDE_FILL:
                    continue
                if _runs_from_left(ink[r0:r0 + band, c:]).max() < arm:   # 위 가로획은 끊기지 않고 길다
                    continue
                if _runs_from_left(ink[max(r0 + band, r1 + 1 - band):r1 + 1, c:]).max() > thick:   # 아래 가로획이 있으면 [ ]다
                    continue
                return True
    return False


def _latin_inside(pieces, index, char):
    """괄호 안쪽 이웃(공백 건너뜀)이 영문자인가. 【 】는 한국어 문서의 표기라 영문 참고문헌의 ]를 바꾸지 않는다."""
    step = 1 if char == "[" else -1
    k = index + step
    while 0 <= k < len(pieces) and pieces[k][0] == " ":
        k += step
    return 0 <= k < len(pieces) and pieces[k][0].isascii() and pieces[k][0].isalpha()


def _lens_near(ink, x, line_height, char):
    """x 가까이의 괄호 덩어리가 【 모양(쐐기)인가. ] 쪽은 180도 돌려서 같은 검사를 쓴다.

    행마다 왼쪽 끝부터 이어진 잉크 길이를 잰다. 【는 위아래 가로획 폭이 같고, 가로획에서 가운데의 가장 가는 세로획까지
    길이가 여러 줄에 걸쳐 단계적으로 줄었다가 다시 는다. [ ]는 굵은 글꼴이라도 가로획 줄 바로 다음에 세로획 굵기가 된다.
    """
    for glyph, _, _, _ in components(ink, x, max(2, line_height // 2)):
        g = glyph if char == "[" else glyph[::-1, ::-1]
        h, w = g.shape
        if h < LENS_MIN_HEIGHT_PX or w / h > LENS_MAX_ASPECT or h < LENS_LINE_RATIO * line_height:
            continue
        lead = _runs_from_left(g)
        middle = lead[h // 3:max(h // 3 + 1, 2 * h // 3)]
        thin = int(middle.min())
        if thin < 1:
            continue
        k = h // 3 + int(middle.argmin())
        up, down = lead[:k + 1], lead[k:]
        up = up[1:] if up[0] < up.max() else up        # 둥근 모서리로 맨 윗줄·아랫줄이 짧을 수 있다
        down = down[:-1] if down[-1] < down.max() else down
        top, foot = int(up.max()), int(down.max())
        if min(top, foot) - thin < 2 or abs(top - foot) > 1:   # 위아래 가로획이 같은 폭으로 세로획보다 넓다
            continue
        upper, lower = int(((up > thin) & (up < top)).sum()), int(((down > thin) & (down < foot)).sum())
        if (min(upper, lower) >= LENS_END_ROWS and upper + lower >= LENS_TAPER_ROWS
                and (np.diff(up) <= 0).all() and (np.diff(down) >= 0).all()):
            return True
    return False


def restore_corner_brackets(pieces, crop, steps, width):
    """[(글자, CTC 위치)]에서 화면 모양이 낫표·렌즈 괄호인 '[' ']'만 바꾼다. 없으면 받은 목록을 그대로 돌려준다."""
    if width <= 0 or not any(char in CORNERS for char, _ in pieces):
        return pieces
    ink = ink_mask(crop, THIN_INK_FRACTION)
    rows = np.flatnonzero(ink.any(axis=1))
    if rows.size == 0:
        return pieces
    line_top, line_bottom = int(rows[0]), int(rows[-1])
    line_height = line_bottom - line_top + 1
    flipped = ink[::-1, ::-1]

    def corner(char, x):
        if _corner_near(ink, x, line_top, line_bottom, char):
            return True
        if char == "[":
            return _stem_corner(ink, x, line_top, line_height)
        return _stem_corner(flipped, ink.shape[1] - 1 - x, ink.shape[0] - 1 - line_bottom, line_height)

    out = []
    for index, (char, center) in enumerate(pieces):
        x = int(center * width / steps)
        if char in CORNERS and corner(char, x):
            char = CORNERS[char]
        elif char in LENSES and not _latin_inside(pieces, index, char) and _lens_near(ink, x, line_height, char):
            char = LENSES[char]
        out.append((char, center))
    return out
