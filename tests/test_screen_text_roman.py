"""공문서 번호의 로마 숫자를 세로획 수로 되살린다. 번호 자리가 아니거나 획 모양이 다르면 글자를 바꾸지 않는다."""
import numpy as np

from screen_text.roman import restore_roman, stroke_count

HEIGHT, TOP = 12, 3


def canvas(width):
    return np.full((HEIGHT + 2 * TOP, width, 3), 255, np.uint8)


def numeral(image, x, strokes, bars=True, gap=4):
    """세로획 strokes개. bars면 위아래 세리프로 잇는다(맑은 고딕), 아니면 줄기만(굴림)."""
    for k in range(strokes):
        image[TOP:TOP + HEIGHT, x + k * gap] = 0
    if bars:
        image[TOP, x - 1:x + (strokes - 1) * gap + 2] = 0
        image[TOP + HEIGHT - 1, x - 1:x + (strokes - 1) * gap + 2] = 0
    return x + (strokes - 1) * gap


def dot_and_word(image, x):
    image[TOP + HEIGHT - 2:TOP + HEIGHT, x:x + 2] = 0
    image[TOP + 1:TOP + HEIGHT - 1, x + 8:x + 20] = 0     # 낱말 덩어리
    return [(".", x + 1.0), ("추", x + 14.0)]


def text(result):
    return "".join(char for char, _ in result)


def line(reads, strokes, bars=True):
    image = canvas(60)
    right = numeral(image, 4, strokes, bars)
    pieces = [(char, 4.0 + k * 3) for k, char in enumerate(reads)] + dot_and_word(image, right + 5)
    return pieces, image, 60, 60


def test_two_strokes_read_as_one_letter():
    """Ⅱ 가 I 로 읽히면 다른 번호가 된다."""
    pieces, image, steps, width = line("I", 2)
    assert text(restore_roman(pieces, image, steps, width)) == "Ⅱ.추"


def test_three_strokes_read_as_korean():
    pieces, image, steps, width = line("피", 3)
    assert text(restore_roman(pieces, image, steps, width)) == "Ⅲ.추"


def test_three_strokes_read_as_two_letters():
    pieces, image, steps, width = line("II", 3)
    assert text(restore_roman(pieces, image, steps, width)) == "Ⅲ.추"


def test_stems_without_serifs():
    """굴림의 Ⅱ 는 줄기만 있다."""
    pieces, image, steps, width = line("||", 2, bars=False)
    assert text(restore_roman(pieces, image, steps, width)) == "Ⅱ.추"


def test_bar_read_as_one():
    pieces, image, steps, width = line("|", 1)
    assert text(restore_roman(pieces, image, steps, width)) == "Ⅰ.추"


def test_letter_i_stays_when_one_stroke():
    pieces, image, steps, width = line("I", 1)
    assert restore_roman(pieces, image, steps, width) == pieces


def test_digit_one_stays():
    pieces, image, steps, width = line("1", 1)
    assert restore_roman(pieces, image, steps, width) == pieces


def test_two_digits_stay():
    """11.6 과 쪽 번호 11 은 세로획 둘로 보여도 숫자다."""
    pieces, image, steps, width = line("11", 2, bars=False)
    assert restore_roman(pieces, image, steps, width) == pieces


def test_middle_of_a_word_stays():
    image = canvas(60)
    numeral(image, 20, 2)
    pieces = [("가", 8.0), ("I", 22.0), ("나", 40.0)]
    assert restore_roman(pieces, image, 60, 60) == pieces


def test_not_a_number_slot_stays():
    """뒤에 낱말이 바로 이어지면 번호가 아니다."""
    image = canvas(60)
    numeral(image, 4, 2)
    pieces = [("I", 6.0), ("나", 30.0)]
    assert restore_roman(pieces, image, 60, 60) == pieces


def test_korean_with_short_stems_is_not_three_strokes():
    """'피'의 ㅍ 줄기는 ㅣ보다 짧다."""
    image = np.zeros((HEIGHT, 13), bool)
    image[2:6, 1] = image[2:6, 5] = True
    image[1, 0:7] = image[6, 0:7] = True
    image[:, 10] = True
    assert stroke_count(image) == 0


def test_stroke_count_of_clean_numerals():
    for strokes in (1, 2, 3):
        image = np.zeros((HEIGHT, 20), bool)
        for k in range(strokes):
            image[:, 2 + k * 4] = True
        assert stroke_count(image) == strokes


def test_brackets_count_as_number_slot():
    image = canvas(70)
    image[TOP:TOP + HEIGHT, 3] = 0                        # (
    numeral(image, 12, 2)
    image[TOP + 5:TOP + 7, 24:28] = 0                     # -
    pieces = [("(", 3.0), ("I", 14.0), ("-", 26.0), ("1", 40.0)]
    assert text(restore_roman(pieces, image, 70, 70)) == "(Ⅱ-1"


def test_square_bracket_stroke_is_not_counted():
    """[Ⅰ-2-1] 의 '['을 획으로 세면 Ⅱ 가 된다."""
    image = canvas(70)
    image[TOP:TOP + HEIGHT, 3] = 0                        # [
    image[TOP, 3:6] = image[TOP + HEIGHT - 1, 3:6] = 0
    numeral(image, 12, 1, bars=False)
    image[TOP + 5:TOP + 7, 18:22] = 0                     # -
    pieces = [("[", 3.0), ("|", 12.0), ("-", 20.0), ("2", 40.0)]
    assert text(restore_roman(pieces, image, 70, 70)) == "[Ⅰ-2"


def test_chapter_form_is_left_to_the_model():
    """'제Ⅱ장'은 앞 글자 ㅔ 획이 섞여 번호가 틀어질 수 있어 건드리지 않는다."""
    image = canvas(70)
    image[TOP:TOP + HEIGHT, 13] = 0
    numeral(image, 22, 2)
    pieces = [("제", 8.0), ("I", 24.0), ("장", 43.0)]
    assert restore_roman(pieces, image, 70, 70) == pieces


def test_model_reading_a_numeral_is_kept():
    """모델이 이미 Ⅱ 로 읽었으면 칸을 잘못 잘라도 줄이지 않는다."""
    pieces, image, steps, width = line("Ⅱ", 1)
    assert restore_roman(pieces, image, steps, width) == pieces


def test_number_alone_in_a_cell_stays():
    """표 칸의 11 이 1l 로 읽혀도 세로획 둘을 Ⅱ 로 바꾸지 않는다."""
    image = canvas(30)
    numeral(image, 8, 2, bars=False)
    pieces = [("1", 8.0), ("l", 12.0)]
    assert restore_roman(pieces, image, 30, 30) == pieces
