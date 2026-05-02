"""Tests for the deterministic forum-policy verifier (SHA-62).

The verifier is the fail-closed gate: a model can be told not to use a phrase,
but only this verifier can guarantee that user-facing output stays within the
forum's compliance envelope.
"""

from __future__ import annotations

import pytest

from domain_core.registry import load_domain_specs
from domain_core.spec import Forum

from llm_orchestrator.models.prediction_v2 import PredictionMode
from llm_orchestrator.pipeline.forum_policy_verifier import (
    ForumPolicyVerifier,
    ForumPolicyViolationKind,
    verify_output,
    verify_output_with_pack,
)
from llm_orchestrator.prompts.packs import get_prompt_pack


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile_for(domain_id: str, forum: Forum):
    spec = load_domain_specs()[domain_id]
    for profile in spec.forum_profiles:
        if profile.forum == forum:
            return profile
    raise AssertionError(f"No {forum} profile in {domain_id}")


_BASELINE_DEPOSIT_DISCLAIMER = (
    "This is legal information based on similar published decisions, not legal advice."
)
_BASELINE_OMBUDSMAN_DISCLAIMER = (
    "This is information about Housing Ombudsman determinations, not legal advice."
)
_BASELINE_RRO_DISCLAIMER = (
    "This is legal information based on similar published Property Chamber decisions, "
    "not legal advice."
)
_BASELINE_ET_DISCLAIMERS = (
    "This is legal information based on similar published Employment Tribunal decisions, "
    "not legal advice. Employment claims have strict time limits - see ACAS early conciliation."
)


def _ok_deposit_output() -> dict:
    return {
        "issue_type": "cleaning",
        "outcome": "tenant_wins",
        "raw_confidence": 0.7,
        "reasoning": (
            f"Tribunals have tended to favour tenants where no inventory exists. "
            f"{_BASELINE_DEPOSIT_DISCLAIMER}"
        ),
        "supporting_cases": [
            {
                "case_reference": "CHI/00MA/2023/123",
                "year": 2023,
                "quote": "...",
                "relevance": "similar cleaning dispute",
                "citation_kind": "retrieved_legal_source",
                "source_kind": "case_decision",
            }
        ],
        "evidence_strength": "moderate",
        "matter_type": "deposit_deduction",
        "forum": "deposit_scheme_adjudication",
    }


# ---------------------------------------------------------------------------
# Housing Ombudsman: court-damages framing must trip the verifier.
# ---------------------------------------------------------------------------


def test_housing_ombudsman_pack_cannot_emit_tribunal_would_award():
    profile = _profile_for("housing.repairs_social.v1", Forum.HOUSING_OMBUDSMAN)
    output = {
        "issue_type": "repairs_damp_mould",
        "outcome": "tenant_wins",
        "raw_confidence": 0.8,
        "reasoning": (
            "Based on similar determinations, the tribunal would award £600 in compensation. "
            f"{_BASELINE_OMBUDSMAN_DISCLAIMER}"
        ),
        "supporting_cases": [],
        "evidence_strength": "moderate",
        "matter_type": "repairs_damp_mould",
        "forum": "housing_ombudsman",
    }
    result = verify_output(output, profile, mode=PredictionMode.HYBRID)
    assert not result.passed
    kinds = {v.kind for v in result.violations}
    assert ForumPolicyViolationKind.PROHIBITED_PHRASE in kinds
    # Quarantine: production posture forces uncertain.
    assert result.output_after_redaction["outcome"] == "uncertain"
    assert result.output_after_redaction["raw_confidence"] == 0.0


def test_housing_ombudsman_pack_passes_with_complaint_framing():
    profile = _profile_for("housing.repairs_social.v1", Forum.HOUSING_OMBUDSMAN)
    output = {
        "issue_type": "repairs_damp_mould",
        "outcome": "tenant_wins",
        "raw_confidence": 0.7,
        "reasoning": (
            "In similar Housing Ombudsman determinations, severe maladministration "
            f"led to compensation orders. {_BASELINE_OMBUDSMAN_DISCLAIMER}"
        ),
        "supporting_cases": [
            {
                "case_reference": "HO/2024/00012345",
                "year": 2024,
                "quote": "severe maladministration found",
                "relevance": "similar damp/mould complaint",
                "citation_kind": "retrieved_legal_source",
                "source_kind": "ombudsman_determination",
            }
        ],
        "evidence_strength": "moderate",
        "matter_type": "repairs_damp_mould",
        "forum": "housing_ombudsman",
    }
    result = verify_output(output, profile, mode=PredictionMode.HYBRID)
    assert result.passed, result.violations


