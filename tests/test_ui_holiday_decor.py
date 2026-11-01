"""v4.6 공휴일 테마: 장식 레이어와 움직임(Task 6b).

DecorationLayer(그리기·타이머·멈춤), 머리줄·D-Day·스티키 띠·스티커·모자 프로펠러 연결, 잠금·숨김·
Windows 애니메이션 끔·현충일에서의 정지를 확인한다. 테마는 화면 전용이므로 모든 검사는 합성 데이터
(app_dir)에서 하고 DB에는 아무것도 쓰지 않는다. 위치·크기 규칙은 holiday_decor의 디자인 좌표를 따른다.
"""
import re
from datetime import date

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

import database as db
import holiday_decor as hd
import holiday_theme as ht
import ui_holiday_decor
from app_paths import resource_root
from holiday_theme import THEME_KEYS, THEMES
from ui_dday import DDayWidgetWindow
from ui_focus import FocusWidgetWindow, TOMATO_IMAGE_SIZE, TOMATO_MINI_IMAGE_SIZE
from ui_holiday_decor import (
    DecorationLayer,
    FRAME_MS,
    _overlaps,
    fit_clear,
    fit_span,
    frame_clock,
    is_backdrop,
    map_band_y,
    resolve_rect,
    scaled_particles,
    sticker_pixmap,
)
from ui_holiday_theme import HAT_OFFSET_UNITS
from ui_main import MainCalendarWindow
from ui_sticky import StickyNoteWindow
from ui_sticky_panel import StickyMiniCard


@pytest.fixture(autouse=True)
def quiet_desktop(app_dir):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")


def _match(key):
    """오늘이 key 테마의 공휴일인 것으로 판정한 결과(날짜 계산 없이 합성)."""
    today = date.today()
    return ht.HolidayThemeMatch(THEMES[key], today, today, (today,), True)


def _wear(monkeypatch, win, key):
    monkeypatch.setattr(ht, "current_match", lambda today=None: _match(key))
    win._holiday_theme.refresh()
    QApplication.processEvents()


@pytest.fixture
def win(qtbot, app_dir):
    w = MainCalendarWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def _host(qtbot, w=380, h=104, show=True):
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(w, h)
    if show:
        parent.show()
        qtbot.waitExposed(parent)
    return parent


def _alpha_at(widget, x, y):
    image = widget.grab().toImage().convertToFormat(QImage.Format_ARGB32)
    return QColor.fromRgba(image.pixel(x, y)).alpha()


def _sticky_win(qtbot, width=300, height=220, content="<p>메모</p>"):
    note_id = db.create_sticky_note(note_type="memo", x=100, y=100)
    win = StickyNoteWindow(note_id, {"content": content, "x_pos": 100, "y_pos": 100,
                                     "width": width, "height": height,
                                     "color": db.DEFAULT_STICKY_COLOR})
    qtbot.addWidget(win)
    return win


def _dday_win(qtbot):
    wid = db.create_dday_widget("마감", "2030-01-01", color="#46679C")
    data = next(w for w in db.get_open_dday_widgets() if w["id"] == wid)
    win = DDayWidgetWindow(wid, data)
    qtbot.addWidget(win)
    return win


def _focus_win(qtbot):
    wid = db.create_focus_widget("테마 집중", "25/5")
    data = next(w for w in db.get_open_focus_widgets() if w["id"] == wid)
    win = FocusWidgetWindow(wid, data)
    qtbot.addWidget(win)
    return win


# ── 순수 규칙: 한 곳에서만 정하는 배치 ───────────────────────────────

def test_full_width_rule_scales_only_full_width_pieces():
    """rect.w가 표면 디자인 폭과 같은 조각만 너비도 늘고, 나머지는 위치만 비례한다."""
    ridge = (0.0, 0.0, 380.0, 70.0)
    lantern = (14.0, 1.0, 20.0, 24.0)
    assert resolve_rect("header", ridge, "full", {}, 380) == (0.0, 0.0, 380.0, 70.0)
    assert resolve_rect("header", ridge, "full", {}, 760) == (0.0, 0.0, 760.0, 70.0)
    assert resolve_rect("header", lantern, "full", {}, 760) == (28.0, 1.0, 20.0, 24.0)
    # D-Day·띠도 같은 규칙(디자인 폭 220)
    assert resolve_rect("sticky_band", (0, 18, 220, 12), "full", {}, 300)[2] == pytest.approx(300)
    assert resolve_rect("sticky_band", (10, 8, 14, 14), "full", {}, 300)[2] == 14


