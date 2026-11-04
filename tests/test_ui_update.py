"""'앱 업데이트' 안내창(2026-11-04 B안): 받는 곳 두 갈래, 온나라 안내 문구 유지, GitLab은 브라우저로만 연다."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QWidget

import ui_update
from app_info import APP_VERSION
from ui_update import (
    GITLAB, GITLAB_LATEST_URL, ICONS, ONNARA, ONNARA_STEPS, UPDATE_GUIDE_HIGHLIGHT, UPDATE_GUIDE_TITLE,
    UpdateGuideDialog, arrow_offset, icon_pixmap, ripple_state, update_guide_dialog_width, update_guide_text,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def calendar(qtbot, qapp):
    """기본 크기 캘린더 창(사이드바 포함 460×660)을 흉내 낸 부모."""
    window = QWidget()
    window.resize(460, 660)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


@pytest.fixture
def opened(monkeypatch):
    """브라우저 열기를 가로챈다. 테스트가 실제 브라우저를 띄우지 않게 한다."""
    urls = []

    class FakeDesktop:
        @staticmethod
        def openUrl(url):
            urls.append(url.toString())
            return True

    monkeypatch.setattr(ui_update, "QDesktopServices", FakeDesktop)
    return urls


@pytest.fixture
def motion_on(monkeypatch):
    """Windows '애니메이션 효과' 설정에 결과가 흔들리지 않게 켠 상태로 고정한다."""
    monkeypatch.setattr(ui_update, "motion_allowed", lambda: True)


def _open(qtbot, parent, latest=None) -> UpdateGuideDialog:
    dlg = UpdateGuideDialog(parent, latest)
    dlg.show()
    qtbot.waitUntil(dlg.isVisible)
    return dlg


def _pixel(widget: QWidget, x: int, y: int) -> str:
    image = widget.grab().toImage()
    ratio = image.devicePixelRatio()
    return image.pixelColor(int(x * ratio), int(y * ratio)).name().upper()


def _plain(label: QLabel) -> str:
    doc = QTextDocument()
    doc.setHtml(label.text())
    return doc.toPlainText()


def test_onnara_guide_text_is_unchanged_from_v46():
    assert UPDATE_GUIDE_TITLE == "최신 업데이트 확인 방법"
    assert UPDATE_GUIDE_HIGHLIGHT == "업데이트 파일은 온나라 커뮤니티 게시물의 첨부파일로 배포됩니다."
    assert ONNARA_STEPS == (
        "온나라 커뮤니티를 엽니다.",
        "지식 > 업무용 프로그램으로 이동합니다.",
        '검색창에 "기후노트"를 입력합니다.',
        "가장 최근 등록된 업데이트 글을 열고 첨부파일을 내려받습니다.",
        "기존 파일을 지우고, 새로 받은 파일을 실행합니다.",
    )
    text = update_guide_text()
    assert text.startswith(UPDATE_GUIDE_HIGHLIGHT)
    assert "5. 기존 파일을 지우고, 새로 받은 파일을 실행합니다." in text
    assert text.endswith(f"현재 앱 버전: {APP_VERSION}")


def test_gitlab_address_is_the_latest_release_permalink():
    # 새 버전을 올리면 이 주소가 그 버전 페이지로 이동한다(2026-11-04 v4.6으로 이동 확인).
    assert GITLAB_LATEST_URL == "https://gitlab.aigov.go.kr/whrhkdrh/climate-note/-/releases/permalink/latest"


@pytest.mark.parametrize(("parent_width", "expected"), [(460, 404), (380, 340), (1880, 420)])
def test_dialog_width_follows_calendar_size(qtbot, qapp, parent_width, expected):
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(parent_width, 660)
    assert update_guide_dialog_width(parent) == expected
    assert update_guide_dialog_width(None) == 404


def test_choice_page_shows_two_colored_tiles(qtbot, calendar, opened):
    dlg = _open(qtbot, calendar)

    assert dlg.choice_page.isVisible() and not dlg.onnara_page.isVisible()
    assert dlg.widget.width() == 404
    assert dlg.widget.height() <= calendar.height()
    onnara, gitlab = dlg.onnara_tile, dlg.gitlab_tile
    assert onnara.accessibleName() == "온나라 시스템에서 받기"
    assert gitlab.accessibleName() == "GitLab에서 받기"
    assert onnara.chip.text() == "공공기관 업무망" and gitlab.chip.text() == "외부 인터넷망"
    assert onnara.hint.text() == "받는 방법 보기" and gitlab.hint.text() == "브라우저로 열기"
    # 좌우로 나란히, 같은 크기
    assert onnara.geometry().right() < gitlab.geometry().left()
    assert onnara.geometry().top() == gitlab.geometry().top()
    assert onnara.size() == gitlab.size()
    # 실제로 그려진 바탕색(QSS가 다른 규칙에 덮이지 않았는지): 온나라 연한 초록, GitLab 연한 파랑, 버전 꼬리표 회색
    assert _pixel(onnara, 10, onnara.height() // 2) == ONNARA["bg"]
    assert _pixel(gitlab, 10, gitlab.height() // 2) == GITLAB["bg"]
    pill = dlg.findChild(QLabel, "updateVersionPill")
    assert pill.text() == f"현재 {APP_VERSION}"
    assert _pixel(pill, 4, pill.height() // 2) == "#F1F4F9"
    assert opened == []


def test_onnara_tile_switches_to_guide_and_back_without_browser(qtbot, calendar, opened):
    dlg = _open(qtbot, calendar)

    qtbot.mouseClick(dlg.onnara_tile, Qt.LeftButton)
    assert dlg.onnara_page.isVisible() and not dlg.choice_page.isVisible()
    assert dlg.isVisible()
    assert dlg.widget.height() <= calendar.height()
    assert [_plain(label) for label in dlg.step_labels] == list(ONNARA_STEPS)
    texts = [label.text() for label in dlg.onnara_page.findChildren(QLabel)]
    assert UPDATE_GUIDE_TITLE in texts and UPDATE_GUIDE_HIGHLIGHT in texts
    assert f"현재 앱 버전: <b>{APP_VERSION}</b>" in texts
    numbers = [label for label in dlg.onnara_page.findChildren(QLabel, "updateStepNumber")]
    assert [n.text() for n in numbers] == ["1", "2", "3", "4", "5"]
    assert _pixel(numbers[0], 11, 4) == ONNARA["accent"]  # 번호 동그라미가 초록으로 그려진다

    qtbot.mouseClick(dlg.back_button, Qt.LeftButton)
    assert dlg.choice_page.isVisible() and not dlg.onnara_page.isVisible()
    assert dlg.isVisible()
    assert opened == []


def test_gitlab_tile_opens_browser_and_closes(qtbot, calendar, opened):
    dlg = _open(qtbot, calendar)

    qtbot.mouseClick(dlg.gitlab_tile, Qt.LeftButton)

    assert opened == [GITLAB_LATEST_URL]
    qtbot.waitUntil(lambda: not dlg.isVisible())
    assert dlg.result() == QDialog.Accepted


def test_close_button_closes_without_browser(qtbot, calendar, opened):
    dlg = _open(qtbot, calendar)

    qtbot.mouseClick(dlg.close_button, Qt.LeftButton)

    qtbot.waitUntil(lambda: not dlg.isVisible())
    assert dlg.result() == QDialog.Rejected
    assert opened == []


# ── ④ 새 버전이 있으면 GitLab 타일 강조 ─────────────────────

def test_ripple_follows_design_keyframes():
    assert ripple_state(0) == (0.0, 0.55)
    assert ripple_state(560) == pytest.approx((10.5, 0.1375))  # 0.5 지점, ease-out(1-(1-p)²)
    assert ripple_state(1120) == (0.0, 0.0)  # 70%에서 끝나고 나머지는 쉰다
    assert ripple_state(1600) == ripple_state(0)


def test_arrow_rises_two_pixels_and_returns():
    assert (arrow_offset(0), arrow_offset(800), arrow_offset(1600)) == (0, 2, 0)
    assert {arrow_offset(t) for t in range(0, 1600, 33)} == {0, 1, 2}


def test_unknown_latest_keeps_b_design(qtbot, calendar, opened, motion_on):
    dlg = _open(qtbot, calendar)
    gitlab = dlg.gitlab_tile
    assert dlg.findChild(QLabel, "updateNewVersionPill") is None
    assert dlg.here_badge is None and dlg._ripple is None
    assert gitlab.hint.text() == "브라우저로 열기"
    assert _pixel(gitlab, 1, gitlab.height() // 2) == GITLAB["bg"]
    assert not dlg._motion_timer.isActive()


def test_new_version_row_and_tile(qtbot, calendar, opened, motion_on):
    dlg = _open(qtbot, calendar, "v4.7")
    current = dlg.findChild(QLabel, "updateVersionPill")
    new = dlg.findChild(QLabel, "updateNewVersionPill")
    assert current.text() == f"현재 {APP_VERSION}" and new.text() == "새 v4.7"
    assert current.geometry().right() < new.geometry().left()
    assert _pixel(new, 4, new.height() // 2) == "#1D4ED8"
    gitlab = dlg.gitlab_tile
    assert gitlab.hint.text() == "v4.7 받으러 가기"
    middle = gitlab.height() // 2
    assert _pixel(gitlab, 0, middle) == _pixel(gitlab, 1, middle) == "#1D4ED8"
    assert "여기서 받으세요" in gitlab.accessibleDescription()


def test_hover_and_focus_keep_two_pixel_border(qtbot, calendar, opened, motion_on):
    dlg = _open(qtbot, calendar, "v4.7")
    gitlab = dlg.gitlab_tile
    gitlab.setFocus()
    qtbot.mouseMove(gitlab, QPoint(20, 20))
    assert _pixel(gitlab, 1, gitlab.height() // 2) == "#1D4ED8"


def test_badge_straddles_top_edge(qtbot, calendar, opened, motion_on):
    dlg = _open(qtbot, calendar, "v4.7")
    badge, tile = dlg.here_badge, dlg.gitlab_tile
    at = tile.mapTo(dlg.widget, QPoint(0, 0))
    assert badge.parent() is dlg.widget and badge.text() == "여기서 받으세요"
    assert badge.y() == at.y() - 12
    assert abs(badge.geometry().center().x() - (at.x() + tile.width() // 2)) <= 1
    assert badge.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert dlg.widget.height() <= calendar.height()
    spot = QPoint(tile.width() // 2, 3)
    under = dlg.widget.childAt(at + spot)  # 꼬리표가 입력을 막지 않고 타일이 받는다
    assert under is tile or tile.isAncestorOf(under)
    qtbot.mouseClick(tile, Qt.LeftButton, pos=spot)
    assert opened == [GITLAB_LATEST_URL]


def test_motion_runs_only_on_visible_choice_page(qtbot, calendar, opened, motion_on):
    dlg = _open(qtbot, calendar, "v4.7")
    timer = dlg._motion_timer
    assert timer.isActive() and timer.interval() >= 33
    assert dlg._ripple.isVisible()
    dlg.show_onnara_guide()
    assert not timer.isActive() and not dlg.here_badge.isVisible() and not dlg._ripple.isVisible()
    dlg.show_choice()
    assert timer.isActive() and dlg.here_badge.isVisible()
    dlg.reject()
    qtbot.waitUntil(lambda: not dlg.isVisible())
    assert not timer.isActive()


def test_motion_off_keeps_border_and_badge(qtbot, calendar, opened, monkeypatch):
    monkeypatch.setattr(ui_update, "motion_allowed", lambda: False)
    dlg = _open(qtbot, calendar, "v4.7")
    assert not dlg._motion_timer.isActive()
    assert dlg._ripple.isHidden() and dlg.here_badge.isVisible()
    assert _pixel(dlg.gitlab_tile, 1, dlg.gitlab_tile.height() // 2) == "#1D4ED8"


def test_motion_stops_while_calendar_is_hidden(qtbot, calendar, opened, motion_on):
    dlg = _open(qtbot, calendar, "v4.7")
    calendar.hide()
    assert not dlg._motion_timer.isActive()
    calendar.show()
    assert dlg._motion_timer.isActive()


def test_arrow_returns_home_when_motion_stops(qtbot, calendar, opened, motion_on):
    dlg = _open(qtbot, calendar, "v4.7")
    dlg.show_onnara_guide()
    arrow = dlg.gitlab_tile.hint_icon
    home = arrow.pos()
    dlg.show_choice()
    qtbot.waitUntil(lambda: arrow.pos() != home)
    assert abs(arrow.x() - home.x()) <= 2 and abs(arrow.y() - home.y()) <= 2
    dlg.show_onnara_guide()
    assert arrow.pos() == home


def test_ripple_stays_inside_card(qtbot, calendar, opened, motion_on):
    dlg = _open(qtbot, calendar, "v4.7")
    assert dlg._ripple.parent() is dlg.widget
    assert dlg.widget.rect().contains(dlg._ripple.geometry())
    tile_at = dlg.gitlab_tile.mapTo(dlg.widget, QPoint(0, 0))
    assert dlg._ripple.geometry().topLeft() == tile_at - QPoint(14, 14)


def test_long_tag_fits_narrow_dialog(qtbot, qapp, opened, motion_on):
    parent = QWidget()
    parent.resize(380, 660)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitExposed(parent)
    dlg = _open(qtbot, parent, "v4.10a")
    tile = dlg.gitlab_tile
    new = dlg.findChild(QLabel, "updateNewVersionPill")
    assert dlg.widget.width() == 340
    assert tile.hint.width() >= tile.hint.sizeHint().width()
    assert tile.hint_icon.geometry().right() <= tile.width()
    assert new.mapTo(dlg.widget, QPoint(new.width(), 0)).x() <= 340 - 20


@pytest.mark.parametrize("name", sorted(ICONS))
def test_line_icons_render(qapp, name):
    image = icon_pixmap(name, ONNARA["accent"], 24).toImage()
    painted = sum(1 for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 0)
    assert painted > 20
