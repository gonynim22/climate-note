# 미니앱 공용 창 틀(B안) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 미니앱 5개 창을 어두운 제목줄(+같은 색 왼쪽 메뉴) 공용 틀 하나로 맞춘다.

**Architecture:** `ui_mini_app_frame.MiniAppTitleBar`(아이콘·이름·닫기, 자체 QSS)를 새로 만들고 다섯 창이 기존 머리줄 대신 이것을 표면 맨 위에 둔다. 각 창의 `header`·`title_label`·`close_button` 속성은 제목줄을 가리키게 해 끌기·좁은 화면·시험 코드를 그대로 쓴다(환산기만 `title_label`이 분류 이름). 체크 색은 테마 고정 팔레트에 `Accent`를 더한다.

**Tech Stack:** Python 3.13, PySide6 6.11.2(Qt 위젯·QSS), pytest-qt, `tools/verify.py` 하네스.

**Spec:** `docs/superpowers/specs/2026-10-10-mini-app-frame-design.md`

## Global Constraints

- 제목줄 바탕 `#23252B`, 높이 48px(좁은 화면 40px), 위 모서리 16px, 아이콘 22px, 이름 15px 굵게 `#F4F5F2`, 닫기 28×28 `#C9CED8`·hover `#343740`·focus `#90ACD0`, 툴팁 `닫기 (Esc)`, 접근 이름 `<앱 이름> 닫기`.
- 메뉴 바탕 `#23252B`(아래 왼쪽 모서리만 16px), 고른 메뉴는 지금 모양 그대로(왼쪽 막대 없음).
- 본문 `#FDFDFB`. 창 크기 환산기 440×580, 날짜·금액·문서 480×620, 글자 따기 460×560 유지.
- 앱 색은 아이콘에만. 주 버튼·포커스·선택·체크 색 `#2563EB`.
- DB v17·Export v2·salt·설정 키·창 수명 불변. QSS 글꼴 크기는 정수 px. 버전 v3.9a 유지, 빌드·push 없음.
- 커밋은 사용자 지시 때만(작업 폴더에 둔다).

## Review Focus

- 좁은 화면(작업 영역 높이 620 미만): 제목줄이 40px로 줄고 무스크롤·경계 시험이 그대로 통과해야 한다 → 기존 날짜·금액 좁은 화면 시험 + Task 2 높이 단언.
- 제목줄 끌기 뒤 창이 화면 밖으로 나가지 않아야 한다(기존 `fit_to_screen` 보정) → Task 1 끌기 시험이 이동량과 화면 안을 함께 확인.
- 닫기 버튼 키보드: Tab으로 가서 Enter/Space로 닫혀야 한다(창 eventFilter 재사용) → Task 1 시험에서 Enter 키로 닫힘.
- 125/150% 배율에서 제목줄 아이콘·글자 잘림 없음 → 하네스 `QT_SCALE_FACTOR` 실행.
- 화면 글자 따기 걷어내기: `screen_text`가 `ui_mini_app_frame`만 한 방향으로 가져다 쓴다 → Task 4에서 import 방향 확인.

---

### Task 1: 공용 제목줄 모듈과 다섯 창 공통 시험

**Files:**
- Create: `ui_mini_app_frame.py`
- Create: `tests/test_ui_mini_app_frame.py`
- Modify: `main.py`(`_apply_light_theme`에 `Accent`), `tests/test_app_theme.py`

**Interfaces:**
- Produces: `MiniAppTitleBar(title: str, icon_path: Path | str, on_close: Callable, parent=None)` — 속성 `icon_label: QLabel`, `title_label: QLabel`, `close_button: QPushButton`, 메서드 `set_compact(compact: bool)`. 상수 `FRAME_DARK = "#23252B"`, `FRAME_SURFACE = "#FDFDFB"`, `TITLE_BAR_HEIGHT = 48`, `TITLE_BAR_COMPACT_HEIGHT = 40`, 함수 `mini_app_icon_path(app_id: str) -> Path`.

- [ ] **Step 1: 실패하는 시험 작성** — `tests/test_ui_mini_app_frame.py`

