"""Tests for ``scripts/eval/promote_factor_annotations_to_gold.py``.

All tests are offline: no real LLM calls, no network I/O. The promoter
itself never calls an LLM — it consumes a JSONL of pre-existing
Annotation rows and produces FactorAssertion dicts.

Run from the repo root::

    pytest scripts/eval/tests/test_promote_factor_annotations.py -v
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


# ---------------------------------------------------------------------------
# Path bootstrap (same shape as the sibling test files in this dir)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "scripts" / "eval"
_PACKAGES = str(_REPO_ROOT / "packages")

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if _PACKAGES not in sys.path:
    sys.path.insert(0, _PACKAGES)


def _load_promoter_module():
    key = "promote_factor_annotations_to_gold"
    if key in sys.modules and hasattr(sys.modules[key], "promote_annotations"):
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(
        key, _SCRIPTS / "promote_factor_annotations_to_gold.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def promoter():
    return _load_promoter_module()


@pytest.fixture(scope="module")
def fixture_iaa_path() -> Path:
    return (
        _REPO_ROOT
        / "data"
        / "eval_artifacts"
        / "gold_annotation"
        / "housing.repairs_social.v1-gold-annotations-n3-seed42-2026-05-07.jsonl"
    )


# ---------------------------------------------------------------------------
# Helpers — build synthetic annotation rows that exactly match the IAA shape
# ---------------------------------------------------------------------------


def _annotation(
    *,
    case_id: str,
    factor_id: str,
    annotator_id: str,
    boolean: bool | None = None,
    enum: str | None = None,
    duration_days: int | None = None,
    is_null: bool = False,
    confidence: float = 0.9,
    value_type: str = "boolean",
    requires_human_review: bool = False,
    source_span: str | None = None,
) -> Dict[str, Any]:
    return {
        "case_id": case_id,
        "factor_id": factor_id,
        "annotator_id": annotator_id,
        "value": {
            "boolean": boolean,
            "enum": enum,
            "number": None,
            "duration_days": duration_days,
            "is_null": is_null,
        },
        "value_type": value_type,
        "confidence": confidence,
        "source_span": source_span,
        "requires_human_review": requires_human_review,
        "reasoning": "fixture",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_promote_existing_iaa_fixture_round_trips_pydantic(
    promoter, fixture_iaa_path
):
    """Run promoter on the 6-row IAA fixture and validate every emitted dict."""
    if not fixture_iaa_path.exists():
        pytest.skip(f"IAA fixture missing at {fixture_iaa_path}")

    from legal_core.graph.factor_assertion import FactorAssertion  # noqa: PLC0415

    rows = promoter._read_annotations_jsonl(fixture_iaa_path)
    out = promoter.promote_annotations(
        rows,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        min_confidence=0.5,
    )

    # Fixture is 3 cases × 1 factor × 2 annotators. Each pair has one
    # extraction_failed (is_null) and one real value. The promoter must
    # tie-break to the real value (higher confidence, non-null).
    assert set(out.keys()) == {"c0", "c1", "c4"}
    for case_id, fas in out.items():
        assert len(fas) == 1, f"expected 1 FA per case, got {len(fas)} for {case_id}"
        # Validate Pydantic round-trip
        fa = FactorAssertion.model_validate(fas[0])
        assert fa.factor_id == "repair_responsibility_established"
        assert fa.value.boolean is True
        assert fa.confidence == 0.9
        # ann-0 was is_null with confidence 0.0; ann-1 was the real
        # value at confidence 0.9. They DISAGREE → review flag must be set.
        assert fa.requires_human_review is True
        # Stable ID format
        assert fa.factor_assertion_id.startswith("fa_promoted_")
        # Synthetic supporting span
        assert len(fa.supported_by) == 1
        assert fa.supported_by[0].startswith("es_promoted_")


def test_disagreement_between_annotators_triggers_review_flag(promoter):
    """When two annotators emit different .value, the canonical row MUST be
    flagged for human review even when confidences are high."""
    rows = [
        _annotation(
            case_id="case-1",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m1",
            boolean=True,
            confidence=0.9,
        ),
        _annotation(
            case_id="case-1",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m2",
            boolean=False,
            confidence=0.8,
        ),
    ]
    out = promoter.promote_annotations(
        rows,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        min_confidence=0.5,
    )
    fas = out["case-1"]
    assert len(fas) == 1
    assert fas[0]["requires_human_review"] is True
    # Higher-confidence wins → True
    assert fas[0]["value"]["boolean"] is True


def test_low_confidence_triggers_review_flag(promoter):
    """Even with full annotator agreement, confidence < min_confidence must
    set requires_human_review=True so the eval reviewer can catch it."""
    rows = [
        _annotation(
            case_id="case-2",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m1",
            boolean=True,
            confidence=0.4,
        ),
        _annotation(
            case_id="case-2",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m2",
            boolean=True,
            confidence=0.45,
        ),
    ]
    out = promoter.promote_annotations(
        rows,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        min_confidence=0.5,
    )
    assert out["case-2"][0]["requires_human_review"] is True


def test_full_agreement_high_confidence_is_clean(promoter):
    """Both annotators agree at confidence >= min_confidence → no review flag."""
    rows = [
        _annotation(
            case_id="case-3",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m1",
            boolean=True,
            confidence=0.95,
        ),
        _annotation(
            case_id="case-3",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m2",
            boolean=True,
            confidence=0.9,
        ),
    ]
    out = promoter.promote_annotations(
        rows,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        min_confidence=0.5,
    )
    assert out["case-3"][0]["requires_human_review"] is False
    assert out["case-3"][0]["value"]["boolean"] is True


def test_promoter_is_idempotent(promoter):
    """Running the promoter twice on the same input must produce byte-equal output.

    Idempotency is critical: the eval runner re-reads the sidecar each run,
    and any churn in factor_assertion_ids would invalidate downstream
    artifact joins.
    """
    rows = [
        _annotation(
            case_id="case-4",
            factor_id="repair_attempted",
            annotator_id="m1",
            boolean=True,
            confidence=0.9,
        ),
        _annotation(
            case_id="case-4",
            factor_id="repair_attempted",
            annotator_id="m2",
            boolean=True,
            confidence=0.8,
        ),
        _annotation(
            case_id="case-5",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m1",
            boolean=False,
            confidence=0.7,
        ),
        _annotation(
            case_id="case-5",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m2",
            boolean=False,
            confidence=0.85,
        ),
    ]
    out_a = promoter.promote_annotations(
        rows,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        min_confidence=0.5,
    )
    out_b = promoter.promote_annotations(
        rows,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        min_confidence=0.5,
    )
    # JSON-serialise with sort_keys to compare bytes — tests both content
    # AND ordering stability (matching what write_sidecar does).
    assert json.dumps(out_a, sort_keys=True) == json.dumps(out_b, sort_keys=True)
    # And factor_assertion_ids are stable across runs
    assert (
        out_a["case-4"][0]["factor_assertion_id"]
        == out_b["case-4"][0]["factor_assertion_id"]
    )


def test_canonical_id_does_not_collide_across_factors(promoter):
    """The deterministic id depends on case_id AND factor_id, so two
    factors on the same case must get distinct ids."""
    rows = [
        _annotation(
            case_id="case-6",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m1",
            boolean=True,
            confidence=0.9,
        ),
        _annotation(
            case_id="case-6",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m2",
            boolean=True,
            confidence=0.9,
        ),
        _annotation(
            case_id="case-6",
            factor_id="repair_attempted",
            annotator_id="m1",
            boolean=False,
            confidence=0.9,
        ),
        _annotation(
            case_id="case-6",
            factor_id="repair_attempted",
            annotator_id="m2",
            boolean=False,
            confidence=0.9,
        ),
    ]
    out = promoter.promote_annotations(
        rows,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        min_confidence=0.5,
    )
    fas = out["case-6"]
    assert len(fas) == 2
    ids = {r["factor_assertion_id"] for r in fas}
    assert len(ids) == 2  # no collision


def test_sidecar_write_then_load_round_trip(tmp_path, promoter):
    """End-to-end: promote → write_sidecar → load_sidecar → matches input."""
    rows = [
        _annotation(
            case_id="case-rt",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m1",
            boolean=True,
            confidence=0.9,
        ),
        _annotation(
            case_id="case-rt",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m2",
            boolean=True,
            confidence=0.85,
        ),
    ]
    out = promoter.promote_annotations(
        rows,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        min_confidence=0.5,
    )
    from eval.factor_assertion_sidecar import (  # noqa: PLC0415
        load_sidecar,
        write_sidecar,
    )

    sidecar_path = tmp_path / "x.factor_assertions.json"
    write_sidecar(
        sidecar_path,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        factor_assertions_by_case_id=out,
    )
    loaded = load_sidecar(sidecar_path)
    assert set(loaded.keys()) == {"case-rt"}
    fa = loaded["case-rt"][0]
    # Loaded object is now a FactorAssertion Pydantic instance
    assert fa.factor_id == "hazard_or_disrepair_reported"
    assert fa.value.boolean is True


def test_canonical_value_is_null_skips_emission(promoter):
    """When BOTH annotators agree on is_null=True, no FactorAssertion is
    emitted (a null value carries no signal for the FactorRetriever)."""
    rows = [
        _annotation(
            case_id="case-null",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m1",
            is_null=True,
            confidence=0.9,
        ),
        _annotation(
            case_id="case-null",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m2",
            is_null=True,
            confidence=0.9,
        ),
    ]
    out = promoter.promote_annotations(
        rows,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        min_confidence=0.5,
    )
    # Either no entry for the case at all OR an empty list — both are
    # acceptable representations of "no signal".
    assert "case-null" not in out or out["case-null"] == []


def test_source_span_promotes_to_evidence_span(promoter):
    spans: Dict[str, List[Dict[str, Any]]] = {}
    rows = [
        _annotation(
            case_id="case-span",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m1",
            boolean=True,
            confidence=0.9,
            source_span="Resident reported damp and mould in the bedroom.",
        ),
        _annotation(
            case_id="case-span",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m2",
            boolean=True,
            confidence=0.8,
            source_span="Resident reported damp and mould in the bedroom.",
        ),
    ]

    out = promoter.promote_annotations(
        rows,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        min_confidence=0.5,
        evidence_spans_by_case_id=spans,
    )

    fa = out["case-span"][0]
    evidence = spans["case-span"][0]
    assert evidence["evidence_span_id"] == fa["supported_by"][0]
    assert evidence["evidence_span_id"] == fa["source_span_refs"][0]
    assert evidence["source_kind"] == "ombudsman_determination"
    assert evidence["source_reference"] == "case-span"
    assert evidence["quote_text"] == "Resident reported damp and mould in the bedroom."


def test_canonical_source_span_comes_from_selected_annotator(promoter):
    spans: Dict[str, List[Dict[str, Any]]] = {}
    rows = [
        _annotation(
            case_id="case-canonical-span",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m1",
            boolean=True,
            confidence=0.6,
            source_span="Lower confidence quote.",
        ),
        _annotation(
            case_id="case-canonical-span",
            factor_id="hazard_or_disrepair_reported",
            annotator_id="m2",
            boolean=False,
            confidence=0.95,
            source_span="Higher confidence quote.",
        ),
    ]

    out = promoter.promote_annotations(
        rows,
        domain_id="housing.repairs_social.v1",
        extractor_version="test",
        min_confidence=0.5,
        evidence_spans_by_case_id=spans,
    )

    assert out["case-canonical-span"][0]["value"]["boolean"] is False
    assert out["case-canonical-span"][0]["requires_human_review"] is True
    assert spans["case-canonical-span"][0]["quote_text"] == "Higher confidence quote."
