# 자동정렬 2D 빈-패킹 재설계 구현 계획

> **✅ 구현 완료 (Claude, 2026-06-13).** 실제 구현은 아래 본문과 **두 가지가 다르다**:
> 1. **점수 1순위 = 제외수(skipped)** — bbox 면적이 아님. 면적 우선이 단일 열을 잘못 선택하는 결함을 TDD로 발견·수정.
> 2. **엄격 비겹침 채택** — 공간 부족 시 위젯을 겹쳐 두지 않는다. 못 담는 위젯은 배치하지 않고 `coords[i]=None`으로 두어 **제자리에 유지**하고, "공간이 부족해 N개 위젯은 정렬에서 제외했습니다" 경고만 표시한다. 즉 자동정렬은 **어떤 경우에도 겹침을 만들지 않는다**(사용자 결정). `_pack_columns`의 overflow 처리는 '겹쳐 클램프'가 아니라 'skip'이며, `_compute_arrange_layout`/호출부 반환 의미는 `clamped`(겹친 수)가 아니라 `skipped`(정렬 제외 수)다. 실제 코드(`ui_main.py`)가 단일 출처.

> **(원래 메모) 구현자(Codex)에게:** 이 문서는 자기완결적이다. 알고리즘 전체 의사코드 + 정확한 테스트 케이스가 포함되어 있다. TDD 순서(실패 테스트 → 구현 → 통과)로 진행하라. 이 프로젝트는 git 저장소가 아니므로 커밋 단계는 없다. 작업 디렉토리: `D:\04_Project\GC\MyDesktopCalendar`. 테스트 실행: `python -m pytest tests -q`.

**Goal:** 자동정렬 시 위젯이 겹치는 문제를 없애고, 작은 위젯(D-Day)이 세로 여러 열로 쌓여 이웃한 긴 스티키 높이에 맞춰 깔끔하고 컴팩트하게 배치되는 결정적 2D 빈-패킹 알고리즘으로 `_compute_arrange_layout`을 재작성한다.

**Architecture:** 캘린더 인접 변에서 코너 방향으로 자라는 **컬럼-우선 셸프 패킹**을 기본으로, 치수를 snap 격자로 **양자화(qceil)**하고, 소수의 **결정적 후보(정렬키 4 × 컬럼 수 3 = 최대 12개)**를 실제 생성·점수화해 가장 컴팩트(긴 변 최소)한 안을 고른다. 반환 직전 **모든 위젯 쌍 AABB 사후검증**으로 비겹침을 닫고, 위반 시 증명 가능한 안전 후보(단일 열)로 폴백한다. `_compute_arrange_layout`의 시그니처는 불변이라 호출부(`_on_arrange_sticky_notes`)·DB 저장·테스트 회귀가 없다.

**Tech Stack:** Python(순수 함수, Qt/DB 비의존), PySide6(호출부만), pytest.

**이 계획은 이전 계획([2026-06-13-auto-arrange-redesign.md](2026-06-13-auto-arrange-redesign.md))의 "세로 넘침 시 같은 좌표에 겹쳐 클램프" 방식을 대체한다.** 겹침은 이제 면적이 가용공간을 진짜 초과하는 극단에서만 발생하고, 그조차 화면 밖 유실 없이 처리하며 개수를 보고한다.

---

## 1. 배경 / 문제

현재 `_compute_arrange_layout`(ui_main.py:70)은 행(row) 단위로만 줄바꿈하고, 세로 공간이 부족하면 여러 위젯을 **같은 y에 겹쳐** 쌓는다(클램프-겹침). 사용자 피드백: "자동정렬 시 겹쳐지는 위젯이 너무 많다." 또한 D-Day(220×95) 다수를 한 줄에 가로로만 늘어놓아, 이웃한 긴 스티키 옆에 빈 공간이 크게 남는다.

**사용자의 핵심 통찰**: D-Day 위젯은 가로 한 줄일 필요가 없다. 세로 2열로 쌓으면 스티키 1개 높이와 맞는다. 스티키가 더 길면 3열까지. "여러 경우의 수로 정렬해서 깔끔하게 배치"되는 알고리즘이 필요하다.

**검증된 상수(load-bearing)**: snap=19일 때 D-Day 2개를 세로로 쌓은 높이 `95 + gap + 95 = 95 + 19 + 95 = 209`는, 스티키 기본 높이 `DDAY_HEIGHT*2 + snap = 190 + 19 = 209`와 **정확히 일치**한다(ui_sticky.py:23 `DDAY_HEIGHT=95`, 스티키 기본 높이 생성 ui_main.py 부근). 즉 D-Day 2열 ↔ 스티키 1개 매칭은 우연이 아니라 산술적 사실이며, 알고리즘은 이를 **점수 최적화의 귀결**로 재현한다.

