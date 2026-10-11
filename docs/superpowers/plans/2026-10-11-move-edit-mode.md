# 캘린더 위치 편집 모드(J안)·고른 날 회색 채움 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 머리줄 이동 토글(켜짐 점·꺼짐 사선)을 "평소 고정 → 화살표 단추로 위치 편집 → 머리줄 끌기 → 완료" 흐름(J안)으로 바꾸고, 중간·크게 모드의 고른 날 표시를 테두리에서 예전의 연한 회색 채움으로 되돌린다.

**Architecture:** 편집 상태는 `MainCalendarWindow._calendar_move_editing`(메모리 전용) 하나다. 이동 단추는 편집을 시작만 하고, 편집 중에는 머리줄 오른쪽 묶음이 '완료' 알약으로 바뀌며, 컨테이너 위에 마우스가 통과하는 덧그림 위젯(`CalendarMoveEditOverlay`)이 점선 테두리와 안내 띠를 그린다. 끌기·저장 로직(`eventFilter`, `_finish_calendar_drag`)은 그대로 두고 허용 조건만 바꾼다.

**Tech Stack:** Python 3.13, PySide6 6.11.2, qfluentwidgets 1.11.1, pytest-qt, `tools/verify.py`.

**Spec:** J안 시안 `output/design/move-button-20261011/move-button-concepts-2.html`(J 행) + 실제 크기 확정 시안 `output/design/move-button-20261011/j-final.html` + 아래 "설계 결정". 2026-10-11 사용자: "J가 괜찮은 것 같아", "네 방향이라기보다 '십자 화살표'가 나을 것 같아", 점선 색은 파랑/노랑 비교(`j-final.html` "점선 색 비교") 후 파랑 두 톤. 회색 채움은 2026-10-10 "제안대로 하는게 낫겠어".

## 설계 결정

- **D1 평소 고정.** 앱은 항상 고정 상태로 시작한다. 예전 `calendar_move_enabled` 값("1"/"0")은 읽지 않고, 행을 지우거나 새로 쓰지도 않는다(Export에도 그대로 남음). 편집 상태는 저장하지 않는다.
- **D2 이동 단추.** 흰 십자 화살표 하나(점·사선 없음), 체크 단추가 아니다. 잠금 중에는 흐리게(불투명도 0.45) 비활성. 툴팁·접근 설명 "캘린더 옮기기 · 누른 뒤 머리줄을 끌어 옮깁니다", 접근 이름 "캘린더 옮기기".
- **D3 '완료' 자리.** 편집 중에는 검색·이동·⋮을 잠시 숨기고 오른쪽 104px 묶음의 오른쪽 끝에 '완료' 알약(52×32, '오늘'과 같은 크기, 13px 굵게, 테두리 `#93C5FD`, 바탕 `rgba(147,197,253,40)`)을 둔다. 380px 머리줄은 좌 104 + 가운데 148 + 우 104 = 356px(여백 24px 제외 전부)라 세 아이콘 옆에 52px를 더 둘 수 없다.
- **D4 점선(색 확정 2026-10-11).** 창 바깥은 바탕화면이라 창 안쪽 가장자리에 2px 점선(6px 선·4px 틈, 모서리 11px)을 그린다. 색은 바탕에 따라 **파랑 두 톤**이다. 남색 머리줄 위는 `#93C5FD`('완료' 테두리와 같은 연한 파랑), 그 밖(흰 칸·회색 바로가기 열·안내 띠·크게 모드 오른쪽 열)은 `#2563EB`(앱 강조색). 같은 점선 경로를 머리줄 영역과 나머지로 잘라 두 번 그려 선·틈 위치가 이어진다.
  - 대비(선·테두리는 3:1 이상, WCAG 1.4.11) — 남색 머리줄 / 흰 칸 / 회색 바로가기 열 / 안내 띠: 파랑 두 톤 **7.8 / 5.2 / 4.7 / 4.6**, 파랑 한 색 `#3B82F6`(이전 계획) 3.8 / 3.7 / 3.4 / 3.3, 노랑 한 색 `#FBBF24` 8.5 / 1.7 / 1.5 / 1.5, 노랑 두 톤 `#FBBF24`+`#D97706` 8.5 / 3.2 / 2.9 / 2.9.
  - 노랑을 쓰지 않는 이유: 흰 바탕에서 거의 안 보인다. 이 머리줄의 키보드 포커스 테두리가 이미 `#FBBF24`라 '편집 중'과 '포커스'가 구분되지 않는다. 흰 쪽을 진하게 하면 주황(경고)으로 읽힌다. 파랑은 Windows·문서 편집기의 선택/편집 틀 관례와 같고 안내 띠·'완료' 테두리와 한 계열이다.
- **D5 안내 띠.** 머리줄 바로 아래 28px 띠(`#EAF2FF` 바탕, `#1D4ED8` 굵은 12px 글자) "머리줄을 끌어 원하는 곳에 두고 '완료'를 누르세요". 달력 칸을 밀지 않도록 겹쳐 그리고(요일 줄을 잠시 가림) 마우스는 아래로 통과한다. 폭이 모자라면 오른쪽 말줄임.
- **D6 끝내는 방법.** '완료', Esc, 다른 곳 클릭(창 비활성), PIN 잠금, 트레이 숨김, 크기 변경, 가져오기·초기화. 모니터 변경은 편집을 유지하고 진행 중 끌기만 취소한다. 위치는 지금처럼 끌기를 놓을 때 저장하며 '완료'는 아무것도 저장하지 않는다.
- **D7 고정 중 끌기 안내.** 고정 상태에서 머리줄을 끌면(시작 거리 이상) 실행마다 한 번 InfoBar(3초, 제목 "캘린더 위치 고정" 위·본문 "옮기려면 머리줄의 십자 화살표 단추를 누르세요." 아래로 쌓아 380px 안에 들어가게)를 띄운다. 업데이트 뒤 예전처럼 끌던 사용자를 위한 것이다.
- **D8 키보드.** Tab으로 이동 단추 → Space/Enter로 시작하면 포커스가 '완료'로, '완료'에서 Space/Enter로 끝내면 이동 단추로 돌아온다. 마우스 클릭은 일정 입력 포커스를 빼앗지 않는다(두 단추 모두 `Qt.TabFocus`).
- **D9 고른 날(중간·크게).** 칸 전체 연한 회색 `rgba(1,41,95,20)`, 테두리 없음. 오늘은 남색 숫자 원 유지(오늘을 고르면 회색 칸 + 남색 원). 기본 크기는 그대로.

## Global Constraints

