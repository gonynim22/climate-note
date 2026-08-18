# 설정 창 레이아웃 재설계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 설정 창(`ui_settings.py`)을 섹션 패널 2열로 재배치하고 캘린더 크기 컨트롤을 일러스트 picker로 교체한다. 기능·저장값·콜백은 100% 동일.

**Architecture:** 컨트롤 생성 코드와 핸들러는 모두 재사용하고, 컨테이너만 `_make_card`/`_section_header` → 패널/행 헬퍼(`_make_panel`/`_add_row`)로 바꾼다. 캘린더 크기는 고정 모니터 + 파란 앱 면적을 그리는 신규 위젯 `CalendarSizePicker`(QFrame+QSS, 외부 이미지 없음)로 교체한다. 창은 800×560 고정·무스크롤 유지.

**Tech Stack:** Python, PySide6 + qfluentwidgets, pytest + pytest-qt.

> **참고(git):** 이 프로젝트는 git 저장소가 아니다. 각 Task의 **Commit 단계는 선택**이다 — `git init` 후 사용하거나, 논리적 체크포인트(테스트 통과 지점)로만 활용한다.

> **스펙:** `docs/superpowers/specs/2026-06-11-settings-redesign-design.md`

---

## File Structure

| 파일 | 책임 | 변경 |
|---|---|---|
| `ui_settings.py` | 설정 창 + 신규 `CalendarSizePicker`/`_ScaleOption` 위젯, 패널/행 헬퍼 | 수정 |
| `tests/test_ui.py` | picker 단위 테스트 + 설정 창 회귀 테스트 | 수정 |
| `AGENTS.md`, `docs/UI_PATTERNS.md` | 설정창 설명 갱신 | 수정 |

전체 작업이 `ui_settings.py` 한 파일(722줄)에 집중된다. picker 위젯은 유일 소비자와 co-locate(동일 파일)한다.

---

## Task 1: CalendarSizePicker 위젯 (TDD)

**Files:**
- Modify: `ui_settings.py` (상단 import 보강 + 파일 끝/`SettingsWindow` 앞에 위젯 클래스 추가)
- Test: `tests/test_ui.py`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_ui.py` 끝에 추가

```python
def test_calendar_size_picker_scales_and_select(qtbot, app_dir, qapp):
    from ui_settings import CalendarSizePicker

    assert [s[0] for s in CalendarSizePicker._SCALES] == ["compact", "medium", "large"]

    picker = CalendarSizePicker("compact")
    qtbot.addWidget(picker)
    got = []
    picker.scaleChanged.connect(lambda v: got.append(v))

    assert picker.current_scale() == "compact"
    picker.select("large")
    assert picker.current_scale() == "large"
    assert got == ["large"]

    selected = [v for v, opt in picker._options.items()
                if opt.property("selected") == "true"]
    assert selected == ["large"]


def test_calendar_size_picker_invalid_current_falls_back(qtbot, app_dir, qapp):
    from ui_settings import CalendarSizePicker

    picker = CalendarSizePicker("nonsense")
    qtbot.addWidget(picker)
    assert picker.current_scale() == "compact"
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_ui.py::test_calendar_size_picker_scales_and_select -v`
Expected: FAIL — `ImportError: cannot import name 'CalendarSizePicker'`

- [ ] **Step 3: import 보강** — `ui_settings.py` 상단

`from PySide6.QtCore import Qt, QUrl` 를 다음으로 변경:

```python
from PySide6.QtCore import Qt, QUrl, Signal
```

`from PySide6.QtWidgets import (...)` 의 import 목록에 `QFrame` 추가:

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog, QLineEdit, QApplication,
    QPushButton, QFrame,
)
```

- [ ] **Step 4: 위젯 구현** — `ui_settings.py` 의 `class SettingsWindow` 정의 **바로 위**에 추가