# ---------------------------------------------------------------------------
# RRO pack: leasehold/Tenant Fees Act must trip the verifier.
# ---------------------------------------------------------------------------


def test_rro_pack_does_not_mention_broad_leasehold_or_tenant_fees_remedies():
    """Audit D4 hard scope-fence: RRO pack must reject leasehold / Tenant
    Fees / park homes / building safety vocabulary even though the YAML
    profile's prohibited list does not include them. The pack contributes
    its own prohibited list via ``extra_prohibited_phrases``.
    """
    profile = _profile_for(
        "housing.property_chamber.rro.v1", Forum.FIRST_TIER_PROPERTY_CHAMBER
    )
    pack = get_prompt_pack("housing.property_chamber.rro.v1")
    output = {
        "issue_type": "rent_repayment_order",
        "outcome": "tenant_wins",
        "raw_confidence": 0.7,
        "reasoning": (
            "The tenant could also pursue leasehold service charges and a "
            "Tenant Fees Act claim alongside the rent repayment. "
            f"{_BASELINE_RRO_DISCLAIMER}"
        ),
        "supporting_cases": [],
        "evidence_strength": "moderate",
        "matter_type": "rent_repayment_order",
        "forum": "first_tier_property_chamber",
    }
    result = verify_output_with_pack(output, profile, pack, mode=PredictionMode.HYBRID)
    assert not result.passed
    kinds = {v.kind for v in result.violations}
    assert ForumPolicyViolationKind.PROHIBITED_PHRASE in kinds
    # Both scope-fence terms should have been flagged.
    msgs = " ".join(v.message for v in result.violations).lower()
    assert "leasehold service charges" in msgs
    assert "tenant fees act" in msgs


# ---------------------------------------------------------------------------
# Employment pack: directive advice must trip the verifier.
# ---------------------------------------------------------------------------


def test_employment_pack_stays_legal_information_only():
    profile = _profile_for(
        "employment.unfair_dismissal.v1", Forum.EMPLOYMENT_TRIBUNAL
    )
    output = {
        "issue_type": "unfair_dismissal",
        "outcome": "tenant_wins",
        "raw_confidence": 0.6,
        "reasoning": (
            "Given the procedural failures, you should accept the £4,000 offer. "
            f"{_BASELINE_ET_DISCLAIMERS}"
        ),
        "supporting_cases": [],
        "evidence_strength": "moderate",
        "matter_type": "unfair_dismissal",
        "forum": "employment_tribunal",
    }
    result = verify_output(output, profile, mode=PredictionMode.HYBRID)
    assert not result.passed
    kinds = {v.kind for v in result.violations}
    # Directive advice rule applies universally.
    assert (
        ForumPolicyViolationKind.DIRECTIVE_ADVICE in kinds
        or ForumPolicyViolationKind.PROHIBITED_PHRASE in kinds
    )


# ---------------------------------------------------------------------------
# Missing disclaimer / citation rules.
# ---------------------------------------------------------------------------


def test_missing_required_disclaimer_is_flagged():
    profile = _profile_for("housing.deposit.v1", Forum.DEPOSIT_SCHEME_ADJUDICATION)
    output = _ok_deposit_output()
    output["reasoning"] = (
        "Tribunals have tended to favour tenants where no inventory exists."
    )
    result = verify_output(output, profile, mode=PredictionMode.HYBRID)
    assert not result.passed
    assert any(
        v.kind == ForumPolicyViolationKind.MISSING_DISCLAIMER for v in result.violations
    )


def test_disclaimer_paraphrase_is_accepted():
    profile = _profile_for("housing.deposit.v1", Forum.DEPOSIT_SCHEME_ADJUDICATION)
    output = _ok_deposit_output()
    output["reasoning"] = (
        "Tribunals have tended to favour tenants where no inventory exists. "
        "this is legal information based on analysis of similar tribunal cases."
    )
    result = verify_output(output, profile, mode=PredictionMode.HYBRID)
    assert result.passed, result.violations


