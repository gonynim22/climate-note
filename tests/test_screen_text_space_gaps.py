"""화면 글자 따기: 이미지의 실제 빈 틈으로 공백을 복원한다.

인식 모델은 CJK 문장에서 공백을 거의 내지 않는다. 글자 사이의 빈 열이 글자 높이에 비해 충분히 넓을 때만
단어 경계로 보고, 인식된 글자의 위치에 대응시켜 공백만 넣는다. 글자는 바꾸지 않는다.
"""
import numpy as np
import pytest
from PySide6.QtGui import QColor, QFont, QImage, QPainter

import screen_text.engine as engine
from screen_text.engine import OcrEngine, rgb_from_buffer


def strip_image(blobs, height=24, width=None, background=255, ink=0, top=6, bottom=18):
    """(시작, 끝) 열 구간마다 글자 높이(top~bottom 행)의 막대를 그린 RGB 배열."""
    width = width or (max(end for _, end in blobs) + 10)
    image = np.full((height, width, 3), background, dtype=np.uint8)
    for start, end in blobs:
        image[top:bottom, start:end] = ink
    return image


# ── 빈 틈 찾기 ──
def test_gap_cuts_pick_word_gap_but_not_letter_gap():
    # 글자 높이 12 → 필요한 틈은 max(3, round(0.40 × 12)) = 5열. 2열 틈은 글자 사이, 8열 틈은 단어 사이.
    image = strip_image([(10, 20), (22, 32), (40, 50)])
    assert engine.ink_gap_cuts(image) == [35]   # 틈(32~39)의 가운데


def test_gap_threshold_scales_with_glyph_height():
    # 같은 8열 틈이라도 글자가 30행이면 필요한 틈은 12열이므로 단어 경계로 보지 않는다.
    image = strip_image([(10, 20), (22, 32), (40, 50)], height=40, top=5, bottom=35)
    assert engine.ink_gap_cuts(image) == []


def test_gap_cuts_ignore_outer_margins_and_blank_images():
    margin = strip_image([(40, 50)], width=100)
    assert engine.ink_gap_cuts(margin) == []                       # 막대 하나: 안쪽 틈이 없다
    assert engine.ink_gap_cuts(np.full((24, 80, 3), 255, dtype=np.uint8)) == []
    assert engine.ink_gap_cuts(np.zeros((0, 0, 3), dtype=np.uint8)) == []


def test_gap_cuts_work_on_dark_background():
    image = strip_image([(10, 20), (22, 32), (40, 50)], background=20, ink=235)
    assert engine.ink_gap_cuts(image) == [35]


def test_gap_cuts_ignore_faint_noise_inside_a_gap():
    image = strip_image([(10, 20), (22, 32), (40, 50)])
    image[8:16, 35] = 246                                           # 배경 255에서 9만큼 어두운 점: 글자가 아니다
    assert engine.ink_gap_cuts(image) == [35]


# ── 글자 위치(CTC)와 공백 넣기 ──
def test_ctc_decode_detail_matches_ctc_decode_and_reports_run_centers():
    charset = ["가", "나", " "]
    probs = np.zeros((6, 4), dtype=np.float32)
    for step, index in enumerate([1, 1, 0, 1, 2, 3]):
        probs[step, index] = 0.9
    pieces, score = engine.ctc_decode_detail(probs, charset)
    assert pieces == [("가", 0.5), ("가", 3.0), ("나", 4.0), (" ", 5.0)]
    assert (engine.ctc_decode(probs, charset)[0], score) == ("".join(p for p, _ in pieces), pytest.approx(0.9))


def test_insert_gap_spaces_puts_space_after_the_glyph_left_of_the_gap():
    pieces = [("가", 2.0), ("나", 6.0), ("다", 12.0)]
    # 16단계가 폭 160px에 대응: 틈 x=90 → 단계 9, 나(6)와 다(12) 사이
    assert engine.insert_gap_spaces(pieces, [90], 16, 160) == "가나 다"


def test_insert_gap_spaces_skips_edges_duplicates_and_existing_spaces():
    pieces = [("가", 2.0), ("나", 6.0), (" ", 8.0), ("다", 12.0)]
    assert engine.insert_gap_spaces(pieces, [5], 16, 160) == "가나 다"          # 앞쪽 가장자리 틈: 넣지 않는다
    assert engine.insert_gap_spaces(pieces, [150], 16, 160) == "가나 다"        # 마지막 글자 뒤: 넣지 않는다
    assert engine.insert_gap_spaces(pieces, [70, 75], 16, 160) == "가나 다"          # 모델이 이미 공백을 냈다: 겹치지 않는다
    two = [("가", 2.0), ("나", 6.0), ("다", 12.0)]
    assert engine.insert_gap_spaces(two, [90, 95], 16, 160) == "가나 다"        # 같은 자리에 틈이 둘이어도 공백은 하나
    assert engine.insert_gap_spaces(two, [], 16, 160) == "가나다"


# ── 실제 모델: 문장 ──
def render_line(text, pixel_size, width=900):
    font = QFont("Malgun Gothic")
    font.setPixelSize(pixel_size)
    image = QImage(width, pixel_size * 2 + 24, QImage.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    painter.drawText(10, 10 + pixel_size, text)
    painter.end()
    return rgb_from_buffer(image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits()))


@pytest.fixture(scope="module")
def ocr():
    return OcrEngine()


def read_line(ocr, text, pixel_size):
    boxes = sorted(ocr.recognize(render_line(text, pixel_size)), key=lambda box: box.x)
    return " ".join(box.text for box in boxes)


@pytest.mark.parametrize("pixel_size", [13, 14, 16])
def test_restores_space_after_period_between_items(qapp, ocr, pixel_size):
    found = read_line(ocr, "붙임 1. 2026년도 추진계획 1부. 끝.", pixel_size)
    assert "1. 2026년도" in found and "1부. 끝" in found, found


@pytest.mark.parametrize("pixel_size", [13, 14, 16])
def test_restores_spaces_between_numbered_items(qapp, ocr, pixel_size):
    found = read_line(ocr, "가. 목적 나. 대상 다. 기간", pixel_size)
    assert all(part in found for part in ("가. 목적", "나. 대상", "다. 기간")), found
    found = read_line(ocr, "1) 현황 2) 문제점 3) 개선방안", pixel_size)
    assert all(part in found for part in ("1) 현황", "2) 문제점", "3) 개선방안")), found


@pytest.mark.parametrize("pixel_size", [13, 14, 16])
def test_keeps_words_without_spaces_unsplit(qapp, ocr, pixel_size):
    for text in ("환경점검결과알림", "본 문서는 시험용이며 실제 업무와 관련이 없습니다."):
        assert read_line(ocr, text, pixel_size) == text
