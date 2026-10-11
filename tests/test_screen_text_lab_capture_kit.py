"""실제 캡처 준비/등록 경계. 작은 합성 PNG만 사용, 화면·OCR·앱 실행 없음."""
from collections import Counter
import json
import shutil

import pytest

from tools.screen_text_lab import capture_kit
from tools.screen_text_lab.corpus import CorpusError, digest, load_corpus, read_json
from tools.screen_text_lab.metrics import score_case
from tools.screen_text_lab.review_store import ReviewSession


def png(path, color='white'):
    from PIL import Image
    Image.new('RGB', (90, 40), color).save(path)
    return path


@pytest.fixture
def kit(tmp_path):
    return capture_kit.prepare(tmp_path / 'capture')


def test_plan_has_fresh_original_groups_and_no_fake_captures(kit):
    plan = capture_kit.load_plan(kit)
    assert len({case['text'] for case in plan['cases']}) == 30
    assert Counter(case['split'] for case in plan['cases']) == {'dev': 24, 'holdout': 6}
    assert Counter(case['category'] for case in plan['cases']) == dict.fromkeys(
        ('batchim', 'logs', 'paths', 'numbers', 'identifiers', 'layout'), 5)
    assert all((case['split'] == 'holdout') == case['id'].endswith('-05') for case in plan['cases'])
    assert not list(kit.rglob('*.png')) and not (kit / 'manifest.json').exists()
    launcher = (kit / 'Start.cmd').read_text(encoding='ascii')
    assert '".venv\\Scripts\\python.exe"' in launcher and 'show-capture --kit "%~dp0."' in launcher
    assert 'ExecutionPolicy' not in launcher and 'powershell' not in launcher.lower()
    for case in plan['cases']:
        assert (kit / 'samples' / (case['id'] + '.txt')).read_text(encoding='utf-8') == case['text']
    originals = []
    def strings(value):
        if isinstance(value, str):
            originals.append(' '.join(value.split()))
        elif isinstance(value, list):
            for item in value:
                strings(item)
        elif isinstance(value, dict):
            for item in value.values():
                strings(item)
    for filename in ('bootstrap.json', 'conditions.json'):
        strings(read_json(capture_kit.RECIPE.parent / filename))
    assert not {' '.join(case['text'].split()) for case in plan['cases']} & set(originals)


def test_separate_preparations_preserve_previous_files(kit):
    before = {path.relative_to(kit): digest(path) for path in kit.rglob('*') if path.is_file()}
    other = capture_kit.prepare(kit.parent)
    assert other != kit
    assert before == {path.relative_to(kit): digest(path) for path in kit.rglob('*') if path.is_file()}


def test_display_prints_exact_text_without_running_example(kit, capsys):
    case = next(case for case in capture_kit.load_plan(kit)['cases'] if case['id'] == 'cli-paths-02')
    capture_kit.show(kit, case['id'])
    assert capsys.readouterr().out == case['text'] + '\n'
    with pytest.raises(CorpusError, match='ID'):
        capture_kit.show(kit, 'unknown')


def test_interactive_display_navigation_and_bad_input(kit, monkeypatch, capsys):
    answers = iter(['invalid', '30', ''])
    monkeypatch.setattr('builtins.input', lambda _: next(answers))
    capture_kit.show(kit)
    output = capsys.readouterr().out
    assert '[1/30]' in output and '[30/30]' in output and '표시를 마쳤습니다' in output
    assert '1~30 또는 q' in output


@pytest.mark.parametrize('name', ['plan.json', 'samples/cli-batchim-01.txt', 'Start.cmd'])
def test_edited_kit_is_rejected_before_display_or_intake(kit, name):
    with open(kit / name, 'ab') as stream:
        stream.write(b'changed')
    with pytest.raises(CorpusError, match='변경'):
        capture_kit.show(kit, 'cli-batchim-01')


