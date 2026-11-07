"""화면 글자 따기: 모델의 공백 확률과 화면의 틈을 더해 단어 사이를 정한다.

모델은 한글 사이의 공백을 거의 그대로 알지만 좁게 조판한 문서에서는 확률이 낮고, 화면의 틈은 자간이 넓은 글꼴(돋움·굴림)에서
음절 사이에도 벌어진다. 글자는 바꾸지 않고 공백만 넣는다.
"""
import numpy as np
import pytest
from PySide6.QtGui import QColor, QFont, QImage, QPainter

import screen_text.engine as engine
from screen_text.engine import OcrEngine, rgb_from_buffer
from screen_text.word_spaces import glyph_kind, join_words, without_long_strokes

HEIGHT = 20


def line(chars, gaps, width=None, glyph=12):
    """글자 폭 12의 막대 글자를 gaps 틈으로 놓는다. (크롭, [(글자, 중심 단계)], 단계, 폭, 단계별 공백 확률). 1px = 1단계."""
    xs, x = [], 4
    for k, char in enumerate(chars):
        xs.append(x)
        x += glyph + (gaps[k] if k < len(gaps) else 0)
    crop_width = width or x + 4
    crop = np.full((HEIGHT + 4, crop_width, 3), 255, np.uint8)
    for start in xs:
        crop[2:HEIGHT + 2, start:start + 2] = 0
        crop[2:HEIGHT + 2, start + glyph - 2:start + glyph] = 0
        crop[11:13, start:start + glyph] = 0
    pieces = [(char, start + glyph / 2) for char, start in zip(chars, xs)]
    return crop, pieces, crop_width, crop_width, np.full(crop_width, 1e-6, np.float32)


def with_space(pieces, probabilities, index, probability=.98):
    """index번 글자 뒤에 모델이 공백을 낸 것으로 만든다."""
    middle = (pieces[index][1] + pieces[index + 1][1]) / 2
    probabilities[int(middle)] = probability
    return sorted(pieces + [(" ", middle)], key=lambda piece: piece[1])


def test_model_space_is_kept():
    crop, pieces, steps, width, spaces = line("가나다라", [2, 9, 2])
    assert join_words(with_space(pieces, spaces, 1), spaces, crop, steps, width) == "가나 다라"


def test_wide_letter_gap_with_no_probability_is_not_a_word_gap():
    """돋움 12px: 음절 사이 틈 4px(글자 높이의 0.2배 이상)인데 모델의 공백 확률은 0.002다."""
    crop, pieces, steps, width, spaces = line("개발착수를통해", [4, 8, 3, 3, 8, 3])
    spaces[:] = 2e-3
    spaced = with_space(with_space(pieces, spaces, 1), spaces, 4)
    assert join_words(spaced, spaces, crop, steps, width) == "개발 착수를 통해"


def test_narrow_typesetting_uses_probability_with_small_gap():
    """좁은 조판: 모델이 공백을 내지 않아도(확률 0.2) 글자 높이의 0.25배 틈이면 단어 사이다."""
    crop, pieces, steps, width, spaces = line("가나다라마", [1, 5, 1, 1])
    spaces[int((pieces[1][1] + pieces[2][1]) / 2)] = .2
    assert join_words(pieces, spaces, crop, steps, width) == "가나 다라마"


def test_letter_spaced_heading_with_no_model_space_is_split():
    """'발  급  기  관'처럼 글자 높이만큼 벌린 머리글은 틈이 말해 준다."""
    crop, pieces, steps, width, spaces = line("발급기관", [26, 26, 26])
    assert join_words(pieces, spaces, crop, steps, width) == "발 급 기 관"


def test_number_is_not_split_around_comma_and_point():
    crop, pieces, steps, width, spaces = line("1,234.5", [5, 5, 3, 3, 5, 5], glyph=8)
    spaces[:] = 1e-3
    assert " " not in join_words(pieces, spaces, crop, steps, width)


def test_thousands_comma_with_wide_gap_stays_in_the_number():
    """굴림·돋움의 쉼표는 칸 가운데라 틈이 넓어 엑셀 표에서 '1, 639'로 나왔다."""
    crop, pieces, steps, width, spaces = digits("1,639")
    assert join_words(pieces, spaces, crop, steps, width) == "1,639"


def test_list_of_short_numbers_keeps_its_spaces():
    crop, pieces, steps, width, spaces = line("2,4,5", [3, 12, 3, 12], glyph=8)
    assert join_words(pieces, spaces, crop, steps, width) == "2, 4, 5"


def test_web_address_is_not_split_at_its_dots():
    """낱말 뒤 마침표는 띄우는 규칙이 'www. me. go. kr'을 만들었다."""
    crop, pieces, steps, width, spaces = line("me.go.kr", [1, 6, 6, 1, 6, 6, 1], glyph=8)
    spaces[:] = 1e-2
    assert join_words(pieces, spaces, crop, steps, width) == "me.go.kr"


