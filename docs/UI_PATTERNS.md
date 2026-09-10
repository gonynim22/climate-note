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
- **Calendar Drag**: Drag only the navy header background or month label. Movement below `QApplication.startDragDistance()` remains a click. Large mode disables dragging. A completed compact/medium drag resizes layouts for the destination screen, clamps the full window, then stores free coordinates, target screen, and nearest corner. Saved target screen wins over a newly calculated center when the window changes size. Navigation/search/settings controls keep their normal click behavior; Monitor or corner selection in Settings switches back to corner placement.
- **Window Opacity**: The saved 30-100 percent opacity is applied immediately to the main window and all sticky/D-Day/focus widgets.
- **Schedule Color Squares & Count**: `_refresh_calendar()` calls `db.get_all_schedule_date_colors()` and `db.get_all_schedule_date_counts()` once each. Raw schedule colors remain the three canonical slot tokens; `db.schedule_display_color()` resolves the selected display palette for compact squares, expanded chips, the schedule list, color-cycle button, and search results. `_refresh_cell_for_date()` updates a changed date in place.
- **Schedule Inline Edit**: Double-click a schedule item to edit in-place. Enter saves, Escape cancels, and focus leaving the composite editor saves. Moving between its input, emoji button and owned popup does not finish editing. Uses `db.update_schedule()` for encrypted update. `_editing_item` guard prevents concurrent edits; save failure preserves the editor and blocks date/month/search navigation, list replacement, data changes and normal quit.
- **일정 행 높이**: `QListWidget::item`의 padding은 0으로 두고 행 레이아웃의 여백에 포함하여 `sizeHint()`에 반영한다. 인라인 편집기는 `show()`한 뒤 행 높이를 다시 계산하여 입력창과 26px 이모지 버튼의 하단을 모두 표시한다. 편집 저장·취소 뒤에는 본문 행 높이로 복귀한다.
- **일정 이모지**: 입력 행은 `[색상 → 이모지 선택 → 본문 → 추가]` 순서다. `ui_schedule_emoji.py`의 공용 선택창은 16개 이모지(4×4)와 `없음`을 제공한다. 선택은 입력창 앞의 알려진 `이모지 + 공백 한 칸`만 추가·교체·제거하고, Enter/추가 또는 인라인 편집 확정 시 기존 본문으로 암호화 저장한다. 본문 중간·미지원·복합 이모지는 변경하지 않는다. 직접 입력한 알려진 선두 표식도 같은 방식으로 편집한다. 별도 중요도·색상 슬롯은 만들지 않는다.
- **이모지 표시·조작**: compact는 하단 일정 목록에, medium/large는 일정 목록과 날짜 칩에 표시하며 검색 결과와 전체 본문 툴팁에도 포함한다. compact 날짜 칸 3행과 기존 칩 크기·말줄임은 유지한다. 선택 버튼과 팝업은 키보드로 접근할 수 있고, 팝업의 방향키/Tab으로 이동·Enter/Space로 선택한다. 팝업에서 Escape는 팝업만 취소하고 입력으로 복귀하며, 편집 입력의 Escape는 수정 전체를 취소한다. 선두 치환은 Undo 한 번으로 되돌릴 수 있다.
- **이모지 팝업 수명·폰트**: 팝업은 한 개만 열고 호출 버튼의 화면 작업 영역 안에 배치한다. 닫힌 팝업은 `deleteLater()`하고 선택 콜백을 무효화한다. 잠금·트레이 숨김·초기화 때 팝업과 예약된 포커스 복원을 취소하여 뒤늦은 저장·재표시를 막는다. 선택창은 시스템 `Segoe UI Emoji`, 일정 본문은 기존 앱 글꼴과 Qt 폴백을 사용한다. 외부 폰트·이미지는 추가하지 않는다. 방향키는 실제 포커스 버튼의 이벤트를 받아 격자 안에서 좌우 한 칸·상하 한 행으로 이동한다.
- **컬러 이모지 렌더링**: Qt 6.10.2의 Windows DirectWrite 글리프 캐시에는 비트맵 우측·하단 한 픽셀을 누락하는 문제가 있어 Qt/PySide6 6.11.2를 사용한다. 버튼 높이·padding을 늘려도 이 문제는 해결되지 않는다. `test_emoji_rendering.py`에서 캐시를 거친 화면 렌더와 원본 컬러 비트맵의 경계를 비교한다. 본문 글꼴·Unicode 저장값은 유지한다.
- **Lunar Setting**: Cached as `self._show_lunar` on `MainCalendarWindow`, refreshed once per `_refresh_calendar()` (not per cell). It now gates ONLY the bottom-panel lunar-date text (`lunar_info_label`). Holiday highlighting (red day number) and the bottom-panel holiday name (`holiday_info_label`) are always shown regardless of this setting (holiday = rest day). Holiday lookup uses `holidays.is_holiday()` / `holidays.get_holiday()`.

