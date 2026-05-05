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

    validated = GoldCase.model_validate(case)
    assert validated.disputed_amount_gbp is None
    assert validated.case_size.value == "unknown"
