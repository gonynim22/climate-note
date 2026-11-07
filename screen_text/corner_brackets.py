"""'[' ']'로 읽힌 조각의 화면 모양이 낫표면 「 」로 바꾼다. Qt를 쓰지 않고 numpy만 쓴다.

인식 모델 사전에 낫표가 없어 공문서의 법령명 표기가 [ ]로 읽힌다. 낫표는 줄 글자 높이의 절반쯤이고 위(「)나
아래(」)에 붙어 있으며 ┌ ┘ 꺾임 하나뿐이라, 위아래 가로획이 모두 있는 [ ]와 모양으로 갈린다. 화면 모양을 읽을
뿐 글자를 추정하지 않으며, 모델이 읽은 방향을 뒤집지 않고, 애매하면 바꾸지 않는다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import numpy as np

from screen_text.leading_symbols import THIN_INK_FRACTION, ink_mask

CORNERS = {"[": "「", "]": "」"}
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


def restore_corner_brackets(pieces, crop, steps, width):
    """[(글자, CTC 위치)]에서 화면 모양이 낫표인 '[' ']'만 바꾼다. 없으면 받은 목록을 그대로 돌려준다."""
    if width <= 0 or not any(char in CORNERS for char, _ in pieces):
        return pieces
    ink = ink_mask(crop, THIN_INK_FRACTION)
    rows = np.flatnonzero(ink.any(axis=1))
    if rows.size == 0:
        return pieces
    line_top, line_bottom = int(rows[0]), int(rows[-1])
    return [(CORNERS[char], center) if char in CORNERS
            and _corner_near(ink, int(center * width / steps), line_top, line_bottom, char)
            else (char, center) for char, center in pieces]
