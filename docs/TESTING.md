# Testing & Security Audit Reference

## 개발 하네스 — 다음 버전부터의 기본 경로

Windows / Python 3.13과 `requirements-lock.txt`의 직접 의존성 8개를 사용한다.
하네스는 패키지를 설치하거나 lock을 갱신하지 않는다. 버전이 다르면 환경 오류로 중단하므로
개발자가 해당 가상환경에서 `pip install -r requirements-lock.txt`로 맞춘다.

프로젝트 루트 PowerShell:

```powershell
.\.venv\Scripts\python.exe tools/verify.py doctor
.\.venv\Scripts\python.exe tools/verify.py quick
.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_ui_sticky.py tests/test_ui_sticky_panel.py
.\.venv\Scripts\python.exe tools/verify.py data
.\.venv\Scripts\python.exe tools/verify.py full
.\.venv\Scripts\python.exe tools/verify.py release
```

| 프로필 | 검사 내용 | 사용 시점 |
|---|---|---|
| `doctor` | OS·Python·lock·필수 파일·출력 쓰기 확인, 앱 import 없음 | 환경 준비/드리프트 진단 |
| `quick` | 리소스·시작 경로·공휴일·실행기·핵심 DB/UI 소규모 회귀 | 일상 개발 + `--tests`로 관련 검사 추가 |
| `data` | DB·암호화·건강 검사·백업·Import/Export·스티키 저장·메인 UI·스트레스 | 데이터 또는 저장/보기 전환 변경 |
| `full` | 전체 pytest 1회 | 공통 실행기·격리 변경, 기능 마무리 |
| `release` | 전체 pytest 1회 → 새 EXE 빌드 → 격리 실행 3개 시나리오 | 배포 산출물 검증 |

`data`는 저장 계약 검사가 들어 있는 `test_ui.py`도 포함하므로 짧은 단위 테스트 묶음이 아니다.
정확한 대상은 `tools/verify.py`의 `QUICK_TESTS`·`DATA_TESTS`가 정본이다.
`quick --tests`는 기본 회귀를 유지하면서 `tests/` 안의 파일 또는 `파일::테스트`를 추가한다.
대상이 없는 경우, 수집 오류, 0건 수집, 전부 skip은 통과가 아니다.
`full`/`release` 실행 전에 `quick`/`data`를 의무적으로 중복 실행하지 않는다.

캘린더 열 너비 변경은 `tests/test_ui_calendar_columns.py`를 포함한다. 창이 화면 안에 들어오는지만 확인해서는 요일 열 축소를 검출하지 못한다. 이 검사는 세로 논리 작업 영역(1080×1920, 864×1536, 720×1280)과 medium/compact에서 실제 날짜 열·요일 제목의 배치를 검사한다. `QT_SCALE_FACTOR=1.25`/`1.5`의 별도 실행은 합성 배율 확인이며 실제 혼합 DPI/KVM 수동 확인을 대신하지 않는다.

### 실행 격리와 증거

각 호출은 `output/harness/<시각-고유값>/`을 새로 만든다. 그 안에:

- `result.json`, `summary.md`: 상태·실제 검사 수·환경·명령·단계별 코드·입력 해시·수동 미검증 범위.
- `pytest.log`, `pytest.xml`, `pytest-tmp/`, `pytest-cache/`, `appdata/`: 검사 로그와 격리 데이터.
- `release`는 추가로 `build.log`, `build/`의 TOC, `dist/`의 신규 EXE,
  `smoke.log`, `smoke.json`, `smoke/<시나리오>/`의 합성 데이터·전후 해시를 보존한다.

출력은 gitignore 대상이다. 실행기는 이전 결과·루트 `dist/`를 재사용하거나 삭제하지 않는다.
실패 원인을 확인한 뒤 새 실행 ID로 다시 실행한다. 자동 재시도·자동 게시 기능은 없다.
여러 단계 작업에서는 [작업 양식](templates/WORK_NOTE.md)을 `docs/work/<날짜>-<주제>.md`로 복사하여
완료 조건과 실제 결과 경로를 기록한다.

