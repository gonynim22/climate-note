# 설계: 캘린더 일자별 총 개수 표시 + 공휴일 강조

- 날짜: 2026-06-02
- 대상 앱: 기후노트 (`MyDesktopCalendar`) v2.9
- 상태: 승인됨 (구현 대기)
- 관련 파일: `ui_main.py`, `database.py`, `fetch_data.py`, `holidays.py`(생성물), `tests/`

---

## 1. 배경 / 문제

캘린더 셀에는 일정 색상 사각형(`■`)이 **색 종류별 1개씩 최대 3개**만 표시된다(`get_all_schedule_date_colors()` 가 `set` 으로 색을 중복 제거). 따라서 한 날짜에 일정이 7개 있어도 3개처럼 보여서 **달력만 보고 총 일정 수를 알 수 없다**(클라이언트 요청).

추가로, 현재 공휴일은 평일/토요일에 걸리면 날짜 숫자가 검정/파랑으로 표시되어 “쉬는 날” 임이 드러나지 않는다. 공휴일 데이터(`holidays.py`)는 오래전 하드코딩되어 최신성이 의심된다.

## 2. 목표 (Goals)

1. **A.** 각 날짜 셀에 그날 **총 일정 수**를 직관적으로 표시(디자인을 해치지 않게).
2. **B.** 공휴일 날짜의 숫자를 **빨강**으로 강조(요일 무관, 쉬는 날 = 빨강). 공휴일명은 하단 선택 영역으로 이동.
3. **C′.** 공휴일/음력 데이터를 **실제 API에서 다시 받아 최신화**.

## 3. 비목표 (Non-Goals)

- 미래 연도 공휴일을 **임의 계산으로 채우지 않는다.** API가 제공하는 범위만 사용한다. (`calculate_holidays()` 사용 금지)
- 색상 사각형의 기존 동작(색=종류, 색당 1개, 최대 3색)은 변경하지 않는다.
- 휴지통/복구, 일정 종류 확장 등은 범위 밖.

## 4. 확정된 결정 (Decisions)

| 항목 | 결정 |
|---|---|
| 숫자 의미 | **총 개수**(그날 전체 일정 수). 초과분(+N) 아님 |
| 표시 조건 | 일정이 **1개 이상이면** 표시(0이면 빈칸) |
| 표기 형식 | **숫자만 `7`** (단위/기호 없음), 회색 작은 글자 |
| 셀 레이아웃 | **Option 3**: `[날짜 / 심볼 / 총개수]`. 공휴일명 행은 셀에서 제거 |
| 공휴일 빨강 | **항상**(음력 표시 설정과 무관). `KOREAN_HOLIDAYS` 의 모든 항목(대체·임시·선거일 포함) |
| 공휴일명 | 셀에서 제거 → **하단 선택 영역**에 빨강으로, 선택 시 **항상** 표시(설정 무관) |
| 데이터 갱신 | **실제 API 재수집**만. 계산 금지. API 범위(예: ~2027/2028)만 사용 |
| 진행 순서 | **Phase 1(데이터) → Phase 2(공휴일 빨강/B) → Phase 3(개수/A)** |

## 5. 현재 구조 (확인된 사실)

- 셀 위젯 `CalendarDayButton`(`ui_main.py`): 세로 레이아웃 `day_label` → `holiday_lbl`(고정 12px, 공휴일 없어도 자리 차지) → `squares_label`(RichText, 고정 14px). 셀 자체는 고정 크기 없이 `calendar_grid`(spacing 2)에서 늘어남.
- `_refresh_calendar()`: `db.get_all_schedule_date_colors()` 로 날짜별 색 목록을 받아 셀 생성. 공휴일명은 `holidays.get_holiday(target_date) if (target_date and self._show_lunar) else ""` — **음력 표시 ON 일 때만** 셀에 전달.
- 일정 추가/삭제(`_on_add_schedule`/`_on_delete_schedule`)는 **그리드를 재빌드하지 않고** `cell._update_squares(...)` 로 해당 셀만 즉석 갱신. 하단 개수는 `_update_count()` 가 `"총 N개"` 로 표시.
- 하단 `date_row`: `[selected_date_label][lunar_info_label(녹색)] … stretch … [count_label(회색, "총 N개")]`.
- 데이터: `KOREAN_HOLIDAYS` **2025–2027(61건)**, `LUNAR_MAPPING` **2025–2050(9,496건)**. `holidays.py` 는 `.gitignore` 대상(생성물). `fetch_data.py` 가 공공데이터포털 API(`getRestDeInfo`, `getLunCalInfo`)로 생성. `calculate_holidays()` 는 정의돼 있으나 `main()` 에서 **호출되지 않음**(미사용)이며 2026년 부활한 제헌절 등이 누락돼 부정확.

