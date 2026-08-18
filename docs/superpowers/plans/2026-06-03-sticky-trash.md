# 스티키 노트 휴지통/복구 기능 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스티키 노트 닫기를 영구삭제 대신 휴지통 이동(soft-delete)으로 바꾸고, 우측 메뉴에 휴지통 창을 추가해 노트를 원위치로 복구하거나 영구삭제할 수 있게 한다.

**Architecture:** `sticky_notes` 테이블에 `is_deleted`/`deleted_at` 컬럼을 추가하는 soft-delete 방식(스키마 v12→v13). 닫기는 플래그만 변경하고, 별도 `ui_trash.py` 창에서 복구/영구삭제/비우기를 수행한다. 휴지통은 최대 50개로 제한해 초과 시 오래된 것부터 자동 영구삭제한다.

**Tech Stack:** Python 3.13, PySide6, qfluentwidgets, SQLite(`PRAGMA user_version` 마이그레이션), Fernet 암호화, pytest / pytest-qt.

**참고:** 이 프로젝트는 git 저장소가 아니다(`Is a git repository: false`). 따라서 각 Task 끝의 "커밋" 대신 **전체 테스트 통과 확인** 체크포인트를 둔다. git을 쓰려면 `git init` 후 각 Task 끝에 커밋하면 된다.

**관련 스펙:** [`docs/superpowers/specs/2026-06-03-sticky-trash-design.md`](../specs/2026-06-03-sticky-trash-design.md)

---

## File Structure

| 파일 | 책임 | 변경 |
|---|---|---|
| `database.py` | 마이그레이션 v13, trash/restore/purge/empty/get_trashed/_enforce_trash_cap, get_open 필터, export/import 2필드 | 수정 |
| `ui_sticky.py` | 닫기 시 확인 문구 + `trash_sticky_note` 호출 | 수정 (`_on_close`) |
| `ui_trash.py` | 휴지통 창 UI(목록·복구·영구삭제·비우기) | **신규** |
| `ui_main.py` | 더보기 메뉴에 "휴지통" 항목 + `_on_open_trash` + `_restore_sticky_note` | 수정 |
| `resources/fluent_icons/delete_color.svg` | 휴지통 메뉴 아이콘 | **신규** |
| `tests/test_database.py` | 마이그레이션·trash·export 테스트 + 기존 테스트 갱신 | 수정 |
| `tests/test_ui_sticky.py` | 닫기=휴지통 이동 테스트 | 수정 |
| `tests/test_ui_trash.py` | 휴지통 창 UI 테스트 | **신규** |
| `AGENTS.md`, `docs/ARCHITECTURE.md` | 문서 갱신 | 수정 |

각 Task는 독립적으로 테스트 가능하며, Task 1→8 순서로 진행한다(2는 1에, 3은 2에, 6·7은 2·5에 의존).

---

## Task 1: DB 마이그레이션 v12 → v13 (컬럼 추가)

**Files:**
- Modify: `database.py` (migrate() — 현재 v11 블록은 `database.py:379-411`, 그 뒤에 v12 블록 추가)
- Test: `tests/test_database.py` (TestMigration 클래스, `test_database.py:12-16` 갱신 + 신규 테스트)

- [ ] **Step 1: 기존 fresh-install 버전 테스트를 v13으로 갱신 (실패 유도)**

`tests/test_database.py:13-16`의 메서드를 아래로 교체:

```python
    def test_fresh_install_is_v13(self, app_dir):
        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 13
```

- [ ] **Step 2: 신규 마이그레이션 테스트 추가 (실패 유도)**

`tests/test_database.py`의 TestMigration 클래스 안(예: `test_v7_to_v8_adds_color_column` 아래)에 추가:

```python
    def test_fresh_has_trash_columns_in_sticky_notes(self, app_dir):
        with db._connection() as conn:
            cols = [c[1] for c in conn.execute("PRAGMA table_info(sticky_notes)").fetchall()]
        assert "is_deleted" in cols
        assert "deleted_at" in cols

    def test_v12_to_v13_adds_trash_columns(self, app_dir):
        """v12 DB를 시뮬레이션 후 migrate() 실행 시 휴지통 컬럼 추가"""
        with db._connection() as conn:
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN is_deleted")
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN deleted_at")
            conn.execute("PRAGMA user_version = 12")
            conn.commit()

        db.migrate()

        with db._connection() as conn:
            cols = [c[1] for c in conn.execute("PRAGMA table_info(sticky_notes)").fetchall()]
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert "is_deleted" in cols and "deleted_at" in cols
        assert version == 13

    def test_migrate_is_idempotent(self, app_dir):
        """migrate()를 두 번 호출해도 오류 없이 v13 유지"""
        db.migrate()
        db.migrate()
        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 13
```

> 참고: SQLite의 `ALTER TABLE DROP COLUMN`은 3.35+에서 지원된다(Python 3.13 동봉 SQLite는 충족). 시뮬레이션이 실패하면 대안으로 테이블 재생성 방식을 쓰되, 본 환경에서는 DROP COLUMN을 우선 사용한다.

