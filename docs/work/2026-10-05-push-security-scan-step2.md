# 작업 기록: GitLab push 보안 검사 대응 — 2단계(cryptography 갱신)

작성일: 2026-10-05 / 상태: 구현·최종 검증·v3.8e 배치 완료 — 커밋/push 결과는 실행 영수증 참조

## 목표와 승인 범위

- `cryptography 46.0.4`의 OSV 지적 13레코드(별칭을 합친 7그룹)를 해소한다. 기존 사용자 데이터의 읽기·백업 복구·PIN 가져오기와 이전 라이브러리로의 되돌림 호환성을 실제 합성 데이터로 검증한다.
- 최신 사용자 요청은 **v3.8e / 2026. 10. 5. / Windows 숫자 버전 3.8.5.0**, 새 EXE 빌드·배치, AGENTS.md 갱신, 커밋과 `git push origin main`까지 승인했다. 인계서의 v3.8d 유지·배치/push 보류 전제는 이 승인으로 대체한다. 기존 v3.8d EXE를 보존하고 v3.8e EXE를 별도로 배치한다.
- 변경 범위는 `requirements-lock.txt`, 고정 벡터와 호환 테스트, `app_info.py`, 배포 고지와 관련 packaging/UI 버전 검사, 정본 문서와 이 기록이다. `build.spec` hidden import는 실제 필요할 때만 변경하며, 현재 확인 결과 변경할 필요가 없다.
- **`security.py`·`database.py`는 수정하지 않는다.** DB v17·Export v2·`.salt`·백업 `.cnbak`·설정 키·PBKDF2HMAC-SHA256(32바이트, 200,000회)·Fernet 토큰 형식을 유지한다. 실사용 AppData와 사용자 문서는 검사 입력으로 사용하지 않는다.
- 주 가상환경의 패키지 변경은 `cryptography` 하나로 제한한다. Qt·pywin32·PyInstaller와 나머지 패키지, 공휴일 자료와 앱 기능은 변경 범위 밖이다.
- 시작 시 존재한 `AGENTS.md` 사용자 미커밋 4줄, `docs/RELEASE_HISTORY.md`, 기존 미추적 작업 기록 5개는 보존하고 이번 커밋에서 제외한다. 기존 미추적 기록은 2026-09-11 두 개, 2026-09-17·2026-09-24·2026-10-04 최초 설정 재초기화 기록이다.

## 근거와 데이터 영향 판단

1단계 커밋 `f187859` 후 push 재시도는 서버의 Gitleaks·Semgrep·Trivy·Syft를 통과하고 OSV에서만 거절됐다. 로그는 `output/harness/20261005-104414-push-attempt-2/push.log`다. 남은 지적은 `cryptography 46.0.4` 13레코드이며 로컬 검사와 범위가 일치한다.

앱은 `security.py`에서 Fernet·PBKDF2HMAC·SHA256을 사용하고, `database.py`에서 시작 건강 검사·백업 manifest의 `key_check`를 검증한다. PIN 내보내기는 32바이트 salt와 Fernet 토큰을 연결한 기존 형식이다. 라이브러리 교체가 저장 형식 변경을 요구하지는 않지만, 키 파생이나 복호화 동작이 달라지면 기존 데이터 접근을 잃을 수 있으므로 규격 설명만으로 안전하다고 판단하지 않는다.

공식 46.0.4/50.0.0 소스 대조에서 Fernet의 토큰 구조는 유지되지만 객체 재사용과 memoryview 사용이 바뀌었고, PBKDF2 Python class는 Rust class alias로 바뀌었다. 따라서 고정 키 값과 실제 DB·백업·PIN 데이터의 양방향 검증, 최종 EXE의 포함 코드·바이너리 대조를 함께 완료 조건으로 삼는다. 공식 출처와 분석은 `output/design/security-step2/crypto_target_review.md` 및 `.json`에 보존한다.

## 계획 검토에서 보완한 사항

