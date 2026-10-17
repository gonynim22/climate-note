# 일정 세부 설정 카드 리디자인 설계 (A 구성 + 스틸 블루)

- 작성: 2026-10-18 · 상태: **설계 확정, 구현 전** (구현은 다른 모델이 이 문서로 진행)
- 대상: 시계 버튼을 누르면 뜨는 '세부 설정' 카드 (`ui_schedule_options.ScheduleOptionsPopup`)
- 정답 화면(시안): `output/design/schedule-options-redesign-20261017/index.html`의 마지막 판 **"UI Colors 색표로 다시 · Azure (#335C8A)"**
  - 같은 판의 원본 마크업(정확한 CSS 값): `output/design/schedule-options-redesign-20261017/project/UI-Final.dc.html`
  - 지금 카드 실제 캡처: 같은 폴더 `current/*.png` (`capture_current.py`로 다시 찍을 수 있음)
  - Design 캔버스(비공개): https://claude.ai/artifact/57qM7bSZ8FtqDrn6qcd2mZ
  - `output/`은 git 무시 대상이다. 시안 파일이 없으면 이 문서의 값만으로 구현한다.

## 1. 배경과 목표

v4.1 세부 카드는 사용자 평가로 **"너무 크고 복잡하다"**와 **"밋밋하다"**는 문제가 함께 있다.
- 크기: 폭 330px, 높이 258 / 369 / 473px. 세 상태는 처음 열었을 때 / 15:00·10분 전·매주 / 여러 날 달력이다.
- 모양: 테두리가 있는 칩이 20개 넘게 흩어져 있다. 알림과 반복은 각각 두 줄을 차지한다. 주황 안내문과 맨 아래 안내줄이 높이를 더 키운다.

사용자 결정:
- **시안 A(한 줄 세그먼트) 구성**을 쓴다.
- **시안 C의 색감(색 머리 띠 + 색으로 채운 선택)**을 쓴다.
- 앱 머리줄 남색 `#01295F`와 겹치지 않는 색을 쓴다.
- 그 색은 UI Colors(uicolors.app)에서 받은 색표의 단계로 맞춘다.
- 추천이자 기준 색은 **Azure `#335C8A`**다.

목표 높이(100%, 논리 px, ±15): ① 약 222 · ② 약 274 · ③ 약 442.

## 2. 범위

바꾸는 것:
- `ui_schedule_options.py`의 카드 관련 부분: `ScheduleOptionsPopup`, `CARD_QSS`, `MiniMonthPicker`의 기간 표시, 카드 상수
- `schedule_rules.py`: 표시 문구 도우미 2개 추가. 기존 함수는 바꾸지 않는다.
- 관련 테스트와 `docs/UI_PATTERNS.md`의 v4.1 '세부 카드' 항목

바꾸지 않는 것:
- **시계 버튼**(`ScheduleOptionsButton`), **알약 줄**(`ScheduleOptionsPills`), 일정 목록, 달력 칩·막대, 알림 카드(`ui_schedule_alarm.py`)
  - 이 부품들의 파랑 `#2563EB`(`ACTIVE_COLOR`)은 그대로 둔다. 앱 전체의 강조색이기 때문이다.
- DB 스키마(v18), Export(v3), 설정 키, salt, 저장값. **데이터 영향은 전혀 없다.**
- 동작 계약은 그대로 둔다(아래 §8).
  - 칩을 누르면 즉시 반영된다.
  - Esc나 바깥을 누르면 닫힌다.
  - 카드 안에서는 다른 팝업(드롭다운·`QCalendarWidget`·메뉴)을 띄우지 않는다.
  - 수명 규칙(잠금·트레이·초기화·크기 전환 때 닫기)을 지킨다.
  - 여러 날과 반복은 서로 막힌다.
  - 365일 상한을 지킨다.

## 3. 색 토큰 (UI Colors "Azure", 입력 `#335C8A` = 600 단계)

