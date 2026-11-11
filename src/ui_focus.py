# ui_focus.py - 집중 모드 위젯
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDialog,
    QGridLayout, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QPoint, QEvent
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap

from qfluentwidgets import (
    LineEdit, PrimaryPushButton, PushButton, BodyLabel, CaptionLabel,
    ComboBox, TransparentToolButton, FluentIcon as FIF, InfoBar, InfoBarPosition,
    Theme,
)

import database as db
from app_paths import resource_root
from ui_holiday_decor import DecorationLayer
from ui_holiday_theme import HAT_OFFSET_UNITS, hat_pixmap


FOCUS_DISTRACTIONS = ["없음", "알림", "피로", "난이도", "기타"]
AMBIENT_SIZE = (241, 78)
GLANCE_SIZE = (241, 126)
TOMATO_MINI_IMAGE_SIZE = 38
TOMATO_IMAGE_SIZE = 50
FOCUS_BUBBLE_DURATION_MS = 3000
FOCUS_CARD_GRADIENT = (
    "qlineargradient("
    "x1:0, y1:0, x2:1, y2:1, "
    "stop:0 #FFFFFF, "
    "stop:0.48 #EEF6FF, "
    "stop:1 #DDE8FF"
    ")"
)
FOCUS_ACCENT_COLOR = "#FF5A45"


def focus_card_gradient(theme=None) -> str:
    """집중 위젯 normal 바탕 그라데이션. 공휴일 테마가 있으면 그 연한색·끝색으로 그린다(화면 전용)."""
    if theme is None:
        return FOCUS_CARD_GRADIENT
    return (
        "qlineargradient("
        "x1:0, y1:0, x2:1, y2:1, "
        f"stop:0 #FFFFFF, stop:0.48 {theme.tint}, stop:1 {theme.focus_end}"
        ")"
    )


_IMAGE_DIR = resource_root() / "resources" / "images"
TOMATO_MINI_IMAGE_PATH = _IMAGE_DIR / "tomato_mini.png"
TOMATO_IMAGE_PATH = _IMAGE_DIR / "tomato.png"
FOCUS_ENCOURAGEMENT_MESSAGES = (
    "지금도 충분히 잘했어",
    "내일은 더 빛날 거야",
    "너는 너라서 특별해",
    "다 잘될 거니 걱정 마",
    "잠시 쉬어가도 괜찮아",
    "오늘도 고생 많았어",
    "결국 다 지나갈 거야",
    "포기하지 않는 게 용기",
    "너를 믿어",
    "넌 할 수 있어",
    "너의 걸음을 응원해",
    "어제보다 성장한 오늘",
    "작은 행복부터 찾아봐",
    "시작이 반이야",
    "힘내",
    "가장 소중한 건 바로 너",
    "포기하긴 아직 일러",
    "너의 진심은 통할 거야",
    "밝게 빛날 너의 미래",
    "오늘의 너를 사랑해줘",
    "견뎌낸 만큼 강해질 거야",
    "함께니까 걱정하지 마",
)


def focus_mode_display_text(mode_key: str) -> str:
    label, focus_minutes, break_minutes = db.FOCUS_MODES.get(
        mode_key, db.FOCUS_MODES[db.DEFAULT_FOCUS_MODE]
    )
    description = f"{focus_minutes}분 집중/{break_minutes}분 휴식"
    if mode_key == "25/5":
        description += ", 포모도로"
    return f"{label} ({description})"