def test_anchor_rect_uses_real_anchor_or_scaled_reference():
    rect = (-9.0, 16.0, 64.0, 64.0)  # right_gap 기준 -9
    assert resolve_rect("header", rect, "right_gap", {"right_gap": 264.0}, 380)[0] == 255.0
    # 기준점을 아직 받지 못했으면 기본 크기 값(245)에 폭 비율을 곱한 값
    assert resolve_rect("header", rect, "right_gap", {}, 760)[0] == pytest.approx(245 * 2 - 9)
    # y·높이는 늘리지 않는다
    assert resolve_rect("header", rect, "right_gap", {}, 760)[1:] == (16.0, 64.0, 64.0)


def test_fit_span_shrinks_around_center_or_drops():
    assert fit_span(100, 20, 90, 150) == (100, 1.0)               # 들어가면 그대로
    x, scale = fit_span(100, 40, 110, 130)                         # 넓으면 가운데를 지키며 줄인다
    assert scale == pytest.approx(0.5) and x == pytest.approx(110)
    assert fit_span(100, 40, 110, 125) is None                     # 절반보다 작아져야 하면 뺀다
    assert fit_span(100, 20, 150, 90) is None                      # 빈 곳이 없다


def test_fit_clear_never_overlaps_blockers():
    blockers = [(100.0, 10.0, 30.0, 30.0), (200.0, 10.0, 30.0, 30.0)]
    assert fit_clear((140.0, 5.0, 20.0, 30.0), blockers) == (140.0, 5.0, 20.0, 30.0)  # 사이 빈 곳
    fitted = fit_clear((131.0, 5.0, 40.0, 40.0), blockers)         # 한쪽에 걸치면 줄이거나 옮긴다
    assert fitted is not None and not any(_overlaps(fitted, b) for b in blockers)
    assert fit_clear((105.0, 5.0, 20.0, 30.0), blockers) is None   # 가운데가 버튼 위
    assert fit_clear((140.0, 60.0, 20.0, 30.0), blockers) == (140.0, 60.0, 20.0, 30.0)  # 세로로 안 겹침
    assert fit_clear((110.0, 5.0, 160.0, 30.0), blockers) is None  # 두 버튼 사이에 절반도 안 들어가는 큰 조각
    inside = fit_clear((125.0, 5.0, 80.0, 30.0), blockers)         # 사이 빈 곳(70)에 들어가게 줄인다
    assert inside is not None and inside[2] < 80 and not any(_overlaps(inside, b) for b in blockers)


def test_map_band_y_places_edge_pieces_on_the_real_band():
    # 디자인 높이(30)와 같으면 그대로, 44px 띠면 위에 붙은 것은 위, 아래에 붙은 것은 아래, 나머지는 가운데
    assert map_band_y("sticky_band", 8, 13, 30) == 8
    assert map_band_y("sticky_band", 0, 12, 44) == 0
    assert map_band_y("sticky_band", 18, 12, 44) == 32
    assert map_band_y("sticky_band", 8, 13, 44) == 15
    assert map_band_y("sticky_band", 0, 30, 44) == 7        # 위아래를 다 덮으면 가운데
    assert map_band_y("header", 50, 20, None) == 50         # 머리줄은 옮기지 않는다


def test_snow_density_grows_with_width_but_is_capped():
    snow = hd.DECOR["christmas"]["header"].particles[0]
    assert scaled_particles(snow, 380, "header").count == snow.count
    assert scaled_particles(snow, 760, "header").count == snow.count * 2
    assert scaled_particles(snow, 1900, "header").count == snow.count * 3
    star = hd.DECOR["newyear"]["header"].particles[0]
    assert scaled_particles(star, 1900, "header") is star    # 손으로 놓은 점은 그대로


# ── 레이어 ───────────────────────────────────────────────────────────

def test_frame_period_is_at_most_24fps():
    assert FRAME_MS >= 1000 / 24


def test_layer_animates_only_when_visible_unpaused_and_allowed(qtbot, monkeypatch):
    parent = _host(qtbot, show=False)
    layer = DecorationLayer("header", parent)
    layer.set_theme("christmas")
    assert not layer.is_animating()          # 부모가 아직 안 보인다
    parent.show()
    qtbot.waitExposed(parent)
    assert layer.is_animating()

    parent.hide()
    assert not layer.is_animating()
    parent.show()
    assert layer.is_animating()

    layer.set_paused(True)
    assert layer.is_paused() and not layer.is_animating()
    layer.set_paused(False)
    assert layer.is_animating()

    monkeypatch.setattr(ui_holiday_decor, "motion_allowed", lambda: False)
    layer.set_paused(True)
    layer.set_paused(False)                  # 다시 설정해도 Windows 애니메이션이 꺼져 있으면 서 있다
    assert not layer.is_animating()