전체 색표: 50 `#F4F7FB` · 100 `#E8EEF6` · 200 `#CCDBEB` · 300 `#9FBCDA` · 400 `#6B98C5` · 500 `#487CAF` · **600 `#335C8A`** · 700 `#2D4F77` · 800 `#284464` · 900 `#263A54` · 950 `#192638`

| 쓰임새 | 값 | 비고 |
|---|---|---|
| 머리 띠 배경, 고른 칸 채움, 값이 있는 줄의 아이콘, 달력 끝날 | 600 `#335C8A` | 흰 글자 대비 6.91:1, 앱 남색과 2.05:1로 구분 |
| 진한 글자(시각 입력값, '~ 17일(토)', 기간 띠 위 숫자) | 700 `#2D4F77` | 100 위 대비 7.21:1 |
| 세그먼트 바 배경, 달력 상자 배경 | 50 `#F4F7FB` | |
| 세그먼트 바·달력 상자 테두리, 기간 띠, 고르지 않은 칸 hover | 100 `#E8EEF6` | |
| 카드 테두리, 시각 입력칸 테두리, 머리 띠 위 '모두 지우기' 글자 | 200 `#CCDBEB` | 600 위 대비 4.9:1 |
| 고르지 않은 칸 글자 | `#475569` | 50 위 대비 7.05:1 |
| 안내 글자(알림 시각 설명 등) | `#64748B` | |
| 막힘 안내, '끝' 라벨 | `#94A3B8` | |
| 끈 칸 글자, 끈 줄 아이콘 | `#B8C2CF` | |
| 값이 없는 줄의 아이콘 | `#64748B` | |
| 본문 키보드 포커스 테두리 | `#2563EB` 2px | 지금과 같다 |
| 머리 띠 위 키보드 포커스 테두리 | `#FBBF24` 2px | 남색 머리줄과 같은 규칙 |
| 반복 끄기 경고(`series_note`) | `#B45309` | 데이터 영향 경고라서 주황을 유지 |

모듈 상수로 둔다. 예: `CARD_ACCENT = "#335C8A"`, `CARD_ACCENT_DARK = "#2D4F77"`, `CARD_TINT_50/100/200`. `ACTIVE_COLOR`(`#2563EB`)는 시계 버튼과 알약 줄 용도로 남긴다.

## 4. 카드 구조와 치수

```
┌ card 320px · 흰색 · 테두리 1px #CCDBEB · radius 12 · 그림자(현행 QGraphicsDropShadowEffect)
│ ┌ 머리 띠 #335C8A (위 모서리만 radius 11) · 여백 10/12/10/14
│ │  [세부 설정 14px 굵게 흰색] ───── [모두 지우기 12px #CCDBEB] [완료 26px 흰 바탕·#335C8A 굵게·radius 6]
│ └
│ ┌ 본문 · 여백 위12 좌우14 아래14 · 줄 간격 12
│ │  [아이콘18][10][시각 바]  [시각 입력 60×28]
│ │  [아이콘18][10][알림 바 ────────────── 가득]
│ │              알림 설명 11px (값이 있을 때만)
│ │  [아이콘18][10][기간 바] [기간 글자 또는 막힘 안내]
│ │              (여러 날이면) 작은 달력 상자
│ │  [아이콘18][10][반복 바 ────────────── 가득]
│ │              [반복 설명 ……가득……] 끝 [계속|날짜까지]   (반복일 때만)
│ │              (날짜까지면) '12월 31일(목)까지 ▾' + 작은 달력 상자
│ │              막힘 안내 / 반복 끄기 경고
│ └
└
```

