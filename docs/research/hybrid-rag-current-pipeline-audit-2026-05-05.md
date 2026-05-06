# Hybrid RAG + KG Current Pipeline Audit (2026-05-05)

Audit scope: read-only audit of the live `housing.repairs_social.v1` (Housing
Ombudsman) prediction pipeline as of `feature/housing-ombudsman-live-eval`
HEAD (commit `9082eeb`). No code was changed. Findings cite
`file:line` against the source tree at
`/Users/msharif/Documents/Projects/proposer/legal-mediation-system/`.

Reference eval result that motivates this audit, from
`docs/eval/housing-ombudsman-stratified-50-full-eval.md:348-365`:

| Mode      | Acc  | Brier | ECE  | Amount@20% | MAE  | Bias  |
| --------- | ---- | ----- | ---- | ---------- | ---- | ----- |
| hybrid    | 0.68 | 0.247 | 0.469 | 0.10      | 520  | -466  |
| rag_only  | 0.70 | 0.234 | 0.457 | 0.12      | 539  | -441  |
| kg_only   | 0.00 | 0.250 | 0.480 | 0.04      | 708  | -708  |
| llm_only  | 0.00 | 0.250 | 0.480 | 0.04      | 708  | -708  |

Always-tenant baseline = 0.98. Headline accuracy is therefore worse than
"always predict tenant"; for the audit, the load-bearing numbers are the
calibration (ECE 0.47 is dramatic) and the amount metrics (Amount@20% 0.10
with negative bias).

---

## Executive Summary — Top 5 Architectural Findings

1. **Liability and remedy collapsed into one prompt with no remedy
   retrieval pass.** A single per-issue IRAC call must (a) decide
   maladministration grade, (b) pick a compensation figure, and (c) cite
   precedent. Retrieval feeds the same chunks for both jobs and the
   reranker has only one outcome-signal heuristic
   (`issue_predictor.py` callsite using
   `issue_retrieval.py:288-413`). Fix sketch: split the call into a
   liability stage (no money, structured outcome rubric) and a remedy
   stage (separate retrieval pass over `remedy/order` paragraphs of the
   top-K liability cases).

2. **Single-query retrieval per issue, not decomposed by sub-question.**
   `IssueRetriever._build_repairs_issue_query`
   (`issue_retrieval.py:546-597`) builds ONE blob per issue mixing the
   resident narrative, evidence types, KG constraints, and a static
   "seed" string. There is no separate query for "remedy/quantum",
   "delay length", "vulnerability", or "Awaab's Law deadline".
   Top-K=10/5 is split across one query, so the prompt rarely sees the
   *order paragraphs* it needs to anchor an amount. Fix sketch: emit
   2–4 sub-queries per issue (liability, remedy, vulnerability,
   delay/severity) and union top-K across them with quotas.

3. **KG fact card is a free-text bullet list with three deposit-only
   typed facts; nothing repairs/Ombudsman-specific is structured.**
   `KGFacts` (`kg_facts.py:44-60`) only types
   `deposit_protection_status`, `prescribed_information_status`, and
   `check_in_inventory_baseline` — none of which apply to the social-
   housing repairs domain. The repairs ontology (`housing_repairs_
   social_v1.yaml:19-89`) defines `Disrepair`, `HazardCategory`,
   `OmbudsmanComplaint`, `Notice`, but `derive_kg_facts` never reads
   them, so for a repairs case the fact card is ALWAYS empty
   (`issue_predictor.py:966-991`). Result: "hybrid" mode is effectively
   `rag_only` plus a few free-text constraint bullets. Fix sketch:
   add a typed repairs fact card (report-to-fix days, vulnerability
   flag, hazard category, complaint stages reached, prior offer
   GBP), inject as a structured ledger above retrieved cases.

4. **`kg_only` and `llm_only` are structurally unable to score above
   ~0% on the leakage-cleaned set.** Both routes go through
   `predict_no_rag` (`issue_predictor.py:102-275`), which forces
   `supporting_cases=[]` (`issue_predictor.py:258`); the prompt itself
   is fine, but the predictions then become "tenant_wins" almost
   uniformly — the eval adapter (`adapter.py:43-68`) applies an overall
   amount summation that pegs Total predicted to 0 (no per-issue
   amounts), so `Amount@20%` and ECE are meaningless. The deeper issue
   is conceptual: the Ombudsman outcome rubric (severe/maladmin/
   service-failure/reasonable-redress/no-maladmin) was never given to
   the model as a discrete choice, just normalized post-hoc
   (`issue_predictor.py:696-762`). With no precedent, the model has no
   way to ground "service failure" vs "maladministration" against
   anything. Fix sketch: keep no-RAG modes for ablation only, but make
   the prompt force the six-class Ombudsman label with explicit
   per-class definitions, and emit `predicted_amount` from a tiny
   pre-computed remedies-guidance look-up (still no precedent
   citations).

