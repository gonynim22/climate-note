# 스티키 노트 Todo 체크박스 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스티키 노트에 todo 체크박스 기능을 추가한다. 툴바에 체크박스 버튼을 두고 누르면 `☐ ` 시작 줄이 삽입된다. 인라인 `☐`를 클릭하면 `☑`로 바뀌고 그 줄 전체가 회색(dim) + 취소선으로 표시된다. 기존 `strike_btn`은 제거된다.

**Architecture:** 기존 `QTextEdit`를 커스텀 서브클래스 `_TodoTextEdit`로 교체한다. 이 서브클래스는 `mousePressEvent`와 `keyPressEvent`를 오버라이드해 체크박스 토글과 Enter 연속 todo 동작을 수행한다. Todo 상태는 유니코드 `☐`/`☑` 문자와 QTextCharFormat 서식으로만 표현되어 기존 HTML 저장 포맷과 DB 스키마를 변경하지 않는다.

**Tech Stack:** PySide6 (QTextEdit, QTextCursor, QTextCharFormat), pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-04-19-sticky-todo-checkbox-design.md`

---

## 사전 안내

- 이 프로젝트는 git 저장소가 **아니다**. 각 태스크 말미의 "체크포인트" 단계는 커밋 대신 `pytest`와 수동 스모크 테스트로 변경점을 확인하는 지점이다.
- 모든 테스트는 `tests/` 디렉터리에서 `python -m pytest tests/test_ui_sticky.py -v`로 실행한다.
- `tests/conftest.py`에 기존 `app_dir` 픽스처가 있으며, `app_dir`는 `DB_FILE`을 `tmp_path`로 리다이렉트하고 `db.migrate()`를 수행한다. 각 테스트에서 `app_dir`을 인자로 받으면 격리된 DB가 준비된다.
- `tests/test_ui.py`의 `qapp` 세션 픽스처 패턴을 참고하여 `QApplication` 인스턴스를 공유한다. `test_ui_sticky.py`에도 같은 fixture를 복사한다.

## 파일 맵

| 역할 | 파일 | 작업 |
|---|---|---|
| 스티키 노트 UI | `ui_sticky.py` | `strike_btn` 제거, `todo_btn` 추가, `_TodoTextEdit` 도입, `_insert_todo`·`_toggle_todo`·`keyPressEvent` 로직 구현 |
| 테스트 | `tests/test_ui_sticky.py` | 신규 파일. 본 계획의 모든 테스트 수록 |
| 스펙 (참조) | `docs/superpowers/specs/2026-04-19-sticky-todo-checkbox-design.md` | 변경 없음 |

---

## Task 1: 테스트 파일 기반 구축 + `strike_btn` 제거

**Files:**
- Create: `tests/test_ui_sticky.py`
- Modify: `ui_sticky.py` (기존 strike_btn 블록 제거)

- [ ] **Step 1: 테스트 파일 골격 작성 (regression 테스트 포함)**

`tests/test_ui_sticky.py`를 새로 생성한다:

```python
# tests/test_ui_sticky.py - 스티키 노트 UI 테스트
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

import database as db
from ui_sticky import StickyNoteWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def sticky(qtbot, app_dir, qapp):
    """테스트용 스티키 노트 창을 생성해 반환한다."""
    note_id = db.create_sticky_note(note_type="memo", x=100, y=100)
    note_data = {"content": "", "x_pos": 100, "y_pos": 100,
                 "width": 300, "height": 400,
                 "color": db.DEFAULT_STICKY_COLOR}
    win = StickyNoteWindow(note_id, note_data)
    qtbot.addWidget(win)
    return win


def test_strike_button_removed(sticky):
    """리그레션: 기존 strike_btn이 더 이상 존재하지 않는다."""
    assert not hasattr(sticky, "strike_btn")
```

- [ ] **Step 2: 테스트 실행으로 초기 실패 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_strike_button_removed -v`

