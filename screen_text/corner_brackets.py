"""'[' ']'로 읽힌 조각의 화면 모양이 낫표면 「 」로, 검은 렌즈 괄호면 【 】로 바꾼다. Qt를 쓰지 않고 numpy만 쓴다.

인식 모델 사전에 낫표와 렌즈 괄호가 없어 공문서의 법령명 표기와 항목 머리가 [ ]로 읽힌다. 낫표는 ┌ ┘ 꺾임 하나뿐이라
위아래 가로획이 모두 있는 [ ]와 모양으로 갈린다. 떨어져 있는 낫표는 덩어리로 보고, 옆 글자에 붙거나 줄 높이만큼 긴
낫표는 세로획을 기준으로 본다(꺾임 안쪽과 반대쪽 끝이 비어야 한다). 렌즈 괄호는 가로획에서 세로획까지 굵기가 여러 줄에
걸쳐 줄어드는 쐐기이고, [ ]는 굵은 글꼴이라도 가로획 바로 다음에 세로획 굵기로 떨어진다. 화면 모양을 읽을 뿐 글자를
추정하지 않으며, 모델이 읽은 방향을 뒤집지 않고, 애매하면 바꾸지 않는다. 계약은 docs/SCREEN_TEXT.md를 따른다.

겹낫표 『 』(2026-11-09)도 사전에 없다. 속을 채운 모양이 ┌ 테두리 하나이고, 그 안에 가는 틈(구멍)이 있거나 작은 글씨처럼
틈이 메워졌어도 가로획이 줄 글자 가로획의 2배·세로획이 1.5배 이상 두꺼우면 겹낫표다. 모델이 낫표·겹낫표를 건너뛰었거나
닮은 글자(' , r F P ° ¶ 등)로 읽은 자리는 더 엄격히 본다: 그 자리 덩어리가 다른 CTC 글자의 몫이 아니고, 줄 윗변(닫는 쪽은
아랫변)에 붙은 꺾임 하나이며, 괄호 안쪽 글자에 띄어쓰기 없이 붙어 있어야 넣거나 바꾼다.
"""
import numpy as np

from screen_text.leading_symbols import THIN_INK_FRACTION, ink_level, ink_mask

CORNERS = {"[": "「", "]": "」"}
DOUBLES = {"「": "『", "」": "』"}
LENSES = {"[": "【", "]": "】"}
# 모델이 낫표·겹낫표를 이렇게 읽은 실측(2026-11-09). 모양이 꺾임 하나일 때만 바꾼다
LOOK_ALIKES = frozenset("',.\"‘’“”r5ㄷFP*°¶ㅣ")
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
# 겹낫표(2026-11-09). 속을 채운 모양이 ┌ 테두리 하나인지 본다
FRAME_FULL = 0.75        # 가로획 줄·세로획 열은 속을 채운 모양의 폭·높이를 이만큼 덮는다
FRAME_REST = 0.04        # 테두리 안쪽(가로획·세로획 너머 1화소 여유 밖)의 채움 상한
FRAME_MAX_ARM = 0.55     # 가로획 두께 상한(높이 대비). 'P'의 둥근 고리는 높이의 절반을 넘는다
FRAME_MAX_STEM = 0.7     # 세로획 두께 상한(폭 대비)
DOUBLE_MIN_HOLE = 2      # 테두리 안 구멍 화소 하한(속이 빈 겹낫표)
DOUBLE_SLIT_PX = 2       # 겹낫표의 구멍은 가는 틈이다. 구멍 두께 상한(화소, 높이 비율과 큰 쪽). 'P'의 둥근 고리 속은 두껍다
DOUBLE_SLIT_RATIO = 0.15
TALL_DOUBLE_RATIO = 1.0  # 모델이 [ ]로 읽은 겹낫표는 줄 높이만큼 길어도 된다(휴먼명조의 괄호는 줄 높이의 0.75~0.9배)
ADJ_GAP = 0.4            # 여는 괄호 뒤·닫는 괄호 앞의 글자까지 빈 열 상한(줄 글자 높이 대비). 괄호는 안쪽 글자에 붙는다. 글머리 ❏의 그림자 ┘는 앞 글자와 띄어 있다
DOUBLE_STROKE = 2.0      # 구멍 없는 겹낫표(작은 글씨는 틈이 메워진다): 가로획이 줄 글자 가로획 굵기의 이 배 이상이고
DOUBLE_STEM = 1.5        # 세로획이 줄 글자 세로획 굵기의 이 배 이상(새 평가 자료의 홑낫표 1,640개 중 1개만 넘었다)
DOUBLE_SOLID_MAX_PX = 13 # 틈이 메워지는 것은 작은 글씨뿐이다(굵기로 찾은 겹낫표의 99%가 이 높이 이하). 더 큰 속이 찬 꺾임은
                         # 휴먼명조 24px·HY중고딕 27px의 「처럼 가로획만 두꺼운 홑낫표였다
