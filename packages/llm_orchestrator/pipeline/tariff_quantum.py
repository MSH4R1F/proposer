"""Tariff-based quantum model for housing.repairs_social.v1.

Award quantum in the Housing Ombudsman forum is tariff-like, not free-form:
the determination class selects a published-guidance band; typed factor
severity selects the position within the band. This replaces free-text
point regression from comparator text (which degenerated to a constant
£400 and chronically under-predicted by £200–£400)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

import yaml

from llm_orchestrator.models.prediction_v2 import Determination
from llm_orchestrator.pipeline.determination_rules import (
    _bool_factor,
    _confident,
    _duration_factor,
)

_TARIFF_PATH = (
    Path(__file__).resolve().parents[2]
    / "domain_packs" / "housing" / "repairs_social" / "tariff.yaml"
)

_IMPACT_BASE = {"none": 0.15, "minor": 0.3, "moderate": 0.55, "severe": 0.85}
_DEFAULT_SEVERITY = 0.5
_VULNERABILITY_BUMP = 0.15
_DELAY_BUMP = 0.10
_DELAY_BUMP_DAYS = 180


@lru_cache(maxsize=1)
def _bands() -> dict:
    payload = yaml.safe_load(_TARIFF_PATH.read_text(encoding="utf-8"))
    return {
        name: (int(spec["low"]), int(spec["high"]))
        for name, spec in payload["bands"].items()
    }


def severity_score(factors: Sequence[Any]) -> float:
    """Position within the band, [0, 1]. Defaults to the midpoint when
    factor evidence is absent."""
    impact = _confident(factors, "impact_severity_reported")
    score = (
        _IMPACT_BASE.get(getattr(impact.value, "enum", None), _DEFAULT_SEVERITY)
        if impact is not None
        else _DEFAULT_SEVERITY
    )
    if _bool_factor(factors, "vulnerability_known"):
        score += _VULNERABILITY_BUMP
    delay = _duration_factor(factors, "repair_delay_days")
    if delay is not None and delay >= _DELAY_BUMP_DAYS:
        score += _DELAY_BUMP
    return min(score, 1.0)


def tariff_estimate(
    determination: Optional[Determination],
    factors: Sequence[Any],
) -> Tuple[Optional[float], Optional[Tuple[int, int]]]:
    """Return (amount_estimate_gbp, (band_low, band_high)) or (None, None)."""
    if determination is None:
        return None, None
    band = _bands().get(determination.value)
    if band is None:
        return None, None
    low, high = band
    if high == low:
        return float(low), band
    return float(low + round((high - low) * severity_score(factors))), band


def clamp_to_band(
    amount: Optional[float],
    determination: Optional[Determination],
    factors: Sequence[Any],
) -> Tuple[Optional[float], Optional[Tuple[int, int]], Optional[str]]:
    """Reconcile an LLM-proposed amount with the tariff.

    Returns (final_amount, band, adjustment) where adjustment is one of
    None (LLM amount kept), "tariff_fill" (LLM gave null), "snap_low",
    "snap_high"."""
    estimate, band = tariff_estimate(determination, factors)
    if band is None:
        return amount, None, None
    low, high = band
    if amount is None:
        return estimate, band, "tariff_fill"
    if high == 0:
        return 0.0, band, None if amount == 0 else "snap_high"
    if amount < low * 0.5:
        return float(low), band, "snap_low"
    if amount > high * 1.5:
        return float(high), band, "snap_high"
    return amount, band, None