- DB v17·Export v2·salt·설정 키 불변. 새 설정 키 없음. 기존 `calendar_move_enabled` 행은 읽지 않고 보존한다.
- 머리줄 계약: 아이콘 단추 32px·간격 4px·좌우 묶음 104px·연월 묶음 148px, 기본 380px에서 연월 가운데(오차 1px).
- 화면 문구는 한국어. 이 단추는 화면·문서에서 '십자 화살표'로 부른다('네 방향 화살표'라고 쓰지 않음). QSS 글꼴 크기는 정수 px.
- 색: 남색 `#01295F`, 점선 `#93C5FD`(남색 머리줄 위)·`#2563EB`(그 밖), 안내 띠 `#EAF2FF`/`#1D4ED8`, '완료' 테두리 `#93C5FD`. 노랑(`#FBBF24`)은 키보드 포커스 표시 전용으로 남긴다.
- 시험·캡처는 `app_dir` 합성 데이터 폴더에서만. 실사용 AppData·DB·salt·실행 중인 앱을 쓰지 않는다.
- 다른 작업(화면 글자 따기 진단: `tools/screen_text_lab/`, `tests/test_screen_text_lab*.py`, `docs/SCREEN_TEXT*.md`, `docs/TESTING.md`의 진단 절, 미추적 `docs/work/*`)은 건드리거나 커밋하지 않는다. 사용자의 `AGENTS.md` 미커밋 4줄과 `docs/RELEASE_HISTORY.md`도 커밋에 넣지 않는다(`AGENTS.md`는 HEAD 사본에 같은 치환만 한 blob을 올림).
- 커밋은 기능 브랜치 `feat/move-edit-mode`에서. main 병합·빌드·push는 사용자 지시 때만. push는 `git push origin main`처럼 브랜치 명시, `--all`/`--mirror` 금지, `archive/local-v3.5` push 금지. 빌드·release는 PowerShell.
- 시험 실행: `.\.venv\Scripts\python.exe -m pytest <파일> -q`(빠른 확인), 묶음 확인은 `.\.venv\Scripts\python.exe tools/verify.py quick --tests <파일들>`, 배율은 `$env:QT_SCALE_FACTOR="1.25"`/`"1.5"`.

## Review Focus

- 125/150% 배율에서 '완료' 글자가 52×32 알약 안에서 잘리지 않고, 편집 중에도 연월이 머리줄 가운데에 있는가 → Task 2 `test_header_geometry_in_both_states`.
- 점선이 남색 머리줄·흰 칸·회색 바로가기 열(중간·크게)·크게 모드 오른쪽 열 어디에 놓여도 보이는가(머리줄 위는 연한 파랑, 그 밖은 진한 파랑으로 바뀌는가) → Task 3 `test_outline_color_follows_background`.
- 마우스를 누른 채(끌기 도중) 완료·Esc·잠금 등으로 편집이 끝나면 위치를 저장하지 않고 끌기가 취소되는가 → Task 4 `test_edit_mode_ends_and_drag_cancels`.
- 키보드로 이동 단추를 쓸 때 단추가 숨겨져도 포커스가 사라지지 않는가('완료'로 갔다가 이동 단추로 복귀) → Task 2 `test_keyboard_enters_and_leaves_edit_mode`.
- 예전 `calendar_move_enabled="1"` 사용자가 업데이트해도 고정으로 시작하고, 그 행이 DB와 Export에 그대로 남는가 → Task 2 `test_starts_fixed_and_keeps_legacy_setting_row`.

## 파일 구조

- 수정 `ui_main.py`
  - `CalendarDayButton._set_style`(expanded 분기) — Task 1
  - `_EnterClickButton`(새, Enter도 click), `CalendarMoveButton`(그림 정리), `CalendarMoveDoneButton`(새) — Task 2
  - `CalendarMoveEditOverlay`(새, 점선·안내 띠) — Task 3
  - `MainCalendarWindow`: `__init__` 상태, `_build_ui`/`_build_top_bar`, `_calendar_drag_allowed`, `_update_calendar_move_control`, `_start_calendar_move_edit`/`_finish_calendar_move_edit`(새, `_on_calendar_move_clicked` 대체), `keyPressEvent`(새), `eventFilter`, `_note_fixed_header_drag`(새), `_lock`/`_minimize_to_tray`/`_apply_calendar_scale`/`_discard_data_widgets`/`_on_import_complete` — Task 2~4
- 수정 `database.py` — `DEFAULT_CALENDAR_MOVE_ENABLED` 삭제, `SETTING_CALENDAR_MOVE_ENABLED` 주석을 "읽지 않음·보존"으로 (Task 2)
- 시험: `tests/test_ui_calendar_cells.py`, `tests/test_ui.py`(Task 1), `tests/test_ui_calendar_move.py`(전면 교체, Task 2~4), `tests/test_ui_calendar_drag.py`, `tests/test_ui_kvm_position.py`(Task 2)
- 문서: `docs/UI_PATTERNS.md`, `docs/TESTING.md`, `README_detail.md`, `AGENTS.md`, `docs/work/2026-10-11-move-edit-mode.md`(새), 보고서 `output/design/design-audit-20261009/design-audit.html`(gitignore) — Task 5

---

### Task 1: 중간·크게 고른 날 연한 회색 채움 복원

**Files:**
- Modify: `ui_main.py` `CalendarDayButton._set_style` expanded 분기(지금 642~653행)
- Test: `tests/test_ui_calendar_cells.py`, `tests/test_ui.py`(1488~1501행 `test_calendar_day_button_selected_style_is_scoped_to_cell`)

**Interfaces:**
- Consumes: 없음
- Produces: 없음(스타일만)

- [ ] **Step 0: 준비** — 다른 작업이 이 작업 폴더를 쓰는지 확인하고(`git status --short`, 진단 도구 실행 여부) 브랜치를 만든다.

```powershell
git status --short
git switch -c feat/move-edit-mode
```

- [ ] **Step 1: 실패하는 시험 쓰기** — `tests/test_ui_calendar_cells.py`의 `test_expanded_selected_day_uses_border_not_fill`을 지우고 아래로 바꾼다. 맨 위 docstring의 "고른 날 테두리"도 "고른 날 연한 회색"으로.

```python
LIGHT_FILL = (235, 238, 242)  # rgba(1,41,95,20)를 흰 칸 바탕에 얹은 색


def _near(color, rgb, tol=3):
    return all(abs(a - b) <= tol for a, b in zip((color.red(), color.green(), color.blue()), rgb))


@pytest.mark.parametrize("scale", ["medium", "large"])
def test_expanded_selected_day_uses_light_fill_not_border(qtbot, scale):
    win = _window(qtbot, scale)
    today = date.today()
    other = today.replace(day=1 if today.day != 1 else 2).isoformat()
    win._on_date_selected(other)
    QApplication.processEvents()
    cell = win._day_cells[other]
    assert _pixel(win, cell, QPoint(cell.width() // 2, 1)).name() != NAVY  # 테두리 없음
    assert _near(_pixel(win, cell, QPoint(cell.width() - 6, cell.height() // 2)), LIGHT_FILL)


@pytest.mark.parametrize("scale", ["medium", "large"])
def test_expanded_selected_today_keeps_circle_on_light_fill(qtbot, scale):
    win = _window(qtbot, scale)
    key = date.today().isoformat()
    win._on_date_selected(key)
    QApplication.processEvents()
    cell = win._day_cells[key]
    label = cell.day_label
    assert _pixel(win, label, QPoint(3, label.height() // 2)).name() == NAVY  # 남색 숫자 원 유지
    assert _near(_pixel(win, cell, QPoint(cell.width() - 4, cell.height() - 4)), LIGHT_FILL)
```

`tests/test_ui.py`의 두 줄(주석 + `border: 2px` 단언)을 바꾼다.

```python
    # 중간·크게 칸도 고른 날을 연한 회색으로 채운다(2026-10-11, 15번 테두리를 되돌림).
    assert "background: rgba(1,41,95,20)" in cell.styleSheet()
    assert "border:" not in cell.styleSheet()
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_calendar_cells.py tests/test_ui.py::test_calendar_day_button_selected_style_is_scoped_to_cell -q`
Expected: 새 시험 4개(2개×2배율)와 `test_ui.py` 1개 FAIL(가운데 픽셀이 흰색, `border: 2px` 있음). 나머지 PASS.

- [ ] **Step 3: 구현** — expanded 분기의 주석과 두 줄만 바꾼다.

