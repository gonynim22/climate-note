# 작업 기록: v3.9a 라이선스 안내·고지 정비

작성일: 2026-10-09 / 상태: 구현·기술 검증·로컬 EXE 갱신 완료, 권리/배포 후속 확인은 별도

## 목표와 범위

- 목표: 설정에서 실제 구성요소의 고지 원문을 오프라인 열람하고, 미니앱·OCR·HWP 고지 누락을 보완한다.
- 변경 대상: 설정의 라이선스 진입점/열람 창, 고지 목록·원문, HWP 소스의 설명, 관련 문서, 빌드의 고지 파일 포함, 관련 테스트.
- 데이터 영향: 없음. 기능 로직·DB v17·Export v2·salt·설정 키·모델/사전·의존성은 유지한다. 실사용 AppData/실행 앱에 접근하지 않는다.
- 제외 범위: 버전/출시일 변경, 모델/계산/변환 로직 변경, 공모전 적격·권리 귀속의 임의 확정, 서명·GitLab Release 게시. 초기 구현 범위에서 제외했던 커밋·push는 아래 사용자 후속 요청에 따라 진행한다.
- 시작 시 사용자 변경: AGENTS.md, docs/RELEASE_HISTORY.md 및 기존 미추적 작업 기록 7개를 보존한다.

## 완료 조건

- [x] 앱 및 제3자 원문 열람, 복사, 닫기, 부모 숨김/잠금 수명, 작은 화면·배율 확인.
- [x] HWP 지정 문구·PaddleOCR 저작권 및 출처 보완; 모델/사전 불변.
- [x] OCR 폴더 유무의 목록/빌드 설정 검사, 현재 포함 빌드 고지 파일 패키징 확인. OCR 제외 EXE를 별도로 빌드하지는 않았다.
- [x] 관련 quick, PowerShell release, 실제 EXE 고지/모델/Qt·의존 DLL 대조.
- [x] v3.9a·Windows 3.9.1.0 유지 및 합성 사용자 데이터 보존 검증.

## 결정과 진행

- 2026-10-09: 사용자가 위 범위의 수정을 승인했고 버전 유지를 명시했다. [설정 분석](2026-10-09-license-contest-review.md), [미니앱 상세 조사](2026-10-09-mini-app-license-audit.md)를 근거로 구현한다.
- 설정 본체 800×560 무스크롤을 유지하고 별도 원문 창을 사용한다. URL은 읽기/복사만 제공하며 브라우저를 열지 않는다.
- 출처 미확인 이미지·개발용 AI 및 기관/공모전 계약은 추정해 표시하지 않는다. 배포 검토 보류 전체를 완료 처리하지 않는다.
- 원문 확보 후 기존 조사 표기를 바로잡았다. pywin32의 설치 메타데이터 분류 대신 실제 win32/win32com/pythonwin의 BSD 계열 원문을 제공한다. cffi 2.0.0은 MIT No Attribution(MIT-0)이다. CPython OpenSSL 3.0.16과 cryptography 내부 OpenSSL 4.0.1을 구분했다.
- 기본 목록 19개 + OCR 목록 3개. 공식 Qt 6.11.2의 해당 모듈/이미지 플러그인 고지 66페이지에서 원문 블록 124개를 보존했다. 잠재 플랫폼 구성도 포함하므로 이 EXE의 정적 의존성 전수 SBOM으로 표시하지 않는다.
- 수정 전 해시 대조에서 기존 Python 파일 중 ui_settings.py와 hwp_conversion.py만 달라졌다. HWP 파일은 모듈 설명을 제외한 AST가 동일하며 설정의 변경 메서드는 초기 참조값과 _on_license뿐이다. app_info.py·의존성·모델/사전/MANIFEST·기존 AGENTS.md는 그대로다.
- 100% 및 125% 합성 캡처에서 긴 원문·좁은 360×400 작업 영역·OCR 출처 화면을 확인했다. Qt 네이티브 창 틀은 Qt widget grab에 포함되지 않으며 실제 혼합 DPI/KVM 검사를 대신하지 않는다.