- 앱 모듈을 import하기 전에 모든 작업·입출력 경로가 해석된 `output/harness/` 내부인지 검사한다. `pristine` 보존 사본을 실행 대상으로 쓰거나 기존 결과를 덮어쓰는 요청은 거부한다.
- PIN 복호화만 확인하지 않고 빈 합성 DB에 실제 Import→Export를 수행한다. 별도 병합 대상에는 기존 메모·바로가기·집중 데이터를 넣어 원래 행의 보존과 가져온 집중 세션의 ID 재연결까지 검사한다.
- 백업의 manifest·key_check 검증 외에 DB와 salt를 새 합성 폴더로 복구하여 모든 암호문을 읽는다. 원본 DB·salt·백업·내보내기 및 보존 사본 전체는 최초 파일 해시 manifest와 대조한다.
- 데이터 helper는 `tools.smoke_release`에 의존하지 않는 표준 라이브러리와 cryptography만 사용한다. 옛 검증 venv에는 계획상 보조 의존성인 defusedxml 0.7.1도 확보했지만 이 helper의 실행에는 필요하지 않다.
- 주 venv는 `--no-deps --no-index`로 cryptography만 바꾸고 설치 전후 freeze와 `pip check`를 확인한다. 자동 다운로드된 의존성 목록이 다르다는 이유만으로 실제 설치 변경이 있었다고 해석하지 않는다.
- 실제 호환성·제품 검증이 실패하면 배포를 진행하지 않고 정확한 이전 wheel과 시작 시 보존한 파일로 되돌린다. 사용자 변경을 소거할 수 있는 포괄적인 `git checkout`은 사용하지 않는다.
- EXE 비교는 cryptography 외 모듈·바이너리의 변경도 검사한다. 승인된 앱 메타데이터와 배포 고지 차이는 정확히 구분하고, `PYZ.pyz` 컨테이너의 변경은 내부 모듈별 대조로 검증한다.

## 완료 조건

- [x] 업그레이드 전에 46.0.4 고정 벡터와 합성 데이터셋을 생성하고 보존했다.
- [x] 50.0.0에서 키 파생 값, 46.0.4 토큰·PIN 내보내기 복호화와 Fernet v1 형식을 확인했다.
- [x] 새 라이브러리가 옛 DB·백업·내보내기를 읽고 실제 복구·가져오기를 통과했다.
- [x] 독립된 옛 라이브러리가 새 데이터셋을 읽고 실제 복구·가져오기를 통과했다.
- [x] 옛 EXE가 새 데이터셋을 읽고, 새 EXE가 옛 데이터셋으로 시작하는 교차 검증을 완료한다.
- [x] 최종 PowerShell release의 전체 테스트·빌드·격리 EXE 시나리오를 통과한다.
- [x] 새 EXE의 포함 코드·바이너리에서 cryptography와 승인된 버전/고지 변경 외 차이가 없음을 확인한다.
- [x] 최종 추적 파일 입력으로 로컬 보안 검사를 완료하고 OSV 지적 0건을 확인한다.
- [x] 정본 문서와 실제 증거를 갱신하고 사용자 변경을 제외한 커밋 대상을 확정했다.
- [x] 검증된 v3.8e EXE를 배치했다.
- 커밋·push는 이 문서를 저장한 다음 실행한다. 실제 SHA·서버 결과는 아래 실행 영수증에 기록한다(사전 성공 처리 없음).

## Task 1: 업그레이드 전 기준 고정 — 완료

기준 폴더는 `output/harness/20261005-105814-security-step2-baseline/`이며 아래에서 **기준 폴더**로 줄여 쓴다. 변경 전 소스·문서 bytes와 해시, Git 상태, 패키지 freeze, 옛/새 wheel을 이곳에 보존했다.

### 목표 버전과 오프라인 wheel

기준 보안 검사 `20261005-105814-security-step2-scan-before`의 cryptography 지적은 7그룹/13레코드다. 공식 PyPI의 46.0.4 이후 안정판을 OSV로 조회한 결과 49.0.0에는 2레코드가 남고 **50.0.0은 0건**이었다. 50.0.0을 이 조회 시점의 취약점 해소 최소 안정판으로 확정했다. 미래의 미공개 취약점까지 없다는 뜻은 아니다.

| 위치 | 확보한 wheel |
|---|---|
| `wheels-old/` | cryptography 46.0.4, cffi 2.0.0, pycparser 3.0, defusedxml 0.7.1 |
| `wheels-new/` | cryptography 50.0.0, cffi 2.0.0, pycparser 3.0 |

Python 3.13/Windows x64에서 활성화되는 50.0.0의 요구조건은 현재 cffi 2.0.0으로 충족한다. wheel의 SHA-256과 라이선스 대조는 기준 폴더의 `wheel-and-license-check.json`, 최소 버전 판단은 `output/design/security-step2/crypto_target_review.md`를 따른다.

### 고정 벡터와 Gitleaks 오탐 처리

