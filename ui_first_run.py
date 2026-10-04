"""DB를 만들기 전에 표시하는 최초 크기 선택(데스크 뷰).

미리보기는 1920×1080 화면에 실제 크기 규칙을 적용한 벡터 그림이며 이미지 자산을 쓰지 않는다.
앱 본체와 첫인상을 맞추기 위해 시스템 테마와 무관하게 항상 밝게 그린다.
"""
from PySide6.QtCore import QEasingCurve, QEvent, QPointF, QRect, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QBoxLayout, QDialog, QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget,
)
from shiboken6 import isValid


SETUP_WINDOW_TITLE = "기후노트 — 처음 설정"
SIZE_CHOICES = (
    ("compact", "기본", "작게 띄워두기"),
    ("medium", "중간", "일정도 함께 보기"),
    ("large", "크게", "위젯까지 한눈에"),
)
HEADING_TWO_LINES = "어떤 크기로\n시작할까요?"
HEADING_ONE_LINE = "어떤 크기로 시작할까요?"
SUBTITLE = "고른 모습 그대로 시작해요."
HINT = "설정에서 언제든 바꿀 수 있어요."

# 미리보기 기준 화면: 1920×1080, 작업 표시줄 48px.
# ui_main 기본값(사이드바 숨김, 오른쪽 아래, 여백 20px)의 크기 규칙을 스냅 전 좌표로 그린다.
PREVIEW_SCREEN_WIDTH = 1920
PREVIEW_WORK_HEIGHT = 1032
PREVIEW_MARGIN = 20

_NAVY = "#01295F"
_BLUE = "#2563EB"
_INK = "#0F2340"
_CHIPS = {2: ("#FFD166",), 8: ("#7FB2EC",), 10: ("#FFD166", "#F2A7B3"), 15: ("#9ED3B0",),
          19: ("#7FB2EC",), 23: ("#FFD166",), 24: ("#F2A7B3",), 30: ("#9ED3B0",)}
_STYLE = """
QDialog#firstRun { background: #FFFFFF; border: 1px solid #D5DDE7; border-radius: 14px; }
QLabel { background: transparent; color: #0F2340; }
QLabel#brand { color: #01295F; }
QLabel#brandSub { color: #7A8AA0; }
QLabel#subtitle, QLabel#hint { color: #5B6B80; }
QPushButton#cancel, QPushButton#start { min-height: 40px; max-height: 40px; border-radius: 9px; }
QPushButton#cancel { padding: 0 18px; color: #475569; background: transparent;
    border: 1px solid transparent; }
QPushButton#cancel:hover { background: #F1F5F9; }
QPushButton#cancel:focus { border: 1px solid #60A5FA; }
QPushButton#start { padding: 0 22px; color: #FFFFFF; background: #2563EB; border: 1px solid #2563EB; }
QPushButton#start:hover { background: #1D4ED8; border-color: #1D4ED8; }
QPushButton#start:focus { border: 1px solid #93C5FD; }
"""


def preview_window_rect(scale: str) -> QRect:
    """ui_main._calendar_scale_geometry 기본 크기와 오른쪽 아래 배치(5mm 스냅 전)."""
    width, height = PREVIEW_SCREEN_WIDTH, PREVIEW_WORK_HEIGHT
    if scale == "compact":
        w, h = min(380, width), min(660, height)
    else:
        if scale == "medium":
            w, h = max(380, int(width * 0.60)), max(500, int(height * 0.60))
        else:
            w, h = max(380, width - 40), max(500, height - 40)
        w, h = min(w, width), min(h, height)
    return QRect(width - PREVIEW_MARGIN - w, height - PREVIEW_MARGIN - h, w, h)


def _font(px: int, weight: QFont.Weight = QFont.Weight.Normal, *, display: bool = False) -> QFont:
    """정수 px 글꼴. display는 번들 Pretendard(미로드 시 맑은 고딕), 본문은 맑은 고딕."""
    font = QFont()
    font.setFamilies(["Pretendard", "Malgun Gothic", "Segoe UI"] if display
                     else ["Malgun Gothic", "Segoe UI"])
    font.setPixelSize(px)
    font.setWeight(weight)
    return font


