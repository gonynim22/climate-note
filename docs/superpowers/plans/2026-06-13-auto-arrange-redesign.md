# 자동정렬 재설계 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `_on_arrange_sticky_notes`의 캘린더 겹침·세로 넘침 버그를 수정하고, 배치 계산을 순수 함수 `_compute_arrange_layout`으로 추출해 테스트 가능하게 만든다.

**Architecture:** 배치 계산(기하)을 Qt/DB 없는 순수 함수 `_compute_arrange_layout`으로 분리한다. 수직 방향은 캘린더 바깥에서 시작해 멀어지는 방향으로 쌓도록 재설계하며(겹침 원천 차단), 세로 넘침 시 클램프로 화면 밖 유실을 방지한다. `_on_arrange_sticky_notes`는 수집·호출·이동·DB저장·InfoBar 역할만 담당한다.

**Tech Stack:** Python, PySide6, SQLite (via `database.py`), pytest

---

## 파일 맵

| 파일 | 변경 | 내용 |
|---|---|---|
| `ui_main.py` | 수정 | `_compute_arrange_layout` 추가 (line 69 이후), `_on_arrange_sticky_notes` 교체 (line 2245~2311) |
| `tests/test_ui.py` | 수정 | `_compute_arrange_layout` 임포트 추가, 테스트 5개 추가 |

---

## Task 1: `_compute_arrange_layout` 순수 함수 추가 + TDD

**Files:**
- Modify: `ui_main.py` (line 69 이후에 함수 추가)
- Modify: `tests/test_ui.py` (임포트 + 테스트 5개 추가)

---

- [ ] **Step 1-1: 임포트에 `_compute_arrange_layout` 추가 (아직 존재 안 함 — 테스트가 ImportError로 실패하도록)**

`tests/test_ui.py` line 22-28:
```python
# 변경 전
from ui_main import (
    MainCalendarWindow,
    ShortcutSidebarWidget,
    _calendar_corner_coordinates,
    _right_aligned_grid_x,
    _snap_not_past_right,
)
```
```python
# 변경 후
from ui_main import (
    MainCalendarWindow,
    ShortcutSidebarWidget,
    _calendar_corner_coordinates,
    _compute_arrange_layout,
    _right_aligned_grid_x,
    _snap_not_past_right,
)
```

---

- [ ] **Step 1-2: 테스트 5개 작성**

`tests/test_ui.py` 파일 끝에 추가:
```python
# ─── _compute_arrange_layout 순수 함수 테스트 ────────────────────────────────

def test_arrange_layout_empty_returns_empty():
    coords, clamped = _compute_arrange_layout(
        [], (0, 0, 100, 100), (0, 0, 1920, 1080), "bottom-right", 19
    )
    assert coords == []
    assert clamped == 0


def test_arrange_layout_all_within_screen():
    """정상 케이스: clamped == 0, 모든 위젯이 화면 안."""
    items = [(220, 95), (220, 95), (241, 78)]
    cal = (1600, 800, 1920, 1080)
    scr = (0, 0, 1920, 1080)
    snap = 19
    coords, clamped = _compute_arrange_layout(items, cal, scr, "bottom-right", snap)
    assert clamped == 0
    for (x, y), (w, h) in zip(coords, items):
        assert scr[0] <= x, f"x={x} < screen left"
        assert x + w <= scr[2], f"x+w={x+w} > screen right"
        assert scr[1] <= y, f"y={y} < screen top"
        assert y + h <= scr[3], f"y+h={y+h} > screen bottom"


def test_arrange_layout_no_overlap_with_calendar():
    """4모서리 각각: 위젯 사각형이 캘린더와 겹치지 않음."""
    items = [(220, 95), (220, 95)]
    snap = 19
    cases = [
        ("bottom-right", (1600, 800, 1920, 1080)),
        ("bottom-left",  (0,    800, 320,  1080)),
        ("top-right",    (1600, 0,   1920, 200)),
        ("top-left",     (0,    0,   320,  200)),
    ]
    scr = (0, 0, 1920, 1080)
    for pos, cal in cases:
        coords, _ = _compute_arrange_layout(items, cal, scr, pos, snap)
        for (x, y), (w, h) in zip(coords, items):
            wx1, wy1, wx2, wy2 = x, y, x + w, y + h
            cx1, cy1, cx2, cy2 = cal
            overlap = (wx2 > cx1 and cx2 > wx1 and wy2 > cy1 and cy2 > wy1)
            assert not overlap, f"pos={pos}: widget ({wx1},{wy1},{wx2},{wy2}) overlaps calendar {cal}"


def test_arrange_layout_vertical_overflow_clamped():
    """세로 공간 부족 → clamped > 0, 모든 y는 화면 안."""
    # scr 폭 500px, 위젯 220px → 행당 2개.
    # cal.top=150, scr.top=0, gap=19:
    #   row1: y=131-95=36 (OK), row2: y=17-95=-78 → clamp → clamped=2
    items = [(220, 95)] * 4
    cal = (300, 150, 500, 200)
    scr = (0, 0, 500, 200)
    snap = 19
    coords, clamped = _compute_arrange_layout(items, cal, scr, "bottom-right", snap)
    assert clamped == 2
    for (x, y), (w, h) in zip(coords, items):
        assert scr[1] <= y, f"y={y} went above screen top"


def test_arrange_layout_four_positions_direction():
    """right계: widget.right <= cal.right / left계: widget.x >= cal.left."""
    items = [(220, 95)]
    snap = 19
    scr = (0, 0, 1920, 1080)

    for pos, cal in [("bottom-right", (1600, 800, 1920, 1080)),
                     ("top-right",    (1600, 0,   1920, 200))]:
        coords, _ = _compute_arrange_layout(items, cal, scr, pos, snap)
        x, _ = coords[0]
        assert x + items[0][0] <= cal[2], f"{pos}: widget right {x+items[0][0]} > cal.right {cal[2]}"

    for pos, cal in [("bottom-left", (0, 800, 320, 1080)),
                     ("top-left",    (0, 0,   320, 200))]:
        coords, _ = _compute_arrange_layout(items, cal, scr, pos, snap)
        x, _ = coords[0]
        assert x >= cal[0], f"{pos}: widget left {x} < cal.left {cal[0]}"
```