Expected: FAIL — `assert not hasattr(sticky, "strike_btn")` 가 아직 `strike_btn`이 존재하므로 실패.

- [ ] **Step 3: `ui_sticky.py`에서 `strike_btn` 관련 코드 삭제**

다음 3곳을 삭제한다.

1) `ui_sticky.py:228-235` 블록을 삭제:

```python
        self.strike_btn = QPushButton("S", self)
        self.strike_btn.setCheckable(True)
        self.strike_btn.setToolTip("취소선")
        self.strike_btn.setStyleSheet(
            _fmt_style + "QPushButton { text-decoration: line-through; }"
        )
        self.strike_btn.clicked.connect(self._toggle_strikethrough)
        hdr_layout.addWidget(self.strike_btn)
```

2) `ui_sticky.py:339-342`의 `_toggle_strikethrough` 메서드 전체 삭제:

```python
    def _toggle_strikethrough(self):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(self.strike_btn.isChecked())
        self.text_edit.mergeCurrentCharFormat(fmt)
```

3) `ui_sticky.py:365`의 `_update_format_buttons` 내부 라인 삭제:

```python
        self.strike_btn.setChecked(fmt.fontStrikeOut())
```

삭제 후 `_update_format_buttons` 메서드는 다음과 같이 `bold_btn`만 남는다:

```python
    def _update_format_buttons(self):
        """커서 위치의 서식 상태를 버튼에 반영"""
        fmt = self.text_edit.currentCharFormat()
        self.bold_btn.setChecked(fmt.fontWeight() >= QFont.Bold)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_strike_button_removed -v`

Expected: PASS.

- [ ] **Step 5: 전체 테스트 스위트 회귀 확인**

Run: `python -m pytest tests/ -v`

Expected: 기존 테스트 전원 통과, 새 테스트(`test_strike_button_removed`) 통과. 만약 다른 곳에서 `strike_btn`을 참조한다면(예: 외부 테스트) 여기서 드러난다.

- [ ] **Step 6: 체크포인트**

변경 범위: `ui_sticky.py` (삭제만), `tests/test_ui_sticky.py` (신규). 이 시점에서 취소선 버튼이 UI에서 사라졌지만 기존 노트의 취소선 텍스트 서식은 여전히 렌더된다 (스펙 §2.2).

---

## Task 2: `todo_btn` UI 추가 (동작 없음)

**Files:**
- Modify: `ui_sticky.py` (이전 strike_btn 위치에 todo_btn 추가)
- Modify: `tests/test_ui_sticky.py` (버튼 존재 테스트 추가)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ui_sticky.py`에 추가:

```python
def test_todo_button_exists(sticky):
    """todo_btn이 헤더에 존재하고 올바른 라벨/툴팁을 가진다."""
    assert hasattr(sticky, "todo_btn")
    assert sticky.todo_btn.text() == "☐"
    assert sticky.todo_btn.toolTip() == "할 일 추가"
    assert sticky.todo_btn.isCheckable() is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_todo_button_exists -v`

Expected: FAIL — `hasattr(sticky, "todo_btn")` 가 False.

- [ ] **Step 3: `ui_sticky.py`에 `todo_btn` 추가**

`_build_ui` 안, `bold_btn` 선언 블록(`ui_sticky.py:221-226`) **바로 아래**에 삽입한다 (이전 strike_btn과 같은 위치):

```python
        self.todo_btn = QPushButton("☐", self)
        self.todo_btn.setToolTip("할 일 추가")
        self.todo_btn.setStyleSheet(_fmt_style)
        self.todo_btn.clicked.connect(self._insert_todo)
        hdr_layout.addWidget(self.todo_btn)
```

그리고 `StickyNoteWindow` 클래스에 placeholder 메서드를 추가한다 (다음 Task에서 구현):

```python
    def _insert_todo(self):
        """Todo 삽입: Task 3에서 구현"""
        pass