## 검증 증거

최종 EXE: **94,012,479 bytes**, SHA-256 **`3C80DBB06028A035EAADD866A21940D5AA95143E6CF61B5A2907E4DD92B6A41A`**, Windows **3.9.1.0**. 이전 대비 138,340 bytes 증가했다. 이전 EXE(`ED4BBD6B…0FDF`)는 `output/harness/20261009-132546-f2aab9b4b1/dist/`에 보존하고, 새 검증본을 루트 `dist/기후노트_v3.9a.exe`로 복사한 뒤 해시를 다시 확인했다. 버전·출시일·EXE 이름은 그대로다.

150% 좁은 화면 캡처도 확인했다. 실제 EXE는 UI Automation으로 더보기 → 설정 → 라이선스 → GPL 전문 → 키보드로 OCR 항목 선택 → PaddlePaddle 고지 → 닫기를 조작했다. 고유 Job의 PID에 속한 컨트롤만 사용하고 전역 마우스/키보드 입력은 보내지 않았다.

첫 보조 EXE 검사는 짧은 AutomationId를 가정해 실패했다. 시작 직후 스티키의 기존 배치 저장에 따른 해시 차이도 관측했다. 시험 코드를 관측된 전체 AutomationId와 배치 안정화 후 기준 snapshot으로 수정했으며 제품 코드는 바꾸지 않았다. 두 번째 실행에서 라이선스 조작 전후 8테이블 raw/평문·ID·salt가 모두 동일했다. 실패 기록도 보존한다.

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 유의사항 |
|---|---|---|---|
| 관련 quick: test_ui_licenses.py, test_ui.py, test_packaging.py | 210개 통과 | [20261009-183610-68062ca27f](../../output/harness/20261009-183610-68062ca27f/summary.md) | 첫 구현 검증. 이후 공백 및 캡처 검사를 보강하여 최종 근거는 후속 검사/새 release |
| QT_SCALE_FACTOR=1.25 quick --tests tests/test_ui_licenses.py | 82개 통과 | [20261009-183828-1b4eaa4a3f](../../output/harness/20261009-183828-1b4eaa4a3f/summary.md) | 실제 열람·복사·잠금·DB/Export/salt 불변 및 합성 PNG |
| QT_SCALE_FACTOR=1.5 quick --tests tests/test_ui_licenses.py | 82개 통과 | [20261009-183904-819039eaae](../../output/harness/20261009-183904-819039eaae/summary.md) | 동일 검사, 합성 150% |
| PowerShell release | 1,816개·빌드·격리 EXE 3개 시나리오 통과 | [20261009-183942-21246a4373](../../output/harness/20261009-183942-21246a4373/summary.md) | 실패/오류/skip 0. 기존 QFluentWidgets SciPy deprecated import 경고 1개 |
| 최종 EXE/소스 대조 | 증거 일치 215/215 통과 | [번들 summary](../../output/harness/20261009-183942-21246a4373/license-bundle-summary.md), [result](../../output/harness/20261009-183942-21246a4373/license-bundle-result.json) | 고지/목록 39개 일치, 모델/사전/네이티브/폰트/아이콘 160개 불변, 네이티브 포함 집합 동일, mingw 원본 경로 없음 |
| 첫 EXE UI 보조 검사 | 실패(검사용 selector/기준 시점 수정) | [첫 결과](../../output/harness/20261009-183942-21246a4373/license-exe-ui/result.json), [UI 관측](../../output/harness/20261009-183942-21246a4373/license-exe-ui/ui.json) | 제품/하네스 변경 없음 |
| 최종 EXE UI 보조 검사 | 통과 | [UI 결과](../../output/harness/20261009-183942-21246a4373/license-exe-ui-2/ui.json), [데이터 결과](../../output/harness/20261009-183942-21246a4373/license-exe-ui-2/result.json) | 실제 원문 열람·닫기 및 데이터 불변. 종료는 소유 Job 강제 정리이며 정상 종료 저장 검사는 아님 |
| 문서 링크·사실·차이 확인 | 통과 | 이 기록 | 검사 뒤 제품 코드 변경 없음. 마지막 변경은 결과 기록 문서뿐 |

