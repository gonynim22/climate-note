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
