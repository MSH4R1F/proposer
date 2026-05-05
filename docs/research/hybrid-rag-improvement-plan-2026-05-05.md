# Hybrid RAG + KG Improvement Plan (2026-05-05)

**Status:** Synthesis of four parallel investigations dispatched on 2026-05-05.
**Author:** Coordinator session (Mohamed) over Codex/CC subagent outputs.
**Trigger:** Post-leakage-fix Housing Ombudsman 50-case eval
(`housing_ombudsman_stratified_50_live_20260505_post_patch_topk5_sharded5_full_eval`).

This is a ranked, ticket-ready implementation plan. It is NOT an attempt to
make the headline numbers look better on the current 50-case slice — that
slice is structurally unable to grade the model (see §1).

## Companion deliverables (read in order)

1. **Failure taxonomy** — [`docs/eval/housing-ombudsman-failure-taxonomy-2026-05-05.md`](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md)
   What's actually broken vs. what looks broken in the current run.
2. **Pipeline audit** — [`docs/research/hybrid-rag-current-pipeline-audit-2026-05-05.md`](hybrid-rag-current-pipeline-audit-2026-05-05.md)
   File-and-line evidence for every architectural weakness named below.
3. **Retrieval & architecture research** — [`docs/research/hybrid-rag-improvement-research-retrieval-2026-05-05.md`](hybrid-rag-improvement-research-retrieval-2026-05-05.md)
   Primary-source evidence for retrieval, chunking, hybrid fusion, GraphRAG.
4. **Prompting, calibration, amount research** — [`docs/research/hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md`](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md)
   Primary-source evidence for IRAC prompting, calibration, conformal abstention,
   amount band/regression, imbalanced-eval methodology.
5. **Agentic retrieval plan** — [`docs/research/hybrid-rag-agentic-retrieval-plan-2026-05-05.md`](hybrid-rag-agentic-retrieval-plan-2026-05-05.md)
   Ticket-ready spec for Architecture B (single-shot query decomposition)
   and Architecture C (iterative retrieval agent). Extends Tier 2/3 below
   with `F-AGENT-1..7`; depends on Phase 1 prerequisites here landing
   first.

Original mission brief: [`docs/prompts/hybrid-rag-prompt-pipeline-investigation.md`](../prompts/hybrid-rag-prompt-pipeline-investigation.md).

---

## 1. Core diagnosis (plain English)

The framing in the original brief — "hybrid is bad" — is wrong, and the
deliverables converge on a much sharper diagnosis:

1. **The 0.68 vs 0.70 hybrid-vs-rag gap is statistical noise on n=50.**
   All but one of the 16 hybrid winner-errors are abstentions
   (`split / p=0.5 / abstained=True / amount=£0`). Under
   abstention-adjusted scoring both modes sit at **0.971 vs 0.972**
   — indistinguishable. The single confidently-wrong call
   (`housing-ombudsman-202413845`) is wrong on rag_only too, so it is
   plausibly a gold-label issue, not a model issue. Source:
   [taxonomy §C, §H#1, §H#5](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md).

2. **Hybrid ≈ RAG_ONLY by construction on this domain.** The KG fact card
   `KGFacts` is deposit-only; for repairs cases it is always-empty. So
   "hybrid" adds at most a few free-text constraint bullets (also empty
   for repairs) over rag_only. The audit confirms the typed-fact
   delta is zero (`kg_facts.py:44-133`,
   `issue_predictor.py:960-991`). Source:
   [audit §3 KG facts injection, audit Top-5 #3](hybrid-rag-current-pipeline-audit-2026-05-05.md).

3. **`kg_only` and `llm_only` are universal abstainers, not 0%-accurate
   models.** Every prediction in both modes is
   `split / 0.5 / £0 / uncertain / abstained=True`. They cannot adjudicate
   ablation claims like "RAG > KG > LLM"; they are no-op stubs on the
   leakage-cleaned set. Source:
   [taxonomy §B kg_only/llm_only, §H#3](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md);
   [audit W8](hybrid-rag-current-pipeline-audit-2026-05-05.md).

4. **The amount head is structurally truncated.** Hybrid never predicts
   above £1000 (1 case out of 50 reaches £1000 exactly), but gold has 9
   cases ≥£1000 and a max of £3818. 21/50 predictions are £0; 21/50
   cluster at £251-600; the rest of the distribution is essentially
   absent. Even on the 34 cases where hybrid wins on the winner head,
   only 5 are within ±£100 and 4 within ±20%. The -£466 bias is the
   natural consequence of band-truncation, not a ranking bug. Source:
   [taxonomy §D, §H#2](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md);
   [audit W6, W7](hybrid-rag-current-pipeline-audit-2026-05-05.md).

5. **always_tenant beats every model on every classification metric.**
   acc 0.98 vs 0.68; macro-F1 0.495 vs 0.273; balanced acc 0.500 vs
   0.347; Brier 0.020 vs 0.247. With 49 tenant / 1 landlord / 0 split,
   no model can demonstrate skill on this slice. **Gold expansion is a
   hard prerequisite** for any thesis-facing accuracy or calibration
   claim. Source:
   [taxonomy §G, §H#4](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md).

6. **The retriever, not the LLM, is the dominant failure path in legal
   RAG.** Magesh et al. (JELS 2025) measured 17-33% hallucination on
   premium commercial legal RAG; Rasiah et al. (NLLP 2025) measured
   >95% Document-Level Retrieval Mismatch on LegalBench-RAG. So it is a
   priori unlikely our 0.47 ECE is fixable from logits alone — most
   likely the model is conditioning on the wrong evidence, especially
   for amount. Source:
   [retrieval §2.1](hybrid-rag-improvement-research-retrieval-2026-05-05.md).

7. **The Housing Ombudsman publishes the bands we need.** Annex A of
   their remedies guidance gives £50-100 / £100-600 / £600-1000 /
   £1000+ tied to severity findings. Adopting these bands as the
   prediction target turns a hard heavy-tailed regression into a
   classification + within-band regression problem that mirrors the
   regulator's own scheme. Source:
   [prompting §2.5.5, §3.4](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md).

---

## 2. Top three fixes ranked by likely impact

These are the three highest-leverage interventions. Detailed tickets follow
in §3-§5.

### Fix #1 — **Adopt published Housing Ombudsman bands as the amount target, with two-stage band-classifier → within-band regression** [F-AMT-1, F-AMT-2, F-PROMPT-1]

- **Targets**: Amount@20% (currently 0.10 → target ≥0.30), Amount@£100
  (0.18 → target ≥0.45), MAE (£520 → target <£300), bias (-£466 → target |bias| <£100).
- **Evidence base**: Housing Ombudsman Annex A bands (regulator-published);
  Dal Pont 2023 (PeerJ CS) and arXiv 2511.15374 on staged classify-then-regress
  for damages/sentencing; Romano et al. NeurIPS 2019 (Conformalized Quantile
  Regression) for predictive intervals; Tweedie/zero-inflated insurance work
  for the £0 / heavy-tail structure. Source:
  [prompting §2.5, §3.4](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md).
- **Why it leads the ranking**: every amount metric in the audit is broken
  *because the amount distribution is structurally truncated above £600*
  ([taxonomy §H#2](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md)).
  No retrieval or prompt fix that keeps a single-integer regressor will close
  this; the regressor pulls toward the £251-600 mode. Banding decouples it.
- **Code surface**: ~300 LOC across `prompts/prediction_v2.py:77-105`,
  `issue_predictor.py:858-890` (repairs prompt), a new
  `pipeline/amount_predictor.py` for the within-band regression, plus
  parser updates in `issue_predictor.py:929-938` and the eval adapter
  in `packages/eval/adapter.py:43-68`.

### Fix #2 — **Add a remedy/orders retrieval pass and persist verifier output** [F-RET-1, F-EVAL-2]

- **Targets**: amount metrics (above), and the 16/16 incorrect predictions
  that emit £0 ([taxonomy §D](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md));
  enables true citation-quality measurement.
- **Evidence base**: L-MARS (arXiv 2509.00761) +38pp on retrieval-heavy
  LegalSearchQA from multi-pass decomposition vs +0.7pp on closed-book
  Bar Exam — our amount task is exactly the former. MSR² (arXiv 2602.04690)
  and Step-wised Verification-Correction (ACL 2025) both implement
  liability-then-remedy structures for legal prediction. Source:
  [retrieval §2.7, §3.2](hybrid-rag-improvement-research-retrieval-2026-05-05.md).
- **Why second**: this is the structural fix that makes Fix #1's
  comparator-anchor table non-empty. Currently the audit notes
  outcome-signal weight is only 0.10 in the reranker
  (`issue_retrieval.py:328`) and there is no separate query for orders.
- **Code surface**: ~500 LOC across `issue_retrieval.py:124-214` (new
  Pass B branch), chunker section-type metadata in
  `rag_engine/chunking/legal_chunker.py`, BM25 tokeniser fix in
  `bm25_index.py:283-287` (keep digits for amount tokens), reindex script.
- **Bonus**: persist verifier output and retrieved chunk IDs in the
  prediction JSONL — currently the artifacts have *no* citation field
  ([taxonomy §E](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md)),
  blocking real citation-quality evaluation. Add to
  `predict_all.py:504-536`.

### Fix #3 — **Replace headline accuracy with abstention-adjusted accuracy + macro-F1 + balanced acc + MCC + AURC, on a class-rebalanced gold set** [F-EVAL-1, F-EVAL-3, F-DATA-1]

- **Targets**: every metric currently in `summary.json` is dominated by the
  always_tenant prior on n=49/1 — none of them grade the model. Until the
  gold set contains real landlord-win and split cases, no thesis-facing
  number is honest.
- **Evidence base**: He & Garcia (TKDE 2009); Saito & Rehmsmeier (PLOS ONE
  2015) on PR vs ROC under imbalance; Chicco & Jurman (BMC Genomics 2020)
  on MCC > F1/accuracy; Brodersen et al. (ICPR 2010) on balanced accuracy;
  Geifman & El-Yaniv (NeurIPS 2017) on AURC; the published
  `eval/methodology.md` already requires reporting baselines so this is
  consistent with our own methodology gates. Source:
  [prompting §2.6, §3.5](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md);
  [taxonomy §G](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md).
- **Why third (above all the prompt/retrieval fixes)**: until the gold set
  has minority-class cases and the metrics surface them, every retrieval
  or prompt change you ship will look like noise on the headline number.
  This is the prerequisite for measuring Fix #1 and Fix #2 honestly. The
  data work (~30 landlord, ~20 split/reasonable-redress real Ombudsman
  decisions) is the long pole; the metrics code is small.
- **Code surface**: ~150 LOC in `packages/eval/metrics/` (new files for
  `macro_f1.py`, `mcc.py`, `aurc.py`, `abstention_adjusted.py`),
  `packages/eval/run.py` to call them, and headline reporting in
  `scripts/eval/run_full_eval.py` to surface them. Plus the gold-build
  workflow that already exists under
  `data/eval_artifacts/gold_build/` — extend that to actively recruit
  landlord-win / reasonable-redress decisions.

---

## 3. Quick wins (Tier 1, ≤1 sprint each, low risk, test-backed)

Each ticket carries an ID for Linear. All include "must add tests" and
"must not increase leakage surface" gates per
[`docs/eval/leakage_controls.md`](../eval/leakage_controls.md) and the
implementation rules in the original brief.

### F-PROMPT-1: Plain-English IRAC schema with typed evidence ledger

- **Hypothesis tested**: Brief Hypothesis #4 (KG facts as ledger, not bullets).
- **What**: Restructure the user prompt so it has an explicit
  `evidence_ledger` table with `(fact_id, claim, supporting_span, supports_issue)`
  rows. The model fills it; missing-span fields must literally read `ABSTAIN`.
  Wording shifts to plain English (LegalBench's up-to-21pp gain finding).
- **Code**: `packages/llm_orchestrator/prompts/packs/housing_repairs_social_v1.py:75-148`
  (system prompt) and `issue_predictor.py:832-890` (repairs user prompt).
  Update `IRAC_JSON_SCHEMA` in `prompts/prediction_v2.py:77-105` to add the
  `evidence_ledger` and `verification_questions_self_answered` fields.
- **Tests**: golden-prompt snapshot tests; schema-validity tests on a
  fixture of model outputs that include `ABSTAIN` tokens.
- **Smoke**: rerun the 5-case smoke suite from the original brief; expect
  unchanged accuracy, ledger fields populated.
- **Evidence**: [prompting §2.1, §2.2, §3.1](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md);
  [audit §3, §4](hybrid-rag-current-pipeline-audit-2026-05-05.md).

### F-PROMPT-2: Native six-class Ombudsman outcome label

- **Hypothesis tested**: Brief Hypothesis #5 (rubric mismatch).
- **What**: Add `ombudsman_outcome ∈ {no_maladministration, reasonable_redress,
  service_failure, maladministration, severe_maladministration, partial_upheld}`
  to the schema as a *first-class* field. Continue collapsing to
  tenant/landlord/split/uncertain *only at the eval-adapter boundary*, not
  inside the model output. Document the collapse rule in
  `docs/eval/methodology.md`.
- **Code**: `prompts/prediction_v2.py:77-105` (schema) + new collapse helper
  in `packages/eval/adapter.py:43-68`; remove the post-hoc
  `_normalise_issue_outcome` overload at `issue_predictor.py:696-762`.
- **Tests**: parser tests for each of the six labels and partial-upheld
  edge cases.
- **Evidence**: [prompting §2.1, §3.1](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md);
  [audit W5](hybrid-rag-current-pipeline-audit-2026-05-05.md).

### F-PROMPT-3: Comparator-award table embedded in prompt

- **Hypothesis tested**: Brief Hypothesis #2 + #6 (comparator anchoring).
- **What**: For each retrieved chunk that contains an order paragraph,
  extract `(case_id, paragraph_id, awarded_amount_gbp)` deterministically
  before prompt rendering, and present them as a separate `comparator_awards`
  table in the user prompt. The schema's `comparator_awards` field (from
  F-PROMPT-1) requires the model to *select* anchors, not invent them.
- **Code**: new `packages/llm_orchestrator/pipeline/comparator_extractor.py`,
  called from `issue_predictor.py:351-556` before the LLM call.
- **Tests**: regex/extraction tests on a fixture of orders sections; a
  property test that the model cannot emit an `amount_estimate` more than
  1 IQR from the comparator anchor without also setting
  `requires-review=true`.
- **Evidence**: [prompting §2.5.2, §3.4](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md);
  [retrieval §3.2 Pass B](hybrid-rag-improvement-research-retrieval-2026-05-05.md).

### F-RET-2: BM25 tokeniser keeps amount tokens

- **Hypothesis tested**: implicit in audit W10.
- **What**: Stop dropping pure-digit tokens in the BM25 tokeniser. Keep
  £-amounts and other 1-6 digit numbers as queryable terms; preserve
  comma-separated forms via a normalisation pass.
- **Code**: `packages/rag_engine/retrieval/bm25_index.py:255-292`.
- **Tests**: tokenisation unit tests for "£1,250", "£1250", "1250".
- **Risk**: re-indexing cost (~30 min per namespace).
- **Evidence**: [audit W10](hybrid-rag-current-pipeline-audit-2026-05-05.md).

### F-RET-3: Outcome-signal weight + temporal decay on repairs reranker

- **Hypothesis tested**: brief context on retrieval ordering.
- **What**: Raise outcome-signal weight in `_apply_repairs_ombudsman_rerank`
  from 0.10 to 0.20 and add temporal decay (currently only on the
  non-repairs branch). Re-tune weights with a bootstrap on a balanced
  held-out split — *not* the current 50-case slice.
- **Code**: `packages/llm_orchestrator/pipeline/issue_retrieval.py:288-336`,
  add `_apply_temporal_decay` call in the repairs branch.
- **Tests**: golden-rerank tests on a fixture of (query, candidates).
- **Evidence**: [audit W11](hybrid-rag-current-pipeline-audit-2026-05-05.md).

### F-VERIFY-1: Loosen citation verifier (proposition path) to embedding similarity ≥ τ

- **Hypothesis tested**: Brief Hypothesis #7 (over-strict short citations).
- **What**: Replace the substring-match in
  `citation_verifier.py:358-377` with sentence-embedding similarity ≥ 0.85
  to the chunk text, using the same embedder as retrieval. Keep
  case_reference + paragraph as hard requirements. On the *chunk* path,
  add a real paragraph-overlap check (currently vacuous) — see audit W9.
- **Code**: `packages/llm_orchestrator/pipeline/citation_verifier.py:229-377`;
  may need to thread the embedder model through `CitationVerifier`.
- **Tests**: positive cases where the model paraphrases by 1-2 words
  ("the landlord shall pay £500" vs "the landlord must pay £500") that
  currently fail; negative cases that should still fail.
- **Evidence**: [audit §5, W9](hybrid-rag-current-pipeline-audit-2026-05-05.md);
  [prompting §2.2](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md).

### F-CAL-1: Temperature scaling on verbalized confidence

- **Hypothesis tested**: not in the brief; surfaced by failure taxonomy
  (mean confidence 0.487 on correct vs 0.494 on incorrect — *no resolution*).
- **What**: Fit a single-parameter temperature `T` on validation NLL of
  the binary outcome using `verbalized_confidence_pct/100` as the input
  probability. Persist `T` per matter type; apply post-hoc.
- **Code**: new `packages/eval/calibrators.py` (sklearn-style fit/transform);
  hook into `packages/eval/run.py` after metrics are computed; surface
  pre/post ECE in `summary.json`.
- **Tests**: synthetic data with known miscalibration → recover known T.
- **Evidence**: [prompting §2.3.1, §3.2](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md);
  [taxonomy §B reliability bucket](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md).

### F-EVAL-1: Macro-F1 / balanced-accuracy / MCC / abstention-adjusted accuracy

- **What**: Add metric implementations and surface them in `summary.json`
  next to the existing accuracy/Brier/ECE. Treat
  `raw_overall_outcome=='uncertain'` as a separate selective track, not
  a wrong tenant-call.
- **Code**: `packages/eval/metrics/macro_f1.py`, `mcc.py`,
  `abstention_adjusted.py`; `packages/eval/run.py`;
  `scripts/eval/run_full_eval.py` headline.
- **Tests**: against scikit-learn ground truth on small fixtures.
- **Evidence**: [prompting §2.6, §3.5](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md);
  [taxonomy §G](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md).

### F-EVAL-2: Persist verifier output + retrieved chunk IDs in JSONL

- **What**: Currently the per-case prediction artifacts contain only
  `{run_id, case_id, mode, context, result_hash, prediction}` —
  no citations, no retrieved chunk IDs ([taxonomy §A, §E](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md)).
  Persist `prediction.supporting_cases`, `verification.verified`, and
  `retrieval.results[*].chunk_id` so we can compute citation-quality
  metrics later.
- **Code**: `scripts/eval/predict_all.py:504-536` (`_serialise_prediction`).
- **Tests**: round-trip serialisation tests; a smoke that asserts every
  hybrid prediction has a non-null `verification` object.
- **Risk**: file size increases ~10x; offset by gzip on artifacts.

### F-MODE-1: Honest naming for `kg_only` and `llm_only`

- **What**: These two modes are universal abstainers on the cleaned set
  ([taxonomy §B kg_only/llm_only](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md);
  [audit W8](hybrid-rag-current-pipeline-audit-2026-05-05.md)).
  Either:
  (a) rename them in eval reports to `kg_only_no_retrieval` and
  `llm_only_no_retrieval` and explicitly flag their abstain-rate=1.0; or
  (b) build a real `kg_aware_no_retrieval` that emits a deterministic
  prediction from KG facts via an Ombudsman-rubric-prior look-up. (a) is
  the immediate fix; (b) is a Tier-2 ticket.
- **Code**: `packages/eval/metrics/types.py` enum names;
  `docs/eval/methodology.md` documentation.
- **Why this matters for the thesis**: the ablation cannot say "RAG > KG"
  while kg_only is mechanically pinned to 0%. Renaming makes the
  comparison honest.

---

## 4. Structural changes (Tier 2, multi-sprint, higher impact)

### F-RET-1: Two-pass retrieval (liability + remedy)

- **Hypothesis tested**: Brief Hypothesis #1 + #2.
- **What**: After Pass A (current single-blob query), add Pass B that:
  1. Builds a separate query from `(issue_type, severity_keywords,
     "compensation"|"order"|"redress")`.
  2. Restricts retrieval to chunks with `section_type ∈ {orders,
     determination}`. (Requires a chunker change to attach
     `section_type` metadata — section_aware retrieval per Liu et al.
     2026, [retrieval §2.6](hybrid-rag-improvement-research-retrieval-2026-05-05.md).)
  3. Fuses with RRF, then reranks the same way as Pass A.
  4. Emits 8 chunks for the prompt's `comparator_awards` block.
- **Evidence**: L-MARS multi-pass +38pp on retrieval-heavy tasks
  (arXiv 2509.00761); MSR² liability-then-remedy structure
  (arXiv 2602.04690). Source:
  [retrieval §2.7, §3.2 Pass B](hybrid-rag-improvement-research-retrieval-2026-05-05.md).
- **Code**: `packages/llm_orchestrator/pipeline/issue_retrieval.py:124-214`
  (new `_retrieve_remedy_pass`); `packages/rag_engine/chunking/legal_chunker.py`
  (section-type metadata); `packages/rag_engine/retrieval/hybrid_retriever.py`
  (filter envelope passes through `section_type`); reindex script under
  `scripts/data/reindex_with_section_types.py`.
- **Test plan**:
  - Unit: chunker tagging, query construction, filter envelope.
  - Integration: golden-retrieval test fixtures for known cases where the
    Pass A retrieved no order paragraph.
  - 5-case smoke → 10-case → 50-case (per the original brief's
    eval-plan ordering), each gated on +0.05 Amount@20% and not regressing
    accuracy.

### F-RET-4: Summary-Augmented Chunking (SAC)

- **Hypothesis tested**: not directly in the brief; emerged from research.
- **What**: Generate one document-level synthetic summary per Ombudsman
  decision (~80-120 tokens) and prepend it to every chunk before
  embedding/BM25. Rasiah et al. NLLP 2025 show this beats KG and
  late-chunking on LegalBench-RAG with generic summaries (legal-expert
  summaries are *worse*). It is the cheapest version of Anthropic's
  Contextual Retrieval that has peer-reviewed legal-domain validation.
- **Evidence**: [retrieval §2.1, §2.2, §3.1 indexing](hybrid-rag-improvement-research-retrieval-2026-05-05.md).
  Citation: <https://arxiv.org/abs/2510.06999>.
- **Code**: extend `packages/data_pipeline/` summarisation step;
  re-index. ~1k-LOC change concentrated in the indexing pipeline; no
  prediction-pipeline changes.
- **Cost estimate**: one cheap-LLM call per document (×~600 documents in
  current Ombudsman corpus) = ~$2 one-off using GPT-4o-mini.
- **Risk**: leakage — the summary must be generated from facts only, not
  from the determination/orders sections. Add a regex check that the
  summary contains no "the landlord shall" / "compensation of £" /
  "service failure" tokens.

### F-AMT-1: Band-classifier head with published Housing Ombudsman bands

- **Hypothesis tested**: Brief Hypothesis #6.
- **What**: Add `remedy_band ∈ {"0", "50-100", "100-600", "600-1000",
  "1000+"}` to the schema as a required field. Train no model — the
  band is emitted by the LLM in the same call as the liability label,
  conditioned on the IRAC-Application output and the comparator-award
  table from F-PROMPT-3.
- **Evidence**: [prompting §2.5.5, §3.4](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md);
  Housing Ombudsman Annex A.
- **Code**: `prompts/prediction_v2.py:77-105`; eval adapter band-aware
  scoring in `packages/eval/adapter.py`.
- **Tests**: per-band F1 in eval; band-confusion-matrix in `summary.json`.

### F-AMT-2: Within-band conformalised quantile regression on log(£+1)

- **Hypothesis tested**: Brief Hypothesis #6.
- **What**: For each non-zero band, fit a small CQR predictor on
  `log(amount+1)` with features:
  (i) one-hot severity label;
  (ii) similarity-weighted mean of log-amounts of the top-5 retrieved
       comparators (kNN anchor);
  (iii) `duration_days_log`;
  (iv) impact one-hots from the IRAC-Application output (vulnerability,
       Awaab's Law applicability, repeated complaint).
  CQR on the calibration split gives heteroscedastic 80% intervals;
  exponentiate to £.
- **Evidence**: Romano et al. NeurIPS 2019 (CQR); Dal Pont 2023 (PeerJ CS);
  Tweedie/zero-inflated insurance work for the £0 / heavy-tail structure.
  Source: [prompting §2.5, §3.4](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md).
- **Code**: new `packages/llm_orchestrator/pipeline/amount_predictor.py`;
  fit script under `scripts/calibration/fit_amount_cqr.py`; the engine
  calls the predictor *after* the LLM call and overrides
  `predicted_amount` if the LLM's number is more than 1 IQR from the
  CQR central estimate.
- **Tests**: synthetic log-normal data → recover known quantiles; CQR
  empirical coverage ≥ 0.78 (target 0.80).
- **Acceptance**: Amount@20% ≥ 0.30, MAE < £300, |bias| < £100 on a
  rebalanced 100-case eval (depends on F-DATA-1).

### F-DATA-1: Gold-set rebalance — landlord wins, reasonable redress, splits

- **What**: Recruit at minimum 30 landlord-favoured Ombudsman decisions
  and 20 reasonable-redress / partial-upheld cases. Add to the
  `housing_repairs_social_v1` gold corpus following the existing
  reviewer-driven pipeline under
  `data/eval_artifacts/gold_review_packets/`.
- **Why P0 for any thesis claim**: see [taxonomy §G, §H#4](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md).
  All current metrics are dominated by the prior on n=49/1.
- **Effort**: large (legal-review hours). This is the long pole; start
  immediately.
- **Risk**: low; existing reviewer workflow is mature.

### F-VERIFY-2: Self-verification pass (Chain-of-Verification)

- **What**: After the main IRAC call, run a second LLM pass that
  consumes the model's draft and asks 3-5 verification questions
  ("does paragraph X support the claim Y in the application?"); collect
  answers; force `ABSTAIN` on any field whose verification answer is
  "no" or "uncertain".
- **Evidence**: Dhuliawala et al., Findings ACL 2024
  (<https://arxiv.org/abs/2309.11495>); Self-RAG (Asai et al., ICLR 2024 oral);
  but watch for QwQ-32B regression in MSLR (`-33.8% reasoning`) — ablate.
- **Code**: new `packages/llm_orchestrator/pipeline/verifier_pass.py`;
  hook in `prediction_engine_v2.py:89-279` after `_predict_issue`.
- **Cost**: doubles inference cost on hybrid path; gate behind a flag.
- **Acceptance**: ECE drops by ≥0.10 on rebalanced gold set with
  abstention rate ≤ +0.05.

### F-EVAL-3: Conformal abstention sets and risk-coverage curves

- **What**: Add APS-style conformal classification (Romano, Sesia,
  Candès, NeurIPS 2020) on the verbalized-confidence/log-prob
  distribution from the liability head; abstain when
  set-size > 1. Report AURC and coverage at risk = {5%, 10%, 20%}.
- **Evidence**: [prompting §2.4, §3.3](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md);
  Geifman & El-Yaniv NeurIPS 2017.
- **Code**: `packages/eval/calibrators.py` (extend with APS),
  `packages/eval/metrics/aurc.py`, hook in `run.py`.
- **Tests**: synthetic data with known coverage → recover ≥ 1-α
  empirical coverage on calibration set.

### F-KG-1: Replace `KGFacts` with a typed repairs evidence ledger

- **Hypothesis tested**: Brief Hypothesis #4.
- **What**: Today `KGFacts` only carries three deposit fields
  (`kg_facts.py:44-60`); for repairs cases the ledger is empty. Add
  typed fields for repairs: `report_to_first_attendance_days`,
  `vulnerability_flag`, `hazard_category` (derived from the ontology
  at `kg_builder/ontology/housing_repairs_social_v1.yaml:19-89`),
  `complaint_stages_reached`, `prior_offer_gbp`, `awaabs_law_applies`,
  `outstanding_works_at_complaint_close`. Inject as a structured table
  *above* the retrieved cases in the prompt, with explicit `unknown`
  markers for missing fields (so the model can distinguish absence from
  evidence-of-absence).
- **Evidence**: [audit W3 + §4](hybrid-rag-current-pipeline-audit-2026-05-05.md);
  [prompting §3.1 evidence_ledger](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md).
- **Code**: `packages/llm_orchestrator/pipeline/kg_facts.py:44-133`,
  `pipeline/issue_predictor.py:960-991` (formatter), and the
  `IssueDecomposer._decompose_from_kg` to read the new node kinds at
  `issue_decomposer.py:115-185`.
- **Tests**: golden-card snapshot tests on five real repairs cases;
  property test that `unknown` fields appear in the prompt with that
  exact token.
- **Acceptance**: hybrid Brier improves vs rag_only by ≥ 0.02 on the
  rebalanced gold set, *holding retrieval fixed*.

---

## 5. Architectural / thesis-grade (Tier 3, defer until Tier 1+2 land)

### F-RET-5: Cross-encoder reranker A/B (BGE-reranker-v2-m3)

- **Why ablation, not assumed gain**: Pipitone & Houir Alami 2024 show
  Cohere rerank-v3 *decreased* P@1 on three of four LegalBench-RAG
  sub-corpora. Domain mismatch matters. Source:
  [retrieval §2.4](hybrid-rag-improvement-research-retrieval-2026-05-05.md).
- **What**: Wire `BAAI/bge-reranker-v2-m3` after RRF fusion. Run as a
  *flagged* ablation against the current weighted-feature
  reranker (`issue_retrieval.py:288-336`).
- **Code**: `packages/rag_engine/retrieval/cross_encoder_reranker.py`
  (new); `hybrid_retriever.py:117-163` to optionally route through it.
- **Acceptance**: NDCG@10 improvement ≥ 0.03 on a held-out
  retrieval-grade gold set (separate from the prediction gold).

### F-RET-6: Auto-merging parent-document retrieval

- **What**: When 2+ leaf chunks of the same parent appear in the top-k,
  merge to the parent (full section). Mitigates "Lost in the Middle"
  by preferring fewer-but-longer high-quality chunks over many fragments.
  Source: [retrieval §3.2 auto-merge](hybrid-rag-improvement-research-retrieval-2026-05-05.md).
- **Code**: `packages/rag_engine/retrieval/auto_merger.py` (new);
  invoked after reranking.

### F-RET-7: HyDE for sparse-narrative cases (gated)

- **What**: When the case file's `evidence_summary` is < 200 tokens
  (sparse intake), generate a hypothetical Ombudsman determination
  paragraph and embed it as the query (HyDE; Gao et al. ACL 2023).
  Gate behind a length check; HyDE risks injecting LLM priors that we
  do not want (Magesh et al. JELS 2025 finding). Source:
  [retrieval §2.3](hybrid-rag-improvement-research-retrieval-2026-05-05.md).
- **Code**: `packages/llm_orchestrator/pipeline/issue_retrieval.py`
  (query construction); flag-gated.

### F-DOM-1: Generalise to other matter types

- After Tier 1 + Tier 2 land for housing repairs, port the same
  patterns (band scheme, section-aware retrieval, evidence ledger) to:
  housing deposit (existing matter), property chamber RRO (existing),
  employment unfair dismissal (existing). Each will need its own
  remedies-guidance band derivation; deposit's 1x-3x rule already exists
  as a special case.

---

## 6. What I would implement now vs. ticket-only

### Implement now (Tier 1, code-only, low risk)

- F-RET-2 (BM25 keep digits): ~30-line change + tests + reindex.
- F-EVAL-1 (macro-F1 / balanced acc / MCC / abstention-adjusted): metrics
  module, no model changes.
- F-EVAL-2 (persist verifier output): JSONL serialiser change.
- F-MODE-1 (rename kg_only / llm_only honestly): docs + enum names.
- F-CAL-1 (temperature scaling): post-hoc calibrator, no model changes.
- F-PROMPT-2 (native six-class outcome): schema field addition; collapse
  at adapter boundary.

These are independent, testable, and reversible. They unlock honest
reporting on the existing 50-case slice and prepare for F-AMT-* and
F-RET-* without changing the prediction pipeline's behaviour.

### Ticket-only (Tier 1, larger surface)

- F-PROMPT-1 (full IRAC + ledger redesign): bigger prompt-engineering
  effort; needs golden-prompt review with someone with HOS-rubric
  expertise (or paralegal-in-loop per `CLAUDE.md` "Human-in-Loop").
- F-PROMPT-3 (comparator-award table): depends on F-RET-1 emitting
  order-paragraph chunks.
- F-RET-3 (rerank weights): tuning needs a balanced held-out set,
  blocked on F-DATA-1.
- F-VERIFY-1 (citation-verifier loosening): real risk of regressing
  citation discipline; needs a careful before/after on the existing
  `citation-verification-failure` smoke cases in
  `docs/eval/housing-ombudsman-hybrid-debug-log.md:171-174`.

### Ticket-only (Tier 2, structural)

- F-RET-1, F-RET-4, F-AMT-1, F-AMT-2, F-DATA-1, F-VERIFY-2,
  F-EVAL-3, F-KG-1.

### Defer (Tier 3)

- F-RET-5, F-RET-6, F-RET-7, F-DOM-1.

---

## 7. Tests and evals to run before claiming any improvement

Per the original brief's eval-plan order, and `docs/eval/gates.md`:

1. **Unit tests** for any changed parser, prompt-renderer, retrieval,
   adapter, or metric.
2. **5-case smoke** on known failure cases. From the taxonomy table,
   these are the highest-signal cases:
   - `housing-ombudsman-202428538` (gold £3818, hybrid £400) — band
     truncation.
   - `housing-ombudsman-202413497` (hybrid abstain, rag tenant) —
     borderline KG fusion noise.
   - `housing-ombudsman-202413845` (only confident-wrong on both
     hybrid & rag) — possible gold-label issue.
   - `housing-ombudsman-202509792` (hybrid £0, gold £1500) — amount
     null + remedy retrieval failure.
   - `housing-ombudsman-202306436` (lone landlord case) — minority class.
3. **10-case mixed smoke** with at least 2 landlord/no-maladministration
   or reasonable-redress rows from F-DATA-1 (or hand-curated synthetic
   if F-DATA-1 has not landed yet).
4. **Full 50-case** ONLY after the 10-case smoke shows movement on
   Amount@20% and macro-F1 *for the right reason* (i.e. the move comes
   from the new comparator anchor or the new band, not from class
   re-balancing tricks). Use the existing
   `scripts/eval/run_full_eval.py` with `--n-resamples 1000` and
   bootstrap CIs.
5. **Rebalanced 100-case** — only meaningful after F-DATA-1.
6. **Calibration evaluation** — train/calibrate on a held-out 30-case
   split; eval on the rest with bootstrap CIs on ECE per Niculescu-Mizil
   & Caruana 2005's stability concern at small n. Source:
   [prompting §3.2, §4 open question 1](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md).

---

## 8. What remains unsafe to claim in the thesis

These are the bright lines for the implementation chapter and any
publication-facing material:

1. **Do not claim "hybrid > rag_only" or "RAG > KG > LLM" on the current
   50-case slice.** The headline 0.68/0.70/0.0/0.0 numbers are: noise
   between hybrid and rag (1 abstention difference, abstention-adjusted
   ~0.97 vs ~0.97); mechanically zero for kg_only/llm_only because they
   are universal abstainers. The 50-case slice cannot adjudicate
   ablation claims.

2. **Do not claim accuracy gains relative to "deterministic baselines"
   on the 49/1 set.** always_tenant scores 0.98 acc / 0.495 macro-F1 /
   0.500 balanced acc; the model trails on every metric. Wait for
   F-DATA-1.

3. **Do not claim calibration improvement from a ECE 0.47 → ECE X
   number until the calibration is fit on a *held-out* set with
   bootstrap CIs.** Class-conditional fitting required (49/1 imbalance
   biases a single global Platt; arXiv 2410.18144). Source:
   [prompting §2.3.5, §3.2 step 4](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md).

4. **Do not claim amount-prediction improvement on the current slice
   without showing per-band MAE.** The current £520 MAE / -£466 bias
   is a bandwidth-truncation artefact; closing the gap with a band
   classifier will not transfer to bands the eval slice does not
   sample. Per-band MAE on a rebalanced gold set is the only
   defensible amount metric.

5. **Do not frame the system as "predicting court decisions".**
   Medvedeva et al. (2023) and Medvedeva & McBride (NLLP 2023) note
   that ~93% of legal-NLP outcome papers are post-hoc identification,
   not forecasting; ours uses published Ombudsman decisions, so we
   should call it "post-hoc outcome identification with retrieval
   anchoring" or equivalent. Source:
   [prompting §2.1.7](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md).

6. **Do not claim the hybrid pipeline beats commercial legal RAG.**
   The Magesh et al. 17-33% hallucination numbers are on a different
   query distribution and corpus; we cannot compare. Source:
   [retrieval §2.1](hybrid-rag-improvement-research-retrieval-2026-05-05.md).

7. **Do not present GraphRAG-style "the KG is the brain" framing.**
   Our own audit shows the KG fact card is empty for repairs (W3); the
   independent literature (Han et al. 2025; Tuora et al. 2026) shows
   VectorRAG matches GraphRAG on factual tasks. Frame the KG as a
   *consistency checker* that filters hallucinated edges and validates
   timelines; not as the primary retriever. Source:
   [retrieval §2.5, §3.3](hybrid-rag-improvement-research-retrieval-2026-05-05.md).

---

## 9. Estimated impact summary

For a rebalanced 100-case eval (50 tenant / 30 landlord / 20 split or
reasonable-redress) — i.e. *post-F-DATA-1*:

| Metric                  | Current (50-case) | Target post-Tier-1+2 | Largest single contributor |
|------------------------|------------------:|---------------------:|---------------------------|
| Accuracy               | 0.680             | 0.80                 | F-DATA-1 (real distribution) |
| Macro-F1 (3-class)     | 0.273             | 0.55                 | F-DATA-1 + F-PROMPT-2     |
| Balanced accuracy      | 0.347             | 0.65                 | F-DATA-1                  |
| Brier                  | 0.247             | 0.18                 | F-CAL-1                   |
| ECE                    | 0.469             | 0.10                 | F-CAL-1 + F-VERIFY-2      |
| Amount@20%             | 0.10              | 0.40                 | F-AMT-1 + F-AMT-2         |
| Amount@£100            | 0.18              | 0.50                 | F-AMT-1                   |
| MAE                    | £520              | £250                 | F-AMT-1 + F-RET-1         |
| Bias                   | -£466             | <£100                | F-AMT-1                   |
| Abstention rate        | 0.30              | 0.15                 | F-VERIFY-1 + F-KG-1       |
| Citation-verified rate | n/a (not persisted) | ≥0.85              | F-EVAL-2 + F-VERIFY-1    |

These targets are aspirational; the thesis-defensible commitment is the
*method* (banded amount + macro-F1 + abstention-adjusted reporting +
class-stratified calibration), not specific numbers.

---

## 10. Final response (per brief format)

**Core diagnosis (plain English):** Hybrid is *not* materially worse than
RAG-only on this slice — the 0.68 vs 0.70 gap is one abstention. The real
failures are (1) a structurally truncated amount predictor that never
emits above £1000, (2) a 49/1 gold split that lets always_tenant beat
every model, and (3) an artifact pipeline that does not persist citation
or retrieval evidence so we cannot measure citation quality at all. The
KG path is empty for repairs cases by construction, so "hybrid" is
operationally rag_only with extra free-text bullets.

**Top three fixes ranked by impact:**

1. Banded amount prediction on the regulator-published Housing Ombudsman
   bands, with a within-band conformalised quantile regressor anchored
   on retrieved comparator awards (F-AMT-1 + F-AMT-2 + F-PROMPT-3).
2. Two-pass retrieval (liability + remedy/orders) with section-typed
   chunks and BM25 that keeps digit tokens; persist verifier output
   (F-RET-1 + F-RET-2 + F-EVAL-2).
3. Honest evaluation: macro-F1 / balanced accuracy / MCC / AURC /
   abstention-adjusted accuracy on a rebalanced 100-case gold set
   (F-EVAL-1 + F-DATA-1 + F-MODE-1).

**What was implemented in this pass:** nothing — this was an
investigation and planning pass, per the original brief's instruction
to "document it as a ticket-ready plan instead of forcing a rushed
patch." Code changes ship under their respective tickets.

**What tests and evals were run:** none — the dispatched agents only
read artifacts and wrote deliverables. The first eval to run is the
unit test suite under `packages/eval/tests/` plus the 5-case smoke
listed in §7, which becomes a real pre-merge gate once F-EVAL-1 lands.

**What remains unsafe to claim in the thesis:** see §8. Headline among
them: do not claim hybrid > rag_only on the 50-case slice, do not claim
accuracy gains relative to deterministic baselines until F-DATA-1
lands, and do not present the system as "predicting court decisions"
(use "post-hoc outcome identification with retrieval anchoring").