class FocusTimer:
    """UI와 분리된 집중 세션 타이머."""

    def __init__(self, mode_key: str = db.DEFAULT_FOCUS_MODE,
                 now_provider=None, goal: str = ""):
        self._now = now_provider or datetime.now
        self.goal = goal
        self.mode_key = mode_key if mode_key in db.FOCUS_MODES else db.DEFAULT_FOCUS_MODE
        self.mode_label, self.focus_minutes, self.break_minutes = db.FOCUS_MODES[self.mode_key]
        self.status = "idle"
        self.phase = "focus"
        self.started_at: datetime | None = None
        self.ended_at: datetime | None = None
        self._run_started_at: datetime | None = None
        self._elapsed_before_pause = 0

    @property
    def duration_seconds(self) -> int:
        minutes = self.break_minutes if self.phase == "break" else self.focus_minutes
        return max(1, minutes * 60)

    def set_mode(self, mode_key: str) -> None:
        if mode_key not in db.FOCUS_MODES:
            mode_key = db.DEFAULT_FOCUS_MODE
        self.mode_key = mode_key
        self.mode_label, self.focus_minutes, self.break_minutes = db.FOCUS_MODES[mode_key]

    def start(self, goal: str = "") -> None:
        self.goal = goal
        now = self._now()
        self.phase = "focus"
        self.started_at = now
        self.ended_at = None
        self._run_started_at = now
        self._elapsed_before_pause = 0
        self.status = "running"

    def start_break(self) -> None:
        now = self._now()
        self.phase = "break"
        self.started_at = now
        self.ended_at = None
        self._run_started_at = now
        self._elapsed_before_pause = 0
        self.status = "running"

    def pause(self) -> None:
        if self.status != "running":
            return
        self._elapsed_before_pause = self.elapsed_seconds()
        self._run_started_at = None
        self.status = "paused"

    def resume(self) -> None:
        if self.status != "paused":
            return
        self._run_started_at = self._now()
        self.status = "running"

    def extend(self, minutes: int = 5) -> None:
        self.focus_minutes += max(1, minutes)

    def stop(self) -> None:
        if self.status == "ended":
            return
        self._elapsed_before_pause = self.elapsed_seconds()
        self._run_started_at = None
        self.ended_at = self._now()
        self.status = "ended"

    def elapsed_seconds(self) -> int:
        elapsed = self._elapsed_before_pause
        if self.status == "running" and self._run_started_at is not None:
            elapsed += int((self._now() - self._run_started_at).total_seconds())
        return max(0, elapsed)

    def remaining_seconds(self) -> int:
        return max(0, self.duration_seconds - self.elapsed_seconds())

    def progress_ratio(self) -> float:
        return min(1.0, self.elapsed_seconds() / self.duration_seconds)

    def progress_percent(self) -> int:
        return int(self.progress_ratio() * 100)

    def is_complete(self) -> bool:
        return self.status == "running" and self.remaining_seconds() <= 0

    def next_break_at(self) -> datetime | None:
        if self.started_at is None or self.phase == "break":
            return None
        return self.started_at + timedelta(seconds=self.duration_seconds)


class FocusProgressRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 0.0
        self.setFixedSize(46, 46)

    def set_progress(self, progress: float) -> None:
        self._progress = max(0.0, min(1.0, progress))
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(6, 6, self.width() - 12, self.height() - 12)

        base_pen = QPen(QColor(255, 90, 69, 55), 4)
        base_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(base_pen)
        painter.drawEllipse(rect)

        progress_pen = QPen(QColor(255, 90, 69, 220), 4)
        progress_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(progress_pen)
        painter.drawArc(rect, 90 * 16, int(-360 * 16 * self._progress))


