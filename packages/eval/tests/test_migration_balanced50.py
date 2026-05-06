"""Tests for the balanced-50 (and any 50-case Housing Ombudsman) migration."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

# Ensure the repo root is on sys.path so `scripts.eval.<module>` is importable
# (mirrors the pattern in test_annotate_cli.py).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.eval.migrate_balanced50_to_determination_schema import (  # noqa: E402
    map_outcome_normalized_to_determination,
    split_amount_by_determination,
)
from eval.schema import Determination  # noqa: E402


class TestOutcomeNormalizedMapping:
    def test_outcome_normalized_to_determination_table(self):
        cases = [
            ("maladministration", Determination.MALADMINISTRATION),
            ("severe-maladministration", Determination.SEVERE_MALADMINISTRATION),
            ("service-failure", Determination.SERVICE_FAILURE),
            ("reasonable-redress", Determination.REASONABLE_REDRESS),
            ("no-maladministration", Determination.NO_MALADMINISTRATION),
            ("outside-jurisdiction", Determination.OUTSIDE_JURISDICTION),
            ("resolved-with-intervention", Determination.RESOLVED_WITH_INTERVENTION),
        ]
        for tag, expected in cases:
            assert map_outcome_normalized_to_determination(tag) == expected

    def test_outcome_normalized_unknown_raises(self):
        with pytest.raises(KeyError):
            map_outcome_normalized_to_determination("widget")


class TestSplitAmountByDetermination:
    @pytest.mark.parametrize(
        "determination,total,expected",
        [
            (Determination.MALADMINISTRATION, Decimal("500"),
             {"amount_ordered_now_gbp": Decimal("500"),
              "amount_previously_offered_gbp": None,
              "amount_global_unapportioned_gbp": None}),
            (Determination.SEVERE_MALADMINISTRATION, Decimal("1000"),
             {"amount_ordered_now_gbp": Decimal("1000"),
              "amount_previously_offered_gbp": None,
              "amount_global_unapportioned_gbp": None}),
            (Determination.SERVICE_FAILURE, Decimal("300"),
             {"amount_ordered_now_gbp": Decimal("300"),
              "amount_previously_offered_gbp": None,
              "amount_global_unapportioned_gbp": None}),
            (Determination.REASONABLE_REDRESS, Decimal("750"),
             {"amount_ordered_now_gbp": None,
              "amount_previously_offered_gbp": Decimal("750"),
              "amount_global_unapportioned_gbp": None}),
            (Determination.RESOLVED_WITH_INTERVENTION, Decimal("1450"),
             {"amount_ordered_now_gbp": None,
              "amount_previously_offered_gbp": None,
              "amount_global_unapportioned_gbp": Decimal("1450")}),
            (Determination.OUTSIDE_JURISDICTION, Decimal("0"),
             {"amount_ordered_now_gbp": None,
              "amount_previously_offered_gbp": None,
              "amount_global_unapportioned_gbp": None}),
            (Determination.NO_MALADMINISTRATION, Decimal("0"),
             {"amount_ordered_now_gbp": None,
              "amount_previously_offered_gbp": None,
              "amount_global_unapportioned_gbp": None}),
        ],
    )
    def test_split_amount_by_determination(self, determination, total, expected):
        got = split_amount_by_determination(determination, total)
        assert got == expected

    def test_split_amount_outside_jurisdiction_with_nonzero_total_raises(self):
        with pytest.raises(ValueError, match="outside_jurisdiction"):
            split_amount_by_determination(Determination.OUTSIDE_JURISDICTION, Decimal("100"))


class TestMigrateOneCase:
    """Unit tests for migrate_one_case using a stub review-packet path."""

    def test_migrates_clean_maladministration(self, tmp_path):
        from scripts.eval.migrate_balanced50_to_determination_schema import migrate_one_case

        # Write a stub packet
        packet_dir = tmp_path / "packets"
        packet_dir.mkdir()
        packet = packet_dir / "01-housing-ombudsman-202451564.review.md"
        packet.write_text(
            "## Manifest Strata\n"
            "- Outcome raw: maladministration\n"
            "- Outcome normalized: maladministration\n"
        )

        raw_row = {
            "case_id": "housing-ombudsman-202451564",
            "ground_truth_outcome": {
                "overall_winner": "tenant",
                "total_awarded_gbp": "500.00",
                "per_issue": [],
                "unapportioned_reason": "global compensation order",
            },
        }
        migrated, flags = migrate_one_case(raw_row, packet_dir)
        assert flags == []
        gto = migrated["ground_truth_outcome"]
        assert gto["determination"] == "maladministration"
        assert gto["amount_ordered_now_gbp"] == "500.00"
        assert gto["amount_previously_offered_gbp"] is None
        assert gto["amount_global_unapportioned_gbp"] is None
        assert gto["overall_winner_legacy"] == "tenant"

    def test_migrates_reasonable_redress_to_previously_offered(self, tmp_path):
        from scripts.eval.migrate_balanced50_to_determination_schema import migrate_one_case
        packet_dir = tmp_path / "packets"
        packet_dir.mkdir()
        packet = packet_dir / "01-housing-ombudsman-202xxx.review.md"
        packet.write_text(
            "## Manifest Strata\n"
            "- Outcome raw: reasonable redress\n"
            "- Outcome normalized: reasonable-redress\n"
        )
        raw_row = {
            "case_id": "housing-ombudsman-202xxx",
            "ground_truth_outcome": {
                "overall_winner": "landlord",
                "total_awarded_gbp": "750.00",
                "per_issue": [],
                "unapportioned_reason": "landlord prior offer ratified",
            },
        }
        migrated, flags = migrate_one_case(raw_row, packet_dir)
        assert flags == []
        gto = migrated["ground_truth_outcome"]
        assert gto["determination"] == "reasonable_redress"
        assert gto["amount_ordered_now_gbp"] is None
        assert gto["amount_previously_offered_gbp"] == "750.00"
        assert gto["overall_winner_legacy"] == "landlord"

    def test_flags_packet_not_found(self, tmp_path):
        from scripts.eval.migrate_balanced50_to_determination_schema import migrate_one_case
        packet_dir = tmp_path / "empty_packets"
        packet_dir.mkdir()
        raw_row = {
            "case_id": "housing-ombudsman-missing",
            "ground_truth_outcome": {
                "overall_winner": "tenant",
                "total_awarded_gbp": "0.00",
                "per_issue": [],
                "unapportioned_reason": "x",
            },
        }
        migrated, flags = migrate_one_case(raw_row, packet_dir)
        assert "packet_not_found" in flags
        # Row returned unchanged.
        assert "determination" not in migrated["ground_truth_outcome"]

    def test_flags_mixed_outcome_raw(self, tmp_path):
        from scripts.eval.migrate_balanced50_to_determination_schema import migrate_one_case
        packet_dir = tmp_path / "packets"
        packet_dir.mkdir()
        packet = packet_dir / "01-housing-ombudsman-mixed.review.md"
        packet.write_text(
            "## Manifest Strata\n"
            "- Outcome raw: no maladministration; maladministration; service failure; reasonable redress\n"
            "- Outcome normalized: maladministration\n"
        )
        raw_row = {
            "case_id": "housing-ombudsman-mixed",
            "ground_truth_outcome": {
                "overall_winner": "tenant",
                "total_awarded_gbp": "200.00",
                "per_issue": [],
                "unapportioned_reason": "x",
            },
        }
        migrated, flags = migrate_one_case(raw_row, packet_dir)
        assert any(f.startswith("mixed_outcome_raw:") for f in flags)
