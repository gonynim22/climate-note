# 행안부 CODEMIND 보안 코딩 기준

> 행안부 소스코드 보안약점 진단 도구 **CODEMIND 4.5** 기준  
> 기후노트 프로젝트 전용 코딩 표준 (v2.1~ 적용)

---

## 규칙 목록

| # | 규칙코드 | 카테고리 | CWE |
|---|---|---|---|
| 1 | 0011_IMPRAUTH | 부적절한 인가 | CWE-285 |
| 2 | 001D_ONEWAYHASH | 솔트 없이 일방향 해쉬 함수 사용 | CWE-759 |
| 3 | 0023_NOACTION | 오류 상황 대응 부재 | CWE-390 |
| 4 | 0024_NOCHKERR | 부적절한 예외 처리 | CWE-754 |
| 5 | 0026_RESLEAK | 부적절한 자원 해제 | CWE-404, CWE-772 |

---

## 1. 부적절한 인가 (0011_IMPRAUTH, CWE-285)

**규칙 설명**  
모든 실행 경로에 대해 접근 제어를 검사하지 않거나 불완전하게 검사하면,
공격자가 권한 검증이 빠진 경로를 통해 정보를 유출하거나 기능을 오용할 수 있습니다.

**❌ 잘못된 예제** — 권한 확인 없이 삭제 수행
```python
def delete_content(request):
    action = request.POST.get('action', '')
    content_id = request.POST.get('content_id', '')
    # 작업 요청을 하는 사용자의 권한 확인 없이 delete를 수행
    if action is not None and action == "delete":
        Content.objects.filter(id=content_id).delete()
    return render(request, '/success.html')
```

**✅ 올바른 예제** — 권한 데코레이터로 모든 진입점 보호
```python
@login_required
@permission_required('content.delete', raise_exception=True)
def delete_content(request):
    action = request.POST.get('action', '')
    content_id = request.POST.get('content_id', '')
    if action is not None and action == "delete":
        Content.objects.filter(id=content_id).delete()
    return render(request, '/success.html')
```

**기후노트 적용 지침**
- 데스크톱 앱이므로 웹 RBAC는 해당 없음 (반론서 참조, 저장소 외부 보관)
- Privacy Lock(PIN 잠금) 기능이 있으므로, PIN 검증이 필요한 기능은
  반드시 `_validate_pin()` 호출 결과를 확인한 후에만 실행
- 민감 기능(데이터 Export/Import, 설정 변경)은 PIN 인증 후 실행되는 경로에서만 접근 가능하도록 구현
- **예외: 데이터 초기화(Factory Reset)** 는 사용성 결정으로 PIN 미적용. 대신 확인 다이얼로그(`MessageBox`)로 우발 실행을 방지한다. (데이터 Export/Import의 PIN 인증은 유지)

---

## 2. 솔트 없이 일방향 해쉬 함수 사용 (001D_ONEWAYHASH, CWE-759)

**규칙 설명**  
패스워드를 Salt 없이 해시하여 저장하면, 공격자가 레인보우 테이블로
전수조사해 패스워드를 역추적할 수 있습니다.

**❌ 잘못된 예제** — Salt 없이 해시
```python
def get_hash_from_pwd(pw):
    h = hashlib.sha256(pw.encode())  # Salt 없음 → 레인보우 테이블 공격에 취약
    return h.digest()
```

**✅ 올바른 예제** — Salt와 함께 해시
```python
def get_hash_from_pwd(pw):
    salt = secrets.token_hex(32)
    h = hashlib.sha256(salt.encode() + pw.encode())
    return h.digest(), salt
```

**기후노트 적용 지침**
- `security.py`의 `_derive_fernet_key()`는 **PBKDF2HMAC + 32바이트 Salt** 사용 → 이미 준수
- SHA-256은 키 재료 생성 보조 용도로만 사용하며, 패스워드 직접 저장에는 절대 사용하지 않음
- 새로운 해시 처리 코드 작성 시 반드시 `secrets.token_bytes(32)` 이상의 Salt 포함
- PIN 저장 시: 평문 저장 금지. 반드시 Salt + PBKDF2HMAC 또는 Fernet 암호화 사용

---

## 3. 오류 상황 대응 부재 (0023_NOACTION, CWE-390)

**규칙 설명**  
`except` 블록에서 오류를 포착했지만 아무 처리도 하지 않으면(`pass` 또는 빈 블록),
공격자가 오류 상황을 악용하여 프로그램을 의도치 않은 방향으로 동작시킬 수 있습니다.

