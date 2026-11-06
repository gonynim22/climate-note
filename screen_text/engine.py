"""PP-OCR 위치 모델과 한국어 인식 모델로 글자 상자를 읽는다.

Qt를 import하지 않는다. numpy와 onnxruntime만 쓰며, MANIFEST.json의 크기와
SHA-256을 확인한 번들 모델만 불러온다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import hashlib
import json
import os
from bisect import bisect_left
from pathlib import Path

import numpy as np

from app_paths import resource_root
from screen_text.corner_brackets import restore_corner_brackets
from screen_text.layout import TextBox
from screen_text.leading_symbols import apply_leading_symbols, ink_mask, restore_inline_checkboxes
from screen_text.triangles import restore_triangles

DET_LIMIT = 960            # 위치 모델 입력의 긴 변 상한
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
SPACE_GAP_RATIO = 0.40     # 글자 높이의 이 비율 이상 빈 열이 이어지면 단어 사이 (실제 PDF·합성·글꼴 6종 시험에서 0.38~0.42가 안정)
SPACE_MIN_GAP = 3          # 아주 작은 글자에서도 이보다 좁은 틈은 단어 사이로 보지 않는다(픽셀)
SPACE_LOOSE_RATIO = 0.20   # 줄의 틈이 두 무리로 뚜렷이 갈릴 때 단어 틈의 하한(글자 높이 대비). 전문 조판의 단어 틈은 0.2~0.35배다
SPACE_GROUP_RATIO = 2.5    # 단어 틈 무리의 평균이 글자 틈 무리의 이 배수 이상이어야 갈린 것으로 본다
SPACE_MIN_PAIRS = 6        # 이보다 틈이 적은 줄은 무리를 말할 수 없다('있습니 다.', '<작성 내 용>'처럼 갈라졌다)
SPACE_WORD_SHARE = 0.5     # 단어 틈은 드물다. 글자 쌍의 이 비율을 넘으면 힌팅된 글자의 1px·3px 차이일 뿐 단어 경계가 아니다
LONG_STROKE = 2.5          # 글자 높이의 이 배수 이상 이어지는 가로 획은 밑줄·표 선이다. 빈 열을 이어 공백을 가린다
# 옆이 넓게 비어 틈이 커 보이는 글자. 둘레의 틈은 고정 기준으로만 본다('10', '1월', '·관'이 갈라지지 않게)
NARROW_GLYPHS = frozenset("1Iil|.,:;·․‧ㆍ･・'\"`()[]{}/~∼～-_!‘’“”")
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
    indices = probs.argmax(axis=1)
    confidence = probs.max(axis=1)
    pieces, scores, previous = [], [], 0
    for step, index in enumerate(indices.tolist()):
        if index != 0 and index != previous:
            pieces.append([charset[index - 1], [step]])
            scores.append(float(confidence[step]))
        elif index != 0 and pieces:
            pieces[-1][1].append(step)
        previous = index
    return [(char, sum(run) / len(run)) for char, run in pieces], (float(np.mean(scores)) if scores else 0.0)


def ctc_decode(probs, charset):
    """(timestep, class) 확률에서 반복·blank(0)를 지운 글자와 평균 확신도."""
    pieces, score = ctc_decode_detail(probs, charset)
    return "".join(char for char, _ in pieces), score


def without_long_strokes(ink, height):
    """글자 높이보다 훨씬 긴 가로 획(밑줄·표 선)을 뺀 글자 픽셀. 남겨 두면 단어 사이의 빈 열이 사라진다."""
    limit = int(LONG_STROKE * height)
    out = ink.copy()
    for row in np.flatnonzero(ink.sum(axis=1) >= limit):
        edges = np.flatnonzero(np.diff(np.r_[0, ink[row].astype(np.int8), 0]))
        for start, end in zip(edges[::2], edges[1::2]):
            if end - start >= limit:
                out[row, start:end] = False
    return out


def split_word_gap(sizes, height, pairs):
    """줄의 틈을 두 무리로 가른 단어 틈의 최소 폭, 뚜렷하지 않으면 None.

    넓은 쪽은 글자 틈과 분명히 다르고 소수여야 한다. PDF처럼 힌팅 없는 글자에서 듣고, 힌팅된 화면 글자는 글자 틈이
    1~4px로 흩어져 두 무리로 갈리지 않으므로 고정 기준으로 남는다.
    """
    values = np.sort(np.array([size for size in sizes if size > 0], dtype=np.float64))
    if values.size < SPACE_MIN_PAIRS:
        return None
    best, cut = -1.0, 0
    for i in np.flatnonzero(np.diff(values)) + 1:  # 분산을 가장 크게 가르는 자리
        low, high = values[:i], values[i:]
        score = low.size * high.size * (high.mean() - low.mean()) ** 2
        if score > best:
            best, cut = score, int(i)
    if cut == 0:
        return None
    low, high = values[:cut], values[cut:]
    if (high[0] < SPACE_LOOSE_RATIO * height or high.mean() < SPACE_GROUP_RATIO * max(low.mean(), 1.0)
            or high.size > SPACE_WORD_SHARE * pairs):
        return None
    return max(SPACE_MIN_GAP, int(high[0]))


def model_word_gap(sizes, height):
    """모델이 공백을 낸 자리의 틈(중앙값)으로 잰 이 줄의 단어 틈, 단어 틈으로 볼 만큼 넓지 않으면 None."""
    if not sizes:
        return None
    gap = float(np.median(sizes))
    return max(SPACE_MIN_GAP, int(round(gap))) if gap >= SPACE_LOOSE_RATIO * height else None


def _gap_needs(gaps, pieces, steps, width, height, fixed):
    """틈마다 필요한 폭. 글자 위치를 알면 줄의 단어 틈을 재고, 잴 수 없거나 좁은 글자 옆이면 고정 기준을 쓴다.

    모델이 공백을 낸 줄은 그 자리의 틈을 자로 쓰고(일부만 내도 나머지를 찾고 글자 틈은 가르지 않는다), 공백이 없는
    줄은 틈을 두 무리로 가른다.
    """
    read = [(char, center * width / steps) for char, center in pieces if char != " "] if width > 0 else []
    if len(read) < 2:
        return [fixed] * len(gaps)
    positions = [x for _, x in read]
    owners = [bisect_left(positions, x) - 1 for x, _ in gaps]  # 틈 왼쪽 글자
    def wide(owner):
        return 0 <= owner < len(read) - 1 and read[owner][0] not in NARROW_GLYPHS and read[owner + 1][0] not in NARROW_GLYPHS
    largest = {}
    for owner, (_, size) in zip(owners, gaps):
        if wide(owner):
            largest[owner] = max(largest.get(owner, 0), size)
    spaces = [center * width / steps for char, center in pieces if char == " "]
    if spaces:
        word_gap = model_word_gap([largest[k] for k in {bisect_left(positions, x) - 1 for x in spaces} if k in largest], height)
    else:
        word_gap = split_word_gap(largest.values(), height, sum(wide(owner) for owner in range(len(read) - 1)))
    if word_gap is None:
        return [fixed] * len(gaps)
    return [min(word_gap, fixed) if wide(owner) else fixed for owner in owners]


def ink_gap_cuts(crop, pieces=(), steps=1, width=0):
    """한 줄 크롭에서 단어 사이로 볼 빈 열의 가운데 x 목록.

    배경은 중앙값 색으로 보고, 배경과 충분히 다른 픽셀만 글자로 센다(옅은 잡음은 무시). 밑줄·표 선은 뺀다. 가장자리
    여백과 글자 사이의 좁은 틈은 세지 않는다. 글자 높이에 견준 고정 기준이 기본이고, 인식 글자의 위치(pieces)를 주면
    줄의 틈이 글자 틈과 단어 틈으로 뚜렷이 갈릴 때 좁은 단어 틈도 찾는다. 화면의 틈을 잴 뿐 글자를 추정하지 않는다.
    """
    if crop.size == 0:
        return []
    ink = ink_mask(crop)
    rows = np.flatnonzero(ink.any(axis=1))
    if rows.size:
        ink = without_long_strokes(ink, int(rows[-1] - rows[0] + 1))
    columns = np.flatnonzero(ink.any(axis=0))
    rows = np.flatnonzero(ink.any(axis=1))
    if columns.size < 2 or rows.size == 0:
        return []
    height = int(rows[-1] - rows[0] + 1)
    fixed = max(SPACE_MIN_GAP, int(round(SPACE_GAP_RATIO * height)))
    empty = np.diff(columns) - 1  # 글자가 있는 열 사이에 낀 빈 열 수
    gaps = [(int(columns[k + 1] - empty[k] // 2 - 1), int(empty[k])) for k in np.flatnonzero(empty)]
    needs = _gap_needs(gaps, pieces, steps, width, height, fixed)
    return [x for (x, size), need in zip(gaps, needs) if size >= need]


def insert_gap_spaces(pieces, cuts, steps, width):
    """빈 틈(크롭 x)을 글자 위치(CTC 단계)에 대응시켜, 틈 왼쪽 글자 뒤에 공백만 넣은 문자열.

    모델이 이미 공백을 낸 자리, 첫 글자 앞·마지막 글자 뒤의 틈, 같은 자리의 중복 틈에는 넣지 않는다.
    """
    centers = [center for _, center in pieces]
    after = [False] * len(pieces)
    for cut in cuts if width > 0 else ():
        left = bisect_left(centers, cut * steps / width) - 1  # 중심이 틈보다 왼쪽인 마지막 글자
        if 0 <= left < len(pieces) - 1 and pieces[left][0] != " " and pieces[left + 1][0] != " ":
            after[left] = True
    return "".join(char + (" " if gap else "") for (char, _), gap in zip(pieces, after))


class OcrEngine:
    """번들 모델 세션을 들고 RGB 배열의 글자 상자를 읽는다. 세션 생성은 무겁다."""

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
        """RGB 배열(H, W, 3)의 글자 상자를 원본 좌표로 돌려준다. 취소되면 RecognitionCancelled."""
        if cancelled():
            raise RecognitionCancelled
        height, width = image.shape[:2]
        scale = min(UPSCALE, MAX_SIDE / max(width, height))
        work = image
        if scale != 1.0:
            size = (max(1, round(width * scale)), max(1, round(height * scale)))
            work = np.clip(resize_bilinear(image, *size), 0, 255).astype(np.uint8)
        boxes = self._detect(work, cancelled)
        if cancelled():
            raise RecognitionCancelled
        results = apply_leading_symbols(work, boxes, self._read(work, boxes, cancelled))
        out = []
        for (x0, y0, x1, y1), (text, score, unsure_prefix) in zip(boxes, results):
            text = text.strip()
            if text:
                out.append(TextBox(round(x0 / scale), round(y0 / scale),
                                   max(1, round((x1 - x0) / scale)), max(1, round((y1 - y0) / scale)),
                                   text, score, unsure_prefix))
        return out

    def _detect(self, image, cancelled=lambda: False):
        if cancelled():
            raise RecognitionCancelled
        height, width = image.shape[:2]
        ratio = min(1.0, DET_LIMIT / max(height, width))
        new_h = max(32, int(round(height * ratio / 32)) * 32)
        new_w = max(32, int(round(width * ratio / 32)) * 32)
        tensor = resize_bilinear(image, new_w, new_h)[:, :, ::-1] / 255.0  # 모델은 BGR 순서로 학습됐다
        tensor = ((tensor - DET_MEAN) / DET_STD).transpose(2, 0, 1)[None].astype(np.float32)
        if cancelled():
            raise RecognitionCancelled
        prob = self._det.run(None, {"x": tensor})[0][0, 0]
        scale_x, scale_y = width / new_w, height / new_h
        boxes = []
        for x0, y0, x1, y1, runs in label_components(prob > DET_THRESHOLD, cancelled):
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

    def _read(self, image, boxes, cancelled):
        if cancelled():
            raise RecognitionCancelled
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
                pieces, _ = ctc_decode_detail(probs[slot, :steps], self._charset)
                if "".join(char for char, _ in pieces) == text:  # 글자와 위치가 맞을 때만 공백 위치를 쓴다
                    x0, y0, x1, y1 = boxes[i]
                    crop = image[y0:y1, x0:x1]
                    pieces = restore_corner_brackets(pieces, crop, steps, x1 - x0)
                    pieces = restore_inline_checkboxes(pieces, crop, steps, x1 - x0)
                    pieces = restore_triangles(pieces, crop, steps, x1 - x0)
                    text = insert_gap_spaces(pieces, ink_gap_cuts(crop, pieces, steps, x1 - x0), steps, x1 - x0)
                results[i] = (text, score)
            del probs, batch
            start = end
        return results
