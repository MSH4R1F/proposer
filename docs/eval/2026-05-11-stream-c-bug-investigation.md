# Stream C Bug Investigation - Why Hybrid Does Not Beat RAG-Only

Date: 2026-05-11
Branch: `codex/stream-c-prediction-path-plan`
Scope: diagnostic only; no Stream D extractor build.

## Executive Summary

The original headline was directionally right but incomplete: hybrid has no measurable lift because the KG still does not pass the graph-quality gate. The investigation found three concrete implementation/data limitations behind that:

1. **Chunked eval did not auto-load the case-side factor sidecar.** The previous chunked runs used `/tmp/stream_c_chunks/chunk_N.jsonl`; filename-based auto-resolution looked for `chunk_N.factor_assertions.json`, not the canonical strict-clean sidecar. This explains why prior metadata showed `evidence_backed_factor_count=0` even though the sidecar on disk had 486 supported assertions.
2. **Annotator `source_span` text was dropped.** `FactorAssertion.supported_by` IDs existed, but they were dangling IDs with no typed `EvidenceSpan.quote_text`. I patched the promoter/sidecar to persist 486 `EvidenceSpan` rows.
3. **Once the sidecar is actually hydrated, the factor-constrained proposition seed pass returns zero candidates for chunk 0.** It searches exact `issue_ids=["repairs_damp_mould"]`, while the proposition store is tagged with labels like `repairs`, `damp_and_mould`, and `complaint_handling`.

After the patch, an offline chunk-0 gate probe hydrates 10-13 factors and 10-13 EvidenceSpans per case. The evidence failures disappear:

```text
before: evidence_backed_factor_count 0 < min 5
before: unsupported_factor_rate 1.00 > max 0.30
before: source_span_coverage 0.00 < min 0.80

after: graph_quality_score=1.0
after failures: dated_event_count 0 < min 2; issue_count 0 < min 1; outcome_or_remedy_candidate_count 0 < min 1
```

A live isolated gate probe with `STREAM_C_FACTOR_RETRIEVAL=0` confirmed the same metadata on 4 completed chunk-0 rows: `graph_quality_score=1.0`, `kg_used_for_prediction=False`, and only the dated-event/issue/outcome failures remain. The remaining 2 live calls were stopped to preserve budget.

## Patch Summary

Implemented narrow eval/data fixes:

- `scripts/eval/promote_factor_annotations_to_gold.py`
  - Preserves canonical `source_span` as a typed `EvidenceSpan` dict.
  - Validates promoted `EvidenceSpan` rows through Pydantic.
- `packages/eval/factor_assertion_sidecar.py`
  - Adds backward-compatible `load_full_sidecar(...)`.
  - Persists optional `evidence_spans_by_case_id`.
  - Hydrates both `factor_assertions` and `evidence_spans`.
- `packages/kg_builder/models/graph.py`
  - Adds duck-typed `evidence_spans: List[Any]`.
- `scripts/eval/predict_all.py`
  - Fixes chunked gold sidecar resolution by finding a sidecar whose case-id set covers the chunk case IDs.
  - Adds repo root to `sys.path` so subprocess tests can import `packages.*` modules when proposition-store auto-load triggers.
- `data/eval_artifacts/factor_assertions/housing_repairs_social_v2_strict_clean.factor_assertions.json`
  - Re-promoted from the May 9 annotations: 48 cases, 486 FactorAssertions, 486 EvidenceSpans.

## Validation

Targeted tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages ./venv/bin/pytest -p no:cacheprovider \
  scripts/eval/tests/test_promote_factor_annotations.py \
  packages/eval/tests/test_factor_assertion_sidecar.py \
  packages/eval/tests/test_predict_all.py \
  packages/legal_core/tests/test_factor_assertion.py \
  packages/legal_core/tests/test_evidence_span.py -q
# 57 passed

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages ./venv/bin/pytest -p no:cacheprovider \
  packages/llm_orchestrator/tests/test_positive_control_kg_smoke.py -q
