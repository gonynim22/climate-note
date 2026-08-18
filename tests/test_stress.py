# tests/test_stress.py - 1년 사용 시뮬레이션 스트레스 테스트
# 실행: python -m pytest tests/test_stress.py -v --timeout=120
import json
from datetime import date, timedelta

import pytest
import database as db


COLORS = [c[0] for c in db.SCHEDULE_COLORS]  # ["#FFD166", "#4CC9F0", "#FF6B6B"]


def _year_dates(year: int = 2025) -> list[str]:
    start = date(year, 1, 1)
    return [str(start + timedelta(days=i)) for i in range(365)]


class TestOneYearSimulation:

    @pytest.mark.timeout(60)
    def test_365_schedules_add_and_retrieve(self, app_dir):
        """365일 × 1 일정 저장 후 임의 날짜 조회 정확성 검증"""
        dates = _year_dates()
        for d in dates:
            db.add_schedule(d, f"{d} 일정", COLORS[0])

        for d in ["2025-01-01", "2025-06-15", "2025-12-31"]:
            result = db.get_schedules(d)
            assert len(result) == 1
            assert result[0]["content"] == f"{d} 일정"

    @pytest.mark.timeout(120)
    def test_1095_schedules_three_colors(self, app_dir):
        """365일 × 3색상 = 1,095개 저장 후 get_all_schedule_date_colors 검증"""
        dates = _year_dates()
        for d in dates:
            for color in COLORS:
                db.add_schedule(d, f"{d} {color}", color)

        date_colors = db.get_all_schedule_date_colors()
        assert len(date_colors) == 365

        # 모든 날짜가 정확히 3색상, 팔레트 순서로 정렬
        for d, colors in date_colors.items():
            assert len(colors) == 3
            assert colors == COLORS  # ["#FFD166", "#4CC9F0", "#FF6B6B"]

    @pytest.mark.timeout(60)
    def test_search_across_large_dataset(self, app_dir):
        """100개 일반 일정 + 1개 특수 일정 중 검색 정확성"""
        dates = _year_dates()
        for d in dates[:100]:
            db.add_schedule(d, "일반 업무 일정", COLORS[0])
        db.add_schedule("2025-07-04", "독립기념일 특별 행사", COLORS[1])

        results = db.search_all("독립기념일")
        assert len(results) == 1
        assert results[0]["date"] == "2025-07-04"

    @pytest.mark.timeout(30)
    def test_memo_upsert_365_times(self, app_dir):
        """같은 날짜 메모 365회 업데이트 후 최종 값만 남아야 함"""
        for i in range(365):
            db.save_memo("2025-01-01", f"업데이트 {i}회차")
        assert db.get_memo("2025-01-01") == "업데이트 364회차"

    @pytest.mark.timeout(90)
    def test_full_year_export_import_roundtrip(self, app_dir):
        """1년치 일정+메모 export→reset→import 후 완전 복원 검증"""
        dates = _year_dates()
        for d in dates:
            db.add_schedule(d, f"{d} 일정", COLORS[0])
            db.save_memo(d, f"{d} 메모")

        exported = db.export_all_data()
        payload = json.loads(exported)
        assert len(payload["schedules"]) == 365
        assert len(payload["memos"]) == 365

        db.reset_database()
        db.import_all_data(exported)

        # 첫날/마지막날 샘플 검증
        assert db.get_schedules("2025-01-01")[0]["content"] == "2025-01-01 일정"
        assert db.get_memo("2025-12-31") == "2025-12-31 메모"

    @pytest.mark.timeout(30)
    def test_rapid_add_delete_100_cycles(self, app_dir):
        """100회 추가/삭제 반복 후 DB 무결성 유지"""
        for i in range(100):
            sid = db.add_schedule("2025-03-15", f"사이클 {i}")
            db.delete_schedule(sid)
        assert db.get_schedules("2025-03-15") == []

    @pytest.mark.timeout(30)
    def test_large_memo_10kb(self, app_dir):
        """10KB 메모 저장/복원"""
        large = "가나다라마바사아자차카타파하 " * 600  # ~8,400자
        db.save_memo("2025-06-01", large)
        assert db.get_memo("2025-06-01") == large

    @pytest.mark.timeout(30)
    def test_20_sticky_notes(self, app_dir):
        """스티키 노트 20개 생성, 내용 저장, 전체 조회"""
        ids = []
        for i in range(20):
            nid = db.create_sticky_note("memo", 100 + i * 10, 100 + i * 10)
            db.update_sticky_note(nid, content=f"노트 {i} 내용")
            ids.append(nid)

        notes = db.get_open_sticky_notes()
        assert len(notes) == 20
        contents = {n["content"] for n in notes}
        for i in range(20):
            assert f"노트 {i} 내용" in contents

    @pytest.mark.timeout(30)
    def test_color_dedup_max_3_regardless_of_count(self, app_dir):
        """같은 날 아무리 많은 일정을 추가해도 색상은 최대 3개"""
        for _ in range(20):
            db.add_schedule("2025-05-01", "노랑 반복", "#FFD166")
        for _ in range(20):
            db.add_schedule("2025-05-01", "파랑 반복", "#4CC9F0")
        for _ in range(20):
            db.add_schedule("2025-05-01", "빨강 반복", "#FF6B6B")

        result = db.get_all_schedule_date_colors()
        assert len(result["2025-05-01"]) == 3

    @pytest.mark.timeout(60)
    def test_backup_rotation_with_full_year_data(self, app_dir):
        """1년 데이터 로드 후 백업 실행 시 5개 회전 정상 작동"""
        import shutil

        dates = _year_dates()
        for d in dates[:50]:  # 50일치만 빠르게
            db.add_schedule(d, f"{d} 일정")

        backup_dir = app_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        db.backup_database()
        template = next(backup_dir.glob("calendar_auto_*.cnbak"))
        # 기존 6개 검증된 새 형식 백업 생성
        for i in range(6):
            dst = backup_dir / (
                f"calendar_auto_2025010{i + 1}_000000_copy{i}.cnbak"
            )
            shutil.copy2(template, dst)
        template.unlink()

        db.backup_database()

        backups = sorted(backup_dir.glob("calendar_auto_*.cnbak"))
        assert len(backups) == 5

    @pytest.mark.timeout(30)
    def test_vacuum_preserves_full_year_data(self, app_dir):
        """VACUUM 후 1년치 데이터 보존"""
        dates = _year_dates()[:30]
        for d in dates:
            db.add_schedule(d, f"{d} 일정")

        db.optimize_database()

        result = db.get_all_schedule_date_colors()
        assert len(result) == 30
