"""v4.6 공휴일 테마: 집중 위젯 바탕과 토마토 모자(Task 5).

집중 위젯(접힌·펼친 상태)과 크게 보기 집중 미니 카드가 테마 색을 입고, 토마토가 공휴일 모자를
쓰는지 확인한다. 테마는 화면 전용이므로 모든 검사는 합성 데이터(app_dir)에서 하며,
집중 세션 기록·타이머·퍼센트 색은 그대로여야 한다.
"""
from datetime import date

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QLabel

import database as db
import holiday_theme as ht
from app_paths import resource_root
from holiday_theme import THEME_KEYS, THEMES
from holidays import KOREAN_HOLIDAYS
from ui_focus import (
    FOCUS_ACCENT_COLOR,
    FOCUS_CARD_GRADIENT,
    FocusWidgetWindow,
    TOMATO_IMAGE_SIZE,
    TOMATO_MINI_IMAGE_SIZE,
)
from ui_focus_panel import FocusMiniCard, FocusSidePanel
from ui_holiday_theme import HAT_OFFSET_UNITS, HAT_VIEWBOX, hat_pixmap
from ui_main import MainCalendarWindow

_HAT_DIR = resource_root() / "resources" / "holiday_themes"
_BANNED = ("<text", "filter", "clipPath", "mask", "paint-order", "style=", "<image")


@pytest.fixture(autouse=True)
def quiet_desktop(app_dir):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")


def _focus_window(qtbot, goal="테마 집중"):
    wid = db.create_focus_widget(goal, "25/5")
    data = next(w for w in db.get_open_focus_widgets() if w["id"] == wid)
    win = FocusWidgetWindow(wid, data)
    qtbot.addWidget(win)
    return win


def _bottom_left_in(win, widget):
    """위젯의 왼쪽 아래 모서리를 창 좌표로 돌려준다."""
    return widget.mapTo(win, QPoint(0, widget.height()))


# ── 모자 그림 ────────────────────────────────────────────────────────

def test_hat_constants():
    assert HAT_VIEWBOX == (0, -30, 100, 130)
    assert HAT_OFFSET_UNITS == {"tomato.png": 8, "tomato_mini.png": 13}


def test_all_hat_assets_are_tiny_svg():
    assert len(THEME_KEYS) == 13
    for key in THEME_KEYS:
        path = _HAT_DIR / key / "hat.svg"
        assert path.is_file(), key
        assert QSvgRenderer(str(path)).isValid(), key
        text = path.read_text(encoding="utf-8")
        assert 'viewBox="0 -30 100 130"' in text, key
        for banned in _BANNED:
            assert banned not in text, (key, banned)


def test_hat_pixmap_geometry(qapp):
    pix = hat_pixmap("christmas", 38, 13, 1.25)
    assert pix.deviceIndependentSize().toSize().toTuple() == (38, 49)
    assert pix.devicePixelRatio() == 1.25
    assert not pix.isNull()


def test_hat_pixmap_unknown_key_is_blank_not_error(qapp):
    pix = hat_pixmap("no_such_theme", 38, 13, 1.0)
    assert pix.deviceIndependentSize().toSize().toTuple() == (38, 49)
    image = pix.toImage()
    assert all(image.pixelColor(x, y).alpha() == 0
               for x in range(image.width()) for y in range(image.height()))


def _opaque_extent(image, min_alpha=16):
    """뚜렷한 픽셀(알파 min_alpha 초과; 안티앨리어싱 찌꺼기 제외)의 (위 행, 아래 행, 왼 열, 오른 열)."""
    ys, xs = [], []
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > min_alpha:
                ys.append(y)
                xs.append(x)
    if not ys:
        return None
    return min(ys), max(ys), min(xs), max(xs)