```

`_apply_color` 메서드(`ui_sticky.py:283` 이후) 바로 앞에 두면 자연스럽다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_todo_button_exists -v`

Expected: PASS.

- [ ] **Step 5: 체크포인트**

UI에 체크박스 버튼이 보이고 누를 수 있지만 아직 아무 동작도 하지 않는다. 변경 범위: `ui_sticky.py` (추가), `tests/test_ui_sticky.py` (테스트 추가).

---

## Task 3: `_insert_todo` 구현 (빈 줄 / 비어있지 않은 줄 분기)

**Files:**
- Modify: `ui_sticky.py` (`_insert_todo` 본문)
- Modify: `tests/test_ui_sticky.py`

- [ ] **Step 1: 실패하는 테스트 2개 작성**

`tests/test_ui_sticky.py`에 추가:

```python
def test_todo_insert_on_empty_line(qtbot, sticky):
    """빈 줄에서 todo_btn 클릭 시 그 줄이 '☐ '로 바뀐다."""
    # 초기 상태: content=="" → 본문 비어있음
    assert sticky.text_edit.toPlainText() == ""

    qtbot.mouseClick(sticky.todo_btn, Qt.LeftButton)

    assert sticky.text_edit.toPlainText() == "☐ "


def test_todo_insert_on_nonempty_line_creates_new_block(qtbot, sticky):
    """텍스트가 있는 줄에서 todo_btn 클릭 시 새 블록이 아래에 생성된다."""
    sticky.text_edit.setPlainText("Hello")
    # 커서를 "Hello" 끝으로 이동
    cursor = sticky.text_edit.textCursor()
    cursor.movePosition(cursor.End)
    sticky.text_edit.setTextCursor(cursor)

    qtbot.mouseClick(sticky.todo_btn, Qt.LeftButton)

    # 2개 블록: "Hello" / "☐ "
    text = sticky.text_edit.toPlainText()
    lines = text.split("\n")
    assert lines[0] == "Hello"
    assert lines[1] == "☐ "
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_todo_insert_on_empty_line tests/test_ui_sticky.py::test_todo_insert_on_nonempty_line_creates_new_block -v`

Expected: FAIL — `_insert_todo`가 현재 `pass`이므로 텍스트가 바뀌지 않는다.

- [ ] **Step 3: `_insert_todo` 구현**

`ui_sticky.py`의 `_insert_todo` 본문을 교체한다. 필요한 임포트가 이미 있는지 확인하고, 없다면 추가한다 (`QTextCursor`):

`ui_sticky.py` 상단의 `from PySide6.QtGui import ...`를 다음과 같이 수정:

```python
from PySide6.QtGui import QColor, QGuiApplication, QFont, QTextCharFormat, QPainter, QTextCursor
```

그리고 `_insert_todo` 본문:

```python
    def _insert_todo(self):
        """Todo 줄 삽입.

        - 현재 블록이 비어있으면 그 자리에 '☐ '를 넣는다.
        - 아니면 현재 블록 끝으로 이동해 새 블록을 만들고 '☐ '를 넣는다.
        - 삽입 전 char format을 기본값(검정·취소선 없음)으로 초기화해,
          직전 커서가 dim·취소선 상태였더라도 새 todo는 깨끗하게 시작한다.
        """
        cursor = self.text_edit.textCursor()
        clean_fmt = QTextCharFormat()
        clean_fmt.setForeground(QColor("#000000"))
        clean_fmt.setFontStrikeOut(False)

        if cursor.block().text() == "":
            cursor.setCharFormat(clean_fmt)
            cursor.insertText("☐ ")
        else:
            cursor.movePosition(QTextCursor.EndOfBlock)
            cursor.insertBlock()
            cursor.setCharFormat(clean_fmt)
            cursor.insertText("☐ ")

        self.text_edit.setTextCursor(cursor)
        self.text_edit.setFocus()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_todo_insert_on_empty_line tests/test_ui_sticky.py::test_todo_insert_on_nonempty_line_creates_new_block -v`

