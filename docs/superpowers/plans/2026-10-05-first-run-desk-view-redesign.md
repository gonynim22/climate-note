# 최초 실행 크기 선택 — 데스크 뷰 리디자인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 최초 크기 선택 대화상자(`ui_first_run.FirstRunSizeDialog`)의 화면을 사용자가 고른 ‘시안 1 — 데스크 뷰’로 교체한다. 시작 흐름·데이터 경로는 바꾸지 않는다.

**Architecture:** `ui_first_run.py` 한 파일을 다시 쓴다. 미리보기는 `_DeskPreview`(QPainter 벡터, `preview_window_rect()`로 `ui_main` 크기 규칙을 1920×1080 화면에 적용), 선택 항목은 `_SizeChoice`(넓은 배치: 라디오 행 / 한 열 배치: 간단한 버튼, 같은 객체 3개를 방향만 바꿔 재사용)로 그린다. `fit_to_available_geometry()`가 작업 영역에 따라 넓은·낮은·한 열 배치를 고른다. `main.py`·`database.py`·`tools/smoke_release.py`는 수정하지 않는다.

**Tech Stack:** Python 3.13, PySide6 6.11.2(QPainter, QVariantAnimation), pytest-qt, 프로젝트 하네스 `tools/verify.py`.

**Spec:** [작업 기록·확정 디자인](../../work/2026-10-05-first-run-desk-view-redesign.md). 시각 기준은 로컬 `output/design/first-run-size-redesign-20261005/desk-view-layouts.html`(Git 제외)이며 수치는 아래 코드에 모두 옮겨 두었다.

## Global Constraints

- 앱 버전 **v3.8d 유지**(`app_info.py` 수정 금지). DB v17·Export v2·salt·설정 키·`calendar_scale` seed 경로 변경 금지. 새 설정 키 금지.
- `main.py`, `database.py`, `tools/smoke_release.py` 수정 금지. `FirstRunSizeDialog()` 무인자 생성, `selected_scale`, `exec()` 결과 계약 유지.
- 창 제목 `기후노트 — 처음 설정` 유지(release smoke가 제목으로 창을 찾는다). ‘이 크기로 시작’이 기본 버튼(Enter=확정), X·Esc·‘종료’=취소, X/종료 버튼에 포커스가 있을 때 Enter=취소 유지.
- 창 크기 = `min(680, 작업 영역 폭 − 24) × min(500, 작업 영역 높이 − 24)`. 낮은 배치: 높이 < 470. 한 열 배치: 폭 < 580 **또는** 높이 < 370.
- 문구(그대로): 제목 `어떤 크기로 시작할까요?`(넓은 배치는 `어떤 크기로` / `시작할까요?` 두 줄), 안내 `고른 모습 그대로 시작해요.` / `설정에서 언제든 바꿀 수 있어요.`, 항목 `기본·작게 띄워두기`, `중간·일정도 함께 보기`, `크게·위젯까지 한눈에`, 미리보기 안내 `1920×1080 화면 기준 · 오른쪽 아래 기본 위치`, 버튼 `종료`, `이 크기로 시작`. **선택 설명 문구는 두지 않는다.**
- 글꼴: 제목·크기 이름·시작 버튼은 번들 `Pretendard`(미로드 시 `Malgun Gothic`), 그 외 `Malgun Gothic`. 모든 글꼴 크기는 정수 px.
- 시스템 테마와 무관하게 항상 밝게 그린다(`isDarkTheme` 사용 금지). 이미지 자산 추가 금지(QPainter 벡터만).
- 테스트·캡처는 합성 데이터(`output/harness/<run-id>/`)에서만. 실사용 `%LOCALAPPDATA%\MyDesktopCalendar` 접근 금지.
- 커밋은 Task 3에서 한 번. `AGENTS.md`의 기존 사용자 변경 4줄, `docs/RELEASE_HISTORY.md`, 기존 미추적 `docs/work/` 기록은 스테이징하지 않는다. push 금지. 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- Pretendard가 로드되지 않은 환경(폰트 파일 누락·로드 실패): 맑은 고딕 폴백은 글자 폭이 넓어 320px 폭·680×376 배치에서 제목/버튼이 넘칠 수 있다 → 폴백 글꼴로도 모든 컨트롤이 창 안에 있어야 한다. (Task 1 `test_layout_fits_when_pretendard_is_unavailable`)
- 매우 낮은 작업 영역(예: 1366×768 @200%, 논리 높이 약 360): 넓은-낮은 배치의 왼쪽 열(약 240px)이 들어가지 않는다 → 높이 370 미만은 한 열 배치로 전환되어야 한다. (Task 1 fit 매개변수 `(800, 380)`)
- 미리보기 애니메이션 중 빠른 재선택: 마지막 선택 위치에서 멈춰야 한다. (Task 1 `test_reselecting_during_animation_ends_at_last_choice`)
- 시스템 다크 모드로 첫 실행: 대화상자가 밝게 보여야 한다. (Task 1 `test_dialog_stays_light_under_dark_theme`)
- 한 열 배치에서 키보드만 사용: 방향키로 크기 버튼을 순환 선택하고 Enter로 확정해야 한다. (Task 1 `test_stacked_keyboard_selection_and_accept`)

