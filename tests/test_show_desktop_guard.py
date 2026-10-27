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


def _set_desktop_predicate(
    monkeypatch,
    desktop_hwnd,
    foreground_hwnd=None,
    click=False,
):
    """가짜 바탕화면 HWND를 셸 바탕화면으로 본다.

    ``click``은 이번 바탕화면 활성화가 바탕화면 위 마우스 클릭인지의 판정이다.
    기본값(False)은 Win+D·'바탕화면 보기' 버튼처럼 클릭이 아닌 활성화다.
    """
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
    monkeypatch.setattr(guard_module, "_is_desktop_click", lambda: click)


_GW_HWNDNEXT = 2
_VK_LBUTTON = 0x01
_VK_RBUTTON = 0x02
_REAL_SET_WINDOW_POS = guard_module._SetWindowPos
_REAL_GET_WINDOW = guard_module._GetWindow


def _place_below(widget, insert_after) -> None:
    """실제 z-order에서 ``widget``을 ``insert_after`` 바로 아래에 둔다."""
    assert _REAL_SET_WINDOW_POS(
        int(widget.winId()),
        int(insert_after.winId()),
        0, 0, 0, 0,
        guard_module._SWP_FLAGS,
    )


def _raise_to_top(widget) -> None:
    """실제 z-order에서 ``widget``을 일반 창 맨 위로 올린다."""
    assert _REAL_SET_WINDOW_POS(
        int(widget.winId()),
        guard_module._HWND_TOP,
        0, 0, 0, 0,
        guard_module._SWP_FLAGS,
    )


def _is_above(upper, lower) -> bool:
    """실제 z-order에서 ``upper``가 ``lower``보다 위인지."""
    target = int(lower.winId())
    hwnd = int(_REAL_GET_WINDOW(int(upper.winId()), _GW_HWNDNEXT) or 0)
    while hwnd:
        if hwnd == target:
            return True
        hwnd = int(_REAL_GET_WINDOW(hwnd, _GW_HWNDNEXT) or 0)
    return False


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


def test_plain_desktop_click_never_raises_guarded_window(
    qtbot,
    monkeypatch,
):
    """바탕화면 클릭은 바탕화면을 올리지 않으므로 topmost pulse가 없어야 한다.

    2026-10-24 실측: 클릭마다 pulse가 캘린더를 탐색기 위로 350ms 올려
    탐색기가 잠깐 사라졌다가 다시 나타났다.
    """
    widget = _make_window(qtbot)
    desktop = _make_window(qtbot)  # 실제 z-order를 가진 바탕화면 대역
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    keeper._settle_timer.setInterval(60)
    _set_desktop_predicate(monkeypatch, int(desktop.winId()), click=True)
    _place_below(desktop, widget)  # 클릭 직후: 바탕화면은 감시 창 아래 그대로

    keeper._on_foreground_changed(int(desktop.winId()))

    assert keeper._pulse_active is False
    topmost_seen = _is_topmost(widget)
    for _ in range(30):  # settle(60ms)이 지날 때까지 관찰
        qtbot.wait(5)
        topmost_seen = topmost_seen or _is_topmost(widget)
    assert topmost_seen is False
    assert _is_above(widget, desktop)


def test_show_desktop_pulses_before_shell_raises_desktop(
    qtbot,
    monkeypatch,
):
    """Win+D는 바탕화면 활성화 알림 뒤에 바탕화면을 올린다.

    2026-10-24 실측: 알림 7~250ms 뒤에 바탕화면이 올라왔다. 알림 시점에
    덮였는지로 판단하면 캘린더가 잠깐 사라졌다가 다시 나타난다.
    """
    widget = _make_window(qtbot)
    desktop = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    keeper._settle_timer.setInterval(60)
    _set_desktop_predicate(monkeypatch, int(desktop.winId()))
    _place_below(desktop, widget)  # 알림 시점: 아직 덮이지 않음

    keeper._on_foreground_changed(int(desktop.winId()))
    assert keeper._pulse_active is True
    assert _is_topmost(widget)

    _raise_to_top(desktop)  # 셸이 뒤늦게 바탕화면을 일반 창 맨 위로 올림
    assert _is_above(widget, desktop)
    qtbot.waitUntil(lambda: not _is_topmost(widget), timeout=1000)
    assert _is_above(widget, desktop)