def test_no_space_before_closing_mark_or_after_opening_mark():
    crop, pieces, steps, width, spaces = line("가(나),다", [2, 4, 4, 2, 2], glyph=10)
    spaces[:] = 1e-3
    assert join_words(pieces, spaces, crop, steps, width) == "가(나),다"


def test_middle_dot_with_wide_side_bearings_stays_attached():
    """글자 폭을 다 쓰는 글꼴의 가운뎃점은 양옆이 넓어 보여도 '제·개정'이다."""
    crop, pieces, steps, width, spaces = line("제·개정", [6, 6, 2], glyph=12)
    spaces[:] = 1e-4
    assert join_words(pieces, spaces, crop, steps, width) == "제·개정"


def test_year_apostrophe_stays_on_its_digits():
    crop, pieces, steps, width, spaces = line("'25년", [9, 2, 2], glyph=10)
    spaces[int((pieces[0][1] + pieces[1][1]) / 2)] = .9
    assert join_words(pieces, spaces, crop, steps, width) == "'25년"


def test_underline_does_not_hide_the_gap():
    crop, pieces, steps, width, spaces = line("가나다라", [2, 26, 2])
    crop[HEIGHT + 1:HEIGHT + 3, :] = 0                          # 글자 아래 밑줄이 모든 열을 잇는다
    assert join_words(pieces, spaces, crop, steps, width) == "가나 다라"


def test_short_or_blank_lines_are_returned_as_read():
    crop, pieces, steps, width, spaces = line("가", [])
    assert join_words(pieces, spaces, crop, steps, width) == "가"
    blank = np.full((24, 60, 3), 255, np.uint8)
    assert join_words([("가", 10.), ("나", 30.)], np.zeros(60), blank, 60, 60) == "가나"


def test_without_long_strokes_keeps_letter_strokes():
    ink = np.zeros((20, 200), bool)
    ink[5, 10:40] = True          # 글자 획: 글자 높이의 1.5배
    ink[18, 10:190] = True        # 밑줄
    out = without_long_strokes(ink, 20)
    assert out[5, 20] and not out[18, 20]


@pytest.mark.parametrize("char, kind", [("가", "h"), ("1", "n"), ("7", "d"), ("A", "a"), (",", "c"), ("(", "o"), ("·", "p"), ("-", "m"), ("'", "q"), ("□", "s")])
def test_glyph_kinds(char, kind):
    assert glyph_kind(char) == kind


# ── 실제 모델 ──
def render_line(text, pixel_size, family="Malgun Gothic", width=1000):
    font = QFont(family)
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


def read_line(ocr, text, pixel_size, family="Malgun Gothic"):
    boxes = sorted(ocr.recognize(render_line(text, pixel_size, family)), key=lambda box: box.x)
    return " ".join(box.text for box in boxes)


@pytest.mark.parametrize("pixel_size", [13, 14, 16])
def test_real_model_keeps_spaces_after_period_between_items(qapp, ocr, pixel_size):
    found = read_line(ocr, "붙임 1. 2026년도 추진계획 1부. 끝.", pixel_size)
    assert "1. 2026년도" in found and "1부. 끝" in found, found


@pytest.mark.parametrize("pixel_size", [13, 14, 16])
def test_real_model_keeps_spaces_between_numbered_items(qapp, ocr, pixel_size):
    found = read_line(ocr, "가. 목적 나. 대상 다. 기간", pixel_size)
    assert all(part in found for part in ("가. 목적", "나. 대상", "다. 기간")), found


@pytest.mark.parametrize("pixel_size", [13, 14, 16])
def test_real_model_keeps_words_without_spaces_unsplit(qapp, ocr, pixel_size):
    for text in ("환경점검결과알림", "본 문서는 시험용이며 실제 업무와 관련이 없습니다."):
        assert read_line(ocr, text, pixel_size) == text


@pytest.mark.parametrize("family", ["Dotum", "Gulim", "Batang"])
@pytest.mark.parametrize("pixel_size", [12, 13, 15])
def test_real_model_does_not_split_syllables_in_wide_set_fonts(qapp, ocr, family, pixel_size):
    """돋움·굴림·바탕의 넓은 자간에서 음절 사이에 공백이 끼어들면 안 된다."""
    text = "개발 착수를 통해 국내 기술 경쟁력 강화 및 신시장 창출"
    assert read_line(ocr, text, pixel_size, family).count(" ") <= text.count(" ") + 1


def test_ctc_decode_detail_matches_ctc_decode_and_reports_run_centers():
    charset = ["가", "나", " "]
    probs = np.zeros((6, 4), dtype=np.float32)
    for step, index in enumerate([1, 1, 0, 1, 2, 3]):
        probs[step, index] = 0.9
    pieces, score = engine.ctc_decode_detail(probs, charset)
    assert pieces == [("가", 0.5), ("가", 3.0), ("나", 4.0), (" ", 5.0)]
    assert (engine.ctc_decode(probs, charset)[0], score) == ("".join(p for p, _ in pieces), pytest.approx(0.9))


def test_change_mark_stays_on_its_number():
    crop, pieces, steps, width, spaces = line("▲1.2", [9, 2, 2], glyph=10)
    spaces[:] = .5
    assert join_words(pieces, spaces, crop, steps, width) == "▲1.2"


