"""Tests for ``eval.factor_assertion_sidecar`` — the case-side backfill
that hydrates the FactorRetriever's ``asserted_factors`` input from a
JSON sidecar instead of a GoldCase schema field (Stream C).

The point of this module is to verify the GOLD-CASE → ENGINE-INPUT path:
once the sidecar is loaded, the FactorAssertion entries must surface on
the KnowledgeGraph's ``factor_assertions`` attribute exactly where the
``IssueRetriever._retrieve_via_factor_retriever`` reads them. Without
that, the LLM extraction run is wasted because the engine never sees
the new field.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

from eval.factor_assertion_sidecar import (
    SIDECAR_SCHEMA_VERSION,
    default_sidecar_path,
    hydrate_knowledge_graph,
    load_full_sidecar,
    load_sidecar,
    resolve_sidecar_for_gold_path,
    write_sidecar,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _sample_factor_assertion_dict(case_id: str, factor_id: str) -> Dict[str, Any]:
    """Construct a minimal valid FactorAssertion-shaped dict.

    The shape mirrors the positive-control fixture under
    ``data/eval_artifacts/positive_control/housing_repairs_social_v1_one_case_kg/``
    — keep them in lockstep when the FactorAssertion model evolves.
    """
    return {
        "factor_assertion_id": f"fa_test_{case_id}_{factor_id}",
        "factor_id": factor_id,
        "domain_id": "housing.repairs_social.v1",
        "claim_head_id": "repairs_damp_mould",
        "value": {"value_type": "boolean", "boolean": True},
        "value_type": "boolean",
        "confidence": 0.9,
        "polarity": "pro_claimant",
        "expected_effects": [],
        "maps_to_outcomes": ["maladministration", "service_failure"],
        "maps_to_remedies": [],
        "supported_by": [f"es_test_{case_id}_{factor_id}"],
        "refuted_by": [],
        "linked_events": [],
        "linked_issues": [],
        "source_span_refs": [f"es_test_{case_id}_{factor_id}"],
        "extraction_method": "llm_extracted",
        "extractor_version": "test/2026-05-08",
        "verifier_version": None,
        "requires_human_review": False,
    }


def _sample_evidence_span_dict(case_id: str, factor_id: str) -> Dict[str, Any]:
    return {
        "evidence_span_id": f"es_test_{case_id}_{factor_id}",
        "source_kind": "ombudsman_determination",
        "source_reference": case_id,
        "quote_text": "The resident reported damp and mould in the property.",
        "paragraph_range": None,
    }


# ---------------------------------------------------------------------------
# Sidecar I/O
# ---------------------------------------------------------------------------


def test_load_sidecar_missing_file_returns_empty_dict(tmp_path):
    """A non-existent sidecar must NOT raise — returning {} keeps the
    existing chunk-RAG fallback working when no factor data is yet
    available."""
    out = load_sidecar(tmp_path / "does-not-exist.json")
    assert out == {}


def test_write_then_load_round_trip(tmp_path):
    payload = {
        "case-A": [_sample_factor_assertion_dict("case-A", "hazard_or_disrepair_reported")],
        "case-B": [
            _sample_factor_assertion_dict("case-B", "hazard_or_disrepair_reported"),
            _sample_factor_assertion_dict("case-B", "landlord_notice_established"),
        ],
    }
    path = tmp_path / "x.factor_assertions.json"
    write_sidecar(
        path,
        domain_id="housing.repairs_social.v1",
        extractor_version="test/v1",
        factor_assertions_by_case_id=payload,
    )

    loaded = load_sidecar(path)
    assert set(loaded.keys()) == {"case-A", "case-B"}
    # Pydantic validation succeeded for every entry
    assert len(loaded["case-A"]) == 1
    assert len(loaded["case-B"]) == 2
    # Loaded items are FactorAssertion instances, not raw dicts
    fa = loaded["case-A"][0]
    assert fa.factor_id == "hazard_or_disrepair_reported"
    assert fa.confidence == 0.9


def test_write_load_round_trip_preserves_evidence_spans(tmp_path):
    factor_payload = {
        "case-A": [_sample_factor_assertion_dict("case-A", "hazard_or_disrepair_reported")]
    }
    span_payload = {
        "case-A": [_sample_evidence_span_dict("case-A", "hazard_or_disrepair_reported")]
    }
    path = tmp_path / "x.factor_assertions.json"
    write_sidecar(
        path,
        domain_id="housing.repairs_social.v1",
        extractor_version="test/v1",
        factor_assertions_by_case_id=factor_payload,
        evidence_spans_by_case_id=span_payload,
    )

    loaded = load_full_sidecar(path)
    assert set(loaded["factor_assertions_by_case_id"]) == {"case-A"}
    assert set(loaded["evidence_spans_by_case_id"]) == {"case-A"}
    span = loaded["evidence_spans_by_case_id"]["case-A"][0]
    assert span.evidence_span_id == "es_test_case-A_hazard_or_disrepair_reported"
    assert span.quote_text.startswith("The resident reported")


def test_unsupported_schema_version_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "v999",
                "domain_id": "housing.repairs_social.v1",
                "extractor_version": "test",
                "factor_assertions_by_case_id": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema_version"):
        load_sidecar(path)


def test_default_sidecar_path_layout(tmp_path):
    out = default_sidecar_path(tmp_path, "housing_repairs_social_v2_strict_clean.jsonl")
    assert out == (
        tmp_path
        / "data"
        / "eval_artifacts"
        / "factor_assertions"
        / "housing_repairs_social_v2_strict_clean.factor_assertions.json"
    )


def test_resolve_sidecar_for_gold_path_picks_canonical_location():
    """The canonical sidecar location must be derivable purely from the
    gold-corpus filename + repo root (no extra config)."""
    gold = (
        _REPO_ROOT
        / "data"
        / "gold_standard"
        / "housing_repairs_social_v2_strict_clean.jsonl"
    )
    sidecar = resolve_sidecar_for_gold_path(gold)
    assert sidecar.name == "housing_repairs_social_v2_strict_clean.factor_assertions.json"
    assert sidecar.parent.name == "factor_assertions"


# ---------------------------------------------------------------------------
# Hydration into the KnowledgeGraph — the load-bearing test
# ---------------------------------------------------------------------------


def test_hydrate_knowledge_graph_attaches_factor_assertions():
    """After hydration the KG must expose ``factor_assertions`` exactly
    where ``IssueRetriever._retrieve_via_factor_retriever`` reads it
    (line 307 of issue_retrieval.py: ``getattr(case_graph,
    "factor_assertions", []) or []``).
    """
    from kg_builder.models.graph import KnowledgeGraph

    sidecar_dict = {
        "case-K": [
            _sample_factor_assertion_dict("case-K", "hazard_or_disrepair_reported")
        ]
    }
    # The sidecar values in real loads are FactorAssertion Pydantic
    # instances. Use the load_sidecar pipeline so we exercise the same
    # type the runner attaches.
    from legal_core.graph.factor_assertion import FactorAssertion

    typed_sidecar = {
        cid: [FactorAssertion.model_validate(d) for d in lst]
        for cid, lst in sidecar_dict.items()
    }

    kg = KnowledgeGraph(case_id="case-K")
    assert kg.factor_assertions == []
    hydrate_knowledge_graph(kg, "case-K", typed_sidecar)

    # Exactly the attribute IssueRetriever reads
    assert getattr(kg, "factor_assertions", None) is not None
    assert len(kg.factor_assertions) == 1
    assert kg.factor_assertions[0].factor_id == "hazard_or_disrepair_reported"


def test_hydrate_knowledge_graph_attaches_evidence_spans():
    from kg_builder.models.graph import KnowledgeGraph
    from legal_core.graph.evidence_span import EvidenceSpan
    from legal_core.graph.factor_assertion import FactorAssertion

    typed_sidecar = {
        "factor_assertions_by_case_id": {
            "case-K": [
                FactorAssertion.model_validate(
                    _sample_factor_assertion_dict("case-K", "hazard_or_disrepair_reported")
                )
            ]
        },
        "evidence_spans_by_case_id": {
            "case-K": [
                EvidenceSpan.model_validate(
                    _sample_evidence_span_dict("case-K", "hazard_or_disrepair_reported")
                )
            ]
        },
    }

    kg = KnowledgeGraph(case_id="case-K")
    hydrate_knowledge_graph(kg, "case-K", typed_sidecar)

    assert len(kg.factor_assertions) == 1
    assert len(kg.evidence_spans) == 1
    assert kg.evidence_spans[0].quote_text.startswith("The resident reported")


def test_hydrate_knowledge_graph_no_op_for_missing_case():
    """When the sidecar has no entry for the case, the KG keeps its
    default empty list (i.e. legacy chunk-RAG fallback path is preserved)."""
    from kg_builder.models.graph import KnowledgeGraph

    kg = KnowledgeGraph(case_id="case-missing")
    sidecar = {"some-other-case": [_sample_factor_assertion_dict("x", "y")]}
    hydrate_knowledge_graph(kg, "case-missing", sidecar)
    assert kg.factor_assertions == []


def test_factor_retriever_input_uses_hydrated_kg_assertions():
    """End-to-end-ish: load a sidecar, hydrate a KG, then construct the
    very RetrievalControlInput the FactorRetriever consumes. The
    ``asserted_factors`` field must be non-empty — the ENTIRE point of
    case-side backfill.

    This is the load-bearing test: without it, the LLM run is wasted
    because the engine never sees the new data.
    """
    from kg_builder.models.graph import KnowledgeGraph
    from legal_core.graph.factor_assertion import FactorAssertion
    from llm_orchestrator.pipeline.factor_retrieval import (
        AuthorityPolicy,
        RetrievalControlInput,
    )

    typed_sidecar = {
        "case-EE": [
            FactorAssertion.model_validate(
                _sample_factor_assertion_dict("case-EE", "hazard_or_disrepair_reported")
            ),
            FactorAssertion.model_validate(
                _sample_factor_assertion_dict("case-EE", "landlord_notice_established")
            ),
        ]
    }
    kg = KnowledgeGraph(case_id="case-EE", domain_id="housing.repairs_social.v1")
    hydrate_knowledge_graph(kg, "case-EE", typed_sidecar)

    # This mirrors the construction in
    # ``IssueRetriever._retrieve_via_factor_retriever`` (line 307+)
    asserted_factors = list(getattr(kg, "factor_assertions", []) or [])
    assert len(asserted_factors) == 2

    control = RetrievalControlInput(
        domain_id="housing.repairs_social.v1",
        claim_head_id="repairs_damp_mould",
        issue_ids=["repairs_damp_mould"],
        asserted_factors=asserted_factors,
        target_outcomes=[],
        target_remedies=[],
        forum="ombudsman",
        authority_policy=AuthorityPolicy(),
        retrieval_profile_id="housing.repairs_social.v1",
    )
    # The pre-build_comparator_pack invariant the engine relies on —
    # without this, line 207 of factor_retrieval.py returns an empty pack
    # with fallback_reason="no_asserted_factors" and the KG path is dead.
    assert control.asserted_factors != []
    assert all(
        fa.domain_id == "housing.repairs_social.v1" for fa in control.asserted_factors
    )


# ---------------------------------------------------------------------------
# Idempotency check on the file format itself
# ---------------------------------------------------------------------------


def test_write_sidecar_is_byte_stable(tmp_path):
    """Writing the same payload twice must produce byte-identical files.

    This guards against accidental unstable serialisation (e.g. Python
    dict ordering churn) which would defeat downstream cache joins.
    """
    payload = {
        "z-case": [_sample_factor_assertion_dict("z-case", "hazard_or_disrepair_reported")],
        "a-case": [_sample_factor_assertion_dict("a-case", "hazard_or_disrepair_reported")],
    }
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    write_sidecar(
        path_a,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        factor_assertions_by_case_id=payload,
    )
    write_sidecar(
        path_b,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        factor_assertions_by_case_id=payload,
    )
    assert path_a.read_bytes() == path_b.read_bytes()


def test_schema_version_constant_matches_written_payload(tmp_path):
    """The exported SIDECAR_SCHEMA_VERSION constant must equal whatever
    write_sidecar embeds, otherwise external readers/consumers could see
    drift between code and on-disk format."""
    path = tmp_path / "x.json"
    write_sidecar(
        path,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        factor_assertions_by_case_id={},
    )
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == SIDECAR_SCHEMA_VERSION
