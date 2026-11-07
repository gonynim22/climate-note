"""숫자 안의 쉼표와 마침표를 화면 모양으로 가른다. 글자로 판단할 수 없는 자리는 바꾸지 않고 표시만 한다."""
import numpy as np

from screen_text.number_marks import restore_number_marks

WHITE, BLACK = 255, 0
INK = BLACK
DIGIT_W, DIGIT_H, GAP, TOP = 5, 9, 2, 3

PERIOD = ["#"]                       # 맑은 고딕 작은 글씨: 바닥선에 놓인 한 점
TICK = ["#", "#"]                    # 돋움 12px: 바닥선에서 끝나는 세로 2화소
LOW_TICK = ["#", "#"]                # 굴림 12px: 바닥선 아래로 1화소 내려오는 세로 2화소
COMMA = [".#", ".#", "#."]           # 바닥선 아래로 내려오는 꼬리
SLANT = [".#", "#."]                 # 굴림 12px 쉼표: 왼쪽 아래로 기운 2화소


def line(text, marks, ink=BLACK, paper=WHITE, drops=None, digit_h=DIGIT_H, tail=4):
    """숫자는 속 빈 네모, 구두점은 marks의 모양으로 그린 줄과 pieces를 만든다. 구두점 아래 끝이 바닥선에서 내려온 화소 수는 drops다."""
    drops = drops or {}
    width = sum((DIGIT_W if char.isdigit() else 3) + GAP for char in text) + 4
    image = np.full((TOP + digit_h + tail, width, 3), paper, np.uint8)
    pieces, x, mark = [], 2, 0
    bottom = TOP + digit_h - 1
    for char in text:
        if char.isdigit():
            image[TOP:bottom + 1, x:x + DIGIT_W] = ink
            image[TOP + 1:bottom, x + 1:x + DIGIT_W - 1] = paper
            pieces.append((char, x + DIGIT_W / 2))
            x += DIGIT_W + GAP
        else:
            shape, drop = marks[mark], drops.get(mark, 0)
            mark += 1
            low = bottom + drop
            for row, pattern in enumerate(shape):
                for column, cell in enumerate(pattern):
                    if cell == "#":
                        image[low - len(shape) + 1 + row, x + column] = ink
            pieces.append((char, x + 1.0))
            x += 3 + GAP
    return pieces, image, (0, 0, width, TOP + digit_h), width


def run(text, marks, **keyword):
    pieces, image, box, steps = line(text, marks, **keyword)
    out, doubtful = restore_number_marks(pieces, image, box, steps)
    return "".join(char for char, _ in out), doubtful


def test_decimal_read_as_comma_returns_to_period():
    assert run("5,6", [PERIOD])[0] == "5.6"
    assert run("27,3", [TICK])[0] == "27.3"


def test_gulim_bitmap_period_below_baseline_is_a_period():
    assert run("5,6", [LOW_TICK], drops={0: 1}, digit_h=10)[0] == "5.6"


def test_gulim_bitmap_comma_is_slanted():
    assert run("4.100", [SLANT], drops={0: 1}, digit_h=10)[0] == "4,100"


def test_leading_zero_cannot_be_a_thousands_comma():
    assert run("0,183", [PERIOD])[0] == "0.183"


def test_thousands_read_as_period_returns_to_comma():
    assert run("4.100", [COMMA], drops={0: 2})[0] == "4,100"
    assert run("1.234.567", [COMMA, COMMA], drops={0: 2, 1: 2})[0] == "1,234,567"


def test_undecidable_three_digits_stay_and_are_flagged():
    """3,852 는 글자로는 천 단위다. HY신명조 쉼표가 마침표와 같은 모양이라 화면만 믿고 바꾸지 않는다."""
    text, doubtful = run("3,852", [PERIOD])
    assert text == "3,852" and len(doubtful) == 1


def test_comma_shape_on_short_decimal_stays_and_is_flagged():
    text, doubtful = run("5.6", [COMMA], drops={0: 2})
    assert text == "5.6" and len(doubtful) == 1


def test_correct_reading_is_left_alone():
    pieces, image, box, steps = line("4,100", [COMMA], drops={0: 2})
    assert restore_number_marks(pieces, image, box, steps) == (pieces, ())
    pieces, image, box, steps = line("2026.10.12", [PERIOD, PERIOD])
    assert restore_number_marks(pieces, image, box, steps) == (pieces, ())


