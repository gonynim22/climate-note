"""'앱 업데이트' 안내창: 받는 곳을 두 갈래로 고른다(2026-11-04 B안, 디자인 캔버스에서 확정).

- 첫 화면: '어디에서 받을까요?' 아래에 큰 타일 두 개.
  · 온나라 시스템에서 받기(공공기관 업무망, 초록) → 같은 창 안에서 온나라 받는 방법 안내로 바뀐다.
  · GitLab에서 받기(외부 인터넷망, 파랑) → 기본 브라우저로 GitLab 최신 Release 주소를 열고 창을 닫는다.
- 온나라 안내 문구는 v4.6 안내창과 같다. '받는 곳 다시 고르기'로 첫 화면에 돌아간다.
- 앱은 네트워크에 접속하지 않는다. 브라우저로 주소를 여는 것만 한다(오프라인 전용 계약의 예외 범위).
- DB·설정을 읽거나 쓰지 않는다.
"""

import math

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase

from app_info import APP_VERSION


UPDATE_GUIDE_TITLE = "최신 업데이트 확인 방법"
UPDATE_GUIDE_HIGHLIGHT = "업데이트 파일은 온나라 커뮤니티 게시물의 첨부파일로 배포됩니다."
# 온나라 받는 방법(v4.6 안내창과 같은 문구). 3번의 "기후노트"만 굵게 보인다.
ONNARA_STEPS = (
    "온나라 커뮤니티를 엽니다.",
    "지식 > 업무용 프로그램으로 이동합니다.",
    '검색창에 "기후노트"를 입력합니다.',
    "가장 최근 등록된 업데이트 글을 열고 첨부파일을 내려받습니다.",
    "기존 파일을 지우고, 새로 받은 파일을 실행합니다.",
)
# 늘 최신 Release 페이지로 이동하는 GitLab 주소(새 버전을 올려도 앱을 고칠 필요가 없다)
GITLAB_LATEST_URL = "https://gitlab.aigov.go.kr/whrhkdrh/climate-note/-/releases/permalink/latest"

# 디자인 토큰(B안, 연하게·초록/파랑). 진한 색은 연한 바탕 위 글자 대비 4.5:1 이상.
INK = "#0F1E36"
BODY = "#1F2A3D"
SUB = "#5B6678"
ONNARA = {"accent": "#1E7A46", "bg": "#E3F3E8", "line": "#C2E4CE", "hover": "#D6EEDF", "pressed": "#CBE8D5"}
GITLAB = {"accent": "#1D4ED8", "bg": "#DFE8FD", "line": "#C3D3FA", "hover": "#D2DFFC", "pressed": "#C6D6FA"}
MASK_COLOR = QColor(1, 20, 48, 112)  # 남색 기운의 바탕 막(44%)
DOT_COLOR = "#F04438"  # 새 버전이 있다는 점

_SVG_HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" '
             'stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round">')
ICONS = {
    "building": '<path d="M3 9.5L12 4l9 5.5"/><path d="M5 10v8"/><path d="M9.5 10v8"/>'
                '<path d="M14.5 10v8"/><path d="M19 10v8"/><path d="M3 20.5h18"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/>'
             '<path d="M12 3c2.6 2.6 3.9 5.6 3.9 9s-1.3 6.4-3.9 9c-2.6-2.6-3.9-5.6-3.9-9S9.4 5.6 12 3z"/>',
    "chevron_right": '<path d="M9 6l6 6-6 6"/>',
    "chevron_left": '<path d="M15 6l-6 6 6 6"/>',
    "external": '<path d="M7 17L17 7"/><path d="M8 7h9v9"/>',
}


def update_guide_text() -> str:
    """온나라 안내 문구 전체(평문). 화면과 같은 문구를 테스트·복사용으로 한곳에서 만든다."""
    steps = "\n".join(f"{i}. {step}" for i, step in enumerate(ONNARA_STEPS, start=1))
    return f"{UPDATE_GUIDE_HIGHLIGHT}\n\n{steps}\n\n현재 앱 버전: {APP_VERSION}"


def update_guide_dialog_width(parent=None) -> int:
    """기본 크기 캘린더(460px 창)에서 404px, 넓은 창에서도 420px을 넘지 않는다."""
    if parent is None:
        return 404
    return min(420, max(340, parent.width() - 56))


