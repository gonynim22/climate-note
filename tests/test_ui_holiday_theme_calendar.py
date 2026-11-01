"""v4.6 공휴일 테마: 캘린더 머리줄·오늘 칸·공휴일 칸·인사말과 컨트롤러(Task 3).

날짜는 holiday_theme.current_match를 패치해 정한다. 테마는 화면 전용이므로 모든 검사는
합성 데이터(app_dir)에서 하고, 테마 적용·해제가 DB에 아무것도 쓰지 않는지도 확인한다.
"""
from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

import database as db
import holiday_theme as ht
from holidays import KOREAN_HOLIDAYS
from ui_holiday_theme import HolidayThemeController
from ui_main import CalendarDayButton, MainCalendarWindow, header_section_qss


@pytest.fixture(autouse=True)
def quiet_desktop(app_dir):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")


def _patch_only(monkeypatch, day):
    """'오늘'의 판정 결과만 day로 바꾼다. refresh()는 부르지 않는다."""
    fixed = ht.resolve_holiday_theme(date.fromisoformat(day), KOREAN_HOLIDAYS)
    monkeypatch.setattr(ht, "current_match", lambda today=None: fixed)
    return fixed


def _at(monkeypatch, win, day):
    """'오늘'을 day로 바꾸고 테마를 다시 판정한다."""
    _patch_only(monkeypatch, day)
    win._holiday_theme.refresh()
    QApplication.processEvents()


@pytest.fixture
def win(qtbot, app_dir):
    w = MainCalendarWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def _go_to_month(win, year, month):
    win._current_year, win._current_month = year, month
    win._refresh_calendar()
    QApplication.processEvents()


def _dot(cell):
    return cell.findChild(QWidget, "holidayThemeDot")


def test_header_uses_theme_color_and_restores_when_disabled(monkeypatch, win):
    _at(monkeypatch, win, "2026-12-25")
    win._holiday_theme.refresh()
    assert "#1D4A3A" in win._header_section.styleSheet()

    db.save_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "0")
    win._holiday_theme.refresh()
    assert "#01295F" in win._header_section.styleSheet()
    assert "#1D4A3A" not in win._header_section.styleSheet()


def test_header_qss_keeps_corner_rules():
    """머리줄 배경만 인자고, 사이드바·확대 때 모서리 규칙은 그대로다."""
    qss = header_section_qss("#123456")
    assert "background: #123456;" in qss
    assert '#headerSection[sidebarActive="true"]' in qss
    assert '#headerSection[expanded="true"]' in qss
    assert "#01295F" not in qss


def test_today_cell_uses_theme_today_color(monkeypatch, win):
    _at(monkeypatch, win, "2027-01-01")
    today_cell = win._day_cells[date.today().isoformat()]
    assert today_cell._is_today
    assert "#B9502C" in today_cell.styleSheet()

    # 중간·크게는 숫자 원이 오늘 색이다.
    cell = CalendarDayButton(
        1, True, [], True, "2027-01-01", False, 5, 0, "expanded",
        today_color="#B9502C", calendar_scale="medium",
    )
    assert "#B9502C" in cell.day_label.styleSheet()
    assert "#01295F" not in cell.day_label.styleSheet()


def test_today_cell_default_color_without_theme(win):
    today_cell = win._day_cells[date.today().isoformat()]
    assert "#01295F" in today_cell.styleSheet()


def test_holiday_group_cells_tinted_with_dot(monkeypatch, win):
    _at(monkeypatch, win, "2027-02-07")
    _go_to_month(win, 2027, 2)
    for day in (6, 7, 8, 9):
        cell = win._day_cells[f"2027-02-{day:02d}"]
        assert "#FBEDF1" in cell.styleSheet(), day
        dot = _dot(cell)
        assert dot is not None and dot.isVisible(), day
        assert (dot.width(), dot.height()) == (6, 6)
        # 오른쪽 위에서 5px 안쪽이다.
        assert dot.x() + dot.width() == cell.width() - 5
        assert dot.y() == 5
    other = win._day_cells["2027-02-05"]
    assert "#FBEDF1" not in other.styleSheet()
    assert _dot(other) is None


