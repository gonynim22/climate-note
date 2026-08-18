# 스티키 노트 휴지통/복구 기능 설계

- 작성일: 2026-06-03
- 대상 앱: 기후노트 (MyDesktopCalendar) v2.91 → (기능 추가)
- 스키마: v12 → **v13**

## 1. 배경 / 문제

현재 스티키 노트는 닫기(X) 시 확인 팝업을 거쳐 `db.delete_sticky_note()`가
`DELETE FROM sticky_notes`로 **즉시 영구 삭제(hard delete)**한다. 복구 수단이 없어
실수로 닫으면 되돌릴 수 없다. (`AGENTS.md` "삭제 정책"에 미구현으로 명시됨.)

## 2. 목표

- 닫기를 **휴지통 이동(soft-delete)**으로 바꿔 실수 삭제를 되돌릴 수 있게 한다.
- 우측 더보기 메뉴(`자동정렬 / 앱 업데이트 / 설정`)에 **휴지통** 진입점을 추가한다.
- 휴지통에서 노트를 **삭제 당시 위치/크기 그대로 복구**하거나 **영구 삭제**할 수 있다.
- 기존 사용자 데이터는 보존한다(데이터보존 철칙: `ALTER TABLE ADD COLUMN`만 사용).

## 3. 사용자 결정 사항 (확정)

| 항목 | 결정 |
|---|---|
| 닫기 동작 | 닫기 = 휴지통으로 이동 (soft-delete) |
| 보관 정책 | **최대 개수 제한** — 휴지통이 `STICKY_TRASH_LIMIT = 50`개를 초과하면 오래된 것부터 자동 영구삭제 |
| PIN 보호 | 영구삭제/휴지통 비우기는 **확인 팝업만**(PIN 불필요). 복구도 무인증 |
| 복구 위치 | 삭제 당시 `x_pos/y_pos/width/height/color` 그대로 복원 |
| 백업(Export) | 휴지통 항목 **포함**. Import 시 휴지통 상태까지 왕복 보존 |
| 메뉴 위치 | `자동정렬 / 앱 업데이트 / [휴지통] / 설정` — **설정 위** |

## 4. 접근법 결정

**채택: 같은 테이블 soft-delete (Approach A)**

`sticky_notes`에 `is_deleted`, `deleted_at` 컬럼을 추가하고 닫기 시 플래그만 변경한다.

- 마이그레이션이 `ALTER TABLE ADD COLUMN` 2줄로 끝나 데이터보존 철칙에 부합.
- 위치/크기/색/내용이 행에 그대로 남아 "원위치 복구"가 자동으로 성립.
- 복구/영구삭제 로직이 단순.
- 비용: `sticky_notes`를 읽는 쿼리에 `is_deleted=0` 필터 추가 필요(영향처는 `get_open_sticky_notes` 1곳, export는 의도적으로 전체 포함).

기각: 별도 `sticky_notes_trash` 테이블(Approach B) — 두 테이블 간 이동 트랜잭션과
id 재발급 처리로 코드량과 버그 표면이 커지고, 복구 시 id가 바뀌어 추적이 복잡.

## 5. 상세 설계

### 5.1 데이터 계층 — `database.py`

**마이그레이션 v12 → v13** (`migrate()`에 `if version == 12:` 블록 추가, 멱등성 유지):

```sql
ALTER TABLE sticky_notes ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sticky_notes ADD COLUMN deleted_at TEXT NOT NULL DEFAULT '';
PRAGMA user_version = 13;
```

> 멱등성: 새 컬럼은 신규 추가이므로 버전 가드(`version == 12`)만으로 1회 실행 보장.
> 재실행 시 `user_version`이 13이라 블록을 건너뜀. 기존 v0 초기 생성 블록은
> 그대로 두되, 신규 설치도 migrate 체인으로 v13까지 도달하도록 한다.
> (v0 블록은 `user_version=8`로 점프 후 8→9→…→13 순차 적용됨.)

**상수**: `STICKY_TRASH_LIMIT = 50` (모듈 상단 설정 상수 영역).

**신규/변경 함수:**

