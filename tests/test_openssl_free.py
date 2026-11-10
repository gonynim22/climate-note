"""OpenSSL이 없는 EXE에서도 열쇠 재료와 백업 해시가 같은 값인지 고정한다.

배포 EXE에는 Python용 OpenSSL이 없어 hashlib.sha256을 내장 구현이 맡는다. 이 값들은 암호화 열쇠의
재료와 백업 검증에 쓰이므로, 달라지면 사용자가 기존 일정을 읽지 못한다. 기대값은 OpenSSL이 있는
환경에서 뽑았고, 같은 시험을 OpenSSL을 막은 프로세스(tools/run_without_openssl.py)에서도 돌린다.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

import database as db
import security

ROOT = Path(__file__).resolve().parents[1]
GUID = "00000000-1111-2222-3333-444444444444"
NODE = 0x112233445566
# (hardware_id, file_link_origin, legacy_hardware_id) — 2026-11-10 OpenSSL 3.0.16이 있는 환경에서 뽑은 값. 고치지 않는다.
VECTORS = {
    "harness-user": ("7dc650290c0532016a31ed99221d240780f68c6f63a0d69819396a6527bef122",
                     "ce5c1d958955efa62d4355ae0bfb45643c059988471c9b23634fc7b249e08204",
                     "e2ceb572c0de8aa64a1c351a7a3a9772f1d99be6d60d7a952a222c760c7b429f"),
    "홍길동": ("e272fbdcf9540e51e0db27be4c045821cbce4c2e4eae9fade70c22f81aa7c4fc",
               "f9e387933d51b28d46154ee1b35114b4a734364e9ed90c6b73e8fd446d8eff13",
               "0ef15c3856686fb0011a43943124312427bdebabfda6007ddea029cd7a2871a7"),
}


@pytest.mark.parametrize("user", VECTORS)
def test_key_material_matches_values_recorded_with_openssl(monkeypatch, user):
    monkeypatch.setattr(security, "_get_machine_guid", lambda: GUID)
    monkeypatch.setattr(security.uuid, "getnode", lambda: NODE)
    monkeypatch.setenv("USERNAME", user)
    assert (security._get_hardware_id(), security.file_link_origin(),
            security._get_legacy_hardware_id()) == VECTORS[user]


def test_backup_digests_match_values_recorded_with_openssl(tmp_path):
    assert db._bytes_sha256("기후노트 climate-note 2026".encode("utf-8")) == \
        "15dd49ec0a725cf5fe10f114eda32ea8d6ebfe511fb6c5d8150a3b474e3c4286"
    path = tmp_path / "payload.bin"
    path.write_bytes(bytes(range(256)) * 4096 * 3 + b"tail!")
    assert db._file_size_and_sha256(path) == (
        3145733, "9d7fb3c88cbab2d4739c50f9f811e879b3cdc7823aaf496096f14fa61a7a0945")


def test_openssl_is_really_blocked_in_the_no_openssl_run():
    if os.environ.get("CLIMATENOTE_NO_OPENSSL") != "1":
        pytest.skip("OpenSSL을 막은 실행에서만 본다")
    assert "openssl" not in hashlib.sha256.__name__ and not hasattr(hashlib, "pbkdf2_hmac")
    with pytest.raises(ImportError):
        import ssl  # noqa: F401


def test_runner_blocks_openssl_before_pytest_starts(tmp_path):
    if os.environ.get("CLIMATENOTE_NO_OPENSSL") == "1":
        pytest.skip("막은 실행 안에서 다시 띄우지 않는다")
    done = subprocess.run(
        [sys.executable, str(ROOT / "tools/run_without_openssl.py"), "tests/test_openssl_free.py", "-q",
         "-p", "no:cacheprovider", "--basetemp", str(tmp_path / "inner")],
        cwd=ROOT, capture_output=True, encoding="utf-8", timeout=180)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "4 passed, 1 skipped" in done.stdout
