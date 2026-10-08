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
from screen_text.layout import TextBox

DET_LIMIT = 960            # 위치 모델 입력의 긴 변 상한
DET_THRESHOLD = 0.3        # 글자 확률 이진화 기준
BOX_THRESHOLD = 0.6        # 상자 평균 확률 하한
UNCLIP_RATIO = 1.5         # DB 방식 상자 확장 비율
MIN_BOX_AREA = 6           # 확률 맵에서 이보다 작은 요소는 잡음
REC_HEIGHT = 48            # 한국어 인식 모델 입력 높이 (모델 입력 [N, 3, 48, W])
REC_BATCH = 6              # 폭이 비슷한 상자끼리 묶는 개수
MAX_SIDE = 4000            # 입력 이미지 긴 변 상한 (넘으면 줄인다)
UPSCALE = 1.0              # 작은 글씨 확대 배율 (Task 4 측정으로 확정)
CHARSET_SIZE = 11945
DET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
DET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class ModelIntegrityError(RuntimeError):
    """번들 모델이 없거나 MANIFEST와 다르다. 이 상태에서는 인식을 시작하지 않는다."""


class RecognitionCancelled(Exception):
    """사용자 동작이나 수명 처리로 인식이 취소됐다."""


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


def label_components(mask):
    """행 단위 run을 8연결로 묶는다. 반환: [(x0, y0, x1, y1, [(y, xs, xe), ...])] (포함 좌표)."""
    parent, runs, previous = [], [], []

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for y in range(mask.shape[0]):
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


def ctc_decode(probs, charset):
    """(timestep, class) 확률에서 반복·blank(0)를 지운 글자와 평균 확신도."""
    indices = probs.argmax(axis=1)
    confidence = probs.max(axis=1)
    text, scores, previous = [], [], 0
    for step, index in enumerate(indices.tolist()):
        if index != 0 and index != previous:
            text.append(charset[index - 1])
            scores.append(float(confidence[step]))
        previous = index
    return "".join(text), (float(np.mean(scores)) if scores else 0.0)


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
        height, width = image.shape[:2]
        scale = min(UPSCALE, MAX_SIDE / max(width, height))
        work = image
        if scale != 1.0:
            size = (max(1, round(width * scale)), max(1, round(height * scale)))
            work = np.clip(resize_bilinear(image, *size), 0, 255).astype(np.uint8)
        boxes = self._detect(work)
        if cancelled():
            raise RecognitionCancelled
        results = self._read(work, boxes, cancelled)
        out = []
        for (x0, y0, x1, y1), (text, score) in zip(boxes, results):
            text = text.strip()
            if text:
                out.append(TextBox(round(x0 / scale), round(y0 / scale),
                                   max(1, round((x1 - x0) / scale)), max(1, round((y1 - y0) / scale)),
                                   text, score))
        return out

    def _detect(self, image):
        height, width = image.shape[:2]
        ratio = min(1.0, DET_LIMIT / max(height, width))
        new_h = max(32, int(round(height * ratio / 32)) * 32)
        new_w = max(32, int(round(width * ratio / 32)) * 32)
        tensor = resize_bilinear(image, new_w, new_h)[:, :, ::-1] / 255.0  # 모델은 BGR 순서로 학습됐다
        tensor = ((tensor - DET_MEAN) / DET_STD).transpose(2, 0, 1)[None].astype(np.float32)
        prob = self._det.run(None, {"x": tensor})[0][0, 0]
        scale_x, scale_y = width / new_w, height / new_h
        boxes = []
        for x0, y0, x1, y1, runs in label_components(prob > DET_THRESHOLD):
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
        crops = []
        for x0, y0, x1, y1 in boxes:
            crop = image[y0:y1, x0:x1]
            crop_width = max(8, int(np.ceil(REC_HEIGHT * crop.shape[1] / max(1, crop.shape[0]))))
            crops.append(resize_bilinear(crop, crop_width, REC_HEIGHT)[:, :, ::-1])
        results = [("", 0.0)] * len(crops)
        order = sorted(range(len(crops)), key=lambda i: crops[i].shape[1])
        for start in range(0, len(order), REC_BATCH):
            if cancelled():
                raise RecognitionCancelled
            ids = order[start:start + REC_BATCH]
            widest = max(crops[i].shape[1] for i in ids)
            batch = np.zeros((len(ids), 3, REC_HEIGHT, widest), dtype=np.float32)
            for slot, i in enumerate(ids):
                batch[slot, :, :, : crops[i].shape[1]] = ((crops[i] / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)
            probs = self._rec.run(None, {"x": batch})[0]
            for slot, i in enumerate(ids):
                steps = max(1, int(np.ceil(probs.shape[1] * crops[i].shape[1] / widest)))
                results[i] = ctc_decode(probs[slot, :steps], self._charset)
        return results