def icon_pixmap(name: str, color: str, size: int, stroke: float = 1.8, ratio: float = 2.0) -> QPixmap:
    """선 아이콘(24 격자 SVG)을 색·크기로 그린다. ratio배 밀도로 그려 고배율 화면에서도 선명하다."""
    svg = (_SVG_HEAD + ICONS[name] + "</svg>").format(c=color, w=stroke)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    px = max(1, math.ceil(size * ratio))
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def _font(px: int, weight: QFont.Weight = QFont.Weight.Normal, *, display: bool = False) -> QFont:
    """정수 px 글꼴. display는 번들 Pretendard(미로드 시 맑은 고딕), 본문은 맑은 고딕."""
    font = QFont()
    font.setFamilies(["Pretendard", "Malgun Gothic", "Segoe UI"] if display else ["Malgun Gothic", "Segoe UI"])
    font.setPixelSize(px)
    font.setWeight(weight)
    return font


def _label(text: str, parent: QWidget, name: str, *, font: QFont | None = None, wrap: bool = False,
           align: Qt.AlignmentFlag = Qt.AlignLeft | Qt.AlignVCenter) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName(name)
    if font is not None:
        label.setFont(font)
    label.setWordWrap(wrap)
    label.setAlignment(align)
    return label


def _icon_label(parent: QWidget, name: str, icon: str, color: str, size: int, box: int, ratio: float) -> QLabel:
    label = QLabel(parent)
    label.setObjectName(name)
    label.setFixedSize(box, box)
    label.setAlignment(Qt.AlignCenter)
    label.setPixmap(icon_pixmap(icon, color, size, ratio=ratio))
    return label


class UpdateDot(QWidget):
    """새 버전이 있다는 빨간 점. 마우스 입력을 막지 않는다. 테두리는 놓인 바탕색을 따른다."""

    def __init__(self, parent: QWidget, *, diameter: int, ring_color: str, ring: int = 2):
        super().__init__(parent)
        self._diameter = diameter
        self._ring = ring
        self._ring_color = ring_color
        self.setFixedSize(diameter + 2 * ring, diameter + 2 * ring)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def ring_color(self) -> str:
        return self._ring_color

    def set_ring_color(self, color: str) -> None:
        self._ring_color = color
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._ring_color))
        painter.drawEllipse(QRectF(self.rect()))
        painter.setBrush(QColor(DOT_COLOR))
        painter.drawEllipse(QRectF(self._ring, self._ring, self._diameter, self._diameter))
        painter.end()


class UpdateTile(QPushButton):
    """받는 곳 타일 하나: 원 안의 그림, 두 줄 제목, 망 꼬리표, 아래 동작 안내."""

    def __init__(self, parent: QWidget, *, name: str, tone: dict, icon: str, title: str, chip: str,
                 hint: str, hint_icon: str, ratio: float):
        super().__init__(parent)
        self.setObjectName(name)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)  # 마우스로 누를 때 포커스 테두리가 남지 않게
        self.setMinimumHeight(204)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName(title.replace("\n", " "))
        self.setAccessibleDescription(f"{chip}. {hint}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 22, 12, 16)
        layout.setSpacing(10)
        self.icon = _icon_label(self, "updateTileIcon", icon, tone["accent"], 28, 58, ratio)
        self.title = _label(title, self, "updateTileTitle", font=_font(16, QFont.Weight.Bold, display=True),
                            align=Qt.AlignCenter)
        self.chip = _label(chip, self, "updateTileChip", font=_font(11, QFont.Weight.Bold), align=Qt.AlignCenter)
        hint_row = QHBoxLayout()
        hint_row.setSpacing(3)
        self.hint = _label(hint, self, "updateTileHint", font=_font(12, QFont.Weight.Bold))
        self.hint_icon = _icon_label(self, "updateTileHintIcon", hint_icon, tone["accent"], 13, 14, ratio)
        hint_row.addStretch(1)
        hint_row.addWidget(self.hint)
        hint_row.addWidget(self.hint_icon)
        hint_row.addStretch(1)
        layout.addWidget(self.icon, 0, Qt.AlignHCenter)
        layout.addWidget(self.title)
        layout.addWidget(self.chip, 0, Qt.AlignHCenter)
        layout.addStretch(1)
        layout.addLayout(hint_row)
        for child in (self.icon, self.title, self.chip, self.hint, self.hint_icon):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)  # 타일 어디를 눌러도 타일이 눌린다


def _tile_qss(name: str, tone: dict) -> str:
    return f"""
QPushButton#{name} {{ background: {tone['bg']}; border: 1px solid {tone['line']}; border-radius: 14px; }}
QPushButton#{name}:hover {{ background: {tone['hover']}; border: 1px solid {tone['accent']}; }}
QPushButton#{name}:pressed {{ background: {tone['pressed']}; border: 1px solid {tone['accent']}; }}
QPushButton#{name}:focus {{ border: 2px solid {tone['accent']}; }}
QPushButton#{name} QLabel#updateTileIcon {{ background: #FFFFFF; border-radius: 29px; }}
QPushButton#{name} QLabel#updateTileTitle {{ color: {INK}; background: transparent; }}
QPushButton#{name} QLabel#updateTileChip {{
    color: #FFFFFF; background: {tone['accent']}; border-radius: 6px; padding: 2px 8px; }}
QPushButton#{name} QLabel#updateTileHint {{ color: {tone['accent']}; background: transparent; }}
QPushButton#{name} QLabel#updateTileHintIcon {{ background: transparent; }}
"""


