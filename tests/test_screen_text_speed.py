"""화면 글자 따기 속도 되찾기(2026-11-09): 빨라진 계산이 v4.8 배포 때와 비트 단위로 같은 값을 내는지 본다.

판독을 바꾸지 않는 최적화만 한다(사용자 결정 2026-11-07 "정확도는 포기 못해"). 아래 _v48_* 함수는 v4.8 배포 코드 그대로다.
"""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from screen_text import engine
from screen_text.engine import _cut_rules, _det_input, add_margin, double_size, resize_bilinear


@pytest.fixture(scope="module")
def pool():
    with ThreadPoolExecutor(4) as executor:
        yield executor


def _v48_resize(image, width, height, rows=None):
    src_h, src_w = image.shape[:2]
    first, last = rows or (0, height)
    if (width, height) == (src_w, src_h):
        return image[first:last].astype(np.float32)
    factor = int(min(src_w / width, src_h / height))
    source = image if image.dtype == np.uint8 else image.astype(np.float32)
    if factor >= 2 and rows:
        return _v48_resize(image, width, height)[first:last]
    if factor >= 2:
        cut_h, cut_w = src_h // factor * factor, src_w // factor * factor
        source = image[:cut_h, :cut_w].astype(np.float32).reshape(cut_h // factor, factor, cut_w // factor, factor, -1).mean(axis=(1, 3))
        src_h, src_w = source.shape[:2]
    ys = np.clip((np.arange(height, dtype=np.float32) + 0.5) * (src_h / height) - 0.5, 0, src_h - 1)
    xs = np.clip((np.arange(width, dtype=np.float32) + 0.5) * (src_w / width) - 0.5, 0, src_w - 1)
    y0, x0 = np.floor(ys).astype(np.int32), np.floor(xs).astype(np.int32)
    y1, x1 = np.minimum(y0 + 1, src_h - 1), np.minimum(x0 + 1, src_w - 1)
    wy, wx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    out = np.empty((last - first, width) + source.shape[2:], dtype=np.result_type(source.dtype, wx.dtype))
    for start in range(first, last, 32):
        band = slice(start, min(start + 32, last))
        upper, lower = source[y0[band]], source[y1[band]]
        top = upper[:, x0] * (1 - wx) + upper[:, x1] * wx
        bottom = lower[:, x0] * (1 - wx) + lower[:, x1] * wx
        out[start - first:band.stop - first] = top * (1 - wy[band]) + bottom * wy[band]
    return out


def _v48_double_size(image):
    def twice(array, axis):
        length = array.shape[axis]
        previous = array.take(np.r_[0, 0:length - 1], axis=axis)
        following = array.take(np.r_[1:length, length - 1], axis=axis)
        shape = list(array.shape)
        shape[axis] = 2 * length
        out = np.empty(shape, dtype=np.uint16)
        slot = [slice(None)] * array.ndim
        slot[axis] = slice(0, None, 2)
        out[tuple(slot)] = (3 * array + previous + 2) >> 2
        slot[axis] = slice(1, None, 2)
        out[tuple(slot)] = (3 * array + following + 2) >> 2
        return out

    return twice(twice(image.astype(np.uint16), 0), 1).astype(np.uint8)


def _v48_cut_rules(image, color):
    ink = np.abs(image.astype(np.int16) - color).max(axis=2) > engine.RIDGE_CONTRAST
    through = ink.all(axis=0)
    rest = np.flatnonzero(ink[:, ~through].any(axis=1))
    if rest.size and image.shape[0] - (rest[-1] - rest[0] + 1) < engine.RULE_PAST_TEXT:
        return np.empty(0, dtype=np.intp)
    return np.flatnonzero(through)


def _v48_det_tensor(small, color, rows, width):
    canvas = np.empty((-(-rows // 32) * 32, -(-width // 32) * 32, 3), dtype=np.float32)
    canvas[:] = color
    canvas[:rows, :width] = small
    bgr = canvas[:, :, ::-1] / 255.0
    bgr -= engine.DET_MEAN
    bgr /= engine.DET_STD
    return np.ascontiguousarray(bgr.transpose(2, 0, 1))[None]


def _page(shape, seed):
    """글자 같은 진한 점과 옅은 바탕이 섞인 그림(값이 0~255 끝까지 나온다)."""
    rng = np.random.default_rng(seed)
    image = rng.integers(200, 256, shape, dtype=np.uint8)
    ink = rng.random(shape[:2]) < 0.15
    image[ink] = rng.integers(0, 120, (int(ink.sum()), shape[2]), dtype=np.uint8)
    return image


RESIZE_CASES = [
    ((50, 70, 3), (35, 25), None),         # 1배와 2배 사이로 줄이기
    ((50, 70, 3), (140, 100), None),       # 키우기
    ((300, 500, 3), (130, 70), None),      # 정수 배(3배) 평균으로 먼저 줄이는 경로
    ((600, 400, 3), (100, 150), None),     # 4배 평균
    ((611, 977, 3), (190, 120), None),     # 5배 평균, 나머지 줄·열 잘림
    ((257, 333, 3), (300, 290), None),     # 여러 줄 묶음에 걸치는 키우기
    ((40, 60, 3), (60, 40), None),         # 크기가 같으면 그대로
    ((2370, 1714, 3), (1389, 1920), None), # 2배로 키운 A4 한 쪽을 위치 찾기 크기로
    ((1144, 1984, 3), (960, 554), None),   # FHD 첫 위치 찾기
    ((257, 333, 3), (300, 290), (37, 201)),
    ((50, 70, 3), (140, 100), (99, 100)),
    ((50, 70, 3), (35, 25), (0, 9)),
    ((40, 60, 3), (60, 40), (5, 33)),
    ((900, 1300, 3), (300, 220), (40, 170)),   # 정수 배 평균 경로의 띠
    ((2288, 3968, 3), (3174, 1830), (499, 1331)),  # 넓은 영역 2배의 둘째 띠
    ((33, 141, 3), (205, 48), None),       # 인식 상자(키우기)
    ((97, 61, 3), (30, 48), None),         # 인식 상자(줄이기)
]


@pytest.mark.parametrize("shape, size, rows", RESIZE_CASES)
def test_resize_bilinear_matches_v48(shape, size, rows, pool):
    image = _page(shape, sum(shape) + size[0])
    want = _v48_resize(image, *size, rows)
    for got in (resize_bilinear(image, *size, rows), resize_bilinear(image, *size, rows, pool)):
        assert got.dtype == want.dtype and got.shape == want.shape
        assert np.array_equal(got, want)


@pytest.mark.parametrize("value", [0, 1, 127, 254, 255])
@pytest.mark.parametrize("factor", [2, 3, 4, 5, 7])
def test_block_mean_is_exact_for_flat_and_extreme_values(value, factor):
    """정수 배 평균은 칸의 합을 정수로 더한다. float32로 더하던 np.mean과 끝값에서도 같아야 한다."""
    image = np.full((factor * 9 + 1, factor * 11 + 2, 3), value, dtype=np.uint8)
    image[::2, ::3] = 255 - value
    size = (image.shape[1] // factor, image.shape[0] // factor)
    assert np.array_equal(resize_bilinear(image, *size), _v48_resize(image, *size))


def test_resize_bilinear_keeps_float_input_path():
    image = np.random.default_rng(3).random((90, 120, 3)).astype(np.float32) * 255
    for size in ((40, 30), (200, 150), (20, 15)):
        assert np.array_equal(resize_bilinear(image, *size), _v48_resize(image, *size))


@pytest.mark.parametrize("shape", [(1, 1, 3), (1, 7, 3), (6, 1, 3), (2, 2, 3), (129, 77, 3), (300, 257, 3), (1185, 857, 3)])
def test_double_size_matches_v48(shape, pool):
    image = _page(shape, shape[0] * 7 + shape[1])
    want = _v48_double_size(image)
    for got in (double_size(image), double_size(image, pool)):
        assert got.dtype == np.uint8 and np.array_equal(got, want)


def test_double_size_reads_strided_views(pool):
    """여백을 두른 이미지의 일부(연속되지 않은 배열)도 같게 키운다."""
    image = _page((260, 390, 3), 5)[3:250:1, 7:300]
    assert np.array_equal(double_size(image, pool), _v48_double_size(image))


def _with_rule(image, column, color):
    image = image.copy()
    image[:, column] = color
    return image


@pytest.mark.parametrize("case", ["plain", "rule", "two_rules", "rule_and_text_to_edges", "white", "dark_rule_on_dark"])
def test_cut_rules_matches_v48(case):
    rng = np.random.default_rng(len(case))
    base = np.full((60, 90, 3), 250, dtype=np.uint8)
    base[20:40, 10:80] = rng.integers(0, 80, (20, 70, 3), dtype=np.uint8)
    image = {
        "plain": base,
        "rule": _with_rule(base, 45, (90, 90, 90)),
        "two_rules": _with_rule(_with_rule(base, 5, (120, 120, 120)), 85, (10, 10, 10)),
        "rule_and_text_to_edges": _with_rule(np.where(np.arange(60)[:, None, None] % 7 == 0, 30, base).astype(np.uint8), 50, (0, 0, 0)),
        "white": np.full((30, 40, 3), 255, dtype=np.uint8),
        "dark_rule_on_dark": _with_rule(np.full((30, 40, 3), 20, dtype=np.uint8), 12, (230, 230, 230)),
    }[case]
    color = np.median(np.concatenate((image[0], image[-1], image[:, 0], image[:, -1])), axis=0).astype(np.uint8)
    got, want = _cut_rules(image, color), _v48_cut_rules(image, color)
    assert got.dtype == want.dtype and np.array_equal(got, want)


def test_add_margin_extends_cut_rules_as_before():
    image = _with_rule(np.full((40, 50, 3), 245, dtype=np.uint8), 20, (60, 60, 60))
    out = add_margin(image, 8)
    assert (out[:8, 28] == 60).all() and (out[-8:, 28] == 60).all() and (out[:8, 27] == 245).all()


def _v48_det_input(image, new_w, new_h, top, bottom):
    """v4.8 _detect_rows의 모델 입력 만들기."""
    whole = (top, bottom) == (0, new_h)
    small = _v48_resize(image, new_w, new_h, None if whole else (top, bottom))
    if whole:
        color = np.median(np.concatenate((small[0], small[-1], small[:, 0], small[:, -1])), axis=0)
    else:
        color = np.median(np.concatenate((image[0], image[-1], image[:, 0], image[:, -1])), axis=0)
    return _v48_det_tensor(small, color, bottom - top, new_w)


DET_CASES = [
    ((1185, 857, 3), (694, 960), None),            # A4 한 쪽 첫 위치 찾기(1배와 2배 사이로 줄이기)
    ((2370, 1714, 3), (1389, 1920), None),         # 2배로 키운 A4 한 쪽
    ((1144, 1984, 3), (1984, 1144), None),         # 크기가 같은 다시 찾기
    ((2224, 3904, 3), (960, 547), None),           # 4K 첫 위치 찾기(정수 배 평균)
    ((140, 673, 3), (960, 200), None),             # 한 줄을 키우기
    ((2288, 3968, 3), (3174, 1830), (499, 1331)),  # 넓은 영역 2배의 띠
    ((2224, 3904, 3), (3904, 2224), (388, 1060)),  # 4K를 원래 크기로 띠 나눠 찾기
    ((3, 5, 3), (2, 1), None),                     # 아주 작은 그림
]


@pytest.mark.parametrize("shape, size, rows", DET_CASES)
def test_det_input_matches_v48(shape, size, rows, pool):
    image = _page(shape, shape[0] + size[1])
    top, bottom = rows or (0, size[1])
    want = _v48_det_input(image, *size, top, bottom)
    for got, got_rows in (_det_input(image, *size, top, bottom), _det_input(image, *size, top, bottom, pool)):
        assert got_rows == bottom - top
        assert got.dtype == want.dtype and got.shape == want.shape and got.flags.c_contiguous
        assert np.array_equal(got, want)


# ---------- 중앙값 ----------

from screen_text import leading_symbols as L  # noqa: E402
from screen_text import table_lines as T  # noqa: E402


@pytest.mark.parametrize("size", [1, 2, 3, 4, 7, 8, 31, 64, 257])
def test_median_matches_numpy(size):
    rng = np.random.default_rng(size)
    for values in (rng.random(size).astype(np.float32) * 255, rng.integers(0, 4, size).astype(np.float32),
                   (rng.random((size, 3)) * 255).astype(np.float32)):
        got, want = L.median(values), np.median(values)
        assert type(got) is type(want) and got == want
    with_nan = rng.random(size).astype(np.float32)
    with_nan[size // 2] = np.nan
    assert np.isnan(L.median(with_nan)) and type(L.median(with_nan)) is type(np.median(with_nan))
    integers = rng.integers(0, 255, size)
    assert L.median(integers) == np.median(integers)


@pytest.mark.parametrize("shape", [(1, 1), (1, 6), (5, 1), (7, 8), (13, 9), (40, 300)])
def test_row_medians_match_numpy(shape):
    rng = np.random.default_rng(sum(shape))
    band = (rng.integers(0, 6, shape) * 37.5).astype(np.float32)
    got, want = L.row_medians(band), np.median(band, axis=1)
    assert got.dtype == want.dtype and np.array_equal(got, want)
    band[0, 0] = np.nan
    assert np.array_equal(L.row_medians(band), np.median(band, axis=1), equal_nan=True)


# ---------- 표 선 찾기 ----------

def _v48_runs(row, length):
    edges = np.flatnonzero(np.diff(np.concatenate(([0], row.astype(np.int8), [0]))))
    spans, start, end = [], None, None
    for a, b in zip(edges[0::2].tolist(), (edges[1::2] - 1).tolist()):
        if start is not None and a - end - 1 <= T.BRIDGE_GAP:
            end = b
            continue
        if start is not None and end - start + 1 >= length:
            spans.append((start, end))
        start, end = a, b
    if start is not None and end - start + 1 >= length:
        spans.append((start, end))
    return spans


def _v48_segments(mask, length):
    finished, active = [], []
    for y in np.flatnonzero(mask.sum(axis=1) >= length).tolist():
        spans = _v48_runs(mask[y], length)
        carried = []
        for segment in active:
            if segment[1] < y - 1:
                finished.append(segment)
            else:
                carried.append(segment)
        active = carried
        for x0, x1 in spans:
            for segment in active:
                if min(segment[3], x1) - max(segment[2], x0) >= T.SAME_LINE * (max(segment[3] - segment[2], x1 - x0) + 1):
                    segment[1] = y
                    segment[2], segment[3] = min(segment[2], x0), max(segment[3], x1)
                    break
            else:
                active.append([y, y, x0, x1])
    finished.extend(active)
    return [tuple(s) for s in finished if s[1] - s[0] + 1 <= T.MAX_THICKNESS]


def _v48_ridges(gray):
    mask = np.zeros(gray.shape, dtype=bool)
    for reach in T.RIDGE_REACHES:
        if gray.shape[0] <= 2 * reach:
            continue
        up = gray[reach:-reach] - gray[:-2 * reach]
        down = gray[reach:-reach] - gray[2 * reach:]
        mask[reach:-reach] |= ((up > T.RIDGE_CONTRAST) & (down > T.RIDGE_CONTRAST)) | ((up < -T.RIDGE_CONTRAST) & (down < -T.RIDGE_CONTRAST))
    return mask


def _v48_steps(gray):
    mask = np.zeros(gray.shape, dtype=bool)
    if gray.shape[0] > 2:
        mask[1:-1] = np.abs(gray[2:] - gray[:-2]) > T.STEP_CONTRAST
    return mask


def _v48_even(pixels):
    return float((np.abs(pixels - np.median(pixels)) <= T.EVEN_RANGE).mean()) >= T.EVEN_SHARE


def _v48_tight(gray, segment):
    top, bottom, left, right = segment
    first, last = max(0, top - 2), min(gray.shape[0], bottom + 3)
    band = gray[first:last, left:right + 1]
    majority = np.median(band, axis=1)
    changed = np.flatnonzero(np.abs(majority - np.median(majority)) >= T.LINE_CONTRAST)
    rows = np.array([row for row in changed if _v48_even(band[row])], dtype=np.int64)
    if rows.size == 0 or rows.size == band.shape[0]:
        profile = band.mean(axis=1)
        contrast = np.abs(profile - np.median(profile))
        peak = float(contrast.max())
        if peak <= 0:
            return segment
        rows = np.flatnonzero(contrast >= .5 * peak)
    return first + int(rows[0]), first + int(rows[-1]), left, right


def _v48_without_text_rows(gray, lines):
    even = [line for line in lines if _v48_even(gray[line[0]:line[1] + 1, line[2]:line[3] + 1].mean(axis=0))]

    def beside(line):
        center = (line[0] + line[1]) / 2
        return any(abs((other[0] + other[1]) / 2 - center) <= T.CLUSTER_GAP
                   and min(other[3], line[3]) - max(other[2], line[2]) >= T.SAME_LINE * (line[3] - line[2] + 1) for other in even)
    return [line for line in lines if line in even or not beside(line)]


def _v48_is_stroke(column, boxes, solid=False, image=None):
    left, right, top, bottom = column
    length = bottom - top + 1
    inside, tallest, edge = 0, 0, False
    for box in boxes:
        x0, y0, x1, y1 = box
        overlap = max(0, min(bottom + 1, y1) - max(top, y0))
        if not overlap:
            continue
        if x0 < left and right < x1:
            inside += overlap
            tallest = max(tallest, y1 - y0)
        elif image is not None and x0 - 1 <= left and right <= x1 and overlap >= .9 * length and T._within_text(column, box, image):
            edge = True
            tallest = max(tallest, y1 - y0)
    return (inside >= .9 * length or edge) and not (solid and length >= T.STROKE_LINES * tallest)


def _v48_in_text_row(line, boxes):
    top, bottom, left, right = line
    inside = 0
    for x0, y0, x1, y1 in boxes:
        reach = T.STROKE_EDGE * (y1 - y0)
        if y0 + reach < top and bottom < y1 - reach:
            inside += max(0, min(right + 1, x1) - max(left, x0))
    return inside >= T.STROKE_SHARE * (right - left + 1)


def _table_page(seed, width=520, height=360):
    """표와 표 밖 글자 줄, 글머리 네모가 든 그림. 글자는 띄엄띄엄한 세로획이다. (그림, 글자 상자)"""
    rng = np.random.default_rng(seed)
    image = np.full((height, width, 3), 250, np.uint8)
    boxes = []
    xs = sorted(set([20] + sorted(rng.choice(np.arange(80, width - 60), 3, replace=False).tolist()) + [width - 20]))
    ys = sorted(set([40] + sorted(rng.choice(np.arange(70, height - 120), 3, replace=False).tolist()) + [height - 90]))
    shade = int(rng.integers(0, 200))
    for y in ys:
        image[y, xs[0]:xs[-1] + 1] = shade
    for k, x in enumerate(xs):
        image[ys[0]:ys[-1] + 1, x] = shade if k != 2 else 120
    for r in range(len(ys) - 1):
        for c in range(len(xs) - 1):
            x0, x1 = xs[c] + 6, xs[c + 1] - 6
            y0 = ys[r] + 6
            if x1 - x0 < 12 or ys[r + 1] - ys[r] < 20:
                continue
            end = x0 + int(rng.integers(8, x1 - x0))
            image[y0 + 2:y0 + 12, x0:end:3] = int(rng.integers(0, 90))
            boxes.append((x0 - 2, y0, end + 2, y0 + 14))
    for line in range(3):
        top = height - 80 + line * 24
        image[top + 2:top + 10, 30:38] = 20                       # 글머리 네모
        end = int(rng.integers(120, width - 30))
        image[top:top + 12, 48:end:3] = 10
        image[top + 11, 48:end] = 10                              # 획이 이어진 글자 바닥
        boxes.append((44, top - 1, end + 2, top + 13))
    return image, boxes


@pytest.mark.parametrize("seed", range(12))
def test_table_line_parts_match_v48(seed):
    image, _ = _table_page(seed)
    gray = T._gray(image)
    for source in (gray, gray.T, gray[:5], gray[:9].T, gray[:1]):
        assert np.array_equal(T._ridges(source), _v48_ridges(source))
        assert np.array_equal(T._steps(source), _v48_steps(source))
    for source, length in ((gray, T.MIN_H_LENGTH), (gray.T, T.MIN_V_LENGTH)):
        for mask, least in ((_v48_ridges(source), length), (_v48_steps(source), T.STEP_LENGTH)):
            segments = _v48_segments(mask, least)
            assert T._segments(mask, least) == segments
            for segment in segments:
                assert T._tight(source, segment) == _v48_tight(source, segment)
        lines = T._lines(source, length)
        assert T._without_text_rows(source, lines) == _v48_without_text_rows(source, lines)
    rows = gray[::7]
    assert [T._even(row) for row in rows] == [_v48_even(row) for row in rows]


def test_row_spans_with_many_rows_match_v48():
    """행이 LINE_ROWS보다 많아도 행마다 찾은 구간이 같다(묶음 경계를 넘는 행)."""
    rng = np.random.default_rng(5)
    mask = rng.random((600, 90)) < 0.6
    assert T._segments(mask, 12) == _v48_segments(mask, 12)


@pytest.mark.parametrize("seed", range(8))
def test_stroke_tests_match_v48(seed):
    rng = np.random.default_rng(100 + seed)
    image, boxes = _table_page(seed)
    boxes = boxes + [tuple(int(v) for v in (x, y, x + rng.integers(4, 90), y + rng.integers(6, 30)))
                     for x, y in zip(rng.integers(0, 480, 25), rng.integers(0, 330, 25))]
    table = T._box_table(boxes)
    columns = [(int(x), int(x) + int(w), int(y), int(y) + int(h)) for x, w, y, h in
               zip(rng.integers(0, 500, 60), rng.integers(0, 3, 60), rng.integers(0, 300, 60), rng.integers(4, 120, 60))]
    columns += [(b[0], b[0] + 1, b[1] + 1, b[3] - 2) for b in boxes[:10]] + [(b[2] - 1, b[2] - 1, b[1], b[3] - 1) for b in boxes[:10]]
    for column in columns:
        for solid in (False, True):
            want = _v48_is_stroke(column, boxes, solid, image)
            assert T._is_stroke(column, boxes, solid, image) == want
            assert T._is_stroke(column, boxes, solid, image, table) == want
            assert T._is_stroke(column, boxes, solid) == _v48_is_stroke(column, boxes, solid)
    lines = [(int(y), int(y) + int(t), int(x), int(x) + int(w)) for y, t, x, w in
             zip(rng.integers(0, 330, 60), rng.integers(0, 3, 60), rng.integers(0, 400, 60), rng.integers(18, 300, 60))]
    for line in lines:
        assert T._in_text_row(line, boxes, table) == _v48_in_text_row(line, boxes)
    assert T._is_stroke((5, 6, 5, 40), []) == _v48_is_stroke((5, 6, 5, 40), [])


@pytest.mark.parametrize("seed", range(6))
def test_find_grids_with_prepared_lines_is_the_same(seed):
    image, boxes = _table_page(seed)
    want = T.find_grids(image, boxes, 8)
    assert want   # 시험 그림에 표가 있다
    assert T.find_grids(image, boxes, 8, T.grid_lines(image)) == want
    assert T.find_grids(image, boxes, 8, T.grid_lines(image, T.grid_gray(image))) == want
    assert T.find_grids(image[:6], boxes, 0, T.grid_lines(image[:6])) == T.find_grids(image[:6], boxes) == []


# ---------- 글자 픽셀 공유·덩어리·글머리 기호 ----------

def _v48_ink_mask(crop, fraction=L.INK_PEAK_FRACTION):
    gray = L._gray(crop)
    if gray.size == 0:
        return np.zeros(gray.shape, dtype=bool)
    diff = np.abs(gray - np.median(gray))
    peak = float(diff.max())
    if peak <= 0:
        return np.zeros(diff.shape, dtype=bool)
    return diff > max(L.INK_MIN_DIFF, fraction * peak)


def test_shared_ink_gives_the_same_masks():
    image, boxes = _table_page(3)
    for x0, y0, x1, y1 in boxes + [(0, 0, 0, 5), (10, 10, 11, 11), (0, 0, 40, 40)]:
        crop = image[y0:y1, x0:x1]
        want = [_v48_ink_mask(crop), _v48_ink_mask(crop, L.THIN_INK_FRACTION), _v48_ink_mask(crop[:, 1:])]
        with L.shared_ink():
            for _ in range(2):
                got = [L.ink_mask(crop), L.ink_mask(crop, L.THIN_INK_FRACTION), L.ink_mask(crop[:, 1:])]
                assert all(np.array_equal(a, b) and a.shape == b.shape for a, b in zip(got, want))
                got[0][...] = True   # 돌려받은 마스크를 바꿔도 다음 결과는 그대로다
        gray = crop.astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        if gray.size:
            assert np.array_equal(L.ink_level(crop)[0], np.abs(gray - np.median(gray)))


def _v48_blobs(ink, reference_height=0, limit=4, thin=None):
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
        qw, qh = max(1, round(blob_w * .25)), max(1, round(blob_h * .25))
        corners = float(np.mean([blob[:qh, :qw].mean(), blob[:qh, -qw:].mean(), blob[-qh:, :qw].mean(), blob[-qh:, -qw:].mean()]))
        cy0, cx0 = int(blob_h * .3), int(blob_w * .3)
        center = float(blob[cy0:max(cy0 + 1, int(blob_h * .7)), cx0:max(cx0 + 1, int(blob_w * .7))].mean())
        outline = blob if thin is None else thin[:, a:b + 1][occupied[0]:occupied[-1] + 1]
        row, column = outline[blob_h // 2], outline[:, blob_w // 2]
        closed = bool(row[:blob_w // 2].any() and row[blob_w // 2 + 1:].any() and column[:blob_h // 2].any() and column[blob_h // 2 + 1:].any())
        th, tw = max(1, round(blob_h * L.TIP_SIZE)), max(1, round(blob_w * L.TIP_SIZE))
        tips = float(np.mean([blob[:th, :tw].any(), blob[:th, -tw:].any(), blob[-th:, :tw].any(), blob[-th:, -tw:].any()]))
        one_sided = bool(blob[:th, :tw].any() and blob[-th:, :tw].any() and not blob[:th, -tw:].any() and not blob[-th:, -tw:].any())
        blobs.append(dict(width=blob_w, height=blob_h, fill=float(blob.mean()), center=center, corners=corners, tips=tips, one_sided=one_sided, closed=closed,
                          mirror=float((blob == blob[:, ::-1]).mean()), relative_height=blob_h / height, line_height=height, left=int(a), right=int(b),
                          top_span=float(blob[0].mean()), top=int(occupied[0]), bottom=int(occupied[-1]),
                          middle=((occupied[0] + occupied[-1]) / 2 - rows[0]) / max(1, rows[-1] - rows[0]),
                          gap=int(runs[k + 1][0] - b - 1) if k + 1 < len(runs) else 10 ** 6))
    return blobs


@pytest.mark.parametrize("seed", range(10))
def test_lazy_blobs_match_v48(seed):
    rng = np.random.default_rng(seed)
    ink = rng.random((int(rng.integers(3, 30)), int(rng.integers(3, 80)))) < 0.4
    thin = ink | (rng.random(ink.shape) < 0.1)
    for reference, limit, outline in ((0, 4, None), (17, 10 ** 6, thin), (3, 2, thin)):
        got, want = L._blobs(ink, reference, limit, outline), _v48_blobs(ink, reference, limit, outline)
        assert len(got) == len(want)
        for blob, expected in zip(got, want):
            assert {key: blob[key] for key in expected} == expected
    with pytest.raises(KeyError):
        L._blobs(np.ones((4, 4), bool))[0]["no such feature"]


def _v48_leading_symbol(image, index, boxes, readable=None):
    box = boxes[index]
    x0, y0, x1, y1 = box
    height = y1 - y0
    left_limit = 0
    for j, other in enumerate(boxes):
        if j != index and other[0] < x0 and L._same_row(other, box) and (readable is None or readable[j]):
            left_limit = max(left_limit, other[2] + 1)
    x_from = max(left_limit, x0 - int(round(L.SEARCH_LEFT * height)))
    x_to = min(x1, x0 + int(round(L.SEARCH_RIGHT * height)))
    if x_to - x_from < 6:
        return None
    reference = max((L._ink_height(image, other) for j, other in enumerate(boxes)
                     if j != index and other[0] >= x0 and other[0] - x0 <= 10 * height and L._same_row(other, box)), default=0)
    crop = image[y0:y1, x_from:x_to]
    blobs = L._blobs(_v48_ink_mask(crop), reference, thin=_v48_ink_mask(crop, L.THIN_INK_FRACTION))
    last_rule = max((k for k, blob in enumerate(blobs) if L._is_rule(blob) and x_from + blob["right"] < x0), default=-1)
    for blob in blobs[last_rule + 1:]:
        if L._is_rule(blob):
            continue
        kind = L._classify(blob)
        if kind is None or L._continues_outside(image, crop, blob, x_from, y0, y1):
            return None
        alone = blob["gap"] >= 10 ** 6 and x_to == x1
        return kind, x_from + blob["left"], x_from + blob["right"], alone
    return None


@pytest.mark.parametrize("seed", range(8))
def test_leading_symbols_match_v48(seed):
    rng = np.random.default_rng(seed)
    image, boxes = _table_page(seed)
    boxes = boxes + [(int(x), int(y), int(x) + int(w), int(y) + 14) for x, y, w in
                     zip(rng.integers(0, 460, 12), rng.integers(0, 330, 12), rng.integers(10, 60, 12))]
    readable = [bool(r) for r in rng.random(len(boxes)) < 0.8]
    found = 0
    for index in range(len(boxes)):
        want = _v48_leading_symbol(image, index, boxes, readable)
        assert L.leading_symbol(image, index, boxes, readable) == want
        assert L.leading_symbol(image, index, boxes) == _v48_leading_symbol(image, index, boxes)
        found += want is not None
    assert found   # 글머리 네모를 찾는 경우가 들어 있다


def test_skew_angle_with_prepared_pixels_is_the_same():
    from screen_text.deskew import ink_pixels, skew_angle
    from screen_text.engine import label_components
    rng = np.random.default_rng(1)
    for degrees in (0.0, 1.0, -2.0):
        image = np.full((300, 480, 3), 255, np.uint8)
        for row in range(8):
            top = 30 + row * 30
            for x in range(30, 450, 3):
                shift = int(round((240 - x) * np.tan(np.radians(degrees))))
                image[top + shift:top + shift + 12, x:x + 2] = int(rng.integers(0, 60))
        components = label_components(L.ink_mask(image))
        assert skew_angle(components, image, lambda: ink_pixels(image)) == skew_angle(components, image)


# ---------- 여러 스레드로 읽어도 같다 ----------

class _InkDetector:
    """정규화한 입력에서 어두운 화소가 든 줄 묶음을 글자 확률로 내는 위치 모델 대역(같은 입력이면 같은 출력)."""

    def run(self, _, feed):
        tensor = feed["x"]
        dark = tensor[0].mean(axis=0) < 0.0
        probability = np.zeros((1, 1) + tensor.shape[2:], np.float32)
        rows = np.flatnonzero(dark.any(axis=1))
        for band in (np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1) if rows.size else []):
            columns = np.flatnonzero(dark[band].any(axis=0))
            for part in np.split(columns, np.flatnonzero(np.diff(columns) > 8) + 1):
                probability[0, 0, band[0]:band[-1] + 1, part[0]:part[-1] + 1] = .9
        return [probability]


class _InkReader:
    """입력 열의 밝기로 글자를 정하는 인식 모델 대역(같은 입력이면 같은 출력). 실행한 스레드와 입력 모양을 적는다."""

    def __init__(self, classes):
        self.classes, self.calls = classes, []

    def run(self, _, feed):
        import threading
        x = feed["x"]
        self.calls.append((threading.current_thread().name, x.shape))
        count, _, _, width = x.shape
        steps = -(-width // 8)
        columns = np.pad(x.mean(axis=(1, 2)), ((0, 0), (0, steps * 8 - width)), constant_values=1.0).reshape(count, steps, 8).mean(axis=2)
        index = np.where(columns < 0.7, 1 + (np.arange(steps) * 7 + (columns * 50).astype(int)) % 300, 0)
        probs = np.full((count, steps, self.classes), 1e-4, np.float32)
        probs[np.arange(count)[:, None], np.arange(steps)[None, :], index] = 0.6 + 0.3 * (columns < 0.3)
        probs[:, :, -1] = 0.05 + 0.4 * (columns > 0.95)   # 공백 확률
        return [probs]

    def get_outputs(self):
        return [type("Output", (), {"shape": [None, None, self.classes]})()]


def _fake_engine(threads):
    from screen_text.engine import OcrEngine, load_charset, model_dir
    instance = object.__new__(OcrEngine)
    instance._charset = load_charset(model_dir() / "dict.txt")
    instance._det, instance._rec = _InkDetector(), _InkReader(len(instance._charset) + 1)
    if threads > 1:
        instance._pool = ThreadPoolExecutor(threads)
        instance._runner = ThreadPoolExecutor(1, thread_name_prefix="screen-text-model")
    return instance


def _reading_page(seed):
    image, _ = _table_page(seed, width=900, height=640)
    image = np.concatenate([image, np.full((300, 900, 3), 250, np.uint8)])
    image[700:712, 40:600:3] = 30      # 표 밖 글자 줄
    image[740:748, 40:48] = 20         # 글머리 네모
    image[738:750, 60:500:3] = 15
    return image


@pytest.mark.parametrize("seed", range(4))
def test_threads_do_not_change_the_reading(seed):
    """스레드로 나눠 계산하고 모델과 규칙을 겹쳐도 상자·글자·점수·확인 필요 표시·격자가 차례로 읽을 때와 같다."""
    image = _reading_page(seed)
    alone, parallel = _fake_engine(1), _fake_engine(4)
    try:
        want, got = alone.recognize(image), parallel.recognize(image)
        flat = [(b.x, b.y, b.w, b.h, b.text, b.score, b.unsure_prefix, b.unsure_chars) for b in want]
        assert flat and [(b.x, b.y, b.w, b.h, b.text, b.score, b.unsure_prefix, b.unsure_chars) for b in got] == flat
        assert got.grids == want.grids
        assert [shape for _, shape in parallel._rec.calls] == [shape for _, shape in alone._rec.calls]   # 같은 묶음을 같은 순서로
        assert {name for name, _ in parallel._rec.calls} == {"screen-text-model_0"}                      # 모델은 전용 스레드 하나에서
    finally:
        parallel._pool.shutdown()
        parallel._runner.shutdown()


def test_cancel_while_the_reader_runs_ahead_stops_the_queued_batches():
    """앞 묶음이 모델에서 도는 동안 취소되면 그 뒤 묶음은 모델에 넘기지 않는다."""
    from screen_text.engine import RecognitionCancelled
    image = _reading_page(1)
    reader = _fake_engine(4)
    try:
        with pytest.raises(RecognitionCancelled):
            reader.recognize(image, lambda: len(reader._rec.calls) >= 2)
        reader._runner.shutdown(wait=True)
        assert 2 <= len(reader._rec.calls) <= 3
    finally:
        reader._pool.shutdown()
