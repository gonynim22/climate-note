# 작업 기록: 미니앱 주머니 구분감·작은 타일·예정 앱

작성일: 2026-09-23 / 상태: 구현·자동 검증·새 EXE 빌드·dist 배치 완료 (실제 EXE 클릭 확인은 도구 오류로 미실행)

## 목표와 범위

- 목표: 미니앱 주머니를 별도 떠 있는 창으로 명확하게 보이게 하고, 작은 정사각형 타일 4개로 앱 모음의 성격을 전달한다.
- 사용자 요청: 그림자 또는 구분되는 위치·구성, 기존 단위 환산기 버튼을 반으로 축소, 클릭할 수 없는 `곧 출시 예정` 타일 3개, 이미지 생성 기능으로 만든 환산기 이미지. 계획 후 92px 크기를 선택하고 구현·빌드·AGENTS 갱신·로컬 커밋을 지시했다.
- 변경 예정: `ui_mini_apps.py`, 필요할 경우 `ui_main.py`의 팝업 배치, 새 번들 이미지, 주머니 관련 테스트, `AGENTS.md`와 관련 정본 문서.
- 데이터 영향: UI·번들 리소스만 변경한다. DB v17·Export v2·salt·사용자 설정·바로가기 6슬롯·환산 계수/입력/최근 기록 계약을 유지한다.
- 제외 범위: 새 미니앱 기능 구현, 환산기 본체 개편, 사용자 앱 등록, 외부 코드 로더, 런타임 이미지 생성/다운로드, 버전·의존성 변경.
- 시작 시 사용자 변경: `.gitignore`, `AGENTS.md`, `docs/RELEASE_HISTORY.md` 수정 및 기존 미추적 기록 `2026-09-11-local-security-audit.md`, `2026-09-11-v3.7a-version.md`, `2026-09-17-release-status-docs.md`. 기존 변경을 보존한다.

## 완료 조건

- [x] 밝은 캘린더 위에서도 본체 경계와 그림자가 보여 떠 있는 창으로 구분된다.
- [x] 같은 크기의 작은 정사각형 타일을 2×2로 배치한다. 좌상단은 단위 환산기, 나머지 3개는 `곧 출시 예정`이다.
- [x] 예정 타일은 읽을 수 있는 대비를 유지하되 비활성 스타일로 구분하고 마우스·Space·Enter로 실행되지 않으며 Tab 대상에서 제외된다.
- [x] 생성한 환산기 이미지가 작은 표시 크기와 100/125/150% 합성 배율에서 선명하고 알아보기 쉽다. 앱 이름은 Qt 텍스트로 표시한다.
- [x] 그림자 여백을 포함한 화면 경계 보정, 바깥 클릭/재클릭/Esc/닫기, 환산기 실행·재사용과 포커스 이동을 유지한다.
- [x] 잠금·트레이·사이드바 숨김·크기/화면 변경·초기화·종료 및 일정 저장 실패 차단을 유지한다.
- [x] 관련 하네스 검사와 합성 화면 확인을 수행하고 실행 ID·summary.md·이미지를 기록한다. 실제 혼합 DPI/KVM 확인과 구분한다.

## 결정과 진행

### 1. 주머니의 시각적 구분

- 현재 구현은 투명한 최상위 창에 흰색 둥근 사각형과 1px 테두리만 직접 그린다. 그림자는 없다.
- 안쪽 카드와 바깥 그림자 여백을 나눈다. 기존 D-Day의 Qt 그림자 패턴을 참고하여 안쪽 카드에 부드러운 그림자를 적용한다. 작은 팝업에 맞게 강도와 여백을 조절하고 실제 렌더로 잘림을 확인한다.
- 옅은 파랑 계열 제목 영역, `미니앱` 제목과 닫기 버튼, 본문 경계를 둔다. 제목 아래에는 타일 네 개만 간결하게 배치한다.
- 버튼 오른쪽 우선/공간 부족 시 왼쪽 배치를 유지하되, 보이는 카드와 실행 버튼 사이에 약 12px 간격을 둔다. 계산에는 그림자 여백과 음수 좌표 화면을 포함한다.
- 투명한 그림자 여백을 누르면 바깥을 누른 것처럼 닫히게 한다. 닫힌 후 원래 버튼으로 클릭이 재전달되어 다시 열리지 않는 기존 계약을 유지한다.

### 2. 타일 크기와 예정 앱

