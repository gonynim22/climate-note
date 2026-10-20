# 작업 기록: 파일 변환 확장·추천 결과 화면

작성일: 2026-10-20 / 상태: 구현·자동 검증 완료, 업무 환경 수동 확인 대기

## 목표와 범위

- 목표: [확정 설계](../superpowers/specs/2026-10-20-file-converter-redesign-design.md)의 D안과 v4.4를 구현한다.
- 변경 대상: 파일 변환 엔진/worker/runner, 기존 문서 변환 창, main 선분기, 타일·SVG, 표시 버전, 관련 시험·정본 문서.
- 데이터 영향: 없음. DB v18·Export v3·salt·설정·바로가기 6슬롯과 HWP 엔진 3개 모듈을 유지한다. 원본과 기존 결과를 덮어쓰지 않는다.
- 제외 범위: 외부 엔진/의존성 추가, Office·HWP 역변환, GitLab 게시·push.
- 시작 시 사용자 변경: 설계 문서, 과거 작업 기록 10개, `motion/`이 미추적 상태다. 기존 파일은 보존한다.

## 완료 조건

- [x] 형식 표와 추천, 사진/PDF/인코딩 변환, 별도 Job 일괄 처리·취소·비덮어쓰기.
- [x] D안 3화면, 관계도/목록 패널, 비동기 파일창·저장 폴더, 접근성·낮은 화면·수명 계약.
- [x] 관련 자동 검사와 전체 하네스, 100/125/150% 합성 배율, 새 EXE 검증.
- [x] 정본 문서 갱신과 수동 미확인 항목 구분.

## 결정과 진행

