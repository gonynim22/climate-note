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


# ── 줄마다 글자 틈과 단어 틈을 가른다(전문 조판은 단어 사이가 글자 높이의 0.2~0.35배라 고정 기준으로는 공백의 24%만 찾았다) ──
def word_line(words=(3, 3, 3), letter=2, word=6, chars=None, height=24, top=2, bottom=22):
    """글자 높이 20. 폭 10의 글자 막대를 단어별로 놓은 한 줄. (이미지, [(글자, 중심 단계)], 단계 수, 폭)."""
    blobs, x = [], 10
    for w, count in enumerate(words):
        for n in range(count):
            blobs.append((x, x + 10))
            x += 10 + (letter if n + 1 < count else word)
    image = np.full((height, x + 10, 3), 255, dtype=np.uint8)
    for start, end in blobs:                                        # 획이 있는 글자(꽉 찬 막대는 배경 추정을 뒤집는다)
        image[top:bottom, start:start + 2] = image[top:bottom, end - 2:end] = 0
        image[top + 9:top + 11, start:end] = 0
    letters = list(chars or "가" * len(blobs))
    return image, [(char, (a + b) / 2) for char, (a, b) in zip(letters, blobs)], image.shape[1], image.shape[1]


def test_narrow_word_gaps_are_found_when_the_line_has_two_clear_groups():
    image, pieces, steps, width = word_line()                       # 글자 틈 2, 단어 틈 6(글자 높이의 0.3배)
    assert engine.ink_gap_cuts(image, pieces, steps, width) == [46, 86]


def test_without_glyph_positions_the_fixed_ratio_stays():
    image, _, _, _ = word_line()
    assert engine.ink_gap_cuts(image) == []                         # 0.3배는 고정 기준 0.4배에 못 미친다


@pytest.mark.parametrize("name, kwargs", [
    ("틈이 모두 같다: 한 단어의 넓은 자간", dict(letter=6, word=6)),
    ("두 무리의 차이가 작다", dict(letter=3, word=6)),
    ("위 무리가 글자 높이의 0.2배에 못 미친다", dict(letter=1, word=3)),
    ("틈이 너무 적어 무리를 말할 수 없다", dict(words=(1, 1, 1))),
    ("짧은 줄: 몇 글자의 틈으로는 무리를 믿을 수 없다", dict(words=(3, 2))),
])
def test_line_without_two_clear_groups_keeps_the_fixed_ratio(name, kwargs):
    image, pieces, steps, width = word_line(**kwargs)
    assert engine.ink_gap_cuts(image, pieces, steps, width) == [], name


def test_gap_beside_a_narrow_glyph_keeps_the_fixed_ratio():
    # 숫자 1과 문장 부호는 옆이 넓게 비어 있다. '10', '1월', '·관'이 갈라지면 안 된다
    chars = "가나다" + "1라마" + "바사아"
    image, pieces, steps, width = word_line(chars=chars)
    assert engine.ink_gap_cuts(image, pieces, steps, width) == [86]  # 다-1 사이는 빠지고 마-바 사이만 찾는다


def test_underline_does_not_hide_a_word_gap():
    image = strip_image([(10, 20), (22, 32), (40, 50)])
    assert engine.ink_gap_cuts(image) == [35]
    image[19:21, 8:52] = 0                                          # 글자 아래 밑줄이 모든 열을 잇는다
    assert engine.ink_gap_cuts(image) == [35]


def test_table_line_across_the_box_does_not_hide_a_word_gap():
    image = strip_image([(10, 20), (22, 32), (40, 50)])
    image[1, :] = 0
    assert engine.ink_gap_cuts(image) == [35]


def with_model_space(pieces, *positions):
    spaces = [(" ", float(x)) for x in positions]
    return sorted(pieces + spaces, key=lambda piece: piece[1])


def test_spaces_the_model_gave_set_the_word_gap_of_their_line():
    # 모델이 공백을 일부만 내도 그 자리의 틈이 이 줄의 단어 틈이다. 나머지 단어 틈을 그 크기로 찾는다
    image, pieces, steps, width = word_line()
    assert engine.ink_gap_cuts(image, with_model_space(pieces, 47), steps, width) == [46, 86]


def test_letter_gaps_narrower_than_the_model_spaces_are_not_split():
    # 모델이 낸 단어 틈(9열)보다 좁은 글자 틈(5열)은 넓어 보여도 갈라지면 안 된다('책 임 이', '주시 기')
    image, pieces, steps, width = word_line(words=(2, 2, 2, 2), letter=5, word=9)
    spaced = with_model_space(pieces, 40, 74, 108)
    assert engine.ink_gap_cuts(image, spaced, steps, width) == [39, 73, 107]


def test_model_space_too_narrow_to_be_a_word_gap_keeps_the_fixed_ratio():
    image, pieces, steps, width = word_line(letter=1, word=3)        # 글자 높이의 0.15배
    assert engine.ink_gap_cuts(image, with_model_space(pieces, 43), steps, width) == []


def test_short_horizontal_strokes_of_letters_are_kept():
    image = strip_image([(10, 20), (22, 32), (40, 50)])
    image[11:13, 10:32] = 0                                         # 글자 높이의 2배쯤인 가로획은 글자 획이다
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
def render_line(text, pixel_size, width=1000, word_spacing=0.0, letter_spacing=0.0):
    font = QFont("Malgun Gothic")
    font.setPixelSize(pixel_size)
    if word_spacing or letter_spacing:                              # PDF 뷰어처럼 힌팅 없이 그린 좁은 조판
        font.setWordSpacing(word_spacing)
        font.setLetterSpacing(QFont.AbsoluteSpacing, letter_spacing)
        font.setHintingPreference(QFont.PreferNoHinting)
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


@pytest.mark.parametrize("pixel_size, letter", [(16, -0.04), (16, -0.06), (24, -0.06), (24, -0.08)])
def test_wide_letter_gaps_are_not_split_when_word_gaps_are_normal(qapp, ocr, pixel_size, letter):
    # 단어 틈이 고정 기준을 넘는 줄에서 기준을 낮추면 '책 임 이', '주시 기'처럼 단어가 갈라졌다
    text = "응시자의 책임이 되므로 반드시 내용을 확인하여 주시기 바랍니다"
    image = render_line(text, pixel_size, word_spacing=-0.14 * pixel_size, letter_spacing=letter * pixel_size)
    found = " ".join(box.text for box in sorted(ocr.recognize(image), key=lambda box: box.x))
    assert found.count(" ") <= text.count(" "), found


@pytest.mark.parametrize("pixel_size", [13, 14, 16])
def test_keeps_words_without_spaces_unsplit(qapp, ocr, pixel_size):
    for text in ("환경점검결과알림", "본 문서는 시험용이며 실제 업무와 관련이 없습니다."):
        assert read_line(ocr, text, pixel_size) == text
