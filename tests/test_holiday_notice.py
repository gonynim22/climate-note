from datetime import date

import pytest
from PySide6.QtWidgets import QWidget
from qfluentwidgets import InfoBar, InfoBarPosition

from app_info import APP_AUTHOR, APP_CONTACT_EMAIL
from holiday_notice import HOLIDAY_NOTICE_TITLE, holiday_expiry_notice

# 380px 알림 띠에 메일이 온전히 들어가도록 줄바꿈 위치만 나눈 문구
FIRST = ("공휴일 정보는 2027년까지\n들어 있습니다.\n"
         "새 버전을 받지 못했다면\n개발자(ggjo@korea.kr)에게\n메일로 알려 주세요.")
AFTER = ("2028년부터는 달력에\n공휴일이 표시되지 않습니다.\n"
         "개발자(ggjo@korea.kr)에게\n메일로 알려 주세요.")


@pytest.mark.parametrize("today,expected", [
    (date(2027, 11, 30), None),
    (date(2027, 12, 1), (HOLIDAY_NOTICE_TITLE, FIRST)),
    (date(2027, 12, 31), (HOLIDAY_NOTICE_TITLE, FIRST)),
    (date(2028, 1, 1), (HOLIDAY_NOTICE_TITLE, AFTER)),
    (date(2031, 6, 1), (HOLIDAY_NOTICE_TITLE, AFTER)),
])
def test_holiday_expiry_notice_by_date(today, expected):
    assert holiday_expiry_notice(today, 2027, "ggjo@korea.kr") == expected


def test_notice_none_without_data_year():
    assert holiday_expiry_notice(date(2027, 12, 1), 0, "ggjo@korea.kr") is None


def test_contact_email_is_single_source():
    assert APP_CONTACT_EMAIL == "ggjo@korea.kr"
    assert APP_AUTHOR == "기후에너지환경부 보문산불주먹 (ggjo@korea.kr)"


@pytest.mark.parametrize("today", [date(2027, 12, 1), date(2028, 1, 1)])
def test_notice_fits_narrowest_main_window(qtbot, today):
    parent = QWidget()
    parent.resize(380, 600)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitExposed(parent)
    title, content = holiday_expiry_notice(today, 2027, APP_CONTACT_EMAIL)
    bar = InfoBar.warning(title, content, parent=parent,
                          position=InfoBarPosition.TOP, duration=-1)
    qtbot.waitExposed(bar)
    assert APP_CONTACT_EMAIL in bar.contentLabel.text()
    assert bar.geometry().right() <= parent.width()
    assert bar.geometry().left() >= 0