| 함수 | 동작 |
|---|---|
| `trash_sticky_note(note_id)` | `UPDATE ... SET is_deleted=1, deleted_at=<now>, is_open=0`. 커밋 전 동일 커넥션에서 `_enforce_trash_cap(conn)` 호출 |
| `get_trashed_sticky_notes()` | `SELECT * WHERE is_deleted=1 ORDER BY deleted_at DESC`. content는 `_safe_decrypt`로 복호화하여 반환(미리보기용) |
| `restore_sticky_note(note_id)` | `UPDATE ... SET is_deleted=0, is_open=1, deleted_at=''` |
| `purge_sticky_note(note_id)` | 실제 `DELETE FROM sticky_notes WHERE id=?` — 기존 `delete_sticky_note`를 이 이름으로 개명 |
| `empty_sticky_trash()` | `DELETE FROM sticky_notes WHERE is_deleted=1` |
| `_enforce_trash_cap(conn)` | 휴지통 개수 > `STICKY_TRASH_LIMIT`이면 `deleted_at` 오름차순(가장 오래된 것)부터 초과분 `DELETE`. 삭제 건수를 `_logger.info`로 기록(무음 삭제 금지, CODEMIND 0023) |

**기존 함수 변경:**

- `delete_sticky_note(note_id)` → **`purge_sticky_note(note_id)`로 개명**. 현재 호출처는 2곳:
  - `ui_sticky.py:545 _on_close()` → `trash_sticky_note`로 전환(영구삭제 아님).
  - `tests/test_database.py:371` → 새 soft-delete 동작에 맞게 갱신(아래 8절 참조).
  개명 후 `purge_sticky_note`의 직접 호출처는 휴지통 UI의 "영구 삭제"/"비우기"와 테스트만 남는다.
- `get_open_sticky_notes()` 쿼리에 `AND is_deleted = 0` 추가(이중 안전장치;
  trashed 노트는 `is_open=0`이기도 함).

**Export/Import (백업) — 휴지통 포함:**

- `export_all_data()`의 `sticky_notes` dict에 두 필드 추가:
  ```python
  "is_deleted": row["is_deleted"],
  "deleted_at": row["deleted_at"],
  ```
  (`SELECT * FROM sticky_notes`는 이미 trashed 행까지 모두 반환하므로 쿼리 변경 불필요.)
- `import_all_data()`의 sticky INSERT에 두 컬럼 추가, 구버전 백업 하위호환을 위해 `.get()` 기본값 사용:
  ```python
  """INSERT INTO sticky_notes
     (type, content, x_pos, y_pos, width, height, is_open, is_pinned, color, is_deleted, deleted_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
  # ... n.get("is_deleted", 0), n.get("deleted_at", "")
  ```
  → 휴지통 상태(`is_deleted=1, is_open=0`)까지 그대로 복원되어 import 후에도 휴지통에 표시됨.
  구버전 백업(필드 없음)은 기본값(0, "")으로 일반 노트로 들어온다.

### 5.2 닫기 경로 — `ui_sticky.py`

`StickyNoteWindow._on_close()` (현 545행 부근):

- 확인 문구를 `"노트를 삭제하시겠습니까?"` → **`"노트를 휴지통으로 이동하시겠습니까?"`**로 변경,
  yes 버튼 텍스트는 `"휴지통으로"` 정도로.
- `db.delete_sticky_note(self.note_id)` → **`db.trash_sticky_note(self.note_id)`**.
- `note_closed.emit(self.note_id)` 및 창 닫기는 그대로(메인이 `_sticky_windows`에서 제거).

### 5.3 휴지통 창 — 신규 `ui_trash.py`

`ui_search.py`의 Notion 스타일 `QTableWidget` 패턴(PySide6 + qfluentwidgets) 재사용.

- 클래스: `StickyTrashWindow(QWidget)` 또는 `(QDialog)`. frameless 여부는 기존 보조 창 톤에 맞춤.
- 표 열: `[색상 스와치] [내용 미리보기] [삭제 시각]`
  - 내용 미리보기: HTML→plain 변환(`QTextDocument().setHtml(...).toPlainText()`) 후 첫 줄 ~40자.
  - 복호화 실패 시 `_safe_decrypt` fallback 문자열 그대로 노출.
  - 삭제 시각: `deleted_at` 표시(`YYYY-MM-DD HH:MM`).
