# tests/test_edge_cases.py - 경계값, 이상 입력, 데이터 무결성 엣지 케이스
import json

import pytest
import security
import database as db


class TestScheduleEdgeCases:
    def test_content_with_newlines(self, app_dir):
        text = "1줄\n2줄\n3줄"
        db.add_schedule("2025-01-10", text)
        assert db.get_schedules("2025-01-10")[0]["content"] == text

    def test_content_with_quotes(self, app_dir):
        text = "그는 \"안녕\"이라고 말했다. It's fine."
        db.add_schedule("2025-01-11", text)
        assert db.get_schedules("2025-01-11")[0]["content"] == text

    def test_content_sql_injection(self, app_dir):
        text = "'; DELETE FROM schedules; --"
        db.add_schedule("2025-01-12", text)
        result = db.get_schedules("2025-01-12")
        assert result[0]["content"] == text
        # 테이블이 살아있어야 함
        assert isinstance(db.get_schedules("2025-01-12"), list)

    def test_content_very_long(self, app_dir):
        text = "매우 긴 일정 내용 " * 200  # ~1,600자
        db.add_schedule("2025-01-13", text)
        assert db.get_schedules("2025-01-13")[0]["content"] == text

    def test_content_unicode_emoji(self, app_dir):
        text = "회의 완료 ✅ 점심 🍜 운동 💪 👊"
        db.add_schedule("2025-02-14", text)
        assert db.get_schedules("2025-02-14")[0]["content"] == text

    def test_schedule_emoji_pin_roundtrip_preserves_existing_dataset(self, app_dir):
        original_id = db.add_schedule("2026-09-09", "기존 일정", "#4CC9F0")
        text = "✉️ 협의회의 👩🏽‍💻 🇰🇷 📌 ⭐ 🔥 ⏰ 🤝 👥 📞 📝 📄 📊 🎯 📚 🚗 🏠 🎉"
        emoji_id = db.add_schedule("2026-09-09", "📌 협의회의", "#FFD166")
        db.update_schedule(emoji_id, content=text)
        assert db.get_schedules_for_month(2026, 9)["2026-09-09"][1]["content"] == text
        assert db.search_all("협의회의")[0]["content"] == text
        with db._connection() as conn:
            before = [tuple(row) for row in conn.execute("SELECT * FROM schedules ORDER BY id")]
            settings = [tuple(row) for row in conn.execute("SELECT * FROM app_settings ORDER BY key")]
        salt = security.read_existing_salt()
        bundle = security.encrypt_with_pin(db.export_all_data().encode("utf-8"), "1234")
        path = app_dir / "emoji-roundtrip.enc"
        with open(path, "wb") as stream:
            stream.write(bundle)
        with open(path, "rb") as stream:
            imported = security.decrypt_with_pin(stream.read(), "1234").decode("utf-8")
        db.import_all_data(imported)
        after = db.get_schedules("2026-09-09")
        assert [row["content"] for row in after] == ["기존 일정", text, "기존 일정", text]
        assert [row["color"] for row in after] == ["#4CC9F0", "#FFD166"] * 2
        with db._connection() as conn:
            assert [tuple(row) for row in conn.execute(
                "SELECT * FROM schedules WHERE id IN (?, ?) ORDER BY id", (original_id, emoji_id)
            )] == before
            assert [tuple(row) for row in conn.execute("SELECT * FROM app_settings ORDER BY key")] == settings
            assert conn.execute("PRAGMA user_version").fetchone()[0] == db.CURRENT_SCHEMA_VERSION
        assert security.read_existing_salt() == salt

    def test_unknown_color_stored_as_is(self, app_dir):
        """팔레트에 없는 색상도 저장/복원"""
        custom = "#ABCDEF"
        db.add_schedule("2025-03-01", "커스텀 색상", custom)
        result = db.get_schedules("2025-03-01")
        assert result[0]["color"] == custom


class TestMemoEdgeCases:
    def test_html_content_stored_verbatim(self, app_dir):
        text = "<script>alert('xss')</script><b>굵게</b>"
        db.save_memo("2025-01-13", text)
        assert db.get_memo("2025-01-13") == text  # 저장/복원만 검증

    def test_memo_with_only_spaces(self, app_dir):
        db.save_memo("2025-02-01", "   ")
        assert db.get_memo("2025-02-01") == "   "

    def test_memo_overwrite_with_empty(self, app_dir):
        db.save_memo("2025-02-02", "원래 내용")
        db.save_memo("2025-02-02", "")
        assert db.get_memo("2025-02-02") == ""