Expected: 둘 다 PASS.

- [ ] **Step 5: 체크포인트**

이제 버튼을 누르면 `☐ `가 삽입된다. 하지만 클릭해도 토글되지 않고, Enter를 눌러도 연속 todo가 안 된다. 다음 태스크에서 추가한다.

---

## Task 4: `_TodoTextEdit` 서브클래스 + 마우스 클릭 토글

**Files:**
- Modify: `ui_sticky.py` (`_TodoTextEdit` 클래스 신설, `_build_ui`에서 `QTextEdit` → `_TodoTextEdit` 교체)
- Modify: `tests/test_ui_sticky.py`

- [ ] **Step 1: 실패하는 테스트 2개 작성**

`tests/test_ui_sticky.py`에 추가 (import는 Task 1에서 이미 추가됨):

```python
def _block_text_at_cursor(text_edit, block_index: int) -> str:
    """n번째 블록의 텍스트 반환 헬퍼"""
    block = text_edit.document().findBlockByNumber(block_index)
    return block.text()


def _char_format_at(text_edit, position: int):
    """position 위치의 문자 서식 반환 헬퍼"""
    cursor = text_edit.textCursor()
    cursor.setPosition(position)
    cursor.setPosition(position + 1, cursor.KeepAnchor)
    return cursor.charFormat()


def _click_on_document_position(qtbot, text_edit, position: int):
    """지정한 document position의 글자 중앙을 viewport 좌표로 클릭한다.

    cursorRect(cursor)는 caret(삽입 지점)의 rect를 반환하므로,
    position과 position+1 양쪽의 caret rect 중간 지점을 찍어 해당 글자 위에 클릭.
    """
    from PySide6.QtCore import QPoint
    c_before = text_edit.textCursor()
    c_before.setPosition(position)
    r_before = text_edit.cursorRect(c_before)

    c_after = text_edit.textCursor()
    c_after.setPosition(position + 1)
    r_after = text_edit.cursorRect(c_after)

    x = (r_before.left() + r_after.left()) // 2
    y = (r_before.top() + r_before.bottom()) // 2
    qtbot.mouseClick(text_edit.viewport(), Qt.LeftButton, pos=QPoint(x, y))


def test_todo_click_toggles_to_checked(qtbot, sticky):
    """☐ 문자 클릭 시 ☑로 바뀌고 그 줄에 dim + 취소선이 적용된다."""
    sticky.text_edit.setPlainText("☐ 우유 사기")

    _click_on_document_position(qtbot, sticky.text_edit, 0)  # ☐ 위치

    assert _block_text_at_cursor(sticky.text_edit, 0) == "☑ 우유 사기"
    # ☑ (pos 0): dim color, strikeout 없음
    fmt_check = _char_format_at(sticky.text_edit, 0)
    assert fmt_check.foreground().color() == QColor("#888888")
    assert fmt_check.fontStrikeOut() is False
    # 텍스트 부분 (pos 2 = '우'): dim color, strikeout 있음
    fmt_text = _char_format_at(sticky.text_edit, 2)
    assert fmt_text.foreground().color() == QColor("#888888")
    assert fmt_text.fontStrikeOut() is True


def test_todo_click_toggles_back_to_unchecked(qtbot, sticky):
    """☑ 문자 클릭 시 ☐로 복귀하고 dim/취소선이 해제된다."""
    # 미리 체크된 상태로 설정
    sticky.text_edit.setPlainText("☐ 우유 사기")
    _click_on_document_position(qtbot, sticky.text_edit, 0)  # 체크
    assert _block_text_at_cursor(sticky.text_edit, 0) == "☑ 우유 사기"

    _click_on_document_position(qtbot, sticky.text_edit, 0)  # 다시 클릭 (언체크)

    assert _block_text_at_cursor(sticky.text_edit, 0) == "☐ 우유 사기"
    fmt_check = _char_format_at(sticky.text_edit, 0)
    assert fmt_check.foreground().color() == QColor("#000000")
    fmt_text = _char_format_at(sticky.text_edit, 2)
    assert fmt_text.foreground().color() == QColor("#000000")
    assert fmt_text.fontStrikeOut() is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_todo_click_toggles_to_checked tests/test_ui_sticky.py::test_todo_click_toggles_back_to_unchecked -v`

