# '크게' 모드 위젯 통합 & 개수 제한 — 구현 계획서

> **For agentic workers (Codex 등):** 이 계획은 task 단위로 순차 실행한다. 각 단계는 체크박스(`- [ ]`)로 추적한다. 한 task = 자기완결적 변경.

**Goal:** 집중/D-Day 위젯 개수를 제한(집중 1·D-Day 5)하고 업그레이드 시 초과분을 안전 정리하며, '크게'(large) 모드 우측 사이드바에 일정·D-Day·집중·스티키를 모두 수용하고 스티키 미니 패널을 플로팅 창과 기능 동기화한다.

**Architecture:** 데이터 정리는 `database.py`의 멱등 함수 `enforce_widget_limits()`로 단일화하고, UI는 `MainCalendarWindow`가 시작 시 1회 호출 후 모달 경고를 띄운다. large 모드는 기존 `StickySidePanel` 패턴을 D-Day/집중 미니 패널로 확장하고, 집중은 숨긴 플로팅 창의 라이브 타이머를 미니 카드가 미러링한다. 스티키 서식 로직은 `ui_sticky.py`의 공용 함수로 추출해 플로팅 창과 패널 툴바가 공유한다.

**Tech Stack:** Python 3, PySide6, qfluentwidgets, SQLite(암호화 Fernet), pytest + pytest-qt.

---

## 사전 메모 (중요)

- **이 저장소는 현재 git 저장소가 아니다**(`Is a git repository: false`). 따라서 각 task 끝의 단계는 **`git commit`이 아니라 "체크포인트 = 관련 테스트 그린"**으로 둔다. (원한다면 `git init` 후 commit 단계를 추가해도 된다.)
- 전체 테스트: `python -m pytest tests -q` / 단일: `python -m pytest tests/<file>::<test> -v`
- **데이터 보존 원칙**: 초과 위젯은 삭제 금지, `is_open=0`으로만 정리한다(`AGENTS.md`).
- 예외는 타입별 세분화 + 로깅(`bare except:`·`except+pass` 금지). DB는 `_connection()`만 사용. Qt 다이얼로그는 `deleteLater()`.
- 관련 설계: `docs/superpowers/specs/2026-06-12-large-mode-widgets-design.md`.

## File Structure (생성/수정 책임)

| 파일 | 책임 | 종류 |
|---|---|---|
| `database.py` | `enforce_widget_limits()` 추가, `get_open_dday_widgets`/`get_open_focus_widgets`에 `ORDER BY id` | 수정 |
| `ui_sticky.py` | 서식 공용 함수(`toggle_bold`/`insert_todo`/`apply_text_color`/`bold_state`) + `StickyFormatToolbar` 위젯 추출, `StickyNoteWindow`는 위임 | 수정 |
| `ui_sticky_panel.py` | 패널 헤더 공용 툴바, 카드 포커스 추적, 카드별 X(휴지통), 배경색 변경, `note_trashed` 시그널 | 수정 |
| `ui_dday_panel.py` | `DDayMiniCard`/`DDaySidePanel` (편집 가능, 1분 갱신) | 신규 |
| `ui_focus_panel.py` | `FocusMiniCard`(라이브 미러)/`FocusSidePanel` | 신규 |
| `ui_main.py` | enforce 호출+모달 경고, 생성 카운트 버그픽스, D-Day/집중 미니 패널 통합, `note_trashed` 처리 | 수정 |
| `tests/test_widget_limits.py` | 개수 제한/정리 테스트 | 신규 |
| `tests/test_ui_dday_panel.py` | D-Day 패널 테스트 | 신규 |
| `tests/test_ui_focus_panel.py` | 집중 미니 패널 테스트 | 신규 |
| `tests/test_ui_sticky_panel.py` | 툴바/삭제/순서 테스트 추가·수정 | 수정 |
| `AGENTS.md` | 모듈맵·제약 갱신 | 수정 |

---

## Phase 1 — 위젯 개수 제한 + 업그레이드 정리

### Task 1: `enforce_widget_limits()` + 결정적 로드 순서 (DB)

**Files:**
- Modify: `database.py` (`get_open_dday_widgets` ~777, `get_open_focus_widgets` ~842, focus CRUD 뒤에 신규 함수)
- Test: `tests/test_widget_limits.py` (신규)

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_widget_limits.py`

```python
# tests/test_widget_limits.py - 위젯 개수 제한/정리 테스트
import database as db


def test_enforce_keeps_newest_focus(app_dir):
    ids = [db.create_focus_widget(f"목표{i}", "25/5") for i in range(3)]
    result = db.enforce_widget_limits()
    assert result["focus"] == 2
    assert [w["id"] for w in db.get_open_focus_widgets()] == [ids[-1]]


def test_enforce_keeps_newest_five_dday(app_dir):
    ids = [db.create_dday_widget(f"D{i}", "2026-12-31") for i in range(7)]
    result = db.enforce_widget_limits()
    assert result["dday"] == 2
    assert sorted(w["id"] for w in db.get_open_dday_widgets()) == sorted(ids[2:])


def test_enforce_is_idempotent(app_dir):
    for i in range(3):
        db.create_focus_widget(f"g{i}", "25/5")
    db.enforce_widget_limits()
    assert db.enforce_widget_limits() == {"focus": 0, "dday": 0}


def test_enforce_preserves_closed_widget_data(app_dir):
    db.create_focus_widget("보존1", "25/5")   # 가장 오래됨 → 닫힘 대상
    db.create_focus_widget("보존2", "25/5")   # 최신 → 유지
    db.enforce_widget_limits()
    with db._connection() as conn:
        rows = conn.execute("SELECT goal FROM focus_widgets ORDER BY id").fetchall()
    assert len(rows) == 2                      # 행 삭제 안 됨(데이터 보존)
    assert db.decrypt(rows[0]["goal"]) == "보존1"
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_widget_limits.py -v`
Expected: FAIL — `AttributeError: module 'database' has no attribute 'enforce_widget_limits'`

- [ ] **Step 3: `get_open_*`에 `ORDER BY id` 추가**

`database.py`에서 두 쿼리를 수정한다.

`get_open_dday_widgets` (~781):
```python
        rows = conn.execute(
            "SELECT * FROM dday_widgets WHERE is_open = 1 ORDER BY id"
        ).fetchall()
```
`get_open_focus_widgets` (~846):
```python
        rows = conn.execute(
            "SELECT * FROM focus_widgets WHERE is_open = 1 ORDER BY id"
        ).fetchall()
```

- [ ] **Step 4: `enforce_widget_limits()` 구현**

`database.py`의 focus CRUD 블록 뒤(예: `delete_focus_widget` 다음, ~911)에 추가한다.

```python
# ─── 위젯 개수 제한 정리 ───────────────────────────────────────
def enforce_widget_limits() -> dict[str, int]:
    """집중(1)·D-Day(5) 상한 초과분을 is_open=0으로 정리한다.

    최신(id 큰) N개만 남기고 나머지를 닫는다(행 삭제 아님, 데이터 보존).
    멱등하며, 정리된 개수를 {"focus": n, "dday": m} 로 반환한다.
    """
    trimmed = {"focus": 0, "dday": 0}
    limits = (("focus", "focus_widgets", 1), ("dday", "dday_widgets", 5))
    with _connection() as conn:
        for kind, table, keep in limits:
            rows = conn.execute(
                f"SELECT id FROM {table} WHERE is_open = 1 ORDER BY id DESC"  # noqa: S608
            ).fetchall()
            excess = [row["id"] for row in rows[keep:]]
            for widget_id in excess:
                conn.execute(
                    f"UPDATE {table} SET is_open = 0 WHERE id = ?",  # noqa: S608
                    (widget_id,),
                )
            trimmed[kind] = len(excess)
        conn.commit()
    return trimmed
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/test_widget_limits.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: 회귀 확인 (DB 테스트)**

