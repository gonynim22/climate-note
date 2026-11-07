"""화면 글자 따기: 모델이 건너뛰거나 닮은 글자로 읽은 △ ▲를 화면 모양으로 되살린다.

모델 사전에 없는 글자라 그대로 두면 △32%가 32%로 읽혀 감소가 증가로 바뀐다. 표의 (△2.2) 같은 숫자 앞 표기는
밑변이 숫자에 붙어 한 덩어리가 되고, 100% 배율에서는 가는 밑변이 옅어 글자 픽셀로 잡히지 않기도 한다.
"""
import numpy as np
import pytest

from screen_text.triangles import restore_triangles

HEIGHT = 24
STEP = 4        # 크롭 4px당 CTC 한 단계


def triangle(width, height, kind="hollow", base=True, thick=2):
    glyph = np.zeros((height, width), bool)
    for y in range(height):
        half = (y + 1) / height * (width - 1) / 2
        left, right = (width - 1) / 2 - half, (width - 1) / 2 + half
        a, b = int(round(left)), int(round(right))
        if kind == "filled":
            glyph[y, a:b + 1] = True
        else:
            glyph[y, a:a + thick] = True
            glyph[y, max(a, b - thick + 1):b + 1] = True
    if base and kind != "filled":
        glyph[-2:] = True
    return glyph


def blank(width=200):
    return np.full((HEIGHT, width, 3), 255, np.uint8)


def stamp(image, glyph, x, top=None):
    height, width = glyph.shape
    top = (HEIGHT - height) // 2 if top is None else top
    image[top:top + height, x:x + width][glyph] = 0


def hangul(image, x):
    """한글 음절처럼 획이 있는 13×18 블록."""
    image[3:21, x:x + 2] = 0
    image[3:21, x + 11:x + 13] = 0
    image[11:13, x:x + 13] = 0


def digit(image, x):
    """숫자처럼 폭이 좁은 7×16 블록."""
    image[4:20, x + 5:x + 7] = 0
    image[4:6, x:x + 7] = 0
    image[18:20, x:x + 7] = 0


def run(pieces, image, end):
    steps = end // STEP
    return restore_triangles([(char, x / STEP) for char, x in pieces], image[:, :end], steps, end)


def chars(pieces):
    return [char for char, _ in pieces]


@pytest.mark.parametrize("kind, mark", [("hollow", "△"), ("filled", "▲")])
def test_triangle_the_model_skipped_is_inserted_in_place(kind, mark):
    image = blank()
    hangul(image, 2)
    stamp(image, triangle(18, 16, kind), 26)
    hangul(image, 54)
    out = run([("대", 8), ("민", 60)], image, 70)
    assert chars(out) == ["대", mark, "민"]
    assert out[0][1] < out[1][1] < out[2][1]


def test_triangle_without_its_faint_base_is_still_inserted():
    image = blank()
    hangul(image, 2)
    stamp(image, triangle(18, 15, base=False), 26)               # 100% 배율: 가는 밑변이 옅어 글자 픽셀로 잡히지 않는다
    hangul(image, 54)
    assert chars(run([("대", 8), ("민", 60)], image, 70)) == ["대", "△", "민"]


def test_triangle_at_the_start_and_end_of_the_box_is_inserted():
    image = blank()
    stamp(image, triangle(18, 16), 2)
    hangul(image, 30)
    assert chars(run([("선", 36)], image, 46)) == ["△", "선"]
    image = blank()
    hangul(image, 2)
    stamp(image, triangle(18, 16), 26)
    assert chars(run([("선", 8)], image, 50)) == ["선", "△"]


def test_triangle_touching_the_next_digit_is_cut_from_it():
    image = blank()
    hangul(image, 2)
    glyph = triangle(16, 14)
    stamp(image, glyph, 28)
    image[17:19, 44:48] = 0                                      # 밑변이 뒤 숫자의 아랫획에 붙었다
    digit(image, 46)
    out = run([("비", 8), ("3", 50)], image, 60)
    assert chars(out) == ["비", "△", "3"]


CLIPPED_TITLE = """
.....##...##......##..###.#####....#####....###....#############...
....########......##..##..###.....###.###...###....############....
..#########.......##......###....###...###..###......###...##......
.####...####......###...#.###...###.....##..###......###...##......
.###......##..###############....#..........###..################..
.###......##..###############...............###..################..
.###########..............###...............###...###############..
..#########...............###...............###....................
.....###..................###...............##.....................
...................................................................
...................................................................
""".split()


