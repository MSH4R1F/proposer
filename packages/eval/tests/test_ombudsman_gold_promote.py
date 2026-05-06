"""Focused tests for the housing-ombudsman gold promotion path.

The promote script reads ``outcome_normalized`` from the per-case review
packet and uses it to populate ``determination``, ``overall_winner_legacy``,
and the appropriate amount-split field on the GoldCase before the append
gate runs.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts/eval/promote_housing_ombudsman_reviewed_gold.py"

spec = importlib.util.spec_from_file_location(
    "promote_housing_ombudsman_reviewed_gold", SCRIPT_PATH
)
promote = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = promote
assert spec.loader is not None
spec.loader.exec_module(promote)


# ---------------------------------------------------------------------------
# _read_outcome_normalized_from_packet
# ---------------------------------------------------------------------------


_PACKET_TEMPLATE = """# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-test`

## Manifest Strata

- Outcome raw: `Maladministration`
- Outcome normalized: `{tag}`
- Matter types: `repairs_damp_mould`

## Determination (auto-suggested)

- determination: `maladministration`

## Candidate Gold Fields
"""


def test_read_outcome_normalized_from_packet_returns_tag(tmp_path: Path) -> None:
    packet = tmp_path / "case.review.md"
    packet.write_text(_PACKET_TEMPLATE.format(tag="maladministration"))
    assert (
        promote._read_outcome_normalized_from_packet(packet) == "maladministration"
    )


def test_read_outcome_normalized_from_packet_missing_returns_none(
    tmp_path: Path,
) -> None:
    assert (
        promote._read_outcome_normalized_from_packet(tmp_path / "nonexistent.md")
        is None
    )


def test_read_outcome_normalized_from_packet_no_tag_returns_none(
    tmp_path: Path,
) -> None:
    packet = tmp_path / "case.review.md"
    packet.write_text("# Header\n\nNo manifest strata here.\n")
    assert promote._read_outcome_normalized_from_packet(packet) is None


# ---------------------------------------------------------------------------
# _apply_determination_to_case_payload
# ---------------------------------------------------------------------------


def _base_case_payload(total: str = "575.00") -> dict:
    return {
        "case_id": "housing-ombudsman-promote-test",
        "ground_truth_outcome": {
            "overall_winner": "tenant",
            "total_awarded_gbp": total,
            "unapportioned_reason": (
                "Housing Ombudsman compensation orders are reported globally; "
                "no per-issue split is available."
            ),
            "per_issue": [],
        },
    }


def test_apply_determination_populates_maladministration_split() -> None:
    case_payload = _base_case_payload(total="750.00")
    promote._apply_determination_to_case_payload(case_payload, "maladministration")
    gto = case_payload["ground_truth_outcome"]
    assert gto["determination"] == "maladministration"
    assert gto["overall_winner_legacy"] == "tenant"
    assert gto["amount_ordered_now_gbp"] == "750.00"
    assert gto["amount_previously_offered_gbp"] is None
    assert gto["amount_global_unapportioned_gbp"] is None


def test_apply_determination_populates_reasonable_redress_split() -> None:
    case_payload = _base_case_payload(total="200.00")
    promote._apply_determination_to_case_payload(
        case_payload, "reasonable-redress"
    )
    gto = case_payload["ground_truth_outcome"]
    assert gto["determination"] == "reasonable_redress"
    assert gto["overall_winner_legacy"] == "landlord"
    assert gto["amount_ordered_now_gbp"] is None
    assert gto["amount_previously_offered_gbp"] == "200.00"
    assert gto["amount_global_unapportioned_gbp"] is None


def test_apply_determination_resolved_with_intervention_routes_to_global() -> None:
    case_payload = _base_case_payload(total="300.00")
    promote._apply_determination_to_case_payload(
        case_payload, "resolved-with-intervention"
    )
    gto = case_payload["ground_truth_outcome"]
    assert gto["determination"] == "resolved_with_intervention"
    assert gto["overall_winner_legacy"] == "split"
    assert gto["amount_global_unapportioned_gbp"] == "300.00"
    assert gto["amount_ordered_now_gbp"] is None
    assert gto["amount_previously_offered_gbp"] is None


def test_apply_determination_no_op_for_missing_outcome() -> None:
    case_payload = _base_case_payload()
    promote._apply_determination_to_case_payload(case_payload, None)
    gto = case_payload["ground_truth_outcome"]
    assert "determination" not in gto
    assert "overall_winner_legacy" not in gto
    assert "amount_ordered_now_gbp" not in gto


def test_apply_determination_no_op_for_unknown_tag() -> None:
    case_payload = _base_case_payload()
    promote._apply_determination_to_case_payload(case_payload, "unknown-tag")
    gto = case_payload["ground_truth_outcome"]
    assert "determination" not in gto


def test_apply_determination_no_op_when_outside_jurisdiction_has_money() -> None:
    """Internal inconsistency must NOT silently promote — INV-D4 should reject."""
    case_payload = _base_case_payload(total="500.00")
    promote._apply_determination_to_case_payload(
        case_payload, "outside-jurisdiction"
    )
    gto = case_payload["ground_truth_outcome"]
    # Determination left unset on inconsistency so the case fails INV-D4.
    assert "determination" not in gto


def test_apply_determination_outside_jurisdiction_with_zero_total_clears_splits() -> None:
    case_payload = _base_case_payload(total="0")
    promote._apply_determination_to_case_payload(
        case_payload, "outside-jurisdiction"
    )
    gto = case_payload["ground_truth_outcome"]
    assert gto["determination"] == "outside_jurisdiction"
    assert gto["overall_winner_legacy"] == "landlord"
    assert gto["amount_ordered_now_gbp"] is None
    assert gto["amount_previously_offered_gbp"] is None
    assert gto["amount_global_unapportioned_gbp"] is None