Expected: FAIL — 클릭이 일반 커서 이동으로 처리되어 토글이 일어나지 않는다.

- [ ] **Step 3: `_TodoTextEdit` 클래스 정의**

`ui_sticky.py`에서 `StickyNoteWindow` 클래스 **바로 위**에 `_TodoTextEdit`를 추가한다:

```python
class _TodoTextEdit(QTextEdit):
    """체크박스(☐/☑) 클릭 토글을 지원하는 QTextEdit.

    마우스 왼쪽 클릭이 체크박스 문자 위에서 발생하면 상태를 토글하고
    해당 블록 전체의 서식(dim 색·취소선)을 갱신한다.
    """

    _DIM_COLOR = "#888888"
    _DEFAULT_COLOR = "#000000"

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = self.cursorForPosition(event.pos()).position()
            char = self.document().characterAt(pos)
            if char in ("☐", "☑"):
                self._toggle_at(pos, char)
                event.accept()
                return
        super().mousePressEvent(event)

    def _toggle_at(self, pos: int, current: str):
        """pos 위치의 체크박스 문자를 토글하고 블록 서식을 갱신한다."""
        cursor = QTextCursor(self.document())
        block = self.document().findBlock(pos)
        block_start = block.position()
        block_end = block_start + block.length() - 1  # exclusive of block separator

        if current == "☐":
            new_char = "☑"
            # 1) 문자 교체
            cursor.setPosition(pos)
            cursor.setPosition(pos + 1, QTextCursor.KeepAnchor)
            cursor.insertText(new_char)
            # 2) 블록 전체를 dim 색으로
            sel = QTextCursor(self.document())
            sel.setPosition(block_start)
            sel.setPosition(block_end, QTextCursor.KeepAnchor)
            fmt_dim = QTextCharFormat()
            fmt_dim.setForeground(QColor(self._DIM_COLOR))
            sel.mergeCharFormat(fmt_dim)
            # 3) 체크박스 뒤(공백 포함) 전체에 취소선
            text_start = pos + 1  # "☑" 뒤 (space 포함하여 취소선)
            if text_start < block_end:
                sel2 = QTextCursor(self.document())
                sel2.setPosition(text_start)
                sel2.setPosition(block_end, QTextCursor.KeepAnchor)
                fmt_strike = QTextCharFormat()
                fmt_strike.setFontStrikeOut(True)
                sel2.mergeCharFormat(fmt_strike)
        else:  # "☑" → "☐"
            new_char = "☐"
            cursor.setPosition(pos)
            cursor.setPosition(pos + 1, QTextCursor.KeepAnchor)
            cursor.insertText(new_char)
            # 블록 전체 복원: 기본색 + 취소선 해제
            sel = QTextCursor(self.document())
            sel.setPosition(block_start)
            sel.setPosition(block_end, QTextCursor.KeepAnchor)
            fmt_reset = QTextCharFormat()
            fmt_reset.setForeground(QColor(self._DEFAULT_COLOR))
            fmt_reset.setFontStrikeOut(False)
            sel.mergeCharFormat(fmt_reset)
```

- [ ] **Step 4: `_build_ui`에서 `QTextEdit` → `_TodoTextEdit`로 교체**

`ui_sticky.py:256`의 `self.text_edit = QTextEdit(self)`를 다음으로 교체:

```python
        self.text_edit = _TodoTextEdit(self)
```

