# 작업 기록: v3.8a 환산기 드롭다운 깜빡임·디자인 통일

작성일: 2026-09-24 / 상태: 구현·검증·빌드 완료

## 목표와 범위

- 목표: [조사 기록](2026-09-24-unit-converter-dropdown-investigation.md)의 Qt roll 효과를 억제하고 FROM/TO·기체 물질·온도 모드의 드롭다운 디자인을 통일한다.
- 변경 대상: 환산기 공통 콤보 UI, 조건/본체 배선, 관련 UI 검사, UI/아키텍처/검증 지침과 AGENTS.md.
- 데이터 영향: 표시/팝업 처리만 변경. DB v17·Export v2·salt·본문·설정 키·바로가기·계산 정의·메모리 기록 계약 유지.
- 버전: 사용자 요청대로 v3.8a/2026. 9. 24./Windows 3.8.1.0 유지. 신규 EXE 빌드·격리 검증과 로컬 커밋 포함.
- 제외 범위: 원격 push/게시, 의존성 변경, 조건 펼침 영역 재설계.
- 시작 시 사용자 변경: `.gitignore`, `AGENTS.md`, `docs/RELEASE_HISTORY.md` 및 미추적 보안/버전/릴리스 상태/환산기 시안 기록. 보존하고 이번 변경만 커밋한다.

## 완료 조건

- [x] 공통 드롭다운·즉시 팝업 표시, 전역 효과 설정 복원.
- [x] 소스 Qt 창의 실제 마우스/키보드 선택·Esc·숨김/잠금·100/125/150% 배치 확인.
- [x] release 전체 검사·새 EXE·격리 3개 시나리오·코드/Qt DLL 대조.
- [x] AGENTS 및 정본 문서·현재 증거 갱신, 기존 dist 파일 유지 후 새 파일 배치. 이번 변경만 로컬 커밋 대상에 포함.

## 결정과 진행

- 2026-09-24: 공통 `ConverterCombo`를 두 UI 모듈이 사용한다. FROM/TO는 닫힌 상태에 기호, 조건은 설명을 표시한다. 28px 높이/13px 글꼴·벡터 화살표·목록 행 스타일을 통일한다.
- Qt `UI_AnimateCombo`는 `showPopup()`의 동기 호출 동안만 끄고 `finally`에서 이전 값으로 복원한다. 앱 전체에 지속 설정하지 않는다. 기본 QComboBox의 입력/선택/팝업 소유권을 유지한다.
- 최종 코드: `ConverterCombo`의 공통 그리기/목록 delegate를 조건과 FROM/TO가 공유한다. 단위용 `UnitCombo`는 기호 표시와 목록 너비 정책만 유지한다. 4개 콤보에서 클릭 직후 실제 팝업 1회 표시, QRollEffect 미생성, 선택/Alt+Down/Esc/숨김을 효과 ON/OFF 양쪽에서 확인한다. 같은 높이/화살표 픽셀과 목록 가독성, 예외 시 효과 복원도 확인한다.
- 신규 마우스 검사 최초 2회는 Qt의 초기 클릭 release 보호 구간에서 선택하여 각각 8건/4건 실패했다. Windows native 커서 이동과 `doubleClickInterval`을 반영한 입력 순서로 보정했다. 즉시 표시 검사는 대기 전 동기 assertion을 유지하며, 대기로 flicker 검사를 우회하지 않는다. 앱 코드는 이 보정에서 변경하지 않았다.
- 125% 기체 조건, 150% 온도 모드/목록 PNG에서 통일된 테두리/화살표와 글자 배치를 검토했다. 소스 Qt 캡처이며 EXE 직접 클릭 증거와 구분한다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 | 유의사항 |
|---|---|---|---|
| quick + 전체 환산기 UI, 신규 클릭 검사 최초 | 실패: 8 / 통과: 105 | `20260924-144247-5ec2936ded` / [summary](../../output/harness/20260924-144247-5ec2936ded/summary.md) | 초기 release 보호 시간 내 선택. 제품 수정 완료 근거로 쓰지 않음 |
| quick + 전체 환산기 UI, native 이동 대기 보정 | 실패: 4 / 통과: 109 | `20260924-144335-bb47453dcf` / [summary](../../output/harness/20260924-144335-bb47453dcf/summary.md) | 동일 입력 보호 구간 이슈가 남음 |
| quick + `tests/test_ui_unit_converter.py::test_converter_dropdown_opens_without_transient_image_and_selects` | 통과: 65 | `20260924-144446-b6e275b547` / [summary](../../output/harness/20260924-144446-b6e275b547/summary.md) | 실제 팝업 즉시 표시 검사 유지, 선택 순서 보정 |
| `QT_SCALE_FACTOR=1.25` quick + `tests/test_ui_unit_converter.py` | 통과: 113 | `20260924-144645-4f40aaea3b` / [summary](../../output/harness/20260924-144645-4f40aaea3b/summary.md) · [result](../../output/harness/20260924-144645-4f40aaea3b/result.json) | 현재 앱/검사 코드. 실제 혼합 DPI 아님 |
| `QT_SCALE_FACTOR=1.5` quick + `tests/test_ui_unit_converter.py` | 통과: 113 | `20260924-144735-8af2ee1df7` / [summary](../../output/harness/20260924-144735-8af2ee1df7/summary.md) · [result](../../output/harness/20260924-144735-8af2ee1df7/result.json) | 현재 앱/검사 코드. 실제 혼합 DPI 아님 |
| `.\.venv\Scripts\python.exe tools/verify.py release` | 통과: 1,082개 + 새 빌드 + EXE 3개 시나리오 | `20260924-144904-bd1ae56a4a` / [summary](../../output/harness/20260924-144904-bd1ae56a4a/summary.md) · [result](../../output/harness/20260924-144904-bd1ae56a4a/result.json) · [smoke](../../output/harness/20260924-144904-bd1ae56a4a/smoke.json) | 실패/오류/skip 0, 검사 전후 입력 불변. 실사용 데이터 접근 없음 |
| EXE 번들/Qt/리소스 대조 | 통과 | [bundle-verification.json](../../output/harness/20260924-144904-bd1ae56a4a/bundle-verification.json) | 새 공통 콤보 포함 6개 모듈의 전체 중첩 code object가 현재 소스 compile 결과와 일치. PNG/SVG·Qt DLL 3개 바이트 일치 |
| dist 배치·SHA-256 재확인 | 통과 | [dist-placement.json](../../output/harness/20260924-144904-bd1ae56a4a/dist-placement.json) | 배치 시 표준 v3.8a 경로에 기존 파일이 없어 신규 배치. 다른 dist 파일은 그대로 유지 |