---

### Task 1: 데스크 뷰 대화상자 재작성

**Files:**
- Modify(전체 교체): `ui_first_run.py`
- Modify: `tests/test_first_run.py` (import 갱신, `test_dialog_controls_fit_small_work_area` 교체, 새 검사 추가. 데이터 경로 검사 1~13번째 함수는 그대로)

**Interfaces:**
- Consumes: 없음(`main._choose_initial_calendar_scale()`가 기존처럼 `FirstRunSizeDialog()`·`exec()`·`selected_scale`을 쓴다).
- Produces:
  - `preview_window_rect(scale: str) -> QRect` — 1920×1032 작업 영역 기준 창 사각형(스냅 전).
  - 상수 `PREVIEW_SCREEN_WIDTH = 1920`, `PREVIEW_WORK_HEIGHT = 1032`, `SETUP_WINDOW_TITLE`, `SIZE_CHOICES`(3-튜플: scale, 이름, 짧은 설명).
  - `FirstRunSizeDialog` 속성: `cards: list[_SizeChoice]`, `selected_scale: str`, `stacked: bool`, `short: bool`, `heading`, `subtitle`, `hint`, `preview: _DeskPreview`, `start_button`, `cancel_button`, `close_button`; 메서드 `fit_to_available_geometry(area: QRect)`, `_select(scale)`, `_screen_changed(screen)`.
  - `_SizeChoice` 속성: `scale`, `label`, `caption`, `segment: bool`; `set_segment(segment: bool, height: int)`.
  - `_DeskPreview`: `scale: str`, `set_scale(scale)`, `set_metrics(padding: tuple[int, int], gap: int)`, `window_rect() -> QRectF`(1920 좌표), `window_rect_on_widget() -> QRectF`, `monitor_ratio() -> float`, `_animation: QVariantAnimation`.

- [ ] **Step 1: 테스트 갱신 — import와 헬퍼**

`tests/test_first_run.py` 상단 import를 다음으로 바꾼다.

```python
"""최초 설치 분기와 선택값의 실제 DB/화면/백업 왕복."""
import sqlite3
import zipfile
from contextlib import closing

import pytest
from PySide6.QtCore import QObject, QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontInfo
from PySide6.QtWidgets import QDialog

import database as db
import security
from ui_first_run import (
    PREVIEW_SCREEN_WIDTH, PREVIEW_WORK_HEIGHT, FirstRunSizeDialog, preview_window_rect,
)
```

`fresh_dir` 픽스처 바로 아래에 헬퍼 3개를 추가한다.

```python
def _mapped(dialog, widget):
    """자식 레이아웃 안의 위젯도 대화상자 좌표로 비교한다."""
    return QRect(widget.mapTo(dialog, QPoint(0, 0)), widget.size())


def _assert_controls_inside(dialog):
    controls = [*dialog.cards, dialog.heading, dialog.subtitle, dialog.preview, dialog.hint,
                dialog.start_button, dialog.cancel_button, dialog.close_button]
    for control in controls:
        if control.isVisible():
            assert dialog.rect().contains(_mapped(dialog, control)), (
                control, _mapped(dialog, control), dialog.rect())
    footer_top = min(_mapped(dialog, dialog.start_button).top(),
                     _mapped(dialog, dialog.cancel_button).top())
    for control in (*dialog.cards, dialog.preview, dialog.subtitle):
        assert _mapped(dialog, control).bottom() < footer_top, control
    if dialog.hint.isVisible():
        assert not _mapped(dialog, dialog.hint).intersects(_mapped(dialog, dialog.cancel_button))


def _show_on_synthetic_area(qtbot, area):
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(20)
    # 아래 QRect는 합성 화면이다. 실제 다중 모니터 이동 통지는 별도 검사한다.
    dialog.windowHandle().screenChanged.disconnect(dialog._screen_changed)
    dialog.fit_to_available_geometry(area)
    qtbot.wait(20)
    return dialog
```

