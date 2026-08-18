# 바탕화면 유지 (Win+D 면역) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Win+D(바탕화면 보기)와 Win+M(모두 최소화)에도 기후노트 메인 창과 모든 플로팅 위젯(스티키·D-Day·집중)이 내려가지 않고 유지되게 한다. 설정 토글(기본 ON)로 실시간 on/off.

**Architecture:** 창을 재부모화(WorkerW/SetParent)하지 않는다 — 그 방식은 과거 "바탕화면 고정 모드"로 시도됐다가 불안정으로 제거됐다. 대신 `QObject` 이벤트 필터(`ShowDesktopKeeper`)가 창의 `WindowStateChange`→`WindowMinimized`를 감지해 `QTimer.singleShot(0, ...)`로 즉시 복원한다. 이 창들은 사용자용 최소화 수단이 없어(최소화 버튼 없음, Boss Key/트레이는 `hide()`) 최소화 = Win+D/Win+M뿐이라 오탐이 없다. 반투명·투명도·드래그·멀티모니터·Win+L 잠금 감지는 무손상.

**Tech Stack:** Python 3.13, PySide6(Qt), SQLite, PySide6-Fluent-Widgets, pytest + pytest-qt.

**참고 스펙:** `docs/superpowers/specs/2026-07-01-desktop-keeper-design.md`

---

## ⚠️ 커밋 정책

이 작업 디렉토리는 **git 저장소가 아니다**(프로젝트 환경 확인됨). 따라서 각 태스크의 "Commit" 단계는 **테스트 그린 확인 체크포인트**로 대체한다. 사용자 별도 VCS(백업/외부 git)가 있으면 각 체크포인트에서 스냅샷을 남긴다.

## 데이터 보존 확인 (AGENTS.md 핵심 원칙)

- 스키마 변경 없음. `app_settings`에 키 1개를 `INSERT OR IGNORE`로 **추가만** 한다.
- `migrate()` 버전만 15 → 16으로 올린다. 기존 키 삭제/변경 없음.
- Export/Import는 `app_settings`를 이미 포함(단 `privacy_pin` 제외)하므로 새 키는 자동 백업/복원된다 — 별도 코드 불필요.

## 파일 구조 (생성/수정 대상)

| 파일 | 책임 | 생성/수정 |
|---|---|---|
| `show_desktop_guard.py` | 최소화 감지 → 복원 (단일 책임, 재사용 단위) | **생성** |
| `database.py` | 새 설정 상수 + v15→v16 마이그레이션 | 수정 |
| `ui_main.py` | keeper 소유·초기화, 창 생성 시 가드 등록, 설정 변경 실시간 반영 | 수정 |
| `ui_settings.py` | "시스템" 섹션 토글 행 + 핸들러 + 콜백 배선 | 수정 |
| `AGENTS.md` | 모듈맵·Key Constraints·마이그레이션 v16 문서화 | 수정 |
| `tests/test_show_desktop_guard.py` | keeper 단위 테스트 | **생성** |
| `tests/test_database.py` | 마이그레이션 v16 테스트 + 기존 v15 단언 갱신 | 수정 |
| `tests/test_ui_keep_desktop.py` | 설정 UI 토글 테스트 | **생성** |

> **UI 배치 결정(스펙 fallback 적용):** 스펙 기본안은 "화면 표시" 섹션이었으나, 실제 설정창은 **800×520 무스크롤 고정**이고 "화면 표시"는 이미 5행이라 행 추가 시 오버플로 위험이 있다. 스펙이 명시적으로 허용한 fallback대로 토글을 **"시스템" 섹션**(현재 2행, 우측 컬럼)에 둔다. 라벨은 고정폭(116px)에 맞춰 **"바탕화면 유지"**로 짧게 쓴다(스펙의 긴 라벨 축약, 사유: 레이아웃 폭).

---

## Task 1: `ShowDesktopKeeper` 단위 (감지 → 복원)

**Files:**
- Create: `show_desktop_guard.py`
- Test: `tests/test_show_desktop_guard.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_show_desktop_guard.py`:

```python
"""ShowDesktopKeeper 단위 테스트 (pytest-qt)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from show_desktop_guard import ShowDesktopKeeper


def _make_window(qtbot):
    w = QWidget()
    w.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.Tool)
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def test_restores_when_enabled(qtbot):
    w = _make_window(qtbot)
    keeper = ShowDesktopKeeper(enabled=True)
    keeper.guard(w)

    w.setWindowState(Qt.WindowMinimized)  # Win+D가 만드는 상태 전이 모사

    qtbot.waitUntil(
        lambda: not (w.windowState() & Qt.WindowMinimized), timeout=2000
    )
    assert not (w.windowState() & Qt.WindowMinimized)


def test_stays_minimized_when_disabled(qtbot):
    w = _make_window(qtbot)
    keeper = ShowDesktopKeeper(enabled=False)
    keeper.guard(w)

    w.setWindowState(Qt.WindowMinimized)

    qtbot.wait(250)
    assert w.windowState() & Qt.WindowMinimized


def test_set_enabled_toggles_state():
    keeper = ShowDesktopKeeper(enabled=True)
    assert keeper.is_enabled() is True
    keeper.set_enabled(False)
    assert keeper.is_enabled() is False
    keeper.set_enabled(True)
    assert keeper.is_enabled() is True


def test_guard_none_is_safe():
    keeper = ShowDesktopKeeper(enabled=True)
    keeper.guard(None)  # 예외 없이 무시
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_show_desktop_guard.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'show_desktop_guard'`

- [ ] **Step 3: 최소 구현 작성**

`show_desktop_guard.py`:

```python
"""Win+D(바탕화면 보기)/모두 최소화에도 창을 유지시키는 가드.

창을 재부모화(SetParent)하지 않고, 최소화 상태 전이를 감지해 즉시 복원한다.
반투명·전체 투명도·드래그·Win+L 잠금 감지 등 기존 창 특성을 보존한다.
과거 WorkerW 재부모화 방식은 불안정으로 제거됐으므로 채택하지 않는다.
"""
import logging

from PySide6.QtCore import QObject, QEvent, QTimer, Qt
from PySide6.QtWidgets import QWidget

_logger = logging.getLogger("app_error")


class ShowDesktopKeeper(QObject):
    """감시 중인 창이 최소화되면(Win+D/Win+M) 즉시 복원한다."""

    def __init__(self, enabled: bool = True, parent=None):
        super().__init__(parent)
        self._enabled = bool(enabled)

    def set_enabled(self, on: bool) -> None:
        """실시간 on/off. 가드는 설치된 채 플래그로만 게이트한다."""
        self._enabled = bool(on)

    def is_enabled(self) -> bool:
        return self._enabled

    def guard(self, widget) -> None:
        """widget에 이 가드를 이벤트 필터로 설치(중복 호출 안전, None 안전)."""
        if widget is not None:
            widget.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        # 감지만 하고 이벤트는 소비하지 않는다(return False).
        try:
            if (self._enabled
                    and event.type() == QEvent.Type.WindowStateChange
                    and isinstance(obj, QWidget)
                    and obj.isWindow()
                    and bool(obj.windowState() & Qt.WindowState.WindowMinimized)):
                # 다음 이벤트 루프 턴에 복원(셸이 최소화를 끝낸 뒤) → 재진입/경쟁 회피.
                QTimer.singleShot(0, lambda w=obj: self._restore(w))
        except RuntimeError as e:
            # 삭제 중인 위젯 등. 이벤트 루프 보호 위해 로깅 후 계속(0023/0024 준수).
            _logger.debug("ShowDesktopKeeper.eventFilter 예외: %s", e)
        return False

    @staticmethod
    def _restore(widget) -> None:
        try:
            state = widget.windowState()
            if state & Qt.WindowState.WindowMinimized:
                widget.setWindowState(state & ~Qt.WindowState.WindowMinimized)
                widget.show()
        except RuntimeError as e:
            _logger.debug("ShowDesktopKeeper._restore 예외: %s", e)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_show_desktop_guard.py -q`