Run: `python -m pytest tests/test_database.py -q`
Expected: PASS (ORDER BY 추가가 기존 테스트에 영향 없음)

- [ ] **Step 7: 체크포인트** — 위 두 명령 그린이면 Task 1 완료.

---

### Task 2: 시작 시 정리 호출 + 모달 경고 (`ui_main.py`)

**Files:**
- Modify: `ui_main.py` (`MainCalendarWindow.__init__` ~635-672, `_load_open_focus_widgets` ~2013)
- Test: `tests/test_widget_limits.py`

- [ ] **Step 1: 실패 테스트 추가** — `tests/test_widget_limits.py` 하단에 추가

```python
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_main_enforces_focus_keeps_newest(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    ids = [db.create_focus_widget(f"목표{i}", db.DEFAULT_FOCUS_MODE) for i in range(3)]
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    assert list(win._focus_windows.keys()) == [ids[-1]]
    assert win._widget_trim_result["focus"] == 2


def test_main_enforces_dday_keeps_newest_five(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    ids = [db.create_dday_widget(f"D{i}", "2026-12-31") for i in range(7)]
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    assert sorted(win._dday_windows.keys()) == sorted(ids[2:])
    assert win._widget_trim_result["dday"] == 2
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_widget_limits.py::test_main_enforces_focus_keeps_newest -v`
Expected: FAIL — `AttributeError: 'MainCalendarWindow' object has no attribute '_widget_trim_result'`

- [ ] **Step 3: `__init__`에서 enforce 호출 (로드 이전)**

`ui_main.py`의 `__init__`에서, 위젯 로드 관련 줄들(현재 ~666-671) **이전**에 정리를 수행한다. 구체적으로 `self._schedule_color = db.DEFAULT_SCHEDULE_COLOR` (현재 ~652) 다음 줄에 삽입한다.

```python
        self._schedule_color = db.DEFAULT_SCHEDULE_COLOR

        # 위젯 개수 상한 정리(집중 1·D-Day 5). 로드/패널 적용 이전에 1회.
        try:
            self._widget_trim_result = db.enforce_widget_limits()
        except sqlite3.Error as e:
            _logger.error("위젯 개수 정리 실패: %s", e)
            self._widget_trim_result = {"focus": 0, "dday": 0}
```

> `sqlite3`/`_logger`는 `ui_main.py` 상단에서 이미 import됨(파일 상단 import 확인). 없다면 `import sqlite3` 추가.

- [ ] **Step 4: 경고 모달 메서드 추가 + 트리거**

`__init__` 끝부분(타이머 설정 근처, 예 `self._periodic_save_timer.start()` 다음)에 트리거를 추가한다.

```python
        # 업그레이드 정리 안내(정리된 위젯이 있을 때만, 창 표시 후 모달)
        if self._widget_trim_result.get("focus") or self._widget_trim_result.get("dday"):
            QTimer.singleShot(1500, self._warn_widget_trim)
```

그리고 클래스에 메서드를 추가한다(집중/D-Day 위젯 관련 메서드 근처, 예 `_on_focus_widget_closed` 뒤).

```python
    def _warn_widget_trim(self):
        """업그레이드 시 상한 초과 위젯을 정리했음을 모달로 안내."""
        focus_n = self._widget_trim_result.get("focus", 0)
        dday_n = self._widget_trim_result.get("dday", 0)
        parts = []
        if focus_n:
            parts.append(f"집중 모드 {focus_n}개")
        if dday_n:
            parts.append(f"D-Day {dday_n}개")
        if not parts:
            return
        from qfluentwidgets import Dialog
        body = (
            "이전 버전에서 만든 위젯이 많아 일부를 정리했습니다.\n"
            f"{' · '.join(parts)}를 닫았습니다(집중 1개·D-Day 최신 5개만 표시).\n"
            "닫힌 위젯의 데이터는 보존됩니다."
        )
        dlg = Dialog("위젯 정리 안내", body, self)
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.cancelButton.hide()
        dlg.yesButton.setText("확인")
        dlg.exec()
        dlg.deleteLater()
```

- [ ] **Step 5: 기존 임시 정리 로직 제거 (`_load_open_focus_widgets`)**

현재 `_load_open_focus_widgets`(~2013)의 `idx >= 1` 정리 블록을 제거하고, 단순 로드로 바꾼다(정리는 이제 enforce 담당).

변경 전:
```python
            for idx, w in enumerate(widgets):
                if idx >= 1:
                    db.update_focus_widget(w["id"], is_open=0)
                    continue
                win = FocusWidgetWindow(w["id"], w)
                ...
```
변경 후:
```python
            for w in widgets:
                win = FocusWidgetWindow(w["id"], w)
                win.widget_closed.connect(self._on_focus_widget_closed)
                win.setWindowOpacity(factor)
                QTimer.singleShot(0, lambda _w=win: (_w.show(), _w.raise_()))
                self._focus_windows[w["id"]] = win
```

- [ ] **Step 6: 통과 확인**

Run: `python -m pytest tests/test_widget_limits.py -v`
Expected: PASS

- [ ] **Step 7: 기존 집중 로드 테스트 회귀 확인**

Run: `python -m pytest tests/test_ui_focus.py::test_focus_widget_load_caps_at_one -v`
Expected: PASS (개수 1 검증 — enforce가 최신 유지로 대체, 개수 동일)

- [ ] **Step 8: 체크포인트** — Step 6·7 그린이면 완료.

---

### Task 3: 생성 카운트 버그픽스 + D-Day 상한 10→5

`isVisible()` 기반 카운트는 패널 모드(위젯 숨김)에서 0으로 세어 제한을 우회한다. 등록 딕셔너리 길이(표시 모드 무관) 기준으로 바꾼다.

**Files:**
- Modify: `ui_main.py` (`_on_new_dday_widget` ~1927, `_on_new_focus_widget` ~1978)
- Test: `tests/test_widget_limits.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_focus_at_limit_counts_registry_not_visibility(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._focus_windows = {1: object()}      # 숨김 여부와 무관하게 등록 기준
    assert win._focus_at_limit() is True
    win._focus_windows = {}
    assert win._focus_at_limit() is False


def test_dday_at_limit_is_five(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._dday_windows = {i: object() for i in range(5)}
    assert win._dday_at_limit() is True
    win._dday_windows = {i: object() for i in range(4)}
    assert win._dday_at_limit() is False
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_widget_limits.py::test_dday_at_limit_is_five -v`
Expected: FAIL — `AttributeError: ... '_dday_at_limit'`

- [ ] **Step 3: 한도 헬퍼 추가**

`ui_main.py`에 두 헬퍼를 추가한다(`_on_new_dday_widget` 근처).

```python
    def _focus_at_limit(self) -> bool:
        return len(self._focus_windows) >= 1

    def _dday_at_limit(self) -> bool:
        return len(self._dday_windows) >= 5
```

- [ ] **Step 4: `_on_new_dday_widget` 수정**

`open_count` 계산과 상한 분기를 헬퍼/등록 기준으로 교체한다(현재 ~1929-1938).

```python
    def _on_new_dday_widget(self):
        from ui_dday import DDayCreateDialog, DDayWidgetWindow
        if self._dday_at_limit():
            InfoBar.warning(
                title="위젯 제한",
                content="D-Day 위젯은 최대 5개까지 만들 수 있습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=3000,
            )
            return

        open_count = len(self._dday_windows)   # 오프셋/색상 인덱스용
        dlg = DDayCreateDialog(self)
        ...
```
(이하 생성 로직은 기존 유지. `offset = open_count * 30`, `color_idx = open_count % len(STICKY_COLORS)` 그대로.)

