# 작업 기록: GitLab push 보안 검사 대응 — 1단계(사용자 데이터 무관 수정)

작성일: 2026-10-05 / 상태: 완료 — 구현·검증·로컬 커밋 (dist 미교체, push 미실행)

## 목표와 범위

- 목표: 기관 GitLab pre-receive 보안 검사(2026-10-05 push 거절)의 지적 중 **사용자 데이터와 무관한 항목**을 고친다. Semgrep 지적을 로컬 재현 기준 0건으로 만들고, OSV 지적은 사용자 EXE에 들어가지 않는 패키지부터 해소한다.
- 변경 대상: `hwp_conversion.py`, `fetch_data.py`, `tools/verify.py`, `build.spec`(hidden import), `requirements.txt`, `requirements-lock.txt`, 관련 테스트, `docs/CODING_STANDARDS.md`, `AGENTS.md`(의존성 환경 줄·기록 줄), 이 작업 기록.
- 데이터 영향: **없음(절대 조건).** `database.py`·`security.py`·DB v17·Export v2·`.salt`·설정 키·암호화 라이브러리(`cryptography`) 버전을 바꾸지 않는다.
- 제외 범위(2단계 이후): `cryptography` 갱신과 그 밖에 **사용자 EXE에 들어가는** 패키지(PySide6 계열, qfluentwidgets, pywin32, PyInstaller 부트로더 등)의 버전 변경, `holidays.py` 재생성, 앱 버전 변경, `dist` EXE 교체, push.
- 시작 시 사용자 변경: `AGENTS.md`의 미커밋 4줄(보안 검사 push 보류·v3.7a·자체 보안 검사·보안 summary), `docs/RELEASE_HISTORY.md`, 미추적 `docs/work/` 5개를 보존하고 커밋하지 않는다.

## 근거 (2026-10-05 확인)

- push 거절 로그: `output/harness/20261005-push-attempt/push.log`. Gitleaks·Trivy·Syft 통과, **Semgrep·OSV-Scanner 실패**. 서버는 push 후 저장소 전체를 검사한다(이번 65개 커밋에서 바뀌지 않은 `fetch_data.py`도 지적됨).
- Semgrep 지적: `use-defused-xml`(ERROR) — `fetch_data.py:11`, `hwp_conversion.py:7`, `tools/verify.py:21` / `dynamic-urllib-use-detected`(WARNING) — `fetch_data.py:23, 36` / 검사기 오류 1건(파일 미표시).
- 같은 규칙이 2026-09-11 자체 검사 사본 `output/harness/20260911-212909-security-6420ac33/rules-security-audit.yaml`에 있다. `use-defused-xml`은 `import xml` 패턴, URL 규칙은 `urllib.request.urlopen(변수)` 패턴이며, `http.client.HTTPSConnection`은 별도 규칙(`httpsconnection-detected`)에 걸린다.
- EXE 포함 여부: `build.spec`가 `PIL`, `numpy`, `scipy`, `setuptools`, `pytest`를 제외하고, `pygments`·`python-dotenv`는 앱이 쓰지 않는다. `cryptography`(번들 OpenSSL 포함)는 EXE에 들어간다.

## 확정한 방향

1. 표준 `xml` 대신 `defusedxml`(새 직접 의존성, 순수 Python)을 쓴다. 세 파일 모두 같은 방식. 예외 목록에 `DefusedXmlException`을 더해 기존 오류 처리(변환 실패 처리·빈 결과)를 유지한다.
2. `fetch_data.py`는 https 처리기만 가진 전용 opener로 고정 주소(`https://apis.data.go.kr/B090041/openapi/service`)만 호출한다. 다른 주소 형식(`file://`, `http://`)은 실제로 거부된다(검사 회피가 아니라 위험 제거).
3. 사용자 EXE에 들어가지 않는 취약 패키지는 **취약점을 모두 해소하는 가장 낮은 버전**으로 올린다(최소 변경). 대상 목록과 버전은 Task 1의 최신 로컬 OSV 결과로 확정한다.
4. 검사 우회(`nosemgrep` 주석, 규칙 제외, 검사만 피하는 코드 변형)는 쓰지 않는다.
5. 1단계 EXE는 release로 빌드·검증만 하고 `dist`는 교체하지 않는다(사용자 배포는 2단계와 함께).

