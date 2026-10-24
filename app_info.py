"""Application metadata shared by UI and build scripts."""

APP_DISPLAY_NAME = "기후노트"
APP_VERSION = "v4.4b"
APP_RELEASE_DATE = "2026. 10. 25."
APP_CONTACT_EMAIL = "ggjo@korea.kr"
APP_AUTHOR = f"기후에너지환경부 보문산불주먹 ({APP_CONTACT_EMAIL})"


def app_credit_text() -> str:
    return f"{APP_VERSION}  ·  {APP_RELEASE_DATE}  ·  만든이: {APP_AUTHOR}"


def app_exe_name() -> str:
    return f"{APP_DISPLAY_NAME}_{APP_VERSION}.exe"