def test_tail_below_the_box_still_counts():
    """상자는 숫자 바닥선에서 끝나도 꼬리는 그 아래에 있다. 상자만 보면 마침표로 보인다."""
    pieces, image, box, steps = line("4.100", [COMMA], drops={0: 3})
    assert box[3] <= TOP + DIGIT_H
    assert "".join(char for char, _ in restore_number_marks(pieces, image, box, steps)[0]) == "4,100"


def test_dark_screen():
    assert run("5,6", [PERIOD], ink=230, paper=30)[0] == "5.6"
    assert run("4.100", [COMMA], drops={0: 2}, ink=230, paper=30)[0] == "4,100"


def test_mark_outside_numbers_is_left_alone():
    pieces = [("가", 3.0), (",", 10.0), ("나", 16.0)]
    image = np.full((16, 22, 3), WHITE, np.uint8)
    assert restore_number_marks(pieces, image, (0, 0, 22, 12), 22) == (pieces, ())


def test_space_inside_the_number_does_not_hide_it():
    """6, 8 처럼 공백으로 읽혀도 숫자 사이의 부호다."""
    pieces, image, box, steps = line("6,8", [PERIOD])
    pieces = [pieces[0], pieces[1], (" ", pieces[1][1] + 1), pieces[2]]
    out, _ = restore_number_marks(pieces, image, box, steps)
    assert [char for char, _ in out] == ["6", ".", " ", "8"]


def test_no_digit_on_screen_keeps_reading():
    """위치가 어긋나 숫자 덩어리를 못 찾으면 모양을 말할 수 없다."""
    pieces = [("5", 3.0), (",", 8.0), ("6", 13.0)]
    image = np.full((16, 20, 3), WHITE, np.uint8)
    assert restore_number_marks(pieces, image, (0, 0, 20, 12), 20) == (pieces, ())


def spaced_pair(first, second, marks, space_piece=False, **keyword):
    """수 두 개를 큰 틈을 두고 나란히 그린다. 모델이 공백을 냈는지와 무관하게 다른 수다."""
    a, image_a, box_a, steps_a = line(first, marks[:1], **keyword)
    b, image_b, _, _ = line(second, marks[1:], **keyword)
    gap = 12
    image = np.concatenate((image_a, np.full((image_a.shape[0], gap, 3), WHITE, np.uint8), image_b), axis=1)
    shift = image_a.shape[1] + gap
    pieces = a + ([(" ", image_a.shape[1] + gap / 2)] if space_piece else []) + [(char, center + shift) for char, center in b]
    return pieces, image, (0, 0, image.shape[1], box_a[3]), image.shape[1]


def test_digits_of_the_next_number_do_not_count():
    """상자 하나에 1,445 1,545 가 나란하면 뒤 수의 숫자까지 세어 3자리가 아닌 줄 알고 마침표로 바꾼다. 줄긋기 글자에서 나왔다."""
    for space in (False, True):
        pieces, image, box, steps = spaced_pair("1,445", "1,545", [PERIOD, PERIOD], space_piece=space)
        out, doubtful = restore_number_marks(pieces, image, box, steps)
        assert "".join(char for char, _ in out if char != " ") == "1,4451,545" and len(doubtful) == 2


def test_short_decimal_next_to_a_number_is_not_thousands():
    """10.6 12.3 에서 뒤 수의 숫자까지 세면 3자리로 보여 10,6 이 된다."""
    pieces, image, box, steps = spaced_pair("10.6", "12.3", [COMMA, COMMA], drops={0: 2})
    out, doubtful = restore_number_marks(pieces, image, box, steps)
    assert "".join(char for char, _ in out) == "10.612.3" and len(doubtful) == 2


def test_next_line_below_the_box_is_not_a_mark():
    """상자 아래를 살필 때 다음 줄 글자 윗부분이 구두점 자리에 걸린다. 4K 화면의 DOI 줄에서 4.400 이 4,400 이 됐다."""
    pieces, image, box, steps = line("4.400", [PERIOD], tail=8)
    image = image.copy()
    image[box[3] + 4:box[3] + 7, 6:18] = BLACK      # 숫자 바닥선에서 떨어진 다음 줄 글자
    assert restore_number_marks(pieces, image, box, steps) == (pieces, ())


TINY_TICK = ["#", "#"]


def test_small_font_tick_with_short_tail_is_a_decimal():
    """바탕 9pt 비트맵: 숫자 높이 9의 세로 2화소가 바닥선 아래로 1화소 내려온다. 쉼표 뒤가 3자리가 아니면 소수점이다."""
    assert run("5,9", [TINY_TICK], drops={0: 1})[0] == "5.9"


