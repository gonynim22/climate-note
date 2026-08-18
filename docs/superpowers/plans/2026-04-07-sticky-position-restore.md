# Sticky Note / Calendar Position Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect screen geometry changes (dual monitor / GPU switch) and restore all windows (calendar, sticky notes, D-Day widgets) to their DB-saved positions, clamping any off-screen windows back into view.

**Architecture:** Add two setting constants for calendar position. Save calendar position on drag release. On startup, restore saved position (fallback to bottom-right). Connect `screenAdded`/`screenRemoved`/`geometryChanged` signals with a 500ms debounce timer to a handler that re-reads all positions from DB and clamps off-screen windows.

**Tech Stack:** PySide6 (QApplication.screens, QScreen signals, QTimer), SQLite via `database.py`

---

### Task 1: Save and restore calendar position

**Files:**
- Modify: `database.py:16-21` (add setting key constants)
- Modify: `ui_main.py:218` (startup position restore)
- Modify: `ui_main.py:1224-1225` (save position on drag release)

- [ ] **Step 1: Add calendar position setting constants to `database.py`**

In `database.py`, after line 21 (`SETTING_SHOW_LAW_SEARCH = "show_law_search"`), add:

```python
SETTING_CALENDAR_X = "calendar_x"
SETTING_CALENDAR_Y = "calendar_y"
```

- [ ] **Step 2: Save calendar position on drag release in `ui_main.py`**

Replace `mouseReleaseEvent` (line 1224-1225):

```python
def mouseReleaseEvent(self, event):
    self._drag_pos = None
```

With:

```python
def mouseReleaseEvent(self, event):
    self._drag_pos = None
    db.save_setting(db.SETTING_CALENDAR_X, str(self.x()))
    db.save_setting(db.SETTING_CALENDAR_Y, str(self.y()))
```

- [ ] **Step 3: Restore saved calendar position on startup**

In `__init__`, replace line 218:

```python
self._position_to_bottom_right()
```

With:

```python
saved_x = db.get_setting(db.SETTING_CALENDAR_X, "")
saved_y = db.get_setting(db.SETTING_CALENDAR_Y, "")
if saved_x and saved_y:
    self.move(int(saved_x), int(saved_y))
else:
    self._position_to_bottom_right()
```

- [ ] **Step 4: Verify manually**

Run: `python main.py`
1. Drag the calendar to a new position, close the app.
2. Re-launch — the calendar should appear at the saved position.
3. Delete `calendar_x`/`calendar_y` from DB (or fresh DB) — calendar should appear at bottom-right.

- [ ] **Step 5: Commit**

```bash
git add database.py ui_main.py
git commit -m "feat: save and restore calendar position on startup"
```

---

### Task 2: Screen change detection and position restore with off-screen clamping

**Files:**
- Modify: `ui_main.py:190-227` (`__init__` — add debounce timer and signal connections)
- Modify: `ui_main.py` (add new method `_on_screen_changed`)

- [ ] **Step 1: Add debounce timer and screen change signal connections in `__init__`**

After the periodic save timer block (after line 227, `self._periodic_save_timer.start()`), add:

```python
# ── 화면 변경 감지 (듀얼 모니터/GPU 전환) ──
self._screen_change_timer = QTimer(self)
self._screen_change_timer.setSingleShot(True)
self._screen_change_timer.setInterval(500)
self._screen_change_timer.timeout.connect(self._on_screen_changed)

app = QApplication.instance()
app.screenAdded.connect(lambda: self._screen_change_timer.start())
app.screenRemoved.connect(lambda: self._screen_change_timer.start())
for screen in app.screens():
    screen.geometryChanged.connect(lambda: self._screen_change_timer.start())
```

- [ ] **Step 2: Implement `_on_screen_changed` method**

Add this method before the `# ─── 잠금 기능 ──` section (before line 1227). Place it right after `mouseReleaseEvent`:

```python
def _on_screen_changed(self):
    """화면 구성 변경 시 모든 창의 위치를 DB 저장값으로 복원하고, 화면 밖이면 보정"""
    screens = QApplication.screens()
    if not screens:
        return

    def _clamp_to_screen(win):
        """창이 모든 모니터 밖에 있으면 가장 가까운 화면 안쪽으로 이동"""
        pos = win.pos()
        for scr in screens:
            if scr.availableGeometry().contains(pos):
                return  # 화면 안에 있음
        # 가장 가까운 화면 찾기
        min_dist = float("inf")
        nearest_geo = screens[0].availableGeometry()
        for scr in screens:
            geo = scr.availableGeometry()
            cx = max(geo.left(), min(pos.x(), geo.right()))
            cy = max(geo.top(), min(pos.y(), geo.bottom()))
            dist = (pos.x() - cx) ** 2 + (pos.y() - cy) ** 2
            if dist < min_dist:
                min_dist = dist
                nearest_geo = geo
        x = max(nearest_geo.left(), min(pos.x(), nearest_geo.right() - win.width()))
        y = max(nearest_geo.top(), min(pos.y(), nearest_geo.bottom() - win.height()))
        win.move(x, y)
        return True  # 위치가 보정됨

    # 1) 캘린더 위치 복원
    saved_x = db.get_setting(db.SETTING_CALENDAR_X, "")
    saved_y = db.get_setting(db.SETTING_CALENDAR_Y, "")
    if saved_x and saved_y:
        self.move(int(saved_x), int(saved_y))
    if _clamp_to_screen(self):
        db.save_setting(db.SETTING_CALENDAR_X, str(self.x()))
        db.save_setting(db.SETTING_CALENDAR_Y, str(self.y()))

    # 2) 스티키 노트 위치 복원
    for note_id, win in self._sticky_windows.items():
        try:
            notes = db.get_open_sticky_notes()
            note_data = next((n for n in notes if n["id"] == note_id), None)
            if note_data:
                win.move(note_data["x_pos"], note_data["y_pos"])
            if _clamp_to_screen(win):
                db.update_sticky_note(note_id, x_pos=win.x(), y_pos=win.y())
        except (sqlite3.Error, OSError) as e:
            _logger.warning("스티키 노트 위치 복원 실패 (id=%s): %s", note_id, e)

    # 3) D-Day 위젯 위치 복원
    for widget_id, win in self._dday_windows.items():
        try:
            widgets = db.get_open_dday_widgets()
            widget_data = next((w for w in widgets if w["id"] == widget_id), None)
            if widget_data:
                win.move(widget_data["x_pos"], widget_data["y_pos"])
            if _clamp_to_screen(win):
                db.update_dday_widget(widget_id, x_pos=win.x(), y_pos=win.y())
        except (sqlite3.Error, OSError) as e:
            _logger.warning("D-Day 위젯 위치 복원 실패 (id=%s): %s", widget_id, e)
```

- [ ] **Step 3: Verify manually**

Run: `python main.py`
1. Open several sticky notes and D-Day widgets, position them.
2. Change display resolution or disconnect/reconnect a monitor.
3. Verify that all windows snap back to their saved positions.
4. Move a window off-screen (e.g., via resolution shrink) and trigger a screen change — verify it gets clamped.

- [ ] **Step 4: Commit**

```bash
git add ui_main.py
git commit -m "feat: restore window positions on screen geometry change with off-screen clamping"
```

---

### Task 3: Optimize — avoid repeated DB queries in `_on_screen_changed`

**Files:**
- Modify: `ui_main.py` (`_on_screen_changed` method)

- [ ] **Step 1: Refactor to batch DB reads**

The current implementation calls `get_open_sticky_notes()` and `get_open_dday_widgets()` inside a loop (once per window). Refactor to read each list once:

Replace the sticky notes and D-Day sections in `_on_screen_changed` with:

```python
    # 2) 스티키 노트 위치 복원
    try:
        notes = db.get_open_sticky_notes()
        note_map = {n["id"]: n for n in notes}
    except (sqlite3.Error, OSError) as e:
        _logger.warning("스티키 노트 목록 조회 실패: %s", e)
        note_map = {}
    for note_id, win in self._sticky_windows.items():
        note_data = note_map.get(note_id)
        if note_data:
            win.move(note_data["x_pos"], note_data["y_pos"])
        if _clamp_to_screen(win):
            try:
                db.update_sticky_note(note_id, x_pos=win.x(), y_pos=win.y())
            except (sqlite3.Error, OSError) as e:
                _logger.warning("스티키 노트 위치 보정 저장 실패 (id=%s): %s", note_id, e)

    # 3) D-Day 위젯 위치 복원
    try:
        widgets = db.get_open_dday_widgets()
        widget_map = {w["id"]: w for w in widgets}
    except (sqlite3.Error, OSError) as e:
        _logger.warning("D-Day 위젯 목록 조회 실패: %s", e)
        widget_map = {}
    for widget_id, win in self._dday_windows.items():
        widget_data = widget_map.get(widget_id)
        if widget_data:
            win.move(widget_data["x_pos"], widget_data["y_pos"])
        if _clamp_to_screen(win):
            try:
                db.update_dday_widget(widget_id, x_pos=win.x(), y_pos=win.y())
            except (sqlite3.Error, OSError) as e:
                _logger.warning("D-Day 위젯 위치 보정 저장 실패 (id=%s): %s", widget_id, e)
```

- [ ] **Step 2: Verify manually**

Same verification as Task 2 Step 3 — behavior should be identical but with fewer DB calls.

- [ ] **Step 3: Commit**

```bash
git add ui_main.py
git commit -m "refactor: batch DB reads in screen change handler"
```
