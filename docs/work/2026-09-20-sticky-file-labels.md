# 작업 기록: 스티키 B+C 파일 라벨 구현

작성일: 2026-09-20 / 상태: 구현·검증 완료, 관련 변경 커밋

## 목표와 범위

- 사용자 승인한 B+C 조합(둥근 옅은 라벨 + PDF/HWP/XLSX 파일 종류 배지)을 두 스티키 보기에서 구현하고 연결 버튼 테두리를 통일한다.
- 버전 v3.7b/날짜/Windows 3.7.2.0 유지. AGENTS.md 업데이트와 로컬 커밋까지 수행한다. EXE 빌드·push는 이번 요청 범위에 추가하지 않는다.
- 변경 예상: 공용 스티키 링크 표시, 기존 체크박스 표시와의 조합, 툴바 버튼, 관련 UI/데이터 보존 검사, 개발 계약 문서.
- DB v17·Export v2·저장 HTML/href·원래 본문/서식·salt·설정·의존성 보존. 배지/라벨/주의 표시는 문서 문자로 삽입하지 않는다.
- 시작 변경: `.gitignore`, `AGENTS.md`, `docs/RELEASE_HISTORY.md`의 기존 변경과 9/11·9/17 미추적 기록을 보존하고 이번 커밋에서 제외한다. 이번 대화의 디자인 기록은 관련 문서로 포함한다.

## 완료 조건

- [x] 두 보기의 라벨/파일 종류 배지·끊김 표시·툴바 테두리.
- [x] 기존 문구/서식/HTML/복사/Undo 보존과 실제 편집·선택·Ctrl+클릭·줄바꿈·스크롤 확인.
- [x] 관련 하네스·합성 UI 캡처, 결과 summary와 실행 ID 기록.
- [x] UI/데이터 계약 및 AGENTS.md 갱신. 관련 변경만 로컬 커밋하며 기존 미커밋 기록은 보존한다.

## 결정과 진행

- 기존 편집기는 QTextEdit이고 저장된 anchor를 공용으로 사용한다. 파일 배지를 저장 문자열에 넣지 않기 위해 표시용 서식과 그리기를 사용한다.
- Qt의 [QSyntaxHighlighter 계약](https://doc.qt.io/qt-6/qsyntaxhighlighter.html#setFormat)에 따라 문서 서식과 별개인 표시용 범위를 사용하고, 테스트에서 본문/HTML/수정 상태/Undo 불변을 직접 검증한다.
- `ui_sticky_link_labels.py`에 라벨 기하/그리기와 공용 highlighter를 두었다. 링크 경계는 UTF-16 grapheme 단위이며 이모지·결합 문자의 글자 간격 단위를 측정해 공간을 확보한다. 체크박스 마스크도 같은 highlighter에 포함해 서로의 표시 서식을 지우지 않게 한다.
- 일반 문구는 네이티브 QTextEdit가 계속 편집·선택·복사한다. 경계 grapheme만 원래 글꼴로 다시 그리며 배지/주의 문자는 삽입하지 않는다. 링크가 없는 노트는 라벨 그리기를 실행하지 않는다.
- 링크 뒤 16px를 표시상 예약해 상태 검사 결과에 따른 줄바꿈 이동을 피한다. 경고는 오른쪽 고정 레일 대신 해당 라벨 끝에 표시하며 Ctrl+클릭/경고 클릭/툴팁은 실제 라벨 위치를 사용한다.
- 버튼은 주변 서식 버튼과 같은 QPushButton QSS·NoFocus·체인 아이콘으로 변경했다. QSS의 24×22px는 내용 상자이며 실제 바깥 크기는 이 환경에서 26×24px로 주변 버튼과 같다.
- 최초 검사 실패는 제거한 경고 레일을 참조하던 이전 테스트 3개와 QPushButton의 테두리 포함 크기 기대값 1개였다. 새 테스트를 추가한 다음 실행에서는 저장 테스트가 존재하지 않는 메서드를 호출한 1건이 실패했고 실제 공개 `save()` 호출로 수정했다. 최종 관련 검사에서는 모두 통과했다.

## 검증 증거

| 범위 | 상태 | 실행 ID / summary | 유의사항 |
|---|---|---|---|
| 최초 관련 quick | 실패, 130 통과/4 실패 | [20260920-193246-43967a5b40](../../output/harness/20260920-193246-43967a5b40/summary.md) | 이전 경고 레일/크기 기대값 갱신 |
| 신규 검사 포함 quick | 실패, 152 통과/1 실패 | [20260920-193524-683b5a551e](../../output/harness/20260920-193524-683b5a551e/summary.md) | 테스트의 저장 메서드 오기 수정 |
| 관련 quick | 통과, 154개 | [20260920-193732-5b601544e8](../../output/harness/20260920-193732-5b601544e8/summary.md) | 두 보기 저장 왕복·실제 마우스 드래그·Undo·그리기/상태 변경 무수정·복사·Unicode 경계·픽셀색·배지 Ctrl+클릭·경고 메뉴 |
| full | 통과, 743개 | [20260920-193942-f66fa6633a](../../output/harness/20260920-193942-f66fa6633a/summary.md), [result.json](../../output/harness/20260920-193942-f66fa6633a/result.json) | quick 이후 런타임/테스트 수정 없음, 계약 문서 갱신 뒤 실행. 검사 전후 입력 동일 |

관련 명령: `.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_ui_sticky_link_labels.py tests/test_ui_sticky_file_links.py tests/test_ui_sticky.py tests/test_ui_sticky_panel.py`, 이후 `.\.venv\Scripts\python.exe tools/verify.py full`.
합성 실제 Qt 캡처: 실행 폴더의 `sticky-label-floating.png`, `sticky-label-panel.png`, `selected-link-floating.png`, `selected-link-panel.png`.
최종 full의 두 보기 캡처를 직접 확인했다. 원문/서식/Undo·DB 암호화 저장 왕복·Export/Import·수명/잠금 관련 기존 검사는 같은 full에 포함됐다. 기존 scipy import 경고 1건은 기능 실패가 아니며 이번 작업에서 의존성을 바꾸지 않았다.

## 미해결과 인계

- 실제 IME/혼합 DPI/KVM/사용자 EXE 확인은 별도. 기존 보안·라이선스 보류를 유지한다.
- 버전 파일·DB/암호화·설정·lock·기존 dist EXE는 변경하지 않았다. 새 디자인의 EXE 빌드·push·배포는 미수행이다.
