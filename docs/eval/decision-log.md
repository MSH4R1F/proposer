# Evaluation Harness — Decision Log

> Chronological record of non-obvious design decisions, what was rejected, and why. **Read this for viva prep.** When the examiner asks "Why did you do X instead of Y?", the answer is here.

Format: each entry has a `Linear ID`, the **Decision**, **Why**, **Rejected alternatives**, and **Trigger to revisit**.

---

## D-001 — Pydantic schema rather than ad-hoc dicts

**Linear:** SHA-28
**Decision:** Define every annotated case as a `GoldCase` Pydantic v2 model with cross-field validators (INV-1..10). Reject JSON dictionaries that don't validate.

**Why:** The schema is the load-bearing contract for every downstream metric. Annotation drift is the most likely silent failure mode (annotator typos a date, forgets a field, mis-labels a winner). Validation at the gate of the JSONL means the cost of a typo is caught at annotation time, not three weeks later when a metric returns nonsense.

**Rejected alternatives:**
- **Plain dicts + duck typing.** Tempting because the corpus is small. Rejected because the cost of wrong data shows up only in metric outputs — by the time a number looks wrong, multiple metric runs have used it.
- **JSON Schema (draft-2020-12).** Equivalent in expressive power for our cases. Rejected because Pydantic's `model_validator` is more readable than JSON Schema's `if`/`then`/`allOf`, and Pydantic gives us Python objects with `.field` access for free.
- **TypedDict + manual validators.** Rejected because TypedDict has no runtime validation in Python 3.9, and we need runtime validation specifically.

**Trigger to revisit:** corpus exceeds 1000 cases AND validators become a perceptible bottleneck (currently <1 ms per case).

---

## D-002 — Lenient defaults, strict opt-in for CLI

**Linear:** SHA-101
**Decision:** Every CLI defaults to lenient mode (skip-and-log for parse errors; warn-but-proceed for leakage). `--strict` flag opts into hard failures for production CI gates.

**Why:** Two opposing requirements. During pilot, a half-broken corpus is the normal state — annotators iterate on a single case while the rest of the corpus has known issues. CI before publication must NOT ship a half-broken corpus. One default cannot serve both.

**Rejected alternatives:**
- **Strict by default, `--lenient` opt-in.** Rejected because annotators run the CLI 100x more often than CI does; the common case should be the default.
- **Two separate CLIs.** `annotate-strict` and `annotate-lenient`. Rejected because it doubles the surface area and reviewers conflate them.
- **Always strict, with a side log.** Rejected because annotators would have to clear the log between every iteration.

**Trigger to revisit:** if annotators forget to flip `--strict` for production runs, add a `make eval-strict` Makefile target that wraps the right invocation.

---

## D-003 — JSONL rather than SQLite for the gold set

**Linear:** SHA-101 (implicit)
**Decision:** Store the gold-standard corpus as a JSONL file (`data/gold_standard/housing_v1.jsonl`), one `GoldCase` JSON object per line.

**Why:**
1. JSONL is human-readable and `git diff`-able. A reviewer can review a PR that adds a case by reading the diff.
2. JSONL is append-only at the file-format level, which matches how annotation actually happens (one case at a time).
3. The corpus size cap is 100 cases × ~5 KB each = 500 KB. Sub-megabyte data does not justify a database.
4. SHA-102 (Postgres migration of user-facing storage) explicitly excludes the gold set: "different access pattern, already appropriate storage" — same logic as ChromaDB and BAILII PDFs.

**Rejected alternatives:**
- **SQLite.** Rejected because the read pattern is "load all 50 cases" for every metric run; no random access; no joins. SQLite adds setup friction with no payoff at this scale.
- **Postgres.** Same as SQLite plus infrastructure overhead.
- **Per-case JSON files in a directory.** Rejected because `git diff` gets noisy across renames; harder to enforce per-case ordering for deterministic metric reproducibility.
- **CSV.** Rejected because the schema is deeply nested (lists of evidence, per-issue outcomes, cited authorities); CSV would force flattening that loses information.

