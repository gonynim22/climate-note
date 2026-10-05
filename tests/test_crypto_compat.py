"""cryptography 갱신 회귀: 46.0.4로 만든 합성 키·암호문·PIN 내보내기를 현재 라이브러리가 그대로 읽는다."""
import base64
import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import security

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "crypto_compat_cryptography46.json")
                     .read_text(encoding="utf-8"))
CASES = VECTORS["cases"]
IDS = [case["name"] for case in CASES]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_key_derivation_matches_cryptography46(case):
    key = security._derive_fernet_key(case["material"], bytes.fromhex(case["salt_hex"]))
    assert base64.urlsafe_b64decode(key) == bytes(case["key_bytes"])


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_cryptography46_tokens_decrypt(case):
    fernet = Fernet(base64.urlsafe_b64encode(bytes(case["key_bytes"])))
    for item in case["tokens"]:
        assert fernet.decrypt(base64.urlsafe_b64encode(bytes(item["token_bytes"]))).decode("utf-8") == item["plaintext"]


def test_cryptography46_pin_export_decrypts():
    export = VECTORS["pin_export"]
    data = security.decrypt_with_pin(base64.b64decode(export["blob_b64"]), export["pin"])
    assert data == base64.b64decode(export["data_b64"])


@pytest.mark.parametrize("case", CASES[:2], ids=IDS[:2])
def test_product_decryption_reads_cryptography46_tokens(case, app_dir, monkeypatch):
    """Actual hardware/legacy paths use only synthetic identifiers and salt."""
    salt = bytes.fromhex(case["salt_hex"])
    security.SALT_FILE.write_bytes(salt)
    legacy = case["name"] == "legacy"
    identifier = "_get_legacy_hardware_id" if legacy else "_get_hardware_id"
    monkeypatch.setattr(security, identifier, lambda: case["material"])
    derive = security.derive_legacy_key if legacy else security.derive_key
    decrypt = security.legacy_decrypt if legacy else security.decrypt
    assert base64.urlsafe_b64decode(derive(salt)) == bytes(case["key_bytes"])
    for item in case["tokens"]:
        assert decrypt(base64.urlsafe_b64encode(bytes(item["token_bytes"])).decode("ascii")) == item["plaintext"]
    assert security.SALT_FILE.read_bytes() == salt


def test_new_tokens_keep_fernet_v1_layout():
    fernet = Fernet(base64.urlsafe_b64encode(bytes(CASES[0]["key_bytes"])))
    raw = base64.urlsafe_b64decode(fernet.encrypt("하네스".encode("utf-8")))
    assert raw[0] == 0x80                          # Fernet 버전 바이트
    assert (len(raw) - 1 - 8 - 16 - 32) % 16 == 0  # 시각 8 + IV 16 + AES 블록 + HMAC 32
