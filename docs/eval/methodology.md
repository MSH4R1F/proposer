# Evaluation Methodology

> Working draft of the "Evaluation methodology" chapter. Audience: examiner / external reviewer reading the thesis. Length: ~6 pages when compressed. Cite-or-defer style — every methodological claim grounded in either a primary source or a recorded design decision (see [`decision-log.md`](decision-log.md)).

## 1. Research questions

The thesis poses four research questions. The evaluation harness is built specifically to answer them empirically.

| RQ | Question | Method |
|---|---|---|
| **RQ1** | Does the hybrid RAG + KG architecture outperform RAG-only and KG-only baselines on UK housing-tribunal predictions? | Ablation runner ([SHA-32](https://linear.app/sharifbuilders/issue/SHA-32)) over four modes; thesis-claim survival rule on accuracy and Brier |
| **RQ2** | Are the prediction probabilities well-calibrated? | Brier score + ECE + reliability diagram; CI fails on >0.05 Brier regression |
| **RQ3** | Is the citation-grounded reasoning trace actually faithful to the cited evidence? | NLI entailment audit (Phase 4b); unsupported-claim-rate <2% target |
| **RQ4** | Does the system generalise across time? | PILOT temporal split (train 2019–22 / test 2023–24); leakage audit |

## 2. Design principles

Three commitments shape every methodology choice. They are visible in the schema, the loader, and the metric implementations.

1. **Falsifiability first.** Every thesis number must be a function of the gold set + the predictions + a deterministic seed. No hand-aggregated numbers. No "we observed informally that…". The CLI orchestrator (`PYTHONPATH=packages python -m eval.run`) emits one JSON file per metric per run. The harness exists so the next reviewer can reproduce every figure in the thesis from first principles.
2. **Pre-register, then measure.** Design decisions (stratification floor, train/test cutoff, threshold percentages, claim-type taxonomy) are locked in the schema before annotation starts. Changing them mid-stream invalidates the corpus. The schema versioning policy ([SHA-95](https://linear.app/sharifbuilders/issue/SHA-95)) enforces this: `v1` is mutable until pilot batch and HIGH Codex items resolve, then frozen.
3. **Lenient defaults, strict CI gates.** Iterating on a half-broken corpus during annotation has to be possible; shipping a half-broken corpus into a published number must not. Every loader and CLI defaults to lenient (warn-and-continue) for development and exposes `--strict` for the production path.

## 3. Terminology

We use the following terms with the precise meanings below. Section 4 applies them.

- **Gold standard.** A versioned set of manually-annotated tribunal decisions. Each case is a `GoldCase` Pydantic record.
- **Apportioned vs unapportioned.** A decision is *apportioned* if the tribunal breaks the award per issue; *unapportioned* if it gives a single global figure. The schema supports both paths; the metrics scoring rule differs (per-issue vs per-case). Real corpora contain both — see [`decision-log.md`](decision-log.md) §SHA-91 for why.
- **Temporal leakage.** A train-window case (`decision_date <= 2022-12-31`) citing an authority whose `cited_date > 2022-12-31`. The model would effectively have access to "future" law, inflating any reported accuracy. The audit rejects such cases when run with `--strict`.
- **Stratification floor.** Minimum cases per `claim_type` for the corpus to be considered balanced. Set to 5 (small enough to be reachable in 50 cases, large enough that bootstrap CIs are meaningful). Multi-type cases count toward each of their types.
- **PILOT methodology.** Temporal split methodology referenced in our interim report and grounded in the principle that an evaluation set must test future generalisation, not in-distribution interpolation [^pilot].

## 4. The gold-standard corpus

### 4.1 Stratification

The corpus is stratified along three dimensions:

| Dimension | Target | Audit method |
|---|---|---|
| Claim type | ≥5 cases per type (cleaning, damages, deposit_non_protection, disrepair, end_of_tenancy) | `dataset.audit().understratified_types` |
| Region | London ~30%, rest of UK ~70% | `dataset.audit().region_distribution`, normalised via `RegionUK` enum |
| Case size | Small (`disputed_amount_gbp <= £1500`) ~30%, Large ~70% | `dataset.audit().case_size_distribution` |

Multi-type cases count toward each of their `claim_types` (rationale: rejecting a single primary label is more honest about real tribunal cases — see [SHA-92](https://linear.app/sharifbuilders/issue/SHA-92)).

### 4.2 Temporal split

Train: 2019-01-01 .. 2022-12-31. Test: 2023-01-01 .. 2024-12-31. No shuffle. Implemented in `eval.dataset.train()` / `eval.dataset.test()` as pure date filters. Constants `TRAIN_CUTOFF` and `TEST_START` are exposed for downstream code.

### 4.3 Annotation reliability — LLM-assisted labeling + human adjudication

> Rewritten 2026-05-03. The original two-paralegal protocol from [SHA-96](https://linear.app/sharifbuilders/issue/SHA-96) is superseded by [`decision-log.md`](decision-log.md) D-021 after Codex sparring at `.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md` (8 P1/P2 findings, all integrated before any code landed).

The protocol is a dual-LLM + deterministic auto-grounder + single-human-adjudicator pipeline:

1. **Dual-LLM extraction** with explicit `LabelerModelSpec` configs — one Anthropic, one OpenAI. Provider independence is enforced at the call site (`packages/llm_orchestrator/clients/labeler_factory.py::build_labeler_client`), not via the role-keyed `get_llm_client(LLMRole.EXTRACTION)` factory which cannot prove independence between two passes (Codex finding [4]). Both passes consume the same allowed-field list and the same source text triples; outputs are partial-`GoldCase`-shaped JSON dicts.
2. **Auto-grounder** (`packages/eval/auto_label/grounder.py`) rejects every cell that cannot be resolved to a basis span: canonical quote match (`canonicalize.py` + `span_match.py`, bounded edit distance only inside the claimed window — no whole-document fuzzy fallback, which would open a prompt-injection surface), versioned BAILII authority lookup, versioned UK-statutes lookup, INV-1..INV-10, plus a `facts` leakage scanner (`auto_label/leakage_scan.py`) that rejects tribunal-finding language and source spans outside `pre_decision_record`.
3. **MandatoryReviewSet** — the human adjudicator confirms every metric-critical cell (`facts`, `disputed_amount_gbp`, `claim_types`, `matter_type`, every `ground_truth_outcome.{overall_winner, total_awarded_gbp, per_issue.*, unapportioned_reason}`) on **every real-gold row**, regardless of A/B agreement. This is the firewall against "LLMs agreed therefore truth."
4. **DisagreementSet** — every cell where A/B disagree, either is `UNGROUNDED`, an invariant fails, a basis span is missing, or null/non-null differs is routed to the adjudicator. Field-path-level granularity (`evidence[key].kind`, `per_issue[issue=damages].winner`) so list disagreements are not hidden inside list equality.
5. **10% agreed-cell audit overlay** — a deterministic 10% random sample of agreed cells is also surfaced to the adjudicator. The resulting `audit_flip_rate` is recorded in `LabelingProvenance` and is the single best operational signal that the LLM pair has a systematic bias.
6. **Human-only anchor set** — a stratified 10–20-case subset is labeled from scratch by the adjudicator without seeing either LLM output. Metrics are reported per anchor / LLM-assisted / combined splits; a combined-corpus calibration claim only lands if anchor divergence is below the pre-registered threshold (Brier delta ≤ 0.05 and no systematic winner-flip pattern).
7. **Adjudication log** at `docs/eval/reviewer-log.md` — one row per adjudicated `(case, field_path)` cell; rationale required.
8. **Real-gold append gate** at `packages/eval/auto_label/append_gate.py` refuses any row missing `labeling_provenance`, with `negative_kind` set, missing `target_source_id` or manifest fields, with incomplete MandatoryReviewSet coverage, or with missing/mismatched run-artifact hashes. Negative-set fixtures (`data/eval/negative_sets/*.jsonl`) never go through this gate.

`inter_model_agreement_rate` is **NOT Cohen's κ** and is not reported as one. It is raw operational telemetry only. The defensibility metrics are `mandatory_review_flip_rate`, `audit_flip_rate`, anchor-set divergence, and adjudication rate by field path.

This protocol pre-empts both the original thesis attack (*"the gold set is one paralegal's opinion"*) and the new attack the LLM-assisted shift introduces (*"you used LLMs to label the gold set used to evaluate your LLM predictor"*) — see [`decision-log.md`](decision-log.md) D-021 for the full counter-stack and rejected alternatives.

The CLI surface is two scripts:

- `scripts/eval/auto_label.py` runs the dual-LLM pass and writes a per-case run artifact under `data/eval_artifacts/labeling/<run_id>/<case_id>.json`. It refuses to write to `data/gold_standard/` and refuses to construct two labelers with the same provider.
- `scripts/eval/adjudicate.py` walks the MandatoryReviewSet, DisagreementSet, and audit overlay; on completion runs `assert_real_gold_appendable` and only on green-light appends one row to `data/gold_standard/<corpus>.jsonl` plus a reviewer-log entry.

Reviewer onboarding: see [`reviewer-guide.md`](reviewer-guide.md) (rewritten as adjudicator-only flow on 2026-05-03).

### 4.4 OCR provenance

Every annotated case carries `source_pdf_sha256` (so a second reviewer can independently re-fetch and verify) and an optional `ocr_confidence` (0–1) flag. Quotes, evidence items, and statutory references carry a structured `Provenance{page, paragraph, optional text_span}` rather than free-text "para 14" — this prevents fabricated references from validating ([SHA-100](https://linear.app/sharifbuilders/issue/SHA-100)).

## 5. Schema invariants

The `GoldCase` model enforces ten cross-field invariants. They are not bureaucratic; each one closes a specific failure mode that would silently corrupt downstream metrics.

| ID | Rule | Failure mode it closes |
|---|---|---|
| INV-1 | `decision_date` in [2019-01-01, 2024-12-31] | Out-of-window cases drift into the corpus |
| INV-2 | ≥1 tenant and ≥1 landlord | Annotator omits a party |
| INV-3 | `ocr_confidence ∈ [0,1]` when set | Garbage OCR confidence values |
| INV-4 | `source_pdf_sha256` matches `^[0-9a-f]{64}$` | Typos and case-mixed hex |
| INV-5 | Every `per_issue.issue` appears in `claimed_amounts` | Annotator drifts between the two issue lists |
| INV-6 | `total_awarded_gbp == sum(per_issue.awarded_gbp)` | Arithmetic typos at annotation time |
| INV-7 | `case_size == small` iff `disputed_amount_gbp <= £1500` | Stratification audit silently broken |
| INV-8 | `Decimal` amounts ≥ 0 | Sign errors |
| INV-9 | `overall_winner` agrees with `per_issue.winner` aggregate | Headline accuracy label silently wrong |
| INV-10 | Empty `evidence`/`statutory_basis` requires explicit `*_unavailable_reason` | Silent omission disguised as "no evidence" |

The full schema with rationale per invariant is in [`gold-schema.md`](gold-schema.md). The pre-publish failure-mode analysis is in `.sisyphus/codex/sha-28-schema-2026-04-27.md`.

## 6. Metrics

### 6.1 Issue-level winner accuracy

Fraction of predicted per-issue winners matching the ground-truth `IssueOutcome.winner`. Apportioned cases are scored per issue; unapportioned cases collapse to a single comparison via `overall_winner`. Missing per-issue predictions count as wrong (silence ≠ free pass).

```python
issue_winner_accuracy(gold, predictions) -> float
```

### 6.2 £-amount within threshold

Fraction of cases where `|predicted_total - actual_total| / actual_total <= threshold_pct`. Default threshold 0.20. Captures the magnitude of the prediction error, not just the direction.

```python
amount_within_threshold(gold, predictions, threshold_pct=0.20) -> float
```

### 6.3 Brier score

Mean of `(P(landlord wins) - actual_landlord_won)^2` over all per-issue pairs (or per-case, for unapportioned). Bounded `[0, 1]`. Perfect predictions score 0; a coin-flip predictor (always P=0.5) scores 0.25. Reference: Brier (1950) [^brier].

The thesis target Brier <0.20 is checked via the upper bound of the bootstrap CI (`brier_upper_95 < 0.20`), not the point estimate. CI guards against an examiner objection that the point estimate is unstable on n=50.

### 6.4 Expected Calibration Error (ECE)

```
ECE = Σ_b (n_b / N) · |accuracy_b − confidence_b|
```

where bin `b` collects predictions whose `win_probability` falls in the b'th of `n_bins` equal-width buckets, `accuracy_b` is the empirical share of landlord wins in that bucket, and `confidence_b` is the mean predicted probability. Reference: Naeini et al. (2015) [^ece].

ECE is reported alongside Brier because they answer different questions: Brier penalises both miscalibration and lack of resolution; ECE isolates the calibration error specifically. A model can have low Brier and high ECE (or vice-versa).

### 6.5 Reliability diagram

Bar plot of `accuracy_b` against the bin centre, with the `y = x` diagonal as the perfectly-calibrated reference. Bin sizes encoded as bar opacity. Saved as PNG via matplotlib's `Agg` backend (no display required).

### 6.6 Bootstrap confidence intervals (SHA-97)

Every metric is wrapped in `bootstrap_ci(metric_fn, gold, predictions, n_resamples=1000, seed=42)`. The implementation:

1. Resamples `(gold[i], predictions[i])` PAIRS with replacement (preserving case-level dependencies between issue-level pairs).
2. Recomputes `metric_fn` on each resample.
3. Returns `MetricResult(point, lower_95, upper_95, n, n_resamples)` where `lower_95` and `upper_95` are the 2.5th and 97.5th percentiles of the resample distribution.

A claim only "lands" in the thesis if its lower CI bound clears the headline target — see [`metrics.md`](metrics.md) §"Thesis-claim survival rule".

### 6.7 Phase 4b metrics (deferred)

| Metric | Reference | Linear |
|---|---|---|
| Citation precision / recall (NLI entailment) | ALCE [^alce] | [SHA-31](https://linear.app/sharifbuilders/issue/SHA-31) |
| Unsupported-claim rate | VeriCite [^vericite] | [SHA-31](https://linear.app/sharifbuilders/issue/SHA-31) |
| RAGAS faithfulness | Es et al. (2023) [^ragas] | [SHA-29](https://linear.app/sharifbuilders/issue/SHA-29) |
| RAGAS context precision/recall | Es et al. (2023) [^ragas] | [SHA-29](https://linear.app/sharifbuilders/issue/SHA-29) |
| RAGAS answer relevance | Es et al. (2023) [^ragas] | [SHA-29](https://linear.app/sharifbuilders/issue/SHA-29) |

These need transformer model checkpoints (DeBERTa-v3-mnli for NLI; sentence-transformer encoders for RAGAS) and are scoped to a separate Phase 4b PR. The `unsupported_claim_rate` metric also depends on the `atomic_claims` schema redesign ([SHA-94](https://linear.app/sharifbuilders/issue/SHA-94)).

## 7. Ablation methodology (Phase 5, SHA-32)

Four modes, evaluated on the same gold set:

| Mode | Context fed to the predictor |
|---|---|
| `rag-only` | Retrieved tribunal precedents (no KG) |
| `kg-only` | Built knowledge graph for the dispute (no precedent retrieval) |
| `hybrid` | Both — the production path |
| `llm-only` | No context at all (controls for raw LLM capability) |

Each mode produces a predictions JSONL. `python -m eval.ablate` (Phase 5) loads the gold set + every mode's predictions in one run, computes accuracy / amount-within-threshold / Brier / ECE per mode under bootstrap CIs, and emits a single `ComparisonReport` JSON for the thesis to consume.

### 7.1 Generating per-mode predictions (Phase 5b)

`scripts/eval/predict_all.py` produces the per-mode JSONLs that `eval.ablate` consumes. For each gold case it:

1. **Reconstructs a pre-decision `CaseFile`** (`eval.case_file_adapter.gold_case_to_case_file`) by stripping every post-decision artifact from the `GoldCase` — `ground_truth_outcome`, `key_reasoning_quotes`, the tribunal's `statutory_basis`, `cited_authorities`, and `decision_date`. Without this step the engine would see the verdict in the input.
2. **Aligns the issue vocabulary** (`eval.issue_alignment`). The eval `ClaimType` enum (annotator-facing) and the orchestrator `DisputeIssue` enum (intake-facing) overlap but aren't identical: `damages↔damage` (spelling), `deposit_non_protection↔deposit_protection` (eval names the breach, orch names the area), `disrepair`/`end_of_tenancy` are unmappable. Unmappables fall back to `DisputeIssue.OTHER`; the count is recorded on `LossyReconstruction.unmapped_claim_types` and surfaced in the runner summary so the alignment loss is reported alongside headline numbers. When the pre-decision `claimed_amounts` labels have a one-to-one shape with `claim_types`, the runner also maps the enum-style prediction label back to the gold free-text issue label before serialising, so per-issue metrics can join on the same label.
3. **Calls the predictor in each mode** — currently the deterministic `make_stub_prediction` (Phase 5b CI default), with a `--engine live` slot for the real `BaseLLMClient` once Phase 5c wires it.
4. **Adapts** orchestrator `PredictionResult` → eval `Prediction` (`eval.adapter.from_prediction_result`), applies any unambiguous gold issue-label map, and writes one JSONL row.

The Phase 5b end-to-end test (`packages/eval/tests/test_predict_all.py::TestOutputAblationCompatible`) exercises this exact chain on the synthetic 10-case fixture in CI — the same chain the thesis chapter (SHA-68) replays once a real corpus and real LLM run land.

### 7.2 Significance test

The hybrid > RAG-only and hybrid > KG-only claims (the thesis's headline novelty contributions) are ablation-runner outputs. The thesis-claim survival rule applies to the *difference* between two modes, not just the absolute number — a 2-point hybrid advantage with overlapping CIs is no thesis claim. Phase 5 ships `summarise_dominance(a, b)` which decides per-metric significance via non-overlapping bootstrap CIs (mirrored for lower-is-better metrics like Brier and ECE). See [`ablation.md`](ablation.md) for the worked example and [`decision-log.md`](decision-log.md) D-018 for the choice of CI overlap over paired hypothesis tests.

## 8. Reproducibility

### 8.1 Determinism

Every random operation (bootstrap resampling, audit sampling) takes a `seed` argument. Default seed `42`. Two invocations with identical `(corpus, predictions, seed)` produce byte-identical reports.

### 8.2 Versioning

The gold set is versioned in the filename: `data/gold_standard/housing_v1.jsonl`. Schema changes after `v1` is frozen require a `v2` migration; `v1` files remain readable by the loader (the `SchemaVersion` enum carries every accepted version, current and historical).

### 8.3 Evidence trail

Per-phase coverage and audit reports are committed at `.sisyphus/evidence/eval/`. CI nightly writes the per-day audit report to `.sisyphus/evidence/eval/audit_<YYYY-MM-DD>.json` via `PYTHONPATH=packages python -m eval.dataset audit ... --evidence`.

### 8.4 Reproducing every thesis number

The thesis-claim audit script (Phase 4b — `scripts/eval/thesis_audit.py`) reads every metric report under `eval/results/` and emits a list of which thesis claims survive their CIs. The list is committed alongside the corpus on every gold-set update. To reproduce the thesis numbers from a clean checkout:

```bash
git checkout <thesis-tag>
pip install -r requirements.txt
PYTHONPATH=packages python -m eval.dataset audit data/gold_standard/housing_v1.jsonl --strict
PYTHONPATH=packages python -m eval.run --metric accuracy --gold ... --predictions ... --seed 42 --out eval/results/accuracy.json
PYTHONPATH=packages python -m eval.run --metric brier    --gold ... --predictions ... --seed 42 --out eval/results/brier.json
PYTHONPATH=packages python -m eval.run --metric ece      --gold ... --predictions ... --seed 42 --out eval/results/ece.json
python scripts/eval/thesis_audit.py eval/results/  # Phase 4b
```

Output should match the committed reports byte-for-byte.

## 9. What is *not* claimed

Methodological honesty requires saying what the harness does not do.

- **No external benchmark comparison.** UK housing-tribunal cases are a niche corpus; no existing benchmark with comparable scope. We cannot say "we beat method X on dataset Y" because no Y exists. The ablation runner provides internal comparisons; external comparison is left to follow-up work.
- **n=50 is small.** Bootstrap CIs make the uncertainty visible rather than hiding it, but they do not make the corpus larger. The minimum-effective-n floor (set per stratum) prevents per-stratum claims with insufficient support.
- **OCR pipeline not evaluated.** The schema records `ocr_confidence` and `source_pdf_sha256` but does not measure OCR error rates against ground truth. OCR errors propagate into annotation errors which propagate into metric noise; we surface them via `ocr_confidence` for downstream filtering but do not isolate them.
- **No fairness audit yet.** [SHA-14](https://linear.app/sharifbuilders/issue/SHA-14) lists fairness across party representation, claim size, and region as eventual scope. Phase 4a does not implement this. The schema captures the necessary fields (`Party.represented`, `region`, `case_size`); the metric is a follow-up.
- **The hybrid pipeline is graded against itself.** RQ1's ablation comparison is internal: hybrid vs RAG-only vs KG-only vs LLM-only, all run by the same harness. We cannot rule out a confounder where both arms benefit equally from a shared component (e.g. retriever quality dominating both RAG-only and hybrid). Mitigation: the metric set is rich enough that a confounder visible in one metric is unlikely to be invisible in all four.

## 10. References

[^pilot]: PILOT temporal-split methodology, referenced in the interim report.

[^brier]: Brier, G. W. (1950). "Verification of forecasts expressed in terms of probability." *Monthly Weather Review*, 78(1), 1–3.

[^ece]: Naeini, M. P., Cooper, G. F., & Hauskrecht, M. (2015). "Obtaining well calibrated probabilities using Bayesian binning." *AAAI*.

[^alce]: Gao, T., Yen, H., Yu, J., & Chen, D. (2023). "Enabling large language models to generate text with citations." [arXiv:2305.14627](https://arxiv.org/abs/2305.14627).

[^vericite]: VeriCite (2025). "Post-hoc verification of generated citations." [arXiv:2510.11394](https://arxiv.org/html/2510.11394v1).

[^ragas]: Es, S., James, J., Espinosa-Anke, L., & Schockaert, S. (2023). "RAGAS: Automated evaluation of retrieval augmented generation." [arXiv:2309.15217](https://arxiv.org/abs/2309.15217).

Other sources used in design but not directly cited in metric implementations:

- TruLens RAG Triad — [https://www.trulens.org/getting_started/core_concepts/rag_triad/](https://www.trulens.org/getting_started/core_concepts/rag_triad/)
- ICAIL workshop on legal AI evaluation
