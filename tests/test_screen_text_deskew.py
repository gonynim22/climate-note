"""기운 스캔본을 바로 세운다. 멀쩡한 화면은 픽셀 하나 건드리지 않는다."""
import math

import numpy as np
import pytest
from PySide6.QtGui import QColor, QFont, QImage, QPainter

import screen_text.deskew as deskew
import screen_text.engine as engine
from screen_text.deskew import skew_angle, straighten
from screen_text.engine import OcrEngine, label_components, rgb_from_buffer
from screen_text.layout import build_blocks, to_plain


def page(degrees, rows=8, width=420, line=12, gap=26, words=None, rules=False):
    """글자 줄을 흉내 낸 막대가 든 쪽. 낱말 사이는 비고 줄은 degrees만큼 오른쪽이 올라간다. (이미지, 글자 마스크)"""
    height = rows * gap + 60
    image = np.full((height, width + 60, 3), 255, np.uint8)
    mask = np.zeros(image.shape[:2], bool)
    slope = math.tan(math.radians(degrees))
    words = words or [(0, 130), (150, 300), (320, width)]
    for row in range(rows):
        top = 30 + row * gap
        for start, end in words:
            for x in range(start, end, 3):      # 세로획. 속이 꽉 찬 막대는 배경 추정을 깨뜨린다
                shift = int(round((width / 2 - x) * slope))
                image[top + shift:top + shift + line, 30 + x:30 + x + 2] = 0
            for x in range(start, end):
                shift = int(round((width / 2 - x) * slope))
                mask[top + 3 + shift:top + line - 3 + shift, 30 + x] = True
        if rules:
            for x in range(width):
                shift = int(round((width / 2 - x) * slope))
                image[top - 6 + shift, 30 + x] = 0
    return image, mask


def angle_of(image, mask):
    return skew_angle(label_components(mask), image)


def test_level_page_is_left_alone():
    assert angle_of(*page(0)) == 0.0


@pytest.mark.parametrize("degrees", [0.8, -0.8, 1.5, -2.0, 3.0])
def test_tilted_page_reports_its_angle(degrees):
    assert angle_of(*page(degrees)) == pytest.approx(degrees, abs=0.15)


def test_tiny_tilt_is_not_worth_blurring_the_text():
    assert angle_of(*page(0.1)) == 0.0


def test_two_lines_of_a_selected_table_row_do_not_look_tilted():
    """높이가 다른 칸 둘은 비스듬히 보면 한 줄로 맞는다. 덩어리 자신은 수평이다."""
    image = np.full((44, 500, 3), 255, np.uint8)
    mask = np.zeros((44, 500), bool)
    for left, right, top in ((10, 200, 6), (260, 480, 22)):
        for x in range(left, right, 3):
            image[top:top + 14, x:x + 2] = 0
        mask[top + 3:top + 11, left:right] = True
    assert angle_of(image, mask) == 0.0


def test_ruled_table_with_few_words_trusts_the_rules():
    """글자가 드문 표는 덩어리가 짧아 기울기를 못 말해 준다. 표 선이 말해 준다(기운 표 행·열 127→168/200)."""
    image, mask = page(1.0, rows=7, gap=34, words=[(0, 44), (190, 234), (340, 384)], rules=True)
    assert angle_of(image, mask) == pytest.approx(1.0, abs=0.15)


def test_staggered_cells_of_a_level_table_stay_level():
    """칸의 높이가 조금씩 어긋난 표는 비스듬히 보면 윤곽이 또렷해지지만 낱말 하나하나는 기운다(복잡한 표 tbl0140)."""
    image = np.full((200, 560, 3), 255, np.uint8)
    mask = np.zeros(image.shape[:2], bool)
    for row in range(3):
        for column, (left, right) in enumerate(((20, 110), (150, 250), (290, 390), (430, 530))):
            top = 30 + row * 50 + (3 - column) * 4
            for x in range(left, right, 3):
                image[top:top + 14, x:x + 2] = 0
            mask[top + 3:top + 11, left:right] = True
    assert angle_of(image, mask) == 0.0