- 버튼:
  - 행 선택 후 **복구**: `db.restore_sticky_note(id)` → 메인에 신호 → 노트 창 원위치 재생성 → 목록 갱신.
  - 행 선택 후 **영구 삭제**: 확인 팝업(`"이 노트를 영구히 삭제할까요? 되돌릴 수 없습니다."`) → `db.purge_sticky_note(id)` → 목록 갱신. PIN 없음.
  - **휴지통 비우기**: 확인 팝업 → `db.empty_sticky_trash()` → 목록 갱신. PIN 없음.
- 빈 상태: 표 대신/위에 `"휴지통이 비어 있습니다"` 안내 라벨.
- 자원 정리: 모든 MessageBox/팝업/이 창은 `deleteLater()` 또는 `WA_DeleteOnClose`
  (CODEMIND 0026_RESLEAK).
- 복구 신호 전달: `restore_requested = Signal(int)` 정의 → 메인에서 연결.

### 5.4 메뉴 진입점 — `ui_main.py`

`_build_more_menu()` (현 978행 부근), `앱 업데이트`와 `설정` 사이에 삽입:

```python
menu.addAction(fluent_icon("arrow_sort_color", size=24), "자동정렬", self._on_arrange_sticky_notes)
menu.addAction(fluent_icon("arrow_sync_color", size=24), "앱 업데이트", self._on_update_guide)
menu.addAction(fluent_icon("delete_color", size=24), "휴지통", self._on_open_trash)   # 신규
menu.addAction(fluent_icon("settings_color", size=24), "설정", self._on_settings)
```

- `_on_open_trash()`: `StickyTrashWindow` 생성/표시(단일 인스턴스 재사용, `_settings_window` 패턴 참고).
  `restore_requested` 신호를 `_restore_sticky_note(note_id)`에 연결.
- `_restore_sticky_note(note_id)`: `db.restore_sticky_note(note_id)` 후
  해당 노트 데이터를 읽어(`get_open_sticky_notes` 결과에서 매칭 또는 단건 조회)
  기존 `_load_open_sticky_notes`/`_on_new_sticky_note`의 `StickyNoteWindow` 생성 패턴으로
  **저장된 x_pos/y_pos/width/height/color로 창을 재생성**, `_sticky_windows[note_id]`에 등록.

### 5.5 아이콘 리소스

- `resources/fluent_icons/delete_color.svg` 추가.
  - 출처: 이미 번들·라이선스된 Fluent UI System Icons("Delete" 계열).
    `licenses/fluentui-system-icons.LICENSE` 적용 범위.
  - 색상 톤은 기존 `*_color.svg`들과 통일(컬러 SVG. `fluent_icon()`이 SVG를 그대로/틴팅).
  - `build.spec`이 `('resources', 'resources')`로 디렉터리 전체를 포함 → 빌드 추가작업 없음.

## 6. 데이터 흐름

```
[닫기 X] → 확인 팝업 → db.trash_sticky_note(id)
                         ├ is_deleted=1, deleted_at=now, is_open=0
                         └ _enforce_trash_cap: >50 이면 오래된 것 purge
        → note_closed → 메인이 _sticky_windows에서 창 제거

[메뉴 → 휴지통] → StickyTrashWindow
   ├ 복구 → restore_requested(id) → 메인: db.restore + 원위치 창 재생성
   ├ 영구삭제 → 확인 → db.purge_sticky_note(id)
   └ 비우기 → 확인 → db.empty_sticky_trash()

[Export] SELECT * (trashed 포함) → JSON(is_deleted/deleted_at 포함)
[Import] INSERT (is_deleted/deleted_at .get 기본값) → 휴지통 상태 왕복 복원
```

## 7. 에러 처리

