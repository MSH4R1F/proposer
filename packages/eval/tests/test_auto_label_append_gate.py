"""Tests for the real-gold append gate.

Covers every refusal condition listed in the SHA-28 LLM-labeling sparring
document §8. Each refusal case mutates a single field of an otherwise-valid
gold case and asserts the raised :class:`AppendGateError` names the matching
:class:`AppendGateRule` value.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from eval.auto_label.append_gate import (
    AppendGateError,
    AppendGateRule,
    MANDATORY_REVIEW_FIELDS,
    REQUIRED_MANIFEST_FIELDS,
    assert_real_gold_appendable,
)
from eval.schema import (
    FieldLabelProvenance,
    GoldCase,
    LabelerModel,
    LabelingProvenance,
    Provenance,
)


_FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Two stable 64-hex-char hashes used across the suite.
_PDF_SHA = "a" * 64
_OCR_SHA = "b" * 64


def _provenance_kwargs(field_provenance: list[FieldLabelProvenance]) -> dict:
    return dict(
        run_id="run-2026-05-02-append-gate",
        labeled_at=datetime(2026, 5, 2, 14, 30, tzinfo=timezone.utc),
        labeler_models=[
            LabelerModel(provider="anthropic", model="claude-sonnet-4-20250514"),
            LabelerModel(provider="openai", model="gpt-5.5"),
        ],
        source_pdf_sha256=_PDF_SHA,
        ocr_text_sha256=_OCR_SHA,
        prompt_template_hash="t" * 16,
        gold_schema_hash="s" * 16,
        corpus_manifest_hash="c" * 16,
        canonicalizer_version="1.0.0",
        grounder_version="1.0.0",
        audit_seed=42,
        adjudicated_fields=[],
        inter_model_agreement_rate=0.92,
        grounding_pass_rate=0.88,
        audit_flip_rate=0.04,
        mandatory_review_flip_rate=0.10,
        field_provenance=field_provenance,
    )


def _human_reviewed(field_path: str) -> FieldLabelProvenance:
    return FieldLabelProvenance(
        field_path=field_path,
        source="human_mandatory_review",
        source_spans=[Provenance(page=1, paragraph=2)],
        reviewer_rationale="Verified against order page.",
    )


def _full_field_provenance_for(gc_dict: dict) -> list[FieldLabelProvenance]:
    """Build a FieldLabelProvenance covering every MandatoryReviewSet path
    derived from the gold-case dict's actual outcome shape."""
    paths = set(MANDATORY_REVIEW_FIELDS)
    gto = gc_dict["ground_truth_outcome"]
    if gto.get("unapportioned_reason") is not None:
        paths.add("ground_truth_outcome.unapportioned_reason")
    else:
        for io in gto["per_issue"]:
            issue = io["issue"]
            paths.add(f"ground_truth_outcome.per_issue[issue={issue}].winner")
            paths.add(f"ground_truth_outcome.per_issue[issue={issue}].awarded_gbp")
    return [_human_reviewed(p) for p in sorted(paths)]


def _full_gold_case_dict() -> dict:
    """Return a real-gold-appendable case dict (all SHA-20 fields set,
    full MandatoryReviewSet covered, source_pdf_sha256 matching artifact)."""
    base = json.loads((_FIXTURES_DIR / "gold_case_minimal.json").read_text())
    # Match the artifact PDF hash so the schema's source_pdf_sha256 lines up
    # when we (independently) write a hash-matched artifact in tests.
    base["source_pdf_sha256"] = _PDF_SHA
    # SHA-20 Phase 7 envelope fields.
    base["domain_id"] = "housing.deposit.v1"
    base["forum"] = "ftt_pc"
    base["retrieval_namespace_id"] = "housing.deposit.v1"
    base["target_source_id"] = "src-housing-deposit-2023-0001"
    base["corpus_version"] = "housing_v1@2026-05-02"
    base["source_publisher"] = "ftt"
    base["source_kind"] = "tribunal_decision"
    base["source_license"] = "OGL-3.0"
    base["matter_type"] = "deposit_deduction"
    base["labeling_provenance"] = LabelingProvenance(
        **_provenance_kwargs(_full_field_provenance_for(base))
    ).model_dump(mode="json")
    return base


def _write_artifact(
    tmp_path: Path,
    *,
    pdf_sha: str = _PDF_SHA,
    ocr_sha: str = _OCR_SHA,
) -> Path:
    # Artifact JSON shape: a flat object with the two replay hashes the
    # gate checks against. The full per-case run artifact (raw labeler
    # outputs, prompt rendering, etc.) will accrete additional keys later;
    # the gate only requires these two and ignores the rest.
    artifact = {
        "source_pdf_sha256": pdf_sha,
        "ocr_text_sha256": ocr_sha,
        "run_id": "run-2026-05-02-append-gate",
        "case_id": "SYNTH-2023-0001",
    }
    path = tmp_path / "case_artifact.json"
    path.write_text(json.dumps(artifact))
    return path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_real_gold_is_appendable(tmp_path: Path) -> None:
    gc = GoldCase(**_full_gold_case_dict())
    artifact = _write_artifact(tmp_path)
    # No exception is success.
    assert_real_gold_appendable(gc, run_artifact_path=artifact)