def test_slanted_line_in_a_picture_does_not_turn_a_level_page():
    image, mask = page(0, rows=6)
    slope = math.tan(math.radians(2.0))
    for x in range(420):
        y = int(round(210 - x * slope))
        image[y:y + 2, 30 + x] = 0
    assert angle_of(image, mask) == 0.0


def test_empty_region_has_no_angle():
    assert skew_angle([], np.full((40, 40, 3), 255, np.uint8)) == 0.0


def rows_used(image):
    return np.flatnonzero((image.min(axis=2) < 128).any(axis=1)).size


def test_straighten_levels_the_lines():
    image, _ = page(2.0, rows=3, gap=40)
    assert rows_used(straighten(image, 2.0)) < 0.6 * rows_used(image)


def test_straighten_keeps_the_corners_and_fills_with_the_background():
    image = np.full((100, 300, 3), 200, np.uint8)
    image[0, 0] = image[-1, -1] = 10
    turned = straighten(image, 3.0)
    assert turned.dtype == np.uint8 and turned.shape[2] == 3
    assert turned.shape[0] > 100 and turned.shape[1] >= 300
    assert (turned[0, 0] == 200).all() and (turned[-1, 0] == 200).all()


def test_straighten_handles_more_rows_than_one_chunk(monkeypatch):
    image, _ = page(1.0, rows=4)
    whole = straighten(image, 1.0)
    monkeypatch.setattr(deskew, "ROTATE_CHUNK", 7)
    assert np.array_equal(straighten(image, 1.0), whole)


LINES = ("수질오염총량 관리계획 시행 현황을 점검하고 하수처리시설 방류수 수질기준을 강화하여 유역 물환경을 개선한다",
         "기후위기 적응대책의 추진 실적을 보고하고 공공폐수처리시설 운영 관리 체계를 개선하는 방안을 마련한다",
         "유역별 물환경 관리 대책을 마련하여 추진하고 대기오염물질 배출 사업장에 대한 지도 점검을 강화한다",
         "하천 수질 측정망을 확대하고 조류 경보제 운영 기준을 정비하여 먹는 물 안전 관리에 만전을 기한다",
         "온실가스 배출량 산정 체계를 고도화하고 탄소중립 이행 점검 결과를 공개하여 주민 참여를 넓혀 나간다",
         "폐기물 처리시설 설치 계획을 수립하고 재활용 가능 자원의 분리 배출 체계를 개선하여 순환 경제를 만든다")


def render_page():
    """줄 간격이 좁아 2도만 기울어도 축에 맞춘 상자에 이웃 줄이 끼는 쪽."""
    font = QFont("Malgun Gothic")
    font.setPixelSize(22)
    image = QImage(1160, 240, QImage.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    for index, line in enumerate(LINES):
        painter.drawText(24, 40 + index * 32, line)
    painter.end()
    return rgb_from_buffer(image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits()))


@pytest.fixture(scope="module")
def ocr():
    return OcrEngine()


def read(ocr, image):
    return [line for line in to_plain(build_blocks(ocr.recognize(image))).split("\n") if line.strip()]


def matches(lines):
    return sum(line.replace(" ", "") in {got.replace(" ", "") for got in lines} for line in LINES)


def test_real_model_reads_a_tilted_scan(qapp, ocr):
    tilted = straighten(render_page(), -2.0)
    assert matches(read(ocr, tilted)) == len(LINES)


def test_tilted_scan_is_unreadable_without_straightening(qapp, ocr, monkeypatch):
    """시험이 정말 기울기를 재현하는지 확인한다. 고치기 전에는 여섯 줄이 '다' 한 글자로 나왔다."""
    monkeypatch.setattr(engine, "skew_angle", lambda components, image: 0.0)
    tilted = straighten(render_page(), -2.0)
    assert matches(read(ocr, tilted)) == 0


def test_real_model_leaves_a_level_page_untouched(qapp, ocr, monkeypatch):
    called = []
    monkeypatch.setattr(engine, "straighten", lambda image, degrees: called.append(degrees) or image)
    assert matches(read(ocr, render_page())) == len(LINES)
    assert called == []
