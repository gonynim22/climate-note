"""기운 스캔본을 바로 세운다. Qt를 쓰지 않고 numpy만 쓴다.

글자를 복사할 수 없는 스캔본에서 글자 따기를 쓰는 일이 많은데, 스캔한 쪽은 1~2도쯤 기운다. 글자 상자는 축에 맞춘 사각형이라
줄이 기울면 상자에 윗줄·아랫줄이 끼어 1도면 글자 오류가 2배, 2도면 6배가 된다. 위치 찾기가 낸 글자 덩어리로 기울기를 재고,
멀쩡한 화면은 픽셀 하나 건드리지 않도록 줄이 분명히 더 또렷해질 때만 돌린다. 판단 근거는 docs/SCREEN_TEXT.md를 따른다.
"""
import math

import numpy as np

from screen_text.leading_symbols import ink_mask

SKEW_RANGE = 5              # 찾는 기울기의 상한(도)
SKEW_COARSE = 0.25          # 먼저 훑는 간격(도)
SKEW_FINE = 0.05            # 좁혀서 찾는 간격(도)
SKEW_MIN = 0.2              # 이보다 덜 기운 것은 돌리지 않는다
SKEW_LINE_GAIN = 1.12       # 화면 전체의 글자·선 윤곽이 이만큼 또렷해지면 그 각도를 믿는다
SKEW_TALL = 6               # 영역 높이가 가장 높은 덩어리의 이 배수 이상이면 여러 줄이다. 한두 줄을 고른 영역은 칸 둘로도 각도가 생긴다
SKEW_TEXT_AGREES = 1.01     # 그때 글자 덩어리도 이만큼은 또렷해져야 한다. 그림 속의 비스듬한 선을 거른다
SKEW_LINE_SHAPE = 0.98      # 덩어리 하나하나는 이 아래로 나빠지면 안 된다. 칸이 어긋난 표는 윤곽만 좋아지고 낱말은 기운다
SKEW_MIN_DROP = 0.5         # 글자 영역 폭에서 생기는 낙차의 하한(덩어리 높이 대비). 이보다 작으면 상자가 이웃 줄을 끌어들이지 않는다
SKEW_MIN_GAIN = 1.03        # 글자 줄 윤곽이 이만큼 또렷해져야 돌린다
SKEW_MIN_SHAPE = 1.002      # 덩어리 자신도 이만큼 또렷해져야 한다. 떨어진 낱말 둘이 우연히 한 줄에 놓이는 각도를 거른다
SKEW_SHORT_SHAPE = 1.02     # 한두 줄만 고른 영역은 더 분명해야 한다
SKEW_MIN_PIXELS = 40
SKEW_MAX_PIXELS = 30000     # 재는 데 쓰는 픽셀 수의 상한
SKEW_MIN_AREA = 12          # 이보다 작은 덩어리는 기울기를 말해 주지 못한다
ROTATE_CHUNK = 512          # 한 번에 돌리는 행 수. 큰 이미지에서 메모리를 아낀다


def _pixels(components):
    """label_components의 덩어리를 픽셀 좌표와 덩어리 번호로 푼다."""
    rows, starts, ends, owners, heights = [], [], [], [], []
    for x0, y0, x1, y1, runs in components:
        if (x1 - x0 + 1) * (y1 - y0 + 1) < SKEW_MIN_AREA:
            continue
        heights.append(y1 - y0 + 1)
        for row, start, end in runs:
            rows.append(row)
            starts.append(start)
            ends.append(end)
            owners.append(len(heights) - 1)
    if not rows:
        return None
    rows, starts, ends, owners = (np.array(values, dtype=np.int64) for values in (rows, starts, ends, owners))
    lengths = ends - starts + 1
    first = np.cumsum(np.concatenate(([0], lengths[:-1])))
    xs = np.arange(lengths.sum()) - np.repeat(first, lengths) + np.repeat(starts, lengths)
    return np.repeat(rows, lengths), xs, np.repeat(owners, lengths), float(np.median(heights)), max(heights)


def _sharpness(ys, xs, degrees, owners=None):
    """각도만큼 민 뒤 행별 픽셀 수의 제곱 합. 줄이 수평이 될수록 행에 몰려 커진다. owners를 주면 덩어리마다 따로 센다."""
    rows = np.rint(ys + xs * math.tan(math.radians(degrees))).astype(np.int64)
    rows -= rows.min()
    if owners is not None:
        rows = rows + owners * (int(rows.max()) + 1)
    counts = np.bincount(rows).astype(np.float64)
    return float((counts * counts).sum())


def _best_angle(ys, xs):
    """줄 윤곽이 가장 또렷해지는 각도. 멀쩡한 화면은 정확히 0에서 가장 또렷하다."""
    reach = round(SKEW_RANGE / SKEW_COARSE)
    coarse = max((step * SKEW_COARSE for step in range(-reach, reach + 1)), key=lambda degrees: _sharpness(ys, xs, degrees))
    reach = round(SKEW_COARSE / SKEW_FINE)
    return max((coarse + step * SKEW_FINE for step in range(-reach, reach + 1)), key=lambda degrees: _sharpness(ys, xs, degrees))