- `CARD_WIDTH` 330 → **320**. `SHADOW_MARGIN`, 그림자, `popup_position`, `remove_dwm_border`는 그대로다.
- 들여쓰기 기준은 아이콘 18 + 간격 10 = **28px**. 설명, 달력 상자, 끝 줄은 모두 이 위치에서 시작한다.
- **없앤다**: 맨 아래 'Esc · 바깥을 누르면 닫힘' 안내줄(`scheduleOptionsHint`)과 아래쪽 '완료' 줄. '완료'는 머리 띠로 옮긴다.
- **글자 라벨('시각'·'알림'·'기간'·'반복')을 아이콘으로 바꾼다.**
  - 기존 `draw_icon`/`icon_pixmap`(`clock`·`bell`·`calendar`·`repeat`)을 16px로 그린 18×18 `QLabel`을 쓴다.
  - 각 아이콘 라벨과 해당 바에 `setAccessibleName`/`setToolTip`으로 '시각'·'알림'·'기간'·'반복'을 준다.
- 아이콘 색은 값이 있으면 600이다.
  - 값이 있다는 기준: 시각은 `start_time`, 알림은 `alarm_before is not None`, 기간은 `end_date`, 반복은 `repeat_rule`가 있는 경우다.
  - 값이 없으면 `#64748B`다. 반복 줄이 여러 날 때문에 막혔을 때만 `#B8C2CF`다.

Qt 구현 메모:
- QSS는 `box-shadow`를 지원하지 않는다. 고른 칸은 그림자 대신 채움으로 표현한다.
- 자식 배경은 부모의 둥근 모서리에 잘리지 않는다. 그래서 다음처럼 만든다.
  - 카드 레이아웃 여백을 1px로 둔다.
  - 머리 띠는 `QFrame#scheduleOptionsHeader`로 만들고 `border-top-left-radius:11px; border-top-right-radius:11px`를 준다.
- QSS는 `#scheduleOptionsCard …`나 `#objectName`으로 범위를 좁힌다. 범위 없는 규칙은 컨텍스트 메뉴 등 다른 위젯으로 번지므로 쓰지 않는다. 글자 크기는 정수 px만 쓴다.

## 5. 세그먼트 바 (칩 대신)

- 바 하나 = `QFrame#scheduleOptionsTrack`
  - 배경 50, 테두리 1px 100, radius 8
  - 안쪽 `QHBoxLayout` 여백 2, 간격 2
- 칸은 기존 칩 `QPushButton`(`segment=true`, checkable)을 그대로 쓴다.
  - 높이 24, radius 6, 테두리 1px transparent, 글자 12px
  - 기본: 바탕 투명, 글자 `#475569`. hover: 바탕 100
  - `:checked`: 바탕·테두리 600, 흰 글자 굵게
  - `:disabled`: 바탕 투명, 글자 `#B8C2CF`
  - `:focus`: 테두리 2px `#2563EB`
- 폭 규칙:
  - 알림 바와 반복 바는 줄 끝까지 늘리고, 칸은 같은 폭으로 나눈다(`Expanding` + 같은 stretch).
  - 시각, 기간, 끝 바는 글자 폭만큼만 쓴다. 칸 좌우 여백은 시각 12px, 기간 14px, 끝 9px이다.
- 끝 바(계속|날짜까지)는 조금 작게 만든다. 칸 높이 22, 글자 11px, 바 radius 7, 칸 radius 5.
- 기존 테스트 `test_card_width_fits_screen_without_clipped_chips`의 조건을 계속 만족해야 한다. 조건은 두 가지다: 칸 폭이 sizeHint 이상이고, 칸이 카드 안에 들어가야 한다.

## 6. 줄별 상세

### 시각
- 바: `하루 종일 | 시각`. 시각을 고르면 오른쪽에 입력칸을 둔다.
  - 크기 60×28, radius 6, 테두리 200, 글자 12px 굵게 700. 포커스 테두리 2px `#2563EB`, 틀린 값 테두리 2px `#DC2626`
- 입력·검증·반영 규칙은 지금과 같다. Enter·다른 곳 누르기·닫기 때 반영하고, 틀리면 빨간 테두리를 보인 뒤 마지막 값으로 되돌린다.

### 알림
- 시각 일정의 바 글자는 짧게 바꾼다: `없음 | 정시 | 10분 | 30분 | 1시간 | 1일`
  - 각 칸 `setAccessibleName`/`setToolTip`에는 긴 이름을 준다: '알림 없음', '정시', '10분 전', '30분 전', '1시간 전', '하루 전'
