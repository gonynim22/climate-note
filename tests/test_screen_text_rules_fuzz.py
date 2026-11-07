"""글자를 고치는 규칙은 어떤 그림과 글자 조합에서도 예외를 내지 않는다. 예외 하나면 인식 전체가 멈춘다.

표 선만 든 상자에서 ValueError가 나 그림 전체가 빈 결과로 끝난 적이 있다(2026-11-07, 평가의 글자 오류가 튀어서 찾았다).
"""
import numpy as np
import pytest

from screen_text.number_marks import restore_number_marks
from screen_text.roman import restore_roman, stroke_count
from screen_text.table_lines import find_grids, fit_boxes
from screen_text.units import restore_units
from screen_text.word_spaces import join_words

CHARS = list("0123456789.,mkCc°'²³Il|1피표-/ 가나")


def random_image(rng, height, width):
    kind = rng.integers(0, 6)
    if kind == 0:
        return np.full((height, width, 3), 255, np.uint8)
    if kind == 1:
        return np.zeros((height, width, 3), np.uint8)
    if kind == 2:
        return rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
    image = np.full((height, width, 3), 255, np.uint8)
    for _ in range(int(rng.integers(0, 12))):
        y0, x0 = rng.integers(0, height), rng.integers(0, width)
        y1, x1 = y0 + rng.integers(1, max(2, height // 2)), x0 + rng.integers(1, max(2, width // 3))
        image[y0:y1, x0:x1] = rng.integers(0, 256)
    if kind == 4:   # 긴 가로선
        image[height // 2, :] = 0
    if kind == 5:   # 긴 세로선
        image[:, width // 2] = 0
    return image


def random_pieces(rng, steps):
    count = int(rng.integers(0, 14))
    centers = np.sort(rng.uniform(0, steps, count))
    return [(CHARS[int(rng.integers(0, len(CHARS)))], float(center)) for center in centers]


@pytest.mark.parametrize("seed", range(40))
def test_rules_never_raise(seed):
    rng = np.random.default_rng(seed)
    for _ in range(25):
        height, width = int(rng.integers(1, 40)), int(rng.integers(1, 160))
        crop = random_image(rng, height, width)
        steps = int(rng.integers(1, 60))
        pieces = random_pieces(rng, steps)
        spaces = rng.uniform(0, 1, steps + 2).astype(np.float32)
        restore_units(pieces, crop, steps, width)
        restore_roman(pieces, crop, steps, width)
        restore_number_marks(pieces, crop, (0, 0, width, height), steps)
        join_words(pieces, spaces, crop, steps, width)
        stroke_count(crop[:, :, 0] < 128)


def test_empty_crop_and_box_at_the_image_edge():
    image = np.full((6, 6, 3), 255, np.uint8)
    pieces = [("5", 1.0), (",", 2.0), ("6", 3.0)]
    assert restore_number_marks(pieces, image, (2, 5, 2, 6), 4) == (pieces, ())
    assert restore_number_marks(pieces, image, (0, 5, 6, 6), 4)[0] == pieces
    assert restore_units(pieces, image[:0], 4, 6) == (pieces, ())
    assert restore_roman(pieces, image[:0], 4, 6) == pieces


@pytest.mark.parametrize("seed", range(20))
def test_grid_search_never_raises(seed):
    rng = np.random.default_rng(seed)
    for _ in range(6):
        height, width = int(rng.integers(12, 120)), int(rng.integers(12, 200))
        image = random_image(rng, height, width)
        boxes = [tuple(int(v) for v in (x, y, x + rng.integers(2, 60), y + rng.integers(2, 20))) for x, y in zip(rng.integers(0, width, 6), rng.integers(0, height, 6))]
        grids = find_grids(image, boxes, int(rng.integers(0, 2)) * 8)
        fit_boxes(image, boxes, grids)
