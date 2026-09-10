# 작업 기록: 스마일·다트 글리프 하단 잘림

작성일: 2026-09-10 / 상태: 수정·로컬 EXE 검증 완료, 실제 듀얼 모니터 확인·게시 별도

## 목표와 범위

- 목표: 사용자가 제공한 `dist/1.bmp`의 스마일 버튼·입력창 다트 하단 잘림을 재현하고 수정한다.
- 변경 대상: Qt/PySide6 계열 4개 패키지 6.10.2 → 6.11.2, 의존성 lock·고지, 글리프 회귀 검사·UI 계약·검증 기록. 앱의 글꼴·위젯 렌더 코드는 추가 변경하지 않는다.
- 데이터 영향: 본문 Unicode·DB v17·암호화·설정 키·salt를 유지한다.
- 제외 범위: 실사용 DB 검사·수정, 실행 중 앱 강제 종료, Qt 계열 외 의존성 업그레이드 및 GitLab 보안 검사 조치.
- 시작 시 사용자 변경: `.gitignore` 수정 보존. 기존 인라인 행 높이 수정은 `dcc5867`로 커밋되어 있으나 push는 차단된 상태다.

## 완료 조건

- [x] 캡처와 일치하는 글리프 잘림을 재현하고 원인을 확인한다.
- [x] 버튼·선택창·일정 입력과 표시에서 이모지 하단을 온전히 표시한다.
- [x] 기존 입력·선택·포커스·저장 계약을 관련 하네스로 검증한다.
- [x] 합성 이미지 확인과 실제 듀얼 모니터 수동 확인을 구분한다.

## 결정과 진행

