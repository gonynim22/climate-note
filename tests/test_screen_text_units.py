"""㎡ ㎥ ㎢ ℃ 를 화면 모양으로 되살린다. 모양이 없으면 글자를 바꾸지 않는다."""
import numpy as np

from screen_text.units import restore_units

INK = 0
TOP, X_HEIGHT, LEFT = 6, 8, 3
SUPER_2 = ["##.", "..#", ".#.", "#..", "###"]
SUPER_3 = ["##.", "..#", ".#.", "..#", "##."]
SMALL = ["###", "###", "###"]
RING = [".#.", "#.#", ".#."]


def canvas(width, height=20):
    return np.full((height, width, 3), 255, np.uint8)


def draw(image, shape, top, left):
    for row, pattern in enumerate(shape):
        for column, cell in enumerate(pattern):
            if cell == "#":
                image[top + row, left + column] = INK


def letter_m(image, x):
    """x-높이 8의 m. 줄기 셋과 위 가로획."""
    image[TOP + 3, x:x + 9] = INK
    for offset in (0, 4, 8):
        image[TOP + 3:TOP + 3 + X_HEIGHT, x + offset] = INK


def letter_c(image, x):
    image[TOP, x + 1:x + 7] = INK
    image[TOP + 10, x + 1:x + 7] = INK
    image[TOP:TOP + 11, x] = INK


def text(result):
    return "".join(char for char, _ in result[0])


def unit_line(reads, superscript=None, step=1.0):
    """숫자 칸 + m + 위 첨자. reads는 모델이 m 뒤에 읽은 글자들이다."""
    image = canvas(40)
    image[TOP + 1:TOP + 11, LEFT:LEFT + 5] = INK     # 숫자 자리
    image[TOP + 2:TOP + 10, LEFT + 1:LEFT + 4] = 255
    letter_m(image, 11)
    if superscript:
        draw(image, superscript, TOP - 3, 21)
    pieces = [("2", LEFT + 2.5), ("m", 15.0)] + [(char, 22.0 + k) for k, char in enumerate(reads)]
    return pieces, image, 40, 40


def test_cube_read_as_plain_m():
    pieces, image, steps, width = unit_line("", SUPER_3)
    assert text(restore_units(pieces, image, steps, width)) == "2㎥"


def test_square_read_as_plain_m():
    pieces, image, steps, width = unit_line("", SUPER_2)
    assert text(restore_units(pieces, image, steps, width)) == "2㎡"


def test_screen_wins_over_model_digit():
    """모델은 ㎥ 을 m² 로 가장 많이 틀린다."""
    pieces, image, steps, width = unit_line("²", SUPER_3)
    assert text(restore_units(pieces, image, steps, width)) == "2㎥"


def test_misread_superscript_is_replaced():
    pieces, image, steps, width = unit_line("{", SUPER_2)
    assert text(restore_units(pieces, image, steps, width)) == "2㎡"


def test_too_small_to_tell_uses_model_digit_and_flags():
    pieces, image, steps, width = unit_line("3", SMALL)
    out, doubtful = restore_units(pieces, image, steps, width)
    assert "".join(char for char, _ in out) == "2㎥" and len(doubtful) == 1


def test_plain_meter_stays():
    pieces, image, steps, width = unit_line("")
    assert restore_units(pieces, image, steps, width) == (pieces, ())


def test_word_with_m_stays():
    pieces, image, steps, width = unit_line("", SUPER_3)
    pieces = [("e", 3.0), ("m", 15.0), ("a", 28.0)]
    assert restore_units(pieces, image, steps, width) == (pieces, ())


def test_centimeter_stays():
    pieces, image, steps, width = unit_line("", SUPER_2)
    pieces = [("c", 3.0), ("m", 15.0)]
    assert restore_units(pieces, image, steps, width) == (pieces, ())


def test_square_kilometer():
    image = canvas(50)
    image[TOP + 1:TOP + 11, LEFT:LEFT + 4] = INK     # k 자리
    letter_m(image, 11)
    draw(image, SUPER_2, TOP - 3, 21)
    pieces = [("k", LEFT + 2.0), ("m", 15.0), ("2", 22.0)]
    assert text(restore_units(pieces, image, 50, 50)) == "㎢"


def degree_line(reads, ring=True):
    image = canvas(40)
    image[TOP + 1:TOP + 11, LEFT:LEFT + 5] = INK
    image[TOP + 2:TOP + 10, LEFT + 1:LEFT + 4] = 255
    if ring:
        draw(image, RING, TOP, 11)
    letter_c(image, 16)
    pieces = [("2", LEFT + 2.5)] + [(char, 12.0) for char in reads] + [("C", 19.0)]
    return pieces, image, 40, 40


def test_celsius_read_as_plain_c():
    pieces, image, steps, width = degree_line("")
    assert text(restore_units(pieces, image, steps, width)) == "2℃"


def test_celsius_read_with_a_quote():
    pieces, image, steps, width = degree_line("'")
    assert text(restore_units(pieces, image, steps, width)) == "2℃"


def test_lowercase_reading():
    pieces, image, steps, width = degree_line("")
    pieces[-1] = ("c", pieces[-1][1])
    assert text(restore_units(pieces, image, steps, width)) == "2℃"


def test_plain_grade_c_stays():
    pieces, image, steps, width = degree_line("", ring=False)
    assert restore_units(pieces, image, steps, width) == (pieces, ())


def test_c_inside_a_word_stays():
    pieces, image, steps, width = degree_line("")
    pieces = pieces + [("O", 26.0), ("2", 31.0)]
    assert restore_units(pieces, image, steps, width) == (pieces, ())


def test_space_pieces_survive():
    pieces, image, steps, width = unit_line("", SUPER_3)
    pieces = [pieces[0], (" ", 8.0), pieces[1]]
    assert text(restore_units(pieces, image, steps, width)) == "2 ㎥"


def test_superscript_right_above_the_last_stem():
    """함초롬 글꼴은 위 첨자가 m 오른쪽 줄기 바로 위에 놓인다. 줄기까지 위 첨자로 세면 키가 m보다 커져 놓쳤다."""
    pieces, image, steps, width = unit_line("")
    draw(image, ["##", ".#", "##"], TOP, 18)
    out, doubtful = restore_units(pieces, image, steps, width)
    assert "".join(char for char, _ in out) == "2㎡" and len(doubtful) == 1


def test_undecided_superscript_after_a_slash_is_a_cube():
    """㎍/㎥ 은 농도다. 위 첨자 모양을 말할 수 없으면 세제곱으로 두고 확인 필요로 표시한다."""
    pieces, image, steps, width = unit_line("", SMALL)
    pieces = [("/", 8.0), pieces[1]]
    out, doubtful = restore_units(pieces, image, steps, width)
    assert "".join(char for char, _ in out) == "/㎥" and len(doubtful) == 1
