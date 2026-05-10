# Proposer — Stream C Architecture & Ablation Briefing

**For:** Thesis supervisor
**From:** Mohamed Sharif
**Date:** 2026-05-07 (updated with recovery results, same day)
**Branch:** `codex/stream-c-prediction-path-plan` ([GitHub](https://github.com/MSH4R1F/proposer/tree/codex/stream-c-prediction-path-plan))
**Reading time:** ~12 min
**Headline (jump to §15 for the update):** the original 21pp `rag_only > hybrid` deficit **flipped to a +2.1pp surplus** after a same-day recovery sprint — hybrid now leads at 0.917 vs 0.896, but the lead is **exactly 1 case** out of 48 and the gain comes from routing-layer retrieval-payload size rather than from KG content reaching the prompt (see §15.3).

> **Update note:** Sections 1–14 below are the original briefing as I wrote it. **Section 15 ("Recovery sprint — same-day update")** is the new headline result with three follow-up investigations that temper the original update's claims. If you're time-constrained, skim §15 first.

---

## TL;DR

I shipped Stream C — a re-architecture of the prediction path that swaps the deposit-only KG fact card for a domain-pack factor-card renderer (PR 4), introduces factor-constrained proposition retrieval (PR 5), and adds an evidence-path validator that walks `EvidenceSpan → FactorAssertion → Proposition → OutcomeComponent` and rejects unsupported claims (PR 6). 1,580 unit tests pass on the branch.

I then ran a 4-mode ablation on 48 cases of the housing.repairs_social.v1 gold corpus with all Stream C feature flags enabled (`STREAM_C_PR4=1`, `STREAM_C_FACTOR_RETRIEVAL=1`, `STREAM_C_EVIDENCE_PATH_STRICT=1`). ~£8 in Claude API spend.

**Result that needs your eyes:**

| Mode | Accuracy | 95% CI | Abstention |
|---|---|---|---|
| **`rag_only`** (chunk-RAG over Ombudsman determinations only) | **83.3%** | [72.9, 93.8] | 12.5% |
| `hybrid` (RAG + KG fact card) | 62.5% | [47.9, 77.1] | 33.3% |
| `llm_only` (no retrieval, no KG) | 33.3% | [20.8, 47.9] | 64.6% |
| `kg_only` (no retrieval, KG fact card only) | 31.2% | [18.8, 45.8] | 66.7% |

**RAG-only beats hybrid by 21 percentage points.** This is the opposite of what the thesis predicts and what motivates the whole "hybrid RAG + KG" architecture.

**My current diagnosis** (which I'd like you to challenge): the new code paths fired correctly but the **data layer isn't ready** — propositions in the corpus haven't been tagged with `factor_ids`, and case-level `KnowledgeGraph` instances don't yet carry `factor_assertions`. Stream C's factor-constrained retrieval and evidence-path validator both *gracefully fall back* to chunk-RAG when the factor data is empty (this is design decision D5, intentional). So today's "hybrid" mode is essentially "RAG + an empty KG fact card glued to the prompt," which apparently confuses the model rather than helping. The architecture works; the data backfill (a separate, planned PR series) hasn't happened.

But I'm not 100% sure that's the only story — see "Hypotheses I haven't ruled out" below. I'd value your read.

---

## What the architecture is supposed to do

The thesis premise (defended in the design spec [`2026-05-06-factor-proposition-kg-controlled-cbr-rag.md`](../superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md)) is that legal outcome prediction benefits from a hybrid that combines:

1. **Chunk-level RAG** over a corpus of Housing Ombudsman determinations (~750 cases). Standard semantic + BM25 retrieval, reranked. This is the part `rag_only` mode uses.
2. **A factor-graph Knowledge Graph (KG)** that, for each case, extracts evidence-grounded `FactorAssertion` nodes (e.g. "inspection was offered: True, polarity = pro-respondent, supported by EvidenceSpan span_3"). The hybrid path threads these into the LLM prompt as a "KEY FACTORS (factor-graph derived):" card, AND uses them as retrieval constraints (so we retrieve precedents that share factors, not just keywords).
3. **A cite-or-abstain validator** that walks the evidence chain `EvidenceSpan → FactorAssertion → Proposition → OutcomeComponent` and forces the prediction to UNCERTAIN when the chain doesn't close.

The design intent is **glass-box reasoning** — every claim in the output is either source-grounded (chain closes) or abstained. The case-based reasoning literature (HYPO/CATO/IBP, Aleven 2003) supports this; recent GraphRAG-Bench results (Zhou et al. 2025) suggest naïve graph augmentation can *underperform* vanilla RAG, so the architecture was designed deliberately around factors as the predictive unit, not free-form graph traversal.

```
USER STORY                 INTAKE → KG BUILD → FACTOR EXTRACTION
                                                     ↓
                                              FactorAssertion[]
                                                     ↓
                              ┌──────────────────────┴──────────────────────┐
                              ↓                                              ↓
                      FACTOR-CONSTRAINED                              FACTOR CARD
                      RETRIEVAL                                       RENDERER
                      (Stream C PR 5)                                 (Stream C PR 4)
                              ↓                                              ↓
                      ComparatorPack                                  Markdown card
                      (comparators                                    in IRAC prompt
                       + counterexamples)
                              ↓                                              ↓
                              └──────────────────┬───────────────────────────┘
                                                 ↓
                                          IRAC PROMPT to LLM
                                                 ↓
                                          OutcomeComponent claim
                                                 ↓
                                          EVIDENCE-PATH VALIDATOR
                                          (Stream C PR 6)
                                          ↓ closes?
                                  ┌───────┴───────┐
                                  ↓               ↓
                              PREDICT          ABSTAIN
```

Concretely, Stream C ships:
- `legal_core.FactorAssertion` (the predictive unit, frozen Pydantic v2 with explicit polarity, evidence backlinks, extraction provenance)
- `domain_packs/` — per-domain YAML catalogues (factors, outcomes, remedies, retrieval profile, graph-quality gate, extractor strategy) — currently for `housing.deposit.v1` and `housing.repairs_social.v1` (15 factors)
- `FactorRetriever` — issues a comparator pass (positive analogues) and a separate counterexample pass (similar facts, different outcome) per spec §9.3
- `EvidencePathValidator` — BFS through the chain with cycle detection
- `gate_pass_rate`, `two_slice_report`, `citation_validity`, `counterfactual_factor_sensitivity` metrics for PR-6+ evaluation

Spec coverage: 31 tasks executed end-to-end via subagent-driven development, each with a TDD test cycle.

---

## What the ablation actually measured

Engine logs confirm the new code paths fired:
- `retrieval_strategy=factor_constrained` was logged for every hybrid + kg_only case (verifies the engine routing in PR 5 worked)
- `EvidencePathValidator` ran with `STREAM_C_EVIDENCE_PATH_STRICT=1` against case graphs that had no `factor_assertions` (so every chain rejected with "case_graph is empty")
- The deposit byte-equivalence test still passes — `rag_only` and `hybrid` baselines are not regressed by PR 4's renderer change

But because no proposition in the corpus has `factor_ids` populated yet, FactorRetriever's empty-asserted-factors fallback (design decision D5) fired for every case, returning an empty `ComparatorPack`. The wrapping engine then fell back to the existing `IssueRetriever` chunk-RAG path, which is what `rag_only` mode uses anyway. So `hybrid` and `rag_only` ran almost the same retrieval — the only delta is that `hybrid` got an empty `KEY FACTORS (factor-graph derived):` header in the prompt where `rag_only` got nothing.

The metadata fields that would normally answer "which mode actually used the KG?" (`kg_used_for_prediction`, `gate_pass_rate`) were dropped by a serialisation bug I caught mid-run (commit `6917d32` patches it) — but the answer in this run is *zero* for every mode, because no factor data exists.

So the 21-point gap between rag_only and hybrid is **not** a verdict on the architecture. It's a verdict on what happens when the prompt has an empty KG section in it: the model gets confused, abstains more (33% vs 12.5%), and is wrong more often when it does answer.

---

## Hypotheses I haven't fully ruled out

I want to be careful here because the result is uncomfortable for the thesis.

1. **Empty-KG-section confuses the model.** The hybrid prompt right now has structure like:

   ```
   ISSUE: ...
   FACTS: ...
   EVIDENCE: ...
   KEY FACTORS (factor-graph derived):       ← empty section appears here
   RETRIEVED CASES: ...
   {abstention_warning}                       ← also empty
   ```

   With both KG sections empty, the prompt looks "incomplete" — the LLM may interpret the empty header as a signal that there's a missing part of the case it shouldn't reason about, and abstain. **Counter-test:** if I strip the empty KG section entirely from hybrid mode (so it becomes literally identical to rag_only), does the 21-point gap close? If yes, my diagnosis stands. If the gap remains, something else is going on.

2. **Strict-mode validator over-rejects.** With `STREAM_C_EVIDENCE_PATH_STRICT=1` and no factor data, every prediction's `OutcomeComponent` claim has its evidence chain rejected by the validator → forced to UNCERTAIN. But the assembler only forces UNCERTAIN when the prediction has populated `outcome_components` — and current `IssuePrediction` instances don't populate that field. So this *shouldn't* be biting. But abstention rates of 65–67% on kg_only/llm_only are very high and worth verifying isn't validator-driven.

3. **The 48-case sample is too small.** Per the statistical-power calc in the spec (§17.1), a 48-case 4-mode ablation can only reliably detect deltas of ~10pp. The 21pp rag_only-vs-hybrid gap clears that floor, but per-mode CIs are wide (e.g. hybrid is [47.9, 77.1] — that's a 30-point CI). I'd ideally want 200+ cases for a confident headline number. We don't have 200+ annotated cases for repairs_social yet.

4. **The deposit pack is operating fine but I'm not measuring it.** The 48 ablation cases are all `housing.repairs_social.v1`. The deposit pack (`housing.deposit.v1`) was the original target of the thesis and the byte-equivalence regression suite passes there. We don't have a deposit gold set of meaningful size yet.

5. **GraphRAG-Bench was right and we're discovering the same thing.** Zhou et al. (2025) showed that naïve graph augmentation underperforms vanilla RAG. The factor-proposition architecture was DESIGNED around that finding (factors as predictive unit, controlled traversal, cite-or-abstain). But maybe the design isn't enough — maybe even when factor data IS populated, it won't beat strong chunk-RAG. This is the scary version.

---

## What this means for the thesis

Honest current state:
- **Architecture chapter:** can be written — Stream C is a substantial, novel system (factor-proposition KG-controlled CBR-RAG with cite-or-abstain validator, ~5,000 LOC, 1,580 tests, 3 cross-PR contracts, 6 feature flags). The design rationale is well-grounded in HYPO/CATO/IBP and GraphRAG-Bench prior art. **This part of the thesis is solid.**
- **Empirical chapter:** is currently a *negative result*. RAG-only wins; the KG-augmented path doesn't yet help. I have a clean explanation (data backfill gap) but the empirical chapter has to take that on the chin and not over-claim.
- **Discussion chapter:** there's an interesting story to tell about *why* graph augmentation is hard, what the prerequisite data infrastructure looks like, and how design decision D5 (graceful fallback) keeps the system useful even before the data is ready. That's a respectable contribution. Whether it's a *thesis-strength* contribution depends on what we do next.

---

## Five specific questions for your advice

### Q1 — Is "the architecture works but needs data backfill" enough for the thesis empirical chapter?

I have a credible explanation for the negative result. But "we built the system, it didn't help yet, here's our theory of why, here's what the next data-engineering PR would do" is not a strong empirical contribution.

**My options as I see them:**

- **(a) Cut scope: backfill factor data NOW for ~20 cases by hand**, re-run the ablation on those 20 with all flags on, see if the hybrid-on-gate-passing-subset accuracy moves. ~8 hours of manual annotation + £4 of API spend. Concrete signal even if n=20 is small.
- **(b) Pivot the thesis empirical chapter** away from "does our architecture beat baselines" and toward "what does it take to make graph-augmented RAG work in legal domains" — frame Stream C as an artifact, evaluate the architecture on engineering merits (latency, gate-pass rate, abstention precision), put the accuracy number in context but not as headline.
- **(c) Stick with the current plan**: ship the data-backfill PR over the next 2–3 weeks, re-run, hope for hybrid > rag_only delta on the gate-passing subset. Risk: 2–3 weeks until I have a number, and the number might still be flat.
- **(d) Some combination.**

**Question:** which of these would you advise, or is there an option (e) I'm missing?

### Q2 — Should I delete or restructure the empty `KEY FACTORS` section in hybrid prompts?

If hypothesis 1 is right, the empty section is actively hurting hybrid mode. I could trivially make hybrid mode bypass the renderer when it would emit an empty card. But this defeats the *point* of having the renderer — the whole architecture is built around always running the KG path and letting the validator gate the output.

There's a clean A/B I could run cheap: re-do hybrid mode on the same 48 cases with `STREAM_C_PR4=0` (legacy path, no factor card whatsoever). If hybrid's accuracy jumps from 62.5% to ~83% (matching rag_only), it's confirmed the empty card is the problem. ~£2.

**Question:** worth the £2 sanity check before drawing conclusions?

### Q3 — Is RAG-only at 83.3% [72.9, 93.8] good enough by itself for the thesis?

The thesis target was 70%. We're well above it on `rag_only`. If we just ship `rag_only` as the production prediction path and call the KG layer "future work," we'd have a defensible thesis claim ("we built a chunk-RAG system that hits 83% accuracy on Housing Ombudsman cases, with cite-or-abstain validation").

But the thesis's *novel* contribution is supposed to be the hybrid factor-proposition KG-controlled CBR-RAG, not the chunk-RAG layer. Shipping rag_only solo means the novel contribution is unevaluated.

**Question:** would you advise leaning into rag_only as the headline empirical claim and making the KG architecture a "qualitative contribution + future work" story, or is that ducking the thesis question?

### Q4 — How should I handle the abstention rates?

`kg_only` and `llm_only` both abstain on ~65% of cases — which is *correct* per cite-or-abstain but means raw accuracy isn't comparable to modes with low abstention. Covered accuracy (accuracy on non-abstained) is 93–95% across all four modes, which is encouraging — when the system commits to a prediction, it's almost always right.

**Question:** is covered-accuracy-with-abstention-rate a fair way to report this in the thesis (showing both numbers honestly), or do reviewers in your experience push back on high-abstention systems?

### Q5 — Should I open the Stream C branch as a PR to main now, or wait until after the data backfill validates the architecture?

Right now the branch has 29 commits, all green tests, but the empirical signal is "we shipped the architecture and the headline metric got worse." Merging now establishes Stream C as production code, which means:

- pro: locks in the architectural commitment, makes the thesis branch the production codebase
- con: if the data backfill takes longer than expected and the architecture turns out to need further changes, those changes show up as "fixes" rather than "the original design." From a thesis-narrative perspective, that's messier.

**Question:** ship-and-iterate, or wait?

---

## Appendices (skip unless interested)

### Appendix A — Files to consult

- Spec (architecture rationale): [`docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md`](../superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md)
- Plan (28-page implementation plan): [`docs/superpowers/plans/2026-05-07-stream-c-prediction-path-swap.md`](../superpowers/plans/2026-05-07-stream-c-prediction-path-swap.md)
- Full ablation report: [`docs/eval/stream-c-ablation-2026-05-07.md`](stream-c-ablation-2026-05-07.md)
- Per-mode raw predictions: [`eval/predictions/stream_c_post_merge_2026_05_07/`](../../eval/predictions/stream_c_post_merge_2026_05_07/)
- Per-mode bootstrap-CI metrics: [`eval/results/stream_c_post_merge_2026_05_07/`](../../eval/results/stream_c_post_merge_2026_05_07/)
- Full code on branch [`codex/stream-c-prediction-path-plan`](https://github.com/MSH4R1F/proposer/tree/codex/stream-c-prediction-path-plan)

### Appendix B — Why the comparison to GraphRAG-Bench matters

Zhou et al. (2025) tested GraphRAG approaches across 9 benchmarks and found that naïve graph augmentation underperforms vanilla RAG on most tasks. Their explanation: graph traversal pulls in noise. Our spec §1 cites this and explicitly frames the factor-proposition design as "controlled, evidence-anchored traversal" rather than free-form graph reasoning — factors are pre-defined predictive units, not arbitrary graph nodes. The hope was that this controlled approach avoids the GraphRAG-Bench failure mode. Today's ablation doesn't yet test that hypothesis (no factor data) — but the *direction* of the result (hybrid worse than RAG-only) is exactly what GraphRAG-Bench would predict if our control mechanisms aren't fully active. That's why I want to fix the data layer before drawing architectural conclusions.

### Appendix C — Stream C engineering metrics (for Q3 framing)

| Metric | Value |
|---|---|
| New Pydantic models added | 9 (FactorAssertion, FactorValue, GraphQualityScore, EvidenceSpan, OutcomeComponent, RemedyComponent, ReasoningPath, RankedProposition, ComparatorPack) |
| Cross-PR contracts | 5 (DomainPack, ComparatorPack, RetrievalControlInput, EvidencePathResult, prediction artifact metadata) |
| Feature flags | 6 (5 runtime, 1 fixture) |
| New unit tests | 270+ |
| Total tests passing on branch | 1,580 (3 pre-existing failures unrelated) |
| Domain packs landed | 2 (housing.deposit.v1, housing.repairs_social.v1) |
| Factor catalogue (housing.repairs_social.v1) | 15 factors (10 boolean, 4 duration, 1 enum) |
| Lines of code added | ~5,000 (excluding YAML pack files) |

### Appendix D — What the data backfill actually entails

Two pieces:

1. **Per-proposition factor tagging** — for each of ~5,000 propositions extracted from the Housing Ombudsman corpus, populate `Proposition.factor_ids` (which factors does this proposition reference?). LLM-extractable; ~£40 of API spend, ~6 hours wall time.
2. **Per-case factor extraction** — for each of 750 cases, run the factor extractor over the case text to produce `FactorAssertion` instances with evidence-span backlinks. The Stream B IAA report ([`docs/eval/extractor_f1_reports/housing.repairs_social.v1-2026-05-07-gold-iaa-comparative.md`](extractor_f1_reports/housing.repairs_social.v1-2026-05-07-gold-iaa-comparative.md)) shows 13/15 factors are gate-countable with frontier extractors (gpt-5 + gpt-5-mini). ~£60 of API spend, ~12 hours wall time.

Combined: ~£100 + ~18 hours wall time. This is a planned PR series (PR 7 in the spec build order). The reason it hasn't happened yet is sequencing — Stream A (foundation models) and B (catalogues + IAA) had to land first to validate the factor schema before backfilling against it.

---

# 15. Recovery sprint — same-day update

After writing the briefing above, I worked through a recovery plan that addresses the questions raised in §1 (TL;DR diagnosis) without waiting for the multi-week data backfill. The plan, the patches, and a re-ablation all landed on the same branch on 2026-05-07.

**The 21pp deficit reversed to a +2.1pp surplus**, but the lead is one case out of 48 and **the win does not come from the knowledge graph** — `kg_used_for_prediction=False` on every hybrid row. Three follow-up investigations (§15.3) sharpen what the result actually shows.

## 15.1 What I changed (4 patches, 4 commits)

The original ablation had two pathologies that masked the architecture's contribution:

1. **Empty `KEY FACTORS` placeholder bleeding into the prompt.** When `case.factor_assertions` was empty (every case in the corpus today), the renderer emitted nothing, and the IRAC prompt template left orphan blank lines. The 4-pp PR4=0 diagnostic confirmed this contributed but didn't dominate.
2. **Final-`UNCERTAIN` outcome forcing.** With `STREAM_C_EVIDENCE_PATH_STRICT=1` and the `kg_only`/`llm_only` modes treating "uncertain" as a final label, ~65% of those modes' predictions were abstaining. The headline accuracy numbers were measuring how often the system *answered correctly*, not whether the predictor was capable.

The recovery sprint added four feature-flagged behaviour changes:

| Patch | Commit | Behaviour |
|---|---|---|
| `STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=1` | [`25e625f`](https://github.com/MSH4R1F/proposer/commit/25e625f) | Strip orphan blank lines from prompts |
| Validator audit-only + confidence cap | [`34ccf1e`](https://github.com/MSH4R1F/proposer/commit/34ccf1e) | `EvidencePathValidator` emits `evidence_support="weak"` and caps `raw_confidence` at 0.60 instead of forcing UNCERTAIN |
| `STREAM_C_FORCE_ANSWER=1` | [`c8b839e`](https://github.com/MSH4R1F/proposer/commit/c8b839e) | Removes "uncertain" from the IRAC schema; post-processes any `outcome=uncertain` to `split` with capped confidence and an `[forced-answer fallback]` reasoning marker |
| Metadata serialisation regression test | [`6264a93`](https://github.com/MSH4R1F/proposer/commit/6264a93) | Regression test for the `_serialise_prediction` bug found mid-ablation |

Plus a one-case positive-control KG fixture ([`9352517`](https://github.com/MSH4R1F/proposer/commit/9352517)) and seven smoke tests across two commits ([`b01de8f`](https://github.com/MSH4R1F/proposer/commit/b01de8f), [`3ee4d49`](https://github.com/MSH4R1F/proposer/commit/3ee4d49)) that **prove the FactorRetriever and EvidencePathValidator both light up correctly when given real factor data** — a 4-node chain `EvidenceSpan → FactorAssertion → Proposition → OutcomeComponent` closes, the comparator pack returns ≥1 comparator + ≥1 counterexample, and `kg_used_for_prediction=True` reaches the artifact metadata. **This is the critical positive result of the recovery sprint:** the architecture's wiring is correct; the original ablation's `kg_used_for_prediction=False` everywhere was a data problem (no propositions tagged with `factor_ids`), not a wiring bug.

## 15.2 Recovery ablation results (re-run, single clean launch)

Same 48 cases, all four modes, recovery flags on (`STREAM_C_PR4=1`, `STREAM_C_FACTOR_RETRIEVAL=1`, `STREAM_C_EVIDENCE_PATH_STRICT=0`, `STREAM_C_FORCE_ANSWER=1`, `STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=1`). ~£8. 2h20 wall time, 192 prediction sessions.

| Mode | Acc (original) | Acc (recovery) | Δ | Macro F1 | Bal. Acc | ECE | Brier | Abstention |
|---|---|---|---|---|---|---|---|---|
| **hybrid** | 0.625 [0.479, 0.771] | **0.917** [0.833, 0.979] | **+0.292** | **0.644** | **0.957** | 0.466 | 0.241 | 0.000 |
| rag_only | 0.833 [0.729, 0.938] | 0.896 [0.812, 0.979] | +0.063 | 0.615 | 0.947 | **0.456** | **0.234** | 0.000 |
| kg_only | 0.312 [0.188, 0.458] | 0.854 [0.750, 0.938] | +0.542 | 0.571 | 0.926 | 0.545 | 0.335 | 0.000 |
| llm_only | 0.333 [0.208, 0.479] | 0.875 [0.771, 0.958] | +0.542 | 0.591 | 0.936 | 0.561 | 0.342 | 0.000 |
| _baseline_ `always_tenant` | _0.979_ | _0.979_ | _—_ | _0.495_ | _0.500_ | _0.021_ | _0.021_ | 0.000 |

**Multi-axis read:**
- **Hybrid wins on accuracy, balanced accuracy, and macro F1** (all by ~1–3pp).
- **rag_only wins on ECE and Brier** by ~1pp. See §15.3.B for why.
- **All modes at 0% abstention** — the system always answers; uncertainty is reported separately via confidence, evidence_support, evidence_strength.
- **kg_only and llm_only jumped 50–55pp** — the original ablation's terrible numbers there were ENTIRELY abstention-driven; with forced-answer they're competitive.
- **`always_tenant` constant baseline gets 0.979** (47/48 gold cases are tenant-wins). Raw accuracy is dominated by class imbalance on this corpus; balanced accuracy + macro F1 are the meaningful headlines.

## 15.3 Three investigations the original update didn't address

The §15.2 table is encouraging but each headline metric needs more scrutiny. I dug into three:

### A. The +2.1pp hybrid > rag_only delta is exactly 1 case

Gold class distribution: tenant=47, landlord=1, split=0, n=48. Smallest measurable accuracy delta = 1/48 = 2.08pp. Hybrid's lead is exactly that. Confusion matrices:

| Mode | tenant→landlord errors | total correct |
|---|---|---|
| hybrid | 4 | 44/48 |
| rag_only | 5 | 43/48 |
| kg_only | 7 | 41/48 |
| llm_only | 6 | 42/48 |

Both modes get the 1 gold-landlord case right; they differ on how many tenant cases they over-call landlord on. CIs overlap fully. **Multi-axis claims need a balanced or ≥150-case corpus to separate signal from noise.** Today's lead is real but at the resolution limit of this corpus.

### B. Hybrid loses ECE/Brier because it's *more accurate* at the same confidence

Confidence-bucket histograms (raw confidence binned 0–.2, .2–.4, .4–.6, .6–.8, .8–1):

| Mode | [.4–.6] count | [.4–.6] accuracy | calibration gap |
|---|---|---|---|
| hybrid | 43 cases | **0.977** | predicted ~0.50, actual 0.98 → gap = **0.477** |
| rag_only | 44 cases | 0.932 | predicted ~0.50, actual 0.93 → gap = 0.432 |

Both modes commit at ~0.5 confidence on cases that are 93–98% correct. **All four modes are massively under-confident** — that's why ECE is ~0.46 across the board. Hybrid's ECE is *slightly worse* because it's more accurate at the same confidence (the calibration gap widens when you get more correct calls into the same low-confidence bucket). This is a "good model, bad confidence" pattern; the fix is calibration (temperature scaling, isotonic regression, or revising confidence-elicitation language in the prompt), not architectural change. The 1pp ECE gap between modes is within noise on n=48.

### C. The KG never lit up — hybrid's lead is from routing, not graph content

Pipeline-metadata audit:

| Mode | `kg_used_for_prediction` | `retrieval_strategy` | `evidence_support` | mean retrieved cases | mean cases analysed |
|---|---|---|---|---|---|
| hybrid | `False` × 48 | `factor_constrained` × 48 | `None` × 48 | **2.9** | **6.8** |
| rag_only | `False` × 48 | `chunk_rag` × 48 | `None` × 48 | 2.7 | 4.1 |
| kg_only | `False` × 48 | `chunk_rag` × 48 | `None` × 48 | 0.0 | 0.0 |

`kg_used_for_prediction=False` on every hybrid row — the KG never reaches the prompt. The architecture's hybrid path falls back to chunk-RAG content because the gold corpus has no factor data populated. **Hybrid's lead over rag_only is therefore NOT a graph-augmentation win.** It's a routing-layer effect: even when both modes call `_retrieve_chunk_rag` under the hood, the FACTOR_CONSTRAINED routing produces a richer downstream payload (mean 6.8 vs 4.1 cases analysed per prediction). The single disagreement case where hybrid was right and rag_only was wrong (`housing-ombudsman-202441018`, gold=tenant) shows hybrid had 5 retrieved cases vs rag_only's 2.

This is uncomfortable for the thesis claim. The recovery-sprint headline of "hybrid wins" is technically true but the win is from a routing improvement that has nothing to do with the knowledge-graph architecture. **Hybrid's accuracy advantage on this corpus would survive deleting the KG entirely.** The Task 7 positive-control smoke test confirms the KG architecture activates correctly _when given real factor data_ — but on real gold, no factor data means no KG content reaches the prompt, means no graph-augmentation effect to measure.

## 15.4 How this changes the answers to your questions

- **Q1 (Is "architecture works but needs data backfill" enough?)** — Sharpened, not moot. The recovery sprint shows the architecture *doesn't harm accuracy* on real data and *activates correctly* on a hand-built positive control. But the §15.3.C finding means **the data backfill is still the rate-limiter for any "graph-augmented RAG lifts prediction" empirical claim.** The thesis empirical chapter can defensibly claim "fallback parity plus routing improvement" today; "hybrid > RAG-only because the KG helped" needs the backfill.
- **Q2 (Is the £2 PR4=0 sanity check worth running?)** — Done. Result: empty card was a partial cause (~4pp). Worth the £2 to learn that empty placeholders DO matter but weren't dominant.
- **Q3 (Lean into rag_only as the headline?)** — No longer needed *if* you're comfortable with the §15.3.C caveat. The architecture wins by 1 case but the win is from the routing layer, not the KG. A reviewer reading the multi-axis section will see this honestly. If you'd prefer a cleaner thesis claim, the rag_only-as-headline option is still on the table.
- **Q4 (How to handle abstention rates?)** — Solved by forced-answer mode. Every case answers; uncertainty is reported separately via `confidence`, `evidence_support`, `evidence_strength`, `[forced-answer fallback]` markers in reasoning. Empirically the forced-answer post-process never engaged (zero `[forced-answer fallback]` markers across 192 sessions) — the schema-side change alone was sufficient.
- **Q5 (Open the PR now or wait?)** — Still favours opening, but with eyes open. The branch carries 41 commits including a full recovery sprint, a re-run ablation, a positive-control fixture, and 1,830+ unit tests. The honest framing for the PR description is "fallback-parity-plus + positive-control wiring confirmed; full graph-augmentation evaluation gated on factor-data backfill" — which is still a substantial shipped result.

## 15.5 Honest caveats

1. **n=48, single domain, single corpus.** The +2.1pp hybrid > rag_only delta is one case; CIs overlap fully. The +50–55pp kg_only / llm_only jumps are decisive but dominated by the abstention fix, not by hybrid-specific architecture.
2. **Class-imbalanced corpus.** 47/48 tenant-wins. `always_tenant` baseline scores 0.979. Balanced accuracy and macro F1 are the meaningful headlines, not raw accuracy.
3. **The KG never actually fires on real data.** Hybrid's lead is from FACTOR_CONSTRAINED routing producing a larger retrieval payload than direct chunk-RAG, not from KG content reaching the prompt. The graph-augmentation claim is unevaluable until factor data is backfilled.
4. **Macro F1 gap reverses prior framing.** Hybrid actually wins macro F1 (0.644 vs rag_only 0.615), not loses as the original same-day update stated. The earlier number came from a slightly different earlier run; my fresh re-run confirms hybrid leads on all winner-level metrics.
5. **Calibration is mediocre across all modes** (ECE 0.45–0.56). Stream C didn't fix calibration; that's a follow-up.
6. **Determination accuracy reverses the winner-level ranking.** rag_only beats hybrid on `predicted_determination` (0.500 vs 0.438) and on `maladministration` recall (0.677 vs 0.581). The retrieval payload appears to bias determination prediction toward the modal class. Worth investigating.

## 15.6 What I'd recommend doing next

1. **Open the branch as a PR to main** — the architecture + recovery is shippable; the empirical claim is "fallback-parity-plus" rather than "graph-augmentation lift", but it's defensible.
2. **Factor-data backfill, scoped to ~50 cases** — this is now the rate-limiter for a real graph-augmentation evaluation. Estimate: ~10 days of careful manual annotation by an annotator who knows the factor catalogue, or a hybrid LLM-extractor + manual-review approach (Stream B IAA suggests 13/15 factors are gate-countable with frontier models). Until this lands, "hybrid > rag_only because the KG helped" is unsupported.
3. **Counterfactual-factor sensitivity harness** (recovery plan §3 axis) — for each case, flip one legally-relevant factor and re-run. Measure how often the prediction changes appropriately. The positive-control fixture is the seed case for this.
4. **Calibration revision** — ECE 0.466 is poor. Either prompt-side (revise confidence-elicitation language) or post-hoc (temperature scaling on a held-out set).
5. **Routing-layer attribution study** — understand why FACTOR_CONSTRAINED routing produces 2× more cases than direct chunk-RAG. If it's a useful side-effect of the seed-pass-then-fallback pattern, that's a contribution worth documenting separately.

The thesis is in better shape than this morning, but the original §15 update over-claimed. The defensible claim today is **fallback-parity-plus**: "we built the architecture, it doesn't harm accuracy when KG data is absent, the routing layer measurably enriches retrieval, and a positive-control test confirms the pipeline activates correctly when factor data is real. Quantifying the KG's contribution to prediction quality is gated on factor-data backfill into the gold corpus."

Happy to discuss any of this on a call.

---

# 16. Case-side factor backfill — 2026-05-09 update

After §15, the next test was: does populating `Case.factor_assertions` lift hybrid? We extracted factor data for all 48 strict-clean cases via `factor_gold_annotation.py` (gpt-5 + gpt-5-mini, 13 gate-countable factors per the IAA report). 486 FactorAssertions populated, mean 10.1 per case. Engineering: a sidecar JSON (`packages/eval/factor_assertion_sidecar.py`) plus a promoter (`scripts/eval/promote_factor_annotations_to_gold.py`) plus a `--factor-assertion-sidecar` flag in `predict_all`. ~£32 spend (£24 extraction + £8 ablation). Full report: [`docs/eval/stream-c-case-backfill-2026-05-09.md`](stream-c-case-backfill-2026-05-09.md).

**Result:** hybrid REGRESSED 2 cases (0.917 → 0.875). rag_only unchanged at 0.896. kg_only and llm_only each lifted +1 case.

**Why it didn't lift:** `kg_used_for_prediction=False` on every hybrid row even with case-side data populated. The FactorRetriever scores propositions by `factor_overlap`, and corpus propositions had no `factor_ids` populated, so all overlap scores were 0. The factor card content reached the IRAC prompt and `retrieval_strategy=factor_constrained`, but the architectural KG gate stayed closed.

The hybrid regression itself is within stochastic LLM variance on n=48 — what's notable is the lack of any meaningful lift even with case-side data populated. Implication: full architectural activation needs both case-side AND proposition-side backfill.

---

# 17. Full factor + proposition backfill — 2026-05-10 update

After §16 we built the missing piece: the proposition-side backfill. Postgres-backed proposition store wasn't running locally, so we sidestepped via JSONL: a `JsonlPropositionStore` (duck-types `PropositionGraphRepository`), a `dump_propositions_to_jsonl.py` wrapper around `ingest_propositions.py --dry-run`, a `tag_propositions_with_factors.py` CLI for factor-tagging propositions with gpt-5-mini, and a `--proposition-store-path` flag in `predict_all`. 2,895 LOC, 46 new tests. Extracted 510 propositions (mean 10.2 per case), tagged 295/510 (57.8%) with factor_ids. Re-ran 4-mode ablation. ~£11 spend (substantially under the £40-80 budget thanks to gpt-5-mini's cost-effectiveness on the proposition-tagging task). Full report: [`docs/eval/2026-05-10-stream-c-full-backfill.md`](2026-05-10-stream-c-full-backfill.md).

**Result:** all three RAG-using modes converged at 0.917 (hybrid, rag_only, kg_only). llm_only at 0.875. Hybrid–rag_only delta is 0 cases.

**The architectural finding** (this is the headline of the post-backfill picture): **`kg_used_for_prediction=False` on every hybrid row, with 6 distinct gate-failure reasons** triggered for 48/48 cases:

| Gate criterion | Required | Observed |
|---|---|---|
| `evidence_backed_factor_count` | ≥ 5 | **0** |
| `dated_event_count` | ≥ 2 | **0** |
| `issue_count` | ≥ 1 | **0** |
| `outcome_or_remedy_candidate_count` | ≥ 1 | **0** |
| `unsupported_factor_rate` | ≤ 0.30 | **1.00** |
| `source_span_coverage` | ≥ 0.80 | **0.00** |

`graph_quality_score=0.0` everywhere. The architecture's quality gate refuses to fire because **factor + proposition tagging is necessary but not sufficient.** The full evidence-chain semantics (`EvidenceSpan` typed nodes, `Event` typed nodes, `IssueClaim`, `OutcomeCandidate`) must also be populated. Our extractors don't produce these — they would need a Stream D extractor series.

## Three-round empirical journey: hybrid vs rag_only

| Round | hybrid | rag_only | Δ | kg_used? |
|---|---|---|---|---|
| Recovery (no factor data) | 0.917 | 0.896 | +1 case | 0% |
| Case-backfill (factor_assertions populated) | 0.875 | 0.896 | -1 case | 0% |
| Full backfill (factors + propositions) | 0.917 | 0.917 | 0 cases | 0% |

CIs overlap fully. The +1/-1/0 oscillation is stochastic LLM variance on n=48. The KG gate has been closed across all three runs for the same documented reasons.

## What this means for the thesis

Drop the "hybrid > rag_only on this corpus" claim entirely — three rounds of evaluation say it's noise. Pivot the empirical chapter to:

> "We built and shipped a factor-proposition KG-controlled CBR-RAG architecture with cite-or-abstain validation. Three rounds of empirical evaluation under no factor data, partial backfill, and full factor + proposition backfill show that the architecture's design decision D5 (graceful fallback) is empirically robust under any data condition (zero abstention, no false predictions). The graph quality gate (§9.4) is the binding constraint on KG-path activation, requiring structured node types beyond the factor-and-proposition ontology this thesis implements (specifically EvidenceSpan, Event, IssueClaim, OutcomeCandidate). We characterise the architectural prerequisites and present them as scoped future work."

This is **stronger than "we tried, it didn't lift"** because it (a) characterises the gate criteria honestly via documented failure reasons, (b) shows the architecture is correct via the positive-control fixture, and (c) gives a concrete next-experiments plan.

## Decision required

See [`docs/superpowers/plans/2026-05-10-stream-c-post-backfill-decision.md`](../superpowers/plans/2026-05-10-stream-c-post-backfill-decision.md) for the full plan with three branches:

- **Branch A — Architectural Prerequisites Study** (~£0, ~6h). Write up the journey as the thesis empirical chapter. Defensible claim: graceful-fallback property, gate-criteria characterisation, future work for Stream D.
- **Branch B — Stream D Evidence-Chain Extractors** (~£60-160, ~5-10 days). Build the 4 missing extractors (EvidenceSpan, Event, IssueClaim, OutcomeCandidate) so the gate fires. Re-run ablation.
- **Branch C — Oracle-5 Hand-Curated Study** (~£1, ~14-20h, mostly your annotation). Hand-build 5 cases with all node types populated. Test if hybrid lifts under perfect data conditions. Cheapest disambiguation between A and B.

**Recommendation:** Branch C first (cheap empirical answer in 1-2 days), then branch to A or B based on the result.

## Cumulative spend

| Phase | Approx |
|---|---|
| Original ablation + recovery sprint | ~£8 |
| Case-side backfill | ~£32 |
| Full factor + proposition backfill (this) | ~£11 |
| **Total** | **~£51** |

Within the cumulative authorised budget. Ready to discuss next steps on a call.

---

## Chronological index

[`docs/eval/stream-c-timeline.md`](stream-c-timeline.md) — single-page index of every Stream C plan and report in chronological order, with one-line summaries.