- 2026-09-10: 사용자에게서 스마일·다트의 잘림이 계속된다는 보고를 받았다. Computer Use 목록에 기후노트가 나타나지 않아 실제 선택은 수행하지 못했고, 사용자가 저장한 `dist/1.bmp`를 직접 확인했다. 입력창에 아래 여백이 있는데도 다트 하단이 끊겨 보인다. 기존 행 높이 수정만으로 전체 문제가 해결됐다는 판단을 정정하고 글리프 렌더링을 별도로 조사한다.
- 큰 캔버스·추가 padding·폰트 hinting 비교에서도 작은 컬러 이모지의 하단이 잘렸다. `QRawFont.alphaMapForGlyph()`가 직접 반환한 ARGB 비트맵에는 남아 있는 우측·하단 픽셀이 `QPainter.drawText()`의 캐시 경로에서 누락됐다.
- 업스트림 [Qt 6.10.2 DirectWrite 소스](https://github.com/qt/qtbase/blob/v6.10.2/src/gui/text/windows/qwindowsfontenginedirectwrite.cpp)의 `alphaMapBoundingBox()`는 포함 좌표인 `QRect`에 `right()-left()`, `bottom()-top()`를 사용한다. [Qt 6.11.2 소스](https://github.com/qt/qtbase/blob/v6.11.2/src/gui/text/windows/qwindowsfontenginedirectwrite.cpp#L1834-L1870)는 `width()`, `height()`로 계산한다. 별도 `output/emoji-glyph-probe/qt611/` 설치로 6.11.2 바이너리에서 5개 재현 사례가 모두 해결되는 것을 확인했다.
- 원인이 Qt에 있으므로 당초 제외했던 의존성 변경 중 Qt 계열 4개만 범위에 포함한다. `requirements-lock.txt`·번들 고지 갱신, `release`의 전체 pytest·재빌드·격리 실행, 결과 스냅샷을 한 묶음으로 수행한다. 다른 의존성과 v3.7 표시 버전·DB v17은 유지한다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| 사용자 제공 `dist/1.bmp` 확인 | 확인 | 로컬 사용자 캡처 | 입력창 다트와 스마일 하단. 저장소에 추가하지 않음. |
| 구버전 `quick --tests tests/test_emoji_rendering.py` | 실패(재현 성공) | `20260910-204952-ae85448ab5`, [summary](../../output/harness/20260910-204952-ae85448ab5/summary.md) | Qt 6.10.2: 새 글리프 검사 5건 실패, 기본 57건 통과. |
| 구버전·후보 버전 분리 비교 | 확인 | `output/emoji-glyph-probe/{6.10.2,6.11.2}/result.json`, `input.png`, `picker.png` | 스마일 20px, 다트 14/22px, 책·시계 22px. 6.10.2는 5건 실패, 6.11.2는 5건 통과. 입력창과 16개 선택창 PNG도 직접 확인. 초기 콘솔의 이모지 cp949 출력 오류는 ASCII JSON 출력으로 수정하여 재실행, 두 실행 모두 종료 코드 0. |
| 수정 후 `release` | 통과 | `20260910-205636-204363fb6e`, [summary](../../output/harness/20260910-205636-204363fb6e/summary.md), [result](../../output/harness/20260910-205636-204363fb6e/result.json) | 전체 pytest 655건, EXE 빌드, 신규·기존·시작 차단 3개 격리 시나리오 통과. Fluent 내부 SciPy deprecated import 경고 1건. 실행 전후 입력 해시 동일. |
| `QT_SCALE_FACTOR=1.25` 관련 `quick` | 통과 | `20260910-210016-bf35995f58`, [summary](../../output/harness/20260910-210016-bf35995f58/summary.md) | 기본 검사 + 행 높이·표시/검색/팝업·글리프 경계, 총 68건. |
| `QT_SCALE_FACTOR=1.5` 관련 `quick` | 통과 | `20260910-210053-1c2cd2e143`, [summary](../../output/harness/20260910-210053-1c2cd2e143/summary.md) | 같은 대상 총 68건. 두 배율의 인라인 행·선택창 PNG 직접 확인. |
| lock 전체 대조·`pip check` | 통과 | 현재 `.venv` | 고정 패키지 31개 모두 버전 일치, 의존성 충돌 0건. PySide6와 shiboken6의 License 메타데이터는 기존 고지와 동일. |
| 실제 듀얼 모니터·혼합 DPI에서 EXE 조작 | 미실행 | | 합성 배율과 격리 smoke로 대체 완료 처리하지 않음. |

재현 명령은 프로젝트 `.venv` Python으로 `tools/verify.py release`를 실행한다. 배율 검사는 새 자식 프로세스 환경에만 `QT_SCALE_FACTOR=1.25` 또는 `1.5`를 설정하고 다음 인자를 사용했다. 실사용 앱의 환경은 바꾸지 않았다.

```text
tools/verify.py quick --tests tests/test_ui_schedule_emoji.py::test_inline_emoji_button_fits_row_before_and_after_edit tests/test_ui_schedule_emoji.py::test_display_search_and_popup_geometry tests/test_emoji_rendering.py
```

검증 환경: Windows 11 build 26200, CPython 3.13.5, Qt/PySide6 6.11.2. 실행 당시 HEAD는 `dcc58671cb04e458cb0a81f6b30b58d251df3d5c` + 이 작업의 변경분이다. `result.json`의 `inputs_before.files`가 검사한 파일별 SHA-256 정본이고 `inputs_after`와 동일하다. 해당 파일 매핑을 키 정렬·ASCII JSON·구분자 `(',', ':')`로 직렬화한 SHA-256은 `9a17158bea42453e59b7ba1af3f7090a0588a4390286d56691362414c3446d31`이다. 검사 뒤 코드·lock·고지는 바꾸지 않았고 README·AGENTS·릴리스 이력의 결과 문구와 이 기록만 갱신했다.

EXE 검증 스냅샷:

- 원본: `output/harness/20260910-205636-204363fb6e/dist/기후노트_v3.7.exe`
- 사용용 복사본: `dist/emoji-fix-20260910/기후노트_v3.7.exe` (원본과 SHA-256 일치)
- 크기: 57,907,537 bytes / File·Product Version: `3.7.0.0` / 서명: `NotSigned`
- SHA-256: `9677998585F0507D6219BE61EEDD80C75046A76A84A65A05A60520F6F6B26810`
- 기존 EXE·`dist/1.bmp`와 실사용 DB·salt는 수정하지 않았다. 격리 smoke의 종료는 Job Object 정리이며 정상 종료 저장의 실제 UI 수동 검증은 아니다.

## 수동 배포 확인

검사일: 2026-09-10 / 담당: Codex 합성 렌더 확인 / OS: Windows 11 build 26200 / 실제 모니터: 사용자 2대, 배율·KVM 미확인 / EXE SHA-256: 위 검증 스냅샷

| 항목 | 결과 | 환경·관측·증거 |
|---|---|---|
| 스마일·다트 입력창, 16개 선택창 합성 렌더 | 통과 | 분리 설치한 Qt 6.11.2의 `input.png`, `picker.png` 직접 확인. 실제 실행 중인 사용자 앱 확인은 아님. |
| 실제 EXE의 이모지 선택·일정 편집·설정·휴지통·정상 종료 저장 | 미확인 | 기존 앱은 종료하거나 검사하지 않음. |
| Win+D·Explorer/브라우저 전환·바탕화면 레이어 | 미확인 | 자동 회귀와 실제 native 수동 확인을 구분. |
| 음수 좌표·혼합 DPI·듀얼 모니터·KVM 전환 | 미확인 | 실제 사용자 환경에서 조작하지 못함. |
| 특정 PC 설정/휴지통 멈춤 | 미확인 | 기존 후속 과제 유지. |
| Defender 검사 | 미확인 | 이번 EXE 별도 미실행. |
| 라이선스·SBOM·Qt 고지·서명 후속 과제 | 미확인 | 고지 버전과 패키지 메타데이터의 License 값 일치 확인. [배포 보류 과제](../RELEASE_HISTORY.md)는 유지. |

최종 배포 판단: GitLab Release 게시 미실행. 로컬 빌드와 자동 검사만으로 배포 완료를 선언하지 않는다.

## 미해결과 인계

- 남은 검사: 위 표의 실제 UI·듀얼 모니터 수동 확인. 기존 실행 앱에는 새 Qt가 적용되지 않으므로 정상 종료 후 새 EXE로 실행해야 한다.
- 정본 문서: [UI 계약](../UI_PATTERNS.md), [검증](../TESTING.md), [릴리스 이력](../RELEASE_HISTORY.md), [AGENTS](../../AGENTS.md).
- 배포·커밋·push: 로컬 EXE 생성·검증과 소스·AGENTS 커밋 완료. `git push origin main`은 GitLab pre-receive 보안 검사에서 거부됐다(종료 코드 1). Semgrep은 `fetch_data.py`·`tools/verify.py`의 XML 사용, 동적 urllib 사용 및 검사기 오류 1건을 보고했다. OSV는 Pygments 2.19.2·cryptography 46.0.4 등의 지적 5건과 생략 54건을 보고했다. Gitleaks·Trivy·Syft는 통과했다. Qt 수정과 별개인 이 항목을 우회하거나 해결 완료 처리하지 않는다. 원격과 GitLab Release는 갱신되지 않았고 기존 `.gitignore` 사용자 변경은 커밋에서 제외했다.
- 검증 뒤 문서 정리: 변경 문서의 로컬 링크 55개 모두 존재하고 `git diff --check`를 통과했다. 위 push 결과를 기록한 문구 수정 외 추가 코드 변경은 없다.