# ---------------------------------------------------------------------------
# One refusal test per AppendGateRule
# ---------------------------------------------------------------------------


def test_refuses_missing_labeling_provenance(tmp_path: Path) -> None:
    d = _full_gold_case_dict()
    d["labeling_provenance"] = None
    gc = GoldCase(**d)
    artifact = _write_artifact(tmp_path)
    with pytest.raises(AppendGateError) as ei:
        assert_real_gold_appendable(gc, run_artifact_path=artifact)
    assert AppendGateRule.MISSING_LABELING_PROVENANCE.value in str(ei.value)


def test_refuses_negative_kind_set(tmp_path: Path) -> None:
    d = _full_gold_case_dict()
    d["negative_kind"] = "insufficient_evidence"
    gc = GoldCase(**d)
    artifact = _write_artifact(tmp_path)
    with pytest.raises(AppendGateError) as ei:
        assert_real_gold_appendable(gc, run_artifact_path=artifact)
    assert AppendGateRule.NEGATIVE_KIND_NOT_NONE.value in str(ei.value)


def test_refuses_missing_target_source_id(tmp_path: Path) -> None:
    d = _full_gold_case_dict()
    d["target_source_id"] = None
    gc = GoldCase(**d)
    artifact = _write_artifact(tmp_path)
    with pytest.raises(AppendGateError) as ei:
        assert_real_gold_appendable(gc, run_artifact_path=artifact)
    assert AppendGateRule.MISSING_TARGET_SOURCE_ID.value in str(ei.value)


@pytest.mark.parametrize("missing_field", REQUIRED_MANIFEST_FIELDS)
def test_refuses_missing_manifest_field(tmp_path: Path, missing_field: str) -> None:
    d = _full_gold_case_dict()
    d[missing_field] = None
    gc = GoldCase(**d)
    artifact = _write_artifact(tmp_path)
    with pytest.raises(AppendGateError) as ei:
        assert_real_gold_appendable(gc, run_artifact_path=artifact)
    msg = str(ei.value)
    assert AppendGateRule.MISSING_MANIFEST_FIELD.value in msg
    # Error message names the offending field.
    assert missing_field in msg


def test_refuses_incomplete_mandatory_review(tmp_path: Path) -> None:
    d = _full_gold_case_dict()
    # Drop the ``facts`` review entry from field_provenance.
    fp = d["labeling_provenance"]["field_provenance"]
    d["labeling_provenance"]["field_provenance"] = [
        e for e in fp if e["field_path"] != "facts"
    ]
    gc = GoldCase(**d)
    artifact = _write_artifact(tmp_path)
    with pytest.raises(AppendGateError) as ei:
        assert_real_gold_appendable(gc, run_artifact_path=artifact)
    msg = str(ei.value)
    assert AppendGateRule.INCOMPLETE_MANDATORY_REVIEW.value in msg
    assert "facts" in msg


def test_refuses_missing_run_artifact(tmp_path: Path) -> None:
    gc = GoldCase(**_full_gold_case_dict())
    artifact = tmp_path / "does_not_exist.json"
    with pytest.raises(AppendGateError) as ei:
        assert_real_gold_appendable(gc, run_artifact_path=artifact)
    assert AppendGateRule.MISSING_RUN_ARTIFACT.value in str(ei.value)


def test_refuses_artifact_hash_mismatch(tmp_path: Path) -> None:
    gc = GoldCase(**_full_gold_case_dict())
    # Artifact's ocr_text_sha256 differs from the labeling provenance's.
    artifact = _write_artifact(tmp_path, ocr_sha="d" * 64)
    with pytest.raises(AppendGateError) as ei:
        assert_real_gold_appendable(gc, run_artifact_path=artifact)
    msg = str(ei.value)
    assert AppendGateRule.ARTIFACT_HASH_MISMATCH.value in msg
    assert "ocr_text_sha256" in msg


# ---------------------------------------------------------------------------
# Per-issue mandatory review path generation
# ---------------------------------------------------------------------------