```python
class _ScaleOption(QFrame):
    """캘린더 크기 옵션 1개: 고정 모니터 + 우측 하단 파란 앱 블록 + 캡션."""

    clicked = Signal(str)

    def __init__(self, value: str, caption: str, app_size: tuple,
                 screen_size: tuple, parent=None):
        super().__init__(parent)
        self.value = value
        self.setObjectName("scaleOption")
        self.setProperty("selected", "false")
        self.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 4)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignHCenter)

        screen = QFrame(self)
        screen.setObjectName("scaleScreen")
        sw, sh = screen_size
        screen.setFixedSize(sw, sh)
        app = QFrame(screen)
        app.setObjectName("scaleApp")
        aw, ah = app_size
        app.setFixedSize(aw, ah)
        app.move(sw - aw - 3, sh - ah - 3)   # 우측 하단 모서리(기본 위치)에 배치
        lay.addWidget(screen, 0, Qt.AlignHCenter)

        cap = BodyLabel(caption, self)
        cap.setObjectName("scaleCaption")
        cap.setAlignment(Qt.AlignHCenter)
        lay.addWidget(cap)

        self.setStyleSheet("""
            #scaleOption { border: 2px solid transparent; border-radius: 8px; }
            #scaleOption[selected="true"] { border-color: #0078D4; background: #EAF3FC; }
            #scaleScreen { background: #E9EEF3; border: 2px solid #B9C2CD; border-radius: 4px; }
            #scaleApp { background: #2566B8; border-top: 3px solid #01295F; border-radius: 2px; }
            #scaleCaption { font-size: 11px; color: #555555; }
            #scaleOption[selected="true"] #scaleCaption { color: #0078D4; font-weight: 700; }
        """)

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event):
        self.clicked.emit(self.value)
        super().mouseReleaseEvent(event)


class CalendarSizePicker(QWidget):
    """캘린더 크기(compact/medium/large) 일러스트 선택 위젯.

    모니터(화면) 크기는 3개 동일, 안의 파란 앱 면적만 다르다.
    저장은 하지 않는다 — 선택 시 scaleChanged(value) 시그널만 emit.
    """

    scaleChanged = Signal(str)
    _SCREEN = (46, 30)
    _SCALES = [
        ("compact", "기본", (16, 10)),
        ("medium", "중간", (26, 16)),
        ("large", "크게", (36, 22)),
    ]

    def __init__(self, current: str, parent=None):
        super().__init__(parent)
        valid = {value for value, _, _ in self._SCALES}
        self._current = current if current in valid else "compact"
        self._options = {}

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for value, caption, app_size in self._SCALES:
            opt = _ScaleOption(value, caption, app_size, self._SCREEN, self)
            opt.clicked.connect(self.select)
            self._options[value] = opt
            lay.addWidget(opt)
        self._apply_highlight()

    def _apply_highlight(self) -> None:
        for value, opt in self._options.items():
            opt.set_selected(value == self._current)

    def select(self, value: str) -> None:
        if value not in self._options:
            return
        self._current = value
        self._apply_highlight()
        self.scaleChanged.emit(value)

    def current_scale(self) -> str:
        return self._current
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/test_ui.py::test_calendar_size_picker_scales_and_select tests/test_ui.py::test_calendar_size_picker_invalid_current_falls_back -v`
Expected: PASS (2 passed)

- [ ] **Step 6: (선택) Commit**

```bash
git add ui_settings.py tests/test_ui.py
git commit -m "feat(settings): add CalendarSizePicker illustration widget"
```

---

## Task 2: 캘린더 크기 컨트롤을 picker로 배선 교체 (TDD)

기존 콤보 기반 테스트를 picker 기반으로 바꾸고, `SettingsWindow`가 picker를 사용하도록 한다. (레이아웃 재구성은 Task 3에서. 여기서는 기존 카드 구조 안에서 위젯만 교체.)

**Files:**
- Modify: `ui_settings.py:252-265` (scale_combo 블록) 및 `_on_scale_changed`
- Test: `tests/test_ui.py:154-162` (기존 테스트 교체)

- [ ] **Step 1: 기존 테스트 교체** — `tests/test_ui.py` 의 `test_settings_scale_combo_persists_and_calls_callback` 함수(현 154–162행) **전체를** 아래로 치환