## 완료 조건

- [x] 로컬 Semgrep(서버와 같은 규칙 사본)에서 `use-defused-xml`·`dynamic-urllib-use-detected` 0건. 검사기 오류는 원인 파일을 기록.
- [x] 로컬 OSV에서 EXE 미포함 패키지 지적 0건. 남은 지적은 EXE 포함 패키지뿐이며 목록을 2단계로 넘김.
- [x] 전체 테스트·빌드·격리 EXE 3개 시나리오(PowerShell release) 통과, 기존 데이터 raw/복호화 해시·salt 보존 확인.
- [x] 새 EXE 추가가 `defusedxml`과 원본 일치가 확인된 표준 `xml.dom` 의존성 8개로 한정되는지 대조. 실제 HWP 예제 변환(소스·frozen) 통과. (사용자 HWP 미배포 범위 정정 반영)
- [x] `database.py`·`security.py`·`cryptography` 버전 무변경 확인.
- [x] 정본 문서 갱신 후 이번 변경만 로컬 커밋. push는 사용자 승인 후.

## 결정과 진행

- 2026-10-05: push 시도 → 거절. 원인 분석 후 사용자와 2단계 분리 합의(1단계 = 데이터 무관). 구현 계획은 다른 모델에서 실행하도록 git 제외 사본 `output/handoff/2026-10-05-push-security-scan-step1.md`로 인계했다(커밋 대상 아님).
- 2026-10-05 후속: 사용자가 HWP 변환 미니앱은 아직 배포하지 않았으므로 기존 저장 데이터 호환 대상이 아니며 기능적으로 정상 작동하면 된다고 정정했다. 이를 반영해 HWP는 정상/손상 문서·취소·원본/동명 결과 비덮어쓰기의 기능 검증으로 판단한다. 기존 캘린더 DB·salt·암호화·설정 보호 조건은 유지한다. 원인이 확인된 `defusedxml`의 표준 `xml.dom` 의존성 8개는 설치된 CPython 코드 일치를 조건으로 수용하고 남은 검증과 로컬 커밋을 재개한다.

## Task 1 결과

- 기준 실행: `20261005-095304-security-step1-baseline` (`output/harness/20261005-095304-security-step1-baseline/summary.json`). 추적 파일의 작업 트리 사본만 검사했다. Semgrep 1.177.0·OSV-Scanner 2.5.1과 기존 규칙 사본을 사용했다.
- Semgrep 기본/60초 실행 모두 6건: `use-defused-xml` 3건, `dynamic-urllib-use-detected` 2건, `use-defused-xml-parse` 1건(`tools/verify.py:245`). 마지막 1건은 서버 요약의 5건과 차이가 있으며 기존 XML 파서 교체 범위에 포함된다.
- 기본 실행의 오류 1건은 `holidays.py`의 `hardcoded-token` 규칙 시간 초과다. 60초 실행에는 오류가 없었다. 서버의 파일 미표시 오류와 동일하다고 단정하지 않는다.
- OSV 취약점 수는 alias를 합친 그룹 수/원본 레코드 수다. 수정 버전 없는 레코드(`no_fix`)는 없었다. 목표는 현재 공개 DB 기준이며 서버 승인이나 향후 취약점 부재를 뜻하지 않는다.

| 패키지 | 현재 | 목표 후보 | 취약점 그룹/레코드 | 실제 EXE 포함 | 단계 |
|---|---|---|---|---|---|
| pillow | 12.1.1 | 12.3.0 | 18/36 | 없음 | 1 |
| Pygments | 2.19.2 | 2.20.0 | 1/2 | 없음 | 1 |
| pytest | 9.0.2 | 9.0.3 | 1/2 | 없음 | 1 |
| python-dotenv | 1.2.1 | 1.2.2 | 1/2 | 없음 | 1 |
| setuptools | 81.0.0 | 83.0.0 | 1/2 | 없음 | 1 |
| cryptography | 46.0.4 | 50.0.0 (이번 변경 제외) | 7/13 | 있음 | 2 |

