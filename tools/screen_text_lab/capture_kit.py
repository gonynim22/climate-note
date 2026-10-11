"""실제 캡처용 문구 준비/표시/등록. 화면 캡처·명령 예문 실행·OCR은 하지 않는다."""
from collections import Counter
from datetime import datetime
from pathlib import Path
import re
import uuid

from .corpus import CorpusError, contained_file, digest, read_json, valid_text

RECIPE = Path(__file__).parent / 'recipes/cli-capture.json'


def load_plan(directory):
    directory = Path(directory).resolve()
    checksums = read_json(contained_file(directory, 'checksums.json'))
    if not isinstance(checksums, dict):
        raise CorpusError('수집 묶음 해시 목록이 잘못되었습니다')
    for name, sha in checksums.items():
        if digest(contained_file(directory, name)) != sha:
            raise CorpusError(f'수집 묶음 파일이 변경되었습니다: {name}')
    if 'plan.json' not in checksums:
        raise CorpusError('수집 계획 해시가 없습니다')
    plan = read_json(directory / 'plan.json')
    if plan.get('version') != 1 or len(plan.get('cases', [])) != 30:
        raise CorpusError('지원하지 않는 수집 계획입니다')
    ids = set()
    for case in plan['cases']:
        text = case['text']
        if (not re.fullmatch(r'cli-[a-z]+-0[1-5]', case['id']) or case['id'] in ids
                or case['split'] not in {'dev', 'holdout'} or not valid_text(text)
                or not text or any(ord(ch) < 32 and ch != '\n' for ch in text)):
            raise CorpusError('수집 계획의 문구/ID/분할이 잘못되었습니다')
        ids.add(case['id'])
    return plan


