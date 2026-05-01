"""Calibration metrics: Brier score, ECE, reliability diagram (SHA-30).

The thesis commits to Brier <0.20 — non-negotiable. ECE complements Brier:
Brier penalises both miscalibration and resolution; ECE isolates the
calibration error specifically.

Both metrics work over per-issue (winner_probability, actual_landlord_won)
pairs. For unapportioned cases (per_issue empty in gold), the case-level
overall pair is used.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import numpy as np

from eval.schema import Winner


def _validate_pairing(gold: list, predictions: list) -> None:
    if len(gold) != len(predictions):
        raise ValueError(
            f"length mismatch: len(gold)={len(gold)} != len(predictions)={len(predictions)}"
        )
    for g, p in zip(gold, predictions):
        if g.case_id != p.case_id:
            raise ValueError(
                f"case_id mismatch: gold={g.case_id!r} prediction={p.case_id!r}"
            )


def _iter_probability_pairs(gold: list, predictions: list) -> List[Tuple[float, int]]:
    """Yield `(predicted_probability_landlord_wins, actual_landlord_won_int)`
    per per-issue comparison or per case (unapportioned)."""
    pairs: List[Tuple[float, int]] = []
    for g, p in zip(gold, predictions):
        gt = g.ground_truth_outcome
        if not gt.per_issue:
            actual = 1 if gt.overall_winner == Winner.LANDLORD else 0
            pairs.append((float(p.overall_win_probability), actual))
            continue
        pred_by_issue = {ip.issue: ip for ip in p.per_issue}
        for io in gt.per_issue:
            ip = pred_by_issue.get(io.issue)
            if ip is None:
                # Missing prediction: treat as P=0.5 (worst-case calibration).
                # Caller already counts this as wrong in accuracy; here we
                # surface it so calibration sees the model's silence.
                actual = 1 if io.winner == Winner.LANDLORD else 0
                pairs.append((0.5, actual))
                continue
            actual = 1 if io.winner == Winner.LANDLORD else 0
            pairs.append((float(ip.win_probability), actual))
    return pairs


def brier_score(gold: list, predictions: list) -> float:
    """Mean of `(P(landlord) - actual)^2` over all per-issue pairs.

    Lower is better. Bounded `[0, 1]`. Brier of a coin-flip predictor is
    `0.25`; perfect predictions (`P=1.0` when landlord wins, `0.0`
    otherwise) score `0.0`.
    """
    _validate_pairing(gold, predictions)
    pairs = _iter_probability_pairs(gold, predictions)
    if not pairs:
        raise ValueError("brier_score requires at least one issue pair")
    return float(np.mean([(p - a) ** 2 for p, a in pairs]))


def expected_calibration_error(
    gold: list, predictions: list, n_bins: int = 10
) -> float:
    """Sum over `n_bins` confidence buckets of
    `|bin_accuracy - bin_confidence|` weighted by bin size, then divided
    by total. Returns 0 when perfectly calibrated.
    """
    _validate_pairing(gold, predictions)
    pairs = _iter_probability_pairs(gold, predictions)
    if not pairs:
        raise ValueError("expected_calibration_error requires at least one pair")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = len(pairs)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            in_bin = [(p, a) for p, a in pairs if lo <= p <= hi]
        else:
            in_bin = [(p, a) for p, a in pairs if lo <= p < hi]
        if not in_bin:
            continue
        bin_accuracy = sum(a for _, a in in_bin) / len(in_bin)
        bin_confidence = sum(p for p, _ in in_bin) / len(in_bin)
        ece += (len(in_bin) / total) * abs(bin_accuracy - bin_confidence)
    return float(ece)


def reliability_diagram(
    gold: list, predictions: list, out_path: Path, n_bins: int = 10
) -> Path:
    """Render a reliability diagram PNG to `out_path`. Returns `out_path`.

    Uses matplotlib's `Agg` backend (no display required). The plot shows
    bin accuracy versus confidence, with a y=x diagonal for perfect
    calibration. Bin sizes are encoded in bar opacity.
    """
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    _validate_pairing(gold, predictions)
    pairs = _iter_probability_pairs(gold, predictions)
    if not pairs:
        raise ValueError("reliability_diagram requires at least one pair")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    accuracies: list = []
    sizes: list = []
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            in_bin = [(p, a) for p, a in pairs if lo <= p <= hi]
        else:
            in_bin = [(p, a) for p, a in pairs if lo <= p < hi]
        if not in_bin:
            accuracies.append(np.nan)
            sizes.append(0)
            continue
        accuracies.append(sum(a for _, a in in_bin) / len(in_bin))
        sizes.append(len(in_bin))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(6, 6))
    width = 1.0 / n_bins
    for center, acc, n in zip(bin_centers, accuracies, sizes):
        if np.isnan(acc):
            continue
        alpha = min(1.0, 0.2 + 0.8 * (n / max(sizes)))
        ax.bar(center, acc, width=width * 0.9, alpha=alpha,
               color="steelblue", edgecolor="black")
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="Perfect calibration")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Confidence (P(landlord wins))")
    ax.set_ylabel("Empirical accuracy")
    ax.set_title("Reliability diagram")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
