"""Tests for the gold-case schema (packages/eval/schema.py)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError


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
