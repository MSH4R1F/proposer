"""Smoke tests proving the FactorRetriever and EvidencePathValidator can
fire end-to-end when given real factor data — using the hand-built
fixture under data/eval_artifacts/positive_control/housing_repairs_social_v1_one_case_kg/.

Recovery plan Task 7. The 2026-05-07 ablation showed both subsystems
silently fell back to chunk-RAG / empty-graph rejection because no
factor data was populated. This test proves the path activates correctly
when the data is real.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from domain_packs.registry import get_domain_pack
from kg_builder.propositions.models import Proposition
from legal_core.graph.evidence_span import EvidenceSpan
from legal_core.graph.factor_assertion import FactorAssertion
from legal_core.graph.outcome_component import OutcomeComponent
from llm_orchestrator.pipeline.comparator_pack import ComparatorPack
from llm_orchestrator.pipeline.evidence_path_validator import (
    EvidencePathValidator,
)
from llm_orchestrator.pipeline.factor_retrieval import (
    AuthorityPolicy,
    FactorRetriever,
    RetrievalControlInput,
)


_FIXTURE_DIR = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "eval_artifacts"
    / "positive_control"
    / "housing_repairs_social_v1_one_case_kg"
)


# ---------------------------------------------------------------------------
# Fixture loaders (each goes through the right Pydantic model)
# ---------------------------------------------------------------------------


def _load_factor_assertions() -> list[FactorAssertion]:
    raw = json.loads((_FIXTURE_DIR / "factor_assertions.json").read_text())
    return [FactorAssertion.model_validate(item) for item in raw]


def _load_evidence_spans() -> list[EvidenceSpan]:
    raw = json.loads((_FIXTURE_DIR / "evidence_spans.json").read_text())
    return [EvidenceSpan.model_validate(item) for item in raw]


def _load_propositions() -> list[Proposition]:
    raw = json.loads((_FIXTURE_DIR / "propositions.json").read_text())
    return [Proposition.model_validate(item) for item in raw]


def _load_outcome_components() -> list[OutcomeComponent]:
    raw = json.loads((_FIXTURE_DIR / "outcome_components.json").read_text())
    return [OutcomeComponent.model_validate(item) for item in raw]


def _load_expected() -> dict:
    return json.loads((_FIXTURE_DIR / "expected_outcome.json").read_text())


class _FixtureKG:
    """Minimal KnowledgeGraph-like object for EvidencePathValidator.

    Mirrors the duck-typed shape EvidencePathValidator expects: three
    attributes — ``factor_assertions``, ``propositions``, ``evidence_spans``.
    """

    def __init__(
        self,
        factor_assertions: list[FactorAssertion],
        propositions: list[Proposition],
        evidence_spans: list[EvidenceSpan],
    ) -> None:
        self.factor_assertions = factor_assertions
        self.propositions = propositions
        self.evidence_spans = evidence_spans


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_fixture_loads_via_pydantic_models():
    """Sanity: every fixture JSON validates against its Pydantic model."""
    fas = _load_factor_assertions()
    spans = _load_evidence_spans()
    props = _load_propositions()
    ocs = _load_outcome_components()
    assert len(fas) >= 5
    assert len(spans) >= 4
    assert len(props) >= 6
    assert len(ocs) >= 1


@pytest.mark.asyncio
async def test_factor_retriever_returns_nonempty_comparator_pack():
    """When fed the fixture's factor assertions and a repository that
    surfaces the fixture's propositions, ``FactorRetriever.build_comparator_pack``
    must return at least one comparator and at least one counterexample."""
    pack = get_domain_pack("housing.repairs_social.v1")
    fixture_props = _load_propositions()
    fixture_fas = _load_factor_assertions()

    repo = AsyncMock()
    # The fixture propositions all carry issue_tags including
    # "housing.repairs_social.v1" so the same-domain gating accepts them.
    repo.search_by_issue_tags = AsyncMock(return_value=fixture_props)

    retriever = FactorRetriever(repository=repo, pack=pack)

    expected = _load_expected()
    primary_outcome = expected.get("outcome", "fault_finding")

    control = RetrievalControlInput(
        domain_id="housing.repairs_social.v1",
        claim_head_id="repairs_damp_mould",
        issue_ids=["repairs_damp_mould"],
        asserted_factors=fixture_fas,
        target_outcomes=[primary_outcome],
        target_remedies=[],
        forum="ombudsman",
        authority_policy=AuthorityPolicy(),
        retrieval_profile_id="housing.repairs_social.v1",
    )
    pack_result = await retriever.build_comparator_pack(
        control, primary_outcome=primary_outcome
    )
    assert isinstance(pack_result, ComparatorPack)
    assert len(pack_result.comparators) >= expected.get(
        "expected_comparator_pack_min_size", 1
    ), (
        f"comparator pack empty: {pack_result.comparator_pass_metadata}"
    )
    assert len(pack_result.counterexamples) >= expected.get(
        "expected_counterexample_pack_min_size", 1
    ), (
        f"counterexample pack empty: {pack_result.counterexample_pass_metadata}"
    )
    assert pack_result.comparator_pass_metadata.fallback_reason is None, (
        "fall-back fired despite real factor data"
    )


def test_evidence_path_validator_closes_chain_for_outcome_component():
    """When given the fixture's KG, the validator must return ``is_supported=True``
    for at least one ``OutcomeComponent`` and the chain must have the expected
    shape (EvidenceSpan → FactorAssertion → Proposition → OutcomeComponent)."""
    fas = _load_factor_assertions()
    spans = _load_evidence_spans()
    props = _load_propositions()
    ocs = _load_outcome_components()

    kg = _FixtureKG(factor_assertions=fas, propositions=props, evidence_spans=spans)
    validator = EvidencePathValidator(case_graph=kg)

    expected = _load_expected()
    if expected.get("expected_evidence_path_supported", True):
        any_supported = False
        for oc in ocs:
            result = validator.validate_outcome_component(oc)
            if result.is_supported:
                any_supported = True
                # Chain must be 4 nodes:
                # EvidenceSpan → FactorAssertion → Proposition → OutcomeComponent
                assert len(result.chain) == 4, (
                    f"unexpected chain length {len(result.chain)}: {result.chain}"
                )
                # First node should be an evidence_span_id
                span_ids = {s.evidence_span_id for s in spans}
                assert result.chain[0] in span_ids, (
                    f"chain[0]={result.chain[0]} not in evidence span ids"
                )
                # Last node is the OC id
                assert result.chain[-1] == oc.outcome_component_id
                break
        assert any_supported, (
            "no OutcomeComponent's chain closed — validator could not reach "
            "EvidenceSpan via FactorAssertion + Proposition. Fixture wiring "
            "is broken."
        )


def test_validator_audit_only_records_strong_when_chain_closes():
    """When the chain closes for at least one component, downstream metadata
    surfaces a supported result (i.e. the validator did not silently reject
    every OutcomeComponent)."""
    fas = _load_factor_assertions()
    spans = _load_evidence_spans()
    props = _load_propositions()
    ocs = _load_outcome_components()

    kg = _FixtureKG(factor_assertions=fas, propositions=props, evidence_spans=spans)
    validator = EvidencePathValidator(case_graph=kg)

    results = [validator.validate_outcome_component(oc) for oc in ocs]
    supported_count = sum(1 for r in results if r.is_supported)
    assert supported_count >= 1, "no OutcomeComponent supported"


def test_authority_policy_default_does_not_disqualify_fixture_propositions():
    """The default ``AuthorityPolicy`` must not zero out scoring for the
    fixture's propositions. Sanity check: ``retrieve_comparators`` non-empty."""
    pack = get_domain_pack("housing.repairs_social.v1")
    fixture_props = _load_propositions()
    fixture_fas = _load_factor_assertions()

    repo = AsyncMock()
    repo.search_by_issue_tags = AsyncMock(return_value=fixture_props)

    retriever = FactorRetriever(repository=repo, pack=pack)
    control = RetrievalControlInput(
        domain_id="housing.repairs_social.v1",
        claim_head_id="repairs_damp_mould",
        issue_ids=["repairs_damp_mould"],
        asserted_factors=fixture_fas,
        target_outcomes=["fault_finding"],
        target_remedies=[],
        forum="ombudsman",
        authority_policy=AuthorityPolicy(),
        retrieval_profile_id="housing.repairs_social.v1",
    )
    out = asyncio.run(retriever.retrieve_comparators(control))
    assert len(out) >= 1, "retrieve_comparators returned empty"


