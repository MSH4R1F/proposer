"""Synthesise a deterministic `PredictionResult` per `(CaseFile, mode)`.

The live runner's `--dry-run` path uses this to produce structurally
valid predictions without touching an LLM. The output is NOT accurate —
it's a fixture-grade stand-in that exercises the GoldCase → CaseFile →
PredictionResult → adapter → eval.ablate pipeline end-to-end.

Determinism is achieved by hashing `case_id` (so identical inputs return
identical outputs across runs and machines). Mode differentiation gives
each `PredictionMode` a slightly different confidence band so the
comparison report shows non-degenerate values per mode.
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm_orchestrator.models.case_file import CaseFile
    from llm_orchestrator.models.prediction_v2 import (
        PredictionMode,
        PredictionResult,
    )


# Per-mode confidence anchors. Hybrid most confident; LLM_ONLY least.
# Picked so all four values are distinct (test guards against accidental
# collapse if anchors are edited).
_MODE_CONFIDENCE = {
    "hybrid": 0.85,
    "rag_only": 0.72,
    "kg_only": 0.65,
    "llm_only": 0.55,
}


def make_stub_prediction(case_file: "CaseFile", mode) -> "PredictionResult":
    """Return a deterministic, mode-differentiated stub PredictionResult."""
    from llm_orchestrator.models.prediction_v2 import (
        IssueOutcome,
        IssuePrediction,
        OutcomeType,
        PipelineMetadata,
        PredictionResult,
    )

    mode_value = getattr(mode, "value", mode)
    base_conf = _MODE_CONFIDENCE.get(mode_value, 0.5)

    seed = _seed_for(case_file.case_id, mode_value)
    # Jitter ±0.04 around the per-mode anchor, deterministic per (case, mode).
    jitter = ((seed % 100) / 100.0 - 0.5) * 0.08
    overall_conf = max(0.0, min(1.0, base_conf + jitter))

    # Outcome cycles between TENANT_WIN / LANDLORD_WIN / SPLIT to cover all
    # branches the adapter handles. Driven by the seed so it's stable.
    outcome_idx = seed % 3
    overall_outcome = (
        OutcomeType.TENANT_WIN,
        OutcomeType.LANDLORD_WIN,
        OutcomeType.SPLIT,
    )[outcome_idx]

    issue_predictions = []
    for i, issue in enumerate(case_file.issues):
        per_issue_conf = max(0.0, min(1.0, overall_conf + (i * 0.01)))
        issue_outcome = (
            IssueOutcome.TENANT_WINS,
            IssueOutcome.LANDLORD_WINS,
            IssueOutcome.SPLIT,
        )[(seed + i) % 3]
        issue_predictions.append(
            IssuePrediction(
                issue_type=issue,
                outcome=issue_outcome,
                raw_confidence=per_issue_conf,
                predicted_amount=float(case_file.dispute_amount or 0)
                / max(1, len(case_file.issues)),
                reasoning="Stub reasoning (eval --dry-run; no LLM was called).",
            )
        )

    # Recovery amounts split deterministically on the dispute total.
    dispute_total = float(case_file.dispute_amount or 0)
    if overall_outcome is OutcomeType.LANDLORD_WIN:
        landlord_recovery = dispute_total
        tenant_recovery = 0.0
    elif overall_outcome is OutcomeType.TENANT_WIN:
        landlord_recovery = 0.0
        tenant_recovery = dispute_total
    else:
        landlord_recovery = dispute_total / 2
        tenant_recovery = dispute_total / 2

    return PredictionResult(
        case_id=case_file.case_id,
        overall_outcome=overall_outcome,
        overall_confidence=overall_conf,
        outcome_summary=f"Stub prediction (mode={mode_value}).",
        tenant_recovery_amount=tenant_recovery,
        landlord_recovery_amount=landlord_recovery,
        issue_predictions=issue_predictions,
        pipeline_metadata=PipelineMetadata(mode=mode_value),
    )


def _seed_for(case_id: str, mode_value: str) -> int:
    """Stable integer seed from (case_id, mode). Hash-based to avoid
    perfect alignment with case-id sort order."""
    payload = f"{case_id}|{mode_value}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:4], "big")
