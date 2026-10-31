"""Windows 11 DWM 창 테두리가 팝업 메뉴 주위에 '넓은 사각 박스'로 보이는 문제 우회.

Windows 11은 모든 최상위 창 외곽에 시스템 테두리를 그린다(DWM). qfluentwidgets의
`RoundMenu`(콤보 드롭다운 `ComboBoxMenu` 포함)는 그림자 여백 때문에 창이 보이는
메뉴보다 크므로, 이 DWM 테두리가 투명 여백 바깥 창 경계를 따라 그려져
"메뉴보다 넓은 테두리 박스"로 보인다. Qt 쪽 완화(그림자/여백/QSS 제거)로는
지워지지 않음이 실측으로 확인됐다(OS가 그리는 선이므로).

해결: 메뉴 창이 표시될 때 `DwmSetWindowAttribute(DWMWA_BORDER_COLOR, COLOR_NONE)`
으로 해당 창의 DWM 테두리만 제거한다. 앱 레벨 이벤트 필터가 `RoundMenu` 계열의
Show 이벤트마다 적용하므로 개별 생성 지점을 수정할 필요가 없다.
Windows 10(빌드<22000)은 이 속성을 지원하지 않아 호출이 실패해도 무해하다(로깅만).
"""
import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QApplication

_logger = logging.getLogger("app_error")

DWMWA_BORDER_COLOR = 34
DWMWA_COLOR_NONE = 0xFFFFFFFE

try:
    _DwmSetWindowAttribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
    _DwmSetWindowAttribute.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    ]
    _DwmSetWindowAttribute.restype = ctypes.c_long  # HRESULT
except (OSError, AttributeError) as e:  # dwmapi 없는 환경(이론상)
    _DwmSetWindowAttribute = None
    _logger.debug("dwmapi 로드 실패, 팝업 테두리 우회 미적용: %s", e)


def remove_dwm_border(widget) -> bool:
    """widget 창의 DWM 테두리를 제거. 성공 시 True (Win10 등 미지원이면 False)."""
    if _DwmSetWindowAttribute is None:
        return False
    try:
        hwnd = int(widget.winId())
        color = ctypes.c_uint(DWMWA_COLOR_NONE)
        hr = _DwmSetWindowAttribute(
            hwnd, DWMWA_BORDER_COLOR, ctypes.byref(color), ctypes.sizeof(color)
        )
        return hr == 0
    except (RuntimeError, OSError, ValueError) as e:
        _logger.debug("remove_dwm_border 예외: %s", e)
        return False


class _PopupBorderFilter(QObject):
    """RoundMenu 계열 창이 표시될 때마다 DWM 테두리를 제거하는 앱 레벨 필터."""

    def __init__(self, menu_cls, parent=None):
        super().__init__(parent)
        self._menu_cls = menu_cls

    def eventFilter(self, obj, event) -> bool:
        try:
            if event.type() == QEvent.Type.Show and isinstance(obj, self._menu_cls):
                remove_dwm_border(obj)
        except RuntimeError as e:
            # 삭제 중인 객체 등. 이벤트 루프 보호 위해 로깅 후 계속.
            _logger.debug("_PopupBorderFilter 예외: %s", e)
        return False  # 이벤트는 소비하지 않는다


def install_popup_border_fix(app: QApplication):
    """앱에 팝업 테두리 우회 필터를 설치하고 필터 객체를 반환(참조 유지용)."""
    try:
        from qfluentwidgets import RoundMenu
    except ImportError as e:
        _logger.warning("RoundMenu 임포트 실패, 팝업 테두리 우회 미적용: %s", e)
        return None
    filt = _PopupBorderFilter(RoundMenu, parent=app)
    app.installEventFilter(filt)
    return filt