## 산출물과 커밋 범위

- [새 EXE](../../dist/기후노트_v3.8a.exe): **58,989,550 bytes**, SHA-256 `ABCF9D62DAB8E75A412765CCB9CD145E0B20F51753872D9250B5A13B759AF0FE`.
- 앱 표시 v3.8a, 출시일 2026. 9. 24., Windows FileVersion/ProductVersion 3.8.1.0. `app_info.py` 변경 없음. Qt6Core/Gui/Widgets는 검증한 venv의 6.11.2와 해시 일치.
- DB v17·Export v2·salt·사용자 설정/본문/바로가기 보존은 전체 회귀와 합성 EXE 기존 데이터 시나리오에서 확인했다. 사용자 실데이터는 검사하지 않았다.
- 검증 후 앱/테스트 코드는 바꾸지 않았다. AGENTS와 이 기록에 최종 결과만 갱신하고 링크/사실·코드 해시를 재확인했다.
- 커밋 범위: `ui_converter_combo.py`, 기존 환산기/조건 모듈 2개, UI 검사, AGENTS의 이번 추가분, UI/아키텍처/검증 정본, 이번 조사/수정 기록. 커밋은 `fix: 단위 환산기 드롭다운 깜빡임과 디자인 통일`로 식별한다.
- 기존 사용자 AGENTS 변경은 선택적으로 제외하고 작업 폴더에 남긴다. `.gitignore`·릴리스 이력·미추적 보안/버전/릴리스 상태/시안 기록도 커밋에 섞지 않는다. EXE/output은 gitignore 대상이다.

## 미해결과 인계

- 실제 회사 PC·혼합 DPI/KVM·Win+D·정상 종료·Defender·서명/라이선스 후속은 별도 수동 확인.
- 원격 push/게시는 수행하지 않는다.

## 수동 확인 구분

검사일: 2026-09-24 / Windows 11·Python 3.13·Qt 6.11.2 / 합성 배율 100·125·150%.

| 항목 | 상태 | 근거/제한 |
|---|---|---|
| 소스 Qt 실제 마우스/키보드·배율·PNG | 통과 | 위 하네스와 팝업/본체 PNG |
| 새 EXE 주머니→환산기→드롭다운 직접 클릭 | 미실행 | computer-use 초기화/재연결/세션 재설정 후에도 `Computer Use native pipe is unavailable ... os error 2`. 기존 사용자 앱은 조작하지 않음 |
| 정상 종료 직전 저장·특정 PC 설정/휴지통 | 미확인 | 자동 저장 회귀/EXE smoke와 구분 |
| Win+D/Explorer·음수 좌표/혼합 DPI/KVM | 미확인 | 물리 장치 수동 확인 필요 |
| Defender | 미확인 | 별도 수동 확인 |
| 라이선스·SBOM·Qt 고지·서명 | 미확인 | [기존 보류 과제](../RELEASE_HISTORY.md) 유지 |
