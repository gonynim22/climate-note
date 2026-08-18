# 캘린더 총 개수 표시 + 공휴일 강조 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 캘린더 각 날짜 셀에 총 일정 수를 표시하고, 공휴일 날짜를 빨강으로 강조하며(공휴일명은 하단으로 이동), 공휴일/음력 데이터를 실제 API로 최신화한다.

**Architecture:** `CalendarDayButton` 셀 레이아웃을 `[날짜 / 심볼 / 총개수]` 로 바꾸고(공휴일명 행 제거), `database.py` 에 날짜별 개수 집계 함수를 추가한다. 공휴일 여부는 음력 설정과 무관하게 항상 계산해 셀 숫자색·하단 라벨에 반영한다. 데이터는 `fetch_data.py` 를 순수 API 기반으로 정리 후 재생성한다.

**Tech Stack:** Python 3.13, PySide6 (Qt), SQLite, pytest + pytest-qt.

---

## 사전 메모

- **이 프로젝트는 git 저장소가 아니다.** 각 Task의 마지막 "Checkpoint" 는 커밋 대신 **전체 테스트 통과 확인**(`python -m pytest tests -q`)이다. git을 도입하면 각 Checkpoint에서 커밋한다.
- 플랫폼은 Windows(win32) / PowerShell. 셸 명령은 PowerShell 기준.
- 테스트 실행: `python -m pytest tests -q` (전체) 또는 `python -m pytest tests/test_x.py::test_y -v` (단건).
- 진행 순서는 스펙대로 **Phase 1(데이터) → Phase 2(공휴일 빨강) → Phase 3(총 개수)**.

## 파일 구조 (생성/수정 대상)

| 파일 | 책임 | 변경 |
|---|---|---|
| `fetch_data.py` | 공공데이터포털 API → `holidays.py` 생성 + 데이터 검증 헬퍼 | 수정(정리 + `verify_holiday_data` 추가) |
| `holidays.py` | 오프라인 공휴일/음력 데이터(생성물) | 재생성(API) |
| `database.py` | 날짜별 일정 개수 집계 함수 추가 | 수정(`get_all_schedule_date_counts`) |
| `ui_main.py` | 셀 위젯 레이아웃/색상, 하단 공휴일명, 실시간 개수 갱신 | 수정 |
| `tests/test_fetch_data.py` | 데이터 검증 헬퍼 테스트 | 생성 |
| `tests/test_database.py` | 개수 집계 테스트 | 수정(추가) |
| `tests/test_ui.py` | 공휴일 빨강/하단 라벨/셀 개수 테스트 | 수정(추가) |

---

# Phase 1 — 데이터 갱신 (실제 API만)

### Task 1: `fetch_data.py` 순수 API 기반으로 정리

**Files:**
- Modify: `fetch_data.py` (docstring 1-5행, `calculate_holidays()` 45-129행 제거)

- [ ] **Step 1: 미사용 계산 함수와 오해 소지 docstring 제거**

`fetch_data.py` 최상단 docstring을 아래로 교체:

```python
"""
fetch_data.py - 공공데이터포털 API에서 음력/공휴일 데이터 수집 (실제 API 데이터만 저장)
* API가 제공하는 범위(통상 1~2년 뒤까지)만 holidays.py로 생성한다.
* 미래 연도를 임의 계산해 채우지 않는다.
"""
```

그리고 `def calculate_holidays(year, lunar_mapping) -> dict:` 함수 **전체**(`# ── 대체 공휴일 포함 계산 ──` 주석 줄부터 `return holidays` 까지, 약 45-129행)를 **삭제**한다. `main()` 은 이미 이 함수를 호출하지 않으므로 다른 변경은 없다.

- [ ] **Step 2: import 부수 확인**

`calculate_holidays` 삭제 후 `timedelta` 가 `main()` 에서 더는 쓰이지 않을 수 있다. `fetch_data.py` 에서 `timedelta` 사용처를 확인하고, 미사용이면 `from datetime import date, timedelta, datetime` 에서 `timedelta` 를 제거한다. (사용 중이면 그대로 둔다.)

Run: `python -c "import fetch_data"`
Expected: import 오류 없음(구문/이름 오류 없음).

- [ ] **Step 3: Checkpoint**

Run: `python -m pytest tests -q`
Expected: 기존 테스트 전부 PASS(회귀 없음).

