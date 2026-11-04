"""새 버전 알림의 메인 창 연결: 빨간 점(②③), 잠금·가져오기·초기화와 함께 움직인다."""
from datetime import date

import pytest
from PySide6.QtCore import QPoint, QRect, Qt

import database as db
import holiday_theme as ht
import update_check
from holidays import KOREAN_HOLIDAYS
from ui_main import MainCalendarWindow, NAVY
from ui_update import UpdateDot
from update_check import CheckResult


@pytest.fixture(autouse=True)
def no_network(app_dir, monkeypatch):  # 키를 켠 테스트의 예약이 울려도 나가지 않게 한다
    monkeypatch.setattr(update_check, "check_latest", lambda opener=None: CheckResult())


def _make(qtbot, **settings):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    for key, value in settings.items():
        db.save_setting(key, value)
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win


def _pixel(widget, x, y):
    image = widget.grab().toImage()
    ratio = image.devicePixelRatio()
    return image.pixelColor(int(x * ratio), int(y * ratio)).name().upper()


def test_no_new_version_no_dots(qtbot, app_dir):
    win = _make(qtbot)
    assert not win._update_dot.isVisible()
    assert win._build_more_menu().findChildren(UpdateDot) == []


def test_more_button_dot_position_and_colors(qtbot, app_dir):
    win = _make(qtbot)
    win._update_check._set_latest("v4.7")
    dot = win._update_dot
    assert dot.isVisible()
    assert dot.parent() is win._more_btn
    assert dot.geometry() == QRect(18, 2, 12, 12)
    assert dot.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert _pixel(dot, 6, 6) == "#F04438"
    assert _pixel(dot, 1, 6) == "#01295F"


def test_dot_disappears_with_latest(qtbot, app_dir):
    win = _make(qtbot)
    win._update_check._set_latest("v4.7")
    win._update_check._set_latest(None)
    assert not win._update_dot.isVisible()


def test_dot_ring_follows_holiday_header(qtbot, app_dir, monkeypatch):
    win = _make(qtbot)
    match = ht.resolve_holiday_theme(date(2026, 12, 25), KOREAN_HOLIDAYS)
    monkeypatch.setattr(ht, "current_match", lambda today=None: match)
    win._holiday_theme.refresh()
    assert win._update_dot.ring_color() == match.theme.header
    monkeypatch.setattr(ht, "current_match", lambda today=None: None)
    win._holiday_theme.refresh()
    assert win._update_dot.ring_color() == NAVY


def test_menu_dot_sits_on_update_icon(qtbot, app_dir):
    win = _make(qtbot)
    win._update_check._set_latest("v4.7")
    menu = win._build_more_menu()
    actions = [a for a in menu.menuActions() if not a.isSeparator()]
    assert [a.text() for a in actions] == ["자동정렬", "앱 업데이트", "휴지통", "설정", "앱 최소화"]
    dots = menu.findChildren(UpdateDot)
    assert len(dots) == 1
    assert dots[0].parent() is menu.view.viewport()
    assert (dots[0].width(), dots[0].height()) == (11, 11)
    item_top_left = menu.view.visualItemRect(actions[1].property("item")).topLeft()
    assert dots[0].pos() == item_top_left + QPoint(27, 3)
    assert dots[0].ring_color() == "#FFFFFF"


def test_update_guide_receives_latest(qtbot, app_dir, monkeypatch):
    calls = []
    monkeypatch.setattr("ui_main.show_update_guide", lambda parent, latest=None: calls.append((parent, latest)))
    win = _make(qtbot)
    win._update_check._set_latest("v4.7")
    menu = win._build_more_menu()
    [a for a in menu.menuActions() if not a.isSeparator()][1].trigger()
    assert calls == [(win, "v4.7")]


def test_lock_overlay_covers_dot(qtbot, app_dir):
    win = _make(qtbot)
    win._update_check._set_latest("v4.7")
    win._lock()
    spot = win.container.mapFromGlobal(win._update_dot.mapToGlobal(QPoint(6, 6)))
    top = win.container.childAt(spot)
    assert top is win.lock_overlay or win.lock_overlay.isAncestorOf(top)


def test_import_keeps_and_reset_clears(qtbot, app_dir):
    win = _make(qtbot, **{db.SETTING_INTERNET_ACCESS: "1"})
    win._update_check._set_latest("v4.7")
    win._on_import_complete()
    assert win._update_check.latest == "v4.7" and win._update_dot.isVisible()
    db.reset_database()
    win._on_factory_reset()
    assert win._update_check.latest is None and not win._update_dot.isVisible()