```python
"""미니앱 공용 창 틀(디자인 점검 5번 B안): 다섯 창이 같은 어두운 제목줄을 쓰는지 검사."""
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import database as db
import ui_document_converter
from hwp_conversion import ConversionEnvironment
from ui_mini_app_frame import FRAME_DARK, FRAME_SURFACE, TITLE_BAR_HEIGHT, MiniAppTitleBar

WINDOWS = {
    "unit": ("ui_unit_converter", "UnitConverterWindow", "단위 환산기", True),
    "date": ("ui_date_time_calculator", "DateTimeCalculatorWindow", "날짜·시간 계산기", True),
    "money": ("ui_money_notation", "MoneyNotationWindow", "금액·숫자 표기 도우미", True),
    "doc": ("ui_document_converter", "DocumentConverterWindow", "문서 형식 변환", False),
    "text": ("screen_text.window", "ScreenTextWindow", "화면 글자 따기", False),
}


@pytest.fixture(autouse=True)
def isolated(app_dir, qapp, monkeypatch):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    monkeypatch.setattr(ui_document_converter, "detect_environment",
                        lambda: ConversionEnvironment(Path("hwp.exe"), Path("HwpxConverter.exe")))


def _open(qtbot, key):
    module_name, class_name, _, _ = WINDOWS[key]
    module = __import__(module_name, fromlist=[class_name])
    win = getattr(module, class_name)()
    qtbot.addWidget(win)
    available = QApplication.primaryScreen().availableGeometry()
    win.show_near(QRect(available.left() + 80, available.top() + 80, 64, 48), available)
    assert QTest.qWaitForWindowExposed(win)
    QApplication.processEvents()
    return win


def _pixel(win, widget, point):
    image = win.surface.grab().toImage()
    ratio = image.devicePixelRatio()
    at = widget.mapTo(win.surface, point)
    return image.pixelColor(int(at.x() * ratio), int(at.y() * ratio)).name()


@pytest.mark.parametrize("key", WINDOWS)
def test_title_bar_spans_top_of_surface(qtbot, key):
    _, _, title, _ = WINDOWS[key]
    win = _open(qtbot, key)
    bar = win.title_bar
    assert isinstance(bar, MiniAppTitleBar)
    assert bar.mapTo(win.surface, QPoint()) == QPoint(0, 0)
    assert bar.width() == win.surface.width()
    assert bar.height() == TITLE_BAR_HEIGHT
    assert bar.title_label.text() == title
    assert not bar.icon_label.pixmap().isNull()
    assert bar.close_button.toolTip() == "닫기 (Esc)"
    assert bar.close_button.accessibleName() == f"{title} 닫기"
    assert win.close_button is bar.close_button
    # 제목 글자 위쪽 빈 곳은 어두운 바탕이다.
    assert _pixel(win, bar, QPoint(bar.width() // 2, 4)) == FRAME_DARK.lower()


@pytest.mark.parametrize("key", WINDOWS)
def test_menu_is_dark_and_body_is_light(qtbot, key):
    _, _, _, has_menu = WINDOWS[key]
    win = _open(qtbot, key)
    if has_menu:
        rail = win.category_rail if key == "unit" else win.rail
        assert _pixel(win, rail, QPoint(2, rail.height() - 30)) == FRAME_DARK.lower()
    else:
        surface = win.surface
        assert _pixel(win, surface, QPoint(surface.width() - 8, surface.height() // 2)) == FRAME_SURFACE.lower()


@pytest.mark.parametrize("key", WINDOWS)
def test_title_bar_drag_moves_window_and_close_by_enter(qtbot, key):
    win = _open(qtbot, key)
    bar = win.title_bar
    start = win.pos()
    press_at = QPointF(bar.width() / 2, bar.height() / 2)
    global_at = QPointF(bar.mapToGlobal(press_at.toPoint()))
    for kind, delta, buttons in ((QEvent.MouseButtonPress, QPointF(0, 0), Qt.LeftButton),
                                 (QEvent.MouseMove, QPointF(-30, 20), Qt.LeftButton),
                                 (QEvent.MouseButtonRelease, QPointF(-30, 20), Qt.NoButton)):
        event = QMouseEvent(kind, press_at + delta, global_at + delta, Qt.LeftButton, buttons, Qt.NoModifier)
        QApplication.sendEvent(bar, event)
    QApplication.processEvents()
    assert win.pos() == start + QPoint(-30, 20)
    available = win.screen().availableGeometry()
    assert available.contains(win.frameGeometry())

    bar.close_button.setFocus()
    QTest.keyClick(bar.close_button, Qt.Key_Return)
    QApplication.processEvents()
    assert not win.isVisible()


def test_document_converter_has_no_purple_left():
    import inspect
    source = inspect.getsource(ui_document_converter)
    for purple in ("#6741D9", "#9775FA", "#F3EEFC", "#D7CDEE", "#F4F1FA", "#51456A", "#EEEAF5", "#C9B6F6", "#685481"):
        assert purple not in source, purple
```