---

- [ ] **Step 1-3: 테스트 실패 확인**

```
python -m pytest tests/test_ui.py::test_arrange_layout_empty_returns_empty tests/test_ui.py::test_arrange_layout_all_within_screen tests/test_ui.py::test_arrange_layout_no_overlap_with_calendar tests/test_ui.py::test_arrange_layout_vertical_overflow_clamped tests/test_ui.py::test_arrange_layout_four_positions_direction -v
```

기대 결과: `ImportError: cannot import name '_compute_arrange_layout'` 또는 전체 FAILED.

---

- [ ] **Step 1-4: `_compute_arrange_layout` 구현**

`ui_main.py` line 64-67 (`_clamp_window_pos` 함수 직후):

```python
# ─── 변경 전 (line 64~68) ───────────────────────────────────────────────────
def _clamp_window_pos(value: int, lower: int, upper: int) -> int:
    if upper < lower:
        return lower
    return max(lower, min(value, upper))


```

```python
# ─── 변경 후 ────────────────────────────────────────────────────────────────
def _clamp_window_pos(value: int, lower: int, upper: int) -> int:
    if upper < lower:
        return lower
    return max(lower, min(value, upper))


def _compute_arrange_layout(items, cal, scr, position, snap):
    """플로팅 위젯 배치 좌표 순수 계산. Qt/DB 없음.

    Args:
        items:    [(width, height), ...]
        cal:      (left, top, right, bottom) — 캘린더 geometry
        scr:      (left, top, right, bottom) — 사용 가능 화면 geometry
        position: "bottom-right" | "bottom-left" | "top-right" | "top-left"
        snap:     픽셀 단위 스냅 크기

    Returns:
        ([(x, y), ...], clamped_count)
        clamped_count: 화면 안으로 클램프된 위젯 수 (겹쳐 배치됨)
    """
    if not items:
        return [], 0

    gap = snap
    is_right = "right" in position
    is_bottom = "bottom" in position
    cal_left, cal_top, cal_right, cal_bottom = cal
    scr_left, scr_top, scr_right, scr_bottom = scr

    # ── 1단계: 행 그루핑 (수평) ──────────────────────────────────────
    rows = []        # list of [(item_idx, w, h, x), ...]
    current_row = []

    if is_right:
        x_anchor = _snap_not_past_right(cal_right, snap)
        x = x_anchor
        x_limit = scr_left + gap
        for i, (w, h) in enumerate(items):
            tx = _right_aligned_grid_x(x, w, snap)
            if tx < x_limit and current_row:
                rows.append(current_row)
                current_row = []
                x = x_anchor
                tx = _right_aligned_grid_x(x, w, snap)
            current_row.append((i, w, h, tx))
            x = tx - gap
    else:
        x_anchor = round(cal_left / snap) * snap
        x = x_anchor
        x_limit = scr_right - gap
        for i, (w, h) in enumerate(items):
            tx = round(x / snap) * snap
            if tx + w > x_limit and current_row:
                rows.append(current_row)
                current_row = []
                x = x_anchor
                tx = round(x_anchor / snap) * snap
            current_row.append((i, w, h, tx))
            x = tx + w + gap

    if current_row:
        rows.append(current_row)

    # ── 2단계: Y 좌표 배분 (수직) ────────────────────────────────────
    coords = [None] * len(items)
    clamped = 0

    if is_bottom:
        # 캘린더 위쪽 공간에 위로 쌓기 — 마지막 행이 캘린더에 가장 가까움
        y_bottom = cal_top - gap
        overflow = False
        for row in rows:
            row_h = max(h for _, _, h, _ in row)
            y = y_bottom - row_h
            if overflow or y < scr_top + gap:
                if not overflow:
                    y = scr_top + gap
                overflow = True
                clamped += len(row)
            for idx, w, h, rx in row:
                coords[idx] = (rx, y)
            if not overflow:
                y_bottom = y - gap
    else:
        # 캘린더 아래쪽 공간에 아래로 쌓기 — 첫 행이 캘린더에 가장 가까움
        y = cal_bottom + gap
        overflow = False
        for row in rows:
            row_h = max(h for _, _, h, _ in row)
            if overflow or y + row_h > scr_bottom - gap:
                if not overflow:
                    y = max(scr_top, scr_bottom - row_h - gap)
                overflow = True
                clamped += len(row)
            for idx, w, h, rx in row:
                coords[idx] = (rx, y)
            if not overflow:
                y += row_h + gap

    return coords, clamped


```

