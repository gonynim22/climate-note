"""자료 누출·정답 손실·이미지 계보를 작은 가짜 입력으로 검증한다."""
import json

import pytest

from tools.screen_text_lab.datasets.audit import (
    cross_audit, ctc_required_steps, label_check, near_key, sha256, validate_manifest, validate_source_plan, write_json,
)
from tools.screen_text_lab.datasets.sources import sources_for


def _case(split="train", text="확인 자료", suffix="a"):
    return {"case_id": suffix, "split": split, "document_id": "document-" + suffix,
            "template_family_id": "family-" + suffix, "source_group_id": "source-" + suffix,
            "image_sha256": "image-" + suffix, "text": text, "expected": {"text": text},
            "image_size": [128, 48], "render_check": {"glyph_zero_count": 0, "ink_clipped": False}}


def _manifest(case):
    return {"dataset_id": case["split"], "cases": [case]}


@pytest.mark.parametrize("field", ["document_id", "template_family_id", "source_group_id", "image_sha256"])
def test_cross_corpus_rejects_shared_lineage_even_when_text_differs(field):
    left = _case()
    right = _case("selection", "서로 다른 문장", "b")
    right[field] = left[field]
    result = cross_audit([_manifest(left), _manifest(right)])
    assert result["status"] == "failed"
    assert any(item["kind"] == field for item in result["failures"])


def test_number_replacement_is_not_independent_text():
    left = _case(text="납부 금액은 123,400원입니다.")
    right = _case("selection", "납부 금액은 987,600원입니다.", "b")
    result = cross_audit([_manifest(left), _manifest(right)])
    assert any(item["kind"] == "near_text" for item in result["failures"])
    assert left["text"] == "납부 금액은 123,400원입니다."


def test_previous_synthetic_source_cannot_leak_into_new_training():
    case = _case(text="문서 접수 번호 2045")
    result = cross_audit([_manifest(case)], ["문서 접수 번호 2026"])
    assert result["failures"][0]["kind"] == "previous_synthetic_text"


def test_a_oov_does_not_normalize_or_drop_source_characters():
    case = _case(text="㈜시험 ₩2,000 / 18 ℃")
    alphabet = set(case["text"]) - {"㈜", "₩", "℃"}
    result = label_check(case, alphabet, {"128": 20})
    assert set(result["oov"]) == {"㈜", "₩", "℃"}
    assert not result["training_ready"]
    assert case["text"] == "㈜시험 ₩2,000 / 18 ℃"
    assert near_key("㈜") != near_key("(주)")


def test_repeated_letters_need_blank_time_steps():
    case = _case(text="가가나나")
    assert ctc_required_steps(case["text"]) == 6
    result = label_check(case, set(case["text"]), {"128": 5})
    assert "ctc_steps_insufficient" in result["reasons"]
    assert not result["training_ready"]


def test_unmeasured_width_is_not_training_ready():
    result = label_check(_case(), set("확인 자료"), {"320": 40})
    assert result["eligible_without_ctc"]
    assert result["ctc_status"] == "unmeasured"
    assert not result["training_ready"]


def test_glyph_loss_and_long_labels_are_visible_exclusions():
    case = _case(text="가" * 65)
    case["render_check"]["glyph_zero_count"] = 1
    result = label_check(case, {"가"}, {"128": 200})
    assert set(result["reasons"]) == {"missing_glyph", "length_exceeds_limit"}


def test_pilot_sources_have_disjoint_families_and_explicit_small_counts():
    train, selection = sources_for("train"), sources_for("selection")
    assert len(train) == 80 and len(selection) == 20
    assert not {item["template_family_id"] for item in train} & {item["template_family_id"] for item in selection}
    assert len({item["template_family_id"] for item in train}) == 20
    assert len({item["template_family_id"] for item in selection}) == 12
    with pytest.raises(ValueError, match="final"):
        sources_for("final")


def test_external_source_plan_rejects_final_or_cross_family_leakage():
    plan = {split: sources_for(split) for split in ("train", "selection")}
    assert validate_source_plan(plan)["status"] == "passed"
    plan["selection"][0]["template_family_id"] = plan["train"][0]["template_family_id"]
    with pytest.raises(ValueError, match="누출"):
        validate_source_plan(plan)
    plan["final"] = []
    with pytest.raises(ValueError, match="train/selection"):
        validate_source_plan(plan)