```python
        if self._mode == "expanded":
            # 중간·크게: 오늘은 숫자 뒤 남색 원, 고른 날은 칸 전체를 연한 회색으로 채운다
            # (2026-10-11 사용자 요청으로 15번의 테두리를 예전 채움으로 되돌림).
            if selected:
                bg_style += "background: rgba(1,41,95,20);"
```

- [ ] **Step 4: 통과 확인**

Run: Step 2와 같은 명령
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```powershell
git add ui_main.py tests/test_ui_calendar_cells.py tests/test_ui.py
git commit -m "fix: 중간·크게 고른 날을 테두리 대신 연한 회색으로 다시 채움"
```

---

### Task 2: 평소 고정 + 이동 단추로 편집 시작 + '완료'/Esc로 끝내기

**Files:**
- Modify: `ui_main.py` `CalendarMoveButton`(467~530행), `MainCalendarWindow.__init__`(1340~1347행), `_build_top_bar`(1994~2017행), `_calendar_drag_allowed`/`_update_calendar_move_control`/`_on_calendar_move_clicked`(3999~4030행), `_on_import_complete`(3482~3486행), 새 `keyPressEvent`
- Modify: `database.py` 47·58행
- Test: `tests/test_ui_calendar_move.py`(전면 교체), `tests/test_ui_calendar_drag.py`, `tests/test_ui_kvm_position.py`

**Interfaces:**
- Consumes: 기존 `_reset_calendar_drag()`, `_calendar_drag_targets`, `eventFilter` 끌기 로직
- Produces (Task 3·4가 씀):
  - `MainCalendarWindow._calendar_move_editing: bool`
  - `MainCalendarWindow._start_calendar_move_edit() -> None` (잠금·숨김·이미 편집 중이면 아무것도 안 함)
  - `MainCalendarWindow._finish_calendar_move_edit() -> None` (언제 불러도 안전: 편집 끝 + 끌기 취소 + 단추 갱신)
  - `MainCalendarWindow._update_calendar_move_control() -> None`
  - `MainCalendarWindow.calendar_move_done_button: CalendarMoveDoneButton`
  - `MainCalendarWindow._header_search_btn` (기존 지역 변수 `search_btn`을 속성으로)

- [ ] **Step 1: 실패하는 시험 쓰기** — `tests/test_ui_calendar_move.py`를 아래로 통째로 바꾼다(예전 ON/OFF 저장·점 시험은 J안과 맞지 않아 삭제).

```python
"""캘린더 위치 편집(2026-10-11 J안): 평소 고정, 화살표 단추로 편집 → 머리줄 끌기 → 완료. 합성 데이터로만 검증한다."""
import json
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

import database as db
import security
import ui_main
from ui_main import MainCalendarWindow


@pytest.fixture(autouse=True)
def isolated_move_ui(app_dir, monkeypatch):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kwargs: None)


def window(qtbot, scale="compact"):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win.activateWindow()
    qtbot.waitExposed(win)
    qtbot.waitUntil(win.isActiveWindow)
    return win


def drag_header(win, delta=QPoint(40, 25)):
    start = win.month_label.rect().center()
    QTest.mousePress(win.month_label, Qt.LeftButton, pos=start)
    QTest.mouseMove(win.month_label, start + delta, delay=20)
    QTest.mouseRelease(win.month_label, Qt.LeftButton, pos=start + delta)


def controls(win):
    return {
        "search": win.findChild(QWidget, "headerSearchButton"),
        "move": win.calendar_move_button,
        "done": win.calendar_move_done_button,
        "more": win._more_btn,
    }


@pytest.mark.parametrize("legacy", [None, "1", "0"], ids=["no-row", "legacy-on", "legacy-off"])
def test_starts_fixed_and_keeps_legacy_setting_row(qtbot, legacy):
    if legacy is not None:
        db.save_setting(db.SETTING_CALENDAR_MOVE_ENABLED, legacy)
    win = window(qtbot)
    position = win.pos()
    drag_header(win)
    assert win.pos() == position
    assert not win._calendar_move_editing
    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "corner"
    # 예전 설정 행은 읽지 않지만 지우거나 새로 만들지도 않는다(Export에도 그대로).
    assert db.get_setting(db.SETTING_CALENDAR_MOVE_ENABLED, "missing") == (legacy or "missing")
    settings = json.loads(db.export_all_data())["settings"]
    assert settings.get(db.SETTING_CALENDAR_MOVE_ENABLED) == legacy


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_move_button_edit_drag_and_done_in_every_size(qtbot, scale):
    win = window(qtbot, scale)
    c = controls(win)
    assert c["move"].isVisible() and not c["done"].isVisible()
    qtbot.mouseClick(c["move"], Qt.LeftButton)
    assert win._calendar_move_editing
    assert c["done"].isVisible()
    assert not any(c[k].isVisible() for k in ("search", "move", "more"))
    drag_header(win)
    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "free"
    assert int(db.get_setting(db.SETTING_CALENDAR_X)) == win.x()
    assert int(db.get_setting(db.SETTING_CALENDAR_Y)) == win.y()
    assert win.screen().availableGeometry().contains(win.geometry())
    assert win._calendar_move_editing  # 한 번 끌어도 '완료' 전까지 편집 상태
    qtbot.mouseClick(c["done"], Qt.LeftButton)
    assert not win._calendar_move_editing
    assert all(c[k].isVisible() for k in ("search", "move", "more")) and not c["done"].isVisible()
    position = win.pos()
    drag_header(win)
    assert win.pos() == position


def test_edit_mode_keeps_input_focus_and_writes_nothing(qtbot):
    note = db.create_sticky_note()
    db.update_sticky_note(note, content="<p>기존 메모</p>")
    win = window(qtbot)
    with db._connection() as conn:
        before_rows = [tuple(row) for row in conn.execute("SELECT * FROM sticky_notes")]
        before_settings = dict(conn.execute("SELECT key,value FROM app_settings"))
    salt = security.SALT_FILE.read_bytes()
    win.schedule_input.setText("📌 아직 입력 중")
    win.schedule_input.setFocus()
    qtbot.waitUntil(win.schedule_input.hasFocus)
    position = win.pos()
    qtbot.mouseClick(win.calendar_move_button, Qt.LeftButton)
    qtbot.mouseClick(win.calendar_move_done_button, Qt.LeftButton)
    assert win.pos() == position
    assert win.schedule_input.text() == "📌 아직 입력 중"
    assert win.focusWidget() is win.schedule_input
    with db._connection() as conn:
        assert [tuple(row) for row in conn.execute("SELECT * FROM sticky_notes")] == before_rows
        assert dict(conn.execute("SELECT key,value FROM app_settings")) == before_settings
    assert security.SALT_FILE.read_bytes() == salt


def test_keyboard_enters_and_leaves_edit_mode(qtbot):
    win = window(qtbot)
    search = win.findChild(QWidget, "headerSearchButton")
    search.setFocus(Qt.TabFocusReason)
    qtbot.waitUntil(search.hasFocus)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
    qtbot.waitUntil(lambda: QApplication.focusWidget() is win.calendar_move_button)
    for key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
        qtbot.keyClick(QApplication.focusWidget(), key)
        assert win._calendar_move_editing
        assert win.focusWidget() is win.calendar_move_done_button
        qtbot.keyClick(QApplication.focusWidget(), key)
        assert not win._calendar_move_editing
        assert win.focusWidget() is win.calendar_move_button
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Space)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)  # '완료'에 포커스가 있어도 Esc는 창까지 올라온다
    assert not win._calendar_move_editing
    assert win.focusWidget() is win.calendar_move_button


def test_escape_on_window_ends_edit_mode(qtbot):
    win = window(qtbot)
    win.calendar_move_button.click()
    qtbot.keyClick(win, Qt.Key_Escape)
    assert not win._calendar_move_editing


def test_move_button_texts_and_plain_arrows(qtbot):
    win = window(qtbot)
    button = win.calendar_move_button
    assert not button.isCheckable()
    assert button.accessibleName() == "캘린더 옮기기"
    assert button.toolTip() == "캘린더 옮기기 · 누른 뒤 머리줄을 끌어 옮깁니다"
    assert win.calendar_move_done_button.text() == "완료"
    assert win.calendar_move_done_button.toolTip() == "위치 편집 끝내기 (Esc)"
    header = win.findChild(QWidget, "headerSection")
    origin = button.mapTo(header, QPoint())
    image = header.grab().toImage()
    ratio = image.devicePixelRatio()

    def pixel(x, y):
        return image.pixelColor(int((origin.x() + x) * ratio), int((origin.y() + y) * ratio))

    header_bg = pixel(-2, 6).name()  # 검색 단추와의 4px 간격은 머리줄 바탕
    assert pixel(6, 6).name() == header_bg       # 채운 상자 없음
    assert pixel(16, 29).name() == header_bg     # 예전 켜짐 점 없음
    assert pixel(10, 22).name() == header_bg     # 예전 꺼짐 사선 자리(8,24)-(24,8) 위, 화살표와 겹치지 않는 점
    assert pixel(16, 16).lightness() > 200       # 가운데 흰 화살표 교차점


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_header_geometry_in_both_states(qtbot, scale):
    win = window(qtbot, scale)
    qtbot.wait(30)
    header = win.findChild(QWidget, "headerSection")
    right = win.findChild(QWidget, "headerRightGroup")

    def rect(w):
        return QRect(w.mapTo(header, QPoint()), w.size())

    def month_centered():
        center = win.month_label.mapTo(header, QPoint()).x() + win.month_label.width() / 2
        return abs(center - header.width() / 2) <= 1

    c = controls(win)
    rects = [rect(c[k]) for k in ("search", "move", "more")]
    assert all(header.rect().contains(r) for r in rects)
    assert all(rects[i + 1].left() - rects[i].right() - 1 == 4 for i in range(2))
    assert month_centered()
    assert win.next_btn.mapTo(header, QPoint()).x() + win.next_btn.width() <= rects[0].left()
    if scale == "compact":
        assert win.width() == 380
    win.calendar_move_button.click()
    QApplication.processEvents()
    done = rect(c["done"])
    assert c["done"].size().width() == 52 and c["done"].size().height() == 32
    assert rect(right).contains(done) and done.right() == rect(right).right()
    assert c["done"].fontMetrics().horizontalAdvance("완료") <= 52 - 2 * 8 - 2  # 125/150%에서도 안 잘림
    assert month_centered()
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        target = Path(appdata).parent
        assert win.grab().save(str(target / f"calendar-move-edit-{scale}.png"))
```

