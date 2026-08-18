# ui_dday.py - D-Day 위젯 (마감일 카운트다운)
from datetime import date, datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDialog,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QTimer, QPoint, QPointF, Signal
from PySide6.QtGui import QFont, QColor, QGuiApplication, QPainter, QPen

from qfluentwidgets import (
    LineEdit, PrimaryPushButton, PushButton, BodyLabel, CaptionLabel,
    TransparentToolButton, FluentIcon as FIF, MessageBox, InfoBar, InfoBarPosition,
)

from ui_sticky import _ColorGridPopup, WIDGET_WIDTH, DDAY_HEIGHT
import database as db

WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]

# ── 플로팅 카드 그림자/헤어라인 (배경에서 분리) ─────────────────
# 불변식: SHADOW_MARGIN ≥ SHADOW_BLUR + SHADOW_OFFSET_Y (아니면 창 경계에서 잘림)
SHADOW_MARGIN = 14
SHADOW_BLUR = 10
SHADOW_OFFSET_Y = 3
SHADOW_ALPHA = 90
HAIRLINE_ALPHA = 45

# ── Cover Tint 팔레트 (D-Day 전용 · 스티키 노트와 분리) ─────────────
# 진한 커버색 배경 + 전부 흰 타이포. STICKY_COLORS/STICKY_HEADER_COLORS를
# 재사용하지 않는다(스티키와 공유 상수라 건드리면 스티키까지 바뀜).
DDAY_COVER_COLORS = [
    ("#46679C", "하늘"),
    ("#A8801F", "노랑"),   # 스펙 #B8912C에서 흰 글씨 대비(≈3.6:1) 확보 위해 소폭 어둡게
    ("#2E8F6E", "민트"),
    ("#B25C8B", "핑크"),
]
_COVER_HEXES = {c.upper() for c, _ in DDAY_COVER_COLORS}
_DEFAULT_COVER = "#46679C"
# 구 파스텔 저장값 → 새 커버 (DB 데이터는 보존, 표시만 매핑)
_LEGACY_DDAY_COVER = {
    "#C4D5FF": "#46679C",  # sky (구 DEFAULT_DDAY_COLOR)
    "#FFFA8E": "#A8801F",  # yellow
    "#D0FFF1": "#2E8F6E",  # mint
    "#FFD8FB": "#B25C8B",  # pink
}


def dday_cover_color(stored: str) -> str:
    """저장된 D-Day 색(구 파스텔 또는 커버 hex)을 커버 hex로 해석."""
    key = (stored or "").strip().upper()
    if key in _LEGACY_DDAY_COVER:
        return _LEGACY_DDAY_COVER[key]
    if key in _COVER_HEXES:
        return key
    return _DEFAULT_COVER


def _dday_font(px: int, weight: QFont.Weight) -> QFont:
    """Pretendard(미로드 시 Malgun Gothic 폴백) 정수 픽셀 폰트."""
    font = QFont()
    font.setFamilies(["Pretendard", "Malgun Gothic", "Segoe UI"])
    font.setPixelSize(px)
    font.setWeight(weight)
    return font


class _CoverIconButton(QPushButton):
    """진한 커버 위에 흰색 X를 그리는 닫기 버튼. hover 시 옅은 흰 배경."""

    def __init__(self, size: int = 24, stroke: float = 1.5,
                 alpha: int = 140, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._stroke = stroke
        self._alpha = alpha
        self._hover = False
        self.setStyleSheet(
            "QPushButton{border:none;background:transparent;border-radius:8px;}"
        )

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if self._hover:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 36))
            painter.drawRoundedRect(self.rect(), 8, 8)
        alpha = 255 if self._hover else self._alpha
        pen = QPen(QColor(255, 255, 255, alpha))
        pen.setWidthF(self._stroke)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        m = w * 0.34
        painter.drawLine(QPointF(m, m), QPointF(w - m, h - m))
        painter.drawLine(QPointF(w - m, m), QPointF(m, h - m))
        painter.end()


