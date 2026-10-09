# 작업 기록: 화면 글자 따기 사용법 안내 (v3.9a)

작성일: 2026-10-09 / 상태: 로컬 구현·검증 완료(업무 PC 수동 확인 대기)

## 목표와 범위

- 목표: 처음 화면 [영역 고르기] 아래 약 300px 빈 곳에 벡터 사용법 애니메이션과 팁 두 줄을 채우고, 결과 화면 [복사] [다시 고르기] 줄 오른쪽 끝에 [사용법]을 둔다. [사용법]은 같은 애니메이션 화면을 열고 [돌아가기]는 결과를 그대로 돌려놓는다. 표시 버전 v3.9a(Windows 3.9.1.0).
- 변경 대상: `screen_text/guide.py`(신규 `UsageGuide`), `screen_text/window.py`, `app_info.py`, `tests/test_screen_text_guide.py`(신규)·`tests/test_screen_text_ui.py`·`tests/test_ui.py`·`tests/test_packaging.py`, `docs/SCREEN_TEXT.md`, `README_detail.md`(현재 소스 버전·빌드 파일명), `AGENTS.md`(기록 관리).
- 데이터 영향: 없음. DB v17·Export v2·salt·설정 키·바로가기 6슬롯·인식 엔진·의존성 유지. 그림 파일·새 설정 키·파일·네트워크·로그를 만들지 않는다.
- 제외 범위: push·GitLab Release 게시, `README_detail.md` 다운로드 절(v3.9 EXE·해시) 갱신(배포 시점에 한다), 애니메이션의 키보드 포커스·소리.
- 시작 시 사용자 변경: `AGENTS.md` 4줄(저장소 절 push 보류 1줄, 기록 관리 3줄)·`docs/RELEASE_HISTORY.md` 수정과 미추적 `docs/work/` 5개를 커밋하지 않고 보존했다. `AGENTS.md`는 `HEAD` 내용에 이번 한 줄만 더한 사본을 인덱스에 올려(`git hash-object -w` + `update-index --cacheinfo`) 사용자 4줄이 커밋에 섞이지 않게 했다.

## 완료 조건

- [x] `UsageGuide`: QPainter 벡터만, `QVariantAnimation` 0→1 6000ms 무한 반복, 세 단계(영역 고르기·글자 읽기·표로 붙여넣기), 설명 줄·단계 점, `start/stop/restart/is_running/step/set_progress`, 보이면 시작·숨기면 정지, 왼쪽 클릭 시 처음부터.
- [x] 처음 화면 `intro_guide`+`tips_label`, 결과 화면 `help_button`, `guide_page`(`help_guide`·`back_button`). [돌아가기]는 결과를 다시 채우지 않는다(고친 글자·표·탭·상태 유지). 결과가 없으면 처음 화면으로 간다.
- [x] 기존 메시지 문구·시험 기대는 그대로. 수명 호출(`cancel_work`·`hide_owned_popups`·`shutdown`·`fit_to_screen`·`closeEvent`)이 사용 방법 화면에서도 동작.
- [x] 100/125/150% 합성 배율 quick, PowerShell `release`.
- [ ] 업무 PC의 실제 EXE에서 본 모양·좁은 화면 확인(수동).

## 결정과 진행

