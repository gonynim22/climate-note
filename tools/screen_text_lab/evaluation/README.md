# Saved-record evaluation

This package never loads a model, captures a screen or opens corpus images. Use
it only with explicitly selected development records. Do not read final records
before the candidate, thresholds, recipe and final-access plan are frozen.

```python
from tools.screen_text_lab.evaluation import analyze_pair, assess, compare_three_way
from tools.screen_text_lab.evaluation.report import save_report

analysis = analyze_pair(product_records, candidate_records, manifest["cases"],
                        recipe, supported_characters=product_dictionary)
decision = assess(analysis)  # Missing evidence cannot pass.
save_report(new_output_directory, analysis, decision)
```

`analyze_pair` requires the complete expected manifest, not the intersection of
successful records. Existing `cases.jsonl` fields are preserved: `case_id`,
`source_group_id`, `split`, `source_kind`, `tags`, `review_status`, `image_sha256`,
`expected`, `expected_sha256`, `status`, and `prediction`. A prediction needs
`text`, a nonnegative integer `unsure_count`, and `table` when table truth exists.
Stored metrics are optional, are recomputed using the existing NFC/LF scorer,
and a mismatch blocks eligibility. Noncompleted or unreviewed rows are excluded
explicitly, which also blocks eligibility.

For the new selection bridge, use `load_crop_run(run_directory,
expected_manifest_sha256=selected_manifest_digest)` first. It requires
`kind=selection_line_crop`, completed status, unchanged source/input snapshots,
matching request/audit/expected manifest digest, matching request/record cases,
canonical scores, and model/dictionary/image copy hashes. It reads only the
explicit run's artifacts, does not open the original dataset, and returns
`records`, `cases`, and `provenance` (model role/id/hashes and artifact hashes).
Pass its records to `analyze_pair` with the external complete manifest and
retain its provenance in the caller's comparison result.

For other run formats, the caller must first verify completed state, cases-file hash,
image/manifest hashes, model/dictionary/source fingerprints and input-stability
checks. This pure record scorer cannot authenticate an in-memory list against
files it never opens. Preserve those run artifacts alongside the comparison.
The comparison input SHA binds the supplied lists/manifest/recipe/vocabulary;
it does not by itself prove which model produced them.

Manifest metadata additionally supplies `document_id`, `template_family_id`,
`evaluation_scope` (`line_crop` or `screen`), `critical_tags`, and
`review_provenance.human_reviewed`. Real app coverage uses `tags.app` values
`hwp`, `pdf`, `word`, `notepad`. Connected components of source/document/template
relationships form bootstrap clusters. Template families are conservatively
correlated, not independently replicated observations. The group macro CER is
the mean of within-cluster case CER means. The percentile paired bootstrap
resamples whole connected clusters and recomputes the micro CER difference.

Shared-vocabulary/OOV slices partition complete cases; they never delete or
replace characters. A case containing an OOV stays in all primary metrics.
The shared vocabulary should normally be P's fixed dictionary for both A/B.
Critical tags measure *whole-case* edit-error increases, not token-specific
accuracy. If a critical case changes but both readings remain wrong, a net CER
gain could hide a newly wrong number or unit. Eligibility requires input-bound
`critical_review: {"method": "annotated_spans" | "human_diff", "cases": {...}}`
for exactly those ambiguous case IDs. Each boolean is true if a new critical
token error exists. Missing review is incomplete; any true value fails. A fully
correct candidate or unchanged reading needs no such additional review.
Table-cell content and shape errors are checked independently of
text CER. Shape distance counts the absolute row-count difference plus absolute
per-row column-count differences, including missing/extra rows.
Expected row/column positions additionally count correct→wrong cells, recovered
cells and newly added extra cells separately. Fixing one cell cannot compensate
for a newly wrong previously correct cell or a new extra cell, even if both
whole tables were already wrong and their total error count improves.

`compare_three_way(P, R, F, cases, ...)` reports export drift P→R, training
effect R→F, and product benefit P→F. Only P→F receives quality eligibility
gates. It does not prove numerical parity of tensors or correct weight loading.

`DEFAULT_RECIPE` is a conservative *proposal*, not a measured or frozen final
recipe. Copy it, fix all fields before the experiment and retain its hash.
Line crops always lack screen eligibility. Actual-screen improvement is scored
separately from synthetic data so synthetic volume cannot hide real regression.
Relative-reduction intervals are absent if any bootstrap draw has zero baseline
errors; those draws are not silently discarded. A CER-difference interval is
still reported. Positive evidence of improvement requires its upper bound < 0.

`assess(analysis, evidence)` additionally requires evidence bound using
`evidence.input_sha256 == analysis.input_sha256`:

```json
{
  "input_sha256": "exact comparison input hash",
  "clipping": {"case-id": false},
  "candidate_model_bytes": 13401252,
  "benchmark": {
    "status": "completed", "case_ids": ["case-id"],
    "warmup_pairs": 3, "threads": 4, "cpu": "recorded CPU",
    "samples": [
      {"case_id": "case-id", "repeat": 0, "first": "baseline",
       "baseline_ms": 100.0, "candidate_ms": 100.0}
    ]
  }
}
```

Clipping values must be explicit candidate observations for *all* expected
cases. Benchmark case IDs come from the frozen recipe; each has all configured
repeats, at least five, with alternating baseline/candidate order. Workload
choice must cover the intended apps, line counts and region sizes; freeze it
without reading final errors. Report pooled workload median and nearest-rank
p95 using all paired repeats. Single-run `total_ms` is never accepted instead.
Wall-clock samples and model size must be measured by the caller, not invented.

Eligibility can be `passed`, `failed`, or `incomplete`; each gate also names
missing measurements. It is never deployment approval. Final-access provenance,
seed stability, existing regression corpus, product lifecycle/capture safety,
EXE verification and human approval remain separate required work.