def test_other_holidays_in_same_month_keep_plain_style(monkeypatch, win):
    """고른 테마 묶음이 아닌 공휴일(삼일절)은 기존 빨간 글자만 쓴다."""
    _at(monkeypatch, win, "2027-02-07")
    _go_to_month(win, 2027, 3)
    cell = win._day_cells["2027-03-01"]
    assert _dot(cell) is None
    assert "#FBEDF1" not in cell.styleSheet()
    assert "#D32F2F" in cell.day_label.styleSheet()


def test_holiday_cell_tint_follows_theme_in_expanded_scale(monkeypatch, app_dir, qtbot):
    db.save_setting(db.SETTING_CALENDAR_SCALE, "medium")
    w = MainCalendarWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    _at(monkeypatch, w, "2027-02-07")
    _go_to_month(w, 2027, 2)
    cell = w._day_cells["2027-02-08"]
    assert "#FBEDF1" in cell.styleSheet()
    assert _dot(cell) is not None and _dot(cell).isVisible()
    # 숫자 글자는 기존 공휴일 빨강을 그대로 쓴다.
    assert "#D32F2F" in cell.day_label.styleSheet()


def test_tinted_cell_selected_keeps_selection_fill(monkeypatch, win):
    _at(monkeypatch, win, "2027-02-07")
    _go_to_month(win, 2027, 2)
    cell = win._day_cells["2027-02-08"]
    cell.set_selected(True)
    assert "rgba(1,41,95,20)" in cell.styleSheet()
    assert "#FBEDF1" not in cell.styleSheet()
    cell.set_selected(False)
    assert "#FBEDF1" in cell.styleSheet()


def test_today_cell_in_holiday_group_is_not_tinted(monkeypatch, win):
    """오늘 칸은 오늘 색만 쓰고 공휴일 바탕·점을 겹치지 않는다."""
    today = date.today()
    key = today.isoformat()
    fixed = ht.resolve_holiday_theme(date(2027, 2, 7), KOREAN_HOLIDAYS)
    # 오늘을 묶음 날짜에 넣은 합성 판정 결과
    synthetic = ht.HolidayThemeMatch(
        theme=fixed.theme, first_day=today, last_day=today,
        dates=(today,), in_holiday=True,
    )
    monkeypatch.setattr(ht, "current_match", lambda t=None: synthetic)
    win._holiday_theme.refresh()
    QApplication.processEvents()
    cell = win._day_cells[key]
    assert _dot(cell) is None
    assert fixed.theme.tint not in cell.styleSheet()
    assert fixed.theme.today in cell.styleSheet()


def test_greeting_only_in_holiday(monkeypatch, win):
    _at(monkeypatch, win, "2027-02-04")
    assert win.holiday_greeting_label.text() == ""
    _at(monkeypatch, win, "2027-02-07")
    assert win.holiday_greeting_label.text() == "새해 복 많이 받으세요"
    assert "#8E2A4E" in win.holiday_greeting_label.styleSheet()
    _at(monkeypatch, win, "2026-12-21")
    assert win.holiday_greeting_label.text() == ""


def test_greeting_sits_right_before_count_label(win):
    label = win.holiday_greeting_label
    layout = win.schedule_panel.layout().itemAt(0).layout()  # date_row
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert widgets.index(label) + 1 == widgets.index(win.count_label)
    assert "font-size: 11px" in label.styleSheet()
    assert "font-weight: bold" in label.styleSheet()


def test_month_navigation_keeps_today_theme(monkeypatch, win):
    _at(monkeypatch, win, "2026-12-25")
    win._on_next_month()
    QApplication.processEvents()
    assert "#1D4A3A" in win._header_section.styleSheet()
    win._on_prev_month()
    win._on_prev_month()
    assert "#1D4A3A" in win._header_section.styleSheet()