```python
def test_settings_scale_picker_persists_and_calls_callback(qtbot, app_dir, qapp):
    received = []
    win = SettingsWindow(on_scale_changed=lambda: received.append(True))
    qtbot.addWidget(win)
    assert win.scale_picker.current_scale() in ("compact", "medium", "large")
    win.scale_picker.select("medium")
    assert db.get_setting(db.SETTING_CALENDAR_SCALE) == "medium"
    assert received == [True]
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_ui.py::test_settings_scale_picker_persists_and_calls_callback -v`
Expected: FAIL — `AttributeError: 'SettingsWindow' object has no attribute 'scale_picker'`

- [ ] **Step 3: scale_combo 블록 교체** — `ui_settings.py` 현 252–265행

```python
        scale_card, scale_action = self._make_card("캘린더 크기")
        self.scale_combo = ComboBox(self)
        ...
        scale_action.addWidget(self.scale_combo, 0, Qt.AlignRight)
        left_layout.addWidget(scale_card)
```

위 블록 전체를 아래로 치환:

```python
        scale_card, scale_action = self._make_card("캘린더 크기")
        self.scale_picker = CalendarSizePicker(
            db.get_setting(db.SETTING_CALENDAR_SCALE, db.DEFAULT_CALENDAR_SCALE), self)
        self.scale_picker.scaleChanged.connect(self._on_scale_changed)
        scale_action.addWidget(self.scale_picker, 0, Qt.AlignRight)
        left_layout.addWidget(scale_card)
```

- [ ] **Step 4: `_on_scale_changed` 시그니처 변경 (index → str)**

기존:

```python
    def _on_scale_changed(self, index: int):
        scale = self.scale_combo.itemData(index)
        if not scale:
            return
        db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
        if self.on_scale_changed:
            self.on_scale_changed()
```

치환:

```python
    def _on_scale_changed(self, scale: str):
        if not scale:
            return
        db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
        if self.on_scale_changed:
            self.on_scale_changed()
```

- [ ] **Step 5: 통과 + 회귀 확인**

Run: `python -m pytest tests/test_ui.py -q`
Expected: PASS (전체 통과 — `scale_combo` 참조가 더 이상 없어야 함). 만약 `scale_combo` 잔존 참조 오류가 나면 검색해 제거: `grep -n scale_combo ui_settings.py tests/test_ui.py` 결과가 없어야 한다.

- [ ] **Step 6: (선택) Commit**

```bash
git add ui_settings.py tests/test_ui.py
git commit -m "feat(settings): replace calendar-size combo with CalendarSizePicker"
```

---

## Task 3: 레이아웃을 섹션 패널 2열로 재구성

컨트롤 생성 코드·핸들러는 그대로 두고, 컨테이너만 패널/행으로 바꾼다. 회귀 테스트(5섹션 헤더·컨트롤 보존·무스크롤)가 가드 역할을 한다.

**Files:**
- Modify: `ui_settings.py` — `_make_panel`/`_add_row` 추가, `_build_ui` 본문 재작성, `_make_card`/`_section_header` 삭제
- Test: `tests/test_ui.py`

- [ ] **Step 1: 실패하는 구조 테스트 추가** — `tests/test_ui.py` 끝에 추가

```python
def test_settings_has_five_section_panels(qtbot, app_dir, qapp):
    from qfluentwidgets import StrongBodyLabel

    win = SettingsWindow()
    qtbot.addWidget(win)
    headers = [w for w in win.findChildren(StrongBodyLabel)
               if w.objectName() == "panelHeader"]
    assert len(headers) == 5
    assert {h.text() for h in headers} == {
        "화면 표시", "위젯·도구", "데이터", "보안", "시스템"}
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_ui.py::test_settings_has_five_section_panels -v`
Expected: FAIL — `assert 0 == 5` (panelHeader objectName 없음)

- [ ] **Step 3: 패널/행 헬퍼 추가** — `ui_settings.py` 의 `_make_card` 메서드 위치에 두 헬퍼 추가