**❌ 잘못된 예제** — except 후 pass만 처리
```python
try:
    static_key = static_keys[key_id]
except IndexError:
    pass  # 오류 무시 → 취약한 기본 키로 암호화 계속 진행
```

**✅ 올바른 예제** — except 후 명시적 복구 처리
```python
try:
    static_key = static_keys[key_id]
except IndexError:
    # 오류 발생 시 안전한 대체 처리 수행
    static_key = {'key': secrets.token_bytes(16), 'iv': secrets.token_bytes(16)}
    static_keys.append(static_key)
```

**기후노트 적용 지침**
- `except` 블록에 **반드시** 다음 중 하나 이상 포함:
  1. 오류 로깅 (`_error_logger.error(...)` 또는 `logging.warning(...)`)
  2. 사용자 알림 (InfoBar, QMessageBox 등)
  3. 안전한 기본값으로 복구 또는 함수 조기 반환 (`return` / `return None`)
- `pass` 단독 사용은 **금지** (단, 비치명적 무시 시 주석으로 이유 명시 필수)
  ```python
  except FileNotFoundError:
      pass  # 자동실행 미등록 상태 — 무시해도 안전
  ```

---

## 4. 부적절한 예외 처리 (0024_NOCHKERR, CWE-754)

**규칙 설명**  
예외 처리를 너무 광범위하게 사용하거나(`except:`, `except Exception:`),
발생 가능한 예외 종류를 세분화하지 않으면 예기치 않은 문제가 발생할 수 있습니다.

**❌ 잘못된 예제** — 광범위한 bare except
```python
try:
    f = open('myfile.txt')
    s = f.readline()
    i = int(s.strip())
except:  # 모든 예외를 하나로 묶음 → 어떤 오류인지 구분 불가
    print("Unexpected error")
```

**✅ 올바른 예제** — 예외 종류별 세분화 처리
```python
try:
    f = open('myfile.txt')
    s = f.readline()
    i = int(s.strip())
except FileNotFoundError:
    print("file is not found")
except OSError:
    print("cannot open file")
except ValueError:
    print("Could not convert data to an integer.")
```

**기후노트 적용 지침**
- `bare except:` (예외 타입 없는 except) 사용 **금지**
- `except Exception:` 은 최후 수단에만 허용, 단 반드시 로깅 포함
- 예외는 **발생 가능한 구체적 타입**부터 순서대로 명시:
  ```python
  except sqlite3.OperationalError:
      ...
  except sqlite3.Error:
      ...
  except (OSError, ValueError):
      ...
  ```
- DB 관련: `sqlite3.OperationalError`, `sqlite3.IntegrityError` 등 세분화
- 암호화 관련: `cryptography.fernet.InvalidToken` 별도 처리
- UI 관련: `RuntimeError` (Qt 객체 소멸 후 접근) 별도 처리

---

## 5. 부적절한 자원 해제 (0026_RESLEAK, CWE-404, CWE-772)

**규칙 설명**  
파일 디스크립터, 소켓, DB 연결 등 유한 자원을 사용 후 명시적으로 반환하지 않으면
자원 누수(Resource Leak)가 발생합니다. 특히 예외 발생 시 `close()`가 호출되지 않는 경우가 위험합니다.

**❌ 잘못된 예제** — try 블록 안에서 close() → 예외 시 누수
```python
def get_config():
    try:
        f = open('config.cfg')
        lines = f.readlines()
        f.close()  # 예외 발생 시 이 줄에 도달하지 못함 → 누수
        return lines
    except Exception as e:
        ...
```

**✅ 올바른 예제 1** — finally 블록에서 자원 해제
```python
def get_config():
    f = None
    try:
        f = open('config.cfg')
        lines = f.readlines()
    except Exception as e:
        ...
    finally:
        if f:
            f.close()  # 예외 여부와 관계없이 항상 실행
    return lines
```

**✅ 올바른 예제 2 (권장)** — `with` 문으로 자동 해제
```python
def get_config():
    try:
        with open('config.cfg') as f:
            return f.readlines()  # with 블록 종료 시 자동으로 close()
    except (OSError, FileNotFoundError) as e:
        ...
```

