"""Update guide dialog shared by the main window and settings."""

from PySide6.QtCore import Qt

from qfluentwidgets import MessageBox

from app_info import APP_VERSION


UPDATE_GUIDE_HIGHLIGHT = "업데이트 파일은 온나라 커뮤니티 게시물의 첨부파일로 배포됩니다."
UPDATE_GUIDE_URL = "https://www.onnara.go.kr/kndg/home/kngList"


def update_guide_text() -> str:
    return (
        f"{UPDATE_GUIDE_HIGHLIGHT}\n\n"
        "1. 온나라 커뮤니티를 엽니다.\n"
        "2. 지식 > 업무용 프로그램으로 이동합니다.\n"
        "3. 검색창에 \"기후노트\"를 입력합니다.\n"
        "4. 가장 최근 등록된 업데이트 글을 열고 첨부파일을 내려받습니다.\n\n"
        "5. 기존 파일을 지우고, 새로 받은 파일을 실행합니다.\n\n"
        f"현재 앱 버전: {APP_VERSION}"
    )


def update_guide_html() -> str:
    return f"""
<div style="font-size:12px; color:#3F4852; line-height:145%;">
  <table width="100%" cellspacing="0" cellpadding="8">
    <tr>
      <td bgcolor="#F7F6F3">
        <span style="font-weight:600; color:#2F3437;">{UPDATE_GUIDE_HIGHLIGHT}</span>
      </td>
    </tr>
  </table>
  <ol style="margin-top:12px; margin-left:18px;">
    <li>온나라 커뮤니티를 엽니다.</li>
    <li>지식 &gt; 업무용 프로그램으로 이동합니다.</li>
    <li>검색창에 <b>"기후노트"</b>를 입력합니다.</li>
    <li>가장 최근 등록된 업데이트 글을 열고 첨부파일을 내려받습니다.</li>
    <li>기존 파일을 지우고, 새로 받은 파일을 실행합니다.</li>
  </ol>
  <p style="margin-top:12px; color:#687076;">현재 앱 버전: <b>{APP_VERSION}</b></p>
</div>
"""


def update_guide_dialog_size(parent=None) -> tuple[int, int]:
    if parent is None:
        return 460, 330
    width = min(460, max(320, parent.width() - 40))
    height = min(360, max(320, parent.height() - 80))
    return width, height


def show_update_guide(parent=None) -> None:
    dlg = MessageBox("최신 업데이트 확인 방법", update_guide_text(), parent)
    dialog_width, dialog_height = update_guide_dialog_size(parent)
    dlg.contentLabel.setTextFormat(Qt.RichText)
    dlg.contentLabel.setWordWrap(True)
    dlg.contentLabel.setFixedWidth(dialog_width - 48)
    dlg.contentLabel.setText(update_guide_html())
    dlg.contentLabel.setStyleSheet("""
        BodyLabel#contentLabel {
            color: #3F4852;
            font-size: 12px;
            line-height: 18px;
        }
    """)
    dlg.textLayout.setSpacing(10)
    dlg.widget.setFixedSize(dialog_width, dialog_height)
    dlg.yesButton.setText("닫기")
    dlg.cancelButton.hide()
    dlg.exec()
