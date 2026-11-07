"""모델이 놓친 문장 부호·별표·원문자를 모델 확률과 화면 모양으로 되살린다."""
import numpy as np

from screen_text.marks import rescue_marks, restore_circled_digits, restore_stars, restore_thin_capitals

CHARSET = ["가", "나", ")", ",", "*", " "]


def probabilities(best, second=None):
    """단계별 가장 높은 클래스 목록으로 확률표를 만든다. second는 {단계: (클래스, 확률)}."""
    table = np.full((len(best), len(CHARSET) + 1), 1e-4, np.float32)
    for step, index in enumerate(best):
        table[step, index] = .9
    for step, (index, value) in (second or {}).items():
        table[step, index] = value
    return table


def test_mark_hidden_behind_blank_is_rescued():
    table = probabilities([1, 1, 0, 0, 2, 2], {2: (3, .45)})
    assert rescue_marks([("가", .5), ("나", 4.5)], table, CHARSET) == [("가", .5), (")", 2.0), ("나", 4.5)]


def test_box_the_model_read_as_nothing_stays_empty():
    """아무것도 못 읽은 상자의 부호는 글자 조각이다. 맞은 것 20건에 없는 '(' 65건이었다."""
    table = probabilities([0, 0, 0, 0], {1: (3, .45)})
    assert rescue_marks([], table, CHARSET) == []


def test_weak_mark_stays_blank():
    table = probabilities([1, 1, 0, 0, 2, 2], {2: (3, .1)})
    pieces = [("가", .5), ("나", 4.5)]
    assert rescue_marks(pieces, table, CHARSET) is pieces


def test_mark_the_model_already_read_is_not_doubled():
    table = probabilities([1, 0, 3, 0, 2], {1: (3, .45), 3: (3, .45)})
    pieces = [("가", 0.), (")", 2.), ("나", 4.)]
    assert rescue_marks(pieces, table, CHARSET) is pieces


def test_letters_are_never_rescued():
    table = probabilities([1, 0, 0, 2], {1: (2, .8)})    # blank 뒤의 '나'는 문장 부호가 아니다
    pieces = [("가", 0.), ("나", 3.)]
    assert rescue_marks(pieces, table, CHARSET) is pieces


HEIGHT = 24


def blank(width=120):
    return np.full((HEIGHT, width, 3), 255, np.uint8)


def hangul(image, x):
    image[3:21, x:x + 2] = 0
    image[3:21, x + 13:x + 15] = 0
    image[11:13, x:x + 15] = 0


def star(image, x, top=3, size=9):
    middle = size // 2
    image[top + middle, x:x + size] = 0
    image[top:top + size, x + middle] = 0
    for k in range(size):
        image[top + k, x + k] = 0
        image[top + k, x + size - 1 - k] = 0
    image[top + middle - 1:top + middle + 2, x + middle - 1:x + middle + 2] = 0


def quote(image, x, top=3):
    image[top:top + 8, x:x + 2] = 0


def run(restore, pieces, image):
    return restore([(char, float(x)) for char, x in pieces], image, image.shape[1], image.shape[1])


def test_quote_shaped_star_becomes_star():
    image = blank()
    hangul(image, 10)
    star(image, 28)
    hangul(image, 44)
    assert [c for c, _ in run(restore_stars, [("가", 17), ('"', 32), ("나", 51)], image)] == ["가", "*", "나"]


def test_real_double_quote_stays():
    image = blank()
    hangul(image, 10)
    quote(image, 29)
    quote(image, 34)
    hangul(image, 44)
    assert [c for c, _ in run(restore_stars, [("가", 17), ('"', 32), ("나", 51)], image)] == ["가", '"', "나"]


def test_apostrophe_stays():
    image = blank()
    quote(image, 29)
    hangul(image, 44)
    assert [c for c, _ in run(restore_stars, [("'", 30), ("나", 51)], image)] == ["'", "나"]


def ring(image, x, size=18, top=3, digit=True):
    yy, xx = np.ogrid[:size, :size]
    distance = np.hypot(yy - (size - 1) / 2, xx - (size - 1) / 2)
    mask = (distance <= size / 2) & (distance >= size / 2 - 2)
    image[top:top + size, x:x + size][mask] = 0
    if digit:
        image[top + 5:top + 13, x + 8:x + 10] = 0


def test_digit_inside_ring_becomes_circled_digit():
    image = blank()
    ring(image, 10)
    hangul(image, 34)
    assert [c for c, _ in run(restore_circled_digits, [("2", 19), ("가", 41)], image)] == ["②", "가"]


def test_plain_digit_stays():
    image = blank()
    image[5:19, 18:20] = 0
    hangul(image, 34)
    assert [c for c, _ in run(restore_circled_digits, [("2", 19), ("가", 41)], image)] == ["2", "가"]


def test_digit_beside_a_round_letter_stays():
    image = blank()
    ring(image, 10, digit=False)   # 'G5' 의 G 처럼 비어 있는 고리
    image[5:19, 34:36] = 0
    assert [c for c, _ in run(restore_circled_digits, [("5", 35)], image)] == ["5"]


def test_digits_of_a_number_inside_table_ring_stay():
    image = blank()
    ring(image, 10)
    assert [c for c, _ in run(restore_circled_digits, [("1", 15), ("2", 22)], image)] == ["1", "2"]


def capital(image, x):
    """폭 13의 'A'처럼 위가 좁고 아래가 넓은 덩어리."""
    for row in range(3, 21):
        half = (row - 3) * 6 // 18
        image[row, x + 6 - half:x + 8 + half] = 0


def stem(image, x):
    image[3:21, x:x + 2] = 0


def test_thin_stroke_after_capital_becomes_capital_i():
    image = blank()
    capital(image, 10)
    stem(image, 27)
    hangul(image, 46)
    assert [c for c, _ in run(restore_thin_capitals, [("A", 17), ("가", 53)], image)] == ["A", "I", "가"]


def test_no_stroke_means_no_capital_i():
    image = blank()
    capital(image, 10)
    hangul(image, 46)
    assert [c for c, _ in run(restore_thin_capitals, [("A", 17), ("가", 53)], image)] == ["A", "가"]


def test_stroke_after_lowercase_is_left_alone():
    image = blank()
    capital(image, 10)
    stem(image, 27)
    assert [c for c, _ in run(restore_thin_capitals, [("a", 17), ("가", 53)], image)] == ["a", "가"]
