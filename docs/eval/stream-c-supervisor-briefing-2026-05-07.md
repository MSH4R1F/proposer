# Proposer — Stream C Architecture & Ablation Briefing

**For:** Thesis supervisor
**From:** Mohamed Sharif
**Date:** 2026-05-07
**Branch:** `codex/stream-c-prediction-path-plan` ([GitHub](https://github.com/MSH4R1F/proposer/tree/codex/stream-c-prediction-path-plan))
**Reading time:** ~10 min
**Asks at the bottom:** 5 specific questions where I'd value your advice.

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