- [ ] **Step 2: 테스트 갱신 — 배치 검사 교체**

기존 `test_dialog_controls_fit_small_work_area` 함수 전체(현재 191~210행)를 아래로 교체한다.

```python
@pytest.mark.parametrize("width,height,stacked,short", [
    (1000, 900, False, False), (700, 550, False, False), (800, 400, False, True),
    (540, 500, True, False), (400, 600, True, False), (320, 600, True, False),
    (400, 450, True, True), (800, 380, True, True),
])
def test_dialog_layout_fits_work_area(qtbot, width, height, stacked, short):
    area = QRect(20, 30, width, height)
    dialog = _show_on_synthetic_area(qtbot, area)
    assert (dialog.stacked, dialog.short) == (stacked, short)
    assert area.contains(dialog.geometry())
    _assert_controls_inside(dialog)
    cards = [_mapped(dialog, card) for card in dialog.cards]
    preview = _mapped(dialog, dialog.preview)
    if stacked:
        # 한 열 배치: 위에 크기 버튼 한 줄, 아래에 미리보기
        assert len({card.top() for card in cards}) == 1
        assert all(card.bottom() < preview.top() for card in cards)
        assert all(card.segment for card in dialog.cards)
    else:
        # 넓은 배치: 왼쪽 세로 목록, 오른쪽 미리보기
        assert len({card.left() for card in cards}) == 1
        assert all(card.right() < preview.left() for card in cards)
        assert not any(card.segment for card in dialog.cards)
    assert dialog.hint.isVisible() is (short and not stacked)
    assert dialog.preview.monitor_ratio() > (0.4 if height >= 450 else 0.1)
```

- [ ] **Step 3: 테스트 추가 — 미리보기·테마·글꼴·키보드**

파일 끝(`test_release_setup_confirmation_refuses_unowned_window` 아래)에 추가한다.

```python
def test_preview_geometry_matches_main_window_rule(app_dir):
    from ui_main import MainCalendarWindow, _calendar_corner_coordinates

    class Screen:
        def availableGeometry(self):
            return QRect(0, 0, PREVIEW_SCREEN_WIDTH, PREVIEW_WORK_HEIGHT)

        def physicalDotsPerInch(self):
            return 96

    screen = Screen()
    snap = round(96 * 5 / 25.4)
    for scale in db.CALENDAR_SCALES:
        width, height = MainCalendarWindow._calendar_scale_geometry(None, scale, screen)
        x, y = _calendar_corner_coordinates(screen, width, height, "bottom-right")
        rect = preview_window_rect(scale)
        assert (rect.width(), rect.height()) == (width, height)
        # 실제 창은 5mm 격자로 스냅하므로 그 이내의 차이만 허용한다.
        assert abs(rect.x() - x) <= snap and abs(rect.y() - y) <= snap


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_preview_paints_selected_window_at_its_real_position(qtbot, scale):
    dialog = _show_on_synthetic_area(qtbot, QRect(0, 0, 1000, 900))
    dialog._select(scale)
    target = QRectF(preview_window_rect(scale))
    qtbot.waitUntil(lambda: dialog.preview.window_rect() == target, timeout=2000)
    image = dialog.preview.grab().toImage()
    ratio = image.devicePixelRatio()
    window = dialog.preview.window_rect_on_widget()

    def color_at(x, y):
        return image.pixelColor(int(x * ratio), int(y * ratio))

    # 세 크기 모두 창 오른쪽 아래 안쪽은 흰 바탕(일정 열/목록 아래 빈 곳)이다.
    assert color_at(window.right() - 3, window.bottom() - 3).name() == "#ffffff"
    if scale != "large":
        outside = color_at(window.left() - 4, window.bottom() - 3)
        assert abs(outside.red() - 0xCB) <= 12
        assert abs(outside.green() - 0xD6) <= 12
        assert abs(outside.blue() - 0xE3) <= 12


def test_reselecting_during_animation_ends_at_last_choice(qtbot):
    dialog = _show_on_synthetic_area(qtbot, QRect(0, 0, 1000, 900))
    dialog._select("large")
    dialog._select("medium")
    target = QRectF(preview_window_rect("medium"))
    qtbot.waitUntil(lambda: dialog.preview.window_rect() == target, timeout=2000)
    qtbot.wait(300)
    assert dialog.preview.window_rect() == target
    assert dialog.preview.scale == "medium"


def test_dialog_stays_light_under_dark_theme(qtbot):
    from qfluentwidgets import Theme, setTheme
    setTheme(Theme.DARK)
    try:
        dialog = _show_on_synthetic_area(qtbot, QRect(0, 0, 1000, 900))
        image = dialog.grab().toImage()
        ratio = image.devicePixelRatio()
        # 머리줄 위 여백(바탕)이 다크 테마에서도 흰색이어야 한다.
        assert image.pixelColor(int(dialog.width() / 2 * ratio), int(8 * ratio)).name() == "#ffffff"
    finally:
        setTheme(Theme.LIGHT)


def test_heading_choice_and_start_use_bundled_pretendard(qtbot):
    from app_fonts import load_ui_fonts
    load_ui_fonts()
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    assert QFontInfo(dialog.heading.font()).family() == "Pretendard"
    assert QFontInfo(dialog.start_button.font()).family() == "Pretendard"
    assert QFontInfo(dialog.subtitle.font()).family() == "Malgun Gothic"


def test_layout_fits_when_pretendard_is_unavailable(qtbot, monkeypatch):
    import ui_first_run
    original = ui_first_run._font

    def without_pretendard(px, weight=QFont.Weight.Normal, *, display=False):
        return original(px, weight, display=False)

    monkeypatch.setattr(ui_first_run, "_font", without_pretendard)
    for width, height in ((320, 600), (800, 400), (400, 450), (1000, 900)):
        dialog = _show_on_synthetic_area(qtbot, QRect(0, 0, width, height))
        _assert_controls_inside(dialog)


def test_stacked_keyboard_selection_and_accept(qtbot):
    dialog = _show_on_synthetic_area(qtbot, QRect(0, 0, 400, 600))
    assert dialog.stacked
    dialog.activateWindow()
    dialog.cards[0].setFocus()
    qtbot.waitUntil(lambda: dialog.cards[0].hasFocus())
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Right)
    assert dialog.selected_scale == "medium" and dialog.cards[1].hasFocus()
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Left)
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Left)
    assert dialog.selected_scale == "large" and dialog.cards[2].hasFocus()
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Return)
    assert dialog.result() == QDialog.Accepted
```

