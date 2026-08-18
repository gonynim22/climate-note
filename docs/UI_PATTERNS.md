# UI Patterns Reference

## Layout

- **Two-Tone Layout**: `#mainContainer` (transparent wrapper) → `#headerSection` (navy `#01295F`, top-rounded) + `#calendarSection` (white `#FFFFFF`, bottom-rounded). Header uses individual `border-*-radius` properties for Qt stylesheet compatibility.
- **Header (Navy)**: Month label (`"26년 3월"`), nav buttons (◀▶), "오늘" button — all white text/icons on `#01295F`. Icon buttons use `FIF.xxx.icon(Theme.DARK)` for forced white icons. Nav group (◀ label ▶) is a sub-layout; `addStretch()` separates it from right-aligned action buttons.
- **Font**: Malgun Gothic is the default app font. App text fonts are not bundled; users can switch between installed system fonts in Settings, and the selection is saved immediately and applied after app restart. Sticky todo backing markers remain Font Awesome-compatible, while their visible checkbox is painted as a vector control.
- **Font Sizes**: Use integer `px` values only in QSS (`12px`, `14px`, etc.). Avoid fractional pixel sizes because they blur more noticeably in Windows Qt rendering.
- **Theme**: Windows registry polling for light/dark mode sync every 60s. Header is always navy (`#01295F`), calendar section always white (`#FFFFFF`). qfluentwidgets icon buttons in header use `Theme.DARK` for white icon rendering regardless of OS theme.

---

## Calendar

- **Calendar Cells**: `CalendarDayButton(QWidget)` supports compact and expanded modes. Compact keeps the 3-row [Day Number] / [Color Squares] / [Total Count] structure. Expanded shows one-line colored schedule chips, elides long titles, and ends overflow with `+N 더` while preserving at least one real event chip.
- **Calendar Scale**: `compact` keeps the schedule panel below the calendar. `medium` and `large` force the shortcut sidebar visible and re-parent the schedule panel into a right column, producing [shortcuts | calendar | schedules].
- **Calendar Drag**: Drag only the navy header background or month label. Movement below `QApplication.startDragDistance()` remains a click. A completed drag resizes medium/large layouts for the destination screen, clamps the full window, then stores free coordinates, target screen, and nearest corner. Saved target screen wins over a newly calculated center when the window changes size. Navigation/search/settings controls keep their normal click behavior; Monitor or corner selection in Settings switches back to corner placement.
- **Window Opacity**: The saved 30-100 percent opacity is applied immediately to the main window and all sticky/D-Day/focus widgets.
- **Schedule Color Squares & Count**: `_refresh_calendar()` calls `db.get_all_schedule_date_colors()` and `db.get_all_schedule_date_counts()` once each. Raw schedule colors remain the three canonical slot tokens; `db.schedule_display_color()` resolves the selected display palette for compact squares, expanded chips, the schedule list, color-cycle button, and search results. `_refresh_cell_for_date()` updates a changed date in place.
- **Schedule Inline Edit**: Double-click a schedule item to edit in-place. Enter saves, Escape cancels, focus-out saves. Uses `db.update_schedule()` for encrypted update. `_editing_item` guard prevents concurrent edits.
- **Lunar Setting**: Cached as `self._show_lunar` on `MainCalendarWindow`, refreshed once per `_refresh_calendar()` (not per cell). It now gates ONLY the bottom-panel lunar-date text (`lunar_info_label`). Holiday highlighting (red day number) and the bottom-panel holiday name (`holiday_info_label`) are always shown regardless of this setting (holiday = rest day). Holiday lookup uses `holidays.is_holiday()` / `holidays.get_holiday()`.

---

## Settings UI

