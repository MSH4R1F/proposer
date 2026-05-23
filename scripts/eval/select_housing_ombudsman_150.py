#!/usr/bin/env python3
"""Cross-domain 150-gold build — stratified case selection.

Selects ~100 NEW Housing Ombudsman cases from the 1,000-case corpus at
``raw/housing_ombudsman/decisions`` (repo-root ``raw/``, NOT ``data/raw``),
excluding the cases already in
``data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl`` (the
canonical 48-case gold), and writes a selection manifest.

Stratification goal: the published-determination corpus is heavily skewed
to ``maladministration`` (700/1000) which maps to a tenant win. The
existing 48-case gold is 47:1 tenant. To make the 4-mode ablation's
``determination`` target (and the landlord-positive-class winner Brier)
non-degenerate, we deliberately OVER-SAMPLE the minority determinations
(reasonable_redress, no_maladministration, severe_maladministration,
resolved_with_intervention, outside_jurisdiction) and CAP the majority
(maladministration / service_failure).

Determination mapping: ``parsed.json.outcome_normalized`` uses hyphens
(e.g. ``service-failure``); the GoldCase ``Determination`` enum uses
underscores. We map hyphen->underscore and drop ``NONE`` (unparsed).

Deterministic: seeded shuffle (seed=42) so the selection is reproducible.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CORPUS_ROOT = REPO_ROOT / "raw" / "housing_ombudsman" / "decisions"
GOLD_PATH = REPO_ROOT / "data" / "gold_standard" / "housing_repairs_social_v2_strict_clean.jsonl"
OUT_MANIFEST = REPO_ROOT / "data" / "eval_artifacts" / "gold_build" / "housing-ombudsman-150-2026-05-21" / "selection.json"

# Hyphenated outcome_normalized -> Determination enum value.
_OUTCOME_MAP = {
    "maladministration": "maladministration",
    "severe-maladministration": "severe_maladministration",
    "service-failure": "service_failure",
    "reasonable-redress": "reasonable_redress",
    "no-maladministration": "no_maladministration",
    "resolved-with-intervention": "resolved_with_intervention",
    "outside-jurisdiction": "outside_jurisdiction",
}

# Per-determination caps for the NEW selection. Designed to lift the
# minority classes well above their corpus share so the eval target has
# real spread. None == take all available.
_TARGET_PER_DETERMINATION = {
    "maladministration": 34,            # cap the dominant class
    "service_failure": 22,
    "reasonable_redress": 18,           # landlord-favourable (legacy)
    "severe_maladministration": 14,
    "resolved_with_intervention": 10,
    "no_maladministration": None,       # take all (rare; landlord win)
    "outside_jurisdiction": None,       # take all (rare; landlord win)
}


def _trailing_number(slug: str) -> str | None:
    m = re.search(r"(\d{6,})$", slug)
    return m.group(1) if m else None


def _gold_case_numbers() -> set[str]:
    nums: set[str] = set()
    with GOLD_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cid = json.loads(line).get("case_id", "")
            m = re.search(r"(\d{6,})$", cid)
            if m:
                nums.add(m.group(1))
    return nums


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=OUT_MANIFEST)
    args = ap.parse_args()

    gold_nums = _gold_case_numbers()
    rng = random.Random(args.seed)

    # Bucket every eligible corpus case by mapped determination.
    by_det: dict[str, list[dict]] = defaultdict(list)
    skipped_in_gold = 0
    skipped_no_outcome = 0
    for slug in sorted(os.listdir(CORPUS_ROOT)):
        case_dir = CORPUS_ROOT / slug
        pj = case_dir / "parsed.json"
        if not pj.exists():
            continue
        num = _trailing_number(slug)
        if num and num in gold_nums:
            skipped_in_gold += 1
            continue
        try:
            parsed = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            continue
        outcome = parsed.get("outcome_normalized")
        det = _OUTCOME_MAP.get(outcome)
        if det is None:
            skipped_no_outcome += 1
            continue
        by_det[det].append(
            {
                "slug": slug,
                "case_number": num,
                "case_id": f"housing-ombudsman-{num}",
                "determination": det,
                "outcome_raw": parsed.get("outcome_raw"),
                "landlord_name": parsed.get("landlord_name"),
                "decision_date": parsed.get("decision_date"),
                "matter_types": parsed.get("complaint_categories") or [],
                "storage_path": str(case_dir),
                "source_url": parsed.get("source_url"),
            }
        )

    selected: list[dict] = []
    per_det_selected: Counter = Counter()
    for det, cap in _TARGET_PER_DETERMINATION.items():
        pool = list(by_det.get(det, []))
        rng.shuffle(pool)
        take = pool if cap is None else pool[:cap]
        selected.extend(take)
        per_det_selected[det] = len(take)

    # Stable order by case_id for reproducible downstream artifacts.
    selected.sort(key=lambda r: r["case_id"])

    manifest = {
        "seed": args.seed,
        "corpus_root": str(CORPUS_ROOT),
        "gold_baseline": str(GOLD_PATH),
        "n_gold_baseline": len(gold_nums),
        "n_selected": len(selected),
        "skipped_already_in_gold": skipped_in_gold,
        "skipped_no_outcome": skipped_no_outcome,
        "available_per_determination": {k: len(v) for k, v in sorted(by_det.items())},
        "selected_per_determination": dict(per_det_selected),
        "cases": selected,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps({k: v for k, v in manifest.items() if k != "cases"}, indent=2))
    print(f"\nmanifest -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
