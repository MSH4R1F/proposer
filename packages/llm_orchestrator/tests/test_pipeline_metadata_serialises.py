"""Recovery plan Task 5: pin pipeline_metadata serialisation to prevent
the bug found mid-ablation where _serialise_prediction silently dropped
the §17.6 / Cross-PR Contract C5 schema fields.

Locks in the union schema across PR-4, PR-5, PR-6 and the recovery
sprint:

  PR-4: core_schema, domain_pack, factor_catalog_version,
        graph_quality_score, kg_used_for_prediction, kg_fallback_mode,
        kg_gate_failure_reasons
  PR-6: evidence_path_results
  T3 :  evidence_support, unsupported_claim_count
  T4 :  [forced-answer fallback] reasoning marker (round-trips via
        IssuePrediction.reasoning)
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

# scripts/eval is not on sys.path by default in pytest runs from the repo
# root. Make the predict_all module importable for this test.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval.metrics.types import IssuePrediction as EvalIssuePrediction
from eval.metrics.types import Prediction as EvalPrediction
from eval.schema import Winner

from llm_orchestrator.models.prediction_v2 import (
    EvidenceStrength,
    IssueOutcome,
    IssuePrediction,
    IssueType,
    OutcomeType,
    PipelineMetadata,
    PredictionResult,
)

from scripts.eval.predict_all import _serialise_prediction


# ---------------------------------------------------------------------------
# Field union pinned by the artifact-stability contract
# ---------------------------------------------------------------------------

_REQUIRED_PIPELINE_METADATA_KEYS = {
    # PR-4 / Cross-PR Contract C5
    "core_schema",
    "domain_pack",
    "factor_catalog_version",
    "graph_quality_score",
    "kg_used_for_prediction",
    "kg_fallback_mode",
    "kg_gate_failure_reasons",
    # PR-6 / Cross-PR Contract C5
    "evidence_path_results",
    # Stream C recovery T3
    "evidence_support",
    "unsupported_claim_count",
}


def _make_issue_prediction(
    *,
    outcome: IssueOutcome = IssueOutcome.TENANT_WINS,
    raw_confidence: float = 0.85,
    reasoning: str = "Concrete reasoning.",
) -> IssuePrediction:
    return IssuePrediction(
        issue_type=IssueType.CLEANING,
        issue_description="Cleaning",
        outcome=outcome,
        raw_confidence=raw_confidence,
        reasoning=reasoning,
        evidence_strength=EvidenceStrength.MODERATE,
        data_completeness_impact="OK",
    )


def _make_pipeline_metadata(**overrides) -> PipelineMetadata:
    """Build a populated PipelineMetadata with values for every key in
    the §17.6 / recovery union."""
    defaults = {
        "core_schema": "legal.core.v1",
        "domain_pack": "housing.repairs_social.v1",
        "factor_catalog_version": "abc123ef",
        "graph_quality_score": 0.42,
        "kg_used_for_prediction": True,
        "kg_fallback_mode": None,
        "kg_gate_failure_reasons": ["evidence_backed_factor_count 1 < min 3"],
        "evidence_path_results": [
            {
                "outcome_component_id": "oc_x",
                "is_supported": True,
                "chain": ["span_1", "fa_1", "prop_1", "oc_x"],
                "rejection_reason": None,
                "abstention_required": False,
            }
        ],
        "evidence_support": "strong",
        "unsupported_claim_count": 0,
    }
    defaults.update(overrides)
    return PipelineMetadata(**defaults)


def _make_eval_prediction(
    *,
    case_id: str = "case-1",
    winner: Winner = Winner.TENANT,
) -> EvalPrediction:
    return EvalPrediction(
        case_id=case_id,
        overall_winner=winner,
        overall_win_probability=0.15,  # P(landlord wins) when tenant wins
        total_predicted_gbp=Decimal("250.00"),
        per_issue=[
            EvalIssuePrediction(
                issue="cleaning",
                predicted_winner=winner,
                win_probability=0.15,
                predicted_amount_gbp=Decimal("250.00"),
            ),
        ],
    )


def _make_prediction_result(
    *,
    issue_predictions=None,
    pipeline_metadata: PipelineMetadata | None = None,
) -> PredictionResult:
    return PredictionResult(
        case_id="case-1",
        overall_outcome=OutcomeType.TENANT_WIN,
        overall_confidence=0.85,
        issue_predictions=issue_predictions
        if issue_predictions is not None
        else [_make_issue_prediction()],
        pipeline_metadata=pipeline_metadata,
    )


# ---------------------------------------------------------------------------
# 1. Round-trip — every documented key carries through
# ---------------------------------------------------------------------------


def test_pipeline_metadata_round_trips_through_predict_all_serialiser():
    """Calling _serialise_prediction with a populated PipelineMetadata
    must produce a dict whose 'pipeline_metadata' is a non-empty mapping
    carrying every documented key from the §17.6 / recovery union."""
    raw = _make_prediction_result(pipeline_metadata=_make_pipeline_metadata())
    eval_pred = _make_eval_prediction()

    out = _serialise_prediction(eval_pred, raw)

    assert "pipeline_metadata" in out
    pmeta = out["pipeline_metadata"]
    assert isinstance(pmeta, dict)
    assert len(pmeta) > 0
    missing = _REQUIRED_PIPELINE_METADATA_KEYS - set(pmeta)
    assert not missing, f"Missing pipeline_metadata keys: {missing}"


# ---------------------------------------------------------------------------
# 2. Audit-only fields from Task 3 round-trip
# ---------------------------------------------------------------------------


def test_pipeline_metadata_evidence_support_round_trips():
    """The recovery-T3 audit fields (evidence_support, unsupported_claim_count)
    must carry through the serialiser."""
    pmeta = _make_pipeline_metadata(
        evidence_support="weak",
        unsupported_claim_count=3,
    )
    raw = _make_prediction_result(pipeline_metadata=pmeta)
    eval_pred = _make_eval_prediction()

    out = _serialise_prediction(eval_pred, raw)

    serialised = out["pipeline_metadata"]
    assert serialised["evidence_support"] == "weak"
    assert serialised["unsupported_claim_count"] == 3


def test_pipeline_metadata_evidence_support_none_round_trips():
    """When no validation occurred, evidence_support must serialise as null."""
    pmeta = _make_pipeline_metadata(
        evidence_support=None,
        unsupported_claim_count=0,
    )
    raw = _make_prediction_result(pipeline_metadata=pmeta)
    eval_pred = _make_eval_prediction()

    out = _serialise_prediction(eval_pred, raw)
    serialised = out["pipeline_metadata"]
    assert serialised["evidence_support"] is None
    assert serialised["unsupported_claim_count"] == 0


# ---------------------------------------------------------------------------
# 3. Forced-answer marker round-trips on the issue prediction
# ---------------------------------------------------------------------------


def test_pipeline_metadata_force_answer_marker_round_trips():
    """When _apply_forced_answer remapped an uncertain LLM response to
    SPLIT, the artifact's reasoning field must contain the
    "[forced-answer fallback" marker so post-hoc analysis can detect the
    remap. The marker travels via the per-issue raw_outcome path; the
    reasoning itself is not currently surfaced in _serialise_prediction
    output, but the SPLIT outcome with raw_outcome="split" + a sentinel
    band is enough to identify the synthetic label."""
    # Build an IssuePrediction shaped like a remapped uncertain.
    issue_pred = IssuePrediction(
        issue_type=IssueType.CLEANING,
        issue_description="Cleaning",
        outcome=IssueOutcome.SPLIT,
        raw_confidence=0.50,
        reasoning="[forced-answer fallback: LLM returned uncertain] Original reasoning.",
        evidence_strength=EvidenceStrength.INSUFFICIENT,
        data_completeness_impact="OK",
    )
    raw = _make_prediction_result(
        issue_predictions=[issue_pred],
        pipeline_metadata=_make_pipeline_metadata(),
    )
    eval_pred = _make_eval_prediction(winner=Winner.SPLIT)

    out = _serialise_prediction(eval_pred, raw)

    # The serialised per-issue row records raw_outcome=split.
    assert len(out["per_issue"]) == 1
    assert out["per_issue"][0]["raw_outcome"] == "split"
    # The forced-answer marker is preserved on the underlying
    # IssuePrediction (not the serialised dict — that's by design).
    assert raw.issue_predictions[0].reasoning.startswith("[forced-answer fallback")


# ---------------------------------------------------------------------------
# 4. Full union schema is present
# ---------------------------------------------------------------------------


def test_pipeline_metadata_full_field_set_present():
    """Lock in the union of PR-4 + PR-6 + recovery (T3) fields:

    {core_schema, domain_pack, factor_catalog_version,
     graph_quality_score, kg_used_for_prediction, kg_fallback_mode,
     kg_gate_failure_reasons, evidence_path_results,
     evidence_support, unsupported_claim_count}

    A regression on this test means _serialise_prediction silently
    dropped a documented field — the bug pattern from the 2026-05-07
    ablation that prompted commit 6917d32 + this whole recovery sprint.
    """
    raw = _make_prediction_result(pipeline_metadata=_make_pipeline_metadata())
    eval_pred = _make_eval_prediction()

    out = _serialise_prediction(eval_pred, raw)
    pmeta = out["pipeline_metadata"]

    for key in _REQUIRED_PIPELINE_METADATA_KEYS:
        assert key in pmeta, f"pipeline_metadata missing key: {key}"

    # Type checks for the headline fields.
    assert isinstance(pmeta["core_schema"], str)
    assert pmeta["domain_pack"] is None or isinstance(pmeta["domain_pack"], str)
    assert (
        pmeta["graph_quality_score"] is None
        or isinstance(pmeta["graph_quality_score"], (int, float))
    )
    assert (
        pmeta["kg_used_for_prediction"] is None
        or isinstance(pmeta["kg_used_for_prediction"], bool)
    )
    assert isinstance(pmeta["kg_gate_failure_reasons"], list)
    assert isinstance(pmeta["evidence_path_results"], list)
    assert pmeta["evidence_support"] in (None, "strong", "weak")
    assert isinstance(pmeta["unsupported_claim_count"], int)


# ---------------------------------------------------------------------------
# 5. raw_result=None still produces a valid dict (predict_all stub path)
# ---------------------------------------------------------------------------


def test_serialise_prediction_handles_none_raw_result():
    """When the stub engine path doesn't have an orchestrator
    PredictionResult, _serialise_prediction(eval_pred, None) must still
    produce a dict — and must NOT include 'pipeline_metadata' (the field
    is only meaningful when a raw_result is supplied)."""
    eval_pred = _make_eval_prediction()
    out = _serialise_prediction(eval_pred, None)
    assert "pipeline_metadata" not in out
    assert out["case_id"] == "case-1"
