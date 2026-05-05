"""Tests for eval.case_file_adapter — GoldCase → CaseFile reconstruction.

The reconstructor builds a *pre-decision* CaseFile from a *post-decision*
GoldCase. Several gold-only fields are deliberately dropped so the
prediction engine cannot cheat by reading the verdict:

- ground_truth_outcome
- key_reasoning_quotes
- statutory_basis (tribunal's cited statutes)
- cited_authorities (tribunal's cited cases)
- decision_date

The reconstruction is lossy but deterministic. Annotator-vocabulary
claim types map to orchestrator's DisputeIssue via eval.issue_alignment;
unmappables (disrepair, end_of_tenancy) fall back to DisputeIssue.OTHER
and are tracked in the produced CaseFile's metadata for the alignment
report.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from eval.case_file_adapter import (
    LossyReconstruction,
    gold_case_to_case_file,
)
from eval.dataset import load
from eval.schema import ClaimedAmount, GoldCase, PartyRole

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def synthetic_gold_cases():
    return load("synthetic_corpus_10", base_dir=FIXTURES, strict=True).cases


@pytest.fixture
def first_gold_case(synthetic_gold_cases) -> GoldCase:
    return synthetic_gold_cases[0]


# ---------- Identity preservation ----------


class TestIdentityPreserved:
    def test_case_id_carries_across(self, first_gold_case):
        out = gold_case_to_case_file(first_gold_case)
        assert out.case_file.case_id == first_gold_case.case_id

    def test_dispute_amount_set_from_disputed_amount_gbp(self, first_gold_case):
        out = gold_case_to_case_file(first_gold_case)
        assert out.case_file.dispute_amount == float(
            first_gold_case.disputed_amount_gbp
        )

    def test_user_role_defaults_to_tenant(self, first_gold_case):
        """Most production users are tenants. Reviewer can override at
        call site if reconstructing from a landlord-perspective record."""
        out = gold_case_to_case_file(first_gold_case)
        assert out.case_file.user_role.value == "tenant"


class TestPartiesPopulated:
    def test_tenant_and_landlord_present(self, first_gold_case):
        out = gold_case_to_case_file(first_gold_case)
        cf = out.case_file
        # Names are placeholder ("Tenant", "Landlord") since gold doesn't
        # carry party names — privacy.
        assert cf.tenant_name is not None
        assert cf.landlord_name is not None


class TestIssueMapping:
    def test_known_claim_types_map_to_dispute_issues(self, synthetic_gold_cases):
        # SYN-CLEANING-2020-001 has claim_types=["cleaning"]
        case = next(g for g in synthetic_gold_cases if g.case_id.startswith("SYN-CLEANING"))
        out = gold_case_to_case_file(case)
        issue_values = [i.value for i in out.case_file.issues]
        assert "cleaning" in issue_values

    def test_disrepair_falls_back_to_other_and_is_logged(
        self, synthetic_gold_cases
    ):
        case = next(g for g in synthetic_gold_cases if g.case_id.startswith("SYN-DISREPAIR"))
        out = gold_case_to_case_file(case)
        issue_values = [i.value for i in out.case_file.issues]
        # "disrepair" has no DisputeIssue equivalent → OTHER
        assert "other" in issue_values
        # The reconstruction tracks unmappable claim types so the runner
        # can write an alignment report.
        assert "disrepair" in out.unmapped_claim_types

    def test_ombudsman_disrepair_maps_to_repairs_issue(self, synthetic_gold_cases):
        case = next(g for g in synthetic_gold_cases if g.case_id.startswith("SYN-DISREPAIR"))
        case = case.model_copy(
            update={
                "domain_id": "housing.repairs_social.v1",
                "matter_type": "repairs_damp_mould",
                "forum": "housing_ombudsman",
                "source_publisher": "housing_ombudsman",
                "source_kind": "ombudsman_determination",
                "retrieval_namespace_id": "housing_repairs_social_v1",
                "target_source_id": "202399999",
            }
        )
        out = gold_case_to_case_file(case)
        issue_values = [i.value for i in out.case_file.issues]
        assert "repairs_damp_mould" in issue_values
        assert "disrepair" not in out.unmapped_claim_types

    def test_ombudsman_domain_fields_are_top_level_on_case_file(
        self, synthetic_gold_cases
    ):
        case = next(g for g in synthetic_gold_cases if g.case_id.startswith("SYN-DISREPAIR"))
        case = case.model_copy(
            update={
                "domain_id": "housing.repairs_social.v1",
                "matter_type": "repairs_damp_mould",
                "forum": "housing_ombudsman",
                "source_publisher": "housing_ombudsman",
                "source_kind": "ombudsman_determination",
                "retrieval_namespace_id": "housing_repairs_social_v1",
                "target_source_id": "202399999",
            }
        )

        out = gold_case_to_case_file(case)

        assert out.case_file.domain_id == "housing.repairs_social.v1"
        assert out.case_file.matter_types == ["repairs_damp_mould"]
        assert out.case_file.routing_confidence == 1.0

    def test_end_of_tenancy_also_falls_back(self, synthetic_gold_cases):
        case = next(g for g in synthetic_gold_cases if g.case_id.startswith("SYN-EOT"))
        out = gold_case_to_case_file(case)
        assert "end_of_tenancy" in out.unmapped_claim_types

    def test_unambiguous_claimed_issue_label_map_recorded(self, first_gold_case):
        out = gold_case_to_case_file(first_gold_case)
        assert out.gold_issue_labels_by_claim_type == {"cleaning": "primary_issue"}

    def test_ambiguous_claimed_issue_label_map_left_empty(self, synthetic_gold_cases):
        case = next(g for g in synthetic_gold_cases if g.case_id.startswith("SYN-MULTI"))
        out = gold_case_to_case_file(case)
        assert out.gold_issue_labels_by_claim_type == {}


class TestNarrativePopulated:
    def test_facts_become_tenant_narrative(self, first_gold_case):
        out = gold_case_to_case_file(first_gold_case)
        # By default user_role=TENANT → facts go into tenant_narrative
        assert out.case_file.tenant_narrative == first_gold_case.facts


class TestDeliberateDrops:
    """Engine must not see the verdict. These fields are intentionally
    dropped from the reconstructed CaseFile."""

    def test_no_outcome_in_metadata(self, first_gold_case):
        out = gold_case_to_case_file(first_gold_case)
        # The verdict must not leak into any user-visible CaseFile field.
        for value in out.case_file.metadata.values():
            assert "tenant_win" not in str(value).lower()
            assert "landlord_win" not in str(value).lower()

    def test_decision_date_not_in_tenancy_or_property(self, first_gold_case):
        out = gold_case_to_case_file(first_gold_case)
        # The tribunal's decision date isn't a pre-decision artifact.
        # Tenancy.end_date is allowed to be None (we don't know it from gold).
        assert out.case_file.tenancy.end_date is None or (
            out.case_file.tenancy.end_date != first_gold_case.decision_date
        )

    def test_returned_object_records_lossy_drops(self, first_gold_case):
        """The wrapper carries provenance metadata so the runner can log
        what was dropped per case (statutory_basis count, authority count,
        unmappable issues, etc.)."""
        out = gold_case_to_case_file(first_gold_case)
        assert isinstance(out, LossyReconstruction)
        # statutory_basis_count is captured even when zero/empty.
        assert out.statutory_basis_count >= 0
        assert out.cited_authorities_count >= 0


class TestEvidencePopulated:
    def test_evidence_items_carry_across(self, first_gold_case):
        out = gold_case_to_case_file(first_gold_case)
        # Synthetic cases ship with at least one evidence item; the
        # reconstructor maps each into an EvidenceItem.
        if first_gold_case.evidence:
            assert len(out.case_file.evidence) == len(first_gold_case.evidence)

    def test_evidence_descriptions_preserved(self, first_gold_case):
        out = gold_case_to_case_file(first_gold_case)
        if first_gold_case.evidence:
            descs_in = {e.description for e in first_gold_case.evidence}
            descs_out = {e.description for e in out.case_file.evidence}
            assert descs_in == descs_out


class TestClaimedAmountsSplitByParty:
    def test_tenant_claims_and_landlord_claims_split(self, first_gold_case):
        out = gold_case_to_case_file(first_gold_case)
        cf = out.case_file
        # Sum of tenant + landlord claim amounts equals total claimed amounts
        # in the gold case.
        gold_total = sum(c.amount_gbp for c in first_gold_case.claimed_amounts)
        cf_total = Decimal(0)
        for c in cf.tenant_claims:
            cf_total += Decimal(str(c.amount))
        for c in cf.landlord_claims:
            cf_total += Decimal(str(c.amount))
        assert cf_total == gold_total

    def test_ombudsman_compensation_claim_attaches_to_repairs_issue(
        self, synthetic_gold_cases
    ):
        case = next(g for g in synthetic_gold_cases if g.case_id.startswith("SYN-DISREPAIR"))
        case = case.model_copy(
            update={
                "domain_id": "housing.repairs_social.v1",
                "matter_type": "repairs_damp_mould",
                "forum": "housing_ombudsman",
                "source_publisher": "housing_ombudsman",
                "source_kind": "ombudsman_determination",
                "retrieval_namespace_id": "housing_repairs_social_v1",
                "target_source_id": "202399999",
                "claimed_amounts": [
                    ClaimedAmount(
                        issue="ombudsman_compensation",
                        amount_gbp=Decimal("575.00"),
                        by_party=PartyRole.TENANT,
                    )
                ],
            }
        )

        out = gold_case_to_case_file(case)

        assert out.case_file.tenant_claims[0].issue.value == "repairs_damp_mould"
        assert (
            "Pre-decision complaint facts"
            in out.case_file.tenant_claims[0].description
        )
        assert case.facts[:80] in out.case_file.tenant_claims[0].description

    def test_ombudsman_generated_final_award_amounts_are_omitted(
        self, synthetic_gold_cases
    ):
        case = next(
            g for g in synthetic_gold_cases if g.case_id.startswith("SYN-DISREPAIR")
        )
        payload = case.model_dump(mode="json")
        payload.update(
            {
                "domain_id": "housing.repairs_social.v1",
                "matter_type": "repairs_damp_mould",
                "forum": "housing_ombudsman",
                "source_publisher": "housing_ombudsman",
                "source_kind": "ombudsman_determination",
                "retrieval_namespace_id": "housing_repairs_social_v1",
                "target_source_id": "202399999",
                "case_size": "small",
                "disputed_amount_gbp": "575.00",
                "claimed_amounts": [
                    {
                        "issue": "ombudsman_compensation",
                        "amount_gbp": "575.00",
                        "by_party": "tenant",
                    }
                ],
                "ground_truth_outcome": {
                    "overall_winner": "tenant",
                    "total_awarded_gbp": "575.00",
                    "per_issue": [],
                    "unapportioned_reason": (
                        "Housing Ombudsman determination made a global "
                        "compensation order without apportioning the final "
                        "total across housing_v1 issue categories."
                    ),
                },
            }
        )
        generated_ombudsman_gold = GoldCase.model_validate(payload)

        out = gold_case_to_case_file(generated_ombudsman_gold)

        assert out.case_file.dispute_amount is None
        assert out.case_file.tenant_claims == []
        assert out.case_file.landlord_claims == []
        assert "575" not in out.case_file.model_dump_json()
        assert out.gold_issue_labels_by_claim_type == {}
        assert out.case_file.metadata["omitted_outcome_derived_amount_fields"] == [
            "claimed_amounts[issue=ombudsman_compensation|by_party=tenant].amount_gbp",
            "disputed_amount_gbp",
        ]


class TestRoundTripAllSyntheticCases:
    """Smoke: every synthetic case reconstructs without errors."""

    def test_all_ten_cases_reconstruct(self, synthetic_gold_cases):
        for g in synthetic_gold_cases:
            out = gold_case_to_case_file(g)
            assert out.case_file.case_id == g.case_id
