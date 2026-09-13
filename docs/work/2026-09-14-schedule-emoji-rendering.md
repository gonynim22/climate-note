# 작업 기록: 크게 모드 일정 이모지 하단 잘림 재점검

작성일: 2026-09-14 / 상태: 원인 확인·빌드 경로 수정·새 EXE 검증·로컬 교체 완료, 개발 지침·커밋 반영

## 목표와 범위

- 목표: 크게 모드 우측 상단의 이모지 선택 버튼·팝업·일정 입력에서 남은 하단 잘림을 재현하고 해당 표시만 개선한다.
- 변경 대상: `build.bat`, `build_app.py`, `tests/test_build_app.py`, 빌드 관련 정본 문서. 앱 UI·저장 소스는 변경하지 않는다.
- 데이터 영향: DB v17·Export v2·본문 Unicode·암호화·salt·기존 설정 키·저장 경로 유지. 실제 사용자 AppData·DB·salt·실행 중 앱은 검사하거나 수정하지 않는다.
- 제외 범위: 무관한 기능·버전·의존성 변경, 보안 검사 후속 수정, GitLab 게시.
- 시작 시 사용자 변경: `.gitignore`, `AGENTS.md`, `README.md`, `app_info.py`, `docs/RELEASE_HISTORY.md`, `tests/test_ui.py` 수정 및 미추적 `docs/work/2026-09-11-local-security-audit.md`, `docs/work/2026-09-11-v3.7a-version.md`. 모두 보존한다.

## 완료 조건

- [x] 실제 위젯 렌더로 잘림을 재현하고 수정 전·후 근거를 남긴다.
- [x] 이모지 선택·키보드·포커스·저장·기존 데이터 보존 계약을 유지한다.
- [x] 관련 하네스와 합성 배율 검사 및 PNG 검토를 완료한다.
- [x] 새 EXE의 기존 데이터 보존 검증과 실제 혼합 DPI/KVM 미확인 범위를 구분한다.

## 결정과 진행