- 실제 배치 EXE: 58,720,841 bytes, SHA-256 `2DE52766166D1CE5C42ED1ECF0FADC0A4AE8AA82BB0141DEA573748780A10DC1`; PYZ 344개, CArchive 261개, DLL/PYD 89개. 후보 5개 패키지의 import 이름은 실제 아카이브에 없었다. PyInstaller 6.19.0은 부트로더가 포함되므로 변경하지 않는다. 근거: `output/design/security-step1/exe_dependency_inventory.json`.
- HTTPS: 키 없는 단일 요청에 **401** 응답, TLS 도달 확인. 응답 본문은 읽지 않았다. 실사용 AppData 접근 없음.
- 위 1단계 5개와 `defusedxml==0.7.1`의 Windows/Python 3.13 호환 wheel 다운로드 성공(설치 전, 기준 실행의 `wheels/`).
- 목표 후보의 OSV 전체 범위·alias와 PyPI 중간 안정판을 대조하고 목표 5개/defusedxml을 OSV API로 재조회해 모두 지적 없음을 확인했다. 위 1단계 목표를 확정한다. setuptools advisory의 수정판 표기 누락은 공식 83.0.0 변경 기록으로 대조했다. python-dotenv 영향 범위 표기 차이는 있으나 수정판은 1.2.2로 일치한다. 세부 출처: `output/design/security-step1/dependency_fix_review.md`·`.json`.

## Task 2 결과

- 다운로드한 wheel로 1단계 5개만 갱신하고 `defusedxml==0.7.1`을 추가했다. `pip check` 통과, 설치 전후 차이가 예정한 6개 항목과 정확히 일치했다. 다른 패키지 변경은 없다(`pip-freeze-before.txt`·`pip-freeze-after.txt`·`pip-change-review.json`).
- requirements/lock/직접 의존성 검사를 갱신했다. doctor `20261005-095733-f576d5a701` 통과.
- quick `20261005-095744-7c569b68f0`: 57개 통과.

## Task 3–4 결과

- 보안 회귀 검사 17개를 추가했다. 구조 이름만 확인하는 계획의 일부 테스트를 실제 XML 거부·입력 보존 검사로 대체하고, 프록시를 거치는 비HTTPS 차단과 정상 HTTPS 프록시 유지, 정상 공휴일/음력 응답 파싱을 검사했다.
- 수정 전 RED `20261005-095958-571d773509`: 16개 실패·83개 통과. 신규 API 경로 부재, UTF-16 ENTITY와 JUnit 엔티티가 거부되지 않음, DefusedXmlException 미변환, 소스 규칙 위반을 확인했다. 정상 UTF-16 HWPX의 읽기 전용 검사는 기존에도 통과했다.
- 수정 후 GREEN `20261005-100100-0a82d78232`: 111개 통과. 새 XML 파서·HTTPS 호출과 HWP runner/packaging까지 검사했다. `database.py`·`security.py`·`holidays.py`·`app_info.py` diff 없음.
- `CODING_STANDARDS.md`의 서버 보안 검사 원칙과 `AGENTS.md`의 환경 기록을 갱신했다. `TESTING.md`의 직접 의존성 수도 9→10으로 함께 정정했다(계획 누락 보완). 기존 사용자 미커밋 내용은 보존한다.

### 데이터 영향 검토와 계획 보완