- [ ] **Step 5: `_on_new_focus_widget` 수정**

상한 분기를 헬퍼 기준으로 교체한다(현재 ~1980-1989).

```python
    def _on_new_focus_widget(self):
        from ui_focus import FocusCreateDialog, FocusWidgetWindow
        if self._focus_at_limit():
            InfoBar.warning(
                title="위젯 제한",
                content="집중 모드는 1개만 사용할 수 있습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=3000,
            )
            return

        open_count = len(self._focus_windows)
        dlg = FocusCreateDialog(self)
        ...
```

- [ ] **Step 6: 통과 + 회귀 확인**

Run: `python -m pytest tests/test_widget_limits.py -v`
Expected: PASS

Run: `python -m pytest tests/test_ui.py -q`
Expected: PASS (메인 창 회귀)

- [ ] **Step 7: 체크포인트** — 완료.

---

## Phase 2 — 스티키 미니 패널 기능 동기화

### Task 4: 스티키 서식 공용화 (`ui_sticky.py`) — 동작 무변경 리팩터링

`StickyNoteWindow` 내부 서식 로직을 재사용 가능한 자유 함수로 추출하고, 기존 핸들러는 그 함수에 **위임**한다(외형·동작 동일). 패널이 쓸 `StickyFormatToolbar`도 추가한다.

**Files:**
- Modify: `ui_sticky.py`
- Test: `tests/test_ui_sticky.py` (기존, 회귀)

- [ ] **Step 1: 자유 함수 추가** — `ui_sticky.py`의 `_TodoTextEdit` 정의 뒤(~278)에 추가

```python
def toggle_bold(text_edit, on: bool) -> None:
    fmt = QTextCharFormat()
    fmt.setFontWeight(QFont.Bold if on else QFont.Normal)
    text_edit.mergeCurrentCharFormat(fmt)


def bold_state(text_edit) -> bool:
    return text_edit.currentCharFormat().fontWeight() >= QFont.Bold


def apply_text_color(text_edit, hex_color: str) -> None:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(hex_color))
    text_edit.mergeCurrentCharFormat(fmt)


def insert_todo(text_edit) -> None:
    """현재 블록이 비어있으면 그 자리에, 아니면 새 블록에 'FA 빈 체크박스 + 공백'을 넣는다."""
    cursor = text_edit.textCursor()
    clean_fmt = QTextCharFormat()
    clean_fmt.setForeground(QColor("#000000"))
    clean_fmt.setFontStrikeOut(False)

    if cursor.block().text() != "":
        cursor.movePosition(QTextCursor.EndOfBlock)
        cursor.insertBlock()
    fa_fmt = QTextCharFormat(clean_fmt)
    fa_fmt.setFontFamilies([_FA_FAMILY])
    fa_fmt.setFontWeight(QFont.Normal)
    cursor.insertText(_UNCHECKED, fa_fmt)
    clean_fmt.setFontWeight(QFont.Normal)
    cursor.setCharFormat(clean_fmt)
    cursor.insertText(" ")

    text_edit.setTextCursor(cursor)
    text_edit.setFocus()
```

- [ ] **Step 2: `StickyNoteWindow` 핸들러를 위임으로 교체** — 동작 동일

`_insert_todo`(~421), `_toggle_bold`(~500), `_apply_text_color`(~514), `_update_format_buttons`(~522)를 다음으로 교체한다.

```python
    def _insert_todo(self):
        insert_todo(self.text_edit)

    def _toggle_bold(self):
        toggle_bold(self.text_edit, self.bold_btn.isChecked())

    def _apply_text_color(self, hex_color: str):
        self._text_color = hex_color
        apply_text_color(self.text_edit, hex_color)
        self.text_color_btn.set_bar_color(hex_color)

    def _update_format_buttons(self):
        self.bold_btn.setChecked(bold_state(self.text_edit))
```

> `bold_btn`/`todo_btn`/`text_color_btn` 버튼 자체와 헤더 구성은 그대로 둔다(기존 테스트가 존재를 검증).

- [ ] **Step 3: `StickyFormatToolbar` 위젯 추가** — `ui_sticky.py` 하단(`StickyNoteWindow` 정의 앞 또는 뒤)에 추가

```python
class StickyFormatToolbar(QWidget):
    """패널 등에서 재사용하는 공용 서식 툴바(대상 QTextEdit에 시그널로 작용)."""
    bold_toggled = Signal(bool)
    todo_requested = Signal()
    text_color_picked = Signal(str)
    bg_color_picked = Signal(str)

    _BTN_STYLE = """
        QPushButton {
            font-size: 12px; font-weight: bold;
            min-width: 24px; max-width: 24px;
            min-height: 22px; max-height: 22px;
            border-radius: 4px;
            border: 1px solid rgba(0,0,0,40);
            background: rgba(255,255,255,120);
        }
        QPushButton:hover { background: rgba(0,0,0,25); }
        QPushButton:checked { background: rgba(0,120,212,60); border: 1px solid #0078D4; }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.bg_btn = QPushButton(self)
        self.bg_btn.setFixedSize(24, 22)
        self.bg_btn.setToolTip("배경 색상")
        self.bg_btn.setFocusPolicy(Qt.NoFocus)
        self.bg_btn.clicked.connect(self._pick_bg_color)
        layout.addWidget(self.bg_btn)

        self.bold_btn = QPushButton("B", self)
        self.bold_btn.setCheckable(True)
        self.bold_btn.setToolTip("굵게")
        self.bold_btn.setFocusPolicy(Qt.NoFocus)
        self.bold_btn.setStyleSheet(self._BTN_STYLE + "QPushButton { font-family: serif; }")
        self.bold_btn.clicked.connect(lambda: self.bold_toggled.emit(self.bold_btn.isChecked()))
        layout.addWidget(self.bold_btn)

        self.todo_btn = QPushButton("✓", self)
        self.todo_btn.setToolTip("할 일 추가")
        self.todo_btn.setFocusPolicy(Qt.NoFocus)
        self.todo_btn.setStyleSheet(self._BTN_STYLE)
        self.todo_btn.clicked.connect(self.todo_requested.emit)
        layout.addWidget(self.todo_btn)

        self.text_color_btn = _TextColorButton(self)
        self.text_color_btn.setFocusPolicy(Qt.NoFocus)
        self.text_color_btn.clicked.connect(self._pick_text_color)
        layout.addWidget(self.text_color_btn)

        layout.addStretch()

    def set_bold_state(self, on: bool) -> None:
        self.bold_btn.setChecked(on)

    def set_bg_swatch(self, hex_color: str) -> None:
        self.bg_btn.setStyleSheet(
            f"QPushButton {{ background: {hex_color}; border-radius: 4px;"
            "border: 1px solid rgba(0,0,0,60); }"
            "QPushButton:hover { border: 2px solid rgba(0,0,0,140); }"
        )

    def _pick_text_color(self):
        popup = _ColorGridPopup(TEXT_COLORS, cols=4, parent=self)
        popup.color_selected.connect(self._on_text_color)
        pos = self.text_color_btn.mapToGlobal(QPoint(0, self.text_color_btn.height() + 4))
        popup.move(pos)
        popup.show()

    def _on_text_color(self, hex_color: str):
        self.text_color_btn.set_bar_color(hex_color)
        self.text_color_picked.emit(hex_color)

    def _pick_bg_color(self):
        popup = _ColorGridPopup(STICKY_COLORS, cols=4, parent=self)
        popup.color_selected.connect(self.bg_color_picked.emit)
        pos = self.bg_btn.mapToGlobal(QPoint(0, self.bg_btn.height() + 4))
        popup.move(pos)
        popup.show()
```

