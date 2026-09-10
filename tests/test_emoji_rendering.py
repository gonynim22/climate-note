"""컬러 글리프의 원본 비트맵과 화면 렌더 사이의 하단·우측 유실 회귀."""
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QFont, QImage, QPainter, QRawFont


def _ink_size(image):
    pixels = [(x, y) for y in range(image.height()) for x in range(image.width())
              if image.pixelColor(x, y).alpha() > 0]
    assert pixels, "이모지 렌더가 비어 있습니다."
    return (max(x for x, y in pixels) - min(x for x, y in pixels) + 1,
            max(y for x, y in pixels) - min(y for x, y in pixels) + 1)


@pytest.mark.parametrize("emoji,pixel_size", [
    ("🙂", 20), ("🎯", 14), ("🎯", 22), ("📚", 22), ("⏰", 22),
])
def test_color_emoji_glyph_retains_bitmap_edges(qapp, emoji, pixel_size):
    font = QFont("Segoe UI Emoji")
    font.setPixelSize(pixel_size)
    raw = QRawFont.fromFont(font)
    glyphs = raw.glyphIndexesForString(emoji)
    assert len(glyphs) == 1 and glyphs[0] != 0
    # alphaMapForGlyph는 컬러 폰트의 ARGB 비트맵을 직접 반환한다.
    # Qt 6.10.2의 글리프 캐시 경로는 이 비트맵의 하단·우측을 잘랐다.
    complete = raw.alphaMapForGlyph(glyphs[0])
    rendered = QImage(80, 80, QImage.Format_ARGB32_Premultiplied)
    rendered.fill(Qt.transparent)
    painter = QPainter(rendered)
    painter.setFont(font)
    painter.drawText(QPointF(20, 45), emoji)
    painter.end()
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        output = Path(appdata).parent
        name = f"emoji-glyph-{ord(emoji):x}-{pixel_size}"
        assert complete.save(str(output / f"{name}-bitmap.png"))
        assert rendered.save(str(output / f"{name}-rendered.png"))
    assert _ink_size(rendered) == _ink_size(complete)