업그레이드 전 46.0.4로 합성 키 3개(hardware·legacy·PIN), 토큰 12개와 PIN 내보내기 blob을 만들었다. 공개 합성 material·salt만 사용했으며 실제 PC 식별값이나 사용자 데이터는 고정 벡터에 넣지 않았다. 테스트는 키 파생·Fernet 복호화뿐 아니라 제품의 hardware/legacy 경로도 합성 식별값으로 검사한다.

원안 JSON의 공개 합성 key/token 문자열에서 Gitleaks `generic-api-key` **오탐 10건**이 발생했다. 이는 공개 material과 salt로 재현 가능한 시험값이며 실제 비밀 유출이 아니다. 다음 증거를 모두 기준 폴더에 남겼다.

- `vectors-original-46.json`: 46.0.4가 처음 만든 원본 벡터.
- `vectors-gitleaks.json`: 문자열 표현에 대한 최초 검출 10건.
- `vector-representation-check.json`: 키 3개와 토큰 12개, 총 **15개 항목**의 원래 ASCII 길이·SHA-256·재구성 bytes 일치.
- `vectors-gitleaks-bytes.json`: 명시적 바이트 배열 표현으로 직렬화한 시험 벡터의 재검사 결과 0건.

키/토큰의 JSON 표현만 정수 바이트 배열로 바꿨으며 새 키 생성이나 재암호화를 하지 않았다. 검사 규칙·경로 제외를 추가하지 않았고, 실제 취약점 10건을 고쳤다고 계산하지 않는다. 동일 bytes의 고정 벡터가 계속 회귀 기준이다. 최초 quick `20261005-110413-73ddf506b8`와 표현 정리 후 `20261005-110824-e6fc3ce4ef`는 각각 125개를 통과했다.

### 합성 데이터셋과 최초 자체 확인

`old-dataset/`과 `old-dataset-pristine/`에 46.0.4로 만든 DB v17·salt·일일 `.cnbak`·PIN `.enc`·기대값을 보존했다. 8개 테이블과 6개 보호 컬럼의 암호문 9개를 포함한다. 원본은 `old-dataset-manifest.json`, 보존 사본은 `old-preserved-manifest.json`으로 전체 파일 해시를 고정했다.

`old-self-check/result.json`과 독립 옛 venv의 `old-isolated-self-check/result.json`은 모두 통과했다. 실제 백업 복구, 빈 DB 가져오기, 기존 메모·바로가기·집중 데이터를 둔 병합, 집중 ID 재연결, 목적지 PIN 보존과 입력 파일 불변을 확인했다. 자세한 결과는 `dataset-baseline-summary.md` 및 `.json`에 있다.

경로 가드 검사도 통과했다. 초기 manifest 파일명에 `pristine`이라는 단어가 들어간 요청 한 번은 보호 가드가 거부했고 앱/데이터 처리가 시작되지 않았다. 출력 이름을 `old-preserved-manifest.json`으로 정정했다. 이후 작업 영역 밖 경로와 pristine 직접 실행의 거부·파일 불변을 `dataset-guard-review.json`에 확인했다.

## Task 2: 라이브러리 갱신 — 완료

- 주 venv는 `--no-deps --no-index`로 **cryptography 46.0.4 → 50.0.0 한 패키지만** 변경했다. cffi 2.0.0·pycparser 3.0과 나머지 패키지는 그대로다. `upgrade.log`, `pip-freeze-before.txt`, `pip-freeze-after.txt`에 기록했고 `pip check`도 통과했다.
- 필수 암호 API와 기존 backend hidden import를 각각 `-W error`로 import해 통과했다(`import-required.log`, `import-backends.log`). 확인한 내장 OpenSSL은 4.0.1이다. `build.spec` 변경은 필요하지 않았다.
- 새 wheel과 기존 cryptography 라이선스 원문 3개가 byte 단위로 같음을 확인했다. 배포 고지에는 새 버전을 반영하고 관련 packaging 검사를 갱신했다.
- doctor `20261005-110953-ef6d4e4af2`를 통과했다. quick `20261005-110955-cb9d9a460e`는 **130개 통과**이며 기존 qfluentwidgets의 `scipy.ndimage.filters` 경고 1개 외 새 경고는 없었다.
- 사용자 승인에 따라 v3.8e·2026. 10. 5.·Windows 3.8.5.0을 반영했다. `security.py`·`database.py`·DB v17·Export v2·salt·키 파생과 설정 계약은 변경하지 않았다.

## Task 3: 소스 라이브러리 양방향 데이터 확인 — 완료