# 회색 농도로 보는 겹낫표(2026-11-09). 글꼴을 넣은 PDF처럼 번지게 그린 화면에서는 『의 두 줄과 틈이 한 획으로 메워져
# 굵기도 본문과 같다. 대신 그 획은 옅고(두 가는 줄의 평균) 넓게 퍼진다. 「는 진한 한 줄이다
GRAY_MIN_PX = 9          # 이보다 작은 괄호는 번짐이 모든 획을 비슷하게 만든다(75% 축소·PDF 100%의 높이 8 이하 「가 옅고 넓었다)
GRAY_PEAK = 0.65         # 꺾임 획의 가장 진한 값이 줄에서 가장 진한 글자 픽셀 대비 이 미만
GRAY_SPREAD = 1.2        # 세로획 단면의 농도 퍼짐(표준편차)이 줄 글자 세로획 퍼짐의 중앙값 대비 이 초과
GRAY_SHARP_TEXT = 0.65   # 줄 글자 세로획의 퍼짐이 이 이하(화소)인 또렷한 줄에서만 본다. 스캔·JPEG·125%처럼 본문이 번진 줄은 「도 옅고 넓다
# 닮은 글자·건너뛴 자리(2026-11-09). 모델이 괄호로 읽지 않은 자리라 더 엄격히 본다
OWN_REACH = 0.35         # 조각 위치에서 덩어리를 찾는 거리(줄 글자 높이 대비)
NEW_MIN_RATIO = 0.35     # 넣거나 바꾸는 낫표의 높이 하한(줄 글자 높이 대비). 쉼표·따옴표·흐린 스캔의 점은 훨씬 작다
ANCHOR = 0.25            # 「 『는 줄 윗변, 」 』는 줄 아랫변에서 이만큼 안에 붙는다(줄 글자 높이 대비). 영문 소문자 r은 줄 가운데서 시작한다
ADJ_GAP = 0.4            # 여는 괄호 뒤·닫는 괄호 앞 글자까지 빈 열 상한(줄 글자 높이 대비). 맞게 넣은 괄호는 0.38 이하였고
                         # 글머리 ❏의 진한 그림자(┘)는 앞 글자와 띄어 있어 0.5 이상이었다
CLAIM_REACH = 0.6        # 이 거리 안에 모델이 읽은 [ ]가 있으면 그 덩어리는 이미 읽힌 것이다(줄 글자 높이 대비)
RULE_FILL = 0.85         # 이만큼 찬 행은 표 선·밑줄이다. 넣거나 바꾸는 자리의 줄 높이를 잴 때 뺀다
BRACKET_PIECES = frozenset("[]")


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