Expected: PASS (4 passed)

> 참고: `test_restores_when_enabled`가 실환경 Win+D 자체를 재현하지는 못한다(셸 동작). 상태 전이(`setWindowState(Minimized)`)에 대한 keeper 반응만 검증한다. 실제 Win+D 검증은 Task 6(수동)에서 수행한다.

- [ ] **Step 5: 체크포인트** — 위 테스트 그린 확인.

---

## Task 2: DB 설정 + 마이그레이션 v15 → v16

**Files:**
- Modify: `database.py:29` (상수), `database.py:34` (기본값), `database.py:453` 뒤 (마이그레이션 블록)
- Test: `tests/test_database.py` (신규 테스트 추가 + 기존 v15 단언 3곳 갱신)

- [ ] **Step 1: 실패하는 마이그레이션 테스트 작성**

`tests/test_database.py`의 마이그레이션 테스트 클래스(기존 `test_migration_v15_*` 근처, 약 162행 뒤)에 추가:

```python
    def test_migration_v16_adds_keep_on_show_desktop_default_on(self, app_dir):
        """app_dir 픽스처가 최신 migrate() 실행 → v16 + 기본 ON."""
        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 16
        assert db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP) == "1"

    def test_migration_v16_preserves_existing_and_idempotent(self, app_dir):
        """v15 상태에서 사용자 설정 보존 + 멱등하게 v16 시드."""
        with db._connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('app_opacity', '55')"
            )
            conn.execute("DELETE FROM app_settings WHERE key = 'keep_on_show_desktop'")
            conn.execute("PRAGMA user_version = 15")
            conn.commit()

        db.migrate()

        assert db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP) == "1"
        assert db.get_setting(db.SETTING_APP_OPACITY) == "55"  # 기존 설정 무손상
        with db._connection() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 16

        # 멱등: 사용자가 OFF로 바꾼 뒤 재마이그레이션해도 값 유지
        db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
        db.migrate()
        assert db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP) == "0"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_database.py -q`
Expected: FAIL — `AttributeError: module 'database' has no attribute 'SETTING_KEEP_ON_SHOW_DESKTOP'` (또한 기존 v15 단언들도 아직 15라 통과 상태)

- [ ] **Step 3: 상수 추가**

`database.py:29` (`SETTING_CALENDAR_SCALE` 줄 바로 뒤)에 추가:

```python
SETTING_KEEP_ON_SHOW_DESKTOP = "keep_on_show_desktop"  # Win+D/모두최소화에도 유지 "1"/"0"
```

`database.py:34` (`DEFAULT_CALENDAR_SCALE` 줄 바로 뒤)에 추가:

```python
DEFAULT_KEEP_ON_SHOW_DESKTOP = "1"
```

- [ ] **Step 4: 마이그레이션 블록 추가**

`database.py`의 `if version == 14:` 블록(끝: `version = 15`, 약 453행) 바로 뒤, `with _connection()` 블록 안에 추가:

```python
        if version == 15:
            # 바탕화면 유지(Win+D/모두최소화 면역) 설정 추가 (스키마 변경 없음, 멱등)
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                (SETTING_KEEP_ON_SHOW_DESKTOP, DEFAULT_KEEP_ON_SHOW_DESKTOP),
            )
            conn.execute("PRAGMA user_version = 16")
            conn.commit()
            version = 16
```

- [ ] **Step 5: 최신 버전을 15로 단언하던 모든 곳을 16으로 갱신**

`migrate()`는 항상 최신 버전까지 진행하므로, `migrate()`(또는 `app_dir` 픽스처) 이후 `PRAGMA user_version`을 검사하는 단언은 전부 최신값이 된다. 따라서 `tests/test_database.py`의 **모든** `assert version == 15`를 `assert version == 16`으로 바꾼다.

