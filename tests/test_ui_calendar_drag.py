from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

import database as db
from ui_main import (
    MainCalendarWindow,
    _clamp_calendar_xy,
    _clamp_window_to_available_screens,
    _nearest_corner_for_rect,
    _snap_px_for_screen,
)


class _MouseEvent:
    def __init__(self, event_type, global_pos, button=Qt.NoButton, buttons=Qt.NoButton):
        self._event_type = event_type
        self._global_pos = QPointF(global_pos)
        self._button = button
        self._buttons = buttons
        self.accepted = False

    def type(self):
        return self._event_type

    def globalPosition(self):
        return self._global_pos

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def accept(self):
        self.accepted = True


class _FakeScreen:
    def __init__(self, geometry):
        self._geometry = geometry

    def availableGeometry(self):
        return self._geometry


class _FakeSignal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback


def test_clamp_calendar_xy_supports_negative_monitor_coordinates():
    geometry = QRect(-1920, 0, 1920, 1080)

    assert _clamp_calendar_xy(-2200, -100, 380, 660, geometry) == (-1920, 0)
    assert _clamp_calendar_xy(-100, 900, 380, 660, geometry) == (-380, 420)


def test_floating_clamp_checks_entire_window_rect(qtbot):
    win = QWidget()
    qtbot.addWidget(win)
    win.resize(300, 200)
    win.move(1200, 100)
    screen = _FakeScreen(QRect(0, 0, 1280, 720))

    assert _clamp_window_to_available_screens(win, [screen]) is True
    assert (win.x(), win.y()) == (980, 100)


def test_floating_clamp_keeps_fully_visible_negative_screen_window(qtbot):
    win = QWidget()
    qtbot.addWidget(win)
    win.resize(300, 200)
    win.move(-800, 100)
    screens = [
        _FakeScreen(QRect(-1920, 0, 1920, 1080)),
        _FakeScreen(QRect(0, 0, 1920, 1080)),
    ]

    assert _clamp_window_to_available_screens(win, screens) is False
    assert (win.x(), win.y()) == (-800, 100)


def test_nearest_corner_uses_actual_calendar_position():
    screen = (0, 0, 1920, 1080)

    assert _nearest_corner_for_rect((100, 100, 480, 760), screen) == "top-left"
    assert _nearest_corner_for_rect((1400, 500, 1780, 1060), screen) == "bottom-right"