def test_rollover_and_tray_return_refresh_theme(monkeypatch, win):
    _at(monkeypatch, win, "2026-12-21")  # 테마 없음
    assert win._holiday_theme.match() is None
    assert "#01295F" in win._header_section.styleSheet()

    _patch_only(monkeypatch, "2026-12-22")
    win._today = "2000-01-01"
    win._check_day_rollover()
    assert "#1D4A3A" in win._header_section.styleSheet()

    _patch_only(monkeypatch, "2026-12-26")
    win._today = "2000-01-01"
    win.hide()
    win._sync_to_today_if_changed()
    assert "#01295F" in win._header_section.styleSheet()


def test_same_day_check_does_not_rebuild_calendar(monkeypatch, win):
    """같은 날 재판정은 신호도, 달력 다시 만들기도 일으키지 않는다."""
    _at(monkeypatch, win, "2026-12-25")
    calls = []
    original = win._refresh_calendar
    monkeypatch.setattr(win, "_refresh_calendar", lambda: calls.append(1) or original())
    win._holiday_theme.refresh()
    win._holiday_theme.refresh()
    assert calls == []


def test_on_today_refreshes_theme(monkeypatch, win):
    _at(monkeypatch, win, "2026-12-21")
    _patch_only(monkeypatch, "2026-12-25")
    win._on_today()
    assert "#1D4A3A" in win._header_section.styleSheet()


def test_settings_callback_refreshes(monkeypatch, win):
    win._on_settings()
    assert win._settings_window.on_holiday_theme_changed == win._on_holiday_theme_setting_changed

    _patch_only(monkeypatch, "2026-12-25")
    win._on_holiday_theme_setting_changed()
    assert "#1D4A3A" in win._header_section.styleSheet()


def test_settings_switch_off_restores_navy(monkeypatch, win):
    _at(monkeypatch, win, "2026-12-25")
    win._on_settings()
    win._settings_window.holiday_theme_switch.setChecked(False)
    QApplication.processEvents()
    assert "#01295F" in win._header_section.styleSheet()
    assert win._holiday_theme.match() is None
    assert win.holiday_greeting_label.text() == ""


def test_theme_apply_writes_nothing(monkeypatch, win):
    writers = [
        name for name in dir(db)
        if name.startswith(("save_", "update_", "create_", "add_", "delete_", "trash_",
                            "restore_", "import_", "reset_", "backup_"))
        and callable(getattr(db, name))
    ]
    assert "save_setting" in writers and "update_dday_widget" in writers

    def boom(*args, **kwargs):
        raise AssertionError("테마 적용이 DB에 쓰려 했다")

    with monkeypatch.context() as scoped:
        for name in writers:
            scoped.setattr(db, name, boom)
        for day in ("2026-12-21", "2026-12-25", "2027-01-01", "2027-02-07", "2027-05-04",
                    "2026-12-21"):
            _at(scoped, win, day)
        win._holiday_theme.set_paused(True)
        win._holiday_theme.set_paused(False)


def test_default_theme_enabled_when_setting_missing(monkeypatch, app_dir, qtbot):
    """키가 없으면 켜짐이다. 시작할 때 이미 판정해 화면에 입힌다."""
    _patch_only(monkeypatch, "2026-12-25")
    w = MainCalendarWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    assert w._holiday_theme.match() is not None
    assert "#1D4A3A" in w._header_section.styleSheet()


def test_disabled_at_startup_has_no_theme(monkeypatch, app_dir, qtbot):
    db.save_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "0")
    _patch_only(monkeypatch, "2026-12-25")
    w = MainCalendarWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    assert w._holiday_theme.match() is None
    assert "#01295F" in w._header_section.styleSheet()


# ── 컨트롤러 단위 검사 ────────────────────────────────────────────────

