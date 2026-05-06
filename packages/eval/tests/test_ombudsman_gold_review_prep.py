"""Focused tests for Housing Ombudsman gold-review draft generation."""
from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

from eval.schema import GoldCase


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts/eval/prepare_housing_ombudsman_gold_review.py"

spec = importlib.util.spec_from_file_location(
    "prepare_housing_ombudsman_gold_review", SCRIPT_PATH
)
prep = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prep
assert spec.loader is not None
spec.loader.exec_module(prep)


def test_draft_decision_keeps_final_award_only_in_ground_truth() -> None:
    span = {"page": 1, "paragraph": 2, "text_span": [10, 20]}
    draft = prep._draft_decision(
        {
            "case_id": "housing-ombudsman-test",
            "decision_date": "2026-01-15",
            "landlord_name": "Test Council",
            "source_url": "https://example.test/decision",
            "source_license": "unknown",
            "target_source_id": "202600001",
            "corpus_version": "test-corpus",
            "train_test_split": "test",
            "primary_matter_type": "repairs_damp_mould",
        },
        bundle={"source_pdf_sha256": "a" * 64},
        paragraphs=[],
        facts=(
            "Resident complained before the Ombudsman decision about recurring "
            "damp and mould and the landlord's repair response."
        ),
        facts_span=span,
        final_award=Decimal("575.00"),
        final_award_span=span,
        quote_text="The landlord must pay the resident GBP 575.",
        quote_span=span,
    )

    case = draft["case"]
    assert case["disputed_amount_gbp"] is None
    assert case["claimed_amounts"] == []
    assert case["case_size"] == "unknown"
    assert case["ground_truth_outcome"]["total_awarded_gbp"] == "575.00"

    paths = {
        row["field_path"]
        for row in draft["labeling_provenance"]["field_provenance"]
    }
    assert "disputed_amount_gbp" not in paths
    assert not any(path.startswith("claimed_amounts[") for path in paths)
    assert "ground_truth_outcome.total_awarded_gbp" in paths

    # The draft is a human-review packet — reviewers fill in determination
    # before promotion. Mirror that step here so the schema-level validation
    # (INV-D4) passes for housing.repairs_social.v1 rows.
    case["ground_truth_outcome"]["determination"] = "maladministration"
    case["ground_truth_outcome"]["amount_ordered_now_gbp"] = "575.00"

    validated = GoldCase.model_validate(case)
    assert validated.disputed_amount_gbp is None
    assert validated.case_size.value == "unknown"
    assert "field_provenance rows" in draft["_review_instructions"]
    assert "disputed_amount_gbp or claimed_amounts" in draft["_review_instructions"]


# ---------------------------------------------------------------------------
# Determination auto-suggestion block
# ---------------------------------------------------------------------------


def test_determination_block_emits_for_known_outcome_normalized() -> None:
    out = prep._build_determination_suggestion_block(
        outcome_normalized="reasonable-redress",
        total_awarded_gbp="1000.00",
    )
    assert out is not None
    assert "## Determination (auto-suggested)" in out
    assert "`reasonable_redress`" in out
    # Reasonable redress maps the total to the previously-offered split.
    assert "amount_previously_offered_gbp: `1000.00`" in out
    assert "amount_ordered_now_gbp: `null`" in out
    assert "amount_global_unapportioned_gbp: `null`" in out


def test_determination_block_returns_none_for_missing_outcome() -> None:
    assert (
        prep._build_determination_suggestion_block(None, None) is None
    )
    assert (
        prep._build_determination_suggestion_block("", "100.00") is None
    )


def test_determination_block_returns_none_for_unknown_tag() -> None:
    assert (
        prep._build_determination_suggestion_block("totally-unknown", "100")
        is None
    )


def test_determination_block_handles_outside_jurisdiction_with_zero_total() -> None:
    out = prep._build_determination_suggestion_block(
        outcome_normalized="outside-jurisdiction",
        total_awarded_gbp="0",
    )
    assert out is not None
    assert "`outside_jurisdiction`" in out
    # Outside-jurisdiction must zero the splits.
    assert "amount_ordered_now_gbp: `null`" in out
    assert "amount_previously_offered_gbp: `null`" in out
    assert "amount_global_unapportioned_gbp: `null`" in out


def test_determination_block_flags_internal_inconsistency() -> None:
    out = prep._build_determination_suggestion_block(
        outcome_normalized="outside-jurisdiction",
        total_awarded_gbp="500",
    )
    assert out is not None
    assert "HUMAN-REVIEW REQUIRED" in out


