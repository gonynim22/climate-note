"""줄 맨 앞 글머리 기호(■ □ ● ◆ ◇ ㅇ ○ • -)를 모양으로 알아본다. Qt를 쓰지 않고 numpy만 쓴다.

인식 모델은 공문서의 글머리 기호를 거의 읽지 못한다(실제 공문서 PDF에서 ■ 94%·□ 100%·ㅇ 55% 누락). 줄(인식 상자)
맨 앞의 글자 픽셀 덩어리가 글자보다 작고 뒤 글자와 떨어져 있으면 모양(속이 찬 정사각/속이 빈 정사각/마름모/
고리/작은 둥근 점/짧은 막대)으로 분류한다. 화면에 있는 모양을 읽을 뿐 글자를 추정하지 않는다. 고리는 ㅇ ◦ ○ o 를 모양으로 다
구별할 수 없어 크기에 따라 'ㅇ'이나 '○'로 내되 확인 필요로 표시한다. 줄 가운데서 모델이 건너뛴 체크박스(□ ■)도
같은 모양 분류로 찾는다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import threading

import numpy as np

INK_MIN_DIFF = 24          # 배경 중앙값과 이만큼(0~255) 달라야 글자 픽셀
INK_PEAK_FRACTION = 0.3    # 그리고 가장 진한 글자 픽셀 차이의 이 비율 이상
THIN_INK_FRACTION = 0.15   # 가는 선으로 된 기호(△ 「)는 화면에서 옅어져 끊기므로 이 비율로 본다
SEARCH_LEFT = 2.5          # 상자 높이의 이 배수만큼 왼쪽(왼쪽 이웃 상자 전까지)에서 기호를 찾는다
SEARCH_RIGHT = 4.0         # 상자 시작에서 상자 높이의 이 배수까지만 본다(기호와 뒤 글자의 간격을 알기에 충분하다)
MIN_SYMBOL_PX = 3          # 이보다 작은 덩어리(마침표·쉼표)는 기호가 아니다
SYMBOL_GAP_RATIO = 0.5     # 기호와 뒤 글자의 간격은 기호 폭의 이 비율(최소 2px) 이상
MIN_SYMBOL_GAP = 2         # 작은 글씨에서는 기호와 뒤 글자가 2px까지 붙는다
FILLED_MIN_FILL = 0.96     # 속이 찬 정사각의 채움(네 꼭짓점 화소를 뺀다. 어긋난 ▪ 는 꼭짓점이 옅어 빠진다). 색 배지는 글자 구멍 때문에 0.95 이하다
FILLED_MIN_HEIGHT = 0.14   # 줄 글자 높이 대비 하한. 크기로는 • 와 ▪ 를 가를 수 없어(둘 다 0.17~0.40) 네모 모서리로 가른다
SQUARE_CORNERS = 0.9       # 네모 모서리 비율(꼭짓점 진하기 / 그 행·열 진하기의 곱)의 하한. ▪ 1,366개 중 0.9 아래 1개, • 393개 중 0.9 이상 12개(흐린 스캔)
FILLED_MIDDLE = (0.3, 0.7) # 작은 ▪ 와 뒤 글자에 붙은 ▪ 는 줄 가운데에 있다. 줄 아래의 네모난 마침표(Ⅲ.)·쉼표 조각(표 칸의 ,)을 거른다
SMALL_SQUARE = 0.22        # 이 높이 비율 미만은 크기로 • 와 겹치는 작은 네모다. 이보다 크고 뒤 글자와 떨어진 ■ 는 예전처럼 자리를 보지 않는다
SQUARE_FLAT = 0.4          # ▪ 는 속이 고르게 진하다(가장 진한 값의 0.85배 이상인 화소 비율, 3~5px ▪ 218개 중 213개가 이 이상).
                           # 흐린 스캔에서 번진 작은 점은 가운데만 진해(37개 중 35개가 미만) 모서리 비율로는 네모처럼 보인다
LOOSE_GAP_MAX = 0.5        # 모델이 점 글자로 읽은 자리는 뒤 글자와 1px만 떨어져도 기호다(이 높이 비율 이하의 덩어리만)
SQUARE_TIGHT_MAX = 0.42    # 이 높이 비율 이하의 또렷한 네모는 뒤 글자와 1px만 떨어져도 ▪ 다(100% 배율 공문서의 ▪ 는 간격이 1px.
                           # 모양 조건을 다 통과하고 간격만 모자란 덩어리 53개 중 50개가 ▪ 였다). 이보다 큰 덩어리는 예전처럼 떨어져야 한다
OUTSIDE_REACH = 0.25       # 상자 밖으로 상자 높이의 이 비율만큼 계속 이어지면 기호가 아니라 줄 옆의 배지·그림이다
TIP_SIZE = 0.1             # 꼭짓점 칸의 크기(덩어리 폭·높이 대비). 네모는 여기까지 차 있고 고리·마름모는 비어 있다
SQUARE_TIPS = 0.75         # 네 꼭짓점 칸 중 이만큼 차 있으면 속이 빈 정사각(실측 □ 82개 모두 1.0, 고리 약 370개 중 예외 2개)
BIG_RING_RATIO = 0.72      # 고리가 줄 글자 높이의 이 비율 이상이면 자모 ㅇ(실측 0.65 이하)보다 커서 ○로 낸다
DIAMOND_CORNERS = 0.06     # 마름모는 네 모서리가 비어 있다
SOLID_CENTER = 0.9         # 속이 찬 원·마름모의 가운데 채움
ROUND_TIPS = 0.25          # 속이 찬 원·마름모의 꼭짓점 칸은 비어 있다
CIRCLE_MIN_FILL = 0.66     # 원의 채움 하한(π/4). 마름모는 1/2 안팎이다
DIAMOND_MIN_FILL = 0.4
SOLID_HEIGHT = (0.5, 0.85) # 속이 찬 원·마름모 높이(줄 글자 높이 대비). 더 작으면 '•'나 '*'이고 더 크면 글자 하나다('응'이 ◆로 보였다)
SOLID_MIDDLE = (0.3, 0.7)  # 줄 위(0)~아래(1)에서 가운데 자리. '*'은 위에 붙는다
SOLID_MIRROR = 0.86        # 좌우 대칭의 하한
DIAMOND_TOP = 0.4          # 마름모의 맨 윗줄은 좁다(작은 글씨의 고리는 위가 평평해 모서리만으로는 마름모처럼 보인다)
DASH_MAX_HEIGHT = 0.22     # '-' 막대 굵기는 줄 글자 높이의 이 비율 이하(실측 0.05~0.20)
DASH_MIN_WIDTH = 0.15      # '-' 막대 길이는 줄 글자 높이의 이 비율 이상(실측 0.22~0.52). 점보다 길고
DASH_MAX_WIDTH = 0.6       # 이 비율 이하다. 표 선은 훨씬 길다
DASH_MIDDLE = (0.4, 0.72)  # 줄 위(0)~아래(1)에서 막대 가운데의 자리(실측 0.47~0.68). 밑줄과 윗줄을 거른다
DASH_MIN_FILL = 0.7
DASH_GAP_RATIO = 0.75      # 뒤 글자와 막대 길이의 이 비율 이상 떨어져야 한다(실측 1.0 이상). 음수 기호는 붙어 있다
DOT_MIN_HEIGHT = 0.14      # '•' 는 줄 글자 높이의 이 비율 이상(실측 0.17~0.36). 가운뎃점은 0.13 이하다
DOT_MAX_HEIGHT = 0.4       # 이 비율 이하(엣지·한글·스캔의 • 는 0.25~0.36이다). ● 는 0.5 이상이다
DOT_MIN_PX = 2             # 100% 배율의 '•' 는 2~3px이다
DOT_ASPECT = (0.7, 1.5)
DOT_MIN_FILL = 0.6         # 둥근 점은 글자 픽셀로 보면 꼭짓점이 빠진다(4px 0.75, 5px 0.76~0.84)
DOT_MIDDLE = (0.3, 0.7)    # 줄 위(0)~아래(1)에서 점 가운데의 자리. 마침표(0.9)와 위 점을 거른다
CHECKBOX_MIN_HEIGHT = 0.6  # 줄 안 체크박스는 줄 글자 높이의 이 비율 이상(실측 0.79~0.93. ㄱ ㄷ 왼쪽 획은 0.71 이하이고 뒤 글자에 붙는다)
CHECKBOX_MIN_PX = 6        # 이보다 작으면 마침표·가운뎃점이 네모로 보이는 크기다
MODEL_SURE = 0.8           # 한 글자 상자를 모델이 이만큼 확신해 한글로 읽었으면 기호로 바꾸지 않는다(실측 기호를 한글로 잘못 읽은 상자 0.17~0.60, 스캔에서 번진 진짜 글자 0.93~1.00)
FILLED = "■"
FILLED_CIRCLE = "●"
FILLED_DIAMOND = "◆"
HOLLOW_SQUARE = "□"
DIAMOND = "◇"
RING = "ㅇ"
BIG_RING = "○"
RINGS = frozenset((RING, BIG_RING))   # 모양으로 ㅇ ◦ ○ o 를 다 가를 수 없어 확인 필요로 표시한다
DASH = "-"
DOT = "•"
# 모델이 기호를 닮은 글자로 읽었을 때 교체해도 되는 첫 글자
CONFUSABLE = frozenset("0oOㅇCcD.:-·•□■▪○●ㅁ")
# 모델이 이 글자로 읽었으면 그 자리에 작은 기호가 따로 있다
DOT_LIKE = frozenset("·•∙ㆍ‧▪")
# '-' 자리에 이 글자가 있으면 모델이 이미 읽은 것이다. 판독을 그대로 둔다
DASH_LIKE = frozenset("-‐‑–—−~ㅡ一_")
# 작은 점 모양 덩어리 자리에 모델이 이 글자를 읽었으면 그 글자다. 흐린 스캔의 * + 는 볼록해져 점처럼 보인다(• * 기상예보)
STAR_LIKE = frozenset("*＊∗⁎✱+×※")


def _gray(pixels):
    return pixels.astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def median(values):
    """np.median과 같은 값. float32 배열은 같은 계산을 준비 비용 없이 한다(작은 배열을 수만 번 재는 표 선 찾기에서 컸다).

    np.median처럼 가운데 두 값의 float32 합을 반으로 나누고, NaN이 있으면 NaN을 낸다.
    """
    flat = np.asarray(values).ravel()
    size = flat.size
    if flat.dtype != np.float32 or size == 0:
        return np.median(flat)
    half = size // 2
    part = np.partition(flat, (half, -1) if size % 2 else (half - 1, half, -1))
    if np.isnan(part[-1]):
        return part[-1]
    return part[half] if size % 2 else (part[half - 1] + part[half]) / np.float32(2)


def row_medians(band):
    """np.median(band, axis=1)과 같은 값. float32 2차원 배열은 np.median과 같은 연산(가운데 값의 평균)을 직접 한다."""
    rows, size = band.shape
    if band.dtype != np.float32 or rows == 0 or size == 0:
        return np.median(band, axis=1)
    half = size // 2
    part = np.partition(band, (half, -1) if size % 2 else (half - 1, half, -1), axis=1)
    middle = np.mean(part[:, half:half + 1] if size % 2 else part[:, half - 1:half + 1], axis=1)
    missing = np.isnan(part[:, -1])
    if missing.any():
        middle[missing] = part[missing, -1]
    return middle


_shared = threading.local()


class shared_ink:
    """이 블록 안에서 같은 crop(같은 메모리·모양·간격)의 글자 픽셀 기준을 한 번만 잰다.

    인식 상자 하나에 규칙 열 개 남짓이 같은 crop의 ink_mask를 거듭 불렀다. 잰 crop을 블록 끝까지 쥐고 있어 그 메모리를 다른
    배열이 다시 쓸 수 없고, 블록 안에서는 화면 이미지를 바꾸지 않으므로 같은 값이 나온다. 블록을 벗어나면 버린다.
    """

    def __enter__(self):
        self._outer = getattr(_shared, "memo", None)
        _shared.memo = {}
        return self

    def __exit__(self, *_):
        _shared.memo = self._outer
        return False


def ink_level(crop):
    """회색이 배경(중앙값)과 다른 정도(float32 배열)와 그 최대. shared_ink 블록 안에서는 같은 crop을 한 번만 잰다."""
    memo = getattr(_shared, "memo", None)
    if memo is not None:
        key = (crop.__array_interface__["data"][0], crop.shape, crop.strides, crop.dtype.str)
        found = memo.get(key)
        if found is not None:
            return found[1], found[2]
    gray = _gray(crop)
    if gray.size == 0:
        diff, peak = gray, 0.0
    else:
        diff = np.abs(gray - median(gray))
        peak = float(diff.max())
    if memo is not None:
        memo[key] = (crop, diff, peak)
    return diff, peak


def ink_mask(crop, fraction=INK_PEAK_FRACTION):
    """배경(중앙값 색)과 충분히 다른 글자 픽셀. 옅은 잡음은 글자로 세지 않는다."""
    diff, peak = ink_level(crop)
    if diff.size == 0 or peak <= 0:  # 아주 좁은 칸은 표 선을 빼면 남는 픽셀이 없다
        return np.zeros(diff.shape, dtype=bool)
    return diff > max(INK_MIN_DIFF, fraction * peak)


def _blobs(ink, reference_height=0, limit=4, thin=None, level=None):
    """왼쪽부터 이어진 글자 열 묶음(덩어리)의 모양 특징. 높이 비율은 줄 글자 높이(기호만 든 상자는 이웃 상자의 글자 높이)에 견준다.

    thin은 옅은 픽셀까지 본 마스크다. 작은 고리는 획이 옅어 끊겨 보이므로 트였는지는 이것으로 잰다.
    level은 같은 자리의 회색 진하기(ink_level)다. 작은 점이 둥근지 네모인지는 글자 픽셀이 아니라 진하기로 잰다.
    """
    columns = np.flatnonzero(ink.any(axis=0))
    rows = np.flatnonzero(ink.any(axis=1))
    if columns.size == 0:
        return []
    height = max(int(rows[-1] - rows[0] + 1), reference_height)
    runs, start, previous = [], columns[0], columns[0]
    for column in columns[1:]:
        if column != previous + 1:
            runs.append((start, previous))
            start = column
        previous = column
    runs.append((start, previous))
    blobs = []
    for k, (a, b) in enumerate(runs[:limit]):
        blob = ink[:, a:b + 1]
        occupied = np.flatnonzero(blob.any(axis=1))
        blob = blob[occupied[0]:occupied[-1] + 1]
        blob_h, blob_w = blob.shape
        outline = blob if thin is None else thin[:, a:b + 1][occupied[0]:occupied[-1] + 1]
        shade = blob if level is None else level[:, a:b + 1][occupied[0]:occupied[-1] + 1]
        blobs.append(_Blob(blob, outline, shade, width=blob_w, height=blob_h, relative_height=blob_h / height, line_height=height,
                           left=int(a), right=int(b), top=int(occupied[0]), bottom=int(occupied[-1]),
                           middle=((occupied[0] + occupied[-1]) / 2 - rows[0]) / max(1, rows[-1] - rows[0]),
                           gap=int(runs[k + 1][0] - b - 1) if k + 1 < len(runs) else 10 ** 6))
    return blobs


class _Blob(dict):
    """덩어리 하나의 특징. 모양 특징(채움·꼭짓점·대칭 등)은 처음 찾을 때 잰다.

    줄 안 체크박스 찾기는 덩어리 대부분을 크기만 보고 거른다. 모든 덩어리의 모양을 미리 재던 것이 상자마다 수백 번이었다(2026-11-09).
    """

    def __init__(self, blob, outline, shade, **sizes):
        super().__init__(sizes)
        self._blob, self._outline, self._shade = blob, outline, shade

    def __missing__(self, key):
        if "fill" in self:
            raise KeyError(key)
        self.update(_shape_features(self._blob, self._outline, self._shade))
        return dict.__getitem__(self, key)


def _square_corners(shade):
    """네모 모서리 비율: 네 꼭짓점 진하기를 그 행 안쪽과 열 안쪽 진하기의 곱으로 나눈 평균(3px 미만이면 0).

    정사각은 화소에 어긋나 놓여도 꼭짓점 진하기가 두 변의 진하기 곱이라(흐려도 가로·세로로 나뉘어 번진다) 1 안팎이고,
    둥근 점은 꼭짓점이 비어 0.85 아래다.
    """
    rows, columns = shade.shape
    if rows < 3 or columns < 3:
        return 0.0
    box = shade.astype(np.float32) / max(float(shade.max()), 1e-6)
    total = 0.0
    for y, x in ((0, 0), (0, -1), (-1, 0), (-1, -1)):
        total += float(box[y, x]) / max(float(box[y, 1:-1].mean()) * float(box[1:-1, x].mean()), 1e-3)
    return total / 4


def _flat_top(shade):
    """가장 진한 값의 0.85배 이상인 화소 비율. 또렷한 네모는 속이 고르고, 번진 점은 가운데만 진하다."""
    peak = float(shade.max())
    return float((shade >= .85 * peak).mean()) if peak > 0 else 0.0


def _convex(shade):
    """가장 진한 값의 반 이상인 화소가 행마다·열마다 한 토막인가. 별표(*)는 팔 사이가 비어 끊긴다(• 392개 모두 한 토막)."""
    on = shade >= .5 * shade.max()
    starts_in_rows = on & ~np.pad(on, ((0, 0), (1, 0)))[:, :-1]
    starts_in_columns = on & ~np.pad(on, ((1, 0), (0, 0)))[:-1]
    return bool(starts_in_rows.sum(axis=1).max(initial=0) <= 1 and starts_in_columns.sum(axis=0).max(initial=0) <= 1)


def _shape_features(blob, outline, shade):
    """덩어리 모양 특징. blob은 위아래를 잘라 낸 글자 픽셀, outline은 트였는지 잴 옅은 픽셀까지 본 같은 자리, shade는 그 자리의 진하기다."""
    blob_h, blob_w = blob.shape
    qw, qh = max(1, round(blob_w * .25)), max(1, round(blob_h * .25))
    corners = float(np.mean([blob[:qh, :qw].mean(), blob[:qh, -qw:].mean(),
                             blob[-qh:, :qw].mean(), blob[-qh:, -qw:].mean()]))
    cy0, cx0 = int(blob_h * .3), int(blob_w * .3)
    center = float(blob[cy0:max(cy0 + 1, int(blob_h * .7)), cx0:max(cx0 + 1, int(blob_w * .7))].mean())
    row, column = outline[blob_h // 2], outline[:, blob_w // 2]
    closed = bool(row[:blob_w // 2].any() and row[blob_w // 2 + 1:].any() and column[:blob_h // 2].any() and column[blob_h // 2 + 1:].any())
    th, tw = max(1, round(blob_h * TIP_SIZE)), max(1, round(blob_w * TIP_SIZE))
    tips = float(np.mean([blob[:th, :tw].any(), blob[:th, -tw:].any(), blob[-th:, :tw].any(), blob[-th:, -tw:].any()]))
    one_sided = bool(blob[:th, :tw].any() and blob[-th:, :tw].any() and not blob[:th, -tw:].any() and not blob[-th:, -tw:].any())
    core = blob.sum() - int(blob[0, 0]) - int(blob[0, -1]) - int(blob[-1, 0]) - int(blob[-1, -1])   # 네 꼭짓점을 뺀 채움
    core_fill = float(core / max(1, blob.size - 4)) if blob_h >= 3 and blob_w >= 3 else float(blob.mean())
    return dict(fill=float(blob.mean()), center=center, corners=corners, tips=tips, one_sided=one_sided, closed=closed,
                mirror=float((blob == blob[:, ::-1]).mean()), top_span=float(blob[0].mean()), core_fill=core_fill,
                square=_square_corners(shade), flat=_flat_top(shade), convex=_convex(shade))


def _is_rule(blob):
    """표 테두리·괄호처럼 가늘고 긴 덩어리."""
    return blob["width"] / max(blob["height"], 1) < .4 and blob["relative_height"] >= .6


def _is_dash(blob):
    """줄 가운데쯤의 짧고 납작한 막대. 표 선·밑줄은 길이와 자리로, 음수 기호는 뒤 글자와의 간격으로 걸러진다."""
    width, height, line = blob["width"], blob["height"], blob["line_height"]
    return (width >= 2 * height and height <= DASH_MAX_HEIGHT * line
            and DASH_MIN_WIDTH * line <= width <= DASH_MAX_WIDTH * line
            and DASH_MIDDLE[0] <= blob["middle"] <= DASH_MIDDLE[1] and blob["fill"] >= DASH_MIN_FILL
            and blob["gap"] >= max(3, DASH_GAP_RATIO * width))


def _loose(blob, loose):
    """모델이 그 자리를 점 글자로 읽었으면(loose) 작은 덩어리는 뒤 글자와 1px만 떨어져도 된다."""
    return loose and blob["gap"] >= 1 and blob["relative_height"] <= LOOSE_GAP_MAX


def _is_filled_square(blob, loose=False):
    """속이 찬 정사각(■ ▪). 크기가 아니라 모양(네 꼭짓점까지 찬 네모)으로 둥근 점과 가른다."""
    width, height, relative = blob["width"], blob["height"], blob["relative_height"]
    if width < MIN_SYMBOL_PX or height < MIN_SYMBOL_PX:
        return False
    apart = blob["gap"] >= max(MIN_SYMBOL_GAP, int(SYMBOL_GAP_RATIO * width))
    if not apart and not _loose(blob, loose) and not (blob["gap"] >= 1 and relative <= SQUARE_TIGHT_MAX):
        return False
    return (blob["core_fill"] >= FILLED_MIN_FILL and blob["center"] >= .9 and .7 <= width / height <= 1.4
            and FILLED_MIN_HEIGHT <= relative <= 1.05 and blob["square"] >= SQUARE_CORNERS and blob["flat"] >= SQUARE_FLAT
            and ((apart and relative >= SMALL_SQUARE) or FILLED_MIDDLE[0] <= blob["middle"] <= FILLED_MIDDLE[1]))


def _is_dot(blob, loose=False):
    """줄 가운데쯤의 작은 둥근 점. 가운뎃점보다 크다. 네모(▪)는 먼저 걸렀고, 반 진하기에서 볼록해야 한다(별표 * 는 끊긴다)."""
    return (DOT_MIN_PX <= min(blob["width"], blob["height"]) and DOT_MIN_HEIGHT <= blob["relative_height"] <= DOT_MAX_HEIGHT
            and DOT_ASPECT[0] <= blob["width"] / blob["height"] <= DOT_ASPECT[1] and blob["fill"] >= DOT_MIN_FILL
            and DOT_MIDDLE[0] <= blob["middle"] <= DOT_MIDDLE[1]
            and (blob["gap"] >= max(2, blob["width"]) or _loose(blob, loose)) and blob["convex"])


def _classify(blob, loose=False):
    if _is_dash(blob):
        return DASH
    if _is_filled_square(blob, loose):
        return FILLED
    if _is_dot(blob, loose):
        return DOT
    if (blob["width"] < MIN_SYMBOL_PX or blob["height"] < MIN_SYMBOL_PX
            or blob["gap"] < max(MIN_SYMBOL_GAP, int(SYMBOL_GAP_RATIO * blob["width"]))):
        return None
    aspect = blob["width"] / blob["height"]
    relative = blob["relative_height"]
    if (blob["center"] >= SOLID_CENTER and blob["tips"] <= ROUND_TIPS and .8 <= aspect <= 1.25 and blob["mirror"] >= SOLID_MIRROR
            and SOLID_HEIGHT[0] <= relative <= SOLID_HEIGHT[1] and SOLID_MIDDLE[0] <= blob["middle"] <= SOLID_MIDDLE[1]
            and blob["fill"] >= DIAMOND_MIN_FILL):
        return FILLED_CIRCLE if blob["fill"] >= CIRCLE_MIN_FILL else FILLED_DIAMOND
    if blob["closed"] and blob["center"] <= .1 and .75 <= aspect <= 1.3 and relative >= .15:  # 'C n u'는 가운데가 비어도 한쪽이 트였다
        if blob["tips"] >= SQUARE_TIPS:
            return HOLLOW_SQUARE
        if blob["one_sided"]:   # 왼쪽 두 모서리만 찬 'D'. 엑셀 열 머리글 D 가 ○ 로 나왔다
            return None
        if blob["corners"] <= DIAMOND_CORNERS and relative >= .5 and blob["top_span"] <= DIAMOND_TOP:
            return DIAMOND
        return BIG_RING if relative >= BIG_RING_RATIO else RING
    return None


def _checkbox(blob, left_gap):
    """줄 안의 체크박스(□ ■)면 그 기호. 글자 크기에 가깝고 양옆이 충분히 비어 있어야 글자의 획이나 문장 부호가 아니다."""
    if (blob["height"] < CHECKBOX_MIN_PX or blob["relative_height"] < CHECKBOX_MIN_HEIGHT
            or left_gap < max(3, SYMBOL_GAP_RATIO * blob["width"])):
        return None
    kind = _classify(blob)
    return kind if kind in (FILLED, HOLLOW_SQUARE) else None


def restore_inline_checkboxes(pieces, crop, steps, width):
    """[(글자, 중심 단계)]에 모델이 건너뛴 줄 안 체크박스를 끼워 넣는다. 그 자리에 모델이 낸 글자가 있으면 건드리지 않는다.

    양식의 '시 □ 군 ■ 구'처럼 한 상자 안에 든 체크박스가 대상이다. 표 선을 뺀 첫 덩어리는 줄 맨 앞이라
    leading_symbol이 맡고, '동의 □'처럼 항목 뒤에 오는 경우가 있어 마지막 글자 뒤는 본다. 화면의 모양만 읽는다.
    """
    if not pieces or width <= 0:
        return pieces
    read = [center for char, center in pieces if char != " "]
    per_pixel = steps / width
    out, previous_right = list(pieces), None
    for blob in _blobs(ink_mask(crop), limit=10 ** 6, level=ink_level(crop)[0]):
        if _is_rule(blob):
            continue
        kind = _checkbox(blob, blob["left"] - previous_right - 1) if previous_right is not None else None
        previous_right = blob["right"]
        low, high = blob["left"] * per_pixel - 1, blob["right"] * per_pixel + 1
        if kind and not any(low <= center <= high for center in read):
            out.append((kind, (low + high) / 2))
    return sorted(out, key=lambda piece: piece[1])


def _ink_height(image, box):
    """상자 앞부분의 글자 픽셀이 차지하는 세로 높이(글자 없으면 0)."""
    x0, y0, x1, y1 = box
    rows = np.flatnonzero(ink_mask(image[y0:y1, x0:min(x1, x0 + int(round(SEARCH_RIGHT * (y1 - y0))))]).any(axis=1))
    return int(rows[-1] - rows[0] + 1) if rows.size else 0


def _same_row(a, b):
    return min(a[3], b[3]) - max(a[1], b[1]) >= .5 * min(a[3] - a[1], b[3] - b[1])


def _continues_outside(image, crop, blob, x_from, y0, y1):
    """덩어리가 상자 위나 아래 경계에서 잘려 밖으로 한참 이어지는가. 줄 옆의 색 배지·그림이 그렇다.

    글머리 기호는 줄 안에 든다. 상자가 기호 끝 한 줄을 잘랐거나 바로 옆에 표 선이 있어도 1~2행이면 끝난다.
    """
    background = float(np.median(_gray(crop)))
    a, b = x_from + blob["left"], x_from + blob["right"] + 1
    reach = max(3, int(round(OUTSIDE_REACH * (y1 - y0))))
    outside = ((blob["top"] == 0, range(max(0, y0 - reach), y0)),
               (blob["bottom"] == crop.shape[0] - 1, range(y1, min(image.shape[0], y1 + reach))))
    for touches, rows in outside:
        if touches and len(rows) >= 2 and all(
                (np.abs(_gray(image[row, a:b]) - background) > INK_MIN_DIFF).mean() >= .5 for row in rows):
            return True
    return False


def leading_symbol(image, index, boxes, readable=None, table=None, heights=None, left_bound=0, loose=False):
    """index번 상자의 줄 맨 앞 기호. (종류, 시작 x, 끝 x, 기호만 든 상자인가) 또는 None.

    기호는 상자 안이나 바로 왼쪽에 있을 수 있다. 위치 찾기가 기호를 글자와 따로 상자로 자르기도 하므로(기호만
    든 상자), 높이 비율은 같은 줄 오른쪽 이웃 상자의 글자 높이에 견주고 그 상자는 이 기호를 다시 찾지 않는다.
    readable은 상자별로 모델이 글자를 읽었는지다. 빈 글자로 읽은 상자는 그 안의 기호를 내놓지 못하므로 왼쪽
    탐색을 막지 않는다(양식의 '□ 시 □ 군 ■ 구'. 기호 일부나 속만 잘린 상자도 있어 그 상자에서 분류하지 않는다).
    table은 boxes의 (개수, 4) float64 배열, heights는 상자 번호별 _ink_height를 담아 둘 사전이다(여러 상자를 차례로 볼 때 한 번씩만 잰다).
    left_bound는 상자가 든 표 칸의 왼쪽 안쪽 x다. 그보다 왼쪽에서 끝나는 덩어리는 다른 칸의 것이다.
    loose는 모델이 상자 맨 앞을 점 글자(DOT_LIKE)로 읽었는가다. 그러면 작은 기호가 뒤 글자에 1px까지 붙어도 된다.
    """
    box = boxes[index]
    x0, y0, x1, y1 = box
    height = y1 - y0
    left_x, top_y, right_x, bottom_y = (np.asarray(boxes, dtype=np.float64).reshape(-1, 4) if table is None else table).T
    same = np.minimum(bottom_y, y1) - np.maximum(top_y, y0) >= .5 * np.minimum(bottom_y - top_y, height)   # _same_row(다른 상자, box)
    same[index] = False
    # 먼저 시작한 같은 줄의 상자(겹치면 그 상자) 몫인 왼쪽은 찾지 않는다
    before = same & (left_x < x0) & (True if readable is None else np.asarray(readable, dtype=bool))
    left_limit = max(0, int((right_x[before] + 1).max())) if before.any() else 0
    x_from = max(left_limit, x0 - int(round(SEARCH_LEFT * height)))
    x_to = min(x1, x0 + int(round(SEARCH_RIGHT * height)))
    if x_to - x_from < 6:
        return None
    heights = {} if heights is None else heights
    after = np.flatnonzero(same & (left_x >= x0) & (left_x - x0 <= 10 * height)).tolist()
    for j in after:
        if j not in heights:
            heights[j] = _ink_height(image, boxes[j])
    reference = max((heights[j] for j in after), default=0)
    crop = image[y0:y1, x_from:x_to]
    blobs = _blobs(ink_mask(crop), reference, thin=ink_mask(crop, THIN_INK_FRACTION), level=ink_level(crop)[0])
    # 표 선 왼쪽은 다른 칸이다. 옆 칸 글자의 조각을 기호로 읽지 않는다. 격자가 아는 칸 경계(left_bound)는 옅은 눈금선처럼
    # 글자 픽셀로 잡히지 않는 선도 지킨다. 자른 그림은 그대로 두어 기호 크기를 견주는 줄 높이를 바꾸지 않는다
    last_rule = max((k for k, blob in enumerate(blobs)
                     if (_is_rule(blob) and x_from + blob["right"] < x0) or x_from + blob["right"] < left_bound), default=-1)
    for blob in blobs[last_rule + 1:]:
        if _is_rule(blob):
            continue
        kind = _classify(blob, loose)
        if kind is None or _continues_outside(image, crop, blob, x_from, y0, y1):
            return None
        alone = blob["gap"] >= 10 ** 6 and x_to == x1  # 상자 안에 이 기호밖에 없다
        return kind, x_from + blob["left"], x_from + blob["right"], alone
    return None


def _cell_left(box, grids):
    """상자 가운데가 든 표 칸의 왼쪽 안쪽 x(표 밖이면 0)."""
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    for grid in grids:
        for cell in grid.cells:
            if cell.left <= x <= cell.right and cell.top <= y <= cell.bottom:
                return int(cell.left)
    return 0


def apply_leading_symbols(image, boxes, results, grids=()):
    """[(글자, 점수)]를 [(글자, 점수, 확인 필요 앞글자 수)]로. 기호가 보이면 앞에 붙이거나(모델이 건너뜀) 닮은 글자를 교체한다.

    grids는 image 좌표의 표 격자다. 표 안의 상자는 제 칸 안에서만 기호를 찾는다. 옆 칸의 체크박스는 그 칸의 표시로
    따로 읽히므로 옅은 눈금선 너머에서 다시 붙이면 두 번 나온다(엣지 표의 '□ □ 정호진', 2026-11-09).
    """
    readable = [bool(text.strip()) for text, _ in results]
    table, heights = np.asarray(boxes, dtype=np.float64).reshape(-1, 4), {}
    out = []
    for index, (text, score) in enumerate(results):
        flagged = 0
        with shared_ink():   # 한 상자의 진한·옅은 글자 픽셀을 같은 기준으로 잰다
            found = (leading_symbol(image, index, boxes, readable, table, heights, _cell_left(boxes[index], grids),
                                    text.lstrip()[:1] in DOT_LIKE) if readable[index] else None)
        if found and found[3] and score >= MODEL_SURE and any("가" <= char <= "힣" for char in text):
            found = None   # 세로로 쓴 칸의 한 글자('해 당 없 음')가 스캔에서 번져 ● ◆ 모양이 됐다. 모델은 확신했다
        if found:
            kind, _, right, alone = found
            body = text.lstrip()
            if (kind == DASH and body[:1] in DASH_LIKE) or (kind == DOT and body[:1] == DOT):  # 모델이 이미 읽었다
                pass
            elif kind == DOT and (body[:1] in DASH_LIKE or body[:1] in STAR_LIKE):   # 흐린 - * 가 점처럼 보였다. 모델 판독이 맞다
                pass
            elif alone:  # 기호만 든 상자: 모델이 읽은 것은 모두 이 기호를 잘못 읽은 것이다
                text = kind
            else:
                if (right >= boxes[index][0] or kind == DOT) and body[:1] in CONFUSABLE:  # 닮은 글자로 읽힌 기호. 작은 점은 상자 경계에 걸린다
                    body = body[1:].lstrip()
                text = f"{kind} {body}" if body else kind
            flagged = int(kind in RINGS)
        out.append((text, score, flagged))
    return out
