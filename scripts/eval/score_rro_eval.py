#!/usr/bin/env python3
"""Score the housing.property_chamber.rro.v1 4-mode ablation.

Consumes the per-mode prediction JSONLs that
``scripts/eval/predict_all.py`` writes into an ``--out-dir`` (one
``<mode>.jsonl`` per mode) and computes RRO-appropriate metrics against
``data/gold_standard/housing_property_chamber_rro_v1.jsonl``.

Winner semantics: tenant / landlord / split. The prediction's
``overall_win_probability`` is oriented as **P(landlord)** by
``eval.adapter._confidence_to_p_landlord``, so the positive-class Brier /
ECE / log-loss here use **landlord as the positive class** (no inversion
needed). The metric is stored under the key ``respondent_brier`` so the
cross-domain aggregator (which expects the employment key names) consumes
every domain uniformly: landlord (the defending party in RRO) ==
respondent (the defending party in employment).

Determination analog: the FTT RRO decision has no Ombudsman-style
determination, so ``ground_truth_outcome.determination`` is unset on the
gold rows. Instead we score an **offence-finding accuracy**: the gold
"offence proven?" label (from the audit sidecar
``*.audit.jsonl``) vs the predicted offence proxy derived from the
predicted winner (tenant/split => offence proven; landlord => not proven).
This is the RRO analog of employment's determination_accuracy and is
written under the ``determination_accuracy`` key.

Emits, per mode, a ``_metrics.json`` whose ``metrics`` list entries carry
exactly: mode, n_cases, accuracy, balanced_accuracy, respondent_brier,
ece, log_loss, determination_accuracy, per_class_accuracy,
per_class_counts (+ extra context fields the aggregator ignores). Also
writes a markdown report.
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

logger = logging.getLogger("rro.score")

_MODES = ("hybrid", "rag_only", "kg_only", "llm_only")


@dataclass
class _Pred:
    case_id: str
    overall_winner: str
    p_landlord: float
    predicted_determination: str | None
    total_predicted_gbp: float | None
    abstained: bool
    rationale: str | None = None


@dataclass
class _ModeResult:
    mode: str
    n_cases: int
    accuracy: float
    balanced_accuracy: float
    respondent_brier: float  # positive class = landlord
    ece: float
    log_loss: float
    determination_accuracy: float  # offence-finding analog
    per_class_accuracy: dict[str, float]
    per_class_counts: dict[str, int]
    by_region: dict[str, dict[str, Any]]
    by_offence: dict[str, dict[str, Any]]
    top_errors: list[dict[str, Any]]
    abstention_rate: float
    prior_p_landlord: float
    amount_bucket_accuracy: float


# ---------------------------------------------------------------------------
# Metric primitives — positive class = landlord
# ---------------------------------------------------------------------------


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
        bucket = (
            [(p, a) for p, a in pairs if lo <= p <= hi]
            if i == n_bins - 1
            else [(p, a) for p, a in pairs if lo <= p < hi]
        )
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
    per_class: dict[str, list[int]] = defaultdict(list)
    for p, g in zip(preds, golds):
        per_class[g].append(1 if p == g else 0)
    if not per_class:
        return float("nan")
    return sum(sum(v) / len(v) for v in per_class.values()) / len(per_class)


def _per_class_accuracy(preds: list[str], golds: list[str]):
    counts = Counter(golds)
    hits: defaultdict[str, int] = defaultdict(int)
    for p, g in zip(preds, golds):
        if p == g:
            hits[g] += 1
    return {c: hits[c] / counts[c] for c in counts}, dict(counts)


# ---------------------------------------------------------------------------
# Amount buckets (the RRO "amount determination" analog)
# ---------------------------------------------------------------------------


def _amount_bucket(amount: float | None) -> str:
    if amount is None:
        return "none"
    if amount <= 0:
        return "zero"
    if amount < 3000:
        return "lt_3k"
    if amount < 8000:
        return "3k_8k"
    if amount < 15000:
        return "8k_15k"
    return "gte_15k"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_gold(gold_path: Path) -> list[GoldCase]:
    rows = []
    with gold_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(GoldCase.model_validate(json.loads(line)))
    return rows


def _load_audit(gold_path: Path) -> dict[str, dict[str, Any]]:
    audit_path = gold_path.with_suffix(".audit.jsonl")
    out: dict[str, dict[str, Any]] = {}
    if not audit_path.exists():
        return out
    with audit_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                a = json.loads(line)
                out[a["case_id"]] = a
    return out


def _load_preds(path: Path) -> list[_Pred]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            rows.append(
                _Pred(
                    case_id=d.get("case_id") or "",
                    overall_winner=str(d.get("overall_winner") or ""),
                    p_landlord=float(d.get("overall_win_probability") or 0.5),
                    predicted_determination=d.get("predicted_determination"),
                    total_predicted_gbp=(
                        float(d["total_predicted_gbp"])
                        if d.get("total_predicted_gbp") not in (None, "")
                        else None
                    ),
                    abstained=bool(d.get("abstained")),
                    rationale=(d.get("verification") or {}).get("rationale")
                    if isinstance(d.get("verification"), dict)
                    else None,
                )
            )
    return rows


def _align(gold: list[GoldCase], preds: list[_Pred]):
    by_id = {p.case_id: p for p in preds}
    out = []
    for g in gold:
        p = by_id.get(g.case_id)
        if p is None:
            logger.warning("no prediction for %r", g.case_id)
            continue
        out.append((g, p))
    return out


# ---------------------------------------------------------------------------
# Per-mode scoring
# ---------------------------------------------------------------------------


def _score_mode(mode: str, aligned, audit: dict[str, dict[str, Any]]) -> _ModeResult:
    n = len(aligned)
    pred_w = [p.overall_winner for _, p in aligned]
    gold_w = [g.ground_truth_outcome.overall_winner.value for g, _ in aligned]

    # Calibration pairs (positive class = landlord; exclude split golds).
    pairs: list[tuple[float, float]] = []
    for g, p in aligned:
        gw = g.ground_truth_outcome.overall_winner
        if gw == Winner.SPLIT:
            continue
        pairs.append((p.p_landlord, float(_actual_landlord(gw))))

    accuracy = _accuracy(pred_w, gold_w)
    balanced = _balanced_accuracy(pred_w, gold_w)
    per_class, per_class_counts = _per_class_accuracy(pred_w, gold_w)
    brier = _brier(pairs)
    ece = _ece(pairs)
    ll = _log_loss(pairs)

    # Offence-finding accuracy (determination analog). Gold offence_proven
    # from the audit sidecar; predicted offence proxy = winner != landlord.
    det_hits = det_total = 0
    for g, p in aligned:
        a = audit.get(g.case_id)
        if not a or a.get("offence_proven") is None:
            continue
        gold_off = bool(a["offence_proven"])
        pred_off = p.overall_winner in ("tenant", "split")
        det_total += 1
        if gold_off == pred_off:
            det_hits += 1
    det_accuracy = (det_hits / det_total) if det_total else float("nan")

    # Amount-bucket accuracy: predicted total vs gold total RRO.
    amt_hits = amt_total = 0
    for g, p in aligned:
        gold_amt = float(g.ground_truth_outcome.total_awarded_gbp) if g.ground_truth_outcome.total_awarded_gbp is not None else None
        amt_total += 1
        if _amount_bucket(gold_amt) == _amount_bucket(p.total_predicted_gbp):
            amt_hits += 1
    amt_accuracy = (amt_hits / amt_total) if amt_total else float("nan")

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

    # Stratify by alleged offence type (from audit sidecar).
    by_offence: dict[str, dict[str, Any]] = {}
    offences = sorted(set(audit.get(g.case_id, {}).get("offence_type", "unknown") for g, _ in aligned))
    for off in offences:
        bucket = [(g, p) for g, p in aligned if audit.get(g.case_id, {}).get("offence_type", "unknown") == off]
        if not bucket:
            continue
        by_offence[off] = {
            "n": len(bucket),
            "accuracy": _accuracy(
                [p.overall_winner for _, p in bucket],
                [g.ground_truth_outcome.overall_winner.value for g, _ in bucket],
            ),
        }

    # Top errors by |P(landlord) - actual|.
    errs = []
    for g, p in aligned:
        gw = g.ground_truth_outcome.overall_winner
        if gw == Winner.SPLIT:
            continue
        diff = abs(p.p_landlord - float(_actual_landlord(gw)))
        errs.append((diff, g, p))
    errs.sort(key=lambda t: t[0], reverse=True)
    top_errors = [
        {
            "case_id": g.case_id,
            "gold_winner": g.ground_truth_outcome.overall_winner.value,
            "predicted_winner": p.overall_winner,
            "p_landlord": round(p.p_landlord, 4),
            "abs_p_error": round(diff, 4),
        }
        for diff, g, p in errs[:5]
    ]

    prior_p = (
        sum(1 for g, _ in aligned if g.ground_truth_outcome.overall_winner == Winner.LANDLORD) / n
        if n
        else float("nan")
    )
    abstention = sum(1 for _, p in aligned if p.abstained) / max(n, 1)

    return _ModeResult(
        mode=mode,
        n_cases=n,
        accuracy=accuracy,
        balanced_accuracy=balanced,
        respondent_brier=brier,
        ece=ece,
        log_loss=ll,
        determination_accuracy=det_accuracy,
        per_class_accuracy=per_class,
        per_class_counts=per_class_counts,
        by_region=by_region,
        by_offence=by_offence,
        top_errors=top_errors,
        abstention_rate=abstention,
        prior_p_landlord=prior_p,
        amount_bucket_accuracy=amt_accuracy,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _fmt(x):
    if x is None:
        return "—"
    if isinstance(x, float):
        return "—" if math.isnan(x) else f"{x:.4f}"
    return str(x)


def _fmt_pct(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x * 100:.1f}%"


def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def _render_report(gold_path, pred_dir, results, prior):
    out = ["# Rent Repayment Order eval — `housing.property_chamber.rro.v1`", ""]
    out.append(f"**Gold:** `{gold_path}`")
    out.append(f"**Predictions:** `{pred_dir}`")
    out.append(f"**Positive class (Brier/ECE):** `Winner.LANDLORD` (== prediction `overall_win_probability`)")
    out.append("")
    out.append("## Gold distribution")
    out.append("")
    out.append(_md_table(["Winner", "Share"], [(k, _fmt_pct(v)) for k, v in prior.items()]))
    out.append("")
    out.append("## Overall metrics")
    out.append("")
    out.append(_md_table(
        ["Mode", "n", "Accuracy", "Bal-Acc", "Brier(L)", "ECE", "LogLoss", "OffenceAcc", "AmtBucketAcc", "Abstain"],
        [
            [f"`{r.mode}`", r.n_cases, _fmt(r.accuracy), _fmt(r.balanced_accuracy),
             _fmt(r.respondent_brier), _fmt(r.ece), _fmt(r.log_loss),
             _fmt(r.determination_accuracy), _fmt(r.amount_bucket_accuracy),
             _fmt_pct(r.abstention_rate)]
            for r in results
        ],
    ))
    out.append("")
    out.append("*Brier: 0.0 perfect, 0.25 coin-flip. OffenceAcc = offence-finding analog of determination accuracy.*")
    out.append("")
    out.append("## Per-class accuracy")
    out.append("")
    classes = sorted({c for r in results for c in r.per_class_accuracy})
    rows = []
    for r in results:
        row = [f"`{r.mode}`"]
        for c in classes:
            n = r.per_class_counts.get(c, 0)
            row.append(f"{_fmt(r.per_class_accuracy.get(c))} (n={n})" if n else "—")
        rows.append(row)
    out.append(_md_table(["Mode"] + classes, rows))
    out.append("")
    out.append("## Stratified — by alleged offence type")
    for r in results:
        out.append("")
        out.append(f"### `{r.mode}`")
        rows = [[o, b["n"], _fmt(b["accuracy"])] for o, b in sorted(r.by_offence.items(), key=lambda kv: kv[1]["n"], reverse=True)]
        out.append(_md_table(["Offence", "n", "Accuracy"], rows))
    out.append("")
    out.append("## Error analysis — top-5 |P(landlord) − actual| per mode")
    for r in results:
        out.append("")
        out.append(f"### `{r.mode}`")
        rows = [[e["case_id"][:48], e["gold_winner"], e["predicted_winner"], _fmt(e["p_landlord"]), e["abs_p_error"]] for e in r.top_errors]
        out.append(_md_table(["case_id", "gold", "predicted", "P(L)", "|err|"], rows))
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    gold_path = Path(args.gold)
    if not gold_path.is_absolute():
        gold_path = REPO_ROOT / gold_path
    gold = _load_gold(gold_path)
    audit = _load_audit(gold_path)

    pred_dir = Path(args.pred_dir)
    if not pred_dir.is_absolute():
        pred_dir = REPO_ROOT / pred_dir

    prior = {
        w: sum(1 for g in gold if g.ground_truth_outcome.overall_winner.value == w) / len(gold)
        for w in ("tenant", "landlord", "split")
    }

    results: list[_ModeResult] = []
    for mode in _MODES:
        pp = pred_dir / f"{mode}.jsonl"
        if not pp.exists():
            logger.warning("missing predictions: %s", pp)
            continue
        preds = _load_preds(pp)
        aligned = _align(gold, preds)
        results.append(_score_mode(mode, aligned, audit))

    out_dir = Path(args.out) if args.out else pred_dir
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = out_dir / "_metrics.json"
    metrics_path.write_text(json.dumps({
        "gold_path": str(gold_path),
        "pred_dir": str(pred_dir),
        "positive_class": "landlord",
        "prior_distribution": {"winner": prior},
        "metrics": [
            {
                "mode": r.mode,
                "n_cases": r.n_cases,
                "accuracy": r.accuracy,
                "balanced_accuracy": r.balanced_accuracy,
                "respondent_brier": r.respondent_brier,
                "ece": r.ece,
                "log_loss": r.log_loss,
                "determination_accuracy": r.determination_accuracy,
                "amount_bucket_accuracy": r.amount_bucket_accuracy,
                "abstention_rate": r.abstention_rate,
                "prior_p_respondent": r.prior_p_landlord,
                "per_class_accuracy": r.per_class_accuracy,
                "per_class_counts": r.per_class_counts,
                "by_region": r.by_region,
                "by_offence": r.by_offence,
                "top_errors": r.top_errors,
            }
            for r in results
        ],
    }, indent=2, default=str), encoding="utf-8")

    report = _render_report(gold_path, pred_dir, results, prior)
    report_path = Path(args.report) if args.report else out_dir / "_report.md"
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"metrics -> {metrics_path}")
    print(f"report  -> {report_path}")
    # Console table.
    for r in results:
        print(f"  {r.mode:10s} acc={_fmt(r.accuracy)} bal={_fmt(r.balanced_accuracy)} brier(L)={_fmt(r.respondent_brier)} offAcc={_fmt(r.determination_accuracy)} amtAcc={_fmt(r.amount_bucket_accuracy)}")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Score the RRO 4-mode ablation.")
    p.add_argument("--gold", default="data/gold_standard/housing_property_chamber_rro_v1.jsonl")
    p.add_argument("--pred-dir", required=True, help="dir containing <mode>.jsonl from predict_all.py")
    p.add_argument("--out", default=None, help="dir for _metrics.json/_report.md (default: pred-dir)")
    p.add_argument("--report", default=None)
    return p


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run(_parser().parse_args(argv))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