```python
    def _make_panel(self, title: str) -> tuple:
        """섹션 패널: 헤더(StrongBodyLabel) + 내부 행 레이아웃(body) 반환."""
        panel = CardWidget(self)
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        header = StrongBodyLabel(title, panel)
        header.setObjectName("panelHeader")
        header.setStyleSheet(
            "#panelHeader{font-size:12px;font-weight:800;color:#01295F;"
            "background:#EDF1F6;border-bottom:1px solid #D7DDE5;padding:6px 10px;}")
        v.addWidget(header)
        body = QVBoxLayout()
        body.setContentsMargins(10, 2, 10, 6)
        body.setSpacing(0)
        v.addLayout(body)
        return panel, body

    def _add_row(self, body: QVBoxLayout, label: str, control: QWidget) -> QWidget:
        """라벨-좌 / 컨트롤-우(우측 정렬). control 은 위젯 또는 컨테이너 위젯."""
        row = QWidget(self)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 6, 0, 6)
        h.setSpacing(8)
        lbl = BodyLabel(label, row)
        lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        h.addWidget(lbl, 1)
        h.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
        body.addWidget(row)
        return row
```

- [ ] **Step 4: `_build_ui` 본문 재작성**

`_build_ui`의 **제목(title) 생성과 2열 스켈레톤은 유지**하되, 기존 `_section_header`/`_make_card` 호출로 채우던 부분을 아래 구조로 교체한다. **각 컨트롤의 생성 코드(ComboBox/Slider/SwitchButton/LineEdit/PushButton 등)는 현재 파일의 것을 그대로 사용**하고, 카드에 넣던 것을 컨테이너 위젯으로 묶어 `_add_row(body, "라벨", control)` 로 추가한다.

`_build_ui` 전체를 아래로 치환:

