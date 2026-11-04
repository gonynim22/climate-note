# ui_settings.py - 설정 창 UI (Export/Import/Reset/라이선스)
# 디자인: 시안 A (Fluent 정돈형) — 기존 2단 구조 유지, 정렬·그룹핑·단일 블루 액센트 통일.
import json
import os
import sys
import sqlite3
import tempfile
import winreg
from pathlib import Path
from datetime import datetime
from cryptography.fernet import InvalidToken

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog, QLineEdit, QApplication,
    QPushButton, QFrame, QLabel, QSizePolicy,
)
from PySide6.QtCore import Qt, QUrl, Signal, QSignalBlocker, QSize, QPoint
from PySide6.QtGui import QDesktopServices, QColor, QPainter, QPen, QPixmap, QIcon

from qfluentwidgets import (
    PushButton, LineEdit, BodyLabel,
    InfoBar, InfoBarPosition, MessageBox, Dialog,
    CardWidget, StrongBodyLabel, Theme,
    SwitchButton, ComboBox, Slider, FluentIcon as FIF,
    RoundMenu, Action,
)

from app_fonts import (
    APP_FONT_OPTIONS,
    SYSTEM_FONT_PREFIX,
    available_system_fonts,
    system_font_family_from_key,
    system_font_key,
)
from app_info import APP_DISPLAY_NAME, app_credit_text
from screen_placement import decode_screen, describe_screen, encode_screen, match_screen
import database as db
from security import (
    encrypt_with_pin, decrypt_with_pin, audit, APP_DIR, reset_salt,
    hash_privacy_pin, MIN_EXPORT_PASSWORD_LENGTH,
)

# ─── 시안 A 디자인 토큰 ────────────────────────────────────────
ACCENT = "#2563EB"            # 단일 블루 액센트
CARD_BORDER = "#D7DAE2"       # 섹션 카드 테두리
HEADER_BG = "#F6F6F6"         # 섹션 헤더 바 배경(CardWidget light hover 합성색)
HEADER_BORDER = "#D7DAE2"     # 섹션 헤더 하단 경계
ROW_DIVIDER = "#F2F3F6"       # 행 구분선
LABEL_COLOR = "#3A3E48"       # 행 라벨 색
INPUT_BORDER = "#D7DAE2"      # 입력 컨트롤 테두리

# ─── 시작프로그램 레지스트리 헬퍼 ─────────────────────────────────
_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = APP_DISPLAY_NAME


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """기존 Export를 보존하면서 같은 폴더에서 검증 가능한 원자 교체를 한다."""
    target = Path(path)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
                prefix=f".{target.name}.", suffix=".tmp",
                dir=target.parent, delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(payload)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, target)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError as e:
                audit("내보내기 임시 파일 정리", f"실패: {e}")


def _get_startup_cmd() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{Path(__file__).parent.parent / "main.py"}"'


def _is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
    except (OSError, FileNotFoundError):
        return False


def _set_startup(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _get_startup_cmd())
        else:
            try:
                winreg.DeleteValue(key, _APP_NAME)
            except FileNotFoundError:
                pass  # 이미 등록 해제된 상태 - 삭제할 값 없음(정상, 0023_NOACTION 사유 명시)


class _SettingsPanel(CardWidget):
    """섹션 카드: 흰 배경 + 시안 A 쿨그레이 라운드 테두리."""

    BORDER_COLOR = QColor(CARD_BORDER)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPanel")
        self.setBorderRadius(11)

    def _hoverBackgroundColor(self):
        return self._normalBackgroundColor()

    def _pressedBackgroundColor(self):
        return self._normalBackgroundColor()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._normalBackgroundColor())
        bg_rect = self.rect().adjusted(1, 1, -1, -1)
        painter.drawRoundedRect(bg_rect, self.borderRadius, self.borderRadius)

        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.setBrush(Qt.NoBrush)
        rect = self.rect().adjusted(0, 0, -1, -1)
        painter.drawRoundedRect(rect, self.borderRadius, self.borderRadius)


class _HoverIconButton(PushButton):
    """hover/press 시 아이콘 색을 배경 대비에 맞게 바꾸는 PushButton.

    qfluentwidgets PushButton은 정적 QIcon을 상태별로 재색칠하지 않으므로,
    소프트 danger 버튼처럼 hover 시 배경이 진해지면 같은 색 아이콘이 묻힌다.
    enter 시 hover_color, leave 시 normal_color 아이콘으로 교체해 항상 보이게 한다.

    주의: `__init__`은 오버라이드하지 않는다 — qfluentwidgets의 오버로드 생성자가
    내부에서 `self.__init__(...)`를 재호출하기 때문에 서브클래스에서 시그니처를 바꾸면 깨진다.
    생성은 기본 PushButton(icon, text, parent)으로 하고 set_hover_icons로 색을 지정한다.
    """

    def set_hover_icons(self, fif, normal_color, hover_color):
        self._normal_icon = fif.icon(color=QColor(normal_color))
        self._hover_icon = fif.icon(color=QColor(hover_color))
        self.setIcon(self._normal_icon)

    def enterEvent(self, event):
        super().enterEvent(event)
        if getattr(self, "_hover_icon", None) is not None:
            self.setIcon(self._hover_icon)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if getattr(self, "_normal_icon", None) is not None:
            self.setIcon(self._normal_icon)


class _ScaleOption(QFrame):
    """캘린더 크기 옵션 1개: 모니터 외곽 + 내부 앱 블록(크기로 스케일 표현) + 캡션.

    선택 시 외곽 옵션·모니터 테두리·앱 블록·캡션이 모두 블루(#2563EB)로 강조된다.
    """

    clicked = Signal(str)

    def __init__(self, value: str, caption: str, block_size: tuple, parent=None):
        super().__init__(parent)
        self.value = value
        self.setObjectName("scaleOption")
        self.setProperty("selected", "false")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(62)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 7)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignHCenter)

        screen = QFrame(self)
        screen.setObjectName("scaleScreen")
        screen.setFixedSize(30, 21)
        sl = QVBoxLayout(screen)
        sl.setContentsMargins(2, 2, 2, 2)
        sl.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        app = QFrame(screen)
        app.setObjectName("scaleApp")
        bw, bh = block_size
        app.setFixedSize(bw, bh)
        sl.addWidget(app)
        lay.addWidget(screen, 0, Qt.AlignHCenter)

        cap = BodyLabel(caption, self)
        cap.setObjectName("scaleCaption")
        cap.setAlignment(Qt.AlignHCenter)
        lay.addWidget(cap)

        self.setStyleSheet(
            "#scaleOption{border:1.5px solid #DEE1E8;border-radius:9px;background:#FFFFFF;}"
            "#scaleOption[selected=\"true\"]{border-color:#2563EB;background:#EFF4FF;}"
            "#scaleScreen{border:1.5px solid #5B5F6B;border-radius:3px;background:transparent;}"
            "#scaleOption[selected=\"true\"] #scaleScreen{border-color:#2563EB;}"
            "#scaleApp{background:#5B5F6B;border-radius:1px;}"
            "#scaleOption[selected=\"true\"] #scaleApp{background:#2563EB;}"
            "#scaleCaption{font-size:12px;color:#5B5F6B;background:transparent;}"
            "#scaleOption[selected=\"true\"] #scaleCaption{color:#2563EB;font-weight:600;}"
        )

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mouseReleaseEvent(self, event):
        self.clicked.emit(self.value)
        super().mouseReleaseEvent(event)