`tests/test_app_theme.py`의 `test_text_selection_color_is_app_blue_not_windows_accent` 루프에 한 줄 추가:

```python
        assert palette.color(group, QPalette.Accent).name() == "#2563eb"  # 체크박스·라디오 채움
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_mini_app_frame.py tests/test_app_theme.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: ui_mini_app_frame`, `Accent` `#009faa`(Windows 강조색).

- [ ] **Step 3: 모듈 구현** — `ui_mini_app_frame.py`

```python
# ui_mini_app_frame.py - 미니앱 공용 창 틀(디자인 점검 5번 B안)의 어두운 제목줄
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from app_paths import resource_root

FRAME_DARK = "#23252B"      # 제목줄과 왼쪽 메뉴
FRAME_SURFACE = "#FDFDFB"   # 본문
TITLE_BAR_HEIGHT = 48
TITLE_BAR_COMPACT_HEIGHT = 40
TITLE_ICON_SIZE = 22


def mini_app_icon_path(app_id: str) -> Path:
    """주머니와 같은 미니앱 아이콘. 경로는 resource_root()만 기준으로 만든다."""
    return resource_root() / "resources" / "icons" / "mini_apps" / f"{app_id}.svg"


class MiniAppTitleBar(QFrame):
    """앱 아이콘 · 이름 · 닫기(×). 창 끌기는 창이 이 위젯에 eventFilter를 걸어 처리한다.

    아이콘과 이름은 마우스를 받지 않아 누르기가 제목줄로 전달된다.
    """

    def __init__(self, title, icon_path, on_close, parent=None):
        super().__init__(parent)
        self.setObjectName("miniAppTitleBar")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        self.setStyleSheet(f"""
            QFrame#miniAppTitleBar {{ background:{FRAME_DARK}; border:0;
                border-top-left-radius:16px; border-top-right-radius:16px; }}
            QLabel#miniAppTitle {{ color:#F4F5F2; font-size:15px; font-weight:bold; background:transparent; }}
            QLabel#miniAppIcon {{ background:transparent; }}
            QPushButton#miniAppClose {{ background:transparent; color:#C9CED8; border:1px solid transparent;
                border-radius:8px; font-size:20px; padding:0; }}
            QPushButton#miniAppClose:hover {{ background:#343740; color:#FFFFFF; }}
            QPushButton#miniAppClose:focus {{ border-color:#90ACD0; }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 10, 0)
        layout.setSpacing(10)
        self.icon_label = QLabel(self)
        self.icon_label.setObjectName("miniAppIcon")
        self.icon_label.setFixedSize(TITLE_ICON_SIZE, TITLE_ICON_SIZE)
        self.icon_label.setPixmap(QIcon(str(icon_path)).pixmap(TITLE_ICON_SIZE, TITLE_ICON_SIZE))
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("miniAppTitle")
        for label in (self.icon_label, self.title_label):
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout.addWidget(label)
        layout.addStretch()
        self.close_button = QPushButton("×", self)
        self.close_button.setObjectName("miniAppClose")
        self.close_button.setFixedSize(28, 28)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setToolTip("닫기 (Esc)")
        self.close_button.setAccessibleName(f"{title} 닫기")
        self.close_button.clicked.connect(on_close)
        layout.addWidget(self.close_button)

    def set_compact(self, compact: bool) -> None:
        self.setFixedHeight(TITLE_BAR_COMPACT_HEIGHT if compact else TITLE_BAR_HEIGHT)
```