**Trigger to revisit:** corpus exceeds 10k cases (would push 50 MB JSONL territory) OR cross-corpus queries become routine.

---

## D-004 — Pre-publish Codex sparring as a process step

**Linear:** SHA-28 (planned in Track A launch prompt)
**Decision:** Before publishing the schema and starting real annotation, run a structured failure-mode review using Codex (separate LLM, separate session) against five specific questions about real-world tribunal text.

**Why:** Schema design is the highest-leverage decision in the whole track — every annotation, every metric inherits the schema's choices. A second pair of eyes is cheap; the cost of catching a schema flaw post-publication (corpus regenerate, cases re-annotated) is huge.

**What it caught:** 8 high-severity findings (5 schema redesigns implemented before annotation: SHA-90/91/92/93/95; 3 implemented in this PR: SHA-98/99/100). 4 medium findings (3 in Phase 3 scope, 1 deferred). The full record is at `.sisyphus/codex/sha-28-schema-2026-04-27.md`.

**Rejected alternatives:**
- **Skip the review and ship.** Rejected because the highest-severity finding (no authority dates → no temporal-leakage audit possible) would have made Phase 2's leakage audit unbuildable. We'd have hit it three weeks later, mid-Phase-2.
- **Internal review only (Mohamed reads).** Rejected because Mohamed wrote the schema; an author cannot easily critique their own schema for failure modes they didn't think of.

**Trigger to revisit:** Phase 4b adds atomic claim units (SHA-94) — that's a schema redesign that warrants its own sparring session before annotation continues.

---

## D-005 — `claim_types` as a list, not a single value

**Linear:** SHA-92 (Codex finding [3])
**Decision:** `GoldCase.claim_types` is `list[ClaimType]` with `min_length=1`. Stratification audits count multi-type cases toward each of their types.

**Why:** Real tribunal cases routinely combine cleaning + damages + disrepair. Forcing one primary label is lossy in two ways:
1. The primary-label choice is subjective; reviewer A might pick `damages`, reviewer B `cleaning`.
2. The thesis claim "the model handles N% of cleaning cases correctly" is misleading if some of those cases were also damages cases.

The list approach lets every case contribute honestly to every relevant stratum.

**Rejected alternatives:**
- **Primary + secondary types.** Rejected because the primary/secondary distinction is just as subjective as the original primary-only choice.
- **Single value with a `tags` companion.** Rejected because then the primary-vs-tag distinction creates the same problem.

**Trigger to revisit:** never. The ergonomic cost of a list is small; the methodological cost of forcing a primary label is large.

---

## D-006 — Apportioned vs unapportioned outcome paths

**Linear:** SHA-91 (Codex finding [2])
**Decision:** `GroundTruthOutcome` supports two paths:
- **Apportioned:** `per_issue` non-empty, INV-6 enforces sum-equals-total.
- **Unapportioned:** `unapportioned_reason` set, `per_issue` MUST be empty, total stands alone.

**Why:** Tribunals routinely give a single global figure with no per-issue breakdown ("balancing all factors, the tribunal awards £1,100"). Forcing per-issue annotation on these cases would either drop them silently from the corpus (biasing the gold set) or force the annotator to fabricate a breakdown (corrupting the labels).

**Rejected alternatives:**
- **Drop unapportioned cases from the corpus.** Rejected because they're a meaningful fraction of real decisions; dropping them biases the gold set toward a subset of tribunals' decision style.
- **Force annotators to fabricate per-issue breakdowns.** Rejected explicitly — fabricated data is worse than missing data.
- **Two separate Pydantic classes** (`ApportionedOutcome`, `UnapportionedOutcome`). Rejected because the metric code would need to dispatch on type, doubling the surface area. The flag-based approach lets metric code branch once.

**Trigger to revisit:** if >30% of real corpus is unapportioned, calibration metrics may need a per-path version (per-case calibration vs per-issue calibration may diverge meaningfully).

