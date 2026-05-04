# Dataset Loader & Audit

`packages/eval/dataset.py` is the librarian for the gold-standard corpus. Pure Python: it reads the JSONL on disk, validates each row against the schema, and exposes filter and audit helpers that every downstream metric and the ablation runner consume.

## Linear

- Parent: [SHA-28](https://linear.app/sharifbuilders/issue/SHA-28) — Build gold standard test set
- Lands: schema rework (SHA-90, SHA-91, SHA-92, SHA-93, SHA-95) is the prerequisite — `cited_authorities`, `disputed_amount_gbp`, `claim_types` are all consumed here.

## Constants

| Constant | Value | Source |
|---|---|---|
| `TRAIN_CUTOFF` | `date(2022, 12, 31)` | PILOT methodology, interim report |
| `TEST_START` | `date(2023, 1, 1)` | PILOT methodology, interim report |
| `STRATIFICATION_FLOOR` | `5` | SHA-28 DoD: ≥5 cases per claim type |

## Public API

### `load(version="housing_v1", *, base_dir=None, strict=False) -> LoadResult`

Reads `<base_dir>/<version>.jsonl`. Default `base_dir` is `Path.cwd() / "data" / "gold_standard"`.

- **Lenient (default):** collects malformed-JSON and validation errors into `LoadResult.errors`; returns the valid cases. Blank lines are skipped silently.
- **Strict:** raises the first `json.JSONDecodeError` or `pydantic.ValidationError`.
- `FileNotFoundError` is raised regardless of `strict` if the file is missing.

```python
from eval import load

result = load("housing_v1")          # picks up data/gold_standard/housing_v1.jsonl
print(len(result.cases), len(result.errors))
if not result.is_clean:
    for err in result.errors:
        print(f"line {err.line_number}: {err.error}")
```

### `train(cases, *, strict=False) -> list[GoldCase]`

Returns cases with `decision_date <= TRAIN_CUTOFF` and runs a leakage check on the train subset: every authority in `case.cited_authorities` must have `cited_date <= TRAIN_CUTOFF`.

- **Lenient (default):** logs one warning per leakage violation via `eval.dataset` logger, returns cases anyway.
- **Strict:** raises `ValueError` on the first violation.

The leakage check is what cashes in the `Authority` work from SHA-90 — without `cited_date` on each authority, this audit is uncomputable.

### `test(cases) -> list[GoldCase]`

Returns cases with `decision_date >= TEST_START`. No audits — test cases may cite authorities of any date by construction.

### `audit(cases) -> AuditReport`

Pure function. Returns:

- `n_cases`, `train_count`, `test_count`
- `leakage_violations: list[LeakageViolation]`
- `understratified_types: dict[ClaimType, int]` — every type below `STRATIFICATION_FLOOR` and its current count. Multi-type cases (per SHA-92's `claim_types` semantics) count toward each of their types.
- `region_distribution: dict[str, int]`
- `case_size_distribution: dict[CaseSize, int]`
- `is_clean: bool` — True iff zero leakage and every type at or above floor.

## CLI

```bash
PYTHONPATH=packages python -m eval.dataset audit data/gold_standard/housing_v1.jsonl
PYTHONPATH=packages python -m eval.dataset audit data/gold_standard/housing_v1.jsonl --strict
PYTHONPATH=packages python -m eval.dataset audit data/gold_standard/housing_v1.jsonl --json eval/results/audit.json
PYTHONPATH=packages python -m eval.dataset audit data/gold_standard/housing_v1.jsonl --evidence
```

| Flag | Effect |
|---|---|
| (none) | Print text report to stdout. Exit 0 always. |
| `--strict` | Exit 1 if `report.is_clean is False`. CI gate flag. |
| `--json PATH` | Also write JSON report to `PATH` (parents created). |
| `--evidence` | Also write JSON to `<cwd>/.sisyphus/evidence/eval/audit_<YYYY-MM-DD>.json`. |

Load errors land on stderr; CLI does not abort on them (lenient by default).

## Housing Ombudsman stratified eval manifest

`data/eval/housing_ombudsman_stratified_50.jsonl` is deliberately **not**
loaded through `eval.dataset.load(...)` yet. It is a selection manifest for
`housing.repairs_social.v1`, not a fully adjudicated `GoldCase` corpus.

The manifest is built from the 1,000-case Housing Ombudsman repairs/social
scrape and records the 50 source determinations that should be promoted into
reviewed gold next:

```bash
python scripts/eval/build_housing_ombudsman_stratified_eval.py --data-dir "$DATA_DIR"
```

Current selection summary:

| Field | Value |
|---|---:|
| Source cases | 1,000 |
| Eligible cases with decision dates | 936 |
| Excluded missing decision date | 64 |
| Selected cases | 50 |
| Selection seed | 42 |

Outcome distribution:

| Outcome | Cases |
|---|---:|
| `maladministration` | 32 |
| `service-failure` | 7 |
| `reasonable-redress` | 4 |
| `severe-maladministration` | 3 |
| `resolved-with-intervention` | 2 |
| `outside-jurisdiction` | 1 |
| `unknown` | 1 |

Primary matter distribution:

| Matter type | Cases |
|---|---:|
| `repairs_disrepair` | 26 |
| `repairs_damp_mould` | 24 |

Each row includes `target_source_id`, `raw_text_sha256`, source paths, forum,
domain, corpus version, outcome stratum, matter-type stratum, and
`annotation_status="needs_gold_labeling"`. Once the SHA-28/SHA-127 review path
extracts compensation/orders/source spans and writes `LabelingProvenance`, the
resulting reviewed rows can move into `data/gold_standard/` and be loaded by
the normal dataset API.

## Lenient default, strict opt-in

Pilot phase needs forgiveness: a half-broken corpus is the normal state during annotation. CI before shipping needs the opposite. Pattern:

| Caller | Mode |
|---|---|
| Annotation CLI (Phase 3) | Lenient — skip-and-log so the annotator can keep iterating. |
| Metrics in development (Phase 4) | Lenient — fixtures are tiny and stratification is meaningless. |
| Production metric run on the real gold set | Strict — `PYTHONPATH=packages python -m eval.dataset audit ... --strict` as a CI step before any Brier/accuracy reporting. |
| Ablation runner (Phase 5) | Strict — a corrupt corpus invalidates every ablation comparison. |

## What this enables

| Consumer | Method called | Why |
|---|---|---|
| Phase 3 annotation CLI | `load(strict=False)` | iterate on a corpus that may have a half-edited line |
| Phase 4 accuracy / Brier / ECE | `train(cases)`, `test(cases)` | run metrics on the right split |
| Phase 4 hallucination audit | `train(cases)` | resampling on the train split for bootstrap CIs |
| Phase 5 ablation runner | `load(strict=True)`, `audit(cases)` | reproducible numbers, leakage-free |
| CI nightly | `PYTHONPATH=packages python -m eval.dataset audit ... --strict --evidence` | fail fast, archive evidence |

## What this does NOT do

- It does not write to the gold-set file. The annotation CLI (Phase 3) owns that.
- It does not load the Housing Ombudsman stratified-50 manifest until that
  manifest is promoted to adjudicated `GoldCase` rows.
- It does not compute metrics. Phase 4 metric modules consume the splits and produce numbers.
- It does not run the prediction model. Phase 5 ablation runner does that.

## Related

- [`docs/eval/gold-schema.md`](gold-schema.md) — the `GoldCase` schema this loader validates against.
- [`docs/eval/housing-ombudsman-stratified-50.md`](housing-ombudsman-stratified-50.md) — selection method for the Housing Ombudsman eval manifest.
- `.sisyphus/plans/track-a-plan.md` — Track A overall plan.
- `docs/superpowers/plans/2026-04-28-gold-set-dataset.md` — the bite-sized TDD plan that built this module.