- [ ] **Step 4: 실패 확인**

Run: `.venv/Scripts/python.exe tools/verify.py quick --tests tests/test_first_run.py`
Expected: FAIL — 수집 단계에서 `ImportError: cannot import name 'PREVIEW_SCREEN_WIDTH' from 'ui_first_run'`.

- [ ] **Step 5: `ui_first_run.py` 전체 교체**

```python
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
        header.addWidget(self.brand_sub)
        header.addStretch(1)
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
```

- [ ] **Step 6: 통과 확인(100%)**

Run: `.venv/Scripts/python.exe tools/verify.py quick --tests tests/test_first_run.py`
Expected: 전체 PASS. 실행 ID(`output/harness/<run-id>/summary.md`)를 기록해 둔다.
실패하면 수치를 임의로 늘리기 전에 해당 배치의 `_mapped()` 좌표를 출력해 원인을 확인한다. 특히 `(800, 380)`·`(400, 450)`·폴백 글꼴 조합의 높이 예산을 본다.

- [ ] **Step 7: 합성 배율 125%·150%**

Run:
```bash
QT_SCALE_FACTOR=1.25 .venv/Scripts/python.exe tools/verify.py quick --tests tests/test_first_run.py
QT_SCALE_FACTOR=1.5 .venv/Scripts/python.exe tools/verify.py quick --tests tests/test_first_run.py
```
Expected: 두 실행 모두 PASS. 실행 ID 기록. (커밋은 Task 3)

---

### Task 2: 정본 문서·계약 갱신

**Files:**
- Modify: `AGENTS.md` (‘반드시 보존할 계약’의 최초 크기 선택 줄, 글꼴 규칙 줄)
- Modify: `docs/UI_PATTERNS.md` (‘Settings UI’의 최초 크기 선택 항목)
- Modify: `docs/ARCHITECTURE.md` (모듈 표의 `ui_first_run.py` 행)
- Modify: `docs/TESTING.md` (최초 크기 선택 검사 문단)
- Modify: `app_fonts.py` (Pretendard 주석 한 줄)

