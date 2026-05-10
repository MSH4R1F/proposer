# Stream C — Post-Backfill Decision Plan (2026-05-10)

> **Predecessors:** [`2026-05-07-stream-c-recovery-sprint.md`](2026-05-07-stream-c-recovery-sprint.md) (recovery patches) → [`2026-05-10-stream-c-proposition-backfill.md`](2026-05-10-stream-c-proposition-backfill.md) (full factor + proposition backfill).

**Empirical state after 3 ablation rounds** (see [`docs/eval/2026-05-10-stream-c-full-backfill.md`](../../eval/2026-05-10-stream-c-full-backfill.md)):
- Recovery (no factor data): hybrid 0.917, rag_only 0.896.
- Case-backfill: hybrid 0.875, rag_only 0.896.
- **Full backfill (factors + propositions): hybrid 0.917, rag_only 0.917.**

The KG gate fails on 48/48 cases for **6 distinct documented reasons** (`evidence_backed_factor_count`, `dated_event_count`, `issue_count`, `outcome_or_remedy_candidate_count`, `unsupported_factor_rate`, `source_span_coverage`). `graph_quality_score=0.0` everywhere. The architectural lift is currently **unmeasurable**.

---

## What this plan does

Three branches, depending on what you (Mohamed) want from the thesis empirical chapter:

1. **Branch A — Architectural Prerequisites Study (LOW cost, defensible thesis claim).** Accept the negative-result framing. Write the empirical chapter as "we built the architecture; we characterised the data prerequisites; we present them as future work for a richer extractor stack." Cost: ~£0 LLM, ~6h writing. Time-to-thesis-draft: 1-2 days.

2. **Branch B — Build Stream D (Evidence-Chain Extractors) (HIGH cost, full empirical lift).** Implement the 4 missing extractors (EvidenceSpan, Event, IssueClaim, OutcomeCandidate) so the gate fires. Re-run the full ablation. Cost: ~£60-160 LLM + 5-10 days engineering. Time-to-thesis-draft: 2-3 weeks.

3. **Branch C — Oracle-N Hand-Curated Study (LOW cost, narrow but cleanest signal).** Build a 5-case hand-curated set in the style of the [positive-control fixture](../../../data/eval_artifacts/positive_control/housing_repairs_social_v1_one_case_kg/) — populating ALL the architectural node types that the gate requires (EvidenceSpan, Event, IssueClaim, OutcomeCandidate). Run ablation against just those 5 cases. Cost: ~£3 LLM + 6-10h hand-annotation. Time-to-result: 1-2 days.

Each branch is a complete plan. Pick one (or stage them: C → B if C works → A if not).

---

## Branch A — Architectural Prerequisites Study

**Goal:** Convert the three-round empirical journey into a defensible thesis chapter that doesn't claim architectural lift.

**Thesis claim** (cleanest version):

> "We built and shipped a factor-proposition KG-controlled CBR-RAG architecture with cite-or-abstain validation. Three rounds of empirical evaluation on 48 housing.repairs_social.v1 gold cases — under no factor data, partial backfill, and full factor + proposition backfill — show that the architecture's design decision D5 (graceful fallback) is empirically robust under any data condition (zero abstention, no false predictions). The graph quality gate is the binding constraint on KG-path activation, requiring structured node types beyond factor-and-proposition tagging. We characterise the architectural prerequisites and present them as scoped future work."

### Tasks

| # | Task | Effort |
|---|---|---|
| A.1 | Write empirical chapter section: 3-round ablation table + multi-axis comparison + KG-gate failure analysis | 3h |
| A.2 | Write contribution chapter section: D5 graceful-fallback empirically validated; positive-control test as architectural correctness proof | 1h |
| A.3 | Write future-work chapter section: Stream D scoping (4 extractors needed, cost estimates, ordering) | 1h |
| A.4 | Update supervisor briefing with all 3 ablations + this decision plan | 30min |
| A.5 | Submit thesis empirical chapter draft to supervisor | — |

**Deliverable:** thesis empirical chapter draft, ~5,000 words. No new code, no new LLM spend.

**Risk:** supervisor pushes back on "we built it but didn't measure lift." Mitigation: the cite-or-abstain + graceful-fallback contributions are independently defensible; the architectural-prerequisites characterisation is a real finding (gate criteria revealed empirically).

### Decision criterion