```python
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 12)
        outer.setSpacing(10)

        title = TitleLabel("설정", self)
        title.setFixedHeight(36)
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        outer.addWidget(title)

        content_grid = QGridLayout()
        content_grid.setSpacing(12)
        content_grid.setColumnStretch(0, 1)
        content_grid.setColumnStretch(1, 1)
        outer.addLayout(content_grid, 1)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        content_grid.addWidget(left, 0, 0, Qt.AlignTop)
        content_grid.addWidget(right, 0, 1, Qt.AlignTop)

        # ───── 화면 표시 ─────
        disp_panel, disp_body = self._make_panel("화면 표시")

        # 모니터 및 위치 (콤보 + 2x2 방향 그리드)
        pos_control = QWidget(self)
        pos_row = QHBoxLayout(pos_control)
        pos_row.setContentsMargins(0, 0, 0, 0)
        pos_row.setSpacing(10)
        self.monitor_combo = ComboBox(self)
        self.monitor_combo.setFixedWidth(145)
        for index, screen in enumerate(QApplication.screens()):
            geometry = screen.geometry()
            self.monitor_combo.addItem(
                f"모니터 {index + 1} ({geometry.width()}x{geometry.height()})",
                userData=str(index),
            )
        monitor_index = self.monitor_combo.findData(db.get_setting(db.SETTING_TARGET_SCREEN, "0"))
        if monitor_index >= 0:
            self.monitor_combo.setCurrentIndex(monitor_index)
        self.monitor_combo.currentIndexChanged.connect(self._on_monitor_changed)
        pos_row.addWidget(self.monitor_combo, 0, Qt.AlignVCenter)
        current_pos = db.get_setting(db.SETTING_CALENDAR_POSITION, "bottom-right")
        self._position_btns = {}
        pos_grid = QGridLayout()
        pos_grid.setSpacing(4)
        for pos_key, symbol, prow, pcol in [
            ("top-left", "◤", 0, 0), ("top-right", "◥", 0, 1),
            ("bottom-left", "◣", 1, 0), ("bottom-right", "◢", 1, 1),
        ]:
            button = QPushButton(symbol, self)
            button.setFixedSize(36, 36)
            button.setProperty("pos_key", pos_key)
            button.clicked.connect(lambda checked=False, key=pos_key: self._on_position_changed(key))
            self._position_btns[pos_key] = button
            pos_grid.addWidget(button, prow, pcol)
        pos_row.addLayout(pos_grid)
        self._update_position_buttons(current_pos)
        self._add_row(disp_body, "모니터 및 위치", pos_control)

        # 전체 투명도
        opacity_control = QWidget(self)
        opacity_row = QHBoxLayout(opacity_control)
        opacity_row.setContentsMargins(0, 0, 0, 0)
        opacity_row.setSpacing(8)
        self.opacity_slider = Slider(Qt.Horizontal, self)
        self.opacity_slider.setObjectName("opacitySlider")
        self.opacity_slider.setRange(db.MIN_APP_OPACITY, 100)
        self.opacity_slider.setFixedWidth(135)
        try:
            opacity = int(db.get_setting(db.SETTING_APP_OPACITY, db.DEFAULT_APP_OPACITY))
        except (TypeError, ValueError):
            opacity = 100
        opacity = max(db.MIN_APP_OPACITY, min(100, opacity))
        self.opacity_slider.setValue(opacity)
        self.opacity_value_label = BodyLabel(f"{opacity}%", self)
        self.opacity_value_label.setStyleSheet("font-size: 12px; color: #0078D4;")
        self.opacity_value_label.setFixedWidth(40)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_value_label)
        self._add_row(disp_body, "전체 투명도", opacity_control)

        # 캘린더 크기 (일러스트 picker)
        self.scale_picker = CalendarSizePicker(
            db.get_setting(db.SETTING_CALENDAR_SCALE, db.DEFAULT_CALENDAR_SCALE), self)
        self.scale_picker.scaleChanged.connect(self._on_scale_changed)
        self._add_row(disp_body, "캘린더 크기", self.scale_picker)

        # 음력 및 공휴일
        self.lunar_switch = SwitchButton(self)
        self.lunar_switch.setChecked(db.get_setting(db.SETTING_SHOW_LUNAR, "0") == "1")
        self.lunar_switch.checkedChanged.connect(self._on_lunar_toggled)
        self._add_row(disp_body, "음력 및 공휴일", self.lunar_switch)

        left_layout.addWidget(disp_panel)

        # ───── 위젯·도구 ─────
        tools_panel, tools_body = self._make_panel("위젯·도구")
        self.sidebar_switch = SwitchButton(self)
        self.sidebar_switch.setChecked(db.get_setting(db.SETTING_SHOW_SIDEBAR, "0") == "1")
        self.sidebar_switch.checkedChanged.connect(self._on_sidebar_toggled)
        self._add_row(tools_body, "바로가기", self.sidebar_switch)
        self.law_search_switch = SwitchButton(self)
        self.law_search_switch.setChecked(db.get_setting(db.SETTING_SHOW_LAW_SEARCH, "1") == "1")
        self.law_search_switch.checkedChanged.connect(self._on_law_search_toggled)
        self._add_row(tools_body, "AI 법령검색", self.law_search_switch)
        left_layout.addWidget(tools_panel)
        left_layout.addStretch(1)

        # ───── 데이터 ─────
        data_panel, data_body = self._make_panel("데이터")
        export_control = QWidget(self)
        export_row = QHBoxLayout(export_control)
        export_row.setContentsMargins(0, 0, 0, 0)
        export_row.setSpacing(6)
        self.export_pin = LineEdit(self)
        self.export_pin.setPlaceholderText("PIN")
        self.export_pin.setEchoMode(QLineEdit.Password)
        self.export_pin.setMaxLength(4)
        self.export_pin.setFixedWidth(54)
        self.export_pin.setStyleSheet("font-size: 12px;")
        export_row.addWidget(self.export_pin)
        export_button = PrimaryPushButton("실행")
        export_button.setStyleSheet("font-size: 12px;")
        export_button.setFixedWidth(48)
        export_button.clicked.connect(self._on_export)
        export_row.addWidget(export_button)
        self._add_row(data_body, "내보내기", export_control)

        import_control = QWidget(self)
        import_row = QHBoxLayout(import_control)
        import_row.setContentsMargins(0, 0, 0, 0)
        import_row.setSpacing(6)
        self.import_pin = LineEdit(self)
        self.import_pin.setPlaceholderText("PIN")
        self.import_pin.setEchoMode(QLineEdit.Password)
        self.import_pin.setMaxLength(4)
        self.import_pin.setFixedWidth(54)
        self.import_pin.setStyleSheet("font-size: 12px;")
        import_row.addWidget(self.import_pin)
        import_button = PrimaryPushButton("실행")
        import_button.setStyleSheet("font-size: 12px;")
        import_button.setFixedWidth(48)
        import_button.clicked.connect(self._on_import)
        import_row.addWidget(import_button)
        self._add_row(data_body, "가져오기", import_control)

        self.open_data_folder_btn = TransparentToolButton(FIF.FOLDER, self)
        self.open_data_folder_btn.setToolTip("저장 폴더 열기")
        self.open_data_folder_btn.clicked.connect(self._on_open_data_folder)
        self._add_row(data_body, "저장 경로", self.open_data_folder_btn)
        right_layout.addWidget(data_panel)

        # ───── 보안 ─────
        sec_panel, sec_body = self._make_panel("보안")
        privacy_control = QWidget(self)
        privacy_row = QHBoxLayout(privacy_control)
        privacy_row.setContentsMargins(0, 0, 0, 0)
        privacy_row.setSpacing(6)
        self.privacy_switch = SwitchButton(self)
        self.privacy_switch.setChecked(db.get_setting(db.SETTING_USE_PRIVACY_LOCK, "0") == "1")
        self.privacy_switch.checkedChanged.connect(self._on_privacy_lock_toggled)
        privacy_row.addWidget(self.privacy_switch)
        self.pin_container = QWidget()
        pin_layout = QHBoxLayout(self.pin_container)
        pin_layout.setContentsMargins(0, 0, 0, 0)
        self.privacy_pin_edit = LineEdit(self)
        self.privacy_pin_edit.setPlaceholderText("PIN")
        self.privacy_pin_edit.setText(db.get_setting(db.SETTING_PRIVACY_PIN, "0000"))
        self.privacy_pin_edit.setMaxLength(4)
        self.privacy_pin_edit.setFixedWidth(60)
        self.privacy_pin_edit.setStyleSheet("font-size: 12px;")
        pin_layout.addWidget(self.privacy_pin_edit)
        save_pin_button = PushButton("저장")
        save_pin_button.setStyleSheet("font-size: 12px;")
        save_pin_button.setFixedWidth(50)
        save_pin_button.clicked.connect(self._on_save_privacy_pin)
        pin_layout.addWidget(save_pin_button)
        privacy_row.addWidget(self.pin_container)
        self.pin_container.setVisible(self.privacy_switch.isChecked())
        self._add_row(sec_body, "개인정보 잠금", privacy_control)

        self.factory_reset_btn = PushButton(FIF.DELETE.icon(Theme.DARK), "Factory Reset", self)
        self.factory_reset_btn.setObjectName("factoryResetButton")
        self.factory_reset_btn.setToolTip("모든 데이터를 초기화")
        self.factory_reset_btn.setFixedHeight(32)
        self.factory_reset_btn.setMinimumWidth(152)
        self.factory_reset_btn.setStyleSheet("""
            PushButton#factoryResetButton {
                color: white; background: #B42318; border: 1px solid #912018;
                border-bottom: 2px solid #7A271A; border-radius: 6px;
                padding: 5px 14px 5px 34px; font-size: 12px; font-weight: 600;
            }
            PushButton#factoryResetButton:hover {
                background: #D92D20; border: 1px solid #B42318;
                border-bottom: 2px solid #912018;
            }
            PushButton#factoryResetButton:pressed {
                background: #7A271A; border: 1px solid #7A271A;
                border-top: 2px solid #55160C; border-bottom: 1px solid #7A271A;
            }
        """)
        self.factory_reset_btn.clicked.connect(self._on_reset)
        self._add_row(sec_body, "데이터 초기화", self.factory_reset_btn)
        right_layout.addWidget(sec_panel)

        # ───── 시스템 ─────
        sys_panel, sys_body = self._make_panel("시스템")
        self.startup_switch = SwitchButton(self)
        self.startup_switch.setChecked(_is_startup_enabled())
        self.startup_switch.checkedChanged.connect(self._on_startup_toggled)
        self._add_row(sys_body, "자동 실행", self.startup_switch)

        self.font_combo = ComboBox(self)
        self.font_combo.setFixedWidth(170)
        for label, value in APP_FONT_OPTIONS:
            self.font_combo.addItem(label, userData=value)
        self.font_combo.addItem("────────", userData="")
        self.font_combo.setItemEnabled(self.font_combo.count() - 1, False)
        for family in available_system_fonts():
            self.font_combo.addItem(family, userData=system_font_key(family))
        current_font = db.get_setting(db.SETTING_APP_FONT, db.DEFAULT_APP_FONT)
        font_index = self.font_combo.findData(current_font)
        if font_index < 0 and current_font.startswith(SYSTEM_FONT_PREFIX):
            font_index = self._add_missing_system_font(current_font)
        if font_index < 0:
            font_index = self.font_combo.findData(db.DEFAULT_APP_FONT)
        if font_index >= 0:
            self.font_combo.setCurrentIndex(font_index)
        self.font_combo.currentIndexChanged.connect(self._on_font_changed)
        self._add_row(sys_body, "앱 글꼴", self.font_combo)
        right_layout.addWidget(sys_panel)
        right_layout.addStretch(1)

        # ───── 하단 바 (기능·스타일 그대로) ─────
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 4, 0, 0)
        license_button = PushButton("라이선스", self)
        license_button.setStyleSheet("font-size: 12px;")
        license_button.clicked.connect(self._on_license)
        bottom_row.addWidget(license_button)
        bottom_row.addStretch()
        author_label = BodyLabel(app_credit_text(), self)
        author_label.setStyleSheet("color: gray; font-size: 11px;")
        bottom_row.addWidget(author_label)
        bottom_row.addStretch()
        self.quit_app_btn = PushButton(FIF.POWER_BUTTON.icon(Theme.DARK), "앱 종료", self)
        self.quit_app_btn.setObjectName("quitAppButton")
        self.quit_app_btn.setToolTip("기후노트 종료")
        self.quit_app_btn.setFixedHeight(32)
        self.quit_app_btn.setMinimumWidth(112)
        self.quit_app_btn.setStyleSheet("""
            PushButton#quitAppButton {
                color: white; background: #344054; border: 1px solid #1D2939;
                border-bottom: 2px solid #101828; border-radius: 6px;
                padding: 5px 12px 5px 32px; font-size: 12px; font-weight: 600;
            }
            PushButton#quitAppButton:hover {
                background: #475467; border: 1px solid #344054;
                border-bottom: 2px solid #1D2939;
            }
            PushButton#quitAppButton:pressed {
                background: #1D2939; border: 1px solid #1D2939;
                border-top: 2px solid #101828; border-bottom: 1px solid #1D2939;
            }
        """)
        self.quit_app_btn.clicked.connect(self._on_quit)
        bottom_row.addWidget(self.quit_app_btn)
        outer.addLayout(bottom_row)
```