**Interfaces:**
- Consumes: Task 1의 동작(문서는 그 동작만 서술한다).
- Produces: Task 3의 스테이징 스크립트가 찾는 줄 접두사 `- 최초 크기 선택(v3.8d 후속)`, `- 폰트·아이콘·이미지·SVG는`.

- [ ] **Step 1: `AGENTS.md` — 최초 크기 선택 계약 줄 교체**

기존 사용자 변경 4줄은 건드리지 않는다. 다음 한 줄을 찾아:

```text
- 최초 크기 선택(v3.8d 후속)은 건강 검사 `fresh`에서만 A안 기본/중간/크게를 표시한다. 확정 전 DB/salt/백업 미생성, X/Esc/종료 후 재표시, 확정 시 신규 DB의 기존 `calendar_scale` seed와 첫 백업/메인 반영을 유지한다. 기존 사용자·키 누락/잘못된 값·Factory Reset은 기존 경로를 유지하며 손상 데이터는 보호 오류로 차단한다. 별도 완료 키/우회 진입/재표시 예약은 없다. DB v17·Export v2·버전·Qt/lock·HWP worker 선분기를 유지한다. 상세 계약과 검증은 [UI 계약](docs/UI_PATTERNS.md), [아키텍처](docs/ARCHITECTURE.md), [작업 기록](docs/work/2026-10-04-first-run-size-setup-plan.md)을 따른다.
```

다음으로 교체한다.

```text
- 최초 크기 선택(v3.8d 후속)은 건강 검사 `fresh`에서만 데스크 뷰(2026-10-05 리디자인)로 기본/중간/크게를 표시한다. 미리보기는 `ui_main` 크기 규칙을 1920×1080 화면에 적용한 실제 비율 벡터 그림이고, 화면은 시스템 테마와 무관하게 밝게 그리며, 폭 580 미만·높이 370 미만은 위 크기 버튼과 아래 미리보기의 한 열 배치다. 확정 전 DB/salt/백업 미생성, X/Esc/종료 후 재표시, 확정 시 신규 DB의 기존 `calendar_scale` seed와 첫 백업/메인 반영을 유지한다. 기존 사용자·키 누락/잘못된 값·Factory Reset은 기존 경로를 유지하며 손상 데이터는 보호 오류로 차단한다. 별도 완료 키/우회 진입/재표시 예약은 없다. DB v17·Export v2·버전·Qt/lock·HWP worker 선분기를 유지한다. 상세 계약과 검증은 [UI 계약](docs/UI_PATTERNS.md), [아키텍처](docs/ARCHITECTURE.md), [작업 기록](docs/work/2026-10-04-first-run-size-setup-plan.md), [디자인 기록](docs/work/2026-10-05-first-run-desk-view-redesign.md)을 따른다.
```

- [ ] **Step 2: `AGENTS.md` — 글꼴 규칙 줄 교체**

```text
- 폰트·아이콘·이미지·SVG는 `app_paths.resource_root()`로 찾는다. 본문은 시스템 Malgun Gothic 기본, Pretendard는 D-Day 강조용이다. QSS 글꼴 크기는 정수 px만 쓴다.
```
→
```text
- 폰트·아이콘·이미지·SVG는 `app_paths.resource_root()`로 찾는다. 본문은 시스템 Malgun Gothic 기본, Pretendard는 D-Day 강조와 최초 설정의 제목·크기 이름·시작 버튼용이다. QSS 글꼴 크기는 정수 px만 쓴다.
```

- [ ] **Step 3: `docs/UI_PATTERNS.md` — 항목 교체**

`- **최초 크기 선택**: 신규 설치에만 캘린더 전에 A안 ...`으로 시작하는 한 줄 전체를 다음으로 교체한다.

