# D-Day 플로팅 위젯 가시성 개선 (그림자 + 헤어라인) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** D-Day 플로팅 위젯이 어떤 바탕화면 위에서도 배경에서 또렷하게 떠 보이도록 소프트 드롭 섀도우 + 옅은 흰 헤어라인을 입힌다.

**Architecture:** `DDayWidgetWindow`(프레임리스·투명배경 톱레벨)의 창을 그림자 여백 `M`만큼 키워 투명 여백을 확보하고, 내부 컨테이너에 `QGraphicsDropShadowEffect`를 적용한다. 커버 QSS에 반투명 흰 헤어라인 1px을 더한다. 좌표 규약은 기존 "창 좌표" 그대로 두어 드래그·자동정렬·DB·`ui_main`을 전혀 건드리지 않는다. 미니 카드는 흰 배경 위라 대비 문제가 없어 대상에서 제외한다.

**Tech Stack:** Python 3.13, PySide6, qfluentwidgets, pytest + pytest-qt.

## Global Constraints

- 변경 파일은 **`ui_dday.py`**(코드), **`AGENTS.md`**(스펙), **`tests/`**(테스트)뿐. `ui_dday_panel.py`·`database.py`·`ui_main.py`·스티키/집중 위젯은 **변경 없음**.
- **좌표 규약 불변**: DB `x_pos/y_pos`와 드래그·자동정렬은 계속 "창 좌표" 기준. 보정 코드 추가 금지.
- **그림자 여백 불변식**: `SHADOW_MARGIN ≥ SHADOW_BLUR + SHADOW_OFFSET_Y` (안 지키면 그림자가 창 경계에서 잘림).
- **카드 본체 크기·팔레트 보존**: 커버 카드는 220×95 유지, `DDAY_COVER_COLORS`/`dday_cover_color()` 레거시 매핑 불변.
- **QSS `font-size`는 정수 px만** (이번 작업은 폰트 QSS 미변경).
- 초기 시각값(튜닝 대상): `SHADOW_MARGIN=14`, `SHADOW_BLUR=10`, `SHADOW_OFFSET_Y=3`, `SHADOW_ALPHA=90`, `HAIRLINE_ALPHA=45`.
- **git**: 이 워크스페이스는 현재 git 미초기화 상태다. 각 태스크 끝의 "Commit"은 저장소로 관리 중일 때만 실행하고, 아니면 그 지점을 **리뷰 체크포인트**로 삼는다.
- 상수(`SHADOW_*`, `HAIRLINE_ALPHA`)는 `ui_dday` 모듈 전역으로 노출해 테스트에서 참조한다.

---

### Task 1: 그림자 여백 확보 + 드롭 섀도우 적용

**Files:**
- Modify: `ui_dday.py` (상수 추가, `DDayWidgetWindow.__init__`의 `setFixedSize`, `_build_ui`의 `outer` 마진 + 컨테이너 효과, import)
- Test: `tests/test_ui_dday_shadow.py` (신규)

**Interfaces:**
- Consumes: `ui_sticky.WIDGET_WIDTH`(=220), `ui_sticky.DDAY_HEIGHT`(=95) — 기존 import 재사용.
- Produces: 모듈 전역 상수 `SHADOW_MARGIN:int`, `SHADOW_BLUR:int`, `SHADOW_OFFSET_Y:int`, `SHADOW_ALPHA:int`. `DDayWidgetWindow.container`에 `QGraphicsDropShadowEffect`가 설정됨. 창 크기 = `(WIDGET_WIDTH+2*SHADOW_MARGIN, DDAY_HEIGHT+2*SHADOW_MARGIN)`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_ui_dday_shadow.py` 신규 생성

```python
import pytest
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect

from ui_sticky import WIDGET_WIDTH, DDAY_HEIGHT
import ui_dday
from ui_dday import DDayWidgetWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _data(**over):
    d = {"name": "마감", "target_date": "2030-01-01",
         "color": "#46679C", "x_pos": 100, "y_pos": 100}
    d.update(over)
    return d