---

## 2. 위젯 / 제약 사실 (실제 코드 값)

| 위젯 | 크기 | 고정/가변 | 최대 개수 |
|---|---|---|---|
| D-Day (`ui_dday.py:151`) | 220 × 95 | 고정 | 5 |
| 집중 (`ui_focus.py:24,389`) | AMBIENT 241 × 78 (정렬 시점 기본) | 고정 | 1 |
| 스티키 (`ui_sticky.py:22-23`) | 최소 220 × 95, 기본 220 × 209 | 가변(리사이즈) | ~10 |

- 정상 위젯 총수 상한 = 5 + 1 + 10 = **16** (`enforce_widget_limits()`가 보장).
- 호출부 수집 순서: `visible_dday + visible_focus + visible_sticky(height desc)` (현 `_on_arrange_sticky_notes`, 유지).
- DB 저장: `update_sticky_note` / `update_dday_widget` / `update_focus_widget` 에 `x_pos`, `y_pos`만 갱신(위치만, 데이터 보존).

**반드시 보존할 하드 제약:**
1. 위젯 상호 비겹침(정상 입력 0겹침).
2. 모든 위젯이 타겟 모니터 `availableGeometry` 안에 완전히 포함(화면 밖 유실 0).
3. 어떤 위젯도 캘린더 사각형과 겹치지 않음.
4. 좌표는 5mm snap 격자 정렬. `_snap_not_past_right`(floor)·`_right_aligned_grid_x`는 **시그니처·로직 변경 금지**, 재사용. 우측 계열은 우측 여백을 줄이지 않음(음수 좌표 모니터 포함).
5. **결정적**: 같은 입력 → 같은 출력. `Date`/`random` 금지(테스트 가능성).
6. `SETTING_CALENDAR_POSITION` 4값: `bottom-right`/`bottom-left`/`top-right`/`top-left` 모두 지원.
7. `large` 캘린더 스케일에서는 플로팅 위젯이 숨겨져 수집 결과가 비므로 자동정렬은 자연히 no-op(현 `InfoBar.info` "열린 노트/위젯이 없습니다" 경로 유지).

---

## 3. 4모서리 배치 규약

`is_right = "right" in position`, `is_bottom = "bottom" in position` 두 부분문자열로 분기. 모두 **"캘린더 인접 변에서 코너로 컬럼 전개, 캘린더 바깥 변에서 코너로 위젯 적층"**의 대칭형이다.

| position | 컬럼 전개(가로) | 컬럼 시작 X (`col_near`) | 가로 한계 (`col_far`) | 위젯 적층(세로) | 적층 기준선 (`band_near`) | 세로 한계 (`band_far`) | 위젯 정렬 |
|---|---|---|---|---|---|---|---|
| **bottom-right** | 우측 → 왼쪽 | `cal_r` (floor) | `scr_l + gap` | 위로 | `cal_t - gap` | `scr_t + gap` | 우측정렬 |
| **bottom-left** | 좌측 → 오른쪽 | `cal_l` (round) | `scr_r - gap` | 위로 | `cal_t - gap` | `scr_t + gap` | 좌측정렬 |
| **top-right** | 우측 → 왼쪽 | `cal_r` (floor) | `scr_l + gap` | 아래로 | `cal_b + gap` | `scr_b - gap` | 우측정렬 |
| **top-left** | 좌측 → 오른쪽 | `cal_l` (round) | `scr_r - gap` | 아래로 | `cal_b + gap` | `scr_b - gap` | 좌측정렬 |

- 위젯은 항상 `band_near`(캘린더 바깥 변에서 gap 떨어진 선)에서만 자라므로 **구조적으로 캘린더와 겹칠 수 없다**.
- right 계열: `_right_aligned_grid_x(col_right, w, snap)` → `x + w ≤ col_right ≤ cal_r`이므로 `x + w ≤ cal.right` (방향 계약).
- left 계열: `x ≥ round(cal_l/snap)*snap ≥ cal.left` (방향 계약).

---

## 4. 최종 알고리즘 (정밀 의사코드)

> 합성안 대비 **수정 사항**: (A) 점수 1순위를 `area`→**`longside`**로 교체(멀티컬럼 선택 보장, Critical 1 수정). (B) 컬럼 분배를 `target` 나눗셈 next-fit → **명시적 최대 G개 연속 컬럼 균형 분할**로 교체(컬럼 수 예측 가능). (C) **가로 클램프도 `clamped` 집계**(Critical 2 수정). (D) `_clamp_window_pos` 별도 안전망 제거, band/screen 경계를 일치시켜 이중 클램프 제거(Important 3 수정).

