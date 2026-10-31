"""Bundled Fluent UI System Icons helpers."""

from functools import lru_cache
from pathlib import Path
import re

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app_paths import resource_root


_ICON_DIR = Path("resources") / "fluent_icons"
_HEX_FILL_RE = re.compile(r'fill="#[0-9A-Fa-f]{6}"')
_KEEP_COLOR_SUFFIX = "_color"


def fluent_icon_path(name: str) -> Path:
    return resource_root() / _ICON_DIR / f"{name}.svg"


def _tint_svg(svg_text: str, color: str) -> str:
    resolved = QColor(color).name()
    return _HEX_FILL_RE.sub(f'fill="{resolved}"', svg_text)


@lru_cache(maxsize=96)
def fluent_icon(name: str, color: str = "#212121", size: int = 24) -> QIcon:
    path = fluent_icon_path(name)
    if not path.exists():
        return QIcon()

    with open(path, encoding="utf-8") as f:
        svg_text = f.read()

    if not name.endswith(_KEEP_COLOR_SUFFIX):
        svg_text = _tint_svg(svg_text, color)

    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)
