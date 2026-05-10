# Stream C — Proposition-Side Factor Backfill Plan (2026-05-10)

> **Predecessor:** [`2026-05-07-stream-c-recovery-sprint.md`](2026-05-07-stream-c-recovery-sprint.md) (forced-answer + audit-only validator). Recovery sprint and case-side backfill complete; this plan addresses the remaining rate-limiter for any "KG fired end-to-end" empirical claim.

**Goal:** Populate `Proposition.factor_ids` across the corpus so `FactorRetriever.factor_overlap` scoring becomes non-zero on real cases. Together with the case-side backfill landed in commits `92a81e9` + `60313a3`, this is the prerequisite for `kg_used_for_prediction=True` to flip in any prediction artifact.

**User direction:** "Proposition-side backfill (£40–80 LLM + ~6h engineering for the Postgres-backed proposition tagger + writer). This is the rate-limiter for any 'KG fired end-to-end' empirical claim. Risk: same as case-side — if it doesn't lift hybrid, the architecture has a real problem on this corpus."

**Operating principle:** Build the cheapest backfill that makes the architectural gate fire end-to-end on the 48-case ablation corpus. Test whether the hybrid prediction lifts. If yes: justifies further investment. If no: thesis pivots to "we built the system; it works as designed; the empirical lift requires datasets/factor-catalogues different from the ones we tested."

---

## Reconnaissance findings (2026-05-10)

### Existing tooling

| Component | Where | What it does |
|---|---|---|
| Proposition extraction CLI | `scripts/ingestion/ingest_propositions.py` | LLM-based extractor that walks corpus manifest → produces `Proposition[]` per case. Writes to Postgres. `--dry-run` exercises LLM but skips DB write. |
| Proposition Pydantic model | `packages/kg_builder/propositions/models.py:192` | Has `factor_ids: list[str]` (already in the model schema; just empty in extraction output). |
| Extractor module | `packages/kg_builder/propositions/extractor.py` | Used by the CLI. |
| FactorRetriever | `packages/llm_orchestrator/pipeline/factor_retrieval.py:119` | Duck-typed: only requires `repository.search_by_issue_tags(...)`. |
| File-backed graph store | `packages/kg_builder/storage/json_store.py:36` (`JSONGraphStore`) | Exists; needs duck-type verification — does it implement `search_by_issue_tags`? |
| Positive-control fixture | `data/eval_artifacts/positive_control/housing_repairs_social_v1_one_case_kg/propositions.json` | 8 hand-tagged propositions; concrete reference for "what populated propositions look like". |

### Critical blocker

**Postgres is not running locally.** `pg_isready` returns "no response on /tmp:5432". The user-direction said "Postgres-backed" but the existing pipeline assumes a running DB. Two paths:

1. **Path A — start Postgres, run existing pipeline.** Brings up local Postgres with the project's schema; runs `ingest_propositions.py --commit`; then writes a separate tagger CLI that updates `proposition.factor_ids` via SQL UPDATE; wires FactorRetriever to a Postgres-backed `PropositionGraphRepository`. Requires DB management work.
2. **Path B — JSONL-backed proposition store.** Modify the extractor to dump propositions to JSONL (or capture from `--dry-run` + monkey-patch). Build/extend `JSONGraphStore` (or a thin wrapper) to implement the duck-typed `search_by_issue_tags`. Tag the JSONL in-place with factor_ids via a separate LLM pass. Wire predict_all with a `--proposition-store-path` flag.

**Decision: Path B (JSONL-backed).**

Reasons:
- FactorRetriever is duck-typed, so the architectural test is invariant to which backend serves the propositions.
- Postgres setup is a wildcard — depends on schema migration state, connection config, secrets management. Could consume hours before any LLM spend.
- JSONL gives the same architectural lift signal AND is reproducible/portable across environments (good for thesis reproducibility).
- Total engineering scope is comparable to Path A (~6h), but with fewer environmental unknowns.
- The case-side backfill already used a sidecar JSON pattern — stylistically consistent.

If the experiment ends up needing Postgres for other reasons (e.g., performance, cross-domain), the work can be redone later — but the empirical question doesn't require Postgres.

---

## Hard constraints

1. **No final UNCERTAIN.** Same as recovery sprint. Forced-answer mode stays on.
2. **Idempotent backfill.** Running the tagger twice on the same propositions produces the same factor_ids (deterministic LLM seed where possible).
3. **No real LLM calls in unit tests.** Existing fakes pattern.
4. **Factor catalogue is the same 13 gate-countable factors** used in the case-side backfill (skip `inspection_offered`, `impact_severity_reported`).
5. **JSONL store is a one-way artifact** — the eval pipeline reads it; nothing else depends on it. Safe to regenerate.
6. **Cap LLM spend at £100.** Hard budget. If trending higher, stop and re-cost.
7. **All 1,830+ existing tests must still pass.**
8. **The proposition extractor's existing CLI (--dry-run mode + DB-write disabled) must not be regressed.**
9. **Dry-run validation before any £-spend step** — small N, verify outputs match Pydantic round-trip and FactorRetriever's duck-type contract.

