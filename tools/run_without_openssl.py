"""Python용 OpenSSL(_ssl, _hashlib)을 막은 프로세스에서 pytest를 돌린다.

배포 EXE에는 Python용 OpenSSL이 없다. 그 상태의 hashlib·hmac으로도 데이터 검사가 통과하는지 보려고,
어떤 모듈보다 먼저 두 확장 모듈의 import를 막고 pytest를 띄운다(pytest가 먼저 hashlib을 불러오므로
conftest에서 막으면 늦다). 인자는 pytest에 그대로 넘긴다.

    .\\.venv\\Scripts\\python.exe tools/run_without_openssl.py tests/test_openssl_free.py -q
"""
import os
import sys

BLOCKED = ("_ssl", "_hashlib")


def main(argv):
    if "hashlib" in sys.modules or "ssl" in sys.modules:
        print("OpenSSL을 막기 전에 hashlib/ssl이 이미 불려 있습니다.", file=sys.stderr)
        return 3
    for name in BLOCKED:
        sys.modules[name] = None  # None이면 import가 ImportError로 끝난다
    os.environ["CLIMATENOTE_NO_OPENSSL"] = "1"
    # `python -m pytest`와 같은 경로로 맞춘다: 스크립트 폴더(tools/) 대신 프로젝트 루트.
    # 루트의 main·screen_text와 `from tools import verify`를 쓰는 테스트가 그대로 수집돼야 한다.
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    import hashlib
    if "openssl" in hashlib.sha256.__name__ or hasattr(hashlib, "pbkdf2_hmac"):
        print("OpenSSL 차단이 적용되지 않았습니다.", file=sys.stderr)
        return 3

    import pytest
    return int(pytest.main(argv))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
