"""Synthetic paths only; the storage proof also exercises Qt's old plain editor."""
import pytest

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextDocument
from sticky_file_links import FileLink, decode


def test_qt_anchor_storage_proof(qapp):
    path = 'C:\\합성 자료\\보고서 & # % \' 😀.pdf'
    href = FileLink(path, 'a' * 64, 'b' * 32, 0).href()
    document = QTextDocument()
    cursor = QTextCursor(document)
    fmt = QTextCharFormat()
    fmt.setForeground(QColor('#7B1FA2'))
    fmt.setFontUnderline(False)
    fmt.setFontWeight(700)
    fmt.setAnchor(True)
    fmt.setAnchorHref(href)
    cursor.insertText('☐ 문서 😀', fmt)
    for _ in range(3):
        html = document.toHtml()
        document.setHtml(html)
        fragment = document.begin().begin().fragment()
        assert fragment.charFormat().anchorHref() == href
        assert fragment.charFormat().foreground().color().name() == '#7b1fa2'
        # Qt adds its anchor underline on reload; original underline travels in href.
        assert decode(fragment.charFormat().anchorHref()).underline == 0
        assert fragment.charFormat().fontWeight() == 700
        assert document.toPlainText() == '☐ 문서 😀'


@pytest.mark.parametrize('path', [
    r'\\server\share\x.pdf', r'C:relative.pdf', r'C:\a\..\b.pdf', r'C:\CON.txt',
    r'C:\a.exe', r'C:\a.PS1', r'C:\a.lnk', r'C:\a.url', r'C:\a.pdf:stream',
    r'C:\a.pdf ', 'https://example.com/a.pdf', r'\\?\C:\a.pdf',
])
def test_unsupported_paths(path):
    from sticky_file_links import new_link
    with pytest.raises(ValueError):
        new_link(path, 'a' * 64)


def test_invalid_metadata():
    from sticky_file_links import new_link
    href = new_link(r'C:\synthetic.pdf', 'a' * 64).href()
    assert decode(href)
    for bad in [href + '&u=0', href.replace('//v1', '//v9'), href + '#fragment',
                href.replace('origin=', 'other='), 'file:///C:/synthetic.pdf']:
        assert decode(bad) is None


def test_origin_does_not_touch_crypto_or_salt(app_dir, monkeypatch):
    import security
    monkeypatch.setattr(security, '_get_hardware_id', lambda: 'synthetic-machine-user')
    monkeypatch.setenv('USERNAME', 'synthetic')
    def forbidden():
        raise AssertionError('link origin must not derive keys or read/create salt')
    monkeypatch.setattr(security, '_get_fernet', forbidden)
    monkeypatch.setattr(security, '_load_or_create_salt', forbidden)
    first = security.file_link_origin()
    assert len(first) == 64 and security.file_link_origin() == first
    monkeypatch.setattr(security, '_get_hardware_id', lambda: 'other-synthetic-machine')
    assert security.file_link_origin() != first