---

## D-007 — `disputed_amount_gbp` as canonical dispute value

**Linear:** SHA-91 (Codex finding [9])
**Decision:** Add `disputed_amount_gbp: Decimal` to `GoldCase` as the canonical disputed value. INV-7 (`case_size`) is now defined against `disputed_amount_gbp`, NOT against `sum(claimed_amounts)`.

**Why:** A common case shape: tenant paid £1200 deposit, landlord retained £400 disputed by tenant. `claimed_amounts` will list the £400 from landlord and possibly a counterclaim of £400 from tenant. Summing both would say £800, label the case `large` if the floor were £750 — a typical small dispute is silently miscategorised.

**Rejected alternatives:**
- **Smart sum that detects mirrored claims and deduplicates.** Rejected because the heuristic is fragile (different parties might describe the same disputed value in slightly different terms) and an annotator's unambiguous canonical figure is far more reliable.
- **Use only one party's claim.** Rejected because the choice of party (tenant vs landlord) is arbitrary and the values can differ.

**Trigger to revisit:** never; canonical fields are a methodological win.

---

## D-008 — INV-9 enforces overall_winner consistency

**Linear:** SHA-93 (Codex finding [4])
**Decision:** When `unapportioned_reason is None`, `overall_winner` must agree with the `per_issue.winner` aggregate (all-same → that value; mixed → must be `split`).

**Why:** Without this invariant, `overall_winner=tenant` with every per-issue outcome favouring landlord validates fine. The headline accuracy label would silently be wrong, and every metric reading it would inherit the wrong answer.

**Rejected alternatives:**
- **Trust annotators.** Rejected because the cost of a single annotation slip is "every accuracy number is wrong by 1/n_cases" — too high for a soft constraint.
- **Just record both, let metrics pick.** Rejected because metric code now has to handle the inconsistency, replicating the rule across modules.

**Trigger to revisit:** if a real tribunal decision has a structural reason to disagree with the aggregate (rare but possible — e.g. costs awards), add a third path with documented reason.

---

## D-009 — Bootstrap pair resampling, not issue resampling

**Linear:** SHA-97
**Decision:** `bootstrap_ci()` resamples `(gold[i], predictions[i])` PAIRS with replacement, not individual issue-level pairs.

**Why:** Issues within a single case are not independent. A case where the tribunal favours the tenant typically has all-tenant per-issue outcomes — they're correlated. Resampling at the issue level would treat them as iid, inflating effective sample size and producing artificially tight CIs.

The conservative choice is to resample at the case level, which preserves the within-case correlation structure. The CI may be wider than necessary; the alternative is wrong.

**Rejected alternatives:**
- **Issue-level resampling.** Rejected for the iid violation above.
- **Hierarchical bootstrap (Cluster + element).** Rejected because the methodological gain over case-level resampling is marginal at n=50, and the implementation complexity is higher. Worth revisiting at n>500.
- **Asymptotic Wald CI.** Rejected because n=50 is too small to trust the normal approximation; bootstrap is the standard remedy.

**Trigger to revisit:** at n>500 cases, hierarchical bootstrap may pay off.

---

## D-010 — Synthetic 10-case fixture, not a held-out real subset

**Linear:** SHA-103
**Decision:** Phase 4 metrics develop against a synthetic 10-case JSONL (`packages/eval/tests/fixtures/synthetic_corpus_10.jsonl`) built reproducibly from a Python script (`_build_synthetic_corpus.py`).

**Why:**
1. Real cases haven't been annotated yet (blocks on reviewer assignment).
2. Synthetic cases let us deliberately exercise edge cases (unapportioned, multi-type, leakage-positive). A real subset would only cover whatever tribunals happened to write.
3. The fixture is a tested artefact: the build script validates every case through `GoldCase.model_validate` before writing. It cannot drift from the schema.