- 먼저 `grep "assert version == 15"`로 전체 개수를 확인한다. **실제 12곳**(예: `test_fresh_install_is_v15`(약 16), `test_v7_to_v8_*`(47), v12 트래시(69), `test_migrate_is_idempotent`(77), `test_idempotent_migration`(114), v9→v11(207), v10→v11(228), v11→v12(249), v13→v15(269), v13→v15 idempotent(289), `test_fresh_install_is_v15_with_new_settings`(296), `test_reset_then_migrate_v15`(988)) — 라인 번호는 편집에 따라 달라질 수 있으니 grep 기준으로 전부 바꾼다.
- docstring에 "v15 유지"가 있는 곳(약 72, 109행)은 "v16 유지"로 갱신.
- 테스트 **메서드명**은 그대로 둔다(예: `test_fresh_install_is_v15`) — 이름의 숫자는 부수적이고 rename은 불필요한 churn. 스켑.

> 주의 1: `test_migration_v15_*`(바로가기 6슬롯) 테스트는 버전이 아니라 shortcut 개수/ids를 보므로 **건드리지 말 것**.
> 주의 2: `break_minutes == 15` 같은 **버전이 아닌** `== 15` 라인은 절대 바꾸지 말 것. 반드시 `assert version == 15` 패턴만 대상으로.

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest tests/test_database.py -q`
Expected: PASS (신규 2개 포함 전부 통과)

- [ ] **Step 7: 체크포인트** — DB 테스트 그린 확인.

---

## Task 3: `MainCalendarWindow`에 keeper 배선

**Files:**
- Modify: `ui_main.py:309` (import), `ui_main.py:884` 뒤 (keeper 생성+self 가드), `ui_main.py:989` 뒤 (설정 변경 핸들러), 창 생성 7개 지점(투명도 적용부), `ui_main.py:2555` (설정창 콜백)

- [ ] **Step 1: import 추가**

`ui_main.py:309` (`import database as db`) 바로 뒤에 추가:

```python
from show_desktop_guard import ShowDesktopKeeper
```

- [ ] **Step 2: keeper 생성 + 메인 창 가드 (`__init__`)**

`ui_main.py:884` (`self.resize(380, 660)`)와 `self._build_ui()`(886행) 사이에 추가. **로더(`_load_open_*`, 889~891행)보다 먼저** 생성되어야 한다:

```python

        # ── Win+D(바탕화면 보기)/모두 최소화에도 유지 ──
        self._show_desktop_keeper = ShowDesktopKeeper(
            enabled=db.get_setting(
                db.SETTING_KEEP_ON_SHOW_DESKTOP, db.DEFAULT_KEEP_ON_SHOW_DESKTOP
            ) == "1",
            parent=self,
        )
        self._show_desktop_keeper.guard(self)
```

- [ ] **Step 3: 공용 등록 헬퍼 + 설정 변경 핸들러 추가**

`ui_main.py:989` (`_apply_app_opacity` 메서드 끝, `win.setWindowOpacity(factor)` 루프 다음 줄) 뒤에 추가:

```python

    def _register_floating_widget(self, win, factor: float | None = None) -> None:
        """새 플로팅 위젯 공통 등록: 투명도 적용 + Win+D 유지 가드."""
        win.setWindowOpacity(self._get_app_opacity() if factor is None else factor)
        self._show_desktop_keeper.guard(win)

    def _on_keep_desktop_changed(self) -> None:
        """설정에서 '바탕화면 유지' 토글 변경 시 실시간 반영."""
        enabled = db.get_setting(
            db.SETTING_KEEP_ON_SHOW_DESKTOP, db.DEFAULT_KEEP_ON_SHOW_DESKTOP
        ) == "1"
        self._show_desktop_keeper.set_enabled(enabled)
