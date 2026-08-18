"""ShowDesktopKeeper unit tests (pytest-qt, real Win32 window styles)."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

import show_desktop_guard as guard_module
from show_desktop_guard import ShowDesktopKeeper

_GWL_EXSTYLE = -20
_WS_EX_TOPMOST = 0x00000008

_GetWindowLongW = ctypes.windll.user32.GetWindowLongW
_GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_GetWindowLongW.restype = ctypes.c_long

def _is_topmost(widget) -> bool:
    ex_style = _GetWindowLongW(int(widget.winId()), _GWL_EXSTYLE)
    return bool(ex_style & _WS_EX_TOPMOST)


def _make_window(qtbot):
    widget = QWidget()
    widget.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.Tool)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def _make_keeper(enabled=True):
    # Unit tests drive foreground transitions explicitly; no process-global hook.
    return ShowDesktopKeeper(enabled=enabled, _install_hook=False)


def _set_desktop_predicate(monkeypatch, desktop_hwnd, foreground_hwnd=None):
    monkeypatch.setattr(
        guard_module,
        "_is_desktop_foreground",
        lambda hwnd: int(hwnd or 0) == int(desktop_hwnd),
    )
    monkeypatch.setattr(
        guard_module,
        "_GetForegroundWindow",
        lambda: desktop_hwnd if foreground_hwnd is None else foreground_hwnd,
    )


def test_restores_when_enabled(qtbot):
    widget = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)

    widget.setWindowState(Qt.WindowState.WindowMinimized)

    qtbot.waitUntil(
        lambda: not (widget.windowState() & Qt.WindowState.WindowMinimized),
        timeout=2000,
    )
    assert not (widget.windowState() & Qt.WindowState.WindowMinimized)


def test_stays_minimized_when_disabled(qtbot):
    widget = _make_window(qtbot)
    keeper = _make_keeper(enabled=False)
    keeper.guard(widget)

    widget.setWindowState(Qt.WindowState.WindowMinimized)

    qtbot.wait(250)
    assert widget.windowState() & Qt.WindowState.WindowMinimized


def test_restore_does_not_undo_intentional_hide(qtbot):
    widget = _make_window(qtbot)
    widget.setWindowState(Qt.WindowState.WindowMinimized)
    widget.hide()

    ShowDesktopKeeper._restore(widget)
    qtbot.wait(50)

    assert widget.isVisible() is False
    assert not (widget.windowState() & Qt.WindowState.WindowMinimized)


def test_set_enabled_gates_live_restore(qtbot, monkeypatch):
    widget = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)

    monkeypatch.setattr(guard_module, "_GetForegroundWindow", lambda: 0)
    keeper.set_enabled(False)
    widget.setWindowState(Qt.WindowState.WindowMinimized)
    qtbot.wait(250)
    assert widget.windowState() & Qt.WindowState.WindowMinimized

    widget.setWindowState(Qt.WindowState.WindowNoState)
    qtbot.waitUntil(
        lambda: not (widget.windowState() & Qt.WindowState.WindowMinimized),
        timeout=2000,
    )

    keeper.set_enabled(True)
    widget.setWindowState(Qt.WindowState.WindowMinimized)
    qtbot.waitUntil(
        lambda: not (widget.windowState() & Qt.WindowState.WindowMinimized),
        timeout=2000,
    )


def test_set_enabled_toggles_state(monkeypatch):
    monkeypatch.setattr(guard_module, "_GetForegroundWindow", lambda: 0)
    keeper = _make_keeper(enabled=True)
    assert keeper.is_enabled() is True
    keeper.set_enabled(False)
    assert keeper.is_enabled() is False
    keeper.set_enabled(True)
    assert keeper.is_enabled() is True


def test_guard_none_is_safe():
    keeper = _make_keeper(enabled=True)
    keeper.guard(None)


def test_enabled_guard_is_not_permanently_topmost(qtbot):
    widget = _make_window(qtbot)
    assert not _is_topmost(widget)

    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    qtbot.wait(50)

    assert not _is_topmost(widget)


def test_desktop_foreground_starts_then_settles_topmost_pulse(
    qtbot,
    monkeypatch,
):
    widget = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    keeper._settle_timer.setInterval(30)
    desktop_hwnd = 101
    _set_desktop_predicate(monkeypatch, desktop_hwnd)

    keeper._on_foreground_changed(desktop_hwnd)
    qtbot.waitUntil(lambda: _is_topmost(widget), timeout=1000)
    assert keeper._pulse_active is True

    qtbot.waitUntil(lambda: not _is_topmost(widget), timeout=1000)
    assert keeper._pulse_active is False
    assert keeper._desktop_foreground is True


def test_non_desktop_foreground_cancels_pulse_and_pins_desktop_layer(
    qtbot,
    monkeypatch,
):
    widget = _make_window(qtbot)
    foreground = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    keeper._settle_timer.setInterval(100)
    desktop_hwnd = 101
    _set_desktop_predicate(monkeypatch, desktop_hwnd)

    keeper._on_foreground_changed(desktop_hwnd)
    qtbot.waitUntil(lambda: _is_topmost(widget), timeout=1000)

    keeper._on_foreground_changed(int(foreground.winId()))
    qtbot.waitUntil(lambda: not _is_topmost(widget), timeout=1000)

    assert keeper._settle_timer.isActive() is False
    assert keeper._pulse_active is False
    assert keeper._desktop_foreground is False


def test_stale_settle_timeout_cannot_restore_topmost(
    qtbot,
    monkeypatch,
):
    widget = _make_window(qtbot)
    foreground = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    keeper._settle_timer.setInterval(30)
    desktop_hwnd = 101
    _set_desktop_predicate(monkeypatch, desktop_hwnd)

    keeper._on_foreground_changed(desktop_hwnd)
    qtbot.waitUntil(lambda: _is_topmost(widget), timeout=1000)
    keeper._on_foreground_changed(int(foreground.winId()))
    qtbot.wait(100)

    assert not _is_topmost(widget)
    assert keeper._pulse_active is False


def test_toggle_off_during_pulse_demotes_immediately(
    qtbot,
    monkeypatch,
):
    widget = _make_window(qtbot)
    foreground = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    desktop_hwnd = 101
    _set_desktop_predicate(monkeypatch, desktop_hwnd)

    keeper._on_foreground_changed(desktop_hwnd)
    qtbot.waitUntil(lambda: _is_topmost(widget), timeout=1000)

    monkeypatch.setattr(
        guard_module,
        "_GetForegroundWindow",
        lambda: int(foreground.winId()),
    )
    keeper.set_enabled(False)
    qtbot.waitUntil(lambda: not _is_topmost(widget), timeout=1000)

    assert keeper._settle_timer.isActive() is False
    assert keeper.is_enabled() is False


def test_desktop_pulse_applies_to_all_visible_guarded_windows(
    qtbot,
    monkeypatch,
):
    first = _make_window(qtbot)
    second = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(first)
    keeper.guard(second)
    desktop_hwnd = 101
    _set_desktop_predicate(monkeypatch, desktop_hwnd)

    keeper._on_foreground_changed(desktop_hwnd)
    qtbot.waitUntil(
        lambda: _is_topmost(first) and _is_topmost(second),
        timeout=1000,
    )

    keeper.set_enabled(False)
    qtbot.waitUntil(
        lambda: not _is_topmost(first) and not _is_topmost(second),
        timeout=1000,
    )


def test_hidden_guarded_window_is_not_promoted_by_desktop_pulse(
    qtbot,
    monkeypatch,
):
    visible = _make_window(qtbot)
    hidden = _make_window(qtbot)
    hidden.hide()
    keeper = _make_keeper(enabled=True)
    keeper.guard(visible)
    keeper.guard(hidden)
    desktop_hwnd = 101
    _set_desktop_predicate(monkeypatch, desktop_hwnd)

    keeper._on_foreground_changed(desktop_hwnd)
    qtbot.waitUntil(lambda: _is_topmost(visible), timeout=1000)

    assert not _is_topmost(hidden)


def test_window_shown_during_active_pulse_gets_only_temporary_topmost(
    qtbot,
    monkeypatch,
):
    widget = _make_window(qtbot)
    widget.hide()
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    keeper._settle_timer.setInterval(50)
    desktop_hwnd = 101
    _set_desktop_predicate(monkeypatch, desktop_hwnd)

    keeper._on_foreground_changed(desktop_hwnd)
    widget.show()
    qtbot.waitUntil(lambda: _is_topmost(widget), timeout=1000)
    qtbot.waitUntil(lambda: not _is_topmost(widget), timeout=1000)


def test_desktop_identity_requires_shell_window_or_shell_owned_host(
    monkeypatch,
):
    monkeypatch.setattr(guard_module, "_GetShellWindow", lambda: 10)
    monkeypatch.setattr(
        guard_module,
        "_window_process_id",
        lambda hwnd: {10: 55, 20: 55, 30: 55, 40: 99}.get(hwnd, 0),
    )

    assert guard_module._is_desktop_foreground(10) is True

    monkeypatch.setattr(guard_module, "_window_class_name", lambda _hwnd: "WorkerW")
    assert guard_module._is_desktop_foreground(20) is True

    monkeypatch.setattr(guard_module, "_window_class_name", lambda _hwnd: "Progman")
    assert guard_module._is_desktop_foreground(30) is True

    monkeypatch.setattr(guard_module, "_window_class_name", lambda _hwnd: "WorkerW")
    assert guard_module._is_desktop_foreground(40) is False

    monkeypatch.setattr(
        guard_module,
        "_window_class_name",
        lambda _hwnd: "CabinetWClass",
    )
    assert guard_module._is_desktop_foreground(20) is False
    assert guard_module._is_desktop_foreground(0) is False


def test_desktop_pin_places_guarded_windows_below_all_normal_windows(
    qtbot,
    monkeypatch,
):
    first = _make_window(qtbot)
    second = _make_window(qtbot)
    keeper = _make_keeper(enabled=False)
    keeper.guard(first)
    keeper.guard(second)

    desktop_hwnd = 101
    normal_hwnd = 202
    first_hwnd = int(first.winId())
    second_hwnd = int(second.winId())
    calls = []
    monkeypatch.setattr(
        guard_module,
        "_is_desktop_foreground",
        lambda hwnd: int(hwnd or 0) == desktop_hwnd,
    )
    monkeypatch.setattr(guard_module, "_GetShellWindow", lambda: desktop_hwnd)
    monkeypatch.setattr(
        guard_module,
        "_GetWindow",
        lambda hwnd, _relation: {
            desktop_hwnd: second_hwnd,
            second_hwnd: first_hwnd,
            first_hwnd: normal_hwnd,
        }.get(int(hwnd), 0),
    )
    monkeypatch.setattr(
        guard_module,
        "_SetWindowPos",
        lambda *args: calls.append(args) or True,
    )

    keeper._enabled = True
    assert keeper._pin_to_desktop_layer() is True

    assert [call[:2] for call in calls] == [
        (first_hwnd, guard_module._HWND_NOTOPMOST),
        (second_hwnd, guard_module._HWND_NOTOPMOST),
        (first_hwnd, normal_hwnd),
        (second_hwnd, normal_hwnd),
    ]


def test_foreground_app_reanchors_guarded_window_to_desktop_layer(
    qtbot,
    monkeypatch,
):
    widget = _make_window(qtbot)
    keeper = _make_keeper(enabled=False)
    keeper.guard(widget)

    desktop_hwnd = 101
    normal_floor_hwnd = 202
    foreground_hwnd = 303
    calls = []
    monkeypatch.setattr(
        guard_module,
        "_is_desktop_foreground",
        lambda hwnd: int(hwnd or 0) == desktop_hwnd,
    )
    monkeypatch.setattr(guard_module, "_GetShellWindow", lambda: desktop_hwnd)
    monkeypatch.setattr(
        guard_module,
        "_GetWindow",
        lambda hwnd, _relation: (
            normal_floor_hwnd if int(hwnd) == desktop_hwnd else 0
        ),
    )
    monkeypatch.setattr(
        guard_module,
        "_SetWindowPos",
        lambda *args: calls.append(args) or True,
    )

    keeper._enabled = True
    keeper._desktop_hwnd = desktop_hwnd
    keeper._on_foreground_changed(foreground_hwnd)

    assert [call[:2] for call in calls] == [
        (int(widget.winId()), guard_module._HWND_NOTOPMOST),
        (int(widget.winId()), normal_floor_hwnd),
    ]
    assert all(call[1] != foreground_hwnd for call in calls)


def test_non_desktop_demote_places_guarded_window_behind_foreground(
    qtbot,
    monkeypatch,
):
    widget = _make_window(qtbot)
    calls = []
    monkeypatch.setattr(
        guard_module,
        "_SetWindowPos",
        lambda *args: calls.append(args) or True,
    )
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    calls.clear()

    keeper._demote_all(98765)

    hwnd = int(widget.winId())
    assert calls[0][:2] == (hwnd, guard_module._HWND_NOTOPMOST)
    assert calls[1][:2] == (hwnd, 98765)


def test_win_event_hook_callback_is_retained_queued_and_released(
    qtbot,
    monkeypatch,
):
    installed = {}
    released = []
    desktop_hwnd = 101

    def fake_install(_min, _max, _module, callback, _pid, _tid, _flags):
        installed["callback"] = callback
        return 1234

    monkeypatch.setattr(guard_module, "_SetWinEventHook", fake_install)
    monkeypatch.setattr(
        guard_module,
        "_UnhookWinEvent",
        lambda hook: released.append(hook) or True,
    )
    _set_desktop_predicate(monkeypatch, desktop_hwnd)

    keeper = ShowDesktopKeeper(enabled=True)
    assert keeper._win_event_callback is installed["callback"]

    installed["callback"](
        1234,
        guard_module._EVENT_SYSTEM_FOREGROUND,
        desktop_hwnd,
        0,
        0,
        0,
        0,
    )
    qtbot.waitUntil(lambda: keeper._pulse_active, timeout=1000)

    keeper.shutdown()
    assert released == [1234]
    assert keeper._win_event_hook is None
    assert keeper._win_event_callback is None


def test_qobject_destruction_unhooks_native_foreground_hook(
    qtbot,
    monkeypatch,
):
    released = []
    monkeypatch.setattr(
        guard_module,
        "_SetWinEventHook",
        lambda *_args: 4321,
    )
    monkeypatch.setattr(
        guard_module,
        "_UnhookWinEvent",
        lambda hook: released.append(hook) or True,
    )

    keeper = ShowDesktopKeeper(enabled=True)
    keeper.deleteLater()
    qtbot.waitUntil(lambda: released == [4321], timeout=1000)

    assert released == [4321]


def test_unhook_failure_retains_callback_and_shutdown_retries_idempotently(
    qtbot,
    monkeypatch,
):
    attempts = []
    outcomes = iter((False, True))
    monkeypatch.setattr(
        guard_module,
        "_SetWinEventHook",
        lambda *_args: 2468,
    )

    def fake_unhook(hook):
        attempts.append(hook)
        return next(outcomes)

    monkeypatch.setattr(guard_module, "_UnhookWinEvent", fake_unhook)
    keeper = ShowDesktopKeeper(enabled=True)
    callback = keeper._win_event_callback

    assert keeper.is_operational() is True
    keeper.shutdown()
    assert keeper._win_event_hook == 2468
    assert keeper._win_event_callback is callback
    assert keeper.is_operational() is True

    keeper.shutdown()
    assert keeper._win_event_hook is None
    assert keeper._win_event_callback is None
    assert keeper.is_operational() is False

    keeper.shutdown()
    assert attempts == [2468, 2468]


def test_hook_install_failure_is_reported_by_operational_state(
    caplog,
    monkeypatch,
):
    monkeypatch.setattr(guard_module, "_SetWinEventHook", lambda *_args: 0)

    with caplog.at_level("WARNING", logger="app_error"):
        keeper = ShowDesktopKeeper(enabled=True)

    assert keeper.is_enabled() is True
    assert keeper.is_operational() is False
    assert "foreground 감지 등록 실패" in caplog.text