**Rejected alternatives:**
- **Hand-edit a JSONL file.** Rejected because hand-edits drift; small schema changes break fixtures silently.
- **Random generation via Hypothesis.** Rejected because Hypothesis generates valid-by-construction cases that don't necessarily exercise the design-space corners we care about. Bespoke factories give us coverage of unapportioned + multi-type + leakage-positive cases by design.
- **Use the actual 10-case pilot batch.** Rejected because (a) it doesn't exist yet, and (b) the synthetic fixture should remain stable across pilot iterations.

**Trigger to revisit:** when 50-case real corpus lands, switch some metric integration tests to use a tiny stable subset of real cases as a sanity check; keep the synthetic fixture as the primary unit-test target.

---

## D-011 — `Provenance` model rather than `paragraph_ref: str`

**Linear:** SHA-100 (Codex finding [12])
**Decision:** Replace `paragraph_ref: Optional[str]` on `Evidence`, `StatutoryReference`, `Authority`, and `ReasoningQuote` with `provenance: Optional[Provenance]` (or required, on `ReasoningQuote`). `Provenance` carries `(page, paragraph, optional text_span)`.

**Why:** Free-text "para 14" is unverifiable under noisy OCR. A reviewer cannot mechanically check that "para 14" exists in a PDF that has been mis-segmented. Structured `(page, paragraph)` is mechanically locatable. The Phase 3 annotation CLI will (in a future iteration) load the source PDF and confirm the chosen page+paragraph exists.

The downstream NLI hallucination audit (Phase 4b / SHA-31) consumes the optional `text_span` to extract the cited evidence span and run entailment against the model's claim.

**Rejected alternatives:**
- **Keep `paragraph_ref: str`.** Rejected because fabricated references would silently pass validation, and the NLI audit would have nothing structured to read.
- **Store the raw character offset.** Rejected because OCR re-runs change offsets but not page/paragraph numbers; offset is more brittle.

**Trigger to revisit:** if PDF annotation tools become reliable enough to attach text_spans automatically, make `text_span` required.

---

## D-012 — Reviewer process: schema-first JSON edit, no interactive prompting

**Linear:** SHA-103
**Decision:** Reviewers edit JSON files in their preferred text editor. The CLI is a gatekeeper (validate, append) — it does NOT prompt the reviewer field-by-field.

**Why:** Real annotation involves cross-referencing the source PDF, scrolling back and forth, copying quotes verbatim. An interactive prompt (`enter the case_id: __`) makes that workflow worse, not better. A text editor is what reviewers reach for naturally.

**Rejected alternatives:**
- **Interactive Python prompt.** Rejected for the workflow reason above.
- **Web UI for annotation.** Rejected because the engineering cost is high, the corpus is small (50–100 cases), and a text editor is good enough.
- **Excel / Google Sheets.** Rejected because the schema is too nested for a flat tabular form.

**Trigger to revisit:** at >300 cases or >5 active reviewers, a web UI starts to pay off.

---

## D-013 — Evidence trail in `.sisyphus/evidence/eval/`, force-added

**Linear:** ad-hoc
**Decision:** Coverage reports and audit JSON are committed under `.sisyphus/evidence/eval/`. The directory is in `.gitignore` per the orchestration convention; specific files are force-added per commit.

**Why:** The thesis-claim survival rule depends on archived evidence. A thesis figure must be reproducible from a tagged commit; the supporting evidence has to be in the repo.

**Rejected alternatives:**
- **Untrack `.sisyphus/` entirely.** Rejected because the orchestration convention treats it as scratch space; some files in there genuinely shouldn't be committed (other windows' notes).
- **Move evidence to `eval/results/`.** Reasonable; defer until the convention shifts. Not worth a fight now.
- **Don't commit evidence.** Rejected because then thesis numbers would be ephemeral.

**Trigger to revisit:** if the orchestration convention changes to allow `.sisyphus/evidence/` by default, drop the force-add and update the gitignore.

---

