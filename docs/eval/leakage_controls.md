# Eval-Time Leakage Controls

> **Status**: SHA-20 Phase 7. Implementation in
> [`packages/eval/leakage.py`](../../packages/eval/leakage.py); tests in
> `packages/eval/tests/test_leakage_controls.py`.

The eval harness enforces three classes of leakage control on every
prediction. Each is **fail-closed**: if a control would be skipped, the
runner aborts the case rather than emit a leaky result.

## 1. Target-source exclusion

The tribunal decision a gold case was annotated from must never be
retrievable while predicting that case. The same applies to any
explicit `excluded_source_ids` on the gold row (typically appeals or
related cases sharing facts).

Enforced at retrieval-filter time via
`build_eval_filter_envelope(gold_case)`, which produces a
`RetrievalFilterEnvelope` with:

```
excluded_source_ids = [target_source_id, *gold_case.excluded_source_ids]
```

After retrieval, `assert_no_target_source_in_results(results, gold)`
performs a defensive sanity check; any leak raises
`TargetSourceExclusionError`.

## 2. Temporal validity

A gold case's predictions must only see authorities that pre-date its
decision. `enforce_temporal_validity(citations, gold_case)` raises
`TemporalLeakageError` when any cited authority's `cited_date` exceeds
`gold.decision_date`.

The retrieval envelope additionally enforces `as_of_date =
gold.law_effective_date` so retrieval-side metadata filters drop
post-effective-date statutes/guidance before reaching the prediction
engine.

For retrospective sweeps (e.g. running 2024 model versions over 2019
cases) the call site can pass `retrospective=True`, which clears
`max_decision_date` while keeping every other filter.

## 3. Namespace match + cross-domain guard

`enforce_namespace_match(domain_spec, gold_case)` asserts
`gold.retrieval_namespace_id` is one of the namespaces declared by the
selected domain spec. Mismatches raise `NamespaceMismatchError`.

For cross-domain retrieval inside eval,
`require_eval_only_for_cross_domain(args)` requires both
`--cross-domain` AND `--eval-only` to be set. Setting `--cross-domain`
without `--eval-only` raises `CrossDomainEvalRefused`.

The envelope is also unconditionally `eval_only=True` — even when a
caller explicitly passes `eval_only=False`. Production code paths are
expected to construct their own envelope, never reuse an eval one.

## How `build_eval_filter_envelope` composes the controls

```python
env = build_eval_filter_envelope(
    gold_case,
    retrospective=False,   # default; set True for retrospective sweeps
    cross_domain=False,    # default; cross-domain retrieval refused unless --eval-only
)
```

The returned envelope contains:

| Field | Value |
| --- | --- |
| `excluded_source_ids` | `[target_source_id, *excluded_source_ids]` (deduped) |
| `max_decision_date` | `gold.decision_date` (None if `retrospective=True`) |
| `as_of_date` | `gold.law_effective_date` |
| `forum` | from `gold.forum` (None if unknown enum value) |
| `source_kind` | from `gold.source_kind` |
| `source_publisher` | from `gold.source_publisher` |
| `matter_type` | `gold.matter_type` |
| `cross_domain_allowed` | `bool(cross_domain)` |
| `eval_only` | always `True` |

Both Chroma and BM25 backends honour the same envelope inside
`HybridRetriever`, so the controls are uniform regardless of backend.

## The `--cross-domain --eval-only` requirement

Cross-domain retrieval is allowed in eval only when the caller
explicitly opts in with **both** flags. This guard exists so that a
future code path that copies eval flags into runtime cannot accidentally
disable the safeguard. If a caller passes `--cross-domain` alone:

```text
CrossDomainEvalRefused: cross-domain eval requires --cross-domain AND --eval-only
```

## Result-hash inputs

The eval result hash captures every component the controls depend on,
so reproducibility is auditable:

- `corpus_version` (per-namespace)
- `namespace_id` (must match the domain spec)
- `prompt_pack_id` / `prompt_pack_hash`
- `ontology_id` / `ontology_hash`
- provider/model role (e.g. `claude-sonnet-4.6` for prediction,
  `gpt-4o-mini` for triage)
- `verifier_hash` (sha256 of the citation verifier source)
- retrieval budget (`top_k`, `min_confidence_threshold`,
  `min_similarity_threshold`)

A change in any of these inputs produces a different result hash, which
the gate artifact captures via `prompt_pack_hash`, `ontology_hash`,
`domain_spec_hash`, `verifier_hash`, and `corpus_version`. See
[`docs/eval/gates.md`](gates.md) for the launch-gate contract.

## Related

- [`docs/eval/gold-schema.md`](gold-schema.md) — gold-case fields
- [`docs/eval/methodology.md`](methodology.md) — overall harness flow
- [`packages/eval/leakage.py`](../../packages/eval/leakage.py) — code
- [`packages/eval/tests/test_leakage_controls.py`](../../packages/eval/tests/test_leakage_controls.py) — tests