CARD_QSS = f"""
QWidget#centerWidget {{ background: #FFFFFF; border: 1px solid rgba(1, 41, 95, 16); border-radius: 18px; }}
QLabel#updateVersionPill {{ color: #3F4852; background: #F1F4F9; border-radius: 10px; padding: 3px 10px; }}
QLabel#updateTitle {{ color: {INK}; }}
QLabel#updateSub, QLabel#updateNote, QLabel#updateVersion {{ color: {SUB}; }}
QLabel#updateHighlight {{ color: {ONNARA['accent']}; }}
QLabel#updateStepText {{ color: {BODY}; }}
QLabel#updateStepNumber {{ color: #FFFFFF; background: {ONNARA['accent']}; border-radius: 11px; }}
QLabel#updateGuideIcon {{ background: {ONNARA['bg']}; border: 1px solid {ONNARA['line']}; border-radius: 24px; }}
QWidget#updateSteps {{ background: #F6F8FB; border-radius: 12px; }}
QPushButton#updateCloseButton {{
    color: {BODY}; background: #FFFFFF; border: 1px solid #DFE5EE; border-radius: 10px; font-size: 13px; }}
QPushButton#updateCloseButton:hover {{ background: #F1F4F9; }}
QPushButton#updateCloseButton:pressed {{ background: #E6EBF3; }}
QPushButton#updateBackButton {{
    color: #3F4852; background: transparent; border: none; border-radius: 10px;
    padding: 0px 12px 0px 6px; font-size: 13px; text-align: left; }}
QPushButton#updateBackButton:hover {{ background: #F1F4F9; }}
""" + _tile_qss("updateTileOnnara", ONNARA) + _tile_qss("updateTileGitLab", GITLAB)