# 토마토 그림에서 머리(빨강)가 시작하는 높이(상자 단위, 시안 측정값). 모자는 이보다 위에서 시작한다.
_HEAD_START = {"tomato_mini.png": 21, "tomato.png": 16}
# 머리 위에 얹지 않는 모양: 삼일절은 머리띠(이마 높이), 현충일은 머리 오른쪽에 꽂은 국화.
_NOT_ON_TOP = {"samil", "memorial"}


@pytest.mark.parametrize("dpr", [1.0, 1.25, 1.5])
@pytest.mark.parametrize("key", THEME_KEYS)
@pytest.mark.parametrize("box,offset_key", [(TOMATO_MINI_IMAGE_SIZE, "tomato_mini.png"),
                                           (TOMATO_IMAGE_SIZE, "tomato.png")])
def test_hats_fit_inside_pixmap_at_scales(qapp, key, dpr, box, offset_key):
    pix = hat_pixmap(key, box, HAT_OFFSET_UNITS[offset_key], dpr)
    image = pix.toImage().convertToFormat(QImage.Format_ARGB32)
    extent = _opaque_extent(image)

    assert extent is not None, "모자가 그려져야 한다"
    top, bottom, left, right = extent
    # 네 가장자리 한 줄은 비어 있어야 모자가 잘리지 않는다.
    assert top > 0 and left > 0
    assert bottom < image.height() - 1 and right < image.width() - 1

    top_units = top / dpr / box * 100 - 30  # 토마토 그림 상자 위쪽 끝이 0
    if key == "memorial":
        # 현충일은 모자 대신 토마토 머리 오른쪽에 국화를 꽂는다(시안: 상자 안쪽 위 오른쪽).
        assert left > image.width() * 0.4, "국화는 오른쪽에 있다"
    if key in _NOT_ON_TOP:
        assert 0 <= top_units < 50, "머리띠·국화는 상자 위쪽 절반에 놓인다"
    else:
        assert top_units < _HEAD_START[offset_key], "모자는 토마토 머리 위에서 시작한다"


# ── 집중 위젯 바탕 ────────────────────────────────────────────────────

def test_focus_theme_gradient_only_in_normal_state(qtbot, app_dir):
    win = _focus_window(qtbot)
    assert FOCUS_CARD_GRADIENT in win.container.styleSheet()

    win.set_holiday_theme(THEMES["labor"])
    sheet = win.container.styleSheet()
    assert "#F6EFE6" in sheet and "#EADBC6" in sheet
    assert "stop:0 #FFFFFF" in sheet and "stop:0.48 #F6EFE6" in sheet and "stop:1 #EADBC6" in sheet
    assert "#EEF6FF" not in sheet

    win._apply_visual_state("break")
    assert "#EDF7FF" in win.container.styleSheet()
    assert "#F6EFE6" not in win.container.styleSheet()

    win._apply_visual_state("complete")
    assert "#FFF0EC" in win.container.styleSheet()
    assert "#F6EFE6" not in win.container.styleSheet()

    win._apply_visual_state("normal")
    assert "#F6EFE6" in win.container.styleSheet()


def test_theme_survives_state_roundtrip_and_keeps_progress_color(qtbot, app_dir):
    win = _focus_window(qtbot)
    win.set_holiday_theme(THEMES["christmas"])
    win._apply_visual_state("break")
    win.set_holiday_theme(THEMES["labor"])   # break 중 테마가 바뀌어도 break 바탕을 지킨다
    assert "#EDF7FF" in win.container.styleSheet()
    win._apply_visual_state("normal")
    assert "#EADBC6" in win.container.styleSheet()
    assert FOCUS_ACCENT_COLOR in win.percent_label.styleSheet()  # 퍼센트는 토마토 빨강 그대로


def test_theme_none_restores_focus_widget(qtbot, app_dir):
    win = _focus_window(qtbot)
    win.set_holiday_theme(THEMES["christmas"])
    win.show()
    assert not win._hat_mini_label.isHidden()

    win.set_holiday_theme(None)
    assert win._hat_mini_label.isHidden()
    assert win._hat_label.isHidden()
    assert FOCUS_CARD_GRADIENT in win.container.styleSheet()
    assert THEMES["christmas"].focus_end not in win.container.styleSheet()