- [ ] **Step 3: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_database.py::TestMigration -q`
Expected: FAIL — `test_fresh_install_is_v13`는 현재 v12라 실패, 신규 테스트는 컬럼 없음으로 실패.

- [ ] **Step 4: 마이그레이션 v12→v13 블록 추가**

`database.py`의 `migrate()` 안, v11 블록(`...version = 12` 끝, `database.py:411`) 바로 다음 줄, `# 암호화 키 마이그레이션` 주석(`database.py:413`) 앞에 삽입:

```python
        if version == 12:
            # 스티키 노트 휴지통(soft-delete) 컬럼 추가
            conn.execute(
                "ALTER TABLE sticky_notes ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0"
            )
            conn.execute(
                "ALTER TABLE sticky_notes ADD COLUMN deleted_at TEXT NOT NULL DEFAULT ''"
            )
            conn.execute("PRAGMA user_version = 13")
            conn.commit()
            version = 13
```

- [ ] **Step 5: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_database.py::TestMigration -q`
Expected: PASS (모든 마이그레이션 테스트 통과)

- [ ] **Step 6: 체크포인트 — DB 테스트 전체 통과 확인**

Run: `python -m pytest tests/test_database.py -q`
Expected: 기존 `test_delete`, `test_roundtrip`는 아직 통과(이번 단계에선 함수 미변경). 전부 PASS.

---

## Task 2: 휴지통 CRUD 함수 + get_open 필터 + delete→purge 개명

**Files:**
- Modify: `database.py` (상수 영역 `database.py:31` 부근, sticky CRUD `database.py:587-649`)
- Test: `tests/test_database.py` (TestStickyNoteCRUD `test_database.py:344-391`, `test_delete` 갱신)

- [ ] **Step 1: 휴지통 동작 테스트 작성 (실패 유도)**

`tests/test_database.py`의 `TestStickyNoteCRUD` 클래스에 추가하고, 기존 `test_delete`(`test_database.py:369-372`)를 아래 `test_purge`로 교체:

```python
    def test_purge(self, app_dir):
        nid = db.create_sticky_note()
        db.purge_sticky_note(nid)
        assert not any(n["id"] == nid for n in db.get_open_sticky_notes())
        assert not any(n["id"] == nid for n in db.get_trashed_sticky_notes())

    def test_trash_moves_to_trash_not_deleted(self, app_dir):
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, content="휴지통 갈 내용")
        db.trash_sticky_note(nid)
        # 열린 목록에서는 사라지고
        assert not any(n["id"] == nid for n in db.get_open_sticky_notes())
        # 휴지통에는 남으며 내용이 보존됨
        trashed = db.get_trashed_sticky_notes()
        match = next(t for t in trashed if t["id"] == nid)
        assert match["content"] == "휴지통 갈 내용"
        assert match["deleted_at"] != ""

    def test_restore_keeps_position_and_content(self, app_dir):
        nid = db.create_sticky_note("memo", 333, 444, "#D0FFF1")
        db.update_sticky_note(nid, content="복구될 내용", width=250, height=260)
        db.trash_sticky_note(nid)
        db.restore_sticky_note(nid)
        note = next(n for n in db.get_open_sticky_notes() if n["id"] == nid)
        assert note["content"] == "복구될 내용"
        assert note["x_pos"] == 333 and note["y_pos"] == 444
        assert note["width"] == 250 and note["height"] == 260
        assert note["color"] == "#D0FFF1"
        # 휴지통에서는 사라짐
        assert not any(t["id"] == nid for t in db.get_trashed_sticky_notes())

    def test_empty_trash_removes_all_trashed_only(self, app_dir):
        live = db.create_sticky_note()
        t1 = db.create_sticky_note()
        t2 = db.create_sticky_note()
        db.trash_sticky_note(t1)
        db.trash_sticky_note(t2)
        db.empty_sticky_trash()
        assert db.get_trashed_sticky_notes() == []
        # 라이브 노트는 유지
        assert any(n["id"] == live for n in db.get_open_sticky_notes())

    def test_trash_cap_purges_oldest(self, app_dir):
        ids = [db.create_sticky_note() for _ in range(db.STICKY_TRASH_LIMIT + 1)]
        for nid in ids:
            db.trash_sticky_note(nid)
        trashed = db.get_trashed_sticky_notes()
        assert len(trashed) == db.STICKY_TRASH_LIMIT
        # 가장 먼저(가장 오래) 휴지통에 들어간 노트가 자동 영구삭제됨
        trashed_ids = {t["id"] for t in trashed}
        assert ids[0] not in trashed_ids
        assert ids[-1] in trashed_ids

    def test_trashed_not_in_open_list(self, app_dir):
        nid = db.create_sticky_note()
        db.trash_sticky_note(nid)
        assert not any(n["id"] == nid for n in db.get_open_sticky_notes())
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_database.py::TestStickyNoteCRUD -q`
Expected: FAIL — `STICKY_TRASH_LIMIT`, `trash_sticky_note`, `restore_sticky_note`, `purge_sticky_note`, `empty_sticky_trash`, `get_trashed_sticky_notes` 미정의.

- [ ] **Step 3: 상수 추가**

`database.py:31` 부근(`DEFAULT_STICKY_COLOR` 정의 다음 줄)에 추가:

```python
STICKY_TRASH_LIMIT = 50  # 휴지통 최대 보관 개수(초과 시 오래된 것부터 자동 영구삭제)
```

- [ ] **Step 4: `get_open_sticky_notes` 쿼리에 휴지통 제외 필터 추가**

`database.py:591-592`의 쿼리를 변경:

```python
        rows = conn.execute(
            "SELECT * FROM sticky_notes WHERE is_open = 1 AND is_deleted = 0"
        ).fetchall()