Pick A if:
- Thesis deadline is within 2 weeks
- Supervisor accepts the negative-result framing as a contribution
- Risk tolerance for "no measured lift" is OK

---

## Branch B — Build Stream D (Evidence-Chain Extractors)

**Goal:** Make the KG gate actually fire by populating the 4 missing structured node types.

### Pieces to build

The gate requires:
- `evidence_backed_factor_count ≥ 5` → need `EvidenceSpan` typed nodes + linkage from `FactorAssertion.supported_by[]`
- `dated_event_count ≥ 2` → need `Event` extractor (date, type, description)
- `issue_count ≥ 1` → need `IssueClaim` extractor
- `outcome_or_remedy_candidate_count ≥ 1` → need `OutcomeCandidate` / `RemedyCandidate` extractor
- `unsupported_factor_rate ≤ 0.30` → addressed by EvidenceSpan extractor + linker
- `source_span_coverage ≥ 0.80` → addressed by EvidenceSpan extractor

### Build sequence

| # | Stage | Detail | Eng hours | LLM (est.) |
|---|---|---|---|---|
| B.1 | Recon: read `legal_core` Pydantic models for EvidenceSpan, Event, IssueClaim, OutcomeCandidate, RemedyCandidate. Read `graph_quality_gate.yaml` thresholds | 2h | £0 |
| B.2 | EvidenceSpan extractor CLI (analogous to `factor_gold_annotation.py`). Reads case raw text, identifies typed evidence with stable IDs + offsets. Outputs JSONL. Tests | 1d | — |
| B.3 | Run EvidenceSpan extractor (50 cases × ~10 spans/case = ~500 spans) | — | £15-25 |
| B.4 | Factor-evidence linker. For each FactorAssertion in the case sidecar, pick the matching EvidenceSpan IDs, populate `supported_by[]` and `source_span_refs[]`. No LLM (rule-based with text-similarity heuristic). Tests | 4h | £0 |
| B.5 | Event extractor CLI. Identifies dated events. Outputs JSONL. Tests | 1d | — |
| B.6 | Run Event extractor | — | £10-20 |
| B.7 | IssueClaim + OutcomeCandidate extractor (combined CLI). Tests | 1d | — |
| B.8 | Run IssueClaim/OutcomeCandidate extractor | — | £15-30 |
| B.9 | Wire all 4 new artifacts into the engine (Knowledge graph hydration step). Each goes via a sidecar JSON keyed by case_id (consistent with case-side backfill pattern) | 1d | £0 |
| B.10 | Re-run 4-mode ablation against fully-prerequisited corpus | — | £8 |
| B.11 | Write report `2026-05-XX-stream-c-stream-d-results.md` | 4h | £0 |
| **Total** | | | **5-10 days** | **£48-83** |

### Decision gate after B.10

| KG gate firing rate | Hybrid lift over rag_only | Action |
|---|---|---|
| `kg_used=True` ≥ 80% AND hybrid +3pp or more | Strong positive — write thesis claim "architecture lifts when prerequisites met" | |
| `kg_used=True` ≥ 50% AND hybrid +1 to +2pp | Modest lift, within CI noise — multi-axis interpretation | |
| `kg_used=True` ≥ 50% AND hybrid flat or negative | Architecture activates but doesn't lift on this corpus — probably class-imbalance pollution | |
| `kg_used=True` < 50% | More gate criteria not met — debug specific failures | |

### Decision criterion

Pick B if:
- Thesis deadline ≥ 4 weeks away
- Funding for £50-80 LLM is available
- The "negative result" framing of Branch A isn't acceptable

---

## Branch C — Oracle-N Hand-Curated Study

**Goal:** Test whether the architecture lifts under *perfect* data conditions on a small N. Cheapest path to a clean signal.

### What "perfect" means

Following the [positive-control fixture pattern](../../../data/eval_artifacts/positive_control/housing_repairs_social_v1_one_case_kg/), each case gets:
- Full case text (already on disk)
- 5-10 hand-written FactorAssertions with `supported_by` evidence-span IDs populated
- 5-10 hand-written EvidenceSpan typed nodes (text quote + page + paragraph + offsets)
- 2-4 hand-written Event nodes (dated, typed)
- 1-3 hand-written IssueClaim nodes
- 1-3 hand-written OutcomeCandidate / RemedyCandidate nodes
- 5-10 hand-written Propositions with factor_ids + outcome_component_ids

Total per case: ~30-50 nodes hand-built. ~1-2 hours per case for an annotator who knows the catalogue.