def test_layer_without_motion_pieces_never_animates(qtbot):
    """움직이는 조각이 없으면(스티키 띠의 정지 무늬) 타이머에 가입하지 않는다."""
    parent = _host(qtbot, 300, 44)
    layer = DecorationLayer("sticky_band", parent)
    layer.set_theme("hangul")                # 원고지 칸 base뿐
    assert not layer.isHidden() and not layer.is_animating()
    assert layer not in frame_clock()._layers


def test_memorial_layer_never_animates_but_still_draws(qtbot):
    parent = _host(qtbot)
    layer = DecorationLayer("header", parent)
    layer.set_theme("memorial")
    assert layer.isVisible() and not layer.is_animating()
    assert layer.grab().toImage().convertToFormat(QImage.Format_ARGB32).hasAlphaChannel()
    image = layer.grab().toImage().convertToFormat(QImage.Format_ARGB32)
    painted = sum(1 for y in range(image.height()) for x in range(image.width())
                  if QColor.fromRgba(image.pixel(x, y)).alpha() > 0)
    assert painted > 200                     # 조기·국화가 그려진다


def test_layer_is_mouse_transparent(qtbot):
    parent = _host(qtbot)
    layer = DecorationLayer("header", parent)
    layer.set_theme("christmas")
    assert layer.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert layer.focusPolicy() == Qt.NoFocus


def test_layer_hides_when_nothing_to_draw(qtbot):
    parent = _host(qtbot, 300, 44)
    layer = DecorationLayer("sticky_band", parent)
    layer.set_theme("seollal")               # 설날 띠는 색동 바탕이 장식이라 그릴 것이 없다
    assert layer.isHidden() and layer.theme_key() is None
    layer.set_theme("christmas")
    assert layer.isVisible() and layer.theme_key() == "christmas"
    layer.set_theme(None)
    assert layer.isHidden() and not layer.is_animating()


def test_set_theme_is_idempotent_and_keeps_time(qtbot):
    parent = _host(qtbot)
    layer = DecorationLayer("header", parent)
    layer.set_theme("christmas")
    qtbot.wait(120)
    before = layer.elapsed()
    assert before > 0.05
    layer.set_theme("christmas")             # 같은 테마를 또 입혀도 처음부터 다시 세지 않는다
    assert layer.elapsed() >= before
    layer.set_theme("newyear")               # 다른 테마는 첫 장면부터
    assert layer.elapsed() < before
    assert len(parent.findChildren(DecorationLayer)) == 1


def test_time_stops_while_hidden_and_resumes(qtbot):
    parent = _host(qtbot)
    layer = DecorationLayer("header", parent)
    layer.set_theme("christmas")
    qtbot.wait(100)
    parent.hide()
    frozen = layer.elapsed()
    qtbot.wait(150)
    assert layer.elapsed() == frozen         # 숨은 동안은 시간이 흐르지 않는다
    parent.show()
    qtbot.wait(100)
    assert layer.elapsed() > frozen


def test_frame_clock_runs_only_while_something_animates(qtbot):
    parent = _host(qtbot)
    layer = DecorationLayer("header", parent)
    layer.set_theme("christmas")
    assert layer in frame_clock()._layers and frame_clock().is_active()
    parent.hide()
    assert layer not in frame_clock()._layers
    qtbot.waitUntil(lambda: not frame_clock().is_active(), timeout=1500)


def test_paused_or_disabled_motion_still_evaluates_motion_state(qtbot, monkeypatch):
    """후광은 불투명한 원 그림이라 glow 투명도(0.16~0.45)가 있어야 은은하다. 멈춘 그림도 거친다."""
    halo_x, halo_y = 268, 22     # 후광 중심(268, 48) 위쪽 26px: 후광 안, 해(반지름 18) 밖

    parent = _host(qtbot)
    layer = DecorationLayer("header", parent)
    layer.set_theme("newyear")
    layer.set_paused(True)                   # 잠금·숨김 같은 멈춤
    assert not layer.is_animating()
    alpha = _alpha_at(layer, halo_x, halo_y)
    assert 20 < alpha < 128, alpha           # 불투명(255)이 아니다

    layer.set_paused(False)
    monkeypatch.setattr(ui_holiday_decor, "motion_allowed", lambda: False)
    layer.sync_animation()                   # Windows 애니메이션 끔
    assert not layer.is_animating()
    alpha = _alpha_at(layer, halo_x, halo_y)
    assert 20 < alpha < 128, alpha