- [ ] **Step 5: 사용하지 않는 헬퍼 삭제**

이제 호출처가 없어진 `_make_card`, `_section_header` 메서드를 `ui_settings.py`에서 삭제한다. 삭제 후 확인: `grep -n "_make_card\|_section_header" ui_settings.py` 결과가 정의·호출 모두 없어야 한다(0건).

- [ ] **Step 6: 전체 테스트 통과 확인**

Run: `python -m pytest tests/test_ui.py -q`
Expected: PASS — 다음이 모두 통과:
- `test_settings_has_five_section_panels` (신규)
- `test_settings_has_five_section_headers` (헤더가 StrongBodyLabel이라 그대로 통과)
- `test_settings_preserves_all_existing_controls`
- `test_settings_has_no_scroll_area`
- `test_settings_scale_picker_persists_and_calls_callback`
- 투명도/모니터/사이드바 등 나머지 SettingsWindow 테스트

- [ ] **Step 7: 전체 스위트 회귀 확인**

Run: `python -m pytest tests -q`
Expected: PASS (전체). 실패 시 해당 테스트의 위젯 참조를 확인해 수정.

- [ ] **Step 8: (선택) Commit**

```bash
git add ui_settings.py tests/test_ui.py
git commit -m "refactor(settings): 2-column section panels with unified control rail"
```

