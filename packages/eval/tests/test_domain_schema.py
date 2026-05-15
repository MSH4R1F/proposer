"""SHA-20 Phase 7 — tests for the GoldCase domain-field extensions.

These cover the new optional/defaulted fields added to
``packages/eval/schema.py`` (``domain_id``, ``forum``, ``matter_type``,
``train_test_split`` …) and the audit D3 split in
``eval.issue_alignment.eval_to_orchestrator``.
"""
from __future__ import annotations

import warnings

import pytest
from pydantic import ValidationError

from eval.issue_alignment import eval_to_orchestrator
from eval.schema import ClaimType, GoldCase
from eval.tests.conftest import gold_case_dict


class TestLegacyRowsStillParse:
    """Audit invariant: legacy ``housing_v1.jsonl`` rows must continue to
    validate when none of the SHA-20 Phase 7 fields are present."""

    def test_minimal_legacy_row_parses(self):
        gc = GoldCase.model_validate(gold_case_dict())
        assert gc.domain_id is None
        assert gc.forum is None
        assert gc.matter_type is None
        assert gc.train_test_split is None
        assert gc.target_source_id is None
        assert gc.excluded_source_ids == []
        assert gc.law_effective_date is None
        assert gc.corpus_version is None
        assert gc.negative_kind is None
        assert gc.expected_redactions == []

    def test_optional_fields_explicitly_omitted(self):
        d = gold_case_dict()
        # Make sure none of the new keys leak into a legacy fixture.
        for key in (
            "domain_id",
            "forum",
            "matter_type",
            "train_test_split",
            "target_source_id",
            "excluded_source_ids",
            "law_effective_date",
            "corpus_version",
        ):
            assert key not in d, f"legacy fixture must not include {key}"


class TestDepositMatterTypeValues:
    """Both ``deposit_deduction`` and ``deposit_non_protection`` must be
    accepted on a ``housing.deposit.v1`` row."""

    @pytest.mark.parametrize(
        "matter_type",
        ["deposit_deduction", "deposit_non_protection"],
    )
    def test_deposit_matter_types_accepted(self, matter_type):
        d = gold_case_dict(
            domain_id="housing.deposit.v1",
            matter_type=matter_type,
        )
        gc = GoldCase.model_validate(d)
        assert gc.domain_id == "housing.deposit.v1"
        assert gc.matter_type == matter_type


class TestIssueAlignmentMatterSplit:
    """Audit D3: deposit_deduction and deposit_non_protection map to
    different DisputeIssue branches."""

    def test_deposit_deduction_routes_to_damage_branch(self):
        out = eval_to_orchestrator(
            ClaimType.DEPOSIT_NON_PROTECTION, matter_type="deposit_deduction"
        )
        assert out.value == "damage"

    def test_deposit_non_protection_routes_to_penalty_branch(self):
        out = eval_to_orchestrator(
            ClaimType.DEPOSIT_NON_PROTECTION, matter_type="deposit_non_protection"
        )
        assert out.value == "deposit_protection"

    def test_missing_matter_type_emits_deprecation_and_keeps_legacy_default(self):
        """When ``matter_type`` is unset on a deposit row the WIP code
        emits a DeprecationWarning and falls back to the legacy
        ``deposit_protection`` mapping. We pin the actual behaviour rather
        than the docstring promise so the test is honest."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            out = eval_to_orchestrator(ClaimType.DEPOSIT_NON_PROTECTION)
        deprecation = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert deprecation, "expected DeprecationWarning when matter_type omitted"
        assert out.value == "deposit_protection"


class TestTrainTestSplit:
    """Audit: ``train_test_split`` is restricted to ``train | test | dev``."""

    @pytest.mark.parametrize("split", ["train", "test", "dev"])
    def test_accepts_known_splits(self, split):
        gc = GoldCase.model_validate(gold_case_dict(train_test_split=split))
        assert gc.train_test_split == split

    @pytest.mark.parametrize("bogus", ["holdout", "validation", "TRAIN", "", "prod"])
    def test_rejects_unknown_splits(self, bogus):
        with pytest.raises(ValidationError):
            GoldCase.model_validate(gold_case_dict(train_test_split=bogus))


class TestExcludedSourceIdsAndCorpusVersion:
    def test_excluded_source_ids_round_trips(self):
        gc = GoldCase.model_validate(
            gold_case_dict(
                target_source_id="src-001",
                excluded_source_ids=["src-002", "src-003"],
            )
        )
        assert gc.target_source_id == "src-001"
        assert gc.excluded_source_ids == ["src-002", "src-003"]

    def test_corpus_version_optional_string(self):
        gc = GoldCase.model_validate(
            gold_case_dict(corpus_version="legacy_2025_pre_sha20")
        )
        assert gc.corpus_version == "legacy_2025_pre_sha20"


class TestNegativeRowFields:
    """Negative-set rows expose ``negative_kind`` + ``expected_redactions``;
    these must round-trip without breaking legacy validation."""

    def test_pii_negative_row_round_trips(self):
        # SHA-144 (2026-05-14): when domain_id is in the employment family
        # the row must be shaped for that family — INV-2 needs claimant +
        # respondent_employer, INV-D5 needs a determination, INV-F1 rejects
        # housing claim types / winners. Construct the employment-shaped
        # fields explicitly here; the housing-shaped default
        # `gold_case_dict()` no longer round-trips under an employment
        # domain_id (and that's the whole point of INV-F1).
        gc = GoldCase.model_validate(
            gold_case_dict(
                domain_id="employment.unfair_dismissal.v1",
                forum="employment_tribunal",
                negative_kind="pii_leakage",
                expected_outcome="redact_all_identifiers",
                expected_redactions=["[ni_number]", "[payroll_id]"],
                disputed_amount_gbp=None,
                case_size="unknown",
                claim_types=["unfair_dismissal"],
                parties=[
                    {"role": "claimant", "represented": False},
                    {"role": "respondent_employer", "represented": True},
                ],
                claimed_amounts=[],
                ground_truth_outcome={
                    "overall_winner": "respondent",
                    "total_awarded_gbp": "0.00",
                    "per_issue": [],
                    "unapportioned_reason": "PII negative-set row: liability not modelled.",
                    "determination": "non_merits",
                },
            )
        )
        assert gc.negative_kind == "pii_leakage"
        assert gc.expected_outcome == "redact_all_identifiers"
        assert "[ni_number]" in gc.expected_redactions
        # And the cross-forum guard let it through because party roles and
        # winners are in the employment partition.
        assert gc.domain_id == "employment.unfair_dismissal.v1"