`tests/test_ui_calendar_drag.py`: 머리줄 끌기를 기대하는 다섯 시험(`test_header_drag_moves_and_persists_free_position`, `test_header_drag_moves_on_target_screen_5mm_grid`, `test_real_qt_mouse_drag_still_finishes_before_ungrab`, `test_header_click_without_drag_keeps_corner_mode`, `test_small_pointer_jitter_does_not_start_calendar_drag`)에서 `MainCalendarWindow()`와 `qtbot.addWidget(win)` 바로 다음 줄에 넣는다.

```python
    win._start_calendar_move_edit()  # J안: 평소 고정, 편집 중에만 머리줄 끌기
```

같은 파일의 `test_header_drag_is_disabled_when_movement_is_off`는 이름을 `test_header_drag_is_disabled_when_not_editing`으로 바꾸고 예전 설정 줄을 아래로 바꾼다(예전 '이동 허용' 값이 있어도 고정).

```python
    db.save_setting(db.SETTING_CALENDAR_MOVE_ENABLED, "1")  # 예전 값은 읽지 않는다
```

`tests/test_ui_kvm_position.py` 92~97행:

```python
@pytest.mark.parametrize("movement_enabled", [True, False], ids=["editing", "fixed"])
def test_free_placement_survives_disconnect_and_reconnect(
        app_dir, qtbot, monkeypatch, scale, movement_enabled):
    win, topology = _setup(scale, "free", qtbot, monkeypatch)
    win._calendar_move_editing = movement_enabled
```

(`db.save_setting(db.SETTING_CALENDAR_MOVE_ENABLED, ...)` 줄은 지운다.)

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_calendar_move.py tests/test_ui_calendar_drag.py tests/test_ui_kvm_position.py -q`
Expected: FAIL — `AttributeError: ... 'calendar_move_done_button'` / `'_calendar_move_editing'` / `'_start_calendar_move_edit'`, `test_starts_fixed...`는 끌기가 창을 옮겨서 FAIL.

- [ ] **Step 3: 구현 — 단추 두 개** (`ui_main.py`, `CalendarMoveButton` 자리 전체를 교체)

```python
class _EnterClickButton(QPushButton):
    """Enter/Return도 Space처럼 한 번 click한다(머리줄 이동·완료 단추 공통)."""

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                self.click()
            event.accept()
        else:
            super().keyPressEvent(event)


