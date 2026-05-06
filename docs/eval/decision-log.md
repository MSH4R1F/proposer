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

## D-021 — Switch annotation from two-paralegal blind double-labeling to LLM-assisted labeling + human adjudication

**Linear:** SHA-28 (rewritten Phase 3 + Phase 6); supersedes [SHA-96](https://linear.app/sharifbuilders/issue/SHA-96).
**Decision:** Replace the original two-paralegal blind double-annotation protocol with a dual-LLM + deterministic auto-grounder + single-human-adjudicator pipeline. Each case is labeled twice — once by an Anthropic model, once by an OpenAI model — through `packages/llm_orchestrator/clients/labeler_factory.py::LabelerModelSpec`. A deterministic auto-grounder (`packages/eval/auto_label/grounder.py`) rejects every cell that cannot be resolved to a basis span. A `DisagreementSet` plus a `MandatoryReviewSet` plus a 10% audit overlay route every metric-critical cell through one human adjudicator. A stratified 10–20-case human-only anchor subset is labeled from scratch (no LLM seed) and used as a calibration anchor. Every row carries a `LabelingProvenance` block (`run_id`, labeler models, source/OCR hashes, prompt-template hash, canonicalizer/grounder versions, `inter_model_agreement_rate`, `audit_flip_rate`, `mandatory_review_flip_rate`, per-cell `field_provenance`) plus a per-case run artifact under `data/eval_artifacts/labeling/<run_id>/<case_id>.json`. Codex sparring on the design (8 P1/P2 findings, all integrated before any code landed) is at `.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md`.

**Why:**
1. **Throughput.** Two paralegals labeling 50 cases at ~30 minutes per case for the single-annotation pass plus 5+ cases at ~60 minutes for the double-annotation pass was unfundable on Mohamed's working timetable. Phase 6 was the standing blocker on every thesis claim. Dual-LLM extraction processes 50 cases in hours, not weeks. One adjudicator's MandatoryReviewSet + DisagreementSet walk on 50 cases is one one-week sprint.
2. **Defensibility against the obvious circularity attack.** The naïve fix — "let the LLM label everything" — collapses the methodology because the predictor being scored is itself LLM-driven. The pipeline closes that loop with three independent firewalls: (a) the auto-grounder is deterministic and rejects cells without basis spans regardless of LLM agreement; (b) the MandatoryReviewSet forces a human to confirm every metric-critical cell on every real-gold row, regardless of A/B agreement; (c) the human-only anchor set is labeled from scratch and metrics are reported per anchor / LLM-assisted / combined splits. A combined-corpus calibration claim is blocked when anchor divergence exceeds the pre-registered threshold (Brier delta > 0.05 or systematic winner-flip).
3. **Reproducibility.** Frozen run artifacts + canonicalizer/grounder versions + index hashes + raw labeler outputs let any reviewer (or examiner) replay any labeling decision after model retirement, OCR engine drift, or authority-index updates. The original "two paralegals signed it off" record would have been irreproducible by definition.
4. **Provider independence is enforced at the call site, not by config.** Codex finding [4] flagged that calling `get_llm_client(LLMRole.EXTRACTION)` twice cannot prove independence — the existing role-keyed factory maps one provider to one role. The new `build_labeler_client(LabelerModelSpec)` constructs each client directly; tests prove A and B are different concrete classes with different providers.

**`inter_model_agreement_rate` is NOT Cohen's κ** and must not be reported as one. It is operational telemetry only. The defensibility metrics are: `mandatory_review_flip_rate`, `audit_flip_rate`, anchor-set divergence, and adjudication rate by field path.

**Rejected alternatives:**
- **Stick with the two-paralegal protocol and slip Phase 6.** Rejected — the timetable does not deliver paralegal staffing on a schedule that lands the interim report numbers. Slipping Phase 6 slips every thesis claim.
- **One LLM labeler, one human adjudicator.** Rejected — without provider independence, a systematic single-provider bias would silently dominate the gold set. The cost of running a second provider is small relative to the defensibility win.
- **Three or more LLM labelers, majority vote.** Rejected — adds cost and complexity without strengthening the firewall. The bottleneck is the human MandatoryReviewSet, not the LLM cost. Two providers are sufficient to surface disagreement at field-path granularity.
- **Whole-document fuzzy quote search instead of bounded-window span match.** Rejected — opens a prompt-injection attack surface: a labeler that hallucinates a quote could land it on a different page that happens to contain matching words. The grounder restricts matching to the span the labeler claims, with a small bounded edit-distance allowance for OCR drift only.
- **Use `data/eval/negative_sets/*.jsonl` as few-shot examples for the labeler.** Rejected — negative sets are runtime adversarial fixtures (prompt-injection, PII leakage, etc.). Mixing them into labeling exemplars contaminates evaluation boundaries. A new `data/eval/labeling_examples/positive/` directory holds positive few-shot exemplars only.
- **Keep `facts` LLM-drafted but unconstrained.** Rejected — `GoldCase.facts` flows into `CaseFile.tenant_narrative`, which flows into prediction at evaluation time. An unconstrained `facts` summary from a post-decision PDF can leak the verdict and corrupt every downstream accuracy/Brier number. The fix is `auto_label/leakage_scan.py`: phrase-list scan for tribunal-finding language plus a span-section check restricting `facts` source spans to `pre_decision_record`. `facts` is also in the MandatoryReviewSet so the adjudicator confirms the narrative is leakage-free on every row.

**Trigger to revisit:** if anchor-set divergence exceeds the pre-registered threshold on the first 10 cases, the pipeline produces a defensible LLM-assisted number but cannot back the combined-corpus calibration claim. At that point: either expand the anchor set (more human-only labels) or fall back to single-human MandatoryReviewSet on every cell of the LLM-assisted set. The pipeline supports both outcomes — the metric split is always reported separately.

---

## D-022 — Treat the Housing Ombudsman stratified-50 as a selection manifest, not gold

**Linear:** SHA-127
**Decision:** The 50-case Housing Ombudsman repairs/social set created on
2026-05-04 is stored under `data/eval/housing_ombudsman_stratified_50.jsonl`
as a source-grounded selection manifest, not under `data/gold_standard/` as
adjudicated gold.

**Why:**
1. **Outcome labels are parser-derived, not human-adjudicated.** The scraper now
   extracts `outcome_raw` and `outcome_normalized`, but those labels are only
   strata for sampling. They are not enough to score prediction quality.
2. **Ombudsman determinations use different remedies.** Housing Ombudsman
   complaint outcomes, orders, recommendations, and compensation are not the
   same as deposit adjudication winners/awards. Forcing them into `GoldCase`
   without a review pass would blur forum-specific remedies.
3. **Leakage controls need source IDs before labels.** The manifest records
   `target_source_id`, source paths, hashes, corpus version, and
   `annotation_status="needs_gold_labeling"` so the eventual gold-building
   path can exclude the target source during retrieval and keep every row
   reproducible.
4. **Representativeness matters.** The sample uses minimum-one-per-outcome plus
   largest-remainder proportional allocation, then matter-type round-robin
   inside each outcome bucket. That gives rare outcomes a foothold without
   throwing away the real corpus distribution.

**Rejected alternatives:**
- **Write directly to `data/gold_standard/housing_repairs_social_v1.jsonl`.**
  Rejected because that would imply reviewed `GoldCase` quality before
  compensation/order spans and human review exist.
- **Sample purely at random.** Rejected because `maladministration` dominates
  the 1,000-case corpus; rare outcomes such as `outside-jurisdiction` and
  `resolved-with-intervention` would likely disappear from a 50-case sample.
- **Only sample known outcomes.** Rejected because `unknown` is a real parser
  and data-quality category that needs one representative row for review.

**Trigger to revisit:** once SHA-127 promotes the manifest into adjudicated
`GoldCase` rows with `LabelingProvenance`, move the reviewed corpus into
`data/gold_standard/housing_repairs_social_v1.jsonl` and update
`eval.dataset.load(...)` guidance accordingly.

---

## D-023 — Treat the 2026-05-04 Housing Ombudsman full eval as a pilot harness run

**Linear:** SHA-127 / SHA-68
**Decision:** The full metric bundle run on 2026-05-04 is recorded as a
10-case Housing Ombudsman pilot run, not as a final thesis ablation result.
The artifacts live under
`eval/results/housing_ombudsman_full_eval_20260504/` and are documented in
`docs/eval/housing-ombudsman-pilot-full-eval.md`.

**Why:**
1. **Only 10 reviewed rows are scoreable.** The stratified 50 exists, but it is
   still a selection manifest. Accuracy, Brier, and ECE require adjudicated
   `GoldCase` rows.
2. **Prediction artifacts are pilot-grade.** The existing per-mode prediction
   JSONLs exercise the metric and ablation harness but are not yet independent
   live production RAG/LLM outputs.
3. **The dataset audit is non-strict.** The pilot corpus fails legacy deposit
   claim-type stratification floors, though it has no leakage violations. That
   is acceptable for a smoke-quality Ombudsman pilot, not for thesis reporting.
4. **Confidence intervals are too wide.** With `n=10`, overlapping CIs cannot
   support a hybrid superiority claim even where point estimates look useful.

**Rejected alternatives:**
- **Report the pilot as final RQ1 evidence.** Rejected because it would
  overstate what a 10-case, pilot-artifact run can prove.
- **Block all metric runs until the stratified 50 is adjudicated.** Rejected
  because the 10-case pilot still validates the metric plumbing, artifact
  layout, and ablation command before the expensive labeling pass.

**Trigger to revisit:** once the stratified 50 is promoted into reviewed
`GoldCase` rows and fresh independent predictions are generated for all four
modes, rerun `scripts/eval/run_full_eval.py` with `--min-case-count 50` and
promote the resulting report into SHA-68 thesis evidence.

---

## D-024 — Promote the reviewed Housing Ombudsman stratified-50, but report the first run as a stub baseline

**Linear:** SHA-127 / SHA-68
**Decision:** On 2026-05-04, after Mohamed confirmed all 50 Housing Ombudsman
review packets were reviewed and acceptable, promote the draft decisions into
`data/gold_standard/housing_repairs_social_v1.jsonl` through the real-gold
append gate. Record the resulting 50-case accuracy/Brier/ECE/ablation run as a
baseline harness result, not a live product-accuracy claim. Artifacts live under
`data/eval_artifacts/gold_build/housing-ombudsman-stratified-50-review-20260504-reviewed/`,
`eval/predictions/housing_ombudsman_stratified_50_20260504/`, and
`eval/results/housing_ombudsman_stratified_50_full_eval_20260504/`; the report is
`docs/eval/housing-ombudsman-stratified-50-full-eval.md`.

**Why:**
1. **The gold side is now scoreable.** All 50 rows carry
   `LabelingProvenance`, target-source IDs, mandatory human-review provenance,
   source/OCR/prompt/schema/corpus hashes, and passed
   `assert_real_gold_appendable(...)`.
2. **The prediction side is still not thesis-grade.** `predict_all.py` was run
   with `--engine stub`. The current live path does not yet wire the Ombudsman
   Chroma/BM25 retrieval namespace with target-source exclusion, so reporting
   the stub numbers as hybrid RAG/KG performance would overclaim.
3. **The issue vocabulary is not aligned.** The runner warned that Ombudsman
   `disrepair` is unmappable into the older deposit `DisputeIssue` enum. That
   makes per-issue metrics non-meaningful until the Ombudsman issue taxonomy is
   connected.
4. **The generic audit is deposit-biased.** `eval.dataset audit` reports
   `is_clean=false` because it checks deposit claim-type floors. It also reports
   zero leakage violations, which is the relevant gate for this baseline.

**Rejected alternatives:**
- **Keep the reviewed 50 outside `data/gold_standard/`.** Rejected because the
  append gate passed and the eval harness expects canonical `GoldCase` JSONL
  input for accuracy/Brier/ECE.
- **Report the stub 50-case run as final RQ1 evidence.** Rejected because the
  predictor is deterministic harness plumbing, not live retrieval + reasoning.
- **Block documentation until live prediction wiring exists.** Rejected because
  the baseline result is useful evidence that the gold-promotion and metric
  plumbing works end to end, provided the caveats are explicit.

**Trigger to revisit:** live Ombudsman retrieval/exclusion and repairs-specific
`disrepair` mapping are now wired in `predict_all.py`. Regenerate independent
predictions for all four modes with provider API keys, then rerun the same
full-eval command. Only that successor run can be considered for SHA-68 thesis
evidence.

---

## D-025 — Do not treat no-RAG abstentions as meaningful `split` predictions

**Linear:** SHA-68 / SHA-139-141
**Decision:** No-RAG Housing Ombudsman ablations (`kg_only`, `llm_only`) need
their own forum-specific ablation prompt and raw abstention diagnostics. The
eval-compatible JSONL still uses the existing three-value `Winner` enum, but
`predict_all.py` now also emits `raw_overall_outcome`, `raw_overall_confidence`,
`abstained`, and per-issue `raw_outcome` fields.

**Why:** The first clean live 50-case run on 2026-05-04 showed
`kg_only=0.000` and `llm_only=0.000` accuracy, with every JSONL row appearing
as `overall_winner="split"`. The logs showed the raw orchestrator outcome was
actually `uncertain` for every no-RAG row. The eval adapter had collapsed
`uncertain -> split` because the metric `Winner` enum has no fourth value.
That collapse is acceptable for binary calibration as a coin-flip proxy, but
it is misleading as a diagnostic label and invalid as product evidence.

The underlying model behavior was also prompt-induced: no-RAG Ombudsman modes
were reusing a cite-or-abstain system prompt that required similar retrieved
determinations. With no retrieved determinations by design, the model abstained.

**Rejected alternatives:**
- **Report the `0.000` no-RAG numbers as model failure.** Rejected because the
  raw logs proved this was prompt/eval-output wiring, not a fair baseline.
- **Add `uncertain` to `eval.schema.Winner` immediately.** Rejected for this
  patch because it would ripple through accuracy, calibration, fixtures, and
  historic result files. Raw diagnostic fields solve the immediate ambiguity
  while preserving metric compatibility.
- **Let no-RAG modes invent supporting determinations.** Rejected because it
  violates cite-or-abstain. The correct ablation rule is citation-free
  prediction with `supporting_cases=[]`, not fabricated authority.

**Trigger to revisit:** add first-class abstention metrics and, if needed, a
four-value prediction outcome model before reporting final SHA-68 thesis
numbers. Any live no-RAG ablation run before this fix must be marked invalid
for product evidence.

---

## D-026 — Treat the post-fix Ombudsman live rerun as a valid baseline, not a hybrid win

**Linear:** SHA-68 / SHA-139-141
**Decision:** The fixed 2026-05-04 live 50-case rerun is valid as a live
baseline/diagnostic run, but it must not be framed as evidence that the hybrid
RAG+KG system outperforms its ablations. The report is
`docs/eval/housing-ombudsman-stratified-50-full-eval.md`; artifacts live under
`eval/predictions/housing_ombudsman_stratified_50_live_20260504_202405_fixed/`
and
`eval/results/housing_ombudsman_stratified_50_live_20260504_202405_fixed_ordered_full_eval/`.

**Why:** The no-RAG prompt/output wiring bug was fixed and the fresh run no
longer collapses `kg_only`/`llm_only` into all-uncertain outputs. Those modes
now score `0.680` accuracy. The retrieval-backed modes are more conservative
after citation verification: `rag_only=0.540`, `hybrid=0.420`. On a 50-case
gold set with `tenant=49`, `landlord=1`, that means the retrieval path is
turning too many tenant-win cases into `split`/raw abstention predictions.

**Rejected alternatives:**
- **Report hybrid as thesis evidence anyway because it is more cited.** Rejected
  because citation discipline is valuable but does not rescue lower outcome
  accuracy on the held-out gold labels.
- **Discard the run because hybrid underperformed.** Rejected because failed
  ablations are still useful product evidence: they identify the retrieval and
  citation-verification layer as the next bottleneck.
- **Optimize against this one tenant-heavy set immediately.** Rejected because
  `n=50` with one landlord-win case can encourage majority-class overfitting.
  The next fix should inspect failure cases and retrieval quality, not hard-code
  tenant-favouring behavior.

**Trigger to revisit:** after issue-specific retrieval tuning, abstention
metrics, and a less tenant-skewed evaluation slice land, rerun the same live
ablation and update SHA-68 evidence only if hybrid improves on both accuracy
and calibration without weakening citation integrity.

---

## D-027 — Use determination accuracy, not binary winner accuracy, as the Housing Ombudsman headline

**Linear:** SHA-68 / Housing Ombudsman Task 18
**Decision:** For `housing.repairs_social.v1`, report the seven-class
`determination.accuracy` and per-class recall as the primary outcome metrics.
Keep binary `accuracy` / `covered_accuracy` in `summary.json` for compatibility,
but do not use them as the thesis headline for Housing Ombudsman results.

**Why:** The Task 18 `v2_valid48` / `par40` live run recovered high legacy
binary accuracy (`hybrid=0.833`, `rag_only=0.812`), but the corpus was heavily
tenant-leaning: the always-tenant baseline was `0.979`. On the same run, the
more honest seven-class determination scores were `hybrid=0.542` and
`rag_only=0.500`. Hybrid recall was concentrated in the majority class
(`maladministration=24/31`) and missed the smaller classes entirely:
`reasonable_redress=0/4`, `severe_maladministration=0/3`, and
`resolved_with_intervention=0/2`.

`covered_accuracy` is also susceptible to selection effects. RAG-only scored
`0.951` covered accuracy vs hybrid `0.930` because it abstained on 7/48 rows
instead of hybrid's 5/48; its answered subset was easier. This is useful
diagnostically, but it is not a standalone product-quality claim.

**Rejected alternatives:**
- **Report hybrid's 0.833 binary accuracy as success.** Rejected because a
  `0.979` always-tenant baseline shows the binary axis is dominated by class
  skew on this slice.
- **Use covered accuracy as the ranking metric.** Rejected because it rewards
  abstaining on hard cases unless read beside abstention and coverage-adjusted
  accuracy.
- **Collapse the seven Ombudsman classes back into tenant/landlord.** Rejected
  because the earlier RCA showed that `reasonable_redress`,
  `outside_jurisdiction`, and `resolved_with_intervention` are not clean
  substantive merits wins.

**Trigger to revisit:** once the minority-class eval slice has enough examples
to estimate recall reliably and the model improves recall on
`reasonable_redress`, `service_failure`, `severe_maladministration`, and
`resolved_with_intervention` without weakening citation validity. The recorded
Task 18 result note is
[`housing-ombudsman-task18-determination-live-eval-2026-05-06.md`](housing-ombudsman-task18-determination-live-eval-2026-05-06.md).

---

## How this log relates to the Codex sparring record

`.sisyphus/codex/sha-28-schema-2026-04-27.md` records Codex's findings and our triage. This log records the *implemented* decisions. Some decisions don't appear in Codex (e.g. D-001 Pydantic vs JSON Schema, D-009 pair-vs-issue bootstrap) — those are pure design choices with no Codex input. Conversely, every Codex HIGH that we accepted produced a decision entry here (D-005 through D-008, D-011, D-014, D-015, D-021).

When the examiner asks "Did you consider alternative X?", the answer pattern is:
1. Find the relevant D-NNN entry.
2. Cite the rejected alternative.
3. Cite the trigger-to-revisit if it's still open.
