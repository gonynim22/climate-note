"""공휴일 데이터 만료 안내 문구 (Qt 없음)."""
from datetime import date

HOLIDAY_NOTICE_TITLE = "공휴일 안내"


def holiday_expiry_notice(today: date, last_year: int, email: str) -> tuple[str, str] | None:
    """마지막 데이터 연도 12월부터 (제목, 본문)을 돌려준다. 안내할 때가 아니면 None.

    줄바꿈은 가장 좁은 메인 창(380px)의 알림 띠에 메일 주소가 온전히 들어가도록 직접 나눈 것이다.
    """
    if last_year <= 0:
        return None
    if today.year == last_year and today.month == 12:
        return (HOLIDAY_NOTICE_TITLE,
                f"공휴일 정보는 {last_year}년까지\n"
                "들어 있습니다.\n"
                "새 버전을 받지 못했다면\n"
                f"개발자({email})에게\n"
                "메일로 알려 주세요.")
    if today.year > last_year:
        return (HOLIDAY_NOTICE_TITLE,
                f"{last_year + 1}년부터는 달력에\n"
                "공휴일이 표시되지 않습니다.\n"
                f"개발자({email})에게\n"
                "메일로 알려 주세요.")
    return None
