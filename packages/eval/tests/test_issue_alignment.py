"""Tests for eval.issue_alignment — bridge between ClaimType (eval) and
DisputeIssue (orchestrator).

The two enums diverged: eval is annotator-facing categories of *claims*
made in tribunal decisions; DisputeIssue is intake/UI categories of
*issues* the user reports. They overlap heavily but not perfectly:

- damages ↔ damage (spelling)
- deposit_non_protection ↔ deposit_protection (eval names the breach,
  orchestrator names the issue area; semantically same dispute)
- disrepair (eval) maps only for Housing Ombudsman repairs matter types
- end_of_tenancy (eval) — no clean DisputeIssue equivalent

The Phase 5b live runner needs both directions: forward to construct a
CaseFile from a GoldCase, inverse to normalise predicted-issue strings
back to gold vocabulary so the metrics see a single namespace.
"""
from __future__ import annotations

import pytest

from eval.issue_alignment import (
    UnmappableIssue,
    eval_to_orchestrator,
    orchestrator_to_eval,
)
from eval.schema import ClaimType


def _orch_dispute_issue(value: str):
    from llm_orchestrator.models.case_file import DisputeIssue

    return DisputeIssue(value)


class TestEvalToOrchestrator:
    def test_cleaning_round_trips(self):
        out = eval_to_orchestrator(ClaimType.CLEANING)
        assert out.value == "cleaning"

    def test_damages_maps_to_singular(self):
        """eval uses plural ('damages'), orchestrator uses singular
        ('damage'). Documented in module docstring."""
        out = eval_to_orchestrator(ClaimType.DAMAGES)
        assert out.value == "damage"

    def test_deposit_non_protection_maps_to_protection(self):
        """eval names the breach (non_protection), orchestrator names the
        issue area (protection). Semantically the same dispute."""
        out = eval_to_orchestrator(ClaimType.DEPOSIT_NON_PROTECTION)
        assert out.value == "deposit_protection"

    def test_disrepair_without_repairs_matter_type_is_unmappable(self):
        """Avoid pretending deposit disrepair has a clean production issue."""
        with pytest.raises(UnmappableIssue, match="disrepair"):
            eval_to_orchestrator(ClaimType.DISREPAIR)

    def test_disrepair_maps_to_repairs_disrepair_for_ombudsman_rows(self):
        out = eval_to_orchestrator(
            ClaimType.DISREPAIR, matter_type="repairs_disrepair"
        )
        assert out.value == "repairs_disrepair"

    def test_disrepair_maps_to_damp_mould_for_ombudsman_rows(self):
        out = eval_to_orchestrator(
            ClaimType.DISREPAIR, matter_type="repairs_damp_mould"
        )
        assert out.value == "repairs_damp_mould"

    def test_end_of_tenancy_is_unmappable(self):
        with pytest.raises(UnmappableIssue, match="end_of_tenancy"):
            eval_to_orchestrator(ClaimType.END_OF_TENANCY)

    def test_string_input_accepted(self):
        out = eval_to_orchestrator("cleaning")
        assert out.value == "cleaning"

    def test_unknown_string_raises_unmappable(self):
        with pytest.raises(UnmappableIssue, match="totally_made_up"):
            eval_to_orchestrator("totally_made_up")


class TestOrchestratorToEval:
    def test_cleaning_round_trips(self):
        out = orchestrator_to_eval(_orch_dispute_issue("cleaning"))
        assert out is ClaimType.CLEANING

    def test_damage_maps_to_damages(self):
        out = orchestrator_to_eval(_orch_dispute_issue("damage"))
        assert out is ClaimType.DAMAGES

    def test_deposit_protection_maps_to_non_protection(self):
        out = orchestrator_to_eval(_orch_dispute_issue("deposit_protection"))
        assert out is ClaimType.DEPOSIT_NON_PROTECTION

    def test_repairs_disrepair_maps_to_eval_disrepair(self):
        out = orchestrator_to_eval(_orch_dispute_issue("repairs_disrepair"))
        assert out is ClaimType.DISREPAIR

    def test_repairs_damp_mould_maps_to_eval_disrepair(self):
        out = orchestrator_to_eval(_orch_dispute_issue("repairs_damp_mould"))
        assert out is ClaimType.DISREPAIR

    def test_orch_only_value_is_unmappable(self):
        """garden, keys, redecoration etc. exist only on the orchestrator
        side — there is no eval ClaimType for them. Surface explicitly so
        the runner can drop the prediction (it cannot be scored against
        any gold issue anyway)."""
        with pytest.raises(UnmappableIssue, match="garden"):
            orchestrator_to_eval(_orch_dispute_issue("garden"))

    def test_string_input_accepted(self):
        out = orchestrator_to_eval("cleaning")
        assert out is ClaimType.CLEANING

    def test_unknown_orch_value_raises_unmappable(self):
        with pytest.raises(UnmappableIssue, match="not_a_real_issue"):
            orchestrator_to_eval("not_a_real_issue")


class TestRoundTripCleanPairs:
    """Every eval ClaimType that has a clean orch equivalent must round-trip
    back to itself. Catches drift if an enum value changes."""

    @pytest.mark.parametrize(
        "claim_type",
        [
            ClaimType.CLEANING,
            ClaimType.DAMAGES,
            ClaimType.DEPOSIT_NON_PROTECTION,
        ],
    )
    def test_eval_to_orch_to_eval_round_trips(self, claim_type):
        forward = eval_to_orchestrator(claim_type)
        back = orchestrator_to_eval(forward)
        assert back is claim_type