def test_controller_emits_only_when_state_changes(monkeypatch, app_dir, qtbot):
    controller = HolidayThemeController()
    received = []
    controller.themeChanged.connect(received.append)

    _patch_only(monkeypatch, "2026-12-21")
    controller.refresh()
    assert received == [] and controller.match() is None and controller.theme() is None

    _patch_only(monkeypatch, "2026-12-22")  # 예고 기간
    controller.refresh()
    assert len(received) == 1
    assert controller.match().theme.key == "christmas"
    assert controller.theme().key == "christmas"
    assert controller.match().in_holiday is False

    _patch_only(monkeypatch, "2026-12-23")  # 같은 묶음·같은 상태
    controller.refresh()
    assert len(received) == 1

    _patch_only(monkeypatch, "2026-12-25")  # 예고 → 공휴일 당일(in_holiday 변경)
    controller.refresh()
    assert len(received) == 2 and received[-1].in_holiday is True

    _patch_only(monkeypatch, "2026-12-26")
    controller.refresh()
    assert len(received) == 3 and received[-1] is None


def test_controller_off_returns_none_without_calling_current_match(monkeypatch, app_dir, qtbot):
    db.save_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "0")
    controller = HolidayThemeController()
    calls = []
    monkeypatch.setattr(ht, "current_match", lambda today=None: calls.append(1))
    controller.refresh()
    assert controller.match() is None
    assert calls == []


def test_controller_paused_state_and_signal(app_dir, qtbot):
    controller = HolidayThemeController()
    seen = []
    controller.pausedChanged.connect(seen.append)
    assert controller.is_paused() is False
    controller.set_paused(True)
    controller.set_paused(True)  # 같은 값은 다시 알리지 않는다
    assert controller.is_paused() is True
    controller.set_paused(False)
    assert seen == [True, False]


# ── 인사말 자리 규칙: 전체가 들어가면 보이고, 모자라면 숨긴다 ───────────────────
# 중간·크게의 일정 패널 폭은 창이 자리를 잡는 동안 300~343px로 달라지므로, 폭을 가정하지 않는
# 내용(들어가는 날 / 확실히 안 들어가는 날)을 고르고 창이 자리 잡은 뒤에 확인한다.

DATE_ROW_LABELS = ("selected_date_label", "lunar_info_label", "holiday_info_label", "count_label")


def _window_at(qtbot, scale, show_lunar):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    db.save_setting(db.SETTING_SHOW_LUNAR, "1" if show_lunar else "0")
    w = MainCalendarWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    qtbot.wait(500)  # 크게 보기는 시작 직후 늦게 도는 정리가 있어 끝난 뒤에 시작한다
    return w


def _select_day(w, day):
    """그 달로 가서 그 날을 고른다(날짜·음력·공휴일명·개수 라벨이 바뀐다)."""
    parsed = date.fromisoformat(day)
    _go_to_month(w, parsed.year, parsed.month)
    w._on_date_selected(day)
    QApplication.processEvents()


def _label_widths(w):
    return {name: getattr(w, name).width() for name in DATE_ROW_LABELS}


def _widths_without_greeting(w):
    """인사말 문구를 비운 같은 배치에서의 날짜 줄 폭(인사말이 다른 글자를 줄였는지 비교용)."""
    text = w.holiday_greeting_label.text()
    w.holiday_greeting_label.setText("")
    QApplication.processEvents()
    widths = _label_widths(w)
    w.holiday_greeting_label.setText(text)
    QApplication.processEvents()
    return widths