```python
# ui_main.py — 기존 _compute_arrange_layout(line 70~) 전체를 아래로 교체.
# _snap_not_past_right, _right_aligned_grid_x (line 54~61)는 그대로 둔다(재사용).

def _overlap(a, b):
    """AABB 엄격 겹침. 경계 접촉(공유 변)은 비겹침으로 본다."""
    return a[2] > b[0] and b[2] > a[0] and a[3] > b[1] and b[3] > a[1]


def _split_into_columns(order, qsize, g, gap):
    """order의 위젯 인덱스들을 '최대 g개의 연속(contiguous) 컬럼'으로 균형 분할.

    연속 분할이라 입력 순서(=타입 그룹)가 보존된다. 정확히 g개 이하가 보장된다:
    마지막 컬럼 하나가 남으면(remaining<=1) 더 쪼개지 않고 나머지를 전부 담는다.
    """
    if not order:
        return []
    if g <= 1:
        return [list(order)]
    total = sum(qsize[i][1] for i in order) + gap * (len(order) - 1)
    tallest = max(qsize[i][1] for i in order)
    target = max(tallest, -(-total // g))   # ceil(total/g), 단 위젯 1개 높이는 보장
    columns = []
    cur = []
    cur_h = 0
    for i in order:
        hi = qsize[i][1]
        add = hi if not cur else hi + gap
        remaining = g - len(columns)        # 아직 새로 열 수 있는 컬럼 수
        if cur and cur_h + add > target and remaining > 1:
            columns.append(cur)
            cur = []
            cur_h = 0
            add = hi
        cur.append(i)
        cur_h += add
    if cur:
        columns.append(cur)
    return columns


def _pack_columns(items, qsize, columns, gap,
                  band_near, band_far, is_bottom,
                  col_near, col_far, is_right, snap,
                  scr_l, scr_t, scr_r, scr_b):
    """컬럼 묶음을 실제 좌표로 배치. 반환: (coords, clamped, bbox)."""
    coords = [None] * len(items)
    clamped = 0
    bxmin = bymin = bxmax = bymax = None

    if is_right:
        x_cursor = _snap_not_past_right(col_near, snap)   # 컬럼 우측 변 시작
    else:
        x_cursor = round(col_near / snap) * snap           # 컬럼 좌측 변 시작

    for col in columns:
        wc = max(qsize[i][0] for i in col)                 # 컬럼 폭(양자화 최대폭)

        # --- 컬럼 X 확정 + 가로 화면 클램프(겹침 집계: Critical 2) ---
        if is_right:
            cx = _right_aligned_grid_x(x_cursor, wc, snap)
            if cx < col_far:                               # 화면 왼쪽 초과
                cx = col_far
                clamped += len(col)                        # 가로 과밀 → 컬럼 멤버 전부 집계
            col_right = cx + wc
            next_cursor = cx - gap
        else:
            cx = round(x_cursor / snap) * snap
            if cx + wc > col_far:                          # 화면 오른쪽 초과
                cx = max(scr_l, col_far - wc)
                clamped += len(col)
            col_right = cx + wc
            next_cursor = cx + wc + gap

        # --- 컬럼 내부 세로 적층 ---
        if is_bottom:
            y_cursor = band_near                           # 바닥선에서 위로
            for i in col:
                w, h = items[i]                            # 좌표는 실제 크기로
                ty = y_cursor - h
                if ty < band_far:                          # 세로 밴드 초과 → 화면 안 강제
                    ty = band_far
                    clamped += 1
                wx = _right_aligned_grid_x(col_right, w, snap) if is_right else cx
                wy = round(ty / snap) * snap
                coords[i] = (wx, wy)
                y_cursor = ty - gap
        else:
            y_cursor = band_near                           # top선에서 아래로
            for i in col:
                w, h = items[i]
                ty = y_cursor
                if ty + h > band_far:                      # 세로 밴드 초과 → 화면 안 강제
                    ty = band_far - h
                    clamped += 1
                wx = _right_aligned_grid_x(col_right, w, snap) if is_right else cx
                wy = round(ty / snap) * snap
                coords[i] = (wx, wy)
                y_cursor = ty + h + gap

        # bbox 누적(점수용, 실제 크기 기준)
        for i in col:
            x0, y0 = coords[i]
            x1, y1 = x0 + items[i][0], y0 + items[i][1]
            bxmin = x0 if bxmin is None else min(bxmin, x0)
            bymin = y0 if bymin is None else min(bymin, y0)
            bxmax = x1 if bxmax is None else max(bxmax, x1)
            bymax = y1 if bymax is None else max(bymax, y1)

        x_cursor = next_cursor

    return coords, clamped, (bxmin, bymin, bxmax, bymax)


def _hard_violation(coords, items, cal, scr, clamped):
    """하드 제약 위반 검사. 위반 종류 문자열 또는 None.

    clamped>0(공간 부족으로 화면 안 강제 배치됨)일 때는 의도적 겹침이 허용되므로
    '상호 겹침' 검사를 면제하고, 캘린더 교차·화면 이탈만 본다.
    """
    rects = [(coords[i][0], coords[i][1],
              coords[i][0] + items[i][0], coords[i][1] + items[i][1])
             for i in range(len(items)) if coords[i] is not None]
    if clamped == 0:
        for a in range(len(rects)):
            for b in range(a + 1, len(rects)):
                if _overlap(rects[a], rects[b]):
                    return "mutual"
    for r in rects:
        if _overlap(r, cal):
            return "calendar"
    sl, st, sr, sb = scr
    for (x1, y1, x2, y2) in rects:
        # 경계 접촉 허용(엄격 부등호): x2==sr 은 화면 내로 본다 (cal_r==scr_r 케이스).
        if x1 < sl or y1 < st or x2 > sr or y2 > sb:
            return "offscreen"
    return None


def _score(bbox, items, clamped, g, violated):
    """후보 점수. 사전식 최소화. (유효성, 클램프수, 긴변, 면적, 빈틈, 컬럼수)

    클램프(겹침 강제)가 컴팩트 지표보다 앞: 사용자 #1 불만이 '겹침'이므로
    겹침 없는 후보가 더 길쭉해도 항상 우선한다. 겹침이 bbox를 쪼그라뜨려
    longside/waste 점수를 거짓으로 좋게 만드는 함정을 차단한다(TDD로 발견·수정).
    클램프 동률일 때만 longside(긴 변)로 멀티컬럼(컴팩트)을 고른다. (Critical 1 수정)
    """
    if violated is not None:
        return (1, 0, 0, 0, 0, 0)              # 위반 후보는 항상 유효(0)보다 나쁨
    bxmin, bymin, bxmax, bymax = bbox
    bw = bxmax - bxmin
    bh = bymax - bymin
    longside = max(bw, bh)
    area = bw * bh
    used = sum(w * h for (w, h) in items)
    waste = area - used
    return (0, clamped, longside, area, waste, g)


def _compute_arrange_layout(items, cal, scr, position, snap):
    """플로팅 위젯 배치 좌표 순수 계산. Qt/DB 없음.

    items: [(w,h),...] (호출부 수집순). cal/scr: (left,top,right,bottom).
    position: 4모서리. snap: 5mm 픽셀.
    반환: (coords[(x,y),...] items와 1:1, clamped_count).
    clamped_count: 공간 부족으로 화면 안에 강제 배치되어 겹쳤을 수 있는 위젯 수.
    """
    if not items:
        return [], 0

    gap = snap
    is_right = "right" in position
    is_bottom = "bottom" in position
    cal_l, cal_t, cal_r, cal_b = cal
    scr_l, scr_t, scr_r, scr_b = scr
    n = len(items)

    # 1. 양자화: 패킹 계산용 치수를 snap 배수로 올림(분리 격자 보존). 좌표는 실제 크기 사용.
    def qceil(v):
        return ((v + snap - 1) // snap) * snap
    qsize = [(qceil(w), qceil(h)) for (w, h) in items]

    # 2. 밴드/컬럼 방향
    if is_bottom:
        band_near, band_far = cal_t - gap, scr_t + gap
    else:
        band_near, band_far = cal_b + gap, scr_b - gap
    if is_right:
        col_near, col_far = cal_r, scr_l + gap
    else:
        col_near, col_far = cal_l, scr_r - gap

    # 3. 결정적 후보 정렬키 (모든 키에 index i tie-break)
    base = list(range(n))
    orders = {
        "type_group": list(base),                                       # 입력순(타입 그룹)
        "height_desc": sorted(base, key=lambda i: (-qsize[i][1], i)),
        "width_desc":  sorted(base, key=lambda i: (-qsize[i][0], i)),
        "area_desc":   sorted(base, key=lambda i: (-(qsize[i][0] * qsize[i][1]), i)),
    }
    order_names = ("type_group", "height_desc", "width_desc", "area_desc")
    # G(컬럼 수 상한) 후보. N_CAP은 정상 상한(16)에선 발동하지 않는 방어 가드(아래 참고).
    N_CAP = 16
    g_cands = (1, 2, 3) if n <= N_CAP else (1, 2)

    # 4. 후보 생성 → 점수화 → 최선 선택
    best = None        # (key, coords, clamped)
    safe = None        # 증명 가능한 무위반 안전 후보 (G=1 type_group)
    cand_seq = 0
    for oname in order_names:
        for g in g_cands:
            cols = _split_into_columns(orders[oname], qsize, g, gap)
            coords, clamped, bbox = _pack_columns(
                items, qsize, cols, gap,
                band_near, band_far, is_bottom,
                col_near, col_far, is_right, snap,
                scr_l, scr_t, scr_r, scr_b)
            violated = _hard_violation(coords, items, cal, scr, clamped)
            key = (_score(bbox, items, clamped, g, violated), cand_seq)
            if best is None or key < best[0]:
                best = (key, coords, clamped)
            if oname == "type_group" and g == 1 and violated is None and safe is None:
                safe = (coords, clamped)
            cand_seq += 1

    coords, clamped = best[1], best[2]

    # 5. 최종 게이트: 선택안이 (정상 입력인데) 위반이면 안전 후보로 폴백
    if safe is not None and _hard_violation(coords, items, cal, scr, clamped) is not None:
        coords, clamped = safe

    return coords, clamped
```