def test_chuseok_halo_is_not_solid_when_still(qtbot, monkeypatch):
    monkeypatch.setattr(ui_holiday_decor, "motion_allowed", lambda: False)
    parent = _host(qtbot, 380, 104)
    layer = DecorationLayer("header", parent)
    layer.set_theme("chuseok")
    # 후광(148..232, 38..122)의 위쪽 가장자리 안쪽: 보름달(60px)은 y 50부터라 닿지 않는다.
    alpha = _alpha_at(layer, 190, 44)
    assert 0 < alpha < 128, alpha


def test_rising_sun_rests_at_risen_position_when_motion_is_off(qtbot, monkeypatch):
    """Windows 애니메이션을 끄면 떠오르는 해는 끝 위치(떠오른 모습)에 선다."""
    sun_x, sun_y = 268, 36       # 해(250..286, 30..66)의 위쪽 안, 능선 위

    parent = _host(qtbot)
    layer = DecorationLayer("header", parent)
    layer.set_theme("newyear")
    layer.set_paused(True)                   # 멈춘 첫 장면: 해는 아직 16px 아래라 이 점에 닿지 않는다
    assert _alpha_at(layer, sun_x, sun_y) < 128

    layer.set_paused(False)
    monkeypatch.setattr(ui_holiday_decor, "motion_allowed", lambda: False)
    layer.sync_animation()
    assert _alpha_at(layer, sun_x, sun_y) > 200


def test_full_width_ridge_stretches_with_header_width(qtbot):
    """신정 능선은 전체 폭 조각이라 머리줄이 넓어져도 끝까지 이어진다."""
    parent = _host(qtbot, 760, 104)
    layer = DecorationLayer("header", parent)
    layer.set_theme("newyear")
    layer.set_paused(True)
    for x in (5, 380, 755):
        assert _alpha_at(layer, x, 66) > 200, x


def test_layer_follows_parent_resize_and_dpr_cache(qtbot):
    parent = _host(qtbot, 380, 104)
    layer = DecorationLayer("header", parent)
    layer.set_theme("christmas")
    parent.resize(500, 90)
    assert layer.geometry() == parent.rect()
    layer.grab()
    assert layer._pixmaps          # 그림은 한 번 그려 캐시한다


# ── 메인 창 머리줄 ───────────────────────────────────────────────────

def test_header_layer_sits_below_controls(monkeypatch, win, qtbot):
    _wear(monkeypatch, win, "christmas")
    header = win._header_section
    layer = win._header_decor
    siblings = header.children()
    assert layer.parentWidget() is header
    assert siblings.index(layer) < siblings.index(win.month_label)
    assert siblings.index(layer) < siblings.index(win.prev_btn)
    assert layer.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert layer.theme_key() == "christmas"

    # 장식이 입혀져 있어도 이전 달 버튼이 눌린다.
    before = (win._current_year, win._current_month)
    QTest.mouseClick(win.prev_btn, Qt.LeftButton)
    after = (win._current_year, win._current_month)
    assert after != before


def test_header_anchors_follow_button_groups_in_all_sizes(monkeypatch, win):
    _wear(monkeypatch, win, "christmas")
    header = win._header_section
    layer = win._header_decor

    def x_of(widget):
        return widget.mapTo(header, QPoint(0, 0)).x()

    widths = []
    for scale in ("compact", "medium", "large"):
        db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
        assert win._apply_calendar_scale()
        QApplication.processEvents()
        anchors = layer.anchors()
        assert anchors["left_gap"] == pytest.approx(x_of(win._add_btn) + win._add_btn.width(), abs=1), scale
        assert anchors["center"] == pytest.approx(x_of(win.month_label) + win.month_label.width() / 2, abs=1), scale
        assert anchors["right_gap"] == pytest.approx(x_of(win.next_btn) + win.next_btn.width(), abs=1), scale
        assert anchors["right"] == pytest.approx(header.width(), abs=1), scale
        assert layer.geometry() == header.rect(), scale
        widths.append(header.width())
    assert widths[0] < widths[1]       # 크기를 바꾸면 머리줄 폭이 실제로 달라졌다


