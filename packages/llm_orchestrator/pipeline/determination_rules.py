"""Deterministic determination post-rules over FactorAssertions.

Rules-then-LLM: the LLM proposes a determination; near-mechanical Ombudsman
criteria (jurisdiction, aggravator-driven severity, prior-offer redress) are
then applied over typed, evidence-backed FactorAssertions. Conservative by
construction: rules only fire on factors with confidence >= MIN_FACTOR_CONFIDENCE,
and the layer is a no-op when no factors are present (llm_only / rag_only).
"""
from __future__ import annotations

from typing import Any, Optional, Sequence, Tuple

from llm_orchestrator.models.prediction_v2 import Determination

MIN_FACTOR_CONFIDENCE = 0.7
SEVERE_DELAY_DAYS = 365
MIN_AGGRAVATORS_FOR_SEVERE = 2


def _confident(factors: Sequence[Any], factor_id: str) -> Optional[Any]:
    # First-match semantics: returns the first FactorAssertion for factor_id
    # that meets the confidence threshold. Callers assume at most one
    # high-confidence assertion per factor_id per case; conflicting duplicates
    # resolve first-wins by list order.
    for fa in factors:
        if getattr(fa, "factor_id", None) == factor_id and (
            getattr(fa, "confidence", 0.0) >= MIN_FACTOR_CONFIDENCE
        ):
            return fa
    return None


def _bool_factor(factors: Sequence[Any], factor_id: str) -> bool:
    fa = _confident(factors, factor_id)
    return bool(fa is not None and getattr(fa.value, "boolean", None) is True)


def _duration_factor(factors: Sequence[Any], factor_id: str) -> Optional[int]:
    fa = _confident(factors, factor_id)
    if fa is None:
        return None
    return getattr(fa.value, "duration_days", None)


def apply_determination_rules(
    predicted: Optional[Determination],
    *,
    predicted_amount: Optional[float],
    factors: Sequence[Any],
) -> Tuple[Optional[Determination], Optional[str]]:
    """Return (possibly-adjusted determination, rule id or None)."""
    if predicted is None or not factors:
        return predicted, None

    # R1 — jurisdiction is rule-like: an out-of-remit complaint head cannot
    # receive a merits finding.
    if _bool_factor(factors, "issue_outside_jurisdiction"):
        return Determination.OUTSIDE_JURISDICTION, "R1_outside_jurisdiction"

    # R2 — severe upgrade: maladministration plus >= 2 aggravators.
    if predicted is Determination.MALADMINISTRATION:
        delay = _duration_factor(factors, "repair_delay_days")
        aggravators = sum(
            [
                _bool_factor(factors, "vulnerability_known"),
                bool(delay is not None and delay >= SEVERE_DELAY_DAYS),
                _bool_factor(factors, "records_inadequate"),
            ]
        )
        if aggravators >= MIN_AGGRAVATORS_FOR_SEVERE:
            return Determination.SEVERE_MALADMINISTRATION, "R2_severe_upgrade"

    # R3 — reasonable redress: a prior proportionate offer plus no fresh
    # award proposed by the model. The Ombudsman finds reasonable redress
    # precisely when no further compensation needs to be ordered.
    if predicted in (Determination.MALADMINISTRATION, Determination.SERVICE_FAILURE):
        if _bool_factor(factors, "prior_compensation_or_apology_offered") and (
            predicted_amount is None or predicted_amount == 0
        ):
            return Determination.REASONABLE_REDRESS, "R3_reasonable_redress"

    return predicted, None