class _BrandMark(QWidget):
    """네이비 둥근 사각 안의 달력 선 아이콘."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(20, 20)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_NAVY))
        p.drawRoundedRect(QRectF(0, 0, 20, 20), 6, 6)
        p.setPen(QPen(QColor("#FFFFFF"), 1.3, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(5.5, 6.5, 9, 8), 1.5, 1.5)
        p.drawLine(QPointF(5.5, 9.2), QPointF(14.5, 9.2))
        p.drawLine(QPointF(8, 5.2), QPointF(8, 7.6))
        p.drawLine(QPointF(12, 5.2), QPointF(12, 7.6))


class _CloseButton(QPushButton):
    """선으로 그린 X. 포커스가 있을 때 Enter도 종료한다(autoDefault)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAccessibleName("종료")
        self.setFixedSize(32, 32)
        self.setAutoDefault(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.isDown():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#F1F5F9"))
            p.drawRoundedRect(QRectF(self.rect()), 8, 8)
        if self.hasFocus():
            p.setPen(QPen(QColor(_BLUE), 1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 7, 7)
        p.setPen(QPen(QColor("#64748B"), 1.5, Qt.SolidLine, Qt.RoundCap))
        center = QPointF(self.width() / 2, self.height() / 2)
        p.drawLine(center + QPointF(-4.5, -4.5), center + QPointF(4.5, 4.5))
        p.drawLine(center + QPointF(4.5, -4.5), center + QPointF(-4.5, 4.5))


class _SizeChoice(QPushButton):
    """넓은 배치에서는 라디오 행, 한 열 배치에서는 간단한 크기 버튼으로 그린다."""

    def __init__(self, choice, parent):
        super().__init__(parent)
        self.scale, self.label, self.caption = choice
        self.segment = False
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setAccessibleName(f"{self.label}: {self.caption}")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.set_segment(False, 56)

    def set_segment(self, segment: bool, height: int) -> None:
        self.segment = segment
        self.setFixedHeight(height)
        self.update()

    def paintEvent(self, event):
        on = self.isChecked()
        hover = self.underMouse() and not on
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        frame = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        radius = 9 if self.segment else 10
        p.setPen(QPen(QColor(_BLUE if on else ("#CBD5E1" if hover else "#E2E8F0")), 1.5 if on else 1))
        p.setBrush(QColor("#EEF4FF" if on else ("#F6F9FC" if hover else "#FFFFFF")))
        p.drawRoundedRect(frame, radius, radius)
        if self.hasFocus():
            p.setPen(QPen(QColor(_BLUE), 1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(frame.adjusted(3, 3, -3, -3), radius - 3, radius - 3)
        if self.segment:
            p.setFont(_font(14, QFont.Weight.DemiBold, display=True))
            p.setPen(QColor("#1D4ED8" if on else "#334155"))
            p.drawText(self.rect(), Qt.AlignCenter, self.label)
            return
        ring = QRectF(14, self.height() / 2 - 9, 18, 18)
        p.setPen(QPen(QColor(_BLUE if on else "#A3B1C2"), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(ring.adjusted(0.75, 0.75, -0.75, -0.75))
        if on:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(_BLUE))
            p.drawEllipse(ring.adjusted(5, 5, -5, -5))
        name_font = _font(15 if self.height() >= 50 else 14, QFont.Weight.DemiBold, display=True)
        caption_font = _font(12)
        name_h = QFontMetrics(name_font).height()
        caption_h = QFontMetrics(caption_font).height()
        top = (self.height() - name_h - 2 - caption_h) / 2
        left = ring.right() + 12
        width = self.width() - left - 12
        p.setFont(name_font)
        p.setPen(QColor(_INK))
        p.drawText(QRectF(left, top, width, name_h), Qt.AlignLeft | Qt.AlignVCenter, self.label)
        p.setFont(caption_font)
        p.setPen(QColor("#64748B"))
        p.drawText(QRectF(left, top + name_h + 2, width, caption_h),
                   Qt.AlignLeft | Qt.AlignVCenter, self.caption)


class _DeskPreview(QWidget):
    """같은 1920×1080 화면 안에서 선택 크기의 실제 비율과 기본 위치를 그린다."""

    MONITOR_W, MONITOR_H = 290.0, 180.5          # 받침 포함 기본 그림
    SCREEN = QRectF(5, 5, 280, 157.5)
    S = 280 / PREVIEW_SCREEN_WIDTH               # 1920 좌표 → 기본 그림 좌표
    CAPTION = "1920×1080 화면 기준 · 오른쪽 아래 기본 위치"
    CAPTION_H = 14

    def __init__(self, parent):
        super().__init__(parent)
        self.scale = "compact"
        self._window = QRectF(preview_window_rect("compact"))
        self._padding = (20, 18)
        self._gap = 12
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(240)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._on_frame)
        self.setAccessibleName("선택한 크기 미리보기")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_scale(self, scale: str) -> None:
        self.scale = scale
        target = QRectF(preview_window_rect(scale))
        self._animation.stop()
        if not self.isVisible():
            self._window = target
            self.update()
            return
        self._animation.setStartValue(QRectF(self._window))
        self._animation.setEndValue(target)
        self._animation.start()

    def set_metrics(self, padding: tuple[int, int], gap: int) -> None:
        self._padding, self._gap = padding, gap
        self.update()

    def window_rect(self) -> QRectF:
        return QRectF(self._window)

    def monitor_ratio(self) -> float:
        """패널 여백과 안내 문구를 뺀 공간에 맞춘 모니터 배율(최대 1)."""
        pad_x, pad_y = self._padding
        avail_w = self.width() - pad_x * 2
        avail_h = self.height() - pad_y * 2 - self.CAPTION_H - self._gap
        return max(0.0, min(1.0, avail_w / self.MONITOR_W, avail_h / self.MONITOR_H))

    def _monitor_origin(self) -> tuple[float, float, float]:
        k = self.monitor_ratio()
        block = self.MONITOR_H * k + self._gap + self.CAPTION_H
        return (self.width() - self.MONITOR_W * k) / 2, (self.height() - block) / 2, k

    def window_rect_on_widget(self) -> QRectF:
        left, top, k = self._monitor_origin()
        return QRectF(left + (self.SCREEN.left() + self._window.x() * self.S) * k,
                      top + (self.SCREEN.top() + self._window.y() * self.S) * k,
                      self._window.width() * self.S * k, self._window.height() * self.S * k)

    def _on_frame(self, value) -> None:
        self._window = QRectF(value)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#F3F6FA"))
        p.drawRoundedRect(QRectF(self.rect()), 12, 12)
        left, top, k = self._monitor_origin()
        if k <= 0:
            return
        p.save()
        p.translate(left, top)
        p.scale(k, k)
        self._paint_monitor(p)
        p.restore()
        p.setFont(_font(11))
        p.setPen(QColor("#66758B"))
        text = QFontMetrics(p.font()).elidedText(
            self.CAPTION, Qt.ElideRight, max(0, self.width() - self._padding[0] * 2))
        p.drawText(QRectF(0, top + self.MONITOR_H * k + self._gap, self.width(), self.CAPTION_H + 4),
                   Qt.AlignHCenter | Qt.AlignTop, text)

    def _paint_monitor(self, p: QPainter) -> None:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1E2734"))
        p.drawRoundedRect(QRectF(0, 0, 290, 167.5), 9, 9)
        p.setBrush(QColor("#AEBBCB"))
        p.drawRect(QRectF(138, 167.5, 14, 9))
        p.setBrush(QColor("#9AA9BB"))
        p.drawRoundedRect(QRectF(103, 176.5, 84, 4), 2, 2)
        screen = self.SCREEN
        clip = QPainterPath()
        clip.addRoundedRect(screen, 4, 4)
        p.save()
        p.setClipPath(clip)
        p.setBrush(QColor("#CBD6E3"))
        p.drawRect(screen)
        bar = QRectF(screen.left(), screen.bottom() - 7, screen.width(), 7)
        p.setBrush(QColor("#EEF2F7"))
        p.drawRect(bar)
        icon_x = screen.center().x() - 12.5
        for i in range(4):
            p.setBrush(QColor(_BLUE if i == 0 else "#9AA9BC"))
            p.drawRoundedRect(QRectF(icon_x + i * 7, bar.top() + 1.5, 4, 4), 1, 1)
        win = QRectF(screen.left() + self._window.x() * self.S,
                     screen.top() + self._window.y() * self.S,
                     self._window.width() * self.S, self._window.height() * self.S)
        p.setBrush(QColor(15, 35, 64, 40))
        p.drawRoundedRect(win.translated(0, 1.5).adjusted(-0.5, -0.5, 0.5, 0.5), 3.5, 3.5)
        p.setPen(QPen(QColor(15, 35, 64, 72), 0.5))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(win, 3, 3)
        inner = QPainterPath()
        inner.addRoundedRect(win, 3, 3)
        p.setClipPath(inner, Qt.IntersectClip)
        p.setPen(Qt.NoPen)
        if self.scale == "compact":
            self._paint_compact(p, win)
        else:
            self._paint_expanded(p, win)
        p.restore()

    def _paint_compact(self, p: QPainter, win: QRectF) -> None:
        # 기본: 네이비 헤더 + 날짜 점 + 아래 일정 목록
        x, y, w = win.left(), win.top(), win.width()
        p.setBrush(QColor(_NAVY))
        p.drawRect(QRectF(x, y, w, 9))
        p.setBrush(QColor(255, 255, 255, 217))
        p.drawRoundedRect(QRectF(x + w / 2 - 7, y + 3.5, 14, 2), 1, 1)
        cell = (w - 8) / 7
        for i in range(35):
            row, col = divmod(i, 7)
            center = QPointF(x + 4 + cell * (col + 0.5), y + 16.5 + 7 * row)
            radius = 2.5 if i == 17 else 1.5
            p.setBrush(QColor(_NAVY if i == 17 else ("#E8A3A3" if col == 0 else "#C3CFDC")))
            p.drawEllipse(center, radius, radius)
        line_y = y + 53
        p.setBrush(QColor("#E3E8EF"))
        p.drawRect(QRectF(x + 4, line_y, w - 8, 1))
        for k, (color, ratio) in enumerate((("#FFD166", .60), ("#7FB2EC", .44), ("#F2A7B3", .52))):
            row_y = line_y + 6 + k * 6
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(x + 6.5, row_y + 1), 1.5, 1.5)
            p.setBrush(QColor("#D3DCE7"))
            p.drawRoundedRect(QRectF(x + 11, row_y, (w - 16) * ratio, 2), 1, 1)

    def _paint_expanded(self, p: QPainter, win: QRectF) -> None:
        # 중간·크게: 바로가기 사이드바 + 달력(일정 칩) + 일정 열(크게: 메모·위젯 패널)
        x, y, w, h = win.left(), win.top(), win.width(), win.height()
        side, col = 80 * self.S, 330 * self.S
        if w < side + col + 8:
            self._paint_compact(p, win)   # 애니메이션 초반의 작은 창
            return
        p.setBrush(QColor("#EEF2F6"))
        p.drawRect(QRectF(x, y, side, h))
        for i in range(4):
            p.setBrush(QColor(_BLUE if i == 0 else "#C5D0DD"))
            p.drawRoundedRect(QRectF(x + side / 2 - 3, y + 4 + i * 9, 6, 6), 2, 2)
        cal = QRectF(x + side, y, w - side - col, h)
        p.setBrush(QColor(_NAVY))
        p.drawRect(QRectF(cal.left(), y, cal.width(), 10))
        p.setBrush(QColor(255, 255, 255, 217))
        p.drawRoundedRect(QRectF(cal.center().x() - 11, y + 4, 22, 2), 1, 1)
        grid = QRectF(cal.left() + 3, y + 13, cal.width() - 6, h - 16)
        gap = 1.5
        cell_w, cell_h = (grid.width() - gap * 6) / 7, (grid.height() - gap * 4) / 5
        for i in range(35):
            row, column = divmod(i, 7)
            cell = QRectF(grid.left() + column * (cell_w + gap), grid.top() + row * (cell_h + gap),
                          cell_w, cell_h)
            p.setBrush(QColor("#DCE6F5" if i == 17 else ("#FBF1F1" if column == 0 else "#F5F7FA")))
            p.drawRoundedRect(cell, 1.5, 1.5)
            for k, color in enumerate(_CHIPS.get(i, ())):
                p.setBrush(QColor(color))
                p.drawRoundedRect(QRectF(cell.left() + 1.5, cell.top() + 1.5 + k * 3,
                                         cell.width() - 3, 2), 1, 1)
        right = QRectF(x + w - col, y, col, h)
        p.setBrush(QColor("#DCE3EB"))
        p.drawRect(QRectF(right.left(), y, 1, h))
        p.setBrush(QColor(_NAVY))
        p.drawRoundedRect(QRectF(right.left() + 5, y + 5, col * .5, 3), 1, 1)
        for k, (color, ratio) in enumerate((("#FFD166", .70), ("#7FB2EC", .52), ("#F2A7B3", .62))):
            row_y = y + 12 + k * 6
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(right.left() + 6.5, row_y + 1), 1.5, 1.5)
            p.setBrush(QColor("#D3DCE7"))
            p.drawRoundedRect(QRectF(right.left() + 11, row_y, (col - 16) * ratio, 2), 1, 1)
        if self.scale == "large":
            split = y + h * 0.3
            p.setBrush(QColor("#DCE3EB"))
            p.drawRect(QRectF(right.left(), split, col, 1))
            half = (col - 11) / 2
            notes = (("#FFF1A8", 18), ("#FFE0E9", 18), ("#46679C", 12), ("#DCEBFF", 12))
            for k, (color, tall) in enumerate(notes):
                row, column = divmod(k, 2)
                p.setBrush(QColor(color))
                p.drawRoundedRect(QRectF(right.left() + 4 + column * (half + 3),
                                         split + 5 + row * 21, half, tall), 2, 2)


class FirstRunSizeDialog(QDialog):
    def __init__(self):
        super().__init__()
        # 이벤트 필터가 참조하는 속성은 위젯 생성·필터 설치보다 먼저 만든다.
        self.cards = []
        self._drag_handles = ()
        self.selected_scale = "compact"
        self.stacked = False
        self.short = False
        self._connected_screen = None
        self.setWindowTitle(SETUP_WINDOW_TITLE)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setObjectName("firstRun")
        self.setStyleSheet(_STYLE)

        self.root = QVBoxLayout(self)
        # 세로 → 가로 변경 직후 Qt가 이전 최소 높이를 강제하지 않게 한다.
        self.root.setSizeConstraint(QLayout.SetNoConstraint)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.mark = _BrandMark(self)
        self.brand = QLabel("기후노트", self)
        self.brand.setObjectName("brand")
        self.brand.setFont(_font(13, QFont.Weight.Bold))
        self.brand_sub = QLabel("처음 설정", self)
        self.brand_sub.setObjectName("brandSub")
        self.brand_sub.setFont(_font(13))
        self.close_button = _CloseButton(self)
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.mark)
        header.addWidget(self.brand)
        header.addWidget(self.brand_sub, 1)
        header.addWidget(self.close_button)
        self.root.addLayout(header)

        self.body = QBoxLayout(QBoxLayout.LeftToRight)
        self.left = QWidget(self)
        self.left_layout = QVBoxLayout(self.left)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(0)
        self.heading = QLabel(self.left)
        self.heading.setObjectName("heading")
        self.heading.setWordWrap(True)
        self.subtitle = QLabel(self.left)
        self.subtitle.setObjectName("subtitle")
        self.subtitle.setWordWrap(True)
        self.subtitle.setFont(_font(13))
        self._subtitle_gap = QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self._cards_gap = QSpacerItem(0, 22, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.cards_layout = QBoxLayout(QBoxLayout.TopToBottom)
        for choice in SIZE_CHOICES:
            card = _SizeChoice(choice, self.left)
            card.clicked.connect(lambda checked=False, scale=choice[0]: self._select(scale))
            self.cards_layout.addWidget(card, 1)
            self.cards.append(card)
        self.left_layout.addWidget(self.heading)
        self.left_layout.addItem(self._subtitle_gap)
        self.left_layout.addWidget(self.subtitle)
        self.left_layout.addItem(self._cards_gap)
        self.left_layout.addLayout(self.cards_layout)
        self.left_layout.addStretch(1)
        self.preview = _DeskPreview(self)
        self.body.addWidget(self.left)
        self.body.addWidget(self.preview, 1)
        self.root.addLayout(self.body, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.hint = QLabel(HINT, self)
        self.hint.setObjectName("hint")
        self.hint.setFont(_font(12))
        self.cancel_button = QPushButton("종료", self)
        self.cancel_button.setObjectName("cancel")
        self.cancel_button.setFont(_font(14))
        self.cancel_button.setAutoDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.start_button = QPushButton("이 크기로 시작", self)
        self.start_button.setObjectName("start")
        self.start_button.setFont(_font(14, QFont.Weight.Bold, display=True))
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self.accept)
        actions.addWidget(self.hint)
        actions.addStretch(1)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.start_button)
        self.root.addLayout(actions)

        self._drag_handles = (self.mark, self.brand, self.brand_sub)
        for handle in self._drag_handles:
            handle.installEventFilter(self)
        for card in self.cards:
            card.installEventFilter(self)
        self._apply_layout(stacked=False, short=False)
        self._select("compact")
        self.setTabOrder(self.close_button, self.cards[0])
        self.setTabOrder(self.cards[0], self.cards[1])
        self.setTabOrder(self.cards[1], self.cards[2])
        self.setTabOrder(self.cards[2], self.cancel_button)
        self.setTabOrder(self.cancel_button, self.start_button)
        self.cards[0].setFocus()
        self.resize(680, 500)

    def _apply_layout(self, *, stacked: bool, short: bool) -> None:
        """넓은 배치(왼쪽 목록 + 오른쪽 미리보기)와 한 열 배치(위 크기 버튼 + 아래 미리보기)."""
        self.stacked, self.short = stacked, short
        if stacked:
            self.root.setContentsMargins(16, 14, 16, 16)
            self.root.setSpacing(12)
        elif short:
            self.root.setContentsMargins(24, 14, 24, 16)
            self.root.setSpacing(10)
        else:
            self.root.setContentsMargins(32, 20, 32, 24)
            self.root.setSpacing(18)
        self.body.setDirection(QBoxLayout.TopToBottom if stacked else QBoxLayout.LeftToRight)
        self.body.setSpacing((8 if short else 14) if stacked else (22 if short else 28))
        if stacked:
            self.left.setMinimumWidth(0)
            self.left.setMaximumWidth(16777215)
            self.left.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        else:
            self.left.setFixedWidth(240)
            self.left.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        hint_in_footer = short and not stacked
        self.heading.setText(HEADING_ONE_LINE if stacked else HEADING_TWO_LINES)
        self.heading.setFont(_font(22 if (stacked or short) else 27, QFont.Weight.Bold, display=True))
        self.subtitle.setText(SUBTITLE if hint_in_footer else f"{SUBTITLE}\n{HINT}")
        self.hint.setVisible(hint_in_footer)
        self._subtitle_gap.changeSize(0, 6 if short else 10, QSizePolicy.Minimum, QSizePolicy.Fixed)
        cards_gap = (10 if short else 14) if stacked else (12 if short else 22)
        self._cards_gap.changeSize(0, cards_gap, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.cards_layout.setDirection(QBoxLayout.LeftToRight if stacked else QBoxLayout.TopToBottom)
        self.cards_layout.setSpacing(6 if (stacked or short) else 8)
        height = (36 if short else 40) if stacked else (46 if short else 56)
        for card in self.cards:
            card.set_segment(stacked, height)
        if stacked:
            self.preview.set_metrics((14, 12), 8)
        elif short:
            self.preview.set_metrics((16, 10), 6)
        else:
            self.preview.set_metrics((20, 18), 12)
        self.left_layout.invalidate()
        self.root.invalidate()

    def _select(self, scale):
        self.selected_scale = scale
        for card in self.cards:
            card.setChecked(card.scale == scale)
        self.preview.set_scale(scale)

    def _step(self, direction):
        index = next(i for i, c in enumerate(self.cards) if c.scale == self.selected_scale)
        card = self.cards[(index + direction) % len(self.cards)]
        self._select(card.scale)
        card.setFocus()

    def eventFilter(self, watched, event):
        if watched in self._drag_handles and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton and self.windowHandle():
                self.windowHandle().startSystemMove()
        if watched in self.cards and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Left, Qt.Key_Up, Qt.Key_Right, Qt.Key_Down):
                self._step(-1 if event.key() in (Qt.Key_Left, Qt.Key_Up) else 1)
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Left, Qt.Key_Up, Qt.Key_Right, Qt.Key_Down):
            self._step(-1 if event.key() in (Qt.Key_Left, Qt.Key_Up) else 1)
        else:
            super().keyPressEvent(event)

    def fit_to_available_geometry(self, area):
        width, height = min(680, area.width() - 24), min(500, area.height() - 24)
        # 폭이 좁거나 높이가 매우 낮으면 크기 버튼을 위로 올린 한 열 배치를 쓴다.
        self._apply_layout(stacked=width < 580 or height < 370, short=height < 470)
        # 배치 전환 직후 resize하면 Windows가 이전 레이아웃의 최소 높이를 적용해 "Unable to set geometry"와 함께 더 큰 크기를 남긴다. 레이아웃 최소값을 먼저 갱신한다.
        self.root.activate()
        self.resize(width, height)
        self.move(area.center() - self.rect().center())

    def _screen_changed(self, screen):
        if self._connected_screen is not None and isValid(self._connected_screen):
            self._connected_screen.availableGeometryChanged.disconnect(self.fit_to_available_geometry)
        self._connected_screen = screen
        if screen is not None:
            screen.availableGeometryChanged.connect(self.fit_to_available_geometry)
            self.fit_to_available_geometry(screen.availableGeometry())

    def showEvent(self, event):
        super().showEvent(event)
        if self._connected_screen is None:
            self.windowHandle().screenChanged.connect(self._screen_changed)
            self._screen_changed(self.screen())