나머지 `text_edit` 사용부는 그대로 둔다 (`setHtml`, `setPlainText`, `toHtml`, `cursorPositionChanged`, `textChanged` 등은 부모 클래스 메서드).

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_todo_click_toggles_to_checked tests/test_ui_sticky.py::test_todo_click_toggles_back_to_unchecked -v`

Expected: 둘 다 PASS.

`test_todo_click_toggles_to_checked`에서 실패하면 클릭 좌표 계산을 의심하자. `_click_on_document_position` 헬퍼가 글자 중앙을 찍는지 디버깅하려면 `print(text_edit.cursorRect(cursor))`로 확인하면 된다.

- [ ] **Step 6: 전체 테스트 스위트 회귀 확인**

Run: `python -m pytest tests/ -v`

Expected: 모든 기존 테스트 + 새 테스트 4건(`test_strike_button_removed`, `test_todo_button_exists`, insert 2건, toggle 2건) 통과.

- [ ] **Step 7: 체크포인트**

이제 버튼 클릭으로 todo 생성, 마우스 클릭으로 토글이 가능하다. Enter 키는 아직 일반 동작. 변경 범위: `ui_sticky.py` (`_TodoTextEdit` 클래스 신설, text_edit 타입 교체), `tests/test_ui_sticky.py` (테스트 2건 + 헬퍼 추가).

---

## Task 5: Enter 키 처리 (연속 todo / 빈 todo 탈출)

**Files:**
- Modify: `ui_sticky.py` (`_TodoTextEdit.keyPressEvent`)
- Modify: `tests/test_ui_sticky.py`

- [ ] **Step 1: 실패하는 테스트 2개 작성**

`tests/test_ui_sticky.py`에 추가:

```python
def test_enter_on_todo_with_text_continues(qtbot, sticky):
    """☐ 뒤에 텍스트가 있을 때 Enter를 누르면 다음 블록도 '☐ '로 시작한다."""
    sticky.text_edit.setPlainText("☐ 우유 사기")
    # 커서를 블록 끝으로
    cursor = sticky.text_edit.textCursor()
    cursor.movePosition(cursor.End)
    sticky.text_edit.setTextCursor(cursor)

    qtbot.keyClick(sticky.text_edit, Qt.Key_Return)

    lines = sticky.text_edit.toPlainText().split("\n")
    assert lines[0] == "☐ 우유 사기"
    assert lines[1] == "☐ "


