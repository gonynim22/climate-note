# Sticky Note / Calendar Position Restore on Screen Change

**Date**: 2026-04-07
**Version**: v2.2 patch

## Overview

듀얼 모니터 환경에서 GPU 전환 등으로 화면 구성이 변경되면 스티키 노트, D-Day 위젯, 캘린더 창의 위치가 조금씩 어긋나는 문제를 해결한다. 화면 변경 감지 시 DB에 저장된 원래 좌표로 위치를 재적용한다.

---

## 1. 캘린더 위치 저장

### 파일

- `database.py` — 설정 키 상수 추가
- `ui_main.py` — `mouseReleaseEvent`, `_position_to_bottom_right`

### 변경 내용

- `database.py`에 설정 키 상수 추가: `SETTING_CALENDAR_X = "calendar_x"`, `SETTING_CALENDAR_Y = "calendar_y"`
- `ui_main.py` `MainCalendarWindow.mouseReleaseEvent`에서 드래그 종료 시 `db.save_setting()`으로 현재 좌표 저장
- 앱 시작 시 `__init__`에서 저장된 좌표가 있으면 해당 위치로 이동, 없으면 기존 `_position_to_bottom_right()` 호출

### 기존 데이터 보존

- `app_settings` key-value 테이블 활용, 스키마 변경 없음
- 기존에 `calendar_x`/`calendar_y` 키가 없으면 `get_setting()` 기본값 `""` 반환 → 기존 동작(우측 하단) 유지

---

## 2. 화면 변경 감지 및 위치 재적용

### 파일

- `ui_main.py` — `MainCalendarWindow.__init__`, 새 메서드 `_on_screen_geometry_changed`

### 변경 내용

#### 시그널 연결 (in `__init__`)

- `QApplication.instance().screenAdded.connect(self._on_screen_changed)`
- `QApplication.instance().screenRemoved.connect(self._on_screen_changed)`
- `QApplication.primaryScreen().geometryChanged.connect(self._on_screen_changed)`

#### `_on_screen_changed` 메서드

디바운스 타이머(500ms)를 사용하여 연속적인 화면 변경 이벤트를 하나로 처리:

1. **캘린더**: DB에서 `calendar_x`/`calendar_y` 읽어서 `move()`. 저장된 값이 없으면 `_position_to_bottom_right()`.
2. **스티키 노트**: 각 `StickyNoteWindow`에 대해 DB에서 `x_pos`/`y_pos` 읽어서 `move()`.
3. **D-Day 위젯**: 각 `DDayWidgetWindow`에 대해 DB에서 `x_pos`/`y_pos` 읽어서 `move()`.
4. **화면 밖 보정**: 이동 후 어떤 모니터의 `availableGeometry()`에도 포함되지 않으면, 가장 가까운 화면 안쪽으로 보정.

#### 화면 밖 보정 로직

```
for each window:
    pos = window.pos()
    if not any(screen.availableGeometry().contains(pos) for screen in QApplication.screens()):
        # 가장 가까운 화면의 availableGeometry 안쪽으로 clamp
        nearest_screen = find nearest screen by distance to pos
        geo = nearest_screen.availableGeometry()
        x = clamp(pos.x(), geo.left(), geo.right() - window.width())
        y = clamp(pos.y(), geo.top(), geo.bottom() - window.height())
        window.move(x, y)
        save updated position to DB
```

---

## 3. 변경하지 않는 것

- DB 스키마 (`app_settings` key-value 활용)
- 기존 드래그/스냅 로직
- 자동정렬 기능
- 스티키 노트/D-Day 위젯의 기존 위치 저장 메커니즘 (mouseReleaseEvent)

---

## 테스트 계획

- [ ] 캘린더 드래그 후 앱 재시작 → 저장된 위치에서 시작 확인
- [ ] 저장된 위치 없이 최초 실행 → 기존 우측 하단 배치 확인
- [ ] 화면 해상도 변경 후 → 캘린더/스티키 노트/D-Day 위젯 위치 복원 확인
- [ ] 창이 화면 밖에 놓이는 경우 → 화면 안쪽으로 보정 확인