- [ ] **Step 4: 회귀 테스트**

Run: `python -m pytest tests/test_ui_sticky.py -q`
Expected: PASS (위임으로 동작 동일)

- [ ] **Step 5: 단위 테스트 추가** — `tests/test_ui_sticky.py` 하단

```python
def test_format_helpers_apply_bold(qtbot, qapp):
    from ui_sticky import _TodoTextEdit, toggle_bold, bold_state
    edit = _TodoTextEdit()
    qtbot.addWidget(edit)
    edit.setPlainText("굵게")
    edit.selectAll()
    toggle_bold(edit, True)
    assert "font-weight" in edit.toHtml()
    assert bold_state(edit) is True
```

> `qapp` 픽스처는 이 파일에 이미 존재한다(없으면 다른 테스트 파일과 동일 패턴으로 추가).

- [ ] **Step 6: 통과 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_format_helpers_apply_bold -v`
Expected: PASS

- [ ] **Step 7: 체크포인트** — 완료.

---

### Task 5: 스티키 패널 공용 툴바 + 포커스 추적 + 배경색 (`ui_sticky_panel.py`)

**Files:**
- Modify: `ui_sticky_panel.py` (`StickyMiniCard` ~15, `StickySidePanel` ~76)
- Test: `tests/test_ui_sticky_panel.py`

- [ ] **Step 1: 실패 테스트 추가** — `tests/test_ui_sticky_panel.py` 하단

```python
from PySide6.QtGui import QFont


def test_panel_toolbar_bold_applies_to_active_card(app_dir, qtbot, qapp):
    from ui_sticky_panel import StickySidePanel
    nid = db.create_sticky_note("memo")
    panel = StickySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    card = panel._cards[0]
    panel._set_active_card(card)
    card.text_edit.setPlainText("굵게 대상")
    card.text_edit.selectAll()
    panel._toolbar.bold_toggled.emit(True)
    assert "font-weight" in card.text_edit.toHtml()


def test_panel_toolbar_bg_color_updates_db(app_dir, qtbot, qapp):
    from ui_sticky_panel import StickySidePanel
    nid = db.create_sticky_note("memo")
    panel = StickySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    panel._set_active_card(panel._cards[0])
    panel._toolbar.bg_color_picked.emit("#D0FFF1")
    notes = {n["id"]: n for n in db.get_open_sticky_notes()}
    assert notes[nid]["color"] == "#D0FFF1"
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_ui_sticky_panel.py::test_panel_toolbar_bold_applies_to_active_card -v`
Expected: FAIL — `AttributeError: 'StickySidePanel' object has no attribute '_toolbar'`

- [ ] **Step 3: 포커스 인지 텍스트 에디트 + 카드 시그널** — `ui_sticky_panel.py`

상단 import에 추가:
```python
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from ui_sticky import STICKY_HEADER_COLORS, _TodoTextEdit, STICKY_COLORS
```

`StickyMiniCard` 위에 포커스 인지 에디트를 추가:
```python
class _PanelTodoEdit(_TodoTextEdit):
    focused = Signal()

    def focusInEvent(self, event):
        self.focused.emit()
        super().focusInEvent(event)
```

`StickyMiniCard`에서 `self.text_edit = _TodoTextEdit(self)`를 `_PanelTodoEdit`로 교체하고, 카드에 `focused`/`apply_color`를 추가한다.

```python
class StickyMiniCard(QWidget):
    focused = Signal(object)        # 자기 자신을 전달

    def __init__(self, note_id, content, color, parent=None):
        super().__init__(parent)
        ...
        self.text_edit = _PanelTodoEdit(self)
        self.text_edit.focused.connect(lambda: self.focused.emit(self))
        ...

    def apply_color(self, hex_color: str):
        """배경색 변경 + DB 저장 + 카드 외형 갱신."""
        self._color = hex_color
        header_hex = STICKY_HEADER_COLORS.get(hex_color, hex_color)
        self._strip.setStyleSheet(
            f"#miniStrip{{background:{header_hex};"
            "border-top-left-radius:8px;border-top-right-radius:8px;}"
        )
        c = QColor(hex_color)
        r, g, b = c.red(), c.green(), c.blue()
        br, bg, bb = max(0, r - 30), max(0, g - 30), max(0, b - 30)
        self.setStyleSheet(
            f"#stickyMiniCard{{background:rgba({r},{g},{b},255);"
            f"border:1px solid rgba({br},{bg},{bb},180);border-radius:8px;}}"
        )
        try:
            db.update_sticky_note(self.note_id, color=hex_color)
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.error("미니 스티키 색상 저장 실패 (id=%s): %s", self.note_id, e)
```

- [ ] **Step 4: 패널 헤더에 공용 툴바 + 활성 카드 추적** — `StickySidePanel`

`StickySidePanel.__init__`에서 제목 라벨 다음에 툴바를 추가한다.
```python
        from ui_sticky import StickyFormatToolbar
        title = QLabel("스티키 노트", self)
        title.setStyleSheet("font-size:13px;font-weight:700;color:#212121;")
        outer.addWidget(title)

        self._active_card = None
        self._toolbar = StickyFormatToolbar(self)
        self._toolbar.bold_toggled.connect(self._on_bold)
        self._toolbar.todo_requested.connect(self._on_todo)
        self._toolbar.text_color_picked.connect(self._on_text_color)
        self._toolbar.bg_color_picked.connect(self._on_bg_color)
        self._toolbar.setEnabled(False)
        outer.addWidget(self._toolbar)
```

`reload()`에서 각 카드의 `focused`를 연결한다(카드 생성 루프 내):
```python
        for note in notes:
            card = StickyMiniCard(note["id"], note["content"], note["color"], self._list)
            card.focused.connect(self._set_active_card)
            self._cards.append(card)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)
        self._empty_label.setVisible(not self._cards)
        if self._active_card not in self._cards:
            self._active_card = None
            self._toolbar.setEnabled(False)
```

패널에 동작 메서드를 추가한다:
```python
    def _set_active_card(self, card):
        if self._active_card is card:
            return
        prev = self._active_card
        if prev is not None:
            try:
                prev.text_edit.cursorPositionChanged.disconnect(self._sync_toolbar)
            except (TypeError, RuntimeError):
                pass
        self._active_card = card
        self._toolbar.setEnabled(True)
        self._toolbar.set_bg_swatch(card._color)
        card.text_edit.cursorPositionChanged.connect(self._sync_toolbar)
        self._sync_toolbar()

    def _sync_toolbar(self):
        if self._active_card is None:
            return
        from ui_sticky import bold_state
        self._toolbar.set_bold_state(bold_state(self._active_card.text_edit))

    def _on_bold(self, on):
        if self._active_card is None:
            return
        from ui_sticky import toggle_bold
        toggle_bold(self._active_card.text_edit, on)

    def _on_todo(self):
        if self._active_card is None:
            return
        from ui_sticky import insert_todo
        insert_todo(self._active_card.text_edit)

    def _on_text_color(self, hex_color):
        if self._active_card is None:
            return
        from ui_sticky import apply_text_color
        apply_text_color(self._active_card.text_edit, hex_color)

    def _on_bg_color(self, hex_color):
        if self._active_card is None:
            return
        self._active_card.apply_color(hex_color)
```

> `StickyMiniCard`는 `_strip`/`_color`를 이미 보유한다(현재 코드 기준). `apply_color`가 이를 갱신한다.

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/test_ui_sticky_panel.py -v`
Expected: PASS (신규 2 + 기존 통과)

- [ ] **Step 6: 체크포인트** — 완료.

---

### Task 6: 미니 카드 X 삭제(휴지통) + `note_trashed` 전파