**`N_CAP` 가드 참고(Minor)**: 정상 위젯 상한이 정확히 16(D-Day5+집중1+스티키10)이라 `n > 16` 분기는 `enforce_widget_limits()`가 막아 실제로는 도달하지 않는 방어 코드다. 제거하지 말되, 죽은 분기에 가깝다는 점을 인지하라.

---

## 5. 비겹침 보장 (3중 방어)

1. **구조적 분리**: 같은 컬럼 내 위젯은 `y_cursor`가 `h+gap`씩 단조 이동 → 세로 서로소. 다른 컬럼은 `x_cursor`가 `wc+gap`씩 단조 이동 → 가로 서로소. AABB는 한 축만 서로소면 비겹침.
2. **양자화**: 컬럼 폭·세로 누적을 `qceil`(snap 배수)로 계산하고 `gap=snap`(1격자)을 항상 더하므로, 좌표를 snap 격자로 다시 당겨도 인접 간극이 최소 1격자 남는다(폭 다른 위젯의 floor 스냅이 분리를 깨는 급소 봉합).
3. **사후검증 + 폴백**: 반환 직전 `_hard_violation`이 전체 쌍 AABB(O(n²)) + 캘린더 + 화면을 재검사. 정상 입력에선 G=1 type_group 후보가 자명히 무위반(단일 컬럼은 컬럼 간 상호작용 없이 세로 단조 분리, 동일 정렬이라 스냅도 균일)이므로, 위반 시 이 안전 후보로 폴백해 **정상 입력 0겹침을 사후 보장**한다. 과밀(`clamped>0`)에서만 상호겹침을 면제하되 모든 위젯은 화면 안에 남는다.

