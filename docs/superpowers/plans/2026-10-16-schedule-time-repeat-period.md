# v4.1 일정 시각·알림·반복·기간 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 데이터를 한 값도 바꾸지 않고, 일정에 시작 시각·여러 날 기간·반복·알림을 더한 기후노트 v4.1을 만든다.

**Architecture:** 규칙(검증·펼치기·알림 시각·막대 차선·한국어 문구)은 Qt·DB 없는 `schedule_rules.py`에 모은다. DB는 v18에서 일정 표에 열 6개만 한 트랜잭션으로 더하고, 화면은 '나타나는 일정' API(`get_schedules`·`get_occurrences`)를 쓴다. 화면 부품은 새 모듈 세 개(`ui_schedule_options.py`·`ui_calendar_spans.py`·`ui_schedule_alarm.py`)로 나누고 `ui_main.py`에는 연결만 더한다.

**Tech Stack:** Python 3.13, PySide6 6.11.2, PySide6-Fluent-Widgets, SQLite(WAL), cryptography(Fernet), pytest·pytest-qt, PyInstaller

**Spec:** `docs/superpowers/specs/2026-10-16-schedule-time-repeat-period-design.md` (확정 시안: `output/design/schedule-features-20261015/index.html`)

## Global Constraints

- 기존 사용자 데이터 값은 바뀌거나 사라지면 안 된다. 스키마는 `ALTER TABLE ... ADD COLUMN`만, 표 DROP/재생성 금지.
- `migrate()`는 멱등이다. v18 블록은 `BEGIN IMMEDIATE`~`COMMIT` 한 트랜잭션이고, 실패하면 `ROLLBACK` 후 예외를 다시 올린다.
- 버전 값: `APP_VERSION = "v4.1"`, Windows `4.1.0.0`, `CURRENT_SCHEMA_VERSION = 18`, `EXPORT_FORMAT_VERSION = 3`.
- 새 설정 키는 `schedule_alarm_seen_at` 하나다. Export에서 빼고 Import에서 무시한다. 설정 창에는 줄을 더하지 않는다.
- 런타임은 오프라인 전용이다. 새 의존성·새 그림/리소스 파일·새 DLL을 만들지 않고 `build.spec`도 바꾸지 않는다. 아이콘은 `QPainter`로 그린다.
- 사용자 본문을 보이는 새 라벨은 모두 `Qt.PlainText`다.
- QSS 글꼴 크기는 정수 px만 쓰고, 규칙은 `#objectName` 범위로 좁힌다(메뉴로 번지지 않게).
- 팝업 규칙
  - 이모지 팝업과 같은 수명 규칙: 한 번에 하나, `deleteLater`, 늦은 콜백 무효화, 버튼 소유 타이머로 포커스 복원.
  - 팝업 안에서 드롭다운·`QCalendarWidget`·메뉴를 띄우지 않는다.
- AGENTS.md 코딩 규칙: DB는 `database._connection()`, 파일은 `with open`, bare except·이유 없는 except/pass 금지.
- 시험은 합성 데이터만 쓴다(`app_dir` 픽스처·`output/harness`). 실사용 AppData·실행 중인 앱은 건드리지 않는다.
- 주석·화면 문구·커밋 메시지는 한국어, 식별자는 영어(PEP 8).
- 시험 실행: `.venv/Scripts/python.exe -m pytest ...`(Git Bash 가능). release·빌드는 PowerShell에서만 한다.
- 브랜치·커밋
  - 커밋은 `feature/v4.1-schedule-time-repeat` 브랜치에서 작업마다 하고, `git add`에는 그 작업의 파일만 이름으로 적는다.
  - 작업 폴더에 있던 9월 미커밋 변경(AGENTS.md·docs/RELEASE_HISTORY.md)은 Task 1에서 stash로 보존하고 섞지 않는다.
  - main 병합·push·Release는 사용자 승인 후에만 한다.
- 커밋 메시지 끝에 넣는 줄: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`

## Review Focus

1. **형식이 다른 옛 날짜 문자열**(예: 가져오기로 들어온 `2026-7-1`)을 가진 기존 일정: 하루 보기·달 보기·내보내기·가져오기가 멈추지 않고 지금과 똑같이 동작해야 하며, 화면에서는 본문 편집만 되고 시계 버튼은 꺼진다 → Task 5·6 시험(`test_get_occurrences_expands_repeat_and_period_and_keeps_legacy_strings`·`test_legacy_date_string_survives_export_import`), Task 8·11 시험(`test_legacy_date_disables_button`·`test_legacy_date_row_still_edits_text_but_not_options`).
2. **구 키(MAC)로 암호화된 본문 + 첫 실행 마이그레이션**: 같은 시작에서 재암호화와 열 추가가 함께 일어나도 복호화한 본문이 같고 새 열은 기본값이어야 한다 → Task 4 시험(`test_v17_upgrade_with_legacy_key_rows_keeps_plaintext`, Task 5에서 통과).
3. **시계가 뒤로 가거나 12시간 넘게 앞으로 뛰는 경우**(수동 변경·절전): 알림이 중복으로 쏟아지거나 아주 오래된 알림이 터지지 않고 지난 12시간 것만 보여야 한다 → Task 14 시험(`test_clock_jumps_do_not_flood_or_repeat`·`test_missed_alarms_only_from_last_12_hours`).
4. **본문에 `<b>`나 아주 긴 글이 있는 일정**: 칩·막대·목록·카드·알약·편집 요약에서 글자 그대로 보이고 말줄임되며, 7열 너비 계약이 깨지지 않아야 한다 → Task 8(`test_elided_label_keeps_full_plain_text_and_shrinks`), Task 9(`test_body_is_plain_text_and_long_text_keeps_delete_button`·`test_timed_chip_and_plain_text`), Task 12(`test_bars_do_not_change_column_widths_and_follow_resize`), Task 14(`test_card_rows_plain_text_lock_and_beep`) 시험.
5. **달 경계를 넘는 기간, 31일 매월 반복의 2월**: 달 첫 주·마지막 주 빈칸 옆 막대 끝 모양이 맞고 2월은 말일로 보여야 한다 → Task 3(`test_week_segments_split_at_week_and_month_edges_and_assign_lanes`·`test_monthly_on_31_uses_the_last_day_of_short_months`), Task 9(`test_monthly_31st_shows_on_february_last_day`), Task 12(`test_bar_from_previous_month_has_square_start_next_to_blank_cells`) 시험.

> 이 계획의 코드는 작성 중에 저장소 밖 임시 사본(현재 HEAD `09df938`의 `git archive`)에 계획 본문을 그대로 적용해 확인했다.
> - 1부 데이터 시험 429개 통과, 2부 각 Task의 '먼저 실패 → 구현 뒤 통과', 전체 `pytest tests` 2,662개 통과
> - 그 사본으로 PowerShell에서 실제 v4.1 EXE 빌드(4.1.0.0, mingw DLL 없음) → 격리 실행 4개 시나리오(fresh·existing·blocked·upgrade) 통과, upgrade에서 '기후노트 업데이트 안내' 창 표시 확인
> - 보관 중인 실제 `dist/기후노트_v4.0a.exe`로 Task 17 리허설 통과: v17 합성 데이터 → v4.0a 정상 → v4.1 업그레이드(안내창 표시, 기존 값·salt 불변, 스냅샷=원본) → v4.0a는 v18에서 '데이터 보호를 위해 실행을 중단했습니다' 창으로 멈추고 DB·salt·백업 불변 → README_detail 되돌리기 절차 뒤 v4.0a가 업데이트 직전 데이터로 정상 시작
>
> 실제 구현은 이 계획대로 다시 하며, 그때의 실행 ID가 정식 검증 증거다.

## File Structure

| 파일 | 책임 |
|---|---|
| `schedule_rules.py` (새) | `ScheduleOptions`·`AlarmItem`·`SpanSegment`, 시각 입력 해석, `validate_options`, 펼치기, 알림 시각, 옵션 변환, 주 단위 막대 조각·차선, 한국어 설명·알약 문구. Qt·DB 의존 없음 |
| `database.py` | v18 열·마이그레이션·건강 검사, 나타나는 일정 조회(`get_schedules`·`get_occurrences`), 세부 설정 쓰기, 이 날만 삭제, 알림 조회, Export v3/Import v1~v3 |
| `main.py` | `schema_newer` 안내 문구, 예전 형식 DB를 올린 실행 알림(`on_upgrade`) |
| `ui_schedule_options.py` (새) | 아이콘 그리기, 팝업 위치, `ElidePaintMixin`·`ElidedLabel`, `ScheduleOptionsButton`·`ScheduleOptionsPopup`·`MiniMonthPicker`·`ScheduleOptionsPills` |
| `ui_schedule_emoji.py` | 편집기에 시계 버튼·요약 줄. `SCHEDULE_CONTROL_DIAMETER`·`popup_position`은 새 모듈에서 다시 내보냄 |
| `ui_calendar_spans.py` (새) | 중간·크게 달력의 기간 막대 오버레이 |
| `ui_schedule_alarm.py` (새) | 알림 엔진 `ScheduleAlarmScheduler`, 카드 `ScheduleAlarmCard` |
| `ui_main.py` | 입력줄·목록·편집·삭제·달 갱신·막대·알림의 연결, 업데이트 1회 안내창 |
| `ui_search.py` | 반복·기간 꼬리 표시 |
| `tools/smoke_release.py`, `tools/verify.py` | 업그레이드 시나리오, 시험 목록 |
| `tests/fixtures/schema_v17.sql` (새) | v4.0a 코드로 뽑은 v17 DDL·기본 설정 원문 |
| `tests/test_schedule_rules.py`, `tests/test_schedule_storage.py`, `tests/test_ui_schedule_options.py`, `tests/test_ui_schedule_input.py`, `tests/test_ui_schedule_list.py`, `tests/test_ui_calendar_spans.py`, `tests/test_ui_schedule_alarm.py`, `tests/test_upgrade_notice.py` (새) | 작업별 시험 |
| `app_info.py`, `AGENTS.md`, `docs/ARCHITECTURE.md`·`UI_PATTERNS.md`·`TESTING.md`·`RELEASE_HISTORY.md`, `README.md`·`README_detail.md` | v4.1 표시·정본 계약·업그레이드/되돌리기 안내 |

| Task | 내용 | 주 파일 |
|---|---|---|
| 1~3 | 규칙(세부 설정·검증·펼치기·알림 시각·막대 차선·문구) | `schedule_rules.py` |
| 4~6 | DB v18 마이그레이션·건강 검사, 나타나는 일정 API, Export v3/Import | `database.py`, `main.py` |
| 7 | 릴리스 격리 실행 'upgrade' 시나리오 | `tools/smoke_release.py` |
| 8 | 세부 설정 부품(시계 버튼·카드·작은 달력·알약) | `ui_schedule_options.py` |
| 9~11 | 달력 월 데이터·목록 줄, 입력줄 연결, 편집·반복 지우기 | `ui_main.py`, `ui_schedule_emoji.py` |
| 12 | 여러 날 막대 | `ui_calendar_spans.py`, `ui_main.py` |
| 13 | 검색 꼬리 | `ui_search.py` |
| 14 | 알림 엔진·카드 | `ui_schedule_alarm.py`, `ui_main.py` |
| 15 | 업데이트 1회 안내창(예전 형식을 올린 실행에서만) | `main.py`, `ui_main.py`, `tools/smoke_release.py` |
| 16~17 | 버전·문서, release·실제 EXE 리허설·배치 | 문서, `dist/` |

---

## 1부 — 데이터 (Task 1~7)

### Task 1: 작업 준비와 규칙 기본(세부 설정·검증·시각 입력)

**Files:**
- Create: `docs/work/2026-10-16-v4.1-schedule-time-repeat-period.md`
- Create: `tests/fixtures/schema_v17.sql`
- Create: `schedule_rules.py`
- Test: `tests/test_schedule_rules.py`

**Interfaces:**
- Consumes: 없음
- Produces
  - `schedule_rules.ScheduleOptions`(동결 dataclass): 필드 `start_time:str`, `end_date:str`, `repeat_rule:str`, `repeat_until:str`, `repeat_skip:tuple[str,...]`, `alarm_before:int|None`
    - `is_default`, `from_row(row)`, `to_db_values() -> (start_time, end_date, repeat_rule, repeat_until, "a,b", alarm_before)`
  - 상수: `REPEAT_RULES`, `TIMED_ALARMS=(0,10,30,60,1440)`, `ALLDAY_ALARMS=(0,1440)`, `MAX_SPAN_DAYS=365`, `MAX_SKIPS=500`, `KOREAN_WEEKDAYS`
  - 함수: `parse_date(value)->date`, `parse_time_input(text)->"HH:MM"`, `validate_options(start, options)->ScheduleOptions`(정규화: 건너뛴 날 정렬·중복 제거)

- [ ] **Step 1: 브랜치를 만들고 9월 미커밋 변경을 보존한다**

```bash
cd /d/04_Project/GC/MyDesktopCalendar
git switch main
git log -1 --format=%h        # 09df938 또는 그 뒤여야 한다
# 9월 미커밋 변경을 파일로도 남긴 뒤(이중 보존) stash로 작업 트리에서 뺀다.
mkdir -p output/v41-preserve
git diff -- AGENTS.md docs/RELEASE_HISTORY.md > output/v41-preserve/september-uncommitted.patch
test -s output/v41-preserve/september-uncommitted.patch   # 비어 있으면 멈추고 사용자에게 알린다
git stash push -m "9월 미커밋 기록(AGENTS·RELEASE_HISTORY) 보존 — v4.1 작업과 분리" -- AGENTS.md docs/RELEASE_HISTORY.md
git switch -c feature/v4.1-schedule-time-repeat
git status --short            # AGENTS.md·docs/RELEASE_HISTORY.md가 'M'으로 보이지 않아야 한다
git stash list | head -1      # 위 메시지의 stash가 맨 위에 있어야 한다
```

> 이 stash와 patch는 v4.1 커밋에 넣지 않는다. 되돌리는 시점(`git stash pop`)은 Task 17 끝에서 사용자에게 묻는다.

- [ ] **Step 2: 작업 기록을 만든다** — `docs/work/2026-10-16-v4.1-schedule-time-repeat-period.md`

```markdown
# 작업 기록: v4.1 일정 시각·알림·반복·기간

작성일: 2026-10-16 / 상태: 진행 중

## 목표와 범위

- 목표: 기존 데이터를 바꾸지 않고 일정에 시작 시각·여러 날 기간·반복·알림을 더한다(v4.1, DB v18, Export v3).
- 변경 대상: 설계 문서의 '모듈 구성' 목록(`docs/superpowers/specs/2026-10-16-schedule-time-repeat-period-design.md` §5).
- 데이터 영향: 일정 표에 열 6개 추가(기본값). 기존 값·ID·암호문·salt 불변. 새 설정 키 `schedule_alarm_seen_at`.
- 제외 범위: 설계 문서 §1 범위 밖 목록.
- 시작 시 사용자 변경: AGENTS.md·docs/RELEASE_HISTORY.md의 9월 미커밋 변경은 `git stash`("9월 미커밋 기록… 보존")와 `output/v41-preserve/september-uncommitted.patch`로 이중 보존. 미추적 9월 작업 기록·`test.png`는 그대로 둔다.

## 완료 조건

- [ ] 구현할 동작과 유지할 계약: 설계 문서 §3~§4
- [ ] 관련 자동 검사: data, full, 100/125/150% quick, PowerShell release(시나리오 4개)
- [ ] 필요한 수동 확인: 설계 문서 §6 수동 항목, v4.0a→v4.1 업그레이드·되돌리기 리허설

## 결정과 진행

- 2026-10-16: 설계 승인 뒤 계획 `docs/superpowers/plans/2026-10-16-schedule-time-repeat-period.md`대로 시작.

이 파일은 진행 기록이다. 영구 지침은 `AGENTS.md`가 지정한 정본 문서에 반영하고
여기에 그 링크를 남긴다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| | 미실행 | | |

## 미해결과 인계

- 남은 문제 / 수동 확인:
- 변경한 정본 문서:
- 다음 행동:
- 배포·커밋·push 여부: 브랜치 커밋만. main 병합·push·Release는 사용자 승인 후
```

- [ ] **Step 3: v17 고정 자료를 만든다** — `tests/fixtures/schema_v17.sql` (v4.0a `migrate()`가 새로 만든 DB의 `sqlite_master`·기본 행을 그대로 옮긴 원문. 한 글자도 고치지 않는다)

```sql
CREATE TABLE app_settings (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL
                );
CREATE TABLE dday_widgets (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    x_pos       INTEGER NOT NULL DEFAULT 100,
                    y_pos       INTEGER NOT NULL DEFAULT 100,
                    is_open     INTEGER NOT NULL DEFAULT 1,
                    color       TEXT DEFAULT '#D6EEFF'
                );
CREATE TABLE focus_sessions (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    widget_id       INTEGER,
                    goal            TEXT NOT NULL DEFAULT '',
                    mode_key        TEXT NOT NULL DEFAULT '25/5',
                    focus_minutes   INTEGER NOT NULL DEFAULT 25,
                    break_minutes   INTEGER NOT NULL DEFAULT 5,
                    started_at      TEXT NOT NULL,
                    ended_at        TEXT NOT NULL,
                    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
                    completed       INTEGER NOT NULL DEFAULT 0,
                    focus_rating    INTEGER,
                    distraction     TEXT NOT NULL DEFAULT '없음',
                    created_at      TEXT NOT NULL
                );
CREATE TABLE focus_widgets (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal          TEXT NOT NULL DEFAULT '',
                    mode_key      TEXT NOT NULL DEFAULT '25/5',
                    focus_minutes INTEGER NOT NULL DEFAULT 25,
                    break_minutes INTEGER NOT NULL DEFAULT 5,
                    x_pos         INTEGER NOT NULL DEFAULT 160,
                    y_pos         INTEGER NOT NULL DEFAULT 160,
                    is_open       INTEGER NOT NULL DEFAULT 1,
                    is_pinned     INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT NOT NULL
                );
CREATE TABLE memos (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    date       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
CREATE TABLE schedules (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    date       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    color      TEXT DEFAULT '#FFD166'
                );
CREATE TABLE shortcuts (
                    id   INTEGER PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    path TEXT NOT NULL DEFAULT ''
                );
CREATE TABLE sticky_notes (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    type      TEXT NOT NULL DEFAULT 'memo',
                    content   TEXT NOT NULL DEFAULT '',
                    x_pos     INTEGER NOT NULL DEFAULT 100,
                    y_pos     INTEGER NOT NULL DEFAULT 100,
                    width     INTEGER NOT NULL DEFAULT 300,
                    height    INTEGER NOT NULL DEFAULT 400,
                    is_open   INTEGER NOT NULL DEFAULT 1,
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    color     TEXT DEFAULT '#FFFDD2'
                , is_deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT NOT NULL DEFAULT '');
INSERT INTO app_settings (key, value) VALUES ('app_font', 'Malgun Gothic');
INSERT INTO app_settings (key, value) VALUES ('app_opacity', '100');
INSERT INTO app_settings (key, value) VALUES ('calendar_position_mode', 'corner');
INSERT INTO app_settings (key, value) VALUES ('calendar_scale', 'compact');
INSERT INTO app_settings (key, value) VALUES ('desktop_mode', '0');
INSERT INTO app_settings (key, value) VALUES ('keep_on_show_desktop', '1');
INSERT INTO app_settings (key, value) VALUES ('privacy_pin', '0000');
INSERT INTO app_settings (key, value) VALUES ('schedule_color_1', '#FFD166');
INSERT INTO app_settings (key, value) VALUES ('schedule_color_2', '#4CC9F0');
INSERT INTO app_settings (key, value) VALUES ('schedule_color_3', '#FF6B6B');
INSERT INTO app_settings (key, value) VALUES ('show_law_search', '1');
INSERT INTO app_settings (key, value) VALUES ('show_sidebar', '0');
INSERT INTO shortcuts (id, name, path) VALUES (1, '', '');
INSERT INTO shortcuts (id, name, path) VALUES (2, '', '');
INSERT INTO shortcuts (id, name, path) VALUES (3, '', '');
INSERT INTO shortcuts (id, name, path) VALUES (4, '', '');
INSERT INTO shortcuts (id, name, path) VALUES (5, '', '');
INSERT INTO shortcuts (id, name, path) VALUES (6, '', '');
```

- [ ] **Step 4: 실패하는 시험을 쓴다** — `tests/test_schedule_rules.py`

```python
"""v4.1 일정 시각·기간·반복·알림 규칙(순수 함수) 회귀. 기대값은 손으로 쓴 리터럴이다."""
from datetime import date, timedelta

import pytest

import schedule_rules as rules
from schedule_rules import ScheduleOptions

START = "2026-10-15"  # 목요일


@pytest.mark.parametrize("text,expected", [
    ("9", "09:00"), ("09", "09:00"), ("14", "14:00"), ("930", "09:30"),
    ("0930", "09:30"), ("1430", "14:30"), ("14:30", "14:30"), (" 7:05 ", "07:05"),
    ("0", "00:00"), ("2359", "23:59"),
])
def test_parse_time_input_accepts_short_forms(text, expected):
    assert rules.parse_time_input(text) == expected


@pytest.mark.parametrize("text", ["", "24", "2400", "1260", "9:5", "14:3", "abc", "12345", "-1", "１４３０"])
def test_parse_time_input_rejects_invalid(text):
    with pytest.raises(ValueError):
        rules.parse_time_input(text)


def test_default_options_mean_all_day_single_day_no_repeat_no_alarm():
    options = ScheduleOptions()
    assert options.is_default
    assert options.to_db_values() == ("", "", "", "", "", None)


def test_from_row_reads_db_values_and_tolerates_bad_stored_values():
    row = {"start_time": "14:00", "end_date": "", "repeat_rule": "weekly",
           "repeat_until": "2026-12-31", "repeat_skip": "2026-10-22,2026-10-29",
           "alarm_before": 10}
    assert ScheduleOptions.from_row(row) == ScheduleOptions(
        start_time="14:00", repeat_rule="weekly", repeat_until="2026-12-31",
        repeat_skip=("2026-10-22", "2026-10-29"), alarm_before=10)
    weird = {"start_time": "9시", "end_date": None, "repeat_rule": "biweekly",
             "repeat_until": None, "repeat_skip": None, "alarm_before": "10"}
    assert ScheduleOptions.from_row(weird) == ScheduleOptions()


@pytest.mark.parametrize("options", [
    ScheduleOptions(),
    ScheduleOptions(start_time="09:30"),
    ScheduleOptions(start_time="09:30", alarm_before=10),
    ScheduleOptions(alarm_before=0),
    ScheduleOptions(alarm_before=1440),
    ScheduleOptions(end_date="2026-10-17"),
    ScheduleOptions(end_date="2027-10-15"),
    ScheduleOptions(repeat_rule="weekly", repeat_until="2026-10-15"),
    ScheduleOptions(repeat_rule="monthly", repeat_skip=("2026-11-15",)),
])
def test_validate_options_accepts_valid(options):
    assert rules.validate_options(START, options) == options


@pytest.mark.parametrize("options,message", [
    (ScheduleOptions(start_time="9:30"), "시작 시각"),
    (ScheduleOptions(start_time="24:00"), "시작 시각"),
    (ScheduleOptions(end_date="2026-10-15"), "기간"),
    (ScheduleOptions(end_date="2026-10-14"), "기간"),
    (ScheduleOptions(end_date="2027-10-16"), "기간"),
    (ScheduleOptions(end_date="2026/10/17"), "날짜"),
    (ScheduleOptions(repeat_rule="biweekly"), "반복"),
    (ScheduleOptions(repeat_rule="weekly", end_date="2026-10-16"), "여러 날"),
    (ScheduleOptions(repeat_until="2026-12-31"), "반복이 아닌"),
    (ScheduleOptions(repeat_skip=("2026-10-22",)), "반복이 아닌"),
    (ScheduleOptions(repeat_rule="daily", repeat_until="2026-10-14"), "반복 끝"),
    (ScheduleOptions(repeat_rule="daily", repeat_skip=("2026-10-14",)), "건너뛴 날"),
    (ScheduleOptions(alarm_before=10), "알림"),
    (ScheduleOptions(start_time="09:00", alarm_before=15), "알림"),
    (ScheduleOptions(start_time="09:00", alarm_before=True), "알림"),
    (ScheduleOptions(start_time="09:00", alarm_before=10.0), "알림"),
    (ScheduleOptions(start_time=None), "형식"),
])
def test_validate_options_rejects_invalid(options, message):
    with pytest.raises(ValueError, match=message):
        rules.validate_options(START, options)


def test_validate_options_sorts_and_dedups_skips_and_caps_count():
    options = ScheduleOptions(repeat_rule="daily", repeat_skip=("2026-10-20", "2026-10-16", "2026-10-20"))
    assert rules.validate_options(START, options).repeat_skip == ("2026-10-16", "2026-10-20")
    many = tuple((date(2027, 1, 1) + timedelta(days=i)).isoformat() for i in range(501))
    with pytest.raises(ValueError, match="건너뛴 날"):
        rules.validate_options(START, ScheduleOptions(repeat_rule="daily", repeat_skip=many))


def test_validate_options_rejects_bad_start_date():
    with pytest.raises(ValueError, match="날짜"):
        rules.validate_options("2026-7-1", ScheduleOptions(start_time="09:00"))
```

- [ ] **Step 5: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_schedule_rules.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'schedule_rules'`

- [ ] **Step 6: 규칙 모듈 1부를 쓴다** — `schedule_rules.py`

```python
"""일정 시각·기간·반복·알림 규칙(v4.1).

Qt·DB에 의존하지 않는 순수 함수만 둔다. 저장(database.py)·가져오기·화면이 모두 이
모듈의 검증과 펼치기를 함께 쓴다. 읽기는 관대하게(규칙에 어긋난 저장값은 기본값처럼),
쓰기는 validate_options로 엄격하게 다룬다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date

REPEAT_RULES = ("", "daily", "weekdays", "weekly", "monthly", "yearly")
TIMED_ALARMS = (0, 10, 30, 60, 1440)
ALLDAY_ALARMS = (0, 1440)
MAX_SPAN_DAYS = 365
MAX_SKIPS = 500
KOREAN_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")  # date.weekday() 순서

_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_TIME_RE = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
_TIME_INPUT_RE = re.compile(r"^([0-9]{1,2})(?::?([0-9]{2}))?$")


def parse_date(value) -> date:
    """'YYYY-MM-DD'만 받는다. 틀리면 ValueError."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ValueError(f"날짜 형식이 올바르지 않습니다: {value!r}")
    return date.fromisoformat(value)


def parse_time_input(text) -> str:
    """'9'·'930'·'1430'·'14:30'을 'HH:MM'으로 바꾼다. 틀리면 ValueError."""
    match = _TIME_INPUT_RE.match((text or "").strip())
    if not match:
        raise ValueError("시각은 0930·14:30처럼 입력합니다.")
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) is not None else 0
    if hour > 23 or minute > 59:
        raise ValueError("시각은 00:00부터 23:59까지입니다.")
    return f"{hour:02d}:{minute:02d}"


@dataclass(frozen=True)
class ScheduleOptions:
    """일정 한 건의 세부 설정. 기본값은 '하루 종일·하루·반복 없음·알림 없음'이다."""

    start_time: str = ""
    end_date: str = ""
    repeat_rule: str = ""
    repeat_until: str = ""
    repeat_skip: tuple[str, ...] = ()
    alarm_before: int | None = None

    @property
    def is_default(self) -> bool:
        return self == ScheduleOptions()

    @classmethod
    def from_row(cls, row) -> "ScheduleOptions":
        """DB 행(sqlite3.Row·dict)을 관대하게 읽는다. 규칙에 어긋난 값은 기본값처럼 다룬다."""
        def text(name: str) -> str:
            value = row[name]
            return value if isinstance(value, str) else ""

        start_time = text("start_time")
        rule = text("repeat_rule")
        alarm = row["alarm_before"]
        return cls(
            start_time=start_time if _TIME_RE.match(start_time) else "",
            end_date=text("end_date"),
            repeat_rule=rule if rule in REPEAT_RULES else "",
            repeat_until=text("repeat_until"),
            repeat_skip=tuple(day for day in text("repeat_skip").split(",") if day),
            alarm_before=alarm if type(alarm) is int else None,
        )

    def to_db_values(self) -> tuple:
        """(start_time, end_date, repeat_rule, repeat_until, repeat_skip, alarm_before) 순서."""
        return (self.start_time, self.end_date, self.repeat_rule,
                self.repeat_until, ",".join(self.repeat_skip), self.alarm_before)


def validate_options(start: str, options: ScheduleOptions) -> ScheduleOptions:
    """세부 설정이 규칙에 맞는지 검사하고 정규화(건너뛴 날 정렬·중복 제거)해 돌려준다."""
    for name in ("start_time", "end_date", "repeat_rule", "repeat_until"):
        if not isinstance(getattr(options, name), str):
            raise ValueError("세부 설정 형식이 올바르지 않습니다.")
    if not isinstance(options.repeat_skip, tuple) or not all(
            isinstance(day, str) for day in options.repeat_skip):
        raise ValueError("세부 설정 형식이 올바르지 않습니다.")
    start_day = parse_date(start)
    if options.start_time and not _TIME_RE.match(options.start_time):
        raise ValueError("시작 시각 형식이 올바르지 않습니다.")
    if options.repeat_rule not in REPEAT_RULES:
        raise ValueError("지원하지 않는 반복입니다.")
    if options.end_date:
        end_day = parse_date(options.end_date)
        if end_day <= start_day or (end_day - start_day).days > MAX_SPAN_DAYS:
            raise ValueError("기간 끝 날짜가 올바르지 않습니다.")
        if options.repeat_rule:
            raise ValueError("여러 날 일정은 반복할 수 없습니다.")
    if not options.repeat_rule and (options.repeat_until or options.repeat_skip):
        raise ValueError("반복이 아닌 일정에는 끝 날짜·건너뛴 날을 둘 수 없습니다.")
    if options.repeat_until and parse_date(options.repeat_until) < start_day:
        raise ValueError("반복 끝 날짜가 시작보다 앞섭니다.")
    skips = tuple(sorted(set(options.repeat_skip)))
    if len(skips) > MAX_SKIPS:
        raise ValueError("건너뛴 날이 너무 많습니다.")
    for day in skips:
        if parse_date(day) < start_day:
            raise ValueError("건너뛴 날이 시작보다 앞섭니다.")
    if options.alarm_before is not None:
        allowed = TIMED_ALARMS if options.start_time else ALLDAY_ALARMS
        if type(options.alarm_before) is not int or options.alarm_before not in allowed:
            raise ValueError("지원하지 않는 알림입니다.")
    return replace(options, repeat_skip=skips)
```

- [ ] **Step 7: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_schedule_rules.py -q`
Expected: PASS (전부)

- [ ] **Step 8: 커밋**

```bash
git add schedule_rules.py tests/test_schedule_rules.py tests/fixtures/schema_v17.sql docs/work/2026-10-16-v4.1-schedule-time-repeat-period.md
git commit -m "feat: v4.1 일정 세부 설정 값과 검증 규칙(순수 모듈)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 2: 펼치기·알림 시각·정렬·옵션 변환

**Files:**
- Modify: `schedule_rules.py` (import 줄 교체 + 함수 추가)
- Test: `tests/test_schedule_rules.py` (시험 추가)

**Interfaces:**
- Consumes: Task 1의 `ScheduleOptions`, `parse_date`
- Produces
  - 펼치기·정렬: `add_months(day, months)->date`, `occurrence_dates(start, options, first:date, last:date)->list[date]`, `occurs_on(start, options, day:date)->bool`, `occurrence_sort_key(shows_time:bool, start_time:str, schedule_id:int)->tuple`
  - 알림: `ALLDAY_ALARM_TIME=time(9,0)`, `alarm_base(day, options)->datetime`, `alarm_times(start, options, after:datetime, until:datetime)->list[(date, datetime)]`(after < 알림 ≤ until)
  - 알림 한 건: `AlarmItem`(동결 dataclass)
    - 필드: `schedule_id:int`, `occurrence_date:str`, `due:datetime`, `content:str`, `color:str`, `start_time:str`, `decryption_failed:bool=False`
    - 속성: `key -> (schedule_id, occurrence_date, due)`
  - 옵션 변환: `with_start_time(options, start_time)`, `with_repeat(options, start, rule)`, `clear_part(options, start, kind)`(kind: `"time"|"alarm"|"period"|"repeat"`), `rebase_options(options, old_start, new_start)`

- [ ] **Step 1: 실패하는 시험을 추가한다** — `tests/test_schedule_rules.py` 끝에 붙인다

```python
from datetime import datetime

D = date.fromisoformat


def days(start, options, first, last):
    return [d.isoformat() for d in rules.occurrence_dates(start, options, D(first), D(last))]


def test_single_day_occurs_only_on_its_date():
    assert days("2026-10-15", ScheduleOptions(), "2026-10-01", "2026-10-31") == ["2026-10-15"]
    assert days("2026-10-15", ScheduleOptions(), "2026-10-16", "2026-10-31") == []


def test_period_covers_each_day_inside_the_range():
    options = ScheduleOptions(end_date="2026-11-02")
    assert days("2026-10-30", options, "2026-10-01", "2026-10-31") == ["2026-10-30", "2026-10-31"]
    assert days("2026-10-30", options, "2026-11-01", "2026-11-30") == ["2026-11-01", "2026-11-02"]


def test_daily_and_weekdays():
    assert days("2026-10-15", ScheduleOptions(repeat_rule="daily"), "2026-10-13", "2026-10-18") == [
        "2026-10-15", "2026-10-16", "2026-10-17", "2026-10-18"]
    # 2026-10-17은 토요일: 평일 반복은 시작일이 주말이면 그 날을 건너뛴다.
    assert days("2026-10-17", ScheduleOptions(repeat_rule="weekdays"), "2026-10-17", "2026-10-23") == [
        "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]


def test_weekly_keeps_the_start_weekday():
    assert days("2026-10-05", ScheduleOptions(repeat_rule="weekly"), "2026-10-01", "2026-10-31") == [
        "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]


def test_monthly_on_31_uses_the_last_day_of_short_months():
    assert days("2026-01-31", ScheduleOptions(repeat_rule="monthly"), "2026-01-01", "2026-05-31") == [
        "2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31"]


def test_yearly_leap_day_falls_back_to_feb_28():
    assert days("2024-02-29", ScheduleOptions(repeat_rule="yearly"), "2024-01-01", "2028-12-31") == [
        "2024-02-29", "2025-02-28", "2026-02-28", "2027-02-28", "2028-02-29"]


def test_until_is_inclusive_and_skips_are_removed():
    options = ScheduleOptions(repeat_rule="weekly", repeat_until="2026-10-26", repeat_skip=("2026-10-12",))
    assert days("2026-10-05", options, "2026-10-01", "2026-12-31") == ["2026-10-05", "2026-10-19", "2026-10-26"]


def test_nothing_before_the_start_date_and_empty_range():
    assert days("2026-10-15", ScheduleOptions(repeat_rule="daily"), "2026-10-01", "2026-10-14") == []
    assert days("2026-10-15", ScheduleOptions(repeat_rule="daily"), "2026-10-20", "2026-10-19") == []


def test_occurs_on():
    options = ScheduleOptions(repeat_rule="weekly")
    assert rules.occurs_on("2026-10-05", options, D("2026-10-19"))
    assert not rules.occurs_on("2026-10-05", options, D("2026-10-20"))


def test_add_months_clamps_to_month_end():
    assert rules.add_months(D("2026-01-31"), 1) == D("2026-02-28")
    assert rules.add_months(D("2026-12-15"), 1) == D("2027-01-15")
    assert rules.add_months(D("2026-03-31"), -1) == D("2026-02-28")


def test_occurrence_sort_key_puts_all_day_first_then_time():
    items = [(True, "16:00", 3), (False, "", 5), (True, "09:00", 9), (False, "", 2), (True, "09:00", 4)]
    ordered = sorted(items, key=lambda item: rules.occurrence_sort_key(*item))
    assert ordered == [(False, "", 2), (False, "", 5), (True, "09:00", 4), (True, "09:00", 9), (True, "16:00", 3)]


def test_alarm_times_for_timed_all_day_period_and_repeat():
    after, until = datetime(2026, 10, 14, 0, 0), datetime(2026, 10, 16, 23, 59)
    timed = ScheduleOptions(start_time="15:00", alarm_before=10)
    assert rules.alarm_times("2026-10-15", timed, after, until) == [
        (D("2026-10-15"), datetime(2026, 10, 15, 14, 50))]
    eve = ScheduleOptions(alarm_before=1440)
    assert rules.alarm_times("2026-10-16", eve, after, until) == [
        (D("2026-10-16"), datetime(2026, 10, 15, 9, 0))]
    period = ScheduleOptions(end_date="2026-10-17", alarm_before=0)
    assert rules.alarm_times("2026-10-15", period, after, until) == [
        (D("2026-10-15"), datetime(2026, 10, 15, 9, 0))]
    daily = ScheduleOptions(start_time="10:00", repeat_rule="daily", repeat_skip=("2026-10-15",), alarm_before=0)
    assert rules.alarm_times("2026-10-01", daily, after, until) == [
        (D("2026-10-14"), datetime(2026, 10, 14, 10, 0)),
        (D("2026-10-16"), datetime(2026, 10, 16, 10, 0))]


def test_alarm_window_is_exclusive_after_inclusive_until():
    options = ScheduleOptions(start_time="15:00", alarm_before=0)
    due = datetime(2026, 10, 15, 15, 0)
    assert rules.alarm_times("2026-10-15", options, due, due.replace(hour=16)) == []
    assert rules.alarm_times("2026-10-15", options, due.replace(hour=14), due) == [(D("2026-10-15"), due)]
    assert rules.alarm_times("2026-10-15", ScheduleOptions(start_time="15:00"), due.replace(hour=0), due) == []


def test_alarm_item_key():
    item = rules.AlarmItem(7, "2026-10-15", datetime(2026, 10, 15, 14, 50), "회의", "#4CC9F0", "15:00")
    assert item.key == (7, "2026-10-15", datetime(2026, 10, 15, 14, 50))
    assert item.decryption_failed is False


def test_with_start_time_keeps_only_alarms_valid_in_both_modes():
    assert rules.with_start_time(ScheduleOptions(start_time="09:00", alarm_before=10), "").alarm_before is None
    assert rules.with_start_time(ScheduleOptions(start_time="09:00", alarm_before=1440), "").alarm_before == 1440
    assert rules.with_start_time(ScheduleOptions(alarm_before=0), "13:00") == ScheduleOptions(
        start_time="13:00", alarm_before=0)
    # 시각만 바꾸면(시각→시각) 알림을 그대로 둔다.
    assert rules.with_start_time(ScheduleOptions(start_time="09:00", alarm_before=10), "10:30") == (
        ScheduleOptions(start_time="10:30", alarm_before=10))


def test_with_repeat_clears_or_resets_dependent_fields():
    base = ScheduleOptions(repeat_rule="weekly", repeat_until="2026-12-31", repeat_skip=("2026-10-22",))
    assert rules.with_repeat(base, "2026-10-15", "") == ScheduleOptions()
    assert rules.with_repeat(base, "2026-10-15", "monthly") == ScheduleOptions(
        repeat_rule="monthly", repeat_until="2026-12-31")
    assert rules.with_repeat(base, "2026-10-15", "weekly") is base
    assert rules.with_repeat(ScheduleOptions(end_date="2026-10-17"), "2026-10-15", "daily") == ScheduleOptions(
        repeat_rule="daily")


def test_clear_part():
    full = ScheduleOptions(start_time="09:00", alarm_before=10)
    assert rules.clear_part(full, START, "time") == ScheduleOptions()
    assert rules.clear_part(full, START, "alarm") == ScheduleOptions(start_time="09:00")
    assert rules.clear_part(ScheduleOptions(end_date="2026-10-17"), START, "period") == ScheduleOptions()
    assert rules.clear_part(ScheduleOptions(repeat_rule="daily", repeat_until="2026-11-01"), START, "repeat") == (
        ScheduleOptions())
    with pytest.raises(ValueError):
        rules.clear_part(full, START, "colour")


def test_rebase_options_keeps_period_length_and_drops_stale_until():
    assert rules.rebase_options(ScheduleOptions(end_date="2026-10-17"), START, "2026-10-20").end_date == "2026-10-22"
    repeat = ScheduleOptions(repeat_rule="weekly", repeat_until="2026-10-18", repeat_skip=("2026-10-22",))
    assert rules.rebase_options(repeat, START, "2026-10-25") == ScheduleOptions(repeat_rule="weekly")
    assert rules.rebase_options(repeat, START, "2026-10-16") == ScheduleOptions(
        repeat_rule="weekly", repeat_until="2026-10-18")
    assert rules.rebase_options(repeat, START, START) is repeat
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_schedule_rules.py -q`
Expected: FAIL — `AttributeError: module 'schedule_rules' has no attribute 'occurrence_dates'`

- [ ] **Step 3: import 줄을 바꾸고 함수를 더한다** — `schedule_rules.py`

import 줄 `from datetime import date`를 아래로 바꾼다.

```python
import calendar
from datetime import date, datetime, time, timedelta
```

파일 끝에 붙인다.

```python
ALLDAY_ALARM_TIME = time(9, 0)


def add_months(day: date, months: int) -> date:
    """달 단위로 옮긴다. 없는 날짜는 그 달의 마지막 날로 맞춘다."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def occurrence_dates(start: str, options: ScheduleOptions, first: date, last: date) -> list[date]:
    """[first, last] 안에서 일정이 나타나는 날짜(오름차순)."""
    if last < first:
        return []
    begin = parse_date(start)
    if options.end_date:
        end = parse_date(options.end_date)
        low, high = max(begin, first), min(end, last)
        return [low + timedelta(days=i) for i in range((high - low).days + 1)] if low <= high else []
    rule = options.repeat_rule
    if not rule:
        return [begin] if first <= begin <= last else []
    stop = min(last, parse_date(options.repeat_until)) if options.repeat_until else last
    low = max(begin, first)
    if low > stop:
        return []
    result: list[date] = []
    if rule in ("daily", "weekdays"):
        day = low
        while day <= stop:
            if rule == "daily" or day.weekday() < 5:
                result.append(day)
            day += timedelta(days=1)
    elif rule == "weekly":
        day = low + timedelta(days=(begin.weekday() - low.weekday()) % 7)
        while day <= stop:
            result.append(day)
            day += timedelta(days=7)
    elif rule == "monthly":
        year, month = low.year, low.month
        while True:
            day = _clamped(year, month, begin.day)
            if day > stop:
                break
            if day >= low:
                result.append(day)
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    elif rule == "yearly":
        year = low.year
        while True:
            day = _clamped(year, begin.month, begin.day)
            if day > stop:
                break
            if day >= low:
                result.append(day)
            year += 1
    skips = set(options.repeat_skip)
    return [day for day in result if day.isoformat() not in skips]


def occurs_on(start: str, options: ScheduleOptions, day: date) -> bool:
    return bool(occurrence_dates(start, options, day, day))


def occurrence_sort_key(shows_time: bool, start_time: str, schedule_id: int) -> tuple:
    """하루 목록 순서: 시각 없이 보이는 것(하루 종일·기간 둘째 날 이후) 먼저 ID 순, 그다음 시각·ID 순."""
    return (1, start_time, schedule_id) if shows_time else (0, "", schedule_id)


def alarm_base(day: date, options: ScheduleOptions) -> datetime:
    """알림 기준 시각: 그 날의 시작 시각(하루 종일이면 09:00)."""
    if options.start_time:
        hour, minute = (int(part) for part in options.start_time.split(":"))
        return datetime.combine(day, time(hour, minute))
    return datetime.combine(day, ALLDAY_ALARM_TIME)


def alarm_times(start: str, options: ScheduleOptions, after: datetime, until: datetime) -> list[tuple[date, datetime]]:
    """after < 알림 ≤ until 인 (날짜, 알림 시각) 목록. 기간 일정은 첫날만 알린다."""
    if options.alarm_before is None or until <= after:
        return []
    shift = timedelta(minutes=options.alarm_before)
    first = (after + shift).date() - timedelta(days=1)
    last = (until + shift).date() + timedelta(days=1)
    days_found = occurrence_dates(start, options, first, last)
    if options.end_date:
        begin = parse_date(start)
        days_found = [day for day in days_found if day == begin]
    result = []
    for day in days_found:
        due = alarm_base(day, options) - shift
        if after < due <= until:
            result.append((day, due))
    return result


@dataclass(frozen=True)
class AlarmItem:
    """알릴 일정 한 건(어느 날짜의 어느 시각에 울릴지)."""

    schedule_id: int
    occurrence_date: str
    due: datetime
    content: str
    color: str
    start_time: str
    decryption_failed: bool = False

    @property
    def key(self) -> tuple:
        return (self.schedule_id, self.occurrence_date, self.due)


def with_start_time(options: ScheduleOptions, start_time: str) -> ScheduleOptions:
    """시각을 바꾼다. 하루 종일↔시각으로 방식이 바뀔 때만 두 방식에 모두 있는 알림(0·1440)을 남긴다."""
    if bool(start_time) == bool(options.start_time):
        return replace(options, start_time=start_time)
    alarm = options.alarm_before if options.alarm_before in (None, 0, 1440) else None
    return replace(options, start_time=start_time, alarm_before=alarm)


def with_repeat(options: ScheduleOptions, start: str, rule: str) -> ScheduleOptions:
    """반복을 바꾼다. 끄면 끝 날짜·건너뛴 날도 지우고, 종류를 바꾸면 건너뛴 날을 비운다."""
    if rule == options.repeat_rule:
        return options
    if not rule:
        return replace(options, repeat_rule="", repeat_until="", repeat_skip=())
    until = options.repeat_until
    if until and parse_date(until) < parse_date(start):
        until = ""
    return replace(options, repeat_rule=rule, repeat_until=until, repeat_skip=(), end_date="")


def clear_part(options: ScheduleOptions, start: str, kind: str) -> ScheduleOptions:
    """알약의 ×: 그 항목만 지운다(시각을 지우면 알림도 지운다)."""
    if kind == "time":
        return replace(options, start_time="", alarm_before=None)
    if kind == "alarm":
        return replace(options, alarm_before=None)
    if kind == "period":
        return replace(options, end_date="")
    if kind == "repeat":
        return with_repeat(options, start, "")
    raise ValueError(f"알 수 없는 항목입니다: {kind}")


def rebase_options(options: ScheduleOptions, old_start: str, new_start: str) -> ScheduleOptions:
    """고른 날짜가 바뀔 때 보류 중 값을 새 날짜 기준으로 옮긴다(기간 길이 유지, 지난 끝 날짜 제거)."""
    if old_start == new_start:
        return options
    end_date = ""
    if options.end_date:
        length = parse_date(options.end_date) - parse_date(old_start)
        end_date = (parse_date(new_start) + length).isoformat()
    until = options.repeat_until
    if until and parse_date(until) < parse_date(new_start):
        until = ""
    return replace(options, end_date=end_date, repeat_until=until, repeat_skip=())
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_schedule_rules.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add schedule_rules.py tests/test_schedule_rules.py
git commit -m "feat: 일정 반복·기간 펼치기와 알림 시각 계산

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 3: 막대 조각·차선과 한국어 문구

**Files:**
- Modify: `schedule_rules.py` (import 줄에 `math` 추가 + 함수 추가)
- Test: `tests/test_schedule_rules.py` (시험 추가)

**Interfaces:**
- Consumes: Task 1·2의 함수들
- Produces
  - 막대
    - `SpanSegment`(동결 dataclass): `key:int`, `row:int`, `first_col:int`, `last_col:int`, `starts:bool`, `ends:bool`, `lane:int=0`
    - `week_segments(weeks:list[list[str]], spans:dict[int,(str,str)])->list[SpanSegment]`
    - `assign_lanes(segments)->list[SpanSegment]`
  - 문구
    - `repeat_caption(start, rule, *, note=True)`, `repeat_pill(start, options)`, `alarm_label(options, *, short=False)`, `time_pill(options)`
    - `span_days(start, options)`, `span_pill(start, options)`, `range_text(start, end)`, `korean_date(day)`, `period_caption(start, end)`
    - `options_summary(start, options)`, `search_suffix(start, options)`, `alarm_subtitle(start_time, day:date, now:datetime)`
    - `until_caption(until)`('12월 31일(목)까지'), `detail_lines(start, options)->list[str]`(목록 툴팁 줄)

- [ ] **Step 1: 실패하는 시험을 추가한다** — `tests/test_schedule_rules.py` 끝에 붙인다

```python
OCT_WEEKS = [
    ["", "", "", "", "2026-10-01", "2026-10-02", "2026-10-03"],
    ["2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-10"],
    ["2026-10-11", "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-17"],
]


def test_week_segments_split_at_week_and_month_edges_and_assign_lanes():
    spans = {
        7: ("2026-09-29", "2026-10-02"),   # 지난달에서 이어짐 → 왼쪽 끝이 각짐
        8: ("2026-10-08", "2026-10-12"),   # 주를 넘김 → 두 조각
        9: ("2026-10-09", "2026-10-10"),   # 8과 겹침 → 둘째 차선
    }
    assert rules.week_segments(OCT_WEEKS, spans) == [
        rules.SpanSegment(7, 0, 4, 5, False, True, 0),
        rules.SpanSegment(8, 1, 4, 6, True, False, 0),
        rules.SpanSegment(9, 1, 5, 6, True, True, 1),
        rules.SpanSegment(8, 2, 0, 1, False, True, 0),
    ]


def test_lanes_put_longer_span_first_when_starting_together():
    spans = {1: ("2026-10-11", "2026-10-13"), 2: ("2026-10-11", "2026-10-16")}
    segments = rules.week_segments(OCT_WEEKS, spans)
    assert [(s.key, s.lane) for s in segments] == [(2, 0), (1, 1)]


def test_korean_captions_and_pills():
    assert rules.repeat_caption("2026-10-15", "weekly") == "매주 목요일"
    assert rules.repeat_caption("2026-10-31", "monthly") == "매월 31일 (없는 달은 마지막 날)"
    assert rules.repeat_caption("2026-10-31", "monthly", note=False) == "매월 31일"
    assert rules.repeat_caption("2026-10-15", "monthly") == "매월 15일"
    assert rules.repeat_caption("2028-02-29", "yearly") == "매년 2월 29일 (평년은 2월 28일)"
    assert rules.repeat_caption("2026-10-15", "weekdays") == "평일(월~금)"
    assert rules.repeat_caption("2026-10-15", "daily") == "매일"
    assert rules.repeat_pill("2026-10-15", ScheduleOptions(repeat_rule="weekly", repeat_until="2026-12-31")) == (
        "매주 목 · ~12.31")
    assert rules.repeat_pill("2026-10-15", ScheduleOptions(repeat_rule="yearly")) == "매년 10.15"
    assert rules.time_pill(ScheduleOptions(start_time="15:00", alarm_before=10)) == "15:00 · 10분 전"
    assert rules.time_pill(ScheduleOptions(start_time="15:00")) == "15:00"
    assert rules.alarm_label(ScheduleOptions(alarm_before=0), short=True) == "당일 9시"
    assert rules.alarm_label(ScheduleOptions(alarm_before=1440)) == "하루 전 오전 9시"
    assert rules.alarm_label(ScheduleOptions(start_time="10:00", alarm_before=60)) == "1시간 전"
    assert rules.alarm_label(ScheduleOptions()) == ""
    assert rules.span_pill("2026-10-21", ScheduleOptions(end_date="2026-10-23")) == "~10.23 · 3일"
    assert rules.range_text("2026-10-21", "2026-10-23") == "10.21~10.23"
    assert rules.range_text("2026-12-30", "2027-01-02") == "26.12.30~27.01.02"
    assert rules.korean_date(D("2026-10-15")) == "10월 15일 (목)"
    assert rules.period_caption("2026-10-21", "2026-10-23") == "10월 21일(수) ~ 23일(금) · 3일"
    assert rules.period_caption("2026-10-30", "2026-11-02") == "10월 30일(금) ~ 11월 2일(월) · 4일"


def test_options_summary_and_search_suffix():
    weekly = ScheduleOptions(start_time="10:00", repeat_rule="weekly", alarm_before=10)
    assert rules.options_summary("2026-10-05", weekly) == "10:00 · 10분 전 · 매주 월요일"
    period = ScheduleOptions(end_date="2026-10-23", alarm_before=0)
    assert rules.options_summary("2026-10-21", period) == "알림 당일 오전 9시 · 10.21~10.23"
    until = ScheduleOptions(repeat_rule="daily", repeat_until="2026-12-31")
    assert rules.options_summary("2026-10-15", until) == "매일 · 12월 31일까지"
    assert rules.options_summary("2026-10-15", ScheduleOptions()) == ""
    assert rules.search_suffix("2026-10-05", ScheduleOptions(repeat_rule="weekly")) == " (매주 월요일 반복)"
    assert rules.search_suffix("2026-10-31", ScheduleOptions(repeat_rule="monthly")) == " (매월 31일 반복)"
    assert rules.search_suffix("2026-10-21", ScheduleOptions(end_date="2026-10-23")) == " (~10.23)"
    assert rules.search_suffix("2026-10-21", ScheduleOptions()) == ""
    assert rules.search_suffix("2026-7-1", ScheduleOptions(repeat_rule="weekly")) == ""


def test_alarm_subtitle():
    now = datetime(2026, 10, 15, 14, 50)
    assert rules.alarm_subtitle("15:00", D("2026-10-15"), now) == "10분 뒤 시작 · 10월 15일 (목)"
    assert rules.alarm_subtitle("15:00", D("2026-10-15"), datetime(2026, 10, 15, 15, 0)) == "지금 시작 · 10월 15일 (목)"
    assert rules.alarm_subtitle("15:00", D("2026-10-15"), datetime(2026, 10, 15, 15, 3)) == (
        "15:00에 시작함 · 10월 15일 (목)")
    assert rules.alarm_subtitle("15:00", D("2026-10-15"), datetime(2026, 10, 15, 13, 0)) == "15:00 시작 · 10월 15일 (목)"
    assert rules.alarm_subtitle("09:00", D("2026-10-16"), now) == "내일 09:00 시작 · 10월 16일 (금)"
    assert rules.alarm_subtitle("", D("2026-10-15"), now) == "오늘 하루 종일 · 10월 15일 (목)"
    assert rules.alarm_subtitle("", D("2026-10-16"), now) == "내일 하루 종일 · 10월 16일 (금)"
    assert rules.alarm_subtitle("", D("2026-10-14"), now) == "하루 종일 · 10월 14일 (수)"


def test_until_caption_detail_lines_and_unknown_rule_suffix():
    assert rules.until_caption("2026-12-31") == "12월 31일(목)까지"
    weekly = ScheduleOptions(start_time="10:00", repeat_rule="weekly", repeat_until="2026-12-28", alarm_before=10)
    assert rules.detail_lines("2026-10-05", weekly) == [
        "시작: 10:00", "매주 월요일 반복 · 끝: 12월 28일(월)까지", "알림: 10분 전"]
    period = ScheduleOptions(end_date="2026-10-23", alarm_before=0)
    assert rules.detail_lines("2026-10-21", period) == ["기간: 10.21~10.23 · 3일", "알림: 당일 오전 9시"]
    assert rules.detail_lines("2026-10-21", ScheduleOptions(repeat_rule="daily")) == ["매일 반복 · 끝: 계속"]
    assert rules.detail_lines("2026-10-21", ScheduleOptions()) == []
    assert rules.search_suffix("2026-10-05", ScheduleOptions(repeat_rule="biweekly")) == ""
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_schedule_rules.py -q`
Expected: FAIL — `AttributeError: module 'schedule_rules' has no attribute 'week_segments'`

- [ ] **Step 3: 구현한다** — `schedule_rules.py`

import 줄에 `import math`를 더한다(`import calendar` 다음 줄).

파일 끝에 붙인다.

```python
@dataclass(frozen=True)
class SpanSegment:
    """한 주 줄 안의 기간 막대 조각."""

    key: int          # 일정 ID
    row: int          # 달력의 주 번호(0부터)
    first_col: int    # 0=일요일
    last_col: int
    starts: bool      # 이 조각에서 일정이 시작하는가(왼쪽 둥근 끝)
    ends: bool        # 이 조각에서 일정이 끝나는가(오른쪽 둥근 끝)
    lane: int = 0


def week_segments(weeks: list[list[str]], spans: dict[int, tuple[str, str]]) -> list[SpanSegment]:
    """weeks: 주마다 7칸의 'YYYY-MM-DD' 또는 ''(빈칸). spans: 일정 ID → (시작, 끝)."""
    segments = []
    for row, days_in_week in enumerate(weeks):
        for key, (span_start, span_end) in spans.items():
            cols = [col for col, day in enumerate(days_in_week) if day and span_start <= day <= span_end]
            if not cols:
                continue
            first_col, last_col = cols[0], cols[-1]
            segments.append(SpanSegment(
                key, row, first_col, last_col,
                days_in_week[first_col] == span_start, days_in_week[last_col] == span_end,
            ))
    return assign_lanes(segments)


def assign_lanes(segments: list[SpanSegment]) -> list[SpanSegment]:
    """같은 주에서 시작 열·긴 순·ID 순으로 겹치지 않는 가장 위 차선을 준다."""
    placed = []
    taken: dict[int, list[list[tuple[int, int]]]] = {}
    ordered = sorted(segments, key=lambda s: (s.row, s.first_col, -(s.last_col - s.first_col), s.key))
    for segment in ordered:
        lanes = taken.setdefault(segment.row, [])
        lane = 0
        while lane < len(lanes) and any(
                not (segment.last_col < a or segment.first_col > b) for a, b in lanes[lane]):
            lane += 1
        if lane == len(lanes):
            lanes.append([])
        lanes[lane].append((segment.first_col, segment.last_col))
        placed.append(replace(segment, lane=lane))
    return placed


def korean_date(day: date) -> str:
    return f"{day.month}월 {day.day}일 ({KOREAN_WEEKDAYS[day.weekday()]})"


def repeat_caption(start: str, rule: str, *, note: bool = True) -> str:
    day = parse_date(start)
    if rule == "daily":
        return "매일"
    if rule == "weekdays":
        return "평일(월~금)"
    if rule == "weekly":
        return f"매주 {KOREAN_WEEKDAYS[day.weekday()]}요일"
    if rule == "monthly":
        extra = " (없는 달은 마지막 날)" if note and day.day >= 29 else ""
        return f"매월 {day.day}일{extra}"
    if rule == "yearly":
        extra = " (평년은 2월 28일)" if note and (day.month, day.day) == (2, 29) else ""
        return f"매년 {day.month}월 {day.day}일{extra}"
    return ""


def repeat_pill(start: str, options: ScheduleOptions) -> str:
    day = parse_date(start)
    short = {
        "daily": "매일", "weekdays": "평일",
        "weekly": f"매주 {KOREAN_WEEKDAYS[day.weekday()]}",
        "monthly": f"매월 {day.day}일", "yearly": f"매년 {day.month}.{day.day}",
    }.get(options.repeat_rule, "")
    if short and options.repeat_until:
        until = parse_date(options.repeat_until)
        short += f" · ~{until.month:02d}.{until.day:02d}"
    return short


def alarm_label(options: ScheduleOptions, *, short: bool = False) -> str:
    if options.alarm_before is None:
        return ""
    if options.start_time:
        return {0: "정시", 10: "10분 전", 30: "30분 전", 60: "1시간 전", 1440: "하루 전"}[options.alarm_before]
    if short:
        return {0: "당일 9시", 1440: "하루 전 9시"}[options.alarm_before]
    return {0: "당일 오전 9시", 1440: "하루 전 오전 9시"}[options.alarm_before]


def time_pill(options: ScheduleOptions) -> str:
    if not options.start_time:
        return ""
    alarm = alarm_label(options)
    return f"{options.start_time} · {alarm}" if alarm else options.start_time


def span_days(start: str, options: ScheduleOptions) -> int:
    if not options.end_date:
        return 1
    return (parse_date(options.end_date) - parse_date(start)).days + 1


def span_pill(start: str, options: ScheduleOptions) -> str:
    if not options.end_date:
        return ""
    end = parse_date(options.end_date)
    return f"~{end.month:02d}.{end.day:02d} · {span_days(start, options)}일"


def range_text(start: str, end: str) -> str:
    a, b = parse_date(start), parse_date(end)
    if a.year == b.year:
        return f"{a.month:02d}.{a.day:02d}~{b.month:02d}.{b.day:02d}"
    return f"{a.year % 100:02d}.{a.month:02d}.{a.day:02d}~{b.year % 100:02d}.{b.month:02d}.{b.day:02d}"


def period_caption(start: str, end: str) -> str:
    a, b = parse_date(start), parse_date(end)
    left = f"{a.month}월 {a.day}일({KOREAN_WEEKDAYS[a.weekday()]})"
    if (a.year, a.month) == (b.year, b.month):
        right = f"{b.day}일({KOREAN_WEEKDAYS[b.weekday()]})"
    else:
        right = f"{b.month}월 {b.day}일({KOREAN_WEEKDAYS[b.weekday()]})"
    return f"{left} ~ {right} · {(b - a).days + 1}일"


def options_summary(start: str, options: ScheduleOptions) -> str:
    """편집 요약·툴팁용 한 줄. 예: '10:00 · 10분 전 · 매주 월요일'."""
    parts = []
    if options.start_time:
        parts.append(options.start_time)
    alarm = alarm_label(options)
    if alarm:
        parts.append(alarm if options.start_time else f"알림 {alarm}")
    if options.end_date:
        parts.append(range_text(start, options.end_date))
    if options.repeat_rule:
        parts.append(repeat_caption(start, options.repeat_rule))
        if options.repeat_until:
            until = parse_date(options.repeat_until)
            parts.append(f"{until.month}월 {until.day}일까지")
    return " · ".join(parts)


def search_suffix(start: str, options: ScheduleOptions) -> str:
    """검색 결과 본문 칸 끝의 표시용 꼬리(저장값은 바꾸지 않는다)."""
    try:
        if options.repeat_rule:
            caption = repeat_caption(start, options.repeat_rule, note=False)
            return f" ({caption} 반복)" if caption else ""
        if options.end_date:
            end = parse_date(options.end_date)
            return f" (~{end.month:02d}.{end.day:02d})"
    except ValueError:
        return ""
    return ""


def alarm_subtitle(start_time: str, day: date, now: datetime) -> str:
    """알림 카드 설명 줄. 예: '10분 뒤 시작 · 10월 15일 (목)'."""
    if start_time:
        hour, minute = (int(part) for part in start_time.split(":"))
        base = datetime.combine(day, time(hour, minute))
        minutes = math.ceil((base - now).total_seconds() / 60)
        if minutes < 0:
            head = f"{start_time}에 시작함"
        elif minutes == 0:
            head = "지금 시작"
        elif minutes < 60:
            head = f"{minutes}분 뒤 시작"
        elif day == now.date() + timedelta(days=1):
            head = f"내일 {start_time} 시작"
        else:
            head = f"{start_time} 시작"
    elif day == now.date():
        head = "오늘 하루 종일"
    elif day == now.date() + timedelta(days=1):
        head = "내일 하루 종일"
    else:
        head = "하루 종일"
    return f"{head} · {korean_date(day)}"


def until_caption(until: str) -> str:
    """반복 끝 설명. 예: '12월 31일(목)까지'."""
    day = parse_date(until)
    return f"{day.month}월 {day.day}일({KOREAN_WEEKDAYS[day.weekday()]})까지"


def detail_lines(start: str, options: ScheduleOptions) -> list[str]:
    """목록 툴팁에서 본문 다음 줄로 붙일 설명. 기본값이면 빈 목록."""
    lines = []
    if options.start_time:
        lines.append(f"시작: {options.start_time}")
    if options.end_date:
        lines.append(f"기간: {range_text(start, options.end_date)} · {span_days(start, options)}일")
    if options.repeat_rule:
        end = until_caption(options.repeat_until) if options.repeat_until else "계속"
        lines.append(f"{repeat_caption(start, options.repeat_rule)} 반복 · 끝: {end}")
    alarm = alarm_label(options)
    if alarm:
        lines.append(f"알림: {alarm}")
    return lines
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_schedule_rules.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add schedule_rules.py tests/test_schedule_rules.py
git commit -m "feat: 기간 막대 차선 배정과 일정 세부 설정 한국어 문구

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 4: DB v18 마이그레이션·건강 검사·기존 v17 고정 시험 갱신

**Files:**
- Modify: `database.py:24` (`CURRENT_SCHEMA_VERSION`), `database.py:31-48` (설정 상수 뒤), `database.py:201-271` (건강 검사), `database.py:800-816` (`migrate()`의 v16 블록 뒤)
- Modify: `main.py:113-130` (`_data_health_error_message`)
- Modify: `tests/test_database.py`, `tests/test_data_safety.py`, `tests/test_edge_cases.py`, `tests/test_release_smoke.py`, `tests/test_ui_kvm_position.py`, `tools/verify.py` (v17 고정값)
- Test: `tests/test_schedule_storage.py` (새)

**Interfaces:**
- Consumes: 없음(규칙 모듈은 Task 5부터 사용)
- Produces
  - 상수: `database.CURRENT_SCHEMA_VERSION == 18`, `database.SCHEDULE_V18_COLUMNS: tuple[(이름, SQL), ...]`, `database.SETTING_SCHEDULE_ALARM_SEEN_AT == "schedule_alarm_seen_at"`
  - 건강 검사 새 코드 `"schema_newer"`
  - 시험 도우미(`tests/test_schedule_storage.py`): `_seed_v17(app_dir)->Path`, `_raw_dump(db_file)->dict`, `V18_COLUMNS`

- [ ] **Step 1: 실패하는 시험을 쓴다** — `tests/test_schedule_storage.py`

```python
"""v4.1 일정 저장(DB v18 마이그레이션·API·Export v3) 회귀. 합성 데이터만 쓴다."""
import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import database as db
import security
from schedule_rules import ScheduleOptions

FIXTURE = Path(__file__).parent / "fixtures" / "schema_v17.sql"
V18_COLUMNS = ["start_time", "end_date", "repeat_rule", "repeat_until", "repeat_skip", "alarm_before"]


def _seed_v17(app_dir):
    """v4.0a와 같은 v17 DB를 만든다(고정 DDL + 기존 사용 흔적 + 형식이 다른 옛 날짜)."""
    db_file = app_dir / "calendar.db"
    for path in (db_file, app_dir / "calendar.db-wal", app_dir / "calendar.db-shm"):
        if path.exists():
            path.unlink()
    conn = sqlite3.connect(db_file)
    try:
        conn.executescript(FIXTURE.read_text(encoding="utf-8"))
        conn.executemany(
            "INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
            [
                ("2026-10-01", security.encrypt("월간 업무 계획 점검"), "2026-09-30 09:00:00", "#4CC9F0"),
                ("2026-10-15", security.encrypt("📌 보고서 초안 검토"), "2026-10-14 18:00:00", "#FF6B6B"),
                ("2026-7-1", security.encrypt("형식이 다른 옛 날짜"), "2026-06-30 08:00:00", "#FFD166"),
            ],
        )
        conn.execute("INSERT INTO memos (date, content, updated_at) VALUES (?, ?, ?)",
                     ("2026-10-15", security.encrypt("회의 자료"), "2026-10-15 08:00:00"))
        conn.execute("INSERT INTO sticky_notes (content) VALUES (?)", (security.encrypt("스티키"),))
        conn.execute("INSERT INTO dday_widgets (name, target_date) VALUES (?, ?)",
                     (security.encrypt("마감"), "2026-12-31"))
        conn.execute("INSERT INTO focus_widgets (goal, created_at) VALUES (?, ?)",
                     (security.encrypt("집중"), "2026-10-15 09:00:00"))
        conn.execute(
            "INSERT INTO focus_sessions (widget_id, goal, started_at, ended_at, created_at) VALUES (1, ?, ?, ?, ?)",
            (security.encrypt("기록"), "2026-10-15 09:00:00", "2026-10-15 09:25:00", "2026-10-15 09:25:00"))
        conn.execute("UPDATE shortcuts SET name = ?, path = ? WHERE id = 1", ("업무", "C:/업무"))
        conn.execute("PRAGMA user_version = 17")
        conn.commit()
    finally:
        conn.close()
    return db_file


def _raw_dump(db_file):
    """모든 표의 v17 열 값을 rowid 순서로 그대로 읽는다(v18 새 열은 뺀다)."""
    conn = sqlite3.connect(f"{Path(db_file).as_uri()}?mode=ro", uri=True)
    try:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        dump = {}
        for table in tables:  # 표·열 이름은 sqlite_master·table_info에서 온 값이다
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")
                       if row[1] not in V18_COLUMNS]
            dump[table] = conn.execute(
                f"SELECT {', '.join(columns)} FROM {table} ORDER BY rowid").fetchall()
        return dump
    finally:
        conn.close()


def test_first_start_on_v17_adds_columns_without_touching_existing_values(app_dir):
    import main as app_main

    db_file = _seed_v17(app_dir)
    before = _raw_dump(db_file)
    salt = security.SALT_FILE.read_bytes()

    assert app_main._initialize_database() is True

    assert _raw_dump(db_file) == before
    assert security.SALT_FILE.read_bytes() == salt
    with db._connection(enable_wal=False, read_only=True) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 18
        columns = [row[1] for row in conn.execute("PRAGMA table_info(schedules)")]
        assert columns == ["id", "date", "content", "created_at", "color", *V18_COLUMNS]
        rows = conn.execute(
            "SELECT start_time, end_date, repeat_rule, repeat_until, repeat_skip, alarm_before FROM schedules"
        ).fetchall()
        assert [tuple(row) for row in rows] == [("", "", "", "", "", None)] * 3
    snapshot = app_dir / "backups" / "calendar_pre_v18_v17.db"
    assert snapshot.is_file()
    assert _raw_dump(snapshot) == before
    assert db.get_schedules("2026-10-15")[0]["content"] == "📌 보고서 초안 검토"
    assert db.get_schedules("2026-7-1")[0]["content"] == "형식이 다른 옛 날짜"


def test_v18_migration_is_idempotent_and_accepts_version_rolled_back(app_dir):
    _seed_v17(app_dir)
    db.migrate()
    db.migrate()
    with db._connection() as conn:
        conn.execute("PRAGMA user_version = 17")  # 외부 도구로 버전만 내린 경우
        conn.commit()
    db.migrate()
    with db._connection(enable_wal=False, read_only=True) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 18
        assert [row[1] for row in conn.execute("PRAGMA table_info(schedules)")][5:] == V18_COLUMNS


def test_v18_migration_failure_rolls_back_every_column(app_dir, monkeypatch):
    db_file = _seed_v17(app_dir)
    before = _raw_dump(db_file)
    broken = list(db.SCHEDULE_V18_COLUMNS)
    # 기본값 없는 NOT NULL 열은 행이 있는 표에 더할 수 없어 SQLite가 거절한다(세 번째 열에서 실패).
    broken[2] = ("repeat_rule", "ALTER TABLE schedules ADD COLUMN repeat_rule TEXT NOT NULL")
    monkeypatch.setattr(db, "SCHEDULE_V18_COLUMNS", tuple(broken))

    with pytest.raises(sqlite3.Error):
        db.migrate()

    with db._connection(enable_wal=False, read_only=True) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 17
        assert [row[1] for row in conn.execute("PRAGMA table_info(schedules)")] == [
            "id", "date", "content", "created_at", "color"]
    assert _raw_dump(db_file) == before


def test_fresh_and_reset_databases_get_the_same_v18_schema(app_dir):
    with db._connection(enable_wal=False, read_only=True) as conn:
        assert [row[1] for row in conn.execute("PRAGMA table_info(schedules)")][5:] == V18_COLUMNS
    db.reset_database()
    with db._connection(enable_wal=False, read_only=True) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 18
        assert [row[1] for row in conn.execute("PRAGMA table_info(schedules)")][5:] == V18_COLUMNS


def test_health_reports_newer_schema(app_dir):
    with db._connection() as conn:
        conn.execute("PRAGMA user_version = 19")
        conn.commit()
    report = db.inspect_startup_data_health()
    assert (report.ok, report.code, report.version) == (False, "schema_newer", 19)


def test_health_rejects_v18_without_new_columns(app_dir):
    db_file = _seed_v17(app_dir)
    conn = sqlite3.connect(db_file)
    try:
        conn.execute("PRAGMA user_version = 18")
        conn.commit()
    finally:
        conn.close()
    report = db.inspect_startup_data_health()
    assert (report.ok, report.code) == (False, "schema_invalid")


def test_newer_schema_message_explains_update():
    import main as app_main
    _title, content = app_main._data_health_error_message("schema_newer")
    assert "더 새 버전" in content
    assert "변경하지 않았습니다" in content


def test_v17_upgrade_with_legacy_key_rows_keeps_plaintext(app_dir):
    """Review Focus 2: 구 키 암호문 재암호화와 v18 열 추가가 같은 시작에서 일어나도 본문이 같다."""
    import main as app_main

    db_file = _seed_v17(app_dir)
    legacy = Fernet(security.derive_legacy_key(security.read_existing_salt())).encrypt(
        "구 키 일정".encode("utf-8")).decode("ascii")
    conn = sqlite3.connect(db_file)
    try:
        conn.execute("INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
                     ("2026-10-20", legacy, "2026-01-01 00:00:00", "#FFD166"))
        conn.commit()
    finally:
        conn.close()
    security._fernet_cache = None
    security._legacy_fernet_cache = None

    assert app_main._initialize_database() is True

    rows = db.get_schedules("2026-10-20")
    assert [row["content"] for row in rows] == ["구 키 일정"]
    assert rows[0]["options"] == ScheduleOptions()
```

> `rows[0]["options"]`는 Task 5에서 생긴다. 이 Task에서는 마지막 시험만 `KeyError`로 실패해도 된다(Step 5에서 그 한 개만 실패하는지 확인).

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_schedule_storage.py -q`
Expected: 7개 FAIL(열·`SCHEDULE_V18_COLUMNS`·`schema_newer`·안내 문구가 아직 없음). `test_health_rejects_v18_without_new_columns`는 지금도 PASS다(지금은 버전 범위 검사로 막히고, 구현 뒤에는 열 검사로 막힌다).

- [ ] **Step 3: DB 상수와 마이그레이션을 구현한다** — `database.py`

`CURRENT_SCHEMA_VERSION = 17`을 `CURRENT_SCHEMA_VERSION = 18`로 바꾼다.

`SETTING_CALENDAR_MOVE_ENABLED = ...` 줄 바로 아래에 더한다.

```python
SETTING_SCHEDULE_ALARM_SEEN_AT = "schedule_alarm_seen_at"  # v4.1: 여기까지의 알림은 처리함(Export 제외)

# v4.1(DB v18): 일정 표에 열만 더한다. 이름 → 고정 SQL(외부 값이 섞이지 않는 상수).
SCHEDULE_V18_COLUMNS = (
    ("start_time", "ALTER TABLE schedules ADD COLUMN start_time TEXT NOT NULL DEFAULT ''"),
    ("end_date", "ALTER TABLE schedules ADD COLUMN end_date TEXT NOT NULL DEFAULT ''"),
    ("repeat_rule", "ALTER TABLE schedules ADD COLUMN repeat_rule TEXT NOT NULL DEFAULT ''"),
    ("repeat_until", "ALTER TABLE schedules ADD COLUMN repeat_until TEXT NOT NULL DEFAULT ''"),
    ("repeat_skip", "ALTER TABLE schedules ADD COLUMN repeat_skip TEXT NOT NULL DEFAULT ''"),
    ("alarm_before", "ALTER TABLE schedules ADD COLUMN alarm_before INTEGER"),
)
```

`migrate()`의 `if version == 16:` 블록(…`version = 17`) 바로 뒤, `with` 블록 안에 더한다.

```python
        if version == 17:
            # v4.1: 일정 시각·기간·반복·알림 열 추가. 기존 행의 값은 읽거나 쓰지 않는다.
            # 열 추가와 버전 표시를 한 트랜잭션으로 묶어 중간에 실패하면 모두 되돌린다.
            if conn.in_transaction:
                conn.commit()
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = {row[1] for row in conn.execute("PRAGMA table_info(schedules)")}
                for name, statement in SCHEDULE_V18_COLUMNS:
                    if name not in existing:
                        conn.execute(statement)
                conn.execute("PRAGMA user_version = 18")
                conn.execute("COMMIT")
            except sqlite3.Error:
                conn.execute("ROLLBACK")
                raise
            version = 18
```

- [ ] **Step 4: 건강 검사와 안내 문구를 바꾼다**

`database.py`의 `inspect_startup_data_health()`에서 아래 두 줄을

```python
            if not 0 < version <= CURRENT_SCHEMA_VERSION:
                return DataHealthReport(False, "schema_invalid", version)
```

다음으로 바꾼다.

```python
            if version > CURRENT_SCHEMA_VERSION:
                return DataHealthReport(False, "schema_newer", version)
            if version <= 0:
                return DataHealthReport(False, "schema_invalid", version)
```

같은 함수의 `if version == CURRENT_SCHEMA_VERSION:` 블록(필수 표 확인) 바로 뒤에 더한다.

```python
            if version >= 18 and "schedules" in tables:
                schedule_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(schedules)")
                }
                if not {name for name, _sql in SCHEDULE_V18_COLUMNS} <= schedule_columns:
                    return DataHealthReport(False, "schema_invalid", version)
```

`main.py`의 `_data_health_error_message`에서 `elif code == "decrypt_failed":` 분기 바로 앞에 더한다.

```python
    elif code == "schema_newer":
        detail = (
            "더 새 버전의 기후노트에서 쓰던 데이터입니다. "
            "최신 버전으로 실행해 주세요."
        )
```

- [ ] **Step 5: 새 시험을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_schedule_storage.py -q`
Expected: `test_v17_upgrade_with_legacy_key_rows_keeps_plaintext` 한 개만 `KeyError: 'options'`로 FAIL(Task 5에서 통과), 나머지 PASS

- [ ] **Step 6: v17 고정 시험을 갱신한다** — 아래 스크립트를 한 번 실행한다(개수가 다르면 멈춘다)

```bash
.venv/Scripts/python.exe -I -X utf8 - <<'EOF'
from pathlib import Path
EDITS = [
    ("tests/test_database.py", "== 17", "== db.CURRENT_SCHEMA_VERSION", 19),
    ("tests/test_database.py", "def test_fresh_install_is_v17(", "def test_fresh_install_is_current_version(", 1),
    ("tests/test_database.py", "def test_fresh_install_is_v17_with_new_settings(",
     "def test_fresh_install_is_current_version_with_new_settings(", 1),
    ("tests/test_database.py", "def test_initialize_database_current_v17_skips_pre_snapshot(",
     "def test_initialize_database_current_version_skips_pre_snapshot(", 1),
    ("tests/test_database.py", "def test_reset_then_migrate_v17(", "def test_reset_then_migrate_current_version(", 1),
    ("tests/test_database.py", 'glob("calendar_pre_v17_*.db")',
     'glob(f"calendar_pre_v{db.CURRENT_SCHEMA_VERSION}_*.db")', 2),
    ("tests/test_database.py", 'f"calendar_pre_v17_v{legacy_version}.db"',
     'f"calendar_pre_v{db.CURRENT_SCHEMA_VERSION}_v{legacy_version}.db"', 1),
    ("tests/test_database.py", '"calendar_pre_v17_v16.db"', 'f"calendar_pre_v{db.CURRENT_SCHEMA_VERSION}_v16.db"', 1),
    ("tests/test_database.py", "오류 없이 v17 유지", "오류 없이 최신 버전 유지", 1),
    ("tests/test_database.py", "v17 + 기본 ON", "최신 버전 + 기본 ON", 1),
    ("tests/test_data_safety.py", "== 17", "== db.CURRENT_SCHEMA_VERSION", 3),
    ("tests/test_edge_cases.py", "== 17", "== db.CURRENT_SCHEMA_VERSION", 1),
    ("tests/test_release_smoke.py", 'assert before["version"] == 17', 'assert before["version"] == 18', 1),
    ("tests/test_ui_kvm_position.py", "assert db.CURRENT_SCHEMA_VERSION == 17",
     "assert db.CURRENT_SCHEMA_VERSION == 18", 1),
    ("tools/verify.py", 'test_fresh_install_is_v17"', 'test_fresh_install_is_current_version"', 1),
]
for name, old, new, expected in EDITS:
    path = Path(name)
    text = path.read_bytes().decode("utf-8")  # 줄 끝(CRLF/LF)을 그대로 둔다
    found = text.count(old)
    assert found == expected, (name, old, found, expected)
    path.write_bytes(text.replace(old, new).encode("utf-8"))
print("ok", len(EDITS))
EOF
```

`tools/verify.py`의 `DATA_TESTS` 이름 목록에 `"schedule_rules", "schedule_storage",`를 `"database",` 앞에 더한다.

```python
DATA_TESTS = tuple(f"tests/test_{name}.py" for name in (
    "schedule_rules", "schedule_storage",
    "database", "security", "data_safety", "edge_cases", "stress",
    "startup_path", "ui", "ui_sticky", "ui_sticky_panel", "ui_data_lifecycle", "widget_limits",
))
```

- [ ] **Step 7: 데이터 시험 전체를 돌린다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_database.py tests/test_data_safety.py tests/test_edge_cases.py tests/test_release_smoke.py tests/test_ui_kvm_position.py tests/test_verify.py tests/test_schedule_rules.py -q`
Expected: PASS (`test_schedule_storage.py`의 Task 5 대기 1건은 여기 포함하지 않음)

- [ ] **Step 8: 커밋**

```bash
git add database.py main.py tests/test_schedule_storage.py tests/test_database.py tests/test_data_safety.py tests/test_edge_cases.py tests/test_release_smoke.py tests/test_ui_kvm_position.py tools/verify.py
git commit -m "feat: DB v18 일정 열 추가 마이그레이션(한 트랜잭션)과 새 버전 데이터 안내

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 5: 나타나는 일정 API·세부 설정 쓰기·이 날만 삭제·알림 조회

**Files:**
- Modify: `database.py:13` (import), `database.py:823-935` (`get_schedules`~`delete_schedule`), `database.py:949-987` (`search_all`)
- Test: `tests/test_schedule_storage.py` (시험 추가)

**Interfaces:**
- Consumes: `schedule_rules.ScheduleOptions`, `validate_options`, `occurrence_dates`, `occurrence_sort_key`, `alarm_times`, `parse_date`, `AlarmItem`
- Produces
  - `get_schedules(date)->list[dict]`
    - 기존 키: `id, date, content, created_at, color, _decryption_failed`
    - 새 키: `options`, `occurrence_date`, `span_start`, `span_end`, `start_time`, `shows_time`
  - 조회
    - `get_occurrences(start:str, end:str)->dict[str, list[dict]]`(위와 같은 항목)
    - `get_alarm_occurrences(after:datetime, until:datetime)->list[AlarmItem]`(알림 시각·ID 순)
    - `has_schedule_alarms()->bool`(알림 켜진 일정이 있는지)
  - 쓰기
    - `add_schedule(date, content, color=DEFAULT_SCHEDULE_COLOR, *, options=None)->int`
    - `update_schedule(schedule_id, content=None, color=None, *, options=None)`
    - `skip_schedule_occurrence(schedule_id:int, day:str)`
  - `search_all`의 일정 결과에 `end_date`, `repeat_rule` 키 추가

- [ ] **Step 1: 실패하는 시험을 추가한다** — `tests/test_schedule_storage.py` 끝에 붙인다

```python
import time
from datetime import datetime


def test_add_with_options_and_read_back(app_dir):
    sid = db.add_schedule("2026-10-15", "부서 회의", "#4CC9F0",
                          options=ScheduleOptions(start_time="15:00", repeat_rule="weekly", alarm_before=10))
    entry = db.get_schedules("2026-10-22")[0]
    assert (entry["id"], entry["date"], entry["occurrence_date"], entry["content"]) == (
        sid, "2026-10-15", "2026-10-22", "부서 회의")
    assert entry["options"] == ScheduleOptions(start_time="15:00", repeat_rule="weekly", alarm_before=10)
    assert (entry["shows_time"], entry["start_time"], entry["span_start"], entry["span_end"]) == (
        True, "15:00", "2026-10-22", "2026-10-22")
    assert db.get_schedules("2026-10-21") == []


def test_invalid_options_write_nothing(app_dir):
    with pytest.raises(ValueError):
        db.add_schedule("2026-10-15", "x", options=ScheduleOptions(repeat_rule="daily", end_date="2026-10-16"))
    with db._connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 0


def test_day_order_all_day_first_then_time(app_dir):
    late = db.add_schedule("2026-10-15", "16시", options=ScheduleOptions(start_time="16:00"))
    allday = db.add_schedule("2026-10-15", "종일")
    early = db.add_schedule("2026-10-15", "9시", options=ScheduleOptions(start_time="09:00"))
    period = db.add_schedule("2026-10-14", "기간", options=ScheduleOptions(start_time="08:00", end_date="2026-10-16"))
    assert [e["id"] for e in db.get_schedules("2026-10-15")] == [allday, period, early, late]
    first_day = db.get_schedules("2026-10-14")
    assert [e["id"] for e in first_day] == [period]
    assert first_day[0]["shows_time"] is True
    assert db.get_schedules("2026-10-15")[1]["shows_time"] is False
    assert (db.get_schedules("2026-10-15")[1]["span_start"],
            db.get_schedules("2026-10-15")[1]["span_end"]) == ("2026-10-14", "2026-10-16")


def test_get_occurrences_expands_repeat_and_period_and_keeps_legacy_strings(app_dir):
    """Review Focus 1: 형식이 다른 옛 날짜는 지금처럼 문자열 그대로만 맞춘다(멈추지 않음)."""
    weekly = db.add_schedule("2026-10-05", "주간 회의", options=ScheduleOptions(start_time="10:00", repeat_rule="weekly"))
    db.add_schedule("2026-10-30", "출장", options=ScheduleOptions(end_date="2026-11-02"))
    with db._connection() as conn:
        conn.execute("INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
                     ("2026-10-7", security.encrypt("옛 형식"), "2026-01-01 00:00:00", "#FFD166"))
        conn.commit()
    month = db.get_occurrences("2026-10-01", "2026-10-31")
    assert sorted(day for day, entries in month.items() if any(e["id"] == weekly for e in entries)) == [
        "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]
    assert [e["span_end"] for e in month["2026-10-31"]] == ["2026-11-02"]
    assert "2026-10-7" not in month
    assert [e["content"] for e in db.get_schedules("2026-10-7")] == ["옛 형식"]


def test_skip_occurrence_only_hides_that_day(app_dir):
    sid = db.add_schedule("2026-10-05", "주간 회의", options=ScheduleOptions(repeat_rule="weekly"))
    db.skip_schedule_occurrence(sid, "2026-10-12")
    assert db.get_schedules("2026-10-12") == []
    assert [e["id"] for e in db.get_schedules("2026-10-19")] == [sid]
    assert db.get_schedules("2026-10-19")[0]["options"].repeat_skip == ("2026-10-12",)
    with pytest.raises(ValueError, match="그 날"):
        db.skip_schedule_occurrence(sid, "2026-10-13")
    single = db.add_schedule("2026-10-05", "하루")
    with pytest.raises(ValueError, match="반복"):
        db.skip_schedule_occurrence(single, "2026-10-05")


def test_update_options_replaces_all_fields_and_validates_against_start(app_dir):
    sid = db.add_schedule("2026-10-15", "회의", options=ScheduleOptions(start_time="09:00", alarm_before=10))
    db.update_schedule(sid, options=ScheduleOptions(repeat_rule="daily"))
    assert db.get_schedules("2026-10-16")[0]["options"] == ScheduleOptions(repeat_rule="daily")
    with pytest.raises(ValueError):
        db.update_schedule(sid, content="바뀌면 안 됨", options=ScheduleOptions(repeat_until="2026-10-01"))
    assert db.get_schedules("2026-10-15")[0]["content"] == "회의"
    db.update_schedule(sid, options=ScheduleOptions())
    assert db.get_schedules("2026-10-16") == []
    with pytest.raises(ValueError, match="없습니다"):
        db.update_schedule(9999, options=ScheduleOptions(start_time="09:00"))


def test_get_alarm_occurrences_window_and_order(app_dir):
    a = db.add_schedule("2026-10-15", "부서 회의", "#4CC9F0",
                        options=ScheduleOptions(start_time="15:00", alarm_before=10))
    b = db.add_schedule("2026-10-16", "보고 마감", options=ScheduleOptions(alarm_before=1440))
    db.add_schedule("2026-10-15", "알림 없음", options=ScheduleOptions(start_time="15:00"))
    items = db.get_alarm_occurrences(datetime(2026, 10, 15, 8, 0), datetime(2026, 10, 15, 15, 0))
    assert [(i.schedule_id, i.occurrence_date, i.due) for i in items] == [
        (b, "2026-10-16", datetime(2026, 10, 15, 9, 0)),
        (a, "2026-10-15", datetime(2026, 10, 15, 14, 50))]
    assert (items[1].content, items[1].start_time, items[1].color) == ("부서 회의", "15:00", "#4CC9F0")
    assert db.get_alarm_occurrences(datetime(2026, 10, 15, 15, 0), datetime(2026, 10, 15, 15, 0)) == []


def test_has_schedule_alarms(app_dir):
    assert db.has_schedule_alarms() is False
    sid = db.add_schedule("2026-10-15", "알림", options=ScheduleOptions(alarm_before=0))
    assert db.has_schedule_alarms() is True
    db.update_schedule(sid, options=ScheduleOptions())
    assert db.has_schedule_alarms() is False


def test_search_results_carry_period_and_repeat(app_dir):
    db.add_schedule("2026-10-05", "주간 회의", options=ScheduleOptions(repeat_rule="weekly"))
    result = db.search_all("주간")[0]
    assert (result["date"], result["repeat_rule"], result["end_date"]) == ("2026-10-05", "weekly", "")


def test_month_expansion_stays_fast_with_many_repeats(app_dir):
    with db._connection() as conn:
        conn.executemany(
            "INSERT INTO schedules (date, content, created_at, color, repeat_rule) VALUES (?, ?, ?, ?, ?)",
            [("2025-01-01", security.encrypt(f"반복 {i}"), "2025-01-01 00:00:00", "#FFD166", "daily")
             for i in range(1000)])
        conn.commit()
    started = time.perf_counter()
    month = db.get_occurrences("2026-10-01", "2026-10-31")
    assert len(month["2026-10-15"]) == 1000
    assert time.perf_counter() - started < 5.0
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_schedule_storage.py -q`
Expected: FAIL — `TypeError: add_schedule() got an unexpected keyword argument 'options'` 등

- [ ] **Step 3: 구현한다** — `database.py`

import 정리(파일 맨 위)
- `from dataclasses import dataclass` → `from dataclasses import dataclass, replace`
- `from datetime import datetime, timezone` → `from datetime import datetime, timedelta, timezone`
- `from app_info import APP_VERSION` 줄 바로 아래에 더한다.

```python
from schedule_rules import (
    AlarmItem, ScheduleOptions, alarm_times, occurrence_dates, occurrence_sort_key,
    parse_date, validate_options,
)
```

`get_schedules`부터 `delete_schedule` 직전까지(현재 `get_schedules`·`get_all_schedule_dates`·`get_all_schedule_date_colors`·`get_all_schedule_date_counts`·`get_schedules_for_month`·`add_schedule`·`update_schedule`)를 아래로 바꾼다. 원본 행 함수 네 개는 본문을 그대로 두고 문서 문자열만 바꾼다.

```python
_SCHEDULE_SELECT = (
    "SELECT id, date, content, created_at, color, start_time, end_date, "
    "repeat_rule, repeat_until, repeat_skip, alarm_before FROM schedules "
)
_SCHEDULE_INSERT = (
    "INSERT INTO schedules (date, content, created_at, color, start_time, end_date, "
    "repeat_rule, repeat_until, repeat_skip, alarm_before) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _decrypt_schedule(ciphertext: str) -> tuple[str, bool]:
    """일정 본문 복호화(구 키 재시도). 실패하면 ('[복호화 오류]', True)."""
    try:
        return decrypt(ciphertext), False
    except (InvalidToken, ValueError, TypeError):
        try:
            return legacy_decrypt(ciphertext), False
        except (InvalidToken, ValueError, TypeError):
            return "[복호화 오류]", True


def _candidate_rows(conn, first: str, last: str) -> list:
    """[first, last]에 나타날 수 있는 행만 고른다(펼치기는 schedule_rules가 한다)."""
    return conn.execute(
        _SCHEDULE_SELECT
        + "WHERE date <= ? AND (date >= ? OR end_date >= ? OR repeat_rule != '') ORDER BY id ASC",
        (last, first, first),
    ).fetchall()


def _occurrence_days(row, first: str, last: str) -> list[str]:
    options = ScheduleOptions.from_row(row)
    if not options.end_date and not options.repeat_rule:
        # 기존 하루 일정: 저장된 문자열 그대로 비교한다(형식이 조금 다른 옛 날짜도 지금처럼 동작).
        return [row["date"]] if first <= row["date"] <= last else []
    try:
        found = occurrence_dates(row["date"], options, parse_date(first), parse_date(last))
    except ValueError as exc:
        _logger.warning("일정 반복·기간 해석 실패 (id=%s): %s", row["id"], exc)
        return [row["date"]] if first <= row["date"] <= last else []
    return [day.isoformat() for day in found]


def _schedule_entry(row, day: str, content: str, failed: bool) -> dict:
    options = ScheduleOptions.from_row(row)
    is_period = bool(options.end_date)
    return {
        "id": row["id"],
        "date": row["date"],
        "content": content,
        "created_at": row["created_at"],
        "color": row["color"] or DEFAULT_SCHEDULE_COLOR,
        "_decryption_failed": failed,
        "options": options,
        "occurrence_date": day,
        # 기간은 전체 범위, 하루·반복은 그 날 하루가 이 항목의 범위다.
        "span_start": row["date"] if is_period else day,
        "span_end": options.end_date if is_period else day,
        "start_time": options.start_time,
        # 기간은 첫날에만 시각을 보이고, 반복은 나타나는 날마다 보인다.
        "shows_time": bool(options.start_time) and (not is_period or day == row["date"]),
    }


def _expand_rows(rows, first: str, last: str) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for row in rows:
        found = _occurrence_days(row, first, last)
        if not found:
            continue
        content, failed = _decrypt_schedule(row["content"])
        for day in found:
            result.setdefault(day, []).append(_schedule_entry(row, day, content, failed))
    for entries in result.values():
        entries.sort(key=lambda e: occurrence_sort_key(e["shows_time"], e["start_time"], e["id"]))
    return result


def get_schedules(date: str) -> list[dict]:
    """그 날 나타나는 일정(하루·기간·반복)을 순서대로 반환한다(복호화)."""
    with _connection() as conn:
        rows = _candidate_rows(conn, date, date)
    return _expand_rows(rows, date, date).get(date, [])


def get_occurrences(start: str, end: str) -> dict[str, list[dict]]:
    """[start, end] 날짜마다 나타나는 일정(달력 한 화면용, 정렬·복호화)."""
    with _connection() as conn:
        rows = _candidate_rows(conn, start, end)
    return _expand_rows(rows, start, end)


def get_all_schedule_dates() -> set[str]:
    """원본 시작일 기준 날짜 목록(반복·기간 미전개). 화면은 get_occurrences를 쓴다."""
    with _connection() as conn:
        rows = conn.execute("SELECT DISTINCT date FROM schedules").fetchall()
        return {row["date"] for row in rows}


def get_all_schedule_date_colors() -> dict[str, list[str]]:
    """원본 시작일 기준 날짜별 고유 색(반복·기간 미전개). 화면은 get_occurrences를 쓴다."""
    with _connection() as conn:
        rows = conn.execute("SELECT date, color FROM schedules").fetchall()
        result: dict[str, set[str]] = {}
        for row in rows:
            color = row["color"] or DEFAULT_SCHEDULE_COLOR
            result.setdefault(row["date"], set()).add(color)
        color_order = {c[0]: i for i, c in enumerate(SCHEDULE_COLORS)}
        return {
            date: sorted(colors, key=lambda c: color_order.get(c, 99))
            for date, colors in result.items()
        }


def get_all_schedule_date_counts() -> dict[str, int]:
    """원본 시작일 기준 날짜별 일정 수(반복·기간 미전개). 화면은 get_occurrences를 쓴다."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT date, COUNT(*) AS n FROM schedules GROUP BY date"
        ).fetchall()
        return {row["date"]: row["n"] for row in rows}


def get_schedules_for_month(year: int, month: int) -> dict[str, list[dict]]:
    """원본 시작일 기준 그 달 일정(반복·기간 미전개). 화면은 get_occurrences를 쓴다."""
    month_prefix = f"{year:04d}-{month:02d}-"
    with _connection() as conn:
        rows = conn.execute(
            "SELECT date, content, color FROM schedules "
            "WHERE date LIKE ? ORDER BY date ASC, id ASC",
            (f"{month_prefix}%",),
        ).fetchall()
        result: dict[str, list[dict]] = {}
        for row in rows:
            result.setdefault(row["date"], []).append({
                "content": _safe_decrypt(row["content"], "[복호화 오류]"),
                "color": row["color"] or DEFAULT_SCHEDULE_COLOR,
            })
        return result


def add_schedule(date: str, content: str, color: str = DEFAULT_SCHEDULE_COLOR, *,
                 options: ScheduleOptions | None = None) -> int:
    """일정 추가(본문 암호화). 세부 설정이 있으면 먼저 검증하고 실패하면 아무것도 쓰지 않는다."""
    options = options or ScheduleOptions()
    if not options.is_default:
        options = validate_options(date, options)
    with _connection() as conn:
        cur = conn.execute(
            _SCHEDULE_INSERT,
            (date, encrypt(content), _now_str(), color, *options.to_db_values()),
        )
        conn.commit()
        return cur.lastrowid


def update_schedule(schedule_id: int, content: str = None, color: str = None, *,
                    options: ScheduleOptions | None = None) -> None:
    """일정 수정. options를 주면 세부 설정 여섯 칸을 한 번에 바꾼다(검증 실패 시 아무것도 안 씀)."""
    with _connection() as conn:
        if options is not None:
            row = conn.execute("SELECT date FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
            if row is None:
                raise ValueError("수정할 일정이 없습니다.")
            if not options.is_default:
                options = validate_options(row["date"], options)
        if content is not None:
            conn.execute(
                "UPDATE schedules SET content = ? WHERE id = ?",
                (encrypt(content), schedule_id),
            )
        if color is not None:
            conn.execute(
                "UPDATE schedules SET color = ? WHERE id = ?",
                (color, schedule_id),
            )
        if options is not None:
            conn.execute(
                "UPDATE schedules SET start_time = ?, end_date = ?, repeat_rule = ?, "
                "repeat_until = ?, repeat_skip = ?, alarm_before = ? WHERE id = ?",
                (*options.to_db_values(), schedule_id),
            )
        conn.commit()


def skip_schedule_occurrence(schedule_id: int, day: str) -> None:
    """반복 일정의 그 날 하나만 지운다(건너뛴 날에 더함)."""
    with _connection() as conn:
        row = conn.execute(_SCHEDULE_SELECT + "WHERE id = ?", (schedule_id,)).fetchone()
        if row is None:
            raise ValueError("일정이 없습니다.")
        options = ScheduleOptions.from_row(row)
        if not options.repeat_rule:
            raise ValueError("반복 일정이 아닙니다.")
        target = parse_date(day)
        if not occurrence_dates(row["date"], options, target, target):
            raise ValueError("그 날에는 이 일정이 없습니다.")
        updated = validate_options(row["date"], replace(options, repeat_skip=options.repeat_skip + (day,)))
        conn.execute(
            "UPDATE schedules SET repeat_skip = ? WHERE id = ?",
            (",".join(updated.repeat_skip), schedule_id),
        )
        conn.commit()


def get_alarm_occurrences(after: datetime, until: datetime) -> list[AlarmItem]:
    """after < 알림 ≤ until 인 알림을 알림 시각·ID 순으로 반환한다."""
    if until <= after:
        return []
    first = (after.date() - timedelta(days=1)).isoformat()
    last = (until.date() + timedelta(days=2)).isoformat()
    with _connection() as conn:
        rows = conn.execute(
            _SCHEDULE_SELECT
            + "WHERE alarm_before IS NOT NULL AND date <= ? "
            "AND (date >= ? OR end_date >= ? OR repeat_rule != '') ORDER BY id ASC",
            (last, first, first),
        ).fetchall()
    items = []
    for row in rows:
        options = ScheduleOptions.from_row(row)
        if options.alarm_before is None:
            continue
        try:
            dues = alarm_times(row["date"], options, after, until)
        except ValueError as exc:
            _logger.warning("일정 알림 시각 계산 실패 (id=%s): %s", row["id"], exc)
            continue
        if not dues:
            continue
        content, failed = _decrypt_schedule(row["content"])
        for day, due in dues:
            items.append(AlarmItem(
                row["id"], day.isoformat(), due, content,
                row["color"] or DEFAULT_SCHEDULE_COLOR, options.start_time, failed,
            ))
    items.sort(key=lambda item: (item.due, item.schedule_id))
    return items


def has_schedule_alarms() -> bool:
    """알림이 켜진 일정이 하나라도 있는지(정상 종료 때 알림 처리 시각을 남길지 판단)."""
    with _connection() as conn:
        return conn.execute(
            "SELECT 1 FROM schedules WHERE alarm_before IS NOT NULL LIMIT 1"
        ).fetchone() is not None
```

`search_all`의 일정 부분에서 `for row in conn.execute("SELECT id, date, content, created_at, color FROM schedules"):`부터 `results.append({...})`의 닫는 `})`까지를 아래로 바꾼다(그 뒤의 `if len(results) >= limit: break`는 그대로).

```python
        for row in conn.execute(
                "SELECT id, date, content, created_at, color, end_date, repeat_rule FROM schedules"):
            content = _safe_decrypt(row["content"])
            if not content:
                continue
            if not keyword_lower or keyword_lower in content.lower():
                results.append({
                    "type": "일정",
                    "date": row["date"],
                    "content": content,
                    "color": row["color"] or DEFAULT_SCHEDULE_COLOR,
                    "end_date": row["end_date"] or "",
                    "repeat_rule": row["repeat_rule"] or "",
                })
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_schedule_storage.py tests/test_database.py tests/test_edge_cases.py tests/test_stress.py -q`
Expected: PASS (Task 4에서 대기하던 `test_v17_upgrade_with_legacy_key_rows_keeps_plaintext` 포함)

- [ ] **Step 5: 커밋**

```bash
git add database.py tests/test_schedule_storage.py
git commit -m "feat: 반복·기간을 펼친 일정 조회, 세부 설정 쓰기, 이 날만 삭제, 알림 조회

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 6: Export v3 / Import v1~v3

**Files:**
- Modify: `database.py:23` (`EXPORT_FORMAT_VERSION`), `database.py` `export_all_data`·`_validate_import_payload`·`import_all_data`
- Modify: `tests/test_ui_kvm_position.py:313`
- Test: `tests/test_schedule_storage.py` (시험 추가)

**Interfaces:**
- Consumes: Task 5의 `_SCHEDULE_INSERT`, `ScheduleOptions`, `validate_options`
- Produces: `database.EXPORT_FORMAT_VERSION == 3`, `database.EXPORT_EXCLUDED_SETTINGS`(frozenset: `privacy_pin`, `schedule_alarm_seen_at`), 일정 항목의 v3 키 6개

- [ ] **Step 1: 실패하는 시험을 추가한다** — `tests/test_schedule_storage.py` 끝에 붙인다

```python
import json

OPTION_KEYS = ("start_time", "end_date", "repeat_rule", "repeat_until", "repeat_skip", "alarm_before")


def test_export_v3_writes_all_schedule_fields_and_hides_alarm_seen_at(app_dir):
    db.add_schedule("2026-10-05", "주간 회의",
                    options=ScheduleOptions(start_time="10:00", repeat_rule="weekly",
                                            repeat_until="2026-12-28", alarm_before=10))
    sid = db.add_schedule("2026-10-05", "건너뛴 회의", options=ScheduleOptions(repeat_rule="weekly"))
    db.skip_schedule_occurrence(sid, "2026-10-12")
    db.add_schedule("2026-10-15", "옛 일정")
    db.save_setting(db.SETTING_SCHEDULE_ALARM_SEEN_AT, "2026-10-15T09:00:00")

    payload = json.loads(db.export_all_data())

    assert payload["format_version"] == 3
    first, second, legacy = payload["schedules"]
    assert {k: first[k] for k in OPTION_KEYS} == {
        "start_time": "10:00", "end_date": "", "repeat_rule": "weekly",
        "repeat_until": "2026-12-28", "repeat_skip": [], "alarm_before": 10}
    assert second["repeat_skip"] == ["2026-10-12"]
    assert {k: legacy[k] for k in OPTION_KEYS} == {
        "start_time": "", "end_date": "", "repeat_rule": "", "repeat_until": "",
        "repeat_skip": [], "alarm_before": None}
    assert db.SETTING_SCHEDULE_ALARM_SEEN_AT not in payload["settings"]
    assert db.SETTING_PRIVACY_PIN not in payload["settings"]


def test_v3_roundtrip_restores_options(app_dir):
    db.add_schedule("2026-10-05", "주간 회의",
                    options=ScheduleOptions(start_time="10:00", repeat_rule="weekly",
                                            repeat_until="2026-12-28", alarm_before=10))
    db.add_schedule("2026-10-21", "출장", options=ScheduleOptions(end_date="2026-10-23"))
    text = db.export_all_data()
    db.reset_database()
    db.import_all_data(text)
    assert db.get_schedules("2026-10-19")[0]["options"] == ScheduleOptions(
        start_time="10:00", repeat_rule="weekly", repeat_until="2026-12-28", alarm_before=10)
    assert db.get_schedules("2026-10-22")[0]["span_end"] == "2026-10-23"


def test_v2_file_imports_with_default_options_and_ignores_extra_keys(app_dir):
    payload = {"format_version": 2, "schedules": [{
        "date": "2026-10-15", "content": "v2 일정", "created_at": "2026-10-01 09:00:00",
        "color": "#FFD166", "repeat_rule": "daily"}]}
    db.import_all_data(json.dumps(payload))
    assert [e["options"] for e in db.get_schedules("2026-10-15")] == [ScheduleOptions()]
    assert db.get_schedules("2026-10-16") == []


@pytest.mark.parametrize("field,value", [
    ("start_time", "9:30"), ("start_time", 930), ("end_date", "2026-10-15"),
    ("repeat_rule", "biweekly"), ("repeat_until", "2026-10-01"), ("repeat_skip", "2026-10-22"),
    ("repeat_skip", [20261022]), ("alarm_before", 15), ("alarm_before", True),
])
def test_v3_invalid_schedule_options_reject_whole_file(app_dir, field, value):
    base = {"date": "2026-10-15", "content": "x"}
    if field in ("repeat_until", "repeat_skip"):
        base["repeat_rule"] = "weekly"
    payload = {
        "format_version": 3,
        "schedules": [{"date": "2026-10-15", "content": "정상"}, {**base, field: value}],
        "memos": [{"date": "2026-10-15", "content": "메모"}],
    }
    with pytest.raises(ValueError):
        db.import_all_data(json.dumps(payload))
    with db._connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM memos").fetchone()[0] == 0


def test_import_ignores_alarm_seen_at_setting(app_dir):
    payload = {"format_version": 3, "settings": {
        db.SETTING_SCHEDULE_ALARM_SEEN_AT: "2030-01-01T00:00:00", "show_lunar": "1"}}
    db.import_all_data(json.dumps(payload))
    assert db.get_setting(db.SETTING_SCHEDULE_ALARM_SEEN_AT, "") == ""
    assert db.get_setting("show_lunar") == "1"


def test_legacy_date_string_survives_export_import(app_dir):
    """Review Focus 1: 형식이 다른 옛 날짜도 v3 내보내기·가져오기를 그대로 지난다."""
    with db._connection() as conn:
        conn.execute("INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
                     ("2026-7-1", security.encrypt("옛 형식"), "2026-01-01 00:00:00", "#FFD166"))
        conn.commit()
    text = db.export_all_data()
    db.reset_database()
    db.import_all_data(text)
    assert [e["content"] for e in db.get_schedules("2026-7-1")] == ["옛 형식"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_schedule_storage.py -q -k "export or import or v3 or v2"`
Expected: FAIL — `format_version == 2` 등

- [ ] **Step 3: 구현한다** — `database.py`

(1) 상수: `EXPORT_FORMAT_VERSION = 2` → `EXPORT_FORMAT_VERSION = 3`. 그리고 Task 4에서 더한 `SETTING_SCHEDULE_ALARM_SEEN_AT = ...` 줄 바로 아래에 더한다.

```python
# Export에 넣지 않고 Import에서도 쓰지 않는 설정(평문 PIN, 이 PC의 알림 처리 시각)
EXPORT_EXCLUDED_SETTINGS = frozenset({SETTING_PRIVACY_PIN, SETTING_SCHEDULE_ALARM_SEEN_AT})
```

(2) `export_all_data`의 일정 목록. 찾을 원문:

```python
        schedules = [{
            "date": row["date"],
            "content": _decrypt_for_export(
                row["content"], "schedules", row["id"]
            ),
            "created_at": row["created_at"],
            "color": row["color"] or DEFAULT_SCHEDULE_COLOR,
        } for row in conn.execute("SELECT * FROM schedules")]
```

바꿀 코드:

```python
        schedules = []
        for row in conn.execute("SELECT * FROM schedules"):
            options = ScheduleOptions.from_row(row)
            schedules.append({
                "date": row["date"],
                "content": _decrypt_for_export(row["content"], "schedules", row["id"]),
                "created_at": row["created_at"],
                "color": row["color"] or DEFAULT_SCHEDULE_COLOR,
                "start_time": options.start_time,
                "end_date": options.end_date,
                "repeat_rule": options.repeat_rule,
                "repeat_until": options.repeat_until,
                "repeat_skip": list(options.repeat_skip),
                "alarm_before": options.alarm_before,
            })
```

(3) `export_all_data`의 설정 수집. 찾을 원문:

```python
        # app_settings 전체 백업 (privacy_pin은 평문 PIN이므로 제외)
        settings = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM app_settings")
            if row["key"] != SETTING_PRIVACY_PIN
        }
```

바꿀 코드:

```python
        # app_settings 전체 백업 (평문 PIN과 이 PC의 알림 처리 시각은 제외)
        settings = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM app_settings")
            if row["key"] not in EXPORT_EXCLUDED_SETTINGS
        }
```

(4) `def _validate_import_payload(data) -> dict:` 바로 위에 도우미를 더한다.

```python
def _import_options(item: dict) -> ScheduleOptions:
    """v3 일정 항목의 세부 설정(없는 키는 기본값)."""
    return ScheduleOptions(
        start_time=item.get("start_time", ""),
        end_date=item.get("end_date", ""),
        repeat_rule=item.get("repeat_rule", ""),
        repeat_until=item.get("repeat_until", ""),
        repeat_skip=tuple(item.get("repeat_skip", [])),
        alarm_before=item.get("alarm_before"),
    )
```

(5) `_validate_import_payload`의 일정 검사. 찾을 원문:

```python
    for index, item in enumerate(data.get("schedules", [])):
        for field in ("date", "content"):
            _validate_import_field(
                item, "schedules", index, field, str, required=True
            )
        for field in ("created_at", "color"):
            _validate_import_field(
                item, "schedules", index, field, str
            )
```

바꿀 코드(앞 부분은 같고 `if version >= 3:` 블록만 더해진다):

```python
    for index, item in enumerate(data.get("schedules", [])):
        for field in ("date", "content"):
            _validate_import_field(
                item, "schedules", index, field, str, required=True
            )
        for field in ("created_at", "color"):
            _validate_import_field(
                item, "schedules", index, field, str
            )
        if version >= 3:
            for field in ("start_time", "end_date", "repeat_rule", "repeat_until"):
                _validate_import_field(item, "schedules", index, field, str)
            skips = item.get("repeat_skip", [])
            if not isinstance(skips, list) or not all(isinstance(day, str) for day in skips):
                raise ValueError(f"schedules[{index}].repeat_skip 형식이 올바르지 않습니다.")
            _validate_import_field(item, "schedules", index, "alarm_before", int, allow_none=True)
            options = _import_options(item)
            if not options.is_default:
                try:
                    validate_options(item["date"], options)
                except ValueError as exc:
                    raise ValueError(f"schedules[{index}] 세부 설정이 올바르지 않습니다: {exc}") from exc
```

(6) `import_all_data`의 일정 삽입. 찾을 원문:

```python
        for s in data.get("schedules", []):
            conn.execute(
                "INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
                (s["date"], encrypt(s["content"]), s.get("created_at", now),
                 s.get("color", DEFAULT_SCHEDULE_COLOR))
            )
```

바꿀 코드:

```python
        for s in data.get("schedules", []):
            options = _import_options(s) if data["format_version"] >= 3 else ScheduleOptions()
            if not options.is_default:
                options = validate_options(s["date"], options)
            conn.execute(
                _SCHEDULE_INSERT,
                (s["date"], encrypt(s["content"]), s.get("created_at", now),
                 s.get("color", DEFAULT_SCHEDULE_COLOR), *options.to_db_values()),
            )
```

(7) `import_all_data`의 설정 복원. 찾을 원문:

```python
        # 설정 복원 (privacy_pin 평문 PIN 제외, None 값 건너뜀)
        for key, value in data.get("settings", {}).items():
            if key == SETTING_PRIVACY_PIN or value is None:
                continue
```

바꿀 코드:

```python
        # 설정 복원 (평문 PIN·알림 처리 시각 제외, None 값 건너뜀)
        for key, value in data.get("settings", {}).items():
            if key in EXPORT_EXCLUDED_SETTINGS or value is None:
                continue
```

(8) 내보내기 형식 v2를 고정한 기존 시험 두 곳을 3으로 바꾼다(가져오기 쪽 `"format_version": 2` 입력은 v2 파일 호환 시험이므로 그대로 둔다).
- `tests/test_ui_kvm_position.py`: `assert json.loads(exported)["format_version"] == 2` → `== 3`
- `tests/test_ui_data_lifecycle.py`: `assert payload['format_version'] == 2` → `== 3`

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_schedule_storage.py tests/test_database.py tests/test_ui_kvm_position.py tests/test_ui_data_lifecycle.py tests/test_edge_cases.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add database.py tests/test_schedule_storage.py tests/test_ui_kvm_position.py tests/test_ui_data_lifecycle.py
git commit -m "feat: 내보내기 v3(일정 세부 설정)와 v1~v3 가져오기, 알림 처리 시각 제외

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 7: 릴리스 격리 실행 'upgrade' 시나리오

**Files:**
- Modify: `tools/smoke_release.py` (상수·도우미·`_data_worker`·`scenario`·`main`)
- Test: `tests/test_release_smoke.py` (시험 추가)

**Interfaces:**
- Consumes: `tests/fixtures/schema_v17.sql`, `main._initialize_database`
- Produces
  - 데이터 작업: `seed_v17`, `upgrade_source`(EXE 없이 소스 시작 경로 실행, 도구 자체 시험용), `inspect_upgrade`
  - 시나리오 순서: `("fresh", "existing", "blocked", "upgrade")`

- [ ] **Step 1: 실패하는 시험을 추가한다** — `tests/test_release_smoke.py`

파일 맨 위 import 묶음에 `import sqlite3`를 더하고(`import os` 다음 줄), 파일 끝에 붙인다.

```python
def test_upgrade_tooling_detects_kept_values_and_snapshot():
    directory = verify.create_run_dir()
    data_root = directory / "legacy"
    data_root.mkdir()
    before = smoke.data_step("seed_v17", data_root, directory / "seed_v17.json")
    assert before["version"] == 17
    conn = sqlite3.connect(data_root / "MyDesktopCalendar" / "calendar.db")
    try:
        assert [r[1] for r in conn.execute("PRAGMA table_info(schedules)")] == [
            "id", "date", "content", "created_at", "color"]
    finally:
        conn.close()
    with pytest.raises(RuntimeError, match="inspect_upgrade"):
        smoke.data_step("inspect_upgrade", data_root, directory / "too-early.json")

    smoke.data_step("upgrade_source", data_root, directory / "upgrade.json")
    after = smoke.data_step("inspect_upgrade", data_root, directory / "after.json")
    assert after["version"] == 18
    assert after["tables"] == before["tables"]
    assert after["pre_snapshot"]["tables"] == before["tables"]
    assert after["pre_snapshot"]["version"] == 17
    assert after["salt_sha256"] == before["salt_sha256"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_release_smoke.py -q -k upgrade`
Expected: FAIL — `RuntimeError: 합성 데이터 seed_v17 실패 ... 지원하지 않는 데이터 작업`

- [ ] **Step 3: 구현한다** — `tools/smoke_release.py` (`hashlib`·`json`·`sqlite3`·`date`·`Path`는 이미 import되어 있다)

(1) `def protected_hashes(data_root):` 바로 위에 더한다.

```python
V18_COLUMNS = ("start_time", "end_date", "repeat_rule", "repeat_until", "repeat_skip", "alarm_before")
V17_FIXTURE = ROOT / "tests" / "fixtures" / "schema_v17.sql"


def _original_columns_snapshot(path):
    """모든 표의 v17 열 값 해시(v18 새 열 제외)와 user_version."""
    conn = sqlite3.connect(f"{Path(path).as_uri()}?mode=ro", uri=True)
    try:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        hashes = {}
        for table in tables:  # 표·열 이름은 sqlite_master·table_info에서만 온다.
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")
                       if row[1] not in V18_COLUMNS]
            rows = conn.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY rowid").fetchall()
            hashes[table] = hashlib.sha256(
                json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()
    return {"tables": hashes, "version": version}
```

(2) `_data_worker`의 `    elif action == "inspect":` 줄 바로 위에 더한다.

```python
    elif action == "seed_v17":
        if db.DB_FILE.exists():
            raise ValueError("새 합성 데이터 폴더만 초기화할 수 있습니다.")
        db.DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        day = date.today().isoformat()
        conn = sqlite3.connect(db.DB_FILE)
        try:
            with open(V17_FIXTURE, encoding="utf-8") as fixture:
                conn.executescript(fixture.read())
            for color, _ in db.SCHEDULE_COLORS:
                conn.execute(
                    "INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
                    (day, security.encrypt("v17 합성 일정 " + color), day + " 09:00:00", color))
            conn.execute("INSERT INTO memos (date, content, updated_at) VALUES (?, ?, ?)",
                         (day, security.encrypt("v17 합성 메모"), day + " 09:00:00"))
            # 닫힌 스티키로 둔다. 열린 스티키는 앱이 창 크기를 5mm 격자에 맞춰(300×400→306×396 등)
            # 저장하는 기존 동작이 있어, 실행 시간에 따라 값 비교가 흔들린다(v4.0부터 같은 동작).
            conn.execute("INSERT INTO sticky_notes (content, is_open) VALUES (?, 0)",
                         (security.encrypt("v17 스티키"),))
            conn.execute("PRAGMA user_version = 17")
            conn.commit()
        finally:
            conn.close()
        result = _original_columns_snapshot(db.DB_FILE)
        result["salt_sha256"] = file_hash(security.SALT_FILE)
    elif action == "upgrade_source":
        # EXE 없이 같은 시작 경로를 소스로 실행한다(검사 도구 자체 시험용).
        import main as app_main
        app_main._initialize_database()
        result = {"ok": True}
    elif action == "inspect_upgrade":
        health = db.inspect_startup_data_health()
        if not health.ok:
            raise ValueError(f"업그레이드 뒤 데이터 건강 검사 실패: {health.code}")
        result = _original_columns_snapshot(db.DB_FILE)
        if result["version"] != db.CURRENT_SCHEMA_VERSION:
            raise ValueError("업그레이드 뒤 DB 버전이 최신이 아닙니다.")
        with db._connection(read_only=True, enable_wal=False) as conn:
            changed = conn.execute(
                "SELECT COUNT(*) FROM schedules WHERE start_time != '' OR end_date != '' "
                "OR repeat_rule != '' OR repeat_until != '' OR repeat_skip != '' "
                "OR alarm_before IS NOT NULL").fetchone()[0]
        if changed:
            raise ValueError("업그레이드 뒤 새 칸이 기본값이 아닙니다.")
        snapshot = db.APP_DIR / "backups" / "calendar_pre_v18_v17.db"
        if not snapshot.is_file():
            raise ValueError("마이그레이션 전 스냅샷이 없습니다.")
        result["pre_snapshot"] = _original_columns_snapshot(snapshot)
        result["salt_sha256"] = file_hash(security.SALT_FILE)
```

(3) `scenario()`의 준비 부분. 찾을 원문:

```python
    before = None
    if name != "fresh":
        before = data_step("seed", data_root, folder / "before.json")
```

바꿀 코드:

```python
    before = None
    if name == "upgrade":
        before = data_step("seed_v17", data_root, folder / "before.json")
    elif name != "fresh":
        before = data_step("seed", data_root, folder / "before.json")
```

(4) `scenario()`의 정상 시작 검사. 찾을 원문:

```python
    else:
        after = data_step("inspect", data_root, folder / "after.json")
```

바꿀 코드:

```python
    else:
        if name == "upgrade":
            after = data_step("inspect_upgrade", data_root, folder / "after.json")
            if after["tables"] != before["tables"]:
                raise ValueError("업그레이드가 기존 값을 바꿨습니다.")
            if after["pre_snapshot"] != {"tables": before["tables"], "version": 17}:
                raise ValueError("마이그레이션 전 스냅샷이 원본과 다릅니다.")
            if after["salt_sha256"] != before["salt_sha256"]:
                raise ValueError("업그레이드가 salt를 바꿨습니다.")
            result["data"] = after
            return result
        after = data_step("inspect", data_root, folder / "after.json")
```

(5) `main()`의 `for name in ("fresh", "existing", "blocked"):` → `for name in ("fresh", "existing", "blocked", "upgrade"):`

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_release_smoke.py tests/test_verify.py -q`
Expected: PASS

- [ ] **Step 5: 1부 점검 — 데이터 프로필**

Run: `.venv/Scripts/python.exe tools/verify.py data`
Expected: `passed` (실행 ID를 작업 기록 '검증 증거'에 적는다)

- [ ] **Step 6: 커밋**

```bash
git add tools/smoke_release.py tests/test_release_smoke.py docs/work/2026-10-16-v4.1-schedule-time-repeat-period.md
git commit -m "test: 릴리스 격리 실행에 v17 데이터 업그레이드 시나리오 추가

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## 2부 — 화면·알림·릴리스 (Task 8~17)

### Task 8: 세부 설정 부품 모듈(시계 버튼·세부 카드·작은 달력·알약)

**Files:**
- Create: `ui_schedule_options.py`
- Modify: `ui_schedule_emoji.py` (지름·`popup_position`을 새 모듈에서 다시 내보내기)
- Test: `tests/test_ui_schedule_options.py` (새, 메인 창 없이 부품만)

**Interfaces:**
- Consumes: `schedule_rules`(Task 1~3), `holidays.is_holiday`, `popup_border_fix.remove_dwm_border`
- Produces (`ui_schedule_options`)
  - 상수: `SCHEDULE_CONTROL_DIAMETER=22`, `SHADOW_MARGIN=16`, `CARD_WIDTH=330`, `CARD_QSS`(카드 범위 QSS)
  - 그리기: `popup_position(anchor, size, available)->QPoint`(이모지 모듈에서 옮김), `draw_icon(painter, name, rect, color)`, `icon_pixmap(name, size, color, device_pixel_ratio=1.0)->QPixmap`
    - 아이콘 이름: `clock`·`bell`·`repeat`·`calendar`·`lock`·`x`(그 밖은 `ValueError`)
  - 라벨: `ElidePaintMixin`(text()는 전체, 그릴 때만 말줄임·PlainText), `ElidedLabel(text, parent)`
  - `ScheduleOptionsButton(edit, can_edit, parent)`
    - 신호: `options_changed(object)`(카드에서 바뀐 값), `popup_closed()`
    - 메서드: `options()`, `start_date()`, `set_context(start, occurrence="")`(옛 형식 날짜면 버튼 끔), `set_options(options)`(신호 없음), `open_popup()`, `close_popup()`
    - 속성: `_popup`(열린 카드 또는 None)
  - `ScheduleOptionsPopup(options, start, occurrence="", parent)`
    - 신호: `options_changed(object)`, `dismissed(bool)`, `size_changed()`
    - 칩·위젯 속성(시험용): `all_day_chip`·`timed_chip`·`time_edit`·`timed_alarm_chips[값]`·`all_day_alarm_chips[값]`·`one_day_chip`·`many_days_chip`·`period_caption`·`period_picker`·`period_note`·`repeat_chips[규칙]`·`repeat_caption`·`repeat_note`·`series_note`·`until_row`·`forever_chip`·`until_chip`·`until_caption`·`until_picker`·`clear_button`·`done_button`·`card`
  - `MiniMonthPicker`: 신호 `date_picked(str)`, `set_state(month=, lower=, upper=, range_start=, selected=)`, `show_month(date)`, `button_for(iso)`, `prev_button`·`next_button`·`title_label`
  - `ScheduleOptionsPills`: 신호 `open_requested()`·`clear_requested(str kind)`(kind: `time`·`alarm`·`period`·`repeat`), `set_state(start, options)`, `visible_texts()`, `pills[kind]`(`clear_rect()`)

- [ ] **Step 1: 실패하는 시험을 쓴다** — `tests/test_ui_schedule_options.py` (새로 만든다)

```python
"""v4.1 세부 설정 부품(아이콘·말줄임 라벨·시계 버튼·세부 카드·작은 달력·알약) 회귀. 합성 값만 쓴다."""
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRect, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLineEdit, QPushButton, QWidget
from shiboken6 import isValid

import ui_schedule_emoji
import ui_schedule_options
from schedule_rules import ScheduleOptions
from ui_schedule_options import (
    CARD_WIDTH, ElidedLabel, ScheduleOptionsButton, ScheduleOptionsPills, ScheduleOptionsPopup,
    icon_pixmap, popup_position,
)


@pytest.fixture(autouse=True)
def _app(qapp):
    """QPixmap·QWidget을 만들기 전에 QApplication이 있어야 한다(없으면 프로세스가 멈춘다)."""
    return qapp


class Host(QWidget):
    """입력칸 + 시계 버튼 + 알약만 둔 작은 창(메인 창 없이 부품만 시험한다)."""

    def __init__(self, start="2026-10-15"):
        super().__init__()
        layout = QHBoxLayout(self)
        self.allowed = True
        self.edit = QLineEdit(self)
        self.button = ScheduleOptionsButton(self.edit, lambda: self.allowed, self)
        self.button.set_context(start)
        self.pills = ScheduleOptionsPills(self)
        layout.addWidget(self.button)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.pills)
        self.button.options_changed.connect(
            lambda options: self.pills.set_state(self.button.start_date(), options))


@pytest.fixture
def host(qtbot):
    widget = Host()
    qtbot.addWidget(widget)
    widget.resize(520, 60)
    widget.show()
    widget.activateWindow()
    assert QTest.qWaitForWindowExposed(widget)
    assert QTest.qWaitForWindowActive(widget)
    return widget


def open_card(qtbot, button):
    qtbot.mouseClick(button, Qt.LeftButton)
    qtbot.waitUntil(lambda: button._popup is not None and button._popup.isVisible())
    assert QTest.qWaitForWindowExposed(button._popup)
    return button._popup


def click(qtbot, widget):
    qtbot.mouseClick(widget, Qt.LeftButton)
    QApplication.processEvents()


def ink(image, predicate):
    return [(x, y) for y in range(image.height()) for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 0 and predicate(image.pixelColor(x, y))]


@pytest.mark.parametrize("ratio", [1.0, 1.25, 1.5])
@pytest.mark.parametrize("name", ["clock", "bell", "repeat", "calendar", "lock", "x"])
def test_icons_are_drawn_without_image_files(name, ratio):
    image = icon_pixmap(name, 12, "#94A3B8", ratio).toImage()
    assert image.width() == round(12 * ratio)
    assert ink(image, lambda color: True)


def test_unknown_icon_is_rejected():
    with pytest.raises(ValueError):
        icon_pixmap("unknown", 12, "#000000")


def test_emoji_module_reexports_moved_names():
    assert ui_schedule_emoji.SCHEDULE_CONTROL_DIAMETER == ui_schedule_options.SCHEDULE_CONTROL_DIAMETER == 22
    assert ui_schedule_emoji.popup_position is ui_schedule_options.popup_position


@pytest.mark.parametrize("anchor", [QRect(-1900, 10, 26, 26), QRect(-30, 1040, 26, 26)])
def test_popup_position_stays_on_negative_coordinate_monitor(anchor):
    available = QRect(-1920, 0, 1920, 1080)
    size = QSize(330, 480)
    assert available.contains(QRect(popup_position(anchor, size, available), size))


def test_elided_label_keeps_full_plain_text_and_shrinks(qtbot):
    text = "<b>굵게 보이면 안 됨</b> " + "긴 글 " * 40
    label = ElidedLabel(text)
    qtbot.addWidget(label)
    label.resize(80, 20)
    label.show()
    assert label.text() == text
    assert label.textFormat() == Qt.PlainText
    assert label.minimumSizeHint().width() == 0
    assert not label.grab().isNull()


def test_clock_button_turns_blue_with_dot_when_set(host):
    blue = lambda color: color.blue() > 180 and color.red() < 90  # noqa: E731
    assert host.button.size() == QSize(26, 26)
    assert not ink(host.button.grab().toImage(), blue)
    host.button.set_options(ScheduleOptions(start_time="09:00"))
    assert ink(host.button.grab().toImage(), blue)
    assert "09:00" in host.button.toolTip()


def test_chips_change_options_and_pills_immediately(qtbot, host):
    card = open_card(qtbot, host.button)
    click(qtbot, card.timed_chip)
    assert host.button.options().start_time == "09:00"
    assert card.time_edit.hasFocus()
    card.time_edit.selectAll()
    qtbot.keyClicks(card.time_edit, "1430")
    assert host.button.options().start_time == "09:00"  # Enter 전에는 반영하지 않는다.
    qtbot.keyClick(card.time_edit, Qt.Key_Return)
    assert host.button.options().start_time == "14:30"
    assert card.isVisible()
    click(qtbot, card.timed_alarm_chips[10])
    click(qtbot, card.repeat_chips["weekly"])
    assert card.repeat_caption.text() == "매주 목요일"
    assert host.button.options() == ScheduleOptions(start_time="14:30", repeat_rule="weekly", alarm_before=10)
    assert host.pills.visible_texts() == ["14:30 · 10분 전", "매주 목"]
    click(qtbot, card.all_day_chip)
    assert host.button.options() == ScheduleOptions(repeat_rule="weekly")
    assert card.all_day_alarm_box.isVisible() and not card.timed_alarm_box.isVisible()
    click(qtbot, card.all_day_alarm_chips[1440])
    assert host.pills.visible_texts() == ["하루 전 9시", "매주 목"]


@pytest.mark.parametrize("typed", ["2460", "9:5", "abc"])
def test_invalid_time_marks_field_and_keeps_last_value(qtbot, host, typed):
    card = open_card(qtbot, host.button)
    click(qtbot, card.timed_chip)
    card.time_edit.selectAll()
    qtbot.keyClicks(card.time_edit, typed)
    assert card.time_edit.property("invalid") is True
    assert host.button.options().start_time == "09:00"
    qtbot.keyClick(card.time_edit, Qt.Key_Return)
    assert card.time_edit.text() == "09:00"
    assert card.time_edit.property("invalid") is False


def test_typed_time_is_applied_when_card_closes(qtbot, host):
    card = open_card(qtbot, host.button)
    click(qtbot, card.timed_chip)
    card.time_edit.selectAll()
    qtbot.keyClicks(card.time_edit, "930")
    click(qtbot, card.done_button)
    assert host.button.options().start_time == "09:30"


def test_period_and_repeat_exclude_each_other(qtbot, host):
    card = open_card(qtbot, host.button)
    click(qtbot, card.many_days_chip)
    assert host.button.options().end_date == "2026-10-16"
    assert [rule for rule, chip in card.repeat_chips.items() if chip.isEnabled()] == [""]
    assert card.repeat_note.isVisible()
    click(qtbot, card.one_day_chip)
    assert all(chip.isEnabled() for chip in card.repeat_chips.values())
    click(qtbot, card.repeat_chips["daily"])
    assert not card.many_days_chip.isEnabled()
    assert card.period_note.isVisible()
    assert card.until_row.isVisible()


def test_mini_month_limits_range_and_picks_end(qtbot, host):
    card = open_card(qtbot, host.button)
    click(qtbot, card.many_days_chip)
    picker = card.period_picker
    assert picker.isVisible() and not card.until_picker.isVisible()
    assert not picker.button_for("2026-10-15").isEnabled()  # 시작일은 고정
    assert picker.button_for("2026-10-15").property("role") == "end"
    assert picker.button_for("2026-10-16").property("role") == "end"
    click(qtbot, picker.button_for("2026-10-23"))
    assert host.button.options().end_date == "2026-10-23"
    assert picker.button_for("2026-10-20").property("role") == "in"
    assert card.period_caption.text().startswith("10월 15일(목) ~ 23일(금) · 9일")
    picker.show_month(picker._month.replace(year=2027))  # 365일 경계
    assert picker.button_for("2027-10-15").isEnabled()
    assert not picker.button_for("2027-10-16").isEnabled()
    assert host.pills.visible_texts() == ["~10.23 · 9일"]


def test_until_picker_defaults_to_one_month_and_toggles(qtbot):
    host = Host(start="2026-01-31")
    qtbot.addWidget(host)
    host.show()
    card = open_card(qtbot, host.button)
    click(qtbot, card.repeat_chips["monthly"])
    assert card.repeat_caption.text() == "매월 31일 (없는 달은 마지막 날)"
    click(qtbot, card.until_chip)
    assert host.button.options().repeat_until == "2026-02-28"
    assert card.until_picker.isVisible()
    assert card.until_picker.title_label.text() == "2026년 2월"
    click(qtbot, card.until_picker.prev_button)
    assert not card.until_picker.button_for("2026-01-30").isEnabled()
    assert card.until_picker.button_for("2026-01-31").isEnabled()
    click(qtbot, card.until_caption)
    assert not card.until_picker.isVisible()
    click(qtbot, card.forever_chip)
    assert host.button.options() == ScheduleOptions(repeat_rule="monthly")


def test_clear_all_resets_every_part(qtbot, host):
    host.button.set_options(ScheduleOptions(start_time="10:00", repeat_rule="daily",
                                            repeat_until="2026-12-31", alarm_before=60))
    card = open_card(qtbot, host.button)
    click(qtbot, card.clear_button)
    assert host.button.options() == ScheduleOptions()
    assert host.pills.isHidden()


@pytest.mark.parametrize("state", [
    ScheduleOptions(),
    ScheduleOptions(start_time="09:00", alarm_before=1440),
    ScheduleOptions(end_date="2026-10-17"),
    ScheduleOptions(repeat_rule="monthly", repeat_until="2026-12-15"),
])
def test_card_width_fits_screen_without_clipped_chips(qtbot, host, state):
    host.button.set_options(state)
    card = open_card(qtbot, host.button)
    if state.end_date:
        click(qtbot, card.period_caption)
    if state.repeat_until:
        click(qtbot, card.until_caption)
    QApplication.processEvents()
    assert card.card.width() == CARD_WIDTH
    assert card.screen().availableGeometry().contains(card.card.geometry().translated(card.pos()))
    chips = [chip for chip in card.findChildren(QPushButton) if chip.property("segment") and chip.isVisible()]
    assert chips
    for chip in chips:
        assert chip.width() >= chip.sizeHint().width(), chip.text()
        assert card.card.rect().contains(chip.mapTo(card.card, chip.rect().bottomRight()))
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        name = "schedule-options-card-" + ("default" if state.is_default else "set") + ".png"
        assert card.grab().save(str(Path(appdata).parent / name))


def test_escape_restores_focus_and_keeps_value(qtbot, host):
    card = open_card(qtbot, host.button)
    click(qtbot, card.repeat_chips["daily"])
    qtbot.keyClick(card, Qt.Key_Escape)
    qtbot.waitUntil(lambda: host.edit.hasFocus())
    assert host.button.options() == ScheduleOptions(repeat_rule="daily")


def test_keyboard_opens_one_card_at_a_time(qtbot, host):
    button = host.button
    for _ in range(6):
        button.setFocus()
        qtbot.keyClick(button, Qt.Key_Return)
        qtbot.waitUntil(lambda: button._popup is not None and button._popup.isVisible())
        popup = button._popup
        button.open_popup()
        assert button._popup is popup
        qtbot.keyClick(popup, Qt.Key_Escape)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        assert not isValid(popup)
    assert host.findChildren(ScheduleOptionsPopup) == []


def test_closed_card_ignores_late_change_and_disallowed_open(qtbot, host):
    card = open_card(qtbot, host.button)
    host.button.close_popup()
    assert not card.isVisible()
    card.options_changed.emit(ScheduleOptions(start_time="11:00"))
    assert host.button.options() == ScheduleOptions()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not isValid(card)
    host.allowed = False  # 잠금·트레이 숨김
    host.button.open_popup()
    assert host.button._popup is None


def test_legacy_date_disables_button(qtbot):
    host = Host(start="2026-7-1")
    qtbot.addWidget(host)
    host.show()
    assert not host.button.isEnabled()
    host.button.open_popup()
    assert host.button._popup is None
    host.button.set_context("2026-07-01")
    assert host.button.isEnabled()


def test_pills_texts_and_signals(qtbot, host):
    opened, cleared = [], []
    host.pills.open_requested.connect(lambda: opened.append(True))
    host.pills.clear_requested.connect(cleared.append)
    host.pills.set_state("2026-10-21", ScheduleOptions(start_time="15:00", end_date="2026-10-23", alarm_before=10))
    QApplication.processEvents()
    assert host.pills.visible_texts() == ["15:00 · 10분 전", "~10.23 · 3일"]
    time_pill = host.pills.pills["time"]
    assert time_pill.height() == 22 and time_pill.width() <= 150
    qtbot.mouseClick(time_pill, Qt.LeftButton, pos=time_pill.clear_rect().center().toPoint())
    qtbot.mouseClick(host.pills.pills["period"], Qt.LeftButton, pos=QPoint(14, 11))
    assert cleared == ["time"] and opened == [True]
    host.pills.set_state("2026-10-21", ScheduleOptions())
    assert host.pills.isHidden()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_schedule_options.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ui_schedule_options'`

- [ ] **Step 3: 모듈을 만들고 이모지 모듈이 옮긴 이름을 다시 내보내게 한다**

세부 카드는 이모지 팝업과 같은 수명 규칙을 따른다. 칩 `clicked(bool)`의 `checked`가 기본값 인자를 덮어쓰지 않도록 칩·글자 버튼은 `lambda checked=False: slot()`으로 연결한다(시험에서 실제로 걸린 문제). 시각 입력칸은 입력 중에는 검사만 하고 Enter·다른 곳 누르기·닫기 때 반영한다(입력 중간값 `246`→`02:46`이 저장되지 않게).

(1) `ui_schedule_options.py`를 새로 만든다(파일 전체).

```python
"""일정 세부 설정(시각·알림·기간·반복) 화면 부품 (v4.1).

입력줄과 더블클릭 편집기가 함께 쓴다. 카드는 이모지 팝업과 같은 수명 규칙을 따른다:
한 번에 하나, 닫히면 deleteLater, 늦게 도착한 신호는 무시, 포커스 복원은 버튼 소유 타이머.
카드 안에서는 다른 팝업(드롭다운·QCalendarWidget·메뉴)을 띄우지 않는다.
"""
import calendar
from dataclasses import replace
from datetime import date, timedelta

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

import holidays
import schedule_rules as rules
from popup_border_fix import remove_dwm_border
from schedule_rules import ScheduleOptions

SCHEDULE_CONTROL_DIAMETER = 22
SHADOW_MARGIN = 16
CARD_WIDTH = 330
ICON_COLOR = "#475569"
ACTIVE_COLOR = "#2563EB"
TIMED_ALARM_CHOICES = ((None, "없음"), (0, "정시"), (10, "10분 전"),
                       (30, "30분 전"), (60, "1시간 전"), (1440, "하루 전"))
ALLDAY_ALARM_CHOICES = ((None, "없음"), (0, "당일 오전 9시"), (1440, "하루 전 오전 9시"))
REPEAT_CHOICES = (("", "안 함"), ("daily", "매일"), ("weekdays", "평일"),
                  ("weekly", "매주"), ("monthly", "매월"), ("yearly", "매년"))
REPEAT_ONLY_ONE_DAY = "반복 일정은 하루만 고를 수 있습니다"
PERIOD_NO_REPEAT = "여러 날 일정은 반복할 수 없습니다"

CARD_QSS = (
    "QFrame#scheduleOptionsCard{background:#FFFFFF;border:1px solid #D9E1EC;border-radius:12px;}"
    "#scheduleOptionsCard QLabel{background:transparent;}"
    "#scheduleOptionsCard QLabel#scheduleOptionsTitle{color:#172B4D;font-size:13px;font-weight:bold;}"
    "#scheduleOptionsCard QLabel#scheduleOptionsRowLabel{color:#64748B;font-size:12px;}"
    "#scheduleOptionsCard QLabel#scheduleOptionsNote{color:#B45309;font-size:11px;}"
    "#scheduleOptionsCard QLabel#scheduleOptionsHint{color:#94A3B8;font-size:11px;}"
    "#scheduleOptionsCard QPushButton[segment=\"true\"]{background:#FFFFFF;border:1px solid #CBD5E1;"
    "border-radius:13px;color:#334155;font-size:12px;padding:0px 9px;}"
    "#scheduleOptionsCard QPushButton[segment=\"true\"]:hover{background:#F8FAFC;}"
    "#scheduleOptionsCard QPushButton[segment=\"true\"]:checked{background:#EFF6FF;"
    "border:1px solid #2563EB;color:#1D4ED8;font-weight:bold;}"
    "#scheduleOptionsCard QPushButton[segment=\"true\"]:disabled{background:#F8FAFC;"
    "border:1px solid #E2E8F0;color:#A3ACB9;}"
    "#scheduleOptionsCard QPushButton[segment=\"true\"]:focus{border:2px solid #2563EB;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsCaption{background:transparent;border:0px;"
    "color:#334155;font-size:12px;text-align:left;padding:0px;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsCaption:hover,"
    "#scheduleOptionsCard QPushButton#scheduleOptionsCaption:focus{color:#1D4ED8;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsClear{background:transparent;border:0px;"
    "color:#64748B;font-size:12px;padding:0px 2px;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsClear:hover,"
    "#scheduleOptionsCard QPushButton#scheduleOptionsClear:focus{color:#B91C1C;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsDone{background:#2563EB;border:1px solid #2563EB;"
    "border-radius:6px;color:#FFFFFF;font-size:12px;font-weight:bold;padding:0px 14px;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsDone:hover{background:#1D4ED8;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsDone:focus{border:2px solid #1E3A8A;}"
    "#scheduleOptionsCard QLineEdit#scheduleOptionsTime{background:#FFFFFF;border:1px solid #CBD5E1;"
    "border-radius:6px;color:#172B4D;font-size:12px;padding:0px 6px;}"
    "#scheduleOptionsCard QLineEdit#scheduleOptionsTime:focus{border:2px solid #2563EB;}"
    "#scheduleOptionsCard QLineEdit#scheduleOptionsTime[invalid=\"true\"]{border:2px solid #DC2626;}"
    "#scheduleOptionsCard QLabel#scheduleMiniTitle{color:#172B4D;font-size:12px;font-weight:bold;}"
    "#scheduleOptionsCard QLabel#scheduleMiniWeekday{color:#64748B;font-size:11px;}"
    "#scheduleOptionsCard QLabel#scheduleMiniWeekday[tone=\"sun\"]{color:#D32F2F;}"
    "#scheduleOptionsCard QLabel#scheduleMiniWeekday[tone=\"sat\"]{color:#1565C0;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniNav{background:transparent;border:0px;"
    "border-radius:4px;color:#475569;font-size:14px;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniNav:hover,"
    "#scheduleOptionsCard QPushButton#scheduleMiniNav:focus{background:#EFF6FF;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay{background:transparent;border:0px;"
    "border-radius:4px;color:#1A1A1A;font-size:11px;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay[tone=\"sun\"]{color:#D32F2F;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay[tone=\"sat\"]{color:#1565C0;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay:hover{background:#EFF6FF;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay:focus{border:1px solid #2563EB;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay[role=\"in\"]{background:#DBEAFE;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay[role=\"end\"]{background:#2563EB;"
    "color:#FFFFFF;font-weight:bold;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay:disabled{background:transparent;color:#CBD5E1;}"
)


def popup_position(anchor, size, available) -> QPoint:
    """버튼 아래(공간 부족 시 위)에 놓고 음수 좌표 작업 영역도 보존한다."""
    x = anchor.left()
    y = anchor.bottom() + 1
    if y + size.height() > available.bottom() + 1:
        y = anchor.top() - size.height()
    return QPoint(
        max(available.left(), min(x, available.right() + 1 - size.width())),
        max(available.top(), min(y, available.bottom() + 1 - size.height())),
    )


def draw_icon(painter: QPainter, name: str, rect: QRectF, color) -> None:
    """작은 선 아이콘을 rect(정사각형 권장) 안에 그린다. 그림 파일 없이 QPainter만 쓴다."""
    size = min(rect.width(), rect.height())
    left = rect.x() + (rect.width() - size) / 2
    top = rect.y() + (rect.height() - size) / 2

    def at(fx: float, fy: float) -> QPointF:
        return QPointF(left + fx * size, top + fy * size)

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(color), max(1.0, size / 11), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    if name == "clock":
        painter.drawEllipse(QRectF(at(0.08, 0.08), at(0.92, 0.92)))
        painter.drawLine(at(0.5, 0.5), at(0.5, 0.25))
        painter.drawLine(at(0.5, 0.5), at(0.69, 0.61))
    elif name == "bell":
        path = QPainterPath(at(0.17, 0.72))
        path.cubicTo(at(0.3, 0.6), at(0.24, 0.16), at(0.5, 0.16))
        path.cubicTo(at(0.76, 0.16), at(0.7, 0.6), at(0.83, 0.72))
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(at(0.42, 0.86), at(0.58, 0.86))
    elif name == "repeat":
        top_path = QPainterPath(at(0.2, 0.58))
        top_path.lineTo(at(0.2, 0.32))
        top_path.lineTo(at(0.76, 0.32))
        painter.drawPath(top_path)
        painter.drawLine(at(0.64, 0.2), at(0.77, 0.32))
        painter.drawLine(at(0.64, 0.44), at(0.77, 0.32))
        bottom_path = QPainterPath(at(0.8, 0.42))
        bottom_path.lineTo(at(0.8, 0.68))
        bottom_path.lineTo(at(0.24, 0.68))
        painter.drawPath(bottom_path)
        painter.drawLine(at(0.36, 0.56), at(0.23, 0.68))
        painter.drawLine(at(0.36, 0.8), at(0.23, 0.68))
    elif name == "calendar":
        painter.drawRoundedRect(QRectF(at(0.12, 0.2), at(0.88, 0.88)), size * 0.1, size * 0.1)
        painter.drawLine(at(0.12, 0.42), at(0.88, 0.42))
        painter.drawLine(at(0.34, 0.08), at(0.34, 0.28))
        painter.drawLine(at(0.66, 0.08), at(0.66, 0.28))
    elif name == "lock":
        painter.drawRoundedRect(QRectF(at(0.2, 0.46), at(0.8, 0.88)), size * 0.08, size * 0.08)
        painter.drawArc(QRectF(at(0.3, 0.14), at(0.7, 0.62)), 0, 180 * 16)
        painter.drawLine(at(0.3, 0.38), at(0.3, 0.46))
        painter.drawLine(at(0.7, 0.38), at(0.7, 0.46))
    elif name == "x":
        painter.drawLine(at(0.28, 0.28), at(0.72, 0.72))
        painter.drawLine(at(0.72, 0.28), at(0.28, 0.72))
    else:
        painter.restore()
        raise ValueError(f"알 수 없는 아이콘입니다: {name}")
    painter.restore()


def icon_pixmap(name: str, size: int, color, device_pixel_ratio: float = 1.0) -> QPixmap:
    """draw_icon을 장치 배율에 맞춘 투명 QPixmap으로 만든다."""
    ratio = max(1.0, float(device_pixel_ratio))
    pixmap = QPixmap(round(size * ratio), round(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    try:
        draw_icon(painter, name, QRectF(0, 0, size, size), color)
    finally:
        painter.end()
    return pixmap


class ElidePaintMixin:
    """text()에는 전체 글자를 두고 그릴 때만 오른쪽을 말줄임한다(글자 그대로, 서식 해석 없음)."""

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, rect.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        painter.drawText(rect, self.alignment(), text)


class ElidedLabel(ElidePaintMixin, QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)


class ScheduleOptionsButton(QPushButton):
    """시계 버튼. 세부 설정 값을 보관하고 카드를 연다(입력줄·편집기 공용)."""

    options_changed = Signal(object)
    popup_closed = Signal()

    def __init__(self, edit: QLineEdit, can_edit, parent=None):
        super().__init__(parent)
        self.edit = edit
        self._can_edit = can_edit
        self._popup = None
        self._options = ScheduleOptions()
        self._start = ""
        self._occurrence = ""
        self.setFixedSize(26, 26)
        self.setAccessibleName("일정 세부 설정")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton{color:#475569;background:transparent;"
            "border:1px solid transparent;border-radius:5px;}"
            "QPushButton:hover,QPushButton:focus{background:#EFF6FF;border-color:#2563EB;}"
        )
        self._restore_timer = QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self._restore_focus)
        self.clicked.connect(self.open_popup)
        self._update_tooltip()

    def options(self) -> ScheduleOptions:
        return self._options

    def start_date(self) -> str:
        return self._start

    def set_context(self, start: str, occurrence: str = "") -> None:
        """기준 날짜(반복·기간의 시작)와 지금 보고 있는 날짜를 정한다.

        형식이 다른 옛 날짜(예: 2026-7-1)의 일정에는 세부 설정을 둘 수 없으므로 버튼을 끈다.
        """
        self._start = start
        self._occurrence = occurrence or start
        try:
            rules.parse_date(start)
            usable = True
        except ValueError:
            usable = False
        self.setEnabled(usable)
        self._update_tooltip()

    def set_options(self, options: ScheduleOptions) -> None:
        """밖에서 값을 바꾼다(알약 ×·날짜 이동·추가 성공). 신호는 내지 않는다."""
        self._options = options
        self._update_tooltip()
        self.update()
        if self._popup is not None:
            self._popup.set_options(options)

    def _update_tooltip(self) -> None:
        if not self.isEnabled():
            self.setToolTip("날짜 형식이 달라 세부 설정을 쓸 수 없는 일정입니다")
            return
        summary = ""
        if self._start and not self._options.is_default:
            try:
                summary = rules.options_summary(self._start, self._options)
            except ValueError:
                summary = ""
        self.setToolTip(f"세부 설정: {summary}" if summary else "시각·알림·기간·반복")

    def paintEvent(self, event):
        # 클릭/포커스 영역은 26px, 원의 외경은 색 원·스마일과 같은 22px.
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        active = not self._options.is_default
        if not self.isEnabled():
            color = QColor("#94A3B8")
        else:
            color = QColor(ACTIVE_COLOR if active else ICON_COLOR)
        diameter = SCHEDULE_CONTROL_DIAMETER
        x, y = (self.width() - diameter) / 2, (self.height() - diameter) / 2
        painter.setPen(QPen(color, 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(x + 0.5, y + 0.5, diameter - 1, diameter - 1))
        center = QPointF(x + diameter / 2, y + diameter / 2)
        painter.setPen(QPen(color, 1.4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(center, QPointF(center.x(), y + 6))
        painter.drawLine(center, QPointF(x + 15.5, center.y() + 2.5))
        if active:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(QRectF(x + diameter - 7, y - 1, 8, 8))
            painter.setBrush(color)
            painter.drawEllipse(QRectF(x + diameter - 6, y, 6, 6))

    def open_popup(self) -> None:
        if (not self._can_edit() or not self.isVisible() or not self.isEnabled()
                or self._popup is not None):
            return
        popup = ScheduleOptionsPopup(self._options, self._start, self._occurrence, self)
        self._popup = popup
        popup.options_changed.connect(lambda options: self._on_popup_changed(popup, options))
        popup.dismissed.connect(lambda restore: self._dismiss(popup, restore))
        popup.size_changed.connect(lambda: self._place(popup))
        self._place(popup)
        popup.show()
        remove_dwm_border(popup)
        popup.focus_first()

    def _place(self, popup) -> None:
        if self._popup is not popup:
            return
        anchor = self.rect().translated(self.mapToGlobal(QPoint(0, 0)))
        screen = QApplication.screenAt(anchor.center()) or self.screen()
        margin = popup.shadow_margin
        card = popup.size() - QSize(2 * margin, 2 * margin)
        point = popup_position(anchor, card, screen.availableGeometry())
        popup.move(point - QPoint(margin, margin))

    def _on_popup_changed(self, popup, options: ScheduleOptions) -> None:
        if self._popup is not popup or not self._can_edit():
            return
        self._options = options
        self._update_tooltip()
        self.update()
        self.options_changed.emit(options)

    def _dismiss(self, popup, restore: bool) -> None:
        if self._popup is not popup:
            return
        self._popup = None
        popup.deleteLater()
        if restore:
            self._restore_timer.start(0)
        self.popup_closed.emit()

    def _restore_focus(self) -> None:
        if self._can_edit() and self.edit.isVisible() and self._popup is None:
            self.edit.setFocus(Qt.PopupFocusReason)

    def close_popup(self) -> None:
        self._restore_timer.stop()
        if self._popup is not None:
            popup = self._popup
            self._popup = None  # 닫히면서 생기는 포커스 복원과 늦은 변경을 무효화한다.
            popup.close()
            popup.deleteLater()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Down):
            self.open_popup()
        else:
            super().keyPressEvent(event)


class MiniMonthPicker(QWidget):
    """카드 안에 펼치는 작은 달력(일요일 시작). 따로 팝업을 띄우지 않는다."""

    date_picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scheduleMiniMonth")
        self._month = date.today().replace(day=1)
        self._lower = None
        self._upper = None
        self._range_start = None
        self._selected = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(2)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        self.prev_button = self._nav_button("‹", "이전 달", -1)
        self.title_label = QLabel(self)
        self.title_label.setObjectName("scheduleMiniTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.next_button = self._nav_button("›", "다음 달", 1)
        head.addWidget(self.prev_button)
        head.addWidget(self.title_label, 1)
        head.addWidget(self.next_button)
        layout.addLayout(head)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(2)
        grid.setVerticalSpacing(1)
        for col, name in enumerate("일월화수목금토"):
            label = QLabel(name, self)
            label.setObjectName("scheduleMiniWeekday")
            label.setAlignment(Qt.AlignCenter)
            label.setProperty("tone", "sun" if col == 0 else "sat" if col == 6 else "")
            grid.addWidget(label, 0, col)
        self.day_buttons = []
        for index in range(42):
            button = QPushButton(self)
            button.setObjectName("scheduleMiniDay")
            button.setFixedSize(30, 24)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, i=index: self._pick(i))
            grid.addWidget(button, 1 + index // 7, index % 7)
            self.day_buttons.append(button)
        layout.addLayout(grid)

    def _nav_button(self, text: str, name: str, step: int) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName("scheduleMiniNav")
        button.setFixedSize(26, 22)
        button.setAccessibleName(name)
        button.setToolTip(name)
        button.clicked.connect(lambda: self.show_month(rules.add_months(self._month, step)))
        return button

    def set_state(self, *, month: date, lower: date, upper: date | None,
                  range_start: date | None, selected: date | None) -> None:
        self._lower, self._upper = lower, upper
        self._range_start, self._selected = range_start, selected
        self.show_month(month)

    def show_month(self, month: date) -> None:
        self._month = month.replace(day=1)
        self.title_label.setText(f"{self._month.year}년 {self._month.month}월")
        first_col = (self._month.weekday() + 1) % 7  # 일요일 = 0
        days = calendar.monthrange(self._month.year, self._month.month)[1]
        for index, button in enumerate(self.day_buttons):
            number = index - first_col + 1
            if not 1 <= number <= days:
                button.setText("")
                button.setEnabled(False)
                button.setVisible(index < 35 or first_col + days > 35)
                button.setProperty("day", "")
                button.setProperty("role", "")
                button.setProperty("tone", "")
            else:
                day = self._month.replace(day=number)
                iso = day.isoformat()
                button.setVisible(True)
                button.setText(str(number))
                button.setProperty("day", iso)
                allowed = day >= self._lower and (self._upper is None or day <= self._upper)
                button.setEnabled(allowed)
                if day == self._selected or (self._range_start is not None and day == self._range_start):
                    role = "end"
                elif (self._range_start is not None and self._selected is not None
                      and self._range_start < day < self._selected):
                    role = "in"
                else:
                    role = ""
                button.setProperty("role", role)
                col = index % 7
                tone = "sun" if col == 0 or holidays.is_holiday(iso) else "sat" if col == 6 else ""
                button.setProperty("tone", tone)
                button.setAccessibleName(rules.korean_date(day))
            button.style().unpolish(button)
            button.style().polish(button)

    def button_for(self, iso: str) -> QPushButton | None:
        return next((b for b in self.day_buttons if b.property("day") == iso), None)

    def _pick(self, index: int) -> None:
        iso = self.day_buttons[index].property("day")
        if iso:
            self.date_picked.emit(iso)


class ScheduleOptionsPopup(QWidget):
    """세부 설정 카드. 칩을 누르는 즉시 값이 바뀌고(options_changed) Esc·바깥·완료는 닫기만 한다."""

    options_changed = Signal(object)
    dismissed = Signal(bool)
    size_changed = Signal()
    shadow_margin = SHADOW_MARGIN

    def __init__(self, options: ScheduleOptions, start: str, occurrence: str = "", parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName("scheduleOptionsPopup")
        self.setAccessibleName("일정 세부 설정")
        self.setWindowOpacity(1.0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 바깥의 원래 버튼 클릭이 재전달되어 곧바로 다시 열리는 것을 막는다.
        self.setAttribute(Qt.WA_NoMouseReplay)
        self._return_focus = False
        self._options = options
        self._start = start
        self._start_day = rules.parse_date(start)
        self._occurrence = occurrence or start
        self._was_repeat = bool(options.repeat_rule)
        self._picker_for = ""
        self._last_time = options.start_time or "09:00"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        self.card = QFrame(self)
        self.card.setObjectName("scheduleOptionsCard")
        self.card.setFixedWidth(CARD_WIDTH)
        self.card.setStyleSheet(CARD_QSS)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(24, 46, 76, 80))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("세부 설정", self.card)
        title.setObjectName("scheduleOptionsTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.clear_button = QPushButton("모두 지우기", self.card)
        self.clear_button.setObjectName("scheduleOptionsClear")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.setToolTip("시각·알림·기간·반복을 모두 기본값으로 되돌립니다")
        self.clear_button.clicked.connect(lambda: self._change(ScheduleOptions()))
        head.addWidget(self.clear_button)
        layout.addLayout(head)

        body = self._row(layout, "시각")
        line = QHBoxLayout()
        line.setSpacing(6)
        self.all_day_chip = self._chip("하루 종일", lambda: self._change(rules.with_start_time(self._options, "")))
        self.timed_chip = self._chip("시각", self._choose_timed)
        self.time_edit = QLineEdit(self.card)
        self.time_edit.setObjectName("scheduleOptionsTime")
        self.time_edit.setFixedSize(62, 26)
        self.time_edit.setPlaceholderText("09:00")
        self.time_edit.setAccessibleName("시작 시각")
        self.time_edit.setToolTip("0930·14:30처럼 입력하고 Enter")
        # 입력 중에는 검사만 하고(틀리면 빨간 테두리), Enter·다른 곳 누르기·닫기 때 반영한다.
        self.time_edit.textEdited.connect(self._on_time_edited)
        self.time_edit.editingFinished.connect(self._commit_time_text)
        line.addWidget(self.all_day_chip)
        line.addWidget(self.timed_chip)
        line.addWidget(self.time_edit)
        line.addStretch(1)
        body.addLayout(line)

        body = self._row(layout, "알림")
        self.timed_alarm_box = QWidget(self.card)
        grid = QGridLayout(self.timed_alarm_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self.timed_alarm_chips = {}
        for index, (value, text) in enumerate(TIMED_ALARM_CHOICES):
            chip = self._chip(text, lambda v=value: self._change(replace(self._options, alarm_before=v)))
            chip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            grid.addWidget(chip, index // 3, index % 3)
            self.timed_alarm_chips[value] = chip
        body.addWidget(self.timed_alarm_box)
        self.all_day_alarm_box = QWidget(self.card)
        row = QHBoxLayout(self.all_day_alarm_box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.all_day_alarm_chips = {}
        for value, text in ALLDAY_ALARM_CHOICES:
            chip = self._chip(text, lambda v=value: self._change(replace(self._options, alarm_before=v)))
            row.addWidget(chip)
            self.all_day_alarm_chips[value] = chip
        row.addStretch(1)
        body.addWidget(self.all_day_alarm_box)

        body = self._row(layout, "기간")
        line = QHBoxLayout()
        line.setSpacing(6)
        self.one_day_chip = self._chip("하루", lambda: self._change(replace(self._options, end_date="")))
        self.many_days_chip = self._chip("여러 날", self._choose_many_days)
        line.addWidget(self.one_day_chip)
        line.addWidget(self.many_days_chip)
        line.addStretch(1)
        body.addLayout(line)
        self.period_caption = self._caption(lambda: self._toggle_picker("period"))
        body.addWidget(self.period_caption)
        self.period_picker = MiniMonthPicker(self.card)
        self.period_picker.date_picked.connect(
            lambda iso: self._change(replace(self._options, end_date=iso)))
        body.addWidget(self.period_picker)
        self.period_note = self._note(REPEAT_ONLY_ONE_DAY)
        body.addWidget(self.period_note)

        body = self._row(layout, "반복")
        grid = QGridLayout()
        grid.setSpacing(6)
        self.repeat_chips = {}
        for index, (rule, text) in enumerate(REPEAT_CHOICES):
            chip = self._chip(text, lambda r=rule: self._change(rules.with_repeat(self._options, self._start, r)))
            chip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            grid.addWidget(chip, index // 3, index % 3)
            self.repeat_chips[rule] = chip
        body.addLayout(grid)
        self.repeat_caption = QLabel(self.card)
        self.repeat_caption.setTextFormat(Qt.PlainText)
        self.repeat_caption.setStyleSheet("color:#334155;font-size:12px;")
        body.addWidget(self.repeat_caption)
        self.repeat_note = self._note(PERIOD_NO_REPEAT)
        body.addWidget(self.repeat_note)
        self.series_note = self._note("")
        body.addWidget(self.series_note)

        self.until_row = QWidget(self.card)
        until_layout = QVBoxLayout(self.until_row)
        until_layout.setContentsMargins(0, 0, 0, 0)
        until_layout.setSpacing(0)
        body = self._row(until_layout, "끝", parent=self.until_row)
        line = QHBoxLayout()
        line.setSpacing(6)
        self.forever_chip = self._chip("계속", lambda: self._change(replace(self._options, repeat_until="")),
                                       parent=self.until_row)
        self.until_chip = self._chip("날짜까지", self._choose_until, parent=self.until_row)
        line.addWidget(self.forever_chip)
        line.addWidget(self.until_chip)
        line.addStretch(1)
        body.addLayout(line)
        self.until_caption = self._caption(lambda: self._toggle_picker("until"), parent=self.until_row)
        body.addWidget(self.until_caption)
        self.until_picker = MiniMonthPicker(self.until_row)
        self.until_picker.date_picked.connect(
            lambda iso: self._change(replace(self._options, repeat_until=iso)))
        body.addWidget(self.until_picker)
        layout.addWidget(self.until_row)

        foot = QHBoxLayout()
        hint = QLabel("Esc · 바깥을 누르면 닫힘", self.card)
        hint.setObjectName("scheduleOptionsHint")
        foot.addWidget(hint)
        foot.addStretch(1)
        self.done_button = QPushButton("완료", self.card)
        self.done_button.setObjectName("scheduleOptionsDone")
        self.done_button.setFixedHeight(28)
        self.done_button.setCursor(Qt.PointingHandCursor)
        self.done_button.clicked.connect(self.dismiss)
        foot.addWidget(self.done_button)
        layout.addLayout(foot)
        self._render()

    # ── 만들기 도우미 ──
    def _row(self, layout, name: str, parent=None) -> QVBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(name, parent or self.card)
        label.setObjectName("scheduleOptionsRowLabel")
        label.setFixedWidth(30)
        label.setFixedHeight(26)
        row.addWidget(label, 0, Qt.AlignTop)
        body = QVBoxLayout()
        body.setSpacing(6)
        row.addLayout(body, 1)
        layout.addLayout(row)
        return body

    def _chip(self, text: str, slot, parent=None) -> QPushButton:
        chip = QPushButton(text, parent or self.card)
        chip.setProperty("segment", True)
        chip.setCheckable(True)
        chip.setFixedHeight(26)
        chip.setCursor(Qt.PointingHandCursor)
        chip.setFocusPolicy(Qt.StrongFocus)
        # clicked(bool)의 checked가 기본값 인자를 덮어쓰지 않도록 인자 없이 부른다.
        chip.clicked.connect(lambda checked=False: slot())
        return chip

    def _caption(self, slot, parent=None) -> QPushButton:
        caption = QPushButton(parent or self.card)
        caption.setObjectName("scheduleOptionsCaption")
        caption.setCursor(Qt.PointingHandCursor)
        caption.setFlat(True)
        caption.clicked.connect(lambda checked=False: slot())
        return caption

    def _note(self, text: str) -> QLabel:
        note = QLabel(text, self.card)
        note.setObjectName("scheduleOptionsNote")
        note.setTextFormat(Qt.PlainText)
        note.setWordWrap(True)
        return note

    # ── 값 바꾸기 ──
    def options(self) -> ScheduleOptions:
        return self._options

    def set_options(self, options: ScheduleOptions) -> None:
        self._options = options
        self._render()

    def _change(self, options: ScheduleOptions) -> None:
        if options.is_default or not options.end_date:
            if self._picker_for == "period":
                self._picker_for = ""
        if not options.repeat_until and self._picker_for == "until":
            self._picker_for = ""
        if options == self._options:
            self._render()
            return
        self._options = options
        if options.start_time:
            self._last_time = options.start_time
        self._render()
        self.options_changed.emit(options)

    def _choose_timed(self) -> None:
        if not self._options.start_time:
            self._change(rules.with_start_time(self._options, self._last_time))
        else:
            self._render()
        self.time_edit.setFocus(Qt.OtherFocusReason)
        self.time_edit.selectAll()

    def _choose_many_days(self) -> None:
        if not self._options.end_date:
            end = (self._start_day + timedelta(days=1)).isoformat()
            self._picker_for = "period"
            self._change(replace(self._options, end_date=end))
        else:
            self._toggle_picker("period")

    def _choose_until(self) -> None:
        if not self._options.repeat_until:
            until = rules.add_months(self._start_day, 1).isoformat()
            self._picker_for = "until"
            self._change(replace(self._options, repeat_until=until))
        else:
            self._toggle_picker("until")

    def _toggle_picker(self, which: str) -> None:
        self._picker_for = "" if self._picker_for == which else which
        self._render()

    def _on_time_edited(self, text: str) -> None:
        try:
            rules.parse_time_input(text)
        except ValueError:
            self._set_time_invalid(bool(text.strip()))
            return
        self._set_time_invalid(False)

    def _commit_time_text(self) -> None:
        """입력칸 글자를 반영한다. 틀렸으면 마지막 올바른 값으로 되돌린다."""
        if not self._options.start_time:
            return
        try:
            value = rules.parse_time_input(self.time_edit.text())
        except ValueError:
            value = self._options.start_time
        self._set_time_invalid(False)
        self.time_edit.setText(value)
        if value != self._options.start_time:
            self._change(rules.with_start_time(self._options, value))

    def _set_time_invalid(self, invalid: bool) -> None:
        if bool(self.time_edit.property("invalid")) != invalid:
            self.time_edit.setProperty("invalid", invalid)
            self.time_edit.style().unpolish(self.time_edit)
            self.time_edit.style().polish(self.time_edit)

    # ── 그리기 ──
    def _render(self) -> None:
        options = self._options
        timed = bool(options.start_time)
        period = bool(options.end_date)
        repeat = bool(options.repeat_rule)
        self.all_day_chip.setChecked(not timed)
        self.timed_chip.setChecked(timed)
        self.time_edit.setVisible(timed)
        if timed and not self.time_edit.hasFocus():
            self.time_edit.setText(options.start_time)
        self.timed_alarm_box.setVisible(timed)
        self.all_day_alarm_box.setVisible(not timed)
        for value, chip in self.timed_alarm_chips.items():
            chip.setChecked(options.alarm_before == value)
        for value, chip in self.all_day_alarm_chips.items():
            chip.setChecked(options.alarm_before == value)
        self.one_day_chip.setChecked(not period)
        self.many_days_chip.setChecked(period)
        self.many_days_chip.setEnabled(not repeat)
        self.period_note.setVisible(repeat)
        self.period_caption.setVisible(period)
        if period:
            self.period_caption.setText(rules.period_caption(self._start, options.end_date) + "  ▾")
        show_period_picker = period and self._picker_for == "period"
        self.period_picker.setVisible(show_period_picker)
        if show_period_picker:
            end = rules.parse_date(options.end_date)
            self.period_picker.set_state(
                month=end, lower=self._start_day + timedelta(days=1),
                upper=self._start_day + timedelta(days=rules.MAX_SPAN_DAYS),
                range_start=self._start_day, selected=end)
        for rule, chip in self.repeat_chips.items():
            chip.setChecked(options.repeat_rule == rule)
            chip.setEnabled(not period or rule == "")
        self.repeat_note.setVisible(period)
        self.repeat_caption.setVisible(repeat)
        if repeat:
            self.repeat_caption.setText(rules.repeat_caption(self._start, options.repeat_rule))
        turned_off = self._was_repeat and not repeat and self._occurrence != self._start
        self.series_note.setVisible(turned_off)
        if turned_off:
            self.series_note.setText(
                f"반복을 끄면 첫 날짜({self._start_day.month}월 {self._start_day.day}일) 하루만 남습니다")
        self.until_row.setVisible(repeat)
        self.forever_chip.setChecked(not options.repeat_until)
        self.until_chip.setChecked(bool(options.repeat_until))
        self.until_caption.setVisible(bool(options.repeat_until))
        if options.repeat_until:
            self.until_caption.setText(rules.until_caption(options.repeat_until) + "  ▾")
        show_until_picker = repeat and bool(options.repeat_until) and self._picker_for == "until"
        self.until_picker.setVisible(show_until_picker)
        if show_until_picker:
            until = rules.parse_date(options.repeat_until)
            self.until_picker.set_state(month=until, lower=self._start_day, upper=None,
                                        range_start=None, selected=until)
        self._relayout()

    def _relayout(self) -> None:
        old = self.size()
        self.card.layout().activate()
        self.layout().activate()
        self.adjustSize()
        if self.size() != old:
            self.size_changed.emit()

    # ── 포커스·닫기 ──
    def focus_first(self) -> None:
        chip = self.timed_chip if self._options.start_time else self.all_day_chip
        chip.setFocus(Qt.PopupFocusReason)

    def dismiss(self) -> None:
        self._return_focus = True
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.dismiss()
            event.accept()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            focused = self.focusWidget()
            if isinstance(focused, QPushButton):
                focused.click()
            elif focused is self.time_edit:
                self._commit_time_text()
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.position().toPoint()):
            self.close()  # 그림자 여백은 카드 바깥이다.
            event.accept()
        else:
            super().mousePressEvent(event)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._commit_time_text()  # 닫기 전에 입력 중인 시각을 반영한다(무효화된 카드면 버튼이 무시).
        self.dismissed.emit(self._return_focus)


class _OptionPill(QWidget):
    """알약 하나: [아이콘 글자 ×]. 본문을 누르면 카드, ×는 그 항목만 지운다."""

    clicked = Signal()
    clear_clicked = Signal()
    HEIGHT = 22
    MAX_WIDTH = 150

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self._icon = "clock"
        self._text = ""
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        font = self.font()
        font.setPixelSize(11)
        self.setFont(font)

    def text(self) -> str:
        return self._text

    def set_content(self, icon: str, text: str) -> None:
        self._icon, self._text = icon, text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        width = 8 + 12 + 4 + self.fontMetrics().horizontalAdvance(self._text) + 4 + 12 + 5
        return QSize(min(self.MAX_WIDTH, width), self.HEIGHT)

    def minimumSizeHint(self):
        return QSize(min(self.MAX_WIDTH, 60), self.HEIGHT)

    def clear_rect(self) -> QRectF:
        return QRectF(self.width() - 5 - 12, (self.height() - 12) / 2, 12, 12)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        hovered = self.underMouse()
        painter.setPen(QPen(QColor("#CBD5E1" if hovered else "#E2E8F0"), 1))
        painter.setBrush(QColor("#E9EEF5" if hovered else "#F1F5F9"))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 10.5, 10.5)
        draw_icon(painter, self._icon, QRectF(8, (self.height() - 12) / 2, 12, 12), "#475569")
        clear = self.clear_rect()
        text_rect = QRectF(24, 0, clear.left() - 4 - 24, self.height())
        painter.setPen(QColor("#334155"))
        painter.setFont(self.font())
        text = self.fontMetrics().elidedText(self._text, Qt.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        draw_icon(painter, "x", clear, "#64748B")

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self.rect().contains(event.position().toPoint()):
            return super().mouseReleaseEvent(event)
        if self.clear_rect().adjusted(-3, -3, 3, 3).contains(event.position()):
            self.clear_clicked.emit()
        else:
            self.clicked.emit()
        event.accept()

    def event(self, event):
        if event.type() in (QEvent.HoverEnter, QEvent.HoverLeave):
            self.update()
        return super().event(event)


class ScheduleOptionsPills(QWidget):
    """입력칸 아래 알약 줄. 값이 있을 때만 보인다(없으면 숨겨 지금 배치와 같다)."""

    open_requested = Signal()
    clear_requested = Signal(str)
    KINDS = ("time", "alarm", "period", "repeat")
    ICONS = {"time": "clock", "alarm": "bell", "period": "calendar", "repeat": "repeat"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scheduleOptionsPills")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.pills = {}
        for kind in self.KINDS:
            pill = _OptionPill(kind, self)
            pill.clicked.connect(self.open_requested)
            pill.clear_clicked.connect(lambda k=kind: self.clear_requested.emit(k))
            pill.hide()
            layout.addWidget(pill)
            self.pills[kind] = pill
        layout.addStretch(1)
        self.hide()

    def set_state(self, start: str, options: ScheduleOptions) -> None:
        texts = {"time": "", "alarm": "", "period": "", "repeat": ""}
        if start and not options.is_default:
            texts = {
                "time": rules.time_pill(options),
                "alarm": "" if options.start_time else rules.alarm_label(options, short=True),
                "period": rules.span_pill(start, options),
                "repeat": rules.repeat_pill(start, options),
            }
        for kind, pill in self.pills.items():
            pill.setVisible(bool(texts[kind]))
            if texts[kind]:
                pill.set_content(self.ICONS[kind], texts[kind])
        self.setVisible(any(texts.values()))

    def visible_texts(self) -> list[str]:
        return [pill.text() for pill in self.pills.values() if not pill.isHidden()]
```

(2) `ui_schedule_emoji.py` — 맨 위 import와 지름 상수. 찾을 원문:

```python
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)


SCHEDULE_CONTROL_DIAMETER = 22
```

바꿀 코드:

```python
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

# 지름·팝업 위치는 세부 설정 모듈로 옮겼고, 기존 import 경로를 위해 이 이름으로 다시 내보낸다.
from ui_schedule_options import SCHEDULE_CONTROL_DIAMETER, popup_position  # noqa: F401
```

(3) `ui_schedule_emoji.py` — 옮긴 `popup_position` 함수를 지운다. 찾을 원문:

```python
def popup_position(anchor, size, available) -> QPoint:
    """버튼 아래(공간 부족 시 위)에 놓고 음수 좌표 작업 영역도 보존한다."""
    x = anchor.left()
    y = anchor.bottom() + 1
    if y + size.height() > available.bottom() + 1:
        y = anchor.top() - size.height()
    return QPoint(
        max(available.left(), min(x, available.right() + 1 - size.width())),
        max(available.top(), min(y, available.bottom() + 1 - size.height())),
    )


class ScheduleEmojiPopup(QWidget):
```

바꿀 코드:

```python
class ScheduleEmojiPopup(QWidget):
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_schedule_options.py tests/test_ui_schedule_emoji.py -q`
Expected: PASS (이모지 시험의 `popup_position` import도 그대로 통과)

- [ ] **Step 5: 커밋**

```bash
git add ui_schedule_options.py ui_schedule_emoji.py tests/test_ui_schedule_options.py
git commit -m "feat: 일정 세부 설정 시계 버튼·카드·작은 달력·알약 부품

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```


### Task 9: 달력 월 데이터(나타나는 일정)와 목록 줄

**Files:**
- Modify: `ui_main.py` (import, `CalendarDayButton._make_chip`, `ScheduleTextLabel`(새), 생성자, `_refresh_calendar`, 월 데이터 함수(새), `_load_schedules`, `_add_schedule_item`, `_on_edit_schedule`의 라벨 숨김 부분, `_refresh_cell_for_date`, `_on_delete_schedule`, `_on_add_schedule`, `_after_schedule_change`·`_highlight_schedule`(새))
- Test: `tests/test_ui_schedule_list.py` (새), `tests/test_ui_calendar_spans.py` (새)

**Interfaces:**
- Consumes: `db.get_occurrences`·`db.get_schedules`의 항목 키(`options`·`occurrence_date`·`span_start`·`span_end`·`start_time`·`shows_time`), `rules.detail_lines`·`rules.range_text`, `ui_schedule_options.ElidePaintMixin`·`icon_pixmap`
- Produces (`MainCalendarWindow`)
  - `_refresh_month_data()`(칸 위젯을 다시 만들지 않고 개수·색·칩 갱신), `_month_bounds()->(first, last)`, `_cell_colors(entries, palette)`, `_chip_events(entries, palette)`
  - `_after_schedule_change(highlight_id=None)`, `_highlight_schedule(schedule_id)`, `_remove_schedule_item(item)`, `_list_reload_pending: bool`
  - `_add_schedule_item(schedule_id, content, decryption_failed=False, color=None, display_color=None, *, entry=None, show_time_column=False)`
    - 항목 데이터: `UserRole+4` 세부 설정, `UserRole+5` 시작 날짜, `UserRole+6` 그 날짜
    - 줄 속성: `schedule_text_label`(`ScheduleTextLabel`), `schedule_text_box`, `schedule_time_label`(없으면 None), `schedule_period_label`(없으면 None), `schedule_icons`(이름 목록)
  - `_refresh_cell_for_date(date)`는 남기되 `_refresh_month_data()`를 부른다

- [ ] **Step 1: 실패하는 목록 시험을 쓴다** — `tests/test_ui_schedule_list.py` (새로 만든다)

```python
"""v4.1 일정 목록 줄(시각 열·아이콘·기간 글자)·편집·반복 삭제·검색 꼬리 회귀. 합성 데이터만 쓴다."""
import sqlite3

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid
from qfluentwidgets.common.font import fontFamilies, setFontFamilies

from app_fonts import apply_app_font
import database as db
import ui_main
from schedule_rules import ScheduleOptions
from show_desktop_guard import ShowDesktopKeeper
from ui_main import MainCalendarWindow
from ui_search import SearchWindow

WEEKLY = ScheduleOptions(start_time="10:00", repeat_rule="weekly", alarm_before=10)


@pytest.fixture(autouse=True)
def isolated_ui(app_dir, monkeypatch, qapp):
    previous_font, previous_families = qapp.font(), fontFamilies()
    apply_app_font(db.DEFAULT_APP_FONT, qapp)
    monkeypatch.setattr(ShowDesktopKeeper, "_install_foreground_hook", lambda self: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_apply_topmost", lambda *a, **kw: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_pin_to_desktop_layer", lambda self: False)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kw: None)
    yield
    qapp.setFont(previous_font)
    setFontFamilies(previous_families, save=False)


def main_window(qtbot, day="2026-10-12", scale="compact"):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win.activateWindow()
    win._current_year, win._current_month = 2026, 10
    win._refresh_calendar()
    win._on_date_selected(day)
    QApplication.processEvents()
    assert QTest.qWaitForWindowExposed(win)
    assert QTest.qWaitForWindowActive(win)
    return win


def rows(win):
    return [win.schedule_list.itemWidget(win.schedule_list.item(i)) for i in range(win.schedule_list.count())]


def texts(win):
    return [row.schedule_text_label.text() for row in rows(win)]


def test_all_day_only_day_keeps_old_row_layout(qtbot):
    db.add_schedule("2026-10-12", "종일 일정")
    win = main_window(qtbot)
    row = rows(win)[0]
    assert row.schedule_time_label is None
    assert row.schedule_period_label is None
    assert row.schedule_icons == []
    assert row.schedule_text_label.toolTip() == "종일 일정"


def test_time_column_order_icons_period_and_tooltip(qtbot):
    late = db.add_schedule("2026-10-12", "오후 점검", options=ScheduleOptions(start_time="16:00"))
    db.add_schedule("2026-10-05", "주간 회의", "#4CC9F0", options=WEEKLY)
    db.add_schedule("2026-10-12", "종일 일정")
    db.add_schedule("2026-10-11", "출장", options=ScheduleOptions(end_date="2026-10-13"))
    win = main_window(qtbot)
    assert texts(win) == ["종일 일정", "출장", "주간 회의", "오후 점검"]
    times = [row.schedule_time_label.text() for row in rows(win)]
    assert times == ["종일", "종일", "10:00", "16:00"]
    assert all(row.schedule_time_label.width() == 40 for row in rows(win))
    weekly_row = rows(win)[2]
    assert weekly_row.schedule_icons == ["repeat", "bell"]
    assert weekly_row.schedule_text_label.toolTip() == (
        "주간 회의\n시작: 10:00\n매주 월요일 반복 · 끝: 계속\n알림: 10분 전")
    assert rows(win)[1].schedule_period_label.text() == "10.11~10.13"
    assert win.count_label.text() == "총 4개"
    item = win.schedule_list.item(3)
    assert item.data(Qt.UserRole) == late
    assert item.data(Qt.UserRole + 5) == "2026-10-12"
    weekly_item = win.schedule_list.item(2)
    assert (weekly_item.data(Qt.UserRole + 4), weekly_item.data(Qt.UserRole + 5),
            weekly_item.data(Qt.UserRole + 6)) == (WEEKLY, "2026-10-05", "2026-10-12")


def test_body_is_plain_text_and_long_text_keeps_delete_button(qtbot):
    content = "<b>굵게 보이면 안 됨</b> " + "아주 긴 일정 제목 " * 30
    db.add_schedule("2026-10-12", content, options=ScheduleOptions(repeat_rule="daily", alarm_before=0))
    win = main_window(qtbot)
    row = rows(win)[0]
    label = row.schedule_text_label
    assert label.text() == content
    assert label.textFormat() == Qt.PlainText
    assert label.minimumSizeHint().width() == 0
    QApplication.processEvents()
    win.schedule_list.setCurrentRow(0)
    assert row.rect().contains(row.delete_button.geometry())
    assert row.rect().contains(row.schedule_text_box.geometry())


def test_new_row_is_highlighted_briefly(qtbot):
    win = main_window(qtbot)
    win.schedule_input.setText("새 일정")
    win._on_add_schedule()
    row = rows(win)[0]
    assert row.objectName() == "scheduleRowNew"
    assert "#EFF6FF" in row.styleSheet()
    qtbot.waitUntil(lambda: row.styleSheet() == "", timeout=2500)
```

- [ ] **Step 2: 실패하는 달력 시험을 쓴다** — `tests/test_ui_calendar_spans.py` (새로 만든다)

```python
"""v4.1 달력: 나타나는 일정 개수·색, 중간·크게 칩 시각과 여러 날 막대 회귀. 합성 데이터만 쓴다."""
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QGridLayout, QWidget

import database as db
from schedule_rules import ScheduleOptions
from show_desktop_guard import ShowDesktopKeeper
from ui_main import MainCalendarWindow


class _Screen:
    def __init__(self, width, height):
        self.geometry = QRect(0, 0, width, height)

    def availableGeometry(self):
        return self.geometry


@pytest.fixture(autouse=True)
def isolated_ui(app_dir, monkeypatch):
    monkeypatch.setattr(ShowDesktopKeeper, "_install_foreground_hook", lambda self: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_apply_topmost", lambda *a, **kw: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_pin_to_desktop_layer", lambda self: False)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")


def calendar_window(qtbot, monkeypatch, scale, year=2026, month=10, screen=(1920, 1080)):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    target = _Screen(*screen)
    monkeypatch.setattr(MainCalendarWindow, "_get_target_screen", lambda self: target)
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win._current_year, win._current_month = year, month
    win._refresh_calendar()
    qtbot.wait(120)
    return win


def test_compact_counts_occurrences(qtbot, monkeypatch):
    db.add_schedule("2026-10-13", "기간", "#4CC9F0", options=ScheduleOptions(end_date="2026-10-15"))
    db.add_schedule("2026-10-01", "매일", options=ScheduleOptions(repeat_rule="daily", repeat_until="2026-10-14"))
    db.add_schedule("2026-10-14", "빨강", "#FF6B6B")
    db.add_schedule("2026-10-14", "노랑 둘", "#FFD166")
    win = calendar_window(qtbot, monkeypatch, "compact")
    cell = win._day_cells["2026-10-14"]
    assert cell._count == 4
    assert cell.squares_label.text().count("■") == 3
    assert cell.count_label.text() == "+1"
    assert win._day_cells["2026-10-16"]._count == 0
    assert win._day_cells["2026-10-02"]._count == 1


def test_timed_chip_and_plain_text(qtbot, monkeypatch):
    db.add_schedule("2026-10-14", "<b>회의</b>", options=ScheduleOptions(start_time="14:00"))
    db.add_schedule("2026-10-14", "종일 일정")
    win = calendar_window(qtbot, monkeypatch, "large", screen=(2560, 1440))
    layout = win._day_cells["2026-10-14"]._chips_layout
    chips = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert [chip.toolTip() for chip in chips] == ["종일 일정", "14:00 <b>회의</b>"]
    assert chips[1].text().startswith("14:00 <b>")
    assert chips[1].textFormat() == Qt.PlainText
    assert not chips[1].font().bold()


def test_monthly_31st_shows_on_february_last_day(qtbot, monkeypatch):
    """Review Focus 5: 매월 31일 반복은 2월에 말일(28일)로 보인다."""
    db.add_schedule("2026-01-31", "월말 보고", options=ScheduleOptions(repeat_rule="monthly"))
    win = calendar_window(qtbot, monkeypatch, "compact", month=2)
    assert win._day_cells["2026-02-28"]._count == 1
    assert sum(cell._count for cell in win._day_cells.values()) == 1


def test_cells_are_not_recreated_by_month_refresh(qtbot, monkeypatch):
    win = calendar_window(qtbot, monkeypatch, "medium")
    cells = dict(win._day_cells)
    db.add_schedule("2026-10-20", "반복", options=ScheduleOptions(repeat_rule="weekly"))
    win._refresh_month_data()
    assert win._day_cells == cells
    assert win._day_cells["2026-10-27"]._chips_layout.count() == 1
```

- [ ] **Step 3: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_schedule_list.py tests/test_ui_calendar_spans.py -q`
Expected: FAIL — `schedule_time_label`이 없고(AttributeError), 반복·기간이 칸 개수에 반영되지 않는다

- [ ] **Step 4: 구현한다**

(1) `ui_main.py` — import(세부 설정 규칙·부품). 찾을 원문:

```python
from ui_schedule_emoji import (
    SCHEDULE_CONTROL_DIAMETER, ScheduleEmojiButton, ScheduleInlineEditor,
)
```

바꿀 코드:

```python
from ui_schedule_emoji import (
    SCHEDULE_CONTROL_DIAMETER, ScheduleEmojiButton, ScheduleInlineEditor,
)
import schedule_rules as rules
from schedule_rules import ScheduleOptions
from ui_schedule_options import ElidePaintMixin, icon_pixmap
```

(2) `ui_main.py` — `CalendarDayButton._make_chip`: 칩 글자를 서식 없이(PlainText) 보인다. 이 원문 바로 뒤에:

```python
        chip = QLabel(self._chips_container)
```

넣을 코드:

```python
        chip.setTextFormat(Qt.PlainText)  # 본문의 <…>를 서식으로 해석하지 않는다.
```

(3) `ui_main.py` — 목록 본문 라벨 클래스를 `ScheduleRow` 앞에 더한다. 이 원문 바로 앞에:

```python
class ScheduleRow(QWidget):
```

넣을 코드:

```python
class ScheduleTextLabel(ElidePaintMixin, BodyLabel):
    """일정 목록 본문. text()는 전체 본문이고 좁으면 그릴 때만 말줄임한다."""


```

(4) `ui_main.py` — 생성자: 편집 중이라 미룬 목록 다시 만들기 표시. 이 원문 바로 앞에:

```python
        self._build_ui()
```

넣을 코드:

```python
        self._list_reload_pending = False  # 다른 줄을 편집 중이라 미룬 목록 다시 만들기
```

(5) `ui_main.py` — `_refresh_calendar`: 전체 날짜 조회 세 개를 없앤다(월 데이터 갱신이 한 번에 읽는다). 찾을 원문:

```python
        today = date.today()
        event_date_colors = db.get_all_schedule_date_colors()
        event_date_counts = db.get_all_schedule_date_counts()
        schedule_palette = db.get_schedule_palette()
        self._show_lunar = db.get_setting(db.SETTING_SHOW_LUNAR, "0") == "1"
        calendar_scale = self._current_calendar_scale()
        cell_mode = "expanded" if calendar_scale != "compact" else "compact"
        self._style_weekday_header(calendar_scale)
        month_events = (
            db.get_schedules_for_month(self._current_year, self._current_month)
            if cell_mode == "expanded" else {}
        )
```

바꿀 코드:

```python
        today = date.today()
        self._show_lunar = db.get_setting(db.SETTING_SHOW_LUNAR, "0") == "1"
        calendar_scale = self._current_calendar_scale()
        cell_mode = "expanded" if calendar_scale != "compact" else "compact"
        self._style_weekday_header(calendar_scale)
```

(6) `ui_main.py` — `_refresh_calendar`: 칸은 빈 데이터로 만들고 칩도 여기서 채우지 않는다. 찾을 원문:

```python
                event_colors = [
                    db.schedule_display_color(color, schedule_palette)
                    for color in event_date_colors.get(target_date, [])
                ]
                is_holiday = bool(target_date) and holidays.is_holiday(target_date)
                count = event_date_counts.get(target_date, 0)

                cell = CalendarDayButton(
                    actual_day, is_today, event_colors, is_current, target_date,
                    is_holiday, col_idx, count, cell_mode, self,
                    calendar_scale=calendar_scale,
                )
                if cell_mode == "expanded" and target_date:
                    cell.set_events([
                        {
                            **event,
                            "color": db.schedule_display_color(
                                event.get("color"), schedule_palette
                            ),
                        }
                        for event in month_events.get(target_date, [])
                    ])
                if target_date:
```

바꿀 코드:

```python
                is_holiday = bool(target_date) and holidays.is_holiday(target_date)

                # 색·개수·칩은 아래 _refresh_month_data()가 한 번의 조회로 채운다.
                cell = CalendarDayButton(
                    actual_day, is_today, [], is_current, target_date,
                    is_holiday, col_idx, 0, cell_mode, self,
                    calendar_scale=calendar_scale,
                )
                if target_date:
```

(7) `ui_main.py` — `_refresh_calendar` 끝: 월 데이터 갱신을 부르고, 월 데이터 함수들을 더한다. 찾을 원문:

```python
                self.calendar_grid.addWidget(cell, row_idx, col_idx)

        # 선택된 날짜 정보 갱신 (루프 완료 후)
        if self._selected_date in self._day_cells:
            self._on_date_selected(self._selected_date)
```

바꿀 코드:

```python
                self.calendar_grid.addWidget(cell, row_idx, col_idx)

        self._refresh_month_data()

        # 선택된 날짜 정보 갱신 (루프 완료 후)
        if self._selected_date in self._day_cells:
            self._on_date_selected(self._selected_date)

    # ─── 월 데이터(나타나는 일정) ────────────────────────────────
    def _month_bounds(self) -> tuple[str, str]:
        last_day = calendar.monthrange(self._current_year, self._current_month)[1]
        first = date(self._current_year, self._current_month, 1)
        return first.isoformat(), first.replace(day=last_day).isoformat()

    @staticmethod
    def _cell_colors(entries: list, palette) -> list:
        """그날 일정의 서로 다른 색(슬롯 순서)을 표시색으로 바꾼다."""
        order = {color: index for index, (color, _name) in enumerate(db.SCHEDULE_COLORS)}
        colors = sorted({entry["color"] for entry in entries}, key=lambda c: order.get(c, 99))
        return [db.schedule_display_color(color, palette) for color in colors]

    @staticmethod
    def _chip_events(entries: list, palette) -> list:
        """중간·크게 칩: 그 날 시각이 보이는 일정은 '14:00 본문'."""
        return [{
            "content": f"{entry['start_time']} {entry['content']}" if entry.get("shows_time")
            else entry["content"],
            "color": db.schedule_display_color(entry.get("color"), palette),
        } for entry in entries]

    def _refresh_month_data(self) -> None:
        """보이는 달의 나타나는 일정을 한 번 읽어 칸 위젯을 다시 만들지 않고 갱신한다."""
        first, last = self._month_bounds()
        try:
            month = db.get_occurrences(first, last)
            palette = db.get_schedule_palette()
        except (sqlite3.Error, OSError) as exc:
            _logger.error("달력 일정 조회 실패: %s", exc)
            return
        expanded = self._current_calendar_scale() != "compact"
        for day, cell in self._day_cells.items():
            entries = month.get(day, [])
            cell._update_squares(self._cell_colors(entries, palette))
            cell.set_count(len(entries))
            if expanded:
                cell.set_events(self._chip_events(entries, palette))
```

(8) `ui_main.py` — `_load_schedules`: 나타나는 일정을 순서대로, 시각 열은 필요할 때만. 찾을 원문:

```python
        try:
            schedules = db.get_schedules(self._selected_date)
            schedule_palette = db.get_schedule_palette()
            for s in schedules:
                self._add_schedule_item(
                    s["id"], s["content"],
                    decryption_failed=s.get("_decryption_failed", False),
                    color=s.get("color", db.DEFAULT_SCHEDULE_COLOR),
                    display_color=db.schedule_display_color(
                        s.get("color"), schedule_palette
                    ),
                )
        except (sqlite3.Error, OSError) as e:
            _logger.error("일정 로드 실패: %s", e)
        self._update_count()
        return True
```

바꿀 코드:

```python
        self._list_reload_pending = False
        try:
            schedules = db.get_schedules(self._selected_date)
            schedule_palette = db.get_schedule_palette()
            # 그날 시각이 보이는 일정이 하나라도 있을 때만 시각 열을 둔다.
            show_time = any(s.get("shows_time") for s in schedules)
            for s in schedules:
                self._add_schedule_item(
                    s["id"], s["content"],
                    decryption_failed=s.get("_decryption_failed", False),
                    color=s.get("color", db.DEFAULT_SCHEDULE_COLOR),
                    display_color=db.schedule_display_color(
                        s.get("color"), schedule_palette
                    ),
                    entry=s, show_time_column=show_time,
                )
        except (sqlite3.Error, OSError) as e:
            _logger.error("일정 로드 실패: %s", e)
        self._update_count()
        return True
```

(9) `ui_main.py` — 목록 툴팁 도우미를 `_add_schedule_item` 앞에 더한다. 이 원문 바로 앞에:

```python
    def _add_schedule_item(self, schedule_id: int, content: str,
```

넣을 코드:

```python
    @staticmethod
    def _schedule_tooltip(content: str, options: ScheduleOptions, start: str) -> str:
        """본문 전체 + 세부 설정 설명 줄(기본값이면 지금처럼 본문만)."""
        details = []
        if not options.is_default:
            try:
                details = rules.detail_lines(start, options)
            except ValueError:
                details = []
        return "\n".join([content, *details])

```

(10) `ui_main.py` — `_add_schedule_item` 머리: 세부 설정·시작 날짜·그 날짜를 항목에 둔다(기존 인자 순서 유지). 찾을 원문:

```python
    def _add_schedule_item(self, schedule_id: int, content: str,
                           decryption_failed: bool = False,
                           color: str = None, display_color: str = None):
        if color is None:
            color = db.DEFAULT_SCHEDULE_COLOR
        if display_color is None:
            display_color = db.schedule_display_color(color)

        item = QListWidgetItem()
        item.setData(Qt.UserRole, schedule_id)
        item.setData(Qt.UserRole + 1, content)
        item.setData(Qt.UserRole + 2, color)
        item.setData(Qt.UserRole + 3, decryption_failed)
        self.schedule_list.addItem(item)
```

바꿀 코드:

```python
    def _add_schedule_item(self, schedule_id: int, content: str,
                           decryption_failed: bool = False,
                           color: str = None, display_color: str = None,
                           *, entry: dict | None = None, show_time_column: bool = False):
        if color is None:
            color = db.DEFAULT_SCHEDULE_COLOR
        if display_color is None:
            display_color = db.schedule_display_color(color)
        options = entry["options"] if entry else ScheduleOptions()
        series_start = entry["date"] if entry else self._selected_date
        occurrence = entry["occurrence_date"] if entry else self._selected_date

        item = QListWidgetItem()
        item.setData(Qt.UserRole, schedule_id)
        item.setData(Qt.UserRole + 1, content)
        item.setData(Qt.UserRole + 2, color)
        item.setData(Qt.UserRole + 3, decryption_failed)
        item.setData(Qt.UserRole + 4, options)        # 세부 설정(ScheduleOptions)
        item.setData(Qt.UserRole + 5, series_start)   # 반복·기간의 시작 날짜
        item.setData(Qt.UserRole + 6, occurrence)     # 이 목록이 보여 주는 날짜
        self.schedule_list.addItem(item)
```

(11) `ui_main.py` — `_add_schedule_item` 줄 구성: [점][시각 열][본문+아이콘][기간 글자][휴지통]. 찾을 원문:

```python
        row_layout.addWidget(color_dot)

        text_label = BodyLabel(content)
        text_label.setToolTip(content)
        row_widget.schedule_text_label = text_label
        if decryption_failed:
            text_label.setStyleSheet("color: #D32F2F; font-style: italic;")
        else:
            text_label.setStyleSheet("color: #1a1a1a;")
        row_layout.addWidget(text_label, 1)
```

바꿀 코드:

```python
        row_layout.addWidget(color_dot)

        row_widget.schedule_time_label = None
        if show_time_column:
            # 시각 열: 그 날 시각이 보이면 13px 시각, 아니면 11px '종일'(40px 고정).
            shows_time = bool(entry and entry.get("shows_time"))
            time_label = QLabel(entry["start_time"] if shows_time else "종일")
            time_label.setTextFormat(Qt.PlainText)
            time_label.setFixedWidth(40)
            time_label.setStyleSheet(
                "color: #475569; font-size: 13px; background: transparent;" if shows_time
                else "color: #94A3B8; font-size: 11px; background: transparent;"
            )
            row_layout.addWidget(time_label)
            row_widget.schedule_time_label = time_label

        # 본문 묶음: 본문 바로 뒤에 반복·종 아이콘을 붙이고 남는 폭은 비운다.
        text_box = QWidget()
        text_box.setStyleSheet("background: transparent;")
        box_layout = QHBoxLayout(text_box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.setSpacing(4)
        text_label = ScheduleTextLabel(content)
        text_label.setTextFormat(Qt.PlainText)
        text_label.setToolTip(self._schedule_tooltip(content, options, series_start))
        row_widget.schedule_text_label = text_label
        if decryption_failed:
            text_label.setStyleSheet("color: #D32F2F; font-style: italic;")
        else:
            text_label.setStyleSheet("color: #1a1a1a;")
        box_layout.addWidget(text_label)
        row_widget.schedule_icons = []
        ratio = self.devicePixelRatioF()
        for name, enabled in (("repeat", bool(options.repeat_rule)),
                              ("bell", options.alarm_before is not None)):
            if enabled:
                icon = QLabel()
                icon.setObjectName(f"scheduleRowIcon_{name}")
                icon.setFixedSize(12, 12)
                icon.setPixmap(icon_pixmap(name, 12, "#94A3B8", ratio))
                box_layout.addWidget(icon)
                row_widget.schedule_icons.append(name)
        box_layout.addStretch(1)
        row_layout.addWidget(text_box, 1)
        row_widget.schedule_text_box = text_box

        row_widget.schedule_period_label = None
        if entry and entry["span_start"] != entry["span_end"]:
            period_label = QLabel(rules.range_text(entry["span_start"], entry["span_end"]))
            period_label.setTextFormat(Qt.PlainText)
            period_label.setStyleSheet("color: #94A3B8; font-size: 11px; background: transparent;")
            row_layout.addWidget(period_label)
            row_widget.schedule_period_label = period_label
```

(12) `ui_main.py` — `_on_edit_schedule`: 본문 라벨 대신 본문 묶음·기간 글자를 숨기고 그 뒤에 편집기를 넣는다(편집기 자체 변경은 Task 11). 찾을 원문:

```python
        text_label = row_widget.schedule_text_label
        text_label.hide()

        editor = ScheduleInlineEditor(old_text, self._schedule_emoji_allowed, row_widget)
        self._schedule_editor = editor
        edit = editor.edit
        layout.insertWidget(layout.indexOf(text_label) + 1, editor, 1)
```

바꿀 코드:

```python
        text_label = row_widget.schedule_text_label
        text_box = row_widget.schedule_text_box
        period_label = row_widget.schedule_period_label
        text_box.hide()
        if period_label is not None:
            period_label.hide()

        editor = ScheduleInlineEditor(old_text, self._schedule_emoji_allowed, row_widget)
        self._schedule_editor = editor
        edit = editor.edit
        layout.insertWidget(layout.indexOf(text_box) + 1, editor, 1)
```

(13) `ui_main.py` — `_on_edit_schedule` 끝: 본문 묶음·기간 글자를 다시 보인다. 찾을 원문:

```python
            editor.deleteLater()
            text_label.show()
            item.setSizeHint(row_widget.sizeHint())
            return True
```

바꿀 코드:

```python
            editor.deleteLater()
            text_box.show()
            if period_label is not None:
                period_label.show()
            item.setSizeHint(row_widget.sizeHint())
            if self._list_reload_pending:
                QTimer.singleShot(0, self, self._after_schedule_change)
            return True
```

(14) `ui_main.py` — `_refresh_cell_for_date`: 반복·기간은 여러 칸에 걸치므로 보이는 달 전체를 다시 읽는다(시험이 쓰는 이름은 유지). 찾을 원문:

```python
    def _refresh_cell_for_date(self, date_str: str):
        """일정 변경 후 해당 날짜 셀만 현재 모드에 맞게 갱신."""
        cell = self._day_cells.get(date_str)
        if not cell:
            return
        schedules = db.get_schedules(date_str)
        schedule_palette = db.get_schedule_palette()
        cell.set_count(len(schedules))
        if getattr(cell, "_mode", "compact") == "expanded":
            cell.set_events([
                {
                    "content": schedule["content"],
                    "color": db.schedule_display_color(
                        schedule.get("color") or db.DEFAULT_SCHEDULE_COLOR,
                        schedule_palette,
                    ),
                }
                for schedule in schedules
            ])
        else:
            colors = {s.get("color") or db.DEFAULT_SCHEDULE_COLOR for s in schedules}
            color_order = {color[0]: index for index, color in enumerate(db.SCHEDULE_COLORS)}
            ordered = sorted(colors, key=lambda color: color_order.get(color, 99))
            cell._update_squares([
                db.schedule_display_color(color, schedule_palette)
                for color in ordered
            ])
```

바꿀 코드:

```python
    def _refresh_cell_for_date(self, date_str: str):
        """일정 변경 후 칸을 갱신한다. 반복·기간은 여러 칸에 걸치므로 보이는 달 전체를 다시 읽는다."""
        self._refresh_month_data()
```

(15) `ui_main.py` — `_on_delete_schedule`: 목록에서 줄을 빼는 부분을 도우미로 나눈다(Task 11의 '이 날만 삭제'도 쓴다). 찾을 원문:

```python
    def _on_delete_schedule(self, item: QListWidgetItem, schedule_id: int):
        if self._is_locked:
            return
        try:
            db.delete_schedule(schedule_id)
            if self._editing_item is item and self._finish_current_edit:
                self._finish_current_edit(False)
            row = self.schedule_list.row(item)
            widget = self.schedule_list.itemWidget(item)
            if widget:
                self.schedule_list.removeItemWidget(item)
                widget.deleteLater()
            self.schedule_list.takeItem(row)
            self._refresh_cell_for_date(self._selected_date)
```

바꿀 코드:

```python
    def _remove_schedule_item(self, item: QListWidgetItem) -> None:
        row = self.schedule_list.row(item)
        widget = self.schedule_list.itemWidget(item)
        if widget:
            self.schedule_list.removeItemWidget(item)
            widget.deleteLater()
        self.schedule_list.takeItem(row)

    def _on_delete_schedule(self, item: QListWidgetItem, schedule_id: int):
        if self._is_locked:
            return
        try:
            db.delete_schedule(schedule_id)
            if self._editing_item is item and self._finish_current_edit:
                self._finish_current_edit(False)
            self._remove_schedule_item(item)
            self._refresh_cell_for_date(self._selected_date)
```

(16) `ui_main.py` — `_on_add_schedule`: 추가 뒤에는 달 전체·목록을 다시 읽고 새 줄을 강조한다(순서가 시각에 따라 바뀔 수 있다). 찾을 원문:

```python
        try:
            new_id = db.add_schedule(self._selected_date, text, self._schedule_color)
            self._add_schedule_item(new_id, text, color=self._schedule_color)
            self.schedule_input.clear()
            self._refresh_cell_for_date(self._selected_date)
            self._update_count()
        except (sqlite3.Error, OSError, ValueError):
```

바꿀 코드:

```python
        try:
            new_id = db.add_schedule(self._selected_date, text, self._schedule_color)
            self.schedule_input.clear()
            self._after_schedule_change(highlight_id=new_id)
        except (sqlite3.Error, OSError, ValueError):
```

(17) `ui_main.py` — `_close_schedule_emoji_popups` 메서드 바로 뒤에 변경 후 처리·강조 메서드를 더한다. 이 원문 바로 뒤에:

```python
    def _close_schedule_emoji_popups(self) -> None:
        self.schedule_emoji_button.close_popup()
        if self._schedule_editor is not None:
            self._schedule_editor.emoji_button.close_popup()
```

넣을 코드:

```python

    def _after_schedule_change(self, highlight_id: int | None = None) -> None:
        """일정 추가·수정 뒤: 달 전체 칸·목록을 다시 읽는다(반복·기간은 여러 칸과 순서에 걸친다)."""
        self._refresh_month_data()
        if self._editing_item is not None:
            self._list_reload_pending = True  # 다른 줄을 편집 중이면 끝난 뒤에 다시 만든다.
        elif self._load_schedules() and highlight_id is not None:
            self._highlight_schedule(highlight_id)

    def _highlight_schedule(self, schedule_id: int) -> None:
        """추가 직후 새 줄을 1.2초 동안 연한 파랑으로 보인다."""
        for index in range(self.schedule_list.count()):
            item = self.schedule_list.item(index)
            if item.data(Qt.UserRole) != schedule_id:
                continue
            row = self.schedule_list.itemWidget(item)
            self.schedule_list.scrollToItem(item)
            if isinstance(row, ScheduleRow):
                row.setObjectName("scheduleRowNew")
                row.setAttribute(Qt.WA_StyledBackground, True)
                row.setStyleSheet("#scheduleRowNew { background: #EFF6FF; border-radius: 6px; }")
                QTimer.singleShot(1200, row, lambda r=row: r.setStyleSheet(""))
            return
```

- [ ] **Step 5: 새 시험과 기존 달력·목록 시험을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_schedule_list.py tests/test_ui_calendar_spans.py tests/test_ui_schedule_emoji.py tests/test_ui_calendar_columns.py tests/test_ui_calendar_count.py tests/test_ui_calendar_cells.py tests/test_ui_main_tidy.py tests/test_ui.py -q`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add ui_main.py tests/test_ui_schedule_list.py tests/test_ui_calendar_spans.py
git commit -m "feat: 달력과 목록에 반복·기간 일정 표시, 시각 열·아이콘·기간 글자

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```


### Task 10: 입력줄 연결(시계 버튼·알약·보류 중 값·추가)

**Files:**
- Modify: `ui_main.py` (import, `_build_bottom_panel`, `_on_date_selected`, `_close_schedule_emoji_popups`, 보류 값 도우미(새), `_on_add_schedule`, `_apply_calendar_scale`, `_discard_data_widgets`)
- Test: `tests/test_ui_schedule_input.py` (새)

**Interfaces:**
- Consumes: Task 8의 `ScheduleOptionsButton`·`ScheduleOptionsPills`, Task 9의 `_after_schedule_change`, `rules.clear_part`·`rules.rebase_options`, `db.add_schedule(..., options=)`
- Produces (`MainCalendarWindow`)
  - 위젯: `schedule_options_button`, `schedule_options_pills`
  - `_set_pending_options(options)`, `_on_pending_options_changed(options)`, `_on_pending_option_cleared(kind)`, `_sync_pending_pills()`, `_rebase_pending_options(old_date, new_date)`
  - `_close_schedule_emoji_popups()`는 입력줄 세부 설정 카드도 닫는다(편집기 쪽은 Task 11)

- [ ] **Step 1: 실패하는 시험을 쓴다** — `tests/test_ui_schedule_input.py` (새로 만든다)

```python
"""v4.1 입력줄: 시계 버튼·알약·보류 중 세부 설정과 일정 추가 연결 회귀. 합성 데이터만 쓴다."""
import sqlite3

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid
from qfluentwidgets.common.font import fontFamilies, setFontFamilies

from app_fonts import apply_app_font
import database as db
import ui_main
from schedule_rules import ScheduleOptions
from show_desktop_guard import ShowDesktopKeeper
from ui_main import MainCalendarWindow


@pytest.fixture(autouse=True)
def isolated_ui(app_dir, monkeypatch, qapp):
    previous_font, previous_families = qapp.font(), fontFamilies()
    apply_app_font(db.DEFAULT_APP_FONT, qapp)
    monkeypatch.setattr(ShowDesktopKeeper, "_install_foreground_hook", lambda self: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_apply_topmost", lambda *a, **kw: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_pin_to_desktop_layer", lambda self: False)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kw: None)
    yield
    qapp.setFont(previous_font)
    setFontFamilies(previous_families, save=False)


def main_window(qtbot, scale="compact", day="2026-10-15"):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win.activateWindow()
    win._current_year, win._current_month = 2026, 10
    win._refresh_calendar()
    win._on_date_selected(day)
    QApplication.processEvents()
    assert QTest.qWaitForWindowExposed(win)
    assert QTest.qWaitForWindowActive(win)
    return win


def open_card(qtbot, button):
    qtbot.mouseClick(button, Qt.LeftButton)
    qtbot.waitUntil(lambda: button._popup is not None and button._popup.isVisible())
    assert QTest.qWaitForWindowExposed(button._popup)
    return button._popup


def click(qtbot, widget):
    qtbot.mouseClick(widget, Qt.LeftButton)
    QApplication.processEvents()


def test_clock_button_sits_between_smile_and_input(qtbot):
    win = main_window(qtbot)
    clock, smile = win.schedule_options_button, win.schedule_emoji_button
    assert clock.size() == QSize(26, 26)
    assert smile.mapTo(win, QPoint()).x() < clock.mapTo(win, QPoint()).x()
    assert clock.mapTo(win, QPoint()).x() < win.schedule_input.mapTo(win, QPoint()).x()
    clock_center = clock.mapTo(win, QPoint()).y() + clock.height() / 2
    smile_center = smile.mapTo(win, QPoint()).y() + smile.height() / 2
    assert abs(clock_center - smile_center) <= 0.5
    assert win.schedule_input.width() >= 100


def test_add_with_options_saves_then_clears_and_failure_keeps(qtbot, monkeypatch):
    win = main_window(qtbot)
    options = ScheduleOptions(start_time="15:00", repeat_rule="weekly", alarm_before=10)
    win._set_pending_options(options)
    win.schedule_input.setText("부서 회의")
    original = db.add_schedule

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic failure")

    monkeypatch.setattr(db, "add_schedule", fail)
    win._on_add_schedule()
    assert win.schedule_input.text() == "부서 회의"
    assert win.schedule_options_button.options() == options
    assert win.schedule_options_pills.visible_texts() == ["15:00 · 10분 전", "매주 목"]
    monkeypatch.setattr(db, "add_schedule", original)
    qtbot.keyClick(win.schedule_input, Qt.Key_Return)
    saved = db.get_schedules("2026-10-22")
    assert [(s["content"], s["options"]) for s in saved] == [("부서 회의", options)]
    assert win.schedule_input.text() == ""
    assert win.schedule_options_button.options() == ScheduleOptions()
    assert win.schedule_options_pills.isHidden()


def test_card_changes_pending_options_without_saving(qtbot):
    win = main_window(qtbot)
    card = open_card(qtbot, win.schedule_options_button)
    click(qtbot, card.repeat_chips["daily"])
    assert win.schedule_options_pills.visible_texts() == ["매일"]
    assert db.get_schedules("2026-10-15") == []


def test_pill_x_clears_only_that_part_and_body_opens_card(qtbot):
    win = main_window(qtbot)
    win._set_pending_options(ScheduleOptions(start_time="09:00", repeat_rule="daily", alarm_before=10))
    QApplication.processEvents()
    pills = win.schedule_options_pills.pills
    qtbot.mouseClick(pills["time"], Qt.LeftButton, pos=pills["time"].clear_rect().center().toPoint())
    assert win.schedule_options_button.options() == ScheduleOptions(repeat_rule="daily")
    qtbot.mouseClick(pills["repeat"], Qt.LeftButton, pos=QPoint(14, 11))
    qtbot.waitUntil(lambda: win.schedule_options_button._popup is not None)
    assert win.schedule_options_button._popup.isVisible()


def test_pending_options_follow_selected_date(qtbot):
    win = main_window(qtbot)
    win._set_pending_options(ScheduleOptions(end_date="2026-10-17"))
    win._on_date_selected("2026-10-20")
    assert win.schedule_options_button.options() == ScheduleOptions(end_date="2026-10-22")
    assert win.schedule_options_pills.visible_texts() == ["~10.22 · 3일"]
    win._set_pending_options(ScheduleOptions(repeat_rule="weekly", repeat_until="2026-10-24"))
    win._on_date_selected("2026-10-25")
    assert win.schedule_options_button.options() == ScheduleOptions(repeat_rule="weekly")


def test_hidden_pills_add_no_space_and_align_with_input(qtbot):
    win = main_window(qtbot)
    row = [win.schedule_color_btn, win.schedule_emoji_button, win.schedule_options_button,
           win.schedule_input]
    QApplication.processEvents()
    row_bottom = max(widget.geometry().bottom() for widget in row)
    hidden_gap = win.schedule_list.geometry().top() - row_bottom
    win._set_pending_options(ScheduleOptions(start_time="09:00"))
    QApplication.processEvents()
    pills = win.schedule_options_pills
    assert pills.isVisible()
    assert pills.pills["time"].mapTo(win, QPoint()).x() == win.schedule_input.mapTo(win, QPoint()).x()
    assert win.schedule_list.geometry().top() - row_bottom == hidden_gap + pills.height() + 4
    win._set_pending_options(ScheduleOptions())
    QApplication.processEvents()
    assert win.schedule_list.geometry().top() - row_bottom == hidden_gap


@pytest.mark.parametrize("action", ["lock", "tray", "reset", "scale"])
def test_card_closes_on_lifecycle_and_ignores_late_change(qtbot, action):
    win = main_window(qtbot)
    button = win.schedule_options_button
    win._set_pending_options(ScheduleOptions(repeat_rule="daily"))
    card = open_card(qtbot, button)
    if action == "lock":
        win._lock()
    elif action == "tray":
        win._minimize_to_tray()
    elif action == "reset":
        win._discard_data_widgets()
    else:
        db.save_setting(db.SETTING_CALENDAR_SCALE, "medium")
        win._apply_calendar_scale()
    assert not card.isVisible()
    card.options_changed.emit(ScheduleOptions(start_time="11:00"))
    expected = ScheduleOptions() if action == "reset" else ScheduleOptions(repeat_rule="daily")
    assert button.options() == expected  # 초기화 전 폐기만 보류 값을 비운다.
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()
    assert not isValid(card)
    if action == "lock":
        button.open_popup()
        assert button._popup is None  # 잠금 중에는 열지 않는다.


def test_escape_restores_focus_to_schedule_input(qtbot):
    win = main_window(qtbot)
    card = open_card(qtbot, win.schedule_options_button)
    click(qtbot, card.repeat_chips["daily"])
    qtbot.keyClick(card, Qt.Key_Escape)
    qtbot.waitUntil(lambda: win.schedule_input.hasFocus())
    assert win.schedule_options_button.options() == ScheduleOptions(repeat_rule="daily")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_schedule_input.py -q`
Expected: FAIL — `AttributeError: 'MainCalendarWindow' object has no attribute 'schedule_options_button'`

- [ ] **Step 3: 구현한다**

(1) `ui_main.py` — import에 시계 버튼·알약을 더한다. 찾을 원문:

```python
from ui_schedule_options import ElidePaintMixin, icon_pixmap
```

바꿀 코드:

```python
from ui_schedule_options import (
    ElidePaintMixin, ScheduleOptionsButton, ScheduleOptionsPills, icon_pixmap,
)
```

(2) `ui_main.py` — `_build_bottom_panel`의 입력줄을 격자로 바꾸고 시계 버튼·알약을 둔다. 찾을 원문:

```python
        # 일정 입력
        schedule_input_row = QHBoxLayout()

        self.schedule_color_btn = SmoothCircleButton(self)
        self.schedule_color_btn.setFixedSize(SCHEDULE_CONTROL_DIAMETER, SCHEDULE_CONTROL_DIAMETER)
        self.schedule_color_btn.setToolTip("일정 색상 선택 (클릭하여 순환)")
        self.schedule_color_btn.clicked.connect(self._on_cycle_schedule_color)
        self._update_schedule_color_btn()
        schedule_input_row.addWidget(self.schedule_color_btn)

        self.schedule_input = LineEdit(self)
        self.schedule_input.setPlaceholderText("일정 추가...")
        self.schedule_input.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.schedule_input.returnPressed.connect(self._on_add_schedule)
        self.schedule_emoji_button = ScheduleEmojiButton(
            self.schedule_input, self._schedule_emoji_allowed, self
        )
        schedule_input_row.addWidget(self.schedule_emoji_button)
        schedule_input_row.addWidget(self.schedule_input, 1)
        add_btn = TransparentToolButton(FIF.ADD, self)
        add_btn.clicked.connect(self._on_add_schedule)
        schedule_input_row.addWidget(add_btn)
        panel_layout.addLayout(schedule_input_row)
```

바꿀 코드:

```python
        # 일정 입력: [색 원][스마일][시계][입력칸][추가], 아래 줄 알약은 입력칸 왼쪽에 맞춘다.
        # 격자로 두어 알약이 입력칸과 같은 열에 놓이고, 알약이 없으면 줄도 생기지 않는다.
        schedule_input_row = QGridLayout()
        schedule_input_row.setVerticalSpacing(4)

        self.schedule_color_btn = SmoothCircleButton(self)
        self.schedule_color_btn.setFixedSize(SCHEDULE_CONTROL_DIAMETER, SCHEDULE_CONTROL_DIAMETER)
        self.schedule_color_btn.setToolTip("일정 색상 선택 (클릭하여 순환)")
        self.schedule_color_btn.clicked.connect(self._on_cycle_schedule_color)
        self._update_schedule_color_btn()
        schedule_input_row.addWidget(self.schedule_color_btn, 0, 0)

        self.schedule_input = LineEdit(self)
        self.schedule_input.setPlaceholderText("일정 추가...")
        self.schedule_input.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.schedule_input.returnPressed.connect(self._on_add_schedule)
        self.schedule_emoji_button = ScheduleEmojiButton(
            self.schedule_input, self._schedule_emoji_allowed, self
        )
        schedule_input_row.addWidget(self.schedule_emoji_button, 0, 1)
        self.schedule_options_button = ScheduleOptionsButton(
            self.schedule_input, self._schedule_emoji_allowed, self
        )
        self.schedule_options_button.set_context(self._selected_date)
        self.schedule_options_button.options_changed.connect(self._on_pending_options_changed)
        schedule_input_row.addWidget(self.schedule_options_button, 0, 2)
        schedule_input_row.addWidget(self.schedule_input, 0, 3)
        schedule_input_row.setColumnStretch(3, 1)
        add_btn = TransparentToolButton(FIF.ADD, self)
        add_btn.clicked.connect(self._on_add_schedule)
        schedule_input_row.addWidget(add_btn, 0, 4)
        self.schedule_options_pills = ScheduleOptionsPills(self)
        self.schedule_options_pills.open_requested.connect(self.schedule_options_button.open_popup)
        self.schedule_options_pills.clear_requested.connect(self._on_pending_option_cleared)
        schedule_input_row.addWidget(self.schedule_options_pills, 1, 3, 1, 2)
        panel_layout.addLayout(schedule_input_row)
```

(3) `ui_main.py` — `_on_date_selected`: 고른 날짜가 바뀌면 보류 중 세부 설정을 새 날짜 기준으로 옮긴다. 찾을 원문:

```python
            except RuntimeError:
                pass  # C++ 객체가 이미 삭제된 경우 안전 무시
        self._selected_date = date_str
```

바꿀 코드:

```python
            except RuntimeError:
                pass  # C++ 객체가 이미 삭제된 경우 안전 무시
        if date_str != self._selected_date:
            self._rebase_pending_options(self._selected_date, date_str)
        self._selected_date = date_str
```

(4) `ui_main.py` — 팝업 닫기에 세부 설정 카드를 넣고, 보류 중 값 도우미를 더한다. 찾을 원문:

```python
    def _close_schedule_emoji_popups(self) -> None:
        self.schedule_emoji_button.close_popup()
        if self._schedule_editor is not None:
            self._schedule_editor.emoji_button.close_popup()
```

바꿀 코드:

```python
    def _close_schedule_emoji_popups(self) -> None:
        """이모지·세부 설정 카드를 모두 닫는다(입력줄·편집기)."""
        self.schedule_emoji_button.close_popup()
        self.schedule_options_button.close_popup()
        if self._schedule_editor is not None:
            self._schedule_editor.emoji_button.close_popup()

    # ─── 입력줄 세부 설정(보류 중 값) ──────────────────────────────
    def _set_pending_options(self, options: ScheduleOptions) -> None:
        self.schedule_options_button.set_options(options)
        self._sync_pending_pills()

    def _on_pending_options_changed(self, _options) -> None:
        self._sync_pending_pills()

    def _on_pending_option_cleared(self, kind: str) -> None:
        if not self._schedule_emoji_allowed():
            return
        button = self.schedule_options_button
        self._set_pending_options(rules.clear_part(button.options(), button.start_date(), kind))

    def _sync_pending_pills(self) -> None:
        button = self.schedule_options_button
        self.schedule_options_pills.set_state(button.start_date(), button.options())

    def _rebase_pending_options(self, old_date: str, new_date: str) -> None:
        """고른 날짜가 바뀌면 보류 중 값을 새 날짜 기준으로 옮긴다(기간 길이 유지, 지난 끝 날짜 해제)."""
        self.schedule_options_button.close_popup()
        options = self.schedule_options_button.options()
        try:
            moved = rules.rebase_options(options, old_date, new_date) if not options.is_default else options
        except ValueError:
            moved = ScheduleOptions()
        self.schedule_options_button.set_context(new_date)
        self._set_pending_options(moved)
```

(5) `ui_main.py` — `_on_add_schedule`: 보류 중 세부 설정과 함께 저장하고, 성공했을 때만 비운다. 찾을 원문:

```python
        try:
            new_id = db.add_schedule(self._selected_date, text, self._schedule_color)
            self.schedule_input.clear()
            self._after_schedule_change(highlight_id=new_id)
        except (sqlite3.Error, OSError, ValueError):
```

바꿀 코드:

```python
        try:
            new_id = db.add_schedule(
                self._selected_date, text, self._schedule_color,
                options=self.schedule_options_button.options(),
            )
            # 성공했을 때만 비운다(실패하면 본문·세부 설정을 그대로 둔다).
            self.schedule_input.clear()
            self._set_pending_options(ScheduleOptions())
            self._after_schedule_change(highlight_id=new_id)
        except (sqlite3.Error, OSError, ValueError):
```

(6) `ui_main.py` — `_apply_calendar_scale`: 크기 전환 때 이모지·세부 설정 카드를 닫는다. 찾을 원문:

```python
    def _apply_calendar_scale(self):
        """저장된 compact/medium/large 설정을 즉시 반영."""
        self._close_mini_apps()
```

바꿀 코드:

```python
    def _apply_calendar_scale(self):
        """저장된 compact/medium/large 설정을 즉시 반영."""
        self._close_mini_apps()
        self._close_schedule_emoji_popups()
```

(7) `ui_main.py` — `_discard_data_widgets`: 초기화 전 폐기 때 보류 중 값을 비운다. 찾을 원문:

```python
        self._finish_calendar_move_edit()
        self._close_schedule_emoji_popups()
        self._cancel_sticky_file_links()
        if self._finish_current_edit:
            self._finish_current_edit(False)
```

바꿀 코드:

```python
        self._finish_calendar_move_edit()
        self._close_schedule_emoji_popups()
        self._set_pending_options(ScheduleOptions())
        self._cancel_sticky_file_links()
        if self._finish_current_edit:
            self._finish_current_edit(False)
```

- [ ] **Step 4: 새 시험과 입력줄 관련 기존 시험을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_schedule_input.py tests/test_ui_schedule_options.py tests/test_ui_schedule_emoji.py tests/test_ui_schedule_list.py tests/test_ui_main_tidy.py tests/test_ui.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add ui_main.py tests/test_ui_schedule_input.py
git commit -m "feat: 일정 입력줄에 시계 버튼과 세부 설정 알약 연결

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```


### Task 11: 더블클릭 편집(시계·요약)과 반복 일정 지우기

**Files:**
- Modify: `ui_schedule_emoji.py` (import, `ScheduleInlineEditor`)
- Modify: `ui_main.py` (QtGui import, `_on_edit_schedule`, `_add_schedule_item`의 휴지통 연결, 우클릭 메뉴, 반복 삭제 도우미(새), `_on_skip_occurrence`(새), `_close_schedule_emoji_popups`)
- Test: `tests/test_ui_schedule_list.py` (시험 추가)

**Interfaces:**
- Consumes: Task 8의 `ScheduleOptionsButton`·`ElidedLabel`, Task 9의 `_schedule_tooltip`·`_after_schedule_change`·`_remove_schedule_item`·`_list_reload_pending`, `db.update_schedule(..., options=)`·`db.skip_schedule_occurrence`
- Produces
  - `ScheduleInlineEditor(content, can_edit, parent=None, *, options=None, start="", occurrence="")`
    - 속성 `options_button`·`summary_label`, 메서드 `options()`, 신호 `summary_changed()`
  - `MainCalendarWindow._on_delete_button(item, schedule_id, button)`, `_build_repeat_delete_menu(item)`, `_add_repeat_delete_actions(menu, item)`, `_on_skip_occurrence(item)`
  - 반복이 아닌 일정의 우클릭 메뉴는 지금처럼 `편집 / 삭제`(기존 시험 고정)

- [ ] **Step 1: 실패하는 시험을 추가한다** — `tests/test_ui_schedule_list.py` (끝에 붙인다)

```python
def test_editor_summary_and_option_save_apply_to_whole_series(qtbot):
    sid = db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    win = main_window(qtbot)
    item = win.schedule_list.item(0)
    win._on_edit_schedule(item)
    editor = win._schedule_editor
    qtbot.waitUntil(lambda: editor.edit.hasFocus())
    QApplication.processEvents()
    assert editor.summary_label.text() == "10:00 · 10분 전 · 매주 월요일 · 모든 날에 적용"
    assert editor.summary_label.isVisible()
    row = win.schedule_list.itemWidget(item)
    assert row.rect().contains(editor.geometry())
    assert editor.rect().contains(editor.options_button.geometry())
    editor.options_button.set_options(ScheduleOptions(start_time="10:00", repeat_rule="weekly",
                                                      alarm_before=30))
    assert win._finish_current_edit(True)
    assert db.get_schedules("2026-10-19")[0]["options"].alarm_before == 30
    qtbot.waitUntil(lambda: win.schedule_list.item(0).data(Qt.UserRole + 4).alarm_before == 30)
    assert win.schedule_list.item(0).data(Qt.UserRole) == sid


def test_text_only_edit_keeps_option_tooltip(qtbot):
    db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    win = main_window(qtbot)
    item = win.schedule_list.item(0)
    win._on_edit_schedule(item)
    win._schedule_editor.edit.setText("주간 업무 회의")
    assert win._finish_current_edit(True)
    label = win.schedule_list.itemWidget(item).schedule_text_label
    assert label.text() == "주간 업무 회의"
    assert label.toolTip().splitlines()[0] == "주간 업무 회의"
    assert "알림: 10분 전" in label.toolTip()


def test_turning_off_repeat_from_another_day_explains_first_date(qtbot):
    db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    win = main_window(qtbot)
    win._on_edit_schedule(win.schedule_list.item(0))
    button = win._schedule_editor.options_button
    qtbot.mouseClick(button, Qt.LeftButton)
    qtbot.waitUntil(lambda: button._popup is not None and button._popup.isVisible())
    card = button._popup
    qtbot.mouseClick(card.repeat_chips[""], Qt.LeftButton)
    assert card.series_note.isVisible()
    assert card.series_note.text() == "반복을 끄면 첫 날짜(10월 5일) 하루만 남습니다"


def test_failed_option_save_keeps_editor_and_blocks_navigation(qtbot, monkeypatch):
    db.add_schedule("2026-10-12", "회의")
    win = main_window(qtbot)
    win._on_edit_schedule(win.schedule_list.item(0))
    editor = win._schedule_editor
    editor.options_button.set_options(ScheduleOptions(start_time="09:00"))

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic failure")

    monkeypatch.setattr(db, "update_schedule", fail)
    assert win._finish_current_edit(True) is False
    win._on_date_selected("2026-10-13")
    assert win._selected_date == "2026-10-12"
    assert win._schedule_editor is editor
    assert db.get_schedules("2026-10-12")[0]["options"] == ScheduleOptions()


def test_reload_waits_while_another_row_is_being_edited(qtbot):
    db.add_schedule("2026-10-12", "첫째")
    db.add_schedule("2026-10-12", "둘째")
    win = main_window(qtbot)
    first, second = win.schedule_list.item(0), win.schedule_list.item(1)
    win._on_edit_schedule(first)
    win._schedule_editor.options_button.set_options(ScheduleOptions(start_time="09:00"))
    win._on_edit_schedule(second)  # 첫째 저장(목록 다시 만들기는 미룸) 뒤 둘째 편집
    QApplication.processEvents()
    assert win._editing_item is second
    assert win._list_reload_pending is True
    assert win._finish_current_edit(False)
    qtbot.waitUntil(lambda: not win._list_reload_pending)
    assert texts(win) == ["둘째", "첫째"]  # 시각 있는 첫째가 뒤로 간다.


def test_repeat_trash_offers_this_day_or_whole_series(qtbot, monkeypatch):
    sid = db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    win = main_window(qtbot)
    shown = []
    monkeypatch.setattr(ui_main.RoundMenu, "exec", lambda self, pos: shown.append(self))
    item = win.schedule_list.item(0)
    row = win.schedule_list.itemWidget(item)
    row.delete_button.click()
    assert len(shown) == 1
    actions = [a for a in shown[0].menuActions() if not a.isSeparator()]
    assert [a.text() for a in actions] == ["이 날만 삭제", "반복 전체 삭제"]
    actions[0].trigger()
    assert win.schedule_list.count() == 0
    assert db.get_schedules("2026-10-12") == []
    assert [s["id"] for s in db.get_schedules("2026-10-19")] == [sid]
    win._on_date_selected("2026-10-19")
    menu = win._build_repeat_delete_menu(win.schedule_list.item(0))
    qtbot.addWidget(menu)
    [a for a in menu.menuActions() if not a.isSeparator()][1].trigger()
    assert db.get_schedules("2026-10-26") == []
    with db._connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 0


def test_single_day_trash_deletes_immediately(qtbot, monkeypatch):
    db.add_schedule("2026-10-12", "하루 일정")
    win = main_window(qtbot)
    shown = []
    monkeypatch.setattr(ui_main.RoundMenu, "exec", lambda self, pos: shown.append(self))
    win.schedule_list.itemWidget(win.schedule_list.item(0)).delete_button.click()
    assert shown == []
    assert db.get_schedules("2026-10-12") == []


def test_context_menu_for_repeat_and_single_rows(qtbot):
    db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    db.add_schedule("2026-10-12", "하루 일정")
    win = main_window(qtbot)
    for index, expected in ((0, ["편집", "삭제"]), (1, ["편집", "이 날만 삭제", "반복 전체 삭제"])):
        menu = win._build_schedule_context_menu(win.schedule_list.item(index))
        qtbot.addWidget(menu)
        assert [a.text() for a in menu.menuActions() if not a.isSeparator()] == expected


def test_locked_window_ignores_trash_and_skip(qtbot, monkeypatch):
    db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    win = main_window(qtbot)
    shown = []
    monkeypatch.setattr(ui_main.RoundMenu, "exec", lambda self, pos: shown.append(self))
    win._is_locked = True
    item = win.schedule_list.item(0)
    win._on_delete_button(item, item.data(Qt.UserRole), win.schedule_list.itemWidget(item).delete_button)
    win._on_skip_occurrence(item)
    assert shown == []
    assert len(db.get_schedules("2026-10-12")) == 1


@pytest.mark.parametrize("action", ["lock", "tray", "reset", "scale"])
def test_editor_card_closes_on_lifecycle_and_ignores_late_change(qtbot, action):
    db.add_schedule("2026-10-12", "회의")
    win = main_window(qtbot)
    win._on_edit_schedule(win.schedule_list.item(0))
    button = win._schedule_editor.options_button
    qtbot.mouseClick(button, Qt.LeftButton)
    qtbot.waitUntil(lambda: button._popup is not None and button._popup.isVisible())
    card = button._popup
    if action == "lock":
        win._lock()
    elif action == "tray":
        win._minimize_to_tray()
    elif action == "reset":
        win._discard_data_widgets()
    else:
        db.save_setting(db.SETTING_CALENDAR_SCALE, "medium")
        win._apply_calendar_scale()
    assert not card.isVisible()
    card.options_changed.emit(ScheduleOptions(start_time="11:00"))
    assert button.options() == ScheduleOptions()
    assert db.get_schedules("2026-10-12")[0]["options"] == ScheduleOptions()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()
    assert not isValid(card)


def test_legacy_date_row_still_edits_text_but_not_options(qtbot):
    """Review Focus 1: 형식이 다른 옛 날짜 일정도 보이고 본문을 고칠 수 있으며 화면이 멈추지 않는다."""
    with db._connection() as conn:
        conn.execute("INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
                     ("2026-7-1", db.encrypt("옛 형식 일정"), "2026-01-01 00:00:00", "#FFD166"))
        conn.commit()
    win = main_window(qtbot)
    win._navigate_to_date("2026-7-1")
    assert texts(win) == ["옛 형식 일정"]
    assert not win.schedule_options_button.isEnabled()
    win._on_edit_schedule(win.schedule_list.item(0))
    editor = win._schedule_editor
    assert not editor.options_button.isEnabled()
    editor.options_button.open_popup()
    assert editor.options_button._popup is None
    editor.edit.setText("고친 옛 일정")
    assert win._finish_current_edit(True)
    assert [s["content"] for s in db.get_schedules("2026-7-1")] == ["고친 옛 일정"]
    win._on_date_selected("2026-07-02")
    assert win.schedule_options_button.isEnabled()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_schedule_list.py -q`
Expected: FAIL — `AttributeError: 'ScheduleInlineEditor' object has no attribute 'summary_label'` 등

- [ ] **Step 3: 편집기(이모지 모듈)를 바꾼다**

(1) `ui_schedule_emoji.py` — import: 편집기가 쓰는 규칙·부품을 더한다. 찾을 원문:

```python
# 지름·팝업 위치는 세부 설정 모듈로 옮겼고, 기존 import 경로를 위해 이 이름으로 다시 내보낸다.
from ui_schedule_options import SCHEDULE_CONTROL_DIAMETER, popup_position  # noqa: F401
```

바꿀 코드:

```python
import schedule_rules as rules
from schedule_rules import ScheduleOptions
# 지름·팝업 위치는 세부 설정 모듈로 옮겼고, 기존 import 경로를 위해 이 이름으로 다시 내보낸다.
from ui_schedule_options import (  # noqa: F401
    SCHEDULE_CONTROL_DIAMETER, ElidedLabel, ScheduleOptionsButton, popup_position,
)
```

(2) `ui_schedule_emoji.py` — `ScheduleInlineEditor` 앞부분: [스마일][시계][본문] + 요약 줄. 찾을 원문:

```python
class ScheduleInlineEditor(QWidget):
    finish_requested = Signal(bool)

    def __init__(self, content: str, can_edit, parent=None):
        super().__init__(parent)
        self._active = True
        self._can_edit = can_edit
        self.edit = QLineEdit(content, self)
        self.edit.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.edit.setStyleSheet(
            "background:#FFFFFF;border:1px solid #0078D4;"
            "border-radius:3px;padding:1px 4px;"
        )
        self.emoji_button = ScheduleEmojiButton(self.edit, self.can_edit, self)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(self.emoji_button)
        row.addWidget(self.edit, 1)
        self._focus_timer = QTimer(self)
        self._focus_timer.setSingleShot(True)
        self._focus_timer.timeout.connect(self._check_focus)
        self.edit.installEventFilter(self)
        self.emoji_button.installEventFilter(self)
        self.edit.returnPressed.connect(lambda: self.finish_requested.emit(True))
        self.emoji_button.popup_closed.connect(lambda: self._focus_timer.start(0))
```

바꿀 코드:

```python
class ScheduleInlineEditor(QWidget):
    """[스마일][시계][본문] 한 줄 + 세부 설정 요약 한 줄. 두 팝업까지 하나의 편집 영역이다."""
    finish_requested = Signal(bool)
    summary_changed = Signal()

    def __init__(self, content: str, can_edit, parent=None, *,
                 options: ScheduleOptions | None = None, start: str = "", occurrence: str = ""):
        super().__init__(parent)
        self._active = True
        self._can_edit = can_edit
        self.edit = QLineEdit(content, self)
        self.edit.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.edit.setStyleSheet(
            "background:#FFFFFF;border:1px solid #0078D4;"
            "border-radius:3px;padding:1px 4px;"
        )
        self.emoji_button = ScheduleEmojiButton(self.edit, self.can_edit, self)
        self.options_button = ScheduleOptionsButton(self.edit, self.can_edit, self)
        self.options_button.set_context(start, occurrence)
        self.options_button.set_options(options or ScheduleOptions())
        self.summary_label = ElidedLabel("", self)
        self.summary_label.setObjectName("scheduleEditorSummary")
        self.summary_label.setStyleSheet("color:#5B6577;font-size:11px;background:transparent;")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(self.emoji_button)
        row.addWidget(self.options_button)
        row.addWidget(self.edit, 1)
        column.addLayout(row)
        column.addWidget(self.summary_label)
        self._focus_timer = QTimer(self)
        self._focus_timer.setSingleShot(True)
        self._focus_timer.timeout.connect(self._check_focus)
        self.edit.installEventFilter(self)
        self.emoji_button.installEventFilter(self)
        self.options_button.installEventFilter(self)
        self.edit.returnPressed.connect(lambda: self.finish_requested.emit(True))
        self.emoji_button.popup_closed.connect(lambda: self._focus_timer.start(0))
        self.options_button.popup_closed.connect(lambda: self._focus_timer.start(0))
        self.options_button.options_changed.connect(lambda _options: self._sync_summary())
        self._sync_summary()

    def options(self) -> ScheduleOptions:
        return self.options_button.options()

    def _sync_summary(self) -> None:
        options = self.options()
        start = self.options_button.start_date()
        summary = ""
        if start and not options.is_default:
            try:
                summary = rules.options_summary(start, options)
            except ValueError:
                summary = ""
            if summary and options.repeat_rule:
                summary += " · 모든 날에 적용"
        self.summary_label.setText(summary)
        self.summary_label.setToolTip(summary)
        self.summary_label.setVisible(bool(summary))
        self.summary_changed.emit()
```

(3) `ui_schedule_emoji.py` — `_check_focus`: 세부 설정 카드가 열려 있어도 저장·종료하지 않는다. 찾을 원문:

```python
    def _check_focus(self) -> None:
        if not self.can_edit() or self.emoji_button._popup is not None:
            return
```

바꿀 코드:

```python
    def _check_focus(self) -> None:
        if (not self.can_edit() or self.emoji_button._popup is not None
                or self.options_button._popup is not None):
            return
```

(4) `ui_schedule_emoji.py` — `deactivate`: 세부 설정 카드도 닫는다. 찾을 원문:

```python
    def deactivate(self) -> None:
        self._active = False
        self._focus_timer.stop()
        self.emoji_button.close_popup()
```

바꿀 코드:

```python
    def deactivate(self) -> None:
        self._active = False
        self._focus_timer.stop()
        self.emoji_button.close_popup()
        self.options_button.close_popup()
```

- [ ] **Step 4: 메인 창의 편집·삭제를 바꾼다**

(1) `ui_main.py` — QtGui import에 `QIcon`을 더한다(삭제 메뉴 아이콘). 찾을 원문:

```python
from PySide6.QtGui import QFont, QFontMetrics, QDesktopServices, QPainter, QBrush, QPen, QColor, QRegion
```

바꿀 코드:

```python
from PySide6.QtGui import (
    QFont, QFontMetrics, QDesktopServices, QPainter, QBrush, QPen, QColor, QRegion, QIcon,
)
```

(2) `ui_main.py` — `_on_edit_schedule`: 세부 설정·시작 날짜·그 날짜를 읽는다. 찾을 원문:

```python
        old_text = item.data(Qt.UserRole + 1)
        editing_date = self._selected_date
```

바꿀 코드:

```python
        old_text = item.data(Qt.UserRole + 1)
        old_options = item.data(Qt.UserRole + 4) or ScheduleOptions()
        series_start = item.data(Qt.UserRole + 5) or self._selected_date
        occurrence = item.data(Qt.UserRole + 6) or self._selected_date
        editing_date = self._selected_date
```

(3) `ui_main.py` — `_on_edit_schedule`: 편집기에 세부 설정을 넘기고 요약 줄 높이를 따라간다. 찾을 원문:

```python
        editor = ScheduleInlineEditor(old_text, self._schedule_emoji_allowed, row_widget)
        self._schedule_editor = editor
        edit = editor.edit
        layout.insertWidget(layout.indexOf(text_box) + 1, editor, 1)
        editor.show()
        item.setSizeHint(row_widget.sizeHint())
```

바꿀 코드:

```python
        # 반복 일정을 고치면 시리즈 전체가 바뀐다. 기준 날짜는 시리즈의 시작 날짜다.
        editor = ScheduleInlineEditor(
            old_text, self._schedule_emoji_allowed, row_widget,
            options=old_options, start=series_start, occurrence=occurrence,
        )
        self._schedule_editor = editor
        edit = editor.edit
        layout.insertWidget(layout.indexOf(text_box) + 1, editor, 1)
        editor.show()
        item.setSizeHint(row_widget.sizeHint())
        editor.summary_changed.connect(lambda: item.setSizeHint(row_widget.sizeHint()))
```

(4) `ui_main.py` — `_finish_edit`: 본문 또는 세부 설정이 바뀌면 한 번에 저장한다. 찾을 원문:

```python
            new_text = old_text if edit.text() == old_text else edit.text().strip()

            if save and new_text and new_text != old_text:
                try:
                    db.update_schedule(schedule_id, content=new_text)
                except (sqlite3.Error, OSError, ValueError) as exc:
```

바꿀 코드:

```python
            new_text = old_text if edit.text() == old_text else edit.text().strip()
            new_options = editor.options()
            text_changed = bool(new_text) and new_text != old_text
            options_changed = new_options != old_options

            if save and (text_changed or options_changed):
                try:
                    db.update_schedule(
                        schedule_id,
                        content=new_text if text_changed else None,
                        options=new_options if options_changed else None,
                    )
                except (sqlite3.Error, OSError, ValueError) as exc:
```

(5) `ui_main.py` — `_finish_edit`: 저장한 값만 줄에 반영한다. 찾을 원문:

```python
                text_label.setText(new_text)
                text_label.setToolTip(new_text)
                item.setData(Qt.UserRole + 1, new_text)
                self._refresh_cell_for_date(editing_date)
```

바꿀 코드:

```python
                if text_changed:
                    text_label.setText(new_text)
                    text_label.setToolTip(self._schedule_tooltip(new_text, new_options, series_start))
                    item.setData(Qt.UserRole + 1, new_text)
                if options_changed:
                    item.setData(Qt.UserRole + 4, new_options)
            else:
                text_changed = options_changed = False
```

(6) `ui_main.py` — `_finish_edit` 끝: 세부 설정이 바뀌면 순서·시각 열을 위해 목록을 다시 만든다(편집 종료 콜백이 끝난 뒤로 미룸). 찾을 원문:

```python
            item.setSizeHint(row_widget.sizeHint())
            if self._list_reload_pending:
                QTimer.singleShot(0, self, self._after_schedule_change)
            return True
```

바꿀 코드:

```python
            item.setSizeHint(row_widget.sizeHint())
            if options_changed or self._list_reload_pending:
                QTimer.singleShot(0, self, self._after_schedule_change)
            elif text_changed:
                self._refresh_cell_for_date(editing_date)
            return True
```

(7) `ui_main.py` — `_add_schedule_item`: 휴지통은 반복 일정이면 메뉴를 연다. 찾을 원문:

```python
        delete_btn.clicked.connect(
            lambda checked=False, i=item, sid=schedule_id: self._on_delete_schedule(i, sid)
        )
```

바꿀 코드:

```python
        delete_btn.clicked.connect(
            lambda checked=False, i=item, sid=schedule_id, b=delete_btn:
                self._on_delete_button(i, sid, b)
        )
```

(8) `ui_main.py` — 우클릭 메뉴: 반복 일정은 편집 / ─ / 이 날만 삭제 / 반복 전체 삭제. 찾을 원문:

```python
        edit_action = Action(FIF.EDIT, "편집", menu)
        edit_action.triggered.connect(
            lambda checked=False, i=item: self._on_edit_schedule(i)
        )
        menu.addAction(edit_action)

        delete_action = Action(FIF.DELETE, "삭제", menu)
```

바꿀 코드:

```python
        edit_action = Action(FIF.EDIT, "편집", menu)
        edit_action.triggered.connect(
            lambda checked=False, i=item: self._on_edit_schedule(i)
        )
        menu.addAction(edit_action)

        options = item.data(Qt.UserRole + 4)
        if options is not None and options.repeat_rule:
            menu.addSeparator()
            self._add_repeat_delete_actions(menu, item)
            return menu

        delete_action = Action(FIF.DELETE, "삭제", menu)
```

(9) `ui_main.py` — 반복 삭제 메뉴 도우미를 우클릭 메뉴 처리기 앞에 더한다. 이 원문 바로 앞에:

```python
    def _on_schedule_context_menu(self, pos: QPoint):
```

넣을 코드:

```python
    def _add_repeat_delete_actions(self, menu: "RoundMenu", item: QListWidgetItem) -> None:
        """반복 일정 지우기: 이 날만(달력 아이콘) / 반복 전체(빨간 반복 아이콘)."""
        ratio = self.devicePixelRatioF()
        skip_action = Action(QIcon(icon_pixmap("calendar", 16, "#475569", ratio)), "이 날만 삭제", menu)
        skip_action.triggered.connect(lambda checked=False, i=item: self._on_skip_occurrence(i))
        menu.addAction(skip_action)
        all_action = Action(QIcon(icon_pixmap("repeat", 16, "#D32F2F", ratio)), "반복 전체 삭제", menu)
        all_action.triggered.connect(
            lambda checked=False, i=item: self._on_delete_schedule(i, i.data(Qt.UserRole)))
        menu.addAction(all_action)

    def _build_repeat_delete_menu(self, item: QListWidgetItem) -> "RoundMenu":
        menu = RoundMenu(parent=self)
        menu.setWindowOpacity(1.0)
        self._apply_header_menu_style(menu)
        self._add_repeat_delete_actions(menu, item)
        return menu

    def _on_delete_button(self, item: QListWidgetItem, schedule_id: int, button) -> None:
        """휴지통: 반복 일정이면 이 날만/반복 전체 메뉴, 아니면 지금처럼 바로 지운다."""
        if self._is_locked:
            return
        options = item.data(Qt.UserRole + 4)
        if options is None or not options.repeat_rule:
            self._on_delete_schedule(item, schedule_id)
            return
        menu = self._build_repeat_delete_menu(item)
        menu.closedSignal.connect(menu.deleteLater)
        menu.exec(button.mapToGlobal(QPoint(0, button.height())))

```

(10) `ui_main.py` — '이 날만 삭제' 처리기를 `_on_delete_schedule` 앞에 더한다. 이 원문 바로 앞에:

```python
    def _on_delete_schedule(self, item: QListWidgetItem, schedule_id: int):
```

넣을 코드:

```python
    def _on_skip_occurrence(self, item: QListWidgetItem) -> None:
        """반복 일정의 이 날 하나만 지운다(건너뛴 날에 더한다)."""
        if self._is_locked:
            return
        try:
            db.skip_schedule_occurrence(item.data(Qt.UserRole), item.data(Qt.UserRole + 6))
        except (sqlite3.Error, OSError, ValueError) as exc:
            _logger.error("반복 일정 이 날만 삭제 실패: %s", exc)
            InfoBar.error(
                title="삭제 오류",
                content="일정 삭제 중 오류가 발생했습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=3000,
            )
            return
        if self._editing_item is item and self._finish_current_edit:
            self._finish_current_edit(False)
        self._remove_schedule_item(item)
        self._refresh_month_data()
        self._update_count()

```

(11) `ui_main.py` — `_close_schedule_emoji_popups`: 편집기의 세부 설정 카드도 닫는다. 찾을 원문:

```python
        if self._schedule_editor is not None:
            self._schedule_editor.emoji_button.close_popup()
```

바꿀 코드:

```python
        if self._schedule_editor is not None:
            self._schedule_editor.emoji_button.close_popup()
            self._schedule_editor.options_button.close_popup()
```

- [ ] **Step 5: 새 시험과 편집·이모지·우클릭 기존 시험을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_schedule_list.py tests/test_ui_schedule_emoji.py tests/test_ui_schedule_input.py tests/test_ui.py -q`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add ui_schedule_emoji.py ui_main.py tests/test_ui_schedule_list.py
git commit -m "feat: 일정 편집에 세부 설정·요약 줄, 반복 일정 이 날만/전체 삭제

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```


### Task 12: 중간·크게 달력의 여러 날 막대

**Files:**
- Create: `ui_calendar_spans.py`
- Modify: `ui_main.py` (`CalendarDayButton` 신호·속성·`set_events`, import, `_build_ui`, `_refresh_calendar`, `_refresh_month_data`)
- Test: `tests/test_ui_calendar_spans.py` (시험 추가)

**Interfaces:**
- Consumes: `rules.week_segments`·`rules.SpanSegment`, Task 9의 `_refresh_month_data`
- Produces
  - `ui_calendar_spans.SpanBar(segment, text, color)`, `CalendarSpanOverlay(section, grid_layout)`
    - `set_bars(cells, bars, *, font_px, visible)`, `bars()`, `bar_rects()->[(SpanBar, QRectF)]`(오버레이 좌표)
  - `CalendarDayButton`
    - 신호 `layout_changed()`, 속성 `chips_container`·`chips_layout`·`chip_height`·`chip_spacing`·`span_lane_cap`
    - `set_events(events, span_lanes=None)`(기존 호출 `set_events(events)`는 그대로 동작)
  - `MainCalendarWindow._calendar_section`, `_grid_cells`(주마다 7칸), `_span_overlay`

- [ ] **Step 1: 실패하는 시험을 추가한다** — `tests/test_ui_calendar_spans.py` (끝에 붙인다)

```python
def overlay_x(win, cell, x):
    return cell.mapTo(win._calendar_section, QPoint(x, 0)).x() - win._span_overlay.x()


def bars(win):
    return {(bar.segment.key, bar.segment.row): (bar, rect) for bar, rect in win._span_overlay.bar_rects()}


def test_bars_follow_columns_lanes_and_break_at_week_edges(qtbot, monkeypatch):
    long_id = db.add_schedule("2026-10-08", "출장 " * 20, "#4CC9F0",
                              options=ScheduleOptions(start_time="09:00", end_date="2026-10-12"))
    short_id = db.add_schedule("2026-10-09", "교육", options=ScheduleOptions(end_date="2026-10-10"))
    win = calendar_window(qtbot, monkeypatch, "medium")
    found = bars(win)
    first_bar, first = found[(long_id, 1)]
    second_bar, second = found[(long_id, 2)]
    lane_bar, lane = found[(short_id, 1)]
    start_cell, sat_cell = win._day_cells["2026-10-08"], win._day_cells["2026-10-10"]
    sun_cell, end_cell = win._day_cells["2026-10-11"], win._day_cells["2026-10-12"]
    assert first.left() == overlay_x(win, start_cell, 6)
    assert first.right() == overlay_x(win, sat_cell, sat_cell.width())
    assert second.left() == overlay_x(win, sun_cell, 0)
    assert second.right() == overlay_x(win, end_cell, end_cell.width() - 4)
    assert (first_bar.segment.starts, first_bar.segment.ends) == (True, False)
    assert (second_bar.segment.starts, second_bar.segment.ends) == (False, True)
    assert first_bar.text.startswith("09:00 출장") and not second_bar.text.startswith("09:00")
    assert lane_bar.segment.lane == 1
    assert lane.top() == first.top() + start_cell.chip_height + start_cell.chip_spacing
    assert first.height() == start_cell.chip_height == 16
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        assert win.grab().save(str(Path(appdata).parent / "calendar-span-medium.png"))


def test_bar_from_previous_month_has_square_start_next_to_blank_cells(qtbot, monkeypatch):
    """Review Focus 5: 달 첫 주 빈칸 옆에서 지난달부터 이어진 막대는 왼쪽 끝이 각지다."""
    span = db.add_schedule("2026-09-29", "월말 출장", options=ScheduleOptions(end_date="2026-10-02"))
    win = calendar_window(qtbot, monkeypatch, "large")
    bar, rect = bars(win)[(span, 0)]
    first_cell = win._day_cells["2026-10-01"]
    assert (bar.segment.first_col, bar.segment.starts, bar.segment.ends) == (4, False, True)
    assert rect.left() == overlay_x(win, first_cell, 0)
    assert rect.height() == 22


def test_cells_reserve_bar_lanes_and_count_hidden_ones(qtbot, monkeypatch):
    for index in range(4):
        db.add_schedule("2026-10-13", f"기간 {index}", options=ScheduleOptions(end_date="2026-10-15"))
    for index in range(3):
        db.add_schedule("2026-10-14", f"하루 {index}")
    win = calendar_window(qtbot, monkeypatch, "medium")
    cell = win._day_cells["2026-10-14"]
    layout = cell.chips_layout
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    slots = [w for w in widgets if w.objectName() == "calendarSpanSlot"]
    chips = [w for w in widgets if w.objectName() != "calendarSpanSlot"]
    assert len(slots) == min(4, cell.span_lane_cap)
    shown_bars = [b for b, _rect in win._span_overlay.bar_rects() if b.segment.row == 2]
    assert len(shown_bars) == len(slots)
    hidden_lanes = 4 - len(slots)
    if hidden_lanes or len(chips) < 3:
        shown_singles = len(chips) - 1
        assert chips[-1].text() == f"+{3 - shown_singles + hidden_lanes} 더"
    assert not cell.count_label.isVisibleTo(cell)  # 중간·크게는 '+N' 숫자 대신 칩을 쓴다


@pytest.mark.parametrize("scale,screen", [("large", (864, 1536)), ("medium", (1440, 2560))])
def test_bars_do_not_change_column_widths_and_follow_resize(qtbot, monkeypatch, scale, screen):
    win = calendar_window(qtbot, monkeypatch, scale, screen=screen)
    before = [win.calendar_grid.cellRect(1, col).width() for col in range(7)]
    span = db.add_schedule("2026-10-06", "아주 긴 기간 일정 제목 " * 10,
                           options=ScheduleOptions(end_date="2026-10-16"))
    win._refresh_month_data()
    qtbot.wait(80)
    widths = [win.calendar_grid.cellRect(1, col).width() for col in range(7)]
    assert widths == before
    assert max(widths) - min(widths) <= 1
    section = win.right_content.findChild(QWidget, "calendarSection")
    headers = [item for item in section.findChildren(QGridLayout)
               if item is not win.calendar_grid and item.count() == 7]
    assert len(headers) == 1
    win.resize(win.width() - 40, win.height())
    qtbot.wait(120)
    _bar, rect = bars(win)[(span, 1)]
    assert rect.left() == overlay_x(win, win._day_cells["2026-10-06"], 6)


def test_scale_switch_hides_and_shows_bars(qtbot, monkeypatch):
    db.add_schedule("2026-10-13", "기간", options=ScheduleOptions(end_date="2026-10-15"))
    win = calendar_window(qtbot, monkeypatch, "medium")
    assert win._span_overlay.isVisible()
    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
    win._apply_calendar_scale()
    QApplication.processEvents()
    assert win._span_overlay.isHidden()
    assert win._day_cells["2026-10-14"]._count == 1
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win._apply_calendar_scale()
    qtbot.wait(120)
    assert win._span_overlay.isVisible()
    assert all(rect.height() == 22 for _bar, rect in win._span_overlay.bar_rects())


def test_period_is_a_bar_not_a_chip(qtbot, monkeypatch):
    db.add_schedule("2026-10-13", "기간", options=ScheduleOptions(end_date="2026-10-14"))
    win = calendar_window(qtbot, monkeypatch, "medium")
    layout = win._day_cells["2026-10-13"].chips_layout
    names = [layout.itemAt(i).widget().objectName() for i in range(layout.count())]
    assert names == ["calendarSpanSlot"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_calendar_spans.py -q`
Expected: FAIL — `AttributeError: ... '_span_overlay'`

- [ ] **Step 3: 막대 오버레이 모듈을 만든다**

(1) `ui_calendar_spans.py`를 새로 만든다(파일 전체).

```python
"""중간·크게 달력의 여러 날 일정 막대 (v4.1).

칸 위에 그리기만 하고 마우스는 통과시킨다. 막대 위치는 그릴 때마다 칸과 칸의 칩 자리에서
다시 읽으므로 크기·배율이 바뀌어도 칩과 같은 선(시작 6px·끝 4px)에 맞는다.
"""
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from schedule_rules import SpanSegment

BAR_RADIUS = 4.0


@dataclass(frozen=True)
class SpanBar:
    """그릴 막대 한 조각."""

    segment: SpanSegment
    text: str
    color: str


class CalendarSpanOverlay(QWidget):
    def __init__(self, section: QWidget, grid_layout):
        super().__init__(section)
        self.setObjectName("calendarSpanOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._grid = grid_layout
        self._cells: list[list[QWidget]] = []
        self._bars: list[SpanBar] = []
        self._font_px = 10
        section.installEventFilter(self)
        self.hide()

    def set_bars(self, cells, bars, *, font_px: int, visible: bool) -> None:
        """cells: 주마다 7칸(CalendarDayButton), bars: SpanBar 목록."""
        self._cells = [list(row) for row in cells]
        self._bars = list(bars)
        self._font_px = font_px
        self.setVisible(visible and bool(self._bars))
        self._sync_geometry()

    def bars(self) -> list[SpanBar]:
        return list(self._bars)

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() in (
                QEvent.Resize, QEvent.LayoutRequest, QEvent.Show):
            self._sync_geometry()
        return False

    def _sync_geometry(self) -> None:
        if self.isHidden():
            return
        self.setGeometry(self._grid.geometry())
        self.raise_()
        self.update()

    def _local(self, widget: QWidget, point: QPoint) -> QPoint:
        return widget.mapTo(self.parentWidget(), point) - self.pos()

    def bar_rects(self) -> list[tuple[SpanBar, QRectF]]:
        """지금 칸 배치에서 보이는 막대와 그 사각형(이 위젯 좌표)."""
        result = []
        for bar in self._bars:
            seg = bar.segment
            if seg.row >= len(self._cells):
                continue
            row = self._cells[seg.row]
            first, last = row[seg.first_col], row[seg.last_col]
            if seg.lane >= min(first.span_lane_cap, last.span_lane_cap):
                continue  # 칸에 자리가 없는 차선은 그날 '+N 더'로 센다.
            container = first.chips_container
            margins = first.chips_layout.contentsMargins()
            top_left = self._local(container, QPoint(0, 0))
            first_left = self._local(first, QPoint(0, 0)).x()
            last_right = self._local(last, QPoint(last.width(), 0)).x()
            last_container_right = self._local(
                last.chips_container, QPoint(last.chips_container.width(), 0)).x()
            left = top_left.x() + margins.left() if seg.starts else first_left
            right = last_container_right - margins.right() if seg.ends else last_right
            step = first.chip_height + first.chip_spacing
            top = top_left.y() + seg.lane * step
            if right - left < 4:
                continue
            result.append((bar, QRectF(left, top, right - left, first.chip_height)))
        return result

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        font = self.font()
        font.setPixelSize(self._font_px)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        for bar, rect in self.bar_rects():
            seg = bar.segment
            path = QPainterPath()
            path.addRoundedRect(rect, BAR_RADIUS, BAR_RADIUS)
            if not seg.starts:
                square = QPainterPath()
                square.addRect(QRectF(rect.left(), rect.top(), BAR_RADIUS * 2, rect.height()))
                path = path.united(square)
            if not seg.ends:
                square = QPainterPath()
                square.addRect(QRectF(rect.right() - BAR_RADIUS * 2, rect.top(), BAR_RADIUS * 2, rect.height()))
                path = path.united(square)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(bar.color))
            painter.drawPath(path)
            text_rect = rect.adjusted(4, 0, -4, 0)
            text = metrics.elidedText(bar.text, Qt.ElideRight, int(text_rect.width()))
            painter.setPen(QColor("#1A1A1A"))
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
```

- [ ] **Step 4: 달력 칸이 막대 자리를 비우게 한다**

(1) `ui_main.py` — `CalendarDayButton`: 배치 신호. 찾을 원문:

```python
class CalendarDayButton(QWidget):
    """달력 날짜 셀 위젯 (compact / expanded 2-모드)"""

    _CHIP_HEIGHT = 16
```

바꿀 코드:

```python
class CalendarDayButton(QWidget):
    """달력 날짜 셀 위젯 (compact / expanded 2-모드)"""

    layout_changed = Signal()  # 중간·크게 칩을 다시 놓았을 때(막대 오버레이가 다시 그린다)
    _CHIP_HEIGHT = 16
```

(2) `ui_main.py` — `CalendarDayButton.__init__`: 막대 차선 상태. 찾을 원문:

```python
        self._count = count
        self._events = []
        self._rendering_events = False
```

바꿀 코드:

```python
        self._count = count
        self._events = []
        self._span_lanes = []
        self.span_lane_cap = 0  # 이 칸 높이에서 막대에 내줄 수 있는 차선 수(칩 자리 - 1)
        self._rendering_events = False
```

(3) `ui_main.py` — `CalendarDayButton`: 오버레이가 읽는 읽기 전용 속성을 `set_count` 앞에 더한다. 이 원문 바로 앞에:

```python
    def set_count(self, n: int):
```

넣을 코드:

```python
    @property
    def chips_container(self) -> QWidget:
        return self._chips_container

    @property
    def chips_layout(self) -> QVBoxLayout:
        return self._chips_layout

    @property
    def chip_height(self) -> int:
        return self._chip_height

    @property
    def chip_spacing(self) -> int:
        return self._chip_spacing

```

(4) `ui_main.py` — `CalendarDayButton.set_events`: 막대 차선만큼 칩 자리를 비우고, 자리가 없는 막대는 '+N 더'에 센다(막대가 없으면 지금과 같은 규칙). 찾을 원문:

```python
    def set_events(self, events: list):
        """expanded 셀 일정 칩 데이터를 갱신한다."""
        self._events = list(events)
        if self._mode != "expanded" or self._rendering_events:
            return
        self._rendering_events = True
        try:
            while self._chips_layout.count():
                item = self._chips_layout.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()
            if not events:
                return
            avail_h = self._chips_container.height()
            per = self._chip_height + self._chip_spacing
            fit = max(1, avail_h // per) if avail_h > 0 else self._MAX_CHIPS
            max_show = min(self._MAX_CHIPS, fit)
            if len(events) > max_show:
                keep = max(1, max_show - 1)
                visible = events[:keep]
                remaining = len(events) - keep
            else:
                visible = events
                remaining = 0
            for event in visible:
                chip = self._make_chip(event["content"], event["color"])
                self._chips_layout.addWidget(chip)
                chip.show()
            if remaining > 0:
                overflow = self._make_chip(f"+{remaining} 더", "", dim=True)
                self._chips_layout.addWidget(overflow)
                overflow.show()
        finally:
            self._rendering_events = False
```

바꿀 코드:

```python
    def set_events(self, events: list, span_lanes: list | None = None):
        """expanded 셀 일정 칩 데이터를 갱신한다.

        span_lanes: 이 날을 덮는 여러 날 막대의 차선 번호들. 보이는 차선만큼 칩 자리를
        비워 두고(막대는 오버레이가 그린다), 자리가 없는 막대는 '+N 더'에 더한다.
        """
        self._events = list(events)
        if span_lanes is not None:
            self._span_lanes = sorted(span_lanes)
        if self._mode != "expanded" or self._rendering_events:
            return
        self._rendering_events = True
        try:
            while self._chips_layout.count():
                item = self._chips_layout.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()
            avail_h = self._chips_container.height()
            per = self._chip_height + self._chip_spacing
            fit = max(1, avail_h // per) if avail_h > 0 else self._MAX_CHIPS
            max_show = min(self._MAX_CHIPS, fit)
            self.span_lane_cap = max(0, max_show - 1)
            lanes = self._span_lanes
            lane_rows = min(lanes[-1] + 1, self.span_lane_cap) if lanes else 0
            hidden = sum(1 for lane in lanes if lane >= lane_rows)
            for _ in range(lane_rows):
                slot = QWidget(self._chips_container)
                slot.setObjectName("calendarSpanSlot")
                slot.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                slot.setFixedHeight(self._chip_height)
                self._chips_layout.addWidget(slot)
                slot.show()
            slots = max_show - lane_rows
            if hidden == 0 and len(events) <= slots:
                visible = events
                remaining = 0
            else:
                keep = max(1 if hidden == 0 else 0, slots - 1)
                visible = events[:keep]
                remaining = len(events) - len(visible) + hidden
            for event in visible:
                chip = self._make_chip(event["content"], event["color"])
                self._chips_layout.addWidget(chip)
                chip.show()
            if remaining > 0:
                overflow = self._make_chip(f"+{remaining} 더", "", dim=True)
                self._chips_layout.addWidget(overflow)
                overflow.show()
        finally:
            self._rendering_events = False
        self.layout_changed.emit()
```

- [ ] **Step 5: 메인 창에 오버레이를 연결한다**

(1) `ui_main.py` — import에 막대 오버레이를 더한다. 이 원문 바로 뒤에:

```python
from ui_schedule_options import (
    ElidePaintMixin, ScheduleOptionsButton, ScheduleOptionsPills, icon_pixmap,
)
```

넣을 코드:

```python
from ui_calendar_spans import CalendarSpanOverlay, SpanBar
```

(2) `ui_main.py` — `_build_ui`: 달력 격자 바로 뒤에 막대 오버레이를 만든다(레이아웃 밖, 마우스 통과). 이 원문 바로 뒤에:

```python
        calendar_layout.addLayout(self.calendar_grid)
```

넣을 코드:

```python
        self._calendar_section = calendar_section
        self._grid_cells = []  # 주마다 7칸(빈칸 포함)
        self._span_overlay = CalendarSpanOverlay(calendar_section, self.calendar_grid)
```

(3) `ui_main.py` — `_refresh_calendar`: 주마다 칸 목록을 새로 모은다. 이 원문 바로 뒤에:

```python
        self._style_weekday_header(calendar_scale)
```

넣을 코드:

```python
        self._grid_cells = []
```

(4) `ui_main.py` — `_refresh_calendar`: 주 줄 목록. 찾을 원문:

```python
        for row_idx, week in enumerate(cal):
            for col_idx, day in enumerate(week):
```

바꿀 코드:

```python
        for row_idx, week in enumerate(cal):
            self._grid_cells.append([])
            for col_idx, day in enumerate(week):
```

(5) `ui_main.py` — `_refresh_calendar`: 칸을 주 목록에 넣고 칸 배치가 바뀌면 막대를 다시 그린다. 찾을 원문:

```python
                    calendar_scale=calendar_scale,
                )
                if target_date:
```

바꿀 코드:

```python
                    calendar_scale=calendar_scale,
                )
                cell.layout_changed.connect(self._span_overlay.update)
                self._grid_cells[row_idx].append(cell)
                if target_date:
```

(6) `ui_main.py` — `_refresh_month_data`: 여러 날 일정은 칩 대신 막대로, 칸은 막대 차선 자리를 비운다. 찾을 원문:

```python
        expanded = self._current_calendar_scale() != "compact"
        for day, cell in self._day_cells.items():
            entries = month.get(day, [])
            cell._update_squares(self._cell_colors(entries, palette))
            cell.set_count(len(entries))
            if expanded:
                cell.set_events(self._chip_events(entries, palette))
```

바꿀 코드:

```python
        expanded = self._current_calendar_scale() != "compact"
        weeks = [[cell.target_date for cell in row] for row in self._grid_cells]
        spans = {}
        if expanded:
            for entries in month.values():
                for entry in entries:
                    if entry["span_start"] != entry["span_end"]:
                        spans.setdefault(entry["id"], entry)
        segments = rules.week_segments(
            weeks, {key: (e["span_start"], e["span_end"]) for key, e in spans.items()}
        ) if spans else []
        lanes_by_day = {}
        for segment in segments:
            for col in range(segment.first_col, segment.last_col + 1):
                lanes_by_day.setdefault(weeks[segment.row][col], []).append(segment.lane)
        for day, cell in self._day_cells.items():
            entries = month.get(day, [])
            cell._update_squares(self._cell_colors(entries, palette))
            cell.set_count(len(entries))
            if expanded:
                singles = [e for e in entries if e["span_start"] == e["span_end"]]
                cell.set_events(self._chip_events(singles, palette),
                                span_lanes=lanes_by_day.get(day, []))
        bars = []
        for segment in segments:
            entry = spans[segment.key]
            label = entry["content"]
            if segment.starts and entry["start_time"]:
                label = f"{entry['start_time']} {label}"
            bars.append(SpanBar(segment, label,
                                db.schedule_display_color(entry.get("color"), palette)))
        font_px = 13 if self._current_calendar_scale() == "large" else 10
        self._span_overlay.set_bars(self._grid_cells, bars, font_px=font_px, visible=expanded)
```

- [ ] **Step 6: 새 시험과 달력 열 너비·칸 기존 시험을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_calendar_spans.py tests/test_ui_calendar_columns.py tests/test_ui_calendar_cells.py tests/test_ui_calendar_count.py tests/test_ui.py tests/test_ui_schedule_emoji.py -q`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add ui_calendar_spans.py ui_main.py tests/test_ui_calendar_spans.py
git commit -m "feat: 중간·크게 달력에 여러 날 일정 막대

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```


### Task 13: 검색 결과의 반복·기간 꼬리

**Files:**
- Modify: `ui_search.py` (import, `_on_search`)
- Test: `tests/test_ui_schedule_list.py` (시험 추가)

**Interfaces:**
- Consumes: `db.search_all`의 `end_date`·`repeat_rule`(Task 5), `rules.search_suffix`(Task 3)
- Produces: 검색 표 본문 칸 = 본문(80자 말줄임) + ` (매주 목요일 반복)` 또는 ` (~10.23)`. 툴팁은 지금처럼 본문 전체

- [ ] **Step 1: 실패하는 시험을 추가한다** — `tests/test_ui_schedule_list.py` (끝에 붙인다)

```python
def test_search_shows_repeat_and_period_tail_without_changing_data(qtbot):
    db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    db.add_schedule("2026-10-21", "출장 보고", options=ScheduleOptions(end_date="2026-10-23"))
    db.add_schedule("2026-10-22", "일반 회의")
    with db._connection() as conn:
        before = [tuple(r) for r in conn.execute("SELECT * FROM schedules ORDER BY id")]
    search = SearchWindow()
    qtbot.addWidget(search)
    search._on_search(search_all=True)
    cells = {search.result_table.item(row, 0).text(): search.result_table.item(row, 2)
             for row in range(search.result_table.rowCount())}
    assert cells["2026-10-05"].text() == "주간 회의 (매주 월요일 반복)"
    assert cells["2026-10-21"].text() == "출장 보고 (~10.23)"
    assert cells["2026-10-22"].text() == "일반 회의"
    assert cells["2026-10-05"].toolTip() == "주간 회의"
    with db._connection() as conn:
        assert [tuple(r) for r in conn.execute("SELECT * FROM schedules ORDER BY id")] == before
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_schedule_list.py -q -k search`
Expected: FAIL — `'주간 회의' == '주간 회의 (매주 월요일 반복)'`

- [ ] **Step 3: 구현한다**

(1) `ui_search.py` — import. 찾을 원문:

```python
import database as db
from ui_window_card import TABLE_QSS, WindowCard
```

바꿀 코드:

```python
import database as db
from schedule_rules import ScheduleOptions, search_suffix
from ui_window_card import TABLE_QSS, WindowCard
```

(2) `ui_search.py` — `_on_search`: 일정 본문 칸 끝에 표시용 꼬리를 붙인다. 찾을 원문:

```python
            content_text = r["content"].replace('\n', ' ')
            if len(content_text) > 80:
                content_text = content_text[:80] + "..."
```

바꿀 코드:

```python
            content_text = r["content"].replace('\n', ' ')
            if len(content_text) > 80:
                content_text = content_text[:80] + "..."
            if r["type"] == "일정":
                # 반복·기간은 원본 한 줄(시작 날짜)에 표시용 꼬리만 붙인다(저장값은 그대로).
                content_text += search_suffix(r["date"], ScheduleOptions(
                    end_date=r.get("end_date", ""), repeat_rule=r.get("repeat_rule", "")))
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_schedule_list.py tests/test_ui_schedule_emoji.py tests/test_ui.py -q`
Expected: PASS (기존 검색 시험의 `item(0, 2).text().startswith(...)`·`toolTip() == content`도 그대로)

- [ ] **Step 5: 커밋**

```bash
git add ui_search.py tests/test_ui_schedule_list.py
git commit -m "feat: 검색 결과에 반복·기간 표시 꼬리

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```


### Task 14: 일정 알림 엔진과 알림 카드

**Files:**
- Create: `ui_schedule_alarm.py`
- Modify: `ui_main.py` (import, 생성자, `_after_schedule_change`·`_on_skip_occurrence`·`_on_delete_schedule`, 알림 메서드(새), `_discard_data_widgets`, `_on_import_complete`, `prepare_for_quit`, `nativeEvent`, `_lock`, `_unlock`)
- Test: `tests/test_ui_schedule_alarm.py` (새)

**Interfaces:**
- Consumes: `db.get_alarm_occurrences`·`db.has_schedule_alarms`·`db.SETTING_SCHEDULE_ALARM_SEEN_AT`, `rules.AlarmItem`·`rules.alarm_subtitle`, `ElidedLabel`·`icon_pixmap`, `popup_border_fix.remove_dwm_border`
- Produces
  - `ScheduleAlarmScheduler(parent=None, *, now=None)`
    - 신호 `alarms_ready(list, bool)`(AlarmItem 목록, 모두 놓친 알림인지)
    - `start()`(실행 중이면 `refresh`), `stop(*, persist=False)`, `refresh()`, `resume()`, `check()`, `snooze(items)`, `is_running()`, `last_check()`
    - 확인한 가장 늦은 시각은 되돌리지 않는다(시계가 12시간 넘게 뒤로 가면 지금부터 다시 센다), 확인 창은 최대 12시간
  - `ScheduleAlarmCard()`: 신호 `snooze_requested(list)`·`open_date_requested(str)`, `add_items(items, *, missed, locked, now=None)`, `set_locked(locked)`, `is_locked_view()`, `show_at(screen)`, 속성 `frame`·`title_label`·`more_label`·`snooze_button`·`ok_button`
  - `MainCalendarWindow._schedule_alarm_scheduler`, `_alarm_card`, `_on_schedule_alarms(items, missed)`, `_open_alarm_date(date)`, `_close_alarm_card()`, `_forget_alarm_card(card)`, `_alarm_screen()`

- [ ] **Step 1: 실패하는 시험을 쓴다** — `tests/test_ui_schedule_alarm.py` (새로 만든다)

Review Focus 3(시계가 뒤로 가거나 크게 뛰는 경우)은 `test_clock_jumps_do_not_flood_or_repeat`가 고정한다.

```python
"""v4.1 일정 알림 엔진·카드 회귀. 가짜 시계와 합성 데이터만 쓴다."""
from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

import database as db
import ui_main
from schedule_rules import AlarmItem, ScheduleOptions
from show_desktop_guard import ShowDesktopKeeper
from ui_main import MainCalendarWindow
from ui_schedule_alarm import ScheduleAlarmCard, ScheduleAlarmScheduler

KEY = db.SETTING_SCHEDULE_ALARM_SEEN_AT


class Clock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value


@pytest.fixture(autouse=True)
def isolated_ui(app_dir, monkeypatch):
    monkeypatch.setattr(ShowDesktopKeeper, "_install_foreground_hook", lambda self: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_apply_topmost", lambda *a, **kw: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_pin_to_desktop_layer", lambda self: False)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    beeps = []
    monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: beeps.append(1)))
    return beeps


def scheduler_with(qtbot, clock):
    host = QObject()  # 창 없이 엔진만 시험한다
    scheduler = ScheduleAlarmScheduler(host, now=clock)
    emitted = []
    scheduler.alarms_ready.connect(lambda items, missed: emitted.append((items, missed)))
    return scheduler, emitted, host


def test_due_alarm_shows_once_and_saves_seen_at(qtbot):
    db.add_schedule("2026-10-15", "부서 회의", options=ScheduleOptions(start_time="15:00", alarm_before=10))
    clock = Clock(datetime(2026, 10, 15, 14, 49, 59))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    assert emitted == []
    assert db.get_setting(KEY, "") == ""  # 시작만으로는 쓰지 않는다.
    assert 0 < scheduler._timer.remainingTime() <= 1100
    clock.value = datetime(2026, 10, 15, 14, 50, 0, 500000)
    scheduler.check()
    assert [(item.content, missed) for item, missed in
            [(items[0], missed) for items, missed in emitted]] == [("부서 회의", False)]
    assert db.get_setting(KEY, "") == "2026-10-15T14:50:00"
    clock.value += timedelta(seconds=30)
    scheduler.check()
    assert len(emitted) == 1


def test_start_without_key_skips_past_alarms(qtbot):
    db.add_schedule("2026-10-15", "아침 회의", options=ScheduleOptions(start_time="09:00", alarm_before=0))
    scheduler, emitted, _host = scheduler_with(qtbot, Clock(datetime(2026, 10, 15, 14, 0)))
    scheduler.start()
    assert emitted == []
    assert db.get_setting(KEY, "") == ""


def test_missed_alarms_only_from_last_12_hours(qtbot):
    db.add_schedule("2026-10-14", "어젯밤", options=ScheduleOptions(start_time="21:00", alarm_before=0))
    db.add_schedule("2026-10-15", "새벽", options=ScheduleOptions(start_time="06:00", alarm_before=0))
    db.save_setting(KEY, "2026-10-14T20:00:00")
    scheduler, emitted, _host = scheduler_with(qtbot, Clock(datetime(2026, 10, 15, 10, 0)))
    scheduler.start()
    assert [[item.content for item in items] for items, _missed in emitted] == [["새벽"]]
    assert emitted[0][1] is True


def test_clock_jumps_do_not_flood_or_repeat(qtbot):
    """Review Focus 3: 시계가 뒤로 가거나 크게 앞으로 뛰어도 중복·아주 오래된 알림이 없다."""
    for hour in range(8, 18):
        db.add_schedule("2026-10-15", f"{hour}시", options=ScheduleOptions(start_time=f"{hour:02d}:00", alarm_before=0))
    clock = Clock(datetime(2026, 10, 15, 8, 30))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    clock.value = datetime(2026, 10, 15, 9, 0, 1)
    scheduler.check()
    clock.value = datetime(2026, 10, 15, 7, 0)  # 뒤로
    scheduler.check()
    clock.value = datetime(2026, 10, 15, 9, 30)  # 다시 앞으로: 9시는 이미 띄웠다
    scheduler.check()
    clock.value = datetime(2026, 10, 18, 9, 0)  # 3일 뒤로 점프: 12시간 밖이라 알리지 않는다
    scheduler.check()
    assert [[item.content for item in items] for items, _missed in emitted] == [["9시"]]


def test_snooze_returns_after_five_minutes_unless_deleted(qtbot):
    keep = db.add_schedule("2026-10-15", "유지", options=ScheduleOptions(start_time="15:00", alarm_before=0))
    gone = db.add_schedule("2026-10-15", "삭제", options=ScheduleOptions(start_time="15:00", alarm_before=0))
    clock = Clock(datetime(2026, 10, 15, 14, 59))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    clock.value = datetime(2026, 10, 15, 15, 0, 1)
    scheduler.check()
    scheduler.snooze(emitted[0][0])
    db.delete_schedule(gone)
    clock.value = datetime(2026, 10, 15, 15, 4)
    scheduler.check()
    assert len(emitted) == 1
    clock.value = datetime(2026, 10, 15, 15, 5, 2)
    scheduler.check()
    assert [item.schedule_id for item in emitted[1][0]] == [keep]


def test_stop_persists_last_check_only_when_alarms_exist(qtbot):
    clock = Clock(datetime(2026, 10, 15, 9, 0))
    scheduler, _emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    scheduler.stop(persist=True)
    assert db.get_setting(KEY, "") == ""
    db.add_schedule("2026-10-20", "알림", options=ScheduleOptions(alarm_before=0))
    scheduler.start()
    clock.value = datetime(2026, 10, 15, 9, 0, 40)
    scheduler.check()
    clock.value = datetime(2026, 10, 15, 9, 1, 10)
    scheduler.stop(persist=True)
    assert db.get_setting(KEY, "") == "2026-10-15T09:00:40"
    assert not scheduler.is_running()


def item(sid, content, *, start_time="15:00", day="2026-10-15", color="#4CC9F0", failed=False):
    return AlarmItem(sid, day, datetime(2026, 10, 15, 14, 50) + timedelta(seconds=sid),
                     content, color, start_time, failed)


def visible_titles(card):
    return [label.text() for label in card.findChildren(ui_main.QLabel, "scheduleAlarmItemTitle")
            if label.isVisibleTo(card)]


def card_window(qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win._current_year, win._current_month = 2026, 10
    win._refresh_calendar()
    QApplication.processEvents()
    return win


def test_card_rows_plain_text_lock_and_beep(qtbot, isolated_ui):
    win = card_window(qtbot)
    items = [item(1, "<b>부서 회의</b>"), item(2, "보고서"), item(3, "", failed=True),
             item(4, "종일", start_time="")]
    win._on_schedule_alarms(items, False)
    card = win._alarm_card
    assert card.isVisible() and isinstance(card, ScheduleAlarmCard)
    assert card.title_label.text() == "일정 알림 4건"
    assert visible_titles(card) == ["15:00 <b>부서 회의</b>", "15:00 보고서", "15:00 내용을 읽을 수 없는 일정"]
    assert card.more_label.text() == "외 1건"
    assert card.snooze_button.isVisible()
    assert isolated_ui == [1]
    win._lock()
    QApplication.processEvents()
    assert card.is_locked_view()
    assert visible_titles(card) == []
    assert card.findChild(ui_main.QLabel, "scheduleAlarmLocked").text() == "PIN 잠금 중이라 내용을 숨겼습니다."
    assert not card.snooze_button.isVisible()
    win._unlock()
    QApplication.processEvents()
    assert len(visible_titles(card)) == 3


def test_missed_card_has_only_ok_and_sits_bottom_right(qtbot):
    win = card_window(qtbot)
    win._on_schedule_alarms([item(1, "놓친 회의")], True)
    card = win._alarm_card
    assert not card.snooze_button.isVisible() and card.ok_button.isVisible()
    available = card.screen().availableGeometry()
    frame = card.frame.geometry().translated(card.pos())
    assert abs(frame.right() + 1 - (available.right() + 1 - 12)) <= 1
    assert abs(frame.bottom() + 1 - (available.bottom() + 1 - 12)) <= 1


def test_card_click_opens_date_and_closes(qtbot):
    db.add_schedule("2026-10-20", "회의", options=ScheduleOptions(start_time="15:00", alarm_before=0))
    win = card_window(qtbot)
    win._minimize_to_tray()
    win._on_schedule_alarms([item(1, "회의", day="2026-10-20")], False)
    card = win._alarm_card
    qtbot.mouseClick(card, Qt.LeftButton, pos=card.frame.geometry().center())
    qtbot.waitUntil(lambda: win._alarm_card is None or not isValid(card))
    assert win.isVisible()
    assert win._selected_date == "2026-10-20"


def test_reset_quit_close_card_and_restart_engine(qtbot):
    db.add_schedule("2026-10-20", "알림", options=ScheduleOptions(alarm_before=0))
    win = card_window(qtbot)
    qtbot.waitUntil(lambda: win._schedule_alarm_scheduler.is_running())
    win._on_schedule_alarms([item(1, "회의")], False)
    card = win._alarm_card
    win._discard_data_widgets()
    assert not win._schedule_alarm_scheduler.is_running()
    qtbot.waitUntil(lambda: not isValid(card) or not card.isVisible())
    win._on_import_complete()
    assert win._schedule_alarm_scheduler.is_running()
    win._on_schedule_alarms([item(2, "다시")], False)
    card = win._alarm_card
    assert win.prepare_for_quit()
    assert not win._schedule_alarm_scheduler.is_running()
    qtbot.waitUntil(lambda: not isValid(card) or not card.isVisible())
    assert db.get_setting(KEY, "") != ""


def test_window_without_alarms_leaves_settings_unchanged(qtbot):
    db.add_schedule("2026-10-15", "알림 없는 일정")
    with db._connection() as conn:
        before = [tuple(row) for row in conn.execute("SELECT * FROM app_settings ORDER BY key")]
    win = card_window(qtbot)
    qtbot.waitUntil(lambda: win._schedule_alarm_scheduler.is_running())
    assert win.prepare_for_quit()
    with db._connection() as conn:
        assert [tuple(row) for row in conn.execute("SELECT * FROM app_settings ORDER BY key")] == before
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_schedule_alarm.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ui_schedule_alarm'`

- [ ] **Step 3: 알림 모듈을 만든다**

(1) `ui_schedule_alarm.py`를 새로 만든다(파일 전체).

```python
"""일정 알림 엔진과 알림 카드 (v4.1).

앱이 켜져 있을 때만 알린다(Windows 알림 센터는 쓰지 않는다). 알림 처리 시각
`schedule_alarm_seen_at`은 카드를 띄울 때와, 알림 켜진 일정이 있을 때의 정상 종료 때만 쓴다.
"""
import logging
import sqlite3
from datetime import date, datetime, timedelta

from PySide6.QtCore import QObject, QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

import database as db
import schedule_rules as rules
from popup_border_fix import remove_dwm_border
from ui_schedule_options import ElidedLabel, icon_pixmap

_logger = logging.getLogger("app_error")

LOOKBACK = timedelta(hours=12)       # 이보다 오래된 알림은 알리지 않는다
MISSED_AFTER = timedelta(minutes=2)  # 이보다 늦게 확인한 알림은 '놓친 알림'
SNOOZE = timedelta(minutes=5)
MAX_INTERVAL_MS = 60_000
CARD_WIDTH = 320
CARD_MARGIN = 16
SCREEN_GAP = 12
MAX_ROWS = 3
UNREADABLE = "내용을 읽을 수 없는 일정"


def _parse_seen(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


class ScheduleAlarmScheduler(QObject):
    """단발 타이머로 다음 알림(최대 60초 뒤)마다 확인한다. 시계 함수는 바꿔 넣을 수 있다(시험용)."""

    alarms_ready = Signal(list, bool)  # (AlarmItem 목록, 모두 놓친 알림인지)

    def __init__(self, parent=None, *, now=None):
        super().__init__(parent)
        self._now = now or datetime.now
        self._running = False
        self._last_check = None
        self._fired = set()
        self._snoozed = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.check)

    def is_running(self) -> bool:
        return self._running

    def last_check(self):
        return self._last_check

    def start(self) -> None:
        """시작: 저장된 처리 시각(최대 12시간 전)부터 지금까지를 확인한다. 키가 없으면 지금부터."""
        if self._running:
            self.refresh()
            return
        now = self._now()
        try:
            seen = _parse_seen(db.get_setting(db.SETTING_SCHEDULE_ALARM_SEEN_AT, ""))
        except (sqlite3.Error, OSError) as exc:
            _logger.error("일정 알림 처리 시각 읽기 실패: %s", exc)
            seen = None
        self._last_check = max(seen, now - LOOKBACK) if seen is not None else now
        self._running = True
        self.check()

    def stop(self, *, persist: bool = False) -> None:
        """멈춘다. persist면 알림 켜진 일정이 있을 때만 마지막 확인 시각을 남긴다."""
        self._timer.stop()
        if persist and self._running and self._last_check is not None:
            try:
                if db.has_schedule_alarms():
                    db.save_setting(db.SETTING_SCHEDULE_ALARM_SEEN_AT,
                                    self._last_check.isoformat(timespec="seconds"))
            except (sqlite3.Error, OSError) as exc:
                _logger.error("일정 알림 처리 시각 저장 실패: %s", exc)
        self._running = False
        self._snoozed.clear()

    def refresh(self) -> None:
        """일정이 바뀐 뒤: 지난 알림은 다시 울리지 않고 다음 확인 시각만 다시 맞춘다."""
        if self._running:
            self._schedule_next(self._now())

    def resume(self) -> None:
        """절전 복귀: 바로 확인한다(2분 넘은 것은 놓친 알림)."""
        if self._running:
            self.check()

    def check(self) -> None:
        if not self._running:
            return
        now = self._now()
        mark = self._last_check or now
        if mark - now > LOOKBACK:
            mark = now  # 시계를 크게 되돌렸으면 지금부터 다시 센다(이미 띄운 것은 _fired가 막는다).
        # 확인한 가장 늦은 시각(mark)은 되돌리지 않는다: 시계가 조금 뒤로 가도 지난 알림이 다시 울리지 않는다.
        after = max(mark, now - LOOKBACK)
        found = self._load(after, now) if now > after else []
        due = [item for item in found if item.key not in self._fired]
        for key, (item, until) in list(self._snoozed.items()):
            if until <= now:
                del self._snoozed[key]
                if self._still_scheduled(item):
                    due.append(item)
        self._last_check = max(mark, now)
        if due:
            due.sort(key=lambda item: (item.due, item.schedule_id))
            self._fired.update(item.key for item in due)
            try:
                db.save_setting(db.SETTING_SCHEDULE_ALARM_SEEN_AT, now.isoformat(timespec="seconds"))
            except (sqlite3.Error, OSError) as exc:
                _logger.error("일정 알림 처리 시각 저장 실패: %s", exc)
            missed = all(now - item.due > MISSED_AFTER for item in due)
            self.alarms_ready.emit(due, missed)
        self._schedule_next(now)

    def snooze(self, items) -> None:
        """'5분 뒤 다시': 메모리에만 두며 종료하면 사라진다."""
        if not self._running:
            return
        until = self._now() + SNOOZE
        for item in items:
            self._snoozed[item.key] = (item, until)
        self._schedule_next(self._now())

    def _load(self, after, until) -> list:
        try:
            return db.get_alarm_occurrences(after, until)
        except (sqlite3.Error, OSError) as exc:
            _logger.error("일정 알림 확인 실패: %s", exc)
            return []

    def _still_scheduled(self, item) -> bool:
        """다시 알릴 때 그 일정·날짜·알림 시각이 아직 그대로인지 본다(삭제·변경 반영)."""
        found = self._load(item.due - timedelta(seconds=1), item.due)
        return any(other.key == item.key for other in found)

    def _schedule_next(self, now) -> None:
        if not self._running:
            return
        horizon = now + timedelta(milliseconds=MAX_INTERVAL_MS)
        candidates = [item.due for item in self._load(now, horizon) if item.key not in self._fired]
        candidates += [until for _item, until in self._snoozed.values()]
        interval = MAX_INTERVAL_MS
        if candidates:
            wait = (min(candidates) - now).total_seconds() * 1000 + 50
            interval = max(50, min(MAX_INTERVAL_MS, int(wait)))
        self._timer.start(interval)


class ScheduleAlarmCard(QWidget):
    """화면 오른쪽 아래 알림 카드. 포커스를 빼앗지 않고 작업 표시줄에 나타나지 않는다."""

    snooze_requested = Signal(list)
    open_date_requested = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setObjectName("scheduleAlarmCard")
        self.setAccessibleName("일정 알림")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._items = []
        self._missed = True
        self._locked = False
        self._now = datetime.now()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(CARD_MARGIN, CARD_MARGIN, CARD_MARGIN, CARD_MARGIN)
        self.frame = QFrame(self)
        self.frame.setObjectName("scheduleAlarmFrame")
        self.frame.setFixedWidth(CARD_WIDTH)
        shadow = QGraphicsDropShadowEffect(self.frame)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(24, 46, 76, 80))
        self.frame.setGraphicsEffect(shadow)
        outer.addWidget(self.frame)
        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.icon_label = QLabel(self.frame)
        self.icon_label.setFixedSize(16, 16)
        head.addWidget(self.icon_label)
        self.title_label = QLabel(self.frame)
        self.title_label.setObjectName("scheduleAlarmTitle")
        self.title_label.setTextFormat(Qt.PlainText)
        head.addWidget(self.title_label)
        head.addStretch(1)
        self.close_button = QPushButton("×", self.frame)
        self.close_button.setObjectName("scheduleAlarmClose")
        self.close_button.setFixedSize(24, 24)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setAccessibleName("알림 닫기")
        self.close_button.clicked.connect(self.close)
        head.addWidget(self.close_button)
        layout.addLayout(head)
        self.rows_box = QWidget(self.frame)
        self.rows_layout = QVBoxLayout(self.rows_box)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)
        layout.addWidget(self.rows_box)
        self.more_label = QLabel(self.frame)
        self.more_label.setObjectName("scheduleAlarmMore")
        self.more_label.setTextFormat(Qt.PlainText)
        layout.addWidget(self.more_label)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.snooze_button = QPushButton("5분 뒤 다시", self.frame)
        self.snooze_button.setObjectName("scheduleAlarmSnooze")
        self.snooze_button.setCursor(Qt.PointingHandCursor)
        self.snooze_button.clicked.connect(self._snooze)
        self.ok_button = QPushButton("확인", self.frame)
        self.ok_button.setObjectName("scheduleAlarmOk")
        self.ok_button.setCursor(Qt.PointingHandCursor)
        self.ok_button.clicked.connect(self.close)
        for button in (self.snooze_button, self.ok_button):
            button.setFixedHeight(28)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self._render()

    def items(self) -> list:
        return list(self._items)

    def add_items(self, items, *, missed: bool, locked: bool, now: datetime | None = None) -> None:
        known = {item.key for item in self._items}
        fresh = [item for item in items if item.key not in known]
        self._missed = (self._missed if self._items else True) and missed
        self._items = sorted(self._items + fresh, key=lambda item: (item.due, item.schedule_id))
        self._locked = locked
        self._now = now or datetime.now()
        self._render()

    def set_locked(self, locked: bool) -> None:
        if self._locked != locked:
            self._locked = locked
            self._render()

    def is_locked_view(self) -> bool:
        return self._locked

    def _render(self) -> None:
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        count = len(self._items)
        stripe = self._items[0].color if self._items and not self._locked else "#2563EB"
        self.frame.setStyleSheet(
            "QFrame#scheduleAlarmFrame{background:#FFFFFF;border:1px solid #D7DAE2;"
            f"border-left:4px solid {stripe};border-radius:12px;}}"
            "QFrame#scheduleAlarmFrame QLabel{background:transparent;}"
            "QLabel#scheduleAlarmTitle{color:#172B4D;font-size:13px;font-weight:bold;}"
            "QLabel#scheduleAlarmItemTitle{color:#172B4D;font-size:15px;font-weight:bold;}"
            "QLabel#scheduleAlarmItemSub,QLabel#scheduleAlarmMore,QLabel#scheduleAlarmLocked"
            "{color:#5B6577;font-size:12px;}"
            "QPushButton#scheduleAlarmClose{background:transparent;border:0px;border-radius:6px;"
            "color:#7A8699;font-size:17px;}"
            "QPushButton#scheduleAlarmClose:hover{background:#F1F4F8;color:#253447;}"
            "QPushButton#scheduleAlarmSnooze{background:#FFFFFF;border:1px solid #CBD5E1;"
            "border-radius:6px;color:#334155;font-size:12px;padding:0px 12px;}"
            "QPushButton#scheduleAlarmSnooze:hover{background:#F8FAFC;}"
            "QPushButton#scheduleAlarmOk{background:#2563EB;border:1px solid #2563EB;"
            "border-radius:6px;color:#FFFFFF;font-size:12px;font-weight:bold;padding:0px 16px;}"
            "QPushButton#scheduleAlarmOk:hover{background:#1D4ED8;}"
        )
        ratio = self.devicePixelRatioF()
        self.title_label.setText("일정 알림" if count <= 1 else f"일정 알림 {count}건")
        if self._locked:
            self.icon_label.setPixmap(icon_pixmap("lock", 16, "#475569", ratio))
            locked = QLabel("PIN 잠금 중이라 내용을 숨겼습니다.", self.rows_box)
            locked.setObjectName("scheduleAlarmLocked")
            locked.setTextFormat(Qt.PlainText)
            self.rows_layout.addWidget(locked)
            self.more_label.hide()
        else:
            self.icon_label.setPixmap(icon_pixmap("bell", 16, "#2563EB", ratio))
            for item in self._items[:MAX_ROWS]:
                self.rows_layout.addWidget(self._row(item))
            extra = count - MAX_ROWS
            self.more_label.setText(f"외 {extra}건" if extra > 0 else "")
            self.more_label.setVisible(extra > 0)
        self.snooze_button.setVisible(not self._missed and not self._locked)
        self.frame.layout().activate()
        self.adjustSize()

    def _row(self, item) -> QWidget:
        row = QWidget(self.rows_box)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        content = UNREADABLE if item.decryption_failed else item.content
        title = ElidedLabel(f"{item.start_time} {content}" if item.start_time else content, row)
        title.setObjectName("scheduleAlarmItemTitle")
        sub = ElidedLabel(rules.alarm_subtitle(
            item.start_time, date.fromisoformat(item.occurrence_date), self._now), row)
        sub.setObjectName("scheduleAlarmItemSub")
        layout.addWidget(title)
        layout.addWidget(sub)
        return row

    def show_at(self, screen) -> None:
        """screen 작업 영역의 오른쪽 아래, 12px 안쪽에 보인다."""
        self.adjustSize()
        available = screen.availableGeometry()
        x = available.right() + 1 - SCREEN_GAP - (self.width() - CARD_MARGIN)
        y = available.bottom() + 1 - SCREEN_GAP - (self.height() - CARD_MARGIN)
        self.move(QPoint(x, y))
        self.show()
        self.raise_()
        remove_dwm_border(self)

    def _snooze(self) -> None:
        self.snooze_requested.emit(list(self._items))
        self.close()

    def mouseReleaseEvent(self, event):
        inside = self.frame.geometry().contains(event.position().toPoint())
        if event.button() == Qt.LeftButton and inside and self._items:
            if not self._locked:
                self.open_date_requested.emit(self._items[0].occurrence_date)
            self.close()
            event.accept()
            return
        super().mouseReleaseEvent(event)
```

- [ ] **Step 4: 메인 창의 수명주기에 연결한다**

(1) `ui_main.py` — import에 알림 엔진·카드를 더한다. 이 원문 바로 뒤에:

```python
from ui_calendar_spans import CalendarSpanOverlay, SpanBar
```

넣을 코드:

```python
from ui_schedule_alarm import ScheduleAlarmCard, ScheduleAlarmScheduler
```

(2) `ui_main.py` — 생성자: 알림 엔진은 창보다 먼저 만든다(달력·목록 갱신이 다시 계산을 요청한다). 이 원문 바로 앞에:

```python
        self._build_ui()
```

넣을 코드:

```python
        self._alarm_card = None
        self._schedule_alarm_scheduler = ScheduleAlarmScheduler(self)
        self._schedule_alarm_scheduler.alarms_ready.connect(self._on_schedule_alarms)
```

(3) `ui_main.py` — 생성자: 창이 뜬 뒤 알림을 시작한다(놓친 알림은 지난 12시간 것만). 이 원문 바로 뒤에:

```python
        if self._widget_trim_result.get("focus") or self._widget_trim_result.get("dday"):
            QTimer.singleShot(1500, self._warn_widget_trim)
```

넣을 코드:

```python

        # 일정 알림은 창이 뜬 뒤 시작한다(놓친 알림은 지난 12시간 것만).
        QTimer.singleShot(0, self, self._schedule_alarm_scheduler.start)
```

(4) `ui_main.py` — `_after_schedule_change`: 일정이 바뀌면 다음 알림을 다시 맞춘다. 찾을 원문:

```python
        elif self._load_schedules() and highlight_id is not None:
            self._highlight_schedule(highlight_id)
```

바꿀 코드:

```python
        elif self._load_schedules() and highlight_id is not None:
            self._highlight_schedule(highlight_id)
        self._schedule_alarm_scheduler.refresh()
```

(5) `ui_main.py` — `_on_skip_occurrence`: 이 날만 삭제 뒤 알림을 다시 맞춘다. 찾을 원문:

```python
        self._remove_schedule_item(item)
        self._refresh_month_data()
        self._update_count()
```

바꿀 코드:

```python
        self._remove_schedule_item(item)
        self._refresh_month_data()
        self._update_count()
        self._schedule_alarm_scheduler.refresh()
```

(6) `ui_main.py` — `_on_delete_schedule`: 삭제 뒤 알림을 다시 맞춘다. 찾을 원문:

```python
            self._remove_schedule_item(item)
            self._refresh_cell_for_date(self._selected_date)
            self._update_count()
```

바꿀 코드:

```python
            self._remove_schedule_item(item)
            self._refresh_cell_for_date(self._selected_date)
            self._update_count()
            self._schedule_alarm_scheduler.refresh()
```

(7) `ui_main.py` — 알림 처리 메서드를 `_highlight_schedule` 뒤에 더한다. 이 원문 바로 뒤에:

```python
                QTimer.singleShot(1200, row, lambda r=row: r.setStyleSheet(""))
            return
```

넣을 코드:

```python

    # ─── 일정 알림 ─────────────────────────────────────────────
    def _alarm_screen(self):
        if self.isVisible() and self.screen() is not None:
            return self.screen()
        return self._get_target_screen() or QApplication.primaryScreen()

    def _on_schedule_alarms(self, items: list, missed: bool) -> None:
        card = self._alarm_card
        if card is None or not isValid(card):
            card = ScheduleAlarmCard()
            card.snooze_requested.connect(self._schedule_alarm_scheduler.snooze)
            card.open_date_requested.connect(self._open_alarm_date)
            card.destroyed.connect(lambda *_args, c=card: self._forget_alarm_card(c))
            self.destroyed.connect(card.close)
            self._alarm_card = card
        card.add_items(items, missed=missed, locked=self._is_locked,
                       now=self._schedule_alarm_scheduler.last_check())
        card.show_at(self._alarm_screen())
        QApplication.beep()  # Windows 기본 알림음(사운드 설정을 따른다)

    def _open_alarm_date(self, date_str: str) -> None:
        if self._is_locked:
            return
        if not self.isVisible():
            self.toggle_visibility()
        self.raise_()
        self.activateWindow()
        self._navigate_to_date(date_str)

    def _forget_alarm_card(self, card) -> None:
        if self._alarm_card is card:  # 늦게 지워진 예전 카드가 새 카드 참조를 지우지 않게 한다.
            self._alarm_card = None

    def _close_alarm_card(self) -> None:
        if self._alarm_card is not None and isValid(self._alarm_card):
            self._alarm_card.close()
        self._alarm_card = None
```

(8) `ui_main.py` — `_discard_data_widgets`: 초기화 전 폐기 때 알림을 멈추고 카드를 닫는다. 찾을 원문:

```python
        self._close_schedule_emoji_popups()
        self._set_pending_options(ScheduleOptions())
```

바꿀 코드:

```python
        self._close_schedule_emoji_popups()
        self._schedule_alarm_scheduler.stop()
        self._close_alarm_card()
        self._set_pending_options(ScheduleOptions())
```

(9) `ui_main.py` — `_on_import_complete`: 가져오기는 다시 계산만, 초기화 뒤에는 새 DB 기준으로 다시 시작한다. 찾을 원문:

```python
        if self._sticky_in_panel_mode and self._sticky_side_panel is not None:
            if not self._sticky_side_panel.reload():
                self._show_sticky_handoff_error()

    def _on_law_search_changed(self):
```

바꿀 코드:

```python
        if self._sticky_in_panel_mode and self._sticky_side_panel is not None:
            if not self._sticky_side_panel.reload():
                self._show_sticky_handoff_error()
        # 가져오기는 다시 계산만 하고(이미 지난 알림은 울리지 않는다), 멈춰 있으면(초기화 뒤) 다시 시작한다.
        self._schedule_alarm_scheduler.start()

    def _on_law_search_changed(self):
```

(10) `ui_main.py` — `prepare_for_quit`: 정상 종료 때 카드를 닫고 알림 처리 시각을 남긴다(알림 켜진 일정이 있을 때만). 찾을 원문:

```python
            self._discard_document_converter()
            self._discard_optional_mini_apps()
            return True
```

바꿀 코드:

```python
            self._discard_document_converter()
            self._discard_optional_mini_apps()
            self._close_schedule_emoji_popups()
            self._schedule_alarm_scheduler.stop(persist=True)
            self._close_alarm_card()
            return True
```

(11) `ui_main.py` — `nativeEvent`: 절전 복귀 때 놓친 알림을 바로 확인한다. 찾을 원문:

```python
                should_lock = (
                    (msg.message == WM_POWERBROADCAST and msg.wParam == PBT_APMRESUMESUSPEND) or
```

바꿀 코드:

```python
                if msg.message == WM_POWERBROADCAST and msg.wParam == PBT_APMRESUMESUSPEND:
                    self._schedule_alarm_scheduler.resume()
                should_lock = (
                    (msg.message == WM_POWERBROADCAST and msg.wParam == PBT_APMRESUMESUSPEND) or
```

(12) `ui_main.py` — `_lock`: 알림 카드 내용을 가린다. 찾을 원문:

```python
        self._is_locked = True
        self._finish_calendar_move_edit()
        self._cancel_sticky_file_links()
        self._close_schedule_emoji_popups()
```

바꿀 코드:

```python
        self._is_locked = True
        self._finish_calendar_move_edit()
        self._cancel_sticky_file_links()
        self._close_schedule_emoji_popups()
        if self._alarm_card is not None and isValid(self._alarm_card):
            self._alarm_card.set_locked(True)
```

(13) `ui_main.py` — `_unlock`: 알림 카드를 평소 모양으로 되돌린다. 찾을 원문:

```python
    def _unlock(self):
        self._is_locked = False
        self._update_calendar_move_control()
```

바꿀 코드:

```python
    def _unlock(self):
        self._is_locked = False
        self._update_calendar_move_control()
        if self._alarm_card is not None and isValid(self._alarm_card):
            self._alarm_card.set_locked(False)
```

- [ ] **Step 5: 새 시험과 데이터·종료 관련 기존 시험을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_schedule_alarm.py tests/test_ui_calendar_columns.py tests/test_ui_data_lifecycle.py tests/test_ui.py tests/test_ui_schedule_list.py tests/test_ui_schedule_input.py -q`
Expected: PASS (`test_calendar_display_roundtrip_preserves_existing_rows_and_salt`: 알림 없는 DB는 시작·종료로 설정 표가 바뀌지 않는다)

- [ ] **Step 6: 커밋**

```bash
git add ui_schedule_alarm.py ui_main.py tests/test_ui_schedule_alarm.py
git commit -m "feat: 앱 안 일정 알림 엔진과 알림 카드(놓친 알림 12시간, 다시 알림, PIN 잠금 가림)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```


### Task 15: 업데이트 1회 안내창

**Files:**
- Modify: `main.py` (`_initialize_database`, `main()`)
- Modify: `ui_main.py` (import, `UPGRADE_NOTICE_TITLE`·`upgrade_notice_text()`(새), `MainCalendarWindow.show_upgrade_notice`(새))
- Modify: `tools/smoke_release.py` (`UPGRADE_NOTICE_TITLE`, `scenario()`의 창 확인)
- Test: `tests/test_upgrade_notice.py` (새)

**Interfaces:**
- Consumes: Task 4의 v18 마이그레이션(`health.version`), Task 7의 'upgrade' 시나리오
- Produces
  - `main._initialize_database(choose_initial_scale=None, on_upgrade=None) -> bool`: 예전 형식(0 < 버전 < 현재) DB를 올린 실행에서만 `on_upgrade(이전 버전)`을 한 번 부른다. 반환값·기존 호출은 그대로
  - `ui_main.UPGRADE_NOTICE_TITLE = "기후노트 업데이트 안내"`, `ui_main.upgrade_notice_text() -> str`
  - `MainCalendarWindow.show_upgrade_notice(previous_version)`: 부모 없는 맨 위 모달 `Dialog`(폭 440, 높이는 글에 맞춤, [확인]만), 아무것도 저장하지 않음
  - `smoke_release.UPGRADE_NOTICE_TITLE`: 실제 EXE 'upgrade' 시나리오는 이 창이 떠야 통과, 다른 시나리오에서 뜨면 실패
- 이유: 이미 배포된 v4.0a는 v18 데이터를 보면 '데이터 보호를 위해 실행을 중단했습니다 — 기존 데이터베이스의 구조 또는 무결성을 확인하지 못했습니다' 창으로 멈춘다. 그 문구는 바꿀 수 없으므로 업데이트하는 순간 v4.1이 미리 알린다(사용자 결정 2026-10-16)

- [ ] **Step 1: 실패하는 시험을 쓴다** — `tests/test_upgrade_notice.py` (새로 만든다)

```python
"""v4.1 업데이트 1회 안내: 예전 형식 DB를 올린 실행에서만 알리고, 아무것도 저장하지 않는다."""
import sqlite3
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Dialog

import database as db
import security
import ui_main
from app_info import APP_VERSION
from show_desktop_guard import ShowDesktopKeeper

FIXTURE = Path(__file__).parent / "fixtures" / "schema_v17.sql"
OLD_VERSION_WINDOW = "데이터 보호를 위해 실행을 중단했습니다"


def _make_v17(app_dir):
    db_file = app_dir / "calendar.db"
    for path in (db_file, app_dir / "calendar.db-wal", app_dir / "calendar.db-shm"):
        path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_file)
    try:
        conn.executescript(FIXTURE.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
                     ("2026-10-15", security.encrypt("기존 일정"), "2026-10-14 09:00:00", "#FFD166"))
        conn.execute("PRAGMA user_version = 17")
        conn.commit()
    finally:
        conn.close()


def _dump():
    with db._connection(read_only=True, enable_wal=False) as conn:
        return {table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                for table in ("app_settings", "schedules", "memos", "sticky_notes")}


def test_initialize_database_reports_upgrade_once(app_dir):
    import main as app_main

    _make_v17(app_dir)
    calls = []
    assert app_main._initialize_database(on_upgrade=calls.append) is True
    assert calls == [17]
    assert app_main._initialize_database(on_upgrade=calls.append) is True  # 이미 새 형식
    assert calls == [17]


def test_initialize_database_does_not_report_fresh_install(app_dir):
    import main as app_main

    for name in ("calendar.db", "calendar.db-wal", "calendar.db-shm"):
        (app_dir / name).unlink(missing_ok=True)
    calls = []
    assert app_main._initialize_database(on_upgrade=calls.append) is True
    assert calls == []


def test_upgrade_notice_text_explains_the_old_version_window():
    text = ui_main.upgrade_notice_text()
    assert f"기후노트 {APP_VERSION}로 업데이트했습니다" in text
    assert f"'{OLD_VERSION_WINDOW}'" in text
    assert "데이터는 바뀌지 않습니다" in text
    assert "이전 버전 EXE 파일과 바탕화면 바로가기는 지워 주세요" in text
    assert "backups" in text


def test_upgrade_notice_dialog_is_modal_fits_and_writes_nothing(qtbot, app_dir, monkeypatch):
    monkeypatch.setattr(ShowDesktopKeeper, "_install_foreground_hook", lambda self: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_apply_topmost", lambda *a, **kw: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_pin_to_desktop_layer", lambda self: False)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    win = ui_main.MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    QApplication.processEvents()
    before = _dump()
    seen = []

    def fake_exec(dialog):
        dialog.show()
        QApplication.processEvents()
        content = dialog.contentLabel
        button_top = dialog.yesButton.mapTo(dialog, QPoint(0, 0)).y()
        seen.append({
            "title": dialog.windowTitle(),
            "label": dialog.windowTitleLabel.text(),
            "text": "".join(content.text().split()),
            "modal": dialog.windowModality(),
            "cancel_hidden": dialog.cancelButton.isHidden(),
            "yes": dialog.yesButton.text(),
            "fits": dialog.rect().contains(content.geometry())
                    and content.height() >= content.heightForWidth(content.width())
                    and content.geometry().bottom() < button_top,
            "on_screen": dialog.screen().availableGeometry().contains(dialog.frameGeometry()),
        })
        dialog.hide()
        return 1

    monkeypatch.setattr(Dialog, "exec", fake_exec)
    win.show_upgrade_notice(17)
    assert seen == [{
        "title": ui_main.UPGRADE_NOTICE_TITLE,
        "label": ui_main.UPGRADE_NOTICE_TITLE,
        "text": "".join(ui_main.upgrade_notice_text().split()),
        "modal": Qt.ApplicationModal,
        "cancel_hidden": True,
        "yes": "확인",
        "fits": True,
        "on_screen": True,
    }]
    assert _dump() == before


def test_release_smoke_looks_for_the_same_notice_title():
    from tools import smoke_release as smoke
    assert smoke.UPGRADE_NOTICE_TITLE == ui_main.UPGRADE_NOTICE_TITLE
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_upgrade_notice.py -q`
Expected: FAIL — `TypeError: _initialize_database() got an unexpected keyword argument 'on_upgrade'`, `AttributeError: module 'ui_main' has no attribute 'upgrade_notice_text'` 등

- [ ] **Step 3: 시작 순서에 알림을 연결한다**

(1) `main.py` — `_initialize_database`: 예전 형식 DB를 올렸으면 알려 주는 선택 인자. 찾을 원문:

```python
def _initialize_database(choose_initial_scale: Callable[[], str | None] | None = None) -> bool:
    """마이그레이션 전 스냅샷 실패 시 스키마 변경을 시작하지 않는다."""
```

바꿀 코드:

```python
def _initialize_database(choose_initial_scale: Callable[[], str | None] | None = None,
                         on_upgrade: Callable[[int], None] | None = None) -> bool:
    """마이그레이션 전 스냅샷 실패 시 스키마 변경을 시작하지 않는다.

    on_upgrade: 예전 형식 DB를 이번 실행에서 올렸으면 원래 DB 버전으로 한 번 부른다(업데이트 안내창용).
    """
```

(2) `main.py` — `_initialize_database` 끝: 올린 경우에만 알린다(새 설치·이미 새 형식이면 부르지 않는다). 찾을 원문:

```python
    # v4.0까지의 백업 검증이 데이터 폴더에 남긴 임시 짝 파일 정리 (실패해도 시작 계속)
    db.cleanup_stale_backup_sidecars()
    return True
```

바꿀 코드:

```python
    # v4.0까지의 백업 검증이 데이터 폴더에 남긴 임시 짝 파일 정리 (실패해도 시작 계속)
    db.cleanup_stale_backup_sidecars()
    if on_upgrade is not None and 0 < health.version < db.CURRENT_SCHEMA_VERSION:
        on_upgrade(health.version)
    return True
```

(3) `main.py` — `main()`: 올린 버전을 받아 둔다. 찾을 원문:

```python
    # ── DB 초기화 및 백업
    try:
        if not _initialize_database(_choose_initial_calendar_scale):
            return
```

바꿀 코드:

```python
    # ── DB 초기화 및 백업
    upgraded_from = []  # 예전 형식 DB를 이번 실행에서 올렸으면 원래 DB 버전이 들어간다
    try:
        if not _initialize_database(_choose_initial_calendar_scale, on_upgrade=upgraded_from.append):
            return
```

(4) `main.py` — `main()`: 메인 창이 뜬 뒤 한 번 안내한다. 찾을 원문:

```python
    from ui_main import MainCalendarWindow
    main_window = MainCalendarWindow()
    main_window.show()
```

바꿀 코드:

```python
    from ui_main import MainCalendarWindow
    main_window = MainCalendarWindow()
    main_window.show()
    if upgraded_from:
        # 창이 뜬 뒤 한 번만 알린다. 아무것도 저장하지 않으며, 다음 실행에는 올릴 것이 없어 뜨지 않는다.
        QTimer.singleShot(800, lambda: main_window.show_upgrade_notice(upgraded_from[0]))
```

- [ ] **Step 4: 안내창을 만든다**

(1) `ui_main.py` — import: 앱 버전. 이 원문 바로 앞에:

```python
import database as db
from show_desktop_guard import ShowDesktopKeeper
```

넣을 코드:

```python
from app_info import APP_VERSION
```

(2) `ui_main.py` — 안내 제목·본문을 `ScheduleTextLabel` 앞에 둔다. 이 원문 바로 앞에:

```python
class ScheduleTextLabel(ElidePaintMixin, BodyLabel):
```

넣을 코드:

```python
UPGRADE_NOTICE_TITLE = "기후노트 업데이트 안내"


def upgrade_notice_text() -> str:
    """예전 형식 데이터를 새 형식으로 올린 실행에서 한 번 보이는 안내 본문."""
    return (
        f"기후노트 {APP_VERSION}로 업데이트했습니다. 기존 일정·메모·설정은 그대로 옮겼습니다.\n\n"
        "데이터 형식이 바뀌어 이전 버전 기후노트로는 열 수 없습니다. 이전 버전을 실행하면 "
        "'데이터 보호를 위해 실행을 중단했습니다' 창이 뜨지만 데이터는 바뀌지 않습니다.\n\n"
        "이전 버전 EXE 파일과 바탕화면 바로가기는 지워 주세요. "
        "업데이트 직전 데이터 사본은 데이터 폴더의 backups에 있습니다."
    )


```

(3) `ui_main.py` — 안내창 메서드를 `_warn_widget_trim` 앞에 더한다. 이 원문 바로 앞에:

```python
    def _warn_widget_trim(self):
```

넣을 코드:

```python
    def show_upgrade_notice(self, previous_version: int) -> None:
        """예전 형식(DB previous_version) 데이터를 이번 실행에서 올렸을 때 한 번 알린다.

        아무것도 저장하지 않는다. 바탕화면 레이어에 있는 메인 창 뒤로 숨지 않도록 부모 없는
        맨 위 창으로 띄운다(스티키 닫기 확인과 같은 방식).
        """
        from qfluentwidgets import Dialog
        dlg = Dialog(UPGRADE_NOTICE_TITLE, upgrade_notice_text(), None)
        dlg.setWindowTitle(UPGRADE_NOTICE_TITLE)  # 제목 줄은 숨겨져 있어도 창 이름은 남긴다
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        # 기본 Dialog는 100자마다 줄을 끊어 넣으므로 원문으로 되돌리고 폭에 맞춰 줄바꿈한다.
        dlg.contentLabel.setText(upgrade_notice_text())
        dlg.contentLabel.setWordWrap(True)
        dlg.setFixedWidth(440)
        dlg.adjustSize()
        dlg.cancelButton.hide()
        dlg.yesButton.setText("확인")
        screen = ((self.screen() if self.isVisible() else None)
                  or self._get_target_screen() or QApplication.primaryScreen())
        available = screen.availableGeometry()
        dlg.move(available.center() - dlg.rect().center())
        dlg.exec()
        dlg.deleteLater()

```

- [ ] **Step 5: 실제 EXE 'upgrade' 시나리오가 안내창을 확인하게 한다**

(1) `tools/smoke_release.py` — 안내창 제목 상수. 이 원문 바로 앞에:

```python
class _BasicLimits(ctypes.Structure):
```

넣을 코드:

```python
# 앱의 ui_main.UPGRADE_NOTICE_TITLE과 같아야 한다(tests/test_upgrade_notice.py가 대조한다).
UPGRADE_NOTICE_TITLE = "기후노트 업데이트 안내"


```

(2) `tools/smoke_release.py` — `scenario()`: upgrade는 안내창이 떠야 준비 완료, 다른 시나리오에는 안내창이 뜨면 안 된다. 찾을 원문:

```python
            errors = [w for w in observed if w["title"] == expected_error and w["responding"]]
            app_windows = [w for w in observed if w["width"] >= 350 and w["height"] >= 450
                           and w["responding"] and w["title"] not in
                           (expected_error, "기후노트 — 처음 설정")]
            if name == "blocked":
                ready = bool(errors) and not app_windows
            else:
                if errors:
                    raise RuntimeError(f"{name}: 정상 데이터로 시작이 차단됐습니다.")
                ready = bool(app_windows) and any(
                    (data_root / "MyDesktopCalendar" / "backups").glob("calendar_auto_*.cnbak")
                )
```

바꿀 코드:

```python
            errors = [w for w in observed if w["title"] == expected_error and w["responding"]]
            notices = [w for w in observed if w["title"] == UPGRADE_NOTICE_TITLE and w["responding"]]
            if notices and name != "upgrade":
                raise RuntimeError(f"{name}: 업그레이드가 아닌데 업데이트 안내창이 표시됐습니다.")
            app_windows = [w for w in observed if w["width"] >= 350 and w["height"] >= 450
                           and w["responding"] and w["title"] not in
                           (expected_error, "기후노트 — 처음 설정", UPGRADE_NOTICE_TITLE)]
            if name == "blocked":
                ready = bool(errors) and not app_windows
            else:
                if errors:
                    raise RuntimeError(f"{name}: 정상 데이터로 시작이 차단됐습니다.")
                ready = bool(app_windows) and any(
                    (data_root / "MyDesktopCalendar" / "backups").glob("calendar_auto_*.cnbak")
                ) and (name != "upgrade" or bool(notices))
```

- [ ] **Step 6: 새 시험과 시작 경로·데이터 기존 시험을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_upgrade_notice.py tests/test_schedule_storage.py tests/test_database.py tests/test_data_safety.py tests/test_release_smoke.py tests/test_first_run.py tests/test_startup_path.py tests/test_ui.py -q`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add main.py ui_main.py tools/smoke_release.py tests/test_upgrade_notice.py
git commit -m "feat: 예전 형식 데이터를 올린 실행에서 한 번 업데이트 안내창

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```


### Task 16: v4.1 버전 표시와 문서

**Files:**
- Modify: `app_info.py`, `tests/test_ui.py`, `tests/test_packaging.py`, `tools/verify.py`
- Modify: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/UI_PATTERNS.md`, `docs/TESTING.md`, `docs/RELEASE_HISTORY.md`, `README.md`, `README_detail.md`

**Interfaces:**
- Consumes: Task 1~14 전체
- Produces: `APP_VERSION = "v4.1"`(EXE `기후노트_v4.1.exe`, Windows `4.1.0.0`), 정본 문서의 v4.1 계약. 실행 ID·EXE 해시·시험 수는 Task 17에서 채운다

- [ ] **Step 1: 출시일을 정한다**

이 계획의 날짜는 `2026. 10. 16.`(계획 작성일)이다. 이 Task를 다른 날 하면 아래 코드·문서의 `2026. 10. 16.`와 `docs/RELEASE_HISTORY.md` 제목의 날짜를 모두 그날로 바꾼다(`date +"%Y. %m. %d."`로 확인). Task 17 release를 또 다른 날 하면 Task 17 Step 1에서 한 번 더 맞춘다.

- [ ] **Step 2: 버전 코드와 버전 시험을 바꾼다**

(1) `app_info.py` — 표시 버전·출시일. 찾을 원문:

```python
APP_VERSION = "v4.0a"
APP_RELEASE_DATE = "2026. 10. 15."
```

바꿀 코드:

```python
APP_VERSION = "v4.1"
APP_RELEASE_DATE = "2026. 10. 16."
```

(2) `tests/test_ui.py` — 설정 하단 문구 시험을 v4.1로. 찾을 원문:

```python
def test_settings_credit_uses_v40a_metadata(qtbot, app_dir, qapp):
    """v4.0a의 설정 하단 문구는 단일 앱 메타데이터를 따른다."""
    win = SettingsWindow()
    qtbot.addWidget(win)

    assert APP_VERSION == "v4.0a"
    assert win.author_label.text().startswith(f"v4.0a  ·  {APP_RELEASE_DATE}")
```

바꿀 코드:

```python
def test_settings_credit_uses_v41_metadata(qtbot, app_dir, qapp):
    """v4.1의 설정 하단 문구는 단일 앱 메타데이터를 따른다."""
    win = SettingsWindow()
    qtbot.addWidget(win)

    assert APP_VERSION == "v4.1"
    assert win.author_label.text().startswith(f"v4.1  ·  {APP_RELEASE_DATE}")
```

(3) `tests/test_packaging.py` — Windows 숫자 버전 표에 v4.1을 더한다. 이 원문 바로 뒤에:

```python
    assert _windows_version_parts("v4.0a") == (4, 0, 1, 0)
```

넣을 코드:

```python
    assert _windows_version_parts("v4.1") == (4, 1, 0, 0)
```

(4) `tools/verify.py` — 수동 확인 목록에 일정 알림을 더한다. 찾을 원문:

```python
    "특정 PC 멈춤 재현", "Defender 검사", "라이선스/SBOM/서명 후속 과제",
)
```

바꿀 코드:

```python
    "특정 PC 멈춤 재현", "Defender 검사", "라이선스/SBOM/서명 후속 과제",
    "일정 알림 실제 시각·절전 복귀·PIN 잠금·Win+D·다중 모니터 카드 위치·알림음",
)
```

- [ ] **Step 3: 버전 시험을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui.py::test_settings_credit_uses_v41_metadata tests/test_ui.py::test_update_guide_text_uses_current_version tests/test_packaging.py tests/test_verify.py -q`
Expected: PASS

- [ ] **Step 4: 정본 문서를 바꾼다**

되돌리기 절차(README_detail)의 2~4단계는 Task 17 리허설이 실제 v4.0a EXE로 그대로 따라 해 본다. `calendar.db-wal`·`-shm`을 남긴 채 `calendar.db`만 바꾸면 v18의 WAL이 옛 DB에 덮여 손상될 수 있으므로 세 파일을 함께 지우는 순서를 바꾸지 않는다.

(1) `AGENTS.md` — 핵심 개발 원칙 끝에 형식 버전 원칙을 더한다. 이 원문 바로 뒤에:

```markdown
- 데이터 변경 기능 추가 시: `tests/`에 왕복 검증 테스트 필수.
```

넣을 코드:

```markdown
- v4.1부터 DB는 v18, 내보내기 형식은 v3다. 아래 이전 항목의 'DB v17·Export v2 유지'는 그 기능이 형식을 바꾸지 않았다는 당시 기록이다. v18 마이그레이션은 일정 표에 열 6개만 한 트랜잭션으로 더하고 기존 값은 읽거나 쓰지 않는다. v4.0a 이하 EXE는 v18 DB를 보면 데이터를 바꾸지 않고 시작을 멈춘다(되돌리기는 `backups/calendar_pre_v18_v17.db`, 그 뒤 입력분 제외).
```

(2) `AGENTS.md` — 보존할 계약에 일정 세부 설정 계약을 더한다(일정 인라인 편집 항목 바로 뒤). 이 원문 바로 뒤에:

```markdown
- 일정 인라인 편집은 입력창·이모지 버튼·팝업을 하나의 편집 영역으로 다룬다. 저장 실패 시 편집 원본을 유지하고 날짜/월/검색 이동·목록 재생성·데이터 작업·정상 종료를 보류한다. 잠금·트레이 숨김·초기화 때 팝업과 예약된 포커스 복원을 취소한다. 키보드 검사는 실제 포커스된 버튼으로 입력하며 상세 동작은 [UI 계약](docs/UI_PATTERNS.md)을 따른다.
```

넣을 코드:

```markdown
- 일정 시각·알림·반복·기간(v4.1): 세부 설정은 스마일 옆 시계 버튼의 카드에서 고르며 카드 안에서는 다른 팝업을 띄우지 않는다. 저장은 `schedules`의 평문 열 `start_time`·`end_date`·`repeat_rule`·`repeat_until`·`repeat_skip`·`alarm_before`이고 본문 암호화·salt는 그대로다. 규칙(검증·펼치기·알림 시각·막대 차선·문구)은 Qt·DB 없는 `schedule_rules.py` 한 곳에 두고 DB 쓰기·가져오기·화면이 같은 `validate_options`를 쓴다. 화면은 나타나는 일정(`get_schedules`·`get_occurrences`)을 쓰고 원본 행 함수(`get_all_schedule_*`·`get_schedules_for_month`)는 지우지 않는다. 알림은 앱이 켜져 있을 때만 카드로 알리며 `schedule_alarm_seen_at`은 카드를 띄울 때와 알림 켜진 일정이 있을 때의 정상 종료 때만 쓴다(알림 없는 DB는 시작·종료로 바뀌지 않는다). 예전 형식 DB를 올린 실행에서만 메인 창이 뜬 뒤 '기후노트 업데이트 안내' 창을 한 번 띄우며 아무것도 저장하지 않는다(이미 배포된 v4.0a의 차단 창 문구는 바꿀 수 없어서). 상세는 [설계](docs/superpowers/specs/2026-10-16-schedule-time-repeat-period-design.md)·[UI 계약](docs/UI_PATTERNS.md)·[아키텍처](docs/ARCHITECTURE.md)를 따른다.
```

(3) `AGENTS.md` — 기록 관리 맨 위에 v4.1 항목을 더한다(검증 값은 Task 17에서 채운다). 이 원문 바로 앞에:

```markdown
- 2026-10-15 **v4.0a**: 백업 검증 임시 DB의
```

넣을 코드:

```markdown
- 2026-10-16 **v4.1**(작업 중): 일정 시각·알림·반복·기간. DB v18(일정 표 열 6개 추가, 한 트랜잭션)·Export v3·새 설정 키 `schedule_alarm_seen_at`(Export 제외). EXE `기후노트_v4.1.exe`, Windows `4.1.0.0`. 검증·배치는 [작업 기록](docs/work/2026-10-16-v4.1-schedule-time-repeat-period.md)을 따른다.

```

(4) `docs/ARCHITECTURE.md` — 스키마 제목. 찾을 원문:

```markdown
## Database Schema (v17)
```

바꿀 코드:

```markdown
## Database Schema (v18)
```

(5) `docs/ARCHITECTURE.md` — 일정 표 설명 뒤에 v18 열을 적는다. 이 원문 바로 뒤에:

```markdown
- **schedules / memos**: Encrypted content storage. `schedules` has `color TEXT DEFAULT '#FFD166'` (plaintext, not encrypted).
```

넣을 코드:

```markdown
- **schedules v18 열(v4.1)**: `start_time`(`HH:MM` 또는 `''`=하루 종일), `end_date`(기간 끝 포함, `''`=하루, 최대 365일), `repeat_rule`(`''`·`daily`·`weekdays`·`weekly`·`monthly`·`yearly`), `repeat_until`(반복 끝 포함, `''`=계속), `repeat_skip`(이 날만 삭제한 날짜, 쉼표·오름차순·500개 이하), `alarm_before`(INTEGER NULL, 기준 시각보다 몇 분 앞). 모두 평문이며 기존 행은 기본값(`''`·NULL)이다. 반복이면 `end_date=''`, 알림은 시각이 있으면 {0,10,30,60,1440}, 하루 종일이면 {0,1440}(기준 09:00). 규칙의 정본은 `schedule_rules.validate_options`다.
```

(6) `docs/ARCHITECTURE.md` — 마이그레이션 목록 끝에 v17→v18을 더한다. 이 원문 바로 뒤에:

```markdown
- **v16→v17**: Adds only the three schedule display-color settings and `calendar_position_mode` via `INSERT OR IGNORE`. It does not alter a table, schedule row, or ciphertext.
```

넣을 코드:

```markdown
- **v17→v18(v4.1)**: `BEGIN IMMEDIATE` 안에서 일정 표에 없는 열만 `ALTER TABLE ... ADD COLUMN`으로 더하고 `user_version=18`까지 한 번에 `COMMIT`한다. 중간에 실패하면 `ROLLBACK`으로 열 0개·v17로 돌아간다. 기존 행 값·ID·암호문·`sqlite_sequence`·salt는 읽거나 쓰지 않는다. 시작 순서상 `backups/calendar_pre_v18_v17.db` 검증 스냅샷이 먼저 생긴다. 건강 검사는 `user_version`이 앱보다 크면 `schema_newer`(구버전 EXE가 새 데이터를 만난 경우, 데이터 무변경), v18인데 새 열이 하나라도 없으면 `schema_invalid`로 멈춘다.
```

(7) `docs/ARCHITECTURE.md` — Export/Import 설정 설명. 찾을 원문:

```markdown
- **Export/Import Settings**: `app_settings` is included in round-trip backups except `privacy_pin`.
```

바꿀 코드:

```markdown
- **Export/Import Settings**: `app_settings` is included in round-trip backups except `privacy_pin` and `schedule_alarm_seen_at` (`EXPORT_EXCLUDED_SETTINGS`). Export v3(v4.1)는 일정마다 세부 설정 6개를 항상 쓰고, Import는 v1·v2(새 열 기본값)와 v3(필드별 형식 검사 + `validate_options`, 하나라도 틀리면 아무것도 쓰지 않음)를 받는다. v4.0a 이하는 v3 파일을 '지원하지 않는 format_version'으로 거절한다.
```

(8) `docs/ARCHITECTURE.md` — 설정 키 목록 끝에 알림 처리 시각을 더한다. 이 원문 바로 뒤에:

```markdown
  - `SETTING_SCHEDULE_COLOR_1/2/3` — 기존 일정 슬롯 3개의 표시색
```

넣을 코드:

```markdown
  - `SETTING_SCHEDULE_ALARM_SEEN_AT = "schedule_alarm_seen_at"`(v4.1) — 여기까지의 일정 알림은 처리함(`YYYY-MM-DDTHH:MM:SS`). 카드를 띄울 때와 알림 켜진 일정이 있을 때의 정상 종료 때만 쓰고 Export/Import에서 뺀다. 없으면 '지금'부터 센다.
```

(9) `docs/ARCHITECTURE.md` — 모듈 표에 새 모듈 네 줄을 더한다(`holidays.py` 줄 앞). 이 원문 바로 앞에:

```markdown
| `holidays.py` | Offline Korean holiday/lunar data
```

넣을 코드:

```markdown
| `schedule_rules.py` | v4.1 일정 세부 설정 규칙(Qt·DB 없음): `ScheduleOptions`, 시각 입력 해석, `validate_options`, 반복·기간 펼치기(`occurrence_dates`, 월말·윤년 보정), 알림 시각(`alarm_times`, 하루 종일 09:00), 주 단위 막대 조각·차선(`week_segments`), 한국어 설명·알약·툴팁 문구 |
| `ui_schedule_options.py` | v4.1 시계 버튼·세부 카드(칩·시각 입력·작은 달력, 팝업 안 팝업 없음)·알약 줄, 선 아이콘 그리기·말줄임 라벨. 이모지 팝업과 같은 수명 규칙 |
| `ui_calendar_spans.py` | v4.1 중간·크게 달력의 여러 날 막대 오버레이(레이아웃 밖, 마우스 통과, 칸 위치를 그릴 때마다 다시 읽음) |
| `ui_schedule_alarm.py` | v4.1 앱 안 일정 알림: 단발 타이머 엔진(최대 60초, 확인 창 12시간, 시계 역행 보호, '5분 뒤 다시'는 메모리)과 화면 오른쪽 아래 카드(포커스를 빼앗지 않음, PIN 잠금 중 내용 가림) |
```

(10) `docs/ARCHITECTURE.md` — `database.py` 줄의 스키마 버전. 찾을 원문:

```markdown
SQLite CRUD + schema migration (v17);
```

바꿀 코드:

```markdown
SQLite CRUD + schema migration (v18, 일정 세부 설정 열);
```

(11) `docs/ARCHITECTURE.md` — `database.py` 줄의 내보내기 형식. 찾을 원문:

```markdown
Export v2 단일 read snapshot
```

바꿀 코드:

```markdown
Export v3 단일 read snapshot
```

(12) `docs/UI_PATTERNS.md` — UI 상세 계약 앞에 v4.1 일정 화면 계약 절을 더한다. 이 원문 바로 앞에:

```markdown
## UI 상세 계약
```

넣을 코드:

```markdown
## 일정 시각·알림·반복·기간 (v4.1)

- **입력줄**: `[색 원][스마일][시계][입력칸][추가]`. 시계 버튼은 26px 클릭 영역에 22px 원을 그리고, 값이 있으면 파랑(`#2563EB`)과 오른쪽 위 6px 점을 그린다. 아래 알약 줄은 입력칸 왼쪽에 맞추고 값이 있을 때만 보인다(없으면 지금 배치와 같다). 알약은 22px·최대 150px 말줄임이며 누르면 카드, ×는 그 항목만(시각 ×는 알림도) 지운다. 추가에 성공했을 때만 비운다. 보류 값의 기간은 길이로 기억해 날짜를 바꿔도 따라가고, 새 날짜보다 앞선 반복 끝은 '계속'으로 돌린다.
- **세부 카드**: 330px 흰 카드(`#D9E1EC`, 12px, 그림자 여백 16px)의 `Qt.Popup`. 시각(하루 종일/시각+입력칸, Enter·다른 곳 누르기·닫기 때 반영, 틀리면 빨간 테두리 뒤 마지막 값), 알림(시각: 없음·정시·10분·30분·1시간·하루 전 / 하루 종일: 없음·당일 오전 9시·하루 전 오전 9시), 기간(하루/여러 날 + 작은 달력, 365일까지), 반복(안 함·매일·평일·매주·매월·매년 + 끝 계속/날짜까지). 여러 날과 반복은 서로 막고 안내한다. 드롭다운·`QCalendarWidget`·메뉴 같은 팝업 안 팝업은 쓰지 않는다. 칩의 `clicked(bool)`은 `lambda checked=False: slot()`으로 받는다(기본값 인자가 덮이지 않게). 잠금·트레이 숨김·초기화 전 폐기·크기 전환·미니앱 열기·종료 때 닫고, 닫힌 뒤 도착한 변경은 버린다.
- **목록 줄**: `[색 점][시각 열][본문+반복·종 아이콘][기간 글자][휴지통]`. 시각 열(40px)은 그날 시각이 보이는 일정이 있을 때만 생긴다. 정렬은 시각 없이 보이는 것(하루 종일·기간 둘째 날 이후) 먼저 ID 순, 그다음 시각·ID 순이다. 본문은 PlainText이고 그릴 때만 말줄임한다(`text()`는 전체). 툴팁은 본문 + 세부 설명 줄. 추가 직후 새 줄은 1.2초 동안 `#EFF6FF`.
- **편집**: `[스마일][시계][본문]` + 요약 줄(반복이면 `… · 모든 날에 적용`). 반복 일정은 시리즈 전체를 고치고, 다른 날에서 반복을 끄면 첫 날짜만 남는다고 카드에 안내한다. 세부 설정을 바꿔 저장하면 편집 종료 뒤 목록을 다시 만들고, 다른 줄을 편집 중이면 그 편집이 끝날 때까지 미룬다. 형식이 다른 옛 날짜 일정은 시계 버튼을 끄고 본문만 고친다.
- **반복 지우기**: 휴지통·우클릭에 `이 날만 삭제`(달력 아이콘)/`반복 전체 삭제`(빨간 반복 아이콘). 반복이 아닌 일정은 지금처럼 바로 지우고 우클릭은 `편집/삭제`다.
- **달력**: 기본 크기는 칸 구조를 그대로 두고 나타나는 일정으로 개수·색을 센다. 중간·크게는 시각 칩 `14:00 본문`(굵게 안 함, PlainText)이고, 여러 날 일정은 `CalendarSpanOverlay` 막대다(칩과 같은 선 6px/4px, 주가 이어지는 쪽은 각진 끝, 칸 높이에서 칩 자리-1까지 차선, 나머지는 `+N 더`). 7열 같은 stretch·칩 Ignored 계약은 그대로다(오버레이는 레이아웃 밖).
- **알림 카드**: 화면 작업 영역 오른쪽 아래 12px, 320px, 왼쪽 4px 띠, `Tool|Frameless|StaysOnTop`·`WA_ShowWithoutActivating`. 최대 3건 + `외 N건`, `[5분 뒤 다시][확인]`(놓친 알림은 확인만), PIN 잠금 중에는 내용을 숨긴다. 누르면 캘린더를 보이고 그 날짜로 간다. 새 알림마다 `QApplication.beep()` 한 번. 트레이·보스 키로 숨긴 동안에도 알린다.
- **업데이트 안내**: 예전 형식 DB를 이번 실행에서 올렸을 때만 메인 창이 뜬 0.8초 뒤 '기후노트 업데이트 안내'를 한 번 띄운다. 부모 없는 맨 위 모달 `Dialog`(폭 440, [확인]만)이고, 이전 버전에서 뜨는 '데이터 보호를 위해 실행을 중단했습니다' 창의 뜻과 이전 EXE·바로가기 삭제를 안내한다. 아무것도 저장하지 않으며 새 설치·이미 새 형식이면 뜨지 않는다.

```

(13) `docs/TESTING.md` — EXE 격리 시나리오에 업그레이드를 더한다. 이 원문 바로 뒤에:

```markdown
3. 시작 차단: 합성 DB의 salt 손상 → 데이터 보호 오류창만 표시 → 원본 DB·salt·기존 보호백업 해시 불변 확인.
```

넣을 코드:

```markdown
4. 업그레이드(v4.1): `tests/fixtures/schema_v17.sql`로 만든 v17 합성 데이터 → 새 EXE 시작 → 모든 표의 기존 열 값 해시·salt 불변, 새 열 기본값, v18, `calendar_pre_v18_v17.db`가 원본과 같은지, 그리고 '기후노트 업데이트 안내' 창이 떴는지 확인. 다른 시나리오에서 이 창이 뜨면 실패다.
```

(14) `docs/TESTING.md` — Test Suite에 v4.1 일정 시험 설명을 더한다. 이 원문 바로 앞에:

```markdown
- **컬러 글리프 경계**:
```

넣을 코드:

```markdown
- **일정 시각·알림·반복·기간(v4.1)**: 순수 규칙 `test_schedule_rules.py`(시각 해석·검증·펼치기·월말/윤년·알림 시각·차선·문구), 저장 `test_schedule_storage.py`(v17 고정 DDL에서 마이그레이션 값 불변·멱등·중간 실패 되돌림·`schema_newer`·구 키 암호문·API·Export v3/Import v1~v3·반복 1,000개 시간 상한, data 프로필), 화면 `test_ui_schedule_options.py`·`test_ui_schedule_input.py`·`test_ui_schedule_list.py`·`test_ui_calendar_spans.py`·`test_ui_schedule_alarm.py`(가짜 시계). 100/125/150%는 `QT_SCALE_FACTOR`로 `quick --tests`를 따로 실행한다. 실제 시계의 알림·절전 복귀·PIN 잠금 중 카드·Win+D·다중 모니터 카드 위치·알림음은 수동 확인이다.
```

(15) `docs/TESTING.md` — 수동 배포 확인 표에 일정 알림 줄을 더한다. 이 원문 바로 뒤에:

```markdown
| Defender 검사 | 미확인 | |
```

넣을 코드:

```markdown
| 일정 알림(실제 시각·절전 복귀·PIN 잠금·Win+D·다중 모니터 카드 위치·알림음) | 미확인 | |
```

(16) `docs/RELEASE_HISTORY.md` — 맨 위 버전 절로 v4.1을 더한다. 이 원문 바로 앞에:

```markdown
## v4.0a 백업 검증 임시 짝 파일 누적 수정 (2026-10-15)
```

넣을 코드:

```markdown
## v4.1 일정 시각·알림·반복·기간 (2026-10-16)

- 일정에 시작 시각·여러 날 기간·반복(매일·평일·매주·매월·매년, 끝 날짜·이 날만 삭제)·앱 안 알림을 더한다. 시안 `output/design/schedule-features-20261015/index.html`, 설계 `docs/superpowers/specs/2026-10-16-schedule-time-repeat-period-design.md`.
- DB v18은 일정 표에 열 6개만 한 트랜잭션으로 더하고 기존 값은 바꾸지 않는다. Export v3, 새 설정 키 `schedule_alarm_seen_at`(Export 제외). v4.0a 이하 EXE는 v18 데이터를 보면 데이터를 바꾸지 않고 '데이터 보호를 위해 실행을 중단했습니다'(구조 또는 무결성 확인 실패 문구) 창으로 시작을 멈춘다. 이 문구는 바꿀 수 없으므로 v4.1은 예전 형식 DB를 올린 실행에서 한 번 '기후노트 업데이트 안내' 창으로 미리 알린다. 되돌리려면 `backups/calendar_pre_v18_v17.db`를 쓴다(그 뒤 입력분 제외, 절차는 README_detail).
- 표시 버전 `v4.1`, EXE `기후노트_v4.1.exe`, Windows `4.1.0.0`. 검증·빌드 결과는 [작업 기록](work/2026-10-16-v4.1-schedule-time-repeat-period.md)을 따른다.

```

(17) `README.md` — 주요 기능에 일정 세부 설정을 더한다. 찾을 원문:

```markdown
- 캘린더(기본·중간·크게 3단계 크기), 일정·메모, 전역 검색
```

바꿀 코드:

```markdown
- 캘린더(기본·중간·크게 3단계 크기), 일정·메모, 전역 검색
- 일정 시작 시각·알림·반복(매일·평일·매주·매월·매년)·여러 날 기간(v4.1)
```

(18) `README.md` — 업데이트 안내에 되돌릴 수 없음을 적는다. 이 원문 바로 뒤에:

```markdown
- 데이터는 이 PC와 Windows 계정에 묶여 있습니다. 다른 PC로 옮길 때는 설정의 **내보내기/가져오기**를 쓰세요.
```

넣을 코드:

```markdown
- v4.1로 처음 실행하면 데이터 형식이 바뀌고 한 번 안내창이 뜹니다. 그 뒤 v4.0a 이하 EXE를 실행하면 '데이터 보호를 위해 실행을 중단했습니다' 창이 뜨며 열리지 않습니다. 데이터 손상이 아니니 v4.1을 실행하고, 이전 EXE와 바로가기는 지워 주세요. 되돌리는 방법은 [README_detail.md](README_detail.md)의 다운로드 절에 있습니다.
```

(19) `README_detail.md` — 현재 소스 버전. 찾을 원문:

```markdown
현재 소스 버전 **v4.0a** (2026. 10. 15.)
```

바꿀 코드:

```markdown
현재 소스 버전 **v4.1** (2026. 10. 16.)
```

(20) `README_detail.md` — 슬라이드 안내의 현재 버전. 찾을 원문:

```markdown
현재 소스 버전은 **v4.0a**입니다.
```

바꿀 코드:

```markdown
현재 소스 버전은 **v4.1**입니다.
```

(21) `README_detail.md` — 다운로드 절 맨 앞 버전 소개로 v4.1을 더한다. 이 원문 바로 앞에:

```markdown
**v4.0a는 데이터 폴더에 백업 검증용 임시 파일
```

넣을 코드:

```markdown
**v4.1은 일정에 시작 시각·알림·반복·여러 날 기간을 더한 버전입니다.** 입력칸 옆 시계 버튼에서 고르며, 중간·크게 달력에서는 여러 날 일정이 이어진 막대로 보입니다. 알림은 기후노트가 켜져 있을 때 화면 오른쪽 아래 카드로 알리고(꺼져 있던 동안의 알림은 다음 실행 때 지난 12시간 것만), PIN 잠금 중에는 내용을 숨깁니다. 기존 일정·메모·설정은 그대로 이어집니다.
**v4.1로 처음 실행하면 데이터 형식이 v18로 바뀌고, 그때 한 번 '기후노트 업데이트 안내' 창으로 알려 줍니다.** 그 뒤 v4.0a 이하 EXE를 실행하면 아래 창이 뜨고 열리지 않습니다. **데이터가 손상된 것이 아니라 새 버전 형식이라서 뜨는 창이며, 데이터와 백업은 바뀌지 않습니다.** v4.1 EXE를 실행하면 그대로 열립니다. 이전 버전 EXE와 바탕화면 바로가기는 지워 두세요. Windows 시작 시 자동 실행은 v4.1을 한 번 켜면 v4.1로 바뀝니다.

> **데이터 보호를 위해 실행을 중단했습니다**  
> 기존 데이터베이스의 구조 또는 무결성을 확인하지 못했습니다.  
> 데이터와 기존 백업은 변경하지 않았습니다. 데이터 폴더를 보존한 뒤 확인해 주세요.  
> [데이터 폴더 열기] [종료]

내보내기 파일도 v3 형식이 되어 이전 버전에서는 가져올 수 없습니다. 꼭 이전 버전으로 돌아가야 하면 업데이트 직전 사본 `backups\calendar_pre_v18_v17.db`를 씁니다. **v4.1에서 입력한 내용은 이 사본에 없습니다.**

   1. 트레이에서 기후노트를 **완전히 종료**합니다.
   2. `%LOCALAPPDATA%\MyDesktopCalendar` 폴더 전체를 다른 곳에 복사해 보관합니다.
   3. 그 폴더의 `calendar.db`·`calendar.db-wal`·`calendar.db-shm`을 지웁니다(없는 파일은 넘어갑니다).
   4. `backups\calendar_pre_v18_v17.db`를 그 폴더에 `calendar.db`라는 이름으로 복사합니다.
   5. 이전 EXE를 실행합니다. `.salt`와 다른 파일은 건드리지 않습니다.

```

(22) `README_detail.md` — 버전별 데이터 유지 문장. 찾을 원문:

```markdown
v4.0a는 기존 DB v17·암호화 방식·설정 키·바로가기 6슬롯을 유지합니다.
```

바꿀 코드:

```markdown
v4.1은 DB를 v18로 올립니다(일정 표에 열만 추가하고 기존 값은 바꾸지 않습니다). 암호화 방식·salt·기존 설정 키·바로가기 6슬롯은 유지합니다.
```

(23) `README_detail.md` — 빌드 결과 파일 이름. 찾을 원문:

```markdown
PyInstaller 단일 실행 파일이 `dist/기후노트_v4.0a.exe`로 생성됩니다.
```

바꿀 코드:

```markdown
PyInstaller 단일 실행 파일이 `dist/기후노트_v4.1.exe`로 생성됩니다.
```

(24) `README_detail.md` — 주요 기능에 일정 세부 설정을 더한다(일정 이모지 줄 뒤). 이 원문 바로 뒤에:

```markdown
- **일정 이모지** — 색상 원과 같은 22px 테두리 스마일에서 이모지를 선택합니다
```

넣을 코드:

```markdown
- **일정 시각·알림·반복·기간(v4.1)** — 스마일 옆 시계 버튼에서 시작 시각, 알림(정시~하루 전, 하루 종일은 오전 9시), 반복(매일·평일·매주·매월·매년, 끝 날짜), 여러 날 기간을 고릅니다. 반복 일정은 '이 날만 삭제'와 '반복 전체 삭제'를 고를 수 있습니다
```

- [ ] **Step 5: 문서 링크와 남은 v4.0a 표시를 확인한다**

Run: `grep -n "v4.0a" app_info.py; grep -c "v4.1" README.md README_detail.md AGENTS.md docs/RELEASE_HISTORY.md`
Expected: 첫 grep은 아무것도 찾지 못한다. 둘째 grep은 네 파일 모두 1 이상. README_detail의 v4.0a EXE 경로·해시·시험 수 문장은 Task 17에서 새 값으로 바꾼다

- [ ] **Step 6: 커밋**

```bash
git add app_info.py tests/test_ui.py tests/test_packaging.py tools/verify.py AGENTS.md docs/ARCHITECTURE.md docs/UI_PATTERNS.md docs/TESTING.md docs/RELEASE_HISTORY.md README.md README_detail.md
git commit -m "docs: v4.1 버전 표시와 일정 세부 설정 계약·업그레이드/되돌리기 안내

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```


### Task 17: 릴리스 검증·실제 EXE 업그레이드/되돌리기 리허설·배치

**Files:**
- Modify: `docs/work/2026-10-16-v4.1-schedule-time-repeat-period.md`, `AGENTS.md`(기록 관리 v4.1 항목), `docs/RELEASE_HISTORY.md`, `README_detail.md`(EXE 경로·크기·해시·시험 수)
- 저장소 밖(커밋 안 함): `output/harness/<실행 ID>/rehearse.py`, `dist/기후노트_v4.1.exe`

**Interfaces:**
- Consumes: Task 1~15 전체, 보관 중인 `dist/기후노트_v4.0a.exe`(SHA-256 `2750798C847F0610F7D885366A398B9498E5252D91689344DBEBA05C15BE8A36`)
- Produces: release 실행 ID, `dist/기후노트_v4.1.exe`와 SHA-256, 리허설 결과 `rehearsal.json`. main 병합·push·GitLab Release는 사용자 승인 전에는 하지 않는다

- [ ] **Step 1: 출시일과 작업 트리를 확인한다**

이 Task의 `<실행 ID>`는 release 명령이 출력한 결과 폴더 이름(`output/harness/` 아래, 예: `20261016-181354-60dfcb782d`)이고, `N개`·`<ID>`·`<앞 8자리>`는 그 실행의 실제 값으로 채운다.

```bash
date +"%Y. %m. %d."            # app_info.APP_RELEASE_DATE와 다르면 Task 16 Step 1처럼 세 곳을 맞추고 커밋한다
git status --short             # v4.1 파일이 모두 커밋돼 있어야 한다(9월 미추적 파일·test.png만 남는다)
git stash list | head -1       # Task 1의 9월 기록 stash가 그대로 있어야 한다
```

- [ ] **Step 2: 전체 시험(full)**

Run: `.venv/Scripts/python.exe tools/verify.py full`
Expected: `passed`. 실행 ID와 시험 수를 작업 기록 '검증 증거'에 적는다

- [ ] **Step 3: 합성 배율 100/125/150% quick**

```bash
for f in 1 1.25 1.5; do
  QT_SCALE_FACTOR=$f .venv/Scripts/python.exe tools/verify.py quick --tests \
    tests/test_ui_schedule_options.py tests/test_ui_schedule_input.py tests/test_ui_schedule_list.py \
    tests/test_ui_calendar_spans.py tests/test_ui_schedule_alarm.py tests/test_ui_schedule_emoji.py \
    tests/test_ui_calendar_columns.py tests/test_ui_calendar_cells.py
done
```
Expected: 세 번 모두 `passed`. 각 실행 폴더의 합성 PNG(`schedule-options-card-*.png`, `calendar-span-medium.png`)를 열어 카드·막대가 잘리지 않았는지 눈으로 확인하고 작업 기록에 적는다.

- [ ] **Step 4: PowerShell release(시험·빌드·격리 EXE 4개 시나리오)**

**PowerShell에서** 실행한다(Git Bash면 mingw OpenSSL DLL이 EXE에 섞인다).

```powershell
.\.venv\Scripts\python.exe tools/verify.py release
```
Expected: `passed`. `output/harness/<실행 ID>/smoke.json`의 `scenarios`에 `fresh`·`existing`·`blocked`·`upgrade`가 모두 `passed`(upgrade는 '기후노트 업데이트 안내' 창이 떠야 통과), `result.json`의 `artifact.file_version`·`product_version`이 `4.1.0.0`. 이어서 확인한다.

```powershell
Select-String -Path output\harness\<실행 ID>\build\build\Analysis-00.toc -Pattern 'mingw64' | Measure-Object   # Count 0
```

- [ ] **Step 5: 실제 v4.0a EXE로 업그레이드·구버전 차단·되돌리기를 리허설한다**

아래 스크립트를 `output/harness/<release 실행 ID>/rehearse.py`로 저장하고 **PowerShell**에서 실행한다. 합성 v17 데이터를 만들고 ① v4.0a로 정상 시작 → ② v4.1로 업그레이드(업데이트 안내창 표시, 기존 값·salt 불변, 스냅샷=원본) → ③ v4.0a가 v18에서 시작을 멈추고 DB·salt·백업을 바꾸지 않음 → ④ README_detail의 되돌리기 절차(세 파일 지우고 스냅샷 복사) 뒤 v4.0a가 업데이트 직전 데이터로 시작하는지 본다.

```python
"""v4.0a → v4.1 업그레이드·구버전 차단·되돌리기 리허설(합성 데이터, 실제 EXE).

사용(PowerShell, 저장소 루트): .\\.venv\\Scripts\\python.exe <이 파일> <이번 release의 v4.1 EXE>
이 파일은 output/harness/<실행 ID>/ 아래에 두고 저장소에는 넣지 않는다.
"""
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # output/harness/<run>/이 파일 → 저장소 루트
sys.path.insert(0, str(ROOT))
from tools import smoke_release as smoke  # noqa: E402
from tools.verify import file_hash, write_json  # noqa: E402

ERROR_TITLE = "데이터 보호를 위해 실행을 중단했습니다"
OLD_EXE = ROOT / "dist" / "기후노트_v4.0a.exe"


def launch(exe: Path, data_root: Path, name: str, *, expect_block: bool, expect_notice: bool = False) -> str:
    """이번 Job이 소유한 EXE 하나를 띄워 정상 시작(창+일일 백업) 또는 시작 차단 창을 기다린다.

    expect_notice면 업데이트 안내창까지 떠야 준비 완료이고, 아니면 안내창이 뜨면 실패다.
    """
    command = [sys.executable, str(ROOT / "tools" / "smoke_release.py"), "_launch", str(exe)]
    backups = data_root / "MyDesktopCalendar" / "backups"
    with smoke.managed_launch(command, smoke.data_env(data_root), HERE / f"{name}.log") as (job, process):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"{name}: 창 준비 전 EXE 종료 ({process.returncode})")
            windows = smoke.windows_in_job(job)
            errors = [w for w in windows if w["title"] == ERROR_TITLE and w["responding"]]
            notices = [w for w in windows if w["title"] == smoke.UPGRADE_NOTICE_TITLE and w["responding"]]
            apps = [w for w in windows if w["width"] >= 350 and w["height"] >= 450 and w["responding"]
                    and w["title"] not in (ERROR_TITLE, smoke.UPGRADE_NOTICE_TITLE)]
            if notices and not expect_notice:
                raise RuntimeError(f"{name}: 업그레이드가 아닌데 업데이트 안내창이 떴습니다")
            if expect_block and errors and not apps:
                return "blocked"
            if not expect_block and errors:
                raise RuntimeError(f"{name}: 시작이 차단됐습니다")
            if (not expect_block and apps and any(backups.glob("calendar_auto_*.cnbak"))
                    and (notices or not expect_notice)):
                time.sleep(2)  # 시작 직후 저장이 끝날 여유
                return "started_with_notice" if notices else "started"
            time.sleep(0.2)
    raise TimeoutError(f"{name}: 60초 안에 기대한 창이 없습니다")


def main(new_exe: Path) -> int:
    if not OLD_EXE.is_file():
        raise SystemExit(f"구버전 EXE가 없습니다: {OLD_EXE}")
    data_root = HERE / "rehearsal-appdata"
    data_root.mkdir()
    app_dir = data_root / "MyDesktopCalendar"
    report = {"old_exe": str(OLD_EXE), "old_sha256": file_hash(OLD_EXE),
              "new_exe": str(new_exe), "new_sha256": file_hash(new_exe), "steps": {}}

    seeded = smoke.data_step("seed_v17", data_root, HERE / "seed.json")
    report["steps"]["seed_v17"] = seeded["version"]
    report["steps"]["v40a_on_v17"] = launch(OLD_EXE, data_root, "v40a-on-v17", expect_block=False)
    before = smoke._original_columns_snapshot(app_dir / "calendar.db")
    if before["tables"] != seeded["tables"] or before["version"] != 17:
        raise ValueError("v4.0a가 v17 합성 데이터를 바꿨습니다")

    report["steps"]["v41_upgrade"] = launch(new_exe, data_root, "v41-upgrade", expect_block=False,
                                            expect_notice=True)
    after = smoke.data_step("inspect_upgrade", data_root, HERE / "after.json")
    if after["tables"] != before["tables"] or after["salt_sha256"] != seeded["salt_sha256"]:
        raise ValueError("업그레이드가 기존 값이나 salt를 바꿨습니다")
    if after["pre_snapshot"] != {"tables": before["tables"], "version": 17}:
        raise ValueError("마이그레이션 전 스냅샷이 원본과 다릅니다")

    protected = smoke.protected_hashes(data_root)
    report["steps"]["v40a_on_v18"] = launch(OLD_EXE, data_root, "v40a-on-v18", expect_block=True)
    if smoke.protected_hashes(data_root) != protected:
        raise ValueError("구버전 EXE가 v18 DB·salt·백업을 바꿨습니다")

    # README_detail의 되돌리기 절차 2~4단계를 그대로 따른다.
    kept = HERE / "rehearsal-kept-copy"
    shutil.copytree(app_dir, kept)
    for name in ("calendar.db", "calendar.db-wal", "calendar.db-shm"):
        target = app_dir / name
        if target.exists():
            target.unlink()
    shutil.copy2(app_dir / "backups" / "calendar_pre_v18_v17.db", app_dir / "calendar.db")
    report["steps"]["v40a_after_rollback"] = launch(OLD_EXE, data_root, "v40a-rollback", expect_block=False)
    rolled = smoke._original_columns_snapshot(app_dir / "calendar.db")
    if rolled != {"tables": before["tables"], "version": 17}:
        raise ValueError("되돌린 DB가 업데이트 직전과 다릅니다")
    report["status"] = "passed"
    write_json(HERE / "rehearsal.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
```

```powershell
.\.venv\Scripts\python.exe output\harness\<실행 ID>\rehearse.py output\harness\<실행 ID>\dist\기후노트_v4.1.exe
```
Expected: 마지막 출력의 `"status": "passed"`와 `steps`가 `seed_v17=17`, `v40a_on_v17=started`, `v41_upgrade=started_with_notice`, `v40a_on_v18=blocked`, `v40a_after_rollback=started`. 실패하면 배치하지 않고 원인을 고친 뒤 release부터 다시 한다.

- [ ] **Step 6: dist에 배치한다**

```powershell
Copy-Item output\harness\<실행 ID>\dist\기후노트_v4.1.exe dist\기후노트_v4.1.exe
Get-FileHash dist\기후노트_v4.1.exe -Algorithm SHA256
(Get-Item dist\기후노트_v4.1.exe).Length
Get-FileHash dist\기후노트_v4.0a.exe -Algorithm SHA256   # 2750798C… 그대로(지우지 않는다)
```

- [ ] **Step 7: 검증 결과를 문서에 채운다**

- 작업 기록 `docs/work/2026-10-16-v4.1-schedule-time-repeat-period.md`: '검증 증거' 표에 data(Task 7)·full·quick 3개·release·리허설 실행 ID와 결과, '결정과 진행'에 실제로 바꾼 결정, '미해결과 인계'에 수동 확인 항목(TESTING.md 표의 일정 알림 줄 포함)과 '배포·커밋·push 여부: 브랜치 커밋만, main 병합·push·Release는 사용자 승인 대기'.
- 같은 기록의 '미해결과 인계'에 기존 동작 메모를 남긴다: 열린 스티키 창은 앱이 크기를 5mm 격자에 맞춰 저장한다(300×400→306×396, v4.0부터 같은 동작, 이번 범위 밖). 그래서 `seed_v17`·리허설의 합성 스티키는 닫힌 상태로 둔다.
- `AGENTS.md` 기록 관리의 `**v4.1**(작업 중)`을 `**v4.1**`로 바꾸고 문장 끝에 `full <ID> N개, 100/125/150% quick 각 N개, PowerShell release <ID> N개·새 빌드·격리 실행 4개(upgrade 포함) 통과, 실제 v4.0a EXE 업그레이드·차단·되돌리기 리허설 통과, dist/ 배치(SHA-256 <앞 8자리>…)`를 실제 값으로 적는다.
- `docs/RELEASE_HISTORY.md` v4.1 절 마지막 줄 뒤에 같은 실행 ID·EXE 크기·SHA-256 한 줄.
- GitLab Release 설명 초안: README_detail의 v4.1 단락(업데이트 안내창, v4.0a 경고창 인용과 '데이터 손상이 아님' 설명, 되돌리기 절차)을 그대로 옮긴 글을 작업 기록 끝에 남긴다. 게시는 사용자가 한다.
- `README_detail.md` 다운로드 절: `로컬 EXE는 \`dist/기후노트_v4.0a.exe\` …` 문장을 v4.1 EXE 경로·크기·release 실행 ID·시험 수·시나리오 4개와 [v4.1 작업 기록](docs/work/2026-10-16-v4.1-schedule-time-repeat-period.md) 링크로 바꾸고, 바로 아래 `SHA-256` 코드 블록과 `v4.0a 빌드 확인 명령`·`Get-FileHash 기후노트_v4.0a.exe`를 v4.1 값으로 바꾼다.

- [ ] **Step 8: 커밋**

```bash
git add docs/work/2026-10-16-v4.1-schedule-time-repeat-period.md AGENTS.md docs/RELEASE_HISTORY.md README_detail.md
git commit -m "docs: v4.1 release 검증·EXE 업그레이드 리허설·배치 기록

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 9: 사용자에게 보고하고 승인을 받는다**

짧은 개조식으로 보고한다: 실행 ID·시험 수, EXE 경로·SHA-256, 리허설 결과, 남은 수동 확인(실제 시계 알림·절전 복귀·PIN 잠금·Win+D·다중 모니터·알림음). 그리고 묻는다.
- `feature/v4.1-schedule-time-repeat`를 main에 병합하고 `git push origin main`(브랜치 이름을 꼭 적는다. `--all`·`--mirror` 금지, `archive/local-v3.5` 금지)해도 되는지
- Task 1에서 보존한 9월 미커밋 기록을 `git stash pop`으로 작업 트리에 되돌릴지(되돌려도 커밋에는 넣지 않는다)

승인 전에는 병합·push·GitLab Release를 하지 않는다.

