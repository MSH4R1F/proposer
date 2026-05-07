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
async def test_positive_control_factor_retriever_returns_nonempty_pack():
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


def test_positive_control_evidence_path_closes():
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


# ---------------------------------------------------------------------------
# End-to-end smoke through PredictionEngineV2
# ---------------------------------------------------------------------------


class _FixtureRepairsKG:
    """KnowledgeGraph-like that carries the fixture's factor_assertions plus
    the auxiliary collections the graph-quality heuristic in
    ``IssuePredictor._compute_graph_quality_score`` reads.

    The repairs gate (``housing.repairs_social.v1`` / graph_quality_gate.yaml)
    requires ≥5 evidence-backed factors, ≥2 dated events, ≥1 issue, and ≥1
    outcome candidate. Our fixture supplies 7 evidence-backed factor
    assertions; the other counts are filled in with synthetic stand-ins so
    ``DomainPack.is_kg_usable`` returns True and the engine flips
    ``kg_used_for_prediction`` to True.
    """

    def __init__(
        self,
        factor_assertions: list[FactorAssertion],
        propositions: list[Proposition],
        evidence_spans: list[EvidenceSpan],
    ) -> None:
        from datetime import date as _date
        from types import SimpleNamespace as _SimpleNamespace

        self.factor_assertions = factor_assertions
        self.propositions = propositions
        self.evidence_spans = evidence_spans
        self.dated_events = [
            _SimpleNamespace(date=_date(2024, 12, 12), description="initial_report"),
            _SimpleNamespace(date=_date(2025, 4, 11), description="first_inspection"),
            _SimpleNamespace(date=_date(2025, 6, 10), description="repair_completed"),
        ]
        self.issues = [_SimpleNamespace(issue_type="repairs_damp_mould")]
        self.candidate_outcomes = [_SimpleNamespace(outcome="maladministration")]

    def get_nodes_by_type(self, node_type):  # noqa: ARG002 — duck-typing stub
        # ``derive_kg_facts`` calls this for non-deposit domains and ignores
        # the result for repairs cases. Returning [] keeps the deposit-typed
        # facts at "unknown" so the KGFacts adapter is empty for this domain.
        return []


def _make_repairs_case_file_for_e2e(case_id: str = "positive-control-001"):
    """Build a SimpleNamespace stand-in for ``CaseFile`` for the e2e smoke.

    The real ``CaseFile`` Pydantic model has many required nested fields
    (PartyRole, PropertyDetails, TenancyDetails). The engine and retriever
    only reach for a handful via ``getattr``, so a SimpleNamespace is
    sufficient and mirrors the precedent in ``test_pr4_integration.py``.
    """
    from datetime import date as _date
    from types import SimpleNamespace as _SimpleNamespace

    return _SimpleNamespace(
        case_id=case_id,
        domain_id="housing.repairs_social.v1",
        forum="ombudsman",
        tenant_narrative=(
            "Damp and mould reported in December 2024; first inspection only "
            "took place 120 days later, and substantive repairs were not "
            "completed for 180 days. I have asthma and live with my child."
        ),
        landlord_narrative=(
            "The landlord acknowledged the report on the day it was made and "
            "treats the repair as completed."
        ),
        tenancy=_SimpleNamespace(
            deposit_amount=None,
            start_date=_date(2023, 6, 1),
            end_date=None,
            tenancy_type="social",
            deposit_protected=None,
            deposit_scheme=None,
            protection_date=None,
            prescribed_info_provided=None,
            prescribed_info_date=None,
        ),
        property=_SimpleNamespace(region="London", postcode=None),
        metadata={"domain_id": "housing.repairs_social.v1"},
        dispute_amount=None,
    )