```

- [ ] **Step 4: 스티키 3개 생성 지점을 헬퍼로 교체**

(a) `_on_new_sticky_note` — `ui_main.py:2032`:
- 기존: `        win.setWindowOpacity(self._get_app_opacity())`
- 변경: `        self._register_floating_widget(win)`

(b) `_load_open_sticky_notes` 루프 — `ui_main.py:2048`:
- 기존: `                win.setWindowOpacity(factor)`
- 변경: `                self._register_floating_widget(win, factor)`

(c) `_restore_sticky_note` — `ui_main.py:2085`:
- 기존: `        win.setWindowOpacity(self._get_app_opacity())`
- 변경: `        self._register_floating_widget(win)`

- [ ] **Step 5: D-Day 2개 생성 지점을 헬퍼로 교체**

(a) 생성(`_on_new_dday...`) — `ui_main.py:2327`:
- 기존: `            win.setWindowOpacity(self._get_app_opacity())`
- 변경: `            self._register_floating_widget(win)`

(b) `_load_open_dday_widgets` 루프 — `ui_main.py:2343`:
- 기존: `                win.setWindowOpacity(factor)`
- 변경: `                self._register_floating_widget(win, factor)`

- [ ] **Step 6: 집중 2개 생성 지점을 헬퍼로 교체**

(a) `_on_new_focus_widget` — `ui_main.py:2393`:
- 기존: `            win.setWindowOpacity(self._get_app_opacity())`
- 변경: `            self._register_floating_widget(win)`

(b) `_load_open_focus_widgets` 루프 — `ui_main.py:2409`:
- 기존: `                win.setWindowOpacity(factor)`
- 변경: `                self._register_floating_widget(win, factor)`

> 참고: `large` 모드 미니 패널(스티키/D-Day/집중)은 메인 창의 자식 위젯이라 메인 가드가 자동 커버한다 — 별도 처리 불필요. large 모드에서 숨겨진 플로팅 창은 최소화 이벤트를 받지 않으므로 무해하다.

- [ ] **Step 7: 설정창 콜백 배선**

`ui_main.py:2555` (`on_scale_changed=self._apply_calendar_scale,`) 바로 뒤, `SettingsWindow(...)` 인자 목록에 추가:

```python
                on_keep_changed=self._on_keep_desktop_changed,
```

- [ ] **Step 8: 스모크 실행 확인**

Run: `python -c "import ui_main"`
Expected: import 에러 없이 종료(구문/이름 오류 없음).

- [ ] **Step 9: 체크포인트** — import 스모크 + 기존 UI 테스트 회귀 없음: `python -m pytest tests/test_ui.py -q` (PASS).

---

## Task 4: 설정 UI 토글 ("시스템" 섹션)

**Files:**
- Modify: `ui_settings.py:269` (생성자 시그니처), `ui_settings.py:278` 뒤 (콜백 저장), `ui_settings.py:614` 뒤 (토글 행), `ui_settings.py:886` 뒤 (핸들러)
- Test: `tests/test_ui_keep_desktop.py` (생성)

- [ ] **Step 1: 실패하는 설정 UI 테스트 작성**

`tests/test_ui_keep_desktop.py`:

```python
"""설정창 '바탕화면 유지' 토글 테스트."""
from qfluentwidgets import SwitchButton

import database as db
from ui_settings import SettingsWindow


def test_settings_has_keep_desktop_switch_default_on(app_dir, qtbot):
    w = SettingsWindow()
    qtbot.addWidget(w)
    assert isinstance(w.keep_desktop_switch, SwitchButton)
    assert w.keep_desktop_switch.isChecked() is True  # 기본 ON


def test_toggle_off_saves_and_calls_back(app_dir, qtbot):
    calls = {"n": 0}
    w = SettingsWindow(on_keep_changed=lambda: calls.__setitem__("n", calls["n"] + 1))
    qtbot.addWidget(w)

    w.keep_desktop_switch.setChecked(False)

    assert db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP) == "0"
    assert calls["n"] >= 1


def test_toggle_back_on_saves(app_dir, qtbot):
    w = SettingsWindow()
    qtbot.addWidget(w)
    w.keep_desktop_switch.setChecked(False)
    w.keep_desktop_switch.setChecked(True)
    assert db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP) == "1"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_ui_keep_desktop.py -q`
Expected: FAIL — `AttributeError: 'SettingsWindow' object has no attribute 'keep_desktop_switch'`

- [ ] **Step 3: 생성자 시그니처 + 콜백 저장**

`ui_settings.py:269` — 시그니처 끝 `on_opacity_changed=None, on_scale_changed=None):` 를:

```python
                 on_opacity_changed=None, on_scale_changed=None,
                 on_keep_changed=None):