class FocusGoalLabel(QLabel):
    """목표 문구를 칸 폭에 맞게 말줄임한다. 줄였을 때만 전체 문구를 툴팁으로 보여 준다.

    QLabel은 글자 전체 폭을 최소 폭으로 잡아, 고정 폭 위젯에서는 끝이 잘리고
    크게 모드 오른쪽 열에서는 카드 폭을 밀어낸다. 가로 Ignored로 레이아웃이 준 폭만 쓴다.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full_text = text or ""
        self._apply_elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide()

    def changeEvent(self, event):
        super().changeEvent(event)
        # 스타일시트 글꼴(12px 굵게)은 표시 직전에 적용되므로 그때 다시 잰다.
        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._apply_elide()

    def _apply_elide(self) -> None:
        width = self.contentsRect().width()
        shown = (
            self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, width)
            if width > 0 else self._full_text
        )
        if shown != self._full_text and shown.endswith("…"):
            shown = shown[:-1].rstrip() + "…"  # 단어 사이에서 잘리면 "초안 …" 대신 "초안…"
        super().setText(shown)
        self.setToolTip(self._full_text if shown != self._full_text else "")


class _ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class FocusCreateDialog(QDialog):
    """집중 모드 위젯 생성 다이얼로그."""

    def __init__(self, parent=None, goal: str = "", mode_key: str = db.DEFAULT_FOCUS_MODE):
        super().__init__(parent)
        self.setWindowTitle("집중 모드 추가")
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.setFixedSize(430, 270)
        self._result_goal = ""
        self._result_mode_key = db.DEFAULT_FOCUS_MODE

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(10)

        # D-Day 만들기 창과 같은 틀: 창 안 제목, 버튼 위 여백(디자인 점검 17번).
        self.title_label = QLabel("집중 모드 추가", self)
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #172B4D;")
        layout.addWidget(self.title_label)

        goal_lbl = BodyLabel("오늘의 한 가지 목표", self)
        goal_lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(goal_lbl)

        self.goal_input = LineEdit(self)
        self.goal_input.setPlaceholderText("예: 보고서 초안 정리")
        self.goal_input.setMaxLength(60)
        self.goal_input.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.goal_input.setText(goal)
        layout.addWidget(self.goal_input)

        mode_lbl = BodyLabel("세션 모드", self)
        mode_lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(mode_lbl)

        self.mode_combo = ComboBox(self)
        for key, (label, focus_minutes, break_minutes) in db.FOCUS_MODES.items():
            self.mode_combo.addItem(focus_mode_display_text(key), userData=key)
        index = self.mode_combo.findData(mode_key)
        self.mode_combo.setCurrentIndex(index if index >= 0 else 0)
        layout.addWidget(self.mode_combo)
        layout.addSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = PushButton("취소", self)
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        start_btn = PrimaryPushButton("시작", self)
        start_btn.setDefault(True)
        start_btn.clicked.connect(self._accept)
        btn_row.addWidget(start_btn)

        layout.addLayout(btn_row)
        self.goal_input.returnPressed.connect(self._accept)
        self.goal_input.setFocus()

    def _accept(self) -> None:
        goal = self.goal_input.text().strip()
        if not goal:
            InfoBar.warning(
                title="입력 오류",
                content="집중 목표를 입력해 주세요.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000,
            )
            return
        self._result_goal = goal
        self._result_mode_key = self.mode_combo.currentData() or db.DEFAULT_FOCUS_MODE
        self.accept()

    def get_result(self) -> tuple[str, str, bool]:
        return self._result_goal, self._result_mode_key, True


class FocusReviewDialog(QDialog):
    """집중 세션 종료 후 간단 회고."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("집중 회고")
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.setFixedSize(300, 170)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        grid.addWidget(BodyLabel("집중도", self), 0, 0)
        self.rating_combo = ComboBox(self)
        for i in range(1, 6):
            self.rating_combo.addItem(str(i), userData=i)
        self.rating_combo.setCurrentIndex(3)
        grid.addWidget(self.rating_combo, 0, 1)

        grid.addWidget(BodyLabel("방해 요인", self), 1, 0)
        self.distraction_combo = ComboBox(self)
        for item in FOCUS_DISTRACTIONS:
            self.distraction_combo.addItem(item, userData=item)
        grid.addWidget(self.distraction_combo, 1, 1)
        layout.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        skip_btn = PushButton("건너뛰기", self)
        skip_btn.setAutoDefault(False)
        skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(skip_btn)

        save_btn = PrimaryPushButton("저장", self)
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def get_result(self) -> tuple[int, str]:
        return self.rating_combo.currentData(), self.distraction_combo.currentData()