---

## Task 4: 실제 창에서 무스크롤·렌더 확인 (수동)

자동 테스트로는 "800×560 안에 스크롤 없이 다 들어가는지"와 picker 그림 렌더를 확인할 수 없다. 실행해 눈으로 확인한다.

**Files:** 없음 (검증 전용)

- [ ] **Step 1: 앱 실행 후 설정 창 열기**

Run: `python main.py`
- 트레이/메인에서 설정 창을 연다.

- [ ] **Step 2: 체크리스트 확인**

- [ ] 창이 800×560에서 **스크롤 없이** 5개 패널이 모두 보인다(좌: 화면 표시·위젯·도구 / 우: 데이터·보안·시스템).
- [ ] 각 패널 우측 컨트롤이 같은 정렬선에 맞아 있다.
- [ ] 캘린더 크기: 모니터 3개 동일 크기, 파란 앱 면적이 기본<중간<크게로 커지고, 현재 설정값이 파란 테두리로 선택돼 있다.
- [ ] picker에서 다른 크기를 클릭하면 메인 캘린더 크기가 즉시 바뀐다(콜백 동작).
- [ ] 모든 기존 컨트롤(투명도/모니터·위치/음력/바로가기/AI법령검색/내보내기·가져오기/저장경로/개인정보잠금/초기화/자동실행/글꼴/라이선스/앱종료)이 동작한다.