def test_determination_block_maladministration_routes_to_ordered_now() -> None:
    out = prep._build_determination_suggestion_block(
        outcome_normalized="maladministration",
        total_awarded_gbp="750.00",
    )
    assert out is not None
    assert "`maladministration`" in out
    assert "amount_ordered_now_gbp: `750.00`" in out
    assert "amount_previously_offered_gbp: `null`" in out


def test_determination_block_renders_inside_review_markdown() -> None:
    """The auto-suggest block lands inside the per-case packet markdown."""
    span = {"page": 1, "paragraph": 2, "text_span": [10, 20]}
    draft = prep._draft_decision(
        {
            "case_id": "housing-ombudsman-test-md",
            "decision_date": "2026-01-15",
            "landlord_name": "Test Council",
            "source_url": "https://example.test/decision",
            "source_license": "unknown",
            "target_source_id": "202600002",
            "corpus_version": "test-corpus",
            "train_test_split": "test",
            "primary_matter_type": "repairs_damp_mould",
        },
        bundle={"source_pdf_sha256": "a" * 64},
        paragraphs=[],
        facts="Resident complained about damp before the Ombudsman ruling.",
        facts_span=span,
        final_award=Decimal("575.00"),
        final_award_span=span,
        quote_text="The landlord must pay the resident GBP 575.",
        quote_span=span,
    )
    md = prep._review_markdown(
        {
            "case_id": "housing-ombudsman-test-md",
            "outcome_raw": "Maladministration",
            "outcome_normalized": "maladministration",
            "matter_types": ["repairs_damp_mould"],
            "primary_matter_type": "repairs_damp_mould",
            "decision_date": "2026-01-15",
            "landlord_name": "Test Council",
            "source_slug": "test-slug",
            "target_source_id": "202600002",
            "title": "Test",
            "source_url": "https://example.test/decision",
        },
        bundle_path=prep.REPO_ROOT / "data/eval_artifacts/x.json",
        raw_text_path=prep.REPO_ROOT / "data/eval_artifacts/x.txt",
        draft_path=prep.REPO_ROOT / "data/eval_artifacts/x.draft.json",
        facts="Resident complained about damp.",
        amount_candidates=[],
        draft=draft,
    )
    # Block is sandwiched between "## Manifest Strata" and "## Candidate Gold Fields".
    manifest_idx = md.index("## Manifest Strata")
    determination_idx = md.index("## Determination (auto-suggested)")
    candidate_idx = md.index("## Candidate Gold Fields")
    assert manifest_idx < determination_idx < candidate_idx
    assert "amount_ordered_now_gbp: `575.00`" in md


def test_review_markdown_omits_determination_block_when_missing() -> None:
    """Cases lacking outcome_normalized must NOT render the auto-suggest block."""
    span = {"page": 1, "paragraph": 2, "text_span": [10, 20]}
    draft = prep._draft_decision(
        {
            "case_id": "housing-ombudsman-test-md2",
            "decision_date": "2026-01-15",
            "landlord_name": "Test Council",
            "source_url": "https://example.test/decision",
            "source_license": "unknown",
            "target_source_id": "202600003",
            "corpus_version": "test-corpus",
            "train_test_split": "test",
            "primary_matter_type": "repairs_damp_mould",
        },
        bundle={"source_pdf_sha256": "a" * 64},
        paragraphs=[],
        facts="Some facts.",
        facts_span=span,
        final_award=Decimal("100.00"),
        final_award_span=span,
        quote_text="Some quote.",
        quote_span=span,
    )
    md = prep._review_markdown(
        {
            "case_id": "housing-ombudsman-test-md2",
            "outcome_raw": None,
            "outcome_normalized": None,
            "matter_types": [],
            "primary_matter_type": None,
            "decision_date": None,
            "landlord_name": None,
            "source_slug": None,
            "target_source_id": "202600003",
            "title": None,
            "source_url": None,
        },
        bundle_path=prep.REPO_ROOT / "data/eval_artifacts/x.json",
        raw_text_path=prep.REPO_ROOT / "data/eval_artifacts/x.txt",
        draft_path=prep.REPO_ROOT / "data/eval_artifacts/x.draft.json",
        facts="Some facts.",
        amount_candidates=[],
        draft=draft,
    )
    assert "## Determination (auto-suggested)" not in md