---

## Stages and budget

| Stage | What | LLM | Engineering | Wall |
|---|---|---|---|---|
| 0 | Verify `JSONGraphStore` duck-type compatibility OR build a thin wrapper. Add tests. | £0 | 1h | — |
| 1 | Write a `dump-to-jsonl` patch to `ingest_propositions.py` (or wrap with a capture script). Add tests. | £0 | 1.5h | — |
| 2 | Run proposition extraction over 48 cases × N propositions/case (estimate ~50 props/case → ~2,400 propositions). | £15–25 | — | ~30min |
| 3 | Build the proposition factor-tagger CLI: read proposition JSONL, batch propositions to LLM with the 13-factor catalogue, emit `factor_ids: list[str]`, write back to JSONL. Add tests, idempotent, dry-run. | £0 | 2.5h | — |
| 4 | Sample run (10–20 propositions) on the tagger to validate output | ~£1 | — | ~5min |
| 5 | Full proposition tagging run | £20–40 | — | ~3–6h |
| 6 | Wire `predict_all` `--proposition-store-path` flag to use the JSONL store. Add tests. | £0 | 1h | — |
| 7 | 4-mode ablation against fully-backfilled corpus | ~£8 | — | ~30min–2h |
| 8 | Write report dated 2026-05-10 with multi-axis comparison vs recovery + case-backfill | £0 | 1h | — |
| **Total** | | **£44–74** | **7h** | **~5–9h** |

**Within user-authorised £40–80 + 6h.** The 7h engineering vs 6h estimate is 17% over — acceptable given Postgres-vs-JSONL design call.

---

## Decision gates

### Gate 1 — JSONGraphStore duck-type compatibility (after Stage 0)

| Result | Action |
|---|---|
| `JSONGraphStore` already implements `search_by_issue_tags` and `search_by_entities` | use it directly |
| Implements one but not the other | extend with the missing method, keep PR minimal |
| Implements neither | build a thin wrapper class (~50 LOC) that loads JSONL into in-memory dict + implements the duck-type interface |

### Gate 2 — Sample tagger validation (after Stage 4)

| Result | Action |
|---|---|
| ≥80% of sampled propositions get ≥1 factor_id, agreement looks reasonable | proceed to Stage 5 |
| <50% get any factor_id | stop, debug prompt or factor-id taxonomy match |
| ≥50% but <80% | inspect samples, decide whether to proceed at degraded coverage or tighten prompt |

### Gate 3 — Ablation result (after Stage 7)

| Result | Interpretation | Thesis framing |
|---|---|---|
| Hybrid lifts ≥+3 cases vs case-backfill (i.e. ≥0.937 vs case-bf 0.875) AND `kg_used_for_prediction=True` rate ≥50% | Architectural lift confirmed; backfill investment justified | "Factor-proposition KG-controlled CBR-RAG measurably lifts prediction when the data layer is populated. Architecture's design decision D5 (graceful fallback) means the system is safe to deploy even before backfill completes." |
| Hybrid lifts +1 to +2 cases AND `kg_used` rate ≥50% | Modest lift, within CI noise on n=48 | "Architecture activates as designed; lift is modest on this corpus and would benefit from a larger eval set." |
| Hybrid unchanged or regresses despite `kg_used` flipping True | KG content reaches prompt but doesn't improve prediction | "Empirical lift requires different datasets/factor-catalogues than this corpus. Architecture works; this corpus may not be the right test." |
| `kg_used` rate stays <30% | Wiring problem; tagger output isn't being matched correctly | Stop and debug the matching logic |

### Gate 4 — Multi-axis hybrid signal (after Stage 7)

Same as recovery sprint Gate 4: hybrid should at minimum match rag_only on accuracy, AND improve at least one of: ECE, citation validity, evidence support rate. Multi-axis interpretation regardless of accuracy delta.

---

## File structure

### New files