class CalendarMoveButton(_EnterClickButton):
    """위치 편집을 시작하는 흰 십자 화살표(2026-10-11 J안). 켜짐/꺼짐 상태는 그리지 않는다.

    평소 캘린더는 고정이고, 누르면 위치 편집이 되어 머리줄을 끌 수 있다. 글리프 폰트에 의존하지 않는다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("headerMoveButton")
        self.setFixedSize(32, 32)
        # 마우스 클릭은 진행 중인 일정 입력의 포커스를 빼앗지 않는다.
        self.setFocusPolicy(Qt.TabFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("캘린더 옮기기")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.45)
        frame = QRectF(0.5, 0.5, 31, 31)
        if self.underMouse() or self.isDown():
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 32))
            painter.drawRoundedRect(frame, 8, 8)
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#FBBF24"), 1))
            painter.drawRoundedRect(frame, 8, 8)
        painter.setPen(QPen(QColor("#FFFFFF"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for x1, y1, x2, y2 in (
            (16, 6, 16, 26), (6, 16, 26, 16),
            (12.5, 9.5, 16, 6), (19.5, 9.5, 16, 6),
            (12.5, 22.5, 16, 26), (19.5, 22.5, 16, 26),
            (9.5, 12.5, 6, 16), (9.5, 19.5, 6, 16),
            (22.5, 12.5, 26, 16), (22.5, 19.5, 26, 16),
        ):
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


class CalendarMoveDoneButton(_EnterClickButton):
    """위치 편집을 끝내는 '완료' 알약. '오늘'과 같은 52×32에 연한 파랑 테두리로 '지금 편집 중'을 보인다."""

    def __init__(self, parent=None):
        super().__init__("완료", parent)
        self.setObjectName("headerMoveDoneButton")
        self.setFixedSize(52, 32)
        self.setFocusPolicy(Qt.TabFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("위치 편집 끝내기 (Esc)")
        self.setAccessibleName("위치 편집 완료")
        self.setStyleSheet("""
            QPushButton#headerMoveDoneButton {
                color: #FFFFFF;
                background: rgba(147, 197, 253, 40);
                border-radius: 9px;
                border: 1px solid #93C5FD;
                padding: 0px 8px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#headerMoveDoneButton:hover { background: rgba(147, 197, 253, 70); }
            QPushButton#headerMoveDoneButton:pressed { background: rgba(147, 197, 253, 100); }
            QPushButton#headerMoveDoneButton:focus { border: 1px solid #FBBF24; }
        """)
        self.hide()
```

- [ ] **Step 4: 구현 — 상태와 머리줄**

`__init__`의 `self._calendar_move_enabled = db.get_setting(...) != "0"` 세 줄을 바꾼다.

```python
        # 위치 편집(J안)은 메모리 상태다. 평소 캘린더는 고정이며, 예전
        # calendar_move_enabled 값은 읽지 않고 행도 그대로 둔다(Export 포함).
        self._calendar_move_editing = False
```

`_build_top_bar`: `search_btn`을 `self._header_search_btn`으로 바꾸고(같은 블록 안 `search_btn` 모두), 이동 단추 연결과 '완료' 단추를 아래로.

```python
        self.calendar_move_button = CalendarMoveButton(self)
        self.calendar_move_button.clicked.connect(self._start_calendar_move_edit)
        right_group.addWidget(self.calendar_move_button)

        # 편집 중에는 검색·이동·⋮을 숨기고 이 알약만 오른쪽 끝에 남는다(104px 묶음 유지).
        self.calendar_move_done_button = CalendarMoveDoneButton(self)
        self.calendar_move_done_button.clicked.connect(self._finish_calendar_move_edit)
        right_group.addWidget(self.calendar_move_done_button)
```

`_calendar_drag_allowed`·`_update_calendar_move_control`·`_on_calendar_move_clicked`를 아래로 교체(`_on_calendar_move_clicked`는 삭제).

```python
    def _calendar_drag_allowed(self) -> bool:
        return self._calendar_move_editing and not self._is_locked and not self._hidden_to_tray

    def _update_calendar_move_control(self) -> None:
        editing = self._calendar_move_editing
        hint = "캘린더 옮기기 · 누른 뒤 머리줄을 끌어 옮깁니다"
        self.calendar_move_button.setToolTip(hint)
        self.calendar_move_button.setAccessibleDescription(hint)
        self.calendar_move_button.setEnabled(not self._is_locked)
        for widget in (self._header_search_btn, self.calendar_move_button, self._more_btn):
            widget.setVisible(not editing)
        self.calendar_move_done_button.setVisible(editing)
        allowed = self._calendar_drag_allowed()
        for target in self._calendar_drag_targets:
            target.setCursor(Qt.SizeAllCursor if allowed else Qt.ArrowCursor)
        self.month_label.setToolTip(
            "드래그하여 캘린더 이동" if allowed
            else "캘린더 위치 고정 · 옮기려면 십자 화살표 단추"
        )

    def _start_calendar_move_edit(self) -> None:
        """이동 단추: 위치 편집을 시작한다. 키보드로 눌렀으면 포커스를 '완료'로 옮긴다."""
        if self._calendar_move_editing or self._is_locked or self._hidden_to_tray:
            return
        keyboard = self.focusWidget() is self.calendar_move_button
        self._reset_calendar_drag()
        self._calendar_move_editing = True
        self._update_calendar_move_control()
        if keyboard:
            self.calendar_move_done_button.setFocus(Qt.TabFocusReason)

    def _finish_calendar_move_edit(self) -> None:
        """완료·Esc·자동 종료: 다시 고정한다. 위치는 끌기를 놓을 때 이미 저장했다. 언제 불러도 안전하다."""
        keyboard = self._calendar_move_editing and self.focusWidget() is self.calendar_move_done_button
        self._calendar_move_editing = False
        self._reset_calendar_drag()
        self._update_calendar_move_control()
        if keyboard and self.calendar_move_button.isEnabled():
            self.calendar_move_button.setFocus(Qt.TabFocusReason)

    def keyPressEvent(self, event):
        # 자식이 쓰지 않은 Esc만 올라온다(일정 편집 칸 등 Esc를 쓰는 곳은 그 동작이 우선).
        if event.key() == Qt.Key_Escape and self._calendar_move_editing:
            self._finish_calendar_move_edit()
            event.accept()
            return
        super().keyPressEvent(event)
```

`_on_import_complete`의 아래 네 줄

```python
        self._reset_calendar_drag()
        self._calendar_move_enabled = db.get_setting(
            db.SETTING_CALENDAR_MOVE_ENABLED, db.DEFAULT_CALENDAR_MOVE_ENABLED,
        ) != "0"
        self._update_calendar_move_control()
```

을 한 줄로.

```python
        self._finish_calendar_move_edit()
```

`database.py`:

```python
SETTING_CALENDAR_MOVE_ENABLED = "calendar_move_enabled"  # v3.9a J안부터 읽지 않음. 기존 행·Export 값은 보존
```

`DEFAULT_CALENDAR_MOVE_ENABLED = "1"` 줄은 삭제(쓰는 곳 없음 — `rg DEFAULT_CALENDAR_MOVE_ENABLED`로 확인).

- [ ] **Step 5: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_calendar_move.py tests/test_ui_calendar_drag.py tests/test_ui_kvm_position.py tests/test_ui.py -q`
Expected: PASS

- [ ] **Step 6: 커밋**

```powershell
git add ui_main.py database.py tests/test_ui_calendar_move.py tests/test_ui_calendar_drag.py tests/test_ui_kvm_position.py
git commit -m "feat: 캘린더는 평소 고정, 이동 단추로 위치 편집을 시작하고 '완료'로 끝냄"
```

---

### Task 3: 편집 표시 — 점선 테두리와 안내 띠

**Files:**
- Modify: `ui_main.py` 새 `CalendarMoveEditOverlay`(`CalendarMoveDoneButton` 아래), import(`QRect`, `QFontMetrics`, `QRegion`), `_build_ui`(1774~1776행 근처), `_update_calendar_move_control`
- Test: `tests/test_ui_calendar_move.py`(추가)

**Interfaces:**
- Consumes: Task 2의 `_calendar_move_editing`, `_update_calendar_move_control()`, `calendar_move_button`, `calendar_move_done_button`
- Produces: `MainCalendarWindow._calendar_move_overlay: CalendarMoveEditOverlay`(속성 `hint_text: str`, 클래스 상수 `HINT_HEIGHT = 28`, `HEADER_DASH = "#93C5FD"`, `BODY_DASH = "#2563EB"`)

- [ ] **Step 1: 실패하는 시험 쓰기** (`tests/test_ui_calendar_move.py` 끝에 추가)

```python
HEADER_DASH = (147, 197, 253)  # #93C5FD — 남색 머리줄 위
BODY_DASH = (37, 99, 235)      # #2563EB — 흰 칸·회색 바로가기 열·안내 띠 위
STRIP = (234, 242, 255)        # #EAF2FF


def _close(color, rgb, tol):
    return all(abs(a - b) <= tol for a, b in zip((color.red(), color.green(), color.blue()), rgb))


def _row_has(win, y, rgb, x_from=20, x_to=None, tol=24):
    """창의 논리 y 줄(x_from~x_to)에 rgb에 가까운 픽셀이 있는가. 점선은 틈이 있어 줄 전체를 훑는다."""
    image = win.grab().toImage()
    ratio = image.devicePixelRatio()
    x_to = win.width() - 20 if x_to is None else x_to
    row = int(y * ratio)
    return any(_close(image.pixelColor(x, row), rgb, tol)
               for x in range(int(x_from * ratio), int(x_to * ratio)))


def _column_has(win, x, y_from, y_to, rgb, tol=24):
    image = win.grab().toImage()
    ratio = image.devicePixelRatio()
    col = int(x * ratio)
    return any(_close(image.pixelColor(col, y), rgb, tol)
               for y in range(int(y_from * ratio), int(y_to * ratio)))


def _strip_color(win):
    header = win.findChild(QWidget, "headerSection")
    image = win.grab().toImage()
    ratio = image.devicePixelRatio()
    at = header.mapTo(win, QPoint(8, header.height() + 4))
    return image.pixelColor(int(at.x() * ratio), int(at.y() * ratio))


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_edit_mode_draws_dashed_outline_and_hint_strip(qtbot, scale):
    win = window(qtbot, scale)
    overlay = win._calendar_move_overlay
    bottom = win.height() - 1.5
    assert not overlay.isVisible()
    assert not _row_has(win, 1, HEADER_DASH) and not _row_has(win, bottom, BODY_DASH)
    win.calendar_move_button.click()
    QApplication.processEvents()
    assert overlay.isVisible()
    assert overlay.geometry() == win.container.rect()
    assert overlay.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert overlay.hint_text == "머리줄을 끌어 원하는 곳에 두고 '완료'를 누르세요"
    assert _row_has(win, 1, HEADER_DASH)       # 위쪽 가장자리(남색 머리줄 위)
    assert _row_has(win, bottom, BODY_DASH)    # 아래쪽 가장자리(흰 바탕 위)
    assert _close(_strip_color(win), STRIP, 3)
    drag_header(win)  # 덧그림이 있어도 머리줄 끌기는 그대로
    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "free"
    win.calendar_move_done_button.click()
    QApplication.processEvents()
    assert not overlay.isVisible()
    assert not _row_has(win, 1, HEADER_DASH) and not _row_has(win, bottom, BODY_DASH)


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_outline_color_follows_background(qtbot, scale):
    """남색 머리줄 위는 연한 파랑, 그 밖(흰 칸·회색 바로가기 열·크게 오른쪽 열)은 진한 파랑이다."""
    win = window(qtbot, scale)
    win.calendar_move_button.click()
    QApplication.processEvents()
    header = win.findChild(QWidget, "headerSection")
    top = header.mapTo(win, QPoint(0, 0))
    over_header = (top.x() + 20, top.x() + header.width() - 20)
    assert _row_has(win, 1, HEADER_DASH, *over_header)
    assert not _row_has(win, 1, BODY_DASH, *over_header)
    below = top.y() + header.height() + 8
    right = win.width() - 1.5
    assert _column_has(win, right, below, win.height() - 20, BODY_DASH)
    assert not _column_has(win, right, below, win.height() - 20, HEADER_DASH)
    if win.sidebar.isVisible():  # 중간·크게: 왼쪽 회색 바로가기 열 위의 위쪽 가장자리
        assert _row_has(win, 1, BODY_DASH, 14, top.x() - 4)


def test_hint_strip_follows_header_height(qtbot):
    db.save_setting(db.SETTING_SHOW_LAW_SEARCH, "1")
    win = window(qtbot)
    win.calendar_move_button.click()
    QApplication.processEvents()
    assert _close(_strip_color(win), STRIP, 3)
    db.save_setting(db.SETTING_SHOW_LAW_SEARCH, "0")
    win._on_law_search_changed()
    QApplication.processEvents()
    assert _close(_strip_color(win), STRIP, 3)
    assert win._calendar_move_overlay.geometry() == win.container.rect()
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_calendar_move.py -q -k "outline or strip"`
Expected: FAIL — `AttributeError: ... '_calendar_move_overlay'`

- [ ] **Step 3: 구현 — 덧그림 위젯**

import 두 줄에 이름을 더한다.

```python
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QUrl, QPoint, QPointF, QRect, QRectF
from PySide6.QtGui import QFont, QFontMetrics, QDesktopServices, QPainter, QBrush, QPen, QColor, QRegion
```

```python
class CalendarMoveEditOverlay(QWidget):
    """위치 편집 중 캘린더 안쪽 가장자리에 점선, 머리줄 바로 아래에 안내 띠를 그린다(J안).

    창 바깥은 바탕화면이라 점선을 안쪽에 그린다. 안내 띠는 달력 칸을 밀지 않도록 겹쳐 그리며
    마우스 입력은 모두 아래 위젯으로 통과한다.
    """

    HINT_TEXT = "머리줄을 끌어 원하는 곳에 두고 '완료'를 누르세요"
    HINT_HEIGHT = 28
    # 점선은 바탕에 따라 두 톤(2026-10-11 색 비교). 노랑은 키보드 포커스 표시와 겹쳐 쓰지 않는다.
    HEADER_DASH = "#93C5FD"  # 남색 머리줄 위: '완료' 테두리와 같은 연한 파랑, 대비 7.8:1
    BODY_DASH = "#2563EB"    # 흰 칸·회색 바로가기 열·안내 띠 위: 앱 강조색, 대비 4.6:1 이상

    def __init__(self, container: QWidget, header: QWidget):
        super().__init__(container)
        self.setObjectName("calendarMoveEditOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._header = header
        self.hint_text = self.HINT_TEXT
        container.installEventFilter(self)
        header.installEventFilter(self)
        self.hide()

    def show_over(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()

    def eventFilter(self, obj, event):
        if self.isVisible() and event.type() in (QEvent.Resize, QEvent.Move):
            if obj is self.parentWidget():
                self.setGeometry(obj.rect())
            self.update()
        return False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        origin = self._header.mapTo(self.parentWidget(), QPoint(0, 0))
        strip = QRect(origin.x(), origin.y() + self._header.height(),
                      self._header.width(), self.HINT_HEIGHT)
        painter.fillRect(strip, QColor("#EAF2FF"))
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#1D4ED8"))
        text = QFontMetrics(font).elidedText(self.hint_text, Qt.ElideRight, max(0, strip.width() - 16))
        painter.drawText(strip, Qt.AlignCenter, text)
        # 같은 점선 경로를 머리줄 영역과 나머지로 잘라 두 번 그린다(색만 바뀌고 선·틈 위치는 이어진다).
        border = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        header_rect = QRect(origin, self._header.size())
        painter.setBrush(Qt.NoBrush)
        for color, region in (
            (self.HEADER_DASH, QRegion(header_rect)),
            (self.BODY_DASH, QRegion(self.rect()).subtracted(QRegion(header_rect))),
        ):
            pen = QPen(QColor(color), 2)
            pen.setDashPattern([3, 2])  # 펜 굵기 배수: 6px 선, 4px 틈
            painter.setPen(pen)
            painter.setClipRegion(region)
            painter.drawRoundedRect(border, 11, 11)
        painter.setClipping(False)
```

`_build_ui`에서 `self._calendar_drag_targets = {...}` 다음, `self._update_calendar_move_control()` 앞에 넣는다.

```python
        self._calendar_move_overlay = CalendarMoveEditOverlay(self.container, header_section)
```

`_update_calendar_move_control` 안 `self.calendar_move_done_button.setVisible(editing)` 다음에 넣는다.

```python
        if editing:
            self._calendar_move_overlay.show_over()
        else:
            self._calendar_move_overlay.hide()
```

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_calendar_move.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add ui_main.py tests/test_ui_calendar_move.py
git commit -m "feat: 위치 편집 중 캘린더에 점선 테두리와 안내 띠 표시"
```

---

### Task 4: 자동 종료와 고정 중 끌기 안내

**Files:**
- Modify: `ui_main.py` `eventFilter`(4032~4060행), 새 `_note_fixed_header_drag`, `__init__`, `_lock`(4179~4181행), `_minimize_to_tray`(3524~3525행), `_apply_calendar_scale`(1667행), `_discard_data_widgets`(3442행)
- Test: `tests/test_ui_calendar_move.py`(추가)

**Interfaces:**
- Consumes: Task 2의 `_finish_calendar_move_edit()`, `_start_calendar_move_edit()`, Task 3의 `_calendar_move_overlay`
- Produces: `MainCalendarWindow._calendar_fixed_hint_shown: bool`, `_note_fixed_header_drag(event) -> None`

- [ ] **Step 1: 실패하는 시험 쓰기** (`tests/test_ui_calendar_move.py` 끝에 추가)

```python
@pytest.mark.parametrize("action", (
    "done", "escape", "deactivate", "lock", "tray", "scale", "import", "discard"))
def test_edit_mode_ends_and_drag_cancels(qtbot, action):
    win = window(qtbot)
    win.calendar_move_button.click()
    point = win.month_label.rect().center()
    QTest.mousePress(win.month_label, Qt.LeftButton, pos=point)
    assert win._calendar_drag_offset is not None
    if action == "done":
        win.calendar_move_done_button.click()
    elif action == "escape":
        qtbot.keyClick(win, Qt.Key_Escape)
    elif action == "deactivate":
        win.eventFilter(win, QEvent(QEvent.Type.WindowDeactivate))
    elif action == "lock":
        win._lock()
    elif action == "tray":
        win._minimize_to_tray()
    elif action == "scale":
        db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
        win._apply_calendar_scale()
    elif action == "import":
        win._on_import_complete()
    else:
        win._discard_data_widgets()
    assert not win._calendar_move_editing
    assert not win._calendar_move_overlay.isVisible()
    assert win._calendar_drag_offset is None and not win._calendar_drag_started
    QTest.mouseRelease(win.month_label, Qt.LeftButton, pos=point)
    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "corner"
    if action == "lock":
        assert not win.calendar_move_button.isEnabled()
        win._start_calendar_move_edit()  # 잠금 중에는 시작하지 않는다
        assert not win._calendar_move_editing
        win._unlock()
        assert win.calendar_move_button.isEnabled() and not win._calendar_move_editing
    elif action == "tray":
        win._start_calendar_move_edit()  # 숨김 중에도 시작하지 않는다
        assert not win._calendar_move_editing
        win.toggle_visibility()
        assert not win._calendar_move_editing and win.calendar_move_button.isVisible()


def test_monitor_change_keeps_edit_mode(qtbot):
    win = window(qtbot)
    win.calendar_move_button.click()
    QTest.mousePress(win.month_label, Qt.LeftButton, pos=win.month_label.rect().center())
    win._on_screen_changed()
    assert win._calendar_move_editing  # 모니터 변경은 끌기만 취소
    assert win._calendar_drag_offset is None


def test_dragging_fixed_header_hints_move_button_once_per_run(qtbot, monkeypatch):
    shown = []
    monkeypatch.setattr(ui_main.InfoBar, "info", lambda **kwargs: shown.append(kwargs))
    win = window(qtbot)
    start = win.month_label.rect().center()
    QTest.mousePress(win.month_label, Qt.LeftButton, pos=start)
    QTest.mouseMove(win.month_label, start + QPoint(1, 1), delay=20)  # 손떨림은 안내하지 않는다
    QTest.mouseRelease(win.month_label, Qt.LeftButton, pos=start + QPoint(1, 1))
    assert shown == []
    drag_header(win)
    assert len(shown) == 1
    assert shown[0]["title"] == "캘린더 위치 고정"
    assert shown[0]["content"] == "옮기려면 머리줄의 십자 화살표 단추를 누르세요."
    drag_header(win)
    assert len(shown) == 1  # 실행마다 한 번
    win.calendar_move_button.click()
    drag_header(win)
    assert len(shown) == 1  # 편집 중 끌기는 안내 없음


def test_fixed_drag_hint_fits_inside_compact_window(qtbot):
    win = window(qtbot)  # 기본 380px
    drag_header(win)
    qtbot.wait(50)
    bars = [bar for bar in win.findChildren(ui_main.InfoBar) if bar.isVisible()]
    assert len(bars) == 1
    assert bars[0].width() <= win.width() - 16
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_calendar_move.py -q -k "ends_and_drag or monitor or hints"`
Expected: FAIL — deactivate·lock·tray·scale·discard에서 `_calendar_move_editing`이 True로 남음, 안내 시험은 `shown == []`(안내 없음).

- [ ] **Step 3: 구현 — 자동 종료**

`__init__`(`self._calendar_move_editing = False` 아래):

```python
        self._calendar_fixed_hint_shown = False
        self._calendar_fixed_press_global = None
```

`_lock`: `self._reset_calendar_drag()` + `self._update_calendar_move_control()` 두 줄을

```python
        self._finish_calendar_move_edit()
```

로. `_minimize_to_tray`도 같은 두 줄을 같은 한 줄로. `_apply_calendar_scale`와 `_discard_data_widgets`의 `self._reset_calendar_drag()`를 `self._finish_calendar_move_edit()`로. `_on_screen_changed`의 `_reset_calendar_drag()`는 그대로 둔다(편집 유지).

`eventFilter`의 비활성 처리:

```python
        if event_type in (
            QEvent.Type.WindowDeactivate,
            QEvent.Type.UngrabMouse,
        ):
            self._reset_calendar_drag()
            if obj is self and event_type == QEvent.Type.WindowDeactivate:
                self._finish_calendar_move_edit()  # 다른 곳을 누르면 자동 완료
```

- [ ] **Step 4: 구현 — 고정 중 끌기 안내**

`eventFilter`의 끌기 불가 분기:

```python
            if (
                not self._calendar_drag_allowed()
                and event_type in (
                    QEvent.Type.MouseButtonPress,
                    QEvent.Type.MouseMove,
                    QEvent.Type.MouseButtonRelease,
                )
            ):
                self._reset_calendar_drag()
                self._note_fixed_header_drag(event)
                return False
```

```python
    def _note_fixed_header_drag(self, event) -> None:
        """고정 중 머리줄을 끌면 실행마다 한 번 이동 단추를 알려 준다(예전 '끌어서 이동' 습관 안내)."""
        if self._calendar_fixed_hint_shown or self._is_locked or self._hidden_to_tray:
            return
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            self._calendar_fixed_press_global = event.globalPosition().toPoint()
            return
        if (event_type == QEvent.Type.MouseMove
                and self._calendar_fixed_press_global is not None
                and bool(event.buttons() & Qt.LeftButton)):
            delta = event.globalPosition().toPoint() - self._calendar_fixed_press_global
            if delta.manhattanLength() < QApplication.startDragDistance():
                return
            self._calendar_fixed_hint_shown = True
            # 380px 창에서 제목·본문을 가로로 두면 창보다 넓어지므로 세로로 쌓는다.
            InfoBar.info(
                title="캘린더 위치 고정",
                content="옮기려면 머리줄의 십자 화살표 단추를 누르세요.",
                orient=Qt.Vertical, parent=self, position=InfoBarPosition.TOP, duration=3000,
            )
        self._calendar_fixed_press_global = None
```

- [ ] **Step 5: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_calendar_move.py tests/test_ui_calendar_drag.py tests/test_ui_kvm_position.py tests/test_ui_screen_change.py tests/test_ui.py -q`
Expected: PASS

- [ ] **Step 6: 커밋**

```powershell
git add ui_main.py tests/test_ui_calendar_move.py
git commit -m "feat: 위치 편집 자동 종료(비활성·잠금·트레이·크기·초기화)와 고정 중 끌기 안내"
```

---

### Task 5: 문서·검증·기록

**Files:**
- Modify: `docs/UI_PATTERNS.md`(15·17·18·22·134행 문단), `docs/TESTING.md`(162·172·186·193행 문단 중 이동 관련 문장만 — 진단 도구 절은 손대지 않음), `README_detail.md`(60행), `AGENTS.md`(85행, HEAD 사본 blob 방식)
- Create: `docs/work/2026-10-11-move-edit-mode.md`
- Modify(gitignore): `output/design/design-audit-20261009/design-audit.html` 진행 상황 판(11·15번 재작업 메모), 캡처 `output/design/move-button-20261011/real/`

- [ ] **Step 1: 문서 문장 바꾸기** — 각 문단에서 "이동 토글 ON/OFF·`calendar_move_enabled` 기본 ON·명시적 토글 저장·점/사선" 설명을 아래 내용으로 바꾼다.
  - UI_PATTERNS 17행(이동 단추): "검색 → 이동 → 더보기 32px 3개·4px 간격, 좌우 104px. 이동 단추는 흰 십자 화살표(상태 표시 없음)로 위치 편집을 시작한다. 편집 중에는 세 단추를 숨기고 오른쪽 끝에 '완료' 알약(52×32, 테두리 `#93C5FD`). Tab → Space/Enter로 시작하면 포커스가 '완료'로, 끝내면 이동 단추로 돌아온다. 마우스 클릭은 일정 입력 포커스를 빼앗지 않는다(2026-10-11 J안, 이전 ON 점·OFF 사선 토글)."
  - 18행(상태·범위): "평소 고정. 편집 상태는 메모리 전용이라 재시작하면 고정. 예전 `calendar_move_enabled` 행은 읽지 않고 보존(Export 포함). 편집 중 창 안쪽 2px 점선(남색 머리줄 위 `#93C5FD`, 그 밖 `#2563EB` — 어느 바탕에서도 4.6:1 이상, 노랑은 포커스 색과 겹쳐 쓰지 않음)과 머리줄 아래 28px 안내 띠(겹쳐 그림, 마우스 통과). 완료·Esc·창 비활성·잠금·트레이·크기 변경·가져오기/초기화로 끝나고 진행 중 끌기를 취소한다. 모니터 변경은 편집 유지·끌기만 취소. 고정 중 머리줄을 끌면 실행마다 한 번 안내 InfoBar."
  - 15행: "이동 OFF도 같은 복원 규칙" → "고정 상태도 같은 복원 규칙".
  - 22행: "고른 날은 칸 바탕 대신 남색 2px 테두리" → "고른 날은 칸 전체 연한 회색(`rgba(1,41,95,20)`, 기본 크기와 같은 색), 오늘을 고르면 회색 칸 위 남색 원(2026-10-11 사용자 요청으로 15번 테두리를 되돌림)".
  - 134행 첫 문장: "헤더 배경과 연월 라벨만 드래그 영역이며 위치 편집 중에만 끌 수 있다."
  - TESTING: 162행 "이동 ON/OFF" → "위치 편집/고정", 172행 `test_ui_calendar_move.py` 설명을 "평소 고정·예전 설정 보존·세 크기 편집/끌기/완료·Tab/Space/Enter/Esc·포커스 보존·점선 두 톤(머리줄 위 연한 파랑/그 밖 진한 파랑)·안내 띠 픽셀·자동 종료 8가지·모니터 변경 유지·고정 중 끌기 안내 1회·두 상태 머리줄 배치"로, 186행 "이동 켜짐 점·채움 없음" → "(11번은 2026-10-11 J안으로 대체)", "고른 날 테두리" → "고른 날 연한 회색", 193행 "이동 토글 OFF 시 드래그 차단" → "고정 상태 드래그 차단".
  - README_detail 60행: "**캘린더 이동** — 평소에는 위치가 고정됩니다. 머리줄의 십자 화살표를 누르고 머리줄을 끌어 옮긴 뒤 '완료'(또는 Esc)를 누릅니다."
  - AGENTS 85행: 같은 요지로 한 문장. 기록 관리 절(169행 근처)에 "2026-10-11 위치 편집(J안)·고른 날 회색 채움은 v3.9a 유지, 기록 [작업 기록](docs/work/2026-10-11-move-edit-mode.md)" 한 줄.
  - `docs/TESTING.md`·`AGENTS.md`는 다른 작업·사용자의 미커밋 줄이 있으므로 Step 5의 blob 방식으로만 스테이지한다.

- [ ] **Step 2: 배율별 관련 시험**

```powershell
$t = "tests/test_ui_calendar_move.py tests/test_ui_calendar_drag.py tests/test_ui_kvm_position.py tests/test_ui_calendar_cells.py tests/test_ui.py tests/test_ui_screen_change.py"
.\.venv\Scripts\python.exe tools/verify.py quick --tests $t.Split(" ")
$env:QT_SCALE_FACTOR="1.25"; .\.venv\Scripts\python.exe tools/verify.py quick --tests $t.Split(" ")
$env:QT_SCALE_FACTOR="1.5";  .\.venv\Scripts\python.exe tools/verify.py quick --tests $t.Split(" ")
Remove-Item Env:QT_SCALE_FACTOR
```

Expected: 세 번 모두 통과(실행 ID 기록). 다른 작업의 동시 수정으로 `inputs_changed`가 나면 그 작업이 끝난 뒤 새 실행 ID로 다시.

- [ ] **Step 3: 전체 시험**

Run: `.\.venv\Scripts\python.exe tools/verify.py full`
Expected: 통과(실패·오류 0). 실행 ID와 개수 기록.

- [ ] **Step 4: 화면 확인 캡처** — 하네스가 남긴 `calendar-move-edit-{compact,medium,large}.png`와 고른 날 회색 캡처(합성 데이터)를 `output/design/move-button-20261011/real/`에 복사하고 `j-final.html`과 나란히 비교. 보고서 `design-audit.html` 진행 판의 11·15번에 "2026-10-11 재작업(J안·회색 채움)" 메모.

- [ ] **Step 5: 작업 기록·커밋** — `docs/work/2026-10-11-move-edit-mode.md`(목표·결정 D1~D9·바뀐 파일·시험 결과·실행 ID·남은 수동 확인: 실제 EXE에서 편집 표시·Esc·다른 창 클릭 자동 완료, 다크 모드·125/150%).

```powershell
git add docs/UI_PATTERNS.md README_detail.md docs/work/2026-10-11-move-edit-mode.md
# docs/TESTING.md(다른 작업의 미커밋 진단 절)와 AGENTS.md(사용자 미커밋 4줄)는 대화형 `git add -p` 대신
# 일회용 스크립트로 작업 트리와 `git show HEAD:<파일>` 사본에 같은 치환만 하고, 사본을
# `git hash-object -w --stdin` → `git update-index --cacheinfo <mode>,<blob>,<파일>`로 스테이지한다.
git diff --cached --stat   # 다른 작업 파일이 섞이지 않았는지 확인
git commit -m "docs: 캘린더 위치 편집(J안)·고른 날 회색 채움 기록"
```

- [ ] **Step 6: 사용자 보고** — 결과·캡처 경로·실행 ID 보고. main 병합·release 빌드·push는 사용자 지시를 받은 뒤에만.
