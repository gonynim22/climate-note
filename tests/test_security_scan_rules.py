"""서버 push 보안 검사(Semgrep) 지적의 재발 방지. 추적 Python 파일만 검사한다."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SELF = "tests/test_security_scan_rules.py"
_STDLIB_XML_IMPORT = re.compile(r"^\s*(import\s+xml\b|from\s+xml(\.|\s))", re.M)
_URLOPEN_CALL = re.compile(r"\burlopen\s*\(")


def _tracked_python_files():
    names = subprocess.run(["git", "ls-files", "-z", "*.py"], cwd=ROOT, check=True,
                           capture_output=True).stdout.decode("utf-8").split("\0")
    return [ROOT / name for name in names if name and name != _SELF]


def _offenders(pattern):
    return [path.relative_to(ROOT).as_posix() for path in _tracked_python_files()
            if pattern.search(path.read_text(encoding="utf-8"))]


def test_tracked_python_reads_xml_with_defusedxml():
    assert _offenders(_STDLIB_XML_IMPORT) == []


def test_tracked_python_has_no_dynamic_urlopen():
    assert _offenders(_URLOPEN_CALL) == []