- 2026-09-23 사용자 선택으로 타일 크기를 **92×92px**로 확정했다. 기존 132×132px의 면적 약 절반이며, 이미지와 이름의 가독성을 확보한다.
- 92×92px 타일 4개를 2×2로 배치한다. 2열 간격은 약 12px, 카드 본체는 약 240×280px으로 잡고 그림자 공간을 별도로 둔다. 본체 크기와 여백은 실제 렌더를 확인하며 조정한다.
- 배치: 첫 행 `단위 환산기 / 곧 출시 예정`, 둘째 행 `곧 출시 예정 / 곧 출시 예정`.
- 예정 타일은 옅은 중성색 배경·점선 테두리·단순한 공통 표식을 사용한다. 출시일이나 미정인 앱 이름을 추가하지 않는다. 문구가 잘리지 않게 필요하면 두 줄로 표시한다.
- 비활성 예정 타일은 실제 실행 앱과 구별한다. 후속 실제 앱은 예정 자리를 대체하고, 앱 수가 늘면 기존 2열/목록 세로 스크롤 방식을 유지할 수 있게 한다. 이 작업을 위해 별도 플러그인 체계를 도입하지 않는다.
- 사용자 요청이 기존 UI 계약의 `가짜 앱/빈 슬롯 타일은 표시하지 않는다`보다 우선한다. 이번 3개 예정 타일과 새 크기를 구현할 때 [UI 계약](../UI_PATTERNS.md), [아키텍처](../ARCHITECTURE.md), [검증](../TESTING.md), `AGENTS.md`를 함께 갱신한다.

### 3. 이미지 생성 계획

- `imagegen` 스킬의 기본 내장 도구를 사용한다. 이 절의 계획에 따라 생성·복사·실제 축소 렌더 확인을 완료했다. 최종 프롬프트와 파일은 아래에 기록한다.
- 용도: 작은 실행 타일에 넣을 정사각형 앱 이미지 1개. 앱의 파랑 계열에 맞춘 입체적인 계량 도구와 양방향 환산 화살표를 큰 형태로 구성한다. 세부 장식을 줄여 축소 시에도 식별되게 한다.
- 이미지에는 한글 이름·숫자·워터마크를 넣지 않는다. `단위 환산기` 이름, 포커스 테두리, hover 효과는 Qt에서 별도로 표시한다.
- 프롬프트 초안: `stylized-concept; square desktop mini-app artwork for a unit converter; a compact measuring ruler with clear opposing conversion arrows; polished softly lit dimensional illustration; blue tones consistent with the host app, restrained mint accent; centered bold silhouette, generous safe margins, legible at approximately 52 pixels; no text, letters, numbers, logos or watermark.`
- 생성 결과는 실제 타일 표시 크기로 검토한다. 선택한 이미지를 `resources/images/mini_apps/unit_converter_tile.png`에 복사하고 `app_paths.resource_root()`로 로드한다. 기존 SVG를 덮어쓰지 않는다.
- 기존 `build.spec`의 `resources` 폴더 묶음에 포함되며 런타임 네트워크나 새 이미지 라이브러리는 필요하지 않다. 실제 생성 프롬프트·저장 경로·사용 도구는 후속 기록에 남긴다.

### 4. 구현과 검증 순서

1. 타일 크기 반영 및 이미지 생성·축소 가독성 확인.
2. 팝업 카드/그림자/제목부/2×2 타일/예정 상태 구현. 필요 범위에서만 메인 창 위치 계산 조정.
3. 기존 기하·격자 테스트를 새 계약에 맞추고, 실제 클릭·키보드 비활성 및 이미지 로드·그림자 경계·화면 배치를 검사한다. 고정 스타일 문자열만 확인하는 테스트보다 사용자 동작과 실제 렌더를 확인한다.
4. 아래 quick 묶음을 실행하고, 125/150% 별도 프로세스에서는 주머니 렌더·입력·화면 경계 관련 검사를 수행한다. 그림자 잘림과 실제 타일 문구는 생성된 PNG를 열어 확인한다.
5. 구현에 맞춰 정본 문서와 이 기록의 실제 증거를 갱신한다. 수정 후에는 관련 검사를 다시 실행한다.

계획한 기본 명령:

```powershell
.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_ui_mini_apps.py tests/test_ui_unit_converter.py tests/test_ui_schedule_emoji.py tests/test_ui_data_lifecycle.py tests/test_packaging.py
```