def test_header_drag_moves_and_persists_free_position(app_dir, qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()

    start_x, start_y = win.x(), win.y()
    press_at = QPointF(start_x + 120, start_y + 20)
    move_to = QPointF(press_at.x() - 90, press_at.y() - 55)

    press = _MouseEvent(
        QEvent.Type.MouseButtonPress,
        press_at,
        button=Qt.LeftButton,
        buttons=Qt.LeftButton,
    )
    assert win.eventFilter(win.month_label, press) is True
    assert press.accepted

    move = _MouseEvent(
        QEvent.Type.MouseMove,
        move_to,
        buttons=Qt.LeftButton,
    )
    assert win.eventFilter(win.month_label, move) is True
    assert (win.x(), win.y()) != (start_x, start_y)

    release = _MouseEvent(
        QEvent.Type.MouseButtonRelease,
        move_to,
        button=Qt.LeftButton,
    )
    assert win.eventFilter(win.month_label, release) is True
    assert release.accepted

    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "free"
    assert int(db.get_setting(db.SETTING_CALENDAR_X)) == win.x()
    assert int(db.get_setting(db.SETTING_CALENDAR_Y)) == win.y()
    assert db.get_setting(db.SETTING_TARGET_SCREEN) in {
        str(i) for i, _screen in enumerate(QApplication.screens())
    }


def test_header_drag_moves_on_target_screen_5mm_grid(app_dir, qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()

    screen = win.screen() or QApplication.primaryScreen()
    snap = _snap_px_for_screen(screen)
    press_global = win.frameGeometry().topLeft() + QPoint(120, 20)
    drag_offset = press_global - win.frameGeometry().topLeft()
    unsnapped_target = QPoint(
        (win.x() // snap + 3) * snap + 1,
        (win.y() // snap + 2) * snap + 1,
    )
    move_global = unsnapped_target + drag_offset

    win.eventFilter(
        win.month_label,
        _MouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(press_global),
            button=Qt.LeftButton,
            buttons=Qt.LeftButton,
        ),
    )
    win.eventFilter(
        win.month_label,
        _MouseEvent(
            QEvent.Type.MouseMove,
            QPointF(move_global),
            buttons=Qt.LeftButton,
        ),
    )

    assert win.pos() == QPoint(
        round(unsnapped_target.x() / snap) * snap,
        round(unsnapped_target.y() / snap) * snap,
    )


def test_real_qt_mouse_drag_still_finishes_before_ungrab(app_dir, qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    db.save_setting(db.SETTING_CALENDAR_POSITION_MODE, "corner")
    start = win.month_label.rect().center()

    QTest.mousePress(win.month_label, Qt.LeftButton, pos=start)
    QTest.mouseMove(win.month_label, start + QPoint(40, 25), delay=20)
    QTest.mouseRelease(
        win.month_label,
        Qt.LeftButton,
        pos=start + QPoint(40, 25),
        delay=20,
    )

    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "free"
    assert win._calendar_drag_offset is None


def test_header_click_without_drag_keeps_corner_mode(app_dir, qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    db.save_setting(db.SETTING_CALENDAR_POSITION_MODE, "corner")
    point = QPointF(win.x() + 120, win.y() + 20)

    press = _MouseEvent(
        QEvent.Type.MouseButtonPress,
        point,
        button=Qt.LeftButton,
        buttons=Qt.LeftButton,
    )
    release = _MouseEvent(
        QEvent.Type.MouseButtonRelease,
        point,
        button=Qt.LeftButton,
    )

    assert win.eventFilter(win.month_label, press) is True
    assert win.eventFilter(win.month_label, release) is True
    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "corner"


def test_small_pointer_jitter_does_not_start_calendar_drag(app_dir, qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    db.save_setting(db.SETTING_CALENDAR_POSITION_MODE, "corner")
    start = QPointF(win.x() + 120, win.y() + 20)

    win.eventFilter(
        win.month_label,
        _MouseEvent(
            QEvent.Type.MouseButtonPress,
            start,
            button=Qt.LeftButton,
            buttons=Qt.LeftButton,
        ),
    )
    win.eventFilter(
        win.month_label,
        _MouseEvent(
            QEvent.Type.MouseMove,
            QPointF(start.x() + 1, start.y() + 1),
            buttons=Qt.LeftButton,
        ),
    )
    win.eventFilter(
        win.month_label,
        _MouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(start.x() + 1, start.y() + 1),
            button=Qt.LeftButton,
        ),
    )

    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "corner"


def test_header_drag_is_disabled_in_large_mode(app_dir, qtbot):
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    db.save_setting(db.SETTING_CALENDAR_POSITION_MODE, "corner")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()

    start_pos = win.pos()
    press_at = win.frameGeometry().topLeft() + QPoint(120, 20)
    move_to = press_at + QPoint(100, 80)

    for target in win._calendar_drag_targets:
        press = _MouseEvent(
            QEvent.Type.MouseButtonPress,
            press_at,
            button=Qt.LeftButton,
            buttons=Qt.LeftButton,
        )
        move = _MouseEvent(
            QEvent.Type.MouseMove,
            move_to,
            buttons=Qt.LeftButton,
        )
        release = _MouseEvent(
            QEvent.Type.MouseButtonRelease,
            move_to,
            button=Qt.LeftButton,
        )

        assert win.eventFilter(target, press) is False
        assert win.eventFilter(target, move) is False
        assert win.eventFilter(target, release) is False

    assert win.pos() == start_pos
    assert win._calendar_drag_offset is None
    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "corner"


def test_corner_setting_replaces_free_position_mode(app_dir, qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    db.save_setting(db.SETTING_CALENDAR_POSITION_MODE, "free")

    win._position_to_corner()

    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "corner"
    assert int(db.get_setting(db.SETTING_CALENDAR_X)) == win.x()
    assert int(db.get_setting(db.SETTING_CALENDAR_Y)) == win.y()


def test_invalid_saved_position_falls_back_without_crash(app_dir, qtbot):
    db.save_setting(db.SETTING_CALENDAR_POSITION_MODE, "free")
    db.save_setting(db.SETTING_CALENDAR_X, "broken")
    db.save_setting(db.SETTING_CALENDAR_Y, "also-broken")

    win = MainCalendarWindow()
    qtbot.addWidget(win)

    screen = win._get_target_screen()
    x, y = win._calendar_xy_for_size(win.width(), win.height(), screen)
    geometry = screen.availableGeometry()
    assert geometry.left() <= x <= geometry.left() + max(0, geometry.width() - win.width())
    assert geometry.top() <= y <= geometry.top() + max(0, geometry.height() - win.height())


def test_free_position_resize_stays_on_saved_negative_coordinate_screen(
        app_dir, qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    left_screen = _FakeScreen(QRect(-1920, 0, 1920, 1080))
    db.save_setting(db.SETTING_CALENDAR_POSITION_MODE, "free")
    db.save_setting(db.SETTING_CALENDAR_X, "-380")
    db.save_setting(db.SETTING_CALENDAR_Y, "40")

    x, y = win._calendar_xy_for_size(1880, 1040, left_screen)

    assert (x, y) == (-1880, 40)
    assert x < 0


def test_drag_to_smaller_screen_resizes_before_clamping(
        app_dir, qtbot, monkeypatch):
    import ui_main

    win = MainCalendarWindow()
    qtbot.addWidget(win)
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win.setMaximumWidth(16777215)
    win.setMinimumSize(500, 500)
    win.resize(1880, 1040)
    small_screen = _FakeScreen(QRect(1920, 0, 1280, 720))

    class _FakeApplication:
        @staticmethod
        def screenAt(_point):
            return small_screen

        @staticmethod
        def screens():
            return [small_screen]

        @staticmethod
        def primaryScreen():
            return small_screen

    monkeypatch.setattr(ui_main, "QApplication", _FakeApplication)

    win._finish_calendar_drag(QPoint(2200, 100))

    available = small_screen.availableGeometry()
    assert win.width() <= available.width()
    assert win.height() <= available.height()
    assert win.x() >= available.left()
    assert win.y() >= available.top()
    assert win.x() + win.width() <= available.left() + available.width()
    assert win.y() + win.height() <= available.top() + available.height()


def test_drag_finish_keeps_grid_alignment_on_negative_coordinate_screen(
        app_dir, qtbot, monkeypatch):
    import ui_main

    win = MainCalendarWindow()
    qtbot.addWidget(win)
    negative_screen = _FakeScreen(QRect(-1920, 0, 1920, 1080))
    negative_screen.physicalDotsPerInch = lambda: 96

    class _FakeApplication:
        @staticmethod
        def screenAt(_point):
            return negative_screen

        @staticmethod
        def screens():
            return [negative_screen]

        @staticmethod
        def primaryScreen():
            return negative_screen

    monkeypatch.setattr(ui_main, "QApplication", _FakeApplication)
    # 화면 왼쪽 경계 자체(-1920)는 19px 전역 격자와 맞지 않는다.
    # 경계로 clamp한 뒤 격자를 잃지 말고, 화면 안 첫 격자에 놓여야 한다.
    win.move(-1918, 37)

    win._finish_calendar_drag(QPoint(-1500, 100))

    snap = _snap_px_for_screen(negative_screen)
    available = negative_screen.availableGeometry()
    assert win.x() % snap == 0
    assert win.y() % snap == 0
    assert win.x() >= available.left()
    assert win.y() >= available.top()
    assert win.x() + win.width() <= available.left() + available.width()
    assert win.y() + win.height() <= available.top() + available.height()


def test_new_screen_geometry_changes_are_watched(app_dir, qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    new_screen = _FakeScreen(QRect(1920, 0, 1280, 720))
    new_screen.geometryChanged = _FakeSignal()
    new_screen.availableGeometryChanged = _FakeSignal()

    win._on_screen_added(new_screen)

    assert new_screen.geometryChanged.callback is not None
    assert new_screen.availableGeometryChanged.callback is not None
    win._screen_change_timer.stop()
    new_screen.geometryChanged.callback(QRect(1920, 0, 1024, 768))
    assert win._screen_change_timer.isActive()

    win._screen_change_timer.stop()
    new_screen.availableGeometryChanged.callback(QRect(1920, 0, 1024, 720))
    assert win._screen_change_timer.isActive()


def test_removed_screen_is_forgotten_and_schedules_recovery(app_dir, qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    removed = _FakeScreen(QRect(1920, 0, 1280, 720))
    win._watched_screen_ids.add(id(removed))
    win._screen_change_timer.stop()

    win._on_screen_removed(removed)

    assert id(removed) not in win._watched_screen_ids
    assert win._screen_change_timer.isActive()


def test_drag_state_resets_when_window_deactivates(app_dir, qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._calendar_drag_offset = QPoint(10, 10)
    win._calendar_drag_press_global = QPoint(20, 20)
    win._calendar_drag_started = True

    win.eventFilter(win, QEvent(QEvent.Type.WindowDeactivate))

    assert win._calendar_drag_offset is None
    assert win._calendar_drag_press_global is None
    assert win._calendar_drag_started is False


def test_drag_state_resets_when_mouse_grab_is_lost(app_dir, qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._calendar_drag_offset = QPoint(10, 10)
    win._calendar_drag_press_global = QPoint(20, 20)
    win._calendar_drag_started = True

    win.eventFilter(win.month_label, QEvent(QEvent.Type.UngrabMouse))

    assert win._calendar_drag_offset is None
    assert win._calendar_drag_press_global is None
    assert win._calendar_drag_started is False