class FocusBreakPromptDialog(QDialog):
    """집중 완료 후 휴식 시작 여부를 묻는 조용한 알림."""

    def __init__(self, break_minutes: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("집중 모드 완료")
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.setFixedSize(320, 130)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        message = BodyLabel(f"집중 모드 완료, {break_minutes}분 휴식하시겠습니까?", self)
        message.setWordWrap(True)
        layout.addWidget(message)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        skip_btn = PushButton("건너뛰기", self)
        skip_btn.setAutoDefault(False)
        skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(skip_btn)

        break_btn = PrimaryPushButton("휴식 시작", self)
        break_btn.setDefault(True)
        break_btn.clicked.connect(self.accept)
        btn_row.addWidget(break_btn)

        layout.addLayout(btn_row)


class FocusWidgetWindow(QWidget):
    """방해를 최소화한 플로팅 집중 모드 위젯."""
    widget_closed = Signal(int)

    def __init__(self, widget_id: int, data: dict, parent=None, auto_start: bool = False):
        super().__init__(parent)
        self.widget_id = widget_id
        self._goal = data.get("goal", "")
        self._mode_key = data.get("mode_key", db.DEFAULT_FOCUS_MODE)
        self._drag_pos = None
        self._display_mode = "ambient"
        self._session_saved = False
        self._visual_state = "normal"
        self._holiday_theme = None   # 공휴일 테마(표시 전용). 집중 세션·저장값과 따로 쥔다
        self._hat_drawn = {}         # 모자 레이블 이름 -> 마지막으로 그린 (테마 키, 장치 배율)
        self._hat_layers = {}        # 모자 레이블 이름 -> 모자 위 장식 레이어(어린이날 프로펠러)

        x = data.get("x_pos", 160)
        y = data.get("y_pos", 160)
        focus_minutes = data.get("focus_minutes")
        break_minutes = data.get("break_minutes")

        self.timer_model = FocusTimer(self._mode_key, goal=self._goal)
        if focus_minutes:
            self.timer_model.focus_minutes = int(focus_minutes)
        if break_minutes:
            self.timer_model.break_minutes = int(break_minutes)

        self._apply_window_flags()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(*AMBIENT_SIZE)
        self.move(x, y)

        self._build_ui()
        self._set_display_mode("ambient")
        self._update_view()

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start()

        if auto_start:
            self._start_session()

    def _apply_window_flags(self) -> None:
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.Tool)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.container = QWidget(self)
        self.container.setObjectName("focusContainer")
        outer.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        self._content_layout = layout

        top = QHBoxLayout()
        top.setSpacing(8)

        self.ring = FocusProgressRing(self)
        top.addWidget(self.ring)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        self.goal_label = FocusGoalLabel(self._goal or "집중 목표", self)
        self.goal_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #172033; background: transparent;")
        self.goal_label.setFixedHeight(22)
        text_col.addWidget(self.goal_label)

        self.percent_label = QLabel("0%")
        self.percent_label.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {FOCUS_ACCENT_COLOR}; background: transparent;")
        text_col.addWidget(self.percent_label)
        top.addLayout(text_col, 1)

        self.tomato_mini_label = QLabel(self)
        self.tomato_mini_label.setObjectName("focusTomatoMiniImage")
        self.tomato_mini_label.setFixedSize(TOMATO_MINI_IMAGE_SIZE, TOMATO_MINI_IMAGE_SIZE)
        self.tomato_mini_label.setAlignment(Qt.AlignCenter)
        self.tomato_mini_label.setStyleSheet("background: transparent;")
        mini_tomato = QPixmap(str(TOMATO_MINI_IMAGE_PATH))
        self._has_tomato_mini = not mini_tomato.isNull()
        if self._has_tomato_mini:
            self.tomato_mini_label.setPixmap(
                mini_tomato.scaled(
                    self.tomato_mini_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        else:
            self.tomato_mini_label.hide()
        top.addWidget(self.tomato_mini_label, 0, Qt.AlignRight | Qt.AlignVCenter)

        self.close_btn = TransparentToolButton(FIF.CLOSE, self)
        self.close_btn.setIcon(FIF.CLOSE.icon(Theme.LIGHT))
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setToolTip("삭제")
        self.close_btn.clicked.connect(self._on_close)
        top.addWidget(self.close_btn)
        layout.addLayout(top)

        self.glance_panel = QWidget(self)
        glance_root = QHBoxLayout(self.glance_panel)
        glance_root.setContentsMargins(2, 0, 0, 0)
        glance_root.setSpacing(6)

        glance = QGridLayout()
        glance.setContentsMargins(0, 0, 0, 0)
        glance.setHorizontalSpacing(8)
        glance.setVerticalSpacing(1)
        self.mode_value = CaptionLabel("", self)
        self.remaining_value = CaptionLabel("", self)
        self.break_value = CaptionLabel("", self)
        for row, (name, value) in enumerate([
            ("모드", self.mode_value),
            ("남은 시간", self.remaining_value),
            ("다음 휴식", self.break_value),
        ]):
            label = CaptionLabel(name, self)
            label.setStyleSheet("color: rgba(23,32,51,145); background: transparent;")
            value.setStyleSheet("color: #172033; font-weight: 600; background: transparent;")
            glance.addWidget(label, row, 0)
            glance.addWidget(value, row, 1)
        glance_root.addLayout(glance, 1)

        self.tomato_label = _ClickableLabel(self.glance_panel)
        self.tomato_label.setObjectName("focusTomatoImage")
        self.tomato_label.setFixedSize(TOMATO_IMAGE_SIZE, TOMATO_IMAGE_SIZE)
        self.tomato_label.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        self.tomato_label.setStyleSheet("background: transparent;")
        tomato = QPixmap(str(TOMATO_IMAGE_PATH))
        self._has_tomato = not tomato.isNull()
        if self._has_tomato:
            self.tomato_label.setCursor(Qt.PointingHandCursor)
            self.tomato_label.setPixmap(
                tomato.scaled(
                    self.tomato_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        else:
            self.tomato_label.hide()
        self.tomato_label.clicked.connect(self._show_encouragement_bubble)
        glance_root.addWidget(self.tomato_label, 0, Qt.AlignRight | Qt.AlignBottom)
        layout.addWidget(self.glance_panel)

        # 공휴일 모자: 토마토 레이블 위에 겹쳐 놓는 마우스 투과 레이블(레이아웃 밖).
        self._hat_mini_label = self._make_hat_label("focusHatMini")
        self._hat_label = self._make_hat_label("focusHat")

        self.encouragement_bubble = QLabel(self)
        self.encouragement_bubble.setObjectName("focusEncouragementBubble")
        self.encouragement_bubble.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.encouragement_bubble.setAttribute(Qt.WA_TranslucentBackground)
        self.encouragement_bubble.setAttribute(Qt.WA_ShowWithoutActivating)
        self.encouragement_bubble.setAutoFillBackground(False)
        self.encouragement_bubble.setAlignment(Qt.AlignCenter)
        self.encouragement_bubble.setWordWrap(True)
        self.encouragement_bubble.setMaximumWidth(210)
        self.encouragement_bubble.setStyleSheet("""
            QLabel#focusEncouragementBubble {
                background: rgba(255, 255, 255, 245);
                color: #172033;
                border: 1px solid rgba(255, 90, 69, 130);
                border-radius: 10px;
                padding: 8px 10px;
                font-size: 12px;
                font-weight: 700;
            }
        """)
        self.encouragement_bubble.hide()
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.setInterval(FOCUS_BUBBLE_DURATION_MS)
        self._bubble_timer.timeout.connect(self._hide_encouragement_bubble)

        self._apply_visual_state("normal")

    def _apply_visual_state(self, state: str) -> None:
        styles = {
            "normal": (focus_card_gradient(self._holiday_theme), "rgba(255, 255, 255, 180)"),
            "complete": (
                "qlineargradient("
                "x1:0, y1:0, x2:1, y2:1, "
                "stop:0 #FFFAF8, "
                "stop:0.55 #FFF0EC, "
                "stop:1 #FFE7E0"
                ")",
                "rgba(255, 90, 69, 120)",
            ),
            "break": (
                "qlineargradient("
                "x1:0, y1:0, x2:1, y2:1, "
                "stop:0 #F8FCFF, "
                "stop:0.55 #EDF7FF, "
                "stop:1 #E2F0FF"
                ")",
                "rgba(120, 166, 210, 130)",
            ),
        }
        background, border = styles.get(state, styles["normal"])
        self._visual_state = state
        self.container.setStyleSheet(f"""
            #focusContainer {{
                background: {background};
                border: 1px solid {border};
                border-radius: 10px;
            }}
        """)

    def _set_display_mode(self, mode: str) -> None:
        self._display_mode = "glance" if mode == "glance" else "ambient"
        if self._display_mode == "glance":
            self.setFixedSize(*GLANCE_SIZE)
            self._content_layout.setContentsMargins(12, 8, 12, 8)
            self._content_layout.setSpacing(6)
            self.tomato_mini_label.setVisible(False)
            self.glance_panel.setVisible(True)
        else:
            self.setFixedSize(*AMBIENT_SIZE)
            self._content_layout.setContentsMargins(12, 8, 12, 8)
            self._content_layout.setSpacing(6)
            self.tomato_mini_label.setVisible(self._has_tomato_mini)
            self.glance_panel.setVisible(False)
        self._update_view()
        self._place_hats()

    def _make_hat_label(self, name: str) -> QLabel:
        """모자를 얹을 투명 레이블. 마우스를 통과시켜 토마토 클릭을 가로채지 않는다."""
        label = QLabel(self.container)
        label.setObjectName(name)
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        label.setStyleSheet("background: transparent;")
        label.hide()
        # 모자 위 장식(어린이날 프로펠러). 모자 레이블 전체를 덮고, 레이블이 숨으면 같이 숨는다.
        self._hat_layers[name] = DecorationLayer("hat", label)
        return label

    def set_holiday_theme(self, theme) -> None:
        """공휴일 테마(HolidayTheme 또는 None)를 화면에만 입힌다. DB에는 쓰지 않는다.

        normal 상태 바탕만 테마 색이고 complete·break는 그대로다. 모자는 상태와 무관하게
        토마토 위에 얹는다. 같은 테마로 여러 번 불려도 레이블·연결이 늘지 않는다.
        """
        self._holiday_theme = theme
        self._apply_visual_state(self._visual_state)
        self._place_hats()

    def _hat_spec(self):
        """(모자 레이블, 토마토 레이블, 토마토 상자 크기, 오프셋 단위, 보일지) 둘을 돌려준다."""
        glance = self._display_mode == "glance"
        return (
            (self._hat_mini_label, self.tomato_mini_label, TOMATO_MINI_IMAGE_SIZE,
             HAT_OFFSET_UNITS["tomato_mini.png"], (not glance) and self._has_tomato_mini),
            (self._hat_label, self.tomato_label, TOMATO_IMAGE_SIZE,
             HAT_OFFSET_UNITS["tomato.png"], glance and self._has_tomato),
        )

    def _place_hats(self) -> None:
        """지금 보이는 토마토 위에만 모자를 얹고(아래 끝·x를 토마토 레이블에 맞춤) 나머지는 숨긴다."""
        theme = self._holiday_theme
        specs = self._hat_spec()
        key = theme.key if theme is not None else None
        for hat, _tomato, _box, offset, _visible in specs:
            layer = self._hat_layers[hat.objectName()]
            layer.set_hat_offset(offset)  # 모자 그림과 같은 만큼 프로펠러도 내린다
            layer.set_theme(key)
        if theme is None:
            for hat, _tomato, _box, _offset, _visible in specs:
                hat.hide()
            return
        # 보이기 전·모드 전환 직후에도 토마토 위치를 최신으로 읽는다.
        self.layout().activate()
        self._content_layout.activate()
        dpr = self.devicePixelRatioF()
        drawn = (theme.key, dpr)
        for hat, tomato, box, offset, visible in specs:
            if not visible:
                hat.hide()
                continue
            if self._hat_drawn.get(hat.objectName()) != drawn:  # 테마·배율이 달라졌을 때만 다시 그린다
                hat.setPixmap(hat_pixmap(theme.key, box, offset, dpr))
                self._hat_drawn[hat.objectName()] = drawn
            hat.setFixedSize(box, round(box * 1.3))
            bottom_left = tomato.mapTo(self.container, QPoint(0, tomato.height()))
            hat.move(bottom_left.x(), bottom_left.y() - hat.height())
            hat.show()
            hat.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self._place_hats()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_hats()

    def event(self, event):
        if event.type() == QEvent.Type.DevicePixelRatioChange:
            self._hat_drawn.clear()  # 화면 배율이 달라졌으니 모자를 다시 그린다
            self._place_hats()
        return super().event(event)

    def _show_encouragement_bubble(self) -> None:
        if self._display_mode != "glance" or self.tomato_label.isHidden():
            return
        self.encouragement_bubble.setText(secrets.choice(FOCUS_ENCOURAGEMENT_MESSAGES))
        self.encouragement_bubble.adjustSize()

        anchor = self.tomato_label.mapToGlobal(
            QPoint(self.tomato_label.width() // 2, self.tomato_label.height())
        )
        x = anchor.x() - self.encouragement_bubble.width() // 2
        y = anchor.y() + 6

        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = max(geo.left() + 4, min(x, geo.right() - self.encouragement_bubble.width() - 4))
            if y + self.encouragement_bubble.height() > geo.bottom() - 4:
                y = anchor.y() - self.tomato_label.height() - self.encouragement_bubble.height() - 6
            y = max(geo.top() + 4, min(y, geo.bottom() - self.encouragement_bubble.height() - 4))

        self.encouragement_bubble.move(x, y)
        self.encouragement_bubble.show()
        self.encouragement_bubble.raise_()
        self._bubble_timer.start()

    def _hide_encouragement_bubble(self) -> None:
        self.encouragement_bubble.hide()

    def _format_remaining(self, seconds: int) -> str:
        seconds = max(0, seconds)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _format_time(self, value: datetime | None) -> str:
        return value.strftime("%I:%M %p") if value else "-"

    def _update_view(self) -> None:
        percent = self.timer_model.progress_percent()
        self.ring.set_progress(self.timer_model.progress_ratio())
        self.goal_label.setText(self._goal or "집중 목표")
        self.percent_label.setText(f"{percent}%")
        if self.timer_model.phase == "break":
            self.goal_label.setText("휴식 중")
            self.mode_value.setText("휴식")
            self.break_value.setText("-")
        else:
            self.mode_value.setText(self.timer_model.mode_label)
            self.break_value.setText(self._format_time(self.timer_model.next_break_at()))
        self.remaining_value.setText(self._format_remaining(self.timer_model.remaining_seconds()))

    def _persist_widget_settings(self) -> None:
        _label, focus_minutes, break_minutes = db.FOCUS_MODES.get(self._mode_key, db.FOCUS_MODES[db.DEFAULT_FOCUS_MODE])
        self.timer_model.goal = self._goal
        self.timer_model.set_mode(self._mode_key)
        self.timer_model.focus_minutes = focus_minutes
        self.timer_model.break_minutes = break_minutes
        db.update_focus_widget(
            self.widget_id,
            goal=self._goal,
            mode_key=self._mode_key,
            focus_minutes=focus_minutes,
            break_minutes=break_minutes,
        )

    def _start_session(self) -> None:
        self._persist_widget_settings()
        self._apply_visual_state("normal")
        self._session_saved = False
        self.timer_model.start(self._goal)
        self._update_view()

    def _on_tick(self) -> None:
        if self.timer_model.is_complete():
            if self.timer_model.phase == "break":
                self._complete_break_session()
            else:
                self._complete_focus_session()
            return
        self._update_view()

    def _finish_session(self, completed: bool) -> None:
        if self.timer_model.status not in {"running", "paused"}:
            return
        self.timer_model.stop()
        self._update_view()
        if self.timer_model.phase == "break":
            self._apply_visual_state("normal")
            return
        self._show_review(completed)

    def _complete_focus_session(self) -> None:
        self.timer_model.stop()
        self._apply_visual_state("complete")
        self._update_view()
        self._save_review(None, "없음", True)
        if self._ask_break():
            self._start_break_session()

    def _ask_break(self) -> bool:
        if self.property("privacyLocked"):
            return False  # 잠금 중에는 완료 상태/기록만 유지하고 팝업을 열지 않는다.
        dlg = FocusBreakPromptDialog(self.timer_model.break_minutes, self)
        return dlg.exec() == QDialog.Accepted

    def _start_break_session(self) -> None:
        self.timer_model.start_break()
        self._apply_visual_state("break")
        self._set_display_mode("ambient")
        self._update_view()

    def _complete_break_session(self) -> None:
        self.timer_model.stop()
        self._apply_visual_state("complete")
        self._update_view()

    def _show_review(self, completed: bool) -> None:
        dlg = FocusReviewDialog(self)
        if dlg.exec() == QDialog.Accepted:
            rating, distraction = dlg.get_result()
            self._save_review(rating, distraction, completed)
        else:
            self._save_review(None, "없음", completed)

    def _save_review(self, rating: int | None, distraction: str, completed: bool) -> None:
        if self._session_saved:
            return
        started_at = self.timer_model.started_at or datetime.now()
        ended_at = self.timer_model.ended_at or datetime.now()
        db.create_focus_session(
            self.widget_id,
            self._goal,
            self.timer_model.mode_key,
            self.timer_model.focus_minutes,
            self.timer_model.break_minutes,
            started_at.strftime("%Y-%m-%d %H:%M:%S"),
            ended_at.strftime("%Y-%m-%d %H:%M:%S"),
            self.timer_model.elapsed_seconds(),
            completed,
            rating,
            distraction,
        )
        self._session_saved = True

    def _on_close(self) -> None:
        self._tick_timer.stop()
        db.delete_focus_widget(self.widget_id)
        self.widget_closed.emit(self.widget_id)
        self.close()

    def enterEvent(self, event):
        if self._display_mode == "ambient":
            self._set_display_mode("glance")
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._display_mode == "glance":
            self._set_display_mode("ambient")
        super().leaveEvent(event)

    @staticmethod
    def _snap_px() -> int:
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
            db.update_focus_widget(self.widget_id, x_pos=self.x(), y_pos=self.y())
