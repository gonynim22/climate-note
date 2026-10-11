"""Manual inference bridge boundaries, with small arrays and fake sessions only."""
from types import SimpleNamespace

import numpy as np
import pytest

from tools.screen_text_lab.crop_evaluation import (
    ProbabilitySession, candidate_bundle, candidate_charset, crop_prediction, validate_selection, validate_session,
    validate_worker_records,
)
from tools.screen_text_lab.corpus import digest, json_hash
from tools.verify import write_json


def test_candidate_requires_matching_hashes_and_contained_paths(tmp_path, monkeypatch):
    from tools.screen_text_lab.training import bundle_candidate
    monkeypatch.setattr(bundle_candidate, "verify_bundle_provenance", lambda *_: {"files": {}})
    model, dictionary = tmp_path / "model.onnx", tmp_path / "dict.txt"
    model.write_bytes(b"fake")
    dictionary.write_text("가\n", encoding="utf-8")
    value = {"schema_version": 1, "role": "F", "id": "test", "provenance": {"run": "research"},
             "model": model.name, "model_sha256": digest(model),
             "dictionary": dictionary.name, "dictionary_sha256": digest(dictionary)}
    manifest = tmp_path / "bundle.json"
    write_json(manifest, value)
    _, files = candidate_bundle(manifest, tmp_path)
    assert files["model"] == model
    model.write_bytes(b"changed")
    with pytest.raises(ValueError, match="해시"):
        candidate_bundle(manifest, tmp_path)
    value["model"] = "../outside.onnx"
    write_json(manifest, value)
    with pytest.raises(ValueError):
        candidate_bundle(manifest, tmp_path)


def test_candidate_requires_real_proof_not_a_source_declaration(tmp_path):
    model, dictionary = tmp_path / "model.onnx", tmp_path / "dict.txt"
    model.write_bytes(b"fake")
    dictionary.write_text("가\n", encoding="utf-8")
    manifest = tmp_path / "bundle.json"
    write_json(manifest, {"schema_version": 1, "role": "F", "id": "unproven", "provenance": {"run": "research"},
                         "model": model.name, "model_sha256": digest(model),
                         "dictionary": dictionary.name, "dictionary_sha256": digest(dictionary)})
    with pytest.raises(ValueError, match="report"):
        candidate_bundle(manifest, tmp_path)


@pytest.mark.parametrize("text", ["가\n가\n", "가\n \n", "가\n\n", "ab\n"])
def test_ambiguous_dictionary_rejected(tmp_path, text):
    path = tmp_path / "dict.txt"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        candidate_charset(path)


def test_candidate_unicode_preserved_and_space_appended(tmp_path):
    path = tmp_path / "dict.txt"
    path.write_text("가\n㎎\n℃\n", encoding="utf-8")
    assert candidate_charset(path) == ["가", "㎎", "℃", " "]


@pytest.mark.parametrize("split", ["train", "final", "holdout", "dev"])
def test_only_selection_can_be_inferred(split):
    with pytest.raises(ValueError):
        validate_selection([{"case_id": "one", "split": split, "evaluation_scope": "line_crop", "review_status": "generated"}])


def test_case_ids_cannot_escape_output():
    with pytest.raises(ValueError):
        validate_selection([{"case_id": "../one", "split": "selection", "evaluation_scope": "line_crop", "review_status": "generated"}])


def test_final_folder_rejected_before_reading_manifest(tmp_path, monkeypatch):
    from tools import verify
    from tools.screen_text_lab import crop_evaluation
    monkeypatch.setattr(verify, "ROOT", tmp_path)
    monkeypatch.setattr(crop_evaluation, "read_json", lambda _: pytest.fail("final manifest opened"))
    with pytest.raises(ValueError, match="selection"):
        crop_evaluation.run(tmp_path / "output/screen_text_lab/training_data/new/final")


def test_dynamic_shape_and_dictionary_output_must_match():
    node = SimpleNamespace(name="x", type="tensor(float)", shape=["N", 3, 48, "W"])
    output = SimpleNamespace(shape=["N", "T", 3], type="tensor(float)")
    session = SimpleNamespace(get_inputs=lambda: [node], get_outputs=lambda: [output])
    validate_session(session, ["가", " "])
    output.shape[-1] = 4
    with pytest.raises(ValueError):
        validate_session(session, ["가", " "])
    output.shape[-1], node.shape[-1] = 3, 320
    with pytest.raises(ValueError):
        validate_session(session, ["가", " "])


@pytest.mark.parametrize("values", [[[float("nan"), 1]], [[-1, 2]], [[.1, .1]]])
def test_logits_and_nonfinite_outputs_cannot_be_used_as_confidence(values):
    session = SimpleNamespace(run=lambda *_: [np.asarray([values], dtype=np.float32)])
    with pytest.raises(ValueError, match="확률분포"):
        ProbabilitySession(session).run(None, {})


def test_crop_uses_product_bgr_tensor_ctc_and_existing_warning():
    from screen_text.engine import OcrEngine
    received = []

    class Session:
        def run(self, _, inputs):
            received.append(inputs["x"].copy())
            # blank, repeated 가, blank, space, 나: CTC must retain the space.
            values = np.zeros((1, 6, 4), dtype=np.float32)
            for step, index in enumerate([0, 1, 1, 0, 3, 2]):
                values[0, step, index] = .7
            return [values]

    engine = object.__new__(OcrEngine)
    engine._rec, engine._charset = Session(), ["가", "나", " "]
    rgb = np.zeros((48, 16, 3), dtype=np.uint8)
    rgb[:, :, 0] = 255
    result = crop_prediction(engine, rgb)
    assert result["text"] == "가 나"
    assert result["unsure_count"] == 1
    assert received[0].shape == (1, 3, 48, 16)
    assert np.all(received[0][0, 0] == -1) and np.all(received[0][0, 2] == 1)


def test_returned_worker_records_cannot_replace_truth_or_group_or_repeat_ids():
    case = {"case_id": "one", "expected": {"text": "12 ㎎/L"}, "source_group_id": "original"}
    record = dict(case, expected_sha256=json_hash(case["expected"]), status="error", metrics=None)
    validate_worker_records([case], [record])
    for changed in [dict(record, expected={"text": "13 ㎎/L"}), dict(record, source_group_id="different"),
                    dict(record, expected_sha256="wrong"), dict(record, case_id="other")]:
        with pytest.raises(ValueError):
            validate_worker_records([case], [changed])
    with pytest.raises(ValueError, match="중복"):
        validate_worker_records([case], [record, record])


def test_worker_metrics_are_recomputed_against_parent_truth(monkeypatch):
    from tools.screen_text_lab import crop_evaluation
    case = {"case_id": "one", "expected": {"text": "12"}}
    monkeypatch.setattr(crop_evaluation, "score_case", lambda original, prediction: {"correct": False})
    record = dict(case, expected_sha256=json_hash(case["expected"]), status="ok", prediction={"text": "13"},
                  metrics={"correct": True})
    with pytest.raises(ValueError, match="채점"):
        validate_worker_records([case], [record])