class UpdateGuideDialog(MaskDialogBase):
    """부모 창 위에 뜨는 '앱 업데이트' 안내창. 첫 화면(받는 곳 고르기) ↔ 온나라 안내를 같은 창에서 바꾼다."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setMaskColor(MASK_COLOR)
        self.setShadowEffect(56, (0, 14), QColor(1, 20, 48, 90))
        self._hBoxLayout.removeWidget(self.widget)
        self._hBoxLayout.addWidget(self.widget, 1, Qt.AlignCenter)
        self._width = update_guide_dialog_width(parent)
        self._ratio = max(2.0, float(math.ceil(parent.devicePixelRatioF())))
        self.widget.setStyleSheet(CARD_QSS)

        self._layout = QVBoxLayout(self.widget)
        self._layout.setSpacing(0)
        self.choice_page = self._build_choice_page()
        self.onnara_page = self._build_onnara_page()
        self._layout.addWidget(self.choice_page)
        self._layout.addWidget(self.onnara_page)

        self.close_button = QPushButton("닫기", self.widget)
        self.close_button.setObjectName("updateCloseButton")
        self.close_button.setFixedHeight(44)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.clicked.connect(self.reject)
        self._layout.addSpacing(10)
        self._layout.addWidget(self.close_button)

        self.onnara_tile.clicked.connect(self.show_onnara_guide)
        self.gitlab_tile.clicked.connect(self.open_gitlab)
        self.back_button.clicked.connect(self.show_choice)
        self.show_choice()

    # ── 화면 구성 ──────────────────────────────────────────
    def _build_choice_page(self) -> QWidget:
        page = QWidget(self.widget)
        page.setObjectName("updateChoicePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        pill = _label(f"현재 {APP_VERSION}", page, "updateVersionPill", font=_font(11, QFont.Weight.Bold))
        title = _label("어디에서 받을까요?", page, "updateTitle", font=_font(20, QFont.Weight.Bold, display=True),
                       align=Qt.AlignCenter)
        sub = _label("PC가 연결된 망에 맞는 쪽을 고르세요", page, "updateSub", font=_font(13), align=Qt.AlignCenter)
        layout.addWidget(pill, 0, Qt.AlignHCenter)
        layout.addSpacing(10)
        layout.addWidget(title)
        layout.addSpacing(6)
        layout.addWidget(sub)
        layout.addSpacing(20)

        tiles = QGridLayout()
        tiles.setHorizontalSpacing(12)
        tiles.setColumnStretch(0, 1)
        tiles.setColumnStretch(1, 1)
        self.onnara_tile = UpdateTile(page, name="updateTileOnnara", tone=ONNARA, icon="building",
                                      title="온나라 시스템에서\n받기", chip="공공기관 업무망",
                                      hint="받는 방법 보기", hint_icon="chevron_right", ratio=self._ratio)
        self.gitlab_tile = UpdateTile(page, name="updateTileGitLab", tone=GITLAB, icon="globe",
                                      title="GitLab에서\n받기", chip="외부 인터넷망",
                                      hint="브라우저로 열기", hint_icon="external", ratio=self._ratio)
        tiles.addWidget(self.onnara_tile, 0, 0)
        tiles.addWidget(self.gitlab_tile, 0, 1)
        layout.addLayout(tiles)
        layout.addSpacing(20)
        layout.addWidget(_label("어느 쪽이든 일정·메모·설정은 그대로 남습니다", page, "updateNote",
                                font=_font(12), align=Qt.AlignCenter))
        return page

    def _build_onnara_page(self) -> QWidget:
        page = QWidget(self.widget)
        page.setObjectName("updateOnnaraPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.back_button = QPushButton("받는 곳 다시 고르기", page)
        self.back_button.setObjectName("updateBackButton")
        self.back_button.setIcon(icon_pixmap("chevron_left", "#3F4852", 16, stroke=2.2, ratio=self._ratio))
        self.back_button.setIconSize(QSize(16, 16))
        self.back_button.setFixedHeight(36)
        self.back_button.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.back_button, 0, Qt.AlignLeft)
        layout.addSpacing(8)

        icon = _icon_label(page, "updateGuideIcon", "building", ONNARA["accent"], 24, 48, self._ratio)
        title = _label(UPDATE_GUIDE_TITLE, page, "updateTitle", font=_font(19, QFont.Weight.Bold, display=True),
                       align=Qt.AlignCenter)
        highlight = _label(UPDATE_GUIDE_HIGHLIGHT, page, "updateHighlight", font=_font(13, QFont.Weight.Bold),
                           wrap=True, align=Qt.AlignCenter)
        layout.addWidget(icon, 0, Qt.AlignHCenter)
        layout.addSpacing(8)
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(highlight)
        layout.addSpacing(16)

        steps = QWidget(page)
        steps.setObjectName("updateSteps")
        steps.setAttribute(Qt.WA_StyledBackground, True)
        steps_layout = QVBoxLayout(steps)
        steps_layout.setContentsMargins(16, 14, 16, 14)
        steps_layout.setSpacing(10)
        self.step_labels = []
        for number, text in enumerate(ONNARA_STEPS, start=1):
            row = QHBoxLayout()
            row.setSpacing(10)
            badge = _label(str(number), steps, "updateStepNumber", font=_font(12, QFont.Weight.Bold),
                           align=Qt.AlignCenter)
            badge.setFixedSize(22, 22)
            shown = text.replace("<", "&lt;").replace(">", "&gt;").replace('"기후노트"', '<b>"기후노트"</b>')
            label = _label(shown, steps, "updateStepText", font=_font(13), wrap=True)
            label.setTextFormat(Qt.RichText)
            row.addWidget(badge, 0, Qt.AlignTop)
            row.addWidget(label, 1)
            steps_layout.addLayout(row)
            self.step_labels.append(label)
        layout.addWidget(steps)
        layout.addSpacing(16)
        layout.addWidget(_label(f"현재 앱 버전: <b>{APP_VERSION}</b>", page, "updateVersion", font=_font(12),
                                align=Qt.AlignCenter))
        return page

    # ── 동작 ───────────────────────────────────────────────
    def show_choice(self) -> None:
        self.onnara_page.hide()
        self.choice_page.show()
        self._layout.setContentsMargins(20, 26, 20, 18)
        self._fit()

    def show_onnara_guide(self) -> None:
        self.choice_page.hide()
        self.onnara_page.show()
        self._layout.setContentsMargins(20, 16, 20, 18)
        self._fit()

    def open_gitlab(self) -> None:
        """기본 브라우저로 GitLab 최신 Release 페이지를 연다. 앱은 접속하지 않는다."""
        QDesktopServices.openUrl(QUrl(GITLAB_LATEST_URL))
        self.accept()

    def _fit(self) -> None:
        self.widget.setFixedWidth(self._width)
        self._layout.activate()
        height = (self._layout.heightForWidth(self._width) if self._layout.hasHeightForWidth()
                  else self._layout.sizeHint().height())
        self.widget.setFixedHeight(max(height, self._layout.minimumSize().height()))


def show_update_guide(parent, latest: str | None = None) -> None:
    dlg = UpdateGuideDialog(parent)
    dlg.close_button.setFocus()
    dlg.exec()
