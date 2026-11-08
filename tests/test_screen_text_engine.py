"""화면 글자 따기 인식 엔진: 번들 모델 무결성과 전후처리, 실제 모델 인식."""
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from app_paths import resource_root
from screen_text.engine import (
    ModelIntegrityError, OcrEngine, RecognitionCancelled, ctc_decode, expand_box,
    label_components, load_charset, model_dir, resize_bilinear, rgb_from_buffer, verify_models,
)

MODEL_DIR = resource_root() / "screen_text" / "models"


def test_manifest_matches_bundled_files():
    with open(MODEL_DIR / "MANIFEST.json", encoding="utf-8") as stream:
        manifest = json.load(stream)
    assert manifest["license"] == "Apache-2.0"
    assert {entry["role"] for entry in manifest["files"]} == {"det", "rec", "dict"}
    for entry in manifest["files"]:
        path = MODEL_DIR / entry["name"]
        with open(path, "rb") as stream:
            data = stream.read()
        assert len(data) == entry["size"], entry["name"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["name"]
    with open(MODEL_DIR / "LICENSE", encoding="utf-8") as stream:
        assert "Apache License" in stream.read()


def test_verify_models_returns_roles_and_rejects_changed_file(tmp_path):
    assert set(verify_models()) == {"det", "rec", "dict"}
    assert model_dir() == MODEL_DIR
    copy = tmp_path / "models"
    shutil.copytree(MODEL_DIR, copy)
    with open(copy / "dict.txt", "ab") as stream:
        stream.write(b"x")
    with pytest.raises(ModelIntegrityError):
        verify_models(copy)


def test_verify_models_rejects_missing_manifest(tmp_path):
    with pytest.raises(ModelIntegrityError):
        verify_models(tmp_path)


def test_load_charset_appends_space_as_last_class():
    chars = load_charset(MODEL_DIR / "dict.txt")
    assert len(chars) == 11946
    assert chars[0] == "\u1100" and chars[-1] == " "


def test_rgb_from_buffer_drops_row_padding():
    data = bytes([1, 2, 3, 4, 5, 6, 0, 0, 7, 8, 9, 10, 11, 12, 0, 0])  # 2×2, 줄당 8바이트
    image = rgb_from_buffer(2, 2, 8, data)
    assert image.shape == (2, 2, 3)
    assert image[1, 1].tolist() == [10, 11, 12]


def test_resize_bilinear_keeps_constant_color_up_and_down():
    image = np.full((7, 10, 3), 200, dtype=np.uint8)
    assert np.allclose(resize_bilinear(image, 25, 13), 200)
    big = np.full((400, 400, 3), 50, dtype=np.uint8)
    small = resize_bilinear(big, 100, 90)
    assert small.shape == (90, 100, 3) and np.allclose(small, 50)


def test_label_components_joins_diagonal_pixels_and_separates_blobs():
    mask = np.zeros((6, 8), dtype=bool)
    mask[0, 0] = mask[1, 1] = True          # 대각선은 같은 요소 (8연결)
    mask[3:5, 4:7] = True                   # 떨어진 사각형
    components = sorted((x0, y0, x1, y1) for x0, y0, x1, y1, _ in label_components(mask))
    assert components == [(0, 0, 1, 1), (4, 3, 6, 4)]


def test_expand_box_matches_db_distance():
    # 10×2 상자: 넓이 20, 둘레 24 → 20 × 1.5 / 24 = 1.25
    assert expand_box(0, 0, 9, 1) == pytest.approx((-1.25, -1.25, 11.25, 3.25))


def test_ctc_decode_collapses_repeats_and_blanks():
    charset = ["가", "나", " "]
    probs = np.zeros((6, 4), dtype=np.float32)
    for step, index in enumerate([1, 1, 0, 1, 2, 3]):
        probs[step, index] = 0.9
    text, score = ctc_decode(probs, charset)
    assert text == "가가나 "
    assert score == pytest.approx(0.9)


def render(lines, pixel_size, width=900):
    """Qt로 그린 합성 문서. '|'로 나눈 칸은 170px 간격의 열이 된다."""
    font = QFont("Malgun Gothic")
    font.setPixelSize(pixel_size)
    image = QImage(width, (pixel_size + 12) * len(lines) + 20, QImage.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    y = 10 + pixel_size
    for line in lines:
        for column, cell in enumerate(line.split("|")):
            painter.drawText(10 + column * 170, y, cell)
        y += pixel_size + 12
    painter.end()
    return rgb_from_buffer(image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits()))


@pytest.fixture(scope="module")
def ocr():
    return OcrEngine()


@pytest.mark.parametrize("pixel_size", [13, 16])
def test_reads_korean_sentence_and_table_cells(qapp, ocr, pixel_size):
    image = render(["환경 점검 결과 알림", "구분|점검 사업장|위반", "대전|42|3"], pixel_size)
    found = [item.text for item in ocr.recognize(image)]
    for expected in ("환경 점검 결과 알림", "구분", "점검 사업장", "위반", "대전", "42", "3"):
        assert expected in found, (expected, found)


def test_boxes_are_in_original_image_coordinates(qapp, ocr):
    image = render(["구분|점검 사업장|위반", "대전|42|3"], 16)
    height, width = image.shape[:2]
    boxes = ocr.recognize(image)
    assert boxes
    for item in boxes:
        assert 0 <= item.x and item.x + item.w <= width and 0 <= item.y and item.y + item.h <= height
    assert next(b for b in boxes if b.text == "대전").x < 170


def test_long_line_remains_readable_with_bounded_batches(qapp, ocr):
    sentence = "환경 점검 결과 알림 " * 4
    found = ocr.recognize(render([sentence], 16, width=1000))
    assert "".join(item.text.replace(" ", "") for item in found) == sentence.replace(" ", "")


def test_large_image_is_downscaled_and_mapped_back(qapp, ocr):
    font = QFont("Malgun Gothic")
    font.setPixelSize(80)
    image = QImage(5200, 400, QImage.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    painter.drawText(4000, 200, "환경 점검")
    painter.end()
    boxes = ocr.recognize(rgb_from_buffer(5200, 400, image.bytesPerLine(), bytes(image.constBits())))
    target = next(b for b in boxes if "환경" in b.text)
    assert 3900 < target.x < 4100


def test_blank_image_returns_no_boxes(ocr):
    assert ocr.recognize(np.full((100, 300, 3), 255, dtype=np.uint8)) == []


def test_cancel_raises_before_reading(qapp, ocr):
    image = render(["환경 점검 결과 알림"], 16)
    with pytest.raises(RecognitionCancelled):
        ocr.recognize(image, cancelled=lambda: True)


def _arena_shrinkage(run_options):
    """모델 실행 옵션에 담긴 '실행이 끝나면 계산 메모리를 돌려준다' 설정. 없으면 None."""
    if run_options is None:
        return None
    try:
        return run_options.get_run_config_entry("memory.enable_memory_arena_shrinkage")
    except RuntimeError:   # onnxruntime은 없는 설정을 예외로 알린다
        return None


def test_every_model_run_gives_back_its_working_memory(qapp, monkeypatch):
    """onnxruntime은 한 번 쓴 계산 메모리를 다음 실행을 위해 붙잡아 둔다. A4 한 쪽이면 인식이 끝난 뒤에도
    약 700MB가 남았다(2026-11-08). 아레나를 둔 세션은 실행이 끝날 때마다 CPU 메모리를 돌려 달라고 해야 한다."""
    import onnxruntime as ort

    runs = []

    class RecordingSession(ort.InferenceSession):
        def __init__(self, path, options, **kwargs):
            self.model, self.arena = Path(path).stem, options.enable_cpu_mem_arena
            super().__init__(path, options, **kwargs)

        def run(self, output_names, input_feed, run_options=None):
            runs.append((self.model, self.arena, _arena_shrinkage(run_options)))
            return super().run(output_names, input_feed, run_options)

    monkeypatch.setattr(ort, "InferenceSession", RecordingSession)
    found = [item.text for item in OcrEngine().recognize(render(["환경 점검 결과 알림"], 16))]
    assert "환경 점검 결과 알림" in found
    assert {model for model, _, _ in runs} == {"det", "rec"}
    assert all(shrink == "cpu:0" for _, arena, shrink in runs if arena)
    assert any(arena for _, arena, _ in runs)


def test_text_finder_takes_memory_straight_from_the_system(qapp, monkeypatch):
    """위치 찾기는 한 번에 몇 번만 크게 돌아(2배 A4 약 420MB) 아레나에 붙잡아 둘 까닭이 없다. 아레나를 끄면 최대 커밋이
    약 160MB 줄고 시간은 같았다(2026-11-08). 인식 모델은 작은 실행이 많아 아레나가 있어야 빠르다(모두 끄면 1.7배 느렸다)."""
    import onnxruntime as ort

    arenas = {}

    class RecordingSession(ort.InferenceSession):
        def __init__(self, path, options, **kwargs):
            arenas[Path(path).stem] = options.enable_cpu_mem_arena
            super().__init__(path, options, **kwargs)

    monkeypatch.setattr(ort, "InferenceSession", RecordingSession)
    found = [item.text for item in OcrEngine().recognize(render(["환경 점검 결과 알림"], 16))]
    assert "환경 점검 결과 알림" in found
    assert arenas == {"det": False, "rec": True}


def test_engine_reads_when_sessions_have_no_memory_arena(qapp, monkeypatch):
    """아레나를 끈 세션에 '실행이 끝나면 돌려 달라'는 옵션을 주면 onnxruntime이 실행을 거부한다(InvalidArgument).
    메모리를 아끼려고 아레나를 꺼도(RapidOCR의 기본값) 글자 따기가 멈추면 안 된다."""
    import onnxruntime as ort

    original = ort.SessionOptions

    def without_arena():
        options = original()
        options.enable_cpu_mem_arena = False
        return options

    monkeypatch.setattr(ort, "SessionOptions", without_arena)
    found = [item.text for item in OcrEngine().recognize(render(["환경 점검 결과 알림"], 16))]
    assert "환경 점검 결과 알림" in found


def _resize_as_before(image, width, height):
    """2026-11-08 이전의 resize_bilinear(한 번에 통째로 계산). 메모리를 줄여도 값은 비트 단위로 같아야 한다."""
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


@pytest.mark.parametrize("shape, size", [
    ((50, 70, 3), (35, 25)),       # 1배와 2배 사이로 줄이기
    ((50, 70, 3), (140, 100)),     # 키우기
    ((300, 500, 3), (130, 70)),    # 정수 배 평균으로 먼저 줄이는 경로
    ((257, 333, 3), (300, 290)),   # 여러 줄 묶음에 걸치는 키우기
    ((40, 60, 3), (60, 40)),       # 크기가 같으면 그대로
])
def test_resize_bilinear_values_do_not_change(shape, size):
    image = np.random.default_rng(7).integers(0, 256, shape, dtype=np.uint8)
    got, want = resize_bilinear(image, *size), _resize_as_before(image, *size)
    assert got.dtype == want.dtype
    assert np.array_equal(got, want)


def test_resize_bilinear_does_not_build_full_size_temporaries():
    """2배로 키운 A4 한 쪽(약 1700×2400)을 위치 찾기 크기로 줄일 때 numpy 임시 배열이 366MB까지 갔다(2026-11-08)."""
    import tracemalloc

    image = np.zeros((2400, 1700, 3), dtype=np.uint8)
    tracemalloc.start()
    try:
        out = resize_bilinear(image, 1360, 1920)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1.25 * out.nbytes


def test_detect_holds_only_the_model_input_while_the_model_runs():
    """위치 찾기 모델이 도는 구간이 인식의 최대 메모리다. 그동안 줄인 이미지와 캔버스를 쥐고 있었다(2배 A4에서 123MB)."""
    import tracemalloc

    engine = OcrEngine()
    seen = {}

    class ZeroDetector:
        def run(self, _, feed):
            seen["held"], seen["input"] = tracemalloc.get_traced_memory()[0], feed["x"].nbytes
            batch, _, height, width = feed["x"].shape
            return [np.zeros((batch, 1, height, width), dtype=np.float32)]

    engine._det = ZeroDetector()
    image = np.full((1700, 1240, 3), 255, dtype=np.uint8)
    tracemalloc.start()
    try:
        assert engine._detect(image, limit=1920) == []
    finally:
        tracemalloc.stop()
    assert seen["held"] < 1.1 * seen["input"]


def test_engine_refuses_tampered_models(tmp_path):
    copy = tmp_path / "models"
    shutil.copytree(MODEL_DIR, copy)
    with open(copy / "rec.onnx", "r+b") as stream:
        stream.seek(-1, 2)
        last = stream.read(1)
        stream.seek(-1, 2)
        stream.write(bytes([last[0] ^ 0xFF]))
    with pytest.raises(ModelIntegrityError):
        OcrEngine(copy)