5. **Amount path has no comparator-anchored prediction and no band.**
   `IRAC_JSON_SCHEMA` (`prompts/prediction_v2.py:77-105`) asks for a
   single `predicted_amount` integer with no instructions to ground it
   on retrieved comparator awards, no required band, no
   reasoning-trace field for "compute high/low from cases X/Y/Z". The
   parser at `issue_predictor.py:627` simply takes the first numeric
   value the model emits. There is no enforcement that the amount must
   fall inside the range of retrieved-case awards. Combined with the
   removal of `claimed_amount` fall-back in commit `9082eeb`
   (`docs/eval/housing-ombudsman-stratified-50-full-eval.md:262-263`),
   the model now ALWAYS under-predicts (-£466 mean bias on hybrid).
   Fix sketch: require `{predicted_low, predicted_central, predicted_
   high}`, enforce that each anchor is a retrieved-case award, and
   re-add a deterministic remedy-guidance prior (see
   <https://www.housing-ombudsman.org.uk/.../remedies-guidance> values)
   as a band prior the model must place inside.

---

## 1. Pipeline Data Flow

End-to-end path for one Housing Ombudsman gold row in `--engine live --client
openai --modes hybrid`:

1. `scripts/eval/predict_all.py:_cli_main` loads gold corpus
   (`predict_all.py:818`), iterates `(gold_case, mode)` pairs
   (`predict_all.py:658-707`).
2. Per row, `gold_case_to_case_file` (`case_file_adapter.py:97-228`)
   reconstructs a *pre-decision* `CaseFile`, dropping the verdict and
   suppressing legacy outcome-derived amount fields
   (`case_file_adapter.py:303-338`). For repairs the issue list is
   `[disrepair]`, mapped via `eval_to_orchestrator(...,
   matter_type=mt)` (`case_file_adapter.py:114-119`).
3. `_live_predict_fn_factory._live_call`
   (`predict_all.py:433-475`) builds:
   - a `RAGPipeline` filtered by `excluded_source_ids` and
     `max_decision_date` (`predict_all.py:122-154`,
     `_EvalFilteredRAGPipeline:196-213`),
   - a `KnowledgeGraph` for HYBRID/KG_ONLY (`_build_eval_knowledge_
     graph:333-344`) using `kg_builder.GraphBuilder`,
   - a `PredictionEngineV2` with `prompt_pack=
     HOUSING_REPAIRS_SOCIAL_V1_PACK` (`predict_all.py:444-463`).
4. `PredictionEngineV2.predict` (`prediction_engine_v2.py:89-279`):
   1. **Mode gating** — `kg_for_decomposer = kg if mode in
      (HYBRID, KG_ONLY) else None` (`prediction_engine_v2.py:114-118`).
   2. **Issue decomposition** —
      `IssueDecomposer.decompose(case_file, kg_for_decomposer)`
      (`prediction_engine_v2.py:121`). For repairs the only issue
      type is `repairs_disrepair`, so `_decompose_from_kg` returns one
      issue node OR `_decompose_from_case_file` returns one
      `IssueContext` (`issue_decomposer.py:115-185`,
      `issue_decomposer.py:187-196`).
   3. **KG fact card derivation** —
      `kg_facts_by_issue[issue.issue_type] =
      derive_kg_facts(knowledge_graph, issue.issue_type)`
      (`prediction_engine_v2.py:142-149`). Critically, `derive_kg_
      facts` (`kg_facts.py:63-133`) only reads `LeaseNode` deposit
      attributes — for a repairs case there is no lease/deposit
      data, so it returns `KGFacts()` all-`unknown`, and
      `kg_facts.is_empty()` is True. **The repairs hybrid path
      therefore has zero typed KG facts.**
   4. **No-RAG short-circuit** — for `LLM_ONLY`/`KG_ONLY` the engine
      jumps to `predict_no_rag` (`prediction_engine_v2.py:152-174`);
      Output assembled with `CitationVerifier.empty_verification()`.
   5. **Per-issue retrieval** —
      `IssueRetriever.retrieve_all` runs per-issue
      `_retrieve_for_issue` tasks in parallel
      (`issue_retrieval.py:84-122`, `issue_retrieval.py:124-214`).
      For repairs cases the path is
      `_retrieve_chunk_rag` → `_apply_repairs_ombudsman_rerank`
      (`issue_retrieval.py:216-275`,
      `issue_retrieval.py:288-336`). KG filter then applied
      (`issue_retrieval.py:251-256`) — but `kg_facts.is_empty()` is
      True for repairs, so `_apply_kg_filter` is a no-op
      (`issue_retrieval.py:650-702`).
   6. **Per-issue prediction** — `IssuePredictor.predict_all`
      builds the per-issue prompt and calls the LLM
      (`issue_predictor.py:277-349`,
      `issue_predictor.py:351-556`). For repairs the prompt is
      `_format_repairs_user_prompt`
      (`issue_predictor.py:832-890`), system prompt is
      `_OMBUDSMAN_PREDICTION_SYSTEM`
      (`packs/housing_repairs_social_v1.py:75-102`).
   7. **Citation verification** —
      `CitationVerifier.verify`
      (`citation_verifier.py:129-221`). Match by
      `case_reference`/`source_id` + paragraph span overlap
      (`citation_verifier.py:229-306`). Failures remove citations
      AND, in `_validate_prediction`
      (`output_assembler.py:436-459`), trigger `overall_outcome =
      UNCERTAIN` if no non-uncertain prediction had a citation,
      OR cap `overall_confidence` at 0.4 otherwise.
   8. **Output assembly** —
      `OutputAssembler.assemble`
      (`output_assembler.py:31-251`) computes
      tenant/landlord/penalty recovery, picks `OverallOutcome` from a
      deposit-shaped 70%-of-deposit rule
      (`output_assembler.py:253-289`), builds
      `predicted_settlement_range = (central*0.85, central*1.15)`
      (`output_assembler.py:377-388`).
5. `from_prediction_result` (`adapter.py:43-68`) collapses to the eval
   `Prediction` shape; `total_predicted_gbp = tenant_recovery +
   landlord_recovery` only when at least one issue carried an explicit
   amount (`adapter.py:50-60`).
6. `_serialise_prediction` (`predict_all.py:504-536`) writes JSONL.

### Mode boundaries

| Mode      | Decomposer KG | KG fact card | Retrieval | KG filter on retrieval | Prompt         | Citations enforced |
| --------- | ------------- | ------------ | --------- | ---------------------- | -------------- | ------------------ |
| HYBRID    | KG            | KG           | yes       | yes (when KG facts)    | repairs IRAC   | yes                |
| RAG_ONLY  | None          | none         | yes       | no                     | repairs IRAC   | yes                |
| KG_ONLY   | KG            | KG           | no        | n/a                    | repairs no-RAG | empty_verification |
| LLM_ONLY  | None          | none         | no        | n/a                    | repairs no-RAG | empty_verification |

Where the audit found those boundaries:
`prediction_engine_v2.py:114-118` (KG visibility) and
`prediction_engine_v2.py:152-174` (no-RAG short-circuit).

---

## 2. Retrieval Architecture

- **Chunking unit**: `DocumentChunk` (`rag_engine/config.py:99-156`),
  default chunk size 500 tokens, overlap 50 (`config.py:236-243`).
  Implementation lives in `rag_engine/chunking/legal_chunker.py`
  (not read here, but referenced).
- **Embedding model**: `text-embedding-3-small` 1536 dims
  (`config.py:223-230`). For Ombudsman the namespace's
  `vector_collection` is opened by `RAGConfig.from_namespace`
  (`config.py:324-394`). Live runner builds one cached pipeline per
  `(domain_id, namespace_id, rag_index_root)`
  (`predict_all.py:404-431`).
- **Vector store**: ChromaDB persistent client
  (`vectorstore/chroma_store.py:60-89`). HNSW + cosine.
- **BM25**: `rank_bm25.BM25Okapi`, lite or full mode
  (`bm25_index.py:60-127`). Tokeniser strips non-alphanumeric and
  drops short tokens (`bm25_index.py:255-292`). Pickled on disk;
  per-namespace path (`config.py:367`).
- **Hybrid fusion**: Reciprocal Rank Fusion in
  `HybridRetriever._rrf_fusion` (`hybrid_retriever.py:243-336`):
  `score = sw / (k + rank_sem) + (1-sw) / (k + rank_kw)` with
  `sw = config.semantic_weight = 0.7` and `k = 60`
  (`config.py:255-263`). Top-K * 2 candidates from each side, fused
  to top-K (`hybrid_retriever.py:132-153`).
- **Reranker (generic)**: `Reranker` weighted blend of issue match,
  temporal, region, evidence, original-score
  (`retrieval/reranker.py:33-145`). **Dead code path on the live
  Ombudsman pipeline** — `IssueRetriever._retrieve_chunk_rag` does NOT
  call the generic reranker (`issue_retrieval.py:216-275`); it does
  its own `_apply_repairs_ombudsman_rerank` for repairs cases
  (`issue_retrieval.py:247-249, 288-336`) or
  `_apply_temporal_decay` for everything else
  (`issue_retrieval.py:599-648`). So `Reranker` is wired only via
  legacy callers (deposit pipeline) and is effectively unused for the
  Housing Ombudsman path.
- **Cross-encoder reranker**: not present. There is no
  `sentence-transformers/cross-encoder/...` step anywhere in
  `rag_engine/retrieval/`. The "rerankers" are weighted-feature
  scorers using BM25 / semantic / keyword features only.
- **Top-K flow**: live calls
  `engine.predict(..., top_k=top_k)` with `--top-k 5` default in the
  shipped command (`docs/eval/.../full-eval.md:101`).
  `IssueRetriever._retrieve_chunk_rag` widens to `top_k+5`
  generally, and to `max(top_k+10, top_k*3)` for repairs
  (`issue_retrieval.py:231-238`); after rerank+KG filter trims back
  to `top_k`. The downstream prompt uses `retrieval.results[:8]`
  (`issue_predictor.py:359`) — i.e. the prompt sees up to 8 cases
  even when `top_k=5` was requested. With `--top-k 5`, this means up
  to 5 reach the prompt.
- **Filter envelope unification**: SHA-20 Phase 4
  `RetrievalFilterEnvelope` (`config.py:410-563`) is propagated to
  both Chroma and BM25 by `HybridRetriever`
  (`hybrid_retriever.py:117-163`). Eval-time leakage filters added
  by `_EvalFilteredRAGPipeline._merge_filter_envelopes`
  (`predict_all.py:157-193`).

### Retrieval architecture findings

- `_apply_repairs_ombudsman_rerank` blends scores using formula
  `0.35*base + 0.30*semantic + 0.25*issue_match + 0.10*outcome_signal`
  (`issue_retrieval.py:323-328`). Outcome signal is a single
  binary keyword check across one fixed list
  (`issue_retrieval.py:386-413`). There is no separate retrieval pass
  for "what the landlord must do" / "compensation order" paragraphs,
  even though the comments at `issue_retrieval.py:296-300`
  acknowledge the prompt needs both fact-similar and outcome-bearing
  passages.
- The BM25 tokeniser drops digits (`bm25_index.py:283-287`) so
  award amounts like "£700" and "1,250" cannot be matched
  literally. Years are kept. This blocks one obvious comparator
  retrieval path.
- The reranker for repairs hardcodes term lists per issue
  (`issue_retrieval.py:338-383`). It does not use the
  `DEPOSIT_ISSUE_KEYWORDS`/repairs additions from
  `rag_engine/config.py:567-650` — those keywords are only
  consumed by the unused `Reranker._detect_issues`
  (`reranker.py:212-234`).

---

## 3. Prompt Structure (`housing_repairs_social_v1`)

Pack defined at
`packages/llm_orchestrator/prompts/packs/housing_repairs_social_v1.py`.

### System prompt (`prediction_system`)

`_OMBUDSMAN_PREDICTION_SYSTEM`
(`packs/housing_repairs_social_v1.py:75-102`) is composed of:
- IRAC framing (Issue/Rule/Application/Conclusion) explicitly tied to
  the Ombudsman Complaint Handling Code, LTA 1985 s.11, Homes (Fitness)
  Act 2018, and Awaab's Law.
- Eval-label collapsing instruction (lines 87-94): "use tenant_wins
  when any substantive repairs or complaint-handling issue is likely
  upheld... use landlord_wins for likely no maladministration/no
  service failure. Use split only when the likely result is genuinely
  balanced after remedies".
- Stacked scaffold blocks: forum policy, forum framing, cite-or-
  abstain, safety (lines 95-101).
- The pack composition then has the engine append `IRAC_JSON_SCHEMA`
  to the system prompt
  (`issue_predictor.py:91-97`).

### User prompt

For repairs cases with retrieval, `_format_repairs_user_prompt`
(`issue_predictor.py:832-890`) is used INSTEAD of the generic
`IRAC_USER_PROMPT`. The repairs prompt has the layout:

```
Forum: Housing Ombudsman Service
Task: Predict the likely Ombudsman complaint outcome ...
Issue type / Matter type / Issue description / amount / region / completeness
Resident position
Landlord position
Evidence summary
Evidence conflicts
Timeline
Structured fact card        <-- KG fact card (empty for repairs!)
KG constraints              <-- free-text bullets from _derive_kg_constraints
Retrieved Ombudsman determinations (N): <retrieved_cases>
Return only JSON ...
```

For no-RAG (kg_only / llm_only) repairs runs, `_format_repairs_user_
prompt` is reused with `retrieved_cases =
"No retrieved cases in {prompt_mode} mode. Leave supporting_cases
empty and do not abstain solely because citations are unavailable."`
(`issue_predictor.py:175-201`) and a different system prompt
`_REPAIRS_NO_RAG_SYSTEM_PROMPT`
(`issue_predictor.py:46-71, 99-100`).

### KG facts injection

Two paths into the prompt:

- **Free text** — `kg_constraints` rendered as bullets in the user
  prompt (`issue_predictor.py:456-458, 873`). For repairs cases
  `_derive_case_file_constraints`
  (`issue_decomposer.py:424-472`) only emits deposit-relevant
  constraints (deposit protection, prescribed info, inventory
  baseline, rent arrears). It returns `[]` for `repairs_disrepair`
  / `repairs_damp_mould` / `complaint_handling_failure`.
- **Typed KG fact card** — `_format_kg_fact_card`
  (`issue_predictor.py:960-991`) renders only the three deposit-
  oriented typed facts and returns "" when all are unknown. For
  repairs: empty string.

### JSON schema enforcement

Single schema in `IRAC_JSON_SCHEMA`
(`prompts/prediction_v2.py:77-105`); always concatenated to whichever
system prompt is used (`issue_predictor.py:91-100`). Fields:
`outcome | raw_confidence | predicted_amount | reasoning |
key_factors | supporting_cases[{case_reference, year, paragraph,
proposition_id, quote, relevance}] | counterfactuals |
evidence_strength | data_completeness_impact`.
Enforcement is regex/JSON parse only — `_extract_json_payload`
(`issue_predictor.py:666-693`) strips fences and tries
`json.loads`, then a sliding-window `JSONDecoder.raw_decode`. There
is no schema validator (no `pydantic` parse on the model output).

### Abstention / uncertainty mechanism

- The IRAC schema rule `"outcome" MUST be exactly one of: ...
  "uncertain"` (`prompts/prediction_v2.py:97`).
- `_normalise_issue_outcome` (`issue_predictor.py:696-762`)
  collapses many surface forms to four labels.
- Engine returns "uncertain" when no issues found
  (`prediction_engine_v2.py:125-130`), or RAG missing
  (`prediction_engine_v2.py:189-198`), or no sufficient cases
  (`prediction_engine_v2.py:217-221`).
- Citation verification (`output_assembler.py:436-459`) demotes
  to UNCERTAIN or caps confidence ≤ 0.4 when there are zero
  verified citations.

### Amount estimation prompt

Schema field: `"predicted_amount": <number in pounds or null if
uncertain>` (`prompts/prediction_v2.py:81-84, 100-101`). For
deposit-protection cases the schema mentions 1x-3x band; for repairs
cases there is **no band, no comparator instruction, and no
remedies-guidance prior**. The repairs user prompt does not even
mention how to compute the amount
(`issue_predictor.py:858-890`).

---

## 4. KG Fusion Mechanism

Three injection paths exist; all weak for the Housing Ombudsman
domain:

1. **Decomposition** — for HYBRID/KG_ONLY, `IssueDecomposer.
   _decompose_from_kg` (`issue_decomposer.py:115-185`) reads
   `IssueNode`/`ClaimedAmountNode`/`EvidenceNode`/`LeaseNode`
   from the KG. The repairs ontology has `Disrepair`,
   `HazardCategory`, `OmbudsmanComplaint`, `Notice` node kinds
   (`housing_repairs_social_v1.yaml:19-47`), but `IssueDecomposer`
   only reads `NodeType.ISSUE` — it has no awareness of these
   repairs-specific node kinds. So even when a repairs KG is built,
   only the generic Issue/Evidence/Claim path runs.

2. **Reranking penalty** — `_apply_kg_filter`
   (`issue_retrieval.py:650-702`) penalises chunks whose text
   contradicts typed KG facts. Patterns are deposit-only
   (`DEPOSIT_LATE_CONTRADICTORS`, etc.,
   `issue_retrieval.py:19-38`). For repairs: no penalty, ever.

3. **Prompt fact card** — `_format_kg_fact_card`
   (`issue_predictor.py:960-991`). Repairs: always empty (all
   three typed facts are deposit-only).

There is no **evidence-ledger** style ("the system *knows* X because
of Y"). The KG-derived data shows up as either:
- The `kg_constraints` free-text bullet list — which is empty for
  repairs (see §3 KG facts injection).
- The `evidence_summary` and `timeline_summary` blocks
  (`issue_predictor.py:790-817, 1056-1092`). These are simple text
  flatten of the case file's evidence/events, with no marker
  separating "KG-derived" from "user-supplied" facts.

The prompt does not distinguish facts the system knows from facts
the model is being asked to infer. Everything is mixed prose under
"Resident position", "Landlord position", "Evidence summary",
"Timeline".

---

## 5. Citation Verification

Implementation: `CitationVerifier.verify`
(`citation_verifier.py:129-221`).

### Match logic

- For non-proposition citations
  (`citation_verifier.py:229-306`):
  1. Resolve candidate chunks by `source_id` (preferred) OR
     `normalize_case_ref(case_reference)`.
  2. Optional `source_kind` equality.
  3. Optional paragraph span overlap via `_parse_paragraph_field`
     (`citation_verifier.py:61-86`) — accepts integers, ranges
     `"7-9"`, otherwise `None`. If either side has no paragraph
     metadata, the span check is treated as vacuously true
     (`citation_verifier.py:288-305`).

- For proposition citations
  (`citation_verifier.py:308-356`): exact `proposition_id` match
  + case-ref + (optional) paragraph + quote substring match
  (`citation_verifier.py:358-377`). Quote is normalised lowercase
  whitespace.

### Failure modes (likely live)

- **Over-strict on quote**: proposition path requires the citation
  quote to be a substring (after lowercasing/whitespace
  normalisation) of the retrieved chunk's `quote`/`source_passage`/
  `chunk_text` (`citation_verifier.py:358-377`). Real LLM outputs
  routinely paraphrase by 1-2 words; substring check fails.
- **Over-permissive on chunk-RAG path**: paragraph span is treated
  as vacuously true when the chunk does not carry a `paragraph`
  field (`citation_verifier.py:299-304`), and the legacy Ombudsman
  chunks generally do not. So the only real check on the chunk path
  is `case_reference` match — i.e. the model can cite ANY paragraph
  of the right case and verification passes.
- **No retrieval-window check** — verification accepts a citation
  if the same `case_reference` is in *any* issue's retrieval set
  (`citation_verifier.py:147-171`). For a multi-issue case the
  model could cite a case retrieved for issue A while predicting
  issue B and pass.
- The hybrid debug log (`docs/eval/housing-ombudsman-hybrid-debug-
  log.md:171-174`) confirms two of five smoke cases still hit
  citation verification failures and got confidence-capped after
  the fix patch.

---

## 6. Amount Prediction Path

- **Origin**: model emits one `predicted_amount` integer per issue
  (`prompts/prediction_v2.py:81-84, 100-101`).
- **Conditioning on comparator awards**: NONE. The retrieved cases
  are pasted as `case_ref / year / score / chunk_text[:1500]` only
  (`issue_predictor.py:374-376`). Award amounts in the chunks are
  whatever happens to be near the top of the reranked text.
- **Band**: NONE for repairs. Generic deposit schema says
  `"For deposit_protection penalty issues, predicted_amount should
  be the penalty amount (1x-3x deposit)"`
  (`prompts/prediction_v2.py:101`); nothing equivalent for repairs.
- **Parsing**: `_to_optional_float` (`issue_predictor.py:929-938`)
  accepts any finite float ≥ -inf; clamped only to "finite"; no
  cap, no floor, no comparison to retrieved-case awards.
- **Issue-to-overall aggregation**: `OutputAssembler.assemble`
  (`output_assembler.py:51-94`) sums tenant/landlord recovery,
  applies `min(deposit_cap, …)` (`output_assembler.py:53,
  92-93`). For Ombudsman cases there is no deposit, so
  `deposit_cap = float('inf')` and the sum passes through.
- **Eval adapter**: `from_prediction_result`
  (`adapter.py:50-60`) sets `total_predicted_gbp = tenant_recovery
  + landlord_recovery` only when at least one issue had an explicit
  amount. With repairs cases predicting `predicted_amount=null`
  (now that `claimed_amount` fall-back was removed in commit
  `9082eeb`), the total can be 0 for many rows — the bias of
  -£466 in the eval metrics is a direct consequence.
- **Settlement range**: `_build_settlement_range` is `[central*0.85,
  central*1.15]` capped at 3× deposit
  (`output_assembler.py:377-388`). Deposit-shaped; meaningless for
  Ombudsman compensation orders.

The recent fix in commit `9082eeb` ("harden ombudsman amount
scoring") removed the safety net of falling back from
`predicted_amount=None` to `issue.claimed_amount` (see
`docs/eval/housing-ombudsman-stratified-50-full-eval.md:262-263`).
This was correct as a leakage fix but exposed the absence of a
real amount-prediction path.

---

## 7. Architectural Weaknesses (12+)

### W1. Single-blob query vs decomposed sub-questions

- **What**: One query string per issue mixing seed terms,
  narrative, evidence types, and KG constraints.
- **Evidence**: `issue_retrieval.py:546-597`
  (`_build_repairs_issue_query`),
  `issue_retrieval.py:583-597` (`_repairs_query_seed`).
- **Why it hurts**: Top-K=5 must cover liability paragraphs,
  remedy paragraphs, vulnerability paragraphs, and Awaab's Law
  applicability — but they are typically on different pages of a
  determination. With one query, the prompt sees mostly liability
  text. Drives Amount@20%=0.10 and bias=-£466 because the model
  has no comparator awards in front of it.

### W2. No remedy-paragraph retrieval pass

- **What**: There is no second retrieval call for "remedy"/
  "what the landlord must do"/"compensation ordered".
- **Evidence**: `issue_retrieval.py:124-214` only branches on
  retrieval *strategy* (chunk vs proposition vs hybrid), not on
  retrieval *purpose*. `_apply_repairs_ombudsman_rerank` weighs
  outcome-signal at 0.10 (`issue_retrieval.py:328`) — too low to
  guarantee a remedy chunk lands in the prompt.
- **Why it hurts**: Same as W1; this is the cleanest architectural
  fix.

### W3. KG fact card is deposit-only; repairs fact card is empty

- **What**: `KGFacts` carries three typed deposit fields; for
  repairs it is always all-`unknown`.
- **Evidence**: `kg_facts.py:44-60` (struct),
  `kg_facts.py:63-133` (only reads `LeaseNode.deposit_*`),
  `issue_predictor.py:960-991` (renders empty when
  `is_empty()`).
- **Why it hurts**: HYBRID is supposed to differ from RAG_ONLY by
  feeding structured facts. For repairs that delta is zero, which
  is consistent with the eval finding `hybrid=0.68 ≤ rag_only=0.70`.

### W4. Liability and remedy entangled in one prompt call

- **What**: One `IssuePredictor._predict_issue` call
  (`issue_predictor.py:351-556`) must decide outcome label AND
  predicted amount AND select citations AND produce reasoning, with
  one max_tokens=8192 generation
  (`issue_predictor.py:512-513`).
- **Evidence**: `issue_predictor.py:444-503` shows `prompt_kwargs`
  is the full bundle.
- **Why it hurts**: The model's attention budget is split. With
  no separate amount-grounding step, money is essentially
  hallucinated from training prior, hence the strong negative
  bias.

### W5. Outcome rubric does not match Ombudsman label space

- **What**: The forum has six labels (no maladmin, service
  failure, maladministration, severe maladministration, reasonable
  redress, partial upheld); the JSON schema only allows four
  (tenant/landlord/split/uncertain). Mapping is post-hoc string
  match.
- **Evidence**: `prompts/prediction_v2.py:81, 96-98` (schema);
  `issue_predictor.py:696-762` (`_normalise_issue_outcome`); the
  pack instruction at
  `packs/housing_repairs_social_v1.py:87-94` tells the model how
  to collapse, but the model never emits the actual six-class
  determination — there is no
  `"ombudsman_outcome": one_of([...])` field on the schema.
- **Why it hurts**: The model has no rich label to reason
  through; "tenant_wins" applies equally to severe maladmin with
  £2k order and to "service failure" with apology only. This
  destroys calibration (ECE 0.47) and amount prediction.

### W6. Amount has no band, no comparator anchor, no remedies-guidance prior

- **What**: `predicted_amount` is a single integer. No
  `low/central/high`. No instruction to anchor on retrieved
  awards. No prior from the Ombudsman remedies-guidance bands.
- **Evidence**: `prompts/prediction_v2.py:81-84, 100-101`;
  `issue_predictor.py:627`; `_format_repairs_user_prompt`
  (`issue_predictor.py:858-890`) does not mention how to compute
  the amount.
- **Why it hurts**: Direct cause of Amount@20%=0.10 and
  MAE=£520.

### W7. Negative bias from `claimed_amount` removal with no replacement

- **What**: The recent fix removed the fall-back from
  `predicted_amount=None` to `issue.claimed_amount` (commit
  `9082eeb`,
  `docs/eval/housing-ombudsman-stratified-50-full-eval.md:262-263`).
  This was correct (the legacy claimed amount was outcome-derived)
  but no comparator-anchored predictor was put in its place.
- **Evidence**: `issue_predictor.py:382-391` no longer has the
  fall-back.
- **Why it hurts**: -£466 mean signed error means the system now
  systematically under-predicts when the model omits an amount.

### W8. `kg_only` and `llm_only` cannot produce non-zero accuracy on the cleaned set

- **What**: Both routes go through `predict_no_rag` and the eval
  adapter then collapses outcomes; without retrieval the model
  abstains in many cases and the eval adapter pegs `total_predicted_
  gbp = 0` because no per-issue amounts exist
  (`adapter.py:50-60`).
- **Evidence**: `issue_predictor.py:102-275` (no-RAG routes);
  the leakage-cleaned eval shows `kg_only=0.0` accuracy and 50/50
  predictions collapsed to "split"
  (`docs/eval/.../full-eval.md:354-365`).
- **Why it hurts**: Ablation cannot say anything about the
  marginal contribution of the KG when KG-only is structurally
  pinned to ~0%. We cannot say "RAG > KG > LLM" with any
  confidence.

### W9. Citation verifier is over-permissive on chunk path, over-strict on proposition path

- **What**: Chunk path verifies on `case_reference` only when no
  paragraph metadata is on chunks; proposition path requires
  substring quote match.
- **Evidence**: `citation_verifier.py:288-305` (chunk path
  vacuous span check), `citation_verifier.py:358-377`
  (proposition substring quote match).
- **Why it hurts**: On the chunk path the model can cite any
  paragraph of the right case and pass — bad for trust. On the
  proposition path real model paraphrases fail — drives the
  citation-verification capping seen in
  `docs/eval/housing-ombudsman-hybrid-debug-log.md:171-174`.

### W10. BM25 tokeniser drops digits

- **What**: `bm25_index.py:283-287` drops pure-digit tokens
  unless they are 4-character years.
- **Why it hurts**: Cannot retrieve by award amount ("£700",
  "£1,250") which is the most direct comparator signal for the
  amount prediction task.

### W11. Reranker weights configured for deposit, not Ombudsman

- **What**: `_apply_repairs_ombudsman_rerank` weights:
  `0.35*base + 0.30*semantic + 0.25*issue_match +
  0.10*outcome_signal` (`issue_retrieval.py:323-328`). The
  generic `Reranker` (`retrieval/reranker.py:33-145`) is unused on
  this path.
- **Why it hurts**: 10% weight on outcome signal is
  insufficient given that the *purpose* of retrieval here is to
  surface determinations whose outcome the model can copy. There
  is no temporal-decay weighting at all on the repairs path
  (`_apply_temporal_decay` is the *else* branch,
  `issue_retrieval.py:247-250`), so very old determinations
  drift up the rank.

### W12. Top-K is too small for one-query setting

- **What**: `--top-k 5` is the shipped command
  (`docs/eval/.../full-eval.md:101`). Pre-rerank pool is at
  most `top_k*3 = 15`; the prompt sees up to 8 cases via
  `retrieval.results[:8]` (`issue_predictor.py:359`).
- **Why it hurts**: With one query that needs to cover liability
  AND remedy, 15 candidates is rarely enough to surface both.

### W13. Output assembler runs deposit-shaped overall-outcome rule

- **What**: `_determine_overall_outcome`
  (`output_assembler.py:253-289`) uses `tenant_recovery > 0.7 *
  deposit` to call tenant-win. For repairs there is no deposit,
  so the function falls into the count-based branch
  (`output_assembler.py:270-289`) which picks the modal issue
  outcome.
- **Why it hurts**: For multi-issue Ombudsman cases (rare, but
  happens) any single uncertain head can flip the overall
  outcome to UNCERTAIN/SPLIT
  (`output_assembler.py:285-289`).

### W14. Settlement range is `[central*0.85, central*1.15]` (deposit-only logic)

- **What**: `_build_settlement_range`
  (`output_assembler.py:377-388`) hardcodes ±15%.
- **Why it hurts**: For Ombudsman compensation orders the
  empirical band is much wider; presenting a tight band signals
  false certainty downstream.

### W15. `IssueRetriever._is_repairs_case` route gating relies on `domain_id` *or* hardcoded issue strings

- **What**: `issue_retrieval.py:277-286` returns True for
  domain-id match `housing.repairs_social.v1` OR for fixed
  issue values `repairs_disrepair`/`repairs_damp_mould`/
  `complaint_handling_failure`. The fixed list is duplicated in
  `issue_predictor.py:39-43` and again in the pack at
  `packs/housing_repairs_social_v1.py:67-72` (matter_types).
- **Why it hurts**: Three separate sources of truth for "what
  counts as a repairs case". Adding a new sub-issue (e.g.
  `cladding_failure`) means editing three lists.

---

## 8. Mode Wiring Sanity Check

**Question**: Does `kg_only` ever read the gold winner field or any
outcome-derived field?

- `predict_no_rag` (`issue_predictor.py:102-275`) builds the
  prompt from `IssueContext` only (`issue_predictor.py:202-247`
  `kg_only` branch). The fields read are: `issue.issue_type`,
  `issue.issue_description`, `tenancy.deposit_amount`,
  `claimed_amount`, `tenancy_duration`, `tenancy_type`, `region`,
  `issue.data_completeness`, `issue.kg_constraints`, KG fact card
  (deposit-typed), `evidence_summary`, `evidence_conflicts`,
  `timeline_summary`, `tenant_claim`, `landlord_claim`.
- `case_file_adapter.gold_case_to_case_file`
  (`case_file_adapter.py:97-228`) explicitly drops
  `ground_truth_outcome`, `key_reasoning_quotes`, `statutory_basis`,
  `cited_authorities`, `decision_date` per the docstring
  (`case_file_adapter.py:9-37`). Outcome-derived
  `disputed_amount_gbp` and `claimed_amounts` are also suppressed
  for legacy Ombudsman rows
  (`case_file_adapter.py:303-338`).
- `IssueDecomposer._decompose_from_kg`
  (`issue_decomposer.py:115-185`) reads from the KG that
  `GraphBuilder` built from the *reconstructed* CaseFile
  (`predict_all.py:333-344`); the KG itself never sees the
  gold outcome.

**Answer**: After the post-`9082eeb` patches there is no path by
which `kg_only` reads the gold winner or outcome amount. The
`kg_only=0.0` accuracy on the cleaned set is therefore a
legitimate signal of W8 (structural inability to predict without
retrieval), not a leakage artifact.

**Question**: Does `llm_only` ever sneak in retrieval?

- `prediction_engine_v2.py:152-174` short-circuits to
  `predict_no_rag` for both LLM_ONLY and KG_ONLY.
  `output_assembler.assemble(..., retrieval_results={},
  verification=CitationVerifier.empty_verification())`
  (`prediction_engine_v2.py:166-174`).
- The repairs no-RAG prompt explicitly tells the model not to
  invent citations
  (`issue_predictor.py:46-61, 195-198`).
- `_predict_issue_no_rag` then force-empties citations
  (`issue_predictor.py:258`).

**Answer**: No retrieval reaches `llm_only`.

**Question**: Does `rag_only` use KG facts?

- `prediction_engine_v2.py:114-118`: `kg_for_decomposer = kg if
  mode in (HYBRID, KG_ONLY) else None` — so RAG_ONLY's
  decomposer sees no KG.
- `prediction_engine_v2.py:142-149`: `kg_facts_by_issue` only
  populated for HYBRID/KG_ONLY.
- The retriever is given the empty `kg_facts_by_issue` for
  RAG_ONLY (`prediction_engine_v2.py:199-204`), so
  `_apply_kg_filter` is bypassed
  (`issue_retrieval.py:251-256`).
- The predictor's `_kg_facts_by_issue` instance attr is
  overwritten with the empty map for RAG_ONLY too
  (`prediction_engine_v2.py:225`).

**Answer**: RAG_ONLY does not see the KG fact card or KG
contradiction-penalties. (For repairs this is moot — the typed
KG facts are empty even in HYBRID, see W3.)

---

## Dead Code Found

- `packages/rag_engine/retrieval/reranker.py` — full file is
  unused on the live Housing Ombudsman path.
  `IssueRetriever._retrieve_chunk_rag`
  (`issue_retrieval.py:216-275`) implements its own rerank inline
  and never instantiates `Reranker`. Unit tests
  (`packages/rag_engine/tests/test_reranker.py`) keep it green.
- `DEPOSIT_ISSUE_KEYWORDS` / `DEPOSIT_LATE_CONTRADICTORS`
  patterns in `rag_engine/config.py:567-650` and
  `issue_retrieval.py:19-38` only fire on the deposit
  pipeline; for repairs they sit in source but never apply.
- `_NO_RAG_JSON_SCHEMA` (`issue_predictor.py:63-71`) is built
  by string-replacing two lines of `IRAC_JSON_SCHEMA` but
  appended to the system prompt only via `_repairs_no_rag_
  system_prompt` (`issue_predictor.py:99-100`); the deposit
  no-RAG path uses the unmodified schema instead
  (`issue_predictor.py:216`). Mild divergence, easy to drift.

## Files Read But Not Cited Above (for completeness)

- `packages/llm_orchestrator/pipeline/proposition_retrieval.py`
  — proposition retriever exists and is wired through
  `RetrievalStrategy.{PROPOSITION_DIRECT,PROPOSITION_PAGERANK,
  HYBRID_CHUNK_PROPOSITION}` (`issue_retrieval.py:134-212`),
  but the live Ombudsman runner uses
  `RetrievalStrategy.CHUNK_RAG` (default in
  `prediction_engine_v2.py:47, 100-103`); the proposition
  retriever does not contribute to the eval numbers under
  audit. Path is intact and well-tested but inactive on this
  matter.
- `packages/llm_orchestrator/pipeline/forum_policy_verifier.py`
  — runs after assembly to suppress directive advice and
  enforce disclaimers; it is not currently wired into the
  prediction engine's `predict()` entry
  (`prediction_engine_v2.py:89-279`). The
  `ForumPolicyVerifier` class is invoked only by tests and
  some product/API surfaces, not by `predict_all.py`.

## Notes on Files Shorter Than Expected

- `packages/rag_engine/vectorstore/base.py` is 148 lines as
  expected. `chroma_store.py` is 380 lines as expected.
- All other listed files were read in full, no truncation.