class CalendarSizePicker(QWidget):
    """캘린더 크기(compact/medium/large) 일러스트 선택 위젯.

    동일 크기 모니터 외곽 + 내부 앱 블록 크기로 스케일을 표현한다(외부 이미지 없음).
    저장은 하지 않는다 — 선택 시 scaleChanged(value) 시그널만 emit.
    """

    scaleChanged = Signal(str)
    _SCALES = [
        ("compact", "기본", (8, 6)),
        ("medium", "중간", (12, 9)),
        ("large", "크게", (18, 13)),
    ]

    def __init__(self, current: str, parent=None):
        super().__init__(parent)
        valid = {value for value, _, _ in self._SCALES}
        self._current = current if current in valid else "compact"
        self._options = {}

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for value, caption, block in self._SCALES:
            opt = _ScaleOption(value, caption, block, self)
            opt.clicked.connect(self.select)
            self._options[value] = opt
            lay.addWidget(opt)
        self._apply_highlight()

    def _apply_highlight(self) -> None:
        for value, opt in self._options.items():
            opt.set_selected(value == self._current)

    def select(self, value: str, *, emit: bool = True) -> None:
        if value not in self._options:
            return
        self._current = value
        self._apply_highlight()
        if emit:
            self.scaleChanged.emit(value)

    def current_scale(self) -> str:
        return self._current


def _schedule_color_icon(color: str, size: int = 16) -> QIcon:
    """RoundMenu 항목용 색상 원 아이콘."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#6B7280"), 1))
    painter.setBrush(QColor(color))
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return QIcon(pixmap)


class _ScheduleColorSwatch(QPushButton):
    """일정 슬롯 표시색을 보여 주는 작은 원형 버튼."""

    def __init__(self, slot_index: int, parent=None):
        super().__init__(parent)
        self.slot_index = slot_index
        self._color = db.DEFAULT_SCHEDULE_PALETTE[slot_index]
        self.setObjectName("scheduleColorSwatch")
        self.setFixedSize(24, 24)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"일정 색상 {slot_index + 1} 변경")
        self.setAccessibleName(f"일정 색상 {slot_index + 1}")
        self.set_color(self._color)

    def set_color(self, color: str) -> None:
        self._color = color
        self.setStyleSheet(
            "QPushButton#scheduleColorSwatch{"
            f"background:{color};border:1px solid #8B909A;border-radius:11px;"
            "}"
            "QPushButton#scheduleColorSwatch:hover{"
            "border:2px solid #2563EB;"
            "}"
            "QPushButton#scheduleColorSwatch:pressed{"
            "border:2px solid #1D4ED8;"
            "}"
        )

    def color(self) -> str:
        return self._color


class ScheduleColorPicker(QWidget):
    """10개 후보 중 서로 다른 일정 표시색 3개를 선택하는 컴팩트 picker."""

    colorsChanged = Signal(object)

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self._colors = list(db.normalize_schedule_palette(colors))
        self._buttons: list[_ScheduleColorSwatch] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        for slot_index, color in enumerate(self._colors):
            button = _ScheduleColorSwatch(slot_index, self)
            button.set_color(color)
            button.clicked.connect(
                lambda checked=False, index=slot_index: self._show_menu(index)
            )
            self._buttons.append(button)
            layout.addWidget(button)

    def colors(self) -> tuple[str, str, str]:
        return tuple(self._colors)

    def set_colors(self, colors) -> None:
        """저장 실패 등에서 시각 상태를 신호 없이 되돌린다."""
        self._colors = list(db.normalize_schedule_palette(colors))
        for button, color in zip(self._buttons, self._colors):
            button.set_color(color)

    def select_color(self, slot_index: int, color: str) -> bool:
        """테스트와 메뉴에서 공용으로 쓰는 선택 진입점."""
        if not 0 <= slot_index < len(self._colors):
            return False
        normalized = str(color).strip().upper()
        allowed = {value for value, _name in db.SCHEDULE_COLOR_OPTIONS}
        if normalized not in allowed:
            return False
        if normalized in self._colors and self._colors[slot_index] != normalized:
            return False
        if self._colors[slot_index] == normalized:
            return False

        self._colors[slot_index] = normalized
        self._buttons[slot_index].set_color(normalized)
        self.colorsChanged.emit(self.colors())
        return True

    def _show_menu(self, slot_index: int) -> None:
        button = self._buttons[slot_index]
        menu = RoundMenu(parent=self)
        menu.setWindowOpacity(1.0)
        used_by_other_slots = {
            color for index, color in enumerate(self._colors)
            if index != slot_index
        }
        for color, name in db.SCHEDULE_COLOR_OPTIONS:
            action = Action(_schedule_color_icon(color), name, menu)
            action.setCheckable(True)
            action.setChecked(color == self._colors[slot_index])
            action.setEnabled(color not in used_by_other_slots)
            action.triggered.connect(
                lambda checked=False, index=slot_index, value=color:
                self.select_color(index, value)
            )
            menu.addAction(action)
        menu.closedSignal.connect(menu.deleteLater)
        position = button.mapToGlobal(QPoint(0, button.height()))
        menu.exec(position)


class _PathLabel(QLabel):
    """경로 한 줄. 폭에 맞게 가운데를 줄이고 전체 경로는 툴팁으로 보인다."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setFixedWidth(190)
        self.setStyleSheet("font-size:12px;color:#6B7280;background:transparent;")
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self._apply()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply()

    def _apply(self) -> None:
        width = max(0, self.contentsRect().width())
        metrics = self.fontMetrics()
        text = self._full_text
        if metrics.horizontalAdvance(text) > width:
            # 드라이브와 마지막 폴더 이름은 남기고 그 사이만 줄인다: C:\…\MyDesktopCalendar
            parts = [part for part in text.replace("/", "\\").split("\\") if part]
            shortened = None
            if len(parts) > 2:
                tail = [parts[-1]]
                for part in reversed(parts[1:-1]):
                    trial = "\\".join([parts[0], "…", part, *tail])
                    if metrics.horizontalAdvance(trial) > width:
                        break
                    tail.insert(0, part)
                shortened = "\\".join([parts[0], "…", *tail])
            if shortened is None or metrics.horizontalAdvance(shortened) > width:
                shortened = metrics.elidedText(text, Qt.ElideMiddle, width)
            text = shortened
        super().setText(text)