---

- [ ] **Step 1-5: 테스트 통과 확인**

```
python -m pytest tests/test_ui.py::test_arrange_layout_empty_returns_empty tests/test_ui.py::test_arrange_layout_all_within_screen tests/test_ui.py::test_arrange_layout_no_overlap_with_calendar tests/test_ui.py::test_arrange_layout_vertical_overflow_clamped tests/test_ui.py::test_arrange_layout_four_positions_direction -v
```

기대 결과: 5개 모두 PASSED.

---

- [ ] **Step 1-6: 기존 스냅 테스트도 통과 확인**

```
python -m pytest tests/test_ui.py::test_right_arrange_snap_does_not_reduce_calendar_margin tests/test_ui.py::test_right_arrange_snap_preserves_negative_monitor_margin -v
```

기대 결과: 2개 PASSED (함수 시그니처 변경 없으므로).

---

- [ ] **Step 1-7: 커밋**

```
git add ui_main.py tests/test_ui.py
git commit -m "feat: extract _compute_arrange_layout pure function with tests

캘린더 겹침·세로 넘침 버그 수정을 위한 순수 배치 계산 함수 분리.
Qt/DB 없는 단위 테스트 5개 추가."
```

---

## Task 2: `_on_arrange_sticky_notes` 리팩토링

**Files:**
- Modify: `ui_main.py` (line 2245~2311, 함수 본문 교체)

---

- [ ] **Step 2-1: `_on_arrange_sticky_notes` 본문 교체**

`ui_main.py` line 2245~2311, 다음 내용으로 교체:

```python
# ─── 변경 전 (line 2245~2311) ────────────────────────────────────────────────
    def _on_arrange_sticky_notes(self):
        """열린 모든 플로팅 위젯을 캘린더 위치 기준 그리드 배열 (5mm 스냅)"""
        visible_sticky = [w for w in self._sticky_windows.values() if w.isVisible()]
        visible_dday = [w for w in self._dday_windows.values() if w.isVisible()]
        visible_focus = [w for w in self._focus_windows.values() if w.isVisible()]
        visible = visible_dday + visible_focus + visible_sticky
        if not visible:
            InfoBar.info(
                title="정렬",
                content="열린 노트/위젯이 없습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=2000,
            )
            return

        # 5mm 스냅 그리드 모두 적용 (X, Y)
        scr = self._get_target_screen()
        snap = max(1, round(scr.physicalDotsPerInch() * 5 / 25.4)) if scr else 19
        _snap = lambda v: round(v / snap) * snap

        screen = scr.availableGeometry() if scr else QApplication.primaryScreen().availableGeometry()
        gap = snap  # 간격도 스냅 단위
        pos = db.get_setting(db.SETTING_CALENDAR_POSITION, "bottom-right")
        is_right = "right" in pos

        if is_right:
            start_x = _snap_not_past_right(self.x() + self.width(), snap)
        else:
            start_x = _snap(self.x())

        if "top" in pos:
            start_y = _snap(self.y() + self.height() + gap)
        else:
            start_y = _snap(screen.top() + gap)

        x = start_x
        y = start_y
        row_max_height = 0

        for win in visible:
            if is_right:
                target_x = _right_aligned_grid_x(x, win.width(), snap)
                if target_x < screen.left() + gap:
                    x = start_x
                    y = _snap(y + row_max_height + gap)
                    row_max_height = 0
                    target_x = _right_aligned_grid_x(x, win.width(), snap)
                win.move(target_x, y)
                x = target_x - gap
            else:
                target_x = _snap(x)
                if target_x + win.width() > screen.right() - gap:
                    x = start_x
                    y = _snap(y + row_max_height + gap)
                    row_max_height = 0
                    target_x = _snap(x)
                win.move(target_x, y)
                x = target_x + win.width() + gap

            if hasattr(win, "note_id"):
                db.update_sticky_note(win.note_id, x_pos=target_x, y_pos=y)
            elif win in self._dday_windows.values():
                db.update_dday_widget(win.widget_id, x_pos=target_x, y_pos=y)
            elif win in self._focus_windows.values():
                db.update_focus_widget(win.widget_id, x_pos=target_x, y_pos=y)
            row_max_height = max(row_max_height, win.height())
```