def test_import_is_unreviewed_preserves_originals_and_group_splits(kit, tmp_path):
    first = png(kit / 'captures/cli-batchim-01.png')
    variant = png(kit / 'captures/cli-batchim-01--dark.png', 'black')
    held = png(kit / 'captures/cli-batchim-05.png', 'blue')
    hashes = {path: digest(path) for path in (first, variant, held)}
    environment = read_json(kit / 'environment.json')
    environment['common']['source_app'] = 'test metadata, not actual capture'
    environment['per_file'][variant.name] = {'theme': 'dark'}
    (kit / 'environment.json').write_text(json.dumps(environment), encoding='utf-8')
    directory = capture_kit.import_captures(kit, root=tmp_path / 'corpus')
    corpus = load_corpus(directory)
    assert hashes == {path: digest(path) for path in hashes}
    assert len(corpus.cases) == 3
    cases = {case['case_id']: case for case in corpus.cases}
    a, b, holdout = (cases[name] for name in ('cli-batchim-01', 'cli-batchim-01--dark', 'cli-batchim-05'))
    assert a['source_group_id'] == b['source_group_id'] != holdout['source_group_id']
    assert a['split'] == b['split'] == 'dev' and holdout['split'] == 'holdout'
    assert b['tags']['theme'] == 'dark' and 'theme' not in a['tags'] and 'windows_scale' not in a['tags']
    assert all(case['source_kind'] == 'user_supplied' and case['review_status'] == 'unreviewed' for case in corpus.cases)
    assert all(score_case(case, {'text': case['expected']['text']}) is None for case in corpus.cases)
    assert all(case['provenance']['plan_sha256'] == digest(kit / 'plan.json') for case in corpus.cases)
    assert len(corpus.select('standard', 'dev')) == 2
    # 기존 review의 확인/새 버전 저장을 거친 사례만 채점한다.
    review = ReviewSession(directory)
    review.update(a['case_id'], text=a['expected']['text'], table=None, group=a['source_group_id'],
                  split=a['split'], tags=a['tags'], reviewed=True)
    new = load_corpus(review.save(tmp_path / 'corpus'))
    reviewed = next(case for case in new.cases if case['case_id'] == a['case_id'])
    assert score_case(reviewed, {'text': reviewed['expected']['text'], 'unsure_count': 0})['exact']
    assert load_corpus(directory).cases == corpus.cases


def test_duplicates_same_group_skipped_but_different_group_refused(kit, tmp_path):
    path = png(kit / 'captures/cli-logs-01.png')
    shutil.copyfile(path, kit / 'captures/cli-logs-01--copy.png')
    corpus = load_corpus(capture_kit.import_captures(kit, root=tmp_path / 'ok'))
    assert len(corpus.cases) == 1 and corpus.manifest['capture_intake']['duplicates_skipped'] == 1
    shutil.copyfile(path, kit / 'captures/cli-logs-05.png')
    with pytest.raises(CorpusError, match='서로 다른 문구'):
        capture_kit.import_captures(kit, root=tmp_path / 'bad')
    assert not (tmp_path / 'bad').exists()


@pytest.mark.parametrize('problem', ['empty', 'unknown', 'bad_png', 'bad_environment', 'changed'])
def test_bad_intake_keeps_originals_and_creates_no_corpus(kit, tmp_path, monkeypatch, problem):
    path = kit / 'captures/cli-numbers-01.png'
    if problem != 'empty':
        png(path)
    if problem == 'unknown':
        png(kit / 'captures/mystery.png', 'black')
    elif problem == 'bad_png':
        (kit / 'captures/cli-numbers-02.png').write_bytes(b'not PNG')
    elif problem == 'bad_environment':
        (kit / 'environment.json').write_text('{"common":[],"per_file":{}}', encoding='utf-8')
    elif problem == 'changed':
        original = ReviewSession.add_pngs
        def change(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            png(path, 'blue')
            return result
        monkeypatch.setattr(ReviewSession, 'add_pngs', change)
    with pytest.raises((ValueError, OSError)):
        capture_kit.import_captures(kit, root=tmp_path / 'corpus')
    assert not list((tmp_path / 'corpus').glob('*'))
    assert (problem == 'empty') or path.is_file()


def test_explicit_folder_is_nonrecursive(kit, tmp_path):
    external = tmp_path / 'chosen'
    external.mkdir()
    png(external / 'cli-layout-01.png')
    (external / 'nested').mkdir()
    png(external / 'nested/cli-layout-05.png', 'black')
    corpus = load_corpus(capture_kit.import_captures(kit, external, tmp_path / 'corpus'))
    assert len(corpus.cases) == 1 and corpus.cases[0]['split'] == 'dev'


def test_commands_are_explicit_and_launcher_uses_project_python():
    from tools.screen_text_lab.__main__ import parser
    assert parser().parse_args(['capture-kit']).command == 'capture-kit'
    assert parser().parse_args(['show-capture', '--kit', 'kit']).case_id is None
    assert parser().parse_args(['import-captures', '--kit', 'kit']).images is None
