# Employment Tribunal Vertical — Pipeline Design (`employment.et.unfair_dismissal.v1`)

**Date:** 2026-05-13
**Author:** Coordinator (multi-window orchestration)
**Status:** Draft → awaiting user review
**Parent epic:** [SHA-20 (Done)](https://linear.app/sharifbuilders/issue/SHA-20)
**Decomposes:** [SHA-65](https://linear.app/sharifbuilders/issue/SHA-65) into six ordered child tickets
**Authoritative architecture spec:** [`docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md`](./2026-05-06-factor-proposition-kg-controlled-cbr-rag.md)
**Boundary audit referenced:** [`docs/superpowers/audits/2026-05-01-domain-corpus-boundary-audit.md`](../audits/2026-05-01-domain-corpus-boundary-audit.md) (decision **D5** — unfair-dismissal-only for v1)

## 1. Goal

Build an end-to-end vertical for **UK Employment Tribunal unfair-dismissal decisions** that mirrors the housing pipeline pattern (scraper → 30-doc pilot → 1000-doc full scrape → 50-case stratified gold → factor catalog → cross-domain evals). The vertical exists to:

1. **Stress-test cross-domain generalisation** of the factor-proposition-KG + CBR-RAG architecture (thesis RQ).
2. **Provide a non-housing corpus** for ablation studies in the thesis Evaluation chapter.
3. **Keep the platform research-stage** behind feature flags until SHA-66 (deterministic award calculator) and SHA-123 (PII redaction) are signed.

Out of scope: discrimination, redundancy, working-time, unlawful deduction of wages, whistleblowing. These remain in [`docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md`](./2026-05-06-factor-proposition-kg-controlled-cbr-rag.md) §13 as later domains.

## 2. Why the housing pattern, not a 1000-shot

The housing pipeline taught the team two lessons that this design encodes as gates:

- **SHA-126/137 (RRO):** corpus rarity (~0.1% of FTT(PC) listings) was not discovered until the live scrape. The fix was to pivot to MNR ([SHA-138](https://linear.app/sharifbuilders/issue/SHA-138)). Lesson: a 30-doc pilot must precede the bulk scrape.
- **Stream B housing factor IAA:** 13/15 factors became gate-countable only after double-pass adjudication. Lesson: gold-set design and factor catalog are not parallelisable with the bulk scrape — they need a small validated sample first.

Therefore the 1000-case target is a **downstream** ticket gated on a 30-doc pilot, not the first ticket.

## 3. Architecture (reuses existing components)

```
gov.uk/employment-tribunal-decisions
        │
        ▼  (SHA-65a)
scripts/scrapers/employment_tribunal/   ──── OGL v3.0 attribution
        │
        ▼  (SHA-65b — 30-doc pilot)
data/raw/employment/<jurisdiction-code>/
        │
        ▼  (SHA-65c — 1000-doc scrape, gated on 65b passing)
employment_unfair_dismissal_v1   ←── RetrievalNamespace (already declared in
        │                            packages/domain_core/domains/employment.unfair_dismissal.v1.yaml)
        ▼  (SHA-65d)
data/gold_standard/employment_unfair_dismissal_v1.jsonl   (≥50 reviewed-gold rows)
        │
        ▼  (SHA-65e)
packages/domain_packs/employment_unfair_dismissal_v1/factors/   (factor catalog + extractor protocol)
        │
        ▼  (SHA-65f)
data/eval_artifacts/.../employment.et.unfair_dismissal.v1/   (Brier, ECE, F1, ablation report)
```

Everything below the scraper is existing code reused via the per-domain abstractions ([SHA-59](https://linear.app/sharifbuilders/issue/SHA-59) registry, [SHA-60](https://linear.app/sharifbuilders/issue/SHA-60) RAG namespacing, [SHA-116](https://linear.app/sharifbuilders/issue/SHA-116) eval harness).

### 3.1 Domain ID note (must be resolved in SHA-65a)

`packages/domain_core/domains/employment.unfair_dismissal.v1.yaml` already exists and uses the legacy domain ID. The authoritative spec ([2026-05-06](./2026-05-06-factor-proposition-kg-controlled-cbr-rag.md)) calls for `employment.et.unfair_dismissal.v1`. Per that spec's implementation note: keep the legacy ID as a compatibility alias and introduce the new namespaced ID in a v2/domain-pack migration with explicit artifact mapping. **SHA-65a must NOT rename in-place in the same PR as the scraper.**

## 4. Child-ticket decomposition

Each child ticket is one PR, one worktree window, one Codex sparring loop.

| ID | Title | Estimate | Depends on | DoD summary |
|---|---|---|---|---|
| **SHA-65a** | ET scraper code (`scripts/scrapers/employment_tribunal/`) | 5 pts | — | Module mirrors `housing_ombudsman/` layout: `config.py`, `downloader.py`, `filter.py` (unfair-dismissal jurisdiction code filter), `models.py`, `parsers.py`, `progress.py`, `to_source_document.py`, `tests/`. **No live scrape.** Unit tests against fixture HTML. PII redactor wired (SHA-123 prereq). OGL v3.0 attribution line in `models.py` and `data/raw/employment/LICENCE.md`. |
| **SHA-65b** | Live 30-doc pilot (unfair dismissal) | 2 pts | 65a | Mirrors SHA-136. Run scraper with `--max-keep 30 --jurisdiction-code unfair_dismissal --rps 0.5`. Validate: (i) parser extracts case name, decision date, jurisdiction code, outcome paragraph; (ii) PII redaction removes claimant name, postcode, email, phone, NI number; (iii) dedupe by case ID; (iv) source-document JSON conforms to `to_source_document` schema; (v) manual spot-check 5 docs for parser fidelity. Pilot manifest committed to `data/eval_artifacts/pilots/employment_et_unfair_dismissal_pilot_30_<date>.jsonl`. |
| **SHA-65c** | 1000-doc full scrape into namespace | 5 pts | 65b passing | Run scrape with `--max-keep 1000 --jurisdiction-code unfair_dismissal --years 2019-2024 --rps 0.5`. Ingest into `employment_unfair_dismissal_v1` retrieval namespace (vector + BM25). Manifest at `data/raw/employment/manifests/employment_et_unfair_dismissal_<date>.jsonl`. Corpus version recorded as `research_seed_2026_05` to match domain spec. Leakage controls per [SHA-121](https://linear.app/sharifbuilders/issue/SHA-121). Temporal split: 2019-2022 train, 2023-2024 test. |
| **SHA-65d** | Stratified 50-case gold set | 5 pts | 65c | Mirrors SHA-127. Outputs to `data/gold_standard/employment_unfair_dismissal_v1.jsonl`. Stratification: by outcome (claim_succeeded / claim_dismissed / partial), by fairness ground (conduct / capability / redundancy / SOSR), by year. Each row uses existing `GoldCase` schema with `domain_id="employment.et.unfair_dismissal.v1"`, `forum="employment_tribunal"`, `source_publisher="govuk"`. LLM-panel double-pass labelling (per memory rule: LLM panel substitutes paralegal review for thesis-pace solo work) + mandatory human review of `claim_types`, `ground_truth_outcome.overall_winner`, `ground_truth_outcome.total_awarded_gbp`, `matter_type`. |
| **SHA-65e** | Factor catalog + extractor for unfair dismissal | 5 pts | 65d | Mirrors housing Stream B. Factor catalog at `packages/domain_packs/employment_unfair_dismissal_v1/factors/catalog.yaml` covering: fair-reason category (ERA 1996 s98(1)-(2)), reasonableness (s98(4)), Acas Code compliance, procedural fairness (notice, hearing, appeal), Polkey deduction triggers, contributory fault. Extractor protocol producing `FactorAssertion` rows with span provenance. LLM panel review + double-pass IAA target ≥0.6 agreement on ≥10 of the catalog factors. Comparative report at `docs/eval/extractor_f1_reports/employment.et.unfair_dismissal.v1-<date>-gold-iaa-comparative.md`. |
| **SHA-65f** | Cross-domain ablation evals | 3 pts | 65e, [SHA-116](https://linear.app/sharifbuilders/issue/SHA-116) | Run prediction harness against ET test split. Metrics: Brier on win-probability, ECE, F1 on factor extraction, MAE on award amount (gated on SHA-66 calculator), retrieval P@5 / nDCG@10. Output cross-domain ablation table (housing vs employment) for thesis Evaluation chapter. Per-domain dashboard entry. Forum-mixing leakage check: assert no `housing_ombudsman` or `first_tier_property_chamber` documents appear in ET retrieval results. |

**Total:** 25 pts (matches SHA-65's original 8-pt estimate being unrealistic for a complete vertical — the original ticket should be downgraded to "epic-only" and the points moved to the children).

## 5. Data flow and contracts

### 5.1 Source

`https://www.gov.uk/employment-tribunal-decisions`. Each decision is a static HTML page with PDF attachment(s). Licence is **OGL v3.0** (Open Government Licence). Attribution string lives in `data/raw/employment/LICENCE.md` and on every persisted record's `source_license` field.

### 5.2 Filtering

Pilot and full scrape filter by `jurisdiction_code` matching "Unfair Dismissal" tag on the listing pages. Reject:

- combined claims where unfair dismissal is not the lead head
- strike-out or jurisdiction-only decisions (no merits ruling)
- decisions where the respondent did not appear (default judgments — too lopsided for outcome modelling)

The filter rules live in `scripts/scrapers/employment_tribunal/filter.py` and are unit-tested in 65a.

### 5.3 Gold record schema

Reuse `GoldCase` (already used by housing). Required fields per [SHA-20](https://linear.app/sharifbuilders/issue/SHA-20) Phase 7:

- `domain_id = "employment.et.unfair_dismissal.v1"`
- `forum = "employment_tribunal"`
- `source_publisher = "govuk"`
- `source_kind = "case_decision"`
- `matter_type = "unfair_dismissal"`
- `retrieval_namespace_id = "employment_unfair_dismissal_v1"`
- `corpus_version = "research_seed_2026_05"`
- `train_test_split ∈ {"train", "test"}` per temporal split
- `labeling_provenance` with `inter_model_agreement_rate`, `mandatory_review_completed_at`, `field_provenance`

### 5.4 Factor catalog (unfair dismissal)

Initial catalog covers s98 ERA 1996 framework. Candidate factors (final list refined in 65e):

1. **Fair reason established (s98(1)-(2))** — categorical: conduct / capability / redundancy / illegality / SOSR / none. (Note: "redundancy" here is a dismissal-reason category under s98, not the separately-scoped `employment.et.redundancy.v1` domain. A dismissal labelled "redundancy" by the employer can still be unfair if the s98(4) reasonableness test fails — that is exactly what this factor measures.)
2. **Reasonableness of decision (s98(4))** — bool
3. **Investigation adequate** — bool
4. **Hearing held before dismissal** — bool
5. **Right of appeal offered** — bool
6. **Right of appeal exercised** — bool
7. **Acas Code followed** — bool
8. **Polkey deduction applied** — bool with % range
9. **Contributory fault deduction** — bool with % range
10. **Reinstatement / re-engagement sought** — bool
11. **Length of service ≥ 2 years (qualifying period)** — bool
12. **Time limit met (ACAS EC + 3 months)** — bool
13. **Compensation awarded** — bool + amount band
14. **Reason genuinely held** — bool (relevant to capability/SOSR)
15. **Band of reasonable responses applied** — bool

Target: ≥10 gate-countable factors after IAA. Mirrors the housing 13-of-15 result.

## 6. Sequencing and dispatch

### 6.1 Critical-path question — UNRESOLVED

[SHA-67](https://linear.app/sharifbuilders/issue/SHA-67) (Implementation chapter, Urgent, due 2026-05-10) is overdue. The coordinator must decide:

- **Option α:** ET work runs **after** SHA-67 chapter is delivered. ET evals (65f) feed the *Evaluation* chapter (SHA-21 children) but not Implementation.
- **Option β:** SHA-65a–c run **in parallel** with SHA-67 in different worktree windows (scraping is independent of chapter prose). SHA-65d-f wait for chapter ship.
- **Option γ:** ET work is **deferred** until after thesis submission entirely.

**Recommended:** Option β. Scrapers do not block writing because they reuse the housing pattern, and a parallel worker window has spare capacity per [`docs/ORCHESTRATION.md`](../../ORCHESTRATION.md). Decision needs user sign-off.

### 6.2 Worktree assignment

Per [`docs/ORCHESTRATION.md`](../../ORCHESTRATION.md), the four parallel windows have file-ownership rules. SHA-65a–c touch only `scripts/scrapers/` and `data/raw/employment/`, which is currently uncontested — any window with capacity can pick them up. SHA-65d–f touch `scripts/eval/` and `packages/domain_packs/`, where ownership conflicts are likelier; coordinator must serialise.

### 6.3 Launch prompt

A launch prompt for SHA-65a will be added to [`docs/prompts/`](../../prompts/) after Linear tickets are created. It will follow the same shape as existing prompts: WORKTREE.md path, ticket link, success criteria, Codex sparring expectation.

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Live scrape reveals corpus rarity for unfair-dismissal-only (cf. RRO at 0.1%) | SHA-65b 30-doc pilot is the gate. If pilot fails to fill 30 docs, escalate before SHA-65c. |
| OGL v3.0 attribution miss | Attribution string committed in `LICENCE.md` and asserted as a unit test in 65a. |
| PII redaction regression on ET data (different fields than housing) | SHA-65b adds 5-doc manual spot-check + automated check for postcode/email/phone/NI patterns. PR blocked if any leak found. |
| Forum leakage in retrieval (ET case retrieved for housing query) | SHA-65f explicit leakage assertion. Per-domain RAG namespacing ([SHA-60](https://linear.app/sharifbuilders/issue/SHA-60)) is the structural defence. |
| Domain ID rename breaks artifacts | SHA-65a keeps legacy `employment.unfair_dismissal.v1` as compatibility alias; new ID introduced separately. |
| Factor catalog IAA fails to clear 10/15 gate | Same fallback as housing Stream B — narrow gate-countable set, document non-gate factors as exploratory. |
| Award amount prediction blocked by missing SHA-66 calculator | SHA-65f reports MAE only if SHA-66 is `Done`; otherwise reports win-probability metrics and flags the gap. |

## 8. Open questions

1. **SHA-67 sequencing (above).** Awaiting user decision.
2. **Years to scrape.** Default proposed: 2019-2024 (matches housing temporal split). User to confirm — earlier coverage would shift train/test cuts.
3. **Reinstatement/re-engagement weight.** These are remedies the housing pipeline does not have an analogue for. Should they be in the per-issue prediction output or only in award-amount calculation? Recommend: predict only the binary remedy-granted, defer amount to SHA-66.
4. **GOV.UK rate limiting.** Housing Ombudsman scrape used 1.0 RPS. ET listing pages are static and lighter — propose 0.5 RPS to be conservative. User to confirm.

## 9. Definition of done for this design phase

- [x] Design committed to `docs/superpowers/specs/2026-05-13-employment-tribunal-vertical-design.md`
- [ ] User reviews and approves design
- [ ] Open question §8.1 (SHA-67 sequencing) resolved
- [ ] Linear tickets SHA-65a..f created/updated and linked to SHA-65
- [ ] Launch prompt for SHA-65a added to `docs/prompts/`
- [ ] First worktree window briefed
