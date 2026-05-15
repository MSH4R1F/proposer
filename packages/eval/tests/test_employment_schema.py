"""SHA-144 / SHA-65-0 — schema readiness for the employment vertical.

Tests the extensions to ``packages/eval/schema.py`` that let a
``GoldCase`` with ``domain_id`` in the employment family validate, while
keeping legacy housing rows working and refusing cross-forum coercion.

Covers:

* New enum values: ``ClaimType.UNFAIR_DISMISSAL``,
  ``PartyRole.CLAIMANT`` / ``RESPONDENT_EMPLOYER``,
  ``Winner.CLAIMANT`` / ``RESPONDENT``, and the forum-neutral
  ``Determination.{CLAIMANT_SUCCESS, RESPONDENT_SUCCESS,
  PARTIAL_SUCCESS, NON_MERITS}``.
* INV-2 (party roles) branches on domain family.
* Disputed-amount / claimed-amounts exemption covers ``employment.*``.
* INV-D5: employment rows require ``ground_truth_outcome.determination``.
* INV-F1: cross-forum coercion refused on every enum surface
  (party roles, claim types, overall winner, per-issue winner,
  determination, per-complaint determination, legacy winner).
* INV-F2: ET remedy fields refused on non-employment rows.
* ``_legacy_winner_for`` extended for the new determinations.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from eval.schema import (
    CaseSize,
    ClaimType,
    ComplaintFinding,
    Determination,
    GoldCase,
    GroundTruthOutcome,
    IssueOutcome,
    Party,
    PartyRole,
    Provenance,
    ReasoningQuote,
    RegionUK,
    SchemaVersion,
    Winner,
    _domain_family,
    _legacy_winner_for,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _employment_kwargs(**gto_overrides) -> dict:
    """Return a fresh, valid ET GoldCase kwargs dict.

    Defaults to an unapportioned outcome with
    ``determination=CLAIMANT_SUCCESS``, which is the canonical shape for
    an ET reserved judgment where the merits are decided but the remedy
    amount is captured via the optional remedy fields rather than the
    housing-style ``total_awarded_gbp`` apportionment. Tests can layer
    additional overrides via ``**gto_overrides``.
    """
    gto_kwargs = dict(
        overall_winner=Winner.CLAIMANT,
        total_awarded_gbp=Decimal("0"),
        per_issue=[],
        unapportioned_reason="ET reserved judgment: remedy deferred to remedy hearing.",
        determination=Determination.CLAIMANT_SUCCESS,
    )
    gto_kwargs.update(gto_overrides)
    return dict(
        schema_version=SchemaVersion.V1,
        case_id="et-unfair-dismissal-test-1",
        decision_date=date(2024, 4, 12),
        region=RegionUK.LONDON,
        case_size=CaseSize.UNKNOWN,
        disputed_amount_gbp=None,
        claim_types=[ClaimType.UNFAIR_DISMISSAL],
        source_pdf_sha256="0" * 64,
        parties=[
            Party(role=PartyRole.CLAIMANT, represented=False),
            Party(role=PartyRole.RESPONDENT_EMPLOYER, represented=True),
        ],
        facts=(
            "Claimant was dismissed on 7 January 2024 for alleged misconduct. "
            "The tribunal applied section 98 ERA 1996 and the band of "
            "reasonable responses test."
        ),
        evidence=[],
        evidence_unavailable_reason="Fixture: evidence not captured.",
        statutory_basis=[],
        statutory_basis_unavailable_reason="Fixture: statutes not captured.",
        claimed_amounts=[],
        ground_truth_outcome=GroundTruthOutcome(**gto_kwargs),
        key_reasoning_quotes=[
            ReasoningQuote(
                text="The dismissal was unfair within the meaning of ERA 1996.",
                provenance=Provenance(page=1, paragraph=1),
            ),
        ],
        domain_id="employment.et.unfair_dismissal.v1",
        forum="employment_tribunal",
        matter_type="unfair_dismissal",
    )


def _housing_legacy_kwargs(**case_overrides) -> dict:
    """Return a valid legacy-housing GoldCase kwargs dict (deposit deduction shape)."""
    base = dict(
        schema_version=SchemaVersion.V1,
        case_id="housing-deposit-test-1",
        decision_date=date(2023, 6, 15),
        region=RegionUK.LONDON,
        case_size=CaseSize.SMALL,
        disputed_amount_gbp=Decimal("400.00"),
        claim_types=[ClaimType.CLEANING],
        source_pdf_sha256="0" * 64,
        parties=[
            Party(role=PartyRole.TENANT, represented=False),
            Party(role=PartyRole.LANDLORD, represented=True),
        ],
        facts="Tenant occupied flat 2022-01-01 to 2023-05-31; landlord withheld 400 GBP citing cleaning.",
        evidence=[],
        evidence_unavailable_reason="Fixture: evidence not captured.",
        statutory_basis=[],
        statutory_basis_unavailable_reason="Fixture: statutes not captured.",
        claimed_amounts=[
            {"issue": "cleaning", "amount_gbp": "400.00", "by_party": "landlord"},
        ],
        ground_truth_outcome=GroundTruthOutcome(
            overall_winner=Winner.TENANT,
            total_awarded_gbp=Decimal("220.00"),
            per_issue=[
                IssueOutcome(
                    issue="cleaning",
                    winner=Winner.TENANT,
                    awarded_gbp=Decimal("220.00"),
                ),
            ],
        ),
        key_reasoning_quotes=[
            ReasoningQuote(
                text="Landlord adduced insufficient evidence.",
                provenance=Provenance(page=1, paragraph=1),
            ),
        ],
        domain_id="housing.deposit.v1",
    )
    base.update(case_overrides)
    return base


# ---------------------------------------------------------------------------
# Enum + family helpers
# ---------------------------------------------------------------------------


class TestDomainFamily:
    def test_housing_prefixes_recognised(self):
        for d in (
            "housing.deposit.v1",
            "housing.repairs_social.v1",
            "housing.property_chamber.rro.v1",
        ):
            assert _domain_family(d) == "housing"

    def test_employment_prefixes_recognised(self):
        for d in (
            "employment.unfair_dismissal.v1",  # legacy compat ID
            "employment.et.unfair_dismissal.v1",
            "employment.et.discrimination.v1",
        ):
            assert _domain_family(d) == "employment"

    def test_unknown_returns_none(self):
        assert _domain_family(None) is None
        assert _domain_family("") is None
        assert _domain_family("xyz.other.v1") is None


class TestLegacyWinnerForEmploymentDeterminations:
    @pytest.mark.parametrize(
        "determination, expected",
        [
            (Determination.CLAIMANT_SUCCESS, Winner.CLAIMANT),
            (Determination.RESPONDENT_SUCCESS, Winner.RESPONDENT),
            (Determination.PARTIAL_SUCCESS, Winner.SPLIT),
            (Determination.NON_MERITS, Winner.RESPONDENT),
        ],
    )
    def test_employment_determinations_map_correctly(self, determination, expected):
        assert _legacy_winner_for(determination) == expected


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestEmploymentGoldCaseValidates:
    def test_minimal_employment_row_validates(self):
        case = GoldCase(**_employment_kwargs())
        assert case.domain_id == "employment.et.unfair_dismissal.v1"
        assert case.claim_types == [ClaimType.UNFAIR_DISMISSAL]
        assert case.ground_truth_outcome.overall_winner == Winner.CLAIMANT
        assert case.ground_truth_outcome.determination == Determination.CLAIMANT_SUCCESS

    def test_employment_decision_dates_through_2026_accepted(self):
        # SHA-147 corpus reality (caught by Codex 2026-05-15): every
        # employment.et.unfair_dismissal.v1 decision in the scraped corpus
        # is dated 2023-03-23 to 2026-04-20. Without an entry in
        # _DOMAIN_MAX_DECISION_DATE the default 2024-12-31 cap rejects
        # them. Both the legacy compat ID and the namespaced ID get the
        # override.
        for domain_id in (
            "employment.unfair_dismissal.v1",
            "employment.et.unfair_dismissal.v1",
        ):
            kwargs = _employment_kwargs()
            kwargs["domain_id"] = domain_id
            kwargs["decision_date"] = date(2026, 4, 20)
            case = GoldCase(**kwargs)
            assert case.decision_date == date(2026, 4, 20)

    def test_employment_decision_dates_after_override_window_rejected(self):
        # The override is 2026-12-31, not "anything goes" — a 2027 row
        # still fails INV-1.
        kwargs = _employment_kwargs()
        kwargs["decision_date"] = date(2027, 1, 1)
        with pytest.raises(ValidationError, match="outside permitted"):
            GoldCase(**kwargs)

    def test_legacy_compat_domain_id_validates(self):
        # Spec §3.1 keeps `employment.unfair_dismissal.v1` as the
        # compatibility ID; scrapers in SHA-145 write that on every row.
        kwargs = _employment_kwargs()
        kwargs["domain_id"] = "employment.unfair_dismissal.v1"
        case = GoldCase(**kwargs)
        assert case.domain_id == "employment.unfair_dismissal.v1"

    def test_respondent_success_outcome_validates(self):
        kwargs = _employment_kwargs(
            overall_winner=Winner.RESPONDENT,
            determination=Determination.RESPONDENT_SUCCESS,
        )
        case = GoldCase(**kwargs)
        assert case.ground_truth_outcome.overall_winner == Winner.RESPONDENT

    def test_partial_success_outcome_validates(self):
        kwargs = _employment_kwargs(
            overall_winner=Winner.SPLIT,
            determination=Determination.PARTIAL_SUCCESS,
        )
        case = GoldCase(**kwargs)
        assert case.ground_truth_outcome.determination == Determination.PARTIAL_SUCCESS

    def test_non_merits_outcome_validates(self):
        # Non-merits rows live in negative sets — abstention test points.
        kwargs = _employment_kwargs(
            overall_winner=Winner.RESPONDENT,
            determination=Determination.NON_MERITS,
        )
        case = GoldCase(**kwargs)
        assert case.ground_truth_outcome.determination == Determination.NON_MERITS

    def test_remedy_fields_accepted(self):
        # Optional ET remedy fields are populated when the scraper extracts
        # an Acas-style award breakdown.
        kwargs = _employment_kwargs(
            basic_award_gbp=Decimal("3500.00"),
            compensatory_award_gbp=Decimal("12000.00"),
            deductions_pct=Decimal("25"),
            uplifts_pct=Decimal("10"),
            reinstatement_sought=True,
            reinstatement_granted=False,
            re_engagement_sought=False,
        )
        case = GoldCase(**kwargs)
        gto = case.ground_truth_outcome
        assert gto.basic_award_gbp == Decimal("3500.00")
        assert gto.compensatory_award_gbp == Decimal("12000.00")
        assert gto.deductions_pct == Decimal("25")
        assert gto.uplifts_pct == Decimal("10")
        assert gto.reinstatement_sought is True
        assert gto.reinstatement_granted is False
        assert gto.re_engagement_sought is False

    def test_overall_winner_legacy_uses_employment_partition(self):
        # The optional overall_winner_legacy can carry CLAIMANT/RESPONDENT
        # for ET rows, and the canonical mapping must agree.
        kwargs = _employment_kwargs(
            overall_winner=Winner.CLAIMANT,
            determination=Determination.CLAIMANT_SUCCESS,
            overall_winner_legacy=Winner.CLAIMANT,
        )
        case = GoldCase(**kwargs)
        assert case.ground_truth_outcome.overall_winner_legacy == Winner.CLAIMANT


class TestHousingRowsStillValidate:
    def test_legacy_housing_deposit_row(self):
        # A row with the schema's original (tenant/landlord) shape and a
        # housing.* domain_id continues to validate after the SHA-144
        # extension. No regression.
        case = GoldCase(**_housing_legacy_kwargs())
        assert case.domain_id == "housing.deposit.v1"
        assert case.ground_truth_outcome.overall_winner == Winner.TENANT


# ---------------------------------------------------------------------------
# INV-2 — party-role coverage branches by family
# ---------------------------------------------------------------------------


class TestPartyRoleCoverage:
    def test_employment_row_without_claimant_rejected(self):
        # GoldCase requires at least 2 parties; use two RESPONDENT_EMPLOYER
        # entries to satisfy that without introducing a CLAIMANT or a
        # housing role that would deflect to a different invariant.
        kwargs = _employment_kwargs()
        kwargs["parties"] = [
            Party(role=PartyRole.RESPONDENT_EMPLOYER, represented=True),
            Party(role=PartyRole.RESPONDENT_EMPLOYER, represented=False),
        ]
        with pytest.raises(ValidationError, match="claimant"):
            GoldCase(**kwargs)

    def test_employment_row_without_respondent_employer_rejected(self):
        kwargs = _employment_kwargs()
        kwargs["parties"] = [
            Party(role=PartyRole.CLAIMANT, represented=False),
            Party(role=PartyRole.CLAIMANT, represented=True),
        ]
        with pytest.raises(ValidationError, match="respondent_employer"):
            GoldCase(**kwargs)

    def test_housing_row_without_tenant_still_rejected(self):
        # INV-2 housing path is unchanged.
        kwargs = _housing_legacy_kwargs()
        kwargs["parties"] = [
            Party(role=PartyRole.LANDLORD, represented=True),
            Party(role=PartyRole.AGENT, represented=False),
        ]
        with pytest.raises(ValidationError, match="tenant"):
            GoldCase(**kwargs)


# ---------------------------------------------------------------------------
# INV-D5 — employment requires determination
# ---------------------------------------------------------------------------


class TestEmploymentDeterminationRequired:
    def test_employment_row_without_determination_rejected(self):
        # Build a GoldCase whose ground_truth_outcome has no determination
        # set. The validator on GroundTruthOutcome accepts this (housing
        # repairs_social.v1 has the same hole), so the rejection lands at
        # GoldCase._validate_invariants (INV-D5).
        kwargs = _employment_kwargs()
        kwargs["ground_truth_outcome"] = GroundTruthOutcome(
            overall_winner=Winner.CLAIMANT,
            total_awarded_gbp=Decimal("0"),
            per_issue=[],
            unapportioned_reason="ET row with no determination — should be rejected.",
        )
        with pytest.raises(ValidationError, match="INV-D5"):
            GoldCase(**kwargs)


# ---------------------------------------------------------------------------
# INV-F1 — cross-forum coercion guard
# ---------------------------------------------------------------------------


class TestInvariantF1HousingDomainRejectsEmploymentValues:
    """A housing.* domain_id must reject every employment enum value."""

    def test_employment_party_role_on_housing_rejected(self):
        # Keep tenant + landlord so INV-2 passes, then add a CLAIMANT —
        # forcing INV-F1 (cross-forum) to be the failing invariant rather
        # than INV-2 (missing tenant).
        kwargs = _housing_legacy_kwargs()
        kwargs["parties"] = [
            Party(role=PartyRole.TENANT, represented=False),
            Party(role=PartyRole.LANDLORD, represented=True),
            Party(role=PartyRole.CLAIMANT, represented=False),
        ]
        with pytest.raises(ValidationError, match="INV-F1"):
            GoldCase(**kwargs)

    def test_employment_claim_type_on_housing_rejected(self):
        kwargs = _housing_legacy_kwargs()
        kwargs["claim_types"] = [ClaimType.UNFAIR_DISMISSAL]
        with pytest.raises(ValidationError, match="INV-F1"):
            GoldCase(**kwargs)

    def test_employment_winner_on_housing_rejected(self):
        kwargs = _housing_legacy_kwargs()
        kwargs["ground_truth_outcome"] = GroundTruthOutcome(
            overall_winner=Winner.CLAIMANT,
            total_awarded_gbp=Decimal("220.00"),
            per_issue=[
                IssueOutcome(
                    issue="cleaning",
                    winner=Winner.CLAIMANT,
                    awarded_gbp=Decimal("220.00"),
                ),
            ],
        )
        with pytest.raises(ValidationError, match="INV-F1"):
            GoldCase(**kwargs)

    def test_employment_determination_on_housing_rejected(self):
        # Pair the housing row with `housing.repairs_social.v1` so the
        # determination requirement (INV-D4) doesn't short-circuit by
        # firing first. Then set an employment-family determination.
        from eval.tests.conftest import gold_case_dict
        d = gold_case_dict(
            domain_id="housing.repairs_social.v1",
            matter_type="repairs_disrepair",
            case_size="unknown",
            disputed_amount_gbp=None,
            claimed_amounts=[],
            claim_types=["disrepair"],
            ground_truth_outcome={
                "overall_winner": "tenant",
                "total_awarded_gbp": "0.00",
                "per_issue": [],
                "unapportioned_reason": "Test fixture.",
                "determination": "claimant_success",  # employment-family value
            },
        )
        with pytest.raises(ValidationError, match="INV-F1"):
            GoldCase.model_validate(d)


class TestInvariantF1EmploymentDomainRejectsHousingValues:
    """An employment.* domain_id must reject every housing enum value."""

    def test_housing_party_role_on_employment_rejected(self):
        kwargs = _employment_kwargs()
        kwargs["parties"] = [
            Party(role=PartyRole.TENANT, represented=False),
            Party(role=PartyRole.RESPONDENT_EMPLOYER, represented=True),
        ]
        with pytest.raises(ValidationError):
            # Either INV-2 (claimant missing) or INV-F1 (TENANT not in
            # employment family) fires. Both are correct rejections.
            GoldCase(**kwargs)

    def test_housing_claim_type_on_employment_rejected(self):
        kwargs = _employment_kwargs()
        kwargs["claim_types"] = [ClaimType.DISREPAIR]
        with pytest.raises(ValidationError, match="INV-F1"):
            GoldCase(**kwargs)

    def test_housing_winner_on_employment_rejected(self):
        kwargs = _employment_kwargs(
            overall_winner=Winner.TENANT,
            determination=Determination.CLAIMANT_SUCCESS,
        )
        with pytest.raises(ValidationError, match="INV-F1"):
            GoldCase(**kwargs)

    def test_housing_determination_on_employment_rejected(self):
        kwargs = _employment_kwargs(
            overall_winner=Winner.CLAIMANT,
            determination=Determination.MALADMINISTRATION,
        )
        # _legacy_winner_for(MALADMINISTRATION) == TENANT, so the
        # GroundTruthOutcome itself fails first when overall_winner_legacy
        # is set. We don't set it, so INV-F1 fires.
        with pytest.raises(ValidationError, match="INV-F1"):
            GoldCase(**kwargs)


# ---------------------------------------------------------------------------
# INV-F2 — ET remedy fields gated on employment family
# ---------------------------------------------------------------------------


class TestInvariantF2RemedyFieldsEmploymentOnly:
    @pytest.mark.parametrize(
        "field, value",
        [
            ("basic_award_gbp", Decimal("3500.00")),
            ("compensatory_award_gbp", Decimal("12000.00")),
            ("deductions_pct", Decimal("25")),
            ("uplifts_pct", Decimal("10")),
            ("reinstatement_sought", True),
            ("reinstatement_granted", False),
            ("re_engagement_sought", True),
            ("re_engagement_granted", False),
        ],
    )
    def test_remedy_field_on_housing_row_rejected(self, field, value):
        kwargs = _housing_legacy_kwargs()
        gto_kwargs = dict(
            overall_winner=Winner.TENANT,
            total_awarded_gbp=Decimal("220.00"),
            per_issue=[
                IssueOutcome(
                    issue="cleaning",
                    winner=Winner.TENANT,
                    awarded_gbp=Decimal("220.00"),
                ),
            ],
        )
        gto_kwargs[field] = value
        kwargs["ground_truth_outcome"] = GroundTruthOutcome(**gto_kwargs)
        with pytest.raises(ValidationError, match=r"INV-F2"):
            GoldCase(**kwargs)

    def test_remedy_field_on_employment_row_accepted(self):
        # Smoke check: the same field set that's rejected above MUST be
        # accepted on an employment-family row.
        kwargs = _employment_kwargs(
            basic_award_gbp=Decimal("3500.00"),
            compensatory_award_gbp=Decimal("12000.00"),
        )
        case = GoldCase(**kwargs)
        assert case.ground_truth_outcome.basic_award_gbp == Decimal("3500.00")