수집 전에 `CLIMATENOTE_TEST_APPDATA`를 통해 `LOCALAPPDATA`를 실행 폴더로 격리한다.
이 변수는 프로젝트 `output/harness/` 하위의 해석된 경로만 허용한다.
직접 pytest는 기존 `.pytest-localappdata` 기본 경로를 유지한다. 각 테스트의 `app_dir` 픽스처도 유지한다.
`app_dir`는 DB 경로를 되돌리기 전에 해당 테스트가 만든 앱 top-level 창을 폐기한다.
메인만 qtbot에 등록한 경우에도 별도 플로팅 저장 타이머가 다음 테스트에 남지 않도록 한다.
이전부터 있던 창이나 Fluent 전역 helper는 폐기 대상에서 제외한다.
EXE는 시나리오마다 별도 AppData를 사용하고 `CLIMATENOTE_SKIP_STARTUP_REFRESH=1`로
실제 시작프로그램 경로 갱신을 막는다. 기존 앱을 종료할 필요가 없다.

보고서에는 검사 전후 소스·빌드 설정·테스트·개발 지침의 SHA-256을 기록한다.
미추적 코드도 포함하고 `.env`, 내부 `security/`, 사용자 데이터·가상환경·빌드 출력은 제외한다.
진행 기록인 `docs/work/`·`docs/superpowers/`도 제외한다. 검사 중 코드가 달라지면
`inputs_changed`로 실패한다. 문서 변경만 했으면 링크·사실·지침 이전을 검토한다.

종료 코드: `0` 자동 검사 완료·통과, `1` 검증 실패/입력 변경,
`2` 인자·환경·수집·실행기·보고서 오류, `130` 사용자 중단.
단계의 실제 하위 프로세스 종료 코드는 별도 기록된다.
`running`이 남은 결과는 중단된 미완료 실행이며 통과 증거가 아니다.

### EXE 격리 검증 범위

`release`는 기존 `build.spec`을 같은 Python의 `-m PyInstaller`로 실행한다.
이번 EXE의 크기·SHA-256·Windows 버전·서명 상태와 TOC 해시를 기록한다.
현재 `NotSigned` 상태를 자동 실패로 바꾸지 않는다. 라이선스·서명 과제는 기존 결정대로 별도다.

1. 신규 설치: 빈 AppData → 응답하는 창 → 현재 schema·SQLite 무결성·32바이트 salt·유효한 일일 `.cnbak`·오류 로그 확인.
2. 기존 데이터: 현재 저장 계약의 합성 일정·메모·열린/휴지통 스티키·D-Day·집중/세션·바로가기·설정 → 실행 전후 raw/복호화 내용 해시·ID·salt 불변과 최초 보호백업 확인.
3. 시작 차단: 합성 DB의 salt 손상 → 데이터 보호 오류창만 표시 → 원본 DB·salt·기존 보호백업 해시 불변 확인.

**격리된 EXE 창이 잠시 표시된다.** 각 시나리오는 60초 안에 창 응답과 백업 상태를 확인한다.
Windows Job Object에 대기 중인 launcher를 먼저 배정한 뒤 실행을 허용하고, 실패/중단 시에도
그 실행의 프로세스 트리만 정리한다. 배정 실패 시 EXE를 실행하지 않는다.
이 방식은 [Microsoft의 자식 프로세스 소속·Job 종료 계약](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)을 사용한다.
테스트·빌드 단계의 자식 프로세스도 같은 소유권 범위로 관리한다.
이름 기반 전체 프로세스 종료나 실사용 데이터 검사는 하지 않는다.

