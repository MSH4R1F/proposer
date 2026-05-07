"""Tests for packages/eval/metrics/counterfactual_sensitivity.py (Stream C §17.7)."""
from __future__ import annotations

import pytest

from eval.metrics.counterfactual_sensitivity import (
    counterfactual_factor_sensitivity,
    sensitivity_score,
)


@pytest.mark.asyncio
async def test_sensitivity_detects_flipped_outcome():
    """Predict_fn returns "win" for original, "lose" when factor "X" flipped."""
    async def predict_fn(case):
        return "win" if case == "original" else "lose"

    def flip(case, fid):
        return "flipped" if fid == "X" else case

    out = await counterfactual_factor_sensitivity(
        case="original",
        factor_ids=["X", "Y"],
        predict_fn=predict_fn,
        flip_factor=flip,
    )
    assert out["X"] is True  # outcome changed
    assert out["Y"] is False  # outcome same


@pytest.mark.asyncio
async def test_no_factors_returns_empty_dict():
    async def predict_fn(case):
        return "win"

    out = await counterfactual_factor_sensitivity(
        case="x", factor_ids=[], predict_fn=predict_fn,
    )
    assert out == {}


@pytest.mark.asyncio
async def test_default_flip_is_noop_so_all_factors_register_unchanged():
    """Without a flip_factor, the case is unchanged; all factors flip to False."""
    async def predict_fn(case):
        return "same"

    out = await counterfactual_factor_sensitivity(
        case="x", factor_ids=["A", "B"], predict_fn=predict_fn,
    )
    assert out == {"A": False, "B": False}


def test_sensitivity_score_all_flipped():
    assert sensitivity_score({"A": True, "B": True}) == 1.0


def test_sensitivity_score_none_flipped():
    assert sensitivity_score({"A": False, "B": False}) == 0.0


def test_sensitivity_score_partial():
    assert sensitivity_score({"A": True, "B": False}) == 0.5


def test_sensitivity_score_empty_returns_zero():
    assert sensitivity_score({}) == 0.0