def _filled(glyph):
    """바깥 빈칸(4방향 연결)에서 닿지 않는 구멍을 채운 모양과 구멍 화소 수."""
    height, width = glyph.shape
    pad = np.zeros((height + 2, width + 2), dtype=bool)
    pad[1:-1, 1:-1] = glyph
    outside = np.zeros_like(pad)
    outside[0, 0] = True
    stack = [(0, 0)]
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < height + 2 and 0 <= nx < width + 2 and not pad[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                stack.append((ny, nx))
    filled = ~outside[1:-1, 1:-1]
    return filled, int((filled & ~glyph).sum())


def _frame(glyph):
    """속을 채운 모양이 ┌ 테두리 하나면 (가로획 줄 수, 세로획 열 수, 구멍 화소 수), 아니면 None."""
    height, width = glyph.shape
    if height < MIN_HEIGHT_PX or width < MIN_WIDTH_PX or not MIN_ASPECT <= width / height <= MAX_ASPECT:
        return None
    filled, holes = _filled(glyph)
    arm = 0
    while arm < height and filled[arm].mean() >= FRAME_FULL:
        arm += 1
    stem = 0
    while stem < width and filled[:, stem].mean() >= FRAME_FULL:
        stem += 1
    if not arm or not stem or arm > FRAME_MAX_ARM * height or stem > FRAME_MAX_STEM * width:
        return None
    if not holes and (height - arm - 1 < 2 or width - stem - 1 < 1):   # 속이 찬 꺾임은 안쪽이 있어야 한다. 4×4 삼각 조각은 안쪽이 없다
        return None
    rest = filled[arm + 1:, stem + 1:]
    if rest.size and rest.mean() > FRAME_REST:
        return None
    if filled[-1, stem + 1:].any() or filled[arm + 1:, -1].any():   # 세로획 끝에 가로획([ ])·가로획 끝에 세로획이 있으면 아니다
        return None
    return arm, stem, holes


def _stroke_widths(ink):
    """줄 글자 획의 굵기(가로획 두께, 세로획 두께). 세로·가로로 이어진 글자 픽셀 길이의 최빈값이다."""
    def mode(mask):
        steps = np.diff(np.pad(mask.astype(np.int8), ((0, 0), (1, 1))), axis=1).ravel()
        lengths = np.flatnonzero(steps == -1) - np.flatnonzero(steps == 1)
        return max(1, int(np.bincount(lengths).argmax())) if lengths.size else 1
    return mode(ink.T), mode(ink)


def _hole_thickness(glyph):
    """구멍 안에 들어가는 가장 큰 정사각형의 변(화소). 겹낫표의 가는 틈은 1~2, 'P'의 둥근 고리 속은 크다."""
    filled, _ = _filled(glyph)
    hole = (filled & ~glyph).astype(np.int32)
    if not hole.any():
        return 0
    table = np.pad(hole.cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))
    side = 1
    while side < min(hole.shape):
        k = side + 1
        windows = table[k:, k:] - table[:-k, k:] - table[k:, :-k] + table[:-k, :-k]
        if not (windows == k * k).any():
            break
        side = k
    return side


def _is_double(glyph, strokes):
    """┌ 테두리 안에 가는 틈이 있거나, 가로획이 줄 글자 가로획의 2배·세로획이 1.5배 이상 두꺼우면 겹낫표다."""
    frame = _frame(glyph)
    if frame is None:
        return False
    arm, stem, holes = frame
    if holes >= DOUBLE_MIN_HOLE:
        return _hole_thickness(glyph) <= max(DOUBLE_SLIT_PX, DOUBLE_SLIT_RATIO * glyph.shape[0])
    if glyph.shape[0] > DOUBLE_SOLID_MAX_PX or arm < DOUBLE_STROKE * strokes[0]:
        return False
    return stem >= DOUBLE_STEM * strokes[1]


def _spread(values):
    """단면 농도의 질량과 표준편차(화소)."""
    values = np.clip(np.asarray(values, dtype=np.float64), 0, None)
    mass = float(values.sum())
    if mass <= 0:
        return 0.0, 0.0
    x = np.arange(values.size)
    mean = float((values * x).sum() / mass)
    return mass, float(np.sqrt((values * (x - mean) ** 2).sum() / mass))


def _stroke_spread(ink, gray, line_height):
    """줄 글자 세로획의 가로 단면 농도 퍼짐 중앙값. 줄 높이의 0.25배를 넘는 가로 막대는 획이 아니라 뺀다."""
    spreads = []
    limit = max(2, 0.25 * line_height)
    for r in range(ink.shape[0]):
        edges = np.flatnonzero(np.diff(np.r_[0, ink[r].view(np.int8), 0]))
        for a, b in zip(edges[0::2].tolist(), edges[1::2].tolist()):
            if b - a <= limit:
                mass, spread = _spread(gray[r, max(0, a - 1):b + 1])
                if mass > 0:
                    spreads.append(spread)
    return float(np.median(spreads)) if spreads else 0.0


def _gray_double(gray, text_spread, glyph, top, left, side):
    """번지게 그린 『: 테두리 꺾임의 획이 줄에서 가장 진한 글자보다 옅고 세로획 단면이 본문 세로획보다 넓게 퍼졌다."""
    if glyph.shape[0] < GRAY_MIN_PX or text_spread > GRAY_SHARP_TEXT:
        return False
    g = glyph if side == "[" else glyph[::-1, ::-1]
    frame = _frame(g)
    if frame is None:
        return False
    arm, stem, _ = frame
    box = gray[top:top + glyph.shape[0], left:left + glyph.shape[1]]
    box = box if side == "[" else box[::-1, ::-1]
    height, width = box.shape
    stem_rows = box[min(height - 1, arm + 1):, :min(width, stem + 3)]
    arm_cols = box[:min(height, arm + 3), min(width - 1, stem + 1):]
    if not stem_rows.size or not arm_cols.size:
        return False
    if max(float(stem_rows.max()), float(arm_cols.max())) >= GRAY_PEAK:
        return False
    _, spread = _spread(stem_rows.mean(axis=0))
    return spread > GRAY_SPREAD * max(0.05, text_spread)


