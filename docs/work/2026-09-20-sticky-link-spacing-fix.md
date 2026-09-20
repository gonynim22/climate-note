# 작업 기록: 스티키 링크 배지·간격 개선

작성일: 2026-09-20 / 상태: 구현·관련 검사 완료, 소스 커밋 후 빌드 예정

## 목표와 범위

- 배지 글자 9→8px, 채움 높이 13→11px와 좌우 여백 축소. 라벨 테두리 안쪽 간격을 확보한다.
- 정상 링크 뒤 16px 상시 경고 공간을 없애고 외부 간격 2px로 줄인다. 경고는 필요한 상태에서만 표시 공간을 둔다.
- 버전 v3.7b 유지. 사용자 추가 요청대로 AGENTS.md 업데이트와 관련 변경 커밋 후 해당 소스로 release 빌드·격리 검증·dist 배치.
- 본문/HTML/href/Undo·DB v17·Export v2·salt·설정·의존성 보존. 실사용 앱/데이터를 테스트하지 않는다.
- 시작 시 기존 `.gitignore`·AGENTS.md·릴리스 이력 변경과 9/11·9/17 미추적 기록은 보존·커밋 제외. 직전 간격 조사 기록은 이번 관련 기록에 포함한다.

## 완료 조건

- [x] 두 편집기의 배지 크기·테두리 여유와 정상 링크 뒤 간격 개선.
- [x] 상태 전환·줄바꿈·연속 링크·Unicode·복사·선택·Undo·저장 보존 검증.
- [ ] UI/아키텍처 계약·AGENTS.md 갱신과 관련 검사 후 소스 커밋.
- [ ] 커밋 후 release 전체 검사·격리 EXE 시나리오·해시/Qt 대조 및 dist 배치.

## 결정과 진행

- [직전 조사](2026-09-20-sticky-link-spacing-review.md)에서 정상 링크 뒤 16px 빈 공간과 배지/테두리 접촉을 두 편집기에서 재현했다.
- 상태 전환 때문에 QSyntaxHighlighter.rehighlight로 문서 revision을 바꾸면 안 된다. Qt 표시용 layout 서식만 갱신하는 작은 경로를 합성 문서로 먼저 확인한다.
- [Qt QTextLayout 추가 서식](https://doc.qt.io/qt-6/qtextlayout.html#setFormats)과 [markContentsDirty](https://doc.qt.io/qt-6/qtextdocument.html#markContentsDirty)를 사용하는 합성 실험 `warning-layout-76b0c1af`에서 실제 커서 기하 14px 축소와 HTML/본문/revision/modified/Undo/수정 신호 불변을 확인했다. 실제 구현에도 마지막 grapheme의 표시 서식만 바꾸는 경로를 적용했다.
- 배지 8px·좌우 padding 3px·최대 높이 11px, 작은 줄에서는 상하 inset 2px가 유지되도록 높이를 줄인다. 기본 Malgun Gothic 13px에서 PDF 배지 폭은 26→21px, 높이는 13→11px, 테두리 안쪽 빈 간격은 0→1px다. 정상 링크 외부 간격은 16→2px, 마지막 글자의 advance 끝부터는 20→6px로 줄었다.
- 경고가 필요한 경우만 외부 공간 14px를 추가하며 다른 링크/체크박스 표시 서식을 유지한다. 상태 변화로 줄바꿈은 바뀔 수 있으나 본문·HTML·복사·revision·Undo는 바뀌지 않는다. 조합 중 블록의 preedit 서식은 건드리지 않고 조합 종료 뒤 공간/아이콘을 반영한다.
- 최초 관련 검사 1건은 테스트가 정상 캐시를 넣은 뒤 이전 경고 공간 좌표로 마우스를 드래그해 뒤 문구까지 선택한 실패다. 캐시 상태가 바뀐 뒤 페인트를 기다리지 않고 기하를 갱신하도록 실제 비동기 콜백과 합성 상태 helper를 맞췄다. 별도 회귀 검사로 결과 콜백 직후 네이티브 커서 위치를 확인한다.
- 100/125/150% 합성 배율의 실제 Qt 캡처를 확인했다. 11/12/13px 본문에서 배지가 테두리와 분리되고 정상 링크 뒤의 공백이 축소됐다. 합성 IME preedit 검사는 실제 한글 키보드/혼합 모니터 실기 확인을 대신하지 않는다.

## 검증 증거

| 범위 | 상태 | 실행 ID / 결과 |
|---|---|---|
| 최초 관련 quick | 실패: 164 통과/1 실패 | [20260920-205213-1e930b4135](../../output/harness/20260920-205213-1e930b4135/summary.md): 상태 갱신 전후 좌표 처리 보완 |
| 최종 관련 quick | 통과: 166개 | [20260920-205445-b49a843d96](../../output/harness/20260920-205445-b49a843d96/summary.md), [result.json](../../output/harness/20260920-205445-b49a843d96/result.json) |
| 125% quick | 통과: 89개 | [20260920-205532-2c2933eb1b](../../output/harness/20260920-205532-2c2933eb1b/summary.md), [result.json](../../output/harness/20260920-205532-2c2933eb1b/result.json) |
| 150% quick | 통과: 89개 | [20260920-205614-70fb806907](../../output/harness/20260920-205614-70fb806907/summary.md), [result.json](../../output/harness/20260920-205614-70fb806907/result.json) |
| release | 미실행 | 소스 커밋 후 실행 |

관련 검사 명령: `.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_ui_sticky_link_labels.py tests/test_ui_sticky_file_links.py tests/test_ui_sticky.py tests/test_ui_sticky_panel.py`.
배율별 검사는 별도 PowerShell 프로세스에서 `QT_SCALE_FACTOR=1.25`/`1.5`를 지정해 `quick --tests tests/test_ui_sticky_link_labels.py`로 실행했다. 각 실행의 `compact-label-*.png`와 기존 두 보기 캡처를 보존한다. 앱 코드/테스트/계약 문서는 최종 quick 이후 변경하지 않았다.

## 미해결과 인계

- 실제 IME/혼합 DPI/KVM·Win+D·보안/라이선스/서명 보류는 별도다.
- push·게시 제외. 기존 EXE 보존 후 새 산출물을 배치한다.
