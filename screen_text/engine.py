"""PP-OCR 위치 모델과 한국어 인식 모델로 글자 상자를 읽는다.

Qt를 import하지 않는다. numpy와 onnxruntime만 쓰며, MANIFEST.json의 크기와
SHA-256을 확인한 번들 모델만 불러온다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path

import numpy as np

from app_paths import resource_root
from screen_text.cell_marks import empty_cell_boxes, gap_mark_boxes, read_marks
from screen_text.corner_brackets import restore_corner_brackets
from screen_text.deskew import ink_pixels, skew_angle, straighten
from screen_text.layout import Grid, GridCell, RecognizedBoxes, TextBox
from screen_text.leading_symbols import apply_leading_symbols, ink_mask, restore_inline_checkboxes, shared_ink
from screen_text.marks import rescue_marks, restore_circled_digits, restore_stars, restore_thin_capitals
from screen_text.number_marks import restore_number_marks
from screen_text.roman import restore_roman
from screen_text.table_lines import RIDGE_CONTRAST, find_grids, fit_boxes, grid_gray, grid_lines
from screen_text.triangles import restore_triangles
from screen_text.units import restore_units
from screen_text.word_spaces import join_words

DET_LIMIT = 960            # 첫 위치 찾기(글자 크기·기울기를 재는 단계) 입력의 긴 변 상한
DET_LIMIT_SMALL = 1920     # 다시 찾을 때 한 번에 넣는 입력의 긴 변 상한. 넘으면 가로 띠로 나눠 찾는다
DET_SMALL_MIN_SCALE = 1.6  # 작은 글씨를 2배로 다시 찾을 때 줄여도 이 배율 아래로는 줄이지 않는다(A4 한 쪽 100%가 1,920/1,185≈1.62배)
DET_TILE_AREA = 1920 * 1408  # 띠 하나의 넓이 상한(모델 입력 화소, A4 한 쪽을 2배로 찾던 입력과 같은 메모리)
DET_TILE_OVERLAP = 256     # 이웃 띠가 겹치는 높이(모델 입력 화소). 이보다 낮은 글자 줄은 한 띠 안에 온전히 든다
DET_MARGIN = 32            # 위치 찾기 전에 이미지 둘레에 두르는 배경 여백(픽셀). 영역을 바짝 골라도 가장자리 글자를 놓치지 않는다
RULE_PAST_TEXT = 2         # 표 세로선은 글자보다 이만큼(픽셀) 더 뻗는다. 바짝 고른 글자의 세로획은 글자와 함께 끝난다
SMALL_TEXT_PX = 22         # 상자 높이 중앙값이 이보다 작으면 2배로 키워 다시 찾고 읽는다
SMALL_TEXT_RECHECK_PX = 20  # 줄여 찾은 첫 결과로는 크게 보여 원래 크기로 다시 찾았을 때, 그 상자 높이가 이보다 작으면 2배로 읽는다
RETRY_LOST = 0.3           # 2배로 찾은 상자가 1배 상자 폭을 이만큼 잃으면 위치 찾기 입력을 조금 줄여 한 번 더 찾는다
RETRY_SCALE = 0.97         # 그때 2배 이미지를 줄이는 비율. 정확히 2배인 입력에서만 위치 모델이 표의 한 열을 통째로 놓쳤다
RETRY_RECOVERED = 0.1      # 다시 찾은 결과는 잃은 폭이 이보다 작을 때만 쓴다. 아니면 2배 결과를 그대로 둔다
CHAR_UNSURE = 0.65         # 글자 확신도가 이보다 낮으면 그 글자만 확인 필요로 표시한다
CUT_LINE_HEIGHT = 0.8      # 영역 끝에 잘린 이웃 줄의 높이 상한(다른 줄 높이 대비). 그보다 높으면 읽을 만한 줄이다
CUT_LINE_SCORE = 0.8       # 잘린 줄로 볼 인식 점수 상한
CUT_LINE_SHORT = 0.6       # 이보다 낮은 조각은 모델이 꽤 확신해도 없는 글자다('거기' 0.92)
CUT_LINE_SHORT_SCORE = 0.95  # 그래도 이만큼 확신하면 바짝 고른 영역의 작은 글자다
FRAGMENT_SCORE = 0.7       # 조각으로 볼 인식 점수 상한
FRAGMENT_CHARS = 2         # 조각은 한두 글자로 읽힌다
FRAGMENT_HEIGHT = 1.5      # 옆 상자가 이 배수 이상 높고
FRAGMENT_OVERLAP = 0.6     # 조각 높이의 이만큼 겹치며
FRAGMENT_REACH = 0.15      # 옆 상자 높이의 이 비율 안에 붙어 있으면 그 글자에서 떨어져 나온 조각이다
FRAGMENT_NEIGHBOR = 0.9    # 옆 상자는 모델이 확신하는 글자여야 한다
FRAGMENT_KEEP = frozenset("ㅇ○•■□◇-.,·'*%")  # 작아도 진짜인 기호(글머리는 모양으로 읽었다)
BOX_FIT_REACH = 0.4        # 상자를 넓혀 볼 거리(상자 높이 대비)
BOX_FIT_INK = 0.01         # 행의 이 비율 이상이 글자 픽셀이면 글자가 이어진다
DET_THRESHOLD = 0.3        # 글자 확률 이진화 기준
BOX_THRESHOLD = 0.6        # 상자 평균 확률 하한
UNCLIP_RATIO = 1.5         # DB 방식 상자 확장 비율
MIN_BOX_AREA = 6           # 확률 맵에서 이보다 작은 요소는 잡음
REC_HEIGHT = 48            # 한국어 인식 모델 입력 높이 (모델 입력 [N, 3, 48, W])
REC_BATCH = 6              # 폭이 비슷한 상자끼리 묶는 개수
MAX_REC_WIDTH = 4096       # 종횡비 이상 상자는 압축하지 않고 영역 재선택 안내
MAX_REC_BOXES = 512
MAX_REC_BATCH_WIDTH = 8192 # 한 배치의 패딩 폭 합계 상한
MAX_SIDE = 4000            # 입력 이미지 긴 변 상한 (넘으면 줄인다)
RESIZE_ROWS = 32           # 크기를 바꿀 때 한 번에 계산하는 줄 수. 이미지 전체 크기의 실수 임시 배열을 만들지 않는다
PARALLEL_ROWS = 128        # 큰 이미지를 여러 스레드로 나눠 계산할 때 한 일감의 줄 수(numpy는 계산하는 동안 GIL을 놓는다)
UPSCALE = 1.0              # 작은 글씨 확대 배율 (Task 4 측정으로 확정)
CHARSET_SIZE = 11945
OUT_OF_MEMORY = ("MemoryError", "RuntimeException")  # 큰 입력을 포기하고 첫 결과로 계속할 오류
DET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
DET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class ModelIntegrityError(RuntimeError):
    """번들 모델이 없거나 MANIFEST와 다르다. 이 상태에서는 인식을 시작하지 않는다."""


class RecognitionCancelled(Exception):
    """사용자 동작이나 수명 처리로 인식이 취소됐다."""


class RecognitionLimitError(ValueError):
    """한 번에 안전하게 읽을 수 있는 영역 크기를 넘었다."""


def model_dir() -> Path:
    return resource_root() / "screen_text" / "models"


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_models(directory=None):
    """MANIFEST의 크기·SHA-256과 일치하는 모델 경로를 역할별로 돌려준다."""
    directory = Path(directory) if directory is not None else model_dir()
    try:
        with open(directory / "MANIFEST.json", encoding="utf-8") as stream:
            manifest = json.load(stream)
        files = {}
        for entry in manifest["files"]:
            path = directory / entry["name"]
            if path.stat().st_size != entry["size"] or _sha256(path) != entry["sha256"]:
                raise ModelIntegrityError(f"모델 파일 불일치: {entry['name']}")
            files[entry["role"]] = path
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ModelIntegrityError("인식 모델을 확인하지 못했습니다") from error
    if set(files) != {"det", "rec", "dict"}:
        raise ModelIntegrityError("인식 모델 구성이 맞지 않습니다")
    return files


def load_charset(path):
    """사전 한 줄이 한 글자다. 모델의 마지막 클래스는 공백이다."""
    with open(path, encoding="utf-8", newline="") as stream:
        chars = [line.rstrip("\r\n") for line in stream]
    if len(chars) != CHARSET_SIZE:
        raise ModelIntegrityError("인식 사전 크기가 맞지 않습니다")
    return chars + [" "]


def rgb_from_buffer(width, height, bytes_per_line, data):
    """줄 끝 여백이 있는 RGB888 버퍼를 (높이, 너비, 3) 배열로 바꾼다."""
    raw = np.frombuffer(data, dtype=np.uint8)[: height * bytes_per_line]
    return raw.reshape(height, bytes_per_line)[:, : width * 3].reshape(height, width, 3).copy()


def _in_parallel(fill, first, last, pool):
    """fill(시작, 끝)을 PARALLEL_ROWS 줄씩 나눠 pool에서 돌린다. 줄끼리 서로 기대지 않는 계산만 쓴다(결과는 한 스레드와 같다)."""
    spans = [(start, min(start + PARALLEL_ROWS, last)) for start in range(first, last, PARALLEL_ROWS)]
    if pool is None or len(spans) < 2:
        for span in spans:
            fill(*span)
        return
    futures = [pool.submit(fill, *span) for span in spans]
    wait(futures)   # 하나가 실패해도 나머지가 끝난 뒤에 알린다(메모리가 모자랄 때 첫 결과로 계속하는 경로가 있다)
    for future in futures:
        future.result()


def _skew_and_gray(plain, sharp):
    """기울기를 잴 화면 전체의 글자 픽셀(plain)과 표 선을 찾을 회색 그림(sharp). 둘 다 그림 크기의 실수 사본을 잠깐 만들므로 차례로 만든다."""
    return ink_pixels(plain), grid_gray(sharp)


class _Deferred:
    """나중에 다른 스레드에서 시작할 계산. 시작하지 못한 채 결과를 찾으면 부른 스레드에서 계산한다(어느 쪽이든 결과는 같다)."""

    def __init__(self, pool, function, *args):
        self._pool, self._function, self._args, self._future = pool, function, args, None

    def start(self):
        if self._future is None and self._pool is not None:
            self._future = self._pool.submit(self._function, *self._args)
            self._args = ()   # 넘긴 큰 배열을 끝날 때까지 여기서도 쥐지 않는다

    def result(self):
        if self._future is None:
            self._future = _Done(self._function(*self._args))
            self._args = ()
        return self._future.result()


class _Done:
    """이미 계산한 결과(Future와 같은 모양으로 꺼낸다)."""

    def __init__(self, value):
        self._value = value

    def result(self):
        return self._value


def _block_mean(image, factor):
    """factor×factor 칸 평균으로 줄인 float32 이미지. uint8은 칸의 합을 정수로 더한다(이미지 전체를 실수로 바꾸지 않는다).

    합이 정수라 float32로 더해도 정확하고(255·factor² < 2^24) 나누기는 np.mean과 같은 연산이라 결과가 비트 단위로 같다.
    """
    src_h, src_w = image.shape[:2]
    cut_h, cut_w = src_h // factor * factor, src_w // factor * factor
    if image.dtype != np.uint8 or image.ndim != 3:
        return image[:cut_h, :cut_w].astype(np.float32).reshape(cut_h // factor, factor, cut_w // factor, factor, -1).mean(axis=(1, 3))
    total = np.zeros((cut_h // factor, cut_w // factor, image.shape[2]), dtype=np.uint32)
    for dy in range(factor):
        for dx in range(factor):
            total += image[dy:cut_h:factor, dx:cut_w:factor]
    mean = total.astype(np.float32)
    return np.true_divide(mean, np.intp(factor * factor), out=mean, casting="unsafe")


def resize_bilinear(image, width, height, rows=None, pool=None, out=None):
    """numpy 이중선형 크기 변경. 크게 줄일 때는 정수 배 평균으로 먼저 줄인다.

    줄 묶음마다 계산해 이미지 전체 크기의 실수 임시 배열을 만들지 않는다(2배로 키운 A4 한 쪽에서 366MB였다, 2026-11-08).
    uint8은 실수로 바꿔도 값이 그대로라 묶음마다 바꾸고, 계산 순서는 전과 같아 결과가 비트 단위로 같다.
    가로 보간은 원본 줄마다 한 번만 하고 결과 줄들이 나눠 쓴다(같은 줄을 위·아래 이웃으로 거듭 보간하던 것, 2026-11-09).
    rows=(위, 아래)면 결과의 그 줄만 계산한다(띠로 나눠 찾을 때). 전체를 계산해 자른 것과 비트 단위로 같다.
    pool(스레드 묶음)을 주면 결과 줄을 나눠 동시에 계산한다. 줄마다 같은 연산이라 결과는 같다.
    out을 주면 결과를 그 배열(모양이 같은 어떤 실수 배열이든)에 넣는다. 계산한 값을 그 형식으로 바꿔 넣는 것과 같다.
    """
    src_h, src_w = image.shape[:2]
    first, last = rows or (0, height)
    if (width, height) == (src_w, src_h):
        if out is not None:   # uint8은 실수로 바꿀 때 값이 그대로이고 float32 out이면 반올림이 한 번이라 사본 없이 넣어도 같다
            out[...] = image[first:last] if image.dtype == np.uint8 or out.dtype == np.float32 else image[first:last].astype(np.float32)
            return out
        return image[first:last].astype(np.float32)
    plan = _bilinear_plan(image, width, height)
    if out is None:
        out = np.empty((last - first, width) + plan[0].shape[2:], dtype=_bilinear_dtype(plan))
    return _bilinear_rows(plan, first, last, out, pool)


def _bilinear_plan(image, width, height):
    """크기 바꾸기에 쓸 원본(크게 줄일 때는 정수 배 평균을 거친 것)과 줄·열의 이웃 위치·가중치."""
    src_h, src_w = image.shape[:2]
    factor = int(min(src_w / width, src_h / height))
    if factor >= 2:
        source = _block_mean(image, factor)
        src_h, src_w = source.shape[:2]
    else:
        source = image if image.dtype == np.uint8 else image.astype(np.float32)
    ys = np.clip((np.arange(height, dtype=np.float32) + 0.5) * (src_h / height) - 0.5, 0, src_h - 1)
    xs = np.clip((np.arange(width, dtype=np.float32) + 0.5) * (src_w / width) - 0.5, 0, src_w - 1)
    y0, x0 = np.floor(ys).astype(np.int32), np.floor(xs).astype(np.int32)
    y1, x1 = np.minimum(y0 + 1, src_h - 1), np.minimum(x0 + 1, src_w - 1)
    wy, wx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    return source, y0, y1, wy, x0, x1, wx


def _bilinear_dtype(plan):
    return np.result_type(plan[0].dtype, plan[6].dtype)


def _bilinear_rows(plan, first, last, out, pool=None, columns=None):
    """plan으로 결과 first~last 줄(columns를 주면 그 열만)을 out에 넣는다. 원소마다 같은 연산이라 나눠 계산해도 값이 같다."""
    source, y0, y1, wy, x0, x1, wx = plan
    if columns is not None:
        x0, x1, wx = x0[columns], x1[columns], wx[:, columns]
    left, upper = 1 - wx, 1 - wy

    def fill(start, stop):
        for begin in range(start, stop, RESIZE_ROWS):
            band = slice(begin, min(begin + RESIZE_ROWS, stop))
            low, high = int(y0[begin]), int(y1[band.stop - 1]) + 1   # y0·y1은 줄 순서대로 늘어난다
            part = source[low:high]
            across = part[:, x0] * left + part[:, x1] * wx
            out[begin - first:band.stop - first] = across[y0[band] - low] * upper[band] + across[y1[band] - low] * wy[band]

    _in_parallel(fill, first, last, pool)
    return out


def _resized_border(plan, width, height):
    """plan으로 크기를 바꾼 그림의 첫 줄·끝 줄·첫 열·끝 열(resize_bilinear 결과에서 잘라 낸 것과 같은 값)."""
    channels = plan[0].shape[2:]
    dtype = _bilinear_dtype(plan)
    top = _bilinear_rows(plan, 0, 1, np.empty((1, width) + channels, dtype=dtype))[0]
    bottom = _bilinear_rows(plan, height - 1, height, np.empty((1, width) + channels, dtype=dtype))[0]
    sides = _bilinear_rows(plan, 0, height, np.empty((height, 2) + channels, dtype=dtype), columns=[0, width - 1])
    return top, bottom, sides[:, 0], sides[:, 1]


def _twice(array, axis):
    """uint16 배열을 axis 쪽으로 2배(3:1 가중, 끝은 자기 자신을 이웃으로). 값은 255를 넘지 않는다."""
    length = array.shape[axis]
    shape = list(array.shape)
    shape[axis] = 2 * length
    out = np.empty(shape, dtype=np.uint16)

    def cut(target, part):
        index = [slice(None)] * target.ndim
        index[axis] = part
        return target[tuple(index)]

    base = array * np.uint16(3)
    base += 2
    even, odd = cut(out, slice(0, None, 2)), cut(out, slice(1, None, 2))
    np.add(cut(base, slice(1, None)), cut(array, slice(0, length - 1)), out=cut(even, slice(1, None)))
    np.add(cut(base, slice(0, 1)), cut(array, slice(0, 1)), out=cut(even, slice(0, 1)))
    np.add(cut(base, slice(0, length - 1)), cut(array, slice(1, None)), out=cut(odd, slice(0, length - 1)))
    np.add(cut(base, slice(length - 1, None)), cut(array, slice(length - 1, None)), out=cut(odd, slice(length - 1, None)))
    out >>= 2
    return out


def double_size(image, pool=None):
    """uint8 이미지를 2배로(이중선형과 같은 3:1 가중). 큰 쪽 이미지를 실수 배열로 만들지 않아 메모리를 아낀다.

    줄 묶음마다(위아래 이웃 한 줄씩 더 읽어) 계산해 결과에 바로 넣는다. 정수 계산이라 묶음으로 나눠도 결과는 같다.
    """
    height = image.shape[0]
    out = np.empty((2 * height, 2 * image.shape[1]) + image.shape[2:], dtype=np.uint8)

    def fill(start, stop):
        low, high = max(0, start - 1), min(height, stop + 1)
        tall = _twice(image[low:high].astype(np.uint16), 0)[2 * (start - low):2 * (stop - low)]
        out[2 * start:2 * stop] = _twice(tall, 1)

    _in_parallel(fill, 0, height, pool)
    return out


def _det_input(image, new_w, new_h, top, bottom, pool=None):
    """image를 new_w×new_h로 바꾼 그림의 top~bottom 줄로 만든 위치 찾기 모델 입력 (1, 3, H, W) float32와 그 줄 수.

    32 배수로 늘이지 않고 바탕색으로 채운다(글자가 찌그러지지 않는다). 모델은 BGR 순서로 학습됐다. 크기를 바꾼 값을 실수 사본 없이
    채널 평면에 바로 넣고 정규화한다(전에는 입력 전체 크기의 배열을 네댓 번 만들었다, 2026-11-09). 값은 전과 비트 단위로 같다.
    """
    rows = bottom - top
    same = (new_w, new_h) == (image.shape[1], image.shape[0])
    plan = None if same else _bilinear_plan(image, new_w, new_h)
    if (top, bottom) == (0, new_h):   # 바탕색은 크기를 바꾼 그림의 둘레에서 잰다
        border = [part.astype(np.float32) for part in (image[0], image[-1], image[:, 0], image[:, -1])] if same else _resized_border(plan, new_w, new_h)
    else:   # 띠의 위아래 끝은 글자 사이를 지난다. 채울 바탕색은 그림 전체의 둘레에서 잰다
        border = (image[0], image[-1], image[:, 0], image[:, -1])
    tensor = _det_canvas(np.median(np.concatenate(border), axis=0), rows, new_w)
    target = tensor[0, ::-1, :rows, :new_w].transpose(1, 2, 0)   # 채널을 뒤집어(BGR) 본 (줄, 열, 채널)
    if same:
        target[...] = image[top:bottom] if image.dtype == np.uint8 else image[top:bottom].astype(np.float32)
    else:
        _bilinear_rows(plan, top, bottom, target, pool)
    return _normalized(tensor), rows


def _det_canvas(color, rows, width):
    """바탕색 color(RGB)로 채운 (1, 3, H, W) float32 캔버스. 채널은 모델 순서(BGR)다."""
    fill = np.asarray(color).astype(np.float32)
    tensor = np.empty((1, 3, -(-rows // 32) * 32, -(-width // 32) * 32), dtype=np.float32)
    for channel in range(3):
        tensor[0, channel] = fill[2 - channel]
    return tensor


def _normalized(tensor):
    """위치 찾기 모델의 정규화(채널마다 float32로 255로 나누고 평균을 빼고 표준편차로 나눈다)를 제자리에서 한다."""
    for channel in range(3):
        plane = tensor[0, channel]
        plane /= np.float32(255.0)
        plane -= DET_MEAN[channel]
        plane /= DET_STD[channel]
    return tensor


def _cut_rules(image, color):
    """고른 영역의 위아래 끝까지 이어진 표 세로선의 열 번호.

    맨 윗줄에서 바탕색과 다른 열만 아래까지 따라가 본다. 그런 열이 없으면 이미지 전체를 재지 않는다(4K 화면에서 0.2초였다).
    """
    def inked(pixels):   # 어느 색 채널이든 바탕색과 RIDGE_CONTRAST보다 다르다
        return np.abs(pixels.astype(np.int16) - color).max(axis=-1) > RIDGE_CONTRAST

    candidates = np.flatnonzero(inked(image[0]))
    if candidates.size == 0 or not inked(image[:, candidates]).all(axis=0).any():
        return np.empty(0, dtype=np.intp)
    ink = inked(image)
    through = ink.all(axis=0)
    rest = np.flatnonzero(ink[:, ~through].any(axis=1))
    if rest.size and image.shape[0] - (rest[-1] - rest[0] + 1) < RULE_PAST_TEXT:
        return np.empty(0, dtype=np.intp)
    return np.flatnonzero(through)


def add_margin(image, margin):
    """둘레 색(중앙값)으로 이미지 둘레에 여백을 두른다. 드래그로 바짝 고른 글자도 위치 찾기가 온전히 보게 한다.

    표의 행만 고르면 세로선이 여백에서 끊겨 떠 있는 막대가 되고 모델이 '|'로 읽으므로, 그 선은 여백까지 잇는다.
    """
    if margin <= 0:
        return image
    edge = np.concatenate((image[0], image[-1], image[:, 0], image[:, -1]))
    color = np.median(edge, axis=0).astype(np.uint8)
    height, width = image.shape[:2]
    out = np.empty((height + 2 * margin, width + 2 * margin, 3), dtype=np.uint8)
    out[:] = color
    out[margin:margin + height, margin:margin + width] = image
    columns = _cut_rules(image, color)
    out[:margin, margin + columns] = image[0, columns]
    out[margin + height:, margin + columns] = image[-1, columns]
    return out


def label_components(mask, cancelled=lambda: False):
    """행 단위 run을 8연결로 묶는다. 반환: [(x0, y0, x1, y1, [(y, xs, xe), ...])] (포함 좌표)."""
    parent, runs, previous = [], [], []

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for y in range(mask.shape[0]):
        if cancelled():
            raise RecognitionCancelled
        row = mask[y]
        if not row.any():
            previous = []
            continue
        edges = np.flatnonzero(np.diff(np.concatenate(([0], row.view(np.int8), [0]))))
        current = []
        for start, end in zip(edges[0::2].tolist(), (edges[1::2] - 1).tolist()):
            run_id = len(runs)
            runs.append((y, start, end))
            parent.append(run_id)
            current.append(run_id)
            for other in previous:
                _, other_start, other_end = runs[other]
                if other_start <= end + 1 and other_end >= start - 1:
                    a, b = find(run_id), find(other)
                    if a != b:
                        parent[a] = b
        previous = current
    groups = {}
    for run_id, run in enumerate(runs):
        groups.setdefault(find(run_id), []).append(run)
    return [
        (min(r[1] for r in members), min(r[0] for r in members),
         max(r[2] for r in members), max(r[0] for r in members), members)
        for members in groups.values()
    ]


def expand_box(x0, y0, x1, y1, ratio=UNCLIP_RATIO):
    """포함 좌표 사각형을 DB 방식 거리만큼 넓힌 반열림 좌표를 돌려준다."""
    width, height = x1 - x0 + 1, y1 - y0 + 1
    distance = width * height * ratio / (2 * (width + height))
    return x0 - distance, y0 - distance, x1 + 1 + distance, y1 + 1 + distance


def ctc_decode_detail(probs, charset):
    """(timestep, class) 확률에서 반복·blank(0)를 지운 글자 목록과 평균 확신도.

    글자 목록은 [(글자, 중심 단계)]이며, 중심은 그 글자가 이어진 단계들의 평균 위치다.
    """
    runs = _ctc_runs(probs, charset)
    scores = [first for _, _, first, _ in runs]
    return [(char, center) for char, center, _, _ in runs], (float(np.mean(scores)) if scores else 0.0)


def _ctc_runs(probs, charset):
    """반복·blank를 지운 [(글자, 중심 단계, 첫 단계 확신도, 가장 높은 확신도)]."""
    indices = probs.argmax(axis=1)
    confidence = probs.max(axis=1)
    runs, previous = [], 0
    for step, index in enumerate(indices.tolist()):
        if index != 0 and index != previous:
            runs.append([charset[index - 1], [step], float(confidence[step]), float(confidence[step])])
        elif index != 0 and runs:
            runs[-1][1].append(step)
            runs[-1][3] = max(runs[-1][3], float(confidence[step]))
        previous = index
    return [(char, sum(steps) / len(steps), first, best) for char, steps, first, best in runs]


def ctc_decode(probs, charset):
    """(timestep, class) 확률에서 반복·blank(0)를 지운 글자와 평균 확신도."""
    pieces, score = ctc_decode_detail(probs, charset)
    return "".join(char for char, _ in pieces), score


def fit_to_ink(image, box):
    """상자 위아래를 글자 픽셀이 끝나는 곳까지 넓힌다. 빈 행이 없으면 윗줄·아랫줄에 닿은 것이므로 그쪽은 그대로 둔다."""
    x0, y0, x1, y1 = box
    reach = max(2, round(BOX_FIT_REACH * (y1 - y0)))
    top, bottom = max(0, y0 - reach), min(image.shape[0], y1 + reach)
    rows = ink_mask(image[top:bottom, x0:x1]).mean(axis=1) >= BOX_FIT_INK
    y = y0 - top
    up = y0
    while y > 0 and rows[y - 1]:
        y -= 1
    if y > 0 or top == 0:
        up = top + y
    y = y1 - top
    down = y1
    while y < rows.size and rows[y]:
        y += 1
    if y < rows.size or bottom == image.shape[0]:
        down = top + y
    return x0, up, x1, down


def _cut_line_boxes(image, boxes, results, margin):
    """영역 위아래 끝에서 잘린 이웃 줄 조각의 상자 번호.

    드래그가 이웃 줄을 걸치면 여백 덕분에 위치 찾기가 잘린 글자까지 찾고 모델은 없는 글자로 읽는다. 글자 픽셀이 영역 끝 행에
    닿고, 다른 줄보다 낮고, 모델도 확신하지 못하는 상자만 고른다. image는 여백을 두른 이미지이고 boxes는 그 좌표다.
    """
    read = [index for index, result in enumerate(results) if result[0].strip()]
    height = image.shape[0] - 2 * margin

    def seen(box):  # 상자는 여백으로 번지므로 영역 안의 높이만 잰다
        return min(box[3] - margin, height) - max(box[1] - margin, 0)

    def is_cut(index, line, row):
        box, score = boxes[index], results[index][1]
        share = seen(box) / line
        return (share < CUT_LINE_HEIGHT and (score < CUT_LINE_SCORE or (share < CUT_LINE_SHORT and score < CUT_LINE_SHORT_SCORE))
                and ink_mask(image[margin:margin + height, box[0]:box[2]])[row].any())

    cut = set()
    for row, touches in ((0, lambda box: box[1] - margin <= 1), (height - 1, lambda box: box[3] - margin >= height - 1)):
        others = [seen(boxes[index]) for index in read if not touches(boxes[index])]
        if others:
            line = float(np.median(others))
            cut.update(index for index in read if touches(boxes[index]) and is_cut(index, line, row))
    return cut


def _fragment_boxes(boxes, results):
    """큰 글자 옆에 붙은 낮은 점수의 짧은 조각. 획이나 글자 틈이 따로 찾힌 것이라 '−', '(', 'c' 같은 없는 글자가 된다."""
    fragments = set()
    for index, (box, (text, score, _)) in enumerate(zip(boxes, results)):
        text, height = text.strip(), box[3] - box[1]
        if not text or score >= FRAGMENT_SCORE or len(text) > FRAGMENT_CHARS or text[0] in FRAGMENT_KEEP:
            continue
        for other, (other_text, other_score, _) in zip(boxes, results):
            tall = other[3] - other[1]
            if (tall >= FRAGMENT_HEIGHT * height and other_score >= FRAGMENT_NEIGHBOR and other_text.strip()
                    and min(box[3], other[3]) - max(box[1], other[1]) >= FRAGMENT_OVERLAP * height
                    and max(box[0], other[0]) - min(box[2], other[2]) <= FRAGMENT_REACH * tall):
                fragments.add(index)
                break
    return fragments


def _median_height(boxes):
    """상자 높이의 중앙값. 상자가 없으면 0."""
    return float(np.median([y1 - y0 for _, y0, _, y1 in boxes])) if boxes else 0.0


def _shrunk_boxes(boxes, factor):
    """확대한 이미지의 상자를 확대 전 좌표로."""
    if factor == 1:
        return boxes
    return [(x0 // factor, y0 // factor, max(x0 // factor + 2, -(-x1 // factor)), max(y0 // factor + 2, -(-y1 // factor))) for x0, y0, x1, y1 in boxes]


def _grown_boxes(boxes, factor):
    return [tuple(value * factor for value in box) for box in boxes]


def _lost_share(first, again, shape):
    """첫 결과 상자 폭 중 다시 찾은 상자가 절반도 덮지 못한 비율. 상자는 모두 같은 좌표(shape 크기의 이미지)다.

    2배로 찾은 상자는 표 칸을 나눠 1배 상자를 다 덮지 않는 게 보통이라, 줄이 통째로 빠진 것만 크게 잡히게 폭으로 센다.
    """
    covered = np.zeros(shape[:2], dtype=bool)
    for x0, y0, x1, y1 in again:
        covered[max(0, y0):y1, max(0, x0):x1] = True
    total = lost = 0
    for x0, y0, x1, y1 in first:
        width = max(1, x1 - x0)
        total += width
        region = covered[max(0, y0):y1, max(0, x0):x1]
        if region.size and region.mean() < 0.5:
            lost += width
    return lost / total if total else 0.0


def _out_of_memory(error):
    """큰 입력을 포기하고 앞 결과로 계속할 오류인가. onnxruntime의 할당 실패는 RuntimeError가 아닌 자체 예외다."""
    return type(error).__name__ in OUT_OF_MEMORY


def _scaled_grid(grid, factor, shift):
    """격자 좌표를 factor배 한 뒤 shift를 뺀다."""
    def x(value):
        return value * factor - shift

    cells = tuple(GridCell(c.row, c.column, c.row_span, c.column_span, x(c.left), x(c.top), x(c.right), x(c.bottom)) for c in grid.cells)
    return Grid(grid.rows, grid.columns, cells, x(grid.left), x(grid.top), x(grid.right), x(grid.bottom))


class _ReleasingSession:
    """모델 세션에 실행 옵션(실행이 끝나면 계산 메모리를 돌려준다)을 붙인다.

    onnxruntime은 한 번 쓴 계산 메모리를 다음 실행을 위해 붙잡아 둔다. A4 한 쪽이면 인식이 끝난 뒤에도 약 700MB가
    남았고, 돌려주게 하면 220MB로 줄었다(속도·판독 같음, 2026-11-08). 부르는 모양 run(names, feed)은 그대로다.
    """

    def __init__(self, session, run_options):
        self._session = session
        self._run_options = run_options

    def run(self, output_names, input_feed, run_options=None):
        return self._session.run(output_names, input_feed, run_options or self._run_options)

    def get_outputs(self):
        return self._session.get_outputs()


class OcrEngine:
    """번들 모델 세션을 들고 RGB 배열의 글자 상자를 읽는다. 세션 생성은 무겁다."""

    _sharp = None  # 이번 인식에서 글자 모양을 잴 확대 전 이미지와 배율. 상자를 직접 읽을 때는 없다
    _char_marks = {}  # 이번 인식의 상자 번호별 확신도가 낮은 글자 위치
    _pool = None   # 큰 이미지 계산을 나눌 스레드 묶음(스레드 하나면 없다)
    _runner = None  # 인식 모델을 차례로 돌릴 스레드(스레드 하나면 없고 부른 스레드에서 돈다)
    _waiting = ()   # 다음 위치 찾기 모델이 돌기 시작할 때 다른 스레드에 넘길 일(_Deferred)

    def __init__(self, directory=None, threads=None):
        import onnxruntime as ort  # 처음 인식할 때만 불러온다

        files = verify_models(directory)
        ort.disable_telemetry_events()
        workers = threads or min(4, os.cpu_count() or 1)
        # 큰 이미지의 크기 바꾸기·2배는 모델과 같은 수의 스레드로 나눠 한다. 모델이 도는 동안에는 쉬므로 서로 다투지 않는다
        self._pool = ThreadPoolExecutor(workers, thread_name_prefix="screen-text") if workers > 1 else None
        # 인식 모델은 이 스레드 하나에서 차례로 돈다. 그동안 부른 쪽은 앞 묶음의 글자 규칙과 다음 묶음의 입력을 만든다
        self._runner = ThreadPoolExecutor(1, thread_name_prefix="screen-text-model") if workers > 1 else None

        def session(path, arena):
            options = ort.SessionOptions()
            options.intra_op_num_threads = workers
            options.inter_op_num_threads = 1
            if not arena:
                options.enable_cpu_mem_arena = False
                # 같은 모양 입력을 두 번째 돌릴 때 미리 짜 둔 메모리 묶음이 첫 실행보다 약 100MB 컸다(A4 한 쪽을 다시 읽으면
                # 최대 633→527MB, 판독·시간 같음, 2026-11-08). 띠로 나눠 찾으면 한 번 읽는 동안에도 같은 모양이 거듭된다
                options.enable_mem_pattern = False
            release = ort.RunOptions()
            if options.enable_cpu_mem_arena:   # 아레나가 없는 세션에 이 옵션을 주면 실행이 거부된다(InvalidArgument)
                release.add_run_config_entry("memory.enable_memory_arena_shrinkage", "cpu:0")
            return _ReleasingSession(ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"]), release)

        # 위치 찾기는 몇 번만 크게 돌아 메모리를 운영체제에서 바로 받고 돌려준다. 인식은 작은 실행이 많아 아레나를 두고(없으면
        # 1.7배 느렸다) 실행이 끝날 때마다 돌려준다
        self._det = session(files["det"], arena=False)
        self._rec = session(files["rec"], arena=True)
        self._charset = load_charset(files["dict"])
        if self._rec.get_outputs()[0].shape[-1] != len(self._charset) + 1:
            raise ModelIntegrityError("인식 모델과 사전이 맞지 않습니다")

    def recognize(self, image, cancelled=lambda: False):
        """RGB 배열(H, W, 3)의 글자 상자를 원본 좌표로 돌려준다(기운 스캔본은 바로 세운 뒤의 좌표). 취소되면 RecognitionCancelled."""
        if cancelled():
            raise RecognitionCancelled
        self._waiting = ()
        height, width = image.shape[:2]
        scale = min(UPSCALE, MAX_SIDE / max(width, height))
        work = image
        if scale != 1.0:
            size = (max(1, round(width * scale)), max(1, round(height * scale)))
            work = np.clip(resize_bilinear(image, *size), 0, 255).astype(np.uint8)
        margin = DET_MARGIN
        plain = work
        work = sharp = add_margin(plain, margin)   # 기호·틈은 확대 전의 또렷한 픽셀로 잰다
        factor = 1
        self._components = None
        # 첫 위치 찾기 모델이 도는 동안(입력이 작아 메모리를 적게 쓴다) 다른 스레드에서 기울기를 잴 화면 전체의 글자 픽셀과 표 선을
        # 찾을 회색 그림을 차례로 만든다. 둘 다 그림 크기의 실수 사본을 잠깐 만들어, 큰 입력으로 찾는 동안에 만들면 최대 메모리가 늘었다
        early = _Deferred(self._pool, _skew_and_gray, plain, sharp) if self._pool is not None else None
        self._waiting = () if early is None else (early,)
        boxes = self._detect(work, cancelled)
        if cancelled():
            raise RecognitionCancelled
        skew = skew_angle(self._components, plain, None if early is None else (lambda: early.result()[0])) if self._components else 0.0
        self._components = None
        gray = None if early is None or skew else early.result()[1]   # 기운 그림을 돌리면 회색 그림도 새로 만든다
        early = None
        if skew:    # 기운 스캔본은 바로 세워 다시 찾는다. 돌린 뒤의 좌표로 돌려주지만 상자는 서로의 위치만 쓰인다
            work = sharp = add_margin(straighten(plain, skew), margin)
            boxes = self._detect(work, cancelled)
            if cancelled():
                raise RecognitionCancelled
        # 표 선 후보는 글자 상자와 상관없다. 다음 위치 찾기 모델이 도는 동안(GIL을 놓는다) 다른 스레드에서 잰다
        lines = _Deferred(self._pool, grid_lines, sharp, gray)
        self._waiting = (lines,)
        gray = None
        text_height = _median_height(boxes)
        side = max(work.shape[:2])
        double = bool(boxes) and text_height < SMALL_TEXT_PX and 2 * side <= MAX_SIDE
        if not double and side > DET_LIMIT and (text_height * DET_LIMIT / side < SMALL_TEXT_PX or side > 2 * DET_LIMIT):
            # 줄여서 찾았더니 글자가 작았다(글자를 못 찾은 경우 포함). 반 넘게 줄인 첫 결과는 여러 줄이 한 덩어리가 되어 큰
            # 글자처럼 보이므로(4K 폭으로 고른 문단 다섯 줄이 높이 180px 상자 하나) 늘 원래 크기로 다시 찾는다. 줄인 상자는
            # 높이도 부풀어(17px 글자가 22px) 넓게 고른 작은 글씨를 2배로 읽지 않았으므로 다시 찾은 상자로 한 번 더 판단한다.
            # 20~21px는 2배로 읽어도 득실이 반반이고 ②③을 2·3으로 읽는 일이 잦았다(평가 자료 15,889장, 2026-11-08)
            again = self._detect_again(work, 1, cancelled)
            if again is not None:
                boxes = again[1]
                double = bool(boxes) and _median_height(boxes) < SMALL_TEXT_RECHECK_PX and 2 * side <= MAX_SIDE
        if double:
            again = self._detect_again(work, 2, cancelled, boxes)
            if again is not None:
                work, boxes = again
                factor = 2
                scale *= 2
                margin *= 2
        if cancelled():
            raise RecognitionCancelled
        self._waiting = ()
        boxes = [fit_to_ink(work, box) for box in boxes]
        grids = find_grids(sharp, _shrunk_boxes(boxes, factor), DET_MARGIN, lines.result())
        if grids:
            boxes = fit_boxes(work, boxes, [_scaled_grid(grid, factor, 0) for grid in grids], factor)
            if cancelled():
                raise RecognitionCancelled
        shrunk = _shrunk_boxes(boxes, factor)
        added = len(boxes)
        boxes = boxes + _grown_boxes(empty_cell_boxes(sharp, grids, shrunk, DET_MARGIN) + gap_mark_boxes(sharp, shrunk, grids), factor)
        self._sharp, self._char_marks = (sharp, factor), {}
        try:
            read = self._read(work, boxes, cancelled)
            marks = self._char_marks
        finally:
            self._sharp = self._components = None
        results = read_marks(sharp, grids, _shrunk_boxes(boxes, factor), apply_leading_symbols(sharp, _shrunk_boxes(boxes, factor), read, grids), added)
        cut = _cut_line_boxes(sharp, _shrunk_boxes(boxes, factor), results, DET_MARGIN) | _fragment_boxes(boxes, results)
        out = []
        for index, ((x0, y0, x1, y1), (text, score, unsure_prefix)) in enumerate(zip(boxes, results)):
            text = text.strip()
            if text and index not in cut:
                shift = len(text) - len(read[index][0].strip())  # 기호는 앞에만 붙으므로 뒤에서 잰 위치는 그대로다
                chars = tuple(position + shift for position in marks.get(index, ()) if position + shift >= 0)
                out.append(TextBox(max(0, round((x0 - margin) / scale)), max(0, round((y0 - margin) / scale)),
                                   max(1, round((x1 - x0) / scale)), max(1, round((y1 - y0) / scale)),
                                   text, score, unsure_prefix, chars))
        return RecognizedBoxes(out, [_scaled_grid(grid, factor / scale, DET_MARGIN * factor / scale) for grid in grids])

    def _detect_again(self, image, factor, cancelled, first=()):
        """더 큰 입력으로 다시 찾는다. 메모리가 모자라면 None을 돌려 첫 결과로 계속한다.

        정확히 2배로 키운 입력에서 위치 모델이 글자를 통째로 놓칠 때가 있다(엑셀 표의 제목 열. 1.98배·2.02배에서는 찾는다).
        2배 결과가 첫 결과 first(image 좌표)의 상자 폭을 많이 잃었으면 입력을 조금 줄여 한 번 더 찾고, first를 거의 다 덮을
        때만 그 결과를 쓴다. 잃은 것이 적으면 다시 찾지 않는다.

        1배는 줄이지 않는다. 2배는 전처럼 긴 변 DET_LIMIT_SMALL까지 줄이되 원래 영역의 DET_SMALL_MIN_SCALE배 아래로는 줄이지
        않는다. 넓은 영역을 1,920px로 줄이면 위치 모델이 보는 글자가 작아져 같은 글자도 틀렸다(같은 쪽을 3,840px 폭으로 고르면
        글자 오류 7.7→36.6%, 2026-11-08). 넘치는 입력은 _detect가 띠로 나눠 찾는다.
        """
        try:
            work = double_size(image, self._pool) if factor == 2 else image
            side = max(work.shape[:2])
            limit = max(DET_LIMIT_SMALL, round(side * DET_SMALL_MIN_SCALE / 2)) if factor == 2 else side
            boxes = self._detect(work, cancelled, limit)
        except RecognitionCancelled:
            raise
        except Exception as error:
            if not _out_of_memory(error):
                raise
            return None
        limit = int(max(work.shape[:2]) * RETRY_SCALE)   # 이미 상한까지 줄여 찾은 큰 입력은 다시 찾아도 같은 입력이다
        if factor == 2 and first and limit < DET_LIMIT_SMALL and _lost_share(first, _shrunk_boxes(boxes, 2), image.shape) >= RETRY_LOST:
            try:
                retry = self._detect(work, cancelled, limit)
            except RecognitionCancelled:
                raise
            except Exception as error:   # 다시 찾기만 포기하고 2배 결과로 계속한다
                if not _out_of_memory(error):
                    raise
                retry = None
            if retry is not None and _lost_share(first, _shrunk_boxes(retry, 2), image.shape) < RETRY_RECOVERED:
                boxes = retry
        return work, boxes

    def _detect(self, image, cancelled=lambda: False, limit=None):
        """글자 상자를 image 좌표로 찾는다. 긴 변을 limit(없으면 DET_LIMIT) 안으로 줄여 모델에 넣는다.

        줄인 입력의 긴 변이 DET_LIMIT_SMALL을 넘으면 가로 띠로 나눠 찾는다(띠 하나는 DET_TILE_AREA 이하, 4K 화면 한 장을
        한 번에 넣으면 870만 화소다). 띠는 글자 줄을 자르지 않게 폭 전체를 쓰고 이웃 띠와 DET_TILE_OVERLAP 이상 겹친다.
        상자는 가운데가 그 띠의 몫(겹친 구간의 가운데에서 나눈다)에 든 것만 쓴다.
        """
        if cancelled():
            raise RecognitionCancelled
        height, width = image.shape[:2]
        ratio = min(1.0, (limit or DET_LIMIT) / max(height, width))
        new_h, new_w = max(1, int(round(height * ratio))), max(1, int(round(width * ratio)))
        strip = max(DET_TILE_OVERLAP + 64, DET_TILE_AREA // (-(-new_w // 32) * 32) // 32 * 32)
        if max(new_h, new_w) <= DET_LIMIT_SMALL or strip >= new_h:
            return self._detect_rows(image, new_w, new_h, 0, new_h, cancelled)
        count = -(-(new_h - DET_TILE_OVERLAP) // (strip - DET_TILE_OVERLAP))
        tops = [round(k * (new_h - strip) / (count - 1)) for k in range(count)]
        edges = [0] + [(tops[k + 1] + tops[k] + strip) / 2 for k in range(count - 1)] + [new_h]
        boxes = []
        # 다음 띠의 입력을 앞 띠의 모델이 도는 동안 만들면 FHD·QHD에서 0.12초 빨랐지만 최대 메모리가 입력 하나(약 32MB)만큼 늘어
        # 그렇게 하지 않는다(2026-11-09). 띠의 입력은 실수 사본 없이 바로 채운다
        for k, top in enumerate(tops):
            for box in self._detect_rows(image, new_w, new_h, top, top + strip, cancelled):
                if edges[k] <= (box[1] + box[3]) / 2 * new_h / height < edges[k + 1]:
                    boxes.append(box)
        self._components = None   # 기울기는 줄여 찾은 첫 결과로만 잰다
        return boxes

    def _detect_rows(self, image, new_w, new_h, top, bottom, cancelled):
        """image를 new_w×new_h로 바꾼 그림의 top~bottom 줄에서 글자 상자를 찾아 image 좌표로 돌려준다."""
        return self._det_boxes(_det_input(image, new_w, new_h, top, bottom, self._pool), image, new_w, new_h, top, cancelled)

    def _det_boxes(self, prepared, image, new_w, new_h, top, cancelled):
        """위치 찾기 모델 입력 prepared=(입력, 줄 수)(그림의 top 줄부터)에서 글자 상자를 찾아 image 좌표로 돌려준다."""
        tensor, rows = prepared
        height, width = image.shape[:2]
        if cancelled():
            raise RecognitionCancelled
        for task in self._waiting:   # 모델이 도는 동안(GIL을 놓는다) 미뤄 둔 일을 다른 스레드에서 한다
            task.start()
        prob = self._det.run(None, {"x": tensor})[0][0, 0][:rows, :new_w]
        scale_x, scale_y = width / new_w, height / new_h
        boxes = []
        self._components = label_components(prob > DET_THRESHOLD, cancelled)
        for x0, y0, x1, y1, runs in self._components:
            if (x1 - x0 + 1) * (y1 - y0 + 1) < MIN_BOX_AREA:
                continue
            score = float(np.mean(np.concatenate([prob[y, a:b + 1] for y, a, b in runs])))
            if score < BOX_THRESHOLD:
                continue
            fx0, fy0, fx1, fy1 = expand_box(x0, y0, x1, y1)
            box = (max(0, int(fx0 * scale_x)), max(0, int((fy0 + top) * scale_y)),
                   min(width, int(round(fx1 * scale_x))), min(height, int(round((fy1 + top) * scale_y))))
            if box[2] - box[0] >= 2 and box[3] - box[1] >= 2:
                boxes.append(box)
        return boxes

    def _note_unsure(self, index, text, pieces, runs, doubtful=()):
        """확신도가 낮은 글자와 화면 모양이 판독과 어긋난 글자(doubtful, CTC 위치)의 text 안 위치를 적어 둔다. 화면 모양으로 고친 글자는 표시하지 않는다."""
        low = {(char, center) for char, center, _, best in runs if best < CHAR_UNSURE and char != " "}
        low.update(piece for piece in pieces if piece[1] in doubtful)
        if not low:
            return
        flags = iter([piece in low for piece in pieces if piece[0] != " "])
        marks = tuple(position for position, char in enumerate(text) if char != " " and next(flags, False))
        if marks:
            self._char_marks[index] = marks

    def _read(self, image, boxes, cancelled):
        """상자를 읽는다. 글자 모양·틈은 이번 인식의 확대 전 이미지(self._sharp)에서 잰다.

        모델 실행 스레드(self._runner)가 있으면 다음 묶음을 모델에 먼저 넘겨 두고, 모델이 도는 동안 앞 묶음의 글자 규칙을 잰다.
        모델은 한 번에 한 묶음씩 같은 순서로 돌고 묶음 구성도 같아 결과는 차례로 읽을 때와 같다(2026-11-09).
        """
        if cancelled():
            raise RecognitionCancelled
        sharp, factor = self._sharp or (image, 1)
        if len(boxes) > MAX_REC_BOXES:
            raise RecognitionLimitError
        widths = []
        for x0, y0, x1, y1 in boxes:
            crop = image[y0:y1, x0:x1]
            crop_width = max(8, int(np.ceil(REC_HEIGHT * crop.shape[1] / max(1, crop.shape[0]))))
            if crop_width > MAX_REC_WIDTH:
                raise RecognitionLimitError
            widths.append(crop_width)
        results = [("", 0.0)] * len(boxes)
        order = sorted(range(len(boxes)), key=lambda i: widths[i])
        batches, start = [], 0
        while start < len(order):
            end = start + 1
            while (end < min(start + REC_BATCH, len(order))
                   and widths[order[end]] * (end - start + 1) <= MAX_REC_BATCH_WIDTH):
                end += 1
            batches.append(order[start:end])
            start = end

        def model_input(ids):
            if cancelled():
                raise RecognitionCancelled
            batch = np.zeros((len(ids), 3, REC_HEIGHT, widths[ids[-1]]), dtype=np.float32)
            for slot, i in enumerate(ids):
                if cancelled():
                    raise RecognitionCancelled
                x0, y0, x1, y1 = boxes[i]
                crop = resize_bilinear(image[y0:y1, x0:x1], widths[i], REC_HEIGHT)[:, :, ::-1]
                batch[slot, :, :, : widths[i]] = ((crop / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)
            if cancelled():
                raise RecognitionCancelled
            return batch

        def run(batch):
            return self._rec.run(None, {"x": batch})[0]

        if self._runner is None:
            for ids in batches:
                self._finish_batch(ids, run(model_input(ids)), widths, boxes, sharp, factor, results, cancelled)
            return results
        started = []
        try:
            started.append(self._runner.submit(run, model_input(batches[0])) if batches else None)
            for k, ids in enumerate(batches):
                if k + 1 < len(batches):   # 앞 묶음이 모델에서 도는 동안 다음 묶음의 입력을 만들어 줄 세운다
                    started.append(self._runner.submit(run, model_input(batches[k + 1])))
                probs = started[k].result()
                started[k] = None   # 다 쓴 결과는 놓는다
                self._finish_batch(ids, probs, widths, boxes, sharp, factor, results, cancelled)
                del probs
        finally:
            for future in started:   # 취소·오류로 그만두면 아직 시작하지 않은 묶음은 돌리지 않는다
                if future is not None:
                    future.cancel()
        return results

    def _finish_batch(self, ids, probs, widths, boxes, sharp, factor, results, cancelled):
        """모델이 읽은 한 묶음의 확률에서 글자를 풀고 화면 모양 규칙을 적용해 results에 넣는다."""
        widest = widths[ids[-1]]
        for slot, i in enumerate(ids):
            if cancelled():
                raise RecognitionCancelled
            steps = max(1, int(np.ceil(probs.shape[1] * widths[i] / widest)))
            text, score = ctc_decode(probs[slot, :steps], self._charset)  # 진단 도구가 가로채는 지점: 상자마다 한 번
            runs = _ctc_runs(probs[slot, :steps], self._charset)
            pieces = [(char, center) for char, center, _, _ in runs]
            if "".join(char for char, _ in pieces) == text:  # 글자와 위치가 맞을 때만 공백 위치를 쓴다
                x0, y0, x1, y1 = _shrunk_boxes([boxes[i]], factor)[0]
                crop = sharp[y0:y1, x0:x1]
                with shared_ink():   # 아래 규칙들이 같은 crop의 글자 픽셀 기준을 한 번만 잰다
                    pieces = rescue_marks(pieces, probs[slot, :steps], self._charset)
                    pieces = restore_corner_brackets(pieces, crop, steps, x1 - x0)
                    pieces = restore_inline_checkboxes(pieces, crop, steps, x1 - x0)
                    pieces = restore_triangles(pieces, crop, steps, x1 - x0)
                    pieces = restore_stars(pieces, crop, steps, x1 - x0)
                    pieces = restore_circled_digits(pieces, crop, steps, x1 - x0)
                    pieces = restore_thin_capitals(pieces, crop, steps, x1 - x0)
                    pieces = restore_roman(pieces, crop, steps, x1 - x0)
                    pieces, doubtful_units = restore_units(pieces, crop, steps, x1 - x0)
                    pieces, doubtful = restore_number_marks(pieces, sharp, (x0, y0, x1, y1), steps)
                    doubtful += doubtful_units
                    has_space = self._charset[-1:] == [" "]  # 공백은 사전의 마지막이다
                    spaces = probs[slot, :steps, len(self._charset)] if has_space else np.zeros(steps, np.float32)
                    text = join_words(pieces, spaces, crop, steps, x1 - x0)
                self._note_unsure(i, text, pieces, runs, doubtful)
            results[i] = (text, score)
