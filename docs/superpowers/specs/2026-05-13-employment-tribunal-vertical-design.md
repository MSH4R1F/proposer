# Employment Tribunal Vertical Design

Domain target: `employment.et.unfair_dismissal.v1`

**Date:** 2026-05-13
**Status:** Reviewed draft - implementation gated
**Parent epic:** [SHA-20 (Done)](https://linear.app/sharifbuilders/issue/SHA-20)
**Decomposes:** [SHA-65](https://linear.app/sharifbuilders/issue/SHA-65) into one schema-readiness gate plus six implementation tickets
**Authoritative architecture spec:** [`docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md`](./2026-05-06-factor-proposition-kg-controlled-cbr-rag.md)
**Boundary audit referenced:** [`docs/superpowers/audits/2026-05-01-domain-corpus-boundary-audit.md`](../audits/2026-05-01-domain-corpus-boundary-audit.md) (decision **D5** - unfair-dismissal-only for v1)

## 0. Review Summary

This revision keeps the original thesis goal but tightens the implementation plan around three blockers:

1. `GoldCase` is not currently employment-ready. `ClaimType`, `PartyRole`, and winner/determination semantics are still housing-shaped, so the ET gold set must be gated on a small schema/adapter readiness ticket before SHA-65d.
2. GOV.UK's "Unfair Dismissal" filter is a discovery signal, not a guarantee that the decision is a clean merits unfair-dismissal judgment. The scraper needs a two-stage filter: category discovery first, merits-quality filtering second.
3. Award metrics should be reported only after an employment-specific award/remedy model exists. Unfair dismissal has basic award, compensatory award, deductions, uplifts, reinstatement, and re-engagement. Treating all remedies as one housing-style amount would create misleading evaluation results.

External facts checked on 2026-05-13:

- [GOV.UK Employment Tribunal decisions](https://www.gov.uk/employment-tribunal-decisions) publishes England, Wales, and Scotland ET decisions from February 2017 onwards and exposes a "Jurisdiction code" filter including "Unfair Dismissal".
- [Filtered GOV.UK unfair dismissal page](https://www.gov.uk/employment-tribunal-decisions?tribunal_decision_categories=unfair-dismissal) returns many current unfair-dismissal-labelled results, so the pilot is primarily a parser/quality gate, not a corpus-rarity gate.
- [GOV.UK reuse terms](https://www.gov.uk/help/reuse-govuk-content) state GOV.UK content is available under OGL v3.0 unless otherwise stated; the scraper must still persist the per-source licence it observes.
- [Acas unfair dismissal guidance](https://www.acas.org.uk/dismissals/unfair-dismissal) confirms the current general two-year service framing and notes the announced Employment Rights Act 2025 change is expected in January 2027 but is not yet law.
- [Acas dismissal-type guidance](https://www.acas.org.uk/dismissals/types-of-dismissal) summarises the potentially fair reasons: conduct, capability, redundancy, legal reason, and some other substantial reason.

## 1. Goal

Build an end-to-end research vertical for **Great Britain Employment Tribunal unfair-dismissal decisions** that mirrors the housing pattern:

```text
scraper -> 30-doc pilot -> 1000-doc corpus -> 50-case reviewed gold set
        -> factor catalog -> cross-domain ablation
```

The vertical exists to:

1. Stress-test cross-domain generalisation of the factor-proposition-KG plus CBR-RAG architecture.
2. Provide a non-housing corpus for the thesis Evaluation chapter.
3. Keep employment functionality research-only behind feature flags until privacy, schema, and award-calculation gates are signed off.

Out of scope for v1: discrimination, redundancy-as-a-standalone-domain, working-time, unlawful deduction of wages, whistleblowing, and Employment Appeal Tribunal authority modelling. A dismissal may still have a "redundancy" reason inside the unfair-dismissal framework; that is allowed only when the unfair-dismissal merits issue is the lead issue being modelled.

## 2. Why Not Start With a 1000-Case Scrape

The housing pipeline produced two lessons that this design turns into gates:

- **SHA-126/137 (RRO):** corpus availability and filter quality were only understood after a live pilot. ET unfair dismissal appears abundant, but the ratio of clean merits judgments to preliminary, strike-out, withdrawal, combined-claim, default, or remedy-only decisions still needs measurement.
- **Stream B housing factor IAA:** factors became gate-countable only after a validated sample and adjudication loop. The ET factor catalog should be derived from a small reviewed sample, not invented before seeing the source-document shape.

Therefore the 1000-case scrape is downstream of the 30-doc pilot, and the 50-case gold set is downstream of a schema-readiness gate.

## 3. Architecture

```text
gov.uk/employment-tribunal-decisions
        |
        v  (SHA-65a)
scripts/scrapers/employment_tribunal/
        |
        v  (SHA-65b - 30-doc pilot)
data/raw/employment/
        |
        v  (SHA-65c - gated 1000-doc corpus)
employment_unfair_dismissal_v1 retrieval namespace
        |
        v  (SHA-65-0 + SHA-65d)
data/gold_standard/employment_unfair_dismissal_v1.jsonl
        |
        v  (SHA-65e)
packages/domain_packs/employment/unfair_dismissal/
        |
        v  (SHA-65f)
cross-domain ablation report and dashboard entry
```

Everything below the scraper should reuse the domain abstractions from SHA-59, SHA-60, and SHA-116 wherever possible. The exception is the gold/eval schema: that contract is not employment-ready yet and must not be assumed.

### 3.1 Domain ID Note

The repo currently has `packages/domain_core/domains/employment_unfair_dismissal_v1.yaml` with:

```yaml
id: employment.unfair_dismissal.v1
retrieval_namespaces:
  - namespace_id: employment_unfair_dismissal_v1
```

The newer architecture spec names the target domain `employment.et.unfair_dismissal.v1`. Do not rename the YAML in the scraper PR. Treat `employment.unfair_dismissal.v1` as the compatibility ID and introduce the namespaced ID through a separate migration with explicit artifact mapping.

## 4. Tickets

Each row is intended to become one PR. The schema gate is listed first because it determines whether SHA-65d can emit valid `GoldCase` rows.

| ID | Title | Estimate | Depends on | DoD summary |
|---|---:|---:|---|---|
| **SHA-65-0** | Employment gold-schema readiness gate | 2 pts | - | Decide whether ET uses an extended `GoldCase` or a domain-specific adapter. Cover `claim_types`, party roles (`claimant`, `respondent_employer`), determination/winner mapping, remedy fields, and 2019-2024 date constraints. Add validator tests before any ET gold rows are generated. |
| **SHA-65a** | ET scraper code (`scripts/scrapers/employment_tribunal/`) | 5 pts | - | Module mirrors the GOV.UK tribunal scraper pattern: `config.py`, `downloader.py`, `filter.py`, `govuk_scraper.py`, `models.py`, `parsers.py`, `progress.py`, `to_source_document.py`, and `tests/`. No live scrape. Unit tests use fixture listing/search HTML, decision-page HTML, and attachment text/PDF fixtures. Persist observed source licence, defaulting to `OGL-3.0` only where the page does not override it. |
| **SHA-65b** | Live 30-doc pilot | 2 pts | 65a | Run a polite live pilot against the unfair-dismissal filter with `--max-keep 30 --rps 0.5`. Validate title, case number, decision date, country, category labels, attachment URLs, extracted text, source hash, and model-facing PII redaction. Manually spot-check 5 documents. Commit pilot manifest to `data/eval_artifacts/pilots/employment_et_unfair_dismissal_pilot_30_<date>.jsonl`. |
| **SHA-65c** | 1000-doc corpus and namespace ingest | 5 pts | 65b passing | Run a 2019-2024 frozen research scrape. Ingest accepted, model-facing documents into `employment_unfair_dismissal_v1` vector/BM25 namespace with `corpus_version=research_seed_2026_05`. Keep excluded/preliminary/default/remedy-only decisions in an exclusion manifest, not silently discarded. Apply leakage controls per SHA-121. |
| **SHA-65d** | Stratified 50-case reviewed gold set | 5 pts | 65-0, 65c | Output `data/gold_standard/employment_unfair_dismissal_v1.jsonl`. Stratify by outcome, fair-reason category, country, and year. Use LLM-panel labelling only for candidate labels; mandatory human review confirms claim type, outcome, award/remedy fields, key reasoning quotes, and matter type before append. |
| **SHA-65e** | Factor catalog and extractor | 5 pts | 65d | Add `packages/domain_packs/employment/unfair_dismissal/factors.yaml` plus extractor protocol. Cover s98 fair-reason category, s98(4) reasonableness, investigation, hearing, appeal, Acas Code, Polkey, contributory fault, qualifying period, time limit, and remedy fields. Every `FactorAssertion` must carry span provenance. Target >=10 gate-countable factors after IAA. |
| **SHA-65f** | Cross-domain ablation evals | 3 pts | 65e, SHA-116 | Run the prediction harness against the ET test split. Metrics: win-probability Brier, ECE, factor F1, retrieval P@5 / nDCG@10, and leakage checks. Report award MAE only if the employment award calculator/remedy schema is done; otherwise explicitly mark amount evaluation as blocked. |

**Total:** 27 pts. The original 8-point SHA-65 estimate should be treated as epic-level only.

## 5. Data Flow and Contracts

### 5.1 Source

Primary source: `https://www.gov.uk/employment-tribunal-decisions`.

The scraper should treat the public page and any GOV.UK APIs as discovery surfaces, not as a stable legal-data contract. It must persist:

- public page URL
- GOV.UK base path or equivalent stable path
- case title
- case number(s)
- decision date
- country (`england_and_wales` or `scotland`, where available)
- jurisdiction/category labels
- attachment metadata
- source hash
- observed licence
- parser version

The persisted source licence should be `OGL-3.0` only where the source page/footer supports that and no exception is stated.

### 5.2 Two-Stage Filtering

Stage 1: discovery filter.

- Use GOV.UK's unfair-dismissal category/filter slug where available.
- Record the raw category labels returned by the page/API.
- Do not assume the label means the case is a clean merits unfair-dismissal judgment.

Stage 2: eval-quality filter.

Reject or quarantine from the gold/eval corpus:

- unfair dismissal is not the lead merits issue
- preliminary-only, strike-out, withdrawal, reconsideration, or jurisdiction-only decisions
- default judgments or no-response decisions with too little reasoning for outcome modelling
- remedy-only decisions without liability reasoning
- decisions where the award/remedy is not attributable to unfair dismissal

Rejected rows should be kept in `excluded.jsonl` with reason codes. They may still be useful later for abstention and routing tests.

### 5.3 Gold Schema

Do not start ET gold promotion until SHA-65-0 resolves the schema mismatch.

Current blockers in `packages/eval/schema.py`:

- `ClaimType` is deposit/housing-shaped (`cleaning`, `damages`, `deposit_non_protection`, `disrepair`, `end_of_tenancy`).
- `PartyRole` is tenancy-shaped (`tenant`, `landlord`, `agent`).
- `Winner` is tenancy-shaped (`tenant`, `landlord`, `split`).
- `Determination` is Housing Ombudsman-shaped.

The ET-ready contract must support at least:

- `domain_id = "employment.et.unfair_dismissal.v1"` or the agreed compatibility ID
- `forum = "employment_tribunal"`
- `source_publisher = "govuk"`
- `source_kind = "case_decision"`
- `matter_type = "unfair_dismissal"`
- `retrieval_namespace_id = "employment_unfair_dismissal_v1"`
- `corpus_version = "research_seed_2026_05"`
- temporal split (`train`, `dev`, `test`) based on decision date
- claimant/respondent-employer party roles
- claimant-success/respondent-success/partial/non-merits determination labels
- basic award, compensatory award, deductions/uplifts, and reinstatement/re-engagement remedy fields where available
- field-level provenance and mandatory human-review markers

### 5.4 Factor Catalog

Initial unfair-dismissal factors:

1. **Potentially fair reason category** - conduct, capability, redundancy, illegality/statutory restriction, SOSR, or none.
2. **Employer's reason genuinely held** - bool.
3. **Reasonableness under s98(4)** - bool or ordinal.
4. **Investigation adequate** - bool.
5. **Employee informed of allegations/reason** - bool.
6. **Hearing or meeting held before dismissal** - bool.
7. **Right of appeal offered** - bool.
8. **Appeal exercised** - bool.
9. **Acas Code compliance relevant** - bool.
10. **Acas uplift/reduction considered** - bool plus percent where available.
11. **Polkey deduction applied** - bool plus percent/range where available.
12. **Contributory fault deduction applied** - bool plus percent/range where available.
13. **Two-year qualifying period satisfied or exception applies** - bool/category.
14. **Limitation/early-conciliation issue** - bool/category.
15. **Basic award identified** - bool plus amount where available.
16. **Compensatory award identified** - bool plus amount where available.
17. **Reinstatement or re-engagement sought/granted** - categorical.
18. **Automatic unfair-dismissal flag** - exclusion or separate-routing flag for v1, unless user explicitly expands scope.

Target: at least 10 gate-countable factors after IAA and human review.

## 6. Sequencing

### 6.1 Critical Path

SHA-67 (Implementation chapter) is overdue as of 2026-05-13. ET work should not derail thesis writing.

Recommended sequence:

1. Run SHA-65a and SHA-65b in a separate worktree/window if capacity exists.
2. Hold SHA-65c until the pilot shows clean parser and merits-filter yield.
3. Hold SHA-65d until SHA-65-0 resolves the employment schema contract.
4. Hold SHA-65f amount metrics until the employment award/remedy model is ready.

### 6.2 Worktree Ownership

SHA-65a and SHA-65b touch only `scripts/scrapers/employment_tribunal/`, fixtures, and `data/raw/employment/`. They are safe to run in parallel with thesis-writing work.

SHA-65-0, SHA-65d, SHA-65e, and SHA-65f touch shared eval schemas, domain packs, and evaluation harness code. These should be serialised with any active Stream C or schema work.

## 7. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| `GoldCase` cannot validate ET rows | Add SHA-65-0 before gold generation. No ET gold append until schema tests pass. |
| GOV.UK category filter includes noisy decisions | Two-stage filter with explicit exclusion reasons and 30-doc pilot yield report. |
| Licence assumption is wrong for a subset of attachments | Persist observed licence/source page footer; default to `OGL-3.0` only when supported; quarantine exceptions. |
| PII redaction damages citation fidelity | Keep raw public source quarantined; use redacted model-facing `SourceDocument`; preserve source hashes and span offsets where possible. |
| ET amount prediction is misleading | Split remedies before MAE: basic award, compensatory award, deductions/uplifts, and reinstatement/re-engagement. Gate MAE on award-schema readiness. |
| Forum leakage in retrieval | Assert ET eval never retrieves `housing_ombudsman` or `first_tier_property_chamber` documents. |
| Domain ID rename breaks artifacts | Keep current YAML ID for compatibility; migrate to `employment.et.unfair_dismissal.v1` separately. |
| 2025/2027 legal changes confuse the corpus | Freeze v1 to 2019-2024 for thesis reproducibility. Add law-effective-date metadata before ingesting post-2024 rows. |

## 8. Open Questions

1. **Gold schema route.** Extend `GoldCase` enums directly, or add a domain-specific ET adapter that projects into common eval metrics?
2. **Domain ID.** Should SHA-65 use the compatibility ID `employment.unfair_dismissal.v1` until migration, or should the migration happen before any ET artifacts are generated?
3. **Raw-source privacy.** Should raw public ET attachments be committed, quarantined locally, or excluded from git with only manifests committed?
4. **Years to scrape.** Default is 2019-2024 for compatibility with the current schema date range and thesis reproducibility. User to confirm.
5. **Remedy output shape.** Should reinstatement/re-engagement be predicted in the main output, or only captured as factor/remedy metadata?
6. **GOV.UK throttle.** Proposed default is 0.5 RPS with robots.txt respected.

## 9. Definition of Done for This Design Phase

- [x] Design committed to `docs/superpowers/specs/2026-05-13-employment-tribunal-vertical-design.md`
- [x] Review pass incorporated schema, data-source, filtering, and remedy gates
- [ ] User approves or rejects SHA-65-0 schema-readiness gate
- [ ] Open questions in section 8 resolved
- [ ] Linear tickets SHA-65-0 and SHA-65a..f created/updated and linked to SHA-65
- [ ] Launch prompt for SHA-65a added to `docs/prompts/`
- [ ] First worktree window briefed