def test_header_corners_follow_sidebar_and_expanded_rules(monkeypatch, win):
    _wear(monkeypatch, win, "christmas")
    layer = win._header_decor
    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
    win._apply_calendar_scale()
    QApplication.processEvents()
    tl, tr, _br, _bl = layer._radii
    sidebar = win._header_section.property("sidebarActive") == "true"
    assert (tl, tr) == (0.0 if sidebar else 12.0, 12.0)
    db.save_setting(db.SETTING_CALENDAR_SCALE, "medium")
    win._apply_calendar_scale()
    QApplication.processEvents()
    tl, tr, _br, _bl = layer._radii
    assert (tl, tr) == (0.0, 0.0)      # 사이드바가 보이고 오른쪽도 확대 모양이다


def test_decor_never_covers_header_buttons_in_all_sizes(monkeypatch, win):
    """기본 크기는 버튼 사이 빈 곳이 거의 없어서 겹치는 조각은 줄거나 빠진다. 어느 크기에서도 겹치지 않는다."""
    layer = win._header_decor
    for scale in ("compact", "medium", "large"):
        db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
        win._apply_calendar_scale()
        QApplication.processEvents()
        for key in THEME_KEYS:
            _wear(monkeypatch, win, key)
            assert len(layer._blockers) >= 8, (scale, key)   # 버튼 7개 + 연월 글자
            sprites = layer._visible_sprites(layer._decor, layer.anchors(), layer._virtual_width())
            for sprite, rect in sprites:
                if is_backdrop("header", sprite.rect[2]):
                    continue                 # 넓은 옅은 배경(능선·빛줄기)은 버튼 뒤로 지나간다
                assert not any(_overlaps(rect, b) for b in layer._blockers), (scale, key, sprite.asset)


def test_wide_header_keeps_decor_that_compact_must_drop(monkeypatch, win):
    """기본 크기는 오른쪽 장식이 대부분 빠지고, 넓은 머리줄은 빈 곳에 그대로 놓인다."""
    _wear(monkeypatch, win, "seollal")
    layer = win._header_decor
    counts = {}
    for scale in ("compact", "medium"):
        db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
        win._apply_calendar_scale()
        QApplication.processEvents()
        counts[scale] = len(layer._visible_sprites(layer._decor, layer.anchors(), layer._virtual_width()))
    assert counts["medium"] == 2 and counts["compact"] < counts["medium"]


def test_lock_pauses_and_unlock_resumes_decorations(monkeypatch, app_dir, qtbot):
    db.create_sticky_note(note_type="memo", x=100, y=100)
    db.create_dday_widget("마감", "2030-01-01", color="#46679C")
    w = MainCalendarWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    _wear(monkeypatch, w, "christmas")
    floating = [layer for registry in (w._sticky_windows, w._dday_windows)
                for win in registry.values() for layer in win.findChildren(DecorationLayer)]
    assert len(floating) >= 2
    assert w._header_decor.is_animating()
    assert all(layer.theme_key() == "christmas" for layer in floating)
    movers = [layer for layer in floating if layer._has_motion]   # 눈이 내리는 D-Day 커버(스티키 띠는 정지 무늬)
    assert movers and all(layer.is_animating() for layer in movers)

    w._lock()
    assert w._holiday_theme.is_paused()
    assert w._header_decor.is_paused() and not w._header_decor.is_animating()
    assert all(layer.is_paused() and not layer.is_animating() for layer in floating)

    w._unlock()
    assert not w._holiday_theme.is_paused()
    assert w._header_decor.is_animating()
    assert not any(layer.is_paused() for layer in floating)
    assert all(layer.is_animating() for layer in movers)     # 다시 보인 위젯도 이어서 움직인다


def test_tray_hide_stops_and_restore_resumes_decorations(monkeypatch, win):
    _wear(monkeypatch, win, "christmas")
    assert win._header_decor.is_animating()
    win._minimize_to_tray()
    assert not win._header_decor.is_animating()
    win.toggle_visibility()
    QApplication.processEvents()
    assert win._header_decor.is_animating()


def test_minimized_window_stops_decorations(qtbot, monkeypatch):
    """최소화된 창은 isVisible()이 True여도 장식은 서 있다(작업 표시줄로 내려간 동안 돌지 않는다)."""
    parent = _host(qtbot)
    layer = DecorationLayer("header", parent)
    layer.set_theme("christmas")
    assert layer.is_animating()
    monkeypatch.setattr(QWidget, "isMinimized", lambda self: self is parent)
    layer.sync_animation()
    assert not layer.is_animating()
    monkeypatch.undo()
    layer.sync_animation()
    assert layer.is_animating()


