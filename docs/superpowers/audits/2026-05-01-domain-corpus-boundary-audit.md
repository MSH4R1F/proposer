# Domain Corpus Boundary Audit — SHA-20 Phase 0

**Date:** 2026-05-01
**Author:** Claude Code (coordinator session, SHA-20 worktree)
**Branch:** `feature/sha-20-epic-multi-domain-architecture-expansion-adjacent-housing`
**Plan reference:** `docs/superpowers/plans/2026-05-01-sha-20-multi-domain-architecture-implementation.md` Phase 0
**Spec reference:** `docs/superpowers/specs/2026-05-01-multi-domain-architecture-expansion-design.md`
**Linear:** SHA-20 (epic), SHA-119 (taxonomy), SHA-120 (corpus/citation), SHA-121 (eval leakage), SHA-122 (gates)

---

## Purpose

Phase 0 of the SHA-20 plan requires proving what the current deposit/corpus baseline actually supports before we build domain-pluggable architecture on top of it. The plan's Phase 0 Blockers section calls out three unverified assumptions; this audit verifies them locally and decides the operational consequence.

This document is the gate that controls whether the `housing.deposit.v1` launch artifact may be marked passing.

---

## Findings

### 1. The deposit gold set does not exist locally

```
$ ls data/gold_standard/
README.md
```

There is no `data/gold_standard/housing_v1.jsonl`. Only the README and `.gitkeep` placeholder are tracked. The eval harness (`packages/eval/dataset.py`) loads from this exact path; calling `python -m eval.dataset audit data/gold_standard/housing_v1.jsonl --strict` will raise.

**Implication:** Any claim of "current deposit accuracy / Brier / calibration" produced from this checkout today is not reproducible. The deposit production launch gate must therefore fail closed until the file is restored or an explicit synthetic-fixture artifact is approved by Mohamed in writing.

### 2. The BAILII scrape contains zero deposit cases — and zero deposit keywords

`data/raw/bailii/scrape_summary.json`:

```json
{
  "total_cases_found": 8834,
  "deposit_cases": 0,
  "adjacent_cases": 2417,
  "other_cases": 6417
}
```

Recomputing the category distribution from `data/raw/bailii/master_index.json` (4,395 deduplicated cases):

| Category | Count |
|---|---|
| other | 3,192 |
| adjacent | 1,203 |
| deposit | 0 |

Across all 4,395 indexed cases, zero entries have any value in `deposit_keywords`.

The top `adjacent_keywords` are dominated by **rent repayment order** material, not deposit material:

| Keyword | Count |
|---|---|
| rent repayment order | 574 |
| assured shorthold tenancy | 320 |
| ast | 262 |
| improvement notice | 63 |
| rro | 36 |

**Implication:** The user-facing description "500+ deposit tribunal cases" is not currently supported by the local corpus. The corpus on disk is closer to a Property Chamber RRO + leasehold corpus. Two reasonable interpretations:

- **(a)** Deposit cases were intended to be sourced separately (deposit-scheme adjudication summaries, county court judgments) and the BAILII pipeline was always for adjacent housing. The deposit RAG namespace was historically populated from another path, not from `data/raw/bailii/deposit-cases/`. The empty `deposit-cases/` directory and `deposit_cases: 0` summary are consistent with that scraper never having a deposit source. Verifying this requires inspecting how the legacy `tribunal_cases` Chroma collection and `data/embeddings/bm25_index.pkl` were populated.
- **(b)** The scraper's deposit keyword list under-fired and real deposit-relevant cases sit inside `adjacent-cases/` and `other-cases/` mislabelled. There are no `deposit_keywords` matches in `master_index.json`, so this is unlikely to fix itself by relabelling alone — keyword dictionary changes would be needed.

Either way, the canonical deposit corpus must be re-stated in `housing.deposit.v1`'s `RetrievalNamespace` (corpus root, source publisher, and `corpus_version`) before any production launch artifact is signed.

### 3. RAG isolation is not enforceable yet

