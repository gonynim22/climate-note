"""Application metadata shared by UI and build scripts."""

APP_DISPLAY_NAME = "기후노트"
APP_VERSION = "v3.8e"
APP_RELEASE_DATE = "2026. 10. 5."
APP_AUTHOR = "기후에너지환경부 보문산불주먹 (ggjo@korea.kr)"


def app_credit_text() -> str:
    return f"{APP_VERSION}  ·  {APP_RELEASE_DATE}  ·  만든이: {APP_AUTHOR}"


def app_exe_name() -> str:
    return f"{APP_DISPLAY_NAME}_{APP_VERSION}.exe"