class DDayCreateDialog(QDialog):
    """D-Day 위젯 생성/편집 다이얼로그"""

    def __init__(self, parent=None, name: str = "", target_date: str = ""):
        super().__init__(parent)
        self.setWindowTitle("D-Day 추가" if not name else "D-Day 편집")
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.setFixedSize(320, 200)

        self._result_name = ""
        self._result_date = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 이름 입력
        name_lbl = BodyLabel("이름", self)
        name_lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(name_lbl)
        self.name_input = LineEdit(self)
        self.name_input.setPlaceholderText("예: 보고서 마감")
        self.name_input.setMaxLength(30)
        self.name_input.setAttribute(Qt.WA_InputMethodEnabled, True)
        if name:
            self.name_input.setText(name)
        layout.addWidget(self.name_input)

        # 날짜 입력
        date_lbl = BodyLabel("목표 날짜", self)
        date_lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(date_lbl)

        date_row = QHBoxLayout()
        date_row.setSpacing(4)

        today = date.today()
        parts = target_date.split("-") if target_date else []

        self.year_input = LineEdit(self)
        self.year_input.setPlaceholderText("년")
        self.year_input.setFixedWidth(70)
        self.year_input.setMaxLength(4)
        self.year_input.setText(parts[0] if len(parts) == 3 else str(today.year))
        date_row.addWidget(self.year_input)

        date_row.addWidget(QLabel("-"))

        self.month_input = LineEdit(self)
        self.month_input.setPlaceholderText("월")
        self.month_input.setFixedWidth(50)
        self.month_input.setMaxLength(2)
        self.month_input.setText(parts[1] if len(parts) == 3 else "")
        date_row.addWidget(self.month_input)

        date_row.addWidget(QLabel("-"))

        self.day_input = LineEdit(self)
        self.day_input.setPlaceholderText("일")
        self.day_input.setFixedWidth(50)
        self.day_input.setMaxLength(2)
        self.day_input.setText(parts[2] if len(parts) == 3 else "")
        date_row.addWidget(self.day_input)

        date_row.addStretch()
        layout.addLayout(date_row)

        # 버튼
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = PushButton("취소", self)
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = PrimaryPushButton("확인", self)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)

        for edit in (self.name_input, self.year_input, self.month_input, self.day_input):
            edit.returnPressed.connect(self._on_ok)

        self.name_input.setFocus()

    def _on_ok(self):
        name = self.name_input.text().strip()
        if not name:
            InfoBar.warning(title="입력 오류", content="이름을 입력해 주세요.",
                            parent=self, position=InfoBarPosition.TOP, duration=2000)
            return

        try:
            y = int(self.year_input.text())
            m = int(self.month_input.text())
            d = int(self.day_input.text())
            target = date(y, m, d)
        except (ValueError, TypeError):
            InfoBar.warning(title="입력 오류", content="올바른 날짜를 입력해 주세요.",
                            parent=self, position=InfoBarPosition.TOP, duration=2000)
            return

        self._result_name = name
        self._result_date = target.isoformat()
        self.accept()

    def get_result(self) -> tuple[str, str]:
        return self._result_name, self._result_date