`main._apply_light_theme`의 선택 팔레트에 추가:

```python
    selection.setColor(QPalette.Accent, QColor("#2563EB"))  # 체크박스·라디오도 Windows 강조색 대신
```

- [ ] **Step 4: 모듈 단위 시험 통과 확인** — 창 시험은 Task 2~5 뒤 통과한다.

Run: `.venv/Scripts/python.exe -m pytest tests/test_app_theme.py -q -p no:cacheprovider`
Expected: PASS

### Task 2: 날짜·시간 계산기와 금액·숫자 표기에 제목줄 적용

**Files:** Modify `ui_date_time_calculator.py`(머리줄 80-95, `fit_to_screen` 707), `ui_money_notation.py`(`_build_header` 152-168, `fit_to_screen` 586)

**Interfaces:** Consumes `MiniAppTitleBar`, `mini_app_icon_path("date_time"|"money_notation")`. Produces `self.title_bar`, `self.header is self.title_bar`, `self.title_label is self.title_bar.title_label`, `self.close_button is self.title_bar.close_button`.

- [ ] **Step 1: 머리줄 교체(날짜·시간)**

```python
        self.title_bar = MiniAppTitleBar('날짜·시간 계산기', mini_app_icon_path('date_time'), self.close, self.surface)
        self.header = self.title_bar
        self.title_label = self.title_bar.title_label
        self.close_button = self.title_bar.close_button
        self.close_button.installEventFilter(self)  # Enter로 닫기(다른 버튼과 같은 처리)
        surface_layout.addWidget(self.title_bar)
        self.title_bar.installEventFilter(self)
```

`fit_to_screen`: `self.header.setFixedHeight(40 if compact else 52)` → `self.title_bar.set_compact(compact)`.

- [ ] **Step 2: 같은 교체(금액)** — `_build_header` 본문을 위와 같은 코드로(제목 `금액·숫자 표기 도우미`, 아이콘 `money_notation`, `parent_layout.addWidget`), `fit_to_screen`도 `set_compact`.

- [ ] **Step 3: 시험** — Run: `pytest tests/test_ui_mini_app_frame.py -k "date or money" tests/test_ui_date_time_calculator.py tests/test_ui_money_notation.py -q`. Expected: PASS.

### Task 3: 문서 형식 변환 — 제목줄과 중립·파랑 색

**Files:** Modify `ui_document_converter.py`(QSS 54-68, 머리줄·여백 80-100, `fit_to_screen` 380-393)

- [ ] **Step 1: QSS 교체**

```python
            QWidget#documentSurface { background:#FDFDFB; border-radius:16px; }
            QPushButton { background:white; border:1px solid #CDD5E0; border-radius:6px; padding:5px 8px; }
            QPushButton:hover { background:#EDF3FB; border-color:#91AACA; }
            QPushButton:focus { border:1px solid #315C98; }
            QPushButton:disabled { color:#959CA6; background:#F3F4F6; }
            QPushButton#convertStart { background:#2563EB; color:white; border:0; font-weight:bold; }
            QPushButton#convertStart:disabled { background:#A9C1F2; color:#FFFFFF; }
            QTreeWidget { background:white; border:1px solid #DDE1E9; border-radius:8px; }
            QTreeWidget::item { height:32px; }
            QHeaderView::section { background:#F5F7FA; color:#4E5663; border:0; padding:7px; }
            QProgressBar { border:0; background:#EEF1F5; border-radius:5px; text-align:center; height:16px; }
            QProgressBar::chunk { background:#A9C1F2; border-radius:5px; }
```

제목 `HWP  →  HWPX`: `color:#172B4D`, 환경 문구 `color:#687080`.

- [ ] **Step 2: 표면 = 제목줄 + 내용**

```python
        surface_layout = QVBoxLayout(self.surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)
        self.title_bar = MiniAppTitleBar("문서 형식 변환", mini_app_icon_path("document_converter"), self.close, self.surface)
        self.header = self.title_bar
        self.title_label = self.title_bar.title_label
        self.close_button = self.title_bar.close_button
        self.close_button.installEventFilter(self)
        self.title_bar.installEventFilter(self)
        surface_layout.addWidget(self.title_bar)
        content = QWidget(self.surface)
        surface_layout.addWidget(content, 1)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 12, 18, 16)
        layout.setSpacing(10)
        self.content_layout = layout
```