---

## 6. Worked Example (집중 위젯 포함 — Important 4 반영)

**입력**(bottom-right, snap=19, 충분히 큰 화면): D-Day 4개(220×95) + 집중 1개(241×78) + 스티키 1개(220×209). 수집순 = `[d,d,d,d, focus, sticky]` = `type_group`.

- 양자화: 높이 `95→95`, `78→95`, `209→209` (95·209는 19의 배수). 폭 `220→228`, `241→247`.
- G=1: 단일 열. bbox ≈ 247(폭) × (95×5 + 78 + gap×5 = 762). **longside = 762**.
- G=2: `_split_into_columns` target = max(209, ceil(779/2)=390) = 390 → `[[d,d,d],[d,focus,sticky]]`. 실제 높이 col1 = 95×3 + gap×2 = 323, col2 = 95 + gap + 78 + gap + 209 = 420. bbox ≈ 494(폭) × 420. **longside = 494**.
- 모든 후보가 clamped=0(동률)이므로 2순위 longside가 결정: 494 < 762 → **G=2 선택**. D-Day가 세로로 묶이고 집중·스티키가 옆 열에 정렬되어 사용자 멘탈모델대로 배치된다. (G=3은 폭이 더 늘어 longside↑ → 탈락.)

"여러 경우의 수"는 후보 12종(정렬키 4 × G 3)을 실제 생성·비교하는 구조 자체로 충족된다.

---

## 7. 복잡도 / 결정성

- 후보 ≤ 12, 후보당 `O(n)` 배치 + `O(n²)` 검증 → 전체 `O(n²)`. 실사용 n≤16이라 최악 ≈ 12×256 AABB = 밀리초 미만(버튼 1회 호출).
- 결정성: `Date`/`random` 없음, 모든 정렬키에 `i` tie-break, 후보 동점은 `cand_seq` tie-break, 폴백도 단일 결정 후보. → 같은 입력 항상 같은 출력.

---

## 8. 구현 태스크 (TDD)

각 태스크는 `tests/test_ui.py`에 테스트 추가 → 실패 확인 → `ui_main.py` 구현 → 통과 확인 순. 모든 신규 순수함수(`_overlap`, `_split_into_columns`, `_pack_columns`, `_hard_violation`, `_score`, `_compute_arrange_layout`)는 `tests/test_ui.py` 임포트 블록(line 22~)에 추가한다.