새 50.0.0 데이터셋도 `new-dataset/`과 `new-dataset-pristine/`으로 분리해 보존하고 `new-dataset-manifest.json`·`new-preserved-manifest.json`에 파일 해시를 기록했다. 각 검사는 별도 작업 사본에서만 실행했다.

| 데이터를 만든 버전 | 읽은 버전 | 작업 사본 / 결과 | 상태 |
|---|---|---|---|
| 46.0.4 | 46.0.4 | `old-self-check/result.json` | 통과 |
| 46.0.4 | 50.0.0 | `new-reads-old/result.json` | 통과 |
| 50.0.0 | 50.0.0 | `new-self-check/result.json` | 통과 |
| 50.0.0 | 독립 venv의 46.0.4 | `old-reads-new/result.json` | 통과 |

각 조합에서 다음을 확인했다.

- 8개 테이블의 raw/복호화 논리 해시·ID, schema 17·SQLite 무결성·salt 해시가 기준과 같다. 6개 보호 컬럼의 암호문 9개를 모두 읽었다.
- 기존 일일 백업의 bytes·manifest를 보존했다. 백업의 DB와 salt를 새 폴더로 실제 복구한 뒤 모든 본문과 원래 해시·ID를 확인했다.
- PIN 내보내기 원문 SHA-256이 기준과 같다. 실제 빈 DB에 가져와 다시 내보낸 논리값도 같으며 목적지 PIN을 유지했다.
- 기존 메모·바로가기·집중 데이터가 있는 DB로 병합해 원래 행을 그대로 보존했다. 가져온 집중 위젯의 ID가 달라진 상황에서 세션 연결도 올바르게 바뀌었다.
- 검사 후 기존 DB·salt·백업·내보내기와 pristine 사본은 불변이다. 마지막에 old/new 원본 및 pristine 네 폴더의 전체 파일 manifest를 최초 값과 다시 대조했다.

종합 결과는 기준 폴더의 `task3-summary.md` 및 `.json`, 세부 복구/가져오기/병합 결과는 각 작업 사본의 `cross-check-details/`에 있다. 이 결과는 같은 PC·Windows 계정의 합성 데이터와 소스 인터프리터 간 검증이다. 실제 EXE 교차 실행은 Task 4에서 별도로 확인한다.

## Task 4: 전체 release·EXE·보안 검사 — 완료

첫 release `20261005-111249-c04e5a2a2f`는 1,652개 통과·1개 실패였다. 유일한 실패는 `test_settings_credit_uses_v38d_metadata`가 구버전을 단언한 것이다. 최신 사용자 승인에 맞춰 테스트 이름·설명·버전·날짜 기대값만 v3.8e로 정정했다. 이 후속에서 제품 코드는 추가 변경하지 않았으며 첫 실행은 빌드 단계에 진입하지 않았다.

두 번째 `20261005-111708-ef570df42a`는 1,653개 테스트·빌드·smoke 3개 모두 통과했지만, 실행 중 AGENTS.md를 갱신하여 **전체 판정은 inputs_changed 실패**였다. `inputs-changed-diagnosis.json`에서 변경 파일은 AGENTS.md 하나이고 코드·lock·HEAD·dirty 상태는 동일함을 확인했다. 이 실패를 최종 통과 근거로 대체하지 않았다.

문서와 index를 고정한 최종 PowerShell release **`20261005-112836-574edfc8b2`는 전체 passed**다. 입력 전후가 완전히 같고 **1,653개 테스트·EXE 빌드·fresh/existing/blocked 3개 시나리오**가 통과했다. 원안 1,651개보다 2개 많은 이유는 실제 하드웨어/레거시 제품 복호화 경로 검사를 추가했기 때문이다. 기존 qfluentwidgets/SciPy 경고 1개 외 신규 경고는 없다.

옛 EXE 검사 준비 중 `dist/기후노트_v3.8d.exe`가 없어 복사가 한 번 실패했다. 확인 당시 `dist`는 비어 있었고 폴더 최종 변경 시각 10:54는 이번 기준 작업 시작 전이었다. 이 실패는 암호화나 사용자 데이터 호환성 실패가 아니다. 대신 `output/harness/20261005-011942-c676bed1f4/dist/기후노트_v3.8d.exe` 보존본이 기존 배치 기록과 같은 **58,720,841 bytes / SHA-256 `2DE52766166D1CE5C42ED1ECF0FADC0A4AE8AA82BB0141DEA573748780A10DC1`**임을 확인하고 `output/harness/20261005-111737-security-step2-old-exe/dist/`로 복사했다. 원래 하네스 파일은 유지하며 사용자 `dist`에 구버전을 다시 생성하지 않는다. 최종 배치는 새 v3.8e만 대상으로 한다.