- Organized as a no-scroll (800x560) layout of five **section panels** in two columns: 화면 표시, 위젯·도구 (left); 데이터, 보안, 시스템 (right). No large in-window "설정" title. Each panel is a `CardWidget` with a `StrongBodyLabel` header (objectName `panelHeader`) on a light `#F6F6F6` strip (`panelHeaderBar`) built by `_make_panel`; header color/weight are fixed via `setTextColor(#1A1A1E)` + `setFont(Bold)` (not QSS) so theme re-application can't wash them out. The panel body does not darken on hover. Each setting is a `_add_row(body, label, control)` row with label-left / control-right on a unified right rail; the 화면 위치 row (`_position_row`) is min-height 60. Footer credit (`author_label`) is single-line (`wordWrap(False)`). Monitor combo width 210.
- **Calendar size** uses `CalendarSizePicker` (not a combo): three same-size monitor illustrations whose blue app block area grows for `compact`/`medium`/`large` (anchored bottom-right, the app's default corner). Pure `QFrame` + QSS, no external image assets; selection highlight via a `selected` style property. Emits `scaleChanged(str)` → `_on_scale_changed(scale)` → saves `SETTING_CALENDAR_SCALE`.
- **Schedule colors** use `ScheduleColorPicker`: three compact swatches map to the three canonical storage slots. Each opens a 10-color `RoundMenu`; colors already used by another slot are disabled. Saving changes only `app_settings`, then immediately repaints the app.
- PIN validated via `_validate_pin(pin)` helper — used by 데이터 Export/Import only.
- **데이터 초기화(Factory Reset)** uses no PIN (usability decision): soft-danger red button (`factoryResetButton`) → confirm `MessageBox` only. 앱 종료 (`quitAppButton`, dark) closes the settings window first, then `QApplication.quit()` (so one click fully exits).

---

## Sticky Notes

- `StickyNoteWindow.save()` is the public entry point for external saves. Internal: `_auto_save_content()`.
- 4 background colors (노랑/민트/보라/하늘).
- Color button styled as rounded rectangle matching B/S/A format buttons.
- `_ColorGridPopup._on_pick()` calls `deleteLater()` on close to prevent memory accumulation.
- Todo markers (`\uf0c8`/`\uf14a`, plus legacy `☐`/`☑`) stay unchanged in plain text and HTML. A `QSyntaxHighlighter` masks only their rendered glyph and `_TodoTextEdit.paintEvent()` draws a 15px rounded checkbox with a roughly 22px hit target, hover accent, and checked tick. Body text clicks must not be captured by the expanded target.

---

## D-Day Widgets

- Floating 220x95 countdown windows. Created via "+" dropdown menu. Double-click to edit name/date.
- `DDayCreateDialog` for input, `DDayWidgetWindow` for display. 1-minute refresh timer for midnight rollover.
- Uses its own dark `DDAY_COVER_COLORS` palette; do not reuse or mutate sticky-note palette constants.
- Delete confirmation uses compact `QDialog` (200x100) instead of `MessageBox` to fit widget size.
- In `large` mode the floating windows are hidden and mirrored in `DDaySidePanel` (`ui_dday_panel.py`) as a **3-column grid** of mini cards (no scroll; up to 5 = 2 rows). Each card has an X (`delete_requested(int)`) → main `_on_panel_dday_delete` confirms, deletes from DB, cleans the hidden floating window, refreshes the panel.

---

## Focus Mode Widgets

- Floating quiet focus timer widgets. Created via "+" dropdown menu → "집중 모드".
- `FocusTimer` owns session timing/progress logic; `FocusWidgetWindow` owns UI state and persistence.
- UI states: Ambient (goal + percent + thin progress ring + right-side `tomato_mini.png`, no remaining time), Glance on hover (same width, taller only: hide mini tomato, show mode, `MM:SS` remaining time, next break, and larger `tomato.png`). Clicking the larger tomato shows a random encouragement speech bubble below it for 3 seconds. No double-click edit/control panel; users configure once in the create dialog and recreate the widget if they want a different goal or mode.
- Modes display without shorthand ratios: 짧은 집중 (`25분 집중/5분 휴식, 포모도로`), 깊은 집중 (`50분 집중/10분 휴식`), 몰입 블록 (`75분 집중/15분 휴식`).
- Manual session end opens `FocusReviewDialog` for focus rating 1-5 and distraction category. Automatic focus completion stores a completed session, shifts the widget to a subtle completion color, then asks "집중 모드 완료, N분 휴식하시겠습니까?" with buttons. Accepting starts break mode with no sound.
- Visual style: translucent charcoal/blue-gray widget with sticky-note-matched `10px` radius and muted teal ring; avoid large countdown numbers.
- In `large` mode the floating focus window is hidden and mirrored in `FocusMiniCard`/`FocusSidePanel` (`ui_focus_panel.py`). The mini card has an X (`close_requested`) → main `_on_panel_focus_close` confirms, then reuses `FocusWidgetWindow._on_close()` (stops timer, deletes from DB, pops registry) and clears the panel.

---

## AI Law Search

- Header section includes "AI 법령정보" search bar (toggled via `SETTING_SHOW_LAW_SEARCH`).
- Dark-bg styled `LineEdit` (white text, translucent border).
- Opens `law.go.kr/LSW/ais/searchList.do` in default browser via `QDesktopServices.openUrl()`.
- URL uses `quote_plus` encoding and includes full query parameters (`searchType=1`, `mainType=main`, `pagePer=10`, etc.) to match the official Lawbot main page search behavior.
- All `LineEdit` inputs have `WA_InputMethodEnabled=True` for Korean IME compatibility.

---

## Update Guide

- Header toolbar places `FIF.UPDATE` between schedule search and settings.
- Settings window shows a two-column row near the bottom: "업데이트 방법" and "데이터 초기화".
- Both entry points call `ui_update.show_update_guide()`, which displays the current `APP_VERSION` and opens `https://www.onnara.go.kr/kndg/home/kngList` only when the user clicks the bottom button.

---

## Known Issues & Notes

- **Korean IME**: `FramelessWindowHint | Tool` flags can cause Korean IME composition issues on PCs with the new Microsoft IME (Win10 2004+/Win11). User-side fix: enable "이전 버전의 Microsoft 입력기" in Windows settings.
- **Author info**: "만든이: 기후에너지환경부 보문산불주먹".