- 하루 종일 일정의 바 글자: `없음 | 당일 9시 | 전날 9시`
  - 긴 이름: '알림 없음', '당일 오전 9시', '하루 전 오전 9시'
  - 이 줄의 칸은 같은 폭으로 나누지 않고 글자 폭 비례(`flex 1 1 auto`)로 둔다. 좌우 여백은 6px이다.
  - 기존 `compact` 속성 규칙(125·150%에서 2px 모자라던 문제)은 글자가 짧아져 필요 없을 수 있다. 다만 125·150% 실행에서 잘림이 없는지 꼭 확인한다.
- 알림 설명 줄(11px `#64748B`, 들여쓰기 28): **시각 일정이고 알림이 있을 때만** 보인다.
  - 문구는 `schedule_rules.alarm_caption(day, options)`로 만든다(§9). 예: `10분 전, 14:50에 알림`, `정시, 15:00에 알림`
  - 알림이 다른 날로 넘어가면 날짜를 붙인다. 예: `하루 전, 10월 14일(수) 15:00에 알림`, 00:05 시작에 10분 전이면 `10분 전, 10월 14일(수) 23:55에 알림`
  - 기준 날짜 `day`는 카드가 보고 있는 날짜(`self._occurrence`)다.
  - 하루 종일 일정에는 설명 줄을 두지 않는다. 칸 글자만으로 뜻이 분명하다.
- 알약 줄과 목록에 쓰는 기존 `alarm_label`은 바꾸지 않는다.

### 기간
- 바: `하루 | 여러 날`.
- 여러 날이면 바 오른쪽에 기간 글자를 둔다(`period_caption` 버튼 재사용, 평평한 버튼).
  - 모양: 12px 굵게 700 + 회색 `· N일`
  - 문구는 `schedule_rules.period_short_caption(start, end)`로 만든다(§9). 예: `~ 17일(토) · 3일`
  - 누르면 지금처럼 작은 달력을 접었다 편다. 접혀 있을 때만 끝에 ` ▾`를 붙인다.
  - 같은 줄에 들어가지 않으면 다음 줄로 내린다(들여쓰기 28). 판단은 `fontMetrics` 폭 비교로 한다.
- 반복 때문에 여러 날이 막히면 바 오른쪽에 `반복 중엔 하루만`(11px `#94A3B8`)을 둔다. 지금의 주황 안내문(`period_note`)을 대체한다.
- 작은 달력은 §7.

### 반복
- 바: `안 함 | 매일 | 평일 | 매주 | 매월 | 매년`. 같은 폭으로 줄 끝까지 늘린다.
- 반복이면 아래 한 줄(들여쓰기 28)을 둔다.
  - 왼쪽: 반복 설명. 기존 `rules.repeat_caption`을 쓴다. 12px `#334155`이고, 남은 폭을 모두 쓰며 넘치면 말줄임한다. 기존 `ElidedLabel` 재사용 가능하고 툴팁에 전문을 넣는다.
  - 오른쪽: `끝`(11px `#94A3B8`)과 끝 바 `계속 | 날짜까지`
- 날짜까지면 그 아래에 `until_caption` 버튼(`12월 31일(목)까지 ▾`)과 작은 달력 상자를 둔다. 둘 다 들여쓰기 28이다.
- 여러 날 때문에 반복이 막히면 '안 함'만 켜 둔다. 아래에 `여러 날 일정은 반복할 수 없어요`(11px `#94A3B8`)를 둔다. 지금의 `repeat_note`를 대체한다.
- 반복 끄기 경고(`series_note`, 문구는 현행)는 반복 줄 아래에 그대로 두고, 색은 `#B45309`를 유지한다.

## 7. 작은 달력 (`MiniMonthPicker`)