```

- [ ] **Step 5: 기존 `delete_sticky_note`를 `purge_sticky_note`로 개명**

`database.py:645-649`를 아래로 교체(주석/이름만 변경, 동작은 동일한 hard delete):

```python
def purge_sticky_note(note_id: int) -> None:
    """스티키 노트 영구 삭제(되돌릴 수 없음). 휴지통 '영구 삭제'에서 호출."""
    with _connection() as conn:
        conn.execute("DELETE FROM sticky_notes WHERE id = ?", (note_id,))
        conn.commit()
```

- [ ] **Step 6: 휴지통 함수 추가**

`purge_sticky_note` 정의 바로 다음에 추가:

```python
def trash_sticky_note(note_id: int) -> None:
    """스티키 노트를 휴지통으로 이동(soft-delete). 닫기에서 호출."""
    with _connection() as conn:
        conn.execute(
            "UPDATE sticky_notes SET is_deleted = 1, deleted_at = ?, is_open = 0 WHERE id = ?",
            (_now_str(), note_id)
        )
        _enforce_trash_cap(conn)
        conn.commit()


def restore_sticky_note(note_id: int) -> None:
    """휴지통의 스티키 노트를 복구(원래 위치/내용 유지)."""
    with _connection() as conn:
        conn.execute(
            "UPDATE sticky_notes SET is_deleted = 0, is_open = 1, deleted_at = '' WHERE id = ?",
            (note_id,)
        )
        conn.commit()


def empty_sticky_trash() -> None:
    """휴지통의 모든 스티키 노트 영구 삭제."""
    with _connection() as conn:
        conn.execute("DELETE FROM sticky_notes WHERE is_deleted = 1")
        conn.commit()


def get_trashed_sticky_notes() -> list[dict]:
    """is_deleted=1인 스티키 노트 조회(최근 삭제순). 미리보기용 content 복호화."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sticky_notes WHERE is_deleted = 1 "
            "ORDER BY deleted_at DESC, id DESC"
        ).fetchall()
        return [{
            "id": row["id"],
            "content": _safe_decrypt(row["content"]),
            "color": row["color"] or DEFAULT_STICKY_COLOR,
            "deleted_at": row["deleted_at"],
        } for row in rows]


def _enforce_trash_cap(conn) -> None:
    """휴지통이 STICKY_TRASH_LIMIT를 넘으면 오래된 것부터 영구삭제(같은 커넥션 사용)."""
    count = conn.execute(
        "SELECT COUNT(*) FROM sticky_notes WHERE is_deleted = 1"
    ).fetchone()[0]
    excess = count - STICKY_TRASH_LIMIT
    if excess > 0:
        conn.execute(
            "DELETE FROM sticky_notes WHERE id IN ("
            "  SELECT id FROM sticky_notes WHERE is_deleted = 1"
            "  ORDER BY deleted_at ASC, id ASC LIMIT ?"
            ")",
            (excess,)
        )
        _logger.info(
            "휴지통 한도(%d) 초과로 오래된 스티키 노트 %d개 영구삭제",
            STICKY_TRASH_LIMIT, excess
        )
```

> `deleted_at`은 `"%Y-%m-%d %H:%M:%S"` 문자열이라 사전식 정렬이 곧 시간순이다. 동일 초에 묶이면 `id ASC`(먼저 생성된 것)로 tie-break → "가장 오래된 것"이 먼저 삭제된다.

- [ ] **Step 7: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_database.py::TestStickyNoteCRUD -q`
Expected: PASS (휴지통 6개 + 기존 CRUD 테스트 모두 통과)

- [ ] **Step 8: 체크포인트 — DB 테스트 전체 통과 확인**

Run: `python -m pytest tests/test_database.py -q`
Expected: `test_roundtrip`(export/import)은 Task 3 전이라 아직 통과(스티키 내용 보존). 전부 PASS.

---

## Task 3: 백업(Export/Import)에 휴지통 항목 포함

**Files:**
- Modify: `database.py` (export `database.py:851-861`, import `database.py:938-946`)
- Test: `tests/test_database.py` (TestExportImport `test_database.py:575` 이하)

- [ ] **Step 1: export/import 휴지통 왕복 테스트 작성 (실패 유도)**

`tests/test_database.py`의 `TestExportImport` 클래스에 추가:

```python
    def test_export_includes_trashed_sticky(self, app_dir):
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, content="휴지통 백업 대상")
        db.trash_sticky_note(nid)
        data = json.loads(db.export_all_data())
        trashed = [s for s in data["sticky_notes"] if s.get("is_deleted") == 1]
        assert len(trashed) == 1
        assert trashed[0]["deleted_at"] != ""

    def test_import_roundtrip_preserves_trash_state(self, app_dir):
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, content="휴지통 왕복")
        db.trash_sticky_note(nid)

        exported = db.export_all_data()
        db.reset_database()
        db.import_all_data(exported)

        # 복원 후에도 휴지통에 존재하고 열린 목록에는 없음
        trashed = db.get_trashed_sticky_notes()
        assert any(t["content"] == "휴지통 왕복" for t in trashed)
        assert all(n["content"] != "휴지통 왕복" for n in db.get_open_sticky_notes())

    def test_import_sticky_without_trash_fields_defaults_live(self, app_dir):
        """구버전 백업(is_deleted/deleted_at 없음) 임포트 시 일반(라이브) 노트로 들어감"""
        old_json = json.dumps({
            "schedules": [], "memos": [],
            "sticky_notes": [{
                "type": "memo", "content": "구버전 노트",
                "x_pos": 100, "y_pos": 100, "width": 300, "height": 400,
                "is_open": 1, "is_pinned": 0, "color": "#FFFA8E",
            }],
            "dday_widgets": [],
        })
        db.import_all_data(old_json)
        notes = db.get_open_sticky_notes()
        assert any(n["content"] == "구버전 노트" for n in notes)
        assert db.get_trashed_sticky_notes() == []
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_database.py::TestExportImport -q`
Expected: FAIL — export dict에 `is_deleted`/`deleted_at` 없음, import가 휴지통 상태 미복원.

- [ ] **Step 3: export에 휴지통 필드 추가**

`database.py:851-861`의 sticky_notes 컴프리헨션에 두 필드를 추가(`"color": ...` 다음):

```python
        sticky_notes = [{
            "type": row["type"],
            "content": _safe_decrypt(row["content"]),
            "x_pos": row["x_pos"],
            "y_pos": row["y_pos"],
            "width": row["width"],
            "height": row["height"],
            "is_open": row["is_open"],
            "is_pinned": row["is_pinned"],
            "color": row["color"] or DEFAULT_STICKY_COLOR,
            "is_deleted": row["is_deleted"],
            "deleted_at": row["deleted_at"],
        } for row in conn.execute("SELECT * FROM sticky_notes")]
```

- [ ] **Step 4: import INSERT에 휴지통 컬럼 추가(하위호환 기본값)**

`database.py:938-946`의 sticky INSERT 루프를 아래로 교체:

```python
        for n in data.get("sticky_notes", []):
            conn.execute(
                """INSERT INTO sticky_notes
                   (type, content, x_pos, y_pos, width, height, is_open, is_pinned,
                    color, is_deleted, deleted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (n["type"], encrypt(n.get("content", "")), n["x_pos"], n["y_pos"],
                 n["width"], n["height"], n["is_open"], n["is_pinned"],
                 n.get("color", DEFAULT_STICKY_COLOR),
                 n.get("is_deleted", 0), n.get("deleted_at", ""))
            )