def _hugs_content(ink, kind, left, right, line_height):
    """여는 괄호면 오른쪽, 닫는 괄호면 왼쪽으로 ADJ_GAP 안에 글자 픽셀이 있는가(괄호는 안쪽 글자에 띄어쓰기 없이 붙는다)."""
    limit = max(2, round(ADJ_GAP * line_height))
    occupied = ink.any(axis=0)
    if kind in "「『":
        return bool(occupied[right + 1:right + 2 + limit].any())
    return bool(occupied[max(0, left - 1 - limit):left].any())


def _alone(ink, glyph, top, left):
    """덩어리의 네모 안에 다른 덩어리의 글자 픽셀이 없는가. 있으면 그 꺾임은 다른 글자를 두른 획의 한 조각이다."""
    box = ink[top:top + glyph.shape[0], left:left + glyph.shape[1]]
    return int((box & ~glyph).sum()) <= 1


def _bracket_glyph(glyph, top, bottom, line_top, line_bottom, side, strokes, strict=False, left=None, shade=None):
    """덩어리 하나가 side('[' ┌ 또는 ']' ┘) 방향 낫표·겹낫표면 그 글자, 아니면 None.

    strict는 모델이 괄호로 읽지 않은 자리(닮은 글자·건너뛴 자리)다. 줄 높이의 0.35배 이상이고 줄 윗변(」는 아랫변)에 붙어야 하며
    홑낫표도 속을 채운 모양이 ┌ 테두리여야 한다.
    """
    line_height = line_bottom - line_top + 1
    g = glyph if side == "[" else glyph[::-1, ::-1]
    room = (line_bottom - bottom) if side == "[" else (top - line_top)
    if g.shape[0] > MAX_LINE_RATIO * line_height or room < MIN_ROOM_RATIO * line_height:
        return None
    anchor = (top - line_top) if side == "[" else (line_bottom - bottom)
    if strict and (g.shape[0] < NEW_MIN_RATIO * line_height or anchor > ANCHOR * line_height):
        return None
    if _is_double(g, strokes):
        return DOUBLES[CORNERS[side]]
    if _is_open_corner(g) and (not strict or _frame(g) is not None):   # 'ㅏ'처럼 세로획 곁가지만 있는 획은 맨 윗줄이 폭을 덮지 못한다
        if shade is not None and left is not None and _gray_double(*shade(), glyph, top, left, side):
            return DOUBLES[CORNERS[side]]
        return CORNERS[side]
    return None