- `packages/rag_engine/vectorstore/chroma_store.py` supports `where={...}` metadata filters — Chroma can isolate by metadata, but only if metadata is populated.
- `packages/rag_engine/chunking/legal_chunker.py` and `DocumentChunk.to_chroma_metadata()` do not currently emit `domain_id`, `domain_family`, `forum`, `source_id`, `source_publisher`, `source_kind`, `corpus_version`, `decision_date`, or `law_effective_date`.
- `packages/rag_engine/retrieval/bm25_index.py` does not accept `filters=` or `excluded_source_ids=` arguments.

**Implication:** Two namespaces cannot safely coexist in one process today. Hybrid retrieval (Chroma + BM25) is unsafe for any namespace other than the legacy single deposit namespace. Phase 4 (SHA-60, SHA-120) is a prerequisite for any adjacent-housing or employment retrieval, and the work is real engineering, not configuration.

### 4. Target-source exclusion is not executable yet

`packages/eval/schema.py` has `source_pdf_sha256` but does **not** define:

- `target_source_id`
- `excluded_source_ids`
- `retrieval_namespace_id`
- `law_effective_date`
- `train_test_split`
- `source_publisher`
- `source_kind`
- `corpus_version`

The leakage controls described in Phase 7 (SHA-121) are aspirational at the schema level. There is no mechanism today that prevents a gold case's own source decision being retrieved as a "similar precedent" during eval. Any leaderboard number reported from the current harness over-claims.

### 5. Deposit non-protection is collapsed into deposit deduction

`packages/eval/issue_alignment.py` documents the alignment as:

```
- `deposit_non_protection` (eval) ↔ `deposit_protection` (orch)
```

`packages/llm_orchestrator/pipeline/output_assembler.py:42-72` then takes any prediction with `issue_type == IssueType.DEPOSIT_PROTECTION` and routes the predicted amount through `penalty_recovery`, which is added directly to `tenant_recovery` (the 1×–3× statutory penalty path under HA 2004 ss.213–215).

**Implication:** A deposit-deduction prediction (landlord wants to keep £X for cleaning/damage) and a deposit non-protection penalty (tenant wants 1×–3× the deposit because it was never protected) are two legally distinct matters with two different remedies, two different forums (deposit-scheme adjudication for the former, county court for the latter), and two different test sets. They are currently being scored as the same issue. Until they are split, no launch gate that mixes them is meaningfully calibrated.

---

## Decisions

### D1 — `housing.deposit.v1` is the compatibility baseline

It must:

- Default `domain_id` for all rows lacking one after the SHA-124 backfill.
- Open the legacy Chroma collection `tribunal_cases` and BM25 path `data/embeddings/bm25_index.pkl`.
- Carry `source_publishers: [bailii]` initially, with the understanding that the practical deposit corpus on disk is currently a **Property Chamber / leasehold + RRO corpus**, not a deposit-deduction corpus. Phase 4 ingestion must re-state this honestly.

### D2 — Production launch gate for `housing.deposit.v1` is fail-closed

Until at least one of the following holds:

- `data/gold_standard/housing_v1.jsonl` is restored to the working tree with at least 50 manually verified deposit-deduction cases.
- A signed gate artifact at `data/eval_artifacts/domain_gates/housing.deposit.v1.json` exists and references either the restored gold file or an explicitly approved synthetic-fixture artifact.

Engineering may continue building architecture; product must not publish accuracy/calibration/ablation numbers from the current local harness.

### D3 — Split `deposit_deduction` from `deposit_non_protection` before exposing either as "deposit"

Phase 6 (prompt packs) and Phase 7 (eval schema) must add explicit `matter_type` so the two flows do not silently share a penalty branch. Concretely:

- `housing.deposit.v1` `forums: [deposit_scheme_adjudication, county_court]` with `matter_types: [deposit_deduction, deposit_non_protection]`.
- `OutputAssembler` keeps a `DEPOSIT_PROTECTION` (non-protection penalty) branch only when `matter_type == deposit_non_protection`. Deposit-deduction predictions use the standard issue-by-issue recovery branch.
- Until this split lands, eval scores for "deposit" must not be macro-averaged across both matters.

