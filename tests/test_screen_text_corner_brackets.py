"""화면 글자 따기: '[' ']'로 읽힌 조각의 화면 모양이 낫표면 「 」로 바꾼다.

모델 사전에 낫표가 없어 공문서의 법령명 표기가 [ ]로 읽힌다. 낫표는 줄 글자 높이의 절반쯤이고 위(「)나 아래(」)에
붙어 있으며 ┌ ┘ 꺾임 한 번뿐이라 위아래 획이 모두 있는 [ ]와 모양으로 갈린다. 애매하면 바꾸지 않는다.
"""
import numpy as np
import pytest
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from screen_text import engine
from screen_text.corner_brackets import restore_corner_brackets
from screen_text.engine import OcrEngine, rgb_from_buffer

HEIGHT, TOP, BOTTOM = 24, 2, 22   # 글자 높이 20


def canvas(width=160):
    return np.full((HEIGHT, width, 3), 255, np.uint8)


def draw_syllable(image, x):
    """한글 음절처럼 획이 있는 11×20 블록."""
    image[TOP:BOTTOM, x:x + 2] = 0
    image[TOP:BOTTOM, x + 9:x + 11] = 0
    image[11:13, x:x + 11] = 0


def draw_open(image, x, top=TOP, size=10):
    """┌ 모양: 왼쪽 세로획과 위쪽 가로획뿐."""
    image[top:top + size, x:x + 2] = 0
    image[top:top + 2, x:x + 7] = 0


def draw_close(image, x, bottom=BOTTOM, size=10):
    """┘ 모양: 오른쪽 세로획과 아래쪽 가로획뿐."""
    image[bottom - size:bottom, x + 5:x + 7] = 0
    image[bottom - 2:bottom, x:x + 7] = 0


def draw_square(image, x, side, top=TOP, size=20):
    """[ 또는 ]: 세로획과 위아래 가로획."""
    image[top:top + size, (x if side == "[" else x + 5):(x + 2 if side == "[" else x + 7)] = 0
    image[top:top + 2, x:x + 7] = 0
    image[top + size - 2:top + size, x:x + 7] = 0


def restore(image, *pieces):
    """조각 위치를 픽셀 좌표로 넘긴다(steps == width)."""
    width = image.shape[1]
    return restore_corner_brackets(list(pieces), image, width, width)


def line(draw_left, draw_right):
    image = canvas()
    draw_left(image, 10)
    for x in (22, 36, 50):
        draw_syllable(image, x)
    draw_right(image, 64)
    draw_syllable(image, 76)
    return image


PIECES = (("[", 13.0), ("가", 27.0), ("나", 41.0), ("다", 55.0), ("]", 67.0), ("라", 81.0))


def test_corner_shapes_read_as_square_brackets_become_nakpyo():
    out = restore(line(draw_open, draw_close), *PIECES)
    assert "".join(c for c, _ in out) == "「가나다」라"
    assert [p for _, p in out] == [p for _, p in PIECES]   # 위치는 공백 복원이 그대로 쓴다


def test_real_square_brackets_stay():
    image = line(lambda im, x: draw_square(im, x, "["), lambda im, x: draw_square(im, x, "]"))
    assert restore(image, *PIECES) == list(PIECES)


def test_short_square_brackets_with_both_arms_stay():
    image = line(lambda im, x: draw_square(im, x, "[", TOP, 10), lambda im, x: draw_square(im, x, "]", BOTTOM - 10, 10))
    assert restore(image, *PIECES) == list(PIECES)


def test_mirrored_corner_does_not_change_the_direction_the_model_read():
    image = line(draw_close, draw_open)
    assert restore(image, *PIECES) == list(PIECES)


def test_half_height_corner_in_the_middle_of_the_line_stays():
    image = line(lambda im, x: draw_open(im, x, TOP + 5), lambda im, x: draw_close(im, x, BOTTOM - 5))
    assert restore(image, *PIECES) == list(PIECES)


def test_full_height_corner_stays_because_it_is_too_ambiguous():
    # 실제 문서의 큰 제목 글꼴에서 [ ] 6개가 이 규칙이 없으면 낫표로 바뀌었다
    image = line(lambda im, x: draw_open(im, x, TOP, 20), lambda im, x: draw_close(im, x, BOTTOM, 20))
    assert restore(image, *PIECES) == list(PIECES)


def test_center_a_few_pixels_off_still_finds_the_glyph():
    out = restore(line(draw_open, draw_close), ("[", 19.0), ("가", 27.0), ("]", 61.0))
    assert "".join(c for c, _ in out) == "「가」"


def test_syllable_next_to_a_bracket_piece_is_not_taken_for_a_corner():
    image = canvas()
    for x in (10, 24, 38):
        draw_syllable(image, x)
    assert restore(image, ("[", 15.0), ("가", 29.0), ("]", 43.0)) == [("[", 15.0), ("가", 29.0), ("]", 43.0)]


def test_steps_are_mapped_to_pixels():
    image = line(draw_open, draw_close)
    width = image.shape[1]
    out = restore_corner_brackets([("[", 13.0 / 8), ("]", 67.0 / 8)], image, width // 8, width)
    assert [c for c, _ in out] == ["「", "」"]


def test_pieces_without_brackets_are_returned_untouched_without_looking_at_the_image():
    pieces = [("가", 3.0), ("나", 7.0)]
    assert restore_corner_brackets(pieces, None, 10, 100) is pieces


@pytest.mark.parametrize("image, width", [(canvas(), 160), (np.zeros((0, 0, 3), np.uint8), 0)])
def test_blank_or_empty_crop_is_safe(image, width):
    assert restore_corner_brackets([("[", 3.0)], image, 40, width) == [("[", 3.0)]


# ── 실제 모델: Qt로 그린 줄 ──
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


def read(ocr, text, pixel_size):
    return " ".join(b.text for b in sorted(ocr.recognize(render_line(text, pixel_size)), key=lambda b: b.x))


@pytest.mark.parametrize("pixel_size", [16, 20, 24])
def test_real_model_restores_nakpyo_in_a_law_name(qapp, ocr, pixel_size):
    found = read(ocr, "관계부처 합동 「국가 기술사업화 전략」 수립", pixel_size)
    assert "「국가" in found and "전략」" in found, found
    assert "[" not in found and "]" not in found, found


@pytest.mark.parametrize("pixel_size", [16, 20, 24])
def test_real_model_keeps_square_brackets(qapp, ocr, pixel_size):
    found = read(ocr, "관계부처 합동 [국가 기술사업화 전략] 수립", pixel_size)
    assert "「" not in found and "」" not in found, found


@pytest.mark.parametrize("pixel_size", [16, 20, 24])
def test_line_starting_with_nakpyo_gets_no_bullet(qapp, ocr, pixel_size):
    found = read(ocr, "「대기환경보전법」 제1조에 따른 조치", pixel_size)
    assert found.startswith("「대기"), found


def test_engine_calls_ctc_decode_once_per_box_with_brackets(qapp, ocr, monkeypatch):
    calls = []
    real = engine.ctc_decode
    monkeypatch.setattr(engine, "ctc_decode", lambda probs, charset: calls.append(1) or real(probs, charset))
    boxes = ocr.recognize(render_line("관계부처 합동 [국가 기술사업화 전략] 수립", 20))
    assert boxes and len(calls) == len(boxes)
