"""새 버전 알림의 메인 창 연결: 빨간 점(②③), 잠금·가져오기·초기화와 함께 움직인다."""
from datetime import date

import pytest
from PySide6.QtCore import QPoint, QRect, Qt

import database as db
import holiday_theme as ht
import ui_update
import update_check
from app_info import APP_VERSION
from holidays import KOREAN_HOLIDAYS
from ui_main import MainCalendarWindow, NAVY
from ui_update import GITLAB_LATEST_URL, TOAST_WIDTH, UpdateDot, UpdateToast
from update_check import CheckResult


@pytest.fixture(autouse=True)
def no_network(app_dir, monkeypatch):  # 키를 켠 테스트의 예약이 울려도 나가지 않게 한다
    monkeypatch.setattr(update_check, "check_latest", lambda opener=None: CheckResult())


@pytest.fixture
def opened(monkeypatch):
    """브라우저 열기를 가로챈다. 테스트가 실제 브라우저를 띄우지 않게 한다."""
    urls = []

    class FakeDesktop:
        @staticmethod
        def openUrl(url):
            urls.append(url.toString())
            return True

    monkeypatch.setattr(ui_update, "QDesktopServices", FakeDesktop)
    return urls


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


# ── ① 처음 발견 알림 ──────────────────────────────────────

def _toast(win, tag="v4.7") -> UpdateToast:
    win._update_check._set_latest(tag)
    assert isinstance(win._update_toast, UpdateToast)
    return win._update_toast


@pytest.mark.parametrize(("sidebar", "law", "expected"), [
    ("1", "1", (96, 112)), ("0", "1", (16, 112)), ("1", "0", (96, 60))])
def test_toast_position_default_size(qtbot, app_dir, sidebar, law, expected):
    win = _make(qtbot, **{db.SETTING_CALENDAR_SCALE: "compact", db.SETTING_SHOW_SIDEBAR: sidebar,
                          db.SETTING_SHOW_LAW_SEARCH: law})
    toast = _toast(win)
    assert toast.parent() is win.container
    assert (toast.x(), toast.y()) == expected
    assert toast.width() == TOAST_WIDTH == 348


def test_toast_stays_centered_after_scale_change(qtbot, app_dir):
    win = _make(qtbot, **{db.SETTING_CALENDAR_SCALE: "compact"})
    toast = _toast(win)
    db.save_setting(db.SETTING_CALENDAR_SCALE, "medium")
    win._apply_calendar_scale()
    header = win._header_section

    def centered():
        below = header.mapTo(win.container, QPoint(0, header.height())).y() + 8
        return (abs(toast.geometry().center().x() - win.right_content.geometry().center().x()) <= 1
                and toast.y() == below)

    qtbot.waitUntil(centered)


def test_toast_content(qtbot, app_dir):
    toast = _toast(_make(qtbot))
    assert toast.title_label.text() == "새 버전 v4.7이 나왔습니다"
    assert toast.title_label.font().pixelSize() == 14
    assert toast.sub_label.text() == f"지금 쓰는 버전 {APP_VERSION}"
    assert toast.get_button.text() == "받기" and toast.get_button.height() == 32
    assert toast.close_button.accessibleName() == "알림 닫기"
    assert (toast.close_button.width(), toast.close_button.height()) == (32, 32)


def test_long_tag_fits_toast(qtbot, app_dir):
    win = _make(qtbot, **{db.SETTING_CALENDAR_SCALE: "compact", db.SETTING_SHOW_SIDEBAR: "0"})
    toast = _toast(win, "v4.10a")
    qtbot.waitUntil(toast.isVisible)
    assert toast.title_label.width() >= toast.title_label.sizeHint().width()
    assert toast.get_button.geometry().right() < toast.close_button.geometry().left()
    assert toast.close_button.geometry().right() < TOAST_WIDTH


def test_get_button_opens_page_and_closes(qtbot, app_dir, opened):
    win = _make(qtbot)
    toast = _toast(win)
    qtbot.mouseClick(toast.get_button, Qt.LeftButton)
    assert opened == [GITLAB_LATEST_URL]
    assert win._update_toast is None


def test_close_button_does_not_open_browser(qtbot, app_dir, opened):
    win = _make(qtbot)
    toast = _toast(win)
    qtbot.mouseClick(toast.close_button, Qt.LeftButton)
    assert opened == [] and win._update_toast is None


def test_toast_closes_after_ten_seconds(qtbot, app_dir):
    win = _make(qtbot)
    toast = _toast(win)
    assert toast._timer.interval() == 10_000 and toast._timer.isActive() and toast._timer.isSingleShot()
    toast._timer.timeout.emit()
    assert win._update_toast is None


def test_toast_once_per_run(qtbot, app_dir):
    win = _make(qtbot)
    _toast(win, "v4.7").close()
    win._update_check._set_latest("v4.8")
    assert win._update_toast is None
    assert win._update_dot.isVisible() and win._update_check.latest == "v4.8"


def test_hidden_then_shown(qtbot, app_dir):
    win = _make(qtbot)
    win._minimize_to_tray()
    win._update_check._set_latest("v4.7")
    assert win._update_toast is None
    win.toggle_visibility()
    qtbot.waitUntil(lambda: win._update_toast is not None)


def test_locked_then_unlocked(qtbot, app_dir):
    win = _make(qtbot)
    win._lock()
    win._update_check._set_latest("v4.7")
    assert win._update_toast is None
    win._unlock()
    assert win._update_toast is not None


def test_locked_and_hidden_waits_for_both(qtbot, app_dir):
    win = _make(qtbot)
    win._lock()
    win._minimize_to_tray()
    win._update_check._set_latest("v4.7")
    win.toggle_visibility()
    qtbot.wait(50)
    assert win._update_toast is None
    win._unlock()
    assert win._update_toast is not None


def test_lock_closes_visible_toast_without_repeat(qtbot, app_dir):
    win = _make(qtbot)
    _toast(win)
    win._lock()
    assert win._update_toast is None
    win._unlock()
    assert win._update_toast is None


def test_tray_closes_visible_toast(qtbot, app_dir):
    win = _make(qtbot)
    _toast(win)
    win._minimize_to_tray()
    assert win._update_toast is None
    win.toggle_visibility()
    qtbot.wait(50)
    assert win._update_toast is None


def test_turning_off_closes_toast(qtbot, app_dir):
    win = _make(qtbot, **{db.SETTING_INTERNET_ACCESS: "1"})
    _toast(win)
    db.save_setting(db.SETTING_INTERNET_ACCESS, "0")
    win._update_check.apply_setting()
    assert win._update_toast is None and not win._update_dot.isVisible()


def test_quit_stops_everything(qtbot, app_dir):
    win = _make(qtbot, **{db.SETTING_INTERNET_ACCESS: "1"})
    qtbot.waitUntil(win._update_check._timer.isActive)
    _toast(win)
    assert win.prepare_for_quit()
    assert not win._update_check._timer.isActive() and win._update_toast is None
