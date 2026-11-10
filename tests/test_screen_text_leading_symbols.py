"""화면 글자 따기: 줄 맨 앞 글머리 기호(■ □ ◇ ㅇ)를 모양으로 알아본다.

인식 모델은 공문서의 글머리 기호를 거의 읽지 못한다(■ 94%, □ 100%, ㅇ 55% 누락). 줄 맨 앞의 글자 높이보다
작은 덩어리를 모양(속이 찬 정사각/속이 빈 정사각/마름모/고리)으로 분류해 판독 결과에 붙이거나 교체한다.
고리 모양은 ㅇ ◦ ○ o 를 구별할 수 없으므로 'ㅇ'으로 내되 확인 필요로 표시한다.
"""
import numpy as np
import pytest

import screen_text.leading_symbols as symbols

HEIGHT, TEXT_TOP, TEXT_BOTTOM = 22, 1, 21   # 글자(한글 음절 모양 막대) 높이 20


def glyph(kind, n):
    yy, xx = np.mgrid[0:n, 0:n]
    c = (n - 1) / 2
    if kind == "filled":
        return np.ones((n, n), bool)
    if kind == "hollow":
        mask = np.zeros((n, n), bool)
        t = max(2, n // 8)
        mask[:t] = mask[-t:] = True
        mask[:, :t] = mask[:, -t:] = True
        return mask
    if kind == "thin":                  # 획이 1px인 속이 빈 정사각: 모서리 칸이 얼마 안 찬다
        mask = np.zeros((n, n), bool)
        mask[0] = mask[-1] = True
        mask[:, 0] = mask[:, -1] = True
        return mask
    if kind == "ring":
        r = np.hypot(yy - c, xx - c)
        return (r <= n / 2) & (r > n / 2 - 2.0)
    if kind == "diamond":
        d = np.abs(yy - c) + np.abs(xx - c)
        return (d <= n / 2) & (d > n / 2 - 2)
    raise ValueError(kind)


def draw_text_block(image, x):
    """한글 음절처럼 획이 있는 11×20 블록(속이 꽉 찬 막대가 아니다)."""
    image[TEXT_TOP:TEXT_BOTTOM, x:x + 2] = 0
    image[TEXT_TOP:TEXT_BOTTOM, x + 9:x + 11] = 0
    image[9:11, x:x + 11] = 0


def line_image(kind=None, size=0, gap=10, rule=False, text_blocks=3):
    """[세로 테두리] [기호] [간격] [글자 막대 여러 개]를 가진 흰 바탕 한 줄. (이미지, 글자 시작 x, 끝 x)를 돌려준다."""
    image = np.full((HEIGHT, 120, 3), 255, np.uint8)
    x = 4
    if rule:
        image[:, 2:4] = 0
        x = 8
    if kind:
        top = (HEIGHT - size) // 2
        image[top:top + size, x:x + size][glyph(kind, size)] = 0
        x += size + gap
    text_left = x
    for _ in range(text_blocks):
        draw_text_block(image, x)
        x += 13
    return image, text_left, x


def outside_box(image, text_left, end):
    return [(text_left, 0, end, HEIGHT)]


def disc(size, sub=8):
    """지름 size인 둥근 점을 화소마다 덮인 비율(0~1)로. 실제 화면처럼 가장자리 화소는 옅다."""
    yy, xx = (np.mgrid[0:size * sub, 0:size * sub] + .5) / sub
    c = size / 2
    inside = (yy - c) ** 2 + (xx - c) ** 2 <= c * c
    return inside.reshape(size, sub, size, sub).mean(axis=(1, 3))


# JPEG로 꼭짓점이 메워진 둥근 점: 꼭짓점도 글자 픽셀 문턱(가장 진한 값의 0.3)을 넘어 글자 픽셀로는 꽉 찬 네모다
FILLED_ROUND_4 = np.array([[.4, .9, .9, .4], [.9, 1, 1, .9], [.9, 1, 1, .9], [.4, .9, .9, .4]])
FILLED_ROUND_5 = np.array([[.4, .9, 1, .9, .4], [.9, 1, 1, 1, .9], [1, 1, 1, 1, 1], [.9, 1, 1, 1, .9], [.4, .9, 1, .9, .4]])


def bullet_line(coverage, gap=10, top=None):
    """[회색 기호] [간격] [글자 막대 셋]. coverage는 화소마다 덮인 비율이다. (이미지, 글자 시작 x, 끝 x)."""
    image = np.full((HEIGHT, 120, 3), 255, np.uint8)
    rows, columns = coverage.shape
    top = (HEIGHT - rows) // 2 if top is None else top
    shade = np.round(255 * (1 - np.asarray(coverage, float))).astype(np.uint8)
    image[top:top + rows, 4:4 + columns] = np.minimum(image[top:top + rows, 4:4 + columns], shade[..., None])
    x = 4 + columns + gap
    left = x
    for _ in range(3):
        draw_text_block(image, x)
        x += 13
    return image, left, x


@pytest.mark.parametrize("kind, size, expected", [
    ("filled", 8, "■"),      # 속이 찬 정사각(작음)
    ("hollow", 16, "□"),     # 속이 빈 정사각(글자 높이에 가까움)
    ("diamond", 20, "◇"),    # 속이 빈 마름모: 모서리가 비어 있다
    ("ring", 11, "ㅇ"),      # 고리(글자 높이의 절반 안팎)
    ("ring", 13, "ㅇ"),      # 100% 배율의 고리는 글자 높이의 0.65배까지 나온다
    ("ring", 18, "○"),       # 글자만큼 큰 고리: 자모 ㅇ보다 크다. 크기로 정사각이라 하면 안 된다(실제 문서에서 □로 나왔다)
    ("ring", 20, "○"),
    ("thin", 12, "□"),       # 작아도 네 꼭짓점이 차 있으면 정사각이다
    ("thin", 20, "□"),       # 획이 얇은 큰 정사각도 마찬가지다
])
def test_symbol_left_of_the_box_is_classified_by_shape(kind, size, expected):
    image, left, end = line_image(kind, size)
    found = symbols.leading_symbol(image, 0, outside_box(image, left, end))
    assert found is not None and found[0] == expected, found


def test_symbol_inside_the_box_is_also_found():
    image, left, end = line_image("filled", 8)
    assert symbols.leading_symbol(image, 0, [(0, 0, end, HEIGHT)])[0] == "■"


def test_no_symbol_when_the_line_starts_with_text():
    image, left, end = line_image(None)
    assert symbols.leading_symbol(image, 0, [(left, 0, end, HEIGHT)]) is None


@pytest.mark.parametrize("size, gap", [(8, 0), (10, 1)])
def test_symbol_touching_the_text_is_not_a_bullet(size, gap):
    # 틈 없이 붙었거나, 줄 높이의 0.42배보다 큰데 1px만 떨어졌으면 글자의 일부일 수 있다
    image, left, end = line_image("filled", size, gap=gap)
    assert symbols.leading_symbol(image, 0, [(0, 0, end, HEIGHT)]) is None


def test_square_bullet_one_pixel_before_the_text_is_found():
    # 100% 배율 공문서의 ▪는 뒤 글자와 1px만 떨어진다(모양 조건을 다 통과하고 간격만 모자란 덩어리 53개 중 50개가 ▪)
    image, left, end = line_image("filled", 6, gap=1)
    assert symbols.leading_symbol(image, 0, [(0, 0, end, HEIGHT)])[0] == "■"


def test_tall_hollow_shape_is_not_a_symbol():
    image = np.full((HEIGHT, 60, 3), 255, np.uint8)
    image[TEXT_TOP:TEXT_BOTTOM, 4:14] = 0
    image[TEXT_TOP + 3:TEXT_BOTTOM - 3, 6:12] = 255          # 속이 빈 세로 직사각형(글자 모양)
    draw_text_block(image, 26)
    assert symbols.leading_symbol(image, 0, [(0, 0, 50, HEIGHT)]) is None


def test_small_round_bullet_is_not_taken_for_a_filled_square():
    # 4px 둥근 글머리 •는 꼭짓점 화소가 옅다. 크기가 아니라 이 모양으로 ▪와 가른다
    image, left, end = bullet_line(disc(4))
    assert symbols.leading_symbol(image, 0, [(left, 0, end, HEIGHT)])[0] == "•"
    assert symbols.apply_leading_symbols(image, outside_box(image, left, end), [("· 선정평가", 0.9)]) == [("• 선정평가", 0.9, 0)]
    assert symbols.apply_leading_symbols(image, outside_box(image, left, end), [("• 선정평가", 0.9)]) == [("• 선정평가", 0.9, 0)]


@pytest.mark.parametrize("size", [3, 4])
def test_small_crisp_square_is_a_square_bullet(size):
    # 크기로는 •와 ▪를 가를 수 없다(둘 다 줄 글자 높이의 0.17~0.40배). 네 꼭짓점까지 고르게 진한 작은 네모는 ▪다
    image, left, end = line_image("filled", size)
    assert symbols.leading_symbol(image, 0, outside_box(image, left, end))[0] == "■"


@pytest.mark.parametrize("size", [5, 6, 7])
def test_round_bullet_larger_than_a_fifth_of_the_line_is_a_dot(size):
    # 엣지·한글·스캔의 •는 줄 글자 높이의 0.25~0.36배다. 예전 상한 0.22배에 걸려 모델이 읽은 '·'가 남았다
    image, left, end = bullet_line(disc(size))
    assert symbols.leading_symbol(image, 0, outside_box(image, left, end))[0] == "•"
    assert symbols.apply_leading_symbols(image, outside_box(image, left, end), [("·슈퍼컴퓨터 소개", 0.9)]) == [("• 슈퍼컴퓨터 소개", 0.9, 0)]


def test_round_bullet_whose_pixels_fill_the_box_is_not_a_square():
    # JPEG로 꼭짓점이 메워져 글자 픽셀로는 꽉 찬 네모인 •. 꼭짓점이 변보다 훨씬 옅어 둥글다(예전에는 ■로 바꿨다)
    image, left, end = bullet_line(FILLED_ROUND_5)
    assert symbols.leading_symbol(image, 0, outside_box(image, left, end))[0] == "•"
    assert symbols.apply_leading_symbols(image, outside_box(image, left, end), [("• 분야별, 지역별", 0.9)]) == [("• 분야별, 지역별", 0.9, 0)]


def test_blurred_small_dot_is_not_taken_for_a_square():
    # 흐린 스캔에서 번진 작은 점은 가로·세로로 나뉘는 모양이라 꼭짓점만 보면 네모다. 속이 고르게 진하지 않으므로 ▪가 아니다
    profile = np.array([.4, .95, .95, .4])
    image, left, end = bullet_line(np.outer(profile, profile))
    assert symbols.leading_symbol(image, 0, outside_box(image, left, end))[0] == "•"


def test_dot_one_pixel_before_the_text_is_found_when_the_model_read_a_dot():
    # 모델이 그 자리를 점 글자로 읽었으면 기호가 따로 있다. 뒤 글자와 1px만 떨어진 •도 찾는다
    image, left, end = bullet_line(disc(5), gap=1)
    box = [(0, 0, end, HEIGHT)]
    assert symbols.leading_symbol(image, 0, box) is None
    assert symbols.leading_symbol(image, 0, box, loose=True)[0] == "•"
    assert symbols.apply_leading_symbols(image, box, [("·영상자료 제출 시", 0.9)]) == [("• 영상자료 제출 시", 0.9, 0)]


@pytest.mark.parametrize("read", ["- 교육평가: 만족도 조사", "* 기상예보 AtoZ"])
def test_dash_or_star_the_model_read_over_a_dot_shaped_blob_is_kept(read):
    # 흐린 스캔에서 짧은 '-'와 '*'는 볼록한 덩어리가 되어 점처럼 보인다. 모델이 읽은 글자가 맞다('• * 기상예보'가 됐다)
    image, left, end = bullet_line(FILLED_ROUND_4)
    box = [(0, 0, end, HEIGHT)]
    assert symbols.leading_symbol(image, 0, box)[0] == "•"
    assert symbols.apply_leading_symbols(image, box, [(read, 0.9)]) == [(read, 0.9, 0)]


def test_star_is_not_a_round_dot():
    # 별표는 반 진하기에서 팔 사이가 비어 끊긴다
    star = np.array([[1, 0, 1, 0, 1], [0, 1, 1, 1, 0], [1, 1, 1, 1, 1], [0, 1, 1, 1, 0], [1, 0, 1, 0, 1]], float)
    image, left, end = bullet_line(star)
    found = symbols.leading_symbol(image, 0, outside_box(image, left, end))
    assert found is None or found[0] != "•"


def test_small_square_period_below_the_middle_is_not_a_bullet():
    # 'Ⅲ.'의 네모난 마침표: 세로획은 표 선처럼 건너뛰고 줄 아래의 작은 네모가 첫 덩어리가 된다
    image, left, end = bullet_line(np.ones((3, 3)), top=17)
    assert symbols.leading_symbol(image, 0, outside_box(image, left, end)) is None


def test_colored_badge_with_letters_is_not_taken_for_a_filled_square():
    # 색 배지(수정·보기)는 통째로 글자 픽셀로 잡힌다. 글자 구멍 때문에 채움이 0.95 이하이고 진짜 ■ ▪는 0.98 이상이다
    image, left, end = line_image("filled", 18)
    image[8:12, 8:16] = 255
    assert symbols.leading_symbol(image, 0, [(left, 0, end, HEIGHT)]) is None


def test_part_of_a_tall_colored_badge_cut_by_the_box_is_not_a_symbol():
    # 줄 왼쪽의 색 배지·그림은 글자 줄보다 커서 상자 높이로 잘리면 꽉 찬 네모처럼 보인다(실제 문서에서 없는 ■ 45개)
    image = np.full((44, 120, 3), 255, np.uint8)
    image[4:40, 4:26] = (240, 150, 120)                          # 상자 위아래로 이어지는 배지
    for x in (40, 53, 66):
        image[12:32, x:x + 2] = image[12:32, x + 9:x + 11] = 0
        image[20:22, x:x + 11] = 0
    boxes = [(38, 11, 79, 33)]
    assert symbols.leading_symbol(image, 0, boxes) is None
    assert symbols.apply_leading_symbols(image, boxes, [("대출 신청", 0.9)]) == [("대출 신청", 0.9, 0)]


def test_real_symbol_touching_the_box_edge_is_still_found():
    # 상자가 기호에 딱 맞아 경계에 닿아도 그 밖이 비어 있으면 온전한 기호다
    image = np.full((44, 120, 3), 255, np.uint8)
    image[14:30, 4:20] = 0
    for x in (40, 53, 66):
        image[12:32, x:x + 2] = image[12:32, x + 9:x + 11] = 0
        image[20:22, x:x + 11] = 0
    assert symbols.leading_symbol(image, 0, [(2, 14, 79, 30)])[0] == "■"


@pytest.mark.parametrize("rule", [False, True])
def test_symbol_whose_last_rows_fall_outside_the_box_is_still_found(rule):
    # 상자가 기호의 끝 한 줄을 잘라도(실제 양식에서 □가 사라졌다), 바로 아래 표 선이 있어도 기호다. 배지는 한참 더 이어진다
    image = np.full((44, 120, 3), 255, np.uint8)
    image[12:30, 4:22][glyph("hollow", 18)] = 0
    if rule:
        image[30:32, :] = 0
    for x in (40, 53, 66):
        image[12:29, x:x + 2] = image[12:29, x + 9:x + 11] = 0
        image[20:22, x:x + 11] = 0
    assert symbols.leading_symbol(image, 0, [(38, 12, 79, 29)])[0] == "□"


def test_vertical_table_rule_before_the_bullet_is_skipped():
    image, left, end = line_image("filled", 8, rule=True)
    assert symbols.leading_symbol(image, 0, outside_box(image, left, end))[0] == "■"


def test_symbol_belonging_to_the_left_neighbor_box_is_not_claimed():
    image = np.full((HEIGHT, 140, 3), 255, np.uint8)
    image[7:15, 4:12] = 0                                    # 왼쪽 칸의 기호
    draw_text_block(image, 22)                               # 왼쪽 칸의 글자
    draw_text_block(image, 60)                               # 오른쪽 칸의 글자(기호 없음)
    draw_text_block(image, 73)
    boxes = [(22, 0, 34, HEIGHT), (60, 0, 85, HEIGHT)]
    assert symbols.leading_symbol(image, 1, boxes) is None
    assert symbols.leading_symbol(image, 0, boxes)[0] == "■"


# ── 판독 결과에 반영 ──
def test_misread_symbol_inside_the_box_is_replaced_and_ring_is_flagged():
    image, left, end = line_image("ring", 11)
    assert symbols.apply_leading_symbols(image, [(0, 0, end, HEIGHT)], [("0 연간 배출량", 0.9)]) == [("ㅇ 연간 배출량", 0.9, 1)]


def test_symbol_the_model_skipped_is_prepended():
    image, left, end = line_image("hollow", 16)
    assert symbols.apply_leading_symbols(image, outside_box(image, left, end), [("추진배경", 0.95)]) == [("□ 추진배경", 0.95, 0)]
    image, left, end = line_image("filled", 8)
    assert symbols.apply_leading_symbols(image, [(0, 0, end, HEIGHT)], [("양자 기술", 0.9)]) == [("■ 양자 기술", 0.9, 0)]


def test_only_ring_shapes_are_flagged_for_confirmation():
    for kind, size, flag in (("ring", 11, 1), ("ring", 18, 1), ("filled", 8, 0), ("hollow", 16, 0), ("diamond", 20, 0)):
        image, left, end = line_image(kind, size)
        (_, _, got), = symbols.apply_leading_symbols(image, outside_box(image, left, end), [("본문", 0.9)])
        assert got == flag, kind


def test_results_without_a_symbol_are_unchanged():
    image, left, end = line_image(None)
    assert symbols.apply_leading_symbols(image, [(left, 0, end, HEIGHT)], [("본문 내용", 0.9)]) == [("본문 내용", 0.9, 0)]


def test_empty_text_gets_no_symbol():
    image, left, end = line_image("filled", 8)
    assert symbols.apply_leading_symbols(image, outside_box(image, left, end), [("", 0.0)]) == [("", 0.0, 0)]


# ── 위치 찾기가 기호를 글자와 따로 상자로 자른 경우 (실제 공문서 PDF에서 확인) ──
def separate_symbol_image(kind="ring", size=11):
    """기호 [간격] 글자: 기호만 든 작은 상자와 글자 상자. 글자 시작 x는 24."""
    image = np.full((HEIGHT, 120, 3), 255, np.uint8)
    top = (HEIGHT - size) // 2
    image[top:top + size, 4:4 + size][glyph(kind, size)] = 0
    x = 24
    for _ in range(3):
        draw_text_block(image, x)
        x += 13
    return image, x


def test_symbol_only_box_uses_the_neighbor_text_height_as_reference():
    image, end = separate_symbol_image("ring", 11)
    boxes = [(2, 4, 18, 18), (24, 0, end, HEIGHT)]               # 첫 상자 안에는 고리밖에 없다
    out = symbols.apply_leading_symbols(image, boxes, [("0", 0.3), ("연간 배출량", 0.99)])
    assert out == [("ㅇ", 0.3, 1), ("연간 배출량", 0.99, 0)]      # 글자 높이 대비 크기를 이웃 글자로 잰다(□가 아니다)


def test_symbol_only_box_replaces_whatever_the_model_read():
    image, end = separate_symbol_image("hollow", 16)
    boxes = [(2, 2, 22, 20), (26, 0, end, HEIGHT)]
    (text, score, flag), _ = symbols.apply_leading_symbols(image, boxes, [("ㄱ", 0.2), ("추진배경", 0.99)])
    assert (text, flag) == ("□", 0)


def test_box_overlapping_the_symbol_box_does_not_claim_the_symbol_again():
    image, end = separate_symbol_image("ring", 11)
    boxes = [(2, 4, 30, 18), (24, 0, end, HEIGHT)]               # 앞 상자가 글자 상자의 시작과 겹친다
    out = symbols.apply_leading_symbols(image, boxes, [("0", 0.3), ("연간 배출량", 0.99)])
    assert out == [("ㅇ", 0.3, 1), ("연간 배출량", 0.99, 0)]      # 'ㅇ ㅇ'으로 중복되지 않는다


# ── 모델이 기호만 든 상자를 빈 글자로 읽은 경우(양식의 '□ 시 □ 군 ■ 구'). 그 상자가 왼쪽 탐색을 막으면 기호가 사라진다 ──
def test_symbol_box_the_model_read_as_empty_gives_the_symbol_to_the_next_box():
    image, end = separate_symbol_image("hollow", 12)
    boxes = [(2, 2, 18, 20), (24, 0, end, HEIGHT)]
    out = symbols.apply_leading_symbols(image, boxes, [("", 0.0), ("특별시", 0.99)])
    assert out == [("", 0.0, 0), ("□ 특별시", 0.99, 0)]


def test_box_cut_inside_a_filled_symbol_does_not_hide_it():
    image, end = separate_symbol_image("filled", 12)
    boxes = [(6, 8, 14, 14), (24, 0, end, HEIGHT)]               # 위치 찾기가 ■의 속만 작은 상자로 잘랐다
    out = symbols.apply_leading_symbols(image, boxes, [("", 0.0), ("광역시", 0.99)])
    assert out == [("", 0.0, 0), ("■ 광역시", 0.99, 0)]


def test_empty_read_box_over_a_real_glyph_is_not_taken_for_a_symbol():
    image = np.full((HEIGHT, 120, 3), 255, np.uint8)
    draw_text_block(image, 8)                                    # 모델이 못 읽은 글자
    draw_text_block(image, 34)
    boxes = [(6, 0, 21, HEIGHT), (32, 0, 47, HEIGHT)]
    assert symbols.apply_leading_symbols(image, boxes, [("", 0.0), ("본문", 0.9)]) == [("", 0.0, 0), ("본문", 0.9, 0)]


# ── 한 상자 안에서 모델이 건너뛴 체크박스(양식의 '시 □ 군'). 위치는 CTC 단계(여기서는 4px당 한 단계) ──
def checkbox_line(kind="hollow", size=16, gap=12):
    """[글자] [간격] [체크박스] [간격] [글자] 흰 바탕 한 줄. (이미지, 체크박스 시작 x, 끝 글자 시작 x, 전체 폭)."""
    image = np.full((HEIGHT, 120, 3), 255, np.uint8)
    draw_text_block(image, 2)
    box_left = 13 + gap
    top = (HEIGHT - size) // 2
    image[top:top + size, box_left:box_left + size][glyph(kind, size)] = 0
    right = box_left + size + gap
    draw_text_block(image, right)
    return image, box_left, right, right + 13


def read_pieces(image, right, end):
    steps = end // 4
    pieces = [("시", 7 / 4), ("군", (right + 5) / 4)]
    return symbols.restore_inline_checkboxes(pieces, image[:, :end], steps, end), steps


@pytest.mark.parametrize("kind, mark", [("hollow", "□"), ("filled", "■")])
def test_checkbox_the_model_skipped_inside_a_box_is_inserted_in_place(kind, mark):
    image, left, right, end = checkbox_line(kind)
    pieces, _ = read_pieces(image, right, end)
    assert [char for char, _ in pieces] == ["시", mark, "군"]
    assert pieces[0][1] < pieces[1][1] < pieces[2][1]


def test_checkbox_after_its_label_at_the_end_of_the_line_is_inserted():
    image, left, right, end = checkbox_line()
    end = left + 16 + 2
    steps = end // 4
    pieces = symbols.restore_inline_checkboxes([("동", 7 / 4)], image[:, :end], steps, end)
    assert [char for char, _ in pieces] == ["동", "□"]


def test_checkbox_the_model_read_is_left_alone():
    image, left, right, end = checkbox_line()
    pieces = [("시", 7 / 4), ("ㅁ", (left + 8) / 4), ("군", (right + 5) / 4)]
    assert symbols.restore_inline_checkboxes(pieces, image[:, :end], end // 4, end) == pieces


def test_leading_checkbox_stays_with_the_leading_symbol_rule():
    image, left, right, end = checkbox_line()
    image[:, :left - 1] = 255                                    # 앞 글자 없음
    pieces = [("군", (right + 5) / 4)]
    assert symbols.restore_inline_checkboxes(pieces, image[:, :end], end // 4, end) == pieces


def test_checkbox_right_after_a_table_rule_is_not_counted_twice():
    image, left, right, end = checkbox_line()
    image[:, :left - 1] = 255
    image[:, 3:5] = 0                                            # 상자 왼쪽에 걸린 표 세로선을 모델이 '|'로 읽었다
    pieces = [("|", 4 / 4), ("군", (right + 5) / 4)]
    boxes = [(0, 0, end, HEIGHT)]
    assert symbols.restore_inline_checkboxes(pieces, image[:, :end], end // 4, end) == pieces
    assert symbols.leading_symbol(image, 0, boxes)[0] == "□"     # 이 기호는 줄 맨 앞 규칙이 낸다


@pytest.mark.parametrize("name, kwargs", [
    ("글자 왼쪽 획처럼 뒤 글자에 붙음", dict(size=16, gap=4)),
    ("줄 높이의 절반쯤인 작은 네모", dict(size=8)),
    ("점이나 쉼표 크기", dict(kind="filled", size=4)),
    ("고리", dict(kind="ring", size=16)),
    ("마름모", dict(kind="diamond", size=20)),
])
def test_other_shapes_are_not_inline_checkboxes(name, kwargs):
    image, left, right, end = checkbox_line(**kwargs)
    pieces, _ = read_pieces(image, right, end)
    assert [char for char, _ in pieces] == ["시", "군"], name


# ── 줄 맨 앞 '-' (개조식 공문서에 흔하다. 상자가 그 오른쪽에서 시작해 모델이 못 보기도 한다) ──
def dash_image(width=9, thick=2, top=11, gap=10, strokes=1):
    """[막대] [간격] [글자]: 글자 높이 20. (이미지, 글자 시작 x, 끝 x)."""
    image = np.full((HEIGHT, 120, 3), 255, np.uint8)
    for k in range(strokes):
        image[top + 4 * k:top + 4 * k + thick, 4:4 + width] = 0
    x = 4 + width + gap
    left = x
    for _ in range(3):
        draw_text_block(image, x)
        x += 13
    return image, left, x


def test_dash_the_model_skipped_is_prepended_and_not_flagged():
    image, left, end = dash_image()
    assert symbols.apply_leading_symbols(image, outside_box(image, left, end), [("기초연구 비전", 0.95)]) == [("- 기초연구 비전", 0.95, 0)]
    assert symbols.apply_leading_symbols(image, [(0, 0, end, HEIGHT)], [("기초연구 비전", 0.95)]) == [("- 기초연구 비전", 0.95, 0)]


@pytest.mark.parametrize("read", ["-설문조사", "- 설문조사", "–설문조사", "~설문조사"])
def test_dash_the_model_already_read_keeps_the_text_as_it_is(read):
    image, left, end = dash_image()
    assert symbols.apply_leading_symbols(image, [(0, 0, end, HEIGHT)], [(read, 0.9)]) == [(read, 0.9, 0)]


def test_dash_misread_as_a_middle_dot_is_replaced():
    image, left, end = dash_image()
    assert symbols.apply_leading_symbols(image, [(0, 0, end, HEIGHT)], [("· 생일 축하", 0.9)]) == [("- 생일 축하", 0.9, 0)]


@pytest.mark.parametrize("name, kwargs", [
    ("표 선처럼 길다", dict(width=40)),
    ("글자 아래쪽(밑줄 높이)", dict(top=18)),
    ("글자 위쪽", dict(top=2)),
    ("두껍다", dict(thick=6, width=14)),
    ("너무 짧다(점)", dict(width=3)),
    ("뒤 글자에 붙었다(음수 기호)", dict(gap=2)),
    ("두 줄이다(=)", dict(thick=2, top=8, strokes=2, width=10)),
])
def test_other_flat_shapes_are_not_a_dash(name, kwargs):
    image, left, end = dash_image(**kwargs)
    found = symbols.leading_symbol(image, 0, [(0, 0, end, HEIGHT)])
    assert found is None or found[0] != "-", name


def test_lone_dash_box_without_a_neighbor_is_left_alone():
    image = np.full((HEIGHT, 40, 3), 255, np.uint8)
    image[11:13, 10:19] = 0
    assert symbols.apply_leading_symbols(image, [(8, 6, 22, 18)], [("-", 0.9)]) == [("-", 0.9, 0)]


def open_glyph(side):
    """한쪽이 트인 글자('C', 'u', 'n'). 가운데가 비어 고리·네모처럼 보인다."""
    mask = glyph("hollow", 14)
    if side == "right":
        mask[5:9, 12:] = False
    elif side == "top":
        mask[:2, 4:10] = False
    else:
        mask[-2:, 4:10] = False
    return mask


@pytest.mark.parametrize("side", ["right", "top", "bottom"])
def test_open_letter_is_not_a_ring_or_a_box(side):
    """엑셀 열 머리글 'C'가 ○로, 칸의 'in'이 □로 나왔다. 고리와 네모는 사방이 닫혀 있다."""
    image = np.full((HEIGHT, 60, 3), 255, np.uint8)
    image[4:18, 4:18][open_glyph(side)] = 0
    assert symbols.leading_symbol(image, 0, [(2, 0, 58, HEIGHT)]) is None


def test_closed_ring_is_still_a_ring():
    image = np.full((HEIGHT, 60, 3), 255, np.uint8)
    image[4:18, 4:18][glyph("ring", 14)] = 0
    assert symbols.leading_symbol(image, 0, [(2, 0, 58, HEIGHT)])[0] in symbols.RINGS


def test_table_rule_keeps_the_neighbor_cell_out():
    """표 선 왼쪽은 다른 칸이다. 옆 칸 글자의 'ㅇ'을 이 칸의 글머리로 붙였다."""
    image = np.full((HEIGHT, 120, 3), 255, np.uint8)
    image[4:18, 4:18][glyph("ring", 14)] = 0
    image[:, 26:27] = 0
    for x in (40, 54, 68):
        draw_text_block(image, x)
    assert symbols.leading_symbol(image, 0, [(40, 0, 118, HEIGHT)]) is None


def test_box_overlapping_its_left_neighbor_does_not_read_the_neighbor():
    """큰 글자에서 상자가 겹치면 앞 글자의 획이 이 상자의 기호로 보였다('표'가 □로)."""
    image = np.full((HEIGHT, 120, 3), 255, np.uint8)
    image[4:18, 40:54][glyph("hollow", 14)] = 0
    for x in (70, 84):
        draw_text_block(image, x)
    assert symbols.leading_symbol(image, 1, [(4, 0, 60, HEIGHT), (36, 0, 118, HEIGHT)]) is None


def test_letter_d_is_not_a_ring():
    """왼쪽 모서리 둘만 찬 D 는 고리가 아니다."""
    from screen_text.leading_symbols import _blobs, _classify
    ink = np.zeros((14, 24), bool)
    ink[2:12, 2] = True
    ink[2, 2:7] = ink[11, 2:7] = True
    ink[3, 7] = ink[10, 7] = True
    ink[4:10, 8] = True
    assert _classify(_blobs(ink)[0]) is None


# ── 표 칸 경계(2026-11-09, 엣지 표의 '□ □ 정호진') ──
def checkbox_cell_row():
    """[체크박스 칸 | 옅은 눈금선 | 이름 칸]. 눈금선은 진한 체크박스에 견주면 글자 픽셀 문턱을 넘지 못한다."""
    from screen_text.layout import Grid, GridCell
    image = np.full((HEIGHT, 120, 3), 255, np.uint8)
    image[3:19, 6:22][glyph("hollow", 16)] = 0
    image[:, 30] = 215
    for x in (40, 54, 68):
        draw_text_block(image, x)
    cells = (GridCell(0, 0, 1, 1, 0, 0, 30, HEIGHT), GridCell(0, 1, 1, 1, 31, 0, 120, HEIGHT))
    return image, Grid(1, 2, cells, 0, 0, 120, HEIGHT)


def test_checkbox_in_the_next_cell_is_not_attached_again():
    """옆 칸의 체크박스는 그 칸의 표시로 따로 읽힌다. 옅은 눈금선 너머에서 이름 앞에 다시 붙여 '□ □ 정호진'이 됐다."""
    image, grid = checkbox_cell_row()
    boxes = [(4, 1, 24, 21), (38, 0, 82, HEIGHT)]
    results = [("", 0.0), ("정호진", 0.99)]
    assert symbols.apply_leading_symbols(image, boxes, results)[1][0] == "□ 정호진"   # 격자를 모르면 예전처럼 붙인다
    assert symbols.apply_leading_symbols(image, boxes, results, [grid])[1][0] == "정호진"


def test_symbol_straddling_the_cell_edge_stays_with_the_cell():
    """제목 □의 왼쪽 변이 아래 표의 왼쪽 테두리와 한 줄로 이어져 칸 경계가 □ 안을 지났다. 칸 안에서 끝나는 기호는 이 칸의 것이다."""
    from screen_text.layout import Grid, GridCell
    image, end = separate_symbol_image("hollow", 11)    # □는 4~14, 칸 경계는 □ 안을 지나는 6
    grid = Grid(1, 1, (GridCell(0, 0, 1, 1, 6, 0, 120, HEIGHT),), 6, 0, 120, HEIGHT)
    out = symbols.apply_leading_symbols(image, [(26, 0, end, HEIGHT)], [("성과지표", 0.99)], [grid])
    assert out[0][0] == "□ 성과지표"


def test_hangul_the_model_is_sure_of_stays_in_a_one_letter_box():
    """세로로 쓴 칸의 한 글자('해 당 없 음')가 스캔에서 번져 ■ 모양이 됐다. 모델이 확신한 한글은 그대로 둔다."""
    image, end = separate_symbol_image("filled", 12)
    boxes = [(2, 2, 22, 20), (26, 0, end, HEIGHT)]
    assert symbols.apply_leading_symbols(image, boxes, [("음", 0.97), ("추진배경", 0.99)])[0] == ("음", 0.97, 0)
    # 기호만 든 상자를 모델이 한글로 잘못 읽을 때는 확신이 낮다(실측 0.17~0.60, '에' '이' '곳')
    assert symbols.apply_leading_symbols(image, boxes, [("에", 0.3), ("추진배경", 0.99)])[0][0] == "■"


# 그림자 동그라미(❍): 사전에 없어 모델이 내지 못하고 고리 판정이 크기에 따라 ○ ㅇ 로 냈다(함평군 업무계획 PDF의 ❍ 875곳이 모두 ○).
# 아래 표는 실제 화면에서 잰 회색 값(배경과의 차이 0~255)이다. 바깥 두 줄·두 열은 바탕이다.
SHADOW_RING_PLAN_80 = [   # 함평군 업무계획 PDF 80%: 왼쪽 획보다 오른쪽 획(그림자)이 두껍고 진하다
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 26, 119, 175, 194, 189, 156, 75, 4, 0, 0, 0, 0],
    [0, 0, 0, 2, 86, 186, 99, 24, 8, 53, 154, 242, 172, 25, 0, 0, 0],
    [0, 0, 0, 73, 166, 26, 0, 0, 0, 0, 2, 94, 239, 176, 16, 0, 0],
    [0, 0, 17, 160, 49, 0, 0, 0, 0, 0, 0, 3, 138, 246, 99, 0, 0],
    [0, 0, 64, 141, 4, 0, 0, 0, 0, 0, 0, 0, 56, 234, 172, 6, 0],
    [0, 0, 90, 114, 0, 0, 0, 0, 0, 0, 0, 0, 31, 217, 196, 18, 0],
    [0, 0, 84, 120, 2, 0, 0, 0, 0, 0, 0, 0, 35, 222, 190, 15, 0],
    [0, 0, 47, 155, 12, 0, 0, 0, 0, 0, 0, 0, 79, 242, 149, 3, 0],
    [0, 0, 6, 139, 86, 0, 0, 0, 0, 0, 0, 18, 183, 234, 62, 0, 0],
    [0, 0, 0, 32, 170, 77, 2, 0, 0, 0, 21, 163, 243, 117, 3, 0, 0],
    [0, 0, 0, 0, 29, 155, 174, 114, 101, 141, 223, 221, 92, 3, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 30, 84, 103, 97, 62, 8, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
]
SHADOW_RING_HWP = [       # 한글 창 12px(안티에일리어싱 없음): 왼쪽 획 1px, 오른쪽 2px
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 255, 255, 255, 255, 255, 0, 0, 0, 0],
    [0, 0, 0, 255, 0, 0, 0, 0, 255, 255, 0, 0, 0],
    [0, 0, 255, 0, 0, 0, 0, 0, 0, 255, 255, 0, 0],
    [0, 0, 255, 0, 0, 0, 0, 0, 0, 255, 255, 0, 0],
    [0, 0, 255, 0, 0, 0, 0, 0, 0, 255, 255, 0, 0],
    [0, 0, 255, 0, 0, 0, 0, 0, 0, 255, 255, 0, 0],
    [0, 0, 255, 0, 0, 0, 0, 0, 0, 255, 255, 0, 0],
    [0, 0, 0, 255, 0, 0, 0, 0, 255, 255, 0, 0, 0],
    [0, 0, 0, 0, 255, 255, 255, 255, 255, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
]
EVEN_RING_GDI = [         # GDI 맑은 고딕 ○: 대칭인데 왼쪽 획이 두 열(56, 54)로 옅게 나뉘어 바깥 열이 글자 픽셀 문턱(76)에 못 미친다
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 25, 134, 238, 255, 255, 248, 161, 43, 0, 0, 0, 0, 0],
    [0, 0, 0, 60, 231, 119, 32, 0, 0, 4, 66, 184, 128, 0, 0, 0, 0],
    [0, 0, 34, 187, 11, 0, 0, 0, 0, 0, 0, 4, 134, 128, 0, 0, 0],
    [0, 4, 140, 22, 0, 0, 0, 0, 0, 0, 0, 0, 4, 166, 22, 0, 0],
    [0, 34, 102, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 60, 89, 0, 0],
    [0, 56, 54, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8, 144, 0, 0],
    [0, 56, 54, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8, 144, 0, 0],
    [0, 56, 54, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8, 144, 0, 0],
    [0, 34, 102, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 60, 89, 0, 0],
    [0, 0, 129, 22, 0, 0, 0, 0, 0, 0, 0, 0, 4, 166, 22, 0, 0],
    [0, 0, 34, 187, 11, 0, 0, 0, 0, 0, 0, 4, 134, 89, 0, 0, 0],
    [0, 0, 0, 60, 231, 119, 32, 0, 0, 4, 66, 184, 128, 0, 0, 0, 0],
    [0, 0, 0, 0, 25, 134, 238, 255, 255, 248, 161, 43, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
]


def measured(levels):
    """화면에서 잰 회색 값을 bullet_line의 덮인 비율로."""
    return np.asarray(levels, float) / 255


def eccentric_ring(size, stroke, offset, sub=8):
    """지름 size인 고리. 구멍을 왼쪽으로 offset만큼 옮겨 오른쪽 획이 그만큼 두껍다(그림자 동그라미 ❍의 모양)."""
    yy, xx = (np.mgrid[0:size * sub, 0:size * sub] + .5) / sub
    c = size / 2
    outer = (yy - c) ** 2 + (xx - c) ** 2 <= c * c
    hole = (yy - c) ** 2 + (xx - c + offset) ** 2 <= (c - stroke) ** 2
    return (outer & ~hole).reshape(size, sub, size, sub).mean(axis=(1, 3))


def shadow_square(size=13, stroke=1, shadow=2):
    """그림자 네모(❏): 속이 빈 네모의 오른쪽과 아래에 그림자가 붙는다."""
    cover = np.zeros((size + shadow, size + shadow))
    cover[:stroke, :size] = cover[size - stroke:size, :size] = 1
    cover[:size, :stroke] = cover[:size, size - stroke:size] = 1
    cover[shadow:size + shadow, size:size + shadow] = 1
    cover[size:size + shadow, shadow:size + shadow] = 1
    return cover


@pytest.mark.parametrize("levels", [SHADOW_RING_PLAN_80, SHADOW_RING_HWP])
def test_ring_with_heavier_right_side_is_shadowed_circle(levels):
    """오른쪽 그림자가 보이는 고리는 ❍다. 모양이 분명해 확인 필요로 표시하지 않는다."""
    image, left, end = bullet_line(measured(levels))
    assert symbols.leading_symbol(image, 0, outside_box(image, left, end))[0] == "❍"
    assert symbols.apply_leading_symbols(image, outside_box(image, left, end), [("사업내용", 0.9)]) == [("❍ 사업내용", 0.9, 0)]


@pytest.mark.parametrize("size, stroke, offset", [(10, 2, .8), (18, 3, 1.2)])   # 크기로는 ㅇ(줄 글자 높이의 0.5배)과 ○(0.9배)가 될 고리
def test_shadowed_circle_does_not_depend_on_size(size, stroke, offset):
    image, left, end = bullet_line(eccentric_ring(size, stroke, offset))
    assert symbols.apply_leading_symbols(image, [(0, 0, end, HEIGHT)], [("O 사업내용", 0.9)]) == [("❍ 사업내용", 0.9, 0)]   # 상자 안의 O로 읽혔다


def test_shadowed_circle_alone_in_its_box():
    """위치 찾기가 기호만 따로 상자로 자르면 모델이 읽은 글자('0', 0.47)를 ❍로 바꾼다."""
    image, left, end = bullet_line(measured(SHADOW_RING_PLAN_80))
    boxes = [(2, 0, left - 4, HEIGHT), (left, 0, end, HEIGHT)]
    assert symbols.apply_leading_symbols(image, boxes, [("0", 0.47), ("사업내용", 0.97)]) == [("❍", 0.47, 0), ("사업내용", 0.97, 0)]


def test_even_ring_whose_faint_edge_is_cut_stays_a_ring():
    """대칭인 고리도 옅은 바깥 열이 글자 픽셀 문턱에 잘리면 덩어리 안만 볼 때 오른쪽이 2배 무거워 보인다. 둘레까지 재면 고르다."""
    image, left, end = bullet_line(measured(EVEN_RING_GDI))
    assert symbols.apply_leading_symbols(image, outside_box(image, left, end), [("사업내용", 0.9)]) == [("ㅇ 사업내용", 0.9, 1)]


def test_shadowed_square_is_not_a_shadowed_circle():
    """그림자 네모(❏)도 오른쪽이 무겁지만 꼭짓점이 찬다. ❍로 바꾸지 않고 지금처럼 고리로 내어 확인 필요로 둔다."""
    image, left, end = bullet_line(shadow_square())
    assert symbols.apply_leading_symbols(image, outside_box(image, left, end), [("사업내용", 0.9)]) == [("○ 사업내용", 0.9, 1)]