**Files:**
- Modify: `ui_sticky_panel.py`, `ui_main.py`
- Test: `tests/test_ui_sticky_panel.py`, `tests/test_widget_limits.py`(또는 `test_ui_sticky_panel.py`)

- [ ] **Step 1: 실패 테스트 추가** — `tests/test_ui_sticky_panel.py`

```python
def test_panel_card_delete_trashes_note(app_dir, qtbot, qapp, monkeypatch):
    from ui_sticky_panel import StickySidePanel
    nid = db.create_sticky_note("memo")
    panel = StickySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    card = panel._cards[0]
    monkeypatch.setattr(card, "_confirm_delete", lambda: True)

    received = []
    panel.note_trashed.connect(received.append)
    card._on_delete()

    assert len(panel._cards) == 0
    assert all(n["id"] != nid for n in db.get_open_sticky_notes())
    assert any(n["id"] == nid for n in db.get_trashed_sticky_notes())
    assert received == [nid]


def test_main_panel_delete_removes_floating(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    nid = db.create_sticky_note("memo")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    assert nid in win._sticky_windows
    win._on_panel_note_trashed(nid)
    assert nid not in win._sticky_windows
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_ui_sticky_panel.py::test_panel_card_delete_trashes_note -v`
Expected: FAIL — `AttributeError: ... '_on_delete'`

- [ ] **Step 3: 카드 X 버튼 + 확인 + 시그널** — `StickyMiniCard`

import에 추가: `from qfluentwidgets import TransparentToolButton, FluentIcon as FIF, Dialog`

`StickyMiniCard`에 `delete_requested = Signal(int)`를 추가하고, 색상 스트립 위에 X 버튼을 올린다. 스트립(`self._strip`) 생성부 다음에:
```python
        self.delete_btn = TransparentToolButton(FIF.CLOSE, self._strip)
        self.delete_btn.setFixedSize(16, 16)
        self.delete_btn.setToolTip("휴지통으로")
        self.delete_btn.move(0, 0)            # resizeEvent에서 우상단 재배치
        self.delete_btn.clicked.connect(self._on_delete)
```

스트립 우상단 정렬을 위해 카드에 `resizeEvent`를 추가:
```python
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.delete_btn.move(self.width() - self.delete_btn.width() - 2, -4)
```

삭제 메서드:
```python
    def _confirm_delete(self) -> bool:
        dlg = Dialog(
            "노트 정리",
            "이 노트를 휴지통으로 이동하시겠습니까?\n휴지통에서 다시 복구할 수 있습니다.",
            self,
        )
        dlg.yesButton.setText("휴지통으로")
        dlg.cancelButton.setText("취소")
        accepted = bool(dlg.exec())
        dlg.deleteLater()
        return accepted

    def _on_delete(self):
        if not self._confirm_delete():
            return
        self.delete_requested.emit(self.note_id)
```

- [ ] **Step 4: 패널이 삭제 처리 + 전파** — `StickySidePanel`

`note_trashed = Signal(int)`를 클래스에 추가. `reload()`의 카드 연결부에 삭제 연결을 더한다:
```python
            card.focused.connect(self._set_active_card)
            card.delete_requested.connect(self._on_card_delete)
```
처리 메서드:
```python
    def _on_card_delete(self, note_id: int):
        try:
            db.trash_sticky_note(note_id)
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.error("미니 스티키 휴지통 이동 실패 (id=%s): %s", note_id, e)
            return
        self.note_trashed.emit(note_id)
        self.reload()
```

- [ ] **Step 5: 메인이 플로팅 정리** — `ui_main.py`

`StickySidePanel`을 생성하는 `_apply_sticky_side_panel`(~1877-1879)에서, 패널 생성 직후 시그널을 연결한다.
```python
            if self._sticky_side_panel is None:
                from ui_sticky_panel import StickySidePanel
                self._sticky_side_panel = StickySidePanel(self._expanded_row)
                self._sticky_side_panel.note_trashed.connect(self._on_panel_note_trashed)
```
핸들러 추가:
```python
    def _on_panel_note_trashed(self, note_id: int):
        win = self._sticky_windows.pop(note_id, None)
        if win is not None:
            win.note_closed.disconnect()      # 중복 정리 방지(있다면)
            win.close()
            win.deleteLater()
```
> `note_closed.disconnect()`가 연결이 없을 때 예외를 던지면 `try/except (TypeError, RuntimeError): pass`로 감싼다.

- [ ] **Step 6: 통과 확인**

Run: `python -m pytest tests/test_ui_sticky_panel.py -v`
Expected: PASS

- [ ] **Step 7: 체크포인트** — 완료.

---

## Phase 3 — '크게' 모드에 D-Day·집중 미니 패널 통합

### Task 7: D-Day 미니 패널 (`ui_dday_panel.py` 신규)

**Files:**
- Create: `ui_dday_panel.py`
- Test: `tests/test_ui_dday_panel.py` (신규)

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_ui_dday_panel.py`

```python
# tests/test_ui_dday_panel.py
import pytest
from PySide6.QtWidgets import QApplication

import database as db


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_dday_panel_reload_lists_open(app_dir, qtbot, qapp):
    from ui_dday_panel import DDaySidePanel
    db.create_dday_widget("마감", "2026-12-31")
    db.create_dday_widget("시험", "2026-11-01")
    panel = DDaySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    assert len(panel._cards) == 2


def test_dday_panel_empty_state(app_dir, qtbot, qapp):
    from ui_dday_panel import DDaySidePanel
    panel = DDaySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    assert len(panel._cards) == 0
    assert panel._empty_label.isVisibleTo(panel)


def test_dday_card_shows_countdown(app_dir, qtbot, qapp):
    from ui_dday_panel import DDayMiniCard
    wid = db.create_dday_widget("마감", "2026-06-20")  # 기준일 2026-06-12 → D-8
    data = next(w for w in db.get_open_dday_widgets() if w["id"] == wid)
    card = DDayMiniCard(wid, data)
    qtbot.addWidget(card)
    assert "마감" in card.name_label.text()
    assert card.count_label.text().startswith("D")
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_ui_dday_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ui_dday_panel'`

- [ ] **Step 3: `ui_dday_panel.py` 구현**