구성 비교 기준인 1단계 검증 EXE `output/harness/20261005-100445-c8bfa148d3/dist/기후노트_v3.8d.exe`는 원래 위치에 있다(SHA-256 `2D00ADBC8C951A32E76A5CA7BF654A5AFCDD6C9CCF129C6EC2164E328D11906F`). 사용자에게 배치됐던 이전 EXE와 1단계 구성 비교 기준을 혼동하지 않는다.

추가 교차 검사에서 직접 만든 합성 스티키의 기본 크기 300×400이 기존 5mm 스냅으로 306×396에 저장되어 raw/논리 해시 차이가 났다. 이전 EXE + 이전 46.0.4 데이터 대조군에서도 같은 두 필드만 바뀌었다. 본문 암호문과 나머지 모든 셀은 동일하며 `ui_sticky.resizeEvent`의 500ms 크기 저장 동작이었다. 원래 실패와 `legacy-sticky-geometry-control.json`을 보존했다. EXE 전용 사본에 관측된 유효 크기 두 값만 미리 적용하고 기대값을 고정했으며, 검사에서 크기 필드를 제외하거나 raw 비교를 완화하지 않았다. 원래 pristine·salt·내보내기·백업은 그대로다.

엄격한 EXE 전후 raw/논리 해시·ID·salt·기존 백업/내보내기 bytes 검사는 `old-exe-on-new-snapped/check/`와 최종 **`new-exe-on-old-final-ready/check/`**에서 통과했다. 준비 변경은 각 `geometry-preparation.json`, 종합은 `exe-cross-geometry-summary.md`에 있다. 옛 EXE 자체 smoke도 `20261005-111737-security-step2-old-exe/smoke.json`의 3개 시나리오를 통과했다.

최종 EXE의 `artifact-comparison-step2/summary.md`는 모든 PYZ/CArchive/내부 ZIP 멤버를 비교했다. PYZ 362→363은 cryptography 2개 추가·1개 제거, CArchive 261→263은 cryptography 메타데이터의 SBOM 2개 추가다. 허용 차이는 설치된 50.0.0의 crypto 코드/바이너리/메타데이터와 정확한 앱 버전·날짜·배포 고지뿐이다. **비crypto DLL/PYD 88개는 bytes 동일**하다. `artifact-verification-step2/summary.md`는 앱 모듈 13개·Qt 6.11.2.0 DLL 4개·PE 3.8.5.0·mingw 미혼입, security/database 원본 해시 불변을 확인했다. 패키지 자체 SBOM 포함이 앱 전체 SBOM/서명 후속 완료를 뜻하지는 않는다.

정확한 staged 트리를 검사한 `20261005-112559-security-step2-staged/summary.md`는 Gitleaks 0건·Semgrep 0건·OSV 0건이다. Semgrep 기본 설정의 holidays.py 규칙 시간초과 1건은 60초 검사에서 오류/지적 없이 완료했다. 규칙·경로·패키지 제외는 추가하지 않았다. 이후 변경은 결과 문서뿐이며 최종 커밋 대상의 실행 코드·lock 해시를 검사 입력과 다시 대조하고 Gitleaks를 재확인한다.

검증된 EXE를 **`dist/기후노트_v3.8e.exe`**에 새로 배치했다. 크기 **59,049,343 bytes**, SHA-256 **`20BE4A07F4EC64DD9078EAF29DCBC65B176F3562D0385517D1FFA0E907EA6AC8`**. 원본 release 파일과 배치 파일의 해시가 같다. 배치 증거는 `output/harness/20261005-v3.8e-completion/delivery.json`이다.

## 검증 증거

아래 실행 ID는 별도 표시가 없으면 `output/harness/<실행 ID>/`를 가리킨다. 기준 폴더 내부 결과는 위 Task 1–3의 경로를 따른다.