def test_enter_on_empty_todo_exits(qtbot, sticky):
    """'☐ '만 있는 빈 todo에서 Enter를 누르면 체크박스가 사라져 일반 줄이 된다."""
    sticky.text_edit.setPlainText("☐ ")
    cursor = sticky.text_edit.textCursor()
    cursor.movePosition(cursor.End)
    sticky.text_edit.setTextCursor(cursor)

    qtbot.keyClick(sticky.text_edit, Qt.Key_Return)

    # 블록이 하나이고 비어있어야 함
    assert sticky.text_edit.document().blockCount() == 1
    assert sticky.text_edit.toPlainText() == ""
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_enter_on_todo_with_text_continues tests/test_ui_sticky.py::test_enter_on_empty_todo_exits -v`

Expected: FAIL — 기본 Enter 처리가 그냥 블록 분리만 하므로 `lines[1]`은 빈 문자열이 되고, 빈 todo 탈출 로직도 없다.

- [ ] **Step 3: `_TodoTextEdit.keyPressEvent` 오버라이드 추가**

`_TodoTextEdit` 클래스 내부에 `keyPressEvent` 메서드를 추가한다 (`_toggle_at` 위든 아래든 무관):

```python
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers():
            cursor = self.textCursor()
            block_text = cursor.block().text()

            if block_text.startswith("☐ ") or block_text.startswith("☑ "):
                if block_text in ("☐ ", "☑ "):
                    # 빈 todo: 체크박스 제거 후 그 자리에 일반 줄로 남긴다.
                    block_cur = QTextCursor(cursor.block())
                    block_cur.select(QTextCursor.BlockUnderCursor)
                    block_cur.removeSelectedText()
                    # removeSelectedText가 블록 구분자까지 먹어 블록 수가 줄어들 수 있음.
                    # 현재 문서가 비어있는 블록 0개가 되면 Qt가 빈 블록 하나를 유지하므로
                    # 추가 처리는 필요 없다.
                    fmt = QTextCharFormat()
                    fmt.setForeground(QColor(self._DEFAULT_COLOR))
                    fmt.setFontStrikeOut(False)
                    self.setCurrentCharFormat(fmt)
                    event.accept()
                    return
                else:
                    # 연속 todo: 기본 처리로 블록 분리 후 새 블록 앞에 '☐ ' 삽입.
                    super().keyPressEvent(event)
                    new_cursor = self.textCursor()
                    fmt = QTextCharFormat()
                    fmt.setForeground(QColor(self._DEFAULT_COLOR))
                    fmt.setFontStrikeOut(False)
                    new_cursor.setCharFormat(fmt)
                    new_cursor.insertText("☐ ")
                    self.setTextCursor(new_cursor)
                    return
        super().keyPressEvent(event)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_enter_on_todo_with_text_continues tests/test_ui_sticky.py::test_enter_on_empty_todo_exits -v`

Expected: 둘 다 PASS.

만약 `test_enter_on_empty_todo_exits`에서 블록 수가 예상과 다르면(예: 2), `QTextCursor.BlockUnderCursor` vs `QTextCursor.Block`의 차이를 의심한다. `BlockUnderCursor`는 선행 블록 구분자까지 포함하여 블록을 완전히 제거하므로, 문서 유일 블록을 지우면 Qt가 자동으로 빈 블록을 유지한다. 첫 블록에서 쓸 경우에는 `select(QTextCursor.LineUnderCursor)` + `removeSelectedText()` + 블록 유지 방식이 더 안전할 수 있다. 테스트 실패 시 다음 대체 구현을 시도:

```python
                    block_cur = QTextCursor(cursor.block())
                    block_cur.select(QTextCursor.LineUnderCursor)
                    block_cur.removeSelectedText()
```

- [ ] **Step 5: 전체 테스트 스위트 회귀 확인**

Run: `python -m pytest tests/ -v`

Expected: 전부 통과.

- [ ] **Step 6: 체크포인트**

이제 완전한 UX가 동작한다: 버튼 → 삽입, Enter → 연속, 빈 todo에서 Enter → 탈출, 클릭 → 토글. 다음 태스크에서 데이터 보존 검증.

---

## Task 6: HTML 왕복 데이터 보존 검증 + 수동 스모크 테스트

**Files:**
- Modify: `tests/test_ui_sticky.py` (왕복 테스트 추가)

- [ ] **Step 1: HTML 왕복 테스트 작성**

`tests/test_ui_sticky.py`에 추가:

```python
def test_html_roundtrip_preserves_todo_state(qtbot, sticky):
    """체크·미체크 todo를 섞은 문서를 HTML로 저장·재로딩해도 상태가 유지된다.

    사용자 데이터 보존 원칙(CLAUDE.md) 검증.
    """
    # 시나리오 구성
    sticky.text_edit.setPlainText("☐ 미완료\n☐ 체크할 것")
    # 2번째 줄의 ☐를 체크
    pos_second_box = sticky.text_edit.toPlainText().find("\n") + 1  # 두 번째 줄 첫 글자
    _click_on_document_position(qtbot, sticky.text_edit, pos_second_box)

    # toHtml()로 직렬화 → 새 에디터에 setHtml()
    html = sticky.text_edit.toHtml()

    from ui_sticky import _TodoTextEdit
    new_edit = _TodoTextEdit()
    qtbot.addWidget(new_edit)
    new_edit.setHtml(html)

    # 텍스트 보존
    text = new_edit.toPlainText()
    lines = text.split("\n")
    assert lines[0] == "☐ 미완료"
    assert lines[1] == "☑ 체크할 것"

    # 체크된 줄 서식 보존
    pos_checked_text = text.find("체")  # 체크된 줄 텍스트 시작
    cursor = new_edit.textCursor()
    cursor.setPosition(pos_checked_text)
    cursor.setPosition(pos_checked_text + 1, cursor.KeepAnchor)
    fmt = cursor.charFormat()
    assert fmt.foreground().color() == QColor("#888888")
    assert fmt.fontStrikeOut() is True

    # 미체크 줄 서식은 기본
    pos_unchecked_text = text.find("미")
    cursor2 = new_edit.textCursor()
    cursor2.setPosition(pos_unchecked_text)
    cursor2.setPosition(pos_unchecked_text + 1, cursor2.KeepAnchor)
    fmt2 = cursor2.charFormat()
    # Qt가 HTML 출력에서 기본색을 명시하지 않을 수 있으므로 "취소선만 없음"을 핵심으로 검증
    assert fmt2.fontStrikeOut() is False
