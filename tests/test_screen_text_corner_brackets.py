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


def test_full_height_corner_without_the_other_arm_becomes_nakpyo():
    # 맑은 고딕의 작은 낫표는 줄 높이만큼 길다(엣지 화면 「나주시 … 용역」, 2026-11-08). 반대쪽 가로획이 전혀 없으면 낫표다
    image = line(lambda im, x: draw_open(im, x, TOP, 20), lambda im, x: draw_close(im, x, BOTTOM, 20))
    assert "".join(c for c, _ in restore(image, *PIECES)) == "「가나다」라"


def test_full_height_square_bracket_with_short_arms_stays():
    # 큰 제목 글꼴의 [ ]는 가로획이 짧아도 위아래에 다 있다(11-06에 줄 높이 상한으로 막았던 6개)
    def square(image, x, side):
        stem = slice(x, x + 2) if side == "[" else slice(x + 3, x + 5)
        image[TOP:BOTTOM, stem] = 0
        image[TOP:TOP + 2, x:x + 5] = 0
        image[BOTTOM - 2:BOTTOM, x:x + 5] = 0

    image = line(lambda im, x: square(im, x, "["), lambda im, x: square(im, x, "]"))
    assert restore(image, *PIECES) == list(PIECES)


def test_corner_touching_the_previous_syllable_becomes_nakpyo():
    # 「조」에서는」의 」가 '조'의 아래 획에 붙어 한 덩어리가 되면 덩어리 판정이 놓쳤다(2026-11-08, 놓친 낫표 147자리의 큰 몫)
    image = canvas()
    draw_open(image, 10)
    for x in (22, 36):
        draw_syllable(image, x)
    draw_syllable(image, 50)
    image[BOTTOM - 2:BOTTOM, 50:66] = 0       # 음절 아래 획이 」의 가로획으로 이어진다
    image[BOTTOM - 10:BOTTOM, 64:66] = 0      # 」의 세로획
    draw_syllable(image, 76)
    out = restore(image, ("[", 13.0), ("가", 27.0), ("나", 41.0), ("다", 55.0), ("]", 65.0), ("라", 81.0))
    assert "".join(c for c, _ in out) == "「가나다」라"


def test_square_bracket_touching_a_capital_with_serifs_stays():
    # [Ⅵ-4-1]에서 로마 숫자의 윗부리가 [ 의 위 가로획에 붙어 가로획이 길게 보였다(아래 가로획은 짧아도 있다)
    image = canvas()
    image[TOP:BOTTOM, 10:12] = 0
    image[TOP:TOP + 2, 10:19] = 0            # 위 가로획이 I의 윗부리로 이어진다
    image[BOTTOM - 2:BOTTOM, 10:14] = 0      # 짧은 아래 가로획
    image[TOP:BOTTOM, 17:19] = 0             # I의 세로획
    image[BOTTOM - 2:BOTTOM, 15:21] = 0      # I의 아랫부리
    for x in (24, 38):
        draw_syllable(image, x)
    pieces = [("[", 11.0), ("I", 18.0), ("가", 29.0), ("나", 43.0)]
    assert restore(image, *pieces) == pieces


def draw_lens(image, x, side, top=TOP, height=20, wide=6, thin=3):
    """【 】: 바깥 세로변이 곧고, 가로획에서 세로획까지 굵기가 여러 줄에 걸쳐 줄어드는 쐐기."""
    for row in range(height):
        edge = min(row, height - 1 - row)
        run = max(thin, wide - edge // 2)
        if side == "[":
            image[top + row, x:x + run] = 0
        else:
            image[top + row, x + wide - run:x + wide] = 0


def test_black_lens_brackets_read_as_square_brackets_become_lens_brackets():
    # 【 】는 사전에 없어 [ ]로 읽혔다. 정답 481개(평가 자료) 중 맞은 것이 없었다
    image = line(lambda im, x: draw_lens(im, x, "["), lambda im, x: draw_lens(im, x, "]"))
    assert "".join(c for c, _ in restore(image, *PIECES)) == "【가나다】라"


def test_bold_square_bracket_drops_straight_to_its_stem_and_stays():
    # 굵은 [ 도 가로획 줄 바로 다음에 세로획 굵기로 떨어진다(쐐기가 아니다)
    def bold(image, x, side):
        stem = slice(x, x + 3) if side == "[" else slice(x + 3, x + 6)
        image[TOP:BOTTOM, stem] = 0
        image[TOP:TOP + 3, x:x + 6] = 0
        image[BOTTOM - 3:BOTTOM, x:x + 6] = 0

    image = line(lambda im, x: bold(im, x, "["), lambda im, x: bold(im, x, "]"))
    assert restore(image, *PIECES) == list(PIECES)


def test_square_bracket_with_a_soft_corner_at_one_end_stays():
    # 스캔으로 흐려진 [ 는 가로획 모서리가 둥글어 한쪽 끝에 짧은 쐐기가 생겼다([공통홍보]가 【로 바뀜, 2026-11-08).
    # 【 】는 양끝 모두 쐐기가 두 줄 이상 이어진다
    def soft(image, x, side):
        runs = [6, 4] + [3] * 14 + [4, 4, 5, 6]
        for row, run in enumerate(runs):
            if side == "[":
                image[TOP + row, x:x + run] = 0
            else:
                image[TOP + row, x + 6 - run:x + 6] = 0

    image = line(lambda im, x: soft(im, x, "["), lambda im, x: soft(im, x, "]"))
    assert restore(image, *PIECES) == list(PIECES)


def test_lens_shape_inside_latin_text_stays():
    # 【 】는 한국어 문서의 표기다. 영문 참고문헌의 ]를 바꾸지 않는다(정답 【 】 481개의 안쪽 이웃에 영문자는 없었다)
    image = line(lambda im, x: draw_lens(im, x, "["), lambda im, x: draw_lens(im, x, "]"))
    pieces = [("[", 13.0), ("A", 27.0), ("b", 41.0), ("c", 55.0), ("]", 67.0), ("라", 81.0)]
    assert restore(image, *pieces) == pieces


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
def test_real_model_reads_black_lens_brackets(qapp, ocr, pixel_size):
    found = read(ocr, "추진 계획 【일반회계】 예산 편성", pixel_size)
    assert "【일반회계】" in found, found


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