### Task 1 — 보조 순수함수 `_overlap`, `_hard_violation`

**Files:** `ui_main.py`(line 70 위, `_clamp_window_pos` 다음), `tests/test_ui.py`.

- [ ] **1-1** 임포트에 `_overlap`, `_hard_violation` 추가(아직 없음 → ImportError로 실패).
- [ ] **1-2** 테스트 작성:
```python
def test_overlap_strict_boundary_touch_is_not_overlap():
    assert ui_main._overlap((0, 0, 10, 10), (5, 5, 15, 15)) is True
    assert ui_main._overlap((0, 0, 10, 10), (10, 0, 20, 10)) is False   # 변 공유
    assert ui_main._overlap((0, 0, 10, 10), (10, 10, 20, 20)) is False  # 꼭짓점 접촉

def test_hard_violation_detects_each_kind():
    cal = (100, 100, 200, 200)
    scr = (0, 0, 300, 300)
    # 정상(겹침 없음, 화면 내, 캘린더 밖)
    coords = [(0, 0), (0, 50)]
    items = [(40, 40), (40, 40)]
    assert ui_main._hard_violation(coords, items, cal, scr, 0) is None
    # 상호 겹침 (clamped==0일 때만 검사)
    assert ui_main._hard_violation([(0, 0), (10, 10)], [(40, 40), (40, 40)], cal, scr, 0) == "mutual"
    # clamped>0이면 상호 겹침 면제
    assert ui_main._hard_violation([(0, 0), (10, 10)], [(40, 40), (40, 40)], cal, scr, 1) is None
    # 캘린더 겹침
    assert ui_main._hard_violation([(120, 120)], [(40, 40)], cal, scr, 0) == "calendar"
    # 화면 이탈
    assert ui_main._hard_violation([(280, 0)], [(40, 40)], cal, scr, 0) == "offscreen"
    # 경계 접촉은 허용 (x+w == scr_r)
    assert ui_main._hard_violation([(260, 0)], [(40, 40)], cal, scr, 0) is None
```
- [ ] **1-3** 실패 확인 → **1-4** `_overlap`, `_hard_violation` 구현(§4 코드) → **1-5** 통과 확인.

### Task 2 — `_split_into_columns`

**Files:** `ui_main.py`, `tests/test_ui.py`.

- [ ] **2-1** 임포트 추가. **2-2** 테스트:
```python
def test_split_into_columns_g1_single_column():
    qsize = [(220, 95)] * 5
    cols = ui_main._split_into_columns(list(range(5)), qsize, 1, 19)
    assert cols == [[0, 1, 2, 3, 4]]

def test_split_into_columns_at_most_g_columns_contiguous():
    qsize = [(220, 95)] * 5
    cols = ui_main._split_into_columns(list(range(5)), qsize, 2, 19)
    assert len(cols) <= 2
    # 연속(순서 보존) 분할
    flat = [i for c in cols for i in c]
    assert flat == [0, 1, 2, 3, 4]
    # 균형: 5개 D-Day(각 95) → [2,3] 또는 [3,2]
    assert sorted(len(c) for c in cols) == [2, 3]

def test_split_into_columns_worked_example_g2():
    # [d,d,d,d, focus, sticky] (집중 포함). qsize 높이: 95,95,95,95,95,209
    qsize = [(228, 95), (228, 95), (228, 95), (228, 95), (247, 95), (228, 209)]
    cols = ui_main._split_into_columns(list(range(6)), qsize, 2, 19)
    assert len(cols) == 2
    assert cols[0] == [0, 1, 2]          # D-Day 3개
    assert cols[1] == [3, 4, 5]          # D-Day1 + 집중 + 스티키
```
- [ ] **2-3** 실패 → **2-4** 구현 → **2-5** 통과.

### Task 3 — `_pack_columns`, `_score`, `_compute_arrange_layout` 재작성

**Files:** `ui_main.py`(line 70~166 `_compute_arrange_layout` 전체 교체 + 위 보조함수들 추가), `tests/test_ui.py`.

