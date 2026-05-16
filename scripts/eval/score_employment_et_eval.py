#!/usr/bin/env python3
"""SHA-148 employment-tribunal eval scorer.

Consumes the prediction JSONLs produced by
``scripts/eval/run_employment_et_predictions.py`` and computes metrics
against ``data/gold_standard/employment_unfair_dismissal_v1.jsonl``.

The existing ``packages/eval/metrics/calibration.py`` is **hardcoded to
``Winner.LANDLORD``** as the positive class. This scorer reimplements
Brier / ECE / accuracy with the employment orientation
``Winner.RESPONDENT == positive class``, then writes a markdown report
plus a machine-readable summary JSON.

Metrics computed per mode:

* ``accuracy``                 — overall_winner exact-match (claimant /
                                 respondent / split).
* ``balanced_accuracy``        — macro-averaged per-class accuracy
                                 (counters minority-class wash-out at
                                 the 84/16 winner skew).
* ``respondent_brier``         — mean (P(respondent) − actual_respondent)^2
                                 over all cases. Lower is better. 0.25
                                 is the coin-flip score; 0.0 is perfect.
* ``ece``                      — expected calibration error over 10 bins.
* ``determination_accuracy``   — predicted_determination exact-match.
* ``log_loss``                 — mean negative log-likelihood (a stricter
                                 calibration signal than Brier).
* per-class accuracy + counts.

Stratified reporting (per mode):

* by gold determination
  (claimant_success / respondent_success / partial_success / non_merits)
* by region (top-N regions in the gold set)

Error analysis: top-5 highest-error cases per mode (largest |P_resp − actual|).

Output:

* ``docs/eval/employment_et_unfair_dismissal_v1_<date>_eval.md`` —
  markdown report.
* ``data/eval_artifacts/runs/employment_unfair_dismissal_v1/<run_id>/_metrics.json`` —
  machine-readable summary.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT, REPO_ROOT / "packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from eval.schema import GoldCase, Winner  # noqa: E402

logger = logging.getLogger("sha148.score")


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class _PredictionRow:
    case_id: str
    overall_winner: str
    overall_win_probability_respondent: float
    predicted_determination: str
    total_predicted_gbp: float | None
    abstained: bool
    rationale: str | None = None


@dataclass
class _ModeResult:
    mode: str
    n_cases: int
    n_matched: int
    accuracy: float
    balanced_accuracy: float
    respondent_brier: float
    ece: float
    determination_accuracy: float
    log_loss: float
    per_class_accuracy: dict[str, float]
    per_class_counts: dict[str, int]
    by_determination: dict[str, dict[str, Any]]
    by_region: dict[str, dict[str, Any]]
    top_errors: list[dict[str, Any]]
    abstention_rate: float
    prior_p_respondent: float


# ---------------------------------------------------------------------------
# Metric primitives (ET-orientation: positive class = respondent)
# ---------------------------------------------------------------------------


def _actual_respondent(gold_winner: Winner) -> int:
    """1 if gold says respondent wins; 0 otherwise.

    ``Winner.SPLIT`` maps to 0.5 conceptually, but Brier/ECE need binary
    actuals. We treat split as 0.5 by emitting it as a half-credit
    actual via fractional weighting in callers; for the binary
    accuracy metric, "split" is its own class so this helper is only
    consulted for cases where the gold is binary (claimant / respondent).
    """
    return 1 if gold_winner == Winner.RESPONDENT else 0


def _brier_respondent(pairs: list[tuple[float, float]]) -> float:
    if not pairs:
        return float("nan")
    return sum((p - a) ** 2 for p, a in pairs) / len(pairs)


def _ece_respondent(pairs: list[tuple[float, float]], n_bins: int = 10) -> float:
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


def _log_loss_respondent(pairs: list[tuple[float, float]]) -> float:
    """Standard negative log-likelihood with clipping to avoid log(0)."""
    if not pairs:
        return float("nan")
    eps = 1e-9
    losses = []
    for p, a in pairs:
        p_clipped = min(max(p, eps), 1.0 - eps)
        losses.append(-(a * math.log(p_clipped) + (1 - a) * math.log(1 - p_clipped)))
    return sum(losses) / len(losses)


def _accuracy(predictions: list[str], golds: list[str]) -> float:
    if not predictions:
        return float("nan")
    return sum(1 for p, g in zip(predictions, golds) if p == g) / len(predictions)


def _balanced_accuracy(predictions: list[str], golds: list[str]) -> float:
    """Macro-averaged per-class accuracy."""
    if not predictions:
        return float("nan")
    per_class: dict[str, list[int]] = defaultdict(list)
    for p, g in zip(predictions, golds):
        per_class[g].append(1 if p == g else 0)
    if not per_class:
        return float("nan")
    return sum(sum(v) / len(v) for v in per_class.values()) / len(per_class)


def _per_class_accuracy(
    predictions: list[str], golds: list[str]
) -> tuple[dict[str, float], dict[str, int]]:
    counts: Counter[str] = Counter(golds)
    hits: defaultdict[str, int] = defaultdict(int)
    for p, g in zip(predictions, golds):
        if p == g:
            hits[g] += 1
    return (
        {cls: hits[cls] / counts[cls] for cls in counts},
        dict(counts),
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_gold(gold_path: Path) -> list[GoldCase]:
    rows: list[GoldCase] = []
    with gold_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(GoldCase.model_validate(json.loads(line)))
    return rows


def _load_predictions(path: Path) -> list[_PredictionRow]:
    rows: list[_PredictionRow] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            rows.append(
                _PredictionRow(
                    case_id=d.get("case_id") or "",
                    overall_winner=str(d.get("overall_winner") or ""),
                    overall_win_probability_respondent=float(
                        d.get("overall_win_probability_respondent") or 0.5
                    ),
                    predicted_determination=str(d.get("predicted_determination") or ""),
                    total_predicted_gbp=(
                        float(d["total_predicted_gbp"])
                        if d.get("total_predicted_gbp") not in (None, "")
                        else None
                    ),
                    abstained=bool(d.get("abstained")),
                    rationale=d.get("rationale"),
                )
            )
    return rows


def _align_predictions(
    gold: list[GoldCase], preds: list[_PredictionRow]
) -> list[tuple[GoldCase, _PredictionRow]]:
    by_id = {p.case_id: p for p in preds}
    aligned: list[tuple[GoldCase, _PredictionRow]] = []
    for g in gold:
        p = by_id.get(g.case_id)
        if p is None:
            logger.warning("no prediction for gold case %r", g.case_id)
            continue
        aligned.append((g, p))
    return aligned


# ---------------------------------------------------------------------------
# Per-mode scoring
# ---------------------------------------------------------------------------


def _score_mode(mode: str, aligned: list[tuple[GoldCase, _PredictionRow]]) -> _ModeResult:
    n = len(aligned)
    pred_winners = [p.overall_winner for _, p in aligned]
    gold_winners = [g.ground_truth_outcome.overall_winner.value for g, _ in aligned]
    pred_dets = [p.predicted_determination for _, p in aligned]
    gold_dets = [
        (g.ground_truth_outcome.determination.value if g.ground_truth_outcome.determination else "")
        for g, _ in aligned
    ]

    # Brier / ECE / log loss pairs (only for binary gold rows; split is
    # excluded from the calibration calculation because it's neither
    # P=1 nor P=0).
    pairs: list[tuple[float, float]] = []
    for g, p in aligned:
        gw = g.ground_truth_outcome.overall_winner
        if gw == Winner.SPLIT:
            continue
        pairs.append((p.overall_win_probability_respondent, float(_actual_respondent(gw))))

    accuracy = _accuracy(pred_winners, gold_winners)
    balanced = _balanced_accuracy(pred_winners, gold_winners)
    per_class, per_class_counts = _per_class_accuracy(pred_winners, gold_winners)
    brier = _brier_respondent(pairs)
    ece = _ece_respondent(pairs)
    log_loss = _log_loss_respondent(pairs)
    det_accuracy = _accuracy(pred_dets, gold_dets)

    # Stratify by gold determination
    by_det: dict[str, dict[str, Any]] = {}
    for det in sorted(set(gold_dets)):
        bucket = [(g, p) for (g, p) in aligned if (g.ground_truth_outcome.determination and g.ground_truth_outcome.determination.value == det) or (not g.ground_truth_outcome.determination and det == "")]
        if not bucket:
            continue
        b_preds = [p.overall_winner for _, p in bucket]
        b_golds = [g.ground_truth_outcome.overall_winner.value for g, _ in bucket]
        b_pairs = [
            (p.overall_win_probability_respondent, float(_actual_respondent(g.ground_truth_outcome.overall_winner)))
            for g, p in bucket
            if g.ground_truth_outcome.overall_winner != Winner.SPLIT
        ]
        by_det[det] = {
            "n": len(bucket),
            "accuracy": _accuracy(b_preds, b_golds),
            "respondent_brier": _brier_respondent(b_pairs) if b_pairs else None,
        }

    # Stratify by region
    by_region: dict[str, dict[str, Any]] = {}
    for region in sorted(set(g.region.value for g, _ in aligned)):
        bucket = [(g, p) for g, p in aligned if g.region.value == region]
        b_preds = [p.overall_winner for _, p in bucket]
        b_golds = [g.ground_truth_outcome.overall_winner.value for g, _ in bucket]
        by_region[region] = {
            "n": len(bucket),
            "accuracy": _accuracy(b_preds, b_golds),
        }

    # Top errors
    errors: list[tuple[float, GoldCase, _PredictionRow]] = []
    for g, p in aligned:
        gw = g.ground_truth_outcome.overall_winner
        if gw == Winner.SPLIT:
            continue
        actual_resp = float(_actual_respondent(gw))
        diff = abs(p.overall_win_probability_respondent - actual_resp)
        errors.append((diff, g, p))
    errors.sort(key=lambda t: t[0], reverse=True)
    top_errors = [
        {
            "case_id": g.case_id,
            "gold_winner": g.ground_truth_outcome.overall_winner.value,
            "gold_determination": (
                g.ground_truth_outcome.determination.value
                if g.ground_truth_outcome.determination
                else None
            ),
            "predicted_winner": p.overall_winner,
            "predicted_p_respondent": p.overall_win_probability_respondent,
            "predicted_determination": p.predicted_determination,
            "abs_p_error": round(diff, 4),
            "rationale": p.rationale,
        }
        for diff, g, p in errors[:5]
    ]

    # Prior P(respondent) — informative for interpreting calibration.
    if not aligned:
        prior_p = float("nan")
    else:
        prior_p = sum(
            1
            for g, _ in aligned
            if g.ground_truth_outcome.overall_winner == Winner.RESPONDENT
        ) / len(aligned)

    abstention_rate = sum(1 for _, p in aligned if p.abstained) / max(n, 1)

    return _ModeResult(
        mode=mode,
        n_cases=n,
        n_matched=len(aligned),
        accuracy=accuracy,
        balanced_accuracy=balanced,
        respondent_brier=brier,
        ece=ece,
        determination_accuracy=det_accuracy,
        log_loss=log_loss,
        per_class_accuracy=per_class,
        per_class_counts=per_class_counts,
        by_determination=by_det,
        by_region=by_region,
        top_errors=top_errors,
        abstention_rate=abstention_rate,
        prior_p_respondent=prior_p,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _fmt(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        if math.isnan(x):
            return "—"
        return f"{x:.4f}"
    return str(x)


def _fmt_pct(x: Any) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x * 100:.1f}%"


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def _render_report(
    gold_path: Path,
    run_dir: Path,
    summary: dict[str, Any],
    results: list[_ModeResult],
) -> str:
    out: list[str] = []
    out.append("# Employment Tribunal eval — `employment.unfair_dismissal.v1`")
    out.append("")
    out.append(f"**Gold:** [`{gold_path.relative_to(REPO_ROOT)}`](../../{gold_path.relative_to(REPO_ROOT)})")
    out.append(f"**Run dir:** `{run_dir.relative_to(REPO_ROOT)}`")
    out.append(f"**Run ID:** `{summary.get('run_id')}`")
    out.append(f"**Predictor:** `{summary.get('predictor_spec', {}).get('provider')}:{summary.get('predictor_spec', {}).get('model')}`")
    out.append(f"**Gold n:** {summary.get('n_gold_cases')}")
    out.append("")
    out.append("## Gold distribution (priors)")
    prior = summary.get("prior_distribution") or {}
    out.append("")
    out.append(_md_table(
        ["Winner", "Share"],
        sorted([(k, _fmt_pct(v)) for k, v in (prior.get("winner") or {}).items()], reverse=True, key=lambda r: r[1]),
    ))
    out.append("")
    out.append(_md_table(
        ["Determination", "Share"],
        sorted([(k, _fmt_pct(v)) for k, v in (prior.get("determination") or {}).items()], reverse=True, key=lambda r: r[1]),
    ))
    out.append("")
    out.append("## Overall metrics (positive class = `Winner.RESPONDENT`)")
    out.append("")
    out.append(_md_table(
        ["Mode", "n", "Accuracy", "Bal-Accuracy", "Brier (R)", "ECE", "LogLoss", "Det-Accuracy", "Abstain"],
        [
            [
                f"`{r.mode}`",
                r.n_cases,
                _fmt(r.accuracy),
                _fmt(r.balanced_accuracy),
                _fmt(r.respondent_brier),
                _fmt(r.ece),
                _fmt(r.log_loss),
                _fmt(r.determination_accuracy),
                _fmt_pct(r.abstention_rate),
            ]
            for r in results
        ],
    ))
    out.append("")
    out.append(
        "*Brier reading: 0.0 = perfect, 0.25 = coin flip, ≥ 0.25 = worse than chance.*"
    )
    out.append("")

    out.append("## Per-class accuracy")
    out.append("")
    all_classes = sorted(
        {cls for r in results for cls in r.per_class_accuracy}
    )
    rows = []
    for r in results:
        row = [f"`{r.mode}`"]
        for cls in all_classes:
            n = r.per_class_counts.get(cls, 0)
            acc = r.per_class_accuracy.get(cls)
            row.append(f"{_fmt(acc)} (n={n})" if n else "—")
        rows.append(row)
    out.append(_md_table(["Mode"] + all_classes, rows))
    out.append("")

    out.append("## Stratified — by gold `determination`")
    for r in results:
        out.append("")
        out.append(f"### `{r.mode}`")
        rows = []
        for det in sorted(r.by_determination):
            b = r.by_determination[det]
            rows.append([
                det,
                b["n"],
                _fmt(b["accuracy"]),
                _fmt(b.get("respondent_brier")),
            ])
        out.append(_md_table(["Determination", "n", "Accuracy", "Brier (R)"], rows))
    out.append("")

    out.append("## Stratified — by region (top 8)")
    for r in results:
        out.append("")
        out.append(f"### `{r.mode}`")
        regions = sorted(r.by_region.items(), key=lambda kv: kv[1]["n"], reverse=True)[:8]
        rows = [[reg, b["n"], _fmt(b["accuracy"])] for reg, b in regions]
        out.append(_md_table(["Region", "n", "Accuracy"], rows))
    out.append("")

    out.append("## Error analysis — top-5 largest |P_respondent − actual| per mode")
    for r in results:
        out.append("")
        out.append(f"### `{r.mode}`")
        rows = [
            [
                e["case_id"][:48],
                e["gold_winner"],
                e["predicted_winner"],
                _fmt(e["predicted_p_respondent"]),
                e["abs_p_error"],
                (e.get("rationale") or "")[:80],
            ]
            for e in r.top_errors
        ]
        out.append(_md_table(
            ["case_id", "gold", "predicted", "P(resp)", "|err|", "rationale"], rows,
        ))
    out.append("")

    # Findings / caveats
    out.append("## Findings")
    out.append("")
    facts_mode = next((r for r in results if r.mode == "facts_llm"), None)
    blind_mode = next((r for r in results if r.mode == "blind_llm"), None)
    prior_mode = next((r for r in results if r.mode == "prior_baseline"), None)

    if facts_mode and blind_mode and prior_mode:
        out.append(
            f"- **Prior baseline** (always predict majority class respondent at "
            f"P={prior_mode.prior_p_respondent:.2f}) lands at "
            f"**{_fmt_pct(prior_mode.accuracy)}** accuracy and Brier "
            f"**{_fmt(prior_mode.respondent_brier)}**. Any meaningful predictor "
            f"must beat both."
        )
        out.append(
            f"- **Blind LLM** (metadata only — no facts narrative) at "
            f"**{_fmt_pct(blind_mode.accuracy)}** accuracy / Brier "
            f"**{_fmt(blind_mode.respondent_brier)}**. Marginal lift over prior: "
            f"accuracy Δ = **{(blind_mode.accuracy - prior_mode.accuracy) * 100:+.1f} pp**, "
            f"Brier Δ = **{prior_mode.respondent_brier - blind_mode.respondent_brier:+.4f}**."
        )
        out.append(
            f"- **Facts LLM** (metadata + grounded facts) at "
            f"**{_fmt_pct(facts_mode.accuracy)}** accuracy / Brier "
            f"**{_fmt(facts_mode.respondent_brier)}**. Marginal lift over blind: "
            f"accuracy Δ = **{(facts_mode.accuracy - blind_mode.accuracy) * 100:+.1f} pp**, "
            f"Brier Δ = **{blind_mode.respondent_brier - facts_mode.respondent_brier:+.4f}**."
        )
        out.append(
            f"- **Balanced accuracy** (macro-averaged per-class) at facts_llm = "
            f"**{_fmt(facts_mode.balanced_accuracy)}** — the relevant number "
            f"when the 84/16 winner skew is suspect of inflating raw accuracy."
        )
        out.append(
            f"- **Determination accuracy** at facts_llm = "
            f"**{_fmt_pct(facts_mode.determination_accuracy)}**. This is the "
            f"4-class task (claimant_success / respondent_success / "
            f"partial_success / non_merits), which carries more signal than "
            f"the binary winner."
        )

    out.append("")
    out.append("## Caveats")
    out.append("")
    out.append(
        "- The gold rows themselves were produced by a same-provider dual-LLM "
        "panel (gpt-5.5 + gpt-5-mini) with mean IAA 0.55 and auto-promoted per "
        "the user's 2026-05-16 decision. Predictions vs gold therefore measure "
        "predictor agreement with an LLM-derived label, NOT agreement with "
        "human-adjudicated ground truth. Phase D refinement would tighten this."
    )
    out.append(
        "- Same-provider LLM stack across labelers AND predictor introduces "
        "correlated bias — both sides may share the same blind spots (e.g. "
        "over-emitting `non_merits` on cases where the s98 framework isn't "
        "visible in the chunked PDF text)."
    )
    out.append(
        "- Brier/ECE are computed only over rows where the gold winner is "
        "claimant or respondent (binary). `Winner.SPLIT` is excluded from "
        "calibration because the actual is neither 0 nor 1; if a future run "
        "carries any split rows the calibration n will drop accordingly."
    )
    out.append(
        "- This eval intentionally does NOT use RAG / KG retrieval. SHA-147 "
        "deferred vector ingestion; SHA-149 (employment factor catalog) has "
        "not been built. The contrast is prior vs blind vs facts only — not "
        "the housing four-mode ablation."
    )
    out.append(
        "- The corpus is heavily skewed to 2025-2026 decisions (97% of gold). "
        "Train/test temporal-split conclusions would need a multi-year corpus "
        "which GOV.UK's ET listing does not currently support (the date filter "
        "is unhonoured server-side and pagination caps at ~3 years)."
    )

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    gold_path = Path(args.gold).expanduser()
    if not gold_path.is_absolute():
        gold_path = REPO_ROOT / gold_path
    gold = _load_gold(gold_path)

    run_dir = Path(args.run_dir).expanduser()
    if not run_dir.is_absolute():
        run_dir = REPO_ROOT / run_dir
    summary_path = run_dir / "_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    results: list[_ModeResult] = []
    for m in summary.get("modes", []):
        mode_name = m["mode"]
        preds_path = Path(m["output"])
        if not preds_path.exists():
            logger.warning("predictions file missing: %s", preds_path)
            continue
        preds = _load_predictions(preds_path)
        aligned = _align_predictions(gold, preds)
        results.append(_score_mode(mode_name, aligned))

    metrics_path = run_dir / "_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "gold_path": str(gold_path),
                "run_dir": str(run_dir),
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
                        "abstention_rate": r.abstention_rate,
                        "prior_p_respondent": r.prior_p_respondent,
                        "per_class_accuracy": r.per_class_accuracy,
                        "per_class_counts": r.per_class_counts,
                        "by_determination": r.by_determination,
                        "by_region": r.by_region,
                        "top_errors": r.top_errors,
                    }
                    for r in results
                ],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    report_md = _render_report(gold_path, run_dir, summary, results)
    report_path = Path(args.report) if args.report else REPO_ROOT / "docs" / "eval" / f"employment_et_unfair_dismissal_v1_2026-05-16_eval.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")
    print(f"metrics -> {metrics_path}")
    print(f"report  -> {report_path}")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="SHA-148 employment-tribunal eval scorer."
    )
    p.add_argument("--gold", default="data/gold_standard/employment_unfair_dismissal_v1.jsonl")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--report", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run(_parser().parse_args(argv))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
