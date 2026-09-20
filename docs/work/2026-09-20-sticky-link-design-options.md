# 작업 기록: 스티키 링크 표시 디자인 비교

작성일: 2026-09-20 / 상태: B+C 조합 사용자 승인, 실제 구현은 별도 작업 기록으로 이관

## 목표와 범위

- 링크 버튼 테두리 누락 원인을 설명하고 기후노트에 맞는 링크 표시 4안을 만들어 사용자가 선택할 수 있게 한다.
- 현재 `ui_sticky.py`의 두 링크 버튼만 `TransparentToolButton`이며, 인접 굵게/할 일 버튼은 테두리·반투명 배경을 가진 `QPushButton`이다. 시안에서는 동일한 테두리와 체인 아이콘으로 통일한다.
- 앱의 Malgun Gothic 본문, 스티키 4색, 작은 서식 툴바를 기준으로 정상/끊긴 링크를 비교한다.
- 이번 범위는 디자인 비교다. 런타임 소스·DB v17·Export v2·저장 HTML·salt·설정·기존 EXE는 변경하지 않는다. 선택한 디자인의 실제 적용은 후속 작업이다.
- 시작 사용자 변경: `.gitignore`, `AGENTS.md`, `docs/RELEASE_HISTORY.md` 및 기존 미추적 9/11·9/17 문서를 보존한다.

## 완료 조건

- [x] 테두리 누락 원인과 주변 버튼의 기준 확인.
- [x] 하이라이트·연결 라벨·파일 배지·괄호 표시 4안 비교 구성.
- [x] 정상/끊김 상태, 노트색·긴 문구·파일 종류 비교 설정 구현.
- [x] 작은 화면 단일 열, 선택 요청, 호스트 API 미지원 시 대체 안내 구현·정적 점검.
- [x] 데스크톱 940px 브라우저 실제 렌더 확인: 독립 프로필의 headless Chrome에서 최종 네 노트가 모두 표시되는 것을 PNG로 확인.
- [ ] 선택 상호작용의 실제 클릭 확인: 미실행. 360px headless 캡처는 브라우저 최소 레이아웃 폭 때문에 잘려 정확한 해당 폭 검증으로 사용하지 않는다.

## 검증 증거

- 시안: `output/design/sticky-link-options/sticky-link-options.html`.
- 시안 실행 ID `sticky-link-options`: [summary.md](../../output/design/sticky-link-options/summary.md), [result.json](../../output/design/sticky-link-options/result.json).
- `node output/design/sticky-link-options/check-fragment.cjs`: JavaScript 구문·4개 선택안·fragment 형식·외부 요청 없음·호스트 API 가드 정적 검사 통과. `git diff --check` 통과.
- 최초에는 CUA/iab를 사용할 수 없어 정적 검사만 수행했다. HTML 내보내기 뒤의 화면을 확인하지 못한 채 전달했고, 사용자가 제목과 설명만 보인다고 보고했다.
- 원인: `export-preview.py`가 HTML escape된 외부 script를 지울 때 `[^>]*`로 여러 줄을 넘어 매칭하여, 그 앞에 있던 노트 생성 inline script도 함께 제거했다. `render-check/original-html/preview.png`에서 실제 증상을 재현했다. 과거 JavaScript 구문 검사 통과는 최종 파일의 실행 검증이 아니었다.
- 최종 전달 파일은 iframe 없이 네 노트를 정적 마크업으로 포함하는 독립 HTML로 변경했다. JavaScript는 배경색/선택 안내에만 쓰며 시안 표시는 실행에 의존하지 않는다. 아이콘은 번들 SVG로 포함하고 외부 요청·호스트 API 의존성을 제거했다.
- 실행 ID `sticky-link-options/render-check/final-html`: [result.json](../../output/design/sticky-link-options/render-check/final-html/result.json), [PNG](../../output/design/sticky-link-options/기후노트_링크디자인_4안.png). 940×780 렌더 결과에서 네 노트·체인 버튼 테두리·정상/끊김 표시·하단 설명을 직접 확인했다. 기존 앱/브라우저 프로필을 사용하지 않았다.
- 수정 HTML: `output/design/sticky-link-options/기후노트_링크디자인_4안.html`. 별도 PNG도 함께 전달한다. 전체 체크 결과는 [summary.md](../../output/design/sticky-link-options/summary.md)를 따른다.
- 앱 검사는 런타임 변경이 없으므로 미실행. 작업 전후 기존 변경 목록을 대조했고 앱 소스·기존 사용자 변경을 유지했다.

## 미해결과 인계

- 사용자 피드백: B안의 라벨을 선호하되 본문 체인 아이콘 대신 C안처럼 파일 종류를 표시하는 조합을 요청했다. `B의 옅은 배경·둥근 테두리 + C의 PDF/HWP/XLSX 배지`로 해석해 정상/끊김 두 상태를 새 시안으로 만들었다. 선택 문구는 파일명으로 바꾸지 않으며 툴바 체인 버튼 테두리도 통일한다.
- 조합 시안은 `output/design/sticky-link-options/기후노트_링크디자인_BC조합.html`이며 JavaScript/iframe/외부 리소스 없이 두 노트를 직접 표시한다. 실행 ID `sticky-link-options/render-check/combined-bc`의 [result.json](../../output/design/sticky-link-options/render-check/combined-bc/result.json), [PNG](../../output/design/sticky-link-options/기후노트_링크디자인_BC조합.png). 940×510 실제 렌더에서 배지 6개·라벨·끊김 경고·테두리 버튼을 확인했다.
- 사용자가 B+C 조합 구현·버전 유지·AGENTS.md 갱신·커밋을 요청했다. 실제 코드 변경과 현재 검증은 [파일 라벨 구현 기록](2026-09-20-sticky-file-labels.md)을 따른다.
- 아이콘·배지·주의 표시는 본문 문자에 삽입하지 않는 원칙을 유지한다.
- 이번 시안은 앱 적용·커밋·재빌드 결과가 아니다.
