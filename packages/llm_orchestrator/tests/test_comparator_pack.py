"""Unit tests for ComparatorPack and supporting models (Cross-PR Contract C2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from llm_orchestrator.pipeline.comparator_pack import (
    ComparatorPack,
    ComparatorPassMetadata,
    CounterexamplePassMetadata,
    RankedProposition,
)


def _make_ranked_proposition(
    proposition_id: str = "prop_1",
    case_reference: str = "Case [2024] UKUT 123",
    score: float = 0.8,
    authority_level: str = "binding_precedent",
    proposition_role: str = "legal_test",
) -> RankedProposition:
    return RankedProposition(
        proposition_id=proposition_id,
        case_reference=case_reference,
        text="The landlord must keep the structure in repair.",
        source_passage="The landlord must keep the structure in repair.",
        authority_level=authority_level,  # type: ignore[arg-type]
        proposition_role=proposition_role,  # type: ignore[arg-type]
        score=score,
        score_breakdown={"semantic": 0.6, "factor_overlap": 0.2},
    )


def test_ranked_proposition_minimum_valid():
    rp = RankedProposition(
        proposition_id="prop_1",
        case_reference="Case [2024] UKUT 123",
        text="The landlord must keep the structure in repair.",
        source_passage="The landlord must keep the structure in repair.",
        authority_level="binding_precedent",
        proposition_role="legal_test",
        score=0.8,
        score_breakdown={"semantic": 0.6, "factor_overlap": 0.2},
    )
    assert rp.proposition_id == "prop_1"
    assert rp.authority_level == "binding_precedent"
    assert rp.proposition_role == "legal_test"
    assert rp.score == 0.8
    assert rp.score_breakdown["semantic"] == 0.6


def test_ranked_proposition_score_must_be_in_unit_interval():
    for bad in (-0.1, 1.1):
        with pytest.raises(ValidationError):
            RankedProposition(
                proposition_id="prop_1",
                case_reference="Case [2024] UKUT 123",
                text="text",
                source_passage="passage",
                authority_level="binding_precedent",
                proposition_role="legal_test",
                score=bad,
                score_breakdown={"semantic": 1.0},
            )


def test_ranked_proposition_authority_level_closed():
    with pytest.raises(ValidationError):
        RankedProposition(
            proposition_id="prop_1",
            case_reference="Case [2024] UKUT 123",
            text="text",
            source_passage="passage",
            authority_level="invalid",  # type: ignore[arg-type]
            proposition_role="legal_test",
            score=0.5,
            score_breakdown={"semantic": 0.5},
        )


def test_ranked_proposition_proposition_role_closed():
    with pytest.raises(ValidationError):
        RankedProposition(
            proposition_id="prop_1",
            case_reference="Case [2024] UKUT 123",
            text="text",
            source_passage="passage",
            authority_level="binding_precedent",
            proposition_role="invalid",  # type: ignore[arg-type]
            score=0.5,
            score_breakdown={"semantic": 0.5},
        )


def test_ranked_proposition_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        RankedProposition(
            proposition_id="prop_1",
            case_reference="Case [2024] UKUT 123",
            text="text",
            source_passage="passage",
            authority_level="binding_precedent",
            proposition_role="legal_test",
            score=0.5,
            score_breakdown={"semantic": 0.5},
            unexpected="oops",  # type: ignore[call-arg]
        )


def test_ranked_proposition_frozen_after_construction():
    rp = _make_ranked_proposition()
    with pytest.raises(ValidationError):
        rp.score = 0.99  # type: ignore[misc]


def test_comparator_pack_minimum_valid_with_empty_lists():
    pack = ComparatorPack(
        comparators=[],
        counterexamples=[],
        comparator_pass_metadata=ComparatorPassMetadata(
            n_retrieved=0,
            weights_used={"semantic": 0.5, "factor_overlap": 0.5},
        ),
        counterexample_pass_metadata=CounterexamplePassMetadata(
            n_retrieved=0,
            k_overlap_min=2,
            abstention_recommended=False,
        ),
    )
    assert pack.comparators == []
    assert pack.counterexamples == []
    assert pack.comparator_pass_metadata.n_retrieved == 0
    assert pack.comparator_pass_metadata.fallback_reason is None
    assert pack.counterexample_pass_metadata.abstention_recommended is False


def test_comparator_pack_round_trip_via_json():
    comparator_a = _make_ranked_proposition(
        proposition_id="prop_a",
        case_reference="Case A [2023] UKUT 1",
        score=0.9,
        authority_level="binding_precedent",
        proposition_role="legal_test",
    )
    comparator_b = _make_ranked_proposition(
        proposition_id="prop_b",
        case_reference="Case B [2023] UKUT 2",
        score=0.7,
        authority_level="comparator",
        proposition_role="fact_comparator",
    )
    counterexample = _make_ranked_proposition(
        proposition_id="prop_c",
        case_reference="Case C [2022] UKUT 3",
        score=0.6,
        authority_level="persuasive",
        proposition_role="factual_finding",
    )
    pack = ComparatorPack(
        comparators=[comparator_a, comparator_b],
        counterexamples=[counterexample],
        comparator_pass_metadata=ComparatorPassMetadata(
            n_retrieved=2,
            weights_used={"semantic": 0.4, "factor_overlap": 0.6},
            fallback_reason=None,
        ),
        counterexample_pass_metadata=CounterexamplePassMetadata(
            n_retrieved=1,
            k_overlap_min=2,
            abstention_recommended=False,
        ),
    )
    json_str = pack.model_dump_json()
    restored = ComparatorPack.model_validate_json(json_str)
    assert restored == pack


def test_counterexample_pass_metadata_abstention_recommended_true_round_trip():
    meta = CounterexamplePassMetadata(
        n_retrieved=3,
        k_overlap_min=4,
        abstention_recommended=True,
    )
    restored = CounterexamplePassMetadata.model_validate_json(meta.model_dump_json())
    assert restored == meta
    assert restored.abstention_recommended is True


def test_comparator_pass_metadata_fallback_reason_default_none():
    meta = ComparatorPassMetadata(
        n_retrieved=5,
        weights_used={"semantic": 1.0},
    )
    assert meta.fallback_reason is None

    meta_with_reason = ComparatorPassMetadata(
        n_retrieved=5,
        weights_used={"semantic": 1.0},
        fallback_reason="factor_retrieval_no_overlap",
    )
    assert meta_with_reason.fallback_reason == "factor_retrieval_no_overlap"


def test_comparator_pack_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        ComparatorPack(
            comparators=[],
            counterexamples=[],
            comparator_pass_metadata=ComparatorPassMetadata(
                n_retrieved=0,
                weights_used={},
            ),
            counterexample_pass_metadata=CounterexamplePassMetadata(
                n_retrieved=0,
                k_overlap_min=2,
                abstention_recommended=False,
            ),
            unexpected="oops",  # type: ignore[call-arg]
        )


def test_comparator_pack_frozen_after_construction():
    pack = ComparatorPack(
        comparators=[],
        counterexamples=[],
        comparator_pass_metadata=ComparatorPassMetadata(
            n_retrieved=0,
            weights_used={},
        ),
        counterexample_pass_metadata=CounterexamplePassMetadata(
            n_retrieved=0,
            k_overlap_min=2,
            abstention_recommended=False,
        ),
    )
    with pytest.raises(ValidationError):
        pack.comparators = [_make_ranked_proposition()]  # type: ignore[misc]