class DDayWidgetWindow(QWidget):
    """독립 플로팅 D-Day 카운트다운 위젯"""
    widget_closed = Signal(int)

    def __init__(self, widget_id: int, data: dict, parent=None):
        super().__init__(parent)
        self.widget_id = widget_id
        self._name = data.get("name", "")
        self._target_date = data.get("target_date", "")
        self._color = data.get("color", db.DEFAULT_DDAY_COLOR)
        self._drag_pos = None

        x = data.get("x_pos", 100)
        y = data.get("y_pos", 100)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(
            WIDGET_WIDTH + 2 * SHADOW_MARGIN, DDAY_HEIGHT + 2 * SHADOW_MARGIN
        )
        self.move(x, y)

        self._build_ui()
        self._apply_color(self._color, save=False)
        self._update_countdown()

        # 1분마다 카운트다운 갱신 (자정 넘김 대응)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(60_000)
        self._refresh_timer.timeout.connect(self._update_countdown)
        self._refresh_timer.start()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN
        )

        self.container = QWidget(self)
        self.container.setObjectName("ddayContainer")
        self.container.setAttribute(Qt.WA_StyledBackground, True)
        outer.addWidget(self.container)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(SHADOW_BLUR)
        shadow.setXOffset(0)
        shadow.setYOffset(SHADOW_OFFSET_Y)
        shadow.setColor(QColor(0, 0, 0, SHADOW_ALPHA))
        self.container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(14, 10, 11, 11)
        layout.setSpacing(0)

        # 상단: 흰 점(색상 변경) + 이름 + 닫기(X)
        top = QHBoxLayout()
        top.setSpacing(7)

        self.color_btn = QPushButton(self)
        self.color_btn.setFixedSize(14, 14)
        self.color_btn.setCursor(Qt.PointingHandCursor)
        self.color_btn.setFocusPolicy(Qt.NoFocus)
        self.color_btn.setToolTip("커버 색상 변경")
        self.color_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,235);"
            "border:2px solid rgba(255,255,255,64);border-radius:7px;}"
            "QPushButton:hover{background:#ffffff;}"
        )
        self.color_btn.clicked.connect(self._on_color_btn)
        top.addWidget(self.color_btn)

        self.name_label = QLabel(self._name)
        self.name_label.setFont(_dday_font(12, QFont.Weight.DemiBold))
        self.name_label.setStyleSheet(
            "color:rgba(255,255,255,230);background:transparent;"
        )
        top.addWidget(self.name_label, 1)

        self.close_btn = _CoverIconButton(24, 1.5, 140, self)
        self.close_btn.setToolTip("삭제")
        self.close_btn.clicked.connect(self._on_close)
        top.addWidget(self.close_btn, 0, Qt.AlignTop)

        layout.addLayout(top)
        layout.addStretch(1)

        # 하단: 카운트(좌, 크게) + 날짜(우) — 바닥 정렬
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(8)

        self.count_label = QLabel("")
        self.count_label.setFont(_dday_font(35, QFont.Weight.ExtraBold))
        self.count_label.setStyleSheet("color:#FFFFFF;background:transparent;")
        bottom.addWidget(self.count_label, 0, Qt.AlignBottom | Qt.AlignLeft)

        bottom.addStretch(1)

        self.date_label = QLabel("")
        self.date_label.setFont(_dday_font(10, QFont.Weight.Medium))
        self.date_label.setStyleSheet(
            "color:rgba(255,255,255,153);background:transparent;"
        )
        bottom.addWidget(self.date_label, 0, Qt.AlignBottom | Qt.AlignRight)

        layout.addLayout(bottom)

    def _update_countdown(self):
        """카운트다운 텍스트 갱신 (Cover Tint: 색 대신 표기+명도로 상태 구분)."""
        try:
            target = date.fromisoformat(self._target_date)
        except (ValueError, TypeError):
            self.count_label.setText("?")
            self.date_label.setText("")
            return

        delta = (target - date.today()).days
        wd = WEEKDAY_NAMES[target.weekday()]
        self.date_label.setText(
            f"{target.year}.{target.month:02d}.{target.day:02d} ({wd})"
        )

        if delta > 0:
            self.count_label.setText(f"D-{delta}")
            self.count_label.setStyleSheet("color:#FFFFFF;background:transparent;")
        elif delta == 0:
            self.count_label.setText("D-Day")
            self.count_label.setStyleSheet("color:#FFFFFF;background:transparent;")
        else:
            self.count_label.setText(f"D+{abs(delta)}")
            self.count_label.setStyleSheet(
                "color:rgba(255,255,255,140);background:transparent;"
            )

    def _apply_color(self, hex_color: str, save: bool = True):
        """저장색을 커버 hex로 매핑해 배경 적용.

        흰 타이포 전제. 어두운 배경 대비를 위해 옅은 흰 헤어라인 1px를 둔다
        (HAIRLINE_ALPHA=0이면 테두리 없음).
        """
        self._color = hex_color
        cover = dday_cover_color(hex_color)
        border = (
            f"border:1px solid rgba(255,255,255,{HAIRLINE_ALPHA});"
            if HAIRLINE_ALPHA > 0 else "border:none;"
        )
        self.container.setStyleSheet(
            f"#ddayContainer{{background:{cover};{border}border-radius:18px;}}"
        )
        if save:
            db.update_dday_widget(self.widget_id, color=hex_color)

    def _on_color_btn(self):
        popup = _ColorGridPopup(DDAY_COVER_COLORS, cols=4, parent=self)
        popup.color_selected.connect(lambda c: self._apply_color(c, save=True))
        pos = self.color_btn.mapToGlobal(QPoint(0, self.color_btn.height() + 6))
        popup.move(pos)
        popup.show()

    def _on_close(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("삭제 확인")
        dlg.setFixedSize(200, 100)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 12, 16, 12)
        lbl = QLabel("위젯을 삭제하시겠습니까?")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = PushButton("취소")
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        del_btn = PrimaryPushButton("삭제")
        del_btn.setDefault(True)
        del_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(del_btn)
        lay.addLayout(btn_row)
        if dlg.exec() == QDialog.Accepted:
            self._refresh_timer.stop()
            db.delete_dday_widget(self.widget_id)
            self.widget_closed.emit(self.widget_id)
            self.close()

    def mouseDoubleClickEvent(self, event):
        """더블클릭으로 편집"""
        if event.button() == Qt.LeftButton:
            dlg = DDayCreateDialog(self, self._name, self._target_date)
            if dlg.exec() == QDialog.Accepted:
                name, target_date = dlg.get_result()
                self._name = name
                self._target_date = target_date
                self.name_label.setText(name)
                self._update_countdown()
                db.update_dday_widget(self.widget_id, name=name, target_date=target_date)

    # ─── 드래그 이동 ─────────────────────────────────────────────
    @staticmethod
    def _snap_px():
        screen = QGuiApplication.primaryScreen()
        if screen:
            return max(1, round(screen.physicalDotsPerInch() * 5 / 25.4))
        return 19

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
            self.raise_()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            snap = self._snap_px()
            new_pos.setX(round(new_pos.x() / snap) * snap)
            new_pos.setY(round(new_pos.y() / snap) * snap)
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = None
            db.update_dday_widget(self.widget_id, x_pos=self.x(), y_pos=self.y())