- 2026-09-14: `AGENTS.md`, UI/아키텍처/검증 정본과 이전 행 높이·Qt 글리프 수정 기록을 읽었다. 기존 수정만으로 해결을 단정하지 않고 실제 버튼·팝업·입력창과 DPR별 렌더를 재점검한다.
- 현재 Qt/PySide6 6.11.2 환경은 doctor 통과. 기존 글리프 검사는 큰 DPR=1 QImage에 직접 그리는 경로이므로 실제 위젯 내부 잘림과 배율 렌더의 검증 공백이 있다.
- 사용자 확인: 문제 위치는 선택 버튼의 웃는 얼굴과 선택 후 일정 입력창에 들어간 이모지다. 실행 파일은 `dist/기후노트_v3.7a.exe`, Windows 배율은 100%다. 소스 캡처가 정상으로 보이는 반면 이 EXE는 다르다는 지적을 받아 실제 바이너리를 대조했다.
- **확정 원인**: 기존 EXE의 Qt6Core/Qt6Gui/Qt6Widgets DLL은 모두 6.10.2.0이며 현재 `.venv`의 6.11.2와 해시가 다르다. 기존 빌드 TOC는 전역 Python313의 PySide6를 가리킨다. `build.bat`의 `python build_app.py`가 검증된 `.venv`를 보장하지 않아 이전 Qt가 다시 포함되었다. [내부 DLL 대조](../../output/harness/20260914-qt-package-probe-278c0b73/result.json). 이전 EXE SHA-256: `CD87E0FFBA1A93AF4CF398B994A9A8947DD0BD8DF4D5A35340EB756C96A9A178`.
- Qt 6.11.2의 실제 메인 위젯 입력·버튼을 100/125/150%에서 같은 DPR의 큰 QPainter 렌더와 비교해 추가 세로 픽셀 유실은 발견하지 못했다. 별도 독립 프로브는 175/200%도 비교했다. [합성 메인 프로브](../../output/harness/emoji-main-probe-20260914/probe.py). 버튼의 아래 치우침만으로 추가 UI 변경을 하지 않는다.
- 구형 `dist` EXE를 합성 AppData와 시작프로그램 갱신 금지 환경으로 Job Object 안에서 실행했다. Computer Use 목록이 Qt 도구창을 반환하지 않아 합성 프로세스 PID와 창 제목을 확인한 후 PrintWindow로 캡처했다. [구형 EXE 캡처](../../output/harness/emoji-exe-probe-20260914/old-exe.png)에서 스마일 하단 누락을 확인했다. 이후 입력창 캡처 시 창 크기가 바뀌어 사전검사가 중단되었으며, 오래된 좌표로 재시도하지 않고 합성 프로세스만 정리했다. 실제 사용자 데이터와 앱은 접근하지 않았다.
- 최소 수정: 일반 빌드를 `.venv`에 고정하고 `doctor()`가 검증한 환경에서만 같은 Python의 PyInstaller를 실행한다. 자동 설치를 제거하고 `--clean`으로 이전 환경의 빌드 캐시 재사용을 막는다. 환경·빌드 실패를 호출자에게 비영 종료 코드로 전달한다. [빌드 계약](../ARCHITECTURE.md), [검증 계약](../TESTING.md)에 반영한다.
- 최종 EXE 비교: 기존/새 EXE를 각각 별도 합성 데이터와 Job Object로 실행하고, 검사 창만 화면 밖으로 이동해 사용 중 화면의 클릭과 격리했다. 100%/large/1880×992의 같은 실제 Windows 창을 PrintWindow로 캡처하고 팝업의 다트를 직접 선택했다. [기존 EXE](../../output/harness/emoji-exe-compare-20260914/old100/old-selected-input.png), [새 EXE](../../output/harness/emoji-exe-compare-20260914/new100/new-input-complete.png). 같은 영역의 컬러 픽셀 경계는 스마일 19×19→20×20, 입력창 다트 14×13→15×14로 우측·하단 한 픽셀이 복원됐다. [픽셀 대조](../../output/harness/emoji-exe-compare-20260914/pixel-comparison.json). 검사 프로세스는 모두 해당 Job만 정리했다. 합성 텍스트 입력은 실제 한글 IME 조합 검사가 아니다.
- 최종 release: 669 passed / 0 failed / 0 errors / 0 skipped, 신규 EXE 빌드와 3개 격리 시나리오 통과. 기존 합성 데이터 8개 테이블의 raw/복호화 해시·ID·salt가 전후 동일했다. 새 EXE의 Qt6Core/Qt6Gui/Qt6Widgets는 모두 6.11.2.0이며 현재 `.venv` DLL과 전체 바이트·SHA-256이 일치한다. [Qt·데이터 독립 대조](../../output/harness/20260914-000953-2116a75e03/qt-artifact.json).
- 로컬 전달: 구형 `dist/기후노트_v3.7a.exe`를 `dist/previous-qt6102-20260914/`에 복사해 기존 해시를 확인한 뒤, root dist EXE를 검증한 새 EXE로 교체했다. 같은 새 파일을 `dist/emoji-fix-20260914/`에도 보관했다. 세 위치의 복사·해시는 [delivery.json](../../output/harness/20260914-000953-2116a75e03/delivery.json)에 남긴다. 새 EXE SHA-256: `D4C6DA1BBCC1A793FE59DE48E98FFA24378F8358E9651D0247895F08D4069D30`. 표시 버전 v3.7a·날짜·DB v17·Export v2·의존성 lock은 변경하지 않았다.
- 사용자 요청으로 `AGENTS.md`에 가상환경 고정 빌드·환경 불일치 차단·실제 EXE 내부 Qt 대조 규칙과 이번 결과를 추가한다. 커밋은 이번 빌드 수정·회귀 검사·정본 문서·작업 기록 및 AGENTS의 이번 변경에 한정한다. 시작 전부터 있던 버전 표기·보안 검사 기록·`.gitignore` 변경은 작업 트리에 보존하고 커밋에서 제외한다. EXE와 `output/`은 커밋하지 않는다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `tools/verify.py doctor` | 통과 | `20260914-000048-a0b3878538` / [summary.md](../../output/harness/20260914-000048-a0b3878538/summary.md) | 앱 import 없이 환경 진단 |
| 수정 전 `quick --tests tests/test_ui_schedule_emoji.py tests/test_emoji_rendering.py` | 통과 | `20260914-000126-fafd637e22` / [summary.md](../../output/harness/20260914-000126-fafd637e22/summary.md) | 120 passed. 현재 소스 Qt와 구형 dist EXE를 구별하기 위한 기준 실행. |
| 일반 빌드 회귀 추가 후 직접 pytest | 통과 | `20260914-000838-eba0adcb50` / [pytest.log](../../output/harness/20260914-000838-eba0adcb50/pytest.log) | `tests/test_build_app.py tests/test_packaging.py`, 11 passed. 직접 실행이며 하네스 summary 없음. 최종 검증은 아래 release. |
| 구형 전역 Python으로 `build_app.py` 실행 | 의도한 차단 확인 | [build-rejected.log](../../output/harness/20260914-qt-package-probe-278c0b73/build-rejected.log) | Qt 6.10.2≠lock 6.11.2, 코드 2로 PyInstaller 실행 전 중단. |
| `tools/verify.py release` | 통과 | `20260914-000953-2116a75e03` / [summary.md](../../output/harness/20260914-000953-2116a75e03/summary.md), [result.json](../../output/harness/20260914-000953-2116a75e03/result.json) | 669 passed, build·smoke 통과. 입력 해시 전후 동일. 기존 Fluent 내부 SciPy deprecation 경고 1건. |
| 실제 구형/신규 EXE의 100% large 버튼·팝업·입력 비교 | 통과 | `emoji-exe-compare-20260914` / [픽셀 경계](../../output/harness/emoji-exe-compare-20260914/pixel-comparison.json) | 실제 EXE + 합성 AppData. 소스 QWidget.grab 결과와 구별. |
| 문서 링크·`git diff --check` | 통과 | 이 기록 및 변경 정본 2개 | 최종 release 이후 런타임·빌드·테스트 변경 없음. `.bat`은 하네스 스냅샷 확장자 대상이 아니므로 [추가 파일 해시](../../output/harness/20260914-000953-2116a75e03/build-fix-inputs.json)에 별도 기록. |

## 미해결과 인계

- 실제 한글 IME·혼합 DPI/KVM·회사 PC UI: 미확인. 이번 100% 합성 데이터 EXE 캡처로 대체 완료 처리하지 않는다.
- 정상 종료 직전 스티키 저장·Win+D·특정 PC 설정/휴지통 멈춤·Defender·라이선스/SBOM/서명 후속 과제: 미확인/기존 보류 유지. 새 EXE도 Authenticode `NotSigned`다.
- 변경한 정본 문서: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`의 빌드 환경·EXE 대조 계약.
- 로컬 EXE 생성·기존 파일 보호 보관·dist 교체 완료. 소스·지침·관련 검사는 로컬 커밋으로 보존한다. 커밋 식별자는 `git log -1 -- docs/work/2026-09-14-schedule-emoji-rendering.md`로 확인한다. push·GitLab Release 게시 수행하지 않음. 서버 보안 검사 담당자 회신 대기는 그대로 유지.
