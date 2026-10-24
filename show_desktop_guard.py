"""Win+D(바탕화면 보기)/모두 최소화에도 창을 유지시키는 가드.

평상시에는 감시 창을 바탕화면 바로 위의 non-topmost z-order에 둔다. Windows
셸의 바탕화면 창이 foreground가 될 때 잠깐 topmost로 올려 Win+D 전환을
통과시키고(셸은 그 알림 뒤에 바탕화면을 올린다), 셸의 z-order 변경이 끝난 뒤
바탕화면 바로 위로 다시 고정한다. 바탕화면 위를 마우스로 누른 경우는 바탕화면이
올라오지 않으므로 topmost로 올리지 않는다(올리면 캘린더가 다른 앱 창 위로 잠깐
튀어나와 깜빡인다).
따라서 바탕화면 아이콘은 기후노트 뒤에 있고 일반 앱 창은 기후노트 위에 있다.

Win+M/실제 최소화는 ``WindowStateChange``를 감지해 다음 이벤트 루프 턴에
복원한다. WorkerW/Progman에 창을 재부모화하는 방식은 사용하지 않는다.
"""
import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QWidget

_logger = logging.getLogger("app_error")

# SetWindowPos 상수
_HWND_TOP = 0
_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010
_SWP_FLAGS = _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE

# foreground WinEvent 상수
_EVENT_SYSTEM_FOREGROUND = 0x0003
_WINEVENT_OUTOFCONTEXT = 0x0000
_DESKTOP_WINDOW_CLASSES = {"Progman", "WorkerW"}
_TOPMOST_PULSE_MS = 350
_GW_HWNDPREV = 3
_GWL_EXSTYLE = -20
_WS_EX_TOPMOST = 0x00000008
_GA_ROOT = 2
_VK_LBUTTON = 0x01
_VK_RBUTTON = 0x02
_VK_MBUTTON = 0x04

_user32 = ctypes.WinDLL("user32", use_last_error=True)

# 64비트에서 HWND(포인터)와 HWND_TOPMOST(-1)를 올바르게 넘기려면 argtypes 지정 필수.
_SetWindowPos = _user32.SetWindowPos
_SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_uint,
]
_SetWindowPos.restype = wintypes.BOOL

_GetForegroundWindow = _user32.GetForegroundWindow
_GetForegroundWindow.argtypes = []
_GetForegroundWindow.restype = wintypes.HWND

_GetShellWindow = _user32.GetShellWindow
_GetShellWindow.argtypes = []
_GetShellWindow.restype = wintypes.HWND

_GetWindow = _user32.GetWindow
_GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
_GetWindow.restype = wintypes.HWND

_GetWindowLongPtrW = _user32.GetWindowLongPtrW
_GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_GetWindowLongPtrW.restype = ctypes.c_ssize_t

_GetWindowThreadProcessId = _user32.GetWindowThreadProcessId
_GetWindowThreadProcessId.argtypes = [
    wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
]
_GetWindowThreadProcessId.restype = wintypes.DWORD

_GetClassNameW = _user32.GetClassNameW
_GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_GetClassNameW.restype = ctypes.c_int

_GetAsyncKeyState = _user32.GetAsyncKeyState
_GetAsyncKeyState.argtypes = [ctypes.c_int]
_GetAsyncKeyState.restype = ctypes.c_short

_GetCursorPos = _user32.GetCursorPos
_GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_GetCursorPos.restype = wintypes.BOOL

_WindowFromPoint = _user32.WindowFromPoint
_WindowFromPoint.argtypes = [wintypes.POINT]
_WindowFromPoint.restype = wintypes.HWND

_GetAncestor = _user32.GetAncestor
_GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
_GetAncestor.restype = wintypes.HWND

_WinEventProc = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.HWND,
    wintypes.LONG,
    wintypes.LONG,
    wintypes.DWORD,
    wintypes.DWORD,
)

_SetWinEventHook = _user32.SetWinEventHook
_SetWinEventHook.argtypes = [
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HMODULE,
    _WinEventProc,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
]
_SetWinEventHook.restype = wintypes.HANDLE

_UnhookWinEvent = _user32.UnhookWinEvent
_UnhookWinEvent.argtypes = [wintypes.HANDLE]
_UnhookWinEvent.restype = wintypes.BOOL