- DB·salt·설정·암호화 본문의 저장/변환 경로를 수정할 필요가 없다. `validate_hwpx()`는 별도 작업 사본의 변환 결과를 읽으며, 실패하면 게시하지 않는 기존 경로를 유지한다. 정상 변환과 원본·기존 결과 보존은 별도 검증한다.
- 무인수 `ProxyHandler()`는 HTTP URL을 HTTPS 프록시로 넘길 수 있다. HTTPS/no_proxy 설정만 등록하도록 보완하고 네트워크 없는 회귀 검사로 실제 거부를 확인한다.
- `tools.verify.DIRECT_DEPENDENCIES`에도 새 직접 의존성을 추가하여 doctor와 lock 검사를 일치시킨다.
- EXE 비교를 DLL/PYD·cryptography PYZ 내용 해시까지 확장한다. 단순 모듈 이름 일치만으로 암호화 구성 보존을 주장하지 않는다.
- 파일 URL 거부 테스트는 합성 파일만 사용한다. 실제 UTF-16 ENTITY HWPX 입력과 JUnit 입력 거부도 검사한다.
- 인계서가 지정한 현재 작업 트리·venv에서 진행하며 기존 사용자 변경을 보존한다. `fetch_data.main()`은 실행하지 않고 `holidays.py` 해시를 보존한다.

## 검증 결과 표

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| push 시도 | 실패(서버 거절) | `output/harness/20261005-push-attempt/push.log` | 원격 무변경 |
| 기준 보안 검사 | 지적 재현 | `20261005-095304-security-step1-baseline/summary.md` | Semgrep 6건, OSV 6패키지; 기본 timeout 1건/60초 오류 0건 |
| doctor | 통과 | `20261005-095733-f576d5a701/summary.md` | 예정한 의존성만 변경, pip check 통과 |
| Task 2 quick | 통과, 57개 | `20261005-095744-7c569b68f0/summary.md` | 패키지 갱신 후 기본 회귀 |
| Task 3 RED | 의도한 실패, 16 실패/83 통과 | `20261005-095958-571d773509/summary.md` | 제품 수정 전 신규 보안 회귀 |
| Task 3 GREEN | 통과, 111개 | `20261005-100100-0a82d78232/summary.md` | 제품 수정 후 HWP runner·packaging 포함 |
| 수정 후 보안 검사 | 1단계 조건 충족 | `20261005-100334-security-step1-after/summary.md` | Semgrep 0건, 60초 오류 0건, OSV cryptography만 남음 |
| 최종 스테이징 보안 검사 | 1단계 조건 충족 | `20261005-102813-security-step1-staged/summary.md` | 새 추적 테스트 포함 182개 Python 파일/200규칙, Semgrep 0건·60초 오류 0건, OSV cryptography만 남음 |
| PowerShell release | 통과, 1,643개·빌드·격리 EXE 3개 시나리오 | `20261005-100445-c8bfa148d3/summary.md` | 기존 1,626개+신규 17개. 합성 기존 데이터 raw/복호화 hash·ID·salt 보존 |
| 소스→EXE·Qt 대조 | 통과 | `20261005-100445-c8bfa148d3/artifact-verification/summary.md` | 앱 모듈 13개 일치·Qt 4개 6.11.2.0 일치·mingw 없음 |
| 기존→신규 EXE 최초 구성 검사 | **최초 실패, 중단 이력 보존** | `20261005-100445-c8bfa148d3/artifact-comparison/summary.md` | defusedxml 10개 외 xml.dom 8개 추가. CArchive·DLL/PYD·암호화 코드 동일 |
| 예상 밖 표준 모듈 원인 분석 | 읽기 전용 확인 | `20261005-100445-c8bfa148d3/artifact-comparison/unexpected-stdlib-diagnosis.json` | 8개 모두 동일 Python 설치의 stdlib 코드와 일치. 실패 판정 변경 없음 |
| 범위 정정 후 EXE 구성 검사 | 통과 | `20261005-100445-c8bfa148d3/artifact-comparison-accepted/summary.md` | exact 8개 stdlib 원본 대조, 제거 0·CArchive 동일·native 89/crypto 36 동일 |
| 실제 HWP 소스 | 통과 | `20261005-102232-security-step1-hwp-source/summary.md` | 설치 번들 예제 사본 2개 변환·손상 1개 거부·원본/동명 결과 보존 |
| 실제 HWP frozen worker | 통과 | `20261005-100445-c8bfa148d3/frozen-hwp-probe-step1/summary.md` | 같은 검증 EXE로 예제 2개 변환·손상 거부·취소 시 미게시·작업 폴더 정리 |

