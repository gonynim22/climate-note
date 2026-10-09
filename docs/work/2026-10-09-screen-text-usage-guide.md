# 작업 기록: 화면 글자 따기 사용법 안내 (v3.9a)

작성일: 2026-10-09 / 상태: 로컬 구현·검증 완료(이 PC의 실제 EXE는 사용자가 확인, 업무 PC 수동 확인 대기)

## 목표와 범위

- 목표: 처음 화면 [영역 고르기] 아래 약 300px 빈 곳에 벡터 사용법 애니메이션과 팁 두 줄을 채우고, 결과 화면 [복사] [다시 고르기] 줄 오른쪽 끝에 [사용법]을 둔다. [사용법]은 같은 애니메이션 화면을 열고 [돌아가기]는 결과를 그대로 돌려놓는다. 표시 버전 v3.9a(Windows 3.9.1.0).
- 변경 대상: `screen_text/guide.py`(신규 `UsageGuide`), `screen_text/window.py`, `app_info.py`, `tests/test_screen_text_guide.py`(신규)·`tests/test_screen_text_ui.py`·`tests/test_ui.py`·`tests/test_packaging.py`, `docs/SCREEN_TEXT.md`·`docs/TESTING.md`·`docs/ARCHITECTURE.md`, `README_detail.md`(현재 소스 버전·빌드 파일명·다운로드 절), `AGENTS.md`(기록 관리).
- 데이터 영향: 없음. DB v17·Export v2·salt·설정 키·바로가기 6슬롯·인식 엔진·의존성 유지. 그림 파일·새 설정 키·파일·네트워크·로그를 만들지 않는다.
- 제외 범위: GitLab Release 게시, 애니메이션의 키보드 포커스·소리.
- 시작 시 사용자 변경: `AGENTS.md` 4줄(저장소 절 push 보류 1줄, 기록 관리 3줄)·`docs/RELEASE_HISTORY.md` 수정과 미추적 `docs/work/` 5개를 커밋하지 않고 보존했다. `AGENTS.md`는 `HEAD` 내용에 이번 한 줄만 더한 사본을 인덱스에 올려(`git hash-object -w` + `update-index --cacheinfo`) 사용자 4줄이 커밋에 섞이지 않게 했다.

## 완료 조건

- [x] `UsageGuide`: QPainter 벡터만, `QVariantAnimation` 0→1 6000ms 무한 반복, 세 단계(영역 고르기·글자 읽기·표로 붙여넣기), 설명 줄·단계 점, `start/stop/restart/is_running/step/set_progress`, 보이면 시작·숨기면 정지, 왼쪽 클릭 시 처음부터.
- [x] 처음 화면 `intro_guide`+`tips_label`, 결과 화면 `help_button`, `guide_page`(`help_guide`·`back_button`). [돌아가기]는 결과를 다시 채우지 않는다(고친 글자·표·탭·상태 유지). 결과가 없으면 처음 화면으로 간다.
- [x] 기존 메시지 문구·시험 기대는 그대로. 수명 호출(`cancel_work`·`hide_owned_popups`·`shutdown`·`fit_to_screen`·`closeEvent`)이 사용 방법 화면에서도 동작.
- [x] 100/125/150% 합성 배율 quick, PowerShell `release`.
- [x] 이 PC에서 사용자가 실제 EXE를 실행해 기능이 동작함을 확인했다(v3.9 때와 v3.9a 지금).
- [ ] 업무 PC의 보안 프로그램 캡처 차단·한글 표 붙여넣기·혼합 DPI/KVM, 사용 가능 높이 약 400px 이하 화면(수동).

## 결정과 진행