def _sampled(ys, xs, owners=None):
    stride = max(1, ys.size // SKEW_MAX_PIXELS)
    ys, xs = ys[::stride].astype(np.float64), xs[::stride].astype(np.float64)
    return ys, xs - xs.mean(), None if owners is None else owners[::stride]


def ink_pixels(image):
    """화면 전체의 글자·선 픽셀 좌표(np.nonzero 결과). 기울기를 잴 때 쓴다."""
    return np.nonzero(ink_mask(image))


def skew_angle(components, image, ink=None):
    """글자 덩어리와 화면의 선으로 잰 기울기(도, 오른쪽이 올라가면 양수). 돌릴 만큼 분명하지 않으면 0.0.

    표 선이 있으면 선이 가장 정확하다. 글자가 드문 표는 칸끼리 우연히 맞는 각도가 있어 덩어리만으로는 틀린다. 다만 그림 속의 비스듬한
    선을 따라가지 않도록 글자도 그 각도에서 나빠지지 않을 때만 믿는다. 선이 없으면 글자 줄이 분명히 또렷해질 때만 돌린다.
    ink는 ink_pixels(image)를 돌려주는 함수다(위치 찾기 모델이 도는 동안 미리 잰 것을 쓴다). 없으면 여기서 잰다.
    """
    found = _pixels(components)
    if found is None or found[0].size < SKEW_MIN_PIXELS:
        return 0.0
    ys, xs, owners = _sampled(*found[:3])
    flat = _sharpness(ys, xs, 0)
    ink = ink_pixels(image) if ink is None else ink()
    tall = image.shape[0] >= SKEW_TALL * found[4]
    if tall and ink[0].size >= SKEW_MIN_PIXELS:
        ink_ys, ink_xs, _ = _sampled(*ink)
        lined = _best_angle(ink_ys, ink_xs)
        if (abs(lined) >= SKEW_MIN and _sharpness(ink_ys, ink_xs, lined) >= SKEW_LINE_GAIN * _sharpness(ink_ys, ink_xs, 0)
                and _sharpness(ys, xs, lined) >= SKEW_TEXT_AGREES * flat
                and _sharpness(ys, xs, lined, owners) >= SKEW_LINE_SHAPE * _sharpness(ys, xs, 0, owners)):
            return round(lined, 2)
    best = _best_angle(ys, xs)
    if abs(best) < SKEW_MIN or _sharpness(ys, xs, best) < SKEW_MIN_GAIN * flat:
        return 0.0
    if (xs.max() - xs.min()) * math.tan(math.radians(abs(best))) < SKEW_MIN_DROP * found[3]:
        return 0.0
    shape = SKEW_MIN_SHAPE if tall else SKEW_SHORT_SHAPE
    return round(best, 2) if _sharpness(ys, xs, best, owners) >= shape * _sharpness(ys, xs, 0, owners) else 0.0


def straighten(image, degrees):
    """기운 이미지를 바로 세운다. 모서리가 잘리지 않게 캔버스를 넓히고 빈 곳은 둘레 색으로 채운다."""
    height, width = image.shape[:2]
    cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    out_width = math.ceil(width * cos + height * abs(sin))
    out_height = math.ceil(height * cos + width * abs(sin))
    color = np.median(np.concatenate((image[0], image[-1], image[:, 0], image[:, -1])), axis=0).astype(np.float32)
    out = np.empty((out_height, out_width, 3), dtype=np.uint8)
    us = np.arange(out_width, dtype=np.float32) - (out_width - 1) / 2
    for top in range(0, out_height, ROTATE_CHUNK):
        bottom = min(top + ROTATE_CHUNK, out_height)
        vs = (np.arange(top, bottom, dtype=np.float32) - (out_height - 1) / 2)[:, None]
        xs = (width - 1) / 2 + cos * us + sin * vs
        ys = (height - 1) / 2 - sin * us + cos * vs
        left, upper = np.floor(xs).astype(np.int32), np.floor(ys).astype(np.int32)
        outside = (left < 0) | (upper < 0) | (left >= width - 1) | (upper >= height - 1)
        left, upper = np.clip(left, 0, width - 2), np.clip(upper, 0, height - 2)
        right_share, lower_share = (xs - left)[:, :, None], (ys - upper)[:, :, None]
        above = image[upper, left] * (1 - right_share) + image[upper, left + 1] * right_share
        below = image[upper + 1, left] * (1 - right_share) + image[upper + 1, left + 1] * right_share
        mixed = above * (1 - lower_share) + below * lower_share
        mixed[outside] = color
        out[top:bottom] = np.rint(mixed).astype(np.uint8)
    return out