def test_small_font_tick_before_three_digits_stays():
    """같은 모양이어도 뒤가 3자리면 글자로 판단할 수 없다. 작은 글씨의 쉼표일 수 있다."""
    assert run("3,852", [TINY_TICK], drops={0: 1})[0] == "3,852"


def missing_mark(text, shape, drop=0):
    """모델이 구두점을 건너뛴 줄: 화면에는 있는데 pieces에는 없다."""
    pieces, image, box, steps = line(text, [shape], drops={0: drop})
    return [piece for piece in pieces if piece[0] not in ",."], image, box, steps


def test_decimal_the_model_skipped_comes_back():
    """5.2 가 52 로 읽히면 수가 열 배가 된다."""
    pieces, image, box, steps = missing_mark("5.2", PERIOD)
    assert "".join(char for char, _ in restore_number_marks(pieces, image, box, steps)[0]) == "5.2"


def test_comma_the_model_skipped_comes_back():
    pieces, image, box, steps = missing_mark("4,100", COMMA, drop=2)
    assert "".join(char for char, _ in restore_number_marks(pieces, image, box, steps)[0]) == "4,100"


def test_digit_without_a_mark_between_gets_nothing():
    pieces, image, box, steps = line("52", [])
    assert restore_number_marks(pieces, image, box, steps) == (pieces, ())


def test_faint_speck_between_digits_is_not_a_mark():
    """스캔본의 옅은 티끌을 소수점으로 읽으면 수가 바뀐다."""
    pieces, image, box, steps = line("52", [])
    image = image.copy()
    image[TOP + DIGIT_H - 1, 8] = 190
    assert restore_number_marks(pieces, image, box, steps) == (pieces, ())


def test_piece_of_a_digit_is_not_a_mark():
    """숫자 획이 끊겨 떨어진 조각은 위쪽 열이 비어 있지 않다."""
    pieces, image, box, steps = line("52", [])
    image = image.copy()
    image[TOP + DIGIT_H - 1, 8] = 0        # 숫자 사이 바닥선의 점 하나
    image[TOP + 1:TOP + 4, 8] = 0          # 같은 열 위쪽에 글자 획이 있다
    assert restore_number_marks(pieces, image, box, steps) == (pieces, ())


def test_mark_touching_the_digit_corner_is_still_seen():
    """비트맵 글꼴의 점은 앞 숫자 끝에 대각선으로 닿아 숫자와 한 덩어리가 된다(바탕 9pt 의 5.9)."""
    image = np.full((18, 24, 3), WHITE, np.uint8)
    # 숫자 5: 오른쪽 획 끝이 (11, 7), 점은 (12, 8)과 (13, 8)
    image[3, 3:8] = INK
    image[3:8, 3] = INK
    image[7, 3:7] = INK
    image[8:12, 7] = INK
    image[12, 3:7] = INK
    image[12:14, 8] = INK
    image[3:13, 11:16] = INK                    # 숫자 9
    image[4:12, 12:15] = WHITE
    pieces = [("5", 5.0), (",", 8.0), ("9", 13.0)]
    out, _ = restore_number_marks(pieces, image, (0, 0, 24, 13), 24)
    assert "".join(char for char, _ in out) == "5.9"


def test_foot_of_a_digit_is_not_a_skipped_mark():
    """글자 사이를 재는 규칙이 숫자의 받침 획을 쉼표로 보면 2025 가 2,025 가 된다."""
    image = np.full((18, 30, 3), WHITE, np.uint8)
    image[3:13, 3:8] = INK                      # 숫자
    image[4:12, 4:7] = WHITE
    image[3:13, 13] = INK                       # '1'의 줄기
    image[12, 10:17] = INK                      # '1'의 받침이 왼쪽으로 뻗었다
    pieces = [("0", 5.0), ("1", 13.0)]
    assert restore_number_marks(pieces, image, (0, 0, 30, 13), 30) == (pieces, ())


def test_second_point_is_never_added():
    """수 하나에 소수점은 하나다. 0.092 가 0.0.92 로 나왔다."""
    pieces, image, box, steps = line("0.092", [PERIOD])
    image = image.copy()
    x = int(pieces[3][1]) + 3
    image[TOP + DIGIT_H - 1, x] = 0        # 숫자 끊긴 획이 바닥선에 떨어져 있다
    assert restore_number_marks(pieces, image, box, steps) == (pieces, ())