---

## 6. Phase 1 — 데이터 갱신 (실제 API만)

### 변경
- `fetch_data.py`
  - 미사용 `calculate_holidays()` 함수와 “API 이후 연도를 계산해 2050까지 채운다”는 docstring 제거 → **순수 API 기반**으로 정리.
  - `main()` 은 현행대로 API가 반환한 연도만 저장(이미 계산 미사용). 음력은 API가 주는 범위 수집.
- `holidays.py` 재생성(스크립트 실행 결과물).

### 절차 & 데이터 보존 안전장치 (핵심)
1. 실행 전 기존 `holidays.py` → `holidays.py.bak` 백업.
2. `python fetch_data.py` 실행(`.env`의 `LUNAR_API_KEY`, 네트워크 필요).
3. **검증**: 재생성 파일이
   - `LUNAR_MAPPING` 연도 범위가 기존 이상(최소 2050까지 유지),
   - `KOREAN_HOLIDAYS` 가 최소 2027년까지 포함, 건수가 비정상적으로 적지 않음
   을 만족하는지 확인하는 검증 스크립트/테스트 통과.
4. 검증 실패(네트워크/키 오류로 빈약/부분 생성) 시 **백업 복구** 후 사용자에게 보고. 기존 데이터(2027까지) 유지.

### 전제
- 네트워크/유효 API 키가 없으면 Phase 1은 스킵하고 기존 데이터로 Phase 2~3 진행(사용자 합의).

### 산출물 확인
- 갱신 후 `KOREAN_HOLIDAYS` 의 최신성(예: 신규 임시공휴일 반영) 및 범위를 로그로 보고.

---

## 7. Phase 2 — 공휴일 빨강 강조 (B)

### `ui_main.py` — `CalendarDayButton`
- 생성자에 `is_holiday: bool` 인자 추가(기존 `holiday_name` 의존 제거).
- `holiday_lbl`(공휴일명 행) **제거**. 레이아웃은 `day_label` → `squares_label` → (Phase 3에서) `count_label`.
- `_set_style()` 색 산출 순서(아래에서 위로 덮어쓰기):
  1. 기본: 평일 `#1a1a1a`, 일요일(col 0) `#D32F2F`, 토요일(col 6) `#1565C0`.
  2. **공휴일**(`is_holiday`)이면 `#D32F2F` 로 덮어씀(요일 무관).
  3. **비현재월**(`_is_current_month=False`)이면 `#BDBDBD` 로 덮어씀(공휴일·요일보다 우선). 단 `monthdayscalendar` 가 타 월 날짜를 `0`(빈 셀)으로 처리하므로 실제로는 숫자 없는 빈 셀이라 영향은 거의 없음 — 기존 동작 보존 차원.
  4. **오늘**이면 배경 남색 `#01295F` + 숫자 흰색(오늘이 공휴일이어도 흰색 유지).
  5. 선택 상태는 배경만 변경(숫자색 불변).

### `ui_main.py` — `_refresh_calendar()`
- `is_holiday = holidays.is_holiday(target_date)` 를 **음력 설정과 무관하게 항상** 계산해 셀에 전달.

### `ui_main.py` — 하단 패널
- `_build_bottom_panel()` 의 `date_row` 에 `holiday_info_label`(빨강 `#D32F2F`, bold) 추가(음력 라벨 옆).
- `_on_date_selected()`: 선택 날짜가 공휴일이면 `holiday_info_label` 에 `"· {공휴일명}"` 설정(**항상**, 설정 무관), 아니면 빈 문자열. 음력 정보(`lunar_info_label`)는 기존대로 `_show_lunar` 토글을 따름.

### 부수 정리
- `_show_lunar` 가 이제 셀 공휴일명을 게이트하지 않으므로 관련 코드 제거. 설정 화면의 “음력 표시” 설명이 공휴일을 함께 언급하면 **음력 한정**으로 문구 점검(필요 시 수정).

---

## 8. Phase 3 — 일자별 총 개수 (A)

### `database.py`
- 신규 함수:
  ```python
  def get_all_schedule_date_counts() -> dict[str, int]:
      """일정이 있는 날짜별 총 일정 수 (달력 개수 표시용)"""
      with _connection() as conn:
          rows = conn.execute(
              "SELECT date, COUNT(*) AS n FROM schedules GROUP BY date"
          ).fetchall()
          return {row["date"]: row["n"] for row in rows}
  ```
  (`_connection()` 사용, 파라미터 없는 집계라 인젝션 위험 없음)

