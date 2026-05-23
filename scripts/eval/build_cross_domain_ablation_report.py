#!/usr/bin/env python3
"""Cross-domain 4-mode ablation report.

Consumes per-domain, per-seed ``_metrics.json`` files (the shape emitted
by ``score_employment_et_eval.py``) and produces a single markdown report
comparing llm_only / rag_only / kg_only / hybrid across domains, with
mean ± std over the seeds for each (domain, mode, metric).

Usage:

    venv/bin/python scripts/eval/build_cross_domain_ablation_report.py \\
        --domain "Employment (unfair dismissal)=run_dir_a,run_dir_b,run_dir_c" \\
        --domain "Housing repairs (Ombudsman)=run_dir_a,run_dir_b,run_dir_c" \\
        --domain "Housing RRO (FTT-PC)=run_dir_a,run_dir_b,run_dir_c" \\
        --out docs/eval/cross_domain_ablation_2026-05-17.md

Each run_dir must contain a ``_metrics.json``. The script is tolerant of
domains with fewer seeds or missing modes.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Sequence

MODES = ("llm_only", "rag_only", "kg_only", "hybrid")
METRICS = (
    ("accuracy", "Accuracy", True),
    ("balanced_accuracy", "Bal-Acc", False),
    ("respondent_brier", "Brier(pos)", False),
    ("log_loss", "LogLoss", False),
    ("determination_accuracy", "Det/Outcome-Acc", True),
)


def _load_runs(run_dirs: list[Path]) -> dict[str, dict[str, list[float]]]:
    """mode -> metric_key -> [values across seeds]."""
    acc: dict[str, dict[str, list[float]]] = {
        m: {k: [] for k, _, _ in METRICS} for m in MODES
    }
    for rd in run_dirs:
        mp = rd / "_metrics.json"
        if not mp.exists():
            continue
        data = json.loads(mp.read_text(encoding="utf-8"))
        for row in data.get("metrics", []):
            mode = row.get("mode")
            if mode not in acc:
                continue
            for key, _, _ in METRICS:
                v = row.get(key)
                if v is None:
                    continue
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if not math.isnan(fv):
                    acc[mode][key].append(fv)
    return acc


def _fmt(vals: list[float], *, pct: bool) -> str:
    if not vals:
        return "—"
    mean = statistics.mean(vals)
    std = statistics.stdev(vals) if len(vals) > 1 else 0.0
    if pct:
        return f"{mean * 100:.1f}±{std * 100:.1f}"
    return f"{mean:.3f}±{std:.3f}"


def _best_mode(agg: dict[str, dict[str, list[float]]], key: str, higher_better: bool) -> str | None:
    scored = []
    for m in MODES:
        vals = agg[m][key]
        if vals:
            scored.append((m, statistics.mean(vals)))
    if not scored:
        return None
    return (max if higher_better else min)(scored, key=lambda kv: kv[1])[0]


def build(domain_runs: list[tuple[str, list[Path]]]) -> str:
    out: list[str] = []
    out.append("# Cross-domain 4-mode ablation — hybrid RAG + KG vs baselines")
    out.append("")
    out.append(
        "Ablation modes: `llm_only` (facts only) · `rag_only` (facts + "
        "retrieved precedents, leave-one-out) · `kg_only` (facts + SHA-149 "
        "factor digest) · `hybrid` (facts + retrieval + factors). Predictor "
        "`openai:gpt-5-mini`. Values are **mean ± std across seeds**."
    )
    out.append("")
    out.append(
        "*Brier(pos): lower is better, positive class is the respondent/"
        "landlord side; 0.25 = coin flip. Det/Outcome-Acc is the per-domain "
        "multi-class label accuracy (employment determination / housing "
        "maladministration / RRO offence-finding).*"
    )
    out.append("")

    # Per-domain detail tables.
    domain_aggs: list[tuple[str, dict]] = []
    for domain_name, run_dirs in domain_runs:
        agg = _load_runs(run_dirs)
        domain_aggs.append((domain_name, agg))
        n_seeds = max(
            (len(agg[m][METRICS[0][0]]) for m in MODES), default=0
        )
        out.append(f"## {domain_name}")
        out.append("")
        out.append(f"*{n_seeds} seed(s).*")
        out.append("")
        header = "| Mode | " + " | ".join(label for _, label, _ in METRICS) + " |"
        sep = "|" + "|".join("---" for _ in range(len(METRICS) + 1)) + "|"
        out.append(header)
        out.append(sep)
        for m in MODES:
            cells = [f"`{m}`"]
            for key, _, pct in METRICS:
                cells.append(_fmt(agg[m][key], pct=pct))
            out.append("| " + " | ".join(cells) + " |")
        out.append("")
        # Best-mode callouts.
        best_brier = _best_mode(agg, "respondent_brier", higher_better=False)
        best_det = _best_mode(agg, "determination_accuracy", higher_better=True)
        best_bal = _best_mode(agg, "balanced_accuracy", higher_better=True)
        out.append(
            f"- Best calibration (Brier): **`{best_brier}`** · "
            f"best balanced accuracy: **`{best_bal}`** · "
            f"best outcome-class accuracy: **`{best_det}`**."
        )
        out.append("")

    # Cross-domain summary: which mode wins each metric in each domain.
    out.append("## Cross-domain summary — winning mode per metric")
    out.append("")
    out.append("| Domain | Best Brier | Best Bal-Acc | Best Outcome-Acc |")
    out.append("|---|---|---|---|")
    for domain_name, agg in domain_aggs:
        out.append(
            f"| {domain_name} | "
            f"`{_best_mode(agg, 'respondent_brier', False)}` | "
            f"`{_best_mode(agg, 'balanced_accuracy', True)}` | "
            f"`{_best_mode(agg, 'determination_accuracy', True)}` |"
        )
    out.append("")
    out.append("## Reading the ablation")
    out.append("")
    out.append(
        "- **`rag_only` − `llm_only`** isolates the marginal value of "
        "case-based retrieval (similar published decisions with their "
        "outcomes attached, leave-one-out)."
    )
    out.append(
        "- **`kg_only` − `llm_only`** isolates the marginal value of the "
        "SHA-149 structured factor digest (typed pre-decision facts with "
        "polarity + confidence)."
    )
    out.append(
        "- **`hybrid`** tests whether retrieval and factors compose. On "
        "small gold sets (n≈150, skewed minority class) raw accuracy "
        "differences under ~4pp are within seed noise — read balanced "
        "accuracy, Brier, and outcome-class accuracy as the signal-bearing "
        "metrics."
    )
    return "\n".join(out)


def _parse_domain_arg(s: str) -> tuple[str, list[Path]]:
    if "=" not in s:
        raise SystemExit(f"--domain must be 'Name=dir1,dir2,...'; got {s!r}")
    name, dirs = s.split("=", 1)
    return name.strip(), [Path(d.strip()) for d in dirs.split(",") if d.strip()]


def _cli(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=Path(__file__).name)
    p.add_argument("--domain", action="append", required=True, dest="domains")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(list(argv) if argv is not None else None)
    domain_runs = [_parse_domain_arg(d) for d in args.domains]
    md = build(domain_runs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
