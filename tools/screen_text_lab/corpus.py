"""개발용 이미지/정답 manifest 검증. 제품 모듈이나 OCR을 import하지 않는다."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

SCHEMA_VERSION = 1
MAX_TEXT = 8192
ID_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}\Z")


class CorpusError(ValueError):
    """실행 전에 수정해야 하는 시험 자료 오류."""


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def json_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def contained_file(directory, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise CorpusError("파일 경로는 자료 폴더 안의 상대 경로여야 합니다")
    boundary = Path(directory).resolve()
    path = (boundary / name).resolve()
    if not path.is_relative_to(boundary) or path == boundary or not path.is_file():
        raise CorpusError(f"자료 파일이 없거나 경로가 범위를 벗어났습니다: {name}")
    return path


def valid_text(value):
    return (isinstance(value, str) and len(value) <= MAX_TEXT
            and not any(0xD800 <= ord(ch) <= 0xDFFF or ord(ch) == 0 for ch in value))


def image_size(path):
    from PIL import Image
    with Image.open(path) as image:
        if image.format != "PNG" or image.width * image.height > 32_000_000:
            raise CorpusError("시험 이미지는 3,200만 픽셀 이하의 PNG여야 합니다")
        size = list(image.size)
        image.verify()
    return size


@dataclass(frozen=True)
class Corpus:
    directory: Path
    manifest: dict
    manifest_sha256: str

    @property
    def cases(self):
        return self.manifest["cases"]

    def select(self, suite, split):
        cases = [case for case in self.cases if case["split"] == split]
        if suite == "bootstrap":
            cases = [case for case in cases if case.get("parent_id") is None][:100]
        elif suite != "standard":
            raise CorpusError("첫 버전은 bootstrap/standard만 지원합니다")
        if not cases:
            raise CorpusError("선택한 분할에 실행할 사례가 없습니다")
        return cases

    def fingerprint(self):
        return {"manifest": digest(self.directory / "manifest.json"),
                "images": {case["case_id"]: digest(contained_file(self.directory, case["image"]))
                           for case in self.cases}}


def load_corpus(directory):
    directory = Path(directory).resolve()
    manifest_path = directory / "manifest.json"
    try:
        manifest = read_json(manifest_path)
        if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
            raise CorpusError("지원하지 않는 자료 스키마입니다")
        if not isinstance(manifest.get("dataset_id"), str) or not manifest["dataset_id"]:
            raise CorpusError("dataset_id가 필요합니다")
        cases = manifest.get("cases")
        if not isinstance(cases, list) or not cases or len(cases) > 20000:
            raise CorpusError("자료에는 1~20,000개 사례가 필요합니다")
        ids, groups, image_splits, content_splits = {}, {}, {}, {}
        for case in cases:
            if not isinstance(case, dict):
                raise CorpusError("사례는 JSON 객체여야 합니다")
            case_id = case.get("case_id")
            if not isinstance(case_id, str) or not ID_PATTERN.fullmatch(case_id) or case_id in ids:
                raise CorpusError("case_id가 잘못되었거나 중복됩니다")
            ids[case_id] = case
            group, split = case.get("source_group_id"), case.get("split")
            if not isinstance(group, str) or not group or split not in {"dev", "holdout"}:
                raise CorpusError(f"{case_id}: 원본 그룹과 분할이 필요합니다")
            if groups.setdefault(group, split) != split:
                raise CorpusError(f"{case_id}: 같은 원본 그룹이 분할 사이에 섞였습니다")
            if case.get("source_kind") not in {"synthetic", "program_capture", "user_supplied"}:
                raise CorpusError(f"{case_id}: 출처 종류가 필요합니다")
            if case.get("review_status") not in {"reviewed", "generated", "unreviewed"}:
                raise CorpusError(f"{case_id}: 정답 검토 상태가 필요합니다")
            if case["review_status"] == "generated" and case["source_kind"] != "synthetic":
                raise CorpusError(f"{case_id}: 실제 캡처에는 생성 정답 상태를 사용할 수 없습니다")
            expected = case.get("expected")
            if not isinstance(expected, dict) or not valid_text(expected.get("text")):
                raise CorpusError(f"{case_id}: 유효한 원문 정답이 필요합니다")
            table = expected.get("table")
            if table is not None and (not isinstance(table, list) or not table
                    or not all(isinstance(row, list) and row for row in table)
                    or len({len(row) for row in table}) != 1
                    or not all(valid_text(cell) for row in table for cell in row)):
                raise CorpusError(f"{case_id}: 표 정답은 같은 열 수의 문자열 배열이어야 합니다")
            tags = case.get("tags")
            if not isinstance(tags, dict) or not all(isinstance(k, str) and isinstance(v, (str, int, float, bool))
                                                     for k, v in tags.items()):
                raise CorpusError(f"{case_id}: 조건 태그가 잘못되었습니다")
            if not isinstance(case.get("regions", []), list):
                raise CorpusError(f"{case_id}: 영역 주석은 목록이어야 합니다")
            path = contained_file(directory, case.get("image"))
            if digest(path) != case.get("image_sha256"):
                raise CorpusError(f"{case_id}: 이미지 해시가 다릅니다")
            size = image_size(path)
            if size != case.get("image_size"):
                raise CorpusError(f"{case_id}: 이미지 크기가 다릅니다")
            if image_splits.setdefault(case["image_sha256"], split) != split:
                raise CorpusError(f"{case_id}: 동일 이미지가 분할 사이에 섞였습니다")
            text_key = " ".join(expected["text"].split())
            if text_key and content_splits.setdefault(text_key, split) != split:
                raise CorpusError(f"{case_id}: 동일 내용이 분할 사이에 섞였습니다")
            for region in case.get("regions", []):
                box = region.get("box") if isinstance(region, dict) else None
                if isinstance(region, dict) and "text" in region and not valid_text(region["text"]):
                    raise CorpusError(f"{case_id}: 영역 정답은 유효한 문자열이어야 합니다")
                if (not isinstance(box, list) or len(box) != 4 or
                        not all(type(n) is int for n in box) or
                        not (0 <= box[0] < box[2] <= size[0] and 0 <= box[1] < box[3] <= size[1])):
                    raise CorpusError(f"{case_id}: 원본 좌표 범위를 벗어났습니다")
        for case in cases:
            parent_id = case.get("parent_id")
            if parent_id is not None:
                parent = ids.get(parent_id)
                if (not parent or parent.get("parent_id") is not None or parent is case
                        or parent["split"] != case["split"]
                        or parent["source_group_id"] != case["source_group_id"]):
                    raise CorpusError(f"{case['case_id']}: 변형은 같은 그룹/분할의 원본에 연결해야 합니다")
        return Corpus(directory, manifest, digest(manifest_path))
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise CorpusError(f"자료를 읽지 못했습니다: {type(error).__name__}") from error
