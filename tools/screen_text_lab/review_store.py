"""시험 자료 편집 세션. 명시적 저장마다 새 자료를 만들고 입력은 덮어쓰지 않는다."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import uuid

from .corpus import (CorpusError, digest, image_size, load_corpus, contained_file,
                     valid_text)


def parse_table(text):
    """TSV의 마지막 빈 셀/행도 정답의 일부로 보존한다."""
    rows = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    table = [row.split("\t") for row in rows]
    if len({len(row) for row in table}) != 1:
        raise CorpusError("표의 열 수가 다릅니다. 빈 셀도 Tab으로 구분해 주세요.")
    if not all(valid_text(cell) for row in table for cell in row):
        raise CorpusError("표 정답에 지원하지 않는 문자나 너무 긴 셀이 있습니다.")
    return table


def default_root():
    return Path(__file__).resolve().parents[2] / "output/screen_text_lab/corpus"


class ReviewSession:
    def __init__(self, directory=None):
        self.manifest = {"schema_version": 1, "dataset_id": "unsaved", "cases": []}
        self.paths = {}
        self.directory = None
        self.manifest_sha256 = None
        self.dirty = False
        if directory is not None:
            corpus = load_corpus(directory)
            self.manifest = deepcopy(corpus.manifest)
            self.directory = corpus.directory
            self.manifest_sha256 = corpus.manifest_sha256
            self.paths = {case["case_id"]: contained_file(corpus.directory, case["image"])
                          for case in corpus.cases}

    @property
    def cases(self):
        return self.manifest["cases"]

    def add_pngs(self, paths, *, group, source_kind="user_supplied", split="dev", tags=None):
        if not isinstance(group, str) or not group.strip():
            raise CorpusError("같은 문서/화면을 묶을 원본 그룹 이름을 입력해 주세요.")
        if source_kind not in {"program_capture", "user_supplied", "synthetic"}:
            raise CorpusError("출처 종류가 잘못되었습니다.")
        if split not in {"dev", "holdout"}:
            raise CorpusError("분할이 잘못되었습니다.")
        if any(case["source_group_id"] == group.strip() and case["split"] != split for case in self.cases):
            raise CorpusError("같은 원본 그룹은 같은 분할에 등록해야 합니다.")
        pending, locations = [], {}
        hashes = {case["image_sha256"] for case in self.cases}
        skipped = 0
        for source in paths:
            path = Path(source).resolve()
            size = image_size(path)
            image_hash = digest(path)
            if image_hash in hashes:
                skipped += 1
                continue
            case_id = "capture-" + uuid.uuid4().hex
            pending.append({"case_id": case_id, "source_group_id": group.strip(),
                            "parent_id": None, "split": split, "source_kind": source_kind,
                            "review_status": "unreviewed", "image": f"images/{case_id}.png",
                            "image_sha256": image_hash, "image_size": size,
                            "expected": {"text": ""}, "tags": deepcopy(tags or {}),
                            "provenance": {"original_name": path.name, "registration": "manual_png"}})
            locations[case_id] = path
            hashes.add(image_hash)
        if len(self.cases) + len(pending) > 20000:
            raise CorpusError("한 자료 묶음에는 최대 20,000개 사례를 등록할 수 있습니다.")
        self.cases.extend(pending)
        self.paths.update(locations)
        self.dirty = self.dirty or bool(pending)
        return len(pending), skipped

    def update(self, case_id, *, text, table, group, split, tags, reviewed, blank_confirmed=False):
        if not valid_text(text):
            raise CorpusError("문자 정답은 8,192자 이내여야 하며 NUL 문자는 쓸 수 없습니다.")
        if not group.strip() or split not in {"dev", "holdout"}:
            raise CorpusError("원본 그룹과 분할을 확인해 주세요.")
        if reviewed and not text.strip() and not blank_confirmed:
            raise CorpusError("빈 정답은 '글자 없는 화면으로 확인'을 선택해야 검토 완료할 수 있습니다.")
        if table is not None and (not table or not all(isinstance(row, list) and row for row in table)
                                  or len({len(row) for row in table}) != 1
                                  or not all(valid_text(cell) for row in table for cell in row)):
            raise CorpusError("표 정답의 행·열과 문자를 확인해 주세요.")
        case = next(case for case in self.cases if case["case_id"] == case_id)
        updated = deepcopy(case)
        expected = deepcopy(case["expected"])
        expected["text"] = text
        if table is None:
            expected.pop("table", None)
        else:
            expected["table"] = deepcopy(table)
        # 생성 정답을 그대로 열어 저장한 경우 generated 상태를 유지한다.
        status = "reviewed" if reviewed else "unreviewed"
        if case["review_status"] == "generated" and expected == case["expected"] and reviewed:
            status = "generated"
        updated.update(expected=expected, source_group_id=group.strip(), split=split,
                       tags=deepcopy(tags), review_status=status)
        if updated != case:
            updated["review"] = {"updated_at": datetime.now(timezone.utc).isoformat(),
                                 "blank_confirmed": bool(blank_confirmed and not text.strip())}
            case.clear()
            case.update(updated)
            self.dirty = True

    def save(self, root=None):
        if not self.cases:
            raise CorpusError("저장할 PNG를 먼저 추가해 주세요.")
        if self.directory and digest(self.directory / "manifest.json") != self.manifest_sha256:
            raise CorpusError("열어 둔 원본 자료가 밖에서 변경되었습니다. 새로 열어 확인해 주세요.")
        boundary = Path(root or default_root()).resolve()
        boundary.mkdir(parents=True, exist_ok=True)
        version = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        staging = boundary / (".pending-" + version)
        target = boundary / version
        staging.mkdir(exist_ok=False)
        manifest = deepcopy(self.manifest)
        manifest.update(dataset_id=version, saved_at=datetime.now(timezone.utc).isoformat())
        if self.directory:
            manifest["parent_dataset"] = {"dataset_id": self.manifest["dataset_id"],
                                          "manifest_sha256": self.manifest_sha256}
        try:
            (staging / "images").mkdir()
            for case in manifest["cases"]:
                source = self.paths[case["case_id"]]
                case["image"] = "images/" + case["case_id"] + ".png"
                destination = staging / case["image"]
                shutil.copyfile(source, destination)
                if digest(destination) != case["image_sha256"]:
                    raise CorpusError("등록한 PNG가 변경되었습니다. 원본을 확인하고 다시 등록해 주세요.")
            with open(staging / "manifest.json", "x", encoding="utf-8", newline="\n") as stream:
                json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
            load_corpus(staging)
            # 원래 자료를 덮어쓰지 않는다. 완전히 검증된 폴더만 새 버전으로 공개한다.
            staging.rename(target)
        except Exception:
            # 이 호출이 만든 임시 폴더만 정리한다. 원본/기존 결과/다른 실행은 대상이 아니다.
            resolved = staging.resolve()
            if resolved.parent == boundary and resolved.name == ".pending-" + version and resolved.is_dir():
                shutil.rmtree(resolved)
            raise
        self.manifest = manifest
        self.directory = target
        self.manifest_sha256 = digest(target / "manifest.json")
        self.paths = {case["case_id"]: target / case["image"] for case in self.cases}
        self.dirty = False
        return target
