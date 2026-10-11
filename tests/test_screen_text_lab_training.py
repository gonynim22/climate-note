"""Training tool contracts; no Paddle/model session/network access."""

import pytest

from tools.screen_text_lab.training.contracts import (
    class_mapping, class_tokens, nrtr_accepts, required_ctc_steps, shape_audit,
)


@pytest.mark.parametrize("head,offset", [("ctc", 1), ("nrtr", 4)])
def test_dictionary_extension_moves_space_without_relabeling_old_classes(head, offset):
    old, new = ["가", "나"], ["가", "나", "℃", "₩"]
    mapping = class_mapping(old, new, head)
    before, after = class_tokens(old, head), class_tokens(new, head)
    assert [after[index] for index in mapping] == before
    assert mapping[-1] == offset + 4
    assert mapping[:offset + 2] == list(range(offset + 2))


@pytest.mark.parametrize("bad", [["가", "가"], ["가", " "], ["blank"], [""], ["ab"], ["\n"]])
def test_dictionary_rejects_ambiguous_classes(bad):
    with pytest.raises(ValueError):
        class_tokens(bad)


def test_expansion_cannot_drop_old_character():
    with pytest.raises(ValueError):
        class_mapping(["가", "나"], ["가", "℃"])


def test_shape_audit_rejects_missing_extra_and_wrong_dimensions():
    result = shape_audit({"a": [2, 3], "b": [4]}, {"a": [3, 2], "c": [4]})
    assert result["ok"] is False
    assert result["missing"] == ["b"]
    assert result["extra"] == ["c"]
    assert result["shape_mismatches"] == [{"key": "a", "expected": [2, 3], "actual": [3, 2]}]
    assert shape_audit({"a": [2, 3]}, {"a": (2, 3)})["ok"]


def test_ctc_requires_blank_between_adjacent_repeats():
    assert required_ctc_steps("가가나나가") == 7
    assert required_ctc_steps("1111") == 7
    assert required_ctc_steps("가나다") == 3


@pytest.mark.parametrize("limit,accepted,rejected", [(25, 23, 24), (66, 64, 65)])
def test_nrtr_boundary_reserves_start_end_tokens(limit, accepted, rejected):
    assert nrtr_accepts("가" * accepted, limit)
    assert not nrtr_accepts("가" * rejected, limit)
    assert not nrtr_accepts("", limit)


@pytest.mark.parametrize("size", [(21, 9), (3, 2), (100, 48), (8, 11)])
def test_training_pixels_match_product_upscale_downscale_and_identity(size):
    import numpy as np
    from screen_text.engine import resize_bilinear as product_resize
    from tools.screen_text_lab.training.pixels import resize_bilinear

    image = np.random.default_rng(7).integers(0, 256, (11, 8, 3), dtype=np.uint8)
    assert np.array_equal(resize_bilinear(image, *size), product_resize(image, *size))


@pytest.mark.parametrize("mutation", ["case_split", "expected_text", "duplicate", "not_ready", "missing_label"])
def test_loader_rejects_split_leaks_and_silent_drops(tmp_path, mutation):
    import json
    from PIL import Image
    from tools.screen_text_lab.training.contracts import sha256
    from tools.screen_text_lab.training.train import load_samples

    image = tmp_path / "line.png"
    Image.new("RGB", (64, 48), "white").save(image)
    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("가\n", encoding="utf-8")
    labels = tmp_path / "labels.txt"
    labels.write_text("line.png\t가\n", encoding="utf-8")
    case = {"image": "line.png", "image_sha256": sha256(image), "case_id": "train-1",
            "split": "train", "text": "가", "expected": {"text": "가"},
            "checks": {"training_ready": True, "reasons": [], "ctc_observed_steps": 8,
                       "training_bucket_width": 64}}
    cases = [case]
    if mutation == "case_split":
        case["split"] = "selection"
    elif mutation == "expected_text":
        case["expected"]["text"] = "나"
    elif mutation == "duplicate":
        cases.append(case.copy())
    elif mutation == "not_ready":
        case["checks"].update(training_ready=False, reasons=["ink_clipped"])
    elif mutation == "missing_label":
        labels.write_text("", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"split": "train", "cases": cases}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_samples(manifest, labels, dictionary)


def test_source_provenance_detects_modified_executed_file(tmp_path):
    import json
    import zipfile
    from tools.screen_text_lab.training.contracts import sha256
    from tools.screen_text_lab.training.provenance import source_evidence

    source = tmp_path / "source" / "PaddleOCR-abc"
    source.mkdir(parents=True)
    (source / "model.py").write_bytes(b"x = 1\n")
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("PaddleOCR-abc/model.py", "x = 1\n")
    (tmp_path / "bootstrap.json").write_text(json.dumps({"revision": "abc", "assets": [
        {"url": "https://codeload.github.com/PaddlePaddle/PaddleOCR/zip/abc",
         "path": str(archive), "sha256": sha256(archive)}]}), encoding="utf-8")
    assert source_evidence(source)["verified_python_yaml_files"] == 1
    (source / "model.py").write_text("x = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="differs"):
        source_evidence(source)