DIGIT_ADVANCE, DIGIT_HEIGHT = 7, 10


def digits(text, space_cells=None):
    """고정폭 숫자 줄. '1'은 칸 가운데의 좁은 세로획이고 ' '는 숫자 칸의 space_cells배다. 굴림 12px은 공백이 숫자 칸과 같다."""
    space = round((space_cells or 1) * DIGIT_ADVANCE)
    width = sum(space if char == " " else DIGIT_ADVANCE for char in text) + 8
    crop = np.full((DIGIT_HEIGHT + 4, width, 3), 255, np.uint8)
    pieces, x = [], 4
    for char in text:
        if char == " ":
            x += space
            continue
        if char == "1":
            crop[2:2 + DIGIT_HEIGHT, x + 2:x + 4] = 0
        elif char in ",.":
            crop[DIGIT_HEIGHT:2 + DIGIT_HEIGHT, x + 2:x + 4] = 0
        else:
            crop[2:2 + DIGIT_HEIGHT, x:x + 6] = 0
            crop[3:1 + DIGIT_HEIGHT, x + 1:x + 5] = 255
        pieces.append((char, x + 3.0))
        x += DIGIT_ADVANCE
    return crop, pieces, width, width, np.full(width, 1e-6, np.float32)


def test_narrow_one_does_not_split_a_number():
    """굴림 '1'은 칸 가운데에 좁게 놓여 틈이 넓다. 228,145 가 228,1 45 로 쪼개졌다. 가운데 거리는 다른 숫자와 같다."""
    crop, pieces, steps, width, spaces = digits("5,228,145")
    spaces[:] = .6      # 모델이 공백을 내도 수 안이다
    assert join_words(pieces, spaces, crop, steps, width) == "5,228,145"


def test_one_at_the_end_of_a_number_stays():
    crop, pieces, steps, width, spaces = digits("13791")
    spaces[:] = .6
    assert join_words(pieces, spaces, crop, steps, width) == "13791"


def test_digits_set_wide_apart_are_not_forced_together():
    """자간을 벌린 문서의 숫자는 가운데 거리로 붙이지 않는다. 모델이 낸 공백을 따른다."""
    crop, pieces, steps, width, spaces = digits("300 1,500")
    spaced = sorted(pieces + [(" ", (pieces[2][1] + pieces[3][1]) / 2)], key=lambda piece: piece[1])
    spaces[int((pieces[2][1] + pieces[3][1]) / 2)] = .98
    assert join_words(spaced, spaces, crop, steps, width) == "300 1,500"


def test_point_inside_a_number_is_not_followed_by_a_space():
    """굴림·돋움은 마침표 칸이 넓어 90. 7 로 벌어졌다."""
    crop, pieces, steps, width, spaces = digits("90.7")
    spaces[:] = .6
    assert join_words(pieces, spaces, crop, steps, width) == "90.7"


def test_list_number_keeps_its_space():
    crop, pieces, steps, width, spaces = digits("1. 2026")
    assert join_words(pieces, spaces, crop, steps, width) == "1. 2026"


def test_line_that_is_all_long_strokes_does_not_stop_recognition():
    """긴 획을 빼면 글자 열이 하나도 안 남는 줄이 있다. 표 선만 든 상자에서 인식 전체가 멈췄다."""
    crop = np.full((14, 80, 3), 255, np.uint8)
    crop[6:8, :] = 0
    pieces = [("1", 20.0), ("2", 40.0), ("3", 60.0)]
    assert join_words(pieces, np.full(80, 1e-6, np.float32), crop, 80, 80).replace(" ", "") == "123"


def test_jittered_digit_gap_stays_in_the_number():
    """한글은 배율에 따라 글자 자리가 1px씩 흔들려 48,300 이 4 8,300 으로 쪼개졌다. 같은 상자의 숫자 간격에 견준다."""
    crop = np.full((14, 60, 3), 255, np.uint8)
    xs, pieces = [4, 11, 19, 26, 33, 41], []       # 간격 7·8이 섞인다
    for char, x in zip("482300", xs):
        crop[2:12, x:x + 5] = 0
        crop[3:11, x + 1:x + 4] = 255
        pieces.append((char, x + 2.5))
    spaces = np.full(60, .6, np.float32)
    assert join_words(pieces, spaces, crop, 60, 60) == "482300"


def test_digits_that_are_all_set_apart_keep_their_spaces():
    """1 2 3 4 처럼 모두 띄어 쓴 숫자는 숫자 간격이 넓다. 그 간격을 자로 쓰면 다 붙는다."""
    crop, pieces, steps, width, spaces = digits("7 2 3 4")
    spaces[:] = .9
    assert join_words(pieces, spaces, crop, steps, width) == "7 2 3 4"


def test_roman_numeral_keeps_its_period():
    crop, pieces, steps, width, spaces = line("Ⅱ.추진", [12, 12, 2], glyph=10)
    spaces[:] = .6
    assert join_words(pieces, spaces, crop, steps, width).startswith("Ⅱ.")