- 바깥 상자: 배경 50, 테두리 1px 100, radius 8, 여백 8/8/6, 들여쓰기 28.
- 머리: `‹  2026년 10월  ›`. 제목 12px 굵게 `#172B4D`, 이동 버튼 22×22.
- 요일과 날짜 색(일·공휴일 빨강, 토 파랑, 고를 수 없는 날 `#CBD5E1`)은 지금과 같다.
- 기간을 **이어진 띠**로 보이게 한다.
  - `grid.setHorizontalSpacing(2)` → **0**으로 바꾼다.
  - 날짜 버튼은 고정폭 30 대신 칸 폭을 가득 채운다.
- `role` 속성을 확장한다.
  - `start`: 기간 첫날(`range_start`). 바탕 100, 글자 700 굵게, radius 왼쪽만 12
  - `in`: 사이 날. 바탕 100, 글자 700, radius 0
  - `end`: 기간 끝날(`selected`, `range_start`가 있을 때). 바탕 600, 흰 글자 굵게, radius 오른쪽만 12
  - `single`: 반복 끝 달력처럼 `range_start` 없이 고른 날. 바탕 600, 흰 글자 굵게, radius 12
  - 지금은 `range_start`와 `selected`가 둘 다 `end`다. 이것을 `start`/`end`로 나눈다.
  - 주가 바뀌는 곳의 띠 끝은 각진 채로 둔다.
- 날짜 선택·월 이동·365일 상한·`date_picked`·`month_changed` 동작은 그대로다.

## 8. 그대로 지키는 동작

- 칩을 누르면 즉시 `options_changed`가 나간다. Esc·바깥·'완료'는 닫기만 하고, 닫은 뒤 늦게 도착한 변경은 무시한다.
- '모두 지우기'(`clear_button`)는 모든 값을 기본값으로 되돌린다.
- `focus_first()`는 지금처럼 시각 칩에 포커스를 준다. Tab/Enter/Space/Esc 동작은 지금과 같다(`keyPressEvent`).
- 잠금·트레이 숨김·초기화 전 폐기·크기 전환·미니앱 열기·종료 때 닫는다. 한 번에 카드 하나만 연다. 닫히면 `deleteLater`. 포커스 복원은 버튼이 가진 타이머로 한다.
- 카드 크기가 바뀌면(달력 펼침·달 이동으로 5↔6줄) `size_changed`를 내보내 위치를 다시 잡는다(`_relayout` 규칙 유지).
- **속성 이름을 유지한다.** 테스트와 `ui_main`이 쓰기 때문이다:
  - `done_button`, `clear_button`, `all_day_chip`, `timed_chip`, `time_edit`
  - `timed_alarm_chips`, `all_day_alarm_chips`, `one_day_chip`, `many_days_chip`
  - `period_caption`, `period_picker`, `period_note`, `repeat_chips`, `repeat_caption`, `repeat_note`, `series_note`
  - `until_row`, `forever_chip`, `until_chip`, `until_caption`, `until_picker`, `card`
  - `period_note`/`repeat_note`의 문구와 색은 §6대로 바꾼다.

## 9. `schedule_rules.py` 추가 함수 (Qt 없음, 순수 함수)

```python
def period_short_caption(start: str, end: str) -> str:
    """세부 카드 기간 글자. 예: '~ 17일(토) · 3일', 달이 다르면 '~ 11월 2일(월) · 19일',
    해가 다르면 '~ 2027년 1월 3일(일) · 81일'."""

def alarm_caption(day: date, options: ScheduleOptions) -> str:
    """세부 카드 알림 설명(시각 일정·알림 있을 때만, 아니면 '').
    예: '10분 전, 14:50에 알림' / 다른 날이면 '하루 전, 10월 14일(수) 15:00에 알림'."""
```
- 알림 시각은 `start_time - alarm_before분`으로 계산한다. 날짜 표기는 `korean_date`나 `KOREAN_WEEKDAYS` 규칙을 따른다.
- `alarm_before`의 이름 부분은 `alarm_label(options)`를 재사용한다.
- 기존 `period_caption`, `alarm_label` 등은 바꾸지 않는다. 툴팁·요약·알약에서 쓰고 있다.