- 2026-10-09: 설계(사용자 승인) → 시험 먼저 작성. RED: `tests/test_screen_text_guide.py`는 `screen_text.guide` 없음(`ModuleNotFoundError`)으로 수집 실패, `test_screen_text_ui.py` 새 시험 12개와 `test_ui.py::test_settings_credit_uses_v39a_metadata`가 실패(`APP_VERSION == "v3.9a"`). `_windows_version_parts("v3.9a") == (3, 9, 1, 0)`는 함수가 일반적이라 처음부터 통과(회귀 방지용).
- 그림 구성(좌표 420×190, 위젯 크기에 비율을 지켜 줄이고 가운데에 둔다): ① 스캔 문서 카드(회색 줄·3×4 표)와 마우스 화살표가 표의 왼쪽 위에서 오른쪽 아래로 끌며 주황 `#E8590C` 점선 사각형이 자란다. ② 주황 상자가 칸마다 나타나며 위에서 아래로 훑는 선이 지나가고, 회색 자리표시가 구분/점검/위반·대전/42/3·세종/18/1·충북/51/4로 바뀐다. ③ 문서가 왼쪽으로 물러나고 "한글·엑셀" 시트가 오른쪽에 나타나며 화살표를 따라 파란 점이 흐르고 값이 채워진다. 51 칸은 노랑 `#FFE58A`에 "확인" 꼬리표. 각 단계 끝은 잠깐 멈춰 보여 주고, 한 바퀴의 처음과 끝은 그림·설명·점이 함께 흐려져 되풀이가 끊겨 보이지 않는다.
- 설계 판단: 정확한 위젯 배율에서 흐려지지 않게 글자 크기는 정수 px, 번짐 방지를 위해 장면 좌표 변환은 정수로 반올림한 평행이동 + 균일 배율만 쓴다. 설명 줄은 13→12→11px로 줄여 맞추고 그래도 넘치면 말줄임.
- 최소 크기: 애니메이션 최소 높이 160px(요구). 이 때문에 도구 창 최소 높이가 335→399px(그림자 여백 0)로 늘었다. 사용 가능 높이가 약 400px보다 낮은 화면에서만 창이 화면보다 커질 수 있다(125%·150%의 일반 해상도에서는 해당 없음).
- 시험 환경: 기존 시험 `test_null_captured_image_*` 2개와 `test_blocked_recapture_*` 1개가 `hasFocus()`를 즉시 확인해, 사용자가 다른 앱(Chrome·KakaoTalk)을 쓰는 중이면 OS 포그라운드를 못 얻어 실패했다(HEAD 변경 없이도 재현: 실패 시 포그라운드 프로세스는 chrome.exe/KakaoTalk.exe, 터미널이 포그라운드일 때 시작한 프로세스는 통과). 코디네이터 지시로 `tests/test_screen_text_ui.py`의 세 검사를 `win.focusWidget() is <위젯>`으로 바꿨다(다른 검사는 약화하지 않음, 다른 시험 파일은 건드리지 않음).
- 1차 150% quick(`20261009-121848-acdb853544`)은 새 시험이 그림 영역을 논리 픽셀로 잘라 3단계 노란 칸이 빠져 실패(시험 오류). 장치 배율을 곱해 고친 뒤 재검증했다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `pytest tests/test_screen_text_guide.py tests/test_screen_text_ui.py tests/test_packaging.py tests/test_ui.py::test_settings_credit_uses_v39a_metadata` (RED, 구현 전) | 실패(의도) | 하네스 실행 ID 없음 (pytest 직접 실행) | guide 수집 실패, ui 새 시험 12개·credit 1개 실패(+ 당시 포그라운드 때문에 기존 포커스 시험 2개 실패) |
| `pytest tests/test_screen_text_guide.py tests/test_screen_text_ui.py tests/test_screen_text_capture.py` (GREEN, 포커스 검사 교체 뒤) | 통과 | 하네스 실행 ID 없음 (pytest 직접 실행) | 96개 통과. 100/125/150%(`QT_SCALE_FACTOR`)에서도 같은 결과. 그 전 `guide`+`ui` 77~81개 통과를 2회 이상 반복 |
| `tools/verify.py quick --tests tests/test_screen_text_guide.py tests/test_screen_text_ui.py tests/test_optional_mini_apps.py tests/test_packaging.py tests/test_ui.py::test_settings_credit_uses_v39a_metadata` (100%, 최종) | 통과 | `20261009-125957-794ed28c6e` (`output/harness/`) | 171개 통과, 실패·오류·skip 0. HEAD `2a87c2d` |
| 같은 명령, `QT_SCALE_FACTOR=1.25` | 통과 | `20261009-130017-45da33c445` (`output/harness/`) | 171개 통과 |
| 같은 명령, `QT_SCALE_FACTOR=1.5` | 통과 | `20261009-130038-b85af8d760` (`output/harness/`) | 171개 통과 |
| 위 quick 이전 시도(코드 변경 전 상태, 참고용) | 통과 2·실패 2 | 100% `20261009-121801-5bc1c4371a`(168개 통과), 125% `20261009-121828-2bcd0aabba`(168개 통과), 150% `20261009-121848-acdb853544`(시험 오류 1개 실패, 위 참조), 100% `20261009-123709-aa79b66e2b`(포그라운드 때문에 기존 포커스 시험 실패) | 최종 증거가 아님. 현재 입력의 근거는 위 세 줄과 아래 `release` |
| PowerShell `.\.venv\Scripts\python.exe tools/verify.py release` | 통과 | `20261009-130109-b8d6977c99` (`output/harness/`) | 1,799개 통과(pytest 258초), PyInstaller 빌드 66초, 격리 EXE 3개 시나리오(`fresh`·`existing`·`blocked`) 통과. HEAD `2a87c2d`. EXE `기후노트_v3.9a.exe` 93,874,175 bytes, SHA-256 `768B4178F3D4B9F7AD201693670C5640D5893E8A4C1B588A194C87C0F36BF202`, 파일 버전 3.9.1.0, 서명 없음 |
| 빌드 TOC (`output/harness/20261009-130109-b8d6977c99/build/build/Analysis-00.toc`) | 통과 | 같은 실행 | `screen_text\models\rec.onnx`·`onnxruntime\capi\onnxruntime.dll`·`numpy`·`html`·`screen_text.guide` 포함. `mingw64`·`Program Files\Git` 항목 0건(`libcrypto-3.dll`·`libssl-3.dll`은 Python313 `DLLs`) |
| `dist/기후노트_v3.9a.exe` 배치 확인 | 통과 | 위 실행의 `dist/`에서 복사 | 두 파일 SHA-256 일치, 크기 93,874,175 bytes. 기존 `dist/기후노트_v3.9.exe`는 그대로 |
| 합성 화면 PNG (실제 데스크톱 캡처 아님) | 저장 | `output/harness/20261009-130109-b8d6977c99/screens/usage-guide-*.png` | 100/125/150% 처음 화면·결과 화면·사용 방법 화면 3프레임, 사용 가능 높이 410·460px 압축 창 |

현재 입력에 대한 실제 결과만 기입한다. 이전 버전의 테스트 수를 현재 통과로 복사하지 않는다.

## 미해결과 인계

- 남은 문제 / 수동 확인: 업무 PC의 실제 EXE에서 처음 화면 애니메이션의 모양·속도, 결과 화면 [사용법]→[돌아가기] 왕복, 125·150% 실제 화면과 좁은 해상도(사용 가능 높이 약 400px 이하) 확인.
- 변경한 정본 문서: `docs/SCREEN_TEXT.md`(사용법 안내 항목), `AGENTS.md`(기록 관리), `README_detail.md`(현재 소스 버전·빌드 파일명).
- 다음 행동: 배포 시점에 `README_detail.md` 다운로드 절을 v3.9a EXE·해시로 갱신하고 GitLab Release를 올린다(승인 필요).
- 배포·커밋·push 여부: 로컬 커밋만 했다. push·GitLab Release 게시는 하지 않았다.