def _corner_near(ink, x, line_top, line_bottom, char, strokes, shade=None):
    """모델이 [ ]로 읽은 자리 가까이의 덩어리 중 낫표·겹낫표 모양의 첫 덩어리가 나타내는 글자."""
    line_height = line_bottom - line_top + 1
    for glyph, top, bottom, left in components(ink, x, max(2, line_height // 2)):
        found = _bracket_glyph(glyph, top, bottom, line_top, line_bottom, char, strokes, left=left, shade=shade)
        if found:
            return found
    return None


def _tall_double_near(ink, x, line_top, line_bottom, char, strokes):
    """모델이 [ ]로 읽은 자리의 긴 겹낫표. 휴먼명조처럼 괄호가 줄 높이만큼 길면 덩어리 판정의 높이·빈 곳 조건에 걸린다.

    테두리 꺾임 하나(아래 가로획이 없음)이고 겹낫표이며 줄 윗변(」는 아랫변)에 붙어 있으면 참.
    """
    line_height = line_bottom - line_top + 1
    for glyph, top, bottom, _ in components(ink, x, max(2, line_height // 2)):
        g = glyph if char == "[" else glyph[::-1, ::-1]
        anchor = (top - line_top) if char == "[" else (line_bottom - bottom)
        if g.shape[0] <= TALL_DOUBLE_RATIO * line_height and anchor <= ANCHOR * line_height and _is_double(g, strokes):
            arm, stem, holes = _frame(g)
            if holes >= DOUBLE_MIN_HOLE or not _widens_at_end(g, arm, stem):   # 작은 렌즈 괄호 】는 세로획 끝이 다시 넓어진다
                return True
    return False


def _widens_at_end(glyph, arm, stem):
    """┌의 세로획이 끝(맨 아래 두 줄)에서 세로획 굵기보다 넓어지는가. 렌즈 괄호는 끝이 쐐기로 다시 넓어지고 낫표는 그대로다."""
    rows = glyph[arm:]
    if rows.shape[0] < 4:
        return False
    widths = np.where(rows.any(axis=1), rows.shape[1] - np.argmax(rows[:, ::-1], axis=1), 0)
    return int(widths[-2:].max()) > max(stem, int(np.median(widths[:-2])))


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


def _neighbor(pieces, index, step):
    """index에서 step 방향으로 공백을 건너뛴 이웃 글자(없으면 '')."""
    k = index + step
    while 0 <= k < len(pieces) and pieces[k][0] == " ":
        k += step
    return pieces[k][0] if 0 <= k < len(pieces) else ""


def _own_bracket(ink, x, others, line_top, line_bottom, strokes, shade=None):
    """조각 위치 x에 가장 가까운 덩어리가 이 조각의 몫이고 낫표·겹낫표 모양이면 그 글자. 방향은 모양으로 정한다.

    CTC 위치는 글자에서 2~3화소 벗어나곤 한다. 덩어리 열 범위까지의 거리가 다른 어느 조각보다 이 조각에 가까워야 한다.
    """
    line_height = line_bottom - line_top + 1
    reach = max(1, round(OWN_REACH * line_height))
    for glyph, top, bottom, left in components(ink, x, reach):
        right = left + glyph.shape[1] - 1
        distance = max(0, left - x, x - right)
        if distance > reach or any(max(0, left - other, other - right) <= distance for other in others):
            continue
        found = [b for side in "[]" if (b := _bracket_glyph(glyph, top, bottom, line_top, line_bottom, side, strokes, True, left, shade))]
        if len(found) == 1 and _alone(ink, glyph, top, left) and _hugs_content(ink, found[0], left, right, line_height):
            return found[0], left, right
    return None


def _between(prev, following):
    """양옆 글자가 모두 영문자이거나 모두 숫자인 자리. 낫표는 그런 자리에 오지 않는다(낱말 속 r, 2,100의 쉼표)."""
    if not prev or not following:
        return False
    return ((prev.isascii() and prev.isalpha() and following.isascii() and following.isalpha())
            or (prev.isdigit() and following.isdigit()))


def _column_runs(ink):
    """빈 열로 갈린 글자 열 묶음 [(왼쪽, 오른쪽)]."""
    edges = np.flatnonzero(np.diff(np.r_[0, ink.any(axis=0).view(np.int8), 0]))
    return list(zip(edges[0::2].tolist(), (edges[1::2] - 1).tolist()))


def _tall_enough(ink, run, line_height):
    """글자 열 묶음의 글자 높이가 넣거나 바꿀 낫표의 하한을 넘는가. 쉼표·따옴표는 여기서 걸러 덩어리를 따라가지 않는다."""
    rows = np.flatnonzero(ink[:, run[0]:run[1] + 1].any(axis=1))
    return rows.size and rows[-1] - rows[0] + 1 >= NEW_MIN_RATIO * line_height


def _skipped(ink, runs, pieces, per_step, line_top, line_bottom, strokes, used, shade=None):
    """모델이 건너뛴 낫표·겹낫표의 (글자, 가운데 x) 목록.

    빈 열로 이웃과 떨어진 글자 열 묶음을 CTC 글자마다 가장 가까운 것에 묶는다. 어느 글자에도 묶이지 않고, 이미 바꾼 괄호
    덩어리(used)와 겹치지 않으며, 가까이에 모델이 읽은 [ ]도 없을 때 묶음 안의 덩어리마다 본다. 덩어리가 꺾임 하나이고
    묶음의 다른 덩어리와 위아래로 떨어져 있으면 넣는다(「법률*」의 별표는 」 위에 있다).
    """
    line_height = line_bottom - line_top + 1
    if not runs:
        return []
    placed = [(char, center * per_step) for char, center in pieces if char != " "]
    claimed = set()
    for _, x in placed:
        gaps = [0 if a <= x <= b else min(abs(x - a), abs(x - b)) for a, b in runs]
        nearest = int(np.argmin(gaps))
        if gaps[nearest] <= CLAIM_REACH * line_height:
            claimed.add(nearest)
    found = []
    for index, (start, stop) in enumerate(runs):
        if index in claimed or stop - start + 1 < MIN_WIDTH_PX or not _tall_enough(ink, (start, stop), line_height):
            continue
        if any(a <= stop and start <= b for a, b in used):
            continue
        if any(char in BRACKET_PIECES and start - CLAIM_REACH * line_height <= x <= stop + CLAIM_REACH * line_height for char, x in placed):
            continue
        prev = next((char for char, x in reversed(placed) if x < start), "")
        following = next((char for char, x in placed if x > stop), "")
        if _between(prev, following):
            continue
        glyphs = list(components(ink, (start + stop) // 2, (stop - start) // 2 + 1))
        for glyph, top, bottom, left in glyphs:
            if any(t <= bottom and top <= b for g, t, b, l in glyphs if l != left or t != top):
                continue   # 같은 열 범위에 위아래로 겹치는 다른 덩어리가 있으면 글자의 한 조각이다
            kinds = [b for side in "[]" if (b := _bracket_glyph(glyph, top, bottom, line_top, line_bottom, side, strokes(), True, left, shade))]
            if (len(kinds) == 1 and _alone(ink, glyph, top, left)
                    and _hugs_content(ink, kinds[0], left, left + glyph.shape[1] - 1, line_height)):
                found.append((kinds[0], left + (glyph.shape[1] - 1) / 2))
    return found


def restore_corner_brackets(pieces, crop, steps, width):
    """[(글자, CTC 위치)]에서 화면 모양이 낫표·겹낫표·렌즈 괄호인 조각을 바꾸고 건너뛴 낫표·겹낫표를 넣는다.

    바꿀 것이 없으면 받은 목록을 그대로 돌려준다.
    """
    if width <= 0 or not pieces:
        return pieces
    ink = ink_mask(crop, THIN_INK_FRACTION)
    rows = np.flatnonzero(ink.any(axis=1))
    if rows.size == 0:
        return pieces
    line_top, line_bottom = int(rows[0]), int(rows[-1])
    line_height = line_bottom - line_top + 1
    flipped = ink[::-1, ::-1]
    text_rows = np.flatnonzero(ink.any(axis=1) & (ink.mean(axis=1) < RULE_FILL))
    text_top, text_bottom = (int(text_rows[0]), int(text_rows[-1])) if text_rows.size else (line_top, line_bottom)
    memo = []

    def strokes():
        if not memo:
            memo.append(_stroke_widths(ink))
        return memo[0]
    per_step = width / steps
    xs = [center * per_step for char, center in pieces if char != " "]
    shade_memo = []

    def shade():
        """(회색 농도 0~1, 줄 글자 세로획 퍼짐). 홑낫표 모양을 찾았을 때만 잰다."""
        if not shade_memo:
            diff, peak = ink_level(crop)
            gray = diff / peak if peak > 0 else diff
            shade_memo.append((gray, _stroke_spread(ink, gray, line_height)))
        return shade_memo[0]

    def corner(char, x):
        found = _corner_near(ink, x, line_top, line_bottom, char, strokes(), shade)
        if found:
            return found
        if _tall_double_near(ink, x, line_top, line_bottom, char, strokes()):
            return DOUBLES[CORNERS[char]]
        if char == "[":
            return CORNERS[char] if _stem_corner(ink, x, line_top, line_height) else None
        stem = _stem_corner(flipped, ink.shape[1] - 1 - x, ink.shape[0] - 1 - line_bottom, line_height)
        return CORNERS[char] if stem else None

    runs = _column_runs(ink)
    text_height = text_bottom - text_top + 1
    out, changed, used = [], False, []
    for index, (char, center) in enumerate(pieces):
        x = int(center * per_step)
        new = char
        if char in CORNERS:
            new = corner(char, x) or char
            if new == char and not _latin_inside(pieces, index, char) and _lens_near(ink, x, line_height, char):
                new = LENSES[char]
        elif char in LOOK_ALIKES and not _between(_neighbor(pieces, index, -1), _neighbor(pieces, index, 1)):
            reach = max(1, round(OWN_REACH * text_height))
            if any(max(0, a - x, x - b) <= reach and _tall_enough(ink, (a, b), text_height) for a, b in runs):
                others = [other for other in xs if abs(other - center * per_step) > 1e-6]
                found = _own_bracket(ink, x, others, text_top, text_bottom, strokes(), shade)
                if found:
                    new = found[0]
                    used.append(found[1:])
        changed |= new != char
        out.append((new, center))
    for kind, x in _skipped(ink, runs, pieces, per_step, text_top, text_bottom, strokes, used, shade):
        out.append((kind, x / per_step))
        changed = True
    return sorted(out, key=lambda piece: piece[1]) if changed else pieces
