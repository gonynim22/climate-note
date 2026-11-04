"""'앱 업데이트' 안내창(2026-11-04 B안): 받는 곳 두 갈래, 온나라 안내 문구 유지, GitLab은 브라우저로만 연다."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QWidget

import ui_update
from app_info import APP_VERSION
from ui_update import (
    GITLAB, GITLAB_LATEST_URL, ICONS, ONNARA, ONNARA_STEPS, UPDATE_GUIDE_HIGHLIGHT, UPDATE_GUIDE_TITLE,
    UpdateGuideDialog, icon_pixmap, update_guide_dialog_width, update_guide_text,
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


def _open(qtbot, parent) -> UpdateGuideDialog:
    dlg = UpdateGuideDialog(parent)
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


@pytest.mark.parametrize("name", sorted(ICONS))
def test_line_icons_render(qapp, name):
    image = icon_pixmap(name, ONNARA["accent"], 24).toImage()
    painted = sum(1 for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 0)
    assert painted > 20
