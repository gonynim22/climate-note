from pathlib import Path
import logging

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from qfluentwidgets.common.font import setFontFamilies


FONT_DIR = Path(__file__).resolve().parent / "fonts"

DEFAULT_APP_FONT = "Malgun Gothic"
APP_FONT_OPTIONS = [
    ("맑은 고딕", "Malgun Gothic"),
]
SYSTEM_FONT_PREFIX = "system:"

_APP_FONT_FILES = {}
_ICON_FONT_FILES = ("fa-regular-400.ttf", "fa-solid-900.ttf")
# 번들 UI 강조 폰트(Pretendard) — D-Day 위젯 등에서 사용. 앱 본문 폰트는 아님.
_UI_FONT_FILES = (
    "Pretendard-Medium.ttf",
    "Pretendard-SemiBold.ttf",
    "Pretendard-Bold.ttf",
    "Pretendard-ExtraBold.ttf",
)
_FONT_FALLBACKS = ("Malgun Gothic", "Segoe UI")
_loaded_font_files: dict[Path, list[str]] = {}
_loaded_font_families: set[str] = set()


def _load_font_file(path: Path, logger: logging.Logger | None = None) -> list[str]:
    if not path.exists():
        if logger:
            logger.warning("폰트 파일 없음: %s", path.name)
        return []

    if path in _loaded_font_files:
        return _loaded_font_files[path]

    font_id = QFontDatabase.addApplicationFont(str(path))
    if font_id < 0:
        if logger:
            logger.error("폰트 로드 실패: %s", path.name)
        return []

    families = QFontDatabase.applicationFontFamilies(font_id)
    _loaded_font_files[path] = families
    _loaded_font_families.update(families)
    return families


def load_app_fonts(logger: logging.Logger | None = None) -> None:
    for file_names, _preferred_family in _APP_FONT_FILES.values():
        for file_name in file_names:
            _load_font_file(FONT_DIR / file_name, logger)


def load_icon_fonts(logger: logging.Logger | None = None) -> None:
    for file_name in _ICON_FONT_FILES:
        _load_font_file(FONT_DIR / file_name, logger)


def load_ui_fonts(logger: logging.Logger | None = None) -> None:
    """번들 UI 강조 폰트(Pretendard) 로드. 미존재/실패해도 앱 폰트로 폴백."""
    for file_name in _UI_FONT_FILES:
        _load_font_file(FONT_DIR / file_name, logger)


def resolve_app_font_family(font_key: str) -> str:
    font_key = font_key or DEFAULT_APP_FONT
    if font_key.startswith(SYSTEM_FONT_PREFIX):
        font_key = font_key[len(SYSTEM_FONT_PREFIX):]
    preferred = _APP_FONT_FILES.get(font_key, (None, font_key))[1]
    families = set(QFontDatabase.families()) | _loaded_font_families
    if preferred in families:
        return preferred
    if font_key in families:
        return font_key

    if DEFAULT_APP_FONT in families:
        return DEFAULT_APP_FONT

    if "Segoe UI" in families:
        return "Segoe UI"
    return DEFAULT_APP_FONT


def app_font_families(font_key: str) -> list[str]:
    primary = resolve_app_font_family(font_key)
    families = [primary]
    for family in _FONT_FALLBACKS:
        if family not in families:
            families.append(family)
    return families


def apply_app_font(font_key: str, app: QApplication | None = None) -> str:
    load_app_fonts()
    target_app = app or QApplication.instance()
    family = resolve_app_font_family(font_key)
    families = app_font_families(font_key)
    setFontFamilies(families, save=False)
    if target_app is not None:
        font = QFont()
        font.setFamilies(families)
        font.setPointSize(10)
        target_app.setFont(font)
    return family


def system_font_key(family: str) -> str:
    return f"{SYSTEM_FONT_PREFIX}{family}"


def system_font_family_from_key(font_key: str) -> str:
    return font_key[len(SYSTEM_FONT_PREFIX):] if font_key.startswith(SYSTEM_FONT_PREFIX) else font_key


def available_system_fonts() -> list[str]:
    load_app_fonts()
    recommended = {value for _label, value in APP_FONT_OPTIONS}
    preferred = {family for _file_names, family in _APP_FONT_FILES.values()}
    bundled = recommended | preferred | _loaded_font_families
    fonts = sorted(set(QFontDatabase.families()), key=str.casefold)
    return [
        family for family in fonts
        if family not in bundled
    ]