```python
# ─── 변경 후 ────────────────────────────────────────────────────────────────
    def _on_arrange_sticky_notes(self):
        """열린 모든 플로팅 위젯을 캘린더 바깥 기준 그리드 배열 (5mm 스냅)"""
        visible_sticky = sorted(
            (w for w in self._sticky_windows.values() if w.isVisible()),
            key=lambda w: w.height(),
            reverse=True,
        )
        visible_dday = [w for w in self._dday_windows.values() if w.isVisible()]
        visible_focus = [w for w in self._focus_windows.values() if w.isVisible()]
        visible = visible_dday + visible_focus + visible_sticky

        if not visible:
            InfoBar.info(
                title="정렬",
                content="열린 노트/위젯이 없습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=2000,
            )
            return

        scr = self._get_target_screen()
        snap = max(1, round(scr.physicalDotsPerInch() * 5 / 25.4)) if scr else 19
        screen_geo = scr.availableGeometry() if scr else QApplication.primaryScreen().availableGeometry()

        cal = (
            self.x(),
            self.y(),
            self.x() + self.width(),
            self.y() + self.height(),
        )
        scr_tuple = (
            screen_geo.left(), screen_geo.top(),
            screen_geo.right(), screen_geo.bottom(),
        )
        pos = db.get_setting(db.SETTING_CALENDAR_POSITION, "bottom-right")
        items = [(w.width(), w.height()) for w in visible]

        coords, clamped = _compute_arrange_layout(items, cal, scr_tuple, pos, snap)

        for win, (x, y) in zip(visible, coords):
            win.move(x, y)
            if hasattr(win, "note_id"):
                db.update_sticky_note(win.note_id, x_pos=x, y_pos=y)
            elif win in self._dday_windows.values():
                db.update_dday_widget(win.widget_id, x_pos=x, y_pos=y)
            elif win in self._focus_windows.values():
                db.update_focus_widget(win.widget_id, x_pos=x, y_pos=y)

        if clamped:
            InfoBar.warning(
                title="정렬",
                content=f"공간 부족으로 {clamped}개 위젯이 겹쳐 배치되었습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=3000,
            )
```

---

- [ ] **Step 2-2: 전체 테스트 통과 확인**

```
python -m pytest tests -q
```

기대 결과: 모두 PASSED, 실패 0.

---

- [ ] **Step 2-3: 커밋**

```
git add ui_main.py
git commit -m "refactor: fix auto-arrange calendar overlap and vertical overflow

- 위젯을 캘린더 바깥쪽 변에서 시작해 멀어지는 방향으로 배치 (겹침 원천 차단)
- 세로 넘침 시 화면 최상단으로 클램프, InfoBar.warning 안내
- 스티키 노트 높이 내림차순 정렬으로 row_max_height 낭비 최소화"
```

---

## 자체 검토

**스펙 커버리지 체크:**
- [x] 버그 1 (세로 넘침) → Task 1 `_compute_arrange_layout` is_bottom/top 오버플로 분기
- [x] 버그 2 (캘린더 겹침) → `cal_top - gap` / `cal_bottom + gap` 시작점
- [x] 배치 품질 3·4 (들쭉날쭉, 큰 스티키) → 스티키 높이 desc 정렬 (Task 2 Step 2-1)
- [x] 기존 5mm 스냅 유지 → `_snap_not_past_right`/`_right_aligned_grid_x` 재사용
- [x] DB 즉시 저장 → Task 2 루프 내 update_* 호출
- [x] InfoBar.warning → Task 2 Step 2-1 마지막 블록

**Placeholder 없음** ✓  
**타입 일관성:** `_compute_arrange_layout` 반환 `list[tuple[int,int]]`을 Task 2에서 `(x, y)` 언패킹으로 그대로 사용 ✓