```text
- **최초 크기 선택(데스크 뷰, 2026-10-05)**: 신규 설치에만 캘린더 전에 `FirstRunSizeDialog`를 표시한다. 기본 680×500 논리 px. 왼쪽 240px에 제목·안내 2줄·라디오 행 3개(이름+짧은 설명), 오른쪽에 모니터 미리보기를 둔다. 미리보기는 1920×1080 화면(작업 표시줄 48px)에 `ui_main`의 기본 크기 규칙(사이드바 숨김 기본 380×660, 중간 60%, 크게 −40px)과 오른쪽 아래 20px 위치를 스냅 전 좌표로 적용한 QPainter 벡터 그림(`preview_window_rect()`)이며, 선택하면 창이 240ms 동안 이동한다. 선택 설명 문구는 두지 않는다. 초기 선택은 기본이고 선택 표시는 메모리 상태에만 연동한다. ‘이 크기로 시작’(기본 버튼, Enter)으로 확정하고 X/Esc/종료는 DB 생성 없이 종료한다. 기존 사용자 업데이트·앱 내 Factory Reset에는 표시하지 않는다. 창 크기는 min(680, 작업 영역 폭−24)×min(500, 높이−24)다. 높이 470 미만은 여백·글자를 압축하고 두 번째 안내를 하단 버튼 왼쪽으로 옮긴다. 폭 580 미만 또는 높이 370 미만은 한 열 배치(위 기본/중간/크게 버튼, 아래 미리보기)를 쓴다. 미리보기 모니터는 남는 공간에 맞춰 최대 1배로 축소한다. 시스템 테마와 무관하게 항상 밝게 그린다. 제목·크기 이름·시작 버튼은 번들 Pretendard(미로드 시 맑은 고딕), 본문은 맑은 고딕이다. Tab/방향키/Space/Enter/Esc와 화면 변경 시 작업 영역 재배치를 지원한다. DB 접근·실제 메인 창 재사용·이미지 자산은 없다. 저장 오류는 기존 초기화 오류로 시작을 중단한다.
```

- [ ] **Step 4: `docs/ARCHITECTURE.md` — 모듈 표 행 교체**

```text
| `ui_first_run.py` | `fresh` 건강 검사 뒤 DB 생성 전 A안 크기 선택. DB 없는 벡터 미리보기·키보드 선택·취소·화면 작업 영역 대응 |
```
→
```text
| `ui_first_run.py` | `fresh` 건강 검사 뒤 DB 생성 전 데스크 뷰 크기 선택. `ui_main` 크기 규칙을 따른 DB 없는 벡터 미리보기(`preview_window_rect`)·키보드 선택·취소·작업 영역별 넓은/한 열 배치 |
```

- [ ] **Step 5: `docs/TESTING.md` — 검사 문단 앞부분 교체**

`최초 크기 선택은 \`tests/test_first_run.py\`에서 신규 선택·취소·기존/손상 분기, 세 크기의 DB/첫 백업/메인/재실행과 Export/Import, 키보드·작은 작업 영역을 검사한다.` 문장을 다음으로 교체한다(문단의 나머지 문장은 그대로).

```text
최초 크기 선택은 `tests/test_first_run.py`에서 신규 선택·취소·기존/손상 분기, 세 크기의 DB/첫 백업/메인/재실행과 Export/Import, 넓은·한 열 배치의 키보드와 작은 작업 영역 8종을 검사한다. 미리보기 크기 규칙은 `ui_main`의 크기 계산·모서리 좌표(5mm 스냅 이내)와 대조하고, 선택 후 실제 그림 위치 픽셀·애니메이션 중 재선택·다크 테마에서의 밝은 화면·Pretendard 부재 시 폴백 배치를 확인한다.
```

- [ ] **Step 6: `app_fonts.py` — 주석 한 줄**

```python
# 번들 UI 강조 폰트(Pretendard) — D-Day 위젯 등에서 사용. 앱 본문 폰트는 아님.
```
→
```python
# 번들 UI 강조 폰트(Pretendard) — D-Day 위젯·최초 설정 제목 등에서 사용. 앱 본문 폰트는 아님.
```

- [ ] **Step 7: 문서 확인**

Run:
```bash
git diff --check -- AGENTS.md docs/UI_PATTERNS.md docs/ARCHITECTURE.md docs/TESTING.md app_fonts.py
git diff AGENTS.md | grep -c '^+- '
```
Expected: 첫 명령 출력 없음. 두 번째 명령 `6` = 기존 사용자 변경 4줄(보안 검사 push 보류, v3.7a 기록, 자체 보안 검사, 보안 summary 보관) + 이번 교체 2줄.

---

### Task 3: 검증 기록과 로컬 커밋

**Files:**
- Create: `output/design/first-run-size-redesign-20261005/capture_qt.py` (로컬, Git 제외)
- Create: `output/design/first-run-size-redesign-20261005/stage_changes.py` (로컬, Git 제외)
- Modify: `docs/work/2026-10-05-first-run-desk-view-redesign.md`, `AGENTS.md`(‘기록 관리’ 첫 항목 추가)

**Interfaces:**
- Consumes: Task 1의 `FirstRunSizeDialog`·`_DeskPreview._animation`·`fit_to_available_geometry`, Task 2의 AGENTS 줄 접두사.
- Produces: 로컬 커밋 1개.