def _accent_pixels(label, accent):
    image = label.grab().toImage()
    ar, ag, ab = (int(accent[i:i + 2], 16) for i in (1, 3, 5))
    count = 0
    for x in range(image.width()):
        for y in range(image.height()):
            color = image.pixelColor(x, y)
            if (abs(color.red() - ar) < 40 and abs(color.green() - ag) < 40
                    and abs(color.blue() - ab) < 40):
                count += 1
    return count


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_greeting_shown_in_full_when_it_fits(monkeypatch, app_dir, qtbot, scale):
    """오늘이 설날이고 고른 날이 평범한 날(공휴일명·음력·개수 없음)이면 인사말이 전체로 들어간다."""
    w = _window_at(qtbot, scale, show_lunar=False)
    _patch_only(monkeypatch, "2027-02-07")
    w._holiday_theme.refresh()
    _select_day(w, "2027-02-10")
    label = w.holiday_greeting_label
    qtbot.waitUntil(label.isVisible, timeout=3000)
    assert label.text() == "새해 복 많이 받으세요"
    assert label.width() >= label.sizeHint().width()  # 말줄임 없이 전체 폭
    assert _accent_pixels(label, "#8E2A4E") > 0
    assert label.toolTip() == ""  # 전체가 보이므로 툴팁은 필요 없다
    assert _label_widths(w) == _widths_without_greeting(w)  # 날짜 줄 다른 글자는 줄지 않는다


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_greeting_hidden_when_it_does_not_fit_and_dates_unchanged(
        monkeypatch, app_dir, qtbot, scale):
    """음력 켬 + 공휴일 당일 + 일정이 있으면 인사말이 안 들어간다: 토막 없이 숨기고 날짜 줄은 그대로."""
    for index in range(3):
        db.add_schedule("2026-12-25", f"일정 {index}", "#4CC9F0")
    w = _window_at(qtbot, scale, show_lunar=True)
    _patch_only(monkeypatch, "2026-12-25")
    w._holiday_theme.refresh()
    _select_day(w, "2026-12-25")
    qtbot.wait(300)
    label = w.holiday_greeting_label
    assert label.text() == "메리 크리스마스"  # 문구는 그대로 두고 보이기만 끈다
    assert label.isHidden() and not label.isVisible()
    assert w.count_label.text() == "총 3개" and w.holiday_info_label.text()
    assert _label_widths(w) == _widths_without_greeting(w)  # 날짜·음력·공휴일명·개수는 그대로
    if scale == "compact":  # 기본 크기 패널은 인사말 없이는 네 글자가 다 들어간다
        for name in DATE_ROW_LABELS:
            widget = getattr(w, name)
            assert widget.width() >= widget.sizeHint().width(), name


def test_greeting_follows_row_content_and_panel_width(monkeypatch, app_dir, qtbot):
    """날짜 줄 글자(일정 추가·삭제)나 패널 폭이 바뀌면 인사말이 다시 보이거나 숨는다."""
    w = _window_at(qtbot, "compact", show_lunar=True)
    _patch_only(monkeypatch, "2027-02-07")
    w._holiday_theme.refresh()
    _select_day(w, "2027-02-07")
    label = w.holiday_greeting_label
    assert label.isVisible()  # 설날 + 음력만이면 들어간다

    db.add_schedule("2027-02-07", "일정", "#4CC9F0")
    w._load_schedules()
    QApplication.processEvents()
    assert w.count_label.text() == "총 1개"
    assert label.isHidden()

    ids = [w.schedule_list.item(index).data(Qt.UserRole)
           for index in range(w.schedule_list.count())]
    for schedule_id in ids:
        db.delete_schedule(schedule_id)
    w._load_schedules()
    QApplication.processEvents()
    assert w.count_label.text() == ""
    assert label.isVisible()

    # 패널 폭이 좁아지면 숨고, 다시 넓어지면 나타난다.
    _select_day(w, "2027-02-10")
    assert label.isVisible()
    w.schedule_panel.setFixedWidth(230)
    QApplication.processEvents()
    assert label.isHidden()
    w.schedule_panel.setMinimumWidth(0)
    w.schedule_panel.setMaximumWidth(16777215)
    w.layout().activate()
    QApplication.processEvents()
    qtbot.waitUntil(label.isVisible, timeout=3000)


def test_greeting_label_paints_nothing_when_narrower_than_text(app_dir, qtbot):
    """자리 판단이 늦는 순간에도 토막 글자나 말줄임 표시를 그리지 않는다."""
    from ui_main import HolidayGreetingLabel
    label = HolidayGreetingLabel("메리 크리스마스")
    qtbot.addWidget(label)
    label.setStyleSheet("color: #8E2A4E; background: white; font-weight: bold; font-size: 11px;")
    assert label.minimumSizeHint().width() == 0
    label.resize(label.sizeHint())
    assert _accent_pixels(label, "#8E2A4E") > 0
    label.resize(label.sizeHint().width() - 6, label.sizeHint().height())
    assert _accent_pixels(label, "#8E2A4E") == 0