## D-014 — `RegionUK` enum + `region_source` companion

**Linear:** SHA-98 (Codex finding [10])
**Decision:** Replace free-text `region: str` with `region: RegionUK` (12-value enum) plus `region_source: str` (verbatim PDF string).

**Why:** The 30/70 stratification audit depends on `region`. With free text, "London" and "Greater London" and "central London" would each be a different stratum, silently breaking the audit. The companion `region_source` field preserves the raw PDF string for provenance — reviewers can recover the original wording without re-fetching the PDF.

**Rejected alternatives:**
- **Free text + post-hoc normalisation in the audit.** Rejected because then the normalisation rule lives in two places (audit code and any other consumer); changing the rule changes audit outputs retroactively.
- **Closed enum with no provenance field.** Rejected because reviewer B disagreements about region might come down to "is this Greater London or just London" — the source string captures the disagreement.

**Trigger to revisit:** if the reviewer needs more granularity (council area, postcode) for fairness analysis, add a sub-region field.

---

## D-015 — INV-10 requires explicit unavailability reason

**Linear:** SHA-99 (Codex finding [11])
**Decision:** Empty `evidence` or `statutory_basis` lists require a corresponding `*_unavailable_reason` string. INV-10 rejects empty-without-reason AND non-empty-with-reason.