def test_window_opened_while_locked_starts_paused(monkeypatch, win, qtbot):
    _wear(monkeypatch, win, "christmas")
    win._holiday_theme.set_paused(True)
    note_id = db.create_sticky_note(note_type="memo", x=0, y=0)
    sticky = StickyNoteWindow(note_id, {"content": "", "x_pos": 0, "y_pos": 0, "width": 300, "height": 220,
                                        "color": db.DEFAULT_STICKY_COLOR})
    qtbot.addWidget(sticky)
    win._register_floating_widget(sticky)
    layers = sticky.findChildren(DecorationLayer)
    assert layers and all(layer.is_paused() for layer in layers)   # 잠금 중 새로 열린 창도 멈춘 채


def test_theme_off_removes_all_decorations(monkeypatch, app_dir, qtbot):
    db.create_sticky_note(note_type="memo", x=100, y=100)
    db.create_dday_widget("마감", "2030-01-01", color="#46679C")
    w = MainCalendarWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    _wear(monkeypatch, w, "christmas")
    sticky = next(iter(w._sticky_windows.values()))
    dday = next(iter(w._dday_windows.values()))
    assert not w._header_decor.isHidden()
    assert not sticky.findChild(QLabel, "holidaySticker").isHidden()

    db.save_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "0")
    w._holiday_theme.refresh()
    QApplication.processEvents()
    assert w._header_decor.isHidden() and not w._header_decor.is_animating()
    for layer in sticky.findChildren(DecorationLayer) + dday.findChildren(DecorationLayer):
        assert layer.isHidden() and not layer.is_animating()
    assert sticky.findChild(QLabel, "holidaySticker").isHidden()


def test_render_three_scales_no_crash(monkeypatch, win):
    for scale in ("compact", "medium", "large"):
        db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
        assert win._apply_calendar_scale()
        QApplication.processEvents()
        for key in THEME_KEYS:
            _wear(monkeypatch, win, key)
            assert win._header_decor.theme_key() == key
            image = win.grab()
            assert not image.isNull(), (scale, key)


# ── D-Day ────────────────────────────────────────────────────────────

def test_dday_layer_sits_below_labels_and_is_created_once(qtbot):
    win = _dday_win(qtbot)
    win.show()
    qtbot.waitExposed(win)
    assert win.container.findChildren(DecorationLayer) == []        # 테마 전에는 레이어가 없다
    win.set_holiday_theme(THEMES["christmas"])
    win.set_holiday_theme(THEMES["christmas"])
    layers = win.container.findChildren(DecorationLayer)
    assert len(layers) == 1
    children = win.container.children()
    assert children.index(layers[0]) < children.index(win.name_label)
    assert children.index(layers[0]) < children.index(win.count_label)
    assert layers[0].geometry() == win.container.rect()
    assert layers[0].is_animating()                                  # 눈이 내린다

    win.set_holiday_theme(None)
    assert layers[0].isHidden() and not layers[0].is_animating()
    win.set_holiday_theme(THEMES["chuseok"])
    assert layers[0].theme_key() == "chuseok"
    assert len(win.container.findChildren(DecorationLayer)) == 1


# ── 스티키 띠와 스티커 ───────────────────────────────────────────────

def test_sticky_band_layer_and_sticker_created_once(qtbot):
    win = _sticky_win(qtbot)
    win.show()
    qtbot.waitExposed(win)
    assert win.header_widget.findChildren(DecorationLayer) == []
    win.set_holiday_theme(THEMES["christmas"])
    win.set_holiday_theme(THEMES["christmas"])
    layers = win.header_widget.findChildren(DecorationLayer)
    assert len(layers) == 1
    siblings = win.header_widget.children()
    assert siblings.index(layers[0]) < siblings.index(win.close_btn)
    assert siblings.index(layers[0]) < siblings.index(win.link_btn)
    stickers = win.findChildren(QLabel, "holidaySticker")
    assert len(stickers) == 1

    # 노트 본문·색은 그대로다.
    assert win.text_edit.toPlainText() == "메모"