```python
# ui_dday_panel.py - '크게' 모드 우측 컬럼의 편집 가능한 미니 D-Day 패널
import logging
import sqlite3
from datetime import date

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QHBoxLayout, QWidget

import database as db
from ui_sticky import STICKY_HEADER_COLORS

_logger = logging.getLogger("app_error")
WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


class DDayMiniCard(QWidget):
    """우측 패널용 미니 D-Day 카드(더블클릭 편집)."""
    edit_requested = Signal(int)

    def __init__(self, widget_id, data, parent=None):
        super().__init__(parent)
        self.widget_id = widget_id
        self._name = data.get("name", "")
        self._target_date = data.get("target_date", "")
        self._color = data.get("color", db.DEFAULT_DDAY_COLOR)
        self.setObjectName("ddayMiniCard")
        self.setAttribute(Qt.WA_StyledBackground, True)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(8)

        self.name_label = QLabel(self._name, self)
        self.name_label.setStyleSheet("font-size:12px;font-weight:600;color:#222;background:transparent;")
        row.addWidget(self.name_label, 1)

        self.count_label = QLabel("", self)
        self.count_label.setStyleSheet("font-size:13px;font-weight:700;background:transparent;")
        row.addWidget(self.count_label, 0, Qt.AlignRight)

        self._apply_color(self._color)
        self._update_countdown()

    def _apply_color(self, hex_color):
        c = QColor(STICKY_HEADER_COLORS.get(hex_color, hex_color))
        r, g, b = c.red(), c.green(), c.blue()
        br, bg, bb = max(0, r - 30), max(0, g - 30), max(0, b - 30)
        self.setStyleSheet(
            f"#ddayMiniCard{{background:rgba({r},{g},{b},255);"
            f"border:1px solid rgba({br},{bg},{bb},180);border-radius:8px;}}"
        )

    def _update_countdown(self):
        try:
            target = date.fromisoformat(self._target_date)
        except (ValueError, TypeError):
            self.count_label.setText("?")
            return
        delta = (target - date.today()).days
        if delta > 0:
            self.count_label.setText(f"D-{delta}")
            self.count_label.setStyleSheet("font-size:13px;font-weight:700;color:#0078D4;background:transparent;")
        elif delta == 0:
            self.count_label.setText("D-Day")
            self.count_label.setStyleSheet("font-size:13px;font-weight:700;color:#D32F2F;background:transparent;")
        else:
            self.count_label.setText(f"D+{abs(delta)}")
            self.count_label.setStyleSheet("font-size:13px;font-weight:700;color:#888;background:transparent;")

    def refresh(self):
        self._update_countdown()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.edit_requested.emit(self.widget_id)


class DDaySidePanel(QWidget):
    """'크게' 모드 우측 컬럼의 미니 D-Day 패널."""
    edit_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ddaySidePanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMaximumHeight(170)
        self.setStyleSheet(
            "#ddaySidePanel{background:#FFFFFF;border:1px solid rgba(180,190,220,180);}"
        )
        self._cards = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        title = QLabel("D-Day", self)
        title.setStyleSheet("font-size:13px;font-weight:700;color:#212121;")
        outer.addWidget(title)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        outer.addWidget(self._scroll, 1)

        self._list = QWidget()
        self._list.setObjectName("ddayMiniList")
        self._list.setStyleSheet("#ddayMiniList{background:transparent;}")
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()
        self._scroll.setWidget(self._list)

        self._empty_label = QLabel("표시할 D-Day가 없습니다.", self._list)
        self._empty_label.setStyleSheet("color:#888888;font-size:12px;")
        self._list_layout.insertWidget(0, self._empty_label)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(60_000)
        self._refresh_timer.timeout.connect(self._refresh_all)
        self._refresh_timer.start()

    def reload(self):
        for card in self._cards:
            self._list_layout.removeWidget(card)
            card.deleteLater()
        self._cards = []
        try:
            widgets = db.get_open_dday_widgets()
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.error("미니 D-Day 목록 조회 실패: %s", e)
            widgets = []
        for w in widgets:
            card = DDayMiniCard(w["id"], w, self._list)
            card.edit_requested.connect(self.edit_requested.emit)
            self._cards.append(card)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)
        self._empty_label.setVisible(not self._cards)

    def _refresh_all(self):
        for card in self._cards:
            card.refresh()
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_ui_dday_panel.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 체크포인트** — 완료.

---

### Task 8: 집중 미니 패널 — 라이브 미러 (`ui_focus_panel.py` 신규)

집중은 1개만 존재한다. 미니 카드는 **숨긴 채 살아 있는 `FocusWidgetWindow`의 `timer_model`을 매초 미러링**한다(표시 전용).

**Files:**
- Create: `ui_focus_panel.py`
- Test: `tests/test_ui_focus_panel.py` (신규)

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_ui_focus_panel.py`

```python
# tests/test_ui_focus_panel.py
from datetime import datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication

import database as db


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_source(qtbot, goal="미러"):
    from ui_focus import FocusWidgetWindow
    wid = db.create_focus_widget(goal, "25/5")
    data = next(w for w in db.get_open_focus_widgets() if w["id"] == wid)
    src = FocusWidgetWindow(wid, data)
    qtbot.addWidget(src)
    return src


def test_focus_mini_card_mirrors_progress(app_dir, qtbot, qapp):
    from ui_focus_panel import FocusMiniCard
    cur = datetime(2026, 4, 27, 9, 0, 0)
    src = _make_source(qtbot)
    src.timer_model._now = lambda: cur
    src._start_session()
    cur = cur + timedelta(minutes=5)        # 5/25 = 20%
    card = FocusMiniCard(src)
    qtbot.addWidget(card)
    card._sync()
    assert card.percent_label.text() == "20%"
    assert card.remaining_label.text() == "20:00"
    assert "미러" in card.goal_label.text()


def test_focus_panel_bind_and_clear(app_dir, qtbot, qapp):
    from ui_focus_panel import FocusSidePanel
    src = _make_source(qtbot)
    panel = FocusSidePanel()
    qtbot.addWidget(panel)
    panel.bind(src)
    assert panel._card is not None
    assert panel._empty_label.isHidden()
    panel.clear()
    assert panel._card is None
    assert not panel._empty_label.isHidden()
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_ui_focus_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ui_focus_panel'`

- [ ] **Step 3: `ui_focus_panel.py` 구현**