**Why:** "No evidence captured" is a meaningful annotation choice that should be deliberate, not a silent omission. Phase 4 metrics (especially Phase 4b's unsupported-claim-rate) need to distinguish "the model cited nothing because nothing was relevant" from "the model cited nothing because the annotator forgot to record evidence."

**Rejected alternatives:**
- **Just allow empty lists.** Rejected because silent annotation gaps contaminate downstream metrics.
- **Forbid empty lists.** Rejected because some real decisions genuinely turn on submissions only with no evidence catalogue published.

**Trigger to revisit:** if `*_unavailable_reason` is set on >20% of cases, the annotation guideline needs revision (most cases should have evidence).

---

## D-016 — Defer NLI + RAGAS to Phase 4b, separate PR

**Linear:** SHA-104 (Phase 4a scope decision)
**Decision:** Phase 4a ships accuracy + Brier + ECE + reliability_diagram + bootstrap_ci. NLI hallucination audit (SHA-31) and RAGAS (SHA-29) are deferred to Phase 4b in a separate PR.

**Why:**
1. **Heavy deps.** transformers + torch + a NLI checkpoint = ~5 GB. ragas pulls langchain. Adding both to one PR balloons CI test time and review surface area.
2. **Atomic claim units (SHA-94)** is a prerequisite for the unsupported-claim-rate metric. The schema redesign needs its own design review before code lands.
3. **Real test data.** Both metrics benefit from realistic predictions with structured citations, which Phase 5 ablation runner produces. Building 4b before 5 means testing against synthetic data only.

The Phase 4a scope (no heavy ML deps) is fully usable on its own — accuracy and calibration are the metrics SHA-30 explicitly targets.

**Rejected alternatives:**
- **Ship everything in one Phase 4 PR.** Rejected for the reasons above.
- **Skip 4a, do 4b first.** Rejected because 4a's bootstrap_ci shape is a dependency for 4b too; building 4b first would either duplicate the helper or merge against a ghost dependency.

**Trigger to revisit:** when SHA-94 (atomic claims) lands AND Phase 5 ablation runner emits real predictions, open Phase 4b PR.

---

## D-017 — Defer live LLM runner; Phase 5 ships fixture-fed comparison machinery only

**Linear:** SHA-32 (Phase 5 scope decision)
**Decision:** Phase 5 ships `eval.adapter`, `eval.compare`, and `python -m eval.ablate` plus four hand-crafted synthetic per-mode prediction JSONLs. The live runner (loops `PredictionEngineV2.predict()` over real cases, writes per-mode JSONL) is deferred to a follow-up PR.

**Why:**
1. **No real corpus yet.** Phase 6 produces the 50-case annotated set. Running the live runner against the synthetic corpus would test the wiring but not the science — and the wiring is unit-testable on hand-crafted prediction fixtures already.
2. **`GoldCase → CaseFile` is lossy.** Gold cases carry post-decision facts (the tribunal's reasoning, awarded amounts). `CaseFile` is the pre-decision intake state the production engine expects. Reconstruction is a non-trivial lossy mapping that deserves its own Codex sparring round before code lands.
3. **PR size discipline.** Bundling the live runner doubles the surface area: subprocess shape, LLM client management, dry-run stub, vocab alignment. Reviewer fatigue produces missed bugs.

**Rejected alternatives:**
- **Ship live runner against synthetic corpus.** Rejected — no `CaseFile` data exists for synthetic gold cases. Would require synthesising fake intake state, which is the same engineering as the deferred reconstructor.
- **Block Phase 5 on Phase 6.** Rejected — the comparison machinery is independent of corpus size and unblocks the thesis-table format work *now*. The follow-up PR can land within an hour of Phase 6 completing.

**Trigger to revisit:** when Phase 6 (50-case corpus) lands, open the follow-up PR with `scripts/eval/predict_all.py` + `eval/case_file_adapter.py` + Codex sparring round on the lossy mapping.

---

## D-018 — Dominance via non-overlapping bootstrap CIs, not paired hypothesis tests

**Linear:** SHA-32 (Phase 5 design decision)
**Decision:** `summarise_dominance(a, b)` decides "X significantly better than Y" by checking whether the two modes' bootstrap CIs are disjoint. Higher-is-better metrics: `a.lower_95 > b.upper_95`. Lower-is-better metrics (Brier, ECE): `a.upper_95 < b.lower_95`.

**Why:**
1. **Interpretability.** "The hybrid CI sits entirely above the RAG-only CI" reads cleanly in the thesis and on a slide. A McNemar p-value or paired-bootstrap p-value adds precision but is harder to explain to a non-statistical examiner.
2. **Conservative.** Non-overlapping CIs is a strictly stronger criterion than a paired test at α=0.05 — claims that survive this test will also survive a paired test, but not vice versa. We prefer the false-negative direction over the false-positive direction in a thesis context.
3. **Reuses existing machinery.** Bootstrap CIs are already produced by `bootstrap_ci()` for every metric. Adding a hypothesis test would mean a parallel resampling loop (paired) plus a new statistical-machinery API surface in `eval.compare`.

**Rejected alternatives:**
- **McNemar's test.** Categorical-only (winner accuracy), can't be applied to Brier/ECE. Would require bolting on a second framework.
- **Paired bootstrap with point-estimate-difference CI.** More powerful than overlap-check, but requires a custom resampling shape and a separate dataclass to communicate the difference's CI. Higher complexity for marginal gain when n=50.
- **No significance test, just point estimates.** Rejected — the interim report claims hybrid > RAG-only, and an examiner will ask "by how much, and how confident are you?".

**Trigger to revisit:** if Phase 6 lands an n=100 corpus and CI overlap blocks a true hybrid > RAG-only claim, add a paired-bootstrap fallback path. Until then, overlap-check is the correct conservative choice.

---

## D-019 — Stub `PredictionResult` builder, not LLM client mock, for `--dry-run`

**Linear:** SHA-32 (Phase 5b runner design)
**Decision:** The live runner's `--engine stub` path bypasses `PredictionEngineV2` entirely and synthesises `PredictionResult` directly via `eval._stub_prediction.make_stub_prediction(case_file, mode)`. The runner does NOT mock `BaseLLMClient` to drive a real engine.

**Why:**
1. **Surface area.** `BaseLLMClient` exposes `generate`, `generate_structured` (with arbitrary Pydantic response models), `get_stats`, `reset_stats`. The pipeline calls `generate_structured` from at least four call sites (decomposer, predictor, retrieval, verifier) with four different response models. A faithful stub would need a fixture or scripted response per model. High maintenance cost; brittle as the pipeline evolves.
2. **What we're testing.** The runner's job is the data-flow plumbing: gold → CaseFile → PredictionResult → adapter → JSONL → ablate. The pipeline's *internal* correctness is tested elsewhere. Stubbing at the engine boundary tests the wiring without coupling to the engine's prompt graph.
3. **Determinism.** A direct `make_stub_prediction` is trivially deterministic (SHA-256 hash of `(case_id, mode)`). A scripted LLM stub would need to be re-pinned every time prompts change.

**Rejected alternatives:**
- **Mock `BaseLLMClient` with a scripted response dict.** Rejected — high maintenance, brittle, couples evaluation tests to prompt internals.
- **Always require a real LLM key in CI.** Rejected — slow, costly, non-deterministic. Real-LLM smoke tests can run nightly outside this CI.
- **No CI exercise of the live runner at all (only unit-test components).** Rejected — the integration risk lives at the seams (CaseFile reconstruction, vocab alignment, JSONL serialisation), and end-to-end is the only way to catch them.

**Trigger to revisit:** if a future runner change makes mode-specific behaviour visible only through the prompt-pipeline (not catchable via direct stub), revisit and either add a thin scripted-LLM stub or pin a real-LLM golden run.

---

## D-020 — Eval-vocab `disrepair` and `end_of_tenancy` fall back to `DisputeIssue.OTHER`

**Linear:** SHA-32 (Phase 5b alignment design)
**Decision:** When `gold_case_to_case_file` encounters a `ClaimType` with no clean orchestrator equivalent (currently `disrepair` and `end_of_tenancy`), the issue is mapped to `DisputeIssue.OTHER` and the original eval value is recorded on `LossyReconstruction.unmapped_claim_types` for the runner's alignment summary. The runner does **not** drop the case.

**Why:**
1. **Don't shrink the corpus arbitrarily.** Roughly 20–30% of housing-tribunal cases involve disrepair; dropping them would meaningfully change the corpus distribution and make the thesis harder to defend on representativeness grounds.
2. **`OTHER` is honest.** The engine sees that *something* is in dispute, just without a tighter category — same as a real intake user who picks "other" from the dropdown.
3. **Surface the gap, don't hide it.** The runner emits the per-eval-value tally to stdout and returns it in the in-process summary, so SHA-68's thesis chapter can quantify the alignment loss alongside the headline numbers.

**Rejected alternatives:**
- **Drop unmappable cases.** Rejected for distribution-bias reasons above.
- **Add `disrepair` and `end_of_tenancy` to `DisputeIssue`.** Rejected from this PR — `DisputeIssue` is a production UI/intake taxonomy with downstream consumers (chat surfaces, settlement nudges, KG facts). Changing it is a coordinated cross-package change that deserves its own ticket.
- **Two-pass mapping (disrepair → fair_wear_and_tear OR damage based on fact text).** Rejected — fact-text classification is a non-trivial subsystem to introduce in an alignment shim. Keep alignment a static lookup; let semantic refinement live elsewhere.

**Trigger to revisit:** when SHA-68 reports a measurable accuracy delta between mapped and `OTHER`-bucketed issues that shifts thesis claims, push the production-vocab expansion as a separate ticket.

---

## How this log relates to the Codex sparring record

`.sisyphus/codex/sha-28-schema-2026-04-27.md` records Codex's findings and our triage. This log records the *implemented* decisions. Some decisions don't appear in Codex (e.g. D-001 Pydantic vs JSON Schema, D-009 pair-vs-issue bootstrap) — those are pure design choices with no Codex input. Conversely, every Codex HIGH that we accepted produced a decision entry here (D-005 through D-008, D-011, D-014, D-015).

When the examiner asks "Did you consider alternative X?", the answer pattern is:
1. Find the relevant D-NNN entry.
2. Cite the rejected alternative.
3. Cite the trigger-to-revisit if it's still open.