- [ ] **Step 3: 어긋남 발견 시 미세 조정**

세로가 넘치면 패널 `body` 마진(`_make_panel`의 `setContentsMargins(10, 2, 10, 6)`)이나 행 패딩(`_add_row`의 `(0, 6, 0, 6)`)을 줄인다. picker가 우측 레일을 벗어나면 `_ScaleOption` 패딩/`_SCREEN` 크기를 줄인다. 조정 후 Task 3 Step 6 테스트 재실행.

---

## Task 5: 문서 갱신

**Files:**
- Modify: `AGENTS.md`, `docs/UI_PATTERNS.md`

- [ ] **Step 1: `AGENTS.md` — Module Map `ui_settings.py` 줄 갱신**

"800x560 무스크롤 2열 보드 + 5개 섹션(화면 표시/위젯·도구/데이터/보안/시스템)" 표현을 **"5개 섹션 패널을 2열로 배치(무스크롤 800x560 고정), 캘린더 크기는 일러스트 picker(`CalendarSizePicker`: 고정 모니터 + 파란 앱 면적)"** 로 갱신.

- [ ] **Step 2: `AGENTS.md` — Key Constraints "설정창 레이아웃" 항목 갱신**

`ScrollArea` 없이 800×560 고정 유지·5섹션 유지는 그대로 두되, "2열 보드" → "**5개 섹션 패널 2열**, 각 행은 라벨-좌/컨트롤-우 고정폭 우측 레일 정렬" 로 보강. 캘린더 크기 컨트롤 설명 추가.

- [ ] **Step 3: `docs/UI_PATTERNS.md` — "Settings UI" 항목 갱신**

다음 취지로 갱신:
- "no-scroll two-column settings board with five sections" → "five **section panels** in two columns; each row = label-left / control-right on a unified right rail".
- 캘린더 크기 컨트롤: `CalendarSizePicker` — fixed-size monitor with a blue app block whose area maps to compact/medium/large; saves `SETTING_CALENDAR_SCALE`, no external image assets.

- [ ] **Step 4: (선택) Commit**

```bash
git add AGENTS.md docs/UI_PATTERNS.md
git commit -m "docs: update settings UI layout (section panels + size picker)"
```

---

## Self-Review (작성자 점검 완료)

- **스펙 커버리지**: ②정렬(=`_add_row` 우측 정렬, Task 3) / ④흐름(=섹션 패널 매핑, Task 3) / ⑤위계(=panelHeader, Task 3) / 캘린더 picker(Task 1–2) / 기능 불변(컨트롤·핸들러 그대로, Task 3) / 무스크롤(Task 4) / 문서(Task 5) — 모두 대응 Task 존재.
- **플레이스홀더**: 없음. 모든 코드 단계에 실제 코드 포함.
- **타입 일관성**: `CalendarSizePicker.select(str)`·`current_scale()`·`scaleChanged(str)`·`_options`(dict) / `_on_scale_changed(scale: str)` / `_make_panel`→`(panel, body)` / `_add_row(body, label, control)` 가 Task 1·2·3에서 일관.
- **기존 테스트 가드**: `test_settings_has_five_section_headers`·`test_settings_preserves_all_existing_controls`·`test_settings_has_no_scroll_area` 는 설계상 그대로 통과(헤더=StrongBodyLabel, 위젯 attr/objectName 보존, ScrollArea 미도입).
```