```

`ui_settings.py:278` (`self.on_scale_changed = on_scale_changed`) 바로 뒤에 추가:

```python
        self.on_keep_changed = on_keep_changed
```

- [ ] **Step 4: "시스템" 섹션에 토글 행 추가**

`ui_settings.py:614` (`self._add_row(sys_body, "자동 실행", self.startup_switch)`) 바로 뒤에 추가(자동 실행과 앱 글꼴 사이):

```python
        self.keep_desktop_switch = self._make_switch(
            db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP,
                           db.DEFAULT_KEEP_ON_SHOW_DESKTOP) == "1",
            self._on_keep_desktop_toggled)
        self._add_row(sys_body, "바탕화면 유지", self.keep_desktop_switch)
```

- [ ] **Step 5: 핸들러 추가**

`ui_settings.py`의 토글 핸들러 그룹(`_on_sidebar_toggled` 끝, 약 886행) 뒤에 추가:

```python

    def _on_keep_desktop_toggled(self, checked: bool):
        db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "1" if checked else "0")
        if self.on_keep_changed:
            self.on_keep_changed()
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest tests/test_ui_keep_desktop.py -q`
Expected: PASS (3 passed)

> 만약 `setChecked()`가 `checkedChanged`를 발신하지 않아 실패하면, 테스트에서 `w._on_keep_desktop_toggled(False)`를 직접 호출하도록 대체(핸들러 로직 검증). 단 qfluentwidgets `SwitchButton`은 값 변경 시 발신하므로 통상 그대로 통과한다.

- [ ] **Step 7: 무스크롤 레이아웃 회귀 확인**

Run: `python -m pytest tests/test_ui.py -q`
Expected: PASS. 설정창 크기/레이아웃 관련 기존 테스트가 800×520(또는 관련 고정값) 위반 없이 통과하는지 확인. 실패 시 라벨/행 높이 조정.

- [ ] **Step 8: 체크포인트** — 설정 UI 테스트 + 기존 UI 테스트 그린.

---

## Task 5: 문서화 (AGENTS.md) + 전체 회귀

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Module Map에 신규 파일 행 추가**

`AGENTS.md`의 Module Map 테이블에서 `security.py` 행 아래에 추가:

```markdown
| `show_desktop_guard.py` | `ShowDesktopKeeper(QObject)` — 감시 창이 최소화(Win+D/Win+M)되면 `WindowStateChange` 감지 후 `singleShot(0)`으로 복원. 재부모화 없이 반투명·투명도·드래그 보존. `enabled` 플래그로 실시간 on/off |
```

- [ ] **Step 2: 기존 행 갱신**

- `database.py` 행: `schema migration (v15)` → `schema migration (v16)`, 그리고 설명에 `SETTING_KEEP_ON_SHOW_DESKTOP` 추가.
- `ui_main.py` 행 끝에 추가: `Win+D 유지용 ShowDesktopKeeper 소유(메인+모든 플로팅 위젯 가드), 설정 토글 실시간 반영`.
- `ui_settings.py` 행: "시스템" 섹션에 `바탕화면 유지`(SwitchButton) 토글 추가 언급.

- [ ] **Step 3: Key Constraints에 제약 추가**

`## Key Constraints`에 항목 추가:

```markdown
- **바탕화면 유지(Win+D)**: `SETTING_KEEP_ON_SHOW_DESKTOP="keep_on_show_desktop"`(기본 `"1"`). Win+D/Win+M 시 메인 + 모든 플로팅 위젯(스티키/D-Day/집중)이 내려가지 않도록 `show_desktop_guard.ShowDesktopKeeper`가 최소화 상태를 감지해 복원한다. **창 재부모화(WorkerW/SetParent) 금지** — 과거 "바탕화면 고정 모드"가 불안정으로 제거됨. 창 생성 시 `_register_floating_widget()`가 투명도와 함께 가드를 등록한다. 설정 "시스템" 섹션 토글로 실시간 on/off.
```

