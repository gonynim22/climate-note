"""서버 push 보안 검사(Semgrep)와 기관 소스 점검 지적의 재발 방지. 추적 Python 파일만 검사한다."""
import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SELF = "tests/test_security_scan_rules.py"
_STDLIB_XML_IMPORT = re.compile(r"^\s*(import\s+xml\b|from\s+xml(\.|\s))", re.M)
_URLOPEN_CALL = re.compile(r"\burlopen\s*\(")
_SUBMITTED_FOLDERS = ("src/", "screen_text/")  # 기관 소스 점검에 내는 코드는 이 두 폴더와 루트 스크립트다


def _tracked_python_files():
    names = subprocess.run(["git", "ls-files", "-z", "*.py"], cwd=ROOT, check=True,
                           capture_output=True).stdout.decode("utf-8").split("\0")
    return [ROOT / name for name in names if name and name != _SELF]


def _offenders(pattern):
    return [path.relative_to(ROOT).as_posix() for path in _tracked_python_files()
            if pattern.search(path.read_text(encoding="utf-8"))]


def _submitted_sources():
    """기관 소스 점검에 내는 코드의 (경로, 본문)."""
    for path in _tracked_python_files():
        name = path.relative_to(ROOT).as_posix()
        if "/" not in name or name.startswith(_SUBMITTED_FOLDERS):
            yield name, path.read_text(encoding="utf-8")


def test_tracked_python_reads_xml_with_defusedxml():
    assert _offenders(_STDLIB_XML_IMPORT) == []


def test_tracked_python_has_no_dynamic_urlopen():
    assert _offenders(_URLOPEN_CALL) == []


def _random_imports(source):
    """`random` 모듈을 import하는 줄 번호."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names = [node.module or ""]
        else:
            continue
        if any(name.split(".")[0] == "random" for name in names):
            lines.append(node.lineno)
    return lines


def test_random_import_finder_sees_every_import_form():
    source = "import os, random\nimport random as r\nfrom random import choice\nimport secrets\nfrom os import path\n"
    assert _random_imports(source) == [1, 2, 3]


def test_submitted_code_picks_at_random_with_secrets():
    # 기관 소스 점검은 보안과 무관한 문구 고르기에 쓴 random import도 지적했다(2026-11-11).
    # tests/·tools/의 합성 자료 생성은 점검에 내지 않으므로 seed를 주는 random을 그대로 쓴다.
    found = [f"{name}:{line}" for name, source in _submitted_sources() for line in _random_imports(source)]
    assert found == []


def _ip_named_literals(source):
    """이름이 `ip`로 끝나는 변수·속성에 문자열(f-string 포함)을 넣는 문장의 줄 번호."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        else:
            continue
        literal = isinstance(node.value, ast.JoinedStr) or (
            isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))
        names = [target.id if isinstance(target, ast.Name) else target.attr
                 for target in targets if isinstance(target, (ast.Name, ast.Attribute))]
        if literal and any(name.lower().endswith("ip") for name in names):
            lines.append(node.lineno)
    return lines


def test_ip_named_literal_finder_matches_only_names_ending_in_ip():
    source = ('tooltip += "\\n이 날만 수정됨"\n'
              'COLOR_BUTTON_TOOLTIP = "누를 때마다 다음 색"\n'
              'self.server_ip = f"{host}"\n'
              'tip: str = "x"\n'
              'description += ", 포모도로"\n'
              'TIPS_TEXT = "x"\n'
              'make(chip="x")\n'
              'tooltip = build()\n'
              'tooltip_text = "x"\n'
              'skip = 3\n')
    assert _ip_named_literals(source) == [1, 2, 3, 4]


def test_submitted_code_keeps_text_out_of_names_ending_in_ip():
    # 기관 소스 점검은 이름이 ip로 끝나는 변수(tooltip)에 넣은 화면 문구를 하드코드된 중요정보로 지적했다(2026-11-11).
    # ip가 이름 가운데 있는 description·TIPS_TEXT와 키워드 인자 chip="…"은 지적되지 않았다.
    found = [f"{name}:{line}" for name, source in _submitted_sources() for line in _ip_named_literals(source)]
    assert found == []