- 미리보기 복호화 실패: `_safe_decrypt`가 `"[복호화 오류]"` 등 fallback 반환 → 표에 그대로 노출(예외 전파 금지).
- 복구 대상이 이미 열린 창과 충돌: 휴지통 항목은 `is_open=0`이라 열린 창이 없음 → 충돌 없음. 방어적으로 `_sticky_windows`에 이미 있으면 raise만.
- 복구 위치가 화면 밖(모니터 구성 변경): 1차 범위에서는 저장 좌표 그대로 사용. 화면 밖 클램프는 후속 과제(필요 시 기존 정렬 로직 재사용)로 남김.
- 예외 처리는 타입별 세분화(`OSError`/`ValueError`/`sqlite3.OperationalError` 등), `bare except` 금지, `except`+`pass` 단독 금지(로깅 필수) — CODEMIND 0023/0024.

## 8. 테스트 (필수, `tests/`)

데이터 변경 기능이므로 왕복 검증 필수(`AGENTS.md` 핵심 원칙).

`tests/test_database.py` (또는 신규 분리):
- **trash 왕복**: `create` → `trash` → 행 존재 & `is_deleted=1` & `deleted_at != ''` & content 복호화 일치.
- **restore 왕복**: trash → restore → `is_deleted=0` & `is_open=1` & 위치/크기/색/내용 보존.
- **purge**: 행 완전 제거.
- **empty**: 모든 trashed 제거, 라이브 노트는 유지.
- **cap**: 51개 trash → `_enforce_trash_cap`이 가장 오래된 1개 purge → 휴지통 50 유지, 가장 최신 50개가 남음.
- **get_open 제외**: trashed 노트는 `get_open_sticky_notes`에 안 나옴.
- **export 포함**: export JSON에 trashed sticky 포함 & `is_deleted/deleted_at` 필드 존재.
- **import 왕복**: trashed 포함 export → 새 DB import → 휴지통 상태 복원. 구버전 백업(필드 없음) import → 일반 노트로 들어옴(기본값).
- **마이그레이션 멱등성**: `migrate()` 2회 호출 → 컬럼 1회만 추가, 오류 없음.
- **기존 테스트 갱신**: `tests/test_database.py:371`의 `delete_sticky_note` 호출은
  `purge_sticky_note`(또는 새 trash→purge 흐름)로 갱신. 기존 "삭제 후 get_open에서 사라짐"
  단언은 trash 후 get_open 제외 + 휴지통 등장으로 의미 보정.

UI 테스트(`tests/test_ui_sticky.py` 또는 신규 `test_ui_trash.py`, pytest-qt):
- 닫기 → `trash_sticky_note` 호출(영구삭제 아님) 확인.
- 휴지통 창: 목록 렌더, 복구 신호 emit, 영구삭제/비우기 확인 팝업 경로.

## 9. 문서 갱신

- `AGENTS.md`
  - "삭제 정책" 항목: 휴지통/복구 **구현됨**으로 갱신(닫기=휴지통 이동, 한도 50, 복구 원위치, 백업 포함).
  - Module Map에 `ui_trash.py` 추가, `database.py` 줄에 스키마 **v13** 및 신규 함수 반영.
  - `ui_sticky.py` 줄에 닫기=휴지통 이동 반영.
- `docs/ARCHITECTURE.md`의 DB Schema 절에 `is_deleted/deleted_at` 및 v13 반영(존재 시).

## 10. 영향 범위 요약

| 파일 | 변경 |
|---|---|
| `database.py` | 마이그레이션 v13, 상수, trash/restore/purge/empty/get_trashed/_enforce_trash_cap, get_open 필터, export/import 2필드 |
| `ui_sticky.py` | `_on_close` 문구 + `trash_sticky_note` 호출 |
| `ui_trash.py` (신규) | 휴지통 창 UI |
| `ui_main.py` | 메뉴 항목 + `_on_open_trash` + `_restore_sticky_note` |
| `resources/fluent_icons/delete_color.svg` (신규) | 메뉴 아이콘 |
| `tests/...` | 왕복/캡/마이그레이션/UI 테스트 |
| `AGENTS.md`, `docs/ARCHITECTURE.md` | 문서 갱신 |

## 11. 비목표 (YAGNI)

- 일정(schedules)/D-Day/집중 모드 위젯의 휴지통은 범위 외(스티키 노트 한정).
- 휴지통 자동 보관 기간(N일) 정책은 채택 안 함(개수 제한만).
- 화면 밖 복구 좌표 클램프, 휴지통 검색/정렬 옵션은 후속 과제.