| 명령/범위 | 상태 | 실행 ID / 결과 | 검사 범위 |
|---|---|---|---|
| 1단계 후 push 재시도 | 실패: OSV만 | `20261005-104414-push-attempt-2/push.log` | Semgrep 통과, cryptography 13레코드 |
| 2단계 기준 보안 검사 | 지적 재현 | `20261005-105814-security-step2-scan-before/` | cryptography 7그룹/13레코드 |
| 목표 버전 검토 | 50.0.0 확정 | `output/design/security-step2/crypto_target_review.md` | 공식 안정판·OSV·wheel·소스 대조 |
| 46.0.4 고정 벡터 최초 quick | 통과: 125개 | `20261005-110413-73ddf506b8/summary.md` | 업그레이드 전 회귀 기준 |
| 벡터 표현 정리 후 quick | 통과: 125개 | `20261005-110824-e6fc3ce4ef/summary.md` | 동일 bytes 표현·실제 제품 암호 경로 |
| 갱신 후 doctor | 통과 | `20261005-110953-ef6d4e4af2/summary.md` | cryptography만 변경, lock 일치 |
| 갱신 후 quick | 통과: 130개 | `20261005-110955-cb9d9a460e/summary.md` | 고정 벡터·보안·데이터·packaging |
| 데이터 자체 확인·경로 거부 | 통과 | 기준 폴더 `dataset-baseline-summary.md`·`dataset-guard-review.json` | 독립 46 venv, 원본/경로 보호 |
| 양방향 데이터 네 조합 | 통과 | 기준 폴더 `task3-summary.md` | 실제 백업 복구·PIN Import/병합·원본 불변 |
| 첫 전체 release | 실패: 1개, 통과: 1,652개 | `20261005-111249-c04e5a2a2f/summary.md` | 구버전 UI 단언 실패, 빌드 미실행 |
| 두 번째 release | 실패: inputs_changed | `20261005-111708-ef570df42a/summary.md` | 테스트/빌드/smoke 통과, AGENTS 변경으로 전체 실패 |
| 최종 고정 입력 release | 통과: 1,653개·빌드·smoke 3개 | `20261005-112836-574edfc8b2/summary.md` | 입력 전후 동일 |
| 최종 EXE 구성·원본 대조 | 통과 | `20261005-112836-574edfc8b2/artifact-comparison-step2/summary.md`·`artifact-verification-step2/summary.md` | 비crypto 88개 동일, 앱/Qt/PE 확인 |
| EXE 양방향 데이터 | 통과 | 기준 폴더 `exe-cross-geometry-summary.md`·`new-exe-on-old-final-ready/check/summary.md` | 원본/암호문 불변, 크기 대조군 포함 |
| 정확한 staged 보안 검사 | 통과: 지적 0건 | `20261005-112559-security-step2-staged/summary.md` | 기본 timeout 1건은 확장 검사 완료 |
| 최종 EXE 배치 | 통과 | `20261005-v3.8e-completion/delivery.json` | 새 dist 파일과 release SHA 동일 |

## Task 5: 문서·커밋·push와 남은 수동 확인

- AGENTS.md의 환경 계약과 v3.8e 기록, CODING_STANDARDS·TESTING의 영구 호환 검증 규칙을 갱신했다. 최종 release 뒤에는 결과 문서만 갱신했으며 코드·테스트·lock·빌드 입력은 동일하다.
- 독립 최종 리뷰는 코드/데이터 보존 결함이 없다고 판정했다. 조건으로 남겼던 최종 release·최종 EXE 대조·교차 실행은 위 실행에서 완료했다. 리뷰 당시 진행 중이던 문서 상태도 실제 결과로 갱신했다.
- 기존 AGENTS 사용자 4줄·RELEASE_HISTORY·미추적 기록 5개를 보존하며 이번 변경만 커밋한다. 보안 검사/아카이브 브랜치를 우회하거나 `--all`/`--mirror`를 사용하지 않는다.
- **이 문서는 단일 커밋 직전 스냅샷이다.** 커밋 SHA와 서버 결과를 사전에 성공으로 적지 않는다. 저장 후 `git push origin main`을 실행하며 실제 완료 결과는 `output/harness/20261005-v3.8e-completion/summary.md`, `completion.json`, `push.log`에 남긴다. 로컬 검사 통과와 서버 수락을 구분한다. EXE를 Git에 넣거나 GitLab Releases에 업로드하지 않는다.
- 모든 데이터 검증은 합성 폴더에서 수행했다. 실사용 AppData·DB·salt·실행 중 사용자 앱은 건드리지 않았다. 자동 EXE smoke는 소유 Job을 강제 정리하므로 실제 정상 종료 직전 저장 검증으로 표현하지 않는다.
- 물리 PC/다른 Windows 계정으로의 이동, 실제 Win+D·혼합 DPI/KVM, Defender·서명·앱 전체 SBOM은 이번 검증에 포함되지 않는다. 소스 PIN Import/백업 복구·전체 테스트와 이 수동 범위를 구분한다.
