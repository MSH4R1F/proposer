"""Tests for the Phase 8 auto-grounder.

Covers every per-field check function with a positive and negative case,
plus a smoke test that aggregates two grounded paths and one ungrounded
through ``ground(...)`` and verifies the pass rate.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from eval.auto_label.grounder import (
    GROUNDER_VERSION,
    GroundingDeps,
    GroundingResult,
    check_amount_sanity,
    check_authority,
    check_date_sanity,
    check_facts_leakage,
    check_invariants,
    check_label_basis,
    check_outcome_basis,
    check_quote,
    check_real_gold_audit,
    check_statute,
    ground,
)
from eval.auto_label.lookups.authorities import InMemoryAuthorityLookup
from eval.auto_label.lookups.statutes import InMemoryStatuteLookup
from eval.auto_label.span_match import MatchStrategy
from eval.schema import (
    Authority,
    ClaimedAmount,
    IssueOutcome,
    LabelerModel,
    LabelingProvenance,
    PartyRole,
    Provenance,
    ReasoningQuote,
    StatutoryReference,
    Winner,
)


def test_grounder_version_pinned() -> None:
    """Bump rule documented in grounder.py docstring."""
    assert GROUNDER_VERSION == "1.0.0"


def _quote(text: str, page: int = 1, paragraph: int = 1, span: tuple[int, int] | None = None) -> ReasoningQuote:
    return ReasoningQuote(
        text=text,
        provenance=Provenance(page=page, paragraph=paragraph, text_span=span),
    )


def _auth(name: str, cited: date) -> Authority:
    return Authority(name=name, cited_date=cited)


def _stat(statute: str, section: str) -> StatutoryReference:
    return StatutoryReference(statute=statute, section=section)


def _ca(issue: str, amount: str, by: PartyRole = PartyRole.LANDLORD) -> ClaimedAmount:
    return ClaimedAmount(issue=issue, amount_gbp=Decimal(amount), by_party=by)


def _io(issue: str, winner: Winner, awarded: str) -> IssueOutcome:
    return IssueOutcome(issue=issue, winner=winner, awarded_gbp=Decimal(awarded))


# ---------------------------------------------------------------------------
# check_quote
# ---------------------------------------------------------------------------


class TestCheckQuote:
    def test_positive_canonical_exact(self) -> None:
        page_text = {1: "Hello, the landlord adduced no evidence today."}
        case = {
            "key_reasoning_quotes": [
                _quote(
                    "the landlord adduced no evidence",
                    page=1,
                    span=(7, 39),
                )
            ]
        }
        rows = check_quote(case, page_text)
        assert len(rows) == 1
        path, verdict, reason = rows[0]
        assert path == "key_reasoning_quotes[0]"
        assert verdict == "GROUNDED"
        assert reason == MatchStrategy.CANONICAL_EXACT.value

    def test_negative_quote_not_in_window(self) -> None:
        page_text = {1: "We accept the tenant's account fully."}
        case = {
            "key_reasoning_quotes": [
                _quote(
                    "the landlord adduced no evidence",
                    page=1,
                    span=(0, 12),
                )
            ]
        }
        rows = check_quote(case, page_text)
        assert len(rows) == 1
        path, verdict, reason = rows[0]
        assert verdict == "UNGROUNDED"
        assert "not found" in reason.lower()

    def test_missing_text_span_ungrounds(self) -> None:
        case = {
            "key_reasoning_quotes": [
                ReasoningQuote(text="x", provenance=Provenance(page=1, paragraph=1))
            ]
        }
        rows = check_quote(case, {1: "x"})
        assert rows[0][1] == "UNGROUNDED"


# ---------------------------------------------------------------------------
# check_authority
# ---------------------------------------------------------------------------


class TestCheckAuthority:
    def test_positive_known(self) -> None:
        lookup = InMemoryAuthorityLookup(
            known_pairs=[("Howard de Walden v Aggio", date(2008, 6, 26))]
        )
        case = {"cited_authorities": [_auth("Howard de Walden v Aggio", date(2008, 6, 26))]}
        rows = check_authority(case, lookup)
        assert len(rows) == 1
        assert rows[0][1] == "GROUNDED"

    def test_negative_unknown(self) -> None:
        lookup = InMemoryAuthorityLookup()
        case = {"cited_authorities": [_auth("Made-up v Imaginary", date(2020, 1, 1))]}
        rows = check_authority(case, lookup)
        assert rows[0][1] == "UNGROUNDED"
        assert "unknown" in rows[0][2].lower()

    def test_negative_ambiguous(self) -> None:
        lookup = InMemoryAuthorityLookup(
            ambiguous_pairs=[("Smith v Jones", date(2010, 5, 1))]
        )
        case = {"cited_authorities": [_auth("Smith v Jones", date(2010, 5, 1))]}
        rows = check_authority(case, lookup)
        assert rows[0][1] == "UNGROUNDED"
        assert "ambiguous" in rows[0][2].lower()


# ---------------------------------------------------------------------------
# check_statute
# ---------------------------------------------------------------------------


class TestCheckStatute:
    def test_positive_known(self) -> None:
        lookup = InMemoryStatuteLookup(known_pairs=[("Housing Act 2004", "s.213")])
        case = {"statutory_basis": [_stat("Housing Act 2004", "s.213")]}
        rows = check_statute(case, lookup)
        assert rows[0][1] == "GROUNDED"

    def test_negative_unknown(self) -> None:
        lookup = InMemoryStatuteLookup()
        case = {"statutory_basis": [_stat("Made-up Act 9999", "s.1")]}
        rows = check_statute(case, lookup)
        assert rows[0][1] == "UNGROUNDED"


# ---------------------------------------------------------------------------
# check_outcome_basis
# ---------------------------------------------------------------------------


class TestCheckOutcomeBasis:
    def test_positive_all_paths_have_provenance(self) -> None:
        io = _io("carpet", Winner.TENANT, "100")
        case = {
            "ground_truth_outcome": {
                "overall_winner": Winner.TENANT,
                "total_awarded_gbp": Decimal("100"),
                "per_issue": [io],
            },
            "_field_provenance": {
                "ground_truth_outcome.overall_winner": [Provenance(page=1, paragraph=1)],
                "ground_truth_outcome.total_awarded_gbp": [Provenance(page=1, paragraph=2)],
                "ground_truth_outcome.per_issue[issue=carpet].winner": [Provenance(page=1, paragraph=3)],
                "ground_truth_outcome.per_issue[issue=carpet].awarded_gbp": [Provenance(page=1, paragraph=4)],
            },
        }
        rows = check_outcome_basis(case)
        assert all(r[1] == "GROUNDED" for r in rows)
        assert len(rows) == 4

    def test_negative_missing_provenance(self) -> None:
        case = {
            "ground_truth_outcome": {
                "overall_winner": Winner.TENANT,
                "total_awarded_gbp": Decimal("100"),
                "per_issue": [_io("x", Winner.TENANT, "100")],
            },
        }
        rows = check_outcome_basis(case)
        assert all(r[1] == "UNGROUNDED" for r in rows)
        assert len(rows) == 4

    def test_unapportioned_path_evaluated(self) -> None:
        case = {
            "ground_truth_outcome": {
                "overall_winner": Winner.TENANT,
                "total_awarded_gbp": Decimal("100"),
                "per_issue": [],
                "unapportioned_reason": "tribunal gave a global figure",
            },
            "_field_provenance": {
                "ground_truth_outcome.overall_winner": [Provenance(page=1, paragraph=1)],
                "ground_truth_outcome.total_awarded_gbp": [Provenance(page=1, paragraph=2)],
                "ground_truth_outcome.unapportioned_reason": [Provenance(page=1, paragraph=3)],
            },
        }
        rows = check_outcome_basis(case)
        assert all(r[1] == "GROUNDED" for r in rows)
        assert any(r[0] == "ground_truth_outcome.unapportioned_reason" for r in rows)


# ---------------------------------------------------------------------------
# check_label_basis
# ---------------------------------------------------------------------------


class TestCheckLabelBasis:
    def test_positive(self) -> None:
        ca = _ca("carpet", "200")
        case = {
            "claim_types": ["cleaning"],
            "matter_type": "deposit_deduction",
            "disputed_amount_gbp": Decimal("200"),
            "claimed_amounts": [ca],
            "_field_provenance": {
                "claim_types": [Provenance(page=1, paragraph=1)],
                "matter_type": [Provenance(page=1, paragraph=1)],
                "disputed_amount_gbp": [Provenance(page=1, paragraph=2)],
                "claimed_amounts[issue=carpet|by_party=landlord].amount_gbp": [
                    Provenance(page=1, paragraph=3)
                ],
            },
        }
        rows = check_label_basis(case)
        assert rows
        assert all(r[1] == "GROUNDED" for r in rows)

    def test_negative(self) -> None:
        case = {
            "claim_types": ["cleaning"],
            "matter_type": "deposit_deduction",
            "disputed_amount_gbp": Decimal("200"),
            "claimed_amounts": [_ca("carpet", "200")],
        }
        rows = check_label_basis(case)
        assert rows
        assert all(r[1] == "UNGROUNDED" for r in rows)


# ---------------------------------------------------------------------------
# check_facts_leakage
# ---------------------------------------------------------------------------


class TestCheckFactsLeakage:
    def test_positive_clean_facts(self) -> None:
        case = {
            "facts": "The tenant moved out on 2023-05-31 and the landlord retained part of the deposit.",
            "_field_provenance": {
                "facts": [Provenance(page=1, paragraph=2)],
            },
        }
        page_sections = {(1, 2): "pre_decision_record"}
        rows = check_facts_leakage(case, page_text={}, page_sections=page_sections)
        assert rows == [("facts", "GROUNDED", "no leakage detected")]

    def test_negative_phrase_leakage(self) -> None:
        case = {
            "facts": "The tribunal finds the deposit was wrongly retained.",
            "_field_provenance": {
                "facts": [Provenance(page=1, paragraph=2)],
            },
        }
        page_sections = {(1, 2): "pre_decision_record"}
        rows = check_facts_leakage(case, page_text={}, page_sections=page_sections)
        assert rows[0][1] == "UNGROUNDED"
        assert "leakage" in rows[0][2].lower()


# ---------------------------------------------------------------------------
# check_date_sanity
# ---------------------------------------------------------------------------


class TestCheckDateSanity:
    def test_positive(self) -> None:
        case = {
            "decision_date": date(2023, 6, 15),
            "cited_authorities": [_auth("Older v Case", date(2008, 1, 1))],
        }
        rows = check_date_sanity(case)
        assert all(r[1] == "GROUNDED" for r in rows)

    def test_negative_authority_post_decision(self) -> None:
        case = {
            "decision_date": date(2023, 6, 15),
            "cited_authorities": [_auth("Future v Case", date(2024, 1, 1))],
        }
        rows = check_date_sanity(case)
        assert any(
            r[1] == "UNGROUNDED" and "cited_date" in r[0]
            for r in rows
        )

    def test_negative_decision_date_missing(self) -> None:
        rows = check_date_sanity({})
        assert rows[0] == ("decision_date", "UNGROUNDED", "decision_date is required")


# ---------------------------------------------------------------------------
# check_amount_sanity
# ---------------------------------------------------------------------------


class TestCheckAmountSanity:
    def test_positive_apportioned(self) -> None:
        case = {
            "ground_truth_outcome": {
                "overall_winner": Winner.TENANT,
                "total_awarded_gbp": Decimal("300"),
                "per_issue": [
                    _io("carpet", Winner.TENANT, "100"),
                    _io("paint", Winner.TENANT, "200"),
                ],
            },
            "disputed_amount_gbp": Decimal("500"),
            "claimed_amounts": [
                _ca("carpet", "300"),
                _ca("paint", "200"),
            ],
        }
        rows = check_amount_sanity(case)
        assert all(r[1] == "GROUNDED" for r in rows)

    def test_negative_per_issue_sum_mismatch(self) -> None:
        case = {
            "ground_truth_outcome": {
                "overall_winner": Winner.TENANT,
                "total_awarded_gbp": Decimal("999"),
                "per_issue": [_io("carpet", Winner.TENANT, "100")],
            },
        }
        rows = check_amount_sanity(case)
        assert any(r[1] == "UNGROUNDED" and "sum" in r[2].lower() for r in rows)

    def test_negative_disputed_below_claimed(self) -> None:
        case = {
            "disputed_amount_gbp": Decimal("100"),
            "claimed_amounts": [_ca("carpet", "500")],
        }
        rows = check_amount_sanity(case)
        assert any(
            r[0] == "disputed_amount_gbp" and r[1] == "UNGROUNDED"
            for r in rows
        )

    def test_unapportioned_with_per_issue_is_invalid(self) -> None:
        case = {
            "ground_truth_outcome": {
                "overall_winner": Winner.TENANT,
                "total_awarded_gbp": Decimal("100"),
                "per_issue": [_io("x", Winner.TENANT, "100")],
                "unapportioned_reason": "tribunal said so",
            },
        }
        rows = check_amount_sanity(case)
        assert any(r[1] == "UNGROUNDED" for r in rows)


# ---------------------------------------------------------------------------
# check_invariants
# ---------------------------------------------------------------------------


class TestCheckInvariants:
    def test_positive_minimal_case_validates(self) -> None:
        rows = check_invariants({})
        assert rows == [("__invariants__", "GROUNDED", "GoldCase round-trip succeeded")]

    def test_negative_invariant_violation(self) -> None:
        case = {"decision_date": date(2018, 1, 1)}
        rows = check_invariants(case)
        assert rows[0][1] == "UNGROUNDED"
        assert "invariant" in rows[0][2].lower() or "decision_date" in rows[0][2].lower()


# ---------------------------------------------------------------------------
# check_real_gold_audit
# ---------------------------------------------------------------------------


_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_PDF_SHA = "a" * 64
_OCR_SHA = "b" * 64


def _full_gold_case_dict() -> dict:
    """Mirror the helper from test_auto_label_append_gate.py."""
    base = json.loads((_FIXTURES_DIR / "gold_case_minimal.json").read_text())
    base["source_pdf_sha256"] = _PDF_SHA
    base["domain_id"] = "housing.deposit.v1"
    base["forum"] = "ftt_pc"
    base["retrieval_namespace_id"] = "housing.deposit.v1"
    base["target_source_id"] = "src-housing-deposit-2023-0001"
    base["corpus_version"] = "housing_v1@2026-05-02"
    base["source_publisher"] = "ftt"
    base["source_kind"] = "tribunal_decision"
    base["source_license"] = "OGL-3.0"
    base["matter_type"] = "deposit_deduction"

    from eval.auto_label.append_gate import MANDATORY_REVIEW_FIELDS

    paths = set(MANDATORY_REVIEW_FIELDS)
    for io in base["ground_truth_outcome"]["per_issue"]:
        paths.add(f"ground_truth_outcome.per_issue[issue={io['issue']}].winner")
        paths.add(f"ground_truth_outcome.per_issue[issue={io['issue']}].awarded_gbp")
    fp = [
        {
            "field_path": p,
            "source": "human_mandatory_review",
            "source_spans": [{"page": 1, "paragraph": 2}],
            "reviewer_rationale": "test",
        }
        for p in sorted(paths)
    ]
    base["labeling_provenance"] = LabelingProvenance(
        run_id="run-grounder-test",
        labeled_at=datetime(2026, 5, 2, 14, 30, tzinfo=timezone.utc),
        labeler_models=[
            LabelerModel(provider="anthropic", model="claude-sonnet-4-20250514"),
            LabelerModel(provider="openai", model="gpt-5.5"),
        ],
        source_pdf_sha256=_PDF_SHA,
        ocr_text_sha256=_OCR_SHA,
        prompt_template_hash="t" * 16,
        gold_schema_hash="s" * 16,
        corpus_manifest_hash="c" * 16,
        canonicalizer_version="1.0.0",
        grounder_version=GROUNDER_VERSION,
        audit_seed=42,
        adjudicated_fields=[],
        inter_model_agreement_rate=0.92,
        grounding_pass_rate=0.88,
        audit_flip_rate=0.04,
        mandatory_review_flip_rate=0.10,
        field_provenance=fp,  # type: ignore[arg-type]
    ).model_dump(mode="json")
    return base


def _write_artifact(tmp_path: Path) -> Path:
    artifact = {
        "source_pdf_sha256": _PDF_SHA,
        "ocr_text_sha256": _OCR_SHA,
    }
    p = tmp_path / "case_artifact.json"
    p.write_text(json.dumps(artifact))
    return p


class TestCheckRealGoldAudit:
    def test_positive_appendable(self, tmp_path: Path) -> None:
        case = _full_gold_case_dict()
        artifact = _write_artifact(tmp_path)
        rows = check_real_gold_audit(case, artifact)
        assert rows == [("__append_gate__", "GROUNDED", "append gate accepted")]

    def test_negative_append_gate_refuses(self, tmp_path: Path) -> None:
        case = _full_gold_case_dict()
        case["target_source_id"] = None
        artifact = _write_artifact(tmp_path)
        rows = check_real_gold_audit(case, artifact)
        assert rows[0][1] == "UNGROUNDED"
        assert "append gate refused" in rows[0][2].lower()


# ---------------------------------------------------------------------------
# Top-level ground(...) smoke
# ---------------------------------------------------------------------------


class TestGroundSmoke:
    def test_pass_rate_two_thirds_via_helpers(self) -> None:
        """Aggregate two grounded paths and one ungrounded by hand."""
        auth_lookup = InMemoryAuthorityLookup(
            known_pairs=[("Howard v Aggio", date(2008, 1, 1))]
        )
        statute_lookup = InMemoryStatuteLookup()

        case = {
            "cited_authorities": [_auth("Howard v Aggio", date(2008, 1, 1))],
            "statutory_basis": [_stat("Made-up Act", "s.1")],
        }

        rows_a = check_authority(case, auth_lookup)
        rows_s = check_statute(case, statute_lookup)
        rows_d = check_date_sanity({"decision_date": date(2023, 6, 15)})

        all_rows = rows_a + rows_s + rows_d
        grounded = sum(1 for _, v, _ in all_rows if v == "GROUNDED")
        ungrounded = sum(1 for _, v, _ in all_rows if v == "UNGROUNDED")
        assert grounded == 2
        assert ungrounded == 1
        assert grounded / (grounded + ungrounded) == pytest.approx(2 / 3)

    def test_ground_returns_field_path_dict(self, tmp_path: Path) -> None:
        """End-to-end smoke: ``ground(...)`` returns a populated GroundingResult."""
        auth_lookup = InMemoryAuthorityLookup(
            known_pairs=[("Howard v Aggio", date(2008, 1, 1))]
        )
        statute_lookup = InMemoryStatuteLookup()
        deps = GroundingDeps(
            authority_lookup=auth_lookup,
            statute_lookup=statute_lookup,
            run_artifact_path=tmp_path / "missing.json",
        )
        case = {
            "decision_date": date(2023, 6, 15),
            "cited_authorities": [_auth("Howard v Aggio", date(2008, 1, 1))],
        }
        result = ground(
            case,
            page_text={},
            page_sections={},
            spans=[],
            lookups=deps,
        )
        assert isinstance(result, GroundingResult)
        auth_path = next(p for p in result.field_path if p.startswith("cited_authorities"))
        assert result.field_path[auth_path] == "GROUNDED"
        assert result.field_path["decision_date"] == "GROUNDED"
        assert 0.0 <= result.grounding_pass_rate <= 1.0