def _image_fixture(tmp_path):
    from PIL import Image
    (tmp_path / "images").mkdir()
    (tmp_path / "sources").mkdir()
    original = Image.new("RGB", (10, 10), "white")
    original.putpixel((3, 4), (20, 30, 40))
    original.save(tmp_path / "sources/original.png")
    original.crop((2, 2, 8, 8)).save(tmp_path / "images/crop.png")
    case = _case()
    case.update(image="images/crop.png", source_image="sources/original.png", crop=[2, 2, 8, 8],
                image_sha256=sha256(tmp_path / "images/crop.png"), image_size=[6, 6],
                source_image_sha256=sha256(tmp_path / "sources/original.png"))
    manifest = {"schema_version": 1, "dataset_id": "fixture", "split": "train", "cases": [case]}
    return manifest


def test_crop_coordinates_and_pixels_must_roundtrip(tmp_path):
    manifest = _image_fixture(tmp_path)
    write_json(tmp_path / "manifest.json", manifest)
    assert len(validate_manifest(tmp_path)["cases"]) == 1
    manifest["cases"][0]["crop"] = [1, 1, 7, 7]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="픽셀"):
        validate_manifest(tmp_path)


def test_crop_path_cannot_escape_dataset(tmp_path):
    manifest = _image_fixture(tmp_path)
    manifest["cases"][0]["image"] = "../outside.png"
    write_json(tmp_path / "manifest.json", manifest)
    with pytest.raises(ValueError, match="벗어났"):
        validate_manifest(tmp_path)


def test_rendered_symbols_are_retained_and_atlas_escapes_markup(tmp_path, qapp):
    from tools.screen_text_lab.datasets.build import CONDITIONS, render_line, write_atlas
    text = "㈜가상 <검토> & 18 ℃"
    image, crop, box, check = render_line(text, CONDITIONS[0], True)
    assert check["glyph_run_families"] and check["glyph_zero_count"] == 0
    assert image.copy(box[0], box[1], box[2] - box[0], box[3] - box[1]) == crop
    case = _case(text=text)
    case.update(image="images/test.png", source_image="sources/test.png", render_check=check,
                checks={"oov": ["㈜", "℃"], "ctc_status": "unmeasured"})
    write_atlas(tmp_path, {"split": "train", "cases": [case]})
    body = (tmp_path / "atlas.html").read_text(encoding="utf-8")
    assert "&lt;검토&gt; &amp;" in body and "<검토>" not in body


def test_extension_preserves_all_existing_ids_except_final_space():
    from tools.screen_text_lab.datasets.extension import expansion_mapping
    new_characters, mapping = expansion_mapping(["가", "나"], ["㈜", "℃", "₩"], {"℃"})
    assert new_characters == ["가", "나", "㈜", "℃", "₩"]
    assert mapping["ctc"]["old_to_new"] == [0, 1, 2, 6]
    assert mapping["nrtr"]["old_to_new"] == [0, 1, 2, 3, 4, 5, 9]
    assert mapping["ctc"]["tokens"][6]["token"] == " "
    assert mapping["nrtr"]["tokens"][9]["token"] == " "
    assert mapping["ctc"]["tokens"][3]["old_id"] is None


@pytest.mark.parametrize("additions,oov", [(["가"], []), (["℃", "℃"], []), ([" "], []), (["℃"], ["₩"])])
def test_extension_rejects_duplicate_or_unapproved_changes(additions, oov):
    from tools.screen_text_lab.datasets.extension import expansion_mapping
    with pytest.raises(ValueError):
        expansion_mapping(["가", "나"], additions, oov)


def test_extension_oov_counts_source_once_per_condition_but_preserves_occurrences():
    from tools.screen_text_lab.datasets.extension import oov_evidence
    first = _case(text="18 ℃~20 ℃")
    second = {**first, "case_id": "condition-b"}
    result = oov_evidence([{"cases": [first, second]}], set("18 ~20"))
    assert result["℃"]["source_groups"] == 1
    assert result["℃"]["source_occurrences"] == 2
    assert result["℃"]["images"] == 2
    assert result["℃"]["sources"][0]["text"] == "18 ℃~20 ℃"


def test_extension_glyph_provenance_has_concrete_font_table_hashes(qapp):
    from tools.screen_text_lab.datasets.build import CONDITIONS
    from tools.screen_text_lab.datasets.extension import glyph_evidence
    result = glyph_evidence("㈜", CONDITIONS[0])
    assert result["nonempty_glyph_run"] and not result["missing_glyph"]
    assert result["runs"][0]["font_tables"]["cmap"]["bytes"] > 0
    assert len(result["runs"][0]["font_tables"]["name"]["sha256"]) == 64