def test_factor_retriever_metadata_records_real_weights_when_factors_present():
    """The ``ComparatorPack`` metadata must record the real comparator weights
    from the pack's ``retrieval_profile`` (NOT empty / fallback)."""
    pack = get_domain_pack("housing.repairs_social.v1")
    fixture_props = _load_propositions()
    fixture_fas = _load_factor_assertions()

    repo = AsyncMock()
    repo.search_by_issue_tags = AsyncMock(return_value=fixture_props)
    retriever = FactorRetriever(repository=repo, pack=pack)
    control = RetrievalControlInput(
        domain_id="housing.repairs_social.v1",
        claim_head_id="repairs_damp_mould",
        issue_ids=["repairs_damp_mould"],
        asserted_factors=fixture_fas,
        target_outcomes=["fault_finding"],
        target_remedies=[],
        forum="ombudsman",
        authority_policy=AuthorityPolicy(),
        retrieval_profile_id="housing.repairs_social.v1",
    )
    pack_result = asyncio.run(
        retriever.build_comparator_pack(control, primary_outcome="fault_finding")
    )
    weights = pack_result.comparator_pass_metadata.weights_used
    assert weights, "weights_used was empty — fallback fired"
    assert "factor_overlap" in weights
    assert weights["factor_overlap"] > 0