def _window_class_name(hwnd: int) -> str:
    """Return a top-level window's Win32 class name, or an empty string."""
    if not hwnd:
        return ""
    buffer = ctypes.create_unicode_buffer(64)
    if not _GetClassNameW(hwnd, buffer, len(buffer)):
        return ""
    return buffer.value


def _window_process_id(hwnd: int) -> int:
    """Return the process id owning ``hwnd``, or zero on failure."""
    if not hwnd:
        return 0
    process_id = wintypes.DWORD()
    _GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return int(process_id.value)


def _window_is_topmost(hwnd: int) -> bool:
    """Whether a native window belongs to the topmost z-order band."""
    if not hwnd:
        return False
    try:
        return bool(_GetWindowLongPtrW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOPMOST)
    except (OSError, ValueError):
        return False


def _is_desktop_foreground(hwnd: int) -> bool:
    """Whether ``hwnd`` is the Windows shell's actual desktop host.

    ``GetShellWindow`` is the primary, documented identity. On Windows 11 the
    foreground desktop host can instead be a WorkerW/Progman owned by the same
    shell process, so class + shell PID is used as a narrowly-scoped fallback.
    Explorer folder windows (CabinetWClass) therefore do not match.
    """
    hwnd = int(hwnd or 0)
    shell_hwnd = int(_GetShellWindow() or 0)
    if not hwnd or not shell_hwnd:
        return False
    if hwnd == shell_hwnd:
        return True
    if _window_class_name(hwnd) not in _DESKTOP_WINDOW_CLASSES:
        return False
    shell_pid = _window_process_id(shell_hwnd)
    return bool(shell_pid and _window_process_id(hwnd) == shell_pid)


def _is_desktop_click() -> bool:
    """Whether a mouse button is held down over the shell desktop right now.

    Clicking the desktop makes it foreground exactly like Show Desktop does,
    but the shell then leaves the desktop at the bottom. Win+D and the taskbar
    corner button raise the desktop only after the foreground notification, so
    the pulse cannot wait for the cover to appear; it is skipped only for a
    click on the desktop itself.
    """
    try:
        if not any(
            _GetAsyncKeyState(vk) & 0x8000
            for vk in (_VK_LBUTTON, _VK_RBUTTON, _VK_MBUTTON)
        ):
            return False
        point = wintypes.POINT()
        if not _GetCursorPos(ctypes.byref(point)):
            return False
        hwnd = int(_WindowFromPoint(point) or 0)
        root = int(_GetAncestor(hwnd, _GA_ROOT) or 0) if hwnd else 0
    except (OSError, ValueError) as e:
        # 판정할 수 없으면 Win+D 보호(topmost pulse)를 유지한다.
        _logger.debug("바탕화면 클릭 확인 실패: %s", e)
        return False
    return _is_desktop_foreground(root)