def test_desktop_raised_after_click_is_repinned_without_topmost(
    qtbot,
    monkeypatch,
):
    widget = _make_window(qtbot)
    desktop = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    keeper._settle_timer.setInterval(60)
    _set_desktop_predicate(monkeypatch, int(desktop.winId()), click=True)
    _place_below(desktop, widget)

    keeper._on_foreground_changed(int(desktop.winId()))
    assert not _is_topmost(widget)
    _place_below(widget, desktop)  # 클릭으로 판단했는데 바탕화면이 올라온 경우

    qtbot.waitUntil(lambda: _is_above(widget, desktop), timeout=1000)
    assert not _is_topmost(widget)
    assert keeper._pulse_active is False


def test_show_desktop_while_desktop_already_active_pulses_on_reorder(
    qtbot,
    monkeypatch,
):
    """바탕화면을 누른 뒤(이미 활성) Win+D는 foreground 알림 없이 바탕화면만 올린다.

    2026-10-25 실측: 그때는 데스크톱 창의 창 순서 변경(REORDER)만 오고,
    캘린더가 다음 Win+D까지 바탕화면에 가려졌다.
    """
    widget = _make_window(qtbot)
    desktop = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    keeper._settle_timer.setInterval(60)
    _set_desktop_predicate(monkeypatch, int(desktop.winId()), click=True)
    _place_below(desktop, widget)
    keeper._on_foreground_changed(int(desktop.winId()))  # 바탕화면 클릭
    qtbot.waitUntil(lambda: not keeper._settle_timer.isActive(), timeout=1000)

    _raise_to_top(desktop)  # Win+D: 알림 없이 바탕화면이 일반 창 맨 위로
    assert not _is_above(widget, desktop)
    keeper._on_desktop_reordered()
    assert keeper._pulse_active is True
    assert _is_topmost(widget)
    qtbot.waitUntil(lambda: not _is_topmost(widget), timeout=1000)
    assert _is_above(widget, desktop)


def test_reorder_without_desktop_cover_does_not_pulse(qtbot, monkeypatch):
    widget = _make_window(qtbot)
    desktop = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    keeper._settle_timer.setInterval(60)
    _set_desktop_predicate(monkeypatch, int(desktop.winId()), click=True)
    _place_below(desktop, widget)
    keeper._on_foreground_changed(int(desktop.winId()))
    qtbot.waitUntil(lambda: not keeper._settle_timer.isActive(), timeout=1000)

    keeper._on_desktop_reordered()  # 바탕화면 클릭 등: 바탕화면은 여전히 아래
    assert keeper._pulse_active is False
    assert not _is_topmost(widget)


def test_reorder_while_other_app_is_active_does_not_pulse(qtbot, monkeypatch):
    widget = _make_window(qtbot)
    desktop = _make_window(qtbot)
    other = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    _set_desktop_predicate(
        monkeypatch, int(desktop.winId()), foreground_hwnd=int(other.winId()))
    keeper._on_foreground_changed(int(other.winId()))
    _raise_to_top(desktop)  # 바탕화면이 위에 있어도 바탕화면이 활성이 아니면 건드리지 않는다

    keeper._on_desktop_reordered()
    assert keeper._pulse_active is False
    assert not _is_topmost(widget)