def prepare(root=None):
    from tools.verify import ROOT, inside, write_json, atomic_text, utc_now
    recipe = read_json(RECIPE)
    cases = [{'id': f'cli-{category}-{index + 1:02d}', 'category': category,
              'split': 'holdout' if index == 4 else 'dev', 'text': text}
             for category, texts in recipe['categories'].items() for index, text in enumerate(texts)]
    if len(cases) != 30 or len({case['text'] for case in cases}) != 30:
        raise CorpusError('서로 다른 원문 30개가 필요합니다')
    boundary = Path(root).resolve() if root is not None else inside(ROOT / 'output/screen_text_lab/capture', ROOT)
    directory = boundary / (datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    (directory / 'samples').mkdir(parents=True, exist_ok=False)
    (directory / 'captures').mkdir()
    for case in cases:
        atomic_text(directory / 'samples' / (case['id'] + '.txt'), case['text'])
    write_json(directory / 'plan.json', {'version': 1, 'created_at': utc_now(),
        'recipe_sha256': digest(RECIPE), 'cases': cases,
        'planned': {'originals': len(cases), 'splits': dict(Counter(case['split'] for case in cases))},
        'note': '계획 수는 실제 캡처/검토/채점 완료 수가 아닙니다. 기존 모델 결과를 정답으로 쓰지 않습니다.'})
    write_json(directory / 'environment.json', {'common': {
        'source_app': '', 'app_version': '', 'windows_scale': '', 'app_zoom': '',
        'font_family': '', 'font_size': '', 'theme': ''}, 'per_file': {}})
    # 이 위치의 실행 파일만 사용자 더블클릭으로 새 콘솔을 열며 실행 정책을 바꾸지 않는다.
    command = ('@echo off\r\nsetlocal\r\npushd "%~dp0..\\..\\..\\.."\r\n'
        'if errorlevel 1 exit /b 1\r\n'
        '".venv\\Scripts\\python.exe" -X utf8 -m tools.screen_text_lab show-capture --kit "%~dp0."\r\n'
        'set "KIT_EXIT=%errorlevel%"\r\nif not "%KIT_EXIT%"=="0" pause\r\npopd\r\nexit /b %KIT_EXIT%\r\n')
    with open(directory / 'Start.cmd', 'x', encoding='ascii', newline='') as stream:
        stream.write(command)
    atomic_text(directory / 'README.txt', INSTRUCTIONS)
    write_json(directory / 'checksums.json', {path.relative_to(directory).as_posix(): digest(path)
        for path in sorted(directory.rglob('*')) if path.is_file() and path.name != 'environment.json'})
    load_plan(directory)
    return directory


def show(directory, case_id=None):
    plan = load_plan(directory)
    cases = plan['cases']
    if case_id is not None:
        case = next((case for case in cases if case['id'] == case_id), None)
        if case is None:
            raise CorpusError('수집 계획에 없는 문구 ID입니다')
        print(case['text'])
        return
    print('화면 글자 따기 — CLI 캡처 준비')
    print('시험 문구만 출력합니다. 화면의 명령 예문은 실행하지 않습니다.')
    print('본문만 PNG로 캡처하세요. Enter: 다음 / 번호: 이동 / q: 종료')
    index = 0
    while True:
        case = cases[index]
        print(f'\n[{index + 1}/30] 저장 이름: {case["id"]}.png\n--- 본문 시작 ---')
        print(case['text'])
        print('--- 본문 끝 ---')
        try:
            answer = input('\n캡처 후 Enter / 번호 / q: ').strip()
        except (EOFError, KeyboardInterrupt):
            return
        if answer.lower() == 'q':
            return
        if not answer:
            if index == len(cases) - 1:
                print('30개 문구 표시를 마쳤습니다. 실제 저장된 PNG와 정답은 별도로 확인합니다.')
                return
            index += 1
        elif answer.isascii() and answer.isdigit() and 1 <= int(answer) <= len(cases):
            index = int(answer) - 1
        else:
            print('1~30 또는 q를 입력하세요.')


def import_captures(directory, images=None, root=None):
    from .review_store import ReviewSession
    directory = Path(directory).resolve()
    plan = load_plan(directory)
    plan_hash = digest(directory / 'plan.json')
    environment_path = contained_file(directory, 'environment.json')
    environment_hash = digest(environment_path)
    environment = read_json(environment_path)
    if (not isinstance(environment, dict) or not isinstance(environment.get('common'), dict)
            or not isinstance(environment.get('per_file'), dict)):
        raise CorpusError('환경 정보에는 common/per_file 객체가 필요합니다')
    folder = Path(images or directory / 'captures').resolve()
    if not folder.is_dir():
        raise CorpusError('지정한 PNG 폴더가 없습니다')
    files = sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() == '.png')
    if not files:
        raise CorpusError('등록할 PNG가 없습니다. 실제 캡처 후 captures 폴더에 넣어 주세요.')
    by_id = {case['id']: case for case in plan['cases']}
    session = ReviewSession()
    seen = {}
    skipped = 0
    for source in files:
        path = contained_file(folder, source.name)
        match = re.fullmatch(r'(cli-[a-z]+-0[1-5])(?:--([a-zA-Z0-9_-]{1,32}))?', path.stem)
        if not match or match[1] not in by_id:
            raise CorpusError(f'문구와 연결할 수 없는 PNG 이름입니다: {path.name}')
        sample = by_id[match[1]]
        overrides = environment['per_file'].get(path.name, {})
        if not isinstance(overrides, dict):
            raise CorpusError('개별 PNG 환경 정보는 객체여야 합니다')
        metadata = environment['common'] | overrides
        if not all(isinstance(key, str) and isinstance(value, (str, int, float, bool))
                   for key, value in metadata.items()):
            raise CorpusError('환경 정보는 문자열/숫자/참거짓만 지원합니다')
        image_hash = digest(path)
        if image_hash in seen:
            if seen[image_hash] != sample['id']:
                raise CorpusError('동일 PNG가 서로 다른 문구에 연결되었습니다')
            skipped += 1
            continue
        seen[image_hash] = sample['id']
        tags = {key: value for key, value in metadata.items() if value != ''}
        tags.update(category='cli', scenario=sample['category'], capture_variant=match[2] or 'base',
                    material='controlled_text')
        session.add_pngs([path], group='cli-capture-v1-' + sample['id'], source_kind='user_supplied',
                         split=sample['split'], tags=tags)
        case = session.cases[-1]
        if case['image_sha256'] != image_hash:
            raise CorpusError('등록 중 PNG가 변경되었습니다')
        old_id = case['case_id']
        case['case_id'] = path.stem
        session.paths[path.stem] = session.paths.pop(old_id)
        case['expected']['text'] = sample['text']
        case['provenance'].update(registration='capture_kit', plan_sha256=plan_hash,
            environment_sha256=environment_hash, expected_origin='template_draft_not_verified')
    if digest(directory / 'plan.json') != plan_hash or digest(environment_path) != environment_hash:
        raise CorpusError('등록 중 수집 계획/환경 정보가 변경되었습니다')
    session.manifest['capture_intake'] = {'plan_sha256': plan_hash, 'environment': environment,
        'duplicates_skipped': skipped, 'registered': len(session.cases), 'reviewed_on_import': 0}
    return session.save(root)


