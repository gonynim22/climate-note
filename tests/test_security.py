# tests/test_security.py - 암호화, 경로 검증, Salt 재설정 테스트
import pytest
import security


class TestEncryptDecrypt:
    def test_basic_roundtrip(self, app_dir):
        text = "안녕하세요"
        assert security.decrypt(security.encrypt(text)) == text

    def test_empty_string(self, app_dir):
        assert security.decrypt(security.encrypt("")) == ""

    def test_korean_text(self, app_dir):
        text = "기후에너지환경부 보문산불주먹"
        assert security.decrypt(security.encrypt(text)) == text

    def test_long_text_10k_chars(self, app_dir):
        text = "가나다라마바사아자차카타파하" * 500
        assert security.decrypt(security.encrypt(text)) == text

    def test_special_chars(self, app_dir):
        text = "!@#$%^&*()_+{}|:<>?'\""
        assert security.decrypt(security.encrypt(text)) == text

    def test_sql_injection_string(self, app_dir):
        text = "'; DROP TABLE schedules; --"
        assert security.decrypt(security.encrypt(text)) == text

    def test_html_content(self, app_dir):
        text = "<b>굵게</b><span style='color:red'>빨강</span>"
        assert security.decrypt(security.encrypt(text)) == text

    def test_emoji(self, app_dir):
        text = "회의 완료 ✅ 🎉 🔥 점심 🍜"
        assert security.decrypt(security.encrypt(text)) == text

    def test_newlines_and_tabs(self, app_dir):
        text = "1줄\n2줄\n\t들여쓰기"
        assert security.decrypt(security.encrypt(text)) == text

    def test_ciphertext_not_plaintext(self, app_dir):
        text = "비밀 내용"
        cipher = security.encrypt(text)
        assert text not in cipher
        assert cipher != text

    def test_nonce_different_each_time(self, app_dir):
        """Fernet은 매번 다른 암호문 생성 (nonce 포함)"""
        text = "동일한 텍스트"
        assert security.encrypt(text) != security.encrypt(text)

    def test_invalid_ciphertext_raises(self, app_dir):
        with pytest.raises(Exception):
            security.decrypt("invalid_ciphertext_that_cannot_be_decrypted")

    def test_empty_ciphertext_raises(self, app_dir):
        with pytest.raises(Exception):
            security.decrypt("")


class TestPinEncryptDecrypt:
    def test_roundtrip(self, app_dir):
        data = b"export data content"
        encrypted = security.encrypt_with_pin(data, "1234")
        assert security.decrypt_with_pin(encrypted, "1234") == data

    def test_wrong_pin_raises(self, app_dir):
        data = b"secret data"
        encrypted = security.encrypt_with_pin(data, "1234")
        with pytest.raises(Exception):
            security.decrypt_with_pin(encrypted, "9999")

    def test_too_short_data_raises(self, app_dir):
        with pytest.raises(ValueError):
            security.decrypt_with_pin(b"short", "1234")

    def test_korean_data(self, app_dir):
        data = "한글 데이터 내용 🎉".encode("utf-8")
        encrypted = security.encrypt_with_pin(data, "0000")
        assert security.decrypt_with_pin(encrypted, "0000") == data

    def test_pin_0000(self, app_dir):
        data = b"zero pin test"
        encrypted = security.encrypt_with_pin(data, "0000")
        assert security.decrypt_with_pin(encrypted, "0000") == data

    def test_large_data(self, app_dir):
        data = ("가나다라" * 5000).encode("utf-8")  # ~20KB
        encrypted = security.encrypt_with_pin(data, "1234")
        assert security.decrypt_with_pin(encrypted, "1234") == data


class TestPathValidation:
    def test_valid_path_passes(self, app_dir):
        valid = app_dir / "calendar.db"
        result = security.validate_app_path(valid, "DB")
        assert result == valid.resolve()

    def test_path_traversal_blocked(self, app_dir):
        evil = app_dir / ".." / "evil.db"
        with pytest.raises(ValueError, match="조작이 감지"):
            security.validate_app_path(evil, "DB")

    def test_nested_valid_path(self, app_dir):
        nested = app_dir / "backups" / "backup.db"
        (app_dir / "backups").mkdir(exist_ok=True)
        result = security.validate_app_path(nested, "Backup")
        assert result == nested.resolve()


class TestSaltReset:
    def test_reset_invalidates_old_ciphertext(self, app_dir):
        """Salt 재설정 후 이전 암호문 복호화 실패해야 함"""
        cipher = security.encrypt("테스트")
        security.reset_salt()
        with pytest.raises(Exception):
            security.decrypt(cipher)

    def test_new_encryption_works_after_reset(self, app_dir):
        security.reset_salt()
        text = "리셋 후 새 암호화"
        assert security.decrypt(security.encrypt(text)) == text

    def test_reset_clears_cache(self, app_dir):
        security.encrypt("캐시 초기화 전")
        assert security._fernet_cache is not None
        security.reset_salt()
        assert security._fernet_cache is None