def test_dday_window_reserves_shadow_margin(app_dir, qtbot, qapp):
    win = DDayWidgetWindow(1, _data())
    qtbot.addWidget(win)
    m = ui_dday.SHADOW_MARGIN
    assert win.width() == WIDGET_WIDTH + 2 * m
    assert win.height() == DDAY_HEIGHT + 2 * m


def test_dday_shadow_margin_not_clipped_invariant():
    assert ui_dday.SHADOW_MARGIN >= ui_dday.SHADOW_BLUR + ui_dday.SHADOW_OFFSET_Y


def test_dday_window_has_drop_shadow(app_dir, qtbot, qapp):
    win = DDayWidgetWindow(1, _data())
    qtbot.addWidget(win)
    eff = win.container.graphicsEffect()
    assert isinstance(eff, QGraphicsDropShadowEffect)
    assert eff.blurRadius() == ui_dday.SHADOW_BLUR
    assert eff.yOffset() == ui_dday.SHADOW_OFFSET_Y
    assert eff.color().alpha() == ui_dday.SHADOW_ALPHA


def test_mini_card_has_no_shadow(app_dir, qtbot, qapp):
    """스코프 경계: 미니 카드에는 그림자를 적용하지 않는다."""
    import database as db
    from ui_dday_panel import DDayMiniCard
    wid = db.create_dday_widget("여행", "2030-01-01")
    data = next(w for w in db.get_open_dday_widgets() if w["id"] == wid)
    card = DDayMiniCard(wid, data)
    qtbot.addWidget(card)
    assert card.graphicsEffect() is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_ui_dday_shadow.py -q`
Expected: FAIL — `AttributeError: module 'ui_dday' has no attribute 'SHADOW_MARGIN'` (및 그림자 효과 None).

- [ ] **Step 3: 상수 + import 추가** — `ui_dday.py`

import 라인 수정(`QGraphicsDropShadowEffect` 추가):

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDialog,
    QGraphicsDropShadowEffect,
)
```

`WEEKDAY_NAMES = [...]` 아래에 상수 블록 추가:

```python
# ── 플로팅 카드 그림자/헤어라인 (배경에서 분리) ─────────────────
# 불변식: SHADOW_MARGIN ≥ SHADOW_BLUR + SHADOW_OFFSET_Y (아니면 창 경계에서 잘림)
SHADOW_MARGIN = 14
SHADOW_BLUR = 10
SHADOW_OFFSET_Y = 3
SHADOW_ALPHA = 90
HAIRLINE_ALPHA = 45
```

- [ ] **Step 4: 창 크기 확대** — `DDayWidgetWindow.__init__`

기존:

```python
        self.setFixedSize(WIDGET_WIDTH, DDAY_HEIGHT)
        self.move(x, y)
```

변경:

```python
        self.setFixedSize(
            WIDGET_WIDTH + 2 * SHADOW_MARGIN, DDAY_HEIGHT + 2 * SHADOW_MARGIN
        )
        self.move(x, y)
```

- [ ] **Step 5: 바깥 마진 확보 + 그림자 효과 적용** — `_build_ui`

기존:

```python
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.container = QWidget(self)
        self.container.setObjectName("ddayContainer")
        self.container.setAttribute(Qt.WA_StyledBackground, True)
        outer.addWidget(self.container)
```

변경(마진을 `SHADOW_MARGIN`으로, 컨테이너 추가 직후 그림자 효과 부착):

```python
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN
        )

        self.container = QWidget(self)
        self.container.setObjectName("ddayContainer")
        self.container.setAttribute(Qt.WA_StyledBackground, True)
        outer.addWidget(self.container)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(SHADOW_BLUR)
        shadow.setXOffset(0)
        shadow.setYOffset(SHADOW_OFFSET_Y)
        shadow.setColor(QColor(0, 0, 0, SHADOW_ALPHA))
        self.container.setGraphicsEffect(shadow)
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest tests/test_ui_dday_shadow.py -q`
Expected: PASS (`test_dday_window_has_light_hairline`은 아직 없음 — Task 2에서 추가).