- 2026-10-20: 프로젝트 계약·기존 HWP runner·창 수명·검증 경로 확인. 기존 HWP 3개 모듈은 수정하지 않고 새 화면에서 재사용한다.
- 2026-10-20: 환경 doctor 통과. 공용 실행기 분기 변경 때문에 마무리 전체 검사와 PowerShell release를 수행한다.
- 2026-10-20: 공통 형식 표/Qt·codecs 엔진, 일괄 worker/runner, D안 UI·패널·실제 판독·v4.4/출시일 구현. 기존 HWP 3개 모듈·DB·security·build.spec·lock diff 없음.
- 2026-10-20: 판독도 별도 worker에서 수행하며 읽기 전용 원본 폴더 때문에 막히지 않도록 판독용 임시 폴더는 시스템 임시 위치에 둔다. 새 작은 PNG/실제 치수만 부모에 전달한다. 변환 결과는 설계대로 저장 위치 내부에서 만든다.
- 2026-10-20: 합성 PNG 캡처로 D안 빈 화면/추천/결과/관계도와 420×500 압축을 검토했다. ICO는 Qt 단일 writer 대신 PNG 4항목 ICONDIR로 구현. qpdf reader의 2쪽/해상도·사진 3장 PDF는 소스 시험에서 통과했다.
- 2026-10-20: 전체 회귀의 두 실패는 기존 `test_ui_data_lifecycle.quiet_native_layer`의 `_pin_to_desktop_layer` 대역이 실제 `preferred_hwnd=0` 인수를 받지 못한 문제다. 대역의 서명만 맞추고 제품의 Win+D 코드는 그대로 뒀다.
- 2026-10-20: 80×40 합성 사진의 사진 비율 PDF에 8mm 여백을 주면 빈 쪽이 되는 경계를 직접 재현했다. [Qt QPageLayout](https://doc.qt.io/qt-6/qpagelayout.html)의 여백/본문 사각형 규칙을 확인하고, 사진 비율을 유지한 쪽에 여백 공간을 더해 원래 픽셀을 그릴 공간을 확보했다. 0/8/15mm 회귀를 추가했다. PDF 결과 이미지 개수와 취소 시 정리 경고 유지도 보완했다.
- 2026-10-20: 최종 release의 전체 2,908개 검사·빌드·격리 EXE 4개 시나리오가 모두 통과했다. 검사 전후 입력 해시가 동일하다. 이후 제품 코드 변경 없이 새 EXE의 실제 변환·번들 대조를 완료하고 `dist/기후노트_v4.4.exe`로 복사해 SHA-256 일치를 확인했다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `tools/verify.py doctor` | 통과 | `20261020-202531-9839636c89`, [summary](../../output/harness/20261020-202531-9839636c89/summary.md) | 변경 전 Python 3.13/lock 환경 |
| 첫 quick | 실패 | `20261020-203823-e533465c9b`, [summary](../../output/harness/20261020-203823-e533465c9b/summary.md) | 160 통과/9 실패. 이전 UI 기대값·ICO reader 내부 깊이 표식 판정 갱신 |
| 두 번째 quick | 실패 | `20261020-204125-ddfa001ee0`, [summary](../../output/harness/20261020-204125-ddfa001ee0/summary.md) | 252 통과/4 실패. 패널 포커스/칩 최소 높이 보완, 부모 숨김에 맞춘 시험 갱신 |
| 세 번째 quick | 실패 | `20261020-204630-cbb4be8e6c`, [summary](../../output/harness/20261020-204630-cbb4be8e6c/summary.md) | 261 통과/1 실패. QTest (0,0)이 가운데 클릭으로 해석되어 실제 가림막 좌표로 교정 |
| 첫 full | 실패 | `20261020-204759-87009ed924`, [summary](../../output/harness/20261020-204759-87009ed924/summary.md) | 2,902 통과/2 실패. 기존 데이터 수명 시험의 Win+D 대역 인수 불일치 수정 |
| 최종 125% quick | 통과 | `20261020-205545-71d1950bd5`, [summary](../../output/harness/20261020-205545-71d1950bd5/summary.md) | 266/266, 엔진·실제 worker·D안·아이콘·주머니·데이터 수명. 합성 배율 |
| 최종 150% quick | 통과 | `20261020-205708-04420b39c0`, [summary](../../output/harness/20261020-205708-04420b39c0/summary.md) | 266/266, 같은 대상. 합성 배율 |
| 최종 100% release(전체 pytest 포함) | 통과 | `20261020-205840-8e8a0ca2c8`, [summary](../../output/harness/20261020-205840-8e8a0ca2c8/summary.md), [result](../../output/harness/20261020-205840-8e8a0ca2c8/result.json) | PowerShell, 2,908/2,908 → 빌드 → fresh/existing/blocked/upgrade 모두 통과. 기존 qfluentwidgets/scipy 사용 중단 경고 1건 |
| 새 EXE 변환·시작 비용 | 통과 | 같은 실행 폴더, [report](../../output/harness/20261020-205840-8e8a0ca2c8/file-converter-frozen/report.json) | 합성 사진 3장 작은 JPG·3쪽 PDF·PDF→PNG 3장·CP949 CSV→UTF-8 BOM. 원본·줄바꿈 보존, 자체 임시 폴더 정리, 격리 AppData에 DB/salt 미생성 |
| 새 EXE 번들·용량 대조 | 통과 | 같은 실행 폴더, [bundle](../../output/harness/20261020-205840-8e8a0ca2c8/file-converter-bundle.json) | Qt 6.11.2 DLL 15개는 v4.3/venv와 일치. qpdf/qoffscreen 플러그인 일치. 새 모듈·SVG 포함, QtPdf.pyd 제외 유지, BINARY 64개 중 mingw 0개 |

최종 검사 입력은 `HEAD 9901a835bec908c88fb5e2db95a28ec25615af14` 위 작업 트리다. 파일별 SHA-256은 최종 `result.json`의 `inputs_before`/`inputs_after`에 있으며 두 묶음이 일치한다. 검증 후 변경은 이 작업 기록과 무시 대상 산출물뿐이다.

125/150% quick의 대상은 `tests/test_file_conversion.py tests/test_file_conversion_runner.py tests/test_ui_document_converter.py tests/test_ui_mini_app_frame.py tests/test_mini_app_icons.py tests/test_ui_mini_app_spacing.py tests/test_ui_mini_apps.py tests/test_ui_data_lifecycle.py`이며 PowerShell의 `QT_SCALE_FACTOR=1.25`/`1.5`로 실행했다. 최종 release는 `QT_SCALE_FACTOR=1`로 실행했다. 100/125/150% 캡처의 빈 화면·추천·결과·관계도와 420×500 압축을 확인했다. 대표 캡처: [빈 화면](../../output/harness/20261020-205840-8e8a0ca2c8/file-converter-drop.png), [추천](../../output/harness/20261020-205840-8e8a0ca2c8/file-converter-pick.png), [결과](../../output/harness/20261020-205840-8e8a0ca2c8/file-converter-result.png).

추가 EXE 검증은 `output/file_converter_frozen_check.py <새 EXE> <run-dir>` 및 `output/file_converter_bundle_check.py <새 EXE> dist/기후노트_v4.3.exe <run-dir>`를 같은 가상환경에서 실행했다. 작업 프로세스는 실제 onefile EXE의 선분기를 사용하고, 각 일괄을 offscreen으로 처리했다.

| 합성 일괄 | 첫 진행까지(초) | 확정·정리 완료까지(초) |
|---|---:|---:|
| 사진 3장 → 작은 JPG | 2.865 | 3.376 |
| 사진 3장 → PDF 3쪽 | 2.683 | 3.207 |
| PDF 3쪽 → PNG 3장 | 3.039 | 3.780 |
| CP949 CSV → UTF-8(BOM) | 3.003 | 3.502 |

위 시간은 이 PC에서 각 일괄 1회 측정한 값이며, 첫 진행까지에는 onefile 시작·해제·Qt 초기화가 포함된다. PDF 읽기/쪽 렌더링이 frozen worker에서 성공하여 `build.spec` 변경은 필요하지 않았다.

- 새 EXE: [dist/기후노트_v4.4.exe](../../dist/기후노트_v4.4.exe), 94,190,409 bytes(89.827 MiB).
- 직전 v4.3: 94,140,392 bytes. 증가량 50,017 bytes(48.845 KiB), 목표 +1 MiB 이내.
- 새 EXE SHA-256: `a98287463077b960587171c704c7ddc14fac7c797627dc02274e28300e94b144`.
- 원본 빌드와 `dist/` 사본 해시 일치. 기존 v4.3 EXE는 보존했다.
- `git diff --check` 및 수정한 문서의 상대 링크 확인 통과. HWP 엔진 3개 모듈·DB·security·lock·build.spec 변경 없음.

## 미해결과 인계

- **미실행:** 업무 PC 한글에서 HWP→HWPX 후 표·그림·수식 배치 확인, Excel에서 UTF-8(BOM) CSV 열기, 실제 혼합 DPI/KVM/Win+D 확인.
- release smoke는 시작·응답·합성 데이터 보존을 확인한 뒤 자기 Job을 닫는다. 정상 종료 직전 저장·실제 설정/휴지통 등 `summary.md`의 수동 항목과 Defender·라이선스/SBOM/서명은 통과 처리하지 않았다.
- 변경한 정본 문서: [AGENTS](../../AGENTS.md), [파일 변환 계약](../DOCUMENT_CONVERSION.md), [아키텍처](../ARCHITECTURE.md), [UI 계약](../UI_PATTERNS.md), [검증](../TESTING.md), [릴리스 이력](../RELEASE_HISTORY.md), [README](../../README.md), [상세 README](../../README_detail.md).
- 배포·커밋·push 여부: 로컬 EXE 빌드·검증·`dist/` 복사만 수행. GitLab 게시·커밋·push는 수행하지 않음.