def test_stroke_of_a_clipped_title_is_not_cut_out_as_a_filled_triangle():
    # 실제 공문서 PDF: 큰 제목 글씨가 잘린 상자라 줄 높이가 작게 재져 글자 사이가 건너뛴 자리로 보였다.
    # 'ㅏ'의 세로획+가로획을 뒤 글자에서 잘라 내면 꽉 찬 삼각형처럼 보인다. 자르기는 속이 빈 △에만 쓴다.
    ink = np.array([[char == "#" for char in row] for row in CLIPPED_TITLE])
    image = np.where(ink[..., None], 0, 255).repeat(3, axis=2).astype(np.uint8)
    end = ink.shape[1]
    out = restore_triangles([(char, x / STEP) for char, x in (("정", 5), ("과", 22), ("시", 38), ("뇨", 56))], image, end // STEP, end)
    assert chars(out) == ["정", "과", "시", "뇨"]


@pytest.mark.parametrize("read", ["스", "ㅅ", "!", "∆"])
def test_triangle_read_as_a_look_alike_is_replaced_at_the_same_place(read):
    image = blank()
    hangul(image, 2)
    stamp(image, triangle(18, 16), 22)
    hangul(image, 44)
    out = run([("대", 8), (read, 31), ("민", 50)], image, 60)
    assert chars(out) == ["대", "△", "민"]
    assert out[1][1] == 31 / STEP


def test_real_seu_is_not_a_triangle():
    image = blank()
    stamp(image, triangle(14, 8, base=False), 20, top=3)         # 'ㅅ'
    image[17:19, 18:36] = 0                                      # 'ㅡ': 빈 행을 사이에 둔 긴 막대
    hangul(image, 2)
    hangul(image, 44)
    pieces = [("서", 8), ("스", 27), ("템", 50)]
    assert chars(run(pieces, image, 60)) == ["서", "스", "템"]


def test_bold_capital_a_is_not_a_filled_triangle():
    image = blank()
    glyph = triangle(18, 16, "filled")
    glyph[6:8, 8:10] = False                                     # 굵은 제목 글씨의 A: 속에 작은 구멍이 있다
    glyph[12:, 5:13] = False                                     # 그리고 다리 사이가 비어 있다
    stamp(image, glyph, 26)
    hangul(image, 2)
    hangul(image, 54)
    assert chars(run([("1", 8), ("A", 34), ("I", 60)], image, 70)) == ["1", "A", "I"]
    assert chars(run([("1", 8), ("I", 60)], image, 70)) == ["1", "I"]


@pytest.mark.parametrize("name, glyph", [
    ("점이나 작은 표시", triangle(8, 8)),
    ("꼭짓점이 한쪽으로 치우친 쐐기", np.flipud(np.tri(14, 14, 0, dtype=bool))[::-1]),
    ("세로로 긴 모양", triangle(8, 18)),
    ("네모", np.ones((14, 14), bool)),
])
def test_other_shapes_are_left_alone(name, glyph):
    image = blank()
    hangul(image, 2)
    stamp(image, glyph, 28)
    hangul(image, 54)
    assert chars(run([("대", 8), ("민", 60)], image, 70)) == ["대", "민"], name


def test_read_character_at_that_place_is_left_alone():
    image = blank()
    hangul(image, 2)
    stamp(image, triangle(18, 16), 26)
    hangul(image, 54)
    assert chars(run([("대", 8), ("소", 35), ("민", 60)], image, 70)) == ["대", "소", "민"]


def test_empty_cases_return_the_input():
    image = blank()
    pieces = [("대", 2.0)]
    assert restore_triangles(pieces, image[:, :0], 1, 0) is pieces
    assert restore_triangles(pieces, image, 50, 200) is pieces          # 글자 픽셀이 없다
    assert restore_triangles([], image, 50, 200) == []


def test_filled_triangle_read_as_a_before_a_number_is_restored():
    image = blank()
    stamp(image, triangle(14, 12, "filled"), 10, 6)
    digit(image, 30)
    assert chars(run([("A", 17), ("1", 34)], image, 60)) == ["▲", "1"]


def test_bold_a_before_a_number_stays():
    image = blank()
    glyph = triangle(14, 12, "filled")
    glyph[8:10, 4:10] = False                  # 'A'의 구멍
    stamp(image, glyph, 10, 6)
    digit(image, 30)
    assert chars(run([("A", 17), ("4", 34)], image, 60)) == ["A", "4"]


def test_model_triangle_is_always_the_standard_mark():
    image = blank()
    digit(image, 30)
    assert chars(run([("∆", 17), ("1", 34)], image, 60)) == ["△", "1"]