- `docs/superpowers/plans/2026-05-10-stream-c-proposition-backfill.md` — this plan
- `packages/kg_builder/storage/jsonl_proposition_store.py` — JSONL-backed proposition store implementing the duck-typed interface (if `JSONGraphStore` doesn't already)
- `packages/kg_builder/storage/tests/test_jsonl_proposition_store.py` — tests
- `scripts/eval/tag_propositions_with_factors.py` — proposition factor-id tagger CLI (analogous in style to `factor_gold_annotation.py`)
- `scripts/eval/tests/test_tag_propositions_with_factors.py` — tests
- `scripts/ingestion/dump_propositions_to_jsonl.py` — wraps `ingest_propositions.py --dry-run` with output capture (or modifies `ingest_propositions.py` to accept `--output-jsonl`)
- `data/eval_artifacts/propositions/housing_repairs_social_v1.propositions.jsonl` — extracted propositions (Stage 2 output)
- `data/eval_artifacts/propositions/housing_repairs_social_v1.propositions.tagged.jsonl` — tagged propositions (Stage 5 output)
- `eval/predictions/stream_c_full_backfill_2026_05_10/` — Stage 7 ablation predictions
- `eval/results/stream_c_full_backfill_2026_05_10/` — Stage 7 ablation results
- `docs/eval/2026-05-10-stream-c-full-backfill.md` — final report (date-prefixed per user request)

### Modified files

- `scripts/eval/predict_all.py` — add `--proposition-store-path` flag (Stage 6)
- `packages/llm_orchestrator/pipeline/factor_retrieval.py` — possibly NO change if the duck-type already works; only modify if a wrapper is needed at the engine seam
- `docs/eval/stream-c-supervisor-briefing-2026-05-07.md` — append Section 16 with proposition-backfill results

### Reorganised docs

To address the user's request for "label all docs by date and chronological order":

- Create `docs/eval/stream-c-timeline.md` — chronological index linking all Stream C eval docs from 2026-05-06 (Stream B IAA) through 2026-05-10 (this work). Existing files are NOT renamed (preserves git history). New files use `YYYY-MM-DD-...` prefix.

---

## Build sequence

```
Stage 0 (recon + storage shim)  [foreground, no LLM]
   │
   ├── Stage 1 (extractor capture patch)  [foreground, no LLM]
   │   │
   │   └── Stage 2 (run extractor) ── £15–25 ── ~30min ──┐
   │                                                       │
   ├── Stage 3 (build tagger CLI)  [foreground, no LLM]    │
   │   │                                                   │
   │   └── Stage 4 (sample tagger) ── £1 ── 5min ──┐       │
   │                                                │       │
   │   └── Stage 5 (full tagger) ── £20–40 ── 3–6h ┴───────┤
   │                                                       │
   ├── Stage 6 (wire predict_all flag)  [foreground]       │
   │                                                       │
   └── Stage 7 (full ablation) ── £8 ── 30min–2h ──────────┘
                                                           │
                                          Stage 8 (report + commit + push)
```

Stages 0+1 can parallelise with Stage 3 (different files). Stages 2 and 4 are gates before larger LLM spends.

---

## Open questions to resolve during execution (do not pause for these)

1. **Proposition count.** Estimated ~50 propositions per case × 48 cases = ~2,400. Actual count comes from Stage 2's run; if it's >5,000, Stage 5 cost projects to £40+ and may need batching.
2. **Tagger prompt design.** Take inspiration from `factor_gold_annotation.py`'s system prompt but adapt for proposition→factor-ids classification (multi-label, not single-value). Likely simpler prompt than the case-text annotator.
3. **Tagger model choice.** Default to `gpt-5-mini` for cost — propositions are short text snippets (≤100 words each), classification task is easier than full case-text annotation. Save gpt-5 for cases where mini disagrees badly. Estimate based on 2,400 props × ~500 tokens/call × $0.30/M in: ~$0.36 for input + comparable output ≈ ~£0.60 for the full run with gpt-5-mini alone. Massive savings vs case-side. Reserve gpt-5 only if mini quality is poor (Gate 2).
4. **Idempotency seed.** Use proposition_id as the random seed for any LLM call deterministic; same proposition tags identically across reruns.
5. **Existing `factor_overlap` scoring uses set intersection** (`packages/llm_orchestrator/pipeline/factor_retrieval.py:293`) — so order of factor_ids doesn't matter, but length does (more matches = higher score). Keep the tagger conservative (only emit factor_ids the proposition clearly references) to avoid false-positive lift.

---

## Self-review (before declaring done)

- All 4 stages complete (extractor → tagger → wire → ablate)
- Pre-existing 1,830+ unit tests still pass
- New tests added: ≥4 for storage shim, ≥4 for tagger, ≥2 for predict_all wiring
- Sample tagger validated against positive-control fixture's 8 propositions (which already have correct factor_ids)
- Final ablation completes; multi-axis report written
- Branch pushed to `codex/stream-c-prediction-path-plan` (PR #37 picks up the new commits)
- Supervisor briefing has new §16 with proposition-backfill results
- Chronological index doc lives at `docs/eval/stream-c-timeline.md`
- Total spend documented in report; receipts ≤£100 cap

---

## Follow-up plan (will be written after Stage 8 — chronological order)

`docs/superpowers/plans/2026-05-11-stream-c-post-backfill-decision.md`

This follow-up plan won't be authored until the proposition-backfill ablation completes. It will branch on Gate 3's outcome:

- **If lift confirmed:** plan to expand the eval corpus from 48 → 150 cases, replicate against deposit pack (`housing.deposit.v1`), publish a thesis-defensible empirical chapter draft.
- **If no lift:** plan to investigate root causes (catalogue mismatch? model capability? domain mismatch?) and possibly pivot the thesis empirical chapter framing from "architecture lifts prediction" to "architecture is correct; corpus/catalogue prerequisites for lift are characterised here."
