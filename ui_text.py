"""사용자 문자열을 Qt의 자동 HTML 판독 없이 표시하는 도우미."""
from html import escape


def plain_tooltip(text: str) -> str:
    # Qt ToolTip에는 TextFormat 설정이 없다. 태그로 오인할 수 있는 원문만
    # escape한 HTML로 감싸며 저장·복사할 본문은 바꾸지 않는다.
    if "<" not in text and "&" not in text:
        return text
    return '<qt><span style="white-space:pre-wrap">' + escape(text) + '</span></qt>'