`fit_to_screen`: `self.surface.layout().setSpacing(...)` → `self.content_layout.setSpacing(...)`.

- [ ] **Step 3: 시험** — `pytest tests/test_ui_mini_app_frame.py -k doc tests/test_ui_document_converter.py -q` PASS.

### Task 4: 화면 글자 따기 — 제목줄

**Files:** Modify `screen_text/window.py`(STYLE 38-53, `_build` 152-171)

- [ ] **Step 1:** STYLE `#screenTextSurface` 바탕 `#FDFDFB`, `QPushButton#screenTextClose` 줄 삭제(제목줄이 자체 QSS). `_build`의 `self.header` QFrame 블록을 Task 2와 같은 제목줄 코드로(제목 `화면 글자 따기`, 아이콘은 `APP.icon_path`와 같은 `resource_root() / "screen_text" / "icon.svg"`) 바꾸고, 표면 레이아웃 여백 0 + 내용 위젯(여백 18·10·18·16, 간격 10)에 `self.stack` 이하를 둔다.
- [ ] **Step 2:** `screen_text`의 새 import는 `ui_mini_app_frame`과 `app_paths`뿐(핵심 → 선택형 방향 import 없음) 확인: `grep -rn "screen_text" ui_mini_app_frame.py` 결과 없음.
- [ ] **Step 3: 시험** — `pytest tests/test_ui_mini_app_frame.py -k text tests/test_screen_text_ui.py tests/test_screen_text_guide.py -q` PASS.

### Task 5: 단위 환산기 — 제목줄과 메뉴 정리

**Files:** Modify `ui_unit_converter.py`(QSS 59-77, 표면 구성 80-175, `eventFilter` 509)

- [ ] **Step 1:** 표면 레이아웃을 `QVBoxLayout`(제목줄) + `QHBoxLayout`(메뉴 | 본문)으로. 메뉴 QSS `border-bottom-left-radius:16px`만, 본문 `border-bottom-right-radius:16px`만. 메뉴 맨 위 `▪  단위 환산` 글자 삭제.
- [ ] **Step 2:** 본문 머리줄(44px)은 분류 이름(`self.title_label`)만 두고 닫기를 뺀다(높이 36px, 여백 16·6·8·0). 닫기는 제목줄 것을 `self.close_button`으로. `QToolButton#converterClose` QSS 줄 정리.
- [ ] **Step 3:** `eventFilter` 끌기 대상 `(self.header, self.title_label)` → `(self.title_bar,)`(분류 이름은 더 이상 끌기 손잡이가 아니다). `self.header = self.title_bar`.
- [ ] **Step 4: 시험** — `pytest tests/test_ui_mini_app_frame.py tests/test_ui_unit_converter.py -q` PASS.

### Task 6: 문서·검증·기록

- [ ] `docs/UI_PATTERNS.md`(미니앱 공용 틀 절), `docs/ARCHITECTURE.md`(모듈 표에 `ui_mini_app_frame.py`), `docs/TESTING.md`(공용 틀 시험), `docs/MONEY_NOTATION.md`·`docs/DATE_TIME_CALCULATION.md`·`docs/SCREEN_TEXT.md`의 틀 설명, `AGENTS.md`(미니앱 계약 줄에 공용 틀, 기록 관리 한 줄), 작업 기록 `docs/work/2026-10-10-mini-app-frame.md`.
- [ ] `verify.py quick --tests tests/test_ui_mini_app_frame.py tests/test_app_theme.py tests/test_ui_unit_converter.py tests/test_ui_date_time_calculator.py tests/test_ui_money_notation.py tests/test_ui_document_converter.py tests/test_screen_text_ui.py tests/test_screen_text_guide.py tests/test_ui_mini_apps.py` 100/125/150%, 이어서 `verify.py full`.
- [ ] 전/후 캡처(`output/design/miniapp-frame-20261010/img/after_*.png`)와 디자인 점검 보고서 5번 완료 표시.