## 10. 테스트

수정:
- `tests/test_ui_schedule_options.py:191`의 기대값을 바꾼다. `period_caption.text()`가 `"~ 23일(금) · 9일"`로 시작해야 한다.
- 맨 아래 안내줄이나 아래쪽 '완료' 위치를 가정한 검사가 있으면 머리 띠 기준으로 고친다.

추가:
- `tests/test_schedule_rules.py`
  - `period_short_caption`: 같은 달, 다른 달, 다른 해, 365일
  - `alarm_caption`: 정시, 10분 전, 1시간 전, 하루 전(날짜 붙음), 자정 넘김(00:05 − 10분), 하루 종일이면 '', 알림 없으면 ''
- `tests/test_ui_schedule_options.py`
  - 머리 띠(`#scheduleOptionsHeader`) 안에 `clear_button`·`done_button`이 있고 `scheduleOptionsHint`는 없다.
  - 알림 칸의 짧은 글자와 긴 접근성 이름
  - 15:00 + 10분이면 알림 설명이 `10분 전, 14:50에 알림`
  - 줄 아이콘 색(값 있음 600, 없음 `#64748B`)은 상태 함수나 속성으로 확인한다.
  - 달력 `role`: 기간은 `start`/`in`/`end`, 반복 끝은 `single`
  - 카드 폭은 320이다(`CARD_WIDTH`).
  - 세 상태의 카드 높이가 목표(§1) ±15 안에 든다.

## 11. 검증 절차와 완료 조건

1. 작업 기록 만들기: [작업 기록 양식](../../templates/WORK_NOTE.md)대로 `docs/work/2026-10-18-schedule-options-card-redesign.md`를 만든다(AGENTS.md 절차 3).
2. 빠른 검사(PowerShell, 프로젝트 루트):
   ```powershell
   .\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_ui_schedule_options.py tests/test_schedule_rules.py tests/test_ui_schedule_input.py tests/test_ui_schedule_list.py tests/test_ui_schedule_emoji.py
   ```
3. 합성 배율: 같은 명령을 `$env:QT_SCALE_FACTOR="1.25"`와 `"1.5"`로 각각 따로 실행한다. 세그먼트 칸 글자가 잘리지 않아야 한다.
4. 화면 대조: `output/design/schedule-options-redesign-20261017/capture_current.py`로 새 카드를 찍는다.
   - `QT_SCALE_FACTOR=2` 권장. 출력 폴더를 `after/`로 바꿔 지금 캡처를 덮지 않는다.
   - 정답 화면(UI-Final)과 나란히 놓고 색, 순서, 간격, 높이를 비교한다.
5. 문서: `docs/UI_PATTERNS.md`의 '일정 시각·알림·반복·기간 (v4.1)' → **세부 카드** 항목을 이 설계대로 고친다. 폭 320, 머리 띠, 세그먼트 바, Azure 토큰, 아이콘 라벨, 알림 설명, 기간 띠를 반영한다. AGENTS.md의 세부 설정 계약 문장은 그대로 유효하므로 고치지 않는다.
6. 수동 확인(자동 검사로 대신할 수 없다):
   - 실제 앱 기본·중간·크게에서 카드가 버튼 아래, 공간이 없으면 위에 뜬다.
   - Win11 팝업에 넓은 DWM 테두리가 생기지 않는다(현행 `remove_dwm_border` 유지).
   - 키보드만으로 모든 값을 고르고 닫을 수 있다.
7. 커밋·push·EXE 빌드·Release는 **사용자 승인 후에만** 한다. push는 `git push origin main`처럼 브랜치를 명시한다.

완료 조건: 2·3의 검사가 통과하고, 4에서 정답 화면과 차이가 없거나 설명된 차이만 남고, 5의 문서가 반영되고, 6의 결과가 '확인함/미확인'으로 작업 기록에 구분되어 있다.