- 2026-10-09: 설계(사용자 승인) → 시험 먼저 작성. RED: `tests/test_screen_text_guide.py`는 `screen_text.guide` 없음(`ModuleNotFoundError`)으로 수집 실패, `test_screen_text_ui.py` 새 시험 12개와 `test_ui.py::test_settings_credit_uses_v39a_metadata`가 실패(`APP_VERSION == "v3.9a"`). `_windows_version_parts("v3.9a") == (3, 9, 1, 0)`는 함수가 일반적이라 처음부터 통과(회귀 방지용).
- 그림 구성(좌표 420×190, 위젯 크기에 비율을 지켜 줄이고 가운데에 둔다): ① 스캔 문서 카드(회색 줄·3×4 표)와 마우스 화살표가 표의 왼쪽 위에서 오른쪽 아래로 끌며 주황 `#E8590C` 점선 사각형이 자란다. ② 주황 상자가 칸마다 나타나며 위에서 아래로 훑는 선이 지나가고, 회색 자리표시가 구분/점검/위반·대전/42/3·세종/18/1·충북/51/4로 바뀐다. ③ 문서가 왼쪽으로 물러나고 "한글·엑셀" 시트가 오른쪽에 나타나며 화살표를 따라 파란 점이 흐르고 값이 채워진다. 51 칸은 노랑 `#FFE58A`에 "확인" 꼬리표. 각 단계 끝은 잠깐 멈춰 보여 주고, 한 바퀴의 처음과 끝은 그림·설명·점이 함께 흐려져 되풀이가 끊겨 보이지 않는다.
- 설계 판단: 정확한 위젯 배율에서 흐려지지 않게 글자 크기는 정수 px, 번짐 방지를 위해 장면 좌표 변환은 정수로 반올림한 평행이동 + 균일 배율만 쓴다. 설명 줄은 13→12→11px로 줄여 맞추고 그래도 넘치면 말줄임.
- 최소 크기: 애니메이션 최소 높이 160px(요구). 이 때문에 도구 창 최소 높이가 335→399px(그림자 여백 0)로 늘었다. 사용 가능 높이가 약 400px보다 낮은 화면에서만 창이 화면보다 커질 수 있다(125%·150%의 일반 해상도에서는 해당 없음).
- 시험 환경: 기존 시험 `test_null_captured_image_*` 2개와 `test_blocked_recapture_*` 1개가 `hasFocus()`를 즉시 확인해, 사용자가 다른 앱(Chrome·KakaoTalk)을 쓰는 중이면 OS 포그라운드를 못 얻어 실패했다(HEAD 변경 없이도 재현: 실패 시 포그라운드 프로세스는 chrome.exe/KakaoTalk.exe, 터미널이 포그라운드일 때 시작한 프로세스는 통과). 코디네이터 지시로 `tests/test_screen_text_ui.py`의 세 검사를 `win.focusWidget() is <위젯>`으로 바꿨다(다른 검사는 약화하지 않음, 다른 시험 파일은 건드리지 않음).
- 2026-10-09 (검토 반영): CPU 비용을 고쳤다. 애니메이션이 매 프레임(초당 약 60번) `update()`를 불러 창 그림자 효과(`QGraphicsDropShadowEffect`, 508×608 표면 전체)가 계속 다시 흐려졌다. 검토자의 오프스크린 측정은 코어 하나의 32.4%(그림자 없이 10.9%, 멈추면 1.0%)였고 같은 탐침(`probe_cpu.py`)을 이 PC에서 돌린 값은 수정 전 35.9%(62.5fps)였다. `valueChanged`는 진행이 1/144 이상 나아가거나 단계가 바뀔 때만 다시 그리게 하고(`set_progress`·`restart`는 항상) 그릴 때마다 만들던 QFont·QFontMetrics 계산을 글꼴·크기 변경 때만 비우는 캐시로 바꿨다. 그림자 효과는 그대로 둔다. 수정 뒤 실제 측정 6회: 10.2·12.9·12.5·18.7·12.1%(약 21fps, 18.7%는 사용자가 PC를 쓰는 중의 이상치)와 그림자를 끈 3.5~5.1%, 멈추면 1.0~2.6%. 1초 동안 그린 횟수는 수정 전 62번, 수정 뒤 30번 이하(시험 `test_repaints_are_throttled_to_about_24_per_second`).
- 2026-10-09 (검토 반영): 루트 `dist/`에는 사용자가 v3.9·v3.8e 파일을 지운 뒤 `기후노트_v3.9a.exe`만 있다. 이전에 검증한 사본은 `output/harness/20261009-021809-e30a49762e/dist/`(v3.9)와 `output/harness/20261005-112836-574edfc8b2/dist/`(v3.8e)에 있다. 포커스 시험 `test_null_captured_image_*` 2개는 시작 때 이미 있던 포커스가 통과를 만들지 않도록 먼저 `clearFocus()`하고(`_reappear`에서 `setFocus`를 빼면 실패함을 확인), `docs/TESTING.md`·`docs/ARCHITECTURE.md`에 guide를 더했다. `README_detail.md` 다운로드 절을 v3.9a로 바꿨다(서버 push 보안 검사 5종 통과 문구는 v3.9a에 대한 근거가 없어 뺐다).
- 2026-10-09 (사용자 확인): 사용자가 이 PC에서 실제 EXE를 실행해 v3.9(앞서)와 v3.9a(지금) 모두 기능이 동작함을 확인했다. 업무 PC 항목(보안 프로그램 캡처 차단·한글 표 붙여넣기·혼합 DPI/KVM)은 계속 수동 미확인이다.
- 1차 150% quick(`20261009-121848-acdb853544`)은 새 시험이 그림 영역을 논리 픽셀로 잘라 3단계 노란 칸이 빠져 실패(시험 오류). 장치 배율을 곱해 고친 뒤 재검증했다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `pytest tests/test_screen_text_guide.py tests/test_screen_text_ui.py tests/test_packaging.py tests/test_ui.py::test_settings_credit_uses_v39a_metadata` (RED, 구현 전) | 실패(의도) | 하네스 실행 ID 없음 (pytest 직접 실행) | guide 수집 실패, ui 새 시험 12개·credit 1개 실패(+ 당시 포그라운드 때문에 기존 포커스 시험 2개 실패) |
| 다시 그리기 제한 시험 RED (`REPAINT_STEP = 0`으로 구 동작 재현) | 실패(의도) | 하네스 실행 ID 없음 | `assert 62 <= 30`(1초에 62번 그림). 제한을 넣은 뒤 같은 시험 통과. 포커스 시험은 `_reappear`에서 `setFocus`를 빼면 두 개 모두 실패 |
| `pytest tests/test_screen_text_guide.py tests/test_screen_text_ui.py tests/test_screen_text_capture.py` (검토 반영 뒤, 2회) | 통과 | 하네스 실행 ID 없음 (pytest 직접 실행) | 100개 통과(9.7초) ×2. 그 전 포커스 검사 교체 뒤에는 96개 통과 |
| `tools/verify.py quick --tests tests/test_screen_text_guide.py tests/test_screen_text_ui.py tests/test_optional_mini_apps.py tests/test_packaging.py tests/test_ui.py::test_settings_credit_uses_v39a_metadata` (100%, 최종) | 통과 | `20261009-132434-fbda78d626` (`output/harness/`) | 175개 통과, 실패·오류·skip 0. HEAD `fa3be4a` |
| 같은 명령, `QT_SCALE_FACTOR=1.25` | 통과 | `20261009-132456-8e830675d0` (`output/harness/`) | 175개 통과 |
| 같은 명령, `QT_SCALE_FACTOR=1.5` | 통과 | `20261009-132518-a62ba5f42e` (`output/harness/`) | 175개 통과 |
| PowerShell `.\.venv\Scripts\python.exe tools/verify.py release` | 통과 | `20261009-132546-f2aab9b4b1` (`output/harness/`) | 1,803개 통과(pytest 235초), PyInstaller 빌드 60초, 격리 EXE 3개 시나리오(`fresh`·`existing`·`blocked`) 통과. HEAD `fa3be4a`. EXE `기후노트_v3.9a.exe` 93,874,139 bytes, SHA-256 `ED4BBD6B15E6224028629A14F33C69DCB0CBAF936E2DB402EE2ED102E4790FDF`, 파일 버전 3.9.1.0, 서명 없음 |
| 빌드 TOC (`output/harness/20261009-132546-f2aab9b4b1/build/build/Analysis-00.toc`) | 통과 | 같은 실행 | `screen_text\models\rec.onnx`·`onnxruntime\capi\onnxruntime.dll`·`numpy`·`html`·`screen_text.guide` 포함. `mingw64`·`Program Files\Git` 항목 0건(`libcrypto-3.dll`·`libssl-3.dll`은 Python313 `DLLs`) |
| `dist/기후노트_v3.9a.exe` 배치 확인 | 통과 | 위 실행의 `dist/`에서 복사(이전 v3.9a 사본 교체) | 두 파일 SHA-256 일치, 크기 93,874,139 bytes. 루트 `dist/`에는 v3.9a만 있다(v3.9·v3.8e 사본은 `output/harness/20261009-021809-e30a49762e/dist/`·`output/harness/20261005-112836-574edfc8b2/dist/`) |
| CPU 탐침 `probe_cpu.py` (오프스크린, 애니메이션 중) | 측정 | 하네스 실행 ID 없음 | 수정 전 35.9%(62.5fps), 수정 뒤 10.2~12.9%(약 21fps, 이상치 18.7%), 그림자 끔 3.5~5.1%, 멈춤 1.0~2.6%. 사용자의 PC 사용량에 따라 흔들리는 값 |
| 합성 화면 PNG (실제 데스크톱 캡처 아님) | 저장 | `output/harness/20261009-132546-f2aab9b4b1/screens/usage-guide-*.png` | 100/125/150% 처음 화면·결과 화면·사용 방법 화면 3프레임, 사용 가능 높이 410·460px 압축 창 |
| 이전 시도(최종 증거 아님) | 참고 | 첫 구현본: quick `20261009-125957-794ed28c6e`·`20261009-130017-45da33c445`·`20261009-130038-b85af8d760`(각 171개), release `20261009-130109-b8d6977c99`(1,799개, EXE 93,874,175 bytes, SHA-256 `768B4178…F202`). 그 이전: `20261009-121801-5bc1c4371a`·`20261009-121828-2bcd0aabba`(168개), `20261009-121848-acdb853544`(시험 오류 1개 실패), `20261009-123709-aa79b66e2b`(포그라운드 때문에 기존 포커스 시험 실패) | CPU 수정 전 코드의 결과다. 현재 입력의 근거는 위 최종 줄이다 |

현재 입력에 대한 실제 결과만 기입한다. 이전 버전의 테스트 수를 현재 통과로 복사하지 않는다.

## 미해결과 인계

- 남은 문제 / 수동 확인: 업무 PC의 보안 프로그램 캡처 차단·한글 표 붙여넣기·혼합 DPI/KVM, 사용 가능 높이 약 400px 이하 화면(애니메이션 최소 높이 160px 때문에 창 최소 높이가 335→399px로 늘었다). 이 PC의 실제 EXE 동작은 사용자가 확인했다.
- 변경한 정본 문서: `docs/SCREEN_TEXT.md`(사용법 안내 항목), `docs/TESTING.md`·`docs/ARCHITECTURE.md`(guide), `AGENTS.md`(기록 관리), `README_detail.md`(현재 소스 버전·빌드 파일명·다운로드 절).
- 다음 행동: GitLab Release에 v3.9a EXE를 올릴 때 위 SHA-256과 비교한다(승인 필요).
- 배포·커밋·push 여부: 로컬 커밋만 했다(push는 조정자가 한다). GitLab Release 게시는 하지 않았다.
