# Stream C — Chronological Timeline

> Single index for navigating the Stream C empirical record. Earliest first; click through to the full report or plan.

## Plans (development direction)

| Date | Plan | Status |
|---|---|---|
| 2026-05-06 | [Stream A foundation models](../superpowers/plans/2026-05-06-stream-a-foundation-codex.md) | Done (PR #35) |
| 2026-05-06 | [Stream B catalog + gold IAA](../superpowers/plans/2026-05-06-stream-b-catalog-and-gold.md) | Done (PR #36) |
| 2026-05-07 | [Stream C prediction-path-swap](../superpowers/plans/2026-05-07-stream-c-prediction-path-swap.md) | Done (PRs 4/5/6 in #37) |
| 2026-05-07 | [Stream C recovery sprint](../superpowers/plans/2026-05-07-stream-c-recovery-sprint.md) (forced-answer + audit-only) | Done (commits `25e625f` → `6264a93`) |
| 2026-05-10 | [Stream C proposition backfill](../superpowers/plans/2026-05-10-stream-c-proposition-backfill.md) | Done (commit `fbe007e`) |
| 2026-05-10 | [Stream C post-backfill decision](../superpowers/plans/2026-05-10-stream-c-post-backfill-decision.md) | **DECIDE NEXT** |

## Empirical reports (results)

| Date | Report | Headline | Spend |
|---|---|---|---|
| 2026-05-06 | [Stream B IAA — v1 (mini-mini annotators)](extractor_f1_reports/housing.repairs_social.v1-2026-05-06-gold-iaa.md) | 1/15 factors gate-countable | ~£1 |
| 2026-05-07 | [Stream B IAA — v2 (frontier annotators)](extractor_f1_reports/housing.repairs_social.v1-2026-05-07-gold-iaa-comparative.md) | **13/15 factors gate-countable** with gpt-5/gpt-5-mini | ~£6 |
| 2026-05-07 | [Original 4-mode ablation](stream-c-ablation-2026-05-07.md) | rag_only 0.833 vs hybrid 0.625 (-21pp deficit, 33% abstention) | ~£8 |
| 2026-05-07 | [PR4=0 diagnostic](stream-c-pr4-off-diagnostic-2026-05-07.md) | Empty-card removed → +4.2pp partial recovery | ~£2 |
| 2026-05-07 | [Recovery ablation](stream-c-recovery-ablation-2026-05-07.md) | All abstention → 0; hybrid 0.917, rag_only 0.896, +1 case lead | ~£8 |
| 2026-05-07 | [Supervisor briefing](stream-c-supervisor-briefing-2026-05-07.md) | Multi-axis read; tempered claims | — |
| 2026-05-09 | [Case-side factor backfill](stream-c-case-backfill-2026-05-09.md) | Hybrid regressed −2 cases (0.917 → 0.875); KG gate stays closed | ~£32 |
| 2026-05-10 | [Full factor + proposition backfill](2026-05-10-stream-c-full-backfill.md) | Hybrid/rag/kg converge at 0.917; KG gate fails on 6 criteria | ~£11 |

## What changed at each step (architecture-level)

```
2026-05-06   Stream A foundation models (FactorAssertion, FactorValue, GraphQualityScore)
             Stream B catalog: 15 factors for housing.repairs_social.v1

2026-05-07   Stream C PRs 4/5/6: factor card renderer, factor-constrained retrieval,
                                  evidence-path validator
             Stream C recovery: forced-answer mode, validator audit-only,
                                empty-card suppression, metadata serialisation

2026-05-09   Case-side factor backfill: GoldCase.factor_assertions sidecar pipeline,
                                         48 cases × 13 factors via gpt-5/gpt-5-mini

2026-05-10   Proposition-side factor backfill: JsonlPropositionStore + tagger CLI,
                                                 510 propositions tagged
             Empirical finding: KG gate requires evidence-chain semantics
                                (EvidenceSpan, Event, IssueClaim, OutcomeCandidate)
                                not just factor + proposition tagging
```

## Empirical journey: hybrid vs rag_only on n=48 strict-clean gold

| Run | hybrid | rag_only | Δ | kg_used_rate | Comment |
|---|---|---|---|---|---|
| Original 2026-05-07 | 0.625 | 0.833 | −21pp | 0% | Abstention pathology dominated |
| PR4=0 diagnostic | 0.667 | (unchanged) | −17pp | 0% | Empty card a partial cause |
| Recovery 2026-05-07 | 0.917 | 0.896 | +2pp | 0% | Forced-answer eliminates abstention |
| Case-backfill 2026-05-09 | 0.875 | 0.896 | −2pp | 0% | Factor card content didn't help |
| **Full backfill 2026-05-10** | **0.917** | **0.917** | **0pp** | 0% | Convergence; gate still closed |

CIs overlap fully across all runs. Smallest measurable accuracy delta on n=48 = 1/48 = 2.08pp. The hybrid–rag_only delta has been +1/-1/0 cases — pure stochastic LLM variance.

## What's next

Decision required (see [post-backfill plan](../superpowers/plans/2026-05-10-stream-c-post-backfill-decision.md)):
- **Branch A** — write up as architectural-prerequisites study (~6h, £0).
- **Branch B** — build Stream D evidence-chain extractors (~5-10 days, £50-80).
- **Branch C** — Oracle-5 hand-curated study (~14-20h, £1) — recommended first step.

## Code commits in PR #37

```
fbe007e  feat(eval): proposition-side factor backfill tooling (Stream C)
60313a3  docs(eval): case-side factor backfill ablation (2026-05-09)
92a81e9  feat(eval): case-side factor-assertion backfill tooling (Stream C)
aa6c05f  docs(eval): update supervisor briefing with re-run + tempered claims (recovery T8)
b092f25  docs(eval): refresh Stream C recovery ablation with re-run + tempered claims
840508d  docs(eval): Stream C recovery ablation — hybrid wins at 93.8% (superseded by b092f25)
3ee4d49  test(llm_orchestrator): address review feedback on positive-control smoke (recovery T7)
b01de8f  test(llm_orchestrator): positive-control KG smoke tests (recovery T7 tests)
e8f32fb  test(llm_orchestrator): positive-control KG fixture smoke tests (recovery T7 code)
d871932  docs(eval): PR4=0 empty-card diagnostic note + artifacts
6264a93  test(llm_orchestrator): pin pipeline_metadata serialisation (recovery T5)
c8b839e  feat(issue_predictor): forced-answer mode (recovery T4)
34ccf1e  feat(output_assembler): validator audit-only + confidence cap (recovery T3)
9352517  data(positive_control): one-case housing_repairs_social_v1 KG fixture (recovery T7 data)
25e625f  feat(issue_predictor): suppress empty factor card sections (recovery T2)
b612591  docs(plans): Stream C recovery sprint plan
a2f2082  docs(eval): supervisor briefing on Stream C architecture + ablation result
94b4224  docs(eval): Stream C 4-mode ablation report (post-merge 2026-05-07)
6917d32  fix(eval): persist pipeline_metadata into prediction artifacts
4f3660d  feat(eval/metrics): gate-pass-rate + two-slice reporter + counterfactual harness
a4fa2a2  feat(llm_orchestrator): EvidencePathValidator + assembler wiring (Contract C4)
f38d4e1  feat(llm_orchestrator, eval): comparator abstention warning + retrieval-quality metrics
36096ad  feat(llm_orchestrator): wire RetrievalStrategy.FACTOR_CONSTRAINED
c631abc  feat(llm_orchestrator): add FactorRetriever core (Contract C3 + spec §9)
e02fec3  feat(kg_builder/propositions): extend Proposition for factor retrieval
820f996  feat(llm_orchestrator): bucketed similarity helpers (Task 5.2)
9f7253d  feat(llm_orchestrator): add ComparatorPack + supporting models (Contract C2)
3e6e40b  test(llm_orchestrator): PR 4 integration smoke test
57e5976  test(llm_orchestrator): snapshot tests for both pack renderer outputs
58c6500  fix(prediction_engine_v2): tighten domain-pack lookup + wire PR5/PR6 schema tests
75948b8  test(llm_orchestrator): pin prediction artifact schema (Contract C5)
d94cf2e  docs(llm_orchestrator): deprecate kg_facts.py rendering helper
5f00afa  fix(prediction_engine_v2): reset _last_kg_metadata between predict() calls
```

## Naming convention going forward

Files dated 2026-05-10 onward use **`YYYY-MM-DD-`** prefix for native chronological sort. Earlier files keep their existing names (preserves git history); this index links them in chronological order.