---

## Settings UI

- Organized as a no-scroll (800x560) layout of five **section panels** in two columns: 화면 표시, 위젯·도구 (left); 데이터, 보안, 시스템 (right). No large in-window "설정" title. Each panel is a `CardWidget` with a `StrongBodyLabel` header (objectName `panelHeader`) on a light `#F6F6F6` strip (`panelHeaderBar`) built by `_make_panel`; header color/weight are fixed via `setTextColor(#1A1A1E)` + `setFont(Bold)` (not QSS) so theme re-application can't wash them out. The panel body does not darken on hover. Each setting is a `_add_row(body, label, control)` row with label-left / control-right on a unified right rail; the 화면 위치 row (`_position_row`) is min-height 60. Footer credit (`author_label`) is single-line (`wordWrap(False)`). Monitor combo width 210.
- **Calendar size** uses `CalendarSizePicker` (not a combo): three same-size monitor illustrations whose blue app block area grows for `compact`/`medium`/`large` (anchored bottom-right, the app's default corner). Pure `QFrame` + QSS, no external image assets; selection highlight via a `selected` style property. Emits `scaleChanged(str)` → `_on_scale_changed(scale)` → saves `SETTING_CALENDAR_SCALE`.
- **Schedule colors** use `ScheduleColorPicker`: three compact swatches map to the three canonical storage slots. Each opens a 10-color `RoundMenu`; colors already used by another slot are disabled. Saving changes only `app_settings`, then immediately repaints the app.
- PIN validated via `_validate_pin(pin)` helper — used by 데이터 Export/Import only.
- **데이터 초기화(Factory Reset)** uses no PIN (usability decision): soft-danger red button (`factoryResetButton`) → confirm `MessageBox` only. 앱 종료 (`quitAppButton`, dark) first checks `prepare_for_quit()` through its callback. Only a successful save allows closing Settings and calling `QApplication.quit()`.

---

## Sticky Notes

- **데이터 작업 전 저장**: 가져오기·초기화는 현재 플로팅/large 패널 원본을 저장한 뒤 보호백업을 만든다. 저장 실패 시 해당 작업을 보류한다. 가져오기 뒤 기존 ID의 편집창은 재사용하고, large 패널 목록은 최신 편집을 보존하며 갱신한다.
- **초기화 객체 정리**: 보호백업 성공 후 기존 플로팅 창과 숨긴 미니 패널의 타이머를 모두 정지·폐기한 다음 DB를 초기화한다. 초기화 전 메모의 지연 저장이 같은 ID의 새 메모에 적용되면 안 된다.

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
- Visual style: white-to-blue gradient (`#FFFFFF` → `#EEF6FF` → `#DDE8FF`) with `#FF5A45` focus accent and transparent tomato assets.
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

- The header's more menu opens the update guide alongside Settings and Trash.
- Settings retains update guidance and the separately styled Factory Reset action.
- Both entry points call `ui_update.show_update_guide()`, which displays the current `APP_VERSION` and opens `https://www.onnara.go.kr/kndg/home/kngList` only when the user clicks the bottom button.

---

## Known Issues & Notes

- **Privacy Lock 표시 계약**: 잠금 중에는 트레이 복원이나 예약된 창 표시로 플로팅 스티키/D-Day/집중 창을 노출하지 않는다. 열려 있던 설정·검색·휴지통은 비활성화하고 숨기며, 잠금 중 재진입은 차단한다. 활성 확인/파일 대화상자와 팝업은 취소한다. 잠금 해제 후 위젯은 현재 패널/트레이 상태에 맞춰 복원하고, 보조 창은 사용자가 다시 연다. 집중 자동 완료가 잠금 중 발생하면 완료 기록은 저장하되 휴식 팝업은 생략한다.

- **Korean IME**: `FramelessWindowHint | Tool` flags can cause Korean IME composition issues on PCs with the new Microsoft IME (Win10 2004+/Win11). User-side fix: enable "이전 버전의 Microsoft 입력기" in Windows settings.
- **Author info**: "만든이: 기후에너지환경부 보문산불주먹".

## UI 상세 계약

- **앱 글꼴**: 기본 본문 폰트는 Windows 시스템 폰트 `Malgun Gothic`이다. 설정 키는 `SETTING_APP_FONT = "app_font"`이며, 적용은 앱 시작 시 `app_fonts.apply_app_font()` 경유. 설정창에서 변경하면 저장만 하고 재시작 안내를 표시한다.
- **폰트 크기**: QSS의 `font-size`는 정수 `px`만 사용한다. 소수점 픽셀 크기는 Windows Qt 렌더링에서 흐림을 만들 수 있다.
- **설정 위험 버튼**: `Factory Reset`은 `factoryResetButton` + `FIF.DELETE`(소프트 danger: 배경 `#FEF2F2`/테두리 `#F0C2C2`/글자 `#DC2626`, hover 시 `#DC2626` 채움), `앱 종료`는 `quitAppButton` + `FIF.POWER_BUTTON`(다크 `#1F2937`) 사용. 아이콘과 텍스트가 겹치지 않도록 왼쪽 padding과 최소 폭을 유지한다. **테스트 고정값**: factoryReset QSS는 `border-radius: 6px` + `padding: 5px 14px 5px 34px` + minWidth≥152, quit QSS는 `border-radius: 6px` + `padding: 5px 12px 5px 32px` + minWidth≥112를 유지한다(QSS에 `#28a745`/`#dc3545` 금지).
- **설정창 레이아웃(시안 A)**: `ScrollArea` 없이 800x560 고정/최소 크기를 유지하며, 레이아웃 최소 크기가 800×560을 넘지 않아야 한다(긴 저작권 라벨은 `setWordWrap(True)`+`QSizePolicy.Maximum`으로 창 폭을 강제하지 않게 한다). 5개 섹션(화면 표시/위젯·도구/데이터/보안/시스템)을 각각 **테두리 카드**(`_SettingsPanel`: 흰 배경 + 라운드 11px `#D7DAE2` 테두리, hover 배경/테두리 변화 없음, `_make_panel`)로 감싸 2열 배치한다. 헤더는 **밝은 바**(`panelHeaderBar` `#F6F6F6` + 라운드 상단/좌우/하단 경계 `#D7DAE2`) 안에 **블루 섹션 아이콘 + 진한 굵은 `StrongBodyLabel`**(`panelHeader`, `#1A1A1E`)로 두며, **딥 네이비(`#01295F`) 풀 바로 되돌리지 않는다**. 섹션 헤더 텍스트는 반드시 `StrongBodyLabel`(섹션명)이어야 한다(테스트 의존). 모든 컨트롤은 스크롤 없이 보여야 한다. 각 행은 `_add_row`로 `라벨-좌(고정폭) / 컨트롤-우`(우측 정렬 레일) + 행간 1px 구분선(`#F2F3F6`, 섹션 마지막 행은 `divider=False`). 모니터와 화면 위치는 **별도 두 행**으로 분리한다(콤보 / 4모서리 2×2 `posGrid`). 화면 위치는 4모서리(top/bottom × left/right)만 지원하며 `_position_btns`는 항상 4개. 카드 보조 설명은 넣지 않고 라벨은 짧게 쓴다. **캘린더 크기**는 콤보가 아니라 `CalendarSizePicker`(동일 크기 모니터 외곽 + 내부 앱 블록 크기로 `compact`/`medium`/`large` 표현, 선택 시 외곽·테두리·블록·캡션 블루 강조, `QFrame`+QSS, 외부 이미지 없음; `scaleChanged(str)` → `_on_scale_changed(scale)` → `SETTING_CALENDAR_SCALE` 저장)다.
- **전역 블루 액센트**: `main.py`에서 `setThemeColor(QColor("#2563EB"))`로 토글(`SwitchButton`)·슬라이더·포인트색을 단일 블루로 통일한다. 시스템 테마 자동 전환(`_check_theme`) 후에도 재적용한다. 집중모드 `#FF5A45`, 공휴일 `#D32F2F`, 오늘 남색 등 **명시 색상은 테마색과 무관**하므로 영향받지 않는다.
- **바로가기 인라인 관리**: 6개 슬롯의 DB 행과 스키마는 유지한다. 빈 슬롯 좌클릭은 파일/폴더 선택, 등록 슬롯 좌클릭은 실행, 우클릭은 이름 변경·경로 재지정·삭제를 제공한다. 끊긴 경로 좌클릭은 재지정 메뉴를 열고, 재지정은 사용자 표시 이름을 보존한다. 파일/폴더 드래그 등록과 기존 X 삭제도 계속 지원한다.
- **캘린더 셀 구조(2-모드)**: `CalendarDayButton`은 `mode`(`compact`/`expanded`)를 가진다. compact는 `[날짜 숫자 / 색상 심볼(■) / 총 일정 수]` 3행이며 개수 0이면 빈칸이다. expanded는 날짜 숫자와 일정 칩 스택을 표시하며, 셀 높이에 맞춰 칩 개수를 계산하고 넘치면 `+N 더`를 표시한다. medium 칩은 10px/16px/2px(글꼴/높이/간격), large 칩은 13px/22px/3px를 사용하고 실제 적용 폰트 메트릭으로 말줄임한다. 일정 추가·삭제·수정 시 `_refresh_cell_for_date()`로 해당 셀만 즉석 갱신한다.
- **일정 행 관리**: 일정 행 오른쪽의 기존 휴지통 버튼은 즉시 삭제를 유지하고, 일정 행 더블클릭은 기존 인라인 편집을 유지한다. 일정 행 우클릭은 `RoundMenu`로 `편집`·`삭제`를 표시하며 각각 동일한 기존 처리 경로를 호출한다. 빈 목록 영역이나 Privacy Lock 상태에서는 메뉴를 열지 않고, 비동기 메뉴는 `closedSignal` 뒤 `deleteLater()`로 정리한다.
- **캘린더 자유 이동**: 헤더 배경과 연월 라벨만 드래그 영역이며 내비게이션·검색·설정 버튼 입력을 가로채지 않는다. `QApplication.startDragDistance()` 이상 움직여야 드래그로 인정하므로 단순 클릭은 위치 모드를 바꾸지 않는다. 드래그 중에는 포인터가 있는 대상 화면의 물리 DPI로 5mm 픽셀 간격을 계산해 전역 x/y 격자에 즉시 스냅한다. 첫 드래그 완료 시 목적지 화면 기준으로 medium/large 크기를 다시 계산하고, 음수 좌표를 포함해 작업 영역 안의 가장 가까운 유효 5mm 격자로 확정한 다음 `calendar_x/y`, 대상 화면, 최근접 모서리를 저장하고 `calendar_position_mode="free"`로 전환한다. v17 기본은 `"corner"`라 기존 사용자의 과거 좌표는 자동 적용하지 않는다. 자유 위치에서 크기를 바꿀 때는 새 창 중심이 아니라 저장된 대상 화면을 우선한다. 화면 추가/제거/해상도·스케일·사이드바 변경 시 **목적지 화면 기준으로 크기를 다시 계산한 뒤** 좌표를 작업 영역 안으로 보정하고, 설정에서 모니터/화면 위치를 선택하면 `"corner"`로 복귀한다.
- **전체 투명도**: `SETTING_APP_OPACITY="app_opacity"`(기본 `"100"`, 범위 30~100). `MainCalendarWindow._apply_app_opacity()`가 메인과 스티키/D-Day/집중 위젯에 `setWindowOpacity`를 일괄 적용하며 새 위젯에도 현재값을 적용한다.
- **바탕화면 고정(Win+D)**: 기존 설정 키 `SETTING_KEEP_ON_SHOW_DESKTOP="keep_on_show_desktop"`(기본 `"1"`)는 데이터 호환을 위해 유지한다. Win+D는 바탕화면 셸 창을 z-order 앞으로 올리므로 최소화 복원만으로는 막을 수 없다. `ShowDesktopKeeper`는 셸 바탕화면이 foreground가 될 때만 메인+플로팅 창을 `HWND_TOPMOST`로 350ms pulse한다. pulse 종료 후에는 먼저 `HWND_NOTOPMOST`로 내리고, `GetWindow(desktop, GW_HWNDPREV)`로 감시 창을 제외한 데스크톱 앞의 첫 창을 찾아 그 창 뒤·데스크톱 앞에 삽입한다. 결과 순서는 **바탕화면 아이콘 < 기후노트 < 탐색기·브라우저 등 일반 창**이어야 한다. 다른 창이 foreground가 되면 pulse를 취소하고 같은 데스크톱 레이어로 즉시 재고정한다. Win+M은 `WindowStateChange` 복원으로 별도 방어한다. **영구 topmost 및 WorkerW/SetParent 재부모화 금지**. 토글 OFF는 타이머 취소+즉시 demote, 앱 종료/객체 파괴 시 native hook을 반드시 해제한다.
- **모니터 구성 변경 시 크기 재계산**: `medium`/`large`는 화면 크기에 비례하는 스케일이므로, 모니터가 바뀔 때 좌표만 clamp하면 안 된다. `_clamp_calendar_xy()`는 `max(0, 화면폭 - 창폭)`을 쓰기 때문에 창이 화면보다 넓으면 좌측 정렬만 하고 초과분을 처리하지 못한다. `_on_screen_changed()`와 `_finish_calendar_drag()`는 **둘 다** `_calendar_scale_geometry(scale, 목적지화면)`으로 크기를 먼저 다시 구한 뒤 좌표를 정한다. KVM 본체 전환으로 가로↔세로 모니터가 끊겼다 붙는 환경에서 실제로 재현된 결함이다(가로 기준 1880×1040 창이 세로 1080×1920 모니터에 그대로 남아 우측과 설정 버튼이 화면 밖으로 나감). `tests/test_ui_screen_change.py`가 양방향을 검사한다.
- **확장 캘린더**: `SETTING_CALENDAR_SCALE="calendar_scale"`(`compact`/`medium`/`large`, 기본 `compact`). 확장 시 좌측 바로가기 6슬롯, 가운데 큰 달력, 우측 일정 패널의 3열로 재배치하며 compact 복귀 시 일정 패널을 달력 하단으로 되돌린다. `large` 스케일에서는 우측 컬럼을 `[일정 → D-Day(미니) → 집중(미니, 라이브 미러) → 스티키(미니)]` 4구획으로 구성한다. 세 패널은 large에서 항상 존재하고 빈 상태를 컴팩트하게 표시한다. 진입 시 플로팅 스티키/D-Day/집중을 숨기며, 집중은 살아 있는 플로팅 창의 타이머를 미니 카드가 매초 미러링한다. 이탈 시 패널 저장 후 DB 최신값을 플로팅 창에 재로드/복원한다.
- **사이드바/캘린더 경계**: 앱 최초 표시 전에는 `self.sidebar.isVisible()`로 사이드바 활성 여부를 판단하지 않는다. 부모 창이 아직 숨겨져 있으면 Qt가 자식 위젯을 false로 보고 `sidebarActive`가 어긋날 수 있으므로, 저장된 사이드바 설정값을 기준으로 `sidebarActive`와 `expanded` dynamic prop을 적용한다.
- **구분선 색·두께**: 구조 구분선(사이드바 우측선, 캘린더 섹션·일정 패널·미니 패널 테두리, 캘린더 내부 가로선)은 모두 **중립 쿨 그레이 `rgba(206, 210, 216, ...)`(`#CED2D8`)** 단일 색을 쓴다. 파란기 도는 페리윙클(`rgba(180,190,220,...)`)로 되돌리지 않는다. 불투명도만 위치별로 다르다(사이드바 150 / 패널·섹션 테두리 180 / 캘린더 내부 가로선 120). **테두리 이중화(2px) 금지**: 테두리 있는 두 면이 맞붙는 쪽은 한쪽 테두리를 제거해 이음새를 1px로 유지한다 — expanded `calendarSection`은 `border-left/right:none`, `large` 우측 컬럼에서 세로로 쌓이는 `[일정 → D-Day → 집중 → 스티키]` 중 **아래 3개 패널(`ddaySidePanel`/`focusSidePanel`/`stickySidePanel`)은 `border-top:none`**(위 패널의 아래 테두리 하나만 남김). 단, 콘텐츠 강조 테두리(스티키/D-Day 미니 카드의 노트 고유색, 집중 카드 `rgba(255,90,69,90)`)는 구분선이 아니므로 이 규칙에서 제외한다.
- **팝업 메뉴 DWM 테두리**: Win11에서 `RoundMenu` 계열 팝업 주위에 생기는 넓은 사각 테두리는 **OS(DWM)가 그리는 창 테두리**다(그림자 여백 때문에 창이 메뉴보다 커서 도드라짐). `popup_border_fix.install_popup_border_fix(app)`가 main에서 설치되어 자동 우회한다. **Qt 쪽 수정(그림자 제거/여백 축소/메뉴 QSS)으로는 지워지지 않으니 재시도하지 말 것**(실측 확인됨).
- **설정창 위치**: 달력이 화면 끝 코너에 있으면 설정창이 화면 밖으로 열려 우측 컬럼이 잘릴 수 있다. `_on_settings`가 표시 후 `QTimer.singleShot(0, ...)`으로 `_clamp_window_to_screen()`을 호출해 작업 영역 안으로 이동시킨다.
- **설정창 높이 = 560 필수**: 창 높이가 레이아웃 최소치(시스템 3행 기준 546px)보다 작으면 우측 컬럼 행들이 세로 압축되어 고정높이(34px) 버튼이 행 구분선을 침범해 '겹쳐 보인다'. 무스크롤 고정 창에 행을 추가할 땐 `layout().minimumSize()` ≤ 창 높이를 실측 확인할 것(v3.1a에서 520→560 정정).
- **공휴일 표시**: 공휴일 날짜 숫자는 빨강(`#D32F2F`), 음력 표시 설정과 무관하게 항상. 오늘 셀은 남색 배경+흰 숫자로 우선. 공휴일명은 선택 시 하단 `holiday_info_label`(빨강)에 항상 표시. `_show_lunar` 설정은 이제 하단 음력 텍스트만 제어한다.
- **오늘 재동기화(자정 롤오버)**: 오늘 날짜(`_today`)는 `__init__`에서 1회 계산되므로, **트레이 상주 앱**(`setQuitOnLastWindowClosed(False)`)이 자정을 넘기면 캘린더가 어제에 박제된다(과거: '오늘' 버튼을 눌러야만 갱신). `toggle_visibility` show 시 `_sync_to_today_if_changed()`가 날짜 변경을 감지하면 `_on_today()`로 오늘 이동(같은 날이면 보던 달 유지). 표시 중 자정 넘김은 30초 주기 타이머에 연결된 `_check_day_rollover()`가 오늘 하이라이트만 갱신(보던 달·선택 유지). **숨김 상태에서는 롤오버를 소비하지 않아** `_today`가 어제로 남고 다음 show에서 이동이 트리거된다. `_on_today()`는 `_today`도 함께 갱신한다.
- **삭제 정책**: 스티키 노트 닫기는 `db.trash_sticky_note()`로 **휴지통 이동(soft-delete)**한다(즉시 삭제 아님). 닫기 확인 팝업은 스티키 창을 parent로 둔 `MessageBox`가 아니라 parent 없는 top-level `Dialog`로 띄워 작은 스티키 내부에서 잘리지 않게 한다. 휴지통(우측 메뉴 → 휴지통, `ui_trash.py`)에서 `restore_sticky_note()`로 원위치 복구, `purge_sticky_note()`로 개별 영구삭제, `empty_sticky_trash()`로 전체 비우기. 휴지통은 `STICKY_TRASH_LIMIT(=50)`개로 제한되어 초과 시 오래된 것부터 자동 영구삭제(`_enforce_trash_cap`, 로그 기록). 영구삭제/비우기는 확인 팝업만(PIN 불필요). 백업(Export/Import)에 휴지통 항목 포함. D-Day/집중 모드/일정 휴지통은 미구현(단, `large` 모드 미니 패널에서 D-Day는 카드 X로 즉시 영구 삭제, 집중은 카드 X로 세션 종료 — 둘 다 확인 팝업 경유).
- **스티키 미니 패널**: large 우측 `StickySidePanel`의 공용 툴바(굵게·할 일·텍스트 색상·배경 색상)는 포커스된 카드에만 작용한다(툴바 버튼 `NoFocus`). 카드별 X는 `trash_sticky_note()`로 휴지통 soft-delete 후 `note_trashed`를 전파해 메인의 숨겨진 플로팅 창 레지스트리를 정리한다.
- **자동정렬**: `ui_main.py`의 `_on_arrange_sticky_notes()`는 스티키/D-Day/집중 모드 위젯을 함께 정렬한다. 자유 이동 뒤에는 저장된 모서리 설정이 아니라 캘린더 중심이 속한 실제 화면과 최근접 모서리를 기준으로 빈 공간을 계산한다. 우측 모서리 배치에서는 스냅 반올림 때문에 캘린더의 우측 여백이 줄어들지 않도록 `_snap_not_past_right()` / `_right_aligned_grid_x()`를 사용한다.
- **집중 모드 UI**: 기본 Ambient는 남은 시간을 숨기고 목표·진행률%·얇은 원형 링·흰 배경이 제거된 투명 `tomato_mini.png`만 표시한다. 기본 배경은 `#FFFFFF` → `#EEF6FF` → `#DDE8FF` 대각선 그라데이션이며 포인트 색은 `#FF5A45`이다. Hover Glance는 같은 폭에서 세로만 늘리고, mini 토마토는 숨기며, 왼쪽에는 모드·남은 시간(`MM:SS`)·다음 휴식(`HH:MM AM/PM`)을, 오른쪽 아래에는 흰 배경이 제거된 투명 `tomato.png`를 `TOMATO_IMAGE_SIZE = 50`으로 표시한다. Hover Glance의 큰 토마토를 클릭하면 22개 응원 문구 중 하나를 랜덤으로 고른 말풍선을 토마토 아래에 3초간 표시하되, 말풍선 창 외곽은 투명해야 한다. 큰 토마토에는 Qt 기본 툴팁을 달지 않는다. 위젯 창 크기는 `AMBIENT_SIZE`/`GLANCE_SIZE`로 고정한다. Hover Glance에 `진행률` 행은 두지 않는다. 더블클릭 편집 패널은 제공하지 않으며, 설정을 바꾸려면 종료 후 새로 만든다.
- **집중 모드 위젯 제한**: 집중 모드 위젯은 1개만 생성/표시한다. `enforce_widget_limits()`가 앱 시작 시 최신(id 큰) 1개만 남기고 초과분은 데이터 보존 상태로 `is_open=0` 정리한다. 정리분이 있으면 모달 경고를 띄운다. 생성 제한 카운트는 `isVisible()`이 아니라 등록 딕셔너리 기준이다.
- **D-Day 위젯 제한**: D-Day 위젯은 최대 5개만 생성/표시한다. `enforce_widget_limits()`가 앱 시작 시 최신(id 큰) 5개만 남기고 초과분은 삭제 없이 `is_open=0` 정리한다. 생성 제한 카운트는 `isVisible()`이 아니라 등록 딕셔너리 기준이다.
- **D-Day Cover Tint(디자인)**: D-Day 플로팅 위젯(`ui_dday.py`)과 large 미니 카드(`ui_dday_panel.py`)는 **진한 커버색 단색 배경 + 전부 흰 타이포**다. 팔레트 `DDAY_COVER_COLORS`(sky `#46679C` 기본 / yellow `#A8801F` / mint `#2E8F6E` / pink `#B25C8B`)는 **스티키 전용 `STICKY_COLORS`/`STICKY_HEADER_COLORS`와 분리**한다(공유 상수 오염 금지). DB에 저장된 구 파스텔 색은 `dday_cover_color()`가 커버색으로 매핑해 렌더한다(저장값 변경 없이 표시만 매핑, 데이터 보존). 카운트는 색이 아니라 **표기+명도**로 상태 구분: 미래 `D-N`·당일 `D-Day`는 흰색(`#FFFFFF`), 지남 `D+N`은 `rgba(255,255,255,140)`(공백 없는 표기). 플로팅 위젯은 **소프트 드롭 섀도우 + 옅은 흰 헤어라인(`rgba(255,255,255,HAIRLINE_ALPHA)`)으로 배경에서 분리**(창을 `SHADOW_MARGIN`만큼 키워 그림자 여백 확보, 좌표 규약은 창 좌표 그대로 유지, 불변식 `SHADOW_MARGIN ≥ SHADOW_BLUR + SHADOW_OFFSET_Y`). 미니 카드(`ui_dday_panel.py`)는 흰 패널 위라 대비 문제가 없어 종전대로 **테두리 없음** 유지. radius 18(플로팅)/12(미니), 좌하단 큰 카운트·우하단 날짜 구도. 카운트/이름/날짜 폰트는 **Pretendard**를 `_dday_font()`로 `QFont` 픽셀 크기·굵기 직접 지정(QSS font-size/weight 미사용, 미로드 시 Malgun 폴백). 닫기 X는 커버 위 가독을 위해 흰색을 직접 그리는 `_CoverIconButton`. large 우측 컬럼의 `ddaySidePanel` **패널 컨테이너**는 스택 이음새 규칙(흰 배경·`border-top:none`·무radius)을 그대로 유지하고 **미니 카드에만** 커버 틴트를 적용한다.
- **집중 모드 세션**: 집중 완료 시 소리 없이 위젯 색만 미세하게 바꾸고 `집중 모드 완료, N분 휴식하시겠습니까?` 버튼 알림을 띄운다. `휴식 시작` 수락 시 break phase로 진입하고, `건너뛰기`면 완료 상태로 남긴다.
- **집중 모드 모드명**: 사용자 표시에는 `25/5` 같은 축약 숫자를 쓰지 않는다. `짧은 집중 (25분 집중/5분 휴식, 포모도로)`, `깊은 집중 (50분 집중/10분 휴식)`, `몰입 블록 (75분 집중/15분 휴식)` 형식을 유지한다.