class ShowDesktopKeeper(QObject):
    """Keep registered windows on Show Desktop without permanent topmost."""

    # HWND is pointer-sized; Signal(int) would truncate 64-bit window handles.
    _foreground_changed = Signal(object)

    def __init__(
        self,
        enabled: bool = True,
        parent=None,
        *,
        _install_hook: bool = True,
    ):
        super().__init__(parent)
        self._enabled = bool(enabled)
        self._guarded = []
        self._desktop_foreground = False
        self._desktop_hwnd = 0
        self._pulse_active = False
        self._win_event_hook = None
        self._win_event_callback = None

        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(_TOPMOST_PULSE_MS)
        self._settle_timer.timeout.connect(self._settle_topmost_pulse)

        # WinEvent callback 안에서는 Qt/창 조작을 하지 않고 다음 Qt 루프 턴으로 넘긴다.
        self._foreground_changed.connect(
            self._on_foreground_changed,
            Qt.ConnectionType.QueuedConnection,
        )

        if _install_hook:
            self._install_foreground_hook()

        # A context-free callable still runs while QObject.destroyed is emitted;
        # a bound slot on this same QObject is disconnected before that point.
        self.destroyed.connect(
            lambda *_args: self._uninstall_foreground_hook()
        )
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def set_enabled(self, on: bool) -> None:
        """실시간 on/off. OFF는 예약 작업을 취소하고 즉시 topmost를 해제한다."""
        self._enabled = bool(on)
        self._settle_timer.stop()
        self._pulse_active = False

        foreground = int(_GetForegroundWindow() or 0)
        if self._enabled and _is_desktop_foreground(foreground):
            self._on_desktop_foreground(foreground)
            return

        self._desktop_foreground = False
        if self._enabled and self._pin_to_desktop_layer():
            return
        self._demote_all(foreground)

    def is_enabled(self) -> bool:
        return self._enabled

    def is_operational(self) -> bool:
        """Whether the native foreground watcher is installed and usable."""
        return bool(self._win_event_hook and self._win_event_callback)

    def guard(self, widget: "QWidget | None") -> None:
        """Register a top-level widget without making it permanently topmost."""
        if widget is None or any(w is widget for w in self._guarded):
            return
        self._guarded.append(widget)
        widget.installEventFilter(self)
        if widget.isVisible():
            if self._enabled and self._pulse_active:
                self._apply_topmost(widget, True)
            elif not self._enabled or not self._pin_to_desktop_layer():
                self._apply_topmost(widget, False)

    def unguard(self, widget: QWidget) -> None:
        """폐기할 창의 이벤트 필터와 강한 참조를 즉시 해제한다."""
        self._guarded = [w for w in self._guarded if w is not widget]
        widget.removeEventFilter(self)

    def shutdown(self) -> None:
        """Release the system hook and leave every guarded window non-topmost."""
        self._settle_timer.stop()
        self._pulse_active = False
        self._desktop_foreground = False
        self._desktop_hwnd = 0
        self._enabled = False
        self._demote_all(int(_GetForegroundWindow() or 0))
        self._uninstall_foreground_hook()

    def _uninstall_foreground_hook(self) -> bool:
        """Idempotently release the native hook and its ctypes callback.

        If Win32 refuses to unhook, both references must stay alive. Dropping
        the ctypes callback while Windows can still call it would leave a
        dangling native function pointer.
        """
        hook = self._win_event_hook
        if not hook:
            self._win_event_callback = None
            return True
        if not _UnhookWinEvent(hook):
            _logger.warning(
                "ShowDesktopKeeper WinEvent hook 해제 실패: %s",
                ctypes.get_last_error(),
            )
            return False
        self._win_event_hook = None
        # ctypes callback이 GC되지 않게 설치 중에는 보관하고, 해제 뒤에만 놓는다.
        self._win_event_callback = None
        return True

    def _install_foreground_hook(self) -> None:
        self._win_event_callback = _WinEventProc(self._win_event_proc)
        hook = _SetWinEventHook(
            _EVENT_SYSTEM_FOREGROUND,
            _EVENT_SYSTEM_FOREGROUND,
            None,
            self._win_event_callback,
            0,
            0,
            _WINEVENT_OUTOFCONTEXT,
        )
        if not hook:
            _logger.warning(
                "바탕화면 foreground 감지 등록 실패: %s",
                ctypes.get_last_error(),
            )
            self._win_event_callback = None
            return
        self._win_event_hook = hook

    def _win_event_proc(
        self,
        _hook,
        event,
        hwnd,
        _object_id,
        _child_id,
        _event_thread,
        _event_time,
    ) -> None:
        """Minimal WinEvent callback; real work is queued onto Qt's event loop."""
        if event == _EVENT_SYSTEM_FOREGROUND:
            self._foreground_changed.emit(int(hwnd or 0))

    def _on_foreground_changed(self, hwnd: int) -> None:
        if not self._enabled:
            return
        if _is_desktop_foreground(hwnd):
            self._on_desktop_foreground(hwnd)
            return

        # 다른 앱이 활성화되면 남은 pulse가 그 앱을 다시 덮지 않도록 즉시 취소.
        self._desktop_foreground = False
        self._settle_timer.stop()
        self._pulse_active = False
        if not self._pin_to_desktop_layer():
            self._demote_all(hwnd)

    def _on_desktop_foreground(self, hwnd: int) -> None:
        """바탕화면이 foreground가 됨: 바탕화면 클릭이 아니면(Win+D 등) topmost pulse."""
        self._desktop_foreground = True
        self._desktop_hwnd = int(hwnd)
        if not _is_desktop_click():
            self._start_topmost_pulse()
            return
        # 바탕화면 클릭: 셸이 바탕화면을 올리지 않으므로 topmost로 올리지 않는다
        # (올리면 다른 앱 창 위로 잠깐 튀어나와 깜빡인다). settle에서 레이어만 재고정.
        self._settle_timer.start()

    def _start_topmost_pulse(self) -> None:
        self._pulse_active = True
        self._apply_to_all(True, visible_only=True)
        self._settle_timer.start()

    def _settle_topmost_pulse(self) -> None:
        """Re-pin to the desktop layer after the shell transition settles.

        Runs after a topmost pulse and also after a click on the desktop,
        where it only re-pins (never raises to topmost).
        """
        self._pulse_active = False
        foreground = int(_GetForegroundWindow() or 0)
        still_on_desktop = (
            self._enabled
            and self._desktop_foreground
            and _is_desktop_foreground(foreground)
        )
        if not still_on_desktop:
            self._desktop_foreground = False
        if not self._pin_to_desktop_layer(
            self._desktop_hwnd if still_on_desktop else 0
        ):
            self._demote_all(foreground)

    def _resolve_desktop_hwnd(self, preferred_hwnd: int = 0) -> int:
        """Return the current shell desktop host used as the z-order floor."""
        candidates = (
            int(preferred_hwnd or 0),
            int(self._desktop_hwnd or 0),
            int(_GetShellWindow() or 0),
        )
        for candidate in candidates:
            if candidate and _is_desktop_foreground(candidate):
                return candidate
        return 0

    def _pin_to_desktop_layer(self, preferred_hwnd: int = 0) -> bool:
        """Place guarded windows immediately above the desktop z-order host.

        ``SetWindowPos(HWND_NOTOPMOST)`` raises a window above every normal
        application window. Instead, find the window immediately preceding the
        desktop and insert each guarded window behind that boundary. This keeps
        desktop icons below us while Explorer, browsers, and other normal
        windows remain above us.
        """
        desktop_hwnd = self._resolve_desktop_hwnd(preferred_hwnd)
        if not desktop_hwnd:
            return False

        native_windows = self._native_guarded_windows()
        if not native_windows:
            return True

        guarded_hwnds = {hwnd for _widget, hwnd in native_windows}
        try:
            insert_after = int(
                _GetWindow(desktop_hwnd, _GW_HWNDPREV) or 0
            )
            seen = set()
            while insert_after in guarded_hwnds and insert_after not in seen:
                seen.add(insert_after)
                insert_after = int(
                    _GetWindow(insert_after, _GW_HWNDPREV) or 0
                )
        except (OSError, ValueError) as e:
            _logger.debug("바탕화면 z-order 경계 조회 실패: %s", e)
            return False

        # 경계가 topmost 창이면 상대 삽입으로 topmost band에 다시 들어갈 수
        # 있으므로, non-topmost band의 맨 위를 안전한 경계로 사용한다.
        if _window_is_topmost(insert_after):
            insert_after = _HWND_TOP

        # 데스크톱 위에 다른 일반 창이 없으면 non-topmost 그룹의 맨 위가
        # 곧 데스크톱 바로 위다. HWND_TOP은 영구 topmost를 만들지 않는다.
        insert_after = insert_after or _HWND_TOP
        success = True
        for widget, hwnd in native_windows:
            if not self._apply_topmost(widget, False, hwnd=hwnd):
                success = False
        for _widget, hwnd in native_windows:
            try:
                if not _SetWindowPos(
                    hwnd, insert_after, 0, 0, 0, 0, _SWP_FLAGS
                ):
                    success = False
                    _logger.debug(
                        "바탕화면 레이어 고정 실패: %s",
                        ctypes.get_last_error(),
                    )
            except (OSError, ValueError) as e:
                success = False
                _logger.debug("바탕화면 레이어 고정 예외: %s", e)
        return success

    def _demote_all(self, foreground_hwnd: int = 0) -> None:
        """Remove topmost and, for a real foreground app, keep it above us."""
        alive = self._apply_to_all(False)
        foreground_hwnd = int(foreground_hwnd or 0)
        if not foreground_hwnd:
            return
        for widget, hwnd in alive:
            if hwnd == foreground_hwnd:
                continue
            self._set_behind(widget, hwnd, foreground_hwnd)

    def _apply_to_all(
        self,
        on: bool,
        *,
        visible_only: bool = False,
    ) -> list[tuple[QWidget, int]]:
        """Apply z-order state and prune deleted Qt wrappers."""
        applied = self._native_guarded_windows(visible_only=visible_only)
        for widget, hwnd in applied:
            self._apply_topmost(widget, on, hwnd=hwnd)
        return applied

    def _native_guarded_windows(
        self,
        *,
        visible_only: bool = False,
    ) -> list[tuple[QWidget, int]]:
        """Return native guarded windows and prune deleted Qt wrappers."""
        alive_widgets = []
        applied = []
        for widget in self._guarded:
            try:
                # Do not call winId() solely for bookkeeping: it would create a
                # native handle for a guarded window that has never been shown.
                if not widget.testAttribute(
                    Qt.WidgetAttribute.WA_WState_Created
                ):
                    alive_widgets.append(widget)
                    continue
                if visible_only and not widget.isVisible():
                    alive_widgets.append(widget)
                    continue
                hwnd = int(widget.winId())
            except RuntimeError:
                continue
            alive_widgets.append(widget)
            applied.append((widget, hwnd))
        self._guarded = alive_widgets
        return applied

    @staticmethod
    def _apply_topmost(
        widget: QWidget,
        on: bool,
        *,
        hwnd: int | None = None,
    ) -> bool:
        """Set or clear WS_EX_TOPMOST without moving, resizing, or activating."""
        try:
            hwnd = int(widget.winId()) if hwnd is None else hwnd
            insert_after = _HWND_TOPMOST if on else _HWND_NOTOPMOST
            if not _SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, _SWP_FLAGS):
                _logger.debug(
                    "ShowDesktopKeeper SetWindowPos 실패: %s",
                    ctypes.get_last_error(),
                )
                return False
            return True
        except (RuntimeError, OSError, ValueError) as e:
            _logger.debug("ShowDesktopKeeper._apply_topmost 예외: %s", e)
            return False

    @staticmethod
    def _set_behind(widget: QWidget, hwnd: int, foreground_hwnd: int) -> None:
        """Place a demoted guarded window directly behind the foreground window."""
        try:
            if not _SetWindowPos(
                hwnd, foreground_hwnd, 0, 0, 0, 0, _SWP_FLAGS
            ):
                _logger.debug(
                    "ShowDesktopKeeper foreground 뒤 배치 실패: %s",
                    ctypes.get_last_error(),
                )
        except (RuntimeError, OSError, ValueError) as e:
            _logger.debug("ShowDesktopKeeper._set_behind 예외: %s", e)

    def eventFilter(self, obj, event) -> bool:
        # 감지만 하고 이벤트는 소비하지 않는다(return False).
        try:
            if isinstance(obj, QWidget) and obj.isWindow():
                event_type = event.type()
                if event_type == QEvent.Type.Show:
                    if self._enabled and self._pulse_active:
                        self._apply_topmost(obj, True)
                    elif not self._enabled or not self._pin_to_desktop_layer():
                        self._apply_topmost(obj, False)
                elif (
                    self._enabled
                    and event_type == QEvent.Type.WindowStateChange
                    and bool(obj.windowState() & Qt.WindowState.WindowMinimized)
                ):
                    QTimer.singleShot(0, lambda w=obj: self._restore(w))
        except RuntimeError as e:
            _logger.debug("ShowDesktopKeeper.eventFilter 예외: %s", e)
        return False

    @staticmethod
    def _restore(widget: QWidget) -> None:
        try:
            # Boss Key/privacy lock may hide a window after the minimize event
            # queued this restore. Clear the minimized state, but never undo an
            # intentional hide that happened in the meantime.
            was_visible = widget.isVisible()
            state = widget.windowState()
            if state & Qt.WindowState.WindowMinimized:
                widget.setWindowState(state & ~Qt.WindowState.WindowMinimized)
                if was_visible:
                    widget.show()
        except RuntimeError as e:
            _logger.debug("ShowDesktopKeeper._restore 예외: %s", e)