---

### Task 2: 데이터 검증 헬퍼 `verify_holiday_data` 추가 (TDD)

**Files:**
- Modify: `fetch_data.py` (함수 추가)
- Test: `tests/test_fetch_data.py` (생성)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_fetch_data.py` 생성:

```python
# tests/test_fetch_data.py - 공휴일/음력 데이터 검증 헬퍼 테스트
import fetch_data
import holidays


def test_verify_passes_on_current_data():
    """현재 번들 데이터(공휴일 ~2027, 음력 ~2050)는 검증 통과."""
    ok, msg = fetch_data.verify_holiday_data(holidays)
    assert ok, msg


def test_verify_fails_on_deficient_data():
    """범위/건수가 부족한 데이터는 검증 실패."""
    class Stub:
        KOREAN_HOLIDAYS = {"2025-01-01": "x"}
        LUNAR_MAPPING = {"2025-01-01": "12.1"}
    ok, msg = fetch_data.verify_holiday_data(Stub)
    assert not ok
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_fetch_data.py -v`
Expected: FAIL — `AttributeError: module 'fetch_data' has no attribute 'verify_holiday_data'`.

- [ ] **Step 3: 검증 함수 구현**

`fetch_data.py` 의 `main()` 정의 **위**에 추가:

```python
def verify_holiday_data(hol) -> tuple[bool, str]:
    """재생성된 holidays 모듈이 최소 커버리지를 만족하는지 검증한다.

    hol: KOREAN_HOLIDAYS, LUNAR_MAPPING 속성을 가진 모듈 또는 객체.
    반환: (통과 여부, 사람이 읽는 메시지)
    """
    kh = getattr(hol, "KOREAN_HOLIDAYS", {})
    lm = getattr(hol, "LUNAR_MAPPING", {})
    kh_years = {k[:4] for k in kh}
    lm_years = {k[:4] for k in lm}
    if not kh_years or max(kh_years) < "2027":
        return False, f"공휴일 범위 부족 (최대 {max(kh_years) if kh_years else '없음'})"
    if not lm_years or max(lm_years) < "2050":
        return False, f"음력 범위 부족 (최대 {max(lm_years) if lm_years else '없음'})"
    if len(kh) < 40:
        return False, f"공휴일 건수 비정상 ({len(kh)}건)"
    return True, f"OK (공휴일 {len(kh)}건, 음력 {len(lm)}건)"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_fetch_data.py -v`
Expected: 2개 PASS.

- [ ] **Step 5: Checkpoint**

Run: `python -m pytest tests -q`
Expected: 전체 PASS.

---

### Task 3: 실제 API로 `holidays.py` 재생성 (가드 포함, 수동 실행)

**Files:**
- Modify: `holidays.py` (재생성 산출물)
- 임시: `holidays.py.bak` (백업, 커밋/배포 대상 아님)

> **주의:** 이 Task는 네트워크 + 유효 `LUNAR_API_KEY`(`.env`)가 필요하다. 불가하면 **재생성을 건너뛰고** 기존 데이터(공휴일 ~2027)로 진행한다(스펙 합의). 이때 `verify_holiday_data(holidays)` 는 현재 데이터로 이미 통과하므로 앱은 정상 동작한다.

- [ ] **Step 1: 백업**

Run (PowerShell): `Copy-Item holidays.py holidays.py.bak -Force`
Expected: `holidays.py.bak` 생성.

- [ ] **Step 2: 재수집 실행**

Run: `python fetch_data.py`
Expected: `✅ 완료! 공휴일: N건, 음력: M건` 출력. (키 없음/네트워크 실패 시 `ERROR: API KEY IS MISSING` 또는 건수 0 → Step 4로.)

- [ ] **Step 3: 재생성 데이터 검증**

Run: `python -c "import importlib, holidays, fetch_data; importlib.reload(holidays); print(fetch_data.verify_holiday_data(holidays))"`
Expected: `(True, 'OK (공휴일 ...건, 음력 ...건)')`.

- [ ] **Step 4: 검증 실패 시 복구**

검증이 `False` 이거나 Step 2가 실패했으면 백업 복구:

Run (PowerShell): `Copy-Item holidays.py.bak holidays.py -Force`
그리고 사용자에게 "API 재수집 실패 → 기존 데이터 유지(공휴일 ~2027)" 로 보고한다.

- [ ] **Step 5: 정리 & Checkpoint**

성공·실패 무관하게 백업 제거(선택): `Remove-Item holidays.py.bak -ErrorAction SilentlyContinue`
Run: `python -m pytest tests -q`
Expected: 전체 PASS (특히 `tests/test_fetch_data.py::test_verify_passes_on_current_data`).

---

# Phase 2 — 공휴일 빨강 강조 (B)

### Task 4: `CalendarDayButton` 공휴일 빨강 + 공휴일명 행 제거 (TDD)

**Files:**
- Modify: `ui_main.py` (`CalendarDayButton.__init__` 130-176행, `_set_style` 187-212행, `_refresh_calendar` 1146-1152행)
- Test: `tests/test_ui.py` (추가)

> 이 Task는 셀의 `count_label` 도 함께 도입한다(Phase 3 위젯 골격). 개수 값 채우기/실시간 갱신은 Phase 3에서 연결한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ui.py` 끝에 추가:

```python
def test_calendar_holiday_dates_use_red(qtbot, app_dir, qapp):
    """공휴일은 요일과 무관하게 날짜 숫자가 빨강(#D32F2F)."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._current_year = 2026
    win._current_month = 5
    win._refresh_calendar()
    # 2026-05-05 어린이날(화요일) → 평일이지만 공휴일이라 빨강
    assert "#D32F2F" in win._day_cells["2026-05-05"].day_label.styleSheet()
    # 공휴일 아닌 평일(2026-05-04 월)은 검정 유지
    assert "#1a1a1a" in win._day_cells["2026-05-04"].day_label.styleSheet()


def test_calendar_cell_has_no_holiday_label(qtbot, app_dir, qapp):
    """공휴일명 행은 셀에서 제거되었다(하단으로 이동)."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._current_year = 2026
    win._current_month = 6
    win._refresh_calendar()
    cell = win._day_cells["2026-06-06"]
    assert not hasattr(cell, "holiday_lbl")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_ui.py::test_calendar_holiday_dates_use_red tests/test_ui.py::test_calendar_cell_has_no_holiday_label -v`
Expected: FAIL (현재는 어린이날이 검정이고 `holiday_lbl` 이 존재).

- [ ] **Step 3: `CalendarDayButton.__init__` 교체**

`ui_main.py` 의 `CalendarDayButton.__init__`(130-176행)을 아래로 교체:

```python
    def __init__(self, day: int, is_today: bool, event_colors: list,
                 is_current_month: bool, target_date: str, is_holiday: bool = False,
                 weekday_col: int = -1, count: int = 0, parent=None):
        super().__init__(parent)
        self.target_date = target_date
        self._callback = None
        self._is_today = is_today
        self._day = day
        self._event_colors = list(event_colors)
        self._is_current_month = is_current_month
        self._is_holiday = is_holiday
        self._weekday_col = weekday_col
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 3, 2, 3)
        layout.setSpacing(0)

        # 날짜 라벨
        self.day_label = QLabel(str(day) if day > 0 else "")
        self.day_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(11)
        if is_today:
            font.setBold(True)
        self.day_label.setFont(font)
        layout.addWidget(self.day_label)

        # 색상 사각형 (RichText로 다중 색상 표시)
        self.squares_label = QLabel("")
        self.squares_label.setAlignment(Qt.AlignCenter)
        self.squares_label.setFixedHeight(14)
        self.squares_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.squares_label)

        # 총 일정 개수 (회색 숫자, 0이면 빈칸)
        self.count_label = QLabel("")
        self.count_label.setAlignment(Qt.AlignCenter)
        self.count_label.setFixedHeight(12)
        layout.addWidget(self.count_label)

        self._update_squares(event_colors)
        self.set_count(count)
        self._set_style(False)
        self.setCursor(Qt.PointingHandCursor)

    def set_count(self, n: int):
        """그날 총 일정 수 표시 (0이면 빈칸)"""
        self.count_label.setText(str(n) if n > 0 else "")
```

(기존 `holiday_lbl` 관련 줄은 모두 사라진다. `_holiday_name` 속성도 제거된다.)

- [ ] **Step 4: `_set_style` 교체**

`ui_main.py` 의 `_set_style`(187-212행)을 아래로 교체:

```python
    def _set_style(self, selected: bool):
        """오늘, 선택, 공휴일 여부에 따른 통합 스타일 적용"""
        base_color = "#1a1a1a"
        count_color = "#9aa0a6"
        bg_style = "border-radius: 6px;"

        if self._weekday_col == 0:
            base_color = "#D32F2F"
        elif self._weekday_col == 6:
            base_color = "#1565C0"

        if self._is_holiday:
            base_color = "#D32F2F"  # 공휴일 = 빨강 (요일 무관)

        if not self._is_current_month:
            base_color = "#BDBDBD"  # 비현재월(빈 셀) — 기존 동작 보존

        if self._is_today:
            bg_style += "background: #01295F;"
            base_color = "white"
            count_color = "rgba(255,255,255,200)"
        elif selected:
            bg_style += "background: rgba(1,41,95,20);"

        self.setStyleSheet(bg_style)
        self.day_label.setStyleSheet(f"color: {base_color}; background: transparent; padding: 2px;")
        self.squares_label.setStyleSheet("font-size: 10px; background: transparent;")
        self.count_label.setStyleSheet(
            f"color: {count_color}; font-size: 9px; font-weight: bold; background: transparent;"
        )
```

- [ ] **Step 5: `_refresh_calendar` 셀 생성부 교체**

`ui_main.py` `_refresh_calendar` 의 1146-1152행(현재 `event_colors = ...` ~ `CalendarDayButton(...)` 호출)을 아래로 교체:

```python
                event_colors = event_date_colors.get(target_date, [])
                is_holiday = bool(target_date) and holidays.is_holiday(target_date)

                cell = CalendarDayButton(
                    actual_day, is_today, event_colors, is_current, target_date,
                    is_holiday, col_idx, 0, self
                )
```

(개수 인자는 우선 `0`. Phase 3에서 실제 값으로 연결한다. 기존 `holiday_name = ...` 줄은 삭제된다.)

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest tests/test_ui.py::test_calendar_holiday_dates_use_red tests/test_ui.py::test_calendar_cell_has_no_holiday_label tests/test_ui.py::test_calendar_weekend_dates_use_weekend_colors -v`
Expected: 3개 PASS (기존 주말 색 테스트 회귀 없음).

- [ ] **Step 7: Checkpoint**

Run: `python -m pytest tests -q`
Expected: 전체 PASS.

---

### Task 5: 하단 패널에 공휴일명 표시 (TDD)

**Files:**
- Modify: `ui_main.py` (`_build_bottom_panel` 1054-1071행 부근, `_on_date_selected` 1164-1196행 부근)
- Test: `tests/test_ui.py` (추가)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ui.py` 끝에 추가:

```python
def test_selected_holiday_shows_name_in_bottom(qtbot, app_dir, qapp):
    """공휴일 선택 시 하단 holiday_info_label에 공휴일명이 (음력 설정과 무관하게) 표시."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._current_year = 2026
    win._current_month = 6
    win._refresh_calendar()

    win._on_date_selected("2026-06-06")  # 현충일
    assert "현충일" in win.holiday_info_label.text()

    win._on_date_selected("2026-06-08")  # 평일
    assert win.holiday_info_label.text() == ""
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_ui.py::test_selected_holiday_shows_name_in_bottom -v`
Expected: FAIL — `AttributeError: 'MainCalendarWindow' object has no attribute 'holiday_info_label'`.

- [ ] **Step 3: `holiday_info_label` 위젯 추가**

`ui_main.py` `_build_bottom_panel` 에서 `lunar_info_label` 추가 직후(현재 1064행 `date_row.addWidget(self.lunar_info_label)` 다음 줄)에 삽입:

```python
        # 공휴일명 라벨 (빨강) — 음력 설정과 무관하게 항상 표시
        self.holiday_info_label = BodyLabel("", self)
        self.holiday_info_label.setStyleSheet("color: #D32F2F; font-weight: bold; font-size: 11px;")
        date_row.addWidget(self.holiday_info_label)
```

- [ ] **Step 4: `_on_date_selected` 에서 공휴일명 설정**

`ui_main.py` `_on_date_selected` 의 `self._load_schedules()` 호출(현재 1196행) **바로 앞**에 삽입:

```python
        hol = holidays.get_holiday(date_str)
        self.holiday_info_label.setText(f" · {hol}" if hol else "")
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_ui.py::test_selected_holiday_shows_name_in_bottom -v`
Expected: PASS.

- [ ] **Step 6: Checkpoint**

Run: `python -m pytest tests -q`
Expected: 전체 PASS.

---

# Phase 3 — 일자별 총 개수 (A)

### Task 6: `database.py` 날짜별 개수 집계 함수 (TDD)

**Files:**
- Modify: `database.py` (`get_all_schedule_date_colors` 467행 다음에 추가)
- Test: `tests/test_database.py` (추가)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_database.py` 의 `TestScheduleDateColors` 클래스 **다음**에 추가:

```python
# ─── get_all_schedule_date_counts ────────────────────────────

class TestScheduleDateCounts:
    def test_counts_total_per_date(self, app_dir):
        db.add_schedule("2025-08-01", "a", "#FFD166")
        db.add_schedule("2025-08-01", "b", "#FFD166")  # 같은 색도 별개로 카운트
        db.add_schedule("2025-08-01", "c", "#FF6B6B")
        result = db.get_all_schedule_date_counts()
        assert result["2025-08-01"] == 3

    def test_empty_db_returns_empty(self, app_dir):
        assert db.get_all_schedule_date_counts() == {}

    def test_separate_dates(self, app_dir):
        db.add_schedule("2025-09-01", "a", "#FFD166")
        db.add_schedule("2025-09-02", "b", "#FFD166")
        db.add_schedule("2025-09-02", "c", "#4CC9F0")
        result = db.get_all_schedule_date_counts()
        assert result["2025-09-01"] == 1
        assert result["2025-09-02"] == 2
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_database.py::TestScheduleDateCounts -v`
Expected: FAIL — `AttributeError: module 'database' has no attribute 'get_all_schedule_date_counts'`.

- [ ] **Step 3: 함수 구현**

`database.py` 의 `get_all_schedule_date_colors()` 정의 끝(467행) **다음**에 추가:

```python
def get_all_schedule_date_counts() -> dict[str, int]:
    """일정이 있는 날짜별 총 일정 수 (달력 개수 표시용)"""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT date, COUNT(*) AS n FROM schedules GROUP BY date"
        ).fetchall()
        return {row["date"]: row["n"] for row in rows}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_database.py::TestScheduleDateCounts -v`
Expected: 3개 PASS.

- [ ] **Step 5: Checkpoint**

Run: `python -m pytest tests -q`
Expected: 전체 PASS.

---

### Task 7: 셀 개수 초기 표시 연결 (TDD)

**Files:**
- Modify: `ui_main.py` (`_refresh_calendar` — counts 조회 및 셀에 전달)
- Test: `tests/test_ui.py` (추가)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ui.py` 끝에 추가:

```python
def test_calendar_cell_shows_total_count(qtbot, app_dir, qapp):
    """셀에 그날 총 일정 수가 표시되고, 0개면 빈칸."""
    db.add_schedule("2026-07-10", "a", "#FFD166")
    db.add_schedule("2026-07-10", "b", "#FFD166")
    db.add_schedule("2026-07-10", "c", "#4CC9F0")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._current_year = 2026
    win._current_month = 7
    win._refresh_calendar()
    assert win._day_cells["2026-07-10"].count_label.text() == "3"
    assert win._day_cells["2026-07-11"].count_label.text() == ""
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_ui.py::test_calendar_cell_shows_total_count -v`
Expected: FAIL — `count_label.text()` 이 `""` (아직 0으로만 전달됨).

- [ ] **Step 3: `_refresh_calendar` 에 개수 조회/전달 추가**

`ui_main.py` `_refresh_calendar` 의 `event_date_colors = db.get_all_schedule_date_colors()`(현재 1124행) **다음 줄**에 추가:

```python
        event_date_counts = db.get_all_schedule_date_counts()
```

그리고 Task 4 Step 5에서 만든 셀 생성부의 `0` 인자를 실제 값으로 교체:

```python
                event_colors = event_date_colors.get(target_date, [])
                is_holiday = bool(target_date) and holidays.is_holiday(target_date)
                count = event_date_counts.get(target_date, 0)

                cell = CalendarDayButton(
                    actual_day, is_today, event_colors, is_current, target_date,
                    is_holiday, col_idx, count, self
                )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_ui.py::test_calendar_cell_shows_total_count -v`
Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run: `python -m pytest tests -q`
Expected: 전체 PASS.