`- **DB 마이그레이션**` 항목: `현재 user_version=15` → `현재 user_version=16`, 그리고 `v15→v16는 keep_on_show_desktop 설정을 INSERT OR IGNORE로 추가한다.` 문장 추가.

- [ ] **Step 4: 전체 테스트 스위트 실행**

Run: `python -m pytest tests -q`
Expected: 전부 PASS (신규 keeper/마이그레이션/설정 UI 테스트 포함, 기존 회귀 없음).

- [ ] **Step 5: 체크포인트** — 전체 그린 + AGENTS.md 갱신 확인.

---

## Task 6: 실기기 수동 검증 (필수) + 컨틴전시

과거 유사 기능이 불안정으로 제거됐으므로, 자동 테스트만으로 완료 선언하지 않는다. 실제 Windows 11에서 앱을 띄워 확인한다.

- [ ] **Step 1: 앱 실행**

Run: `python main.py`

- [ ] **Step 2: 체크리스트 확인 (스펙 §11)**

1. Win+D → 메인 + 스티키/D-Day/집중이 모두 유지되는가.
2. 다시 Win+D → 다른 앱 복원과 충돌 없는가.
3. Win+M(모두 최소화)에도 유지되는가.
4. Boss Key(Ctrl+Shift+H) / 트레이 숨김이 정상 작동하는가(가드가 방해 안 함).
5. 반투명·둥근 모서리·전체 투명도·드래그·멀티모니터·Win+L 잠금 무손상인가.
6. 설정 "시스템 → 바탕화면 유지" OFF → Win+D에 정상적으로 내려가는가(즉시 반영). 다시 ON → 유지되는가.
7. `large`(크게) 모드에서 Win+D → 메인(임베드 패널 포함) 유지되는가.
8. 깜빡임 정도가 수용 가능한가.

- [ ] **Step 3: 컨틴전시 (필요 시에만)**

만약 특정 창에서 Win+D 시 `WindowStateChange`가 발생하지 않아 복원이 안 되면(플랫폼 편차), 해당 창의 `nativeEvent`에서 `WM_SIZE`(`0x0005`) + `SIZE_MINIMIZED`(`wParam==1`)를 보조 감지해 동일 복원 로직을 호출하는 fallback을 추가한다. **8번(깜빡임)이 수용 불가**할 때만 스펙 §2의 ②b(`WM_WINDOWPOSCHANGING` 거부)를 별도 후속 작업으로 검토(이 계획 범위 밖).

- [ ] **Step 4: 완료** — 체크리스트 통과 시 기능 완료.

---

## Self-Review (계획 작성자 확인 완료)

- **스펙 커버리지:** §2 목표(메인+플로팅 유지, 토글 기본 ON 실시간, 무손상) → Task 1·3·4. §6 DB/마이그레이션 → Task 2. §7 설정 UI → Task 4. §9 테스트 → Task 1·2·4 + Task 5 전체 실행. §11 수동 검증 → Task 6. §12 기술 전제/컨틴전시 → Task 1 참고 + Task 6 Step 3. ✅
- **UI 배치:** 스펙 "화면 표시" 기본안 → 레이아웃 안전상 스펙 허용 fallback "시스템"으로 명시 이동(사유 문서화). ✅
- **플레이스홀더 스캔:** 모든 코드 단계에 실제 코드/명령/예상 출력 포함. ✅
- **타입/이름 일관성:** `ShowDesktopKeeper`·`guard`·`set_enabled`·`is_enabled`·`_register_floating_widget`·`_on_keep_desktop_changed`(main)·`_on_keep_desktop_toggled`(settings)·`keep_desktop_switch`·`on_keep_changed`·`SETTING_KEEP_ON_SHOW_DESKTOP`·`DEFAULT_KEEP_ON_SHOW_DESKTOP` — 태스크 전반 일치. ✅
- **커밋:** git 저장소 아님 → 체크포인트로 대체 명시. ✅