- [ ] **3-1** 임포트에 `_pack_columns`, `_score` 추가.
- [ ] **3-2** 핵심 불변식 테스트(정상 입력 비겹침·화면내·캘린더 회피·결정성):
```python
_NORMAL_ITEMS = [(220, 95), (220, 95), (220, 95), (220, 95), (241, 78), (220, 209)]
_POSITIONS = ["bottom-right", "bottom-left", "top-right", "top-left"]

def _rects(coords, items):
    return [(x, y, x + w, y + h) for (x, y), (w, h) in zip(coords, items)]

def test_arrange_layout_no_mutual_overlap_all_corners():
    scr = (0, 0, 1920, 1080)
    cal = {"bottom-right": (1540, 420, 1920, 1080),
           "bottom-left":  (0, 420, 380, 1080),
           "top-right":    (1540, 0, 1920, 660),
           "top-left":     (0, 0, 380, 660)}
    for pos in _POSITIONS:
        coords, clamped = ui_main._compute_arrange_layout(_NORMAL_ITEMS, cal[pos], scr, pos, 19)
        assert clamped == 0, f"{pos}: 정상 입력인데 clamped>0"
        rs = _rects(coords, items=_NORMAL_ITEMS)
        for a in range(len(rs)):
            for b in range(a + 1, len(rs)):
                assert not ui_main._overlap(rs[a], rs[b]), f"{pos}: 위젯 {a}/{b} 겹침"

def test_arrange_layout_within_screen_and_clear_of_calendar_all_corners():
    scr = (0, 0, 1920, 1080)
    cal = {"bottom-right": (1540, 420, 1920, 1080),
           "bottom-left":  (0, 420, 380, 1080),
           "top-right":    (1540, 0, 1920, 660),
           "top-left":     (0, 0, 380, 660)}
    for pos in _POSITIONS:
        coords, _ = ui_main._compute_arrange_layout(_NORMAL_ITEMS, cal[pos], scr, pos, 19)
        for (x1, y1, x2, y2) in _rects(coords, _NORMAL_ITEMS):
            assert x1 >= scr[0] and y1 >= scr[1] and x2 <= scr[2] and y2 <= scr[3]
            assert not ui_main._overlap((x1, y1, x2, y2), cal[pos])

def test_arrange_layout_deterministic():
    scr, cal = (0, 0, 1920, 1080), (1540, 420, 1920, 1080)
    r1 = ui_main._compute_arrange_layout(_NORMAL_ITEMS, cal, scr, "bottom-right", 19)
    r2 = ui_main._compute_arrange_layout(_NORMAL_ITEMS, cal, scr, "bottom-right", 19)
    assert r1 == r2

def test_arrange_layout_snap_grid_alignment():
    scr, cal = (0, 0, 1920, 1080), (1540, 420, 1920, 1080)
    coords, _ = ui_main._compute_arrange_layout(_NORMAL_ITEMS, cal, scr, "bottom-right", 19)
    for (x, y) in coords:
        assert x % 19 == 0 and y % 19 == 0
```
- [ ] **3-3** 실패 확인 → **3-4** `_pack_columns`/`_score` 추가 + `_compute_arrange_layout` 교체(§4) → **3-5** 통과 확인.

### Task 4 — 효율(멀티컬럼) 테스트 — 사용자 요구 검증

**Files:** `tests/test_ui.py`.

- [ ] **4-1** 테스트:
```python
def test_arrange_layout_prefers_multicolumn_for_mixed_sizes():
    """D-Day 다수 + 긴 스티키 → 단일 열보다 멀티컬럼(컴팩트)을 선택한다."""
    scr, cal = (0, 0, 1920, 1080), (1540, 420, 1920, 1080)
    coords, clamped = ui_main._compute_arrange_layout(_NORMAL_ITEMS, cal, scr, "bottom-right", 19)
    assert clamped == 0
    rs = _rects(coords, _NORMAL_ITEMS)
    bw = max(r[2] for r in rs) - min(r[0] for r in rs)
    bh = max(r[3] for r in rs) - min(r[1] for r in rs)
    # 멀티컬럼: bbox 폭이 가장 넓은 단일 위젯(241)보다 크다.
    assert bw > 241, "단일 열로 배치됨 — 멀티컬럼 실패"
    # 단일 열 대비 세로가 짧다: 모든 높이 합(naive 단일열)보다 작다.
    naive_h = sum(h for (_, h) in _NORMAL_ITEMS) + 19 * (len(_NORMAL_ITEMS) - 1)
    assert bh < naive_h
```
- [ ] **4-2** 실패하지 않고 바로 통과해야 함(Task 3에서 이미 longside 점수로 멀티컬럼 선택). 통과 확인.

### Task 5 — 기존 테스트 갱신 + 보존 테스트 실제 실행 (Important 5)

**Files:** `tests/test_ui.py`.