```python
# ui_focus_panel.py - '크게' 모드 우측 컬럼의 집중 모드 미니 패널(라이브 미러)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QHBoxLayout, QVBoxLayout, QWidget

from ui_focus import FocusProgressRing, FOCUS_ACCENT_COLOR


class FocusMiniCard(QWidget):
    """숨긴 채 살아 있는 FocusWidgetWindow의 타이머를 미러링하는 표시 전용 카드."""

    def __init__(self, source_window, parent=None):
        super().__init__(parent)
        self._source = source_window
        self.setObjectName("focusMiniCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "#focusMiniCard{background:rgba(255,255,255,235);"
            "border:1px solid rgba(255,90,69,90);border-radius:8px;}"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)

        self.ring = FocusProgressRing(self)
        row.addWidget(self.ring)

        col = QVBoxLayout()
        col.setSpacing(0)
        self.goal_label = QLabel("집중 목표", self)
        self.goal_label.setStyleSheet("font-size:12px;font-weight:700;color:#172033;background:transparent;")
        col.addWidget(self.goal_label)

        sub = QHBoxLayout()
        sub.setSpacing(8)
        self.percent_label = QLabel("0%", self)
        self.percent_label.setStyleSheet(
            f"font-size:14px;font-weight:700;color:{FOCUS_ACCENT_COLOR};background:transparent;"
        )
        sub.addWidget(self.percent_label)
        self.remaining_label = QLabel("00:00", self)
        self.remaining_label.setStyleSheet("font-size:12px;color:#555;background:transparent;")
        sub.addWidget(self.remaining_label)
        sub.addStretch()
        col.addLayout(sub)
        row.addLayout(col, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._sync)
        self._timer.start()
        self._sync()

    def _sync(self):
        src = self._source
        if src is None:
            return
        tm = src.timer_model
        self.ring.set_progress(tm.progress_ratio())
        self.percent_label.setText(f"{tm.progress_percent()}%")
        self.remaining_label.setText(src._format_remaining(tm.remaining_seconds()))
        self.goal_label.setText("휴식 중" if tm.phase == "break" else (src._goal or "집중 목표"))


class FocusSidePanel(QWidget):
    """'크게' 모드 우측 컬럼의 집중 모드 미니 패널(0~1개)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("focusSidePanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMaximumHeight(110)
        self.setStyleSheet(
            "#focusSidePanel{background:#FFFFFF;border:1px solid rgba(180,190,220,180);}"
        )
        self._card = None

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(12, 10, 12, 10)
        self._outer.setSpacing(8)

        title = QLabel("집중 모드", self)
        title.setStyleSheet("font-size:13px;font-weight:700;color:#212121;")
        self._outer.addWidget(title)

        self._empty_label = QLabel("진행 중인 집중 모드가 없습니다.", self)
        self._empty_label.setStyleSheet("color:#888888;font-size:12px;")
        self._outer.addWidget(self._empty_label)
        self._outer.addStretch()

    def bind(self, source_window):
        self.clear()
        self._card = FocusMiniCard(source_window, self)
        self._outer.insertWidget(2, self._card)   # title, empty 다음
        self._empty_label.hide()

    def clear(self):
        if self._card is not None:
            self._outer.removeWidget(self._card)
            self._card.deleteLater()
            self._card = None
        self._empty_label.show()
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_ui_focus_panel.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: 체크포인트** — 완료.

---

### Task 9: 메인 통합 — large 모드 4구획 + 패널 동기화 (`ui_main.py`)

large 모드 우측 컬럼을 `[일정 → D-Day → 집중 → 스티키]` 순서로 구성하고, 진입/이탈/생성 시 D-Day·집중을 패널로 동기화한다. **세 패널(스티키 포함)은 large에서 항상 존재**하며, 빈 경우 컴팩트 빈 상태로 표시한다.

**Files:**
- Modify: `ui_main.py` (`__init__` ~640-672, `_apply_calendar_scale` ~836-877, `_apply_sticky_side_panel` ~1867-1905, `_load_open_dday_widgets` ~1958, `_on_new_dday_widget` ~1927, `_load_open_focus_widgets` ~2013, `_on_new_focus_widget` ~1978)
- Test: `tests/test_ui_sticky_panel.py`(순서 테스트 수정), `tests/test_ui_dday_panel.py`/신규 메인 테스트

- [ ] **Step 1: 기존 순서 테스트를 4구획으로 수정** — `tests/test_ui_sticky_panel.py`

`test_reapplying_large_keeps_card_order`(~84)를 다음으로 교체한다.
```python
def test_reapplying_large_keeps_card_order(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    db.create_sticky_note("memo")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    expected = ["schedulePanel", "ddaySidePanel", "focusSidePanel", "stickySidePanel"]
    assert _expanded_row_order(win) == expected
    win._apply_calendar_scale()
    assert _expanded_row_order(win) == expected
    win._apply_calendar_scale()
    assert _expanded_row_order(win) == expected
```

- [ ] **Step 2: 신규 통합 테스트 추가** — `tests/test_ui_sticky_panel.py`

```python
def test_large_mode_hides_dday_focus_and_shows_panels(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    db.create_sticky_note("memo")
    db.create_dday_widget("마감", "2026-12-31")
    db.create_focus_widget("집중", "25/5")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win = MainCalendarWindow()
    qtbot.addWidget(win)

    assert win._dday_in_panel_mode is True
    assert win._focus_in_panel_mode is True
    assert all(not w.isVisible() for w in win._dday_windows.values())
    assert all(not w.isVisible() for w in win._focus_windows.values())
    assert len(win._dday_side_panel._cards) == 1
    assert win._focus_side_panel._card is not None
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/test_ui_sticky_panel.py::test_large_mode_hides_dday_focus_and_shows_panels -v`
Expected: FAIL — `AttributeError: ... '_dday_in_panel_mode'`

- [ ] **Step 4: `__init__` 상태 필드 추가** — `ui_main.py` (~643-644 인근)

```python
        self._sticky_side_panel = None
        self._sticky_in_panel_mode = False
        self._dday_side_panel = None
        self._dday_in_panel_mode = False
        self._focus_side_panel = None
        self._focus_in_panel_mode = False
```

- [ ] **Step 5: `_apply_calendar_scale`에 패널 적용 추가** — `ui_main.py` (~857-858)

`self._reparent_schedule_panel(scale)` 다음, `self._apply_sticky_side_panel(...)` **이전**에 두 줄을 삽입한다(순서: 일정 → D-Day → 집중 → 스티키).
```python
        self._reparent_schedule_panel(scale)
        self._apply_dday_side_panel(scale == "large")
        self._apply_focus_side_panel(scale == "large")
        self._apply_sticky_side_panel(scale == "large")
```

- [ ] **Step 6: D-Day 패널 적용 메서드** — `ui_main.py` (집중/D-Day 영역에 추가)

```python
    def _apply_dday_side_panel(self, large: bool):
        if large and not self._dday_in_panel_mode:
            for win in self._dday_windows.values():
                win.hide()
            if self._dday_side_panel is None:
                from ui_dday_panel import DDaySidePanel
                self._dday_side_panel = DDaySidePanel(self._expanded_row)
                self._dday_side_panel.edit_requested.connect(self._on_panel_dday_edit)
            self._refresh_dday_panel()
            self._dday_in_panel_mode = True
        elif not large and self._dday_in_panel_mode:
            if self._dday_side_panel is not None:
                if self._expanded_row is not None and self._expanded_row.layout() is not None:
                    self._expanded_row.layout().removeWidget(self._dday_side_panel)
                self._dday_side_panel.hide()
                self._dday_side_panel.setParent(None)
            if self.isVisible():
                for win in self._dday_windows.values():
                    win.show()
            self._dday_in_panel_mode = False

        if large and self._dday_side_panel is not None and self._expanded_row is not None:
            layout = self._expanded_row.layout()
            if layout is not None:
                self._dday_side_panel.setParent(self._expanded_row)
                layout.removeWidget(self._dday_side_panel)
                layout.addWidget(self._dday_side_panel, 0)   # 자연 높이(maxHeight 캡)
                self._dday_side_panel.show()

    def _refresh_dday_panel(self):
        if self._dday_side_panel is not None:
            self._dday_side_panel.reload()

    def _on_panel_dday_edit(self, widget_id: int):
        """미니 D-Day 카드 더블클릭 → 편집 다이얼로그(플로팅 창과 동일 동작)."""
        win = self._dday_windows.get(widget_id)
        if win is None:
            return
        from ui_dday import DDayCreateDialog
        from PySide6.QtWidgets import QDialog
        dlg = DDayCreateDialog(self, win._name, win._target_date)
        if dlg.exec() == QDialog.Accepted:
            name, target_date = dlg.get_result()
            win._name = name
            win._target_date = target_date
            win.name_label.setText(name)
            win._update_countdown()
            db.update_dday_widget(widget_id, name=name, target_date=target_date)
            self._refresh_dday_panel()
        dlg.deleteLater()
```

- [ ] **Step 7: 집중 패널 적용 메서드** — `ui_main.py`

```python
    def _apply_focus_side_panel(self, large: bool):
        if large and not self._focus_in_panel_mode:
            for win in self._focus_windows.values():
                win.hide()                       # 살아 있는 채로 숨김(타이머 유지)
            if self._focus_side_panel is None:
                from ui_focus_panel import FocusSidePanel
                self._focus_side_panel = FocusSidePanel(self._expanded_row)
            self._refresh_focus_panel()
            self._focus_in_panel_mode = True
        elif not large and self._focus_in_panel_mode:
            if self._focus_side_panel is not None:
                self._focus_side_panel.clear()
                if self._expanded_row is not None and self._expanded_row.layout() is not None:
                    self._expanded_row.layout().removeWidget(self._focus_side_panel)
                self._focus_side_panel.hide()
                self._focus_side_panel.setParent(None)
            if self.isVisible():
                for win in self._focus_windows.values():
                    win.show()
            self._focus_in_panel_mode = False

        if large and self._focus_side_panel is not None and self._expanded_row is not None:
            layout = self._expanded_row.layout()
            if layout is not None:
                self._focus_side_panel.setParent(self._expanded_row)
                layout.removeWidget(self._focus_side_panel)
                layout.addWidget(self._focus_side_panel, 0)
                self._focus_side_panel.show()

    def _refresh_focus_panel(self):
        if self._focus_side_panel is None:
            return
        source = next(iter(self._focus_windows.values()), None)
        if source is not None:
            self._focus_side_panel.bind(source)
        else:
            self._focus_side_panel.clear()
```

- [ ] **Step 8: 로드 메서드가 패널 모드에서 동기화하도록 수정**

`_load_open_dday_widgets`(~1958) 루프 끝(딕셔너리 등록 후)에서, 패널 모드면 숨기고 패널 갱신:
```python
        except (sqlite3.Error, OSError) as e:
            _logger.error("D-Day 위젯 로드 실패: %s", e)
        if self._dday_in_panel_mode:
            for win in self._dday_windows.values():
                win.hide()
            self._refresh_dday_panel()
```

`_load_open_focus_widgets`(~2013) 끝에서도:
```python
        except (sqlite3.Error, OSError) as e:
            _logger.error("집중 모드 위젯 로드 실패: %s", e)
        if self._focus_in_panel_mode:
            for win in self._focus_windows.values():
                win.hide()
            self._refresh_focus_panel()
```

> `__init__` 순서상 `_apply_calendar_scale`(668)가 먼저 패널 모드 플래그를 켜고, `_load_open_dday_widgets`(670)/`_load_open_focus_widgets`(671)가 플로팅 창을 만든 뒤 위 블록이 숨김+패널 바인딩을 수행한다.

- [ ] **Step 9: 패널 모드 중 신규 생성 동기화**

`_on_new_dday_widget`의 생성 성공부 끝(`self._dday_windows[widget_id] = win` 다음)에 추가:
```python
            self._dday_windows[widget_id] = win
            if self._dday_in_panel_mode:
                win.hide()
                self._refresh_dday_panel()
```

`_on_new_focus_widget`의 생성 성공부 끝(`self._focus_windows[widget_id] = win` 다음)에 추가:
```python
            self._focus_windows[widget_id] = win
            if self._focus_in_panel_mode:
                win.hide()
                self._refresh_focus_panel()
```

- [ ] **Step 10: 통과 확인 (신규 + 순서)**

Run: `python -m pytest tests/test_ui_sticky_panel.py -v`
Expected: PASS (순서 4구획 + 신규 통합 테스트 포함)

- [ ] **Step 11: 전체 회귀**

Run: `python -m pytest tests -q`
Expected: PASS (전체)

- [ ] **Step 12: 체크포인트** — 완료.

---

### Task 10: 문서 갱신 (`AGENTS.md`)

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 모듈맵 갱신**

`ui_main.py` 행에 D-Day/집중 미니 패널 통합을 한 줄 덧붙이고, 신규 행을 추가한다.
```markdown
| `ui_dday_panel.py` | `large` 모드 우측 컬럼의 편집 가능한 미니 D-Day 패널(`DDayMiniCard`/`DDaySidePanel`). 더블클릭 편집·1분 갱신. |
| `ui_focus_panel.py` | `large` 모드 우측 컬럼의 집중 미니 패널(`FocusMiniCard`/`FocusSidePanel`). 숨긴 플로팅 집중창의 `FocusTimer`를 매초 미러링(표시 전용). |
```
`ui_sticky.py` 행에 "서식 공용 함수(`toggle_bold`/`insert_todo`/`apply_text_color`/`bold_state`) + `StickyFormatToolbar` 추출" 추가.
`ui_sticky_panel.py` 행에 "공용 서식 툴바·카드별 X(휴지통)·`note_trashed`·배경색 변경" 추가.

- [ ] **Step 2: 제약 갱신**

- "집중 모드 위젯 제한": `enforce_widget_limits()`가 시작 시 **최신(id 큰) 1개만 남기고** 정리, 정리분이 있으면 **모달 경고**. 생성 카운트는 `isVisible()`이 아니라 등록 기준.
- 신규 "D-Day 위젯 제한": 최대 5개, `enforce_widget_limits()`가 최신 5개 유지.
- "확장 캘린더(large)": 우측 컬럼이 `[일정 → D-Day(미니) → 집중(미니, 라이브 미러) → 스티키(메인)]` 4구획, 세 패널 항상 존재(빈 상태 컴팩트). 진입 시 D-Day/집중 플로팅 숨김(집중은 살아있는 채), 이탈 시 복원.
- 스티키 미니 패널: 공용 툴바(굵게·할 일·텍스트 색상·배경 색상)는 **포커스된 카드**에 작용(버튼 `NoFocus`), 카드별 X는 **휴지통 soft-delete** + `note_trashed`로 플로팅 정리.

- [ ] **Step 3: `database.py` 행 갱신** — `enforce_widget_limits()` 및 `get_open_*` ORDER BY 명시.

- [ ] **Step 4: 체크포인트** — 전체 테스트 재확인.

Run: `python -m pytest tests -q`
Expected: PASS

---

## 자기 점검 (작성자 확인 완료)

- **스펙 커버리지**: 기능1(Task 1·2·3) / 기능2(Task 7·8·9) / 기능3(Task 4·5·6) / 문서(Task 10) — 스펙 10절 결정사항 전부 task에 매핑됨.
- **타입/시그니처 일관성**: `enforce_widget_limits() -> dict`, `_widget_trim_result`, `_focus_at_limit/_dday_at_limit`, `StickyFormatToolbar`(시그널 4종), `StickyMiniCard.apply_color/_on_delete/delete_requested/focused`, `StickySidePanel.note_trashed/_set_active_card/_toolbar`, `DDaySidePanel.reload/_cards/edit_requested`, `FocusMiniCard._sync/percent_label/remaining_label/goal_label`, `FocusSidePanel.bind/clear/_card` — task 간 명칭 일치.
- **플레이스홀더 없음**: 모든 코드 단계에 실제 코드/명령/기대값 포함.
- **알려진 리스크**: (a) 집중 라이브 미러에서 숨긴 플로팅 창의 완료/휴식/회고 모달 위치 — 부모를 메인 창으로 둘지 구현 중 확인. (b) large 진입/이탈 시 `setParent`/`removeWidget` 순서로 인한 레이아웃 깜빡임 — 재부착 순서(일정→D-Day→집중→스티키) 고정으로 완화. (c) `__init__` 순서 의존(스케일 적용 후 로드) — Task 9 Step 8의 로드-후 동기화로 처리.

## 검증 결과 (2026-06-12, 4개 병렬 비평가가 실제 코드 대조)

- DB/API(6/6), ui_sticky·ui_sticky_panel(11/11), 테스트 규약(10/10) 전부 **일치 확인**.
- 확인된 사실: `delete_focus_widget`(database.py:906-910) 뒤 삽입 지점 유효 · `get_open_*`에 ORDER BY 없음(안전 추가) · `db.decrypt`/`get_trashed_sticky_notes`/`trash_sticky_note`/`save_setting`/CRUD 시그니처 일치 · `StickyNoteWindow`의 위임 대상 메서드·`bold_btn`/`todo_btn`/`text_color_btn`·`note_closed` 존재 · `Dialog(title,content,parent)` API 일치 · `StickyMiniCard._strip`/`_color` 존재 · `ui_main.py` 임포트(sqlite3/_logger/QTimer/Qt) 가용 · 레이아웃 재배치 기반(`addWidget(schedule,3)`/`removeWidget+addWidget(sticky,7)`) · `FocusProgressRing`/`FOCUS_ACCENT_COLOR`/`FocusWidgetWindow.timer_model`/`_goal`/`_format_remaining` 익스포트 일치 · 신규 테스트의 `app_dir`/`qtbot`/`qapp` 패턴·날짜 비독립 assertion 적합.
- 구현 전 코드에는 enforce 호출·`_warn_widget_trim`·한도 헬퍼·`_*_in_panel_mode`가 **아직 없음**(=본 계획이 추가하는 대상). 정상.
