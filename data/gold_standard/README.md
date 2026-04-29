# Gold-Standard Evaluation Set

This directory holds the production gold-standard JSONL files. Format: one validated `GoldCase` JSON object per line.

| File | Purpose | Maintainer |
|---|---|---|
| `housing_v1.jsonl` | Housing-tribunal corpus, 50–100 annotated cases (2019–2024 PILOT split) | Paralegal reviewers |

## How to add a case

See [`docs/eval/reviewer-guide.md`](../../docs/eval/reviewer-guide.md). The short version:

```bash
python scripts/eval/annotate.py template > my_case.json
# edit my_case.json
python scripts/eval/annotate.py validate my_case.json
python scripts/eval/annotate.py append my_case.json
```

## How to audit

```bash
python -m eval.dataset audit data/gold_standard/housing_v1.jsonl
```

Reports leakage violations, under-stratified claim types, and region/case-size distributions. `--strict` makes the exit code non-zero when not clean (CI gate).

## Schema

Defined in `packages/eval/schema.py`. See [`docs/eval/gold-schema.md`](../../docs/eval/gold-schema.md) for human-readable field reference and the 10 cross-field invariants.

## v1 freeze policy

`v1` is mutable until both: (a) full pilot batch (10 cases) signed off by reviewer, and (b) every HIGH-severity Codex sparring item resolved. Once frozen, breaking field changes require `v2`. See [SHA-95](https://linear.app/sharifbuilders/issue/SHA-95).