# 7 passed
```

Probes:

- Re-promote: `486` FactorAssertions and `486` EvidenceSpans written.
- Offline chunk-0 gate probe: sidecar resolves from `/tmp/stream_c_chunks/chunk_0.jsonl` to the strict-clean sidecar; evidence/source-span failures vanish.
- Live factor-constrained probe: `eval/predictions/stream_c_h1_sidecar_probe_2026_05_10_chunk_0/`; 6/6 rows abstained before prediction because factor-constrained proposition retrieval returned zero sufficient cases.
- Live isolated gate probe: `eval/predictions/stream_c_h1_gate_probe_no_factor_retrieval_2026_05_10_chunk_0/`; stopped after 4 rows once all showed the same metadata pattern.

## Hypothesis Verdicts

### H1 - Promoter drops evidence spans

**Verdict: confirmed, but not exactly as stated.**

`source_span` text was dropped. However, `supported_by` and `source_span_refs` were already populated with deterministic `es_promoted_*` IDs. The true bug was that those IDs were not backed by typed `EvidenceSpan` rows, and chunked eval was not loading the sidecar anyway.

Evidence:

- `scripts/eval/promote_factor_annotations_to_gold.py` previously generated span IDs but did not persist `canonical["source_span"]`.
- Current sidecar before patch: 486/486 assertions had non-empty `supported_by`, but 0 typed evidence spans.
- After patch/re-promote: 486 typed evidence spans.
- Offline gate probe on chunk 0: evidence-backed factors are 10-13 per case; graph score is 1.0; evidence/source-span failures disappear.

Recommendation: keep this patch. It is cheap and fixes artifact integrity. Expected outcome lift by itself: **near zero**, because the gate still fails on dated events, issues, and outcome candidates. Expected diagnostic lift: **high**, because it separates evidence-link failures from the remaining ontology gaps.

### H2 - Gate requires more than factor coverage

**Verdict: confirmed, with one extra smoke-test caveat.**

The positive-control fixture contains real `EvidenceSpan`, `FactorAssertion`, `Proposition`, and `OutcomeComponent` files, but no real Event, IssueClaim, or OutcomeCandidate fixture files. The e2e smoke passes because its hand-shaped `_FixtureRepairsKG` adds synthetic top-level `dated_events`, `issues`, and `candidate_outcomes` fields.

Production mismatch:

- `GraphBuilder` creates `EventNode` and `IssueNode` entries inside `kg.nodes`.
- `IssuePredictor._compute_graph_quality_score(...)` does not count those nodes. It only reads top-level `case_graph.dated_events`, `case_graph.issues`, and `case_graph.candidate_outcomes`.
- The production KG therefore reports `issue_count=0` even when `kg.nodes` contains an issue node.

Recommendation: before building Stream D, decide whether the gate should count existing `KnowledgeGraph.nodes` by `NodeType` as a compatibility bridge, or whether Stream D must hydrate the exact top-level fields the smoke test uses. Cost: **0.5-1 day** for a bridge and tests, or **5-10 days** for full Stream D extractors. Expected lift: bridge alone may make `issue_count` pass, but dated events/outcome candidates still need data; full Stream D is required for real KG activation.

### H3 - Factor card biases the LLM toward landlord

**Verdict: not supported as the main cause.**

The two May 9 cases where hybrid lost and `rag_only` was right were `housing-ombudsman-202401431` and `housing-ombudsman-202408056`. Prediction rows do not embed factor-card text, so I inspected the sidecar factor assertions that would render into the card.

`housing-ombudsman-202401431`: factor sidecar was not landlord-dominated. It had 11 factors, 4 human-review flagged, roughly 8 pro-claimant / 2 pro-respondent / 1 neutral. Clean pro-claimant signals included `hazard_or_disrepair_reported=True`, `landlord_notice_established=True`, `records_inadequate=True`, `vulnerability_known=True`, and delay factors. Hybrid nevertheless retrieved/use-weighted no-maladministration or low-severity comparators (`london-borough-of-lewisham-202527711`, `royal-borough-of-greenwich-202337916`, `the-riverside-group-limited-202406793`) and predicted landlord/no maladministration. RAG-only retrieved `paragon-asra-housing-limited-202509212` and stayed tenant/service-failure.

`housing-ombudsman-202408056`: factor sidecar again was not dominated by review or landlord factors. It had 9 factors, 3 human-review flagged, roughly 7 pro-claimant / 2 pro-respondent. The stronger problem was artifact integrity: hybrid's citation verifier removed all 3 supporting citations (`removal_rate=1.0`, `needs_reprediction=True`), leaving `retrieved_cases=[]` and `supporting_cases=[]`, yet the row still carried a landlord/no-maladministration outcome. RAG-only kept verified damp/mould comparators and predicted tenant/service-failure.

Recommendation: do not spend time filtering human-review factors as the primary fix. Add a guard that treats `needs_reprediction=True` with zero verified citations as an invalid row for eval or forces a re-prediction path. Cost: **0.5 day**. Expected lift: small on winner accuracy, but useful for artifact trustworthiness.

### H4 - Retrieval payload composition is noisy

**Verdict: supported, and there is a stronger underlying bug.**

Subagent diffing found 69/96 paired rows across May 9 and May 10 had different `retrieved_cases` lists/order; 52 had hybrid-only cases. In sampled disagreements, hybrid-only extras often skewed low-severity, complaint-handling-heavy, or off-target.

New finding: the previous chunked backfills did not actually hydrate factors, so "factor_constrained" usually fell back to the repairs purposeful chunk-RAG path. Once factors are hydrated, `_retrieve_via_factor_retriever(...)` returns a non-None but empty/insufficient `IssueRetrievalResult`, so D5 fallback does not trigger.

Root cause of the empty factor path:

```text
JsonlPropositionStore.search_by_issue_tags(["repairs_damp_mould"]) -> 0
JsonlPropositionStore.search_by_issue_tags(["repairs_disrepair"]) -> 0
JsonlPropositionStore.search_by_issue_tags(["repairs"]) -> 10
JsonlPropositionStore.search_by_issue_tags(["damp_and_mould"]) -> 10
JsonlPropositionStore.search_by_issue_tags(["complaint_handling"]) -> 10
```

The FactorRetriever seed pass uses exact issue tags from `issue.issue_type.value`. The proposition tagger uses natural domain tags. Those contracts do not meet.

Recommendation: do not change FactorRetriever without sign-off, but the next targeted fix should be a small issue-tag normalization layer or proposition tagger backfill that adds canonical orchestrator issue tags (`repairs_damp_mould`, `repairs_disrepair`, `complaint_handling_failure`) alongside natural tags. Also change D5 fallback to fall through when factor retrieval returns zero comparators/insufficient results, not only when prerequisites are missing. Cost: **1-2 days**. Expected lift: moderate for stability and amount coverage; uncertain for winner accuracy until the graph gate can pass.

### H5 - Hybrid emits fewer amounts than RAG-only

**Verdict: supported as a retrieval/prompt-context effect, not an amount parser bug.**

No hybrid-specific nulling was found after model output. `predicted_amount` is parsed in `issue_predictor.py` and then passed through by `output_assembler.py`. The May 10 full backfill amount coverage remains asymmetric:

```text
hybrid: 27/48
rag_only: 43/48
```

The in-flight `STREAM_C_NO_RAG_PREDICT_AMOUNTS=1` run was stopped after repeated stuck retry processes. Partial coverage after kill:

```text
hybrid: 29/48
rag_only: 43/47
kg_only: 38/42
llm_only: 30/36
```

So the no-RAG amount flag works for `kg_only`/`llm_only`, but it is orthogonal to hybrid vs RAG-only. Hybrid amount nulls are more likely caused by broader/noisier comparator mixes and the repairs prompt instruction to set amounts null when comparator awards are absent or too dispersed.

Recommendation: keep the no-RAG amount flag as a separate eval option if needed, but do not treat it as the hybrid-lift blocker. First fix retrieval seed tags/fallback. Then re-measure amount coverage. Cost: **0.5 day** after retrieval fix. Expected lift: amount coverage only, not necessarily winner accuracy.

## New Root Causes To Add To The Stream C Record

1. **Chunked sidecar auto-resolution bug.** Previous chunked ablations using `/tmp/stream_c_chunks/chunk_N.jsonl` silently missed the strict-clean factor sidecar. This invalidates the interpretation that "486 assertions were hydrated but graph score stayed 0"; they were on disk, but not in those chunked KGs.
2. **Issue-tag contract mismatch.** FactorRetriever seeds by exact orchestrator issue ID; proposition store issue tags are natural labels. With real factors loaded, factor-constrained retrieval can return zero results and prevent prediction.
3. **Positive-control shape mismatch.** The smoke test's top-level `dated_events`/`issues`/`candidate_outcomes` are not what production `GraphBuilder` emits. The smoke proves the gate can pass for a hand-shaped object, not that production hydration can satisfy those fields.

## Recommendation

Do **not** start Stream D yet. The cheapest next sequence is:

1. Land the eval-tooling patch in this investigation.
2. Add canonical issue tags to the proposition sidecar or normalize issue tags inside the factor retrieval input path, with sign-off because this changes retrieval behavior.
3. Add D5 fallback when factor-constrained retrieval returns zero/insufficient comparator rows.
4. Run one chunked hybrid-vs-rag probe again. If predictions now run with factors hydrated, inspect gate metadata.
5. Only then decide on Stream D. The remaining hard gate failures still require dated events and outcome/remedy candidates, so H1 alone cannot make hybrid win.

Expected measurable hybrid lift from this patch alone: **none yet**. Expected value: it turns a misleading "all six gate criteria fail with factor data" result into a precise prerequisite map: evidence coverage can be fixed cheaply, but issue-tag normalization and event/issue/outcome hydration remain required before a real hybrid-lift test is possible.
