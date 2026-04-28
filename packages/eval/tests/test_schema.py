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
        from eval.schema import ClaimType
        assert {c.value for c in ClaimType} == {
            "cleaning",
            "damages",
            "deposit_non_protection",
            "disrepair",
            "end_of_tenancy",
        }

    def test_case_size_values(self):
        from eval.schema import CaseSize
        assert {c.value for c in CaseSize} == {"small", "large"}

    def test_party_role_values(self):
        from eval.schema import PartyRole
        assert {c.value for c in PartyRole} == {"tenant", "landlord", "agent"}

    def test_winner_values(self):
        from eval.schema import Winner
        assert {c.value for c in Winner} == {"tenant", "landlord", "split"}

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
        from eval.schema import ReasoningQuote
        q = ReasoningQuote(text="The deposit was not protected.", paragraph_ref="para 14")
        assert q.paragraph_ref == "para 14"

    def test_paragraph_ref_required(self):
        from eval.schema import ReasoningQuote
        with pytest.raises(ValidationError):
            ReasoningQuote(text="x", paragraph_ref=None)  # type: ignore[arg-type]

    def test_empty_text_rejected(self):
        from eval.schema import ReasoningQuote
        with pytest.raises(ValidationError):
            ReasoningQuote(text="", paragraph_ref="para 1")


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

    def test_unapportioned_bypasses_inv5_per_issue_match(self):
        # When unapportioned, per_issue is empty so INV-5 is vacuously satisfied
        from eval.schema import GoldCase
        case = _load_unapportioned()
        # claimed_amounts has issues that don't appear in per_issue (empty), should still validate
        gc = GoldCase.model_validate(case)
        assert len(gc.claimed_amounts) == 2
        assert gc.ground_truth_outcome.per_issue == []


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
        from eval.schema import Authority
        from datetime import date as _date
        a = Authority(
            name="Howard de Walden Estates Ltd v Aggio",
            court="UKSC",
            cited_date=_date(2008, 6, 25),
            paragraph_ref="para 12",
        )
        assert a.name.startswith("Howard")
        assert a.court == "UKSC"
        assert a.cited_date.year == 2008

    def test_optional_fields_default(self):
        from eval.schema import Authority
        from datetime import date as _date
        a = Authority(name="Anon v Anon", cited_date=_date(2021, 1, 1))
        assert a.court is None and a.paragraph_ref is None

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
                    "paragraph_ref": "para 12",
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