def test_set_holiday_theme_is_idempotent(qtbot, app_dir):
    win = _focus_window(qtbot)
    for _ in range(3):
        win.set_holiday_theme(THEMES["christmas"])
    assert len(win.container.findChildren(QLabel, "focusHatMini")) == 1
    assert len(win.container.findChildren(QLabel, "focusHat")) == 1
    sheet = win.container.styleSheet()
    win.set_holiday_theme(THEMES["christmas"])
    assert win.container.styleSheet() == sheet


# ── 토마토 모자 배치 ─────────────────────────────────────────────────

def test_hat_labels_follow_tomato_in_both_modes(qtbot, app_dir):
    win = _focus_window(qtbot)
    win.set_holiday_theme(THEMES["christmas"])
    win.show()
    qtbot.waitExposed(win)

    # 접힌 상태: 작은 토마토에 맞춘다.
    assert win._display_mode == "ambient"
    assert win._hat_mini_label.objectName() == "focusHatMini"
    assert not win._hat_mini_label.isHidden()
    assert win._hat_label.isHidden()
    mini = win.tomato_mini_label
    assert _bottom_left_in(win, win._hat_mini_label) == _bottom_left_in(win, mini)
    assert win._hat_mini_label.size().toTuple() == (TOMATO_MINI_IMAGE_SIZE,
                                                    round(TOMATO_MINI_IMAGE_SIZE * 1.3))
    # 창 밖으로 잘려 나가지 않는다.
    assert win._hat_mini_label.mapTo(win, QPoint(0, 0)).y() >= 0

    # 펼친 상태: 큰 토마토에 맞춘다.
    win._set_display_mode("glance")
    assert win._hat_label.objectName() == "focusHat"
    assert not win._hat_label.isHidden()
    assert win._hat_mini_label.isHidden()
    big = win.tomato_label
    assert _bottom_left_in(win, win._hat_label) == _bottom_left_in(win, big)
    assert win._hat_label.size().toTuple() == (TOMATO_IMAGE_SIZE, round(TOMATO_IMAGE_SIZE * 1.3))
    assert win._hat_label.mapTo(win, QPoint(0, 0)).y() >= 0

    # 다시 접으면 작은 모자로 돌아온다.
    win._set_display_mode("ambient")
    assert not win._hat_mini_label.isHidden()
    assert win._hat_label.isHidden()
    assert _bottom_left_in(win, win._hat_mini_label) == _bottom_left_in(win, mini)


def test_hat_theme_set_before_show_is_placed_on_show(qtbot, app_dir):
    win = _focus_window(qtbot)
    win.set_holiday_theme(THEMES["hangul"])  # 보이기 전에 입혀도
    win.show()
    qtbot.waitExposed(win)
    assert not win._hat_mini_label.isHidden()
    assert _bottom_left_in(win, win._hat_mini_label) == _bottom_left_in(win, win.tomato_mini_label)


def test_hat_labels_are_transparent_for_mouse(qtbot, app_dir):
    win = _focus_window(qtbot)
    for hat in (win._hat_mini_label, win._hat_label):
        assert hat.testAttribute(Qt.WA_TransparentForMouseEvents)