@pytest.mark.asyncio
async def test_positive_control_engine_e2e_metadata_shows_kg_used(monkeypatch):
    """End-to-end: with ``STREAM_C_FACTOR_RETRIEVAL=1`` and the fixture's
    propositions surfaced via a stub repository, ``PredictionEngineV2.predict``
    must produce a ``PipelineMetadata`` recording:

    - ``retrieval_strategy == "factor_constrained"``
    - ``kg_used_for_prediction is True``

    No real LLM or RAG call is made: the LLM client is a fake that returns a
    canned IRAC JSON, and the proposition repository is an ``AsyncMock``
    returning the fixture's hand-built propositions.
    """
    from unittest.mock import MagicMock

    from llm_orchestrator.models.prediction_v2 import (
        IssueContext,
        IssueType,
        PredictionMode,
    )
    from llm_orchestrator.pipeline.prediction_engine_v2 import (
        PredictionEngineV2,
    )

    # Flip the engine into the FACTOR_CONSTRAINED strategy. PR4 must stay on
    # so the renderer and gate fire (PR4=1 is the production default).
    monkeypatch.setenv("STREAM_C_FACTOR_RETRIEVAL", "1")
    monkeypatch.setenv("STREAM_C_PR4", "1")
    monkeypatch.setenv("STREAM_C_PR4_REPAIRS", "1")

    fixture_fas = _load_factor_assertions()
    fixture_props = _load_propositions()
    fixture_spans = _load_evidence_spans()

    captured_prompts: list[str] = []

    async def fake_generate(messages, system_prompt, max_tokens, temperature):
        captured_prompts.append(messages[0]["content"])
        return (
            '{"outcome":"tenant_wins","raw_confidence":0.7,"reasoning":"r",'
            '"supporting_cases":[{"case_reference":"positive-control-comparator-001",'
            '"year":2024,"quote":"q","relevance":"r"}],'
            '"counterfactuals":[],'
            '"evidence_strength":"moderate","data_completeness_impact":"ok",'
            '"predicted_determination":"maladministration",'
            '"amount_construct":null}'
        )

    llm = MagicMock()
    llm.generate = fake_generate

    # Real RAG pipeline isn't used: the FACTOR_CONSTRAINED branch never
    # hits chunk-RAG when its prerequisites (asserted_factors + repository)
    # are satisfied. We still pass an AsyncMock so the engine doesn't
    # short-circuit on a missing ``rag_pipeline`` (see lines 268-274 of
    # prediction_engine_v2.py — both pipelines must be available so the
    # FACTOR_CONSTRAINED-fallback branch wouldn't strand the call).
    rag = AsyncMock()
    rag.retrieve = AsyncMock(return_value={"results": [], "confidence": 0.0})

    proposition_retriever = MagicMock()
    repo = AsyncMock()
    repo.search_by_issue_tags = AsyncMock(return_value=fixture_props)
    proposition_retriever.repository = repo

    engine = PredictionEngineV2(
        llm_client=llm,
        rag_pipeline=rag,
        proposition_retriever=proposition_retriever,
        min_cases_required=1,  # one fixture comparator must clear the bar
    )

    # Replace the LLM-backed issue decomposer with a deterministic stub so
    # the engine reliably yields one REPAIRS_DAMP_MOULD issue (the fixture's
    # claim head). Mirrors the precedent in test_pr4_integration.py.
    fake_issue = IssueContext(
        issue_type=IssueType.REPAIRS_DAMP_MOULD,
        issue_description=(
            "120-day inspection delay, 180-day repair delay, vulnerable "
            "resident with asthma."
        ),
        kg_constraints=[],
        data_completeness=0.8,
    )
    engine.issue_decomposer.decompose = lambda cf, kg=None: [fake_issue]

    kg = _FixtureRepairsKG(
        factor_assertions=fixture_fas,
        propositions=fixture_props,
        evidence_spans=fixture_spans,
    )
    case_file = _make_repairs_case_file_for_e2e()

    result = await engine.predict(
        case_file=case_file,
        knowledge_graph=kg,
        mode=PredictionMode.HYBRID,
    )

    metadata = result.pipeline_metadata
    # The engine returns ``pipeline_metadata=None`` only when it short-circuits
    # via ``PredictionResult.create_uncertain`` (e.g. no issues / no sufficient
    # cases / missing RAG pipeline). A None here means the smoke regressed
    # before the OutputAssembler ran — surface it directly rather than letting
    # the strategy assertion crash with an opaque AttributeError.
    assert metadata is not None, (
        "engine returned create_uncertain (no pipeline_metadata): "
        f"overall_outcome={result.overall_outcome.value}, "
        f"summary={result.outcome_summary!r}"
    )
    # The plan's hard requirements (recovery T7 / Gate 3 precondition):
    assert metadata.retrieval_strategy == "factor_constrained", (
        f"engine did not flip to factor_constrained: "
        f"strategy={metadata.retrieval_strategy!r}, "
        f"steps={metadata.steps_executed}"
    )
    assert metadata.kg_used_for_prediction is True, (
        f"kg_used_for_prediction was {metadata.kg_used_for_prediction!r}: "
        f"fallback_mode={metadata.kg_fallback_mode!r}, "
        f"gate_failures={metadata.kg_gate_failure_reasons}"
    )
    # Domain pack identifiers stamped from the active pack.
    assert metadata.domain_pack == "housing.repairs_social.v1"
    # Sanity: at least one LLM call was made (i.e. the path didn't degrade
    # to UNCERTAIN before the predictor ran).
    assert captured_prompts, "fake LLM was never invoked"