```

- [ ] **Step 5: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_database.py::TestExportImport -q`
Expected: PASS (휴지통 백업 3개 + 기존 `test_roundtrip` 등 모두 통과)

- [ ] **Step 6: 체크포인트 — DB 테스트 전체 통과**

Run: `python -m pytest tests/test_database.py -q`
Expected: 전부 PASS.

---

## Task 4: 닫기 → 휴지통 이동 (`ui_sticky.py`)

**Files:**
- Modify: `ui_sticky.py` (`_on_close` — `ui_sticky.py:534-547`)
- Test: `tests/test_ui_sticky.py`

- [ ] **Step 1: 닫기=휴지통 이동 테스트 작성 (실패 유도)**

`tests/test_ui_sticky.py` 끝에 추가:

```python
def test_close_moves_note_to_trash(qtbot, app_dir, qapp, monkeypatch):
    """닫기 확인 시 영구삭제가 아니라 휴지통으로 이동해야 한다."""
    nid = db.create_sticky_note(note_type="memo", x=120, y=130)
    db.update_sticky_note(nid, content="닫을 노트")
    note_data = {"content": "닫을 노트", "x_pos": 120, "y_pos": 130,
                 "width": 300, "height": 400, "color": db.DEFAULT_STICKY_COLOR}
    win = StickyNoteWindow(nid, note_data)
    qtbot.addWidget(win)

    # 확인 팝업을 자동 수락 처리
    monkeypatch.setattr("ui_sticky.MessageBox.exec", lambda self: True)

    win._on_close()

    # 열린 목록에서 사라지고 휴지통에 존재
    assert not any(n["id"] == nid for n in db.get_open_sticky_notes())
    assert any(t["id"] == nid for t in db.get_trashed_sticky_notes())
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_close_moves_note_to_trash -q`
Expected: FAIL — 현재 `_on_close`가 `db.delete_sticky_note`(개명되어 이제 미존재) 또는 영구삭제를 호출.

- [ ] **Step 3: `_on_close` 구현 변경**

`ui_sticky.py:534-547`의 `_on_close`를 아래로 교체:

```python
    def _on_close(self):
        """닫기 확인 → 휴지통으로 이동(soft-delete)"""
        dlg = MessageBox(
            "노트 정리",
            "이 노트를 휴지통으로 이동하시겠습니까?\n휴지통에서 다시 복구할 수 있습니다.",
            self
        )
        dlg.yesButton.setText("휴지통으로")
        dlg.cancelButton.setText("취소")
        if dlg.exec():
            self._save_timer.stop()
            db.trash_sticky_note(self.note_id)
            self.note_closed.emit(self.note_id)
            self.close()
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_close_moves_note_to_trash -q`
Expected: PASS