- [ ] **Step 7: Commit** *(git 관리 중일 때만)*

```bash
git add ui_dday.py tests/test_ui_dday_shadow.py
git commit -m "feat(dday): 플로팅 위젯에 드롭 섀도우 + 그림자 여백 확보"
```

---

### Task 2: 옅은 흰 헤어라인 추가

**Files:**
- Modify: `ui_dday.py` (`DDayWidgetWindow._apply_color`의 커버 QSS)
- Test: `tests/test_ui_dday_shadow.py` (테스트 추가)

**Interfaces:**
- Consumes: `HAIRLINE_ALPHA:int` (Task 1에서 정의), `dday_cover_color()` (기존).
- Produces: `HAIRLINE_ALPHA > 0`일 때 `#ddayContainer` QSS에 `border:1px solid rgba(255,255,255,{HAIRLINE_ALPHA})` 포함. 커버 배경색·`border-radius:18px` 유지.

- [ ] **Step 1: 실패하는 테스트 추가** — `tests/test_ui_dday_shadow.py` 하단에 추가

```python
def test_dday_window_has_light_hairline(app_dir, qtbot, qapp):
    win = DDayWidgetWindow(1, _data())
    qtbot.addWidget(win)
    ss = win.container.styleSheet().replace(" ", "")
    assert f"rgba(255,255,255,{ui_dday.HAIRLINE_ALPHA})" in ss
    assert "border:1pxsolid" in ss
    assert "border-radius:18px" in ss
    assert "#46679C" in ss  # 커버색 유지
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_ui_dday_shadow.py::test_dday_window_has_light_hairline -q`
Expected: FAIL — 현재 QSS는 `border:none`이라 `rgba(255,255,255,45)` 미포함.

- [ ] **Step 3: 헤어라인 구현** — `_apply_color`

기존:

```python
    def _apply_color(self, hex_color: str, save: bool = True):
        """저장색을 커버 hex로 매핑해 배경 적용. 흰 타이포 전제라 테두리 없음."""
        self._color = hex_color
        cover = dday_cover_color(hex_color)
        self.container.setStyleSheet(
            f"#ddayContainer{{background:{cover};"
            "border:none;border-radius:18px;}"
        )
        if save:
            db.update_dday_widget(self.widget_id, color=hex_color)
```

변경:

```python
    def _apply_color(self, hex_color: str, save: bool = True):
        """저장색을 커버 hex로 매핑해 배경 적용.

        흰 타이포 전제. 어두운 배경 대비를 위해 옅은 흰 헤어라인 1px를 둔다
        (HAIRLINE_ALPHA=0이면 테두리 없음).
        """
        self._color = hex_color
        cover = dday_cover_color(hex_color)
        border = (
            f"border:1px solid rgba(255,255,255,{HAIRLINE_ALPHA});"
            if HAIRLINE_ALPHA > 0 else "border:none;"
        )
        self.container.setStyleSheet(
            f"#ddayContainer{{background:{cover};{border}border-radius:18px;}}"
        )
        if save:
            db.update_dday_widget(self.widget_id, color=hex_color)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_ui_dday_shadow.py -q`
Expected: PASS (5개 테스트 모두).

- [ ] **Step 5: Commit** *(git 관리 중일 때만)*

```bash
git add ui_dday.py tests/test_ui_dday_shadow.py
git commit -m "feat(dday): 커버에 옅은 흰 헤어라인 추가 (어두운 배경 대비)"
```

---

### Task 3: AGENTS.md 스펙 갱신

**Files:**
- Modify: `AGENTS.md` (Module Map의 `ui_dday.py` 행, Key Constraints의 "D-Day Cover Tint(디자인)" 항목)

**Interfaces:** 없음(문서). 소스 오브 트루스를 실제 동작과 일치시킨다.

- [ ] **Step 1: Module Map 행 갱신** — `ui_dday.py` 설명의 크기 표기

기존 문구 중:

```
| `ui_dday.py` | D-Day widgets: 220x95 fixed, color picker, double-click edit, 1-min auto-refresh.
```

변경:

```
| `ui_dday.py` | D-Day widgets: 카드 본체 220x95(창은 그림자 여백 `SHADOW_MARGIN`만큼 큼), color picker, double-click edit, 1-min auto-refresh.
```

- [ ] **Step 2: Cover Tint 제약 문구 갱신** — "테두리 없음" 부분

기존 문구 중:

```
컨테이너는 **테두리 없음**·radius 18(플로팅)/12(미니), 좌하단 큰 카운트·우하단 날짜 구도.
```

변경:

```
플로팅 위젯은 **소프트 드롭 섀도우 + 옅은 흰 헤어라인(`rgba(255,255,255,HAIRLINE_ALPHA)`)으로 배경에서 분리**(창을 `SHADOW_MARGIN`만큼 키워 그림자 여백 확보, 좌표 규약은 창 좌표 그대로 유지). 미니 카드(`ui_dday_panel.py`)는 흰 패널 위라 대비 문제가 없어 종전대로 **테두리 없음** 유지. radius 18(플로팅)/12(미니), 좌하단 큰 카운트·우하단 날짜 구도.
```

- [ ] **Step 3: 정합성 확인**

Run: `python -m pytest tests -q`
Expected: PASS (문서 변경은 테스트에 영향 없음 — 회귀 없음 확인용).

- [ ] **Step 4: Commit** *(git 관리 중일 때만)*

```bash
git add AGENTS.md
git commit -m "docs(agents): D-Day 플로팅 위젯 그림자/헤어라인 스펙 반영"
```

---

### Task 4: 전체 테스트 + 실측 스크린샷 튜닝

**Files:**
- Modify(필요 시): `ui_dday.py` 상수 값 (`SHADOW_*`, `HAIRLINE_ALPHA`) — 시각 튜닝만.

**Interfaces:** 없음(값 튜닝). 불변식 `SHADOW_MARGIN ≥ SHADOW_BLUR + SHADOW_OFFSET_Y` 유지.

- [ ] **Step 1: 전체 테스트 실행**

Run: `python -m pytest tests -q`
Expected: PASS (기존 + 신규 전부).

- [ ] **Step 2: 앱 실행 후 스크린샷 캡쳐**

앱을 실행(`python main.py`)하고 D-Day 위젯이 강한 파란 바탕화면 위에 뜬 모니터를 캡쳐한다. PowerShell 예:

```powershell
Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing
$s = [System.Windows.Forms.Screen]::AllScreens | Where-Object { -not $_.Primary }
$b = $s.Bounds
$bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size)
$bmp.Save("$env:TEMP\dday_after.png", [System.Drawing.Imaging.ImageFormat]::Png)
```

- [ ] **Step 3: 육안 검증 및 튜닝**

수용 기준:
- 하늘색 커버(`#46679C`) 카드가 강한 파란 바탕화면에서 **경계가 또렷하게 분리**되어 보인다.
- 헤어라인이 과하지 않다(선명한 흰 테두리처럼 도드라지지 않고 은은한 가장자리 광택 수준).
- 그림자가 창 경계에서 잘리지 않는다.

미흡하면 `SHADOW_BLUR`/`SHADOW_OFFSET_Y`/`SHADOW_ALPHA`/`HAIRLINE_ALPHA`를 조정한다.
`SHADOW_BLUR`/`SHADOW_OFFSET_Y`를 키우면 `SHADOW_MARGIN`도 불변식(`≥ blur + offset`)을 지키도록 함께 키운다. 값 변경 시 `test_dday_window_has_drop_shadow`가 상수 참조라 자동으로 따라간다.

- [ ] **Step 4: 튜닝 반영 시 테스트 재실행 + Commit** *(git 관리 중일 때만)*

```bash
python -m pytest tests/test_ui_dday_shadow.py -q
git add ui_dday.py
git commit -m "tune(dday): 실측 기준 그림자/헤어라인 값 조정"
```