def _show_desktop(qtbot, keeper, widget, desktop, other) -> None:
    """Win+D: pulse 뒤 셸이 맨 위로 올린 바탕화면 바로 위에 고정된 상태를 만든다."""
    _place_below(desktop, widget)
    _place_below(other, desktop)  # 바탕화면 보기로 내려간 일반 창
    keeper._on_foreground_changed(int(desktop.winId()))
    assert keeper._pulse_active is True
    _raise_to_top(desktop)  # 셸이 알림 뒤에 바탕화면을 일반 창 맨 위로 올림
    qtbot.waitUntil(lambda: not _is_topmost(widget), timeout=1000)
    assert _is_above(widget, desktop)
    assert _is_above(desktop, other)


def test_show_desktop_restore_follows_desktop_back_down(qtbot, monkeypatch):
    """바탕화면 보기를 되돌리면 셸은 바탕화면만 맨 아래로 내린다.

    2026-10-25 실측: 되돌릴 때 활성화되는 앱이 없으면(바탕화면이 이미 활성이던
    Win+D) 캘린더가 되살아난 창들 위에 남아 다른 창을 누를 때까지 가렸다.
    """
    widget = _make_window(qtbot)
    desktop = _make_window(qtbot)
    other = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    keeper._settle_timer.setInterval(60)
    _set_desktop_predicate(monkeypatch, int(desktop.winId()))
    _show_desktop(qtbot, keeper, widget, desktop, other)

    _place_below(desktop, other)  # 되돌림: 바탕화면만 되살아난 창 아래로
    assert _is_above(widget, other)
    keeper._on_desktop_reordered()
    assert _is_above(other, widget)
    assert _is_above(widget, desktop)
    assert not _is_topmost(widget)

    # 한 번 따라간 뒤에는 다른 '바탕화면 고정' 앱과 서로 밀어내지 않는다.
    rival = _make_window(qtbot)
    _place_below(rival, widget)
    keeper._on_desktop_reordered()
    assert _is_above(widget, rival)


def test_show_desktop_button_restore_follows_desktop_back_down(
    qtbot,
    monkeypatch,
):
    """'바탕화면 보기' 버튼으로 되돌리면 작업 표시줄이 먼저 활성화된다.

    2026-10-25 실측: 그 순간 고정하면 아직 맨 위인 바탕화면 바로 위(맨 위)로
    고정되고, 뒤이어 바탕화면이 내려가 캘린더가 창들 위에 남았다.
    """
    widget = _make_window(qtbot)
    desktop = _make_window(qtbot)
    other = _make_window(qtbot)
    taskbar = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    keeper._settle_timer.setInterval(60)
    _set_desktop_predicate(monkeypatch, int(desktop.winId()))
    _show_desktop(qtbot, keeper, widget, desktop, other)

    keeper._on_foreground_changed(int(taskbar.winId()))  # 버튼을 누름
    assert _is_above(widget, desktop)
    _place_below(desktop, other)
    keeper._on_desktop_reordered()
    assert _is_above(other, widget)
    assert _is_above(widget, desktop)


def test_reorder_without_show_desktop_leaves_windows_below_alone(
    qtbot,
    monkeypatch,
):
    """바탕화면 보기가 없었으면 감시 창 아래의 창을 이유로 다시 고정하지 않는다."""
    widget = _make_window(qtbot)
    desktop = _make_window(qtbot)
    rival = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    _set_desktop_predicate(monkeypatch, int(desktop.winId()), click=True)
    _place_below(desktop, widget)
    _place_below(rival, widget)  # 다른 '바탕화면 고정' 앱이 사이에 들어옴

    keeper._on_desktop_reordered()
    assert _is_above(widget, rival)
    assert keeper._pulse_active is False


def test_enabling_on_desktop_skips_pulse_only_for_desktop_click(
    qtbot,
    monkeypatch,
):
    widget = _make_window(qtbot)
    keeper = _make_keeper(enabled=False)
    keeper.guard(widget)
    desktop_hwnd = 101

    _set_desktop_predicate(monkeypatch, desktop_hwnd, click=True)
    keeper.set_enabled(True)
    assert keeper._pulse_active is False
    assert not _is_topmost(widget)

    keeper.set_enabled(False)
    _set_desktop_predicate(monkeypatch, desktop_hwnd, click=False)
    keeper.set_enabled(True)
    assert keeper._pulse_active is True
    assert _is_topmost(widget)
    keeper.set_enabled(False)


