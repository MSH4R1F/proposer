"""Tests for FactorRetriever (Stream C PR 5 — Task 5.3).

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md
      §9.2 (comparator scoring), §9.3 (counterexamples), Cross-PR Contract C3.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from domain_packs.registry import get_domain_pack
from kg_builder.propositions.models import Proposition, PropositionType
from legal_core.graph.factor_assertion import (
    ExtractionMethod,
    FactorAssertion,
    FactorPolarity,
)
from legal_core.graph.factor_value import FactorValue, FactorValueType
from llm_orchestrator.pipeline.factor_retrieval import (
    AuthorityPolicy,
    FactorRetriever,
    RetrievalControlInput,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fa(factor_id: str) -> FactorAssertion:
    return FactorAssertion(
        factor_assertion_id=f"fa_{factor_id}",
        factor_id=factor_id,
        domain_id="housing.repairs_social.v1",
        claim_head_id="claim_1",
        value=FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
        value_type=FactorValueType.BOOLEAN,
        confidence=0.92,
        polarity=FactorPolarity.PRO_CLAIMANT,
        supported_by=["span_1"],
        extraction_method=ExtractionMethod.LLM_VERIFIED,
        extractor_version="test_v1",
        verifier_version="test_v1",
    )


def _make_prop(
    factor_ids: list[str],
    outcome_component_ids: list[str] | None = None,
    *,
    authority_level: str = "comparator",
    proposition_role: str = "fact_comparator",
    text: str = "P1 text",
    case_ref: str = "PROP-001",
    issue_tags: list[str] | None = None,
    claim_head_ids: list[str] | None = None,
) -> Proposition:
    return Proposition(
        proposition_id=uuid4(),
        document_id=uuid4(),
        case_reference=case_ref,
        text=text,
        source_passage=text,
        proposition_type=PropositionType.fact,
        confidence=0.85,
        issue_tags=issue_tags or [],
        factor_ids=factor_ids,
        outcome_component_ids=outcome_component_ids or [],
        claim_head_ids=claim_head_ids or [],
        authority_level=authority_level,
        proposition_role=proposition_role,
    )


def _control_input(
    asserted_factor_ids: list[str],
    target_outcomes: list[str] | None = None,
) -> RetrievalControlInput:
    return RetrievalControlInput(
        domain_id="housing.repairs_social.v1",
        claim_head_id="claim_1",
        issue_ids=["repairs_disrepair"],
        asserted_factors=[_make_fa(fid) for fid in asserted_factor_ids],
        target_outcomes=target_outcomes or ["fault_finding"],
        target_remedies=[],
        forum="ombudsman",
        authority_policy=AuthorityPolicy(),
        retrieval_profile_id="housing.repairs_social.v1",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_comparators_returns_scored_props():
    pack = get_domain_pack("housing.repairs_social.v1")
    repo = AsyncMock()
    repo.search_by_issue_tags = AsyncMock(
        return_value=[
            _make_prop(
                ["repair_responsibility_established"],
                ["fault_finding"],
                issue_tags=["housing.repairs_social.v1"],
            ),
            _make_prop(
                [
                    "repair_responsibility_established",
                    "inspection_offered",
                ],
                ["fault_finding"],
                issue_tags=["housing.repairs_social.v1"],
            ),
        ]
    )
    retriever = FactorRetriever(repo, pack)
    out = await retriever.retrieve_comparators(
        _control_input(["repair_responsibility_established"]),
    )
    assert len(out) >= 1
    assert all(p.score > 0 for p in out)


@pytest.mark.asyncio
async def test_retrieve_counterexamples_filters_by_outcome():
    pack = get_domain_pack("housing.repairs_social.v1")
    repo = AsyncMock()
    repo.search_by_issue_tags = AsyncMock(
        return_value=[
            _make_prop(
                [
                    "repair_responsibility_established",
                    "inspection_offered",
                    "hazard_or_disrepair_reported",
                ],
                ["fault_finding"],
                issue_tags=["housing.repairs_social.v1"],
            ),
            _make_prop(
                [
                    "repair_responsibility_established",
                    "inspection_offered",
                    "hazard_or_disrepair_reported",
                ],
                ["no_fault"],
                issue_tags=["housing.repairs_social.v1"],
            ),
        ]
    )
    retriever = FactorRetriever(repo, pack)
    inp = _control_input(
        [
            "repair_responsibility_established",
            "inspection_offered",
            "hazard_or_disrepair_reported",
        ]
    )
    out = await retriever.retrieve_counterexamples(
        inp, primary_outcome="fault_finding"
    )
    assert len(out) == 1


@pytest.mark.asyncio
async def test_empty_asserted_factors_returns_empty_pack_with_fallback():
    pack = get_domain_pack("housing.repairs_social.v1")
    repo = AsyncMock()
    retriever = FactorRetriever(repo, pack)
    pack_out = await retriever.build_comparator_pack(
        _control_input(asserted_factor_ids=[]),
        primary_outcome="fault_finding",
    )
    assert pack_out.comparators == []
    assert pack_out.counterexamples == []
    assert pack_out.comparator_pass_metadata.fallback_reason == "no_asserted_factors"
    assert pack_out.counterexample_pass_metadata.abstention_recommended is False


@pytest.mark.asyncio
async def test_counterexample_pass_abstention_recommended_when_none():
    """When abstain_if_none=True (pack default for repairs) and no
    counterexamples found, abstention_recommended=True."""
    pack = get_domain_pack("housing.repairs_social.v1")
    repo = AsyncMock()
    # All candidates have the SAME outcome — no counterexamples possible.
    repo.search_by_issue_tags = AsyncMock(
        return_value=[
            _make_prop(
                ["a", "b", "c"],
                ["fault_finding"],
                issue_tags=["housing.repairs_social.v1"],
            ),
        ]
    )
    retriever = FactorRetriever(repo, pack)
    pack_out = await retriever.build_comparator_pack(
        _control_input(["a", "b", "c"]),
        primary_outcome="fault_finding",
    )
    assert pack_out.counterexample_pass_metadata.abstention_recommended is True


@pytest.mark.asyncio
async def test_stream_c_k_overlap_min_env_override(monkeypatch):
    monkeypatch.setenv("STREAM_C_K_OVERLAP_MIN", "1")
    pack = get_domain_pack("housing.repairs_social.v1")
    repo = AsyncMock()
    repo.search_by_issue_tags = AsyncMock(
        return_value=[
            _make_prop(
                ["a"], ["no_fault"], issue_tags=["housing.repairs_social.v1"]
            ),
        ]
    )
    retriever = FactorRetriever(repo, pack)
    out = await retriever.retrieve_counterexamples(
        _control_input(["a"]), primary_outcome="fault_finding"
    )
    # 1 shared factor, k_overlap_min=1 from env -> matches.
    assert len(out) == 1


@pytest.mark.asyncio
async def test_stream_c_counterexample_abstain_zero_disables(monkeypatch):
    monkeypatch.setenv("STREAM_C_COUNTEREXAMPLE_ABSTAIN", "0")
    pack = get_domain_pack("housing.repairs_social.v1")
    repo = AsyncMock()
    repo.search_by_issue_tags = AsyncMock(return_value=[])
    retriever = FactorRetriever(repo, pack)
    pack_out = await retriever.build_comparator_pack(
        _control_input(
            [
                "repair_responsibility_established",
                "inspection_offered",
                "hazard_or_disrepair_reported",
            ]
        ),
        primary_outcome="fault_finding",
    )
    # abstain_if_none=False from env -> abstention_recommended=False even
    # though no counterexamples found.
    assert pack_out.counterexample_pass_metadata.abstention_recommended is False


@pytest.mark.asyncio
async def test_authority_policy_disqualifies_first_instance_legal_test():
    """When authority_policy.accept_first_instance_as_fact_comparator=False,
    a comparator-level proposition with role=legal_test gets
    authority_match=0."""
    pack = get_domain_pack("housing.repairs_social.v1")
    repo = AsyncMock()
    repo.search_by_issue_tags = AsyncMock(
        return_value=[
            _make_prop(
                ["repair_responsibility_established"],
                ["fault_finding"],
                authority_level="comparator",
                proposition_role="legal_test",
                issue_tags=["housing.repairs_social.v1"],
            ),
        ]
    )
    retriever = FactorRetriever(repo, pack)
    inp = RetrievalControlInput(
        domain_id="housing.repairs_social.v1",
        claim_head_id="claim_1",
        issue_ids=["repairs_disrepair"],
        asserted_factors=[_make_fa("repair_responsibility_established")],
        target_outcomes=["fault_finding"],
        target_remedies=[],
        forum="ombudsman",
        authority_policy=AuthorityPolicy(
            accept_first_instance_as_fact_comparator=False
        ),
        retrieval_profile_id="housing.repairs_social.v1",
    )
    out = await retriever.retrieve_comparators(inp)
    if out:
        assert out[0].score_breakdown["authority_level_match"] == 0.0


@pytest.mark.asyncio
async def test_cross_domain_filtering_excludes_other_domains():
    pack = get_domain_pack("housing.repairs_social.v1")
    repo = AsyncMock()
    repo.search_by_issue_tags = AsyncMock(
        return_value=[
            _make_prop(
                ["fa1"],
                ["fault_finding"],
                issue_tags=["housing.repairs_social.v1"],
            ),
            _make_prop(
                ["fa1"],
                ["fault_finding"],
                issue_tags=["housing.deposit.v1"],
            ),
        ]
    )
    retriever = FactorRetriever(repo, pack)
    out = await retriever.retrieve_comparators(_control_input(["fa1"]))
    # Only the same-domain proposition should survive cross-domain filter.
    assert len(out) == 1


@pytest.mark.asyncio
async def test_score_breakdown_keys_complete():
    pack = get_domain_pack("housing.repairs_social.v1")
    repo = AsyncMock()
    repo.search_by_issue_tags = AsyncMock(
        return_value=[
            _make_prop(
                ["a"], ["fault_finding"], issue_tags=["housing.repairs_social.v1"]
            ),
        ]
    )
    retriever = FactorRetriever(repo, pack)
    out = await retriever.retrieve_comparators(_control_input(["a"]))
    assert out, "expected at least one ranked proposition"
    breakdown = out[0].score_breakdown
    for key in (
        "factor_overlap",
        "text_relevance",
        "outcome_component_match",
        "remedy_similarity",
        "authority_level_match",
        "chronology_match",
        "claim_head_exact_match",
    ):
        assert key in breakdown


@pytest.mark.asyncio
async def test_build_comparator_pack_metadata_weights_snapshot():
    """build_comparator_pack snapshots the active comparator_weights."""
    pack = get_domain_pack("housing.repairs_social.v1")
    repo = AsyncMock()
    repo.search_by_issue_tags = AsyncMock(
        return_value=[
            _make_prop(
                ["a"],
                ["fault_finding"],
                issue_tags=["housing.repairs_social.v1"],
            ),
        ]
    )
    retriever = FactorRetriever(repo, pack)
    pack_out = await retriever.build_comparator_pack(
        _control_input(["a"]), primary_outcome="fault_finding"
    )
    weights_used = pack_out.comparator_pass_metadata.weights_used
    assert weights_used["factor_overlap"] == pytest.approx(
        pack.retrieval_profile.comparator_weights.factor_overlap
    )
    assert pack_out.counterexample_pass_metadata.k_overlap_min == (
        pack.retrieval_profile.counterexample.k_overlap_min
    )


@pytest.mark.asyncio
async def test_retrieve_comparators_no_issue_ids_returns_empty():
    """Guard: when issue_ids is empty the seed pass returns no candidates."""
    pack = get_domain_pack("housing.repairs_social.v1")
    repo = AsyncMock()
    repo.search_by_issue_tags = AsyncMock(return_value=[])
    retriever = FactorRetriever(repo, pack)
    inp = RetrievalControlInput(
        domain_id="housing.repairs_social.v1",
        claim_head_id="claim_1",
        issue_ids=[],
        asserted_factors=[_make_fa("a")],
        target_outcomes=["fault_finding"],
        target_remedies=[],
        forum="ombudsman",
        authority_policy=AuthorityPolicy(),
        retrieval_profile_id="housing.repairs_social.v1",
    )
    out = await retriever.retrieve_comparators(inp)
    assert out == []
    repo.search_by_issue_tags.assert_not_called()
