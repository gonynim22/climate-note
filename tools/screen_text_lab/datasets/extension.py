"""제품 사전/자료를 유지하며 업무 기호 확장 B의 입력 자료만 준비한다."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import uuid

from .audit import label_check, sha256, validate_manifest, write_json
from .build import CONDITIONS, render_line
from ..training.contracts import class_mapping, class_tokens

# 2026-10-11 실행 계획의 20자 + 새 pilot에서 관측한 ㎠. 순서는 새 ID의 계약이다.
APPROVED_ADDITIONS = list("㈜℃₩㎎㎏㎍㎥㎡㎜㎝㎞㏊㏈ℓ㎖㏙㎐㎾㎸㎃㎠")


def expansion_mapping(old_characters, additions, observed_oov=()):
    """기존 문자/특수토큰 ID를 보존하고 암묵 공백만 이동하는 표를 만든다."""
    if len(set(additions)) != len(additions) or any(len(char) != 1 or char.isspace() for char in additions):
        raise ValueError("확장 목록에는 중복/공백 없는 한 문자씩 필요합니다")
    if set(old_characters) & set(additions):
        raise ValueError("기존 사전 문자를 중복 추가할 수 없습니다")
    if not set(observed_oov).issubset(additions):
        raise ValueError("새 OOV가 승인 확장 목록 밖에 있습니다")
    new_characters = old_characters + additions
    heads = {}
    for head in ("ctc", "nrtr"):
        old_tokens, new_tokens = class_tokens(old_characters, head), class_tokens(new_characters, head)
        mapping = class_mapping(old_characters, new_characters, head)
        if len(set(mapping)) != len(mapping) or any(new_tokens[new_id] != old_tokens[old_id] for old_id, new_id in enumerate(mapping)):
            raise ValueError("기존 문자 ID 왕복 검사 실패")
        if mapping[-1] != len(new_tokens) - 1 or new_tokens[mapping[-1]] != " ":
            raise ValueError("마지막 공백 이동 검사 실패")
        if any(old_id != new_id for old_id, new_id in enumerate(mapping[:-1])):
            raise ValueError("공백 이외 기존 ID가 이동했습니다")
        old_lookup = {token: index for index, token in enumerate(old_tokens)}
        heads[head] = {"old_class_count": len(old_tokens), "new_class_count": len(new_tokens),
                       "old_space_id": len(old_tokens) - 1, "new_space_id": len(new_tokens) - 1,
                       "old_to_new": mapping,
                       "tokens": [{"token": token, "old_id": old_lookup.get(token), "new_id": index,
                                   "new_class": token not in old_lookup,
                                   "code_point": f"U+{ord(token):04X}" if len(token) == 1 else None}
                                  for index, token in enumerate(new_tokens)]}
    return new_characters, heads


def oov_evidence(manifests, alphabet):
    sources = {}
    images = Counter()
    for manifest in manifests:
        for case in manifest["cases"]:
            sources[(case["split"], case["source_group_id"])] = case
            images.update(set(case["text"]) - alphabet)
    evidence = {}
    for char in sorted({char for case in sources.values() for char in case["text"] if char not in alphabet}):
        rows = [case for case in sources.values() if char in case["text"]]
        evidence[char] = {"code_point": f"U+{ord(char):04X}", "source_groups": len(rows),
                          "source_occurrences": sum(case["text"].count(char) for case in rows),
                          "images": images[char],
                          "sources": [{"split": case["split"], "source_group_id": case["source_group_id"],
                                       "document_id": case["document_id"], "text": case["text"]} for case in rows]}
    return evidence


def glyph_evidence(char, condition):
    """실제 Qt fallback run의 family/style/cmap/name 해시와 glyph ID를 기록한다."""
    from PySide6.QtGui import QFont, QFontInfo, QRawFont, QTextLayout
    font = QFont(condition["font"])
    font.setPixelSize(condition["px"])
    layout = QTextLayout(char, font)
    layout.beginLayout()
    line = layout.createLine()
    line.setLineWidth(200)
    layout.endLayout()
    runs = []
    for run in layout.glyphRuns():
        raw = run.rawFont()
        tables = {}
        for name in ("name", "cmap", "head"):
            data = bytes(raw.fontTable(name))
            tables[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        runs.append({"family": raw.familyName(), "style": raw.styleName(),
                     "glyph_ids": list(run.glyphIndexes()), "font_tables": tables})
    missing = any(glyph == 0 for run in runs for glyph in run["glyph_ids"])
    return {"character": char, "code_point": f"U+{ord(char):04X}", "condition": condition["id"],
            "requested_font": condition["font"], "resolved_primary_font": QFontInfo(font).family(),
            "font_px": condition["px"], "primary_supports_character": QRawFont.fromFont(font).supportsCharacter(ord(char)),
            "runs": runs, "missing_glyph": missing, "nonempty_glyph_run": bool(runs),
            "source": "현재 PC에 설치된 글꼴을 Qt QTextLayout으로 shaping. 실제 run의 name/cmap/head 표 SHA-256.",
            "human_reviewed": False}


def prepare_extension(dataset_root, dictionary_path, run_root=None):
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    dataset_root = Path(dataset_root).resolve()
    dictionary_path = Path(dictionary_path).resolve()
    with open(dictionary_path, encoding="utf-8") as stream:
        old_characters = stream.read().splitlines()
    manifests = [validate_manifest(dataset_root / split) for split in ("train", "selection")]
    if any(manifest["split"] not in {"train", "selection"} for manifest in manifests):
        raise ValueError("B 준비는 train/selection만 읽습니다")
    original_hashes = {"dictionary": sha256(dictionary_path),
                       **{split: sha256(dataset_root / split / "manifest.json") for split in ("train", "selection")}}
    module_hashes = {path.name: sha256(path) for path in Path(__file__).parent.glob("*.py")}
    contract_path = Path(__file__).resolve().parent.parent / "training/contracts.py"
    contract_hash = sha256(contract_path)
    evidence = oov_evidence(manifests, set(old_characters) | {" "})
    new_characters, mapping = expansion_mapping(old_characters, APPROVED_ADDITIONS, evidence)
    suffix = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    directory = dataset_root / ("extension-b-" + suffix)
    (directory / "glyphs").mkdir(parents=True, exist_ok=False)
    with open(directory / "dict-b.txt", "x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(new_characters) + "\n")
    write_json(directory / "class-mapping.json", mapping)
    write_json(directory / "oov-evidence.json", evidence)
    additions = [{"character": char, "code_point": f"U+{ord(char):04X}",
                  "reason": "pilot 원문에서 추가 관측한 제곱센티미터" if char == "㎠" else "2026-10-11 승인된 업무 기호 확장 계획",
                  "source_groups_in_pilot": evidence.get(char, {}).get("source_groups", 0),
                  "training_evidence": "present_in_pilot" if any(row["split"] == "train" for row in evidence.get(char, {}).get("sources", [])) else "absent_from_train_pilot"}
                 for char in APPROVED_ADDITIONS]
    write_json(directory / "additions.json", additions)
    glyph_rows, atlas_rows = [], []
    for char in APPROVED_ADDITIONS:
        for condition in CONDITIONS:
            glyph = glyph_evidence(char, condition)
            _, crop, _, render_check = render_line(char, condition)
            file_name = f"u{ord(char):04x}--{condition['id']}.png"
            path = directory / "glyphs" / file_name
            if not crop.save(str(path), "PNG"):
                raise OSError("기호 glyph 진단 PNG 저장 실패")
            glyph.update(image="glyphs/" + file_name, image_sha256=sha256(path),
                         ink_clipped=render_check["ink_clipped"], diagnostic_only=True)
            glyph_rows.append(glyph)
            atlas_rows.append("<tr><td>" + html.escape(char) + "</td><td>" + glyph["code_point"] + "</td><td>"
                              + condition["id"] + "</td><td><img src=\"" + glyph["image"] + "\"></td><td>"
                              + html.escape(", ".join(run["family"] for run in glyph["runs"])) + "</td></tr>")
    write_json(directory / "glyph-evidence.json", glyph_rows)
    with open(directory / "glyph-atlas.html", "x", encoding="utf-8", newline="\n") as stream:
        stream.write("<!doctype html><html lang=\"ko\"><meta charset=\"utf-8\"><title>B 기호 글꼴 진단</title>"
                     "<style>body{font:16px 'Malgun Gothic';margin:24px}td{border:1px solid #bbb;padding:8px}table{border-collapse:collapse}</style>"
                     "<h1>B 기호 글꼴 진단</h1><p>단일 문자 그림은 학습/평가 corpus에 포함하지 않습니다. "
                     "원본 code point를 치환하지 않았으며 글리프가 그려졌다는 것이 사람의 독립 검토를 뜻하지 않습니다.</p><table>"
                     + "".join(atlas_rows) + "</table></html>")
    b_labels = {}
    for manifest in manifests:
        split = manifest["split"]
        rows = []
        for case in manifest["cases"]:
            check = label_check(case, set(new_characters) | {" "})
            rows.append({"case_id": case["case_id"], **check})
        eligible = {row["case_id"] for row in rows if row["eligible_without_ctc"]}
        with open(directory / f"labels-b-{split}.txt", "x", encoding="utf-8", newline="\n") as stream:
            for case in manifest["cases"]:
                if case["case_id"] in eligible:
                    # data_dir는 원래 해당 split 경로. PNG나 manifest를 복사/변경하지 않는다.
                    stream.write(case["image"] + "\t" + case["text"] + "\n")
        b_labels[split] = {"data_dir": str(dataset_root / split), "labels": f"labels-b-{split}.txt",
                           "eligible_by_dictionary_and_render": len(eligible), "total": len(rows),
                           "excluded": [row for row in rows if row["case_id"] not in eligible],
                           "new_b_model_ctc_and_loader": "not_run"}
    write_json(directory / "labels-report.json", b_labels)
    # 기존 정본의 모든 PNG도 다시 검사한다. 이 작업에서 원본/manifest는 쓰지 않는다.
    for split in ("train", "selection"):
        validate_manifest(dataset_root / split)
    preserved = original_hashes == {"dictionary": sha256(dictionary_path),
                                    **{split: sha256(dataset_root / split / "manifest.json") for split in ("train", "selection")}}
    module_preserved = module_hashes == {path.name: sha256(path) for path in Path(__file__).parent.glob("*.py")}
    contract_preserved = contract_hash == sha256(contract_path)
    glyph_failures = [row for row in glyph_rows if row["missing_glyph"] or row["ink_clipped"] or not row["nonempty_glyph_run"]]
    result = {"status": "passed_inputs_ready_model_pending" if preserved and module_preserved and contract_preserved and not glyph_failures else "failed",
              "directory": str(directory), "created_at": datetime.now(timezone.utc).isoformat(),
              "source_hashes": module_hashes, "training_contracts_sha256": contract_hash,
              "original_input_hashes": original_hashes, "original_inputs_preserved": preserved,
              "source_preserved": module_preserved and contract_preserved,
              "old_dictionary_count": len(old_characters), "new_dictionary_count": len(new_characters),
              "dict_b_sha256": sha256(directory / "dict-b.txt"), "additions": APPROVED_ADDITIONS,
              "observed_oov": sorted(evidence), "observed_oov_count": len(evidence),
              "unseen_in_train_pilot": [row["character"] for row in additions if row["training_evidence"] == "absent_from_train_pilot"],
              "glyph_diagnostics": len(glyph_rows), "glyph_failures": glyph_failures,
              "mapping_roundtrip": "passed", "mapping_space_shift": {head: {key: mapping[head][key] for key in ("old_space_id", "new_space_id")}
                                                                        for head in ("ctc", "nrtr")},
              "labels": b_labels, "model_weight_mapping": "not_run", "actual_b_logits": "not_run",
              "final_or_real_capture_access": "none", "human_review": "not_run"}
    write_json(directory / "result.json", result)
    summary = ["# B 업무 기호 사전 준비", "", f"상태: {result['status']}", f"출력: `{directory}`", "",
               f"사전 {len(old_characters)} → {len(new_characters)}자, 추가 {len(APPROVED_ADDITIONS)}자. 제품 사전/기존 manifest/PNG 유지.",
               f"pilot에서 실제 관측한 OOV {len(evidence)}자: {''.join(sorted(evidence))}",
               f"승인 확장 중 train pilot에 아직 없는 문자: {''.join(result['unseen_in_train_pilot'])}",
               f"기호×조건 {len(glyph_rows)}개에서 글꼴 glyph run 출처/표 해시·PNG를 기록. 실패 {len(glyph_failures)}개.",
               "", f"CTC 공백 {mapping['ctc']['old_space_id']} → {mapping['ctc']['new_space_id']}; "
               f"NRTR 공백 {mapping['nrtr']['old_space_id']} → {mapping['nrtr']['new_space_id']}. 다른 기존 token ID 보존·왕복 통과.",
               "", f"B 라벨은 train {b_labels['train']['eligible_by_dictionary_and_render']}/selection {b_labels['selection']['eligible_by_dictionary_and_render']}개의 원문을 그대로 유지한다. "
               "입력 준비 결과이며 가중치 이동·새 softmax·학습·독립 평가 완료가 아니다.",
               "관측되지 않은 기호에는 새 학습 문구가 필요하다. 단일 기호 진단 이미지는 학습 corpus에 넣지 않는다.",
               "사람 검토·실제 앱/Windows DPI·final은 미실행이다."]
    with open(directory / "summary.md", "x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(summary) + "\n")
    if run_root is not None:
        run_dir = Path(run_root) / ("dataset-extension-" + suffix)
        run_dir.mkdir(parents=True, exist_ok=False)
        write_json(run_dir / "result.json", result)
        with open(run_dir / "summary.md", "x", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(summary) + "\n")
    return directory, result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="B 기호 사전과 원문/ID/글꼴 진단을 별도 출력으로 준비")
    parser.add_argument("dataset_root", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    directory, result = prepare_extension(args.dataset_root, root / "screen_text/models/dict.txt", root / "output/harness")
    print(directory)
    print(result["status"])
    return 0 if result["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