def _fake_pointer(monkeypatch, *, down=(), root=0):
    """마우스 버튼 상태와 커서 아래 최상위 창을 흉내 낸다."""
    monkeypatch.setattr(
        guard_module,
        "_GetAsyncKeyState",
        lambda vk: -32768 if vk in down else 0,
    )
    monkeypatch.setattr(guard_module, "_GetCursorPos", lambda _point: True)
    monkeypatch.setattr(guard_module, "_WindowFromPoint", lambda _point: 555)
    monkeypatch.setattr(
        guard_module,
        "_GetAncestor",
        lambda hwnd, _flag: root if int(hwnd) == 555 else 0,
    )
    monkeypatch.setattr(
        guard_module,
        "_is_desktop_foreground",
        lambda hwnd: int(hwnd or 0) == 101,
    )


def test_desktop_click_is_mouse_activation_over_desktop(monkeypatch):
    """커서 아래가 바탕화면이고 Win 키가 눌려 있지 않으면 바탕화면 클릭이다.

    2026-10-25 실측: 바탕화면 아이콘을 누르면 활성화 알림이 마우스 버튼을
    뗀 뒤에 와서(`down=[]`) 버튼 눌림을 요구하면 Win+D로 보고 pulse했다.
    Win+D는 알림 순간 늘 Win 키가 눌려 있었다(커서가 바탕화면 위일 때도).
    """
    # 빈 바탕화면 클릭: 알림 순간 버튼이 눌려 있다.
    _fake_pointer(monkeypatch, down=(_VK_LBUTTON,), root=101)
    assert guard_module._is_desktop_click() is True

    _fake_pointer(monkeypatch, down=(_VK_RBUTTON,), root=101)
    assert guard_module._is_desktop_click() is True

    # 바탕화면 아이콘 클릭: 버튼을 뗀 뒤에 알림이 온다.
    _fake_pointer(monkeypatch, down=(), root=101)
    assert guard_module._is_desktop_click() is True

    # Win+D: 커서가 바탕화면 위에 있어도 Win 키가 눌려 있다.
    _fake_pointer(monkeypatch, down=(guard_module._VK_LWIN,), root=101)
    assert guard_module._is_desktop_click() is False

    _fake_pointer(monkeypatch, down=(guard_module._VK_RWIN,), root=101)
    assert guard_module._is_desktop_click() is False

    # '바탕화면 보기' 버튼: 누르는 중이든 뗀 뒤든 커서는 작업 표시줄이다.
    _fake_pointer(monkeypatch, down=(_VK_LBUTTON,), root=202)
    assert guard_module._is_desktop_click() is False

    _fake_pointer(monkeypatch, down=(), root=202)
    assert guard_module._is_desktop_click() is False


def test_show_desktop_taken_for_click_is_rescued_by_reorder(
    qtbot,
    monkeypatch,
):
    """키·버튼 없이 바탕화면을 올리는 경로는 클릭으로 볼 수 있다.

    터치패드 제스처나 Win 키를 곧바로 떼는 자동 입력의 Win+D가 그렇다.
    클릭 settle 전에 셸이 바탕화면을 올려 감시 창을 덮으면 REORDER에서
    Win+D와 같은 pulse로 되살린다.
    """
    widget = _make_window(qtbot)
    desktop = _make_window(qtbot)
    keeper = _make_keeper(enabled=True)
    keeper.guard(widget)
    keeper._settle_timer.setInterval(60)
    _set_desktop_predicate(monkeypatch, int(desktop.winId()), click=True)
    _place_below(desktop, widget)

    keeper._on_foreground_changed(int(desktop.winId()))  # 클릭으로 판단
    assert keeper._pulse_active is False
    assert keeper._settle_timer.isActive()

    _raise_to_top(desktop)  # 셸이 뒤늦게 바탕화면을 일반 창 맨 위로 올림
    keeper._on_desktop_reordered()
    assert keeper._pulse_active is True
    assert _is_topmost(widget)
    qtbot.waitUntil(lambda: not _is_topmost(widget), timeout=1000)
    assert _is_above(widget, desktop)


