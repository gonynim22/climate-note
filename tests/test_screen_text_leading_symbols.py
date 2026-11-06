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


def test_symbol_touching_the_text_is_not_a_bullet():
    image, left, end = line_image("filled", 8, gap=1)   # 붙어 있으면 글자의 일부일 수 있다
    assert symbols.leading_symbol(image, 0, [(0, 0, end, HEIGHT)]) is None


def test_tall_hollow_shape_is_not_a_symbol():
    image = np.full((HEIGHT, 60, 3), 255, np.uint8)
    image[TEXT_TOP:TEXT_BOTTOM, 4:14] = 0
    image[TEXT_TOP + 3:TEXT_BOTTOM - 3, 6:12] = 255          # 속이 빈 세로 직사각형(글자 모양)
    draw_text_block(image, 26)
    assert symbols.leading_symbol(image, 0, [(0, 0, 50, HEIGHT)]) is None


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