### D4 — Property Chamber first slice is RRO-only

`housing.property_chamber.rro.v1` (not a broad `housing.property_chamber.v1`). The 574 RRO cases in `master_index.json` are the most coherent slice we already have on disk. Leasehold, rents, Tenant Fees Act, park homes, building safety, and broad regulatory appeals are explicitly out of the first slice (Phase 10 acceptance criteria).

### D5 — Employment first slice is `employment.unfair_dismissal.v1` only

Wage disputes route to unsupported/research capture. PII redaction (SHA-123) blocks anything beyond research ingestion.

### D6 — Deposit non-protection is unsupported until D3 lands

Public/beta gates for deposit non-protection remain disabled. A separate `matter_type=deposit_non_protection` gate artifact is required before re-enabling that path.

---

## Acceptance checklist (from Phase 0 of the plan)

- [x] `housing.deposit.v1` confirmed as compatibility baseline (D1).
- [x] `data/gold_standard/housing_v1.jsonl` confirmed missing locally; consequence is fail-closed production gate (D2).
- [x] `data/raw/bailii/scrape_summary.json` zero-deposit fact recorded; cross-checked against `master_index.json` (zero `deposit_keywords` matches across 4,395 cases).
- [x] HMF/RRO/non-protection mislabel audit performed: 574 RRO cases, 320 AST, 63 improvement notices, 36 RRO. No deposit-protection cases identified by current keyword lists. The `adjacent-cases/` bucket is functionally an RRO + AST corpus.
- [x] Product boundary decided: deposit deduction and deposit non-protection are explicitly split (D3); only deposit deduction is on the public path until corpus and split land.
- [x] `deposit_deduction` ↔ `deposit_non_protection` split queued for Phase 6/7 (D3).
- [x] Property Chamber first slice = `housing.property_chamber.rro.v1` only (D4).
- [x] Employment first slice = `employment.unfair_dismissal.v1` only (D5).
- [x] Deposit non-protection unsupported until corpus/split verified (D6).
- [ ] Baseline test results recorded — deferred to subagent runs in Phases 1–3, will be linked back to SHA-20 in the Linear comment after each phase commits.
- [x] Dirty/unrelated files in the main worktree (`docs/API_DOCUMENTATION 2.md` etc.) are not being touched by this branch.
- [x] Plan does not assume current local deposit accuracy is publishable.

Linking to SHA-20 happens after this commits and the worktree is pushed.

---

## Out of scope for this audit

- Restoring `housing_v1.jsonl`. That is a corpus-team task tracked under SHA-120 / SHA-121.
- Re-running the BAILII scraper with a wider deposit keyword dictionary. Tracked under SHA-120.
- Deciding whether to re-source deposit-protection cases from non-BAILII publishers (deposit-scheme adjudication summaries, county-court judgments). Tracked under SHA-120.

---

## Stop conditions surfaced

The plan's "Stop Conditions" section already requires pausing if the existing deposit eval or API contract regresses. This audit surfaces one additional concrete one for SHA-20 implementers:

> If a Phase ≥ 6 task would publicly route a "deposit" prediction without distinguishing matter_type ∈ {deposit_deduction, deposit_non_protection}, pause and refer back to D3.

---

## Next actions (immediately after this commit)

1. Phase 1 (SHA-59, SHA-119): build `packages/domain_core` with the four domain YAMLs. The deposit YAML must encode D1, and explicitly mark `matter_types: [deposit_deduction, deposit_non_protection]` so the split can be enforced downstream.
2. Phase 2 (SHA-124): two-revision Alembic migration. Backfill defaults `domain_id=housing.deposit.v1`, `matter_types=[]`, leave `forum` nullable per the plan.
3. Phase 3: thread `domain_id` through runtime as a no-op default for deposit.
4. Update SHA-20 in Linear with this audit URL after the worktree is pushed; copy D1–D6 into the SHA-20 description as the operational baseline.