정리는 Job 닫기에 의한 **강제 종료**이며 보고서에 `graceful_quit_verified: false`로 남는다.
정상 종료 직전 저장·실제 native UI·혼합 DPI·성능·라이선스 준수는 이 smoke의 통과 범위가 아니다.
작업이 화면을 점유할 수 있으므로 `release`는 사용 가능한 데스크톱 세션에서 실행한다.
서비스 세션의 CI 연결은 Windows Runner 환경을 확인한 뒤 별도로 구성한다.

### 수동 배포 확인 기록

자동 `release` 통과는 배포 승인이 아니다. 다음 양식을 작업 기록에 포함하고,
확인하지 않은 항목은 `미확인`으로 남긴다. 기존 보류 과제를 증빙 없이 완료 처리하지 않는다.

검사일 / 담당자 / OS / 모니터·DPI / KVM / EXE SHA-256: `<기입>`

| 항목 | 결과(통과·실패·미확인) | 환경·관측·증거 |
|---|---|---|
| 버전 표시·일정 편집/삭제·설정/휴지통·정상 종료 직전 최신 스티키 저장 | 미확인 | |
| Win+D 직후 Explorer·브라우저 전환 및 바탕화면 레이어 | 미확인 | |
| 음수 좌표·혼합 DPI·가로/세로 모니터·KVM 전환 | 미확인 | |
| 특정 PC 설정/휴지통 멈춤 | 미확인 | |
| Defender 검사 | 미확인 | |
| 라이선스·SBOM·Qt 고지·서명 후속 과제 | 미확인 | [보류 기록](RELEASE_HISTORY.md) |

최종 배포 판단 / 근거: `<별도 기입>`

## Test Suite

- **Location**: `tests/` (pytest 기반 전체 테스트)
- **구조**: `conftest.py` (격리 픽스처) + DB/보안/스트레스/UI 테스트와 `test_ui_calendar_drag.py`, `test_ui_sticky.py`, `test_show_desktop_guard.py`
- **데이터 UI 수명**: `test_ui_data_lifecycle.py`는 실제 합성 `.enc` 가져오기 후 편집기·집중 타이머 유지, 최신 저장 실패/보호백업 실패 차단, 초기화 전 플로팅/미니 패널 타이머 폐기와 ID 재사용, PIN 잠금·보조 창·예약된 표시를 검사한다. `data`와 `full`에 포함한다. 이 검사는 실제 Windows 잠금/절전·Win+D 수동 확인을 대체하지 않는다.
- **일정 이모지**: `test_ui_schedule_emoji.py`는 16개 선택지·접두 치환 Undo·인라인 팝업 포커스·저장 실패 보류·잠금/트레이/초기화 뒤 콜백 무효화·모드별 표시/검색을 검사한다. `quick --tests tests/test_ui_schedule_emoji.py tests/test_edge_cases.py` 또는 `full`로 실행한다. `test_edge_cases.py`의 PIN `.enc` 왕복 검사는 기존 행·암호문·색상·설정·salt 보존을 포함한다. 하네스 실행 시 합성 UI PNG를 실행 폴더에 남기며, 이는 실제 한글 IME와 혼합 DPI/KVM 검증을 대신하지 않는다.
- **컬러 글리프 경계**: `test_emoji_rendering.py`는 스마일·다트·책·시계의 원본 ARGB 비트맵과 `QPainter` 텍스트 렌더의 경계를 비교한다. Qt 6.10.2에서 5건 실패하고 6.11.2에서 통과하는 Windows 글리프 캐시 회귀 검사다. 위 일정 UI 검사와 함께 `quick --tests`에 추가하거나 `full`/`release`로 실행하며 원본·렌더 PNG를 실행 폴더에 보존한다.
- **격리 전략**: `app_dir` 픽스처가 `security.APP_DIR`, `SALT_FILE`, `database.DB_FILE` 등을 `monkeypatch`로 `tmp_path`에 패치하고 Fernet 캐시 초기화. 테스트 간 DB/암호화 키 완전 격리.
- **스트레스 커버**: 1년×3색상 1,095개 일정, 365회 메모 upsert, 10KB 메모, Export/Import 왕복, 100회 추가/삭제 사이클, 백업 회전, VACUUM 무결성
- **리소스/빌드 커버**: 번들 Fluent UI System Icons 존재 여부, 일반 SVG tint, 컬러 SVG palette 보존, `build.spec` 리소스/라이선스/QtSvg 포함, 설정창 라이선스 고지를 검증한다.
- **v3.4 무손상 커버**: v16→v17 전후 schedule raw row exact snapshot, 팔레트 설정 Export/Import 왕복, canonical 3슬롯 유지, 음수 모니터 좌표 drag/clamp, large 모드 드래그 비활성, 800×560 설정 최소 크기, sticky HTML/plain-text 불변, Win+D topmost pulse/데스크톱 레이어 재고정/hook 해제를 검증한다.
- **의존성**: `pytest`, `pytest-timeout` (`requirements.txt`에 포함)