- [ ] **Step 1: 소스 프로세스 시작 검사(취소→재표시·확정→메인·기존 실행 생략)**

기존 도구를 그대로 쓴다(제품 우회 없음, 합성 데이터).
Run: `.venv/Scripts/python.exe output/design/first-run-size-setup/probe_startup.py "$(date +%Y%m%d-%H%M%S)-desk-view-source-startup"`
Expected: 마지막 줄 JSON에 `"cancel"`, `"accept"`, `"existing"` 모두 `"status": "passed"`, 최상위 `"status": "passed"`.

- [ ] **Step 2: Qt 캡처 스크립트 작성**

`output/design/first-run-size-redesign-20261005/capture_qt.py`:

```python
"""데스크 뷰 Qt 캡처: 합성 작업 영역 6개 × 크기 3개. 사용: python capture_qt.py <run-id>"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
destination = ROOT / "output" / "harness" / sys.argv[1]
destination.mkdir(parents=True, exist_ok=False)
os.environ["LOCALAPPDATA"] = str(destination / "appdata")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from app_fonts import apply_app_font, load_ui_fonts
from ui_first_run import FirstRunSizeDialog

app = QApplication([])
apply_app_font("Malgun Gothic", app)
load_ui_fonts()
setTheme(Theme.DARK)  # 다크 모드에서도 밝게 그려지는지 함께 본다.
AREAS = {"normal": (1000, 900), "short": (800, 400), "narrow540": (540, 500),
         "narrow400": (400, 600), "narrow320": (320, 600), "narrow-short": (400, 450)}
for name, (width, height) in AREAS.items():
    dialog = FirstRunSizeDialog()
    dialog.show()
    app.processEvents()
    dialog.windowHandle().screenChanged.disconnect(dialog._screen_changed)
    dialog.fit_to_available_geometry(QRect(0, 0, width, height))
    for scale in ("compact", "medium", "large"):
        dialog._select(scale)
        dialog.preview._animation.setCurrentTime(dialog.preview._animation.duration())
        app.processEvents()
        dialog.grab().save(str(destination / f"{name}-{scale}.png"))
    dialog.close()
    dialog.deleteLater()
    app.processEvents()
print(destination)
```

- [ ] **Step 3: 캡처 실행과 직접 확인**

Run:
```bash
STAMP=$(date +%Y%m%d-%H%M%S)
.venv/Scripts/python.exe output/design/first-run-size-redesign-20261005/capture_qt.py "$STAMP-desk-view-qt-100"
QT_SCALE_FACTOR=1.25 .venv/Scripts/python.exe output/design/first-run-size-redesign-20261005/capture_qt.py "$STAMP-desk-view-qt-125"
QT_SCALE_FACTOR=1.5 .venv/Scripts/python.exe output/design/first-run-size-redesign-20261005/capture_qt.py "$STAMP-desk-view-qt-150"
```
Expected: 각 폴더에 PNG 18개. 최소 `normal-medium`, `short-large`, `narrow320-compact`, `narrow-short-large`를 세 배율 모두 열어 확인한다: 흰 바탕, 제목 Pretendard, 잘림·겹침 없음, 미리보기 창이 오른쪽 아래(크게는 거의 전체), 한 열 배치의 버튼 3개가 위에 있음. 시안 HTML(`desk-view-layouts.html`)과 다르게 보이는 점은 작업 기록에 적는다.

- [ ] **Step 4: 작업 기록·AGENTS 기록 갱신**

`docs/work/2026-10-05-first-run-desk-view-redesign.md`의 상태를 `완료 — 구현·검증·로컬 커밋`으로 바꾸고, 완료 조건 체크, ‘검증 증거’ 표에 Task 1 Step 6·7, Task 3 Step 1·3의 **실제 실행 ID와 통과 수**를 적는다. 실패했던 실행이 있으면 지우지 말고 원인과 함께 남긴다.

`AGENTS.md`의 `## 기록 관리` 바로 아래(기존 첫 항목 `- 2026-10-04 최초 크기 선택 후속…` 위)에 한 줄을 추가한다. `<…>`는 실제 값으로 채운다.

