#!/usr/bin/env bash
# Cross-domain 150-gold 4-mode ablation — 3 seeds.
#
# Concurrency model (learned the hard way on a 16GB host):
#   * ChromaDB does NOT support concurrent reads from multiple processes
#     against the same persist dir — they deadlock on the SQLite lock.
#     So the Chroma-using modes (rag_only, hybrid) each get their OWN
#     index copy under /tmp/idx_copies/copy{seed}. The 3 seeds of a slow
#     mode then run in parallel safely.
#   * 12 heavy processes OOM-kill a 16GB host. So we run in waves:
#       wave A: rag_only   x 3 seeds (own copies)
#       wave B: hybrid     x 3 seeds (own copies)
#       wave C: llm_only   x 3 seeds (shared data/indices; no Chroma)
#       wave D: kg_only    x 3 seeds (shared data/indices; no Chroma)
#     3 concurrent processes per wave stays well under the memory ceiling.
#
# gpt-5.5 (reasoning_effort=medium) produces 1-2 case flips per run at
# default temperature — that is the "seed" variation the aggregator
# captures as mean ± std.
#
# Prereq: 3 index copies must exist at /tmp/idx_copies/copy{1,2,3}
# (each a full {namespace}/{corpus_version} tree). The driver creates them.
#
# Usage: bash scripts/eval/run_housing_150_ablation.sh
set -uo pipefail
cd "$(dirname "$0")/../.."

GOLD=data/gold_standard/housing_repairs_social_v1_150.jsonl
SIDECAR=data/eval_artifacts/factor_assertions/housing_repairs_social_v1.factor_assertions.json
SHARED_INDEX_ROOT=data/indices
COPY_ROOT=/tmp/idx_copies
BASE=eval/predictions/housing_150_ablation_20260521
LOGDIR=/tmp/housing150_runs
mkdir -p "$LOGDIR"

export LLM_PREDICTION_REASONING_EFFORT=${LLM_PREDICTION_REASONING_EFFORT:-medium}

run_one() {
  local seed=$1 mode=$2 index_root=$3
  local out="${BASE}/seed${seed}"
  local runid="housing150-s${seed}-${mode}-20260521"
  PYTHONPATH=packages venv/bin/python3 scripts/eval/predict_all.py \
    --gold "$GOLD" \
    --out-dir "$out" \
    --engine live --client openai \
    --modes "$mode" \
    --top-k 5 \
    --rag-index-root "$index_root" \
    --factor-assertion-sidecar "$SIDECAR" \
    --run-id "$runid" \
    > "${LOGDIR}/seed${seed}_${mode}.log" 2>&1
}

# Chroma-using modes: per-seed index copy, 3 in parallel.
for MODE in rag_only hybrid; do
  echo "=== wave: ${MODE} x 3 seeds (own index copies) ==="
  for SEED in 1 2 3; do
    run_one "$SEED" "$MODE" "${COPY_ROOT}/copy${SEED}" &
    echo "launched seed${SEED}/${MODE} PID=$!"
  done
  wait
  echo "=== ${MODE} wave done ==="
done

# Non-Chroma modes: shared index root is fine, 3 in parallel.
for MODE in llm_only kg_only; do
  echo "=== wave: ${MODE} x 3 seeds (shared index) ==="
  for SEED in 1 2 3; do
    run_one "$SEED" "$MODE" "$SHARED_INDEX_ROOT" &
    echo "launched seed${SEED}/${MODE} PID=$!"
  done
  wait
  echo "=== ${MODE} wave done ==="
done

echo "ALL 12 (seed x mode) JOBS COMPLETE"