def test_tomato_click_still_shows_bubble_with_hat(qtbot, app_dir, monkeypatch):
    win = _focus_window(qtbot)
    monkeypatch.setattr("ui_focus.secrets.choice", lambda messages: "힘내")
    win.set_holiday_theme(THEMES["christmas"])
    win.show()
    qtbot.waitExposed(win)
    win._set_display_mode("glance")
    assert not win._hat_label.isHidden()

    # 모자 레이블이 토마토 위를 덮고 있어도 그 자리를 누르면 토마토 레이블이 받는다
    # (childAt은 마우스 투과 위젯을 건너뛴다. qtbot.mouseClick은 위젯에 바로 보내므로 따로 확인한다).
    for dx, dy in ((TOMATO_IMAGE_SIZE // 2, TOMATO_IMAGE_SIZE // 2), (8, 6), (TOMATO_IMAGE_SIZE - 8, 6)):
        assert win.childAt(win.tomato_label.mapTo(win, QPoint(dx, dy))) is win.tomato_label
    qtbot.mouseClick(win.tomato_label, Qt.LeftButton)

    assert not win.encouragement_bubble.isHidden()
    assert win.encouragement_bubble.text() == "힘내"
    win._hide_encouragement_bubble()


def test_hat_is_rendered_over_tomato_at_dpr(qtbot, app_dir):
    """모자 그림이 실제로 레이블 픽스맵으로 걸려 있고, 장치 배율을 따른다."""
    win = _focus_window(qtbot)
    win.set_holiday_theme(THEMES["christmas"])
    pix = win._hat_mini_label.pixmap()
    assert pix is not None and not pix.isNull()
    assert pix.deviceIndependentSize().toSize().toTuple() == (
        TOMATO_MINI_IMAGE_SIZE, round(TOMATO_MINI_IMAGE_SIZE * 1.3))
    assert pix.devicePixelRatio() == pytest.approx(win.devicePixelRatioF())


def test_theme_change_swaps_hat_pixmap(qtbot, app_dir):
    win = _focus_window(qtbot)
    win.set_holiday_theme(THEMES["christmas"])
    first = win._hat_mini_label.pixmap().toImage()
    win.set_holiday_theme(THEMES["labor"])
    second = win._hat_mini_label.pixmap().toImage()
    assert first != second


# ── 크게 보기 집중 미니 카드 ─────────────────────────────────────────

def test_mini_card_and_side_panel_get_gradient_only(qtbot, app_dir):
    win = _focus_window(qtbot)
    card = FocusMiniCard(win)
    qtbot.addWidget(card)
    before = card.styleSheet()
    assert "rgba(255,255,255,235)" in before

    card.set_holiday_theme(THEMES["labor"])
    sheet = card.styleSheet()
    assert "#F6EFE6" in sheet and "#EADBC6" in sheet
    assert "border:1px solid rgba(255,90,69,90)" in sheet  # 테두리는 그대로
    assert FOCUS_ACCENT_COLOR in card.percent_label.styleSheet()

    card.set_holiday_theme(None)
    assert card.styleSheet() == before


def test_side_panel_hands_theme_to_new_card(qtbot, app_dir):
    win = _focus_window(qtbot)
    panel = FocusSidePanel()
    qtbot.addWidget(panel)
    panel.set_holiday_theme(THEMES["labor"])   # 카드가 없을 때 먼저 받아 둔다
    panel.bind(win)
    assert "#EADBC6" in panel._card.styleSheet()
    panel.set_holiday_theme(THEMES["christmas"])
    assert "#EADBC6" not in panel._card.styleSheet()
    panel.bind(win)                            # 다시 묶어 새로 만든 카드에도
    assert panel._card._holiday_theme is THEMES["christmas"]
    panel.set_holiday_theme(None)
    assert "rgba(255,255,255,235)" in panel._card.styleSheet()


def test_focus_theme_apply_writes_nothing(qtbot, app_dir, monkeypatch):
    """테마·모자·모드 전환·상태 전환 어디에서도 DB에 쓰지 않는다(집중 기록은 그대로)."""
    win = _focus_window(qtbot)
    card = FocusMiniCard(win)
    qtbot.addWidget(card)

    def boom(*args, **kwargs):
        raise AssertionError("공휴일 테마가 DB에 쓰려 했다")

    for name in dir(db):
        if name.startswith(("save_", "update_", "create_", "add_", "delete_", "trash_",
                            "restore_", "import_", "reset_", "backup_")) and callable(getattr(db, name)):
            monkeypatch.setattr(db, name, boom)

    win.show()
    for key in ("christmas", "memorial", "labor"):
        win.set_holiday_theme(THEMES[key])
        card.set_holiday_theme(THEMES[key])
        win._set_display_mode("glance")
        win._set_display_mode("ambient")
        win._apply_visual_state("break")
        win._apply_visual_state("normal")
    win.set_holiday_theme(None)
    card.set_holiday_theme(None)
    assert db.get_open_focus_widgets()[0]["goal"] == "테마 집중"


# ── 메인 창 연결 ─────────────────────────────────────────────────────

def _at(monkeypatch, win, day):
    fixed = ht.resolve_holiday_theme(date.fromisoformat(day), KOREAN_HOLIDAYS)
    monkeypatch.setattr(ht, "current_match", lambda today=None: fixed)
    win._holiday_theme.refresh()
    QApplication.processEvents()


@pytest.fixture
def main_win(qtbot, app_dir):
    w = MainCalendarWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def test_theme_change_reaches_focus_window_and_new_windows(monkeypatch, main_win):
    wid = db.create_focus_widget("기존 집중", "25/5")
    main_win._load_open_focus_widgets()
    focus = main_win._focus_windows[wid]
    assert FOCUS_CARD_GRADIENT in focus.container.styleSheet()

    _at(monkeypatch, main_win, "2026-12-25")
    assert "#EADBC6" not in focus.container.styleSheet()
    assert THEMES["christmas"].focus_end in focus.container.styleSheet()
    assert not focus._hat_mini_label.isHidden()

    _at(monkeypatch, main_win, "2027-05-01")   # 노동절: 다른 테마로 바뀐다
    assert "#EADBC6" in focus.container.styleSheet()

    # 테마 중에 새로 열리는 집중 위젯도 처음부터 입고 있다.
    focus._on_close()
    QApplication.processEvents()
    wid2 = db.create_focus_widget("새 집중", "25/5")
    main_win._load_open_focus_widgets()
    assert "#EADBC6" in main_win._focus_windows[wid2].container.styleSheet()

    # 스위치를 끄면 원래 바탕으로 돌아온다.
    db.save_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "0")
    main_win._holiday_theme.refresh()
    again = main_win._focus_windows[wid2]
    assert FOCUS_CARD_GRADIENT in again.container.styleSheet()
    assert again._hat_mini_label.isHidden()


def test_large_mode_focus_panel_gets_theme_and_hidden_window_keeps_it(monkeypatch, main_win):
    wid = db.create_focus_widget("크게 집중", "25/5")
    main_win._load_open_focus_widgets()
    _at(monkeypatch, main_win, "2027-05-01")

    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    assert main_win._apply_calendar_scale()
    QApplication.processEvents()
    panel = main_win._focus_side_panel
    assert panel is not None and panel._card is not None
    assert "#EADBC6" in panel._card.styleSheet()
    assert "#EADBC6" in main_win._focus_windows[wid].container.styleSheet()

    # 패널이 이미 있는 채로 테마가 바뀌어도 카드가 따라간다.
    _at(monkeypatch, main_win, "2026-12-25")
    assert THEMES["christmas"].focus_end in panel._card.styleSheet()

    # 처음 만드는 패널도 현재 테마를 받는다(작게 갔다가 패널을 버리고 다시 만든 경우와 같다).
    main_win._focus_side_panel = None
    main_win._focus_in_panel_mode = False
    main_win._apply_focus_side_panel(True)
    assert THEMES["christmas"].focus_end in main_win._focus_side_panel._card.styleSheet()

    db.save_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "0")
    main_win._holiday_theme.refresh()
    assert "rgba(255,255,255,235)" in main_win._focus_side_panel._card.styleSheet()
