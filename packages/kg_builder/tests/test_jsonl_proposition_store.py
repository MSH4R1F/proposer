"""Tests for ``kg_builder.storage.jsonl_proposition_store``.

Verifies the JSONL-backed proposition store satisfies the duck-typed
``PropositionGraphRepository`` Protocol that
``llm_orchestrator.pipeline.factor_retrieval.FactorRetriever`` consumes.

The load-bearing test
``test_search_by_issue_tags_returns_propositions_factor_retriever_can_score``
proves that asking the store for propositions seeded by
``housing.repairs_social.v1`` returns rows whose ``factor_ids`` survive
Pydantic validation — i.e. ``FactorRetriever._score_proposition`` will
read non-empty ``factor_ids`` and produce non-zero ``factor_overlap``
scores. Without that, the entire architectural gate stays closed and
the LLM proposition tagging is wasted.
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from kg_builder.propositions.models import Proposition
from kg_builder.storage.jsonl_proposition_store import (
    JsonlPropositionStore,
    load_propositions_from_jsonl,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_POSITIVE_CONTROL_PROPS = (
    _REPO_ROOT
    / "data"
    / "eval_artifacts"
    / "positive_control"
    / "housing_repairs_social_v1_one_case_kg"
    / "propositions.json"
)


def _make_proposition(
    *,
    case_reference: str,
    text: str = "Sample factual claim about damp and mould.",
    source_passage: str = "Sample source passage referenced by the proposition.",
    issue_tags: list[str] | None = None,
    factor_ids: list[str] | None = None,
) -> Proposition:
    """Build a minimal valid Proposition for tests."""
    return Proposition(
        proposition_id=uuid4(),
        document_id=uuid4(),
        case_reference=case_reference,
        text=text,
        source_passage=source_passage,
        paragraph_ref="P1",
        proposition_type="fact",
        issue_tags=list(issue_tags or []),
        entities=[],
        confidence=0.85,
        factor_ids=list(factor_ids or []),
        outcome_component_ids=[],
        remedy_component_ids=[],
        claim_head_ids=[],
        authority_level="comparator",
        proposition_role="fact_comparator",
    )


# ---------------------------------------------------------------------------
# load_propositions_from_jsonl
# ---------------------------------------------------------------------------


def test_load_propositions_from_jsonl_round_trip(tmp_path):
    """A JSONL written from Pydantic Propositions must round-trip cleanly."""
    props = [
        _make_proposition(
            case_reference="case-A",
            issue_tags=["housing.repairs_social.v1"],
            factor_ids=["repair_responsibility_established"],
        ),
        _make_proposition(
            case_reference="case-B",
            issue_tags=["housing.repairs_social.v1"],
            factor_ids=["hazard_or_disrepair_reported", "landlord_notice_established"],
        ),
    ]
    path = tmp_path / "props.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for p in props:
            fh.write(p.model_dump_json() + "\n")

    loaded = load_propositions_from_jsonl(path)
    assert len(loaded) == 2
    assert {p.case_reference for p in loaded} == {"case-A", "case-B"}
    assert loaded[0].factor_ids == ["repair_responsibility_established"]


def test_load_propositions_skips_blank_lines(tmp_path):
    """Blank/whitespace-only lines must be ignored, not parsed."""
    p = _make_proposition(case_reference="solo", issue_tags=["x.y"])
    path = tmp_path / "props.jsonl"
    text = "\n  \n" + p.model_dump_json() + "\n\n"
    path.write_text(text, encoding="utf-8")
    loaded = load_propositions_from_jsonl(path)
    assert len(loaded) == 1
    assert loaded[0].case_reference == "solo"


def test_load_propositions_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_propositions_from_jsonl(tmp_path / "no-such-file.jsonl")


def test_load_propositions_invalid_json_raises(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{not valid json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_propositions_from_jsonl(path)


# ---------------------------------------------------------------------------
# JsonlPropositionStore — basic invariants
# ---------------------------------------------------------------------------


def test_store_constructor_accepts_empty_iterable():
    store = JsonlPropositionStore([])
    assert len(store) == 0
    assert store.propositions == []


def test_store_indexes_by_issue_tag():
    store = JsonlPropositionStore(
        [
            _make_proposition(
                case_reference="A",
                issue_tags=["t1", "t2"],
                factor_ids=["f1"],
            ),
            _make_proposition(
                case_reference="B",
                issue_tags=["t2"],
                factor_ids=["f2"],
            ),
            _make_proposition(
                case_reference="C",
                issue_tags=["t3"],
                factor_ids=["f3"],
            ),
        ]
    )
    assert len(store) == 3


# ---------------------------------------------------------------------------
# search_by_issue_tags — the load-bearing duck-type method
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_by_issue_tags_returns_overlapping_propositions():
    p1 = _make_proposition(
        case_reference="A",
        issue_tags=["housing.repairs_social.v1"],
        factor_ids=["repair_responsibility_established"],
    )
    p2 = _make_proposition(
        case_reference="B",
        issue_tags=["housing.repairs_social.v1"],
        factor_ids=["hazard_or_disrepair_reported"],
    )
    p3 = _make_proposition(
        case_reference="C",
        issue_tags=["housing.deposit.v1"],
        factor_ids=["deposit_protection"],
    )
    store = JsonlPropositionStore([p1, p2, p3])

    out = await store.search_by_issue_tags(["housing.repairs_social.v1"])
    out_refs = {p.case_reference for p in out}
    assert out_refs == {"A", "B"}


@pytest.mark.asyncio
async def test_search_by_issue_tags_empty_tags_returns_empty():
    """Mirrors FactorRetriever._seed_candidates: empty issue_ids => no seed."""
    store = JsonlPropositionStore(
        [
            _make_proposition(
                case_reference="A", issue_tags=["x"], factor_ids=["f"]
            )
        ]
    )
    out = await store.search_by_issue_tags([])
    assert out == []


@pytest.mark.asyncio
async def test_search_by_issue_tags_nonmatching_returns_empty():
    store = JsonlPropositionStore(
        [
            _make_proposition(
                case_reference="A",
                issue_tags=["housing.repairs_social.v1"],
                factor_ids=["f"],
            )
        ]
    )
    out = await store.search_by_issue_tags(["totally-different-domain.v1"])
    assert out == []


@pytest.mark.asyncio
async def test_search_by_issue_tags_dedupes_propositions_with_multiple_matching_tags():
    """A single proposition listed under two requested tags must appear once."""
    p = _make_proposition(
        case_reference="A",
        issue_tags=["t1", "t2"],
        factor_ids=["f"],
    )
    store = JsonlPropositionStore([p])
    out = await store.search_by_issue_tags(["t1", "t2"])
    assert len(out) == 1
    assert out[0].case_reference == "A"


@pytest.mark.asyncio
async def test_search_by_issue_tags_respects_limit():
    props = [
        _make_proposition(
            case_reference=f"case-{i}",
            issue_tags=["t"],
            factor_ids=["f"],
        )
        for i in range(10)
    ]
    store = JsonlPropositionStore(props)
    out = await store.search_by_issue_tags(["t"], limit=3)
    assert len(out) == 3


# ---------------------------------------------------------------------------
# Positive-control fixture round-trip
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _POSITIVE_CONTROL_PROPS.exists(),
    reason="positive-control fixture missing in this checkout",
)
def test_positive_control_propositions_load_through_store(tmp_path):
    """Convert the positive-control JSON-array fixture to JSONL and load it.

    The 8 hand-tagged propositions in
    ``data/eval_artifacts/positive_control/.../propositions.json`` have
    populated ``factor_ids`` lists that mirror what the tagger CLI must
    produce for each real case. If this round-trip breaks, every
    downstream stage breaks with it.
    """
    fixture = json.loads(_POSITIVE_CONTROL_PROPS.read_text(encoding="utf-8"))
    assert isinstance(fixture, list) and len(fixture) >= 1

    jsonl_path = tmp_path / "fixture.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for entry in fixture:
            # Re-serialise via Pydantic so the JSONL on disk matches what
            # the tagger CLI would write.
            prop = Proposition.model_validate(entry)
            fh.write(prop.model_dump_json() + "\n")

    store = JsonlPropositionStore.from_path(jsonl_path)
    assert len(store) == len(fixture)
    # All 8 are tagged with this domain
    every_factor_ids = [p.factor_ids for p in store.propositions]
    assert all(len(f) > 0 for f in every_factor_ids), (
        "fixture must have populated factor_ids; without that the rest of "
        "the JSONL pipeline can't measure factor_overlap lift"
    )


# ---------------------------------------------------------------------------
# End-to-end-ish: FactorRetriever consumes the store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_satisfies_factor_retriever_seed_pass():
    """``FactorRetriever._seed_candidates`` calls
    ``repository.search_by_issue_tags(tags=..., limit=...)``. Verify our
    store responds with the right shape so the engine's seam works.

    This is the load-bearing assertion for Piece 1: if this passes, the
    Postgres-or-JSONL decision is purely an engineering one — the
    architectural test is invariant.
    """
    p_match = _make_proposition(
        case_reference="match",
        issue_tags=["housing.repairs_social.v1"],
        factor_ids=[
            "repair_responsibility_established",
            "hazard_or_disrepair_reported",
        ],
    )
    p_other = _make_proposition(
        case_reference="other",
        issue_tags=["unrelated.domain"],
        factor_ids=["irrelevant"],
    )
    store = JsonlPropositionStore([p_match, p_other])

    seeded = await store.search_by_issue_tags(
        tags=["housing.repairs_social.v1"], limit=50
    )
    assert len(seeded) == 1
    seed = seeded[0]
    assert seed.case_reference == "match"
    # The exact field FactorRetriever._score_proposition reads.
    assert "repair_responsibility_established" in seed.factor_ids
