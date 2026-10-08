"""화면 글자 따기 인식 엔진: 번들 모델 무결성과 전후처리, 실제 모델 인식."""
import hashlib
import json
from pathlib import Path

from app_paths import resource_root

MODEL_DIR = resource_root() / "screen_text" / "models"


def test_manifest_matches_bundled_files():
    with open(MODEL_DIR / "MANIFEST.json", encoding="utf-8") as stream:
        manifest = json.load(stream)
    assert manifest["license"] == "Apache-2.0"
    assert {entry["role"] for entry in manifest["files"]} == {"det", "rec", "dict"}
    for entry in manifest["files"]:
        path = MODEL_DIR / entry["name"]
        with open(path, "rb") as stream:
            data = stream.read()
        assert len(data) == entry["size"], entry["name"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["name"]
    with open(MODEL_DIR / "LICENSE", encoding="utf-8") as stream:
        assert "Apache License" in stream.read()