공용 실행기·격리는 변경하지 않는다. 사용자가 EXE 빌드도 요청했으므로 `release` 한 번으로 전체 검사·새 빌드·격리 smoke를 수행하고, 생성 이미지가 포함된 실제 EXE의 주머니도 합성 데이터에서 따로 확인한다. 이전 release 결과를 이번 UI의 검증으로 쓰지 않는다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| 첫 quick, 100% | 실패: 118 통과/2 실패 | [20260923-230134-0b93daafc8](../../output/harness/20260923-230134-0b93daafc8/summary.md) | DB 보존 검사 기준 시점에 스티키의 500ms 크기 스냅 저장이 대기 중이었음. 아래 보완 |
| quick + 주머니/환산기, 125% | 통과: 120개 | [20260923-230515-3c1496c89b](../../output/harness/20260923-230515-3c1496c89b/summary.md) | 실패/오류/skip 0. 실제 Qt 합성 PNG 직접 검토 |
| quick + 주머니/환산기 실행, 150% | 통과: 90개 | [20260923-230605-105a76b74d](../../output/harness/20260923-230605-105a76b74d/summary.md) | 실패/오류/skip 0. 실제 Qt 합성 PNG 직접 검토 |
| release, 100% | 통과: 1,026개·새 빌드·격리 3개 시나리오 | [20260923-230703-359f295b1f](../../output/harness/20260923-230703-359f295b1f/summary.md), [result.json](../../output/harness/20260923-230703-359f295b1f/result.json) | 실패/오류/skip 0, 실행 전후 입력 불변. 신규 설치/기존 합성 데이터 보존/손상 salt 차단 |
| 번들 코드·이미지·Qt 대조 | 통과 | [bundle-verification.json](../../output/harness/20260923-230703-359f295b1f/bundle-verification.json) | 현재 코드 객체/이미지와 바이트 일치, Qt DLL 3종 6.11.2.0/venv 해시 일치 |
| 격리 EXE 직접 클릭·화면 | 미실행: 도구 연결 오류 | [exe-ui/result.json](../../output/harness/20260923-230703-359f295b1f/exe-ui/result.json), [launch.json](../../output/harness/20260923-230703-359f295b1f/exe-ui/launch.json) | 전용 합성 데이터의 EXE 창 응답은 확인. Computer Use native pipe unavailable(os error 2), 재시도/세션 초기화 후에도 실패하여 입력하지 않고 소유 Job만 정리 |
| 기존 EXE 보관·dist 배치 | 통과 | [dist-placement.json](../../output/harness/20260923-230703-359f295b1f/dist-placement.json) | 검증한 EXE와 표준 dist SHA-256 일치 |

### 실제 구현과 이미지

- 카드 본체 240×280px, 그림자 여백 사방 24px, 최상위 창 288×328px. 카드에 blur 20/아래 4px/alpha 80의 Qt 그림자를 적용하고 native 중복 그림자를 끈다. 54px 제목부와 92px 타일 네 개를 적용했다.
- 실제 실행 타일 추가 시 예정 자리를 대체한다. 예정 타일은 disabled/NoFocus이며 실제 마우스 입력·Tab 순회에서 비실행을 확인했다. 투명 그림자 여백 클릭도 닫힘 경로로 처리한다.
- 첫 quick 실패의 DB 차이는 기존 스티키 폭/높이 `300×400 → 306×396`뿐이고 본문 암호문은 같았다. `ui_sticky.resizeEvent()`의 기동 시 500ms 스냅 저장 완료 전 snapshot을 잡은 검사 경합이었다. 주머니/환산기 보존 테스트 두 곳에서 타이머 완료를 기다린 뒤 전체 DB/Export/salt snapshot을 잡도록 보완했다. 프로덕션 저장 코드·타이머와 하네스/공용 격리는 변경하지 않았다.
- 이미지 생성 도구: 내장 `image_gen` (CLI/API 키 사용 없음). 원본은 `C:/Users/GG/.codex/generated_images/01a0ce86-b70f-7362-85eb-2ec797425ca0/exec-08c0be06-3a63-4fb4-bb76-fd89d142a8bf.png`에 보존하고 프로젝트에 복사했다.
- 최종 이미지: [unit_converter_tile.png](../../resources/images/mini_apps/unit_converter_tile.png). SHA-256 `C611C9439AD17991C9BF51F3AA822B1D35E999F804DCCE01BD403DD3C30F0CCC`. 투명 PNG이며 표시 크기는 52px, 앱 이름은 별도 Qt 텍스트다.
- 실제 생성 프롬프트:

```text
Use case: stylized-concept. Asset type: one square desktop mini-app illustration for a unit converter, displayed at 52 pixels. Create a polished softly lit dimensional app artwork: a compact ivory measuring ruler with simple dark blue tick marks, combined with two thick clear opposing conversion arrows in rich cobalt blue and restrained mint. Bold centered simple silhouette, front three-quarter perspective with subtle depth, refined satin materials, generous 8 percent safe margins. A genuinely transparent background (alpha), no enclosing app tile or square background. Main subject fills most of the image and reads clearly when very small. No text, letters, numbers, logos, watermark, extra objects or thin complicated detail. This artwork will be placed on a pale blue tile in a Windows productivity app.
```

## 미해결과 인계

- 타일 크기: 사용자 선택으로 92×92px 확정. 크기 관련 미결 사항 없음.
- 필요한 수동 확인: 밝은 배경 위 그림자의 구분감, 실제 혼합 DPI/KVM에서 위치·클릭 경계.
- 변경한 정본 문서: AGENTS.md, UI_PATTERNS.md, ARCHITECTURE.md, TESTING.md, RELEASE_HISTORY.md.
- EXE: [dist/기후노트_v3.8.exe](../../dist/기후노트_v3.8.exe), 58,974,200 bytes, Windows 버전 3.8.0.0. SHA-256 `49E8FDE45DD6F0844548E999E02DB383C6344BE2639C40DFABD96CB185E05B12`.
- 기존 EXE: [previous-v3.8-20260923-230703](../../dist/previous-v3.8-20260923-230703/기후노트_v3.8.exe)에 보관. SHA-256 `BF726F5FD21374FFEE9DF76F6B868847B1EE4C28B0E3123CCC4190481AE173CA`.
- 100% [합성 주머니](../../output/harness/20260923-230703-359f295b1f/mini-apps-pocket-compact.png), [캘린더와 겹친 화면](../../output/harness/20260923-230703-359f295b1f/mini-apps-compact.png), 125% [주머니](../../output/harness/20260923-230515-3c1496c89b/mini-apps-pocket-compact.png), 150% [주머니](../../output/harness/20260923-230605-105a76b74d/mini-apps-pocket-compact.png). 소스 Qt 렌더이며 EXE 캡처와 구분한다.
- 검증 후 소스/테스트/리소스는 변경하지 않았다. 결과를 반영한 AGENTS와 이 기록의 문서만 갱신하고 링크·사실을 대조했다. 기존 qfluentwidgets의 scipy import 사용 중단 예정 경고 1개는 유지한다.
- 로컬 커밋은 이 작업 기록을 포함한 Git 이력으로 식별한다. AGENTS/RELEASE_HISTORY는 시작 상태와의 차이만 반영하며 기존 사용자 변경은 작업 트리에 남긴다. 소스·테스트·정본 문서·생성 이미지만 포함하고 EXE/output은 커밋하지 않는다. 원격 push/게시는 수행하지 않는다.

### 수동 배포 확인

검사일: 2026-09-23 / 자동 검사: Windows / EXE SHA-256: 위 참조 / 회사 모니터·혼합 DPI·KVM: 미확인.

| 항목 | 결과 | 환경·관측·증거 |
|---|---|---|
| 주머니 그림자·타일·이미지·기본/중간/크게, 100/125/150% | 통과 (소스 Qt 합성) | 각 하네스의 PNG 직접 검토와 실제 입력 테스트 |
| 실제 EXE 주머니 직접 클릭·정상 종료 직전 저장 | 미확인 | 창 응답/번들 대조는 통과, Computer Use 연결 오류로 클릭 미실행. Job 정리는 강제 종료 |
| Win+D·Explorer/브라우저 전환 | 미확인 | 실제 UI 별도 |
| 음수 좌표·혼합 DPI·KVM | 미확인 (실기) | 합성 위치/배율 검사와 구분 |
| 특정 PC 설정/휴지통 멈춤·Defender | 미확인 | 기존 보류 유지 |
| 라이선스·SBOM·Qt 고지·서명 | 기존 보류 | EXE NotSigned, [보류 기록](../RELEASE_HISTORY.md) 유지 |

최종 상태: 로컬 새 EXE 제공, 원격 게시 및 회사 PC 수동 확인과 구분한다.