모든 실행 ID 경로는 `output/harness/` 하위다. OSV 종료 1은 남은 2단계 지적 때문이며 전체 보안 검사 통과로 표현하지 않는다.

### 최종 코드 검토

- 별도 읽기 전용 검토에서 Critical/Important 지적 없음. 파서 오류의 기존 실패 처리, HTTPS 프록시 우회 차단, 파일 보존, 정확한 의존성 범위를 확인했다.
- 스킬 진행 원장의 “malformed JUnit” 표현을 실제 추가한 “JUnit entity rejection”으로 정정했다. 제품 코드 추가 변경은 없다. `junit_result()`의 실제 엔티티 거부·입력 파일 보존을 검사하며, 상위 `execute()`의 기존 ValueError/ParseError 보고 경로는 유지한다.
- 검토자가 판단을 유보한 사항: 서버 push 수락, 인증된 API·실제 기관 프록시 호환, 임의 HWP 서식/다른 한글 버전, 물리 Win+D/DPI/KVM. 모두 이번 검사로 확인했다고 주장하지 않는다. EXE 구성·합성 데이터 보존과 설치된 변환기의 예제 사본은 Task 5 실증 결과로 별도 판단한다.
- 사용자 정정 후 소스/frozen HWP 실증과 release의 기존 데이터 보존 검사를 재검토했다. 실제 변환 2개·손상 거부·원본 해시·동명 비덮어쓰기·작업 폴더 정리·작업 모드 DB 미생성, frozen 취소 후 미게시를 확인했다. 이번 파서 수정 범위의 기능/데이터 보존 문제는 발견하지 않았다. 임의 문서의 서식 충실도·DRM·다른 한글 버전과 frozen 메인창 직접 클릭은 이번 실증 범위 밖이다.
- 별도 최종 검토에서 보완 구성 검사와 스테이징 15개 파일/AGENTS 두 구간을 승인했다. AGENTS의 “서버 시간 초과”는 확인된 로컬 시간 초과와 미확인 서버 오류 원인을 구분하도록 정정했다. Critical/Important 미해결 지적은 없으며 이 표현 정정 외 제품 변경은 없다.

### Task 5 최초 중단과 재개