class TestStickyNoteEdgeCases:
    def test_empty_content_on_create(self, app_dir):
        nid = db.create_sticky_note()
        note = next(n for n in db.get_open_sticky_notes() if n["id"] == nid)
        assert note["content"] == ""

    def test_html_content_roundtrip(self, app_dir):
        html = "<b>굵게</b> <s>취소선</s> <span style='color:#FF6B6B'>빨강</span>"
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, content=html)
        note = next(n for n in db.get_open_sticky_notes() if n["id"] == nid)
        assert note["content"] == html

    def test_update_no_fields_no_error(self, app_dir):
        nid = db.create_sticky_note()
        db.update_sticky_note(nid)  # 필드 없음 → 오류 없어야 함

    def test_unknown_field_ignored(self, app_dir):
        """allowed 외 필드는 무시"""
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, unknown_field="value")  # 무시


class TestDDayEdgeCases:
    def test_past_date(self, app_dir):
        wid = db.create_dday_widget("과거", "2020-01-01")
        w = next(x for x in db.get_open_dday_widgets() if x["id"] == wid)
        assert w["target_date"] == "2020-01-01"

    def test_today_date(self, app_dir):
        wid = db.create_dday_widget("오늘", "2026-03-15")
        assert any(w["id"] == wid for w in db.get_open_dday_widgets())

    def test_far_future_date(self, app_dir):
        wid = db.create_dday_widget("먼 미래", "2099-12-31")
        w = next(x for x in db.get_open_dday_widgets() if x["id"] == wid)
        assert w["target_date"] == "2099-12-31"

    def test_name_with_spaces_and_special(self, app_dir):
        name = "D-Day! 목표 달성 🎯"
        wid = db.create_dday_widget(name, "2026-12-31")
        w = next(x for x in db.get_open_dday_widgets() if x["id"] == wid)
        assert w["name"] == name


class TestImportEdgeCases:
    def test_empty_sections(self, app_dir):
        db.import_all_data(json.dumps({
            "schedules": [], "memos": [],
            "sticky_notes": [], "dday_widgets": []
        }))

    def test_missing_sections(self, app_dir):
        db.import_all_data(json.dumps({"schedules": []}))

    def test_missing_optional_fields(self, app_dir):
        """optional 필드 없는 JSON도 정상 처리"""
        payload = json.dumps({
            "schedules": [
                {"date": "2025-05-01", "content": "최소 필드 일정",
                 "created_at": "2025-05-01 00:00:00"}
            ],
            "memos": [{"date": "2025-05-01", "content": "메모"}],
            "sticky_notes": [
                {"type": "memo", "content": "", "x_pos": 100, "y_pos": 100,
                 "width": 300, "height": 400, "is_open": 1, "is_pinned": 0}
            ],
            "dday_widgets": [
                {"name": "디데이", "target_date": "2026-01-01"}
            ]
        })
        db.import_all_data(payload)
        result = db.get_schedules("2025-05-01")
        assert result[0]["color"] == db.DEFAULT_SCHEDULE_COLOR

    def test_import_then_export_consistent(self, app_dir):
        """import 후 export 시 데이터 손실 없음"""
        original = json.dumps({
            "schedules": [
                {"date": "2025-06-01", "content": "일정A",
                 "created_at": "2025-06-01 09:00:00", "color": "#FF6B6B"}
            ],
            "memos": [{"date": "2025-06-01", "content": "메모A"}],
            "sticky_notes": [], "dday_widgets": []
        })
        db.import_all_data(original)
        exported = json.loads(db.export_all_data())

        s = next(x for x in exported["schedules"] if x["content"] == "일정A")
        assert s["color"] == "#FF6B6B"
        m = next(x for x in exported["memos"] if x["content"] == "메모A")
        assert m["date"] == "2025-06-01"


class TestColorSquaresLogic:
    def test_single_color_returns_one(self, app_dir):
        db.add_schedule("2025-08-01", "a", "#FFD166")
        db.add_schedule("2025-08-01", "b", "#FFD166")
        db.add_schedule("2025-08-01", "c", "#FFD166")
        result = db.get_all_schedule_date_colors()
        assert result["2025-08-01"] == ["#FFD166"]

    def test_two_colors_sorted_correctly(self, app_dir):
        db.add_schedule("2025-08-02", "빨강", "#FF6B6B")
        db.add_schedule("2025-08-02", "파랑", "#4CC9F0")
        result = db.get_all_schedule_date_colors()
        # 팔레트 순서: 파랑(index 1) < 빨강(index 2)
        assert result["2025-08-02"] == ["#4CC9F0", "#FF6B6B"]

    def test_delete_schedule_removes_color_if_last(self, app_dir):
        sid = db.add_schedule("2025-08-03", "유일한 노랑", "#FFD166")
        db.delete_schedule(sid)
        result = db.get_all_schedule_date_colors()
        assert "2025-08-03" not in result

    def test_delete_one_keeps_remaining_color(self, app_dir):
        sid_yellow = db.add_schedule("2025-08-04", "노랑", "#FFD166")
        db.add_schedule("2025-08-04", "파랑", "#4CC9F0")
        db.delete_schedule(sid_yellow)
        result = db.get_all_schedule_date_colors()
        assert result["2025-08-04"] == ["#4CC9F0"]
