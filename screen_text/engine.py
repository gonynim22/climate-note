"""PP-OCR 위치 모델과 한국어 인식 모델로 글자 상자를 읽는다.

Qt를 import하지 않는다. numpy와 onnxruntime만 쓰며, MANIFEST.json의 크기와
SHA-256을 확인한 번들 모델만 불러온다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from app_paths import resource_root
from screen_text.cell_marks import empty_cell_boxes, gap_mark_boxes, read_marks
from screen_text.corner_brackets import restore_corner_brackets
from screen_text.deskew import skew_angle, straighten
from screen_text.layout import Grid, GridCell, RecognizedBoxes, TextBox
from screen_text.leading_symbols import apply_leading_symbols, ink_mask, restore_inline_checkboxes
from screen_text.marks import rescue_marks, restore_circled_digits, restore_stars, restore_thin_capitals
from screen_text.table_lines import RIDGE_CONTRAST, find_grids, fit_boxes
from screen_text.triangles import restore_triangles
from screen_text.word_spaces import join_words

DET_LIMIT = 960            # 위치 모델 입력의 긴 변 상한
DET_LIMIT_SMALL = 1920     # 작은 글씨를 2배로 다시 찾을 때의 긴 변 상한
DET_MARGIN = 32            # 위치 찾기 전에 이미지 둘레에 두르는 배경 여백(픽셀). 영역을 바짝 골라도 가장자리 글자를 놓치지 않는다
RULE_PAST_TEXT = 2         # 표 세로선은 글자보다 이만큼(픽셀) 더 뻗는다. 바짝 고른 글자의 세로획은 글자와 함께 끝난다
SMALL_TEXT_PX = 22         # 상자 높이 중앙값이 이보다 작으면 2배로 키워 다시 찾고 읽는다
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


def resize_bilinear(image, width, height):
    """numpy 이중선형 크기 변경. 크게 줄일 때는 정수 배 평균으로 먼저 줄인다."""
    source = image.astype(np.float32)
    src_h, src_w = source.shape[:2]
    if (width, height) == (src_w, src_h):
        return source
    factor = int(min(src_w / width, src_h / height))
    if factor >= 2:
        cut_h, cut_w = src_h // factor * factor, src_w // factor * factor
        source = source[:cut_h, :cut_w].reshape(cut_h // factor, factor, cut_w // factor, factor, -1).mean(axis=(1, 3))
        src_h, src_w = source.shape[:2]
    ys = np.clip((np.arange(height, dtype=np.float32) + 0.5) * (src_h / height) - 0.5, 0, src_h - 1)
    xs = np.clip((np.arange(width, dtype=np.float32) + 0.5) * (src_w / width) - 0.5, 0, src_w - 1)
    y0, x0 = np.floor(ys).astype(np.int32), np.floor(xs).astype(np.int32)
    y1, x1 = np.minimum(y0 + 1, src_h - 1), np.minimum(x0 + 1, src_w - 1)
    wy, wx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    top = source[y0][:, x0] * (1 - wx) + source[y0][:, x1] * wx
    bottom = source[y1][:, x0] * (1 - wx) + source[y1][:, x1] * wx
    return top * (1 - wy) + bottom * wy


def double_size(image):
    """uint8 이미지를 2배로(이중선형과 같은 3:1 가중). 큰 쪽 이미지를 실수 배열로 만들지 않아 메모리를 아낀다."""
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


def _cut_rules(image, color):
    """고른 영역의 위아래 끝까지 이어진 표 세로선의 열 번호."""
    ink = np.abs(image.astype(np.int16) - color).max(axis=2) > RIDGE_CONTRAST
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


def _shrunk_boxes(boxes, factor):
    """확대한 이미지의 상자를 확대 전 좌표로."""
    if factor == 1:
        return boxes
    return [(x0 // factor, y0 // factor, max(x0 // factor + 2, -(-x1 // factor)), max(y0 // factor + 2, -(-y1 // factor))) for x0, y0, x1, y1 in boxes]


def _grown_boxes(boxes, factor):
    return [tuple(value * factor for value in box) for box in boxes]


def _scaled_grid(grid, factor, shift):
    """격자 좌표를 factor배 한 뒤 shift를 뺀다."""
    def x(value):
        return value * factor - shift

    cells = tuple(GridCell(c.row, c.column, c.row_span, c.column_span, x(c.left), x(c.top), x(c.right), x(c.bottom)) for c in grid.cells)
    return Grid(grid.rows, grid.columns, cells, x(grid.left), x(grid.top), x(grid.right), x(grid.bottom))


class OcrEngine:
    """번들 모델 세션을 들고 RGB 배열의 글자 상자를 읽는다. 세션 생성은 무겁다."""

    _sharp = None  # 이번 인식에서 글자 모양을 잴 확대 전 이미지와 배율. 상자를 직접 읽을 때는 없다
    _char_marks = {}  # 이번 인식의 상자 번호별 확신도가 낮은 글자 위치

    def __init__(self, directory=None, threads=None):
        import onnxruntime as ort  # 처음 인식할 때만 불러온다

        files = verify_models(directory)
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads or min(4, os.cpu_count() or 1)
        options.inter_op_num_threads = 1
        providers = ["CPUExecutionProvider"]
        self._det = ort.InferenceSession(str(files["det"]), options, providers=providers)
        self._rec = ort.InferenceSession(str(files["rec"]), options, providers=providers)
        self._charset = load_charset(files["dict"])
        if self._rec.get_outputs()[0].shape[-1] != len(self._charset) + 1:
            raise ModelIntegrityError("인식 모델과 사전이 맞지 않습니다")

    def recognize(self, image, cancelled=lambda: False):
        """RGB 배열(H, W, 3)의 글자 상자를 원본 좌표로 돌려준다(기운 스캔본은 바로 세운 뒤의 좌표). 취소되면 RecognitionCancelled."""
        if cancelled():
            raise RecognitionCancelled
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
        boxes = self._detect(work, cancelled)
        if cancelled():
            raise RecognitionCancelled
        skew = skew_angle(self._components, plain) if self._components else 0.0
        self._components = None
        if skew:    # 기운 스캔본은 바로 세워 다시 찾는다. 돌린 뒤의 좌표로 돌려주지만 상자는 서로의 위치만 쓰인다
            work = sharp = add_margin(straighten(plain, skew), margin)
            boxes = self._detect(work, cancelled)
            if cancelled():
                raise RecognitionCancelled
        text_height = float(np.median([y1 - y0 for _, y0, _, y1 in boxes])) if boxes else 0.0
        side = max(work.shape[:2])
        if boxes and text_height < SMALL_TEXT_PX and 2 * side <= MAX_SIDE:
            again = self._detect_again(work, 2, cancelled)
            if again is not None:
                work, boxes = again
                factor = 2
                scale *= 2
                margin *= 2
        elif side > DET_LIMIT and text_height * DET_LIMIT / side < SMALL_TEXT_PX:  # 줄여서 찾았더니 글자가 작았다(글자를 못 찾은 경우 포함)
            again = self._detect_again(work, 1, cancelled)
            if again is not None:
                boxes = again[1]
        if cancelled():
            raise RecognitionCancelled
        boxes = [fit_to_ink(work, box) for box in boxes]
        grids = find_grids(sharp, _shrunk_boxes(boxes, factor), DET_MARGIN)
        if grids:
            boxes = fit_boxes(work, boxes, [_scaled_grid(grid, factor, 0) for grid in grids], factor)
            if cancelled():
                raise RecognitionCancelled
        shrunk = _shrunk_boxes(boxes, factor)
        added = len(boxes)
        boxes = boxes + _grown_boxes(empty_cell_boxes(sharp, grids, shrunk) + gap_mark_boxes(sharp, shrunk), factor)
        self._sharp, self._char_marks = (sharp, factor), {}
        try:
            read = self._read(work, boxes, cancelled)
            marks = self._char_marks
        finally:
            self._sharp = self._components = None
        results = read_marks(sharp, grids, _shrunk_boxes(boxes, factor), apply_leading_symbols(sharp, _shrunk_boxes(boxes, factor), read), added)
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

    def _detect_again(self, image, factor, cancelled):
        """더 큰 입력으로 다시 찾는다. 메모리가 모자라면 None을 돌려 첫 결과로 계속한다."""
        try:
            work = double_size(image) if factor == 2 else image
            return work, self._detect(work, cancelled, DET_LIMIT_SMALL)
        except RecognitionCancelled:
            raise
        except Exception as error:  # onnxruntime의 할당 실패는 RuntimeError가 아닌 자체 예외다
            if type(error).__name__ not in OUT_OF_MEMORY:
                raise
            return None

    def _detect(self, image, cancelled=lambda: False, limit=None):
        if cancelled():
            raise RecognitionCancelled
        height, width = image.shape[:2]
        ratio = min(1.0, (limit or DET_LIMIT) / max(height, width))
        new_h, new_w = max(1, int(round(height * ratio))), max(1, int(round(width * ratio)))
        small = resize_bilinear(image, new_w, new_h)
        color = np.median(np.concatenate((small[0], small[-1], small[:, 0], small[:, -1])), axis=0)
        canvas = np.empty((-(-new_h // 32) * 32, -(-new_w // 32) * 32, 3), dtype=np.float32)  # 32 배수로 늘이지 않고 채운다(글자가 찌그러지지 않는다)
        canvas[:] = color
        canvas[:new_h, :new_w] = small
        tensor = canvas[:, :, ::-1] / 255.0  # 모델은 BGR 순서로 학습됐다
        tensor = ((tensor - DET_MEAN) / DET_STD).transpose(2, 0, 1)[None].astype(np.float32)
        if cancelled():
            raise RecognitionCancelled
        prob = self._det.run(None, {"x": tensor})[0][0, 0][:new_h, :new_w]
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
            box = (max(0, int(fx0 * scale_x)), max(0, int(fy0 * scale_y)),
                   min(width, int(round(fx1 * scale_x))), min(height, int(round(fy1 * scale_y))))
            if box[2] - box[0] >= 2 and box[3] - box[1] >= 2:
                boxes.append(box)
        return boxes

    def _note_unsure(self, index, text, pieces, runs):
        """확신도가 낮은 글자의 text 안 위치를 적어 둔다. 화면 모양으로 고친 글자는 표시하지 않는다."""
        low = {(char, center) for char, center, _, best in runs if best < CHAR_UNSURE and char != " "}
        if not low:
            return
        flags = iter([piece in low for piece in pieces if piece[0] != " "])
        marks = tuple(position for position, char in enumerate(text) if char != " " and next(flags, False))
        if marks:
            self._char_marks[index] = marks

    def _read(self, image, boxes, cancelled):
        """상자를 읽는다. 글자 모양·틈은 이번 인식의 확대 전 이미지(self._sharp)에서 잰다."""
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
        start = 0
        while start < len(order):
            if cancelled():
                raise RecognitionCancelled
            end = start + 1
            while (end < min(start + REC_BATCH, len(order))
                   and widths[order[end]] * (end - start + 1) <= MAX_REC_BATCH_WIDTH):
                end += 1
            ids = order[start:end]
            widest = widths[ids[-1]]
            batch = np.zeros((len(ids), 3, REC_HEIGHT, widest), dtype=np.float32)
            for slot, i in enumerate(ids):
                if cancelled():
                    raise RecognitionCancelled
                x0, y0, x1, y1 = boxes[i]
                crop = resize_bilinear(image[y0:y1, x0:x1], widths[i], REC_HEIGHT)[:, :, ::-1]
                batch[slot, :, :, : widths[i]] = ((crop / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)
            if cancelled():
                raise RecognitionCancelled
            probs = self._rec.run(None, {"x": batch})[0]
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
                    pieces = rescue_marks(pieces, probs[slot, :steps], self._charset)
                    pieces = restore_corner_brackets(pieces, crop, steps, x1 - x0)
                    pieces = restore_inline_checkboxes(pieces, crop, steps, x1 - x0)
                    pieces = restore_triangles(pieces, crop, steps, x1 - x0)
                    pieces = restore_stars(pieces, crop, steps, x1 - x0)
                    pieces = restore_circled_digits(pieces, crop, steps, x1 - x0)
                    pieces = restore_thin_capitals(pieces, crop, steps, x1 - x0)
                    has_space = self._charset[-1:] == [" "]  # 공백은 사전의 마지막이다
                    spaces = probs[slot, :steps, len(self._charset)] if has_space else np.zeros(steps, np.float32)
                    text = join_words(pieces, spaces, crop, steps, x1 - x0)
                    self._note_unsure(i, text, pieces, runs)
                results[i] = (text, score)
            del probs, batch
            start = end
        return results
