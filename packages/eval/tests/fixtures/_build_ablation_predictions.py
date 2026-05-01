"""Generate synthetic per-mode prediction JSONLs for the 10-case corpus.

The four files produced demonstrate the RQ1 thesis claim:

    hybrid > rag_only > kg_only > llm_only

on accuracy, Brier, and ECE. They are deterministic and check into the
repo so CI + the worked example in docs/eval/ablation.md reproduce
without LLM calls.

Re-generate when the underlying corpus changes:

    python packages/eval/tests/fixtures/_build_ablation_predictions.py

Output files (alongside synthetic_corpus_10.jsonl):
    predictions_synthetic_hybrid.jsonl
    predictions_synthetic_rag_only.jsonl
    predictions_synthetic_kg_only.jsonl
    predictions_synthetic_llm_only.jsonl

Error model per mode:

| Mode      | Winner errors  | Calibration              |
|-----------|----------------|--------------------------|
| hybrid    | 0%             | confident, correct (1.0) |
| rag_only  | flip every 4th | overconfident (0.85)     |
| kg_only   | flip every 2nd | poorly calibrated (0.7)  |
| llm_only  | always SPLIT   | coinflip (0.5)           |
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[4]
sys.path.insert(0, str(_REPO_ROOT / "packages"))

from eval.dataset import load  # noqa: E402
from eval.schema import Winner  # noqa: E402

FIXTURES = _HERE.parent
GOLD = FIXTURES / "synthetic_corpus_10.jsonl"


_FLIP = {
    Winner.TENANT: Winner.LANDLORD,
    Winner.LANDLORD: Winner.TENANT,
    Winner.SPLIT: Winner.SPLIT,
}


def _winner_to_p_landlord(w: Winner, conf: float) -> float:
    """Map (winner, confidence) → P(landlord wins outright).

    LANDLORD returns `conf`; TENANT returns `1 - conf`. SPLIT is treated as
    maximum uncertainty for binary calibration here, so it returns 0.5.
    """
    if w is Winner.LANDLORD:
        return conf
    if w is Winner.TENANT:
        return 1.0 - conf
    return 0.5


def _row_for(g, *, winner_pick, confidence: float, idx_counter: list) -> dict:
    """Build a Prediction row dict for the given gold case.

    `idx_counter` is a single-element mutable list used as a global
    counter across the corpus, so flip-every-Nth patterns spread errors
    across cases (most synthetic cases have only one issue each).
    """
    gt = g.ground_truth_outcome
    overall_pred = winner_pick(gt.overall_winner, idx_counter[0])
    overall_p_landlord = _winner_to_p_landlord(overall_pred, confidence)

    per_issue = []
    for io in gt.per_issue:
        pred_winner = winner_pick(io.winner, idx_counter[0])
        idx_counter[0] += 1
        per_issue.append(
            {
                "issue": io.issue,
                "predicted_winner": pred_winner.value,
                "win_probability": _winner_to_p_landlord(pred_winner, confidence),
                "predicted_amount_gbp": str(io.awarded_gbp),
            }
        )

    if not gt.per_issue:
        # Unapportioned case — still consume one counter slot so the next
        # case lands in the right bucket.
        idx_counter[0] += 1

    return {
        "case_id": g.case_id,
        "overall_winner": overall_pred.value,
        "overall_win_probability": overall_p_landlord,
        "total_predicted_gbp": str(gt.total_awarded_gbp),
        "per_issue": per_issue,
    }


def _hybrid_pick(true_w, idx):
    return true_w


def _rag_only_pick(true_w, idx):
    # Flip every 4th issue.
    if idx % 4 == 3:
        return _FLIP[true_w]
    return true_w


def _kg_only_pick(true_w, idx):
    # Flip every 2nd issue (heavier error rate than rag_only).
    if idx % 2 == 1:
        return _FLIP[true_w]
    return true_w


def _llm_only_pick(true_w, idx):
    return Winner.SPLIT


_MODES = {
    "hybrid": (_hybrid_pick, 1.0),
    "rag_only": (_rag_only_pick, 0.85),
    "kg_only": (_kg_only_pick, 0.7),
    "llm_only": (_llm_only_pick, 0.5),
}


def main() -> int:
    gold = load("synthetic_corpus_10", base_dir=FIXTURES, strict=True).cases
    if not gold:
        print("ERROR: synthetic gold corpus is empty", file=sys.stderr)
        return 1

    for mode, (pick_fn, conf) in _MODES.items():
        out = FIXTURES / f"predictions_synthetic_{mode}.jsonl"
        idx_counter = [0]
        with out.open("w") as f:
            for g in gold:
                row = _row_for(
                    g,
                    winner_pick=pick_fn,
                    confidence=conf,
                    idx_counter=idx_counter,
                )
                f.write(json.dumps(row) + "\n")
        print(f"wrote {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