```bash
python -m pytest tests/ -v
python -m pytest tests/test_stress.py -v --timeout=120   # 스트레스 테스트만
```

### v3.4 수동 릴리스 게이트

- Windows 11에서 `바탕화면 고정` ON → Win+D 후 메인/스티키/D-Day/집중 창이 남고 바탕화면 아이콘보다 위에 있는지 확인한다.
- 이어서 Explorer 폴더와 브라우저를 각각 활성화해 모든 일반 창이 기후노트 위에 표시되는지 확인한다.
- 듀얼 모니터(좌측 음수 좌표 포함)로 캘린더를 드래그한 뒤 재시작·크기 변경·모니터 분리 시 작업 영역 안에 복원되는지 확인한다.

### 테스트 추가 기준

데이터 변경이 수반되는 기능은 반드시 왕복 검증 테스트를 추가한다:
- DB 스키마 변경 → migrate 전후 데이터 보존 확인
- 신규 필드/설정 → 기본값 fallback 동작 확인
- Export/Import → 왕복 후 동일 데이터 확인

---

## Security Audit (CODEMIND) 이력

- **점검 도구**: 행안부 CODEMIND 4.5 (정적 분석)
- **점검 결과**: 72건 탐지 → 코드 수정 + 반론서 대응 (v2.0 → v2.1)

| # | 카테고리 | CWE | 규칙코드 | 대상 파일 | 대응 |
|---|---|---|---|---|---|
| 1 | 부적절한 인가 | CWE-285 | 0011_IMPRAUTH | ui_dday.py, ui_main.py, ui_sticky.py | 반론 (데스크톱 앱 특성상 웹 RBAC 비해당, PIN 잠금 + 하드웨어 암호화 이미 구현) |
| 2 | 솔트 없이 일방향 해쉬 함수 사용 | CWE-759 | 001D_ONEWAYHASH | security.py | 반론 (SHA-256은 키 재료 생성용, 실제 KDF는 PBKDF2HMAC 200K + 32B Salt로 CODEMIND 권장 초과) |
| 3 | 오류 상황 대응 부재 | CWE-390 | 0023_NOACTION | database.py, ui_main.py, ui_settings.py, ui_sticky.py | 코드 수정 |
| 4 | 부적절한 예외 처리 | CWE-754 | 0024_NOCHKERR | build_app.py, database.py, fetch_data.py, main.py, security.py, ui_dday.py, ui_main.py, ui_settings.py, ui_sticky.py | 코드 수정 |
| 5 | 부적절한 자원 해제 | CWE-404/772 | 0026_RESLEAK | main.py | 코드 수정 |

- **반론서 · 보고서**: 기관 내부 문서이므로 저장소에 포함하지 않는다. 담당자가 저장소 외부에서 별도 보관한다.
- **코딩 규칙**: [`docs/CODING_STANDARDS.md`](CODING_STANDARDS.md)
