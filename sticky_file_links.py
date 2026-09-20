"""Versioned sticky-file anchors. No database, Qt, or file mutation."""
from dataclasses import dataclass
import ctypes
import ntpath
import os
import re
import stat
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

PREFIX = "climatenote-file:"
UNSUPPORTED = (
    "로컬 일반 파일만 연결할 수 있습니다. 폴더, 네트워크 경로, "
    "실행 파일·스크립트·바로가기는 지원하지 않습니다."
)
_BLOCKED = frozenset(('.exe .com .bat .cmd .ps1 .psm1 .psd1 .vbs .vbe '
                      '.js .jse .wsf .wsh .msi .msp .scr .pif .hta .cpl '
                      '.lnk .url .reg .msc .chm .appref-ms .application '
                      '.jar .py .pyw .sh .bash .shb .scf .sct .inf .ins .isp').split())


@dataclass(frozen=True)
class FileLink:
    path: str
    origin: str
    identity: str
    underline: int = 0

    def href(self) -> str:
        return 'climatenote-file://v1?' + urlencode({
            'path': self.path, 'origin': self.origin,
            'id': self.identity, 'u': self.underline,
        })


def local_path(path: str) -> str:
    """Lexical validation only. Drive and resolved-target checks run in a worker."""
    if not isinstance(path, str) or not path or len(path) > 32760:
        raise ValueError(UNSUPPORTED)
    path = path.replace('/', '\\')
    drive, tail = ntpath.splitdrive(path)
    if (not re.fullmatch(r'[A-Za-z]:', drive) or not tail.startswith('\\')
            or any(ord(c) < 32 for c in path) or any(c in tail for c in ':*?"<>|')):
        raise ValueError(UNSUPPORTED)
    parts = tail.split('\\')[1:]
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in parts):
        raise ValueError(UNSUPPORTED)
    if any(re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p)
           for p in parts):
        raise ValueError(UNSUPPORTED)
    if ntpath.splitext(path)[1].lower() in _BLOCKED:
        raise ValueError(UNSUPPORTED)
    return path


def new_link(path: str, origin: str) -> FileLink:
    if not re.fullmatch(r'[0-9a-f]{64}', origin):
        raise ValueError('이 PC의 연결 정보를 확인하지 못했습니다.')
    return FileLink(local_path(path), origin, uuid4().hex)


def decode(href: str) -> FileLink | None:
    try:
        url = urlsplit(href)
        if (url.scheme != 'climatenote-file' or url.netloc != 'v1'
                or url.path or url.fragment or len(href) > 200000):
            return None
        values = parse_qs(url.query, strict_parsing=True, max_num_fields=5)
        if set(values) != {'path', 'origin', 'id', 'u'} or any(len(v) != 1 for v in values.values()):
            return None
        path, origin, identity, underline = (values[k][0] for k in ('path', 'origin', 'id', 'u'))
        if (not re.fullmatch(r'[0-9a-f]{64}', origin)
                or not re.fullmatch(r'[0-9a-f]{32}', identity)
                or underline not in tuple(str(i) for i in range(8))):
            return None
        return FileLink(local_path(path), origin, identity, int(underline))
    except (ValueError, UnicodeError):
        return None


def inspect_file(path: str) -> str:
    """Return a display error or ''. Never run this filesystem work on the GUI thread."""
    try:
        path = local_path(path)
        # Reject mapped network drives before resolve/stat (including disconnected ones).
        get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
        get_drive_type.argtypes = [ctypes.c_wchar_p]
        get_drive_type.restype = ctypes.c_uint
        if get_drive_type(ntpath.splitdrive(path)[0] + '\\') not in (2, 3, 5, 6):
            return UNSUPPORTED
        # Do not follow a local junction/symlink into a network share or executable.
        drive, tail = ntpath.splitdrive(path)
        current = drive + '\\'
        for part in tail.split('\\')[1:]:
            current = ntpath.join(current, part)
            info = os.lstat(current)
            if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                return UNSUPPORTED
        if not stat.S_ISREG(info.st_mode):
            return UNSUPPORTED
        return ''
    except FileNotFoundError:
        return '파일을 찾을 수 없습니다. 이동했거나 삭제되었다면 다시 연결해 주세요.'
    except PermissionError:
        return '파일에 접근할 권한이 없습니다.'
    except ValueError as error:
        return str(error)
    except OSError:
        return '파일 상태를 확인할 수 없습니다. 장치와 접근 권한을 확인해 주세요.'