def test_sticker_geometry_and_clicks(qtbot):
    win = _sticky_win(qtbot)
    win.show()
    qtbot.waitExposed(win)
    win.set_holiday_theme(THEMES["christmas"])
    sticker = win.findChild(QLabel, "holidaySticker")
    box = ui_holiday_decor.STICKER_BOX
    pad = ui_holiday_decor.STICKER_PAD
    assert sticker.isVisible()
    assert (sticker.width(), sticker.height()) == (box + 2 * pad, box + 2 * pad)
    assert sticker.testAttribute(Qt.WA_TransparentForMouseEvents)
    # 56px 그림이 본문 오른쪽 아래에서 10px 안쪽에 놓인다.
    assert sticker.x() + sticker.width() - pad == win.container.width() - 10
    assert sticker.y() + sticker.height() - pad == win.container.height() - 10
    assert sticker.pixmap() is not None and not sticker.pixmap().isNull()

    # 창 크기를 바꾸면 따라간다.
    win.resize(360, 260)
    QApplication.processEvents()
    assert sticker.x() + sticker.width() - pad == win.container.width() - 10
    assert sticker.y() + sticker.height() - pad == win.container.height() - 10

    # 스티커 위는 마우스를 통과해 아래 위젯(본문 편집기)이 받는다.
    center = sticker.mapTo(win, QPoint(sticker.width() // 2, sticker.height() // 2))
    target = win.childAt(center)
    assert target is not None and target is not sticker


def test_sticker_is_hidden_without_theme_and_not_on_mini_cards(qtbot):
    win = _sticky_win(qtbot)
    win.show()
    qtbot.waitExposed(win)
    assert win.findChild(QLabel, "holidaySticker").isHidden()        # 테마 전
    win.set_holiday_theme(THEMES["seollal"])
    assert not win.findChild(QLabel, "holidaySticker").isHidden()
    win.set_holiday_theme(None)
    assert win.findChild(QLabel, "holidaySticker").isHidden()

    note_id = db.create_sticky_note(note_type="memo", x=0, y=0)
    note = next(n for n in db.get_open_sticky_notes() if n["id"] == note_id)
    card = StickyMiniCard(note_id, note["content"], note["color"])
    qtbot.addWidget(card)
    card.set_holiday_theme(THEMES["christmas"])
    assert card.findChild(QLabel, "holidaySticker") is None
    assert card.findChildren(DecorationLayer) == []


def test_sticker_lettering_is_painted_for_hangul_and_constitution(monkeypatch):
    for key in ("hangul", "constitution"):
        with_text = sticker_pixmap(key, 1.0).toImage()
        monkeypatch.setattr(hd, "STICKER_BADGES", {})
        without = sticker_pixmap(key, 1.0).toImage()
        monkeypatch.undo()
        assert with_text.size() == without.size()
        assert with_text != without, key
    # 글자가 없는 스티커는 같다
    assert sticker_pixmap("christmas", 1.0).toImage() == sticker_pixmap("christmas", 1.0).toImage()


def test_sticker_pixmap_is_rotated_with_margin():
    """-6° 기울인 56px 그림이 62px 상자 안에 들어가 가장자리가 잘리지 않는다."""
    pix = sticker_pixmap("hangul", 1.0)
    image = pix.toImage().convertToFormat(QImage.Format_ARGB32)
    assert (image.width(), image.height()) == (ui_holiday_decor.STICKER_LABEL,) * 2
    edge = [QColor.fromRgba(image.pixel(x, y)).alpha()
            for x in range(image.width()) for y in range(image.height())
            if x in (0, image.width() - 1) or y in (0, image.height() - 1)]
    assert max(edge) == 0


def test_sticky_band_drops_pieces_that_do_not_fit_between_buttons(qtbot):
    """최소 폭(220)에서는 도구 버튼과 닫기 버튼 사이가 좁아 솔가지를 줄이거나 뺀다. 버튼은 덮지 않는다."""
    wide = _sticky_win(qtbot, width=300, height=220)
    wide.show()
    qtbot.waitExposed(wide)
    wide.set_holiday_theme(THEMES["christmas"])
    layer = wide.header_widget.findChild(DecorationLayer)
    QApplication.processEvents()
    pieces = layer._visible_sprites(layer._decor, layer.anchors(), layer._virtual_width())
    assert len(pieces) == 1 and pieces[0][1][2] == pytest.approx(46)   # 300px: 디자인 크기 그대로

    narrow = _sticky_win(qtbot, width=220, height=220)
    narrow.show()
    qtbot.waitExposed(narrow)
    narrow.set_holiday_theme(THEMES["christmas"])
    layer = narrow.header_widget.findChild(DecorationLayer)
    QApplication.processEvents()
    assert layer.width() == 220
    assert layer._visible_sprites(layer._decor, layer.anchors(), layer._virtual_width()) == []


def test_sticky_band_vertical_placement_uses_real_header_height(qtbot):
    """실제 머리띠(44px)는 디자인(30px)보다 높다. 능선은 아래에 붙고 위에 붙은 눈은 위에 붙는다."""
    win = _sticky_win(qtbot, width=300, height=220)
    win.show()
    qtbot.waitExposed(win)
    win.set_holiday_theme(THEMES["newyear"])
    layer = win.header_widget.findChild(DecorationLayer)
    QApplication.processEvents()
    assert layer._band_h == win.header_widget.height() > 30
    ridge = next(r for s, r in layer._visible_sprites(layer._decor, layer.anchors(), layer._virtual_width())
                 if s.asset == "newyear/sticky_band.svg")
    assert ridge[1] + ridge[3] == pytest.approx(layer._band_h)         # 능선 아래 끝 = 띠 아래 끝


# ── 집중 위젯의 프로펠러 ─────────────────────────────────────────────

def test_hat_svg_has_no_static_propeller():
    text = (resource_root() / "resources" / "holiday_themes" / "children" / "hat.svg").read_text(encoding="utf-8")
    assert "<ellipse" not in text
    assert 'cy="-11"' not in text and 'r="3.2"' not in text
    assert re.search(r'<rect x="48.5" y="-11"', text)                   # 깃대는 그대로


def test_children_hat_layer_draws_propeller_on_both_hat_labels(qtbot, monkeypatch):
    monkeypatch.setattr(ui_holiday_decor, "motion_allowed", lambda: False)   # 첫 장면에서도 보여야 한다
    win = _focus_win(qtbot)
    win.show()
    qtbot.waitExposed(win)
    win.set_holiday_theme(THEMES["children"])
    for display in ("ambient", "glance"):
        win._set_display_mode(display)
        QApplication.processEvents()
        label, box, offset = (
            (win._hat_mini_label, TOMATO_MINI_IMAGE_SIZE, HAT_OFFSET_UNITS["tomato_mini.png"])
            if display == "ambient"
            else (win._hat_label, TOMATO_IMAGE_SIZE, HAT_OFFSET_UNITS["tomato.png"])
        )
        layer = label.findChild(DecorationLayer)
        assert label.isVisible(), display
        assert layer is not None and layer.isVisible() and not layer.is_animating(), display
        assert layer.geometry() == label.rect(), display
        # 왼쪽 날개 중심(hat 공간 x 38.8, y 19)은 모자 그림과 같은 만큼 내려가 있다.
        k = box / 100.0
        x, y = round(38.8 * k), round((19 + offset) * k)
        image = label.grab().toImage().convertToFormat(QImage.Format_ARGB32)
        color = QColor.fromRgba(image.pixel(x, y))
        assert color.alpha() > 200 and color.green() > color.red(), (display, color.name())   # 초록 날개


def test_hat_layer_animates_only_for_children_and_while_visible(qtbot):
    win = _focus_win(qtbot)
    win.show()
    qtbot.waitExposed(win)
    win._set_display_mode("glance")
    win.set_holiday_theme(THEMES["children"])
    layer = win._hat_label.findChild(DecorationLayer)
    assert layer.is_animating()
    win.set_holiday_theme(THEMES["children"])               # 같은 테마를 또 입혀도 레이어는 하나
    assert len(win._hat_label.findChildren(DecorationLayer)) == 1 and layer.is_animating()

    win.set_holiday_theme(THEMES["christmas"])               # 프로펠러는 어린이날 모자뿐
    assert layer.isHidden() and not layer.is_animating()
    win.set_holiday_theme(THEMES["children"])
    assert layer.is_animating()
    win.hide()
    assert not layer.is_animating()
    win.set_holiday_theme(None)
    assert layer.isHidden()


def test_decor_is_display_only_and_never_writes_db(monkeypatch, app_dir, qtbot):
    writers = [name for name in dir(db)
               if name.startswith(("save_", "update_", "create_", "add_", "delete_", "trash_",
                                   "restore_", "import_", "reset_", "backup_"))
               and callable(getattr(db, name))]
    sticky = _sticky_win(qtbot)
    dday = _dday_win(qtbot)
    focus = _focus_win(qtbot)

    def boom(*args, **kwargs):
        raise AssertionError("장식이 DB에 쓰려 했다")

    with monkeypatch.context() as scoped:
        for name in writers:
            scoped.setattr(db, name, boom)
        for key in THEME_KEYS:
            for window in (sticky, dday, focus):
                window.set_holiday_theme(THEMES[key])
        for window in (sticky, dday, focus):
            window.set_holiday_theme(None)
