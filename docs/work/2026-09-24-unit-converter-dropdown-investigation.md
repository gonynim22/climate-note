# 작업 기록: 단위 환산기 조건 드롭다운 동작 조사

작성일: 2026-09-24 / 상태: 조사 완료(앱 수정 없음)

## 목표와 범위

- 목표: 조건이 있는 분류에서 펼침 버튼·선택 목록의 어색한 동작을 재현하고 원인을 구분한다.
- 변경 대상: 이 조사 기록과 실행별 격리 진단 산출물. 앱 소스 수정은 이번 요청 범위에 포함하지 않는다.
- 데이터 영향: 합성 창/하네스 전용 경로만 사용한다. 실사용 AppData·DB·salt·기존 앱에 접근하지 않는다.
- 제외 범위: 기능 수정, EXE 재빌드, 배포, 커밋, push.
- 시작 시 사용자 변경: `.gitignore`, `AGENTS.md`, `docs/RELEASE_HISTORY.md` 수정 및 미추적 작업 기록 4개(보안 검사, v3.7a 버전, 릴리스 상태, 환산기 재설계 시안). 그대로 보존한다.

## 완료 조건

- [x] 조건 펼침/접힘과 실제 콤보 목록의 이벤트·배치·처리 시간을 확인한다.
- [x] 기존 관련 검사를 현재 소스로 실행하고 조사에서 확인한 현상과 구분한다.
- [x] 원인, 재현 조건, 권장 수정 방향과 미확인 범위를 기록한다.

## 결정과 진행

- 2026-09-24: UI/아키텍처/검증/단위 계약을 읽고 `ui_conversion_conditions.py`, `ui_unit_converter.py`, 기존 UI 검사를 추적했다. 조건 펼침은 `setVisible()`로 본문 레이아웃을 즉시 변경하며, 물질 선택은 요약·조건 행과 결과를 동기적으로 갱신한다. 실제 영향은 격리 측정으로 확인한다.
- 사용자 추가 설명: 클릭 직후 아주 짧은 메뉴 깜빡임과 FROM/TO·조건 드롭다운의 디자인 차이를 보고했다.

### 주원인: Qt 기본 콤보 펼침 효과

