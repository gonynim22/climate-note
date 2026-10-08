"""화면 글자 따기 미니앱 (걷어낼 수 있는 선택형 앱). 계약은 docs/SCREEN_TEXT.md를 따른다."""
from app_paths import resource_root
from ui_mini_apps import MiniAppSpec


def _create_window(parent):
    from screen_text.window import ScreenTextWindow  # 타일을 눌렀을 때만 창 모듈을 불러온다
    return ScreenTextWindow(parent)


APP = MiniAppSpec(
    app_id="screen_text",
    title="화면 글자\n따기",
    accessible_name="화면 글자 따기 실행",
    description="이미지·스캔 속 글자를 읽어 복사",
    icon_path=resource_root() / "screen_text" / "icon.svg",
    create_window=_create_window,
)