def test_desktop_click_check_failure_keeps_show_desktop_pulse(monkeypatch):
    _fake_pointer(monkeypatch, down=(_VK_LBUTTON,), root=101)

    def fail(_point):
        raise OSError("cursor unavailable")

    monkeypatch.setattr(guard_module, "_GetCursorPos", fail)
    assert guard_module._is_desktop_click() is False


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

    def fake_install(event_min, _max, _module, callback, _pid, _tid, _flags):
        installed.setdefault("callbacks", []).append(callback)
        installed["callback"] = callback
        return {guard_module._EVENT_SYSTEM_FOREGROUND: 1234,
                guard_module._EVENT_OBJECT_REORDER: 5678}[event_min]

    monkeypatch.setattr(guard_module, "_SetWinEventHook", fake_install)
    monkeypatch.setattr(
        guard_module,
        "_UnhookWinEvent",
        lambda hook: released.append(hook) or True,
    )
    _set_desktop_predicate(monkeypatch, desktop_hwnd)

    keeper = ShowDesktopKeeper(enabled=True)
    # 두 hook(foreground·창 순서)이 같은 보관 callback을 쓴다.
    assert installed["callbacks"] == [keeper._win_event_callback] * 2

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
    assert sorted(released) == [1234, 5678]
    assert keeper._win_event_hook is None
    assert keeper._reorder_hook is None
    assert keeper._win_event_callback is None


def test_reorder_event_of_root_desktop_is_queued_to_cover_check(
    qtbot,
    monkeypatch,
):
    checks = []
    monkeypatch.setattr(guard_module, "_SetWinEventHook", lambda *_args: 1357)
    monkeypatch.setattr(guard_module, "_UnhookWinEvent", lambda _hook: True)
    monkeypatch.setattr(
        ShowDesktopKeeper, "_on_desktop_reordered", lambda self: checks.append(self))
    keeper = ShowDesktopKeeper(enabled=True)
    root = int(guard_module._GetDesktopWindow() or 0)
    assert root

    callback = keeper._win_event_callback
    callback(1357, guard_module._EVENT_OBJECT_REORDER, root + 4, 0, 0, 0, 0)  # 다른 창 안 순서
    callback(1357, guard_module._EVENT_OBJECT_REORDER, root, -4, 0, 0, 0)
    assert checks == []  # WinEvent callback 안에서는 처리하지 않는다
    qtbot.waitUntil(lambda: checks == [keeper], timeout=1000)
    qtbot.wait(50)
    assert checks == [keeper]
    keeper.shutdown()


def test_reorder_hook_failure_keeps_foreground_protection(caplog, monkeypatch):
    monkeypatch.setattr(
        guard_module,
        "_SetWinEventHook",
        lambda event_min, *_args: 0 if event_min == guard_module._EVENT_OBJECT_REORDER else 2222,
    )
    monkeypatch.setattr(guard_module, "_UnhookWinEvent", lambda _hook: True)

    with caplog.at_level("WARNING", logger="app_error"):
        keeper = ShowDesktopKeeper(enabled=True)

    assert keeper.is_operational() is True
    assert keeper._reorder_hook is None
    assert "창 순서 감지 등록 실패" in caplog.text
    keeper.shutdown()


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
    qtbot.waitUntil(lambda: released == [4321, 4321], timeout=1000)

    assert released == [4321, 4321]  # foreground·창 순서 hook


def test_unhook_failure_retains_callback_and_shutdown_retries_idempotently(
    qtbot,
    monkeypatch,
):
    attempts = []
    outcomes = iter((False, True, True))  # 창 순서 hook 실패 → 재시도 때 두 hook 모두 해제
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
    assert attempts == [2468, 2468, 2468]


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