### Build sequence

| # | Stage | Effort | LLM |
|---|---|---|---|
| C.1 | Pick 5 cases from strict_clean that are "diverse" (different determinations, mixes of factors) | 30min | £0 |
| C.2 | Build a structured worksheet (Markdown checklists, one per case, with prompts for each node type) | 2h | £0 |
| C.3 | Hand-annotate the 5 cases against the worksheet. (You.) | 6-10h | £0 |
| C.4 | Promote worksheet → sidecar JSONs (case factor_assertions, EvidenceSpan, Event, IssueClaim, OutcomeCandidate, Propositions) via small one-off promoter scripts | 4h | £0 |
| C.5 | Run the 4-mode ablation against just those 5 cases | 30min | £1 |
| C.6 | Write report `2026-05-XX-stream-c-oracle-5-results.md` | 2h | £0 |
| **Total** | | **~14-20h (mostly your annotation)** | **£1** |

### Decision gate after C.5

| KG gate fires? | Hybrid lift? | Interpretation |
|---|---|---|
| Yes ≥ 4/5 cases | Hybrid lifts substantially over rag_only on these 5 | Architecture works when data is right; Branch B is justified |
| Yes ≥ 4/5 cases | Hybrid flat or worse | Architecture doesn't actually help on this corpus even with perfect data; Branch A is the honest answer |
| No, gate still fails | — | Even perfect data doesn't trip the gate; gate thresholds may be too strict for n=5 OR there's a real wiring bug; investigate before more spending |

### Decision criterion

Pick C if:
- You have 1-2 days of careful annotation time
- You want a clean answer cheaply before committing to Branch B
- You're willing to accept the small-N narrowness as a caveat

C is the **strongly recommended next step** if Branch A's "negative result" framing isn't satisfactory and Branch B's £50-80 + 5-10 days isn't yet justified. C is the cheapest empirical disambiguation.

---

## Branching strategy

Recommended sequence:

```
Today (2026-05-10): Branch C (Oracle-5)
  │
  └── if hybrid lifts cleanly on Oracle-5:
       │
       └── 2026-05-11+ : Branch B (Stream D extractors) on the full corpus
                          │
                          └── thesis claim: "architecture lifts when prerequisites met; we built the prerequisites"
  │
  └── if hybrid doesn't lift on Oracle-5:
       │
       └── 2026-05-11+ : Branch A (architectural prerequisites study writeup)
                          │
                          └── thesis claim: "architecture is correct; corpus / catalogue prerequisites for measurable lift are
                                             characterised here; Stream D shows the path forward"
```

This sequence makes Branch C the first branchpoint at minimal cost (~£1 + 1-2 days). Either outcome dictates the next move clearly.

---

## What I'd recommend (Mohamed's framing)

You're balancing thesis deadline pressure against the strength of the empirical chapter. The current state is:
- **3 ablations done**, totalling ~£40 LLM + ~3 days engineering.
- **No measurable architectural lift** detected on the 48-case corpus across 3 distinct data conditions.
- **Architecture itself is validated** by the positive-control test (smoke test in `test_positive_control_kg_smoke.py`).
- **Tooling is shipped and committed** (PR #37 has all of it).

The thesis can ship right now under Branch A — and the chapter would be honest, defensible, and represent real engineering work. The contribution is the architecture + the cite-or-abstain framework + the graceful-fallback property + the empirical map of prerequisites.

If you have 1-2 spare days, Branch C is high-value: it answers the "would it lift if data were perfect?" question for £1 and gives you either ammunition for Branch B (commit £80 + 2 weeks) or confidence in Branch A (write the thesis as is).

Branch B is only worth it if Branch C says yes AND you have ≥4 weeks before submission.

---

## Open questions you should decide

1. **Thesis submission target date?** This dictates which branch is feasible.
2. **Supervisor's tolerance for "negative result with characterised prerequisites"?** Branch A depends on this. Send them the [full-backfill report](../../eval/2026-05-10-stream-c-full-backfill.md) before deciding.
3. **Annotation bandwidth?** Branch C needs 1-2 days of your hands-on time. If you're more constrained, Branch B is the next-cheapest option.

---

## Self-review (before declaring this decision-plan complete)

- 3 branches with concrete tasks + effort + cost
- Decision gates per branch
- Branching strategy (which to do first)
- Tied back to thesis-level concerns
- All cross-references to predecessor reports/plans intact