```

- [ ] **Step 2: 테스트 실행**

Run: `python -m pytest tests/test_ui_sticky.py::test_html_roundtrip_preserves_todo_state -v`

Expected: PASS. 만약 색 비교가 실패하면 Qt의 HTML 출력이 RGB 문자열을 `#888888` 대신 `rgb(136,136,136)`으로 쓸 수 있는데, `QColor`는 둘 다 동일하게 비교되므로 문제없어야 한다. 그래도 실패하면 `fmt.foreground().color().name()`으로 프린트해 실제 값을 확인하자.

- [ ] **Step 3: 전체 회귀**

Run: `python -m pytest tests/ -v`

Expected: 전체 통과.

- [ ] **Step 4: 수동 스모크 테스트**

`python main.py`로 앱 실행 후 다음을 확인:

1. 스티키 노트를 새로 하나 생성(혹은 기존 노트 열기).
2. 헤더에 `B`, `☐`, `A` 버튼이 있고 이전 `S`(취소선) 버튼이 **없음**을 확인.
3. `☐` 버튼을 누르면 빈 `☐ ` 줄이 생성되고, 그 상태에서 텍스트 "우유 사기" 입력.
4. 줄 끝에서 Enter → 다음 줄에 `☐ `가 자동으로 시작되는지 확인. "빵 사기" 입력.
5. 빈 줄(`☐ ` 상태)에서 Enter → 체크박스가 사라지고 일반 줄로 돌아가는지 확인.
6. `☐` 문자를 마우스로 클릭 → `☑`로 바뀌고 그 줄 전체가 회색 + 취소선 되는지 확인.
7. 한 번 더 클릭 → `☐`로 복귀, 기본색/취소선 해제.
8. **중요 (데이터 보존 검증):** 노트를 그대로 두고 앱 종료 후 재실행 → 체크 상태·서식이 그대로 복원되는지 확인.
9. **중요 (기존 노트 호환):** 이전 버전에서 쓰던 노트(취소선 서식이 적용된 텍스트 포함)를 열어 취소선이 여전히 렌더되는지 확인.
10. 배경 색상·텍스트 색상·굵게 등 **기존 서식 기능이 정상 동작**하는지 확인.

위 10항목 모두 통과하면 구현 완료.

- [ ] **Step 5: 체크포인트 — 작업 마무리**

변경 파일 요약:
- `ui_sticky.py`: `strike_btn`/`_toggle_strikethrough` 제거, `_TodoTextEdit` 신설, `todo_btn` 추가, `_insert_todo` 구현, `QTextCursor` 임포트 추가.
- `tests/test_ui_sticky.py` (신규): 7개 테스트 + 헬퍼.
- 스펙·계획 문서는 `docs/superpowers/`에 이미 저장됨.

DB 스키마, `database.py`, `security.py`, 기존 노트 데이터는 어떤 변경도 없음. 사용자 데이터 보존 원칙을 완전히 지켰다.