- [ ] **Step 5: 체크포인트 — 스티키 UI 테스트 전체 통과**

Run: `python -m pytest tests/test_ui_sticky.py -q`
Expected: 전부 PASS.

---

## Task 5: 휴지통 메뉴 아이콘 추가 (`delete_color.svg`)

**Files:**
- Create: `resources/fluent_icons/delete_color.svg`
- Test: `tests/test_database.py` 아님 → 간단 검증은 Step 3에서 직접 로드 확인

- [ ] **Step 1: SVG 파일 생성**

`resources/fluent_icons/delete_color.svg` 생성(24x24, 기존 `_color` 아이콘 팔레트 #D9ECFF/#005A9E와 통일된 휴지통 모양):

```xml
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M6 7.5H18L17.1 19.6C17.02 20.66 16.13 21.5 15.06 21.5H8.94C7.87 21.5 6.98 20.66 6.9 19.6L6 7.5Z" fill="#D9ECFF"/>
<path d="M6 7.5H18L17.1 19.6C17.02 20.66 16.13 21.5 15.06 21.5H8.94C7.87 21.5 6.98 20.66 6.9 19.6L6 7.5Z" stroke="#005A9E" stroke-width="1.5" stroke-linejoin="round"/>
<path d="M4 6.5H20" stroke="#005A9E" stroke-width="1.5" stroke-linecap="round"/>
<path d="M9.5 6.5V5.2C9.5 4.54 10.04 4 10.7 4H13.3C13.96 4 14.5 4.54 14.5 5.2V6.5" stroke="#005A9E" stroke-width="1.5" stroke-linejoin="round"/>
<path d="M10 10.5V17" stroke="#005A9E" stroke-width="1.5" stroke-linecap="round"/>
<path d="M14 10.5V17" stroke="#005A9E" stroke-width="1.5" stroke-linecap="round"/>
</svg>
```

> `fluent_icon()`은 이름이 `_color`로 끝나면 틴팅하지 않고 SVG 원본 색을 그대로 쓴다(`fluent_icons.py:42-43`). `build.spec`이 `('resources','resources')`로 디렉터리 전체를 번들하므로 추가 빌드 설정은 불필요(`build.spec:23`).

- [ ] **Step 2: 로드 검증 테스트 작성 (실패 유도)**

`tests/test_ui_sticky.py` 끝에 추가(파일 존재 + QIcon 비어있지 않음 확인):

```python
def test_delete_color_icon_loads(qapp):
    from fluent_icons import fluent_icon, fluent_icon_path
    assert fluent_icon_path("delete_color").exists()
    icon = fluent_icon("delete_color", size=24)
    assert not icon.isNull()
```

- [ ] **Step 3: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_ui_sticky.py::test_delete_color_icon_loads -q`
Expected: PASS (SVG가 정상 로드되어 QIcon이 비어있지 않음). 실패 시 SVG 문법(따옴표/태그) 점검.

---

## Task 6: 휴지통 창 (`ui_trash.py`)

**Files:**
- Create: `ui_trash.py`
- Test: `tests/test_ui_trash.py` (신규)

- [ ] **Step 1: 휴지통 창 테스트 작성 (실패 유도)**

`tests/test_ui_trash.py` 생성:

```python
# tests/test_ui_trash.py - 휴지통 창 UI 테스트
import pytest
from PySide6.QtWidgets import QApplication

import database as db
from ui_trash import StickyTrashWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def trash_win(qtbot, app_dir, qapp):
    win = StickyTrashWindow()
    qtbot.addWidget(win)
    return win


def test_table_lists_trashed_notes(qtbot, app_dir, qapp):
    nid = db.create_sticky_note()
    db.update_sticky_note(nid, content="삭제된 노트 본문")
    db.trash_sticky_note(nid)

    win = StickyTrashWindow()
    qtbot.addWidget(win)
    assert win.table.rowCount() == 1
    # 미리보기 텍스트가 본문에서 파생됨
    assert "삭제된 노트" in win.table.item(0, 1).text()


def test_empty_state_when_no_trash(trash_win):
    assert trash_win.table.rowCount() == 0
    assert trash_win.empty_label.isVisible()


def test_restore_emits_signal_and_refreshes(qtbot, app_dir, qapp):
    nid = db.create_sticky_note()
    db.trash_sticky_note(nid)
    win = StickyTrashWindow()
    qtbot.addWidget(win)
    win.table.selectRow(0)

    with qtbot.waitSignal(win.restore_requested, timeout=1000) as blocker:
        win._on_restore()
    assert blocker.args == [nid]


def test_purge_removes_row(qtbot, app_dir, qapp, monkeypatch):
    nid = db.create_sticky_note()
    db.trash_sticky_note(nid)
    win = StickyTrashWindow()
    qtbot.addWidget(win)
    win.table.selectRow(0)

    monkeypatch.setattr("ui_trash.MessageBox.exec", lambda self: True)
    win._on_purge()

    assert win.table.rowCount() == 0
    assert db.get_trashed_sticky_notes() == []


def test_empty_trash_clears_all(qtbot, app_dir, qapp, monkeypatch):
    for _ in range(3):
        nid = db.create_sticky_note()
        db.trash_sticky_note(nid)
    win = StickyTrashWindow()
    qtbot.addWidget(win)

    monkeypatch.setattr("ui_trash.MessageBox.exec", lambda self: True)
    win._on_empty()

    assert win.table.rowCount() == 0
    assert db.get_trashed_sticky_notes() == []
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_ui_trash.py -q`
Expected: FAIL — `ui_trash` 모듈 없음(ImportError).

- [ ] **Step 3: `ui_trash.py` 구현**

`ui_trash.py` 생성:

```python
# ui_trash.py - 스티키 노트 휴지통 창 (복구 / 영구삭제 / 비우기)
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QTextDocument

from qfluentwidgets import (
    PrimaryPushButton, PushButton, BodyLabel, CaptionLabel, MessageBox,
)

import database as db

_logger = logging.getLogger("app_error")


def _preview_text(html: str, limit: int = 40) -> str:
    """HTML 본문을 한 줄 평문 미리보기로 변환."""
    doc = QTextDocument()
    doc.setHtml(html or "")
    text = doc.toPlainText().replace("\n", " ").strip()
    if not text:
        return "(빈 노트)"
    return text[:limit] + ("..." if len(text) > limit else "")


class StickyTrashWindow(QWidget):
    """삭제된 스티키 노트를 보고 복구/영구삭제하는 창."""
    restore_requested = Signal(int)  # 복구할 note_id를 메인 창에 전달

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("휴지통")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setMinimumSize(440, 480)
        self.resize(440, 480)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = BodyLabel("🗑️ 스티키 노트 휴지통", self)
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        self.count_label = CaptionLabel("", self)
        self.count_label.setStyleSheet("color: gray;")
        layout.addWidget(self.count_label)

        # 빈 상태 안내
        self.empty_label = BodyLabel("휴지통이 비어 있습니다.", self)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #9aa0a6; padding: 40px;")
        layout.addWidget(self.empty_label)

        # 결과 테이블
        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["색상", "내용", "삭제 시각"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setShowGrid(True)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                color: #37352f;
                border: 1px solid #ededed;
                border-radius: 4px;
                gridline-color: #ededed;
                outline: none;
            }
            QTableWidget::item { padding: 8px 12px; border-bottom: none; }
            QTableWidget::item:selected { background-color: #ebeced; color: #37352f; }
            QHeaderView::section {
                background-color: #f7f7f5;
                color: #37352f;
                padding: 8px 12px;
                font-weight: 500;
                font-size: 13px;
                border: none;
                border-bottom: 1px solid #ededed;
            }
        """)
        layout.addWidget(self.table, 1)

        # 버튼 줄
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.restore_btn = PrimaryPushButton("복구", self)
        self.restore_btn.clicked.connect(self._on_restore)
        btn_row.addWidget(self.restore_btn)

        self.purge_btn = PushButton("영구 삭제", self)
        self.purge_btn.clicked.connect(self._on_purge)
        btn_row.addWidget(self.purge_btn)

        btn_row.addStretch(1)

        self.empty_btn = PushButton("휴지통 비우기", self)
        self.empty_btn.clicked.connect(self._on_empty)
        btn_row.addWidget(self.empty_btn)

        layout.addLayout(btn_row)

    def _refresh(self):
        """휴지통 목록을 다시 읽어 테이블 갱신."""
        try:
            items = db.get_trashed_sticky_notes()
        except (OSError, ValueError) as e:
            _logger.error("휴지통 목록 로드 실패: %s", e)
            items = []

        self.table.setRowCount(len(items))
        for row, it in enumerate(items):
            color_item = QTableWidgetItem("")
            color_item.setBackground(QColor(it["color"]))
            color_item.setData(Qt.UserRole, it["id"])  # 행 식별용 note_id

            content_item = QTableWidgetItem(_preview_text(it["content"]))
            content_item.setToolTip(_preview_text(it["content"], 200))

            when = (it["deleted_at"] or "")[:16]  # YYYY-MM-DD HH:MM
            when_item = QTableWidgetItem(when)

            self.table.setItem(row, 0, color_item)
            self.table.setItem(row, 1, content_item)
            self.table.setItem(row, 2, when_item)

        has_items = len(items) > 0
        self.empty_label.setVisible(not has_items)
        self.table.setVisible(has_items)
        self.restore_btn.setEnabled(has_items)
        self.purge_btn.setEnabled(has_items)
        self.empty_btn.setEnabled(has_items)
        self.count_label.setText(f"휴지통: {len(items)}개" if has_items else "")

    def _selected_note_id(self):
        """선택된 행의 note_id 반환(없으면 None)."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_restore(self):
        note_id = self._selected_note_id()
        if note_id is None:
            return
        self.restore_requested.emit(note_id)
        self._refresh()

    def _on_purge(self):
        note_id = self._selected_note_id()
        if note_id is None:
            return
        dlg = MessageBox(
            "영구 삭제",
            "이 노트를 영구히 삭제할까요?\n되돌릴 수 없습니다.",
            self
        )
        dlg.yesButton.setText("영구 삭제")
        dlg.cancelButton.setText("취소")
        if dlg.exec():
            db.purge_sticky_note(note_id)
            self._refresh()

    def _on_empty(self):
        if self.table.rowCount() == 0:
            return
        dlg = MessageBox(
            "휴지통 비우기",
            "휴지통의 모든 노트를 영구히 삭제할까요?\n되돌릴 수 없습니다.",
            self
        )
        dlg.yesButton.setText("모두 삭제")
        dlg.cancelButton.setText("취소")
        if dlg.exec():
            db.empty_sticky_trash()
            self._refresh()
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_ui_trash.py -q`
Expected: PASS (5개 테스트)

> 참고: `test_restore_emits_signal_and_refreshes`는 신호만 검증한다. 신호 처리 후 실제 복구는 메인 창(`_restore_sticky_note`)이 하므로 Task 7에서 db.restore가 호출된다. 이 테스트에서 휴지통 행은 신호 emit 직후 `_refresh()`로 재조회되지만 아직 db에는 남아 있어 1행이 유지될 수 있다 — 신호 인자(`blocker.args == [nid]`)만 단언하므로 무방하다.

---

## Task 7: 메뉴 항목 + 복구 핸들러 (`ui_main.py`)

**Files:**
- Modify: `ui_main.py` (`__init__` `ui_main.py:526-533`, `_build_more_menu` `ui_main.py:978-989`, 스티키 영역 `ui_main.py:1542-1558`)
- Test: `tests/test_ui_trash.py` (메인 연동 테스트 추가)

- [ ] **Step 1: 복구 연동 테스트 작성 (실패 유도)**

`tests/test_ui_trash.py` 끝에 추가:

```python
def test_main_restore_handler_reopens_note(qtbot, app_dir, qapp):
    from ui_main import MainWindow
    nid = db.create_sticky_note("memo", 222, 233, "#C4D5FF")
    db.update_sticky_note(nid, content="복구해서 다시 열 노트")
    db.trash_sticky_note(nid)

    win = MainWindow()
    qtbot.addWidget(win)

    win._restore_sticky_note(nid)

    # db에서 복구되어 열린 목록에 등장
    assert any(n["id"] == nid for n in db.get_open_sticky_notes())
    # 메인이 해당 노트 창을 다시 생성
    assert nid in win._sticky_windows
```

> `MainWindow()` 생성이 무거우면(트레이/타이머 등) 이 테스트는 `@pytest.mark.slow` 등으로 분리해도 된다. 우선 그대로 작성하고, 생성 비용 문제가 있으면 Task 8 체크포인트에서 조정한다.

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_ui_trash.py::test_main_restore_handler_reopens_note -q`
Expected: FAIL — `_restore_sticky_note` 미정의.

- [ ] **Step 3: `__init__`에 휴지통 창 참조 초기화**

`ui_main.py:529`의 `self._settings_window = None` 다음 줄에 추가:

```python
        self._trash_window = None
```

- [ ] **Step 4: 더보기 메뉴에 "휴지통" 항목 삽입**

`ui_main.py:982-984` 사이, `앱 업데이트`와 `설정` 사이에 한 줄 삽입:

```python
        menu.addAction(fluent_icon("arrow_sort_color", size=24), "자동정렬", self._on_arrange_sticky_notes)
        menu.addAction(fluent_icon("arrow_sync_color", size=24), "앱 업데이트", self._on_update_guide)
        menu.addAction(fluent_icon("delete_color", size=24), "휴지통", self._on_open_trash)
        menu.addAction(fluent_icon("settings_color", size=24), "설정", self._on_settings)
```

- [ ] **Step 5: `_on_open_trash` + `_restore_sticky_note` 추가**

`ui_main.py`의 `_on_sticky_note_closed`(`ui_main.py:1554-1558`) 다음에 추가:

```python
    def _on_open_trash(self):
        """휴지통 창 열기(단일 인스턴스 재사용)."""
        from ui_trash import StickyTrashWindow
        if self._trash_window is None or not self._trash_window.isVisible():
            self._trash_window = StickyTrashWindow()
            self._trash_window.restore_requested.connect(self._restore_sticky_note)
        else:
            self._trash_window._refresh()
        self._trash_window.show()
        self._trash_window.raise_()

    def _restore_sticky_note(self, note_id: int):
        """휴지통에서 복구: db 복구 후 원위치에 노트 창 재생성."""
        from ui_sticky import StickyNoteWindow
        db.restore_sticky_note(note_id)
        if note_id in self._sticky_windows:
            return
        note = next((n for n in db.get_open_sticky_notes() if n["id"] == note_id), None)
        if note is None:
            return
        win = StickyNoteWindow(note_id, note)
        win.note_closed.connect(self._on_sticky_note_closed)
        win.show()
        self._sticky_windows[note_id] = win
```

- [ ] **Step 6: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_ui_trash.py -q`
Expected: PASS (Task 6의 5개 + 본 연동 테스트)

- [ ] **Step 7: 체크포인트 — UI 테스트 전체 통과**

Run: `python -m pytest tests/test_ui_sticky.py tests/test_ui_trash.py -q`
Expected: 전부 PASS.

---

## Task 8: 전체 검증 + 문서 갱신

**Files:**
- Modify: `AGENTS.md` (`AGENTS.md:45` ui_sticky 행, `AGENTS.md:38` database 행, `AGENTS.md:66` 삭제 정책)
- Modify: `docs/ARCHITECTURE.md` (DB Schema 절)

- [ ] **Step 1: 전체 테스트 스위트 실행**

Run: `python -m pytest tests -q`
Expected: 전부 PASS. 실패 시 해당 Task로 돌아가 수정.

- [ ] **Step 2: `AGENTS.md` 삭제 정책 항목 교체**

`AGENTS.md:66`의 삭제 정책 줄을 아래로 교체:

```markdown
- **삭제 정책**: 스티키 노트 닫기는 `db.trash_sticky_note()`로 **휴지통 이동(soft-delete)**한다(즉시 삭제 아님). 휴지통(우측 메뉴 → 휴지통, `ui_trash.py`)에서 `restore_sticky_note()`로 원위치 복구, `purge_sticky_note()`로 개별 영구삭제, `empty_sticky_trash()`로 전체 비우기. 휴지통은 `STICKY_TRASH_LIMIT(=50)`개로 제한되어 초과 시 오래된 것부터 자동 영구삭제(`_enforce_trash_cap`, 로그 기록). 영구삭제/비우기는 확인 팝업만(PIN 불필요). 백업(Export/Import)에 휴지통 항목 포함. D-Day/집중 모드/일정 휴지통은 미구현.
```

- [ ] **Step 3: `AGENTS.md` Module Map 갱신**

`AGENTS.md:38`의 `database.py` 행에서 `(v12)` → `(v13)`로 바꾸고 `; 스티키 휴지통(trash/restore/purge/empty/get_trashed_sticky_notes, STICKY_TRASH_LIMIT)` 문구를 끝에 덧붙인다.

`AGENTS.md:45`의 `ui_sticky.py` 행 끝에 `, 닫기는 휴지통 이동(trash_sticky_note)` 추가.

`AGENTS.md`의 Module Map 표(`ui_sticky.py` 행 부근)에 새 행 추가:

```markdown
| `ui_trash.py` | 스티키 노트 휴지통 창: 삭제된 노트 목록(색상/미리보기/삭제시각), 복구(`restore_requested` 시그널 → 메인이 원위치 재생성)/영구삭제/휴지통 비우기. 확인 팝업만(PIN 없음) |
```

- [ ] **Step 4: `docs/ARCHITECTURE.md` 스키마 갱신**

`docs/ARCHITECTURE.md`에서 `sticky_notes` 스키마와 스키마 버전 표기를 찾는다:

Run: `python -m pytest -q` 가 아닌 검색 — 에디터/grep으로 `sticky_notes`, `user_version`, `v12` 검색.

찾은 위치에 `sticky_notes`의 컬럼 목록에 `is_deleted INTEGER`, `deleted_at TEXT`를 추가하고, 스키마 버전 표기를 `v12` → `v13`으로 바꾼다. (해당 표기가 없으면 이 단계는 생략.)

- [ ] **Step 5: 최종 체크포인트 — 전체 테스트 재실행**

Run: `python -m pytest tests -q`
Expected: 전부 PASS.

- [ ] **Step 6: 수동 스모크 테스트 (선택, 권장)**

Run: `python main.py`
확인 절차:
1. 스티키 노트 생성 → 내용 입력 → 닫기(X) → "휴지통으로 이동" 확인.
2. 우측 더보기 메뉴 → "휴지통" 클릭 → 방금 노트가 목록에 보이는지.
3. 행 선택 → "복구" → 원래 위치/내용으로 다시 뜨는지.
4. 다시 닫고 휴지통에서 "영구 삭제" / "휴지통 비우기" 동작 확인.
5. 설정 → Export → Import 시 휴지통 항목이 보존되는지.

---

## Self-Review (작성자 점검 완료)

**Spec coverage:**
- soft-delete 컬럼/마이그레이션 → Task 1 ✅
- trash/restore/purge/empty/get_trashed/cap/get_open 필터/개명 → Task 2 ✅
- 백업 포함(왕복·하위호환) → Task 3 ✅
- 닫기=휴지통 이동 → Task 4 ✅
- 메뉴 아이콘 → Task 5 ✅
- 휴지통 창 UI(복구/영구삭제/비우기/빈 상태/미리보기) → Task 6 ✅
- 메뉴 항목(설정 위) + 복구 핸들러(원위치 재생성) → Task 7 ✅
- 문서 갱신 → Task 8 ✅

**Placeholder scan:** 코드 단계는 모두 완전한 코드 포함, 명령·기대결과 명시. ARCHITECTURE.md만 "있으면 갱신"의 조건부(문서이므로 허용).

**Type/이름 일관성:** `trash_sticky_note`/`restore_sticky_note`/`purge_sticky_note`/`empty_sticky_trash`/`get_trashed_sticky_notes`/`_enforce_trash_cap`/`STICKY_TRASH_LIMIT`/`StickyTrashWindow`/`restore_requested`/`_on_open_trash`/`_restore_sticky_note`/`_trash_window` — 전 Task에서 동일하게 사용. `delete_color`(아이콘) 일관. get_open 필터 컬럼명 `is_deleted`/`deleted_at` 일관.