### `ui_main.py` — `CalendarDayButton`
- 심볼 행 **아래** `count_label`(QLabel) 추가:
  - 스타일: 작은 글자, 회색 `#9aa0a6`, 가운데 정렬, 고정 높이 ~12px.
  - 오늘 셀에서는 흰색계열(`rgba(255,255,255,0.8)`).
- 메서드 `set_count(n: int)`: `n>0` → `str(n)`, 아니면 `""`.
- 생성자에서 초기 개수 인자 받아 표시.

### `ui_main.py` — `_refresh_calendar()`
- `counts = db.get_all_schedule_date_counts()` 한 번 호출, 셀 생성 시 `counts.get(target_date, 0)` 전달.

### `ui_main.py` — 실시간 갱신
- `_on_add_schedule()` / `_on_delete_schedule()` 의 `cell._update_squares(...)` 직후에
  `cell.set_count(self.schedule_list.count())` 추가. (그리드 재빌드 불필요 — 기존 즉석 갱신 패턴과 동일)

### 셀 높이
- 공휴일 행 제거(−12px) + 개수 행 추가(+12px) = **순증 0**. 셀 높이 변화 없음.

---

## 9. 데이터 흐름 요약

```
[월 진입/이동]  _refresh_calendar()
   ├─ get_all_schedule_date_colors() → 색 사각형
   ├─ get_all_schedule_date_counts() → 개수            (신규)
   └─ holidays.is_holiday(date)      → 빨강 여부        (항상)

[일정 추가/삭제]  _on_add/_on_delete_schedule()
   ├─ cell._update_squares(...)      (기존)
   └─ cell.set_count(list.count())   (신규)

[날짜 선택]  _on_date_selected()
   ├─ lunar_info_label   ← 음력 (음력 표시 ON일 때만)
   ├─ holiday_info_label ← 공휴일명 (항상)             (신규)
   └─ count_label        ← "총 N개" (기존)
```

## 10. 에러 처리 / 보안 규칙 (행안부 CODEMIND)

- DB 접근은 `_connection()` 컨텍스트 매니저만 사용(직접 `sqlite3.connect()` 금지) — 0026_RESLEAK.
- 파일 입출력은 `with open(...)` — 0026_RESLEAK.
- 예외는 타입별 세분화 + 로깅. `except: pass` 단독 금지(데이터 검증 실패는 로그/복구) — 0023/0024.
- 데이터 변경(holidays.py 재생성)은 백업/복구 경로 포함 — 데이터 보존 원칙.

## 11. 테스트 (`tests/`)

- `get_all_schedule_date_counts()`: 같은 날 여러 색·여러 건 입력 → 정수 합이 정확한지 왕복 테스트. 일정 없는 날은 키 부재 확인.
- 공휴일 색 로직: `is_holiday` 기반으로 (오늘/공휴일/일/토/평일) 우선순위가 기대대로인지 단위 테스트(스타일 산출 함수 분리 가능하면 그 함수 대상).
- 데이터 검증 함수: 범위/건수 검증 로직과 실패 시 복구 동작 테스트.
- 기존 캘린더/DB/보안 테스트 회귀 통과(`python -m pytest tests -q`).

## 12. 리스크 / 전제

- **Phase 1은 네트워크 + 유효 API 키 의존.** 불가 시 갱신 스킵, 기존 데이터(2027까지) 사용.
- 재생성 결과가 기존보다 빈약하면 **덮어쓰지 않고 복구** 후 보고(음력 2050 데이터 손실 방지).
- `holidays.py` 는 생성물이라 백업 파일(`holidays.py.bak`)은 임시이며 커밋/배포 대상 아님.

## 13. 수용 기준 (Acceptance)

1. 일정이 N개인 날짜 셀에 회색 숫자 `N` 이 심볼 아래 표시되고, 추가/삭제 시 즉시 반영된다(월 이동 없이).
2. 일정 0개인 날은 심볼·개수 모두 빈칸이다.
3. 공휴일(평일/토 포함)의 날짜 숫자가 빨강이다. 오늘 셀은 남색 배경+흰 숫자를 유지한다.
4. 공휴일명이 셀에서 사라지고, 날짜 선택 시 하단에 빨강으로 항상 표시된다(음력 표시 OFF여도).
5. 셀 높이가 기존과 동일하다(행 추가로 길어지지 않음).
6. `holidays.py` 가 실제 API 데이터로 갱신되거나(성공 시), 실패 시 기존 데이터가 안전하게 보존된다.
7. `python -m pytest tests -q` 전체 통과.
