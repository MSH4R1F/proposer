#!/usr/bin/env python3
"""Housing Ombudsman eval scorer (cross-domain 150-gold ablation).

Consumes the per-mode prediction JSONLs produced by
``scripts/eval/predict_all.py`` (``{mode}.jsonl`` under ``--pred-dir``)
and computes metrics against the housing gold.

Emits a per-run ``_metrics.json`` in the SAME shape that
``scripts/eval/score_employment_et_eval.py`` produces, so the
cross-domain aggregator can consume both domains uniformly. The
``respondent_brier`` key name is REUSED for the housing positive-class
Brier (positive class = ``Winner.LANDLORD``) — the housing analog of the
employment ``Winner.RESPONDENT`` positive class.

Housing-specific orientation:

* Winner classes are tenant / landlord / split.
* ``overall_win_probability`` in the predict_all serialization is already
  P(landlord) (see ``eval.adapter._confidence_to_p_landlord``), so the
  positive-class Brier is computed directly against it with
  ``actual_landlord = 1 if gold winner == landlord``.
* The discriminative target on this corpus is the 6-class
  ``determination`` (the tenant/landlord winner is heavily skewed because
  most published Ombudsman determinations find for the resident).
  ``determination_accuracy`` is therefore the headline merits metric.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT, REPO_ROOT / "packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from eval.schema import GoldCase, Winner  # noqa: E402

logger = logging.getLogger("housing.score")

_MODES = ("llm_only", "rag_only", "kg_only", "hybrid")


@dataclass
class _PredictionRow:
    case_id: str
    overall_winner: str
    p_landlord: float
    predicted_determination: str
    abstained: bool


def _load_gold(gold_path: Path) -> list[GoldCase]:
    rows: list[GoldCase] = []
    with gold_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(GoldCase.model_validate(json.loads(line)))
    return rows


def _load_predictions(path: Path) -> list[_PredictionRow]:
    rows: list[_PredictionRow] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            rows.append(
                _PredictionRow(
                    case_id=d.get("case_id") or "",
                    overall_winner=str(d.get("overall_winner") or ""),
                    p_landlord=float(d.get("overall_win_probability") or 0.5),
                    predicted_determination=str(d.get("predicted_determination") or ""),
                    abstained=bool(d.get("abstained")),
                )
            )
    return rows


def _actual_landlord(w: Winner) -> int:
    return 1 if w == Winner.LANDLORD else 0


def _brier(pairs: list[tuple[float, float]]) -> float:
    if not pairs:
        return float("nan")
    return sum((p - a) ** 2 for p, a in pairs) / len(pairs)


def _ece(pairs: list[tuple[float, float]], n_bins: int = 10) -> float:
    if not pairs:
        return float("nan")
    edges = [i / n_bins for i in range(n_bins + 1)]
    total = len(pairs)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bins - 1:
            bucket = [(p, a) for p, a in pairs if lo <= p <= hi]
        else:
            bucket = [(p, a) for p, a in pairs if lo <= p < hi]
        if not bucket:
            continue
        avg_p = sum(p for p, _ in bucket) / len(bucket)
        avg_a = sum(a for _, a in bucket) / len(bucket)
        ece += (len(bucket) / total) * abs(avg_p - avg_a)
    return ece


def _log_loss(pairs: list[tuple[float, float]]) -> float:
    if not pairs:
        return float("nan")
    eps = 1e-9
    losses = []
    for p, a in pairs:
        pc = min(max(p, eps), 1.0 - eps)
        losses.append(-(a * math.log(pc) + (1 - a) * math.log(1 - pc)))
    return sum(losses) / len(losses)


def _accuracy(preds: list[str], golds: list[str]) -> float:
    if not preds:
        return float("nan")
    return sum(1 for p, g in zip(preds, golds) if p == g) / len(preds)


def _balanced_accuracy(preds: list[str], golds: list[str]) -> float:
    if not preds:
        return float("nan")
    per: dict[str, list[int]] = defaultdict(list)
    for p, g in zip(preds, golds):
        per[g].append(1 if p == g else 0)
    if not per:
        return float("nan")
    return sum(sum(v) / len(v) for v in per.values()) / len(per)


def _per_class_accuracy(preds: list[str], golds: list[str]) -> tuple[dict[str, float], dict[str, int]]:
    counts = Counter(golds)
    hits: dict[str, int] = defaultdict(int)
    for p, g in zip(preds, golds):
        if p == g:
            hits[g] += 1
    return ({c: hits[c] / counts[c] for c in counts}, dict(counts))


def _align(gold: list[GoldCase], preds: list[_PredictionRow]) -> list[tuple[GoldCase, _PredictionRow]]:
    by_id = {p.case_id: p for p in preds}
    aligned = []
    for g in gold:
        p = by_id.get(g.case_id)
        if p is None:
            logger.warning("no prediction for gold case %r", g.case_id)
            continue
        aligned.append((g, p))
    return aligned


def _score_mode(mode: str, aligned: list[tuple[GoldCase, _PredictionRow]]) -> dict[str, Any]:
    n = len(aligned)
    pred_w = [p.overall_winner for _, p in aligned]
    gold_w = [g.ground_truth_outcome.overall_winner.value for g, _ in aligned]
    pred_d = [p.predicted_determination for _, p in aligned]
    gold_d = [
        (g.ground_truth_outcome.determination.value if g.ground_truth_outcome.determination else "")
        for g, _ in aligned
    ]

    # Brier / ECE / log loss: positive class = landlord; split excluded
    # (actual is neither 0 nor 1).
    pairs: list[tuple[float, float]] = []
    for g, p in aligned:
        gw = g.ground_truth_outcome.overall_winner
        if gw == Winner.SPLIT:
            continue
        pairs.append((p.p_landlord, float(_actual_landlord(gw))))

    per_class, per_class_counts = _per_class_accuracy(pred_w, gold_w)

    # Stratify by gold determination.
    by_det: dict[str, dict[str, Any]] = {}
    for det in sorted(set(gold_d)):
        bucket = [
            (g, p) for g, p in aligned
            if (g.ground_truth_outcome.determination and g.ground_truth_outcome.determination.value == det)
            or (not g.ground_truth_outcome.determination and det == "")
        ]
        if not bucket:
            continue
        b_pred_w = [p.overall_winner for _, p in bucket]
        b_gold_w = [g.ground_truth_outcome.overall_winner.value for g, _ in bucket]
        b_pred_d = [p.predicted_determination for _, p in bucket]
        b_gold_d = [det] * len(bucket)
        by_det[det] = {
            "n": len(bucket),
            "accuracy": _accuracy(b_pred_w, b_gold_w),
            "determination_accuracy": _accuracy(b_pred_d, b_gold_d),
        }

    # Stratify by region.
    by_region: dict[str, dict[str, Any]] = {}
    for region in sorted(set(g.region.value for g, _ in aligned)):
        bucket = [(g, p) for g, p in aligned if g.region.value == region]
        by_region[region] = {
            "n": len(bucket),
            "accuracy": _accuracy(
                [p.overall_winner for _, p in bucket],
                [g.ground_truth_outcome.overall_winner.value for g, _ in bucket],
            ),
        }

    # Top errors by |P(landlord) - actual_landlord|.
    errors = []
    for g, p in aligned:
        gw = g.ground_truth_outcome.overall_winner
        if gw == Winner.SPLIT:
            continue
        diff = abs(p.p_landlord - float(_actual_landlord(gw)))
        errors.append((diff, g, p))
    errors.sort(key=lambda t: t[0], reverse=True)
    top_errors = [
        {
            "case_id": g.case_id,
            "gold_winner": g.ground_truth_outcome.overall_winner.value,
            "gold_determination": (
                g.ground_truth_outcome.determination.value if g.ground_truth_outcome.determination else None
            ),
            "predicted_winner": p.overall_winner,
            "predicted_p_landlord": p.p_landlord,
            "predicted_determination": p.predicted_determination,
            "abs_p_error": round(diff, 4),
        }
        for diff, g, p in errors[:5]
    ]

    prior_p_landlord = (
        sum(1 for g, _ in aligned if g.ground_truth_outcome.overall_winner == Winner.LANDLORD) / n
        if n else float("nan")
    )

    return {
        "mode": mode,
        "n_cases": n,
        "accuracy": _accuracy(pred_w, gold_w),
        "balanced_accuracy": _balanced_accuracy(pred_w, gold_w),
        "respondent_brier": _brier(pairs),   # key reused: positive class = landlord
        "ece": _ece(pairs),
        "log_loss": _log_loss(pairs),
        "determination_accuracy": _accuracy(pred_d, gold_d),
        "abstention_rate": sum(1 for _, p in aligned if p.abstained) / max(n, 1),
        "prior_p_respondent": prior_p_landlord,  # key reused: P(landlord)
        "per_class_accuracy": per_class,
        "per_class_counts": per_class_counts,
        "by_determination": by_det,
        "by_region": by_region,
        "top_errors": top_errors,
    }


def run(args: argparse.Namespace) -> int:
    gold_path = Path(args.gold).expanduser()
    if not gold_path.is_absolute():
        gold_path = REPO_ROOT / gold_path
    gold = _load_gold(gold_path)

    pred_dir = Path(args.pred_dir).expanduser()
    if not pred_dir.is_absolute():
        pred_dir = REPO_ROOT / pred_dir

    out_dir = Path(args.out_dir).expanduser() if args.out_dir else pred_dir
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics: list[dict[str, Any]] = []
    for mode in _MODES:
        preds_path = pred_dir / f"{mode}.jsonl"
        if not preds_path.exists():
            logger.warning("predictions file missing: %s", preds_path)
            continue
        aligned = _align(gold, _load_predictions(preds_path))
        metrics.append(_score_mode(mode, aligned))

    out = {
        "gold_path": str(gold_path),
        "pred_dir": str(pred_dir),
        "n_gold": len(gold),
        "metrics": metrics,
    }
    metrics_path = out_dir / "_metrics.json"
    metrics_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"metrics -> {metrics_path}")
    # short stdout table
    for m in metrics:
        print(
            f"  {m['mode']:9s} acc={m['accuracy']:.3f} bal={m['balanced_accuracy']:.3f} "
            f"brier(L)={m['respondent_brier']:.3f} logloss={m['log_loss']:.3f} "
            f"det-acc={m['determination_accuracy']:.3f}"
        )
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Housing Ombudsman eval scorer (employment-compatible _metrics.json).")
    p.add_argument("--gold", default="data/gold_standard/housing_repairs_social_v1_150.jsonl")
    p.add_argument("--pred-dir", required=True, help="predict_all.py --out-dir containing {mode}.jsonl")
    p.add_argument("--out-dir", default=None, help="where to write _metrics.json (defaults to --pred-dir)")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    return run(_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