- [ ] **5-1** `test_arrange_layout_vertical_overflow_clamped`(line 1265) **재정의**: 현 `clamped == 2` 절대값은 행-major 가정이라 컬럼-major에서 깨진다. 계약을 "공간 부족 시 화면 안 강제 배치되고 그 수가 보고된다"로 바꾼다:
```python
def test_arrange_layout_vertical_overflow_clamped():
    """가용 공간이 위젯 총량보다 작으면 clamped>0, 그래도 모두 화면 안."""
    items = [(220, 95)] * 12          # 좁은 화면에 과다
    scr = (0, 0, 400, 300)
    cal = (200, 200, 400, 300)
    coords, clamped = ui_main._compute_arrange_layout(items, cal, scr, "bottom-right", 19)
    assert clamped > 0
    for (x1, y1, x2, y2) in _rects(coords, items):
        assert x1 >= scr[0] and y1 >= scr[1] and x2 <= scr[2] and y2 <= scr[3]
```
- [ ] **5-2** 유지 테스트가 새 본체에서 실제 통과하는지 **명시적 실행**:
```
python -m pytest tests/test_ui.py::test_arrange_layout_empty_returns_empty tests/test_ui.py::test_arrange_layout_all_within_screen tests/test_ui.py::test_arrange_layout_no_overlap_with_calendar tests/test_ui.py::test_arrange_layout_four_positions_direction tests/test_ui.py::test_right_arrange_snap_does_not_reduce_calendar_margin tests/test_ui.py::test_right_arrange_snap_preserves_negative_monitor_margin -v
```
기대: 6개 PASS. 만약 `test_arrange_layout_all_within_screen`/`test_arrange_layout_no_overlap_with_calendar`/`test_arrange_layout_four_positions_direction`이 입력 구조 차이로 실패하면, **단언 의미는 유지**하되(화면내/캘린더비겹침/방향) 새 알고리즘에 맞게 입력만 조정하라(겹침 0·화면내·방향 계약은 반드시 통과해야 하는 불변식이다).
- [ ] **5-3** 경계 케이스 추가(`cal_r == scr_r`):
```python
def test_arrange_layout_calendar_right_edge_at_screen_edge():
    scr = (0, 0, 1920, 1080)
    cal = (1540, 420, 1920, 1080)   # cal_r == scr_r
    coords, clamped = ui_main._compute_arrange_layout(_NORMAL_ITEMS, cal, scr, "bottom-right", 19)
    assert clamped == 0
    for (x1, y1, x2, y2) in _rects(coords, _NORMAL_ITEMS):
        assert x2 <= 1920                      # 우측 화면 끝 침범 없음
        assert not ui_main._overlap((x1, y1, x2, y2), cal)
```

### Task 6 — 호출부 무수정 확인 + 전체 회귀

**Files:** `ui_main.py`(`_on_arrange_sticky_notes` 검토만, line 2344~).

- [ ] **6-1** `_on_arrange_sticky_notes`가 `_compute_arrange_layout(items, cal, scr_tuple, pos, snap)`을 그대로 호출하고 `clamped > 0`일 때 `InfoBar.warning`을 띄우는지 확인. 시그니처가 불변이므로 **수정 불필요**. (clamped 의미는 "겹쳤을 수 있는 위젯 수"로 일관 — 가로/세로 과밀 모두 집계되므로 경고가 실제 겹침과 일치.) 문구는 기존 유지.
- [ ] **6-2** 전체 테스트:
```
python -m pytest tests -q
```
기대: 전부 PASS(기존 319 + 신규). 실패 0.

---

## 9. 자체 검토 (스펙 커버리지)

- [x] **겹침 제거(핵심 불만)** → 구조적 분리 + 양자화 + 사후검증/폴백 (Task 1·3, §5)
- [x] **D-Day 세로 다열 ↔ 스티키 매칭** → `_split_into_columns` + longside 점수 (Task 2·3·4, §6)
- [x] **여러 경우의 수** → 후보 12종 생성·점수 비교 (Task 3)
- [x] **Critical 1(area→longside)** → `_score` 1순위 longside (§4)
- [x] **Critical 2(가로 클램프 집계)** → `_pack_columns` 가로 클램프 `clamped += len(col)` (§4)
- [x] **Important 3(이중 클램프 제거)** → 안전망 제거, band/screen 경계 일치 (§4)
- [x] **Important 4(집중 위젯 포함)** → worked example·테스트에 (241,78) 포함 (§6, Task 2·3·4)
- [x] **Important 5(보존 테스트 실제 실행)** → Task 5-2, 경계 테스트 5-3
- [x] **5mm snap·우측여백·음수모니터** → `_snap_not_past_right`/`_right_aligned_grid_x` 재사용, 기존 스냅 테스트 유지
- [x] **결정성** → tie-break(i, cand_seq), Date/random 없음 (Task 3 결정성 테스트)
- [x] **DB·데이터 보존·호출부 무수정** → 시그니처 불변 (Task 6)
- [x] **large 스케일 no-op** → 수집 결과 비면 기존 InfoBar.info 경로(호출부, 변경 없음)
- [x] **Minor: N_CAP 가드 문서화** (§4 참고), **InfoBar 문구 일관**(Task 6-1)
```
