#!/usr/bin/env python3
"""Score a housing 4-mode ablation (tenant/landlord winner semantics).

The employment scorer (``score_employment_et_eval.py``) is hardcoded to
the claimant/respondent family with ``Winner.RESPONDENT`` as positive
class. Housing domains (repairs_social Ombudsman, property_chamber RRO)
use tenant/landlord. This scorer mirrors the employment scorer's metric
set but with the **landlord** side as the positive class (the minority
class in both housing corpora — Ombudsman finds for the resident ~96% of
the time; RRO grants for the tenant ~82% of the time — so landlord is the
hard, signal-bearing class, analogous to respondent in employment).

Consumes the per-mode JSONLs that ``predict_all.py`` writes (``<mode>.jsonl``,
possibly concatenated across shards) plus the gold JSONL. Emits a
``_metrics.json`` in the SAME shape ``score_employment_et_eval.py`` writes
(keys: mode, n_cases, accuracy, balanced_accuracy, respondent_brier
[reused for the positive-class Brier], ece, log_loss,
determination_accuracy, per_class_accuracy, per_class_counts) so the
cross-domain aggregator/report consume all three domains uniformly.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Sequence

POSITIVE = "landlord"  # positive class for Brier/log-loss/ECE


def _load_gold(path: Path) -> dict[str, dict]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        gto = d.get("ground_truth_outcome", {})
        out[d["case_id"]] = {
            "winner": gto.get("overall_winner"),
            "determination": gto.get("determination"),
        }
    return out


def _load_preds(path: Path) -> dict[str, dict]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        winner = d.get("overall_winner")
        p = d.get("overall_win_probability")
        # ``overall_win_probability`` from predict_all is ALREADY P(landlord)
        # — eval.adapter._confidence_to_p_landlord emits it as a fixed-class
        # (landlord = positive) probability regardless of the predicted
        # winner (LANDLORD_WIN→conf, TENANT_WIN→1−conf, SPLIT→0.5). An earlier
        # version of this scorer re-inverted it (1−p for tenant), which
        # DOUBLE-inverted and manufactured a fake "RAG doubles Brier"
        # regression. Use it directly.
        try:
            p_landlord = float(p)
        except (TypeError, ValueError):
            p_landlord = 0.5
        out[d["case_id"]] = {
            "winner": winner,
            "p_landlord": p_landlord,
            "determination": d.get("predicted_determination"),
            "abstained": bool(d.get("abstained")),
        }
    return out


def _brier(pairs: list[tuple[float, float]]) -> float:
    if not pairs:
        return float("nan")
    return sum((p - a) ** 2 for p, a in pairs) / len(pairs)


def _log_loss(pairs: list[tuple[float, float]]) -> float:
    if not pairs:
        return float("nan")
    eps = 1e-9
    return sum(
        -(a * math.log(min(max(p, eps), 1 - eps)) + (1 - a) * math.log(1 - min(max(p, eps), 1 - eps)))
        for p, a in pairs
    ) / len(pairs)


def _ece(pairs: list[tuple[float, float]], n_bins: int = 10) -> float:
    if not pairs:
        return float("nan")
    total = len(pairs)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        bucket = [
            (p, a) for p, a in pairs if (lo <= p < hi or (i == n_bins - 1 and p == hi))
        ]
        if not bucket:
            continue
        ap = sum(p for p, _ in bucket) / len(bucket)
        aa = sum(a for _, a in bucket) / len(bucket)
        ece += (len(bucket) / total) * abs(ap - aa)
    return ece


def _balanced_accuracy(preds: list[str], golds: list[str]) -> float:
    per: dict[str, list[int]] = defaultdict(list)
    for p, g in zip(preds, golds):
        per[g].append(1 if p == g else 0)
    if not per:
        return float("nan")
    return sum(sum(v) / len(v) for v in per.values()) / len(per)


def _score_mode(mode: str, gold: dict, preds: dict) -> dict:
    ids = [c for c in gold if c in preds]
    pred_w = [preds[c]["winner"] for c in ids]
    gold_w = [gold[c]["winner"] for c in ids]
    pred_d = [(preds[c]["determination"] or "") for c in ids]
    gold_d = [(gold[c]["determination"] or "") for c in ids]
    n = len(ids)

    acc = sum(1 for p, g in zip(pred_w, gold_w) if p == g) / n if n else float("nan")
    bal = _balanced_accuracy(pred_w, gold_w)
    counts = Counter(gold_w)
    hits: dict[str, int] = defaultdict(int)
    for p, g in zip(pred_w, gold_w):
        if p == g:
            hits[g] += 1
    per_class_acc = {c: hits[c] / counts[c] for c in counts}

    pairs = [
        (preds[c]["p_landlord"], 1.0 if gold[c]["winner"] == POSITIVE else 0.0)
        for c in ids
        if gold[c]["winner"] in (POSITIVE, "tenant")
    ]
    det_acc = (
        sum(1 for p, g in zip(pred_d, gold_d) if p == g and g) / n if n else float("nan")
    )
    abst = sum(1 for c in ids if preds[c]["abstained"]) / n if n else 0.0

    return {
        "mode": mode,
        "n_cases": n,
        "accuracy": acc,
        "balanced_accuracy": bal,
        "respondent_brier": _brier(pairs),  # positive class = landlord
        "ece": _ece(pairs),
        "log_loss": _log_loss(pairs),
        "determination_accuracy": det_acc,
        "abstention_rate": abst,
        "per_class_accuracy": per_class_acc,
        "per_class_counts": dict(counts),
        "positive_class": POSITIVE,
    }


def _cli(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=Path(__file__).name)
    p.add_argument("--gold", required=True, type=Path)
    p.add_argument("--pred-dir", required=True, type=Path, help="dir with <mode>.jsonl")
    p.add_argument("--modes", default="llm_only,rag_only,kg_only,hybrid")
    p.add_argument("--out", type=Path, default=None, help="defaults to <pred-dir>/_metrics.json")
    args = p.parse_args(list(argv) if argv is not None else None)

    gold = _load_gold(args.gold)
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    results = []
    for mode in modes:
        f = args.pred_dir / f"{mode}.jsonl"
        if not f.exists():
            print(f"WARN: missing {f}")
            continue
        preds = _load_preds(f)
        results.append(_score_mode(mode, gold, preds))

    out = args.out or (args.pred_dir / "_metrics.json")
    out.write_text(json.dumps({"metrics": results}, indent=2, default=str), encoding="utf-8")
    # Print table.
    print(f"{'mode':12} {'n':>4} {'acc':>7} {'bal':>7} {'brier(L)':>9} {'logloss':>8} {'det':>7}")
    for r in results:
        print(
            f"{r['mode']:12} {r['n_cases']:>4} {r['accuracy']:>7.3f} "
            f"{r['balanced_accuracy']:>7.3f} {r['respondent_brier']:>9.3f} "
            f"{r['log_loss']:>8.3f} {r['determination_accuracy']:>7.3f}"
        )
    print(f"metrics -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