def test_per_issue_paths_partially_covered(tmp_path: Path) -> None:
    """A case with two per_issue entries where only one is covered must
    fail INCOMPLETE_MANDATORY_REVIEW citing the uncovered issue paths."""
    d = _full_gold_case_dict()
    # Reshape outcome into a two-issue split award.
    d["claimed_amounts"] = [
        {"issue": "carpet_cleaning", "amount_gbp": "300.00", "by_party": "landlord"},
        {"issue": "redecoration", "amount_gbp": "100.00", "by_party": "landlord"},
    ]
    d["disputed_amount_gbp"] = "400.00"
    d["ground_truth_outcome"] = {
        "overall_winner": "split",
        "total_awarded_gbp": "180.00",
        "per_issue": [
            {"issue": "carpet_cleaning", "winner": "tenant", "awarded_gbp": "120.00"},
            {"issue": "redecoration", "winner": "landlord", "awarded_gbp": "60.00"},
        ],
    }
    # Build the FULL MandatoryReviewSet then drop the redecoration entries.
    full = _full_field_provenance_for(d)
    pruned = [
        fp
        for fp in full
        if "redecoration" not in fp.field_path
    ]
    d["labeling_provenance"] = LabelingProvenance(
        **_provenance_kwargs(pruned)
    ).model_dump(mode="json")
    gc = GoldCase(**d)
    artifact = _write_artifact(tmp_path)
    with pytest.raises(AppendGateError) as ei:
        assert_real_gold_appendable(gc, run_artifact_path=artifact)
    msg = str(ei.value)
    assert AppendGateRule.INCOMPLETE_MANDATORY_REVIEW.value in msg
    assert "redecoration" in msg
    # The carpet_cleaning paths were covered, so the gate must not list them.
    assert ".winner" in msg or ".awarded_gbp" in msg


# ---------------------------------------------------------------------------
# Unapportioned outcome
# ---------------------------------------------------------------------------


def test_unapportioned_outcome_requires_unapportioned_reason_review(
    tmp_path: Path,
) -> None:
    """When ``unapportioned_reason`` is set, MandatoryReviewSet replaces
    per-issue paths with ``ground_truth_outcome.unapportioned_reason``.
    Coverage of that single path must satisfy the gate."""
    d = _full_gold_case_dict()
    # Strip the apportioned outcome and use an unapportioned global figure.
    d["ground_truth_outcome"] = {
        "overall_winner": "tenant",
        "total_awarded_gbp": "220.00",
        "per_issue": [],
        "unapportioned_reason": "Tribunal awarded a global figure with no "
        "per-issue breakdown.",
    }
    fp = _full_field_provenance_for(d)
    # Sanity: per-issue paths are absent, unapportioned_reason is present.
    paths = {f.field_path for f in fp}
    assert "ground_truth_outcome.unapportioned_reason" in paths
    assert not any("per_issue" in p for p in paths)
    d["labeling_provenance"] = LabelingProvenance(
        **_provenance_kwargs(fp)
    ).model_dump(mode="json")
    gc = GoldCase(**d)
    artifact = _write_artifact(tmp_path)
    # Happy path under unapportioned outcome.
    assert_real_gold_appendable(gc, run_artifact_path=artifact)


def test_unapportioned_outcome_missing_reason_review_refused(
    tmp_path: Path,
) -> None:
    """If ``unapportioned_reason`` is set but the human did not review it,
    the gate must refuse."""
    d = _full_gold_case_dict()
    d["ground_truth_outcome"] = {
        "overall_winner": "tenant",
        "total_awarded_gbp": "220.00",
        "per_issue": [],
        "unapportioned_reason": "Tribunal awarded a global figure with no "
        "per-issue breakdown.",
    }
    fp = _full_field_provenance_for(d)
    fp = [f for f in fp if f.field_path != "ground_truth_outcome.unapportioned_reason"]
    d["labeling_provenance"] = LabelingProvenance(
        **_provenance_kwargs(fp)
    ).model_dump(mode="json")
    gc = GoldCase(**d)
    artifact = _write_artifact(tmp_path)
    with pytest.raises(AppendGateError) as ei:
        assert_real_gold_appendable(gc, run_artifact_path=artifact)
    msg = str(ei.value)
    assert AppendGateRule.INCOMPLETE_MANDATORY_REVIEW.value in msg
    assert "unapportioned_reason" in msg


# ---------------------------------------------------------------------------
# Sanity: model_agreement source does NOT count as human review
# ---------------------------------------------------------------------------


def test_model_agreement_source_does_not_satisfy_mandatory_review(
    tmp_path: Path,
) -> None:
    d = _full_gold_case_dict()
    fp = d["labeling_provenance"]["field_provenance"]
    # Flip every facts entry to model_agreement (LLMs agreed, no human).
    for entry in fp:
        if entry["field_path"] == "facts":
            entry["source"] = "model_agreement"
    gc = GoldCase(**d)
    artifact = _write_artifact(tmp_path)
    with pytest.raises(AppendGateError) as ei:
        assert_real_gold_appendable(gc, run_artifact_path=artifact)
    assert AppendGateRule.INCOMPLETE_MANDATORY_REVIEW.value in str(ei.value)
    assert "facts" in str(ei.value)


# ---------------------------------------------------------------------------
# Stability: mutating the input dict between cases should not leak state.
# ---------------------------------------------------------------------------


def test_full_dict_factory_is_independent_per_call() -> None:
    a = _full_gold_case_dict()
    b = _full_gold_case_dict()
    a["case_id"] = "MUTATED"
    assert b["case_id"] != "MUTATED"
    # Pydantic round-trip works on both.
    GoldCase(**a)
    GoldCase(**b)
    # Deepcopy isolation explicit.
    c = copy.deepcopy(a)
    c["facts"] = "x" * 60
    assert a["facts"] != c["facts"]