**기후노트 적용 지침**
- 파일 열기: 반드시 `with open(...) as f:` 사용
- SQLite 연결: `database.py`의 `@contextmanager _connection()` 사용 (직접 `sqlite3.connect()` 사용 금지)
- Qt 리소스(`QDialog`, `QMenu` 등): 사용 후 `deleteLater()` 또는 `close()` 호출
- 서드파티 연결(소켓 등): `try/finally` 또는 컨텍스트 매니저 패턴 준수

---

## 6. 서버 push 보안 검사(Semgrep·OSV) 대응 — 2026-10-05

기관 GitLab은 push마다 저장소 전체를 Gitleaks·Semgrep·OSV-Scanner·Trivy·Syft로 검사한다. 현재 서버 로그에서는 검사 실패로 push가 거절됐다. 세부 차단 기준은 담당자 확인이 필요하며 다음 원칙으로 원인을 수정한다.

- XML은 `defusedxml`로 읽는다(`from defusedxml import ElementTree`). 제품의 오류 처리에서는 `ElementTree.ParseError`와 `DefusedXmlException`을 기존 실패 처리로 넘긴다. 하네스의 XML 거부도 검증 실패로 기록하고 성공 처리하지 않는다.
- 개발용 API 호출은 `fetch_data.py`의 고정 HTTPS 주소와 전용 `urllib.request.OpenerDirector`를 사용한다. HTTPS용 프록시·HTTPS·거부(Unknown)·HTTP 오류 처리기만 등록한다. 비HTTPS URL을 HTTPS 프록시로 우회하지 못하도록 다른 scheme의 프록시는 등록하지 않는다. HTTPS 프록시와 `no_proxy` 동작은 유지한다. `urlopen(변수)`나 `http.client.HTTPSConnection`으로 대체하지 않는다. 앱 런타임은 오프라인 전용이다.
- `nosemgrep` 주석·규칙 제외 같은 검사 우회는 쓰지 않는다. `tests/test_security_scan_rules.py`가 추적 Python 파일의 표준 `xml` import와 `urlopen` 호출 재발을 검사하며, 실제 로컬 Semgrep 결과도 별도로 확인한다.
- 의존성 취약점은 사용자 EXE 포함 여부로 나눠 대응한다. EXE에 들어가지 않는 개발·빌드 패키지는 취약점을 해소하는 최소 버전으로 올린다. EXE에 들어가는 패키지, 특히 `cryptography`는 기존 데이터 양방향 호환 검증을 거친 별도 단계에서만 바꾼다. 빌드 도구의 간접 영향을 확인하기 위해 EXE 모듈 구성과 암호화·Qt 바이너리도 대조한다. 상세는 [1단계 작업 기록](work/2026-10-05-push-security-scan-step1.md).

### 암호 라이브러리 갱신의 데이터 호환 게이트

- `tests/fixtures/crypto_compat_cryptography46.json`은 cryptography 46.0.4에서 만든 합성 고정 벡터다. 실제 PC 식별값·사용자 데이터는 없으며, 라이브러리 갱신 때 새 버전으로 다시 생성하지 않는다. 키 파생 값과 기존 토큰·PIN 파일을 읽는 제품 경로를 `tests/test_crypto_compat.py`로 검사한다.
- 암호 라이브러리를 바꾸기 전에 구버전으로 DB·salt·일일 백업·PIN 내보내기 기준본을 보존한다. 신→구·구→신 양방향으로 전체 본문, ID 연결, 실제 백업 복구와 가져오기/재내보내기를 확인한다. 기존 목적지 메모·사용 중인 바로가기와 원본 보존 사본의 해시도 확인한다.
- `security.py`·`database.py`의 저장 계약 변경과 라이브러리 갱신을 섞지 않는다. 설치 전후 패키지 차이와 EXE 내부 모듈·바이너리를 대조하고, 키 파생 또는 복구 호환이 달라지면 배포를 진행하지 않는다. 검증 경로는 `output/harness/` 내부로 제한하며 실사용 AppData는 검사에 쓰지 않는다. 실행 증거와 승인된 버전 메타데이터 차이는 [2단계 작업 기록](work/2026-10-05-push-security-scan-step2.md)에 남긴다.

## 참고 문서

> CODEMIND 점검 원본 자료는 기관 내부 문서이므로 이 저장소에 포함하지 않는다.
> 담당자가 저장소 외부에서 별도 보관하며, 필요한 경우 담당자에게 요청한다.

- CODEMIND 반론서 — 규칙 0011, 001D에 대한 기술적 반론 (저장소 외부 보관)
- 금강청 소스코드 취약점 점검 상세·요약 보고서 (2026-03-17, 저장소 외부 보관)