---

### Task 8: 일정 추가/삭제 시 셀 개수 실시간 갱신 (TDD)

**Files:**
- Modify: `ui_main.py` (`_on_add_schedule` 1316행 부근, `_on_delete_schedule` 1288행 부근)
- Test: `tests/test_ui.py` (추가)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ui.py` 끝에 추가:

```python
def test_cell_count_updates_live_on_add_and_delete(qtbot, app_dir, qapp):
    """일정 추가/삭제 시 그리드 재빌드 없이 셀 개수가 즉시 갱신."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._current_year = 2026
    win._current_month = 7
    win._refresh_calendar()
    win._on_date_selected("2026-07-15")
    assert win._day_cells["2026-07-15"].count_label.text() == ""

    # 추가
    win._schedule_color = "#FFD166"
    win.schedule_input.setText("새 일정")
    win._on_add_schedule()
    assert win._day_cells["2026-07-15"].count_label.text() == "1"

    # 삭제
    item = win.schedule_list.item(0)
    sid = item.data(Qt.UserRole)
    win._on_delete_schedule(item, sid)
    assert win._day_cells["2026-07-15"].count_label.text() == ""
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_ui.py::test_cell_count_updates_live_on_add_and_delete -v`
Expected: FAIL — 추가 후에도 `count_label.text()` 이 `""`.

- [ ] **Step 3: `_on_add_schedule` 에 개수 갱신 추가**

`ui_main.py` `_on_add_schedule` 의 `cell._update_squares(sorted_colors)`(현재 1316행) **다음 줄**에 추가:

```python
                cell.set_count(self.schedule_list.count())
```

- [ ] **Step 4: `_on_delete_schedule` 에 개수 갱신 추가**

`ui_main.py` `_on_delete_schedule` 의 `cell._update_squares(sorted_colors)`(현재 1288행) **다음 줄**에 추가:

```python
                cell.set_count(self.schedule_list.count())
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_ui.py::test_cell_count_updates_live_on_add_and_delete -v`
Expected: PASS.

- [ ] **Step 6: Checkpoint**

Run: `python -m pytest tests -q`
Expected: 전체 PASS.

---

### Task 9: 최종 회귀 + 수동 스모크 점검

**Files:** 없음 (검증 전용)

- [ ] **Step 1: 전체 테스트**

Run: `python -m pytest tests -q`
Expected: 전체 PASS.

- [ ] **Step 2: 앱 수동 실행 점검**

Run: `python main.py`
확인 항목:
- 일정 여러 개 추가한 날 셀에 회색 숫자(예: `3`)가 심볼 아래에 뜬다. 추가/삭제 시 즉시 변한다.
- 일정 0개 날은 심볼·개수 모두 빈칸.
- 공휴일(예: 6/6 현충일, 5/5 어린이날)의 날짜 숫자가 빨강. 오늘 셀은 남색 배경+흰 숫자.
- 공휴일 날짜 선택 시 하단에 빨강으로 공휴일명이 뜬다(설정 > 음력 표시 OFF 여도).
- 셀 높이가 기존과 동일(길어지지 않음).

- [ ] **Step 3: 완료 보고**

수용 기준(스펙 §13) 충족 여부를 사용자에게 보고한다. Phase 1 재수집을 건너뛴 경우 그 사실과 현재 공휴일 데이터 범위를 함께 보고한다.

---

## Self-Review 메모 (작성자 확인 완료)

- **스펙 커버리지:** A(Task 6-8), B(Task 4-5), C′(Task 1-3) 모두 태스크로 매핑됨. 수용 기준 §13의 7개 항목은 Task 4/5/7/8/3/9 에서 검증.
- **타입 일관성:** 셀 메서드명 `set_count(n)`, 속성 `count_label`, DB 함수 `get_all_schedule_date_counts()`, 검증 함수 `verify_holiday_data(hol)` — 전 태스크에서 동일하게 사용.
- **순서 의존성:** Task 4가 `count_label`/`set_count`/셀 시그니처(개수 인자 포함)를 먼저 도입하고, Task 7이 그 인자에 실제 값을 연결 → 충돌 없음.
- **플레이스홀더:** 없음(모든 코드/명령 구체화).
