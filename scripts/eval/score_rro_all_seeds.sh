#!/usr/bin/env bash
# Score every seed dir of an RRO sweep + aggregate (cross-domain build).
# Usage: bash scripts/eval/score_rro_all_seeds.sh <out-root> <gold>
set -euo pipefail
cd "$(dirname "$0")/../.."

OUT_ROOT="${1:-data/eval_artifacts/runs/rro_eval40}"
GOLD="${2:-data/gold_standard/housing_property_chamber_rro_v1_eval40.jsonl}"

metrics_files=()
for seed_dir in "$OUT_ROOT"/seed*; do
  [ -d "$seed_dir" ] || continue
  echo "=== scoring $seed_dir ==="
  PYTHONPATH=packages venv/bin/python scripts/eval/score_rro_eval.py \
    --gold "$GOLD" --pred-dir "$seed_dir" --out "$seed_dir"
  metrics_files+=("$seed_dir/_metrics.json")
done

echo "=== aggregating ${#metrics_files[@]} seed metrics ==="
PYTHONPATH=packages venv/bin/python scripts/eval/aggregate_rro_runs.py \
  --metrics "${metrics_files[@]}" \
  --out "$OUT_ROOT/_aggregate.json"
