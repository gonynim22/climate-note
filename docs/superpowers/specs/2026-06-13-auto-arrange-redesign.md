# 자동정렬 재설계 스펙

**날짜**: 2026-06-13  
**대상 파일**: `ui_main.py`, `tests/test_ui.py`  
**범위**: 버그 수정 + 배치 품질 개선 (UX 전체 재설계 제외)

---

## 배경 및 문제점

`_on_arrange_sticky_notes()`는 메뉴 > "자동정렬"로 호출되어 D-Day·집중·스티키 플로팅 위젯을 캘린더 위치 기준으로 배열한다. 현재 두 가지 버그와 두 가지 배치 품질 문제가 있다.

| # | 분류 | 문제 |
|---|---|---|
| 1 | 버그 | 세로 넘침 미처리 — 행이 화면 높이를 초과하면 위젯이 화면 밖으로 사라진다 |
| 2 | 버그 | 캘린더 겹침 — 위젯이 캘린더 사각형을 회피하지 않아 bottom-right 등 설정에서 위젯이 캘린더 위로 올라탄다 |
| 3 | 배치 | 들쭉날쭉 행 — D-Day(220×95)·집중(241×78)·스티키(가변)가 섞여 우측 정렬 행에 빈틈이 생긴다 |
| 4 | 배치 | 큰 스티키 — 리사이즈된 스티키가 `row_max_height`를 크게 만들어 세로 공간 낭비 및 넘침을 앞당긴다 |

---

## 설계 목표

1. **겹침 원천 차단**: 위젯이 캘린더 사각형과 구조적으로 겹칠 수 없도록 시작점을 캘린더 바깥으로 고정
2. **화면 밖 유실 금지**: 세로 넘침 시 화면 안으로 클램프, `InfoBar`로 안내
3. **테스트 용이성**: 배치 계산을 순수 함수로 분리 (Qt/DB 없이 단위 테스트 가능)
4. **기존 보존**: 5mm 스냅 그리드, 타겟 모니터, `_snap_not_past_right`/`_right_aligned_grid_x`, DB 즉시 저장

---

## 구조 변경

### 순수 함수 추출 — `_compute_arrange_layout`

```python
def _compute_arrange_layout(
    items: list[tuple[int, int]],           # (width, height) 리스트
    cal: tuple[int, int, int, int],         # (left, top, right, bottom)
    scr: tuple[int, int, int, int],         # (left, top, right, bottom)
    position: str,                          # "bottom-right" 등 4종
    snap: int,
) -> tuple[list[tuple[int, int]], int]:
    """
    Returns: ([(x, y), ...], clamped_count)
    clamped_count: 화면 밖으로 나가려다 클램프된 위젯 수
    """
```

- Qt 없음, DB 없음 — int 튜플만 사용해 단위 테스트에서 QRect 불필요
- 호출부(`_on_arrange_sticky_notes`)에서 `QRect` → `(left, top, right, bottom)` 변환
- 기존 `_snap_not_past_right`, `_right_aligned_grid_x` 내부에서 재사용
- 반환값은 `(x, y)` 좌표 리스트 (items와 1:1 대응)

### `_on_arrange_sticky_notes` 역할 축소

1. 보이는 위젯 수집: D-Day → 집중 → 스티키 (스티키는 `height` desc 정렬)
2. `_compute_arrange_layout()` 호출
3. 각 위젯 `move()` + DB 저장
4. `clamped_count > 0`이면 `InfoBar.warning()` 표시

---

## 배치 규칙 상세

### 시작점: 캘린더 바깥

| 설정 | 수직 시작 (행 기준선) | 수평 시작 (행 기준선) |
|---|---|---|
| `bottom-right` | `calendar_rect.top() − gap` (위로 쌓임) | `calendar_rect.right()` (왼쪽으로 채움) |
| `bottom-left` | `calendar_rect.top() − gap` (위로 쌓임) | `calendar_rect.left()` (오른쪽으로 채움) |
| `top-right` | `calendar_rect.bottom() + gap` (아래로 쌓임) | `calendar_rect.right()` (왼쪽으로 채움) |
| `top-left` | `calendar_rect.bottom() + gap` (아래로 쌓임) | `calendar_rect.left()` (오른쪽으로 채움) |

- `gap = snap` (기존과 동일)
- `right`계: 각 행을 캘린더 우측 변에 오른쪽 정렬, 왼쪽으로 채움 (한계: `screen_rect.left() + gap`)
- `left`계: 캘린더 좌측 변에 왼쪽 정렬, 오른쪽으로 채움 (한계: `screen_rect.right() − gap`)

### 행 쌓기 방향

- `bottom-*`: 첫 행 하단이 `calendar_rect.top() − gap`, 다음 행은 더 **위**로 (`y -= row_max_height + gap`)
- `top-*`: 첫 행 상단이 `calendar_rect.bottom() + gap`, 다음 행은 더 **아래**로 (`y += row_max_height + gap`)

### 세로 넘침 처리 (버그 1 수정)

- `bottom-*`: 새 행이 `screen_rect.top()`을 침범하면 더 이상 올라가지 않고 `screen_rect.top() + gap`로 클램프
- `top-*`: 새 행이 `screen_rect.bottom()`을 침범하면 `screen_rect.bottom() - row_max_height - gap`로 클램프
- 클램프 후에도 남은 위젯은 해당 클램프 위치에 겹쳐 배치 (화면 밖 유실 방지, `clamped_count` 증가)

### 스티키 정렬 (배치 품질 3·4)

수집 순서: `visible_dday + visible_focus + sorted(visible_sticky, key=lambda w: w.height(), reverse=True)`

높이 내림차순으로 스티키를 정렬하면 비슷한 높이끼리 같은 행에 배치되어 `row_max_height` 낭비가 줄어든다.

---

## 테스트 계획 (`tests/test_ui.py`)

### 유지: 기존 2개 스냅 헬퍼 테스트

`test_right_arrange_snap_does_not_reduce_calendar_margin`, `test_right_arrange_snap_preserves_negative_monitor_margin` — 변경 없음.

### 신규: `_compute_arrange_layout` 단위 테스트

| 테스트 | 검증 내용 |
|---|---|
| `test_arrange_layout_all_within_screen` | 정상 케이스(위젯 수 < 화면 수용 한계): 모든 `(x, y)` 가 `screen_rect` 안에 있고 `clamped_count == 0` |
| `test_arrange_layout_no_overlap_with_calendar` | 4모서리 각각: 반환된 위젯 사각형이 `calendar_rect`와 교차하지 않음 |
| `test_arrange_layout_vertical_overflow_clamped` | 위젯 수를 화면 높이 초과로 설정 → `clamped_count > 0`, 모든 y가 화면 안 |
| `test_arrange_layout_four_positions` | 4모서리 배치 방향 검증: right 계열은 x가 calendar_rect.right() 이하, left 계열은 x가 calendar_rect.left() 이상으로 시작 |
| `test_arrange_layout_sticky_height_sort` | 높이 다른 스티키 3개 → 가장 높은 스티키가 먼저 배치됨 |

---

## 변경 없는 항목

- `large` 스케일 동작 — 범위 외
- `_snap_not_past_right`, `_right_aligned_grid_x` 시그니처/로직
- DB 저장 방식 (`update_sticky_note`, `update_dday_widget`, `update_focus_widget`)
- `InfoBar.info` (위젯 없음 안내) — 기존 유지
- 메뉴 항목명, 트리거 방식