def test_citation_kind_outside_forum_allowlist_is_flagged():
    profile = _profile_for(
        "housing.repairs_social.v1", Forum.HOUSING_OMBUDSMAN
    )
    # Ombudsman profile doesn't allow ``deterministic_calculator_trace``.
    output = {
        "issue_type": "repairs_damp_mould",
        "outcome": "tenant_wins",
        "raw_confidence": 0.6,
        "reasoning": (
            "In similar determinations, severe maladministration was found. "
            f"{_BASELINE_OMBUDSMAN_DISCLAIMER}"
        ),
        "supporting_cases": [
            {
                "case_reference": "HO/2024/00099999",
                "year": 2024,
                "quote": "...",
                "relevance": "similar damp complaint",
                "citation_kind": "deterministic_calculator_trace",
                "source_kind": "ombudsman_determination",
            }
        ],
        "evidence_strength": "moderate",
        "matter_type": "repairs_damp_mould",
        "forum": "housing_ombudsman",
    }
    result = verify_output(output, profile, mode=PredictionMode.HYBRID)
    assert not result.passed
    assert any(
        v.kind == ForumPolicyViolationKind.CITATION_KIND_MISUSE
        for v in result.violations
    )


def test_statutory_cap_claim_requires_calculator_trace():
    profile = _profile_for("housing.deposit.v1", Forum.COUNTY_COURT)
    output = {
        "issue_type": "deposit_protection",
        "outcome": "tenant_wins",
        "raw_confidence": 0.8,
        "predicted_amount": 3000.0,
        "reasoning": (
            "The penalty is 1x-3x the deposit under Housing Act 2004 s.214. "
            f"{_BASELINE_DEPOSIT_DISCLAIMER}"
        ),
        "supporting_cases": [
            {
                "case_reference": "Smith v Jones [2019]",
                "year": 2019,
                "quote": "...",
                "relevance": "non-protection penalty",
                "citation_kind": "retrieved_legal_source",
                "source_kind": "case_decision",
            }
        ],
        "evidence_strength": "strong",
        "matter_type": "deposit_non_protection",
        "forum": "county_court",
    }
    result = verify_output(output, profile, mode=PredictionMode.HYBRID)
    assert not result.passed
    assert any(
        v.kind == ForumPolicyViolationKind.CALCULATOR_TRACE_REQUIRED
        for v in result.violations
    )


def test_statutory_cap_claim_passes_with_calculator_trace():
    profile = _profile_for("housing.deposit.v1", Forum.COUNTY_COURT)
    output = {
        "issue_type": "deposit_protection",
        "outcome": "tenant_wins",
        "raw_confidence": 0.8,
        "predicted_amount": 3000.0,
        "reasoning": (
            "The penalty is 1x-3x the deposit under Housing Act 2004 s.214. "
            f"{_BASELINE_DEPOSIT_DISCLAIMER}"
        ),
        "supporting_cases": [
            {
                "case_reference": "Smith v Jones [2019]",
                "year": 2019,
                "quote": "...",
                "relevance": "non-protection penalty",
                "citation_kind": "retrieved_legal_source",
                "source_kind": "case_decision",
            }
        ],
        "calculator_trace": {"multiplier": 3, "deposit": 1000.0, "result": 3000.0},
        "evidence_strength": "strong",
        "matter_type": "deposit_non_protection",
        "forum": "county_court",
    }
    result = verify_output(output, profile, mode=PredictionMode.HYBRID)
    assert result.passed, result.violations


# ---------------------------------------------------------------------------
# Mode-specific behaviour.
# ---------------------------------------------------------------------------


def test_research_mode_annotates_warnings_but_does_not_quarantine():
    profile = _profile_for("housing.repairs_social.v1", Forum.HOUSING_OMBUDSMAN)
    output = {
        "issue_type": "repairs_damp_mould",
        "outcome": "tenant_wins",
        "raw_confidence": 0.8,
        "reasoning": (
            "The tribunal would award compensation here. "
            f"{_BASELINE_OMBUDSMAN_DISCLAIMER}"
        ),
        "supporting_cases": [],
        "evidence_strength": "moderate",
        "matter_type": "repairs_damp_mould",
        "forum": "housing_ombudsman",
    }
    verifier = ForumPolicyVerifier(profile, mode=PredictionMode.LLM_ONLY)
    result = verifier.verify(output)
    assert not result.passed
    # Research-mode posture: outcome NOT clobbered, but warnings annotated.
    assert result.output_after_redaction["outcome"] == "tenant_wins"
    assert result.output_after_redaction["forum_policy_warnings"]