- 인계서의 명시적 조건은 “Task 5에서 … EXE 구성의 예상 밖 차이 … 멈추고 사용자에게 보고”이며, Step 3은 “PYZ 추가는 defusedxml 계열뿐”을 요구한다. release 자체는 통과했으나 후속 구성 대조는 이 조건을 만족하지 못해 구현 후속/HWP 실증/커밋을 멈췄다.
- PYZ 344→362개: `defusedxml` 계열 10개와 `xml.dom`, `xml.dom.NodeFilter`, `xml.dom.domreg`, `xml.dom.expatbuilder`, `xml.dom.minicompat`, `xml.dom.minidom`, `xml.dom.pulldom`, `xml.dom.xmlbuilder` 8개가 추가됐다. 제거 0개, CArchive 261개 구성 동일.
- PyInstaller가 `defusedxml/__init__.py`의 `defuse_stdlib()` 안에 있는 import까지 정적으로 수집하면서 minidom/pulldom/expatbuilder의 표준 라이브러리 의존성이 포함됐다. 해당 release의 `build/build/xref-build.html`로 연결을 확인했다. 제품에서 `defuse_stdlib()`나 `xml.dom`을 호출하도록 변경하지 않았다.
- 추가 8개의 번들 코드는 현재 Python 3.13 설치의 stdlib 소스를 컴파일한 코드와 모두 일치했다(파일명만 정규화, 코드·상수·메타데이터 대조). 이 확인은 원인 진단이며 허용 목록이나 기존 실패 판정을 바꾸지 않았다.
- DLL/PYD **89개 모두 원본 bytes/SHA-256 동일**, cryptography PYZ **36개 모두 raw hash 동일**(fallback 정규화 필요 없음). `database.py`·`security.py`·`holidays.py`·`app_info.py`와 기존 사용자 `RELEASE_HISTORY.md`의 파일 해시도 시작 전과 같다. `cryptography==46.0.4` 유지.
- 검증 EXE: `output/harness/20261005-100445-c8bfa148d3/dist/기후노트_v3.8d.exe`, 58,808,984 bytes, SHA-256 `2D00ADBC8C951A32E76A5CA7BF654A5AFCDD6C9CCF129C6EC2164E328D11906F`. 배치된 `dist` EXE는 기존 해시 그대로다.
- 최초 중단 보고 후 사용자가 HWP 미배포/기능 검증 범위를 정정했다. 이를 반영해 **추가 8개를 정확히 명시하고 설치된 CPython 코드와 일치하는 경우만 허용**하도록 EXE 수용 조건을 보완해 재개했다. 기존 제거 0·CArchive 불변·native 89/crypto 36 바이트 일치 조건은 유지한다. 검사를 피하기 위한 빌드 제외나 Semgrep/OSV 규칙 변경은 추가하지 않았다. 최초 실패 스크립트와 결과도 보존한다.
- 보완한 별도 검사 `compare_artifacts_accepted.py`의 실제 실행이 통과했다. 최초 실패 결과는 덮어쓰지 않았으며 `artifact-comparison-accepted/`에 새 판정과 모든 모듈별 근거를 보존한다.
- 소스·frozen HWP 기능 검증 모두 통과했다. release 이후 제품 코드·테스트·빌드·의존성 입력은 바뀌지 않았고 AGENTS 결과 기록만 추가했다(`final-input-review.json`). 따라서 같은 입력에 대한 전체 release는 중복 실행하지 않았다.
- 신규 테스트를 추적 대상으로 스테이징한 뒤 동일 도구/규칙으로 최종 검사를 추가했다. 그 테스트도 검사 사본에 포함됐고 Python 대상 182개에서 Semgrep 지적 0건·60초 검사 오류 0건, OSV는 기존 2단계 cryptography만 남았다. 최종 검사 뒤에는 결과 문서의 상태/실행 ID/오류 설명만 정정했다.

## 미해결과 인계

- 남은 문제 / 수동 확인: Semgrep 검사기 오류 1건의 서버 쪽 원인, 경고(WARNING)·개발 전용 패키지의 차단 대상 여부는 담당자 회신 필요. 실제 기관 프록시/인증 API, 임의 HWP 서식/DRM/다른 한글 버전, 물리 Windows 잠금·DPI/KVM은 이번 결과로 확인했다고 주장하지 않는다.
- 2단계 대상: cryptography 46.0.4의 7그룹/13레코드. 50.0.0은 기준 OSV 계산 후보일 뿐이며 양방향 데이터 호환 검증이나 업그레이드 승인을 뜻하지 않는다.
- 변경한 정본 문서: CODING_STANDARDS.md·TESTING.md·AGENTS.md의 환경/결과 기록·이 작업 기록.
- 다음 행동: 남은 cryptography 2단계와 서버 검사기 오류/차단 기준을 별도로 검토한다. 로컬 검사 결과를 서버 push 승인으로 간주하지 않는다.
- 배포·커밋·push 여부: 이 기록을 포함한 이번 수정 15개 파일을 1회 로컬 커밋한다. 배포 EXE 교체·push는 수행하지 않는다. 기존 사용자 AGENTS 4줄·RELEASE_HISTORY.md·미추적 기록 5개는 커밋에서 제외한다. 실사용 앱 데이터 접근/초기화 없음. 커밋 식별자는 이 파일을 최초 추가한 Git 이력과 최종 응답에서 확인할 수 있다.