INSTRUCTIONS = '''화면 글자 따기 — 실제 CLI 캡처 첫 수집 묶음

1. Start.cmd를 더블클릭하면 문구가 하나씩 표시됩니다.
   기존 Windows Terminal/PowerShell 환경을 쓰려면 프로젝트 루트에서 실행하세요:
   .\\.venv\\Scripts\\python.exe -X utf8 -m tools.screen_text_lab show-capture --kit "이 폴더의 전체 경로"
   화면에 표시된 명령어/경로는 모두 출력용 시험 문구입니다. 복사해서 실행할 필요가 없습니다.
2. 현재 사용하는 글꼴·글자 크기·테마·Windows 배율을 우선 그대로 사용하세요.
   환경 설정을 바꾸거나 화면을 자동 촬영하지 않습니다. 첫 6개만 먼저 저장해도 등록할 수 있습니다.
3. 문구 위·아래의 안내와 입력 프롬프트를 제외하고 본문 전체를 PNG로 캡처하세요.
   이미지의 크기 조정·재압축은 하지 마세요. 표시가 잘렸거나 자동 줄바꿈되면 정답 검토 때 확인합니다.
4. 표시된 파일명(예: cli-batchim-01.png)으로 이 폴더의 captures 안에 저장하세요.
   같은 문구를 다른 조건에서 찍으면 cli-batchim-01--dark.png처럼 접미사를 붙입니다.
   파일명 접미사에서 실제 테마/배율을 추정하지 않습니다. 같은 문구는 항상 같은 평가 분할입니다.
5. environment.json의 common에는 확인한 환경만 적습니다. 모르는 값은 빈 문자열을 유지합니다.
   per_file에는 {"파일명.png": {"theme": "dark"}}처럼 개별 환경을 지정할 수 있습니다.
   plan.json·checksums.json·samples의 원문은 고정이며 수정하지 않습니다.
6. 프로젝트 루트에서 등록합니다(원본 보존 사본, OCR 미실행):
   .\\.venv\\Scripts\\python.exe -X utf8 -m tools.screen_text_lab import-captures --kit "이 폴더의 전체 경로"
   다른 폴더에 저장했다면 --images "PNG 폴더"를 추가합니다. 하위 폴더는 읽지 않습니다.
7. 출력된 자료 경로로 기존 검토 창을 엽니다:
   .\\.venv\\Scripts\\python.exe -X utf8 -m tools.screen_text_lab review --corpus "출력된 자료 경로"
   원본 화면과 정답 초안을 대조하고 '정답 확인 완료'를 선택한 뒤 새 버전을 저장합니다.
   표 모양 사례도 기본은 문자 평가입니다. 표 구조를 평가하려면 검토 창에 표 정답을 따로 입력합니다.
8. 검토한 개발용 자료만 첫 기준 인식을 합니다:
   .\\.venv\\Scripts\\python.exe -X utf8 -m tools.screen_text_lab run --corpus "검토 후 새 자료 경로" --suite standard --split dev
   각 분류의 05 문구는 보류용입니다. 후보가 확정될 때까지 holdout 인식을 실행하지 않습니다.

문구 30개 = 6분류 × 5원문, 개발 24/보류 6. 실제 캡처 수는 저장한 PNG로 별도 집계합니다.
첫 수집 절차를 확인하는 규모이며 전체 업무 정확도를 대표하거나 충분한 최종 평가 규모라는 뜻이 아닙니다.
잘못 읽힌 화면뿐 아니라 정상적으로 읽힌 화면도 그대로 보존합니다.
평상시 코딩·테스트·빌드에는 이 수집/인식 작업이 자동으로 실행되지 않습니다.
'''