class SettingsWindow(QWidget):
    """설정 창 (시안 A)"""
    reset_succeeded = Signal()

    def __init__(self, parent=None, on_reset_callback=None, on_import_callback=None,
                 on_quit_callback=None,
                 on_lunar_changed=None, on_law_search_changed=None,
                 on_position_changed=None, on_sidebar_changed=None,
                 on_opacity_changed=None, on_scale_changed=None,
                 on_keep_changed=None, on_schedule_colors_changed=None,
                 on_prepare_data_change=None, on_before_reset=None,
                 on_monitor_selected=None, on_holiday_theme_changed=None,
                 on_internet_access_changed=None):
        super().__init__(parent)
        self.on_reset_callback = on_reset_callback
        self.on_import_callback = on_import_callback
        self.on_quit_callback = on_quit_callback
        self.on_lunar_changed = on_lunar_changed
        self.on_holiday_theme_changed = on_holiday_theme_changed
        self.on_internet_access_changed = on_internet_access_changed
        self.on_law_search_changed = on_law_search_changed
        self.on_position_changed = on_position_changed
        self.on_monitor_selected = on_monitor_selected
        self.on_sidebar_changed = on_sidebar_changed
        self.on_opacity_changed = on_opacity_changed
        self.on_scale_changed = on_scale_changed
        self.on_keep_changed = on_keep_changed
        self.on_schedule_colors_changed = on_schedule_colors_changed
        self.on_prepare_data_change = on_prepare_data_change
        self.on_before_reset = on_before_reset
        self._license_dialog = None
        self.setWindowTitle("설정")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        # AGENTS.md 스펙 800x560 (시안 A 무스크롤). 520이면 우측 컬럼(데이터/보안/시스템,
        # 시스템 3행 기준 레이아웃 최소 546px)이 세로 압축되어 고정높이(34px) 버튼이
        # 행 구분선을 침범해 '겹쳐 보이는' 문제가 생긴다.
        self.resize(800, 560)
        self.setMinimumSize(800, 560)
        self._build_ui()

    # ─── 시안 A 공용 빌더 ─────────────────────────────────────
    def _section_icon(self, fif) -> QLabel:
        """섹션 헤더용 18px 블루 아이콘 라벨."""
        lbl = QLabel(self)
        lbl.setFixedSize(17, 17)
        lbl.setPixmap(fif.icon(color=QColor(ACCENT)).pixmap(QSize(17, 17)))
        lbl.setScaledContents(True)
        return lbl

    def _make_panel(self, title: str, icon=None) -> tuple:
        """섹션 카드: 밝은 헤더 바(아이콘+StrongBodyLabel) + 내부 행 레이아웃(body) 반환."""
        panel = _SettingsPanel(self)
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        header = QWidget(panel)
        header.setObjectName("panelHeaderBar")
        header.setStyleSheet(
            "#panelHeaderBar{background:%s;border:1px solid %s;border-bottom:1px solid %s;"
            "border-top-left-radius:11px;border-top-right-radius:11px;}" %
            (HEADER_BG, HEADER_BORDER, HEADER_BORDER))
        hb = QHBoxLayout(header)
        hb.setContentsMargins(16, 9, 16, 9)
        hb.setSpacing(9)
        if icon is not None:
            hb.addWidget(self._section_icon(icon), 0, Qt.AlignVCenter)
        header_label = StrongBodyLabel(title, header)
        header_label.setObjectName("panelHeader")
        # 색은 qfluentwidgets 네이티브 setTextColor로 고정(테마 재적용에도 안 흔들림),
        # 굵기는 setFont(Bold)로 보강(Malgun Gothic이 DemiBold로는 가볍게 렌더됨).
        header_label.setTextColor(QColor("#1A1A1E"), QColor("#1A1A1E"))
        hf = header_label.font()
        hf.setPixelSize(14)
        hf.setBold(True)
        header_label.setFont(hf)
        hb.addWidget(header_label, 0, Qt.AlignVCenter)
        hb.addStretch(1)
        v.addWidget(header)

        body = QVBoxLayout()
        body.setContentsMargins(16, 1, 16, 3)
        body.setSpacing(0)
        v.addLayout(body)
        return panel, body

    def _add_row(self, body: QVBoxLayout, label: str, control: QWidget,
                 label_width: int = 116, divider: bool = True,
                 row_height: int = 36) -> QWidget:
        """라벨-좌(고정폭) / 컨트롤-우(우측 정렬) 행. divider=True면 하단 1px 구분선 추가.

        row_height는 행의 최소 높이다. 800x560 무스크롤 창에 공휴일 테마·인터넷 접속 행 자리를 만들려고
        양쪽 열 모두 36을 쓴다.
        """
        row = QWidget(self)
        row.setObjectName("settingsRow")
        row.setMinimumHeight(row_height)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        lbl = BodyLabel(label, row)
        lbl.setObjectName("rowLabel")
        lbl.setStyleSheet(
            "#rowLabel{font-size:13px;font-weight:500;color:%s;background:transparent;}" % LABEL_COLOR)
        lbl.setFixedWidth(label_width)
        h.addWidget(lbl, 0, Qt.AlignVCenter)
        h.addStretch(1)
        h.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
        body.addWidget(row)
        if divider:
            line = QFrame(self)
            line.setObjectName("rowDivider")
            line.setFixedHeight(1)
            line.setStyleSheet("#rowDivider{background:%s;border:none;}" % ROW_DIVIDER)
            body.addWidget(line)
        return row

    def _make_switch(self, checked: bool, handler) -> SwitchButton:
        """텍스트 없는 시안 A 토글(블루 on은 전역 테마색에서 적용)."""
        sw = SwitchButton(self)
        sw.setOnText("")
        sw.setOffText("")
        sw.setChecked(checked)
        sw.checkedChanged.connect(handler)
        return sw

    def _outline_blue_button(self, text: str) -> PushButton:
        """아웃라인 블루 액션 버튼(실행 등)."""
        btn = PushButton(text, self)
        btn.setObjectName("outlineBtn")
        btn.setFixedHeight(34)
        btn.setStyleSheet(
            "PushButton#outlineBtn{background:#FFFFFF;color:#2563EB;border:1px solid #2563EB;"
            "border-radius:8px;padding:0 14px;font-size:13px;font-weight:600;}"
            "PushButton#outlineBtn:hover{background:#EFF4FF;}"
            "PushButton#outlineBtn:pressed{background:#DCE8FF;}")
        return btn

    def _pin_edit(self, *, importing=False) -> LineEdit:
        # 좁은 가운데 정렬 'PIN'은 버튼처럼 보여 입력칸 모양으로 넓힌다(디자인 점검 18번).
        edit = LineEdit(self)
        edit.setPlaceholderText("암호 / 이전 PIN" if importing else "암호 12자 이상")
        edit.setEchoMode(QLineEdit.Password)
        edit.setMaxLength(128)
        edit.setFixedWidth(110)
        edit.setToolTip("파일을 만들 때 사용한 암호 또는 이전 파일의 4자리 PIN" if importing
                        else "12자 이상의 긴 암호를 입력하세요. 새 파일은 v4.3 이상에서 가져올 수 있습니다.")
        edit.setStyleSheet("LineEdit{font-size:13px;}")  # 타입 스코프(컨텍스트 메뉴 전파 방지)
        return edit

    def _validate_pin(self, pin: str) -> bool:
        """4자리 숫자 PIN 유효성 검사, 실패 시 InfoBar 표시"""
        if len(pin) != 4 or not pin.isdigit():
            InfoBar.warning(
                title="PIN 오류",
                content="4자리 숫자 PIN을 입력해 주세요.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return False
        return True

    def _validate_transfer_password(self, password: str, *, importing=False) -> bool:
        legacy = importing and len(password) == 4 and password.isdigit()
        if legacy or (MIN_EXPORT_PASSWORD_LENGTH <= len(password) <= 128 and password.strip()):
            return True
        InfoBar.warning(title="암호 확인", content=("12자 이상의 암호 또는 이전 파일의 4자리 PIN을 입력해 주세요."
                        if importing else "내보내기 파일을 보호할 12자 이상의 긴 암호를 입력해 주세요."), parent=self)
        return False

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 10)
        outer.setSpacing(8)

        content_grid = QGridLayout()
        content_grid.setHorizontalSpacing(14)
        content_grid.setVerticalSpacing(0)
        content_grid.setColumnStretch(0, 1)
        content_grid.setColumnStretch(1, 1)
        # 그리드는 콘텐츠 자연 높이만 차지(stretch 0). 남는 세로 여백은 하단 stretch로 보내
        # 라이선스/크레딧/앱 종료 푸터가 패널 바로 아래에 붙도록 한다(중간의 빈 공간 제거).
        outer.addLayout(content_grid, 0)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        content_grid.addWidget(left, 0, 0, Qt.AlignTop)
        content_grid.addWidget(right, 0, 1, Qt.AlignTop)

        # ───── 화면 표시 ─────
        disp_panel, disp_body = self._make_panel("화면 표시", FIF.VIEW)

        # 모니터 (콤보 단독 행)
        self.monitor_combo = ComboBox(self)
        self.monitor_combo.setFixedWidth(210)
        self._monitor_screens = list(QApplication.screens())
        self._monitor_records = [describe_screen(screen) for screen in self._monitor_screens]
        for index, screen in enumerate(self._monitor_screens):
            geometry = screen.geometry()
            self.monitor_combo.addItem(
                f"모니터 {index + 1} ({geometry.width()}x{geometry.height()})",
                userData=str(index),
            )
        monitor_index = self.monitor_combo.findData(db.get_setting(db.SETTING_TARGET_SCREEN, "0"))
        preferred = match_screen(
            decode_screen(db.get_setting(db.SETTING_CALENDAR_SCREEN, "")), self._monitor_screens,
        )
        if preferred is not None:
            monitor_index = self._monitor_screens.index(preferred)
        if monitor_index >= 0:
            self.monitor_combo.setCurrentIndex(monitor_index)
        self._monitor_selection_index = self.monitor_combo.currentIndex()
        self.monitor_combo.currentIndexChanged.connect(self._on_monitor_changed)
        self._add_row(disp_body, "모니터", self.monitor_combo, row_height=36)

        # 화면 위치 (4모서리 그리드: 2x2)
        current_pos = db.get_setting(db.SETTING_CALENDAR_POSITION, "bottom-right")
        self._position_btns = {}
        pos_grid_frame = QFrame(self)
        pos_grid_frame.setObjectName("posGrid")
        pos_grid_frame.setStyleSheet(
            "#posGrid{background:#F4F5F8;border:1px solid #DCE0E8;border-radius:9px;}")
        pos_grid = QGridLayout(pos_grid_frame)
        pos_grid.setContentsMargins(9, 9, 9, 9)
        pos_grid.setSpacing(5)
        for pos_key, prow, pcol in [
            ("top-left", 0, 0), ("top-right", 0, 1),
            ("bottom-left", 1, 0), ("bottom-right", 1, 1),
        ]:
            button = QPushButton(self)
            button.setFixedSize(20, 20)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("pos_key", pos_key)
            button.clicked.connect(lambda checked=False, key=pos_key: self._on_position_changed(key))
            self._position_btns[pos_key] = button
            pos_grid.addWidget(button, prow, pcol)
        self._update_position_buttons(current_pos)
        self._position_row = self._add_row(
            disp_body, "화면 위치", pos_grid_frame, row_height=36)
        self._position_row.setMinimumHeight(60)

        # 전체 투명도
        opacity_control = QWidget(self)
        opacity_row = QHBoxLayout(opacity_control)
        opacity_row.setContentsMargins(0, 0, 0, 0)
        opacity_row.setSpacing(8)
        self.opacity_slider = Slider(Qt.Horizontal, self)
        self.opacity_slider.setObjectName("opacitySlider")
        self.opacity_slider.setRange(db.MIN_APP_OPACITY, 100)
        self.opacity_slider.setFixedWidth(150)
        try:
            opacity = int(db.get_setting(db.SETTING_APP_OPACITY, db.DEFAULT_APP_OPACITY))
        except (TypeError, ValueError):
            opacity = 100
        opacity = max(db.MIN_APP_OPACITY, min(100, opacity))
        self.opacity_slider.setValue(opacity)
        self.opacity_value_label = BodyLabel(f"{opacity}%", self)
        self.opacity_value_label.setStyleSheet(
            "font-size: 13px; color: #3A3E48; font-weight: 600;")
        self.opacity_value_label.setFixedWidth(38)
        self.opacity_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_value_label)
        self._add_row(disp_body, "전체 투명도", opacity_control, row_height=36)

        # 캘린더 크기 (일러스트 picker)
        self.scale_picker = CalendarSizePicker(
            db.get_setting(db.SETTING_CALENDAR_SCALE, db.DEFAULT_CALENDAR_SCALE), self)
        self.scale_picker.scaleChanged.connect(self._on_scale_changed)
        self._add_row(disp_body, "캘린더 크기", self.scale_picker, row_height=36)

        # 음력 및 공휴일
        self.lunar_switch = self._make_switch(
            db.get_setting(db.SETTING_SHOW_LUNAR, "0") == "1", self._on_lunar_toggled)
        self._add_row(disp_body, "음력 및 공휴일", self.lunar_switch, row_height=36)

        # 공휴일 테마 (섹션 마지막 행). 키가 없으면 켜짐.
        self.holiday_theme_switch = self._make_switch(
            db.get_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "1") == "1",
            self._on_holiday_theme_toggled)
        self.holiday_theme_switch.setToolTip("공휴일 3일 전부터 캘린더와 위젯에 그날 분위기를 입힙니다.")
        self._add_row(
            disp_body, "공휴일 테마", self.holiday_theme_switch, divider=False, row_height=36)

        left_layout.addWidget(disp_panel)

        # ───── 위젯·도구 ─────
        tools_panel, tools_body = self._make_panel("위젯·도구", FIF.TILES)
        self.sidebar_switch = self._make_switch(
            db.get_setting(db.SETTING_SHOW_SIDEBAR, "0") == "1", self._on_sidebar_toggled)
        # 중간·크게는 [바로가기 | 달력 | 일정] 배치라 늘 보이므로 이 스위치는 기본 크기에만 적용된다.
        self.sidebar_switch.setToolTip("기본 크기에서 바로가기 열을 보입니다. 중간·크게에서는 늘 보입니다.")
        self._add_row(tools_body, "기본 크기 바로가기", self.sidebar_switch, row_height=36)
        self.law_search_switch = self._make_switch(
            db.get_setting(db.SETTING_SHOW_LAW_SEARCH, "1") == "1", self._on_law_search_toggled)
        self._add_row(tools_body, "AI 법령검색", self.law_search_switch, row_height=36)
        self._saved_schedule_colors = db.get_schedule_palette()
        self.schedule_color_picker = ScheduleColorPicker(
            self._saved_schedule_colors, self
        )
        self.schedule_color_picker.colorsChanged.connect(
            self._on_schedule_colors_changed
        )
        self._add_row(
            tools_body, "일정 색상", self.schedule_color_picker, divider=False, row_height=36
        )
        left_layout.addWidget(tools_panel)
        left_layout.addStretch(1)

        # ───── 데이터 ─────
        data_panel, data_body = self._make_panel("데이터", FIF.SAVE)
        export_control = QWidget(self)
        export_row = QHBoxLayout(export_control)
        export_row.setContentsMargins(0, 0, 0, 0)
        export_row.setSpacing(8)
        self.export_pin = self._pin_edit()
        export_row.addWidget(self.export_pin)
        export_button = self._outline_blue_button("실행")
        export_button.clicked.connect(self._on_export)
        export_row.addWidget(export_button)
        self._add_row(data_body, "내보내기", export_control, label_width=80)

        import_control = QWidget(self)
        import_row = QHBoxLayout(import_control)
        import_row.setContentsMargins(0, 0, 0, 0)
        import_row.setSpacing(8)
        self.import_pin = self._pin_edit(importing=True)
        import_row.addWidget(self.import_pin)
        import_button = self._outline_blue_button("실행")
        import_button.clicked.connect(self._on_import)
        import_row.addWidget(import_button)
        self._add_row(data_body, "가져오기", import_control, label_width=80)

        self.open_data_folder_btn = PushButton(
            FIF.FOLDER.icon(color=QColor("#5B5F6B")), "", self)
        self.open_data_folder_btn.setObjectName("folderBtn")
        self.open_data_folder_btn.setFixedSize(34, 34)
        self.open_data_folder_btn.setToolTip("저장 폴더 열기")
        self.open_data_folder_btn.setStyleSheet(
            "PushButton#folderBtn{background:#FFFFFF;border:1px solid #D7DAE2;border-radius:8px;}"
            "PushButton#folderBtn:hover{background:#F2F3F6;}")
        self.open_data_folder_btn.clicked.connect(self._on_open_data_folder)
        # 저장 경로를 한 줄로 보이고(길면 가운데 말줄임, 전체는 툴팁) 폴더 버튼은 그대로 둔다(디자인 점검 18번).
        path_control = QWidget(self)
        path_row = QHBoxLayout(path_control)
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(8)
        self.data_path_label = _PathLabel(str(APP_DIR), path_control)
        path_row.addWidget(self.data_path_label)
        path_row.addWidget(self.open_data_folder_btn)
        self._add_row(data_body, "저장 경로", path_control, label_width=80, divider=False)
        right_layout.addWidget(data_panel)

        # ───── 보안 ─────
        sec_panel, sec_body = self._make_panel("보안", FIF.VPN)
        privacy_control = QWidget(self)
        privacy_row = QHBoxLayout(privacy_control)
        privacy_row.setContentsMargins(0, 0, 0, 0)
        privacy_row.setSpacing(8)
        self.pin_container = QWidget(self)
        pin_layout = QHBoxLayout(self.pin_container)
        pin_layout.setContentsMargins(0, 0, 0, 0)
        pin_layout.setSpacing(6)
        self.privacy_pin_edit = LineEdit(self)
        self.privacy_pin_edit.setPlaceholderText("새 PIN")
        self.privacy_pin_edit.setEchoMode(QLineEdit.Password)
        self.privacy_pin_edit.setToolTip("초기 PIN은 0000입니다. 새 4자리 PIN을 입력하고 저장하세요. 기존 PIN은 표시하지 않습니다.")
        self.privacy_pin_edit.setMaxLength(4)
        self.privacy_pin_edit.setFixedWidth(60)
        self.privacy_pin_edit.setAlignment(Qt.AlignCenter)
        self.privacy_pin_edit.setStyleSheet("LineEdit{font-size:13px;}")  # 타입 스코프
        pin_layout.addWidget(self.privacy_pin_edit)
        save_pin_button = PushButton("저장", self)
        save_pin_button.setFixedHeight(34)
        save_pin_button.setStyleSheet("font-size: 13px;")
        save_pin_button.setFixedWidth(52)
        save_pin_button.clicked.connect(self._on_save_privacy_pin)
        pin_layout.addWidget(save_pin_button)
        privacy_row.addWidget(self.pin_container)
        self.privacy_switch = self._make_switch(
            db.get_setting(db.SETTING_USE_PRIVACY_LOCK, "0") == "1", self._on_privacy_lock_toggled)
        privacy_row.addWidget(self.privacy_switch)
        self.pin_container.setVisible(self.privacy_switch.isChecked())
        self._add_row(sec_body, "개인정보 잠금", privacy_control)

        self.factory_reset_btn = _HoverIconButton(
            FIF.DELETE.icon(color=QColor("#DC2626")), "초기화", self)
        self.factory_reset_btn.set_hover_icons(FIF.DELETE, "#DC2626", "#FFFFFF")
        self.factory_reset_btn.setObjectName("factoryResetButton")
        self.factory_reset_btn.setToolTip("모든 데이터를 초기화")
        self.factory_reset_btn.setFixedHeight(34)
        self.factory_reset_btn.setMinimumWidth(152)
        self.factory_reset_btn.setStyleSheet("""
            PushButton#factoryResetButton {
                color: #DC2626; background: #FEF2F2; border: 1px solid #F0C2C2;
                border-radius: 6px; padding: 5px 14px 5px 34px;
                font-size: 12px; font-weight: 600;
            }
            PushButton#factoryResetButton:hover {
                background: #DC2626; color: #FFFFFF; border: 1px solid #DC2626;
            }
            PushButton#factoryResetButton:pressed {
                background: #B91C1C; color: #FFFFFF; border: 1px solid #B91C1C;
            }
        """)
        self.factory_reset_btn.clicked.connect(self._on_reset)
        # 데이터 초기화: 사용성 결정으로 PIN 미적용. 확인 팝업으로 우발 실행을 막는다.
        # (행안부 0011_IMPRAUTH 완화 — security 문서에 사유 명시)
        self._add_row(sec_body, "데이터 초기화", self.factory_reset_btn, divider=False)
        right_layout.addWidget(sec_panel)

        # ───── 시스템 ─────
        sys_panel, sys_body = self._make_panel("시스템", FIF.SETTING)
        self.startup_switch = self._make_switch(_is_startup_enabled(), self._on_startup_toggled)
        self._add_row(sys_body, "자동 실행", self.startup_switch)

        self.keep_desktop_switch = self._make_switch(
            db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP,
                           db.DEFAULT_KEEP_ON_SHOW_DESKTOP) == "1",
            self._on_keep_desktop_toggled)
        self._add_row(sys_body, "바탕화면 고정", self.keep_desktop_switch)

        # 인터넷 접속: 켠 PC만 새 버전을 확인한다. 키가 없으면 꺼짐.
        self.internet_switch = self._make_switch(
            db.get_setting(db.SETTING_INTERNET_ACCESS, "0") == "1", self._on_internet_access_toggled)
        self.internet_switch.setToolTip(
            "켜면 하루 한 번 GitLab 공개 저장소에서 새 버전이 있는지만 확인합니다. "
            "일정·메모는 보내지 않습니다. 업무망 PC는 꺼 두세요.")
        self._add_row(sys_body, "인터넷 접속", self.internet_switch)

        self.font_combo = ComboBox(self)
        self.font_combo.setFixedWidth(170)
        for label, value in APP_FONT_OPTIONS:
            self.font_combo.addItem(label, userData=value)
        self.font_combo.addItem("────────", userData="")
        self.font_combo.setItemEnabled(self.font_combo.count() - 1, False)
        for family in available_system_fonts():
            self.font_combo.addItem(family, userData=system_font_key(family))
        current_font = db.get_setting(db.SETTING_APP_FONT, db.DEFAULT_APP_FONT)
        font_index = self.font_combo.findData(current_font)
        if font_index < 0 and current_font.startswith(SYSTEM_FONT_PREFIX):
            font_index = self._add_missing_system_font(current_font)
        if font_index < 0:
            font_index = self.font_combo.findData(db.DEFAULT_APP_FONT)
        if font_index >= 0:
            self.font_combo.setCurrentIndex(font_index)
        self.font_combo.currentIndexChanged.connect(self._on_font_changed)
        self._add_row(sys_body, "앱 글꼴", self.font_combo, divider=False)
        right_layout.addWidget(sys_panel)
        right_layout.addStretch(1)

        # ───── 하단 바 (라이선스 · 저작 · 앱 종료) ─────
        footer_bar = QFrame(self)
        footer_bar.setObjectName("footerBar")
        footer_bar.setStyleSheet(
            "#footerBar{background:#FAFBFC;border-top:1px solid #ECEEF2;}")
        bottom_row = QHBoxLayout(footer_bar)
        bottom_row.setContentsMargins(4, 8, 4, 6)
        license_button = PushButton("라이선스", self)
        license_button.setObjectName("licenseBtn")
        license_button.setFixedHeight(32)
        license_button.setStyleSheet(
            "PushButton#licenseBtn{background:#FFFFFF;color:#5B5F6B;border:1px solid #D7DAE2;"
            "border-radius:7px;padding:0 13px;font-size:12px;font-weight:600;}"
            "PushButton#licenseBtn:hover{background:#F2F3F6;}")
        license_button.clicked.connect(self._on_license)
        bottom_row.addWidget(license_button)
        bottom_row.addStretch()
        self.author_label = BodyLabel(app_credit_text(), self)
        self.author_label.setStyleSheet("color: #9094A0; font-size: 12px;")
        # 한 줄 고정. 폭을 강제로 늘리지 않도록 가로 size policy는 Ignored(중앙 stretch가 폭 담당).
        self.author_label.setWordWrap(False)
        self.author_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.author_label.setAlignment(Qt.AlignCenter)
        bottom_row.addWidget(self.author_label, 1)
        bottom_row.addStretch()
        self.quit_app_btn = PushButton(FIF.POWER_BUTTON.icon(Theme.DARK), "앱 종료", self)
        self.quit_app_btn.setObjectName("quitAppButton")
        self.quit_app_btn.setToolTip("기후노트 종료")
        self.quit_app_btn.setFixedHeight(34)
        self.quit_app_btn.setMinimumWidth(112)
        self.quit_app_btn.setStyleSheet("""
            PushButton#quitAppButton {
                color: white; background: #1F2937; border: 1px solid #1A2433;
                border-radius: 6px; padding: 5px 12px 5px 32px;
                font-size: 12px; font-weight: 600;
            }
            PushButton#quitAppButton:hover {
                background: #111827; border: 1px solid #111827;
            }
            PushButton#quitAppButton:pressed {
                background: #0B1220; border: 1px solid #0B1220;
            }
        """)
        self.quit_app_btn.clicked.connect(self._on_quit)
        bottom_row.addWidget(self.quit_app_btn)
        outer.addStretch(1)
        outer.addWidget(footer_bar)

    def _on_opacity_changed(self, value: int):
        value = max(db.MIN_APP_OPACITY, min(100, int(value)))
        db.save_setting(db.SETTING_APP_OPACITY, str(value))
        self.opacity_value_label.setText(f"{value}%")
        if self.on_opacity_changed:
            self.on_opacity_changed()

    def _on_scale_changed(self, scale: str):
        if not scale:
            return
        previous = db.get_setting(db.SETTING_CALENDAR_SCALE, db.DEFAULT_CALENDAR_SCALE)
        try:
            db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
            if self.on_scale_changed and self.on_scale_changed() is False:
                self.scale_picker.select(previous, emit=False)
        except (sqlite3.Error, OSError, ValueError) as exc:
            self.scale_picker.select(previous, emit=False)
            audit("캘린더 크기 변경", f"실패: {type(exc).__name__}")
            InfoBar.error(title="크기 변경 보류", content="설정을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.", parent=self)

    def _on_schedule_colors_changed(self, colors) -> None:
        try:
            db.save_schedule_palette(colors)
        except (sqlite3.Error, ValueError) as e:
            self.schedule_color_picker.set_colors(self._saved_schedule_colors)
            audit("일정 색상 설정", f"실패: {e}")
            InfoBar.error(
                title="설정 오류",
                content="일정 색상을 저장하지 못했습니다.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return
        self._saved_schedule_colors = tuple(colors)
        if self.on_schedule_colors_changed:
            self.on_schedule_colors_changed()

    def _on_monitor_changed(self, index: int):
        if not 0 <= index < len(self._monitor_screens):
            return
        screens = QApplication.screens()
        selected = self._monitor_screens[index]
        if selected not in screens:
            selected = match_screen(self._monitor_records[index], screens)
        if selected is None:
            self._restore_monitor_selection()
            InfoBar.warning(
                title="모니터 연결 변경", content="선택한 모니터가 없습니다. 설정을 다시 열어 주세요.",
                parent=self, position=InfoBarPosition.TOP, duration=3000,
            )
            return
        if self.on_monitor_selected:
            if self.on_monitor_selected(selected):
                self._monitor_selection_index = index
            else:
                self._restore_monitor_selection()
            return
        try:
            db.save_settings({
                db.SETTING_TARGET_SCREEN: str(screens.index(selected)),
                db.SETTING_CALENDAR_SCREEN: encode_screen(selected),
            })
        except (sqlite3.Error, OSError, ValueError) as exc:
            self._restore_monitor_selection()
            import logging
            logging.getLogger("app_error").error("모니터 설정 저장 실패: %s", exc)
            InfoBar.error(title="저장 실패", content="모니터 설정을 저장하지 못했습니다.",
                          parent=self, position=InfoBarPosition.TOP, duration=3000)
            return
        self._monitor_selection_index = index
        if self.on_position_changed:
            self.on_position_changed()

    def _restore_monitor_selection(self):
        blocked = self.monitor_combo.blockSignals(True)
        self.monitor_combo.setCurrentIndex(self._monitor_selection_index)
        self.monitor_combo.blockSignals(blocked)

    # ─── 시작프로그램 토글 ──────────────────────────────────────
    def _on_startup_toggled(self, checked: bool):
        try:
            _set_startup(checked)
        except (OSError, PermissionError):
            InfoBar.error(
                title="오류",
                content="시작프로그램 설정에 실패했습니다.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            self.startup_switch.setChecked(not checked)

    # ─── 데이터 폴더 열기 ───────────────────────────────────────
    def _on_open_data_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(APP_DIR)))

    # ─── Export ────────────────────────────────────────────────
    def _on_export(self):
        if not self.isEnabled():
            return
        pin = self.export_pin.text()
        if not self._validate_transfer_password(pin):
            return
        if not self._prepare_data_change():
            return

        try:
            json_data = db.export_all_data()
            encrypted_bytes = encrypt_with_pin(json_data.encode("utf-8"), pin)
        except (OSError, ValueError, TypeError) as e:
            InfoBar.error(
                title="내보내기 실패",
                content=(
                    "일부 데이터를 안전하게 읽지 못해 내보내기를 중단했습니다. "
                    "원본 데이터는 변경되지 않았습니다."
                ),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            audit("데이터 내보내기", f"실패: {e}")
            return

        default_name = f"MyCalendar_{datetime.now().strftime('%Y%m%d')}.enc"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "내보내기 파일 저장", default_name, "암호화 파일 (*.enc)"
        )
        if not file_path or not self.isEnabled():
            return

        try:
            # 경로 조작 방지
            save_path = Path(file_path).resolve()
            _atomic_write_bytes(save_path, encrypted_bytes)
            audit("데이터 내보내기", "성공")
            InfoBar.success(
                title="내보내기 완료",
                content=f"저장 완료: {save_path.name}",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            self.export_pin.clear()
        except (OSError, PermissionError) as e:
            audit("데이터 내보내기", f"실패: {e}")
            InfoBar.error(
                title="저장 실패",
                content="파일 저장 중 오류가 발생했습니다.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )

    # ─── Import ────────────────────────────────────────────────
    def _prepare_data_change(self) -> bool:
        """보호백업/병합 전에 현재 편집 원본의 저장을 확정한다."""
        if not self.isEnabled():
            return False
        if self.on_prepare_data_change and not self.on_prepare_data_change():
            InfoBar.error(
                title="데이터 작업 보류",
                content="편집 내용을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.",
                parent=self, position=InfoBarPosition.TOP, duration=5000,
            )
            return False
        return True

    def _on_import(self):
        if not self.isEnabled():
            return
        pin = self.import_pin.text()
        if not self._validate_transfer_password(pin, importing=True):
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "가져오기 파일 선택", "", "암호화 파일 (*.enc)"
        )
        if not file_path or not self.isEnabled():
            return

        try:
            # 경로 조작 방지
            load_path = Path(file_path).resolve()
            with open(load_path, "rb") as import_file:
                encrypted_bytes = import_file.read()
            json_bytes = decrypt_with_pin(encrypted_bytes, pin)
            if not self._prepare_data_change():
                return
            db.backup_before_operation("import")
            limited = db.import_all_data(json_bytes.decode("utf-8")) or {}
            imported_palette = db.get_schedule_palette()
            self._saved_schedule_colors = imported_palette
            self.schedule_color_picker.set_colors(imported_palette)
            audit("데이터 가져오기", "성공")
            InfoBar.success(
                title="가져오기 완료",
                content=(
                    "데이터를 병합했습니다. 같은 파일을 반복해서 가져오면 "
                    "일정·위젯이 중복될 수 있습니다."
                    + (f" 표시 상한을 넘은 새 위젯 {sum(limited.values())}개는 데이터를 보존하고 닫힌 상태로 가져왔습니다."
                       if any(limited.values()) else "")
                ),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=6000,
            )
            self.import_pin.clear()
            if self.on_import_callback:
                self.on_import_callback()
        except (
            OSError, ValueError, TypeError, sqlite3.Error, KeyError, InvalidToken,
            AttributeError, db.DataHealthError,
        ) as e:
            audit("데이터 가져오기", f"실패: {e}")
            InfoBar.error(
                title="가져오기 실패",
                content="암호가 틀렸거나 파일이 손상되었거나 데이터 병합에 실패했습니다.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )

    # ─── Factory Reset ─────────────────────────────────────────
    def _on_reset(self):
        if not self.isEnabled():
            return
        # 데이터 초기화: PIN 없이 확인 팝업만 거친다(사용성 결정, 0011_IMPRAUTH 완화).
        dlg = MessageBox(
            "초기화 확인",
            "모든 일정, 메모, 스티키 노트가 영구적으로 삭제됩니다.\n정말 초기화하시겠습니까?",
            self
        )
        dlg.yesButton.setText("초기화")
        dlg.cancelButton.setText("취소")
        confirmed = dlg.exec()
        dlg.deleteLater()  # 0026_RESLEAK: 모달 종료 후 팝업 해제
        if confirmed and self.isEnabled():
            try:
                if not self._prepare_data_change():
                    return
                db.backup_before_operation("reset")
                if self.on_before_reset:
                    self.on_before_reset()
                try:
                    db.reset_database()
                    reset_salt()
                finally:
                    # 교체 실패 시에도 이전 타이머를 재개하지 않고 현재 DB로 UI를 복원한다.
                    if self.on_reset_callback:
                        self.on_reset_callback()
                audit("전체 초기화(Factory Reset)", "성공")
                self._set_internet_switch(False)  # 설정이 지워져 꺼짐이다. 열린 창의 스위치도 맞춘다
                self.reset_succeeded.emit()
                InfoBar.success(
                    title="초기화 완료",
                    content="모든 데이터가 초기화되었습니다.",
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                )
            except (
                OSError, sqlite3.Error, ValueError, RuntimeError,
            ) as e:
                audit("전체 초기화(Factory Reset)", f"실패: {e}")
                InfoBar.error(
                    title="초기화 실패",
                    content="초기화 중 오류가 발생했습니다.",
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                )

    def _on_save_privacy_pin(self):
        pin = self.privacy_pin_edit.text().strip()
        if not self._validate_pin(pin):
            return
        try:
            db.save_setting(db.SETTING_PRIVACY_PIN, hash_privacy_pin(pin))
        except (sqlite3.Error, OSError, ValueError) as exc:
            audit("잠금 PIN 변경", f"실패: {type(exc).__name__}")
            InfoBar.error(title="저장 실패", content="PIN을 저장하지 못했습니다. 다시 시도해 주세요.", parent=self)
            return
        self.privacy_pin_edit.clear()
        InfoBar.success(title="저장됨", content="잠금 PIN이 변경되었습니다.", parent=self)

    def _on_privacy_lock_toggled(self, checked: bool):
        db.save_setting(db.SETTING_USE_PRIVACY_LOCK, "1" if checked else "0")
        self.pin_container.setVisible(checked)
        InfoBar.info(title="잠금 설정", content="이제 앱 진입 시 PIN을 확인합니다." if checked else "잠금 기능이 비활성화되었습니다.", parent=self)

    def _on_lunar_toggled(self, checked: bool):
        db.save_setting(db.SETTING_SHOW_LUNAR, "1" if checked else "0")
        if self.on_lunar_changed:
            self.on_lunar_changed()
        if checked:
            InfoBar.info(title="음력 및 공휴일 표시", content="달력에 음력과 공휴일이 표시됩니다.", parent=self)
        else:
            InfoBar.info(title="설정 변경", content="음력 및 공휴일 표시가 비활성화되었습니다.", parent=self)

    def _on_holiday_theme_toggled(self, checked: bool):
        """공휴일 테마 스위치: 키 하나만 저장하고 화면 갱신은 콜백에 맡긴다(알림 없음)."""
        db.save_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "1" if checked else "0")
        if self.on_holiday_theme_changed:
            self.on_holiday_theme_changed()

    def _on_law_search_toggled(self, checked: bool):
        db.save_setting(db.SETTING_SHOW_LAW_SEARCH, "1" if checked else "0")
        if self.on_law_search_changed:
            self.on_law_search_changed()
        if checked:
            InfoBar.info(title="AI 법령정보 검색", content="법령검색 바가 활성화되었습니다.", parent=self)
        else:
            InfoBar.info(title="설정 변경", content="법령검색 바가 비활성화되었습니다.", parent=self)

    def _on_sidebar_toggled(self, checked: bool):
        db.save_setting(db.SETTING_SHOW_SIDEBAR, "1" if checked else "0")
        if self.on_sidebar_changed:
            self.on_sidebar_changed()
        if checked:
            InfoBar.info(title="사이드바 활성화", content="사이드바가 화면 좌측에 표시됩니다.", parent=self)
        else:
            InfoBar.info(title="설정 변경", content="사이드바가 비활성화되었습니다.", parent=self)

    def _on_keep_desktop_toggled(self, checked: bool):
        db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "1" if checked else "0")
        if self.on_keep_changed:
            self.on_keep_changed()

    def _on_internet_access_toggled(self, checked: bool):
        """키 하나만 저장한다. 끄기 저장이 실패한 채 화면만 꺼지면 요청이 계속 나가므로 스위치를 되돌린다."""
        try:
            db.save_setting(db.SETTING_INTERNET_ACCESS, "1" if checked else "0")
        except (sqlite3.Error, OSError, ValueError) as e:
            self._set_internet_switch(not checked)  # DB를 다시 읽지 않는다: 읽기도 실패할 수 있다
            audit("인터넷 접속 설정", f"실패: {type(e).__name__}")
            InfoBar.error(
                title="설정 오류",
                content="인터넷 접속 설정을 저장하지 못했습니다.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return
        audit("인터넷 접속 켬" if checked else "인터넷 접속 끔")
        if self.on_internet_access_changed:
            self.on_internet_access_changed()

    def _set_internet_switch(self, checked: bool) -> None:
        """저장 없이 스위치 모양만 맞춘다. 신호를 막아야 처리기가 저장을 다시 시도하지 않는다."""
        with QSignalBlocker(self.internet_switch):
            self.internet_switch.setChecked(checked)

    def _on_font_changed(self, index: int):
        font_key = self.font_combo.itemData(index)
        if not font_key:
            return
        db.save_setting(db.SETTING_APP_FONT, font_key)
        InfoBar.error(
            title="재시작 필요",
            content="글꼴 변경은 앱을 재시작해야 적용됩니다.",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=7000,
        )

    def _add_missing_system_font(self, font_key: str) -> int:
        family = system_font_family_from_key(font_key)
        if not family:
            return -1
        self.font_combo.addItem(f"{family} (없음)", userData=font_key)
        index = self.font_combo.count() - 1
        self.font_combo.setItemEnabled(index, False)
        return index

    # ─── 캘린더 위치 ──────────────────────────────────────────
    def _update_position_buttons(self, active_key: str):
        """선택된 모서리 셀 강조 (블루 채움), 미선택은 흰 셀."""
        for key, btn in self._position_btns.items():
            if key == active_key:
                btn.setStyleSheet(
                    "QPushButton{background:#2563EB;border:1px solid #2563EB;border-radius:4px;}")
            else:
                btn.setStyleSheet(
                    "QPushButton{background:#FFFFFF;border:1px solid #D7DAE2;border-radius:4px;}"
                    "QPushButton:hover{border:1px solid #2563EB;background:#EFF4FF;}")

    def _on_position_changed(self, pos_key: str):
        db.save_setting(db.SETTING_CALENDAR_POSITION, pos_key)
        self._update_position_buttons(pos_key)
        if self.on_position_changed:
            self.on_position_changed()

    # ─── 라이선스 ──────────────────────────────────────────────
    def _on_license(self):
        from ui_licenses import LicenseDialog

        if not self.isVisible() or not self.isEnabled():
            return
        if self._license_dialog is not None:
            self._license_dialog.raise_()
            self._license_dialog.activateWindow()
            return
        dlg = LicenseDialog(self)
        self._license_dialog = dlg
        dlg.finished.connect(lambda _result: setattr(self, "_license_dialog", None))
        dlg.open()

    # ─── 앱 종료 ───────────────────────────────────────────────
    def _on_quit(self):
        if self.on_quit_callback and not self.on_quit_callback():
            return
        # 설정창(top-level)을 먼저 닫고 종료한다. 메인 closeEvent는 트레이로 최소화만 하므로,
        # 설정창이 닫히지 않으면 한 번에 완전히 종료되지 않는다.
        self.close()
        QApplication.quit()