## 미해결과 인계

- 수동 확인: 실제 혼합 DPI/KVM·기관 보안 환경은 별도. 공모전 공고·AI 도구·일부 자산·한컴 계약 미확인.
- 변경한 정본 문서: UI_PATTERNS.md, ARCHITECTURE.md, TESTING.md, DOCUMENT_CONVERSION.md, SCREEN_TEXT.md, RELEASE_HISTORY.md. README/사용자 설명에도 접근 방법과 HWP 지정 문구를 반영했다.
- 다음 행동: 공모전 규정·개발용 AI 도구·자산 출처·기관/Hancom 계약·외부 대응 소스 제공·전수 SBOM/서명 등의 별도 후속 확인. 현재 앱에 확인되지 않은 권리 취득을 주장하지 않는다.
- 배포 여부: 검증 EXE의 로컬 배치 완료. GitLab Release 게시는 수행하지 않음.

## AGENTS 갱신·커밋·push 후속 (2026-10-09)

- 사용자 요청: “AGENTS.md 업데이트, 커밋, 빌드, push 해줘. 만약 했다면 안해도 돼.” 버전 유지와 기능·사용자 데이터 보존 조건은 계속 적용한다.
- AGENTS.md에 라이선스 열람/번들 계약과 최신 검증 EXE 해시를 반영했다. 이미 통과한 release 이후 제품 입력 변경 없이 문서·Git 원문 보존 규칙만 갱신했으므로 검증 산출물을 재사용한다.
- 원격 main을 fetch한 결과 시작 HEAD `ac7306a`와 일치했다. 기존 AGENTS.md·RELEASE_HISTORY.md의 다른 작업 수정과 관련 미추적 기록은 작업 트리에 보존하고 이번 라이선스 정비만 커밋 대상으로 선택한다.
- 커밋 전 문서 링크·제품 입력 및 EXE 해시를 재확인했다. release 이후 입력 차이는 AGENTS.md·RELEASE_HISTORY.md뿐이며 고지 파일 39개도 EXE와 일치했다. 경로 재확인 중 루트 dist가 비어 있음을 확인하여 검증 실행 폴더의 동일 해시 EXE를 다시 배치했다. 결과는 `output/license-update/precommit-check.json`에 보존한다.
- Git 준비 중 자동 줄바꿈 변환이 원문 SHA-256을 바꾸는 것을 확인하여 `.gitattributes`에 출처 기록 대상 16개 원문의 `-text`를 추가했다. 앱/고지 파일의 바이트는 변경하지 않고 Git 저장·체크아웃에서 원문을 보존한다. 원문 자체의 공백·끝 빈 줄과 OpenSSL Authors의 `=======` 제목 밑줄은 출처 그대로 보존하며 일반 차이 검사와 구분한다.
- 첫 체크아웃 검사에서 이미 stage된 파일에 이전 줄바꿈 변환이 남은 것을 확인하여 해당 원문만 명시적으로 다시 stage했다. 최종 Git index 및 별도 폴더 checkout에서 기존 PaddleOCR 원문을 포함한 **17/17개 SHA-256 일치**를 확인했다(`core.autocrlf=true`, `output/license-update/git-originals-check.json`). 원문을 제외한 staged diff 검사는 통과했다.
- push는 `git push origin main`으로 한정하며 실제 커밋과 원격 반영 결과는 Git 이력 및 최종 응답으로 확인한다. EXE·output·기존 보관 브랜치는 커밋/push 대상에 추가하지 않는다.