- 현 환경은 Qt 6.11.2, DPR 1.0, `UI_AnimateCombo=True`, `SH_ComboBox_Popup=0`이다. 앱 콤보는 기본 `QComboBox.showPopup()`을 그대로 사용한다. FROM/TO의 `UnitCombo.showPopup()`도 너비만 정한 뒤 기본 구현을 호출한다.
- [Qt 6.11.2 QComboBox 구현](https://github.com/qt/qtbase/blob/v6.11.2/src/widgets/widgets/qcombobox.cpp#L3078)은 이 조건에서 150ms `qScrollEffect`를 실행한다. [QRollEffect 구현](https://github.com/qt/qtbase/blob/v6.11.2/src/widgets/widgets/qeffects.cpp#L358)은 목록의 pixmap을 임시 창에 펼친 뒤 실제 목록으로 전환한다.
- 격리된 Windows 창에서 물질/FROM/TO 각각 두 번씩 실제 마우스 누름·놓음과 항목 선택을 수행했다. 기본 설정 6회 모두 `QRollEffect`가 생성되고 약 **154~164ms** 뒤 실제 `QComboBoxPrivateContainer`가 표시됐다. 화면 캡처에서 아래쪽 항목 일부가 먼저 보인 뒤 전체 목록이 나타난다. 이 전환이 사용자가 묘사한 짧은 깜빡임/튀는 느낌에 대응한다.
- 같은 동작에서 그림자만 비활성화해도 **157~166ms** 전환과 부분 목록 표시가 남는다. `UI_AnimateCombo`만 끈 진단 프로세스에서는 임시 효과 창이 0개이고 처음부터 완성된 목록이 표시된다. 그림자와 계산 지연을 주원인으로 볼 근거가 없다.
- 18회 모두 정상 선택 후 팝업이 닫혔다. 실제 팝업은 각 조작에서 Show 1회/선택 후 Hide 1회였으며, 열자마자 닫혔다 다시 열리는 루프는 관측되지 않았다. `SH_Menu_FlashTriggeredItem=0`이므로 선택 항목을 일부러 깜빡이는 별도 효과도 이번 원인이 아니다.
- 초기 `probe.py`는 150ms보다 짧은 시점에 가시성을 판단했고 `QWidget.grab()`을 사용했으므로 메뉴가 안 열렸거나 창 전체가 비었다는 판정 근거로 쓰지 않는다. 결론은 충분한 대기와 합성 창 영역의 실제 화면 캡처를 사용하는 `popup_probe.py`의 A/B 결과에 따른다.

### 디자인 차이: 서로 다른 그리기·크기 정책

- `ui_unit_converter.py:26`의 `UnitCombo.paintEvent()`가 FROM/TO의 둥근 테두리·흰 배경·기호·화살표를 직접 그린다. 카드에서 높이 28px를 고정하고, 목록 최소 너비는 화면 범위 내 320px로 잡는다.
- `ui_conversion_conditions.py:60`과 `:64`의 온도 모드/기체 물질은 기본 `QComboBox`다. 동일한 전용 그리기·높이 정책이 없어 Qt/Windows 기본 화살표·하단선/테두리 표현이 남는다. 물질 콤보는 이번 기본 크기에서 높이 25px·목록 폭 276px였다.
- 공통 QSS는 배경/테두리/글꼴과 목록 일부 속성만 지정하며 `::drop-down`, `::down-arrow`, 열린 상태를 통일하지 않는다. 같은 앱 안에서 사용자 정의 그림과 native 스타일이 섞인다. [Qt 콤보 스타일 예제](https://doc.qt.io/qt-6/stylesheet-examples.html#customizing-qcombobox)도 본체·드롭다운 버튼·화살표·열린 상태·목록을 별도로 지정한다.

### 별도 관찰: 조건 펼침의 즉시 재배치

- 기체 `조건 ▾`를 펼치면 패널 높이 31→198px, FROM y=102→269px, 다른 단위 영역 높이 163→33px, 본문 스크롤 최대값 0→37px로 바뀐다. 스크롤바가 생겨 본문 너비도 308→303px로 줄어든다.
- 수질 `밀도 ▾`에서는 패널 31→138px로 바뀐다. 펼침 자체는 애니메이션 없이 즉시 적용된다. 이는 선택 목록의 150ms 효과와 구분되는 화면 이동이며, 사용자의 추가 설명 이후 주원인으로 취급하지 않는다.

### 권장 후속 수정

- 환산기 드롭다운을 공통 UI 구현으로 묶어 본체·화살표·포커스·행 높이·팝업의 표시 방식을 통일한다. FROM/TO는 닫힌 상태에 기호, 조건은 설명을 표시하는 기존 의미를 유지한다.
- 환산기 팝업의 Qt 기본 roll 효과를 사용하지 않도록 하거나 같은 방식의 안정적인 팝업 표시로 대체한다. 진단에서는 비교를 위해 별도 프로세스의 전역 효과를 껐으며, 이 전역 설정을 앱 전체에 적용하는 구현을 결정한 것은 아니다.
- 실제 클릭 직후의 임시 효과 창/표시 안정성, 클릭 선택·Esc·키보드·잠금/숨김 정리까지 검사한다. 기존 검사는 최종 표시·계산값 중심이어서 중간 150ms 표현을 놓친다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_ui_unit_converter.py` | 통과: 103개, 실패/오류/skip 0 | `20260924-143004-8f2433d4ac` / [summary](../../output/harness/20260924-143004-8f2433d4ac/summary.md) · [result](../../output/harness/20260924-143004-8f2433d4ac/result.json) | 현재 소스. 중간 프레임 품질 통과를 뜻하지 않음 |
| `.\.venv\Scripts\python.exe output/harness/20260924-dropdown-probe/probe.py` | 진단 완료 | `20260924-dropdown-probe` / [result](../../output/harness/20260924-dropdown-probe/result.json) | 조건 레이아웃 관찰. 초기 짧은 팝업 검사는 결론에서 제외 |
| `.\.venv\Scripts\python.exe output/harness/20260924-dropdown-probe/popup_probe.py <mode>` (`baseline`, `noshadow`, `noanimation` 순차 실행) | 비교 완료: 18회 선택 성공 | `20260924-dropdown-probe` / [summary](../../output/harness/20260924-dropdown-probe/summary.md) · [baseline](../../output/harness/20260924-dropdown-probe/baseline/result.json) · [noshadow](../../output/harness/20260924-dropdown-probe/noshadow/result.json) · [noanimation](../../output/harness/20260924-dropdown-probe/noanimation/result.json) | Qt 6.11.2/100%. 독립 진단이며 verify 프로필 결과와 구분. 모듈 SHA-256 및 화면 PNG 보존 |

## 미해결과 인계

- 실제 사용자 EXE·회사 PC·혼합 DPI에서의 동일 증상과 수정 후 체감은 미확인. 본 조사는 현재 소스의 격리 창 재현이다.
- 앱 코드/의존성/DB/salt/설정/EXE 변경 없음. 향후 UI 수정 때 관련 검사와 필요한 배율/EXE 확인을 새로 수행한다.
- 변경한 정본 문서: 없음(원인 조사).
- 배포·커밋·push: 수행하지 않음.
