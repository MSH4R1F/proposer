"""Tests for the gold-case schema (packages/eval/schema.py)."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_minimal() -> dict:
    return json.loads((FIXTURES_DIR / "gold_case_minimal.json").read_text())


def _load_unapportioned() -> dict:
    return json.loads((FIXTURES_DIR / "gold_case_unapportioned.json").read_text())


class TestEnums:
    def test_claim_type_values(self):
        # SHA-144 (2026-05-14): enum extended additively with the SHA-65
        # employment vertical. Housing values unchanged.
        from eval.schema import ClaimType
        assert {c.value for c in ClaimType} == {
            "cleaning",
            "damages",
            "deposit_non_protection",
            "disrepair",
            "end_of_tenancy",
            "unfair_dismissal",
        }

    def test_case_size_values(self):
        from eval.schema import CaseSize
        assert {c.value for c in CaseSize} == {"small", "large", "unknown"}

    def test_party_role_values(self):
        from eval.schema import PartyRole
        assert {c.value for c in PartyRole} == {
            "tenant",
            "landlord",
            "agent",
            "claimant",
            "respondent_employer",
        }

    def test_winner_values(self):
        from eval.schema import Winner
        assert {c.value for c in Winner} == {
            "tenant",
            "landlord",
            "claimant",
            "respondent",
            "split",
        }

    def test_schema_version_v1_only(self):
        from eval.schema import SchemaVersion
        assert {c.value for c in SchemaVersion} == {"v1"}


class TestParty:
    def test_valid_party(self):
        from eval.schema import Party, PartyRole
        p = Party(role=PartyRole.TENANT, represented=False)
        assert p.role == PartyRole.TENANT and p.represented is False

    def test_unknown_role_rejected(self):
        from eval.schema import Party
        with pytest.raises(ValidationError):
            Party(role="judge", represented=False)


class TestClaimedAmount:
    def test_valid(self):
        from eval.schema import ClaimedAmount, PartyRole
        c = ClaimedAmount(
            issue="cleaning",
            amount_gbp=Decimal("250.00"),
            by_party=PartyRole.LANDLORD,
        )
        assert c.amount_gbp == Decimal("250.00")

    def test_negative_amount_rejected(self):
        from eval.schema import ClaimedAmount, PartyRole
        with pytest.raises(ValidationError):
            ClaimedAmount(
                issue="cleaning",
                amount_gbp=Decimal("-1"),
                by_party=PartyRole.LANDLORD,
            )


class TestReasoningQuote:
    def test_valid(self):
        from eval.schema import Provenance, ReasoningQuote
        q = ReasoningQuote(
            text="The deposit was not protected.",
            provenance=Provenance(page=1, paragraph=14),
        )
        assert q.provenance.paragraph == 14

    def test_provenance_required(self):
        from eval.schema import ReasoningQuote
        with pytest.raises(ValidationError):
            ReasoningQuote(text="x")  # provenance required

    def test_empty_text_rejected(self):
        from eval.schema import Provenance, ReasoningQuote
        with pytest.raises(ValidationError):
            ReasoningQuote(text="", provenance=Provenance(page=1, paragraph=1))


class TestGroundTruthOutcome:
    def test_per_issue_must_be_non_empty(self):
        from eval.schema import GroundTruthOutcome, Winner
        with pytest.raises(ValidationError):
            GroundTruthOutcome(
                overall_winner=Winner.TENANT,
                total_awarded_gbp=Decimal("0"),
                per_issue=[],
            )

    def test_total_must_match_sum_of_per_issue(self):
        from eval.schema import GroundTruthOutcome, IssueOutcome, Winner
        with pytest.raises(ValidationError):
            GroundTruthOutcome(
                overall_winner=Winner.TENANT,
                total_awarded_gbp=Decimal("100"),
                per_issue=[
                    IssueOutcome(
                        issue="cleaning",
                        winner=Winner.TENANT,
                        awarded_gbp=Decimal("60"),
                    ),
                    IssueOutcome(
                        issue="damages",
                        winner=Winner.TENANT,
                        awarded_gbp=Decimal("50"),
                    ),
                ],
            )

    def test_total_matches_sum_ok(self):
        from eval.schema import GroundTruthOutcome, IssueOutcome, Winner
        gto = GroundTruthOutcome(
            overall_winner=Winner.TENANT,
            total_awarded_gbp=Decimal("110"),
            per_issue=[
                IssueOutcome(
                    issue="cleaning",
                    winner=Winner.TENANT,
                    awarded_gbp=Decimal("60"),
                ),
                IssueOutcome(
                    issue="damages",
                    winner=Winner.TENANT,
                    awarded_gbp=Decimal("50"),
                ),
            ],
        )
        assert gto.total_awarded_gbp == Decimal("110")


class TestGoldCaseRoundTrip:
    def test_minimal_fixture_validates(self):
        from eval.schema import GoldCase
        gc = GoldCase.model_validate(_load_minimal())
        assert gc.case_id == "SYNTH-2023-0001"

    def test_round_trip_json_stable(self):
        from eval.schema import GoldCase
        gc = GoldCase.model_validate(_load_minimal())
        again = GoldCase.model_validate(json.loads(gc.model_dump_json()))
        assert again == gc


class TestGoldCaseInvariants:
    def _base(self) -> dict:
        return _load_minimal()

    def test_inv1_decision_date_too_early(self):
        from eval.schema import GoldCase
        bad = self._base() | {"decision_date": "2018-12-31"}
        with pytest.raises(ValidationError, match="decision_date"):
            GoldCase.model_validate(bad)

    def test_inv1_decision_date_too_late(self):
        from eval.schema import GoldCase
        bad = self._base() | {"decision_date": "2025-01-01"}
        with pytest.raises(ValidationError, match="decision_date"):
            GoldCase.model_validate(bad)

    def test_inv1_repairs_social_domain_allows_2026_seed_window(self):
        from eval.schema import GoldCase
        ok = self._base() | {
            "decision_date": "2026-01-08",
            "domain_id": "housing.repairs_social.v1",
            "ground_truth_outcome": {
                "overall_winner": "tenant",
                "total_awarded_gbp": "220.00",
                "per_issue": [
                    {"issue": "carpet_cleaning", "winner": "tenant", "awarded_gbp": "220.00"}
                ],
                "determination": "maladministration",
            },
        }
        gc = GoldCase.model_validate(ok)
        assert gc.decision_date.isoformat() == "2026-01-08"

    def test_inv2_requires_tenant_and_landlord(self):
        from eval.schema import GoldCase
        bad = self._base() | {"parties": [{"role": "tenant", "represented": False}]}
        with pytest.raises(ValidationError, match="tenant.*landlord|parties"):
            GoldCase.model_validate(bad)

    def test_inv3_ocr_confidence_above_unit_interval(self):
        from eval.schema import GoldCase
        bad = self._base() | {"ocr_confidence": 1.5}
        with pytest.raises(ValidationError, match="ocr_confidence"):
            GoldCase.model_validate(bad)

    def test_inv3_ocr_confidence_below_unit_interval(self):
        from eval.schema import GoldCase
        bad = self._base() | {"ocr_confidence": -0.01}
        with pytest.raises(ValidationError, match="ocr_confidence"):
            GoldCase.model_validate(bad)

    def test_inv3_ocr_confidence_none_permitted(self):
        from eval.schema import GoldCase
        ok = self._base() | {"ocr_confidence": None}
        gc = GoldCase.model_validate(ok)
        assert gc.ocr_confidence is None

    def test_inv4_pdf_sha256_format(self):
        from eval.schema import GoldCase
        bad = self._base() | {"source_pdf_sha256": "ZZZ"}
        with pytest.raises(ValidationError, match="source_pdf_sha256"):
            GoldCase.model_validate(bad)

    def test_inv5_per_issue_must_match_claimed(self):
        from eval.schema import GoldCase
        case = self._base()
        case["ground_truth_outcome"]["per_issue"][0]["issue"] = "ghost_issue"
        with pytest.raises(ValidationError, match="ghost_issue"):
            GoldCase.model_validate(case)

    def test_inv7_case_size_inconsistent_small(self):
        from eval.schema import GoldCase
        # disputed_amount = 400 GBP -> should be small; declaring large is wrong
        bad = self._base() | {"case_size": "large"}
        with pytest.raises(ValidationError, match="case_size"):
            GoldCase.model_validate(bad)

    def test_inv7_case_size_inconsistent_large(self):
        from eval.schema import GoldCase
        # disputed_amount > 1500 GBP must yield case_size=large
        case = self._base() | {"disputed_amount_gbp": "1600.00"}
        with pytest.raises(ValidationError, match="case_size"):
            GoldCase.model_validate(case)

    def test_inv7_case_size_boundary_exactly_1500_is_small(self):
        from eval.schema import GoldCase
        case = self._base() | {"disputed_amount_gbp": "1500.00", "case_size": "small"}
        gc = GoldCase.model_validate(case)
        assert gc.case_size.value == "small"


class TestDisputedAmount:
    def _base(self) -> dict:
        return _load_minimal()

    def test_disputed_amount_required(self):
        from eval.schema import GoldCase
        case = self._base()
        del case["disputed_amount_gbp"]
        with pytest.raises(ValidationError, match="disputed_amount_gbp"):
            GoldCase.model_validate(case)

    def test_disputed_amount_negative_rejected(self):
        from eval.schema import GoldCase
        case = self._base() | {"disputed_amount_gbp": "-1"}
        with pytest.raises(ValidationError, match="disputed_amount_gbp"):
            GoldCase.model_validate(case)

    def test_inv7_independent_of_claimed_amounts_sum(self):
        from eval.schema import GoldCase
        # Mirror the dispute: tenant claims 400 back, landlord claims 400 from deposit.
        # Naive sum would say 800 GBP and label it small; disputed_amount_gbp=400 is canonical.
        case = self._base()
        case["claimed_amounts"] = [
            {"issue": "carpet_cleaning", "amount_gbp": "400.00", "by_party": "landlord"},
            {"issue": "carpet_cleaning", "amount_gbp": "400.00", "by_party": "tenant"},
        ]
        case["disputed_amount_gbp"] = "400.00"
        case["case_size"] = "small"
        gc = GoldCase.model_validate(case)
        assert gc.case_size.value == "small"

    def test_repairs_social_allows_unknown_pre_decision_amounts(self):
        from eval.schema import GoldCase
        case = self._base()
        case.update(
            {
                "domain_id": "housing.repairs_social.v1",
                "forum": "housing_ombudsman",
                "retrieval_namespace_id": "housing_repairs_social_v1",
                "source_publisher": "housing_ombudsman",
                "source_kind": "ombudsman_determination",
                "matter_type": "repairs_disrepair",
                "case_size": "unknown",
                "disputed_amount_gbp": None,
                "claimed_amounts": [],
                "ground_truth_outcome": {
                    "overall_winner": "tenant",
                    "total_awarded_gbp": "575.00",
                    "per_issue": [],
                    "unapportioned_reason": (
                        "Housing Ombudsman determination records a global "
                        "compensation order without a per-issue award split."
                    ),
                    "determination": "maladministration",
                    "amount_ordered_now_gbp": "575.00",
                },
            }
        )

        gc = GoldCase.model_validate(case)

        assert gc.disputed_amount_gbp is None
        assert gc.claimed_amounts == []
        assert gc.case_size.value == "unknown"

    def test_unknown_amount_requires_unknown_case_size(self):
        from eval.schema import GoldCase
        case = self._base()
        case.update(
            {
                "domain_id": "housing.repairs_social.v1",
                "case_size": "small",
                "disputed_amount_gbp": None,
                "claimed_amounts": [],
                "ground_truth_outcome": {
                    "overall_winner": "tenant",
                    "total_awarded_gbp": "575.00",
                    "per_issue": [],
                    "unapportioned_reason": "Global compensation order.",
                    "determination": "maladministration",
                    "amount_ordered_now_gbp": "575.00",
                },
            }
        )

        with pytest.raises(ValidationError, match="unknown disputed_amount_gbp"):
            GoldCase.model_validate(case)


class TestUnapportionedOutcome:
    def test_unapportioned_fixture_validates(self):
        from eval.schema import GoldCase
        gc = GoldCase.model_validate(_load_unapportioned())
        assert gc.ground_truth_outcome.unapportioned_reason is not None
        assert gc.ground_truth_outcome.per_issue == []
        assert gc.ground_truth_outcome.total_awarded_gbp == Decimal("1100.00")

    def test_unapportioned_round_trip(self):
        from eval.schema import GoldCase
        gc = GoldCase.model_validate(_load_unapportioned())
        again = GoldCase.model_validate(json.loads(gc.model_dump_json()))
        assert again == gc

    def test_apportioned_path_still_requires_sum_match(self):
        # Regression: when unapportioned_reason is None, INV-6 still applies
        from eval.schema import GroundTruthOutcome, IssueOutcome, Winner
        with pytest.raises(ValidationError):
            GroundTruthOutcome(
                overall_winner=Winner.TENANT,
                total_awarded_gbp=Decimal("100"),
                per_issue=[
                    IssueOutcome(
                        issue="cleaning",
                        winner=Winner.TENANT,
                        awarded_gbp=Decimal("60"),
                    ),
                ],
            )

    def test_apportioned_path_requires_non_empty_per_issue(self):
        # When unapportioned_reason is None, per_issue must be >=1
        from eval.schema import GroundTruthOutcome, Winner
        with pytest.raises(ValidationError):
            GroundTruthOutcome(
                overall_winner=Winner.TENANT,
                total_awarded_gbp=Decimal("0"),
                per_issue=[],
            )

    def test_unapportioned_with_per_issue_rejected(self):
        # If you provide an unapportioned_reason you should NOT also provide per_issue
        from eval.schema import GroundTruthOutcome, IssueOutcome, Winner
        with pytest.raises(ValidationError, match="unapportioned"):
            GroundTruthOutcome(
                overall_winner=Winner.SPLIT,
                total_awarded_gbp=Decimal("100"),
                per_issue=[
                    IssueOutcome(
                        issue="cleaning",
                        winner=Winner.TENANT,
                        awarded_gbp=Decimal("60"),
                    ),
                ],
                unapportioned_reason="Judge declined to break it down.",
            )

    def test_unapportioned_reason_empty_string_rejected(self):
        from eval.schema import GroundTruthOutcome, Winner
        with pytest.raises(ValidationError, match="unapportioned_reason"):
            GroundTruthOutcome(
                overall_winner=Winner.SPLIT,
                total_awarded_gbp=Decimal("100"),
                per_issue=[],
                unapportioned_reason=" ",
            )

    def test_unapportioned_bypasses_inv5_per_issue_match(self):
        # When unapportioned, per_issue is empty so INV-5 is vacuously satisfied
        from eval.schema import GoldCase
        case = _load_unapportioned()
        # claimed_amounts has issues that don't appear in per_issue (empty), should still validate
        gc = GoldCase.model_validate(case)
        assert len(gc.claimed_amounts) == 2
        assert gc.ground_truth_outcome.per_issue == []


class TestInv9OverallWinnerConsistency:
    """INV-9: overall_winner must agree with the per_issue.winner aggregate.

    Skipped on the unapportioned path — there is no per_issue to aggregate.
    """

    def _base(self) -> dict:
        return _load_minimal()

    def _with_per_issue(self, base: dict, issues: list[dict]) -> dict:
        case = base.copy()
        case["claimed_amounts"] = [
            {"issue": i["issue"], "amount_gbp": "100.00", "by_party": "landlord"}
            for i in issues
        ]
        case["ground_truth_outcome"] = {
            "overall_winner": case["ground_truth_outcome"]["overall_winner"],
            "total_awarded_gbp": str(sum(int(i["awarded_gbp"]) for i in issues)) + ".00",
            "per_issue": issues,
        }
        return case

    def test_inv9_all_tenant_implies_overall_tenant_ok(self):
        from eval.schema import GoldCase
        case = self._with_per_issue(
            self._base() | {"ground_truth_outcome": {"overall_winner": "tenant"}},
            [
                {"issue": "a", "winner": "tenant", "awarded_gbp": "0"},
                {"issue": "b", "winner": "tenant", "awarded_gbp": "0"},
            ],
        )
        case["disputed_amount_gbp"] = "200.00"
        gc = GoldCase.model_validate(case)
        assert gc.ground_truth_outcome.overall_winner.value == "tenant"

    def test_inv9_all_tenant_but_overall_landlord_rejected(self):
        from eval.schema import GoldCase
        case = self._with_per_issue(
            self._base() | {"ground_truth_outcome": {"overall_winner": "landlord"}},
            [
                {"issue": "a", "winner": "tenant", "awarded_gbp": "0"},
                {"issue": "b", "winner": "tenant", "awarded_gbp": "0"},
            ],
        )
        case["disputed_amount_gbp"] = "200.00"
        with pytest.raises(ValidationError, match="overall_winner"):
            GoldCase.model_validate(case)

    def test_inv9_mixed_tenant_landlord_implies_split_ok(self):
        from eval.schema import GoldCase
        case = self._with_per_issue(
            self._base() | {"ground_truth_outcome": {"overall_winner": "split"}},
            [
                {"issue": "a", "winner": "tenant", "awarded_gbp": "60"},
                {"issue": "b", "winner": "landlord", "awarded_gbp": "60"},
            ],
        )
        case["disputed_amount_gbp"] = "200.00"
        gc = GoldCase.model_validate(case)
        assert gc.ground_truth_outcome.overall_winner.value == "split"

    def test_inv9_mixed_tenant_landlord_but_overall_tenant_rejected(self):
        from eval.schema import GoldCase
        case = self._with_per_issue(
            self._base() | {"ground_truth_outcome": {"overall_winner": "tenant"}},
            [
                {"issue": "a", "winner": "tenant", "awarded_gbp": "60"},
                {"issue": "b", "winner": "landlord", "awarded_gbp": "60"},
            ],
        )
        case["disputed_amount_gbp"] = "200.00"
        with pytest.raises(ValidationError, match="overall_winner"):
            GoldCase.model_validate(case)

    def test_inv9_all_split_implies_overall_split_ok(self):
        from eval.schema import GoldCase
        case = self._with_per_issue(
            self._base() | {"ground_truth_outcome": {"overall_winner": "split"}},
            [
                {"issue": "a", "winner": "split", "awarded_gbp": "60"},
                {"issue": "b", "winner": "split", "awarded_gbp": "60"},
            ],
        )
        case["disputed_amount_gbp"] = "200.00"
        gc = GoldCase.model_validate(case)
        assert gc.ground_truth_outcome.overall_winner.value == "split"

    def test_inv9_skipped_on_unapportioned_path(self):
        # In the unapportioned fixture, overall_winner=split with per_issue=[].
        # INV-9 is skipped — annotator asserts overall_winner directly.
        from eval.schema import GoldCase
        gc = GoldCase.model_validate(_load_unapportioned())
        assert gc.ground_truth_outcome.overall_winner.value == "split"
        assert gc.ground_truth_outcome.per_issue == []


class TestRegionUK:
    def _base(self) -> dict:
        return _load_minimal()

    def test_region_is_enum(self):
        from eval.schema import GoldCase, RegionUK
        case = self._base() | {"region": "london"}
        gc = GoldCase.model_validate(case)
        assert gc.region == RegionUK.LONDON

    def test_region_source_preserved(self):
        from eval.schema import GoldCase
        case = self._base() | {"region": "london", "region_source": "Greater London"}
        gc = GoldCase.model_validate(case)
        assert gc.region_source == "Greater London"

    def test_region_unknown_value_rejected(self):
        from eval.schema import GoldCase
        case = self._base() | {"region": "atlantis"}
        with pytest.raises(ValidationError, match="region"):
            GoldCase.model_validate(case)

    def test_region_uk_has_12_values(self):
        from eval.schema import RegionUK
        assert len(list(RegionUK)) == 12

    def test_region_uk_values_match_uk_standard_regions(self):
        from eval.schema import RegionUK
        expected = {
            "london", "south_east", "south_west", "east_of_england",
            "east_midlands", "west_midlands", "north_west", "north_east",
            "yorkshire_and_humber", "wales", "scotland", "northern_ireland",
        }
        assert {r.value for r in RegionUK} == expected


class TestInv10EvidenceStatutoryAvailability:
    def _base(self) -> dict:
        return _load_minimal()

    def test_empty_evidence_without_reason_rejected(self):
        from eval.schema import GoldCase
        case = self._base() | {"evidence": []}
        with pytest.raises(ValidationError, match="evidence"):
            GoldCase.model_validate(case)

    def test_empty_evidence_with_reason_ok(self):
        from eval.schema import GoldCase
        case = self._base() | {
            "evidence": [],
            "evidence_unavailable_reason": "Tribunal heard the case on submissions only; no evidence catalogue published.",
        }
        gc = GoldCase.model_validate(case)
        assert gc.evidence == []
        assert gc.evidence_unavailable_reason is not None

    def test_empty_statutory_basis_without_reason_rejected(self):
        from eval.schema import GoldCase
        case = self._base() | {"statutory_basis": []}
        with pytest.raises(ValidationError, match="statutory_basis"):
            GoldCase.model_validate(case)

    def test_empty_statutory_basis_with_reason_ok(self):
        from eval.schema import GoldCase
        case = self._base() | {
            "statutory_basis": [],
            "statutory_basis_unavailable_reason": "Decision turned on common-law principles only.",
        }
        gc = GoldCase.model_validate(case)
        assert gc.statutory_basis == []

    def test_empty_evidence_reason_must_be_non_empty(self):
        from eval.schema import GoldCase
        case = self._base() | {
            "evidence": [],
            "evidence_unavailable_reason": " ",
        }
        with pytest.raises(ValidationError, match="evidence_unavailable_reason"):
            GoldCase.model_validate(case)

    def test_empty_statutory_basis_reason_must_be_non_empty(self):
        from eval.schema import GoldCase
        case = self._base() | {
            "statutory_basis": [],
            "statutory_basis_unavailable_reason": "",
        }
        with pytest.raises(ValidationError, match="statutory_basis_unavailable_reason"):
            GoldCase.model_validate(case)

    def test_non_empty_evidence_with_reason_rejected(self):
        from eval.schema import GoldCase
        case = self._base() | {
            "evidence_unavailable_reason": "Should not be set when evidence is non-empty",
        }
        with pytest.raises(ValidationError, match="evidence"):
            GoldCase.model_validate(case)

    def test_non_empty_statute_with_reason_rejected(self):
        from eval.schema import GoldCase
        case = self._base() | {
            "statutory_basis_unavailable_reason": "Should not be set when statutory_basis is non-empty",
        }
        with pytest.raises(ValidationError, match="statutory_basis"):
            GoldCase.model_validate(case)


class TestProvenance:
    def test_valid_provenance(self):
        from eval.schema import Provenance
        p = Provenance(page=1, paragraph=14)
        assert p.page == 1 and p.paragraph == 14
        assert p.text_span is None

    def test_text_span_optional(self):
        from eval.schema import Provenance
        p = Provenance(page=2, paragraph=3, text_span=(120, 240))
        assert p.text_span == (120, 240)

    def test_text_span_rejects_negative_values(self):
        from eval.schema import Provenance
        with pytest.raises(ValidationError, match="text_span"):
            Provenance(page=2, paragraph=3, text_span=(-1, 10))

    def test_text_span_rejects_reversed_range(self):
        from eval.schema import Provenance
        with pytest.raises(ValidationError, match="text_span"):
            Provenance(page=2, paragraph=3, text_span=(240, 120))

    def test_page_min_1(self):
        from eval.schema import Provenance
        with pytest.raises(ValidationError):
            Provenance(page=0, paragraph=1)

    def test_paragraph_min_1(self):
        from eval.schema import Provenance
        with pytest.raises(ValidationError):
            Provenance(page=1, paragraph=0)


class TestProvenanceMigration:
    """Verify Evidence, StatutoryReference, Authority, ReasoningQuote all
    use Provenance instead of bare paragraph_ref."""

    def test_evidence_uses_provenance(self):
        from eval.schema import Evidence, Provenance
        e = Evidence(
            kind="invoice",
            description="Cleaning invoice",
            provenance=Provenance(page=1, paragraph=7),
        )
        assert e.provenance.paragraph == 7

    def test_evidence_provenance_optional(self):
        from eval.schema import Evidence
        Evidence(kind="invoice", description="Cleaning invoice")  # no provenance is fine

    def test_reasoning_quote_requires_provenance(self):
        from eval.schema import ReasoningQuote, Provenance
        rq = ReasoningQuote(text="Quote.", provenance=Provenance(page=1, paragraph=1))
        assert rq.provenance.page == 1

    def test_reasoning_quote_provenance_required(self):
        from eval.schema import ReasoningQuote
        with pytest.raises(ValidationError):
            ReasoningQuote(text="Quote.")  # provenance required

    def test_authority_uses_provenance(self):
        from eval.schema import Authority, Provenance
        from datetime import date as _date
        a = Authority(
            name="Howard v Aggio",
            cited_date=_date(2008, 6, 25),
            provenance=Provenance(page=2, paragraph=12),
        )
        assert a.provenance.page == 2

    def test_statutory_reference_uses_provenance(self):
        from eval.schema import StatutoryReference, Provenance
        s = StatutoryReference(
            statute="Housing Act 2004",
            section="s.213",
            provenance=Provenance(page=1, paragraph=12),
        )
        assert s.provenance.paragraph == 12


class TestClaimTypesIsList:
    def _base(self) -> dict:
        return _load_minimal()

    def test_claim_types_is_a_list_field(self):
        from eval.schema import GoldCase, ClaimType
        gc = GoldCase.model_validate(self._base())
        assert gc.claim_types == [ClaimType.CLEANING]

    def test_claim_types_accepts_multiple(self):
        from eval.schema import GoldCase, ClaimType
        case = self._base() | {"claim_types": ["cleaning", "damages"]}
        gc = GoldCase.model_validate(case)
        assert set(gc.claim_types) == {ClaimType.CLEANING, ClaimType.DAMAGES}

    def test_claim_types_rejects_duplicates(self):
        from eval.schema import GoldCase
        case = self._base() | {"claim_types": ["cleaning", "cleaning"]}
        with pytest.raises(ValidationError, match="claim_types"):
            GoldCase.model_validate(case)

    def test_claim_types_rejects_empty_list(self):
        from eval.schema import GoldCase
        case = self._base() | {"claim_types": []}
        with pytest.raises(ValidationError, match="claim_types"):
            GoldCase.model_validate(case)

    def test_claim_types_rejects_unknown_value(self):
        from eval.schema import GoldCase
        case = self._base() | {"claim_types": ["arson"]}
        with pytest.raises(ValidationError, match="claim_types"):
            GoldCase.model_validate(case)


class TestAuthority:
    def test_valid_authority(self):
        from eval.schema import Authority, Provenance
        from datetime import date as _date
        a = Authority(
            name="Howard de Walden Estates Ltd v Aggio",
            court="UKSC",
            cited_date=_date(2008, 6, 25),
            provenance=Provenance(page=2, paragraph=12),
        )
        assert a.name.startswith("Howard")
        assert a.court == "UKSC"
        assert a.cited_date.year == 2008
        assert a.provenance.paragraph == 12

    def test_legacy_paragraph_ref_rejected(self):
        from eval.schema import Authority
        from datetime import date as _date
        with pytest.raises(ValidationError, match="paragraph_ref|Extra"):
            Authority(
                name="Howard de Walden Estates Ltd v Aggio",
                cited_date=_date(2008, 6, 25),
                paragraph_ref="para 12",
            )

    def test_optional_fields_default(self):
        from eval.schema import Authority
        from datetime import date as _date
        a = Authority(name="Anon v Anon", cited_date=_date(2021, 1, 1))
        assert a.court is None and a.provenance is None

    def test_empty_name_rejected(self):
        from eval.schema import Authority
        from datetime import date as _date
        with pytest.raises(ValidationError):
            Authority(name="", cited_date=_date(2021, 1, 1))


class TestGoldCaseAuthorities:
    def _base(self) -> dict:
        return _load_minimal()

    def test_default_cited_authorities_is_empty_list(self):
        from eval.schema import GoldCase
        gc = GoldCase.model_validate(self._base())
        assert gc.cited_authorities == []

    def test_accepts_cited_authorities(self):
        from eval.schema import GoldCase
        case = self._base() | {
            "cited_authorities": [
                {
                    "name": "Howard de Walden Estates Ltd v Aggio",
                    "court": "UKSC",
                    "cited_date": "2008-06-25",
                    "provenance": {"page": 2, "paragraph": 12},
                }
            ]
        }
        gc = GoldCase.model_validate(case)
        assert len(gc.cited_authorities) == 1
        assert gc.cited_authorities[0].name.startswith("Howard")

    def test_round_trip_with_authorities(self):
        from eval.schema import GoldCase
        case = self._base() | {
            "cited_authorities": [
                {"name": "Anon v Anon", "cited_date": "2020-03-15"}
            ]
        }
        gc = GoldCase.model_validate(case)
        again = GoldCase.model_validate(json.loads(gc.model_dump_json()))
        assert again == gc