```text
- 2026-10-05 최초 설정 디자인 후속(데스크 뷰)은 **v3.8d를 유지**한다. 최초 크기 선택 화면을 시안 1 데스크 뷰(실제 비율 미리보기·항상 밝게·Pretendard 제목·한 열 배치)로 교체했고 시작 흐름·DB v17·Export v2·salt·설정 키는 바꾸지 않았다. `tests/test_first_run.py` 100% <N>개(`<run-id>`), 125%/150% 각 <N>개(`<run-id>`, `<run-id>`), 소스 프로세스 3개(`<run-id>`)를 통과했다. EXE는 재빌드하지 않았으며 아래 10월 4일 EXE에는 이 디자인이 없다. 상세는 [디자인 기록](docs/work/2026-10-05-first-run-desk-view-redesign.md)을 따른다.
```

- [ ] **Step 5: 부분 스테이징 스크립트 작성**

`output/design/first-run-size-redesign-20261005/stage_changes.py`:

```python
"""AGENTS의 기존 사용자 변경을 제외하고 이번 데스크 뷰 항목만 index에 올린다."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def git(*args, **kwargs):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, **kwargs).stdout


def only_line(text, prefix):
    lines = [line for line in text.splitlines() if line.startswith(prefix)]
    assert len(lines) == 1, prefix
    return lines[0]


base = git("show", "HEAD:AGENTS.md").decode("utf-8")
working = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
for prefix in ("- 최초 크기 선택(v3.8d 후속)", "- 폰트·아이콘·이미지·SVG는"):
    old, new = only_line(base, prefix), only_line(working, prefix)
    assert old != new, prefix
    base = base.replace(old, new, 1)
record_prefix = "- 2026-10-05 최초 설정 디자인 후속"
record = only_line(working, record_prefix)
assert record_prefix not in base
heading = "## 기록 관리\n"
assert heading + "\n" in base
base = base.replace(heading + "\n", heading + "\n" + record + "\n\n", 1)
blob = git("hash-object", "-w", "--stdin", input=base.encode("utf-8")).decode().strip()
git("update-index", "--cacheinfo", "100644", blob, "AGENTS.md")
git("add", "--", "ui_first_run.py", "tests/test_first_run.py", "app_fonts.py",
    "docs/UI_PATTERNS.md", "docs/ARCHITECTURE.md", "docs/TESTING.md",
    "docs/work/2026-10-05-first-run-desk-view-redesign.md",
    "docs/superpowers/plans/2026-10-05-first-run-desk-view-redesign.md")
print(git("diff", "--cached", "--stat").decode("utf-8"))
```

- [ ] **Step 6: 스테이징과 확인**

Run:
```bash
.venv/Scripts/python.exe output/design/first-run-size-redesign-20261005/stage_changes.py
git diff --cached AGENTS.md
git diff AGENTS.md | grep -c '^+- '
git status --short
```
Expected: cached diff의 AGENTS.md 변경은 3곳(계약 줄 교체·글꼴 줄 교체·기록 줄 추가)뿐. 작업 트리에 남은(스테이징 안 된) AGENTS.md 변경은 기존 사용자 4줄뿐(`grep -c` 결과 `4`). `docs/RELEASE_HISTORY.md`와 기존 미추적 기록 5개는 스테이징되지 않음.

- [ ] **Step 7: 커밋**

```bash
git commit -F - <<'EOF'
feat: 최초 실행 크기 선택 데스크 뷰 리디자인

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git log --oneline -1 && git status --short
```
Expected: 새 커밋 1개. push하지 않는다.

---

### Task 4 (선택, 사용자 승인 후에만): 새 EXE 빌드·격리 검증·배치

사용자가 EXE 갱신을 요청한 경우에만 진행한다. 10월 4일 절차와 같다.

- [ ] **Step 1:** PowerShell에서 `.\.venv\Scripts\python.exe tools/verify.py release` (Git Bash 금지 — mingw64 OpenSSL DLL 혼입 사례). 실패 시 빌드 산출물을 쓰지 않는다.
- [ ] **Step 2:** release의 `artifact-verification/summary.md`에서 포함 모듈에 `ui_first_run`이 현재 소스와 일치, Qt DLL 4개 6.11.2.0, BINARY 원본 경로에 Git/mingw 없음을 확인한다.
- [ ] **Step 3:** 기존 `dist/기후노트_v3.8d.exe`를 `output/harness/<release-id>/previous/`로 보존한 뒤 새 EXE를 같은 볼륨 원자 교체로 배치하고 SHA-256을 대조한다. 실행 중인 EXE는 강제 종료하지 않는다.
- [ ] **Step 4:** README의 최신 EXE 크기·해시·실행 ID와 작업 기록·AGENTS 기록 줄을 갱신하고 문서만 별도 커밋한다(`docs: 데스크 뷰 EXE 검증과 배치 기록` + Co-Authored-By).
