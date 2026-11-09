"""화면 글자 따기: '[' ']'로 읽힌 조각의 화면 모양이 낫표면 「 」로 바꾼다.

모델 사전에 낫표가 없어 공문서의 법령명 표기가 [ ]로 읽힌다. 낫표는 줄 글자 높이의 절반쯤이고 위(「)나 아래(」)에
붙어 있으며 ┌ ┘ 꺾임 한 번뿐이라 위아래 획이 모두 있는 [ ]와 모양으로 갈린다. 애매하면 바꾸지 않는다.
겹낫표 『 』(2026-11-09)는 속이 빈 테두리 꺾임이거나 꺾임 획이 줄 글자 획보다 두껍다. 모델이 건너뛰거나 닮은 글자로
읽은 낫표·겹낫표는 그 자리 덩어리가 다른 글자의 몫이 아니고 꺾임 하나일 때만 넣거나 바꾼다.
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


def test_line_without_corners_is_returned_untouched():
    # 건너뛴 낫표를 찾느라 괄호 조각이 없는 줄도 화면을 본다(2026-11-09). 바꿀 것이 없으면 받은 목록 그대로다
    image = canvas()
    for x in (22, 36):
        draw_syllable(image, x)
    pieces = [("가", 27.0), ("나", 41.0)]
    assert restore_corner_brackets(pieces, image, image.shape[1], image.shape[1]) is pieces


def test_no_pieces_are_returned_untouched_without_looking_at_the_image():
    assert restore_corner_brackets([], None, 10, 100) == []


@pytest.mark.parametrize("image, width", [(canvas(), 160), (np.zeros((0, 0, 3), np.uint8), 0)])
def test_blank_or_empty_crop_is_safe(image, width):
    assert restore_corner_brackets([("[", 3.0)], image, 40, width) == [("[", 3.0)]


# ── 겹낫표 『 』(2026-11-09) ──
def draw_double_open(image, x, top=TOP, size=11, width=8):
    """『 모양: ┌ 테두리(바깥 선과 안쪽 선 사이가 1화소 빈 겹꺾임)."""
    image[top, x:x + width] = 0                  # 바깥 가로획
    image[top:top + size, x] = 0                 # 바깥 세로획
    image[top + 2, x + 2:x + width] = 0          # 안쪽 가로획
    image[top + 2:top + size, x + 2] = 0         # 안쪽 세로획
    image[top:top + 3, x + width - 1] = 0        # 가로획 끝을 닫는다
    image[top + size - 1, x:x + 3] = 0           # 세로획 끝을 닫는다


def draw_double_close(image, x, bottom=BOTTOM, size=11, width=8):
    """』 모양: 『를 180도 돌린 것."""
    patch = np.full((size, width, 3), 255, np.uint8)
    draw_double_open(patch, 0, 0, size, width)
    image[bottom - size:bottom, x:x + width] = np.minimum(image[bottom - size:bottom, x:x + width], patch[::-1, ::-1])


def draw_thick_open(image, x, top=TOP, size=10, width=7, arm=4, stem=4):
    """속이 메워진 『: 작은 글씨에서는 겹꺾임의 틈이 메워져 꺾임 획만 두껍다."""
    image[top:top + arm, x:x + width] = 0
    image[top:top + size, x:x + stem] = 0


def draw_thick_close(image, x, bottom=BOTTOM, size=10, width=7, arm=4, stem=4):
    patch = np.full((size, width, 3), 255, np.uint8)
    draw_thick_open(patch, 0, 0, size, width, arm, stem)
    image[bottom - size:bottom, x:x + width] = np.minimum(image[bottom - size:bottom, x:x + width], patch[::-1, ::-1])


def test_hollow_corners_read_as_square_brackets_become_double_nakpyo():
    # 『 』는 사전에 없어 [ ]로 읽히고 낫표 규칙이 「 」로 바꿨다(새 평가 자료 1,806개 중 맞은 것 0)
    image = line(draw_double_open, draw_double_close)
    assert "".join(c for c, _ in restore(image, *PIECES)) == "『가나다』라"


def test_corners_twice_as_thick_as_the_text_strokes_become_double_nakpyo():
    # 작은 글씨의 『 』는 틈이 메워져 속이 찬다. 가로획이 글자 가로획의 2배, 세로획이 1.5배 이상이면 겹낫표다
    image = line(draw_thick_open, draw_thick_close)
    assert "".join(c for c, _ in restore(image, *PIECES)) == "『가나다』라"


def test_thick_corner_in_bold_text_stays_single():
    # 굵은 글씨는 글자 획도 두꺼워 낫표 획이 두꺼워도 겹낫표가 아니다
    image = canvas()
    draw_thick_open(image, 10, stem=3)
    for x in (22, 36, 50, 76):
        image[TOP:BOTTOM, x:x + 3] = 0
        image[TOP:BOTTOM, x + 8:x + 11] = 0
        image[10:13, x:x + 11] = 0
    draw_thick_close(image, 64, stem=3)
    assert "".join(c for c, _ in restore(image, *PIECES)) == "「가나다」라"


def test_tall_hollow_corner_read_as_square_bracket_becomes_double_nakpyo():
    # 휴먼명조의 괄호는 줄 높이의 0.75~0.9배라 덩어리 판정의 높이 상한에 걸렸다(휴먼명조 『 』 144개 중 0)
    image = line(lambda im, x: draw_double_open(im, x, TOP, 19), lambda im, x: draw_double_close(im, x, BOTTOM, 19))
    assert "".join(c for c, _ in restore(image, *PIECES)) == "『가나다』라"


def test_small_lens_bracket_with_a_widening_end_is_not_a_tall_double():
    # 작은 렌즈 괄호 】는 줄 높이만큼 길고 두꺼운 꺾임처럼 보이지만 세로획 끝이 다시 넓어진다(엑셀 표 '개선】' → 』)
    image = canvas()
    for x in (22, 36, 50):
        draw_syllable(image, x)
    for row, run in enumerate([3, 3] + [2] * 14 + [3, 3, 4, 4]):
        image[TOP + row, 70 - run:70] = 0
    pieces = [("가", 27.0), ("나", 41.0), ("다", 55.0), ("]", 68.0)]
    assert "".join(c for c, _ in restore(image, *pieces)) == "가나다]"


def draw_soft_open(image, x, top=TOP, size=11, width=8, value=128):
    """번지게 그린 『: 글꼴을 넣은 PDF에서는 두 줄과 틈이 옅은 한 획으로 메워진다(가로획 2줄, 세로획 3열)."""
    image[top:top + 2, x:x + width] = value
    image[top:top + size, x:x + 3] = value


def draw_soft_close(image, x, bottom=BOTTOM, size=11, width=8, value=128):
    patch = np.full((size, width, 3), 255, np.uint8)
    draw_soft_open(patch, 0, 0, size, width, value)
    image[bottom - size:bottom, x:x + width] = np.minimum(image[bottom - size:bottom, x:x + width], patch[::-1, ::-1])


def test_faint_wide_corners_in_sharp_text_become_double_nakpyo():
    # 맑은 고딕을 넣은 PDF의 『 』는 틈이 메워져 굵기로는 「 」와 같았다. 획이 본문보다 옅고 넓게 퍼지면 겹낫표다
    image = line(draw_soft_open, draw_soft_close)
    assert "".join(c for c, _ in restore(image, *PIECES)) == "『가나다』라"


def test_faint_wide_corners_in_blurred_text_stay_single():
    # 스캔·JPEG처럼 본문까지 번진 줄은 「도 옅고 넓다(거짓 겹낫표 37곳). 본문 획이 또렷한 줄에서만 회색 농도로 본다
    image = canvas()
    draw_soft_open(image, 10)
    for x in (22, 36, 50, 76):
        image[TOP:BOTTOM, x:x + 3] = 128
        image[TOP:BOTTOM, x + 8:x + 11] = 128
        image[11:13, x:x + 11] = 128
    draw_soft_close(image, 64)
    assert "".join(c for c, _ in restore(image, *PIECES)) == "「가나다」라"


# ── 모델이 건너뛰거나 닮은 글자로 읽은 낫표(2026-11-09) ──
def test_corners_read_as_quote_and_comma_become_nakpyo():
    # 「를 '·‘·r, 」를 ,·ㅣ로 읽은 자리가 남은 낫표의 큰 몫이었다. 모양이 꺾임 하나면 방향은 모양으로 정한다
    pieces = [("‘", 12.0), ("가", 27.0), ("나", 41.0), ("다", 55.0), (",", 66.0), ("라", 81.0)]
    assert "".join(c for c, _ in restore(line(draw_open, draw_close), *pieces)) == "「가나다」라"


def test_hollow_corners_read_as_letters_become_double_nakpyo():
    # 『를 F·P·°, 』를 ¶·s로 읽었다
    pieces = [("F", 13.0), ("가", 27.0), ("나", 41.0), ("다", 55.0), ("¶", 67.0), ("라", 81.0)]
    assert "".join(c for c, _ in restore(line(draw_double_open, draw_double_close), *pieces)) == "『가나다』라"


def test_ctc_position_a_few_pixels_left_of_the_corner_still_owns_it():
    # CTC 위치가 괄호에서 2~3화소 왼쪽에 찍히곤 했다. 덩어리에 가장 가까운 조각이면 그 조각의 몫이다
    pieces = [("'", 7.0), ("가", 27.0), ("나", 41.0), ("다", 55.0), (",", 62.0), ("라", 81.0)]
    assert "".join(c for c, _ in restore(line(draw_open, draw_close), *pieces)) == "「가나다」라"


def test_real_quote_and_comma_stay():
    image = canvas()
    for x in (22, 36, 50, 76):
        draw_syllable(image, x)
    image[TOP:TOP + 5, 14:16] = 0          # ' : 줄 윗변의 짧은 표시
    image[BOTTOM - 3:BOTTOM + 1, 65:67] = 0   # , : 아랫변의 짧은 획
    pieces = [("'", 15.0), ("가", 27.0), ("나", 41.0), ("다", 55.0), (",", 66.0), ("라", 81.0)]
    assert restore(image, *pieces) == pieces


def test_skipped_corners_are_put_back_where_they_are_drawn():
    # 모델이 아예 읽지 않은 낫표가 남은 낫표의 약 100자리였다
    out = restore(line(draw_open, draw_close), ("가", 27.0), ("나", 41.0), ("다", 55.0), ("라", 81.0))
    assert "".join(c for c, _ in out) == "「가나다」라"
    assert [round(p) for c, p in out if c in "「」"] == [13, 67]


def test_skipped_hollow_corners_are_put_back_as_double_nakpyo():
    out = restore(line(draw_double_open, draw_double_close), ("가", 27.0), ("나", 41.0), ("다", 55.0), ("라", 81.0))
    assert "".join(c for c, _ in out) == "『가나다』라"


def test_corner_already_read_off_center_is_not_put_back_twice():
    # [ 의 CTC 위치가 이웃 글자에 더 가까우면 괄호 덩어리가 어느 조각에도 묶이지 않아 「「하수도법」이 됐다
    pieces = [("[", 19.0), ("가", 27.0), ("나", 41.0), ("다", 55.0), ("]", 61.0), ("라", 81.0)]
    assert "".join(c for c, _ in restore(line(draw_open, draw_close), *pieces)) == "「가나다」라"


def test_vowel_stroke_with_a_side_tick_is_not_taken_for_a_skipped_corner():
    # '가'의 'ㅏ'처럼 세로획에 짧은 곁가지만 있는 획은 맨 윗줄이 폭을 덮지 못한다((가칭) 앞에 「가 끼어들었다)
    image = canvas()
    for x in (10, 36, 50):
        draw_syllable(image, x)
    image[TOP:TOP + 12, 26:29] = 0         # ㅏ의 세로획(줄 윗변에 붙음)
    image[TOP + 4:TOP + 6, 29:32] = 0      # 곁가지(세로획 가운데보다 위)
    pieces = [("가", 15.0), ("나", 41.0), ("다", 55.0)]
    assert restore(image, *pieces) == pieces


def test_small_solid_wedge_is_not_taken_for_a_skipped_corner():
    # 표 칸 글머리 조각(4×4 삼각, 줄 높이 10)이 꺾임처럼 보여 』가 끼어들었다. 속이 찬 꺾임은 안쪽이 있어야 한다
    image = canvas()
    for x in (10, 36):                     # 줄 높이 10의 글자
        image[12:22, x:x + 2] = 0
        image[12:22, x + 8:x + 10] = 0
        image[16:18, x:x + 10] = 0
    for row, run in enumerate([1, 2, 3, 4]):   # ◢: 오른쪽 아래가 찬 삼각
        image[18 + row, 28 - run:28] = 0
    pieces = [("가", 15.0), ("나", 41.0)]
    assert restore(image, *pieces) == pieces


def test_shadow_of_a_box_bullet_is_not_taken_for_a_closing_corner():
    # 글머리 ❏의 그림자는 ┘ 모양이고 네모 테두리는 그림자보다 훨씬 옅다. 꺾임 안쪽에 옅은 네모가 있으면 낫표가 아니다
    image = canvas()
    for x in (36, 50):
        draw_syllable(image, x)
    image[8:20, 12:13] = 215               # 옅은 네모 테두리
    image[8, 12:24] = 215
    image[8:20, 23:24] = 215
    image[19, 12:24] = 215
    image[10:21, 24:26] = 0                # 진한 그림자(┘)
    image[20:22, 14:26] = 0
    pieces = [("나", 41.0), ("다", 55.0)]
    assert restore(image, *pieces) == pieces


def test_capital_p_above_a_table_line_stays():
    # 상자 아래에 표 선이 걸리면 줄 높이가 늘어 'P'가 위에 붙은 꺾임처럼 보였다(PA → 『A). 표 선 행은 줄 높이에서 뺀다
    image = np.full((32, 120, 3), 255, np.uint8)
    for x in (30, 44):
        draw_syllable(image, x)
    image[4:BOTTOM, 10:12] = 0             # P의 세로획
    image[4:6, 10:17] = 0                  # 고리 위
    image[11:13, 10:17] = 0                # 고리 아래
    image[4:13, 15:17] = 0                 # 고리 오른쪽
    image[31, :] = 0                       # 표 선
    pieces = [("P", 13.0), ("가", 35.0), ("나", 49.0)]
    assert restore_corner_brackets(pieces, image, 120, 120) == pieces


def test_corner_between_digits_stays():
    # 2,100의 쉼표처럼 숫자 사이나 영문자 사이에는 낫표가 오지 않는다(흐린 스캔의 쉼표가 「로 바뀌었다)
    image = canvas()
    for x in (22, 76):
        draw_syllable(image, x)
    draw_open(image, 40)
    pieces = [("2", 27.0), (",", 43.0), ("1", 81.0)]
    assert restore(image, *pieces) == pieces


# ── 실제 모델: Qt로 그린 줄 ──
def render_line(text, pixel_size, width=900, family="Malgun Gothic"):
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


def read(ocr, text, pixel_size, family="Malgun Gothic"):
    return " ".join(b.text for b in sorted(ocr.recognize(render_line(text, pixel_size, family=family)), key=lambda b: b.x))


def need_font(qapp, family):
    """휴먼명조(한글 프로그램)·바탕은 PC에 따라 없다. 없으면 그 경우만 건너뛴다."""
    from PySide6.QtGui import QFontDatabase
    if family not in QFontDatabase.families():
        pytest.skip(f"{family} 글꼴 없음")


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


@pytest.mark.parametrize("family, pixel_size", [("Malgun Gothic", 20), ("Malgun Gothic", 24), ("휴먼명조", 16),
                                                ("휴먼명조", 24), ("Batang", 16), ("Batang", 20)])
def test_real_model_reads_double_nakpyo_in_a_report_title(qapp, ocr, family, pixel_size):
    # 보고서·책 이름의 『 』는 사전에 없어 「 」·F·'로 읽히거나 빠졌다(2026-11-09)
    need_font(qapp, family)
    found = read(ocr, "『2050 탄소중립 시나리오』에 따르면", pixel_size, family)
    assert "『2050" in found and "시나리오』" in found, found


@pytest.mark.parametrize("family, pixel_size", [("Malgun Gothic", 16), ("Malgun Gothic", 20), ("Malgun Gothic", 24),
                                                ("휴먼명조", 14), ("휴먼명조", 16), ("휴먼명조", 20), ("휴먼명조", 24)])
def test_real_model_keeps_law_name_nakpyo_single(qapp, ocr, family, pixel_size):
    # 휴먼명조 24px의 「는 가로획이 한글 가로획의 2배라 겹낫표로 잘못 바뀌었다(속이 찬 꺾임은 높이 13화소 이하만 본다)
    need_font(qapp, family)
    found = read(ocr, "'24년 「물환경보전법」 개정", pixel_size, family)
    assert "『" not in found and "』" not in found and "보전법」" in found, found


def test_engine_calls_ctc_decode_once_per_box_with_brackets(qapp, ocr, monkeypatch):
    calls = []
    real = engine.ctc_decode
    monkeypatch.setattr(engine, "ctc_decode", lambda probs, charset: calls.append(1) or real(probs, charset))
    boxes = ocr.recognize(render_line("관계부처 합동 [국가 기술사업화 전략] 수립", 20))
    assert boxes and len(calls) == len(boxes)
