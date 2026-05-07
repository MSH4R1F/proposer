# Stream C: Prediction Path Swap (PR 4 + PR 5 + PR 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the prediction-path swap of the factor-proposition KG-controlled CBR-RAG architecture across three PRs: replace the deposit-centric `kg_facts.py` with domain-pack rendering (PR 4), introduce factor-constrained proposition retrieval with a separate counterexample pass (PR 5), and add an evidence-path validator that walks `EvidenceSpan → FactorAssertion → Proposition → OutcomeComponent` and forces unsupported claims to abstention (PR 6).

**Architecture:** Three PRs, sequenced PR 4 → PR 5 → PR 6 with intra-PR parallelization. Built on Stream A's `legal_core` foundation (`FactorAssertion`, `FactorValue`, `GraphQualityScore`) and Stream B's `domain_packs` (per-domain catalogs, retrieval profiles, gates, extractor strategies). Three runtime feature flags (`STREAM_C_PR4`, `STREAM_C_FACTOR_RETRIEVAL`, `STREAM_C_EVIDENCE_PATH_STRICT`) gate each PR for safe rollback. Net effect: kg_only and hybrid modes go from "deposit-centric 3-enum card + generic top-K retrieval + LLM-trust-based citation" to "per-domain factor card + factor-constrained comparator/counterexample retrieval + KG-chain-validated cite-or-abstain".

**Tech Stack:** Python 3.11+, Pydantic v2 (`>=2.5.0`), pytest, pytest-asyncio. Existing `anthropic` and `openai` SDKs. No new third-party dependencies.

**Spec reference:** [`docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md`](../specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md). Primary sections: §4 (FactorAssertion), §5 / §5.1 / §5.2 (core nodes), §6 (Domain Pack Contract), §8 / §8.1 / §8.2 / §8.3 (graph quality gate), §9 / §9.1 / §9.2 / §9.2.1 / §9.3 (factor-constrained retrieval), §10 (corpus proposition KG), §11 (authority hierarchy), §17.1–§17.8 (evaluation), §19 PR 4, PR 5, PR 6, §22 (Definition of Done).

**Predecessor work:** Stream A ([2026-05-06-stream-a-foundation-codex.md](2026-05-06-stream-a-foundation-codex.md)) and Stream B ([2026-05-06-stream-b-catalog-and-gold.md](2026-05-06-stream-b-catalog-and-gold.md)) merged via [proposer#36](https://github.com/MSH4R1F/proposer/pull/36). The B12 v2 IAA report ([`docs/eval/extractor_f1_reports/housing.repairs_social.v1-2026-05-07-gold-iaa-comparative.md`](../../eval/extractor_f1_reports/housing.repairs_social.v1-2026-05-07-gold-iaa-comparative.md)) shows 13/15 housing.repairs_social factors gate-countable with frontier extractors — Stream C is what lets that signal actually reach the prediction prompt and the retrieval path.

---

## Executive Scope

### What this plan ships

- **PR 4 — Replace global KG fact card** (≈14 tasks). Add `DomainPack` registry; per-pack `render_factor_card(case_graph) -> str`; wire into `issue_predictor.py` behind a feature flag; preserve `housing.deposit.v1` regression-clean; surface housing.repairs_social.v1's 15 factors in the kg_only / hybrid prompt; record graph-quality gate result on every prediction artifact.
- **PR 5 — Factor-constrained proposition retrieval** (≈14 tasks). New `factor_retrieval.py` and `comparator_pack.py` modules; load `RetrievalProfile` weights per domain; bucketed similarity for money/duration/date factors per §9.2.1; separate counterexample pass per §9.3; soft-flag abstention; `RetrievalStrategy.FACTOR_CONSTRAINED` mode in `prediction_engine_v2.py`; new retrieval-quality metrics in `eval.metrics`.
- **PR 6 — Evidence-path validator** (≈12 tasks). New `EvidencePathValidator` class with iterative BFS + cycle detection; new `legal_core` models for `EvidenceSpan`, `OutcomeComponent`, `ReasoningPath`; integration in `output_assembler.py` AFTER `CitationVerifier`; gate-pass-rate as first-class metric; counterfactual-sensitivity harness (not run in CI); two-slice metric reporting (full corpus + gate-passing subset).
- **Post-PR-6 ablation rerun** (≈3 tasks). 4-mode ablation against the housing.repairs_social.v1 gold corpus with frontier extractors; comparison report against Task 18 baseline; commit findings.

### What this plan does NOT do

- **Does not implement deterministic calculators** (`inspection_delay_calculator`, `repair_delay_calculator`, etc.) referenced in `extractor_strategy.yaml`. Those are PR 3a follow-up work; Stream C consumes whatever extractors land separately. If they're absent at run time, factor extraction yields `extraction_method == "llm_extracted"` factors which are correctly excluded from gate-counting per spec §4.1.
- **Does not extend domain coverage beyond housing.deposit.v1 + housing.repairs_social.v1.** Employment domain (PR 7-8b) is out of scope.
- **Does not redesign the Knowledge Graph node/edge model.** Stream A landed `FactorAssertion`/`FactorValue`/`GraphQualityScore`; Stream C adds `EvidenceSpan`, `OutcomeComponent`, `ReasoningPath` minimal stubs because the validator needs them. Richer graph reasoning is future work.
- **Does not delete `packages/llm_orchestrator/pipeline/kg_facts.py`** — replaces its rendering responsibility but keeps `derive_kg_facts(kg, issue_type) -> KGFacts` as a shared utility (one of the locked-in design decisions; see D1 below). Final deletion is a separate post-Stream-C cleanup PR after one release cycle.
- **Does not auto-tune retrieval weights.** Per spec §9.2 the weights are starting hyperparameters. Tuning happens on a held-out validation slice in a follow-up evaluation pass; Stream C just ships the defaults from `retrieval_profile.yaml`.

### Build sequence

```
Pre-PR-4 setup (legal_core stubs)
  ↓
PR 4-A (DomainPack registry + render_factor_card protocol)
  ↓
PR 4-B (deposit renderer)  ║  PR 4-C (repairs renderer)  ║  PR 5 stub work begins (against fake factor graphs)  ║  PR 6 stub work begins
  ↓                        ↓
PR 4-D (wire into issue_predictor.py behind STREAM_C_PR4 flag)
  ↓
PR 4-E (kg_facts.py shim + deprecation warning)
  ↓
PR 4 merges → smoke-test prompt diff against gold subset (no full ablation yet)
  ↓
PR 5 wiring (RetrievalStrategy.FACTOR_CONSTRAINED in prediction_engine_v2.py, behind STREAM_C_FACTOR_RETRIEVAL)
  ↓
PR 5 merges → integration smoke test (asserted_factors stub → no LLM-cost ablation)
  ↓
PR 6 wiring (EvidencePathValidator after CitationVerifier in output_assembler.py, audit-only mode default)
  ↓
PR 6 merges → end-to-end integration test (still no full ablation)
  ↓
Post-PR-6: full 4-mode ablation rerun (~£5 cost), comparative report, lock-in decisions
```

Per the risk analysis ([R-cross-1](#risk-register)) we deliberately do **not** run a full 4-mode ablation after each PR in isolation — the prompt change in PR 4 alone, the retrieval change in PR 5 alone, neither moves the needle measurably against the spec §17.1 statistical-power budget. We run one consolidated ablation after all three land.

---

## Hard Constraints

These apply across PR 4-6 collectively. Implementer/agent must respect them without waiting for explicit reminders.

1. **Leaf package discipline** (per Stream A's import boundary tests). `packages/legal_core/` MUST NOT import from `domain_core`, `domain_packs`, `rag_engine`, `kg_builder`, `llm_orchestrator`, `eval`, `scripts`, or `apps`. `packages/domain_core/` MUST NOT import from `domain_packs`, `rag_engine`, etc. `packages/domain_packs/` MAY import from `domain_core` and `legal_core` only. The hot-prediction packages (`llm_orchestrator/`, `eval/`) MAY import any of the leaf packages but the reverse is forbidden.

2. **Pydantic v2 idioms throughout.** `model_config = ConfigDict(extra="forbid", frozen=True)` on every new model. `field_validator` and `model_validator` from `pydantic`. Match the style in `packages/legal_core/graph/factor_assertion.py` and `packages/domain_packs/loaders.py`.

3. **Feature-flag every behaviour change.** Three env vars read at call time (NOT at module load time). Defaults chosen so a partial Stream C deploy is safe:
   - `STREAM_C_PR4="1"` (default) — turn off to revert `issue_predictor.py` to the legacy `_format_kg_fact_card` path.
   - `STREAM_C_FACTOR_RETRIEVAL="0"` (default; flip to `"1"` after PR 5 verified on a subset) — controls whether `prediction_engine_v2.py` uses the new factor-constrained retrieval or the existing `IssueRetriever`.
   - `STREAM_C_EVIDENCE_PATH_STRICT="0"` (default = audit-only mode; flip to `"1"` after PR 6 rejection-rate verified < 20%) — controls whether the validator merely logs rejections or forces them to abstention.

4. **TDD strictly.** Every behavioural change starts with a failing test. No implementation before the failing test. Tests use the existing fixture/mock patterns from `packages/llm_orchestrator/tests/test_prediction_engine_agentic.py` (scripted LLM client + fake RAG) and `packages/legal_core/tests/test_factor_assertion.py` (frozen-model construction tests).

5. **No real-money LLM calls in tests.** Always inject fakes. Real-LLM execution only happens at the post-PR-6 ablation rerun and that's a checkpoint task requiring user approval.

6. **No prompt regressions for `housing.deposit.v1`.** PR 4 must produce byte-equivalent prompt content for deposit cases when `STREAM_C_PR4=1`. Snapshot tests in `packages/llm_orchestrator/tests/test_kg_in_prompt_golden.py` are the gate.

7. **Do not delete `packages/llm_orchestrator/pipeline/kg_facts.py` in PR 4.** Replace its rendering responsibility but keep `derive_kg_facts(kg, issue_type) -> KGFacts` callable; PR 4 leaves a one-line shim with `DeprecationWarning`. Final deletion is post-Stream-C cleanup after one release cycle.

8. **Money is a typed value, not a node.** Per spec §5.2. PR 6's `OutcomeComponent`/`RemedyComponent` carry money via `money_minor_units: int + money_currency: Literal["GBP"]`, mirroring the Stream A `FactorValue` pattern.

9. **Two-slice reporting on every prediction-side metric.** PR 6 must emit metadata that lets evaluation slice on `kg_used_for_prediction == True` (gate-passing subset) vs full corpus. This is non-negotiable per spec §17.6.

10. **Cite-or-abstain enforcement at the validator layer, not just the prompt.** Per spec §1: "All material legal claims must be source-grounded or abstained." PR 6 enforces this structurally; PR 4 surfaces the metadata; PR 5 surfaces the comparator/counterexample pack.

11. **PageRank remains optional throughout PR 5.** Per spec §1 ("PageRank is an ablation signal, not the headline method") and §19 PR 5 ("PageRank remains optional"): PR 5 must NOT remove the existing `PersonalizedPageRank` class at `packages/llm_orchestrator/pipeline/proposition_retrieval.py:169-240` or its `use_pagerank: bool` parameter. The new `FactorRetriever` is an alternate retrieval path selected by `RetrievalStrategy.FACTOR_CONSTRAINED`; the existing `PROPOSITION_PAGERANK` strategy continues to work unchanged. Tests must verify that `RetrievalStrategy.PROPOSITION_PAGERANK` still routes through `PersonalizedPageRank` after PR 5 lands.

---

## Locked-in Design Decisions

The spec leaves several PR 4-6 implementation choices open. These are decided up front so the plan tasks can reference them without re-litigating:

**D1 — `kg_facts.py` deprecation is two-step.** PR 4 keeps `derive_kg_facts(kg, issue_type) -> KGFacts` as a shared utility (deposit case extraction logic) and replaces only the *string-rendering* call site. The dataclass `KGFacts` itself is preserved as the input type to `housing.deposit.v1.render_factor_card(kg_facts)`. A separate post-Stream-C PR (out of scope here) deletes both the dataclass and the `derive_*` helper once a more general extractor lands. This avoids the "rewrite everything at once" trap and keeps the deposit regression risk minimal.

**D2 — `DomainPack` lives at `packages/domain_packs/registry.py`.** New module sibling to `packages/domain_core/registry.py`. Provides `get_domain_pack(domain_id: str) -> DomainPack`. Imports from `domain_core` (for `DomainSpec`) and `legal_core` (for typed models). Does NOT touch `domain_core/registry.py`.

**D3 — `render_factor_card` signature is uniform.** `pack.render_factor_card(case_graph: Any) -> str`. The `case_graph` parameter is whatever the caller has at hand: today it's a `KGFacts` instance for deposit cases (post-`derive_kg_facts`); for repairs cases it's the full `KnowledgeGraph` with `FactorAssertion` nodes. Each pack adapts internally. Returns markdown string consumable by the existing `{kg_fact_card}` placeholder in `IRAC_USER_PROMPT` and `_format_repairs_user_prompt`.

**D4 — Per-pack renderers are co-located with YAMLs.** Each domain pack has a `renderer.py` next to its YAMLs. PR 4 creates:
- `packages/domain_packs/housing/deposit/renderer.py` (NEW deposit pack — currently the deposit logic lives in `kg_facts.py` only; PR 4 introduces a thin pack wrapper)
- `packages/domain_packs/housing/repairs_social/renderer.py`
The dispatcher in `packages/domain_packs/registry.py` returns the right `DomainPack` whose `.render_factor_card(case_graph)` method delegates to the per-pack `renderer.py`.

**D5 — PR 5 falls back to chunk-RAG when `asserted_factors == []`.** `factor_retrieval.py`'s controller returns an empty `ComparatorPack` and emits a `factor_retrieval_fallback` log event. The wrapping `PredictionEngineV2.predict()` notices the empty pack and falls through to the existing `IssueRetriever` (chunk-RAG) path. This degrades gracefully when the factor extractor hasn't populated assertions for a case; combined with `STREAM_C_FACTOR_RETRIEVAL=0` default, regression risk is minimal.

**D6 — PR 5 abstention is a soft flag, not hard `outcome=uncertain`.** Per spec §9.3 wording ("flagged for low-confidence / abstention review"). When `counterexample.abstain_if_none == True` and the counterexample pass returns 0, the `ComparatorPack`'s `counterexample_pass_metadata.abstention_recommended = True`. The downstream predictor (and PR 6's validator) decide whether to honour the flag. Hard `outcome=uncertain` only happens if the validator can't construct an evidence path, not on counterexample absence alone.

**D7 — PR 6's validator is a separate class, not a `CitationVerifier` extension.** New module `packages/llm_orchestrator/pipeline/evidence_path_validator.py`. Different unit of work: `CitationVerifier` checks `Citation` objects produced by the LLM; `EvidencePathValidator` walks the KG chain `EvidenceSpan → FactorAssertion → Proposition → OutcomeComponent`. They run sequentially in `output_assembler.py`: `CitationVerifier` first (existing), `EvidencePathValidator` second (new). This keeps each class small and testable.

**D8 — Build sequence: PR 4-A first, then parallel PR 4-B/C/PR 5/PR 6 stub work, then sequential PR 4-D/E/PR 5 wiring/PR 6 wiring.** Detailed in [Build Sequence](#build-sequence) below. Justification: PR 4-A defines the `DomainPack` API surface; once that's a one-hour task, B/C/PR 5/PR 6 can all develop in parallel against the API.

**D9 — Three feature flags, all read at call time.** Listed under hard constraint #3 above. Flags must be `os.getenv(...)` checks inside functions, not module-level constants — otherwise restart-required for changes.

**D10 — One ablation rerun, post-PR-6.** Not after each PR. Per spec §17.1 (statistical power), a 50-case 4-mode ablation can't reliably distinguish a 1-3pp prompt-only delta. Smoke-test prompt diffs after each PR; full ablation only when all three land.

**D11 — Pre-PR-4 setup task adds `EvidenceSpan`/`OutcomeComponent`/`ReasoningPath` stubs to `legal_core`.** PR 4 needs `EvidenceSpan` for the renderer to reference evidence. PR 5 extends the existing `Proposition` model in `packages/kg_builder/propositions/models.py` (the spec calls this `AtomicProposition` — implementation-side it's the existing `Proposition` class; PR 5 makes it richer). PR 6 uses all of them plus walks the `ReasoningPath` chain. Adding minimal frozen models up-front (just enough for type-checking) avoids forward-reference hell across the three PRs.

**Note on the `AtomicProposition` ↔ `Proposition` naming.** Spec §5 / §10 use the term `AtomicProposition` to emphasize the unit being a single quote-verified atomic claim. The implementation has lived as `Proposition` since the kg_builder.propositions module landed (pre-Stream-A). PR 5 extends the existing `Proposition` rather than introducing a parallel class — this is the simpler route and the rename is deferred to a future cleanup PR. Spec readers should mentally substitute the two terms.

**Note on `ComparatorCase`.** Spec §5 lists `ComparatorCase` as a core node type. Stream C does NOT introduce it as a standalone Pydantic model — instead, the existing `Proposition` (with the new `proposition_role: Literal["fact_comparator", ...]` field added in Task 5.4) carries the comparator-case role. A `ComparatorCase` view-model could be added later if downstream consumers want a typed projection, but it's out of scope for Stream C.

**D12 — Renderer signature is `render_factor_card(case_graph: Any, pack: DomainPack) -> str`** — pack is passed in so the renderer can read its own `factors.yaml` content (factor IDs, polarity labels, descriptions) without re-loading.

---

## Cross-PR Contracts

These are the type signatures that bind PR 4 / 5 / 6. Once pinned here, no PR may drift.

### Contract C1 — `DomainPack`

Defined in `packages/domain_packs/registry.py` (PR 4-A).

```python
@dataclass(frozen=True)
class DomainPack:
    """Bundle of domain pack YAMLs for a single domain.

    Loaded by get_domain_pack(domain_id). Each attribute is a frozen Pydantic
    v2 model from packages/domain_packs/loaders.py.
    """

    domain_id: str
    spec: DomainSpec  # from domain_core
    factors: FactorCatalog  # from domain_packs.loaders
    outcomes: OutcomeSchema
    remedies: RemedySchema
    retrieval_profile: RetrievalProfile
    graph_quality_gate: GraphQualityGate
    extractor_strategy: ExtractorStrategy
    annotation_rubric: str  # markdown content as a single string

    def render_factor_card(self, case_graph: Any) -> str:
        """Delegate to the pack's renderer.py module.

        For housing.deposit.v1, case_graph is expected to be a KGFacts instance
        (or anything with the same attributes); for housing.repairs_social.v1,
        case_graph is a KnowledgeGraph with FactorAssertion nodes.
        """
        ...

    def is_kg_usable(self, score: GraphQualityScore) -> bool:
        """Return True iff score passes this pack's graph_quality_gate thresholds.

        Per spec §8.1, thresholds live on the pack, not in shared core code.
        """
        ...
```

### Contract C2 — `ComparatorPack`

Defined in `packages/llm_orchestrator/pipeline/comparator_pack.py` (PR 5).

```python
class RankedProposition(BaseModel):
    """A proposition with its retrieval score and provenance."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposition_id: str
    case_reference: str
    text: str
    source_passage: str  # verbatim quote
    authority_level: Literal[
        "statute", "regulation", "official_guidance",
        "binding_precedent", "persuasive", "comparator",
    ]
    proposition_role: Literal[
        "legal_test", "factual_finding", "fact_comparator", "remedy_rationale",
    ]
    score: float = Field(ge=0.0, le=1.0)
    score_breakdown: Dict[str, float]


class ComparatorPassMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    n_retrieved: int
    weights_used: Dict[str, float]  # comparator_weights snapshot
    fallback_reason: Optional[str] = None  # set if factor_retrieval falls back


class CounterexamplePassMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    n_retrieved: int
    k_overlap_min: int
    abstention_recommended: bool


class ComparatorPack(BaseModel):
    """Output of factor-constrained retrieval per spec §9.3."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    comparators: List[RankedProposition]  # positive analogues
    counterexamples: List[RankedProposition]  # differential analogues
    comparator_pass_metadata: ComparatorPassMetadata
    counterexample_pass_metadata: CounterexamplePassMetadata
```

### Contract C3 — `RetrievalControlInput`

Defined in `packages/llm_orchestrator/pipeline/factor_retrieval.py` (PR 5).

```python
class RetrievalControlInput(BaseModel):
    """Input to the factor-constrained retrieval controller per spec §9.1."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_id: str
    claim_head_id: str
    issue_ids: List[str]
    asserted_factors: List[FactorAssertion]  # from legal_core
    target_outcomes: List[str]
    target_remedies: List[str]
    forum: str
    authority_policy: "AuthorityPolicy"
    retrieval_profile_id: str
```

### Contract C4 — `EvidencePathResult`

Defined in `packages/llm_orchestrator/pipeline/evidence_path_validator.py` (PR 6).

```python
class EvidencePathResult(BaseModel):
    """Validator output per OutcomeComponent claim."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome_component_id: str
    is_supported: bool
    chain: List[str]  # node ids: EvidenceSpan → FactorAssertion → Proposition → OutcomeComponent
    rejection_reason: Optional[str] = None  # set if is_supported=False
    abstention_required: bool  # is_supported=False AND STREAM_C_EVIDENCE_PATH_STRICT=1
```

### Contract C5 — Prediction artifact metadata schema

Every PR must emit metadata fields per spec §6 / §8.2 / §17.6 in the prediction artifact (the JSONL row written by `output_assembler.py`):

```json
{
  "core_schema": "legal.core.v1",
  "domain_pack": "housing.repairs_social.v1",
  "domain_pack_version": "2026_05_07",
  "factor_catalog_version": "<sha hash of factors.yaml>",
  "extractor_version": "<sha hash of extractor_strategy.yaml>",
  "retrieval_profile": "<sha hash of retrieval_profile.yaml>",
  "graph_quality_score": 0.76,
  "kg_used_for_prediction": true,
  "kg_fallback_mode": null,
  "kg_gate_failure_reasons": [],
  "comparator_pass_n_retrieved": 5,
  "counterexample_pass_n_retrieved": 2,
  "abstention_recommended": false,
  "evidence_path_results": [
    {"outcome_component_id": "...", "is_supported": true, "chain": [...]}
  ]
}
```

PR 4 lands `core_schema`, `domain_pack`, `factor_catalog_version`, `graph_quality_score`, `kg_used_for_prediction`, `kg_fallback_mode`, `kg_gate_failure_reasons`. PR 5 adds `retrieval_profile`, `comparator_pass_n_retrieved`, `counterexample_pass_n_retrieved`, `abstention_recommended`. PR 6 adds `evidence_path_results`. None override each other.

---

## Feature Flag Inventory

| Flag | Default | Module that reads it | Effect when `0` |
|---|---|---|---|
| `STREAM_C_PR4` | `1` | `issue_predictor.py:_predict_issue_no_rag` | Reverts to legacy `_format_kg_fact_card`; `domain_pack.render_factor_card` not called. |
| `STREAM_C_PR4_REPAIRS` | `1` | `housing/repairs_social/renderer.py` | Repairs renderer returns `""` (empty card); deposit renderer unaffected. |
| `STREAM_C_FACTOR_RETRIEVAL` | `0` | `prediction_engine_v2.py:predict` | New retrieval path skipped; existing `IssueRetriever` used. |
| `STREAM_C_EVIDENCE_PATH_STRICT` | `0` | `output_assembler.py:assemble` | Validator runs in audit-only mode (logs rejections, doesn't enforce abstention). |
| `STREAM_C_K_OVERLAP_MIN` | (read from YAML) | `factor_retrieval.py` | Override the per-domain `k_overlap_min` from `retrieval_profile.yaml`. |
| `STREAM_C_COUNTEREXAMPLE_ABSTAIN` | (read from YAML) | `factor_retrieval.py` | Override per-domain `abstain_if_none`; `0` = soft-flag only. |

All flags read via `os.getenv(name, default)` inside the relevant function (NOT at module top-level). Tests verify each flag's effect.

---

## File Structure

### Pre-PR-4 setup (legal_core stubs needed by PR 4-6)

- Create: `packages/legal_core/graph/evidence_span.py` — minimal frozen `EvidenceSpan` model
- Create: `packages/legal_core/graph/outcome_component.py` — minimal frozen `OutcomeComponent` + `RemedyComponent` models
- Create: `packages/legal_core/graph/reasoning_path.py` — minimal frozen `ReasoningPath` model
- Create: `packages/legal_core/tests/test_evidence_span.py`
- Create: `packages/legal_core/tests/test_outcome_component.py`
- Create: `packages/legal_core/tests/test_reasoning_path.py`
- Modify: `packages/legal_core/__init__.py` — re-export new types

### PR 4

- Create: `packages/domain_packs/registry.py` — `DomainPack` dataclass + `get_domain_pack(domain_id)` resolver
- Create: `packages/domain_packs/housing/deposit/__init__.py` — package marker
- Create: `packages/domain_packs/housing/deposit/renderer.py` — deposit renderer
- Create: `packages/domain_packs/housing/repairs_social/renderer.py` — repairs renderer
- Modify: `packages/domain_packs/__init__.py` — export `DomainPack`, `get_domain_pack`
- Modify: `packages/llm_orchestrator/pipeline/kg_facts.py` — keep `derive_kg_facts` and `KGFacts`, deprecate the rendering helper, add `DeprecationWarning`
- Modify: `packages/llm_orchestrator/pipeline/issue_predictor.py:1206-1237` — replace `_format_kg_fact_card` with `domain_pack.render_factor_card(case_graph)` behind `STREAM_C_PR4` flag
- Modify: `packages/llm_orchestrator/pipeline/prediction_engine_v2.py` — record `graph_quality_score` and `kg_used_for_prediction` in artifact
- Create: `packages/domain_packs/tests/test_registry.py`
- Create: `packages/domain_packs/tests/test_deposit_renderer.py`
- Create: `packages/domain_packs/tests/test_repairs_renderer.py`
- Modify: `packages/llm_orchestrator/tests/test_kg_fact_card.py` — update to exercise pack-based path; assert deposit renderer matches legacy output byte-for-byte
- Modify: `packages/llm_orchestrator/tests/test_kg_in_prompt_golden.py` — regenerate golden snapshots
- Create: `packages/llm_orchestrator/tests/test_issue_predictor_factor_card.py` — new snapshot tests for repairs prompt content
- Create: `packages/llm_orchestrator/tests/test_prediction_artifact_schema_stable.py` — Cross-PR Contract C5 regression: load a fixture artifact and assert the full Stream C metadata field set is present and typed correctly

### PR 5

- Create: `packages/llm_orchestrator/pipeline/comparator_pack.py` — `ComparatorPack`, `RankedProposition`, `ComparatorPassMetadata`, `CounterexamplePassMetadata`
- Create: `packages/llm_orchestrator/pipeline/factor_retrieval.py` — `FactorRetriever`, `RetrievalControlInput`, `AuthorityPolicy`
- Create: `packages/llm_orchestrator/pipeline/_factor_overlap.py` — bucketed similarity helpers (per spec §9.2.1)
- Modify: `packages/kg_builder/propositions/models.py` — extend `Proposition` with `factor_ids`, `outcome_component_ids`, `remedy_component_ids`, `claim_head_ids`, `authority_level`, `proposition_role` (additive, all defaulting to empty list / None)
- Modify: `packages/llm_orchestrator/pipeline/prediction_engine_v2.py` — add `RetrievalStrategy.FACTOR_CONSTRAINED`; route through `factor_retrieval.py` when `STREAM_C_FACTOR_RETRIEVAL=1`
- Modify: `packages/llm_orchestrator/pipeline/issue_predictor.py` — accept optional `ComparatorPack` and surface comparators + counterexamples in the prompt template
- Create: `packages/eval/metrics/retrieval_quality.py` — `retrieval_context_precision_at_k`, `retrieval_context_recall_at_k`, `citation_validity`
- Create: `packages/llm_orchestrator/tests/test_factor_overlap.py`
- Create: `packages/llm_orchestrator/tests/test_comparator_pack.py`
- Create: `packages/llm_orchestrator/tests/test_factor_retrieval.py`
- Create: `packages/llm_orchestrator/tests/test_factor_retrieval_integration.py` — exercises engine routing
- Create: `packages/eval/tests/test_retrieval_quality_metrics.py`
- Modify: `packages/kg_builder/tests/test_propositions_models.py` — coverage for new optional fields
- Modify: `packages/llm_orchestrator/tests/test_proposition_retrieval.py` — assert legacy path still works when `STREAM_C_FACTOR_RETRIEVAL=0`

### PR 6

- Create: `packages/llm_orchestrator/pipeline/evidence_path_validator.py` — `EvidencePathValidator`, `EvidencePathResult`
- Modify: `packages/llm_orchestrator/pipeline/output_assembler.py:574-594` — call validator after `CitationVerifier`, enforce abstention behind `STREAM_C_EVIDENCE_PATH_STRICT`
- Modify: `packages/llm_orchestrator/pipeline/citation_verifier.py` — small docstring update noting the validator runs after this class
- Create: `packages/eval/metrics/gate_pass_rate.py` — `gate_pass_rate(predictions: list) -> MetricResult`
- Create: `packages/eval/metrics/two_slice_reporter.py` — utility that splits a metric across full corpus + gate-passing subset
- Create: `packages/eval/metrics/counterfactual_sensitivity.py` — harness only (not invoked in CI)
- Create: `packages/llm_orchestrator/tests/test_evidence_path_validator.py`
- Create: `packages/llm_orchestrator/tests/test_evidence_path_validator_cycles.py` — cycle-detection unit tests
- Create: `packages/llm_orchestrator/tests/test_output_assembler_validator_wiring.py`
- Create: `packages/eval/tests/test_gate_pass_rate.py`
- Create: `packages/eval/tests/test_two_slice_reporter.py`
- Create: `packages/eval/tests/test_counterfactual_sensitivity.py`

### Post-PR-6 ablation rerun

- Create: `docs/eval/stream-c-ablation-2026-05-XX.md` — comparative report against Task 18 baseline
- Possibly modify: `scripts/eval/predict_all.py` — add `--use-stream-c` flag for explicit ablation control (or rely on env vars)

---

## Pre-PR-4 Setup Tasks

These create the `legal_core` stubs that PR 4-6 depend on for type-checking. Each is a small TDD task following Stream A's pattern at [packages/legal_core/graph/factor_assertion.py](../../packages/legal_core/graph/factor_assertion.py).

### Task 0.1 — `EvidenceSpan` model

**Files:**
- Create: `packages/legal_core/graph/evidence_span.py`
- Create: `packages/legal_core/tests/test_evidence_span.py`

- [ ] **Step 1 — Write the failing tests**

```python
# packages/legal_core/tests/test_evidence_span.py
"""Unit tests for EvidenceSpan."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from legal_core.graph.evidence_span import EvidenceSpan, EvidenceSourceKind


def test_minimum_valid_span():
    span = EvidenceSpan(
        evidence_span_id="span_1",
        source_kind=EvidenceSourceKind.USER_NARRATIVE,
        source_reference="tenant_narrative.txt",
        quote_text="The roof leaked from January 2026.",
    )
    assert span.evidence_span_id == "span_1"
    assert span.source_kind is EvidenceSourceKind.USER_NARRATIVE
    assert span.paragraph_range is None


def test_paragraph_range_round_trip():
    span = EvidenceSpan(
        evidence_span_id="span_2",
        source_kind=EvidenceSourceKind.OMBUDSMAN_DETERMINATION,
        source_reference="housing-ombudsman-202402569.txt",
        quote_text="The Landlord did not respond within ten working days.",
        paragraph_range="¶12-¶14",
    )
    assert span.paragraph_range == "¶12-¶14"


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        EvidenceSpan(
            evidence_span_id="span_3",
            source_kind=EvidenceSourceKind.USER_NARRATIVE,
            source_reference="x",
            quote_text="y",
            unexpected_field="oops",
        )


def test_frozen_after_construction():
    span = EvidenceSpan(
        evidence_span_id="span_4",
        source_kind=EvidenceSourceKind.USER_NARRATIVE,
        source_reference="x",
        quote_text="y",
    )
    with pytest.raises(ValidationError):
        span.quote_text = "modified"


def test_quote_text_must_be_non_empty():
    with pytest.raises(ValidationError):
        EvidenceSpan(
            evidence_span_id="span_5",
            source_kind=EvidenceSourceKind.USER_NARRATIVE,
            source_reference="x",
            quote_text="",
        )


def test_source_kind_enum_closed():
    valid = {k.value for k in EvidenceSourceKind}
    assert valid == {
        "user_narrative",
        "user_uploaded_document",
        "ombudsman_determination",
        "tribunal_decision",
        "statute",
        "guidance",
        "calculator_trace",
    }
```

- [ ] **Step 2 — Run, expect failure**

Run: `pytest packages/legal_core/tests/test_evidence_span.py -v`
Expected: import error for `legal_core.graph.evidence_span`.

- [ ] **Step 3 — Implement**

```python
# packages/legal_core/graph/evidence_span.py
"""EvidenceSpan: typed reference to a source-text span supporting a factor.

Per spec §5 + §17.6, every persisted FactorAssertion that isn't deterministic
must reference at least one EvidenceSpan via its supported_by list. The span
itself records the verbatim quote, source, and (optional) paragraph range so
the citation verifier (PR 6) can re-locate the evidence in the original text.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EvidenceSourceKind(str, Enum):
    """Closed enum of where evidence can come from."""

    USER_NARRATIVE = "user_narrative"
    USER_UPLOADED_DOCUMENT = "user_uploaded_document"
    OMBUDSMAN_DETERMINATION = "ombudsman_determination"
    TRIBUNAL_DECISION = "tribunal_decision"
    STATUTE = "statute"
    GUIDANCE = "guidance"
    CALCULATOR_TRACE = "calculator_trace"


class EvidenceSpan(BaseModel):
    """Typed reference to a span of source text. See spec §5."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_span_id: str
    source_kind: EvidenceSourceKind
    source_reference: str  # e.g. "tenant_narrative.txt" or case ID
    quote_text: str = Field(min_length=1)
    paragraph_range: Optional[str] = None  # e.g. "¶12-¶14"
```

- [ ] **Step 4 — Run, expect pass**

Run: `pytest packages/legal_core/tests/test_evidence_span.py -v`
Expected: all 6 tests pass.

- [ ] **Step 5 — Update package exports**

Edit `packages/legal_core/__init__.py` — add `from legal_core.graph.evidence_span import EvidenceSpan, EvidenceSourceKind`. Add both names to `__all__` in alphabetical order.

- [ ] **Step 6 — Verify import boundary still holds**

Run: `pytest packages/legal_core/tests/test_import_boundary.py -v`
Expected: pass (no new forbidden imports).

- [ ] **Step 7 — Commit**

```bash
git add packages/legal_core/graph/evidence_span.py \
        packages/legal_core/tests/test_evidence_span.py \
        packages/legal_core/__init__.py
git commit -m "feat(legal_core): add EvidenceSpan model

Typed reference to a source-text span supporting a FactorAssertion.
Enum-typed source_kind covers user narrative, uploaded documents,
Ombudsman determinations, tribunal decisions, statutes, guidance,
and calculator traces. Frozen + extra=forbid.

Required by Stream C PR 4 (renderer references), PR 5 (proposition
linkage), and PR 6 (validator chain start).

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §5"
```

### Task 0.2 — `OutcomeComponent` + `RemedyComponent` models

**Files:**
- Create: `packages/legal_core/graph/outcome_component.py`
- Create: `packages/legal_core/tests/test_outcome_component.py`

Same TDD pattern as Task 0.1. Two Pydantic models in one file:

`OutcomeComponent` fields:
- `outcome_component_id: str`
- `outcome_id: str` (references `OutcomeSchema.outcomes[].id` from Stream B)
- `domain_id: str`
- `claim_head_id: str`
- `confidence: float = Field(ge=0.0, le=1.0)`
- `supporting_factor_ids: List[str] = Field(default_factory=list)`
- `mitigating_factor_ids: List[str] = Field(default_factory=list)`
- `supported_by_propositions: List[str] = Field(default_factory=list)`

`RemedyComponent` fields:
- `remedy_component_id: str`
- `remedy_id: str` (references `RemedySchema.remedies[].id`)
- `domain_id: str`
- `claim_head_id: str`
- `confidence: float = Field(ge=0.0, le=1.0)`
- `money_minor_units: Optional[int] = Field(None, ge=0)`  # GBP pence
- `money_currency: Optional[Literal["GBP"]] = None`
- `supporting_factor_ids: List[str] = Field(default_factory=list)`
- `supported_by_propositions: List[str] = Field(default_factory=list)`

Required tests (full code in spec for each, mirroring the Stream A tests/factor_assertion.py pattern):
- minimum valid construction for both
- frozen + extra=forbid
- confidence in [0, 1]
- `RemedyComponent`: money_minor_units ≥ 0, GBP currency only
- `RemedyComponent`: model_validator — if `money_minor_units` is set, `money_currency` must also be set (and vice versa)
- both: empty default lists round-trip cleanly

Acceptance: ~10 tests pass; `legal_core.__init__.py` re-exports both. Single commit.

### Task 0.3 — `ReasoningPath` model

**Files:**
- Create: `packages/legal_core/graph/reasoning_path.py`
- Create: `packages/legal_core/tests/test_reasoning_path.py`

`ReasoningPath` fields (per spec §5):
- `reasoning_path_id: str`
- `outcome_component_id: str` — the outcome this path justifies
- `node_chain: List[str] = Field(min_length=2)`  # ordered node IDs: typically EvidenceSpan → FactorAssertion → Proposition → OutcomeComponent
- `edges_used: List[str] = Field(default_factory=list)`  # edge IDs from the KG
- `confidence: float = Field(ge=0.0, le=1.0)`

Required tests:
- Minimum valid construction (chain of 2)
- Chain length must be ≥ 2 (single node is not a "path")
- Frozen + extra=forbid
- Confidence in [0, 1]
- Node chain round-trips via JSON

Same TDD discipline as 0.1. Single commit.

### Task 0.4 — Verify all setup foundation tests pass together

- [ ] **Step 1 — Full legal_core test run**

Run: `pytest packages/legal_core/tests/ -v`
Expected: all tests pass (Stream A's existing + the 3 new test files).

- [ ] **Step 2 — Confirm imports work end-to-end**

Run:
```bash
./venv/bin/python -c "from legal_core import (
    EvidenceSpan, EvidenceSourceKind,
    OutcomeComponent, RemedyComponent,
    ReasoningPath,
    FactorAssertion, FactorValue,
)
print('imports ok')"
```
Expected: `imports ok`.

This closes Pre-PR-4 setup. PR 4 begins below.

---

## PR 4 — Replace global KG fact card

PR 4 lands the `DomainPack` registry, per-pack renderers, and rewires `issue_predictor.py` to call `pack.render_factor_card(case_graph)` instead of the static `_format_kg_fact_card` method. Behind `STREAM_C_PR4=1` (default) the new path is active; flip to `0` for emergency rollback.

### Task 4.1 — `DomainPack` dataclass

**Files:**
- Create: `packages/domain_packs/registry.py`
- Create: `packages/domain_packs/tests/test_registry.py`

- [ ] **Step 1 — Failing test**

```python
# packages/domain_packs/tests/test_registry.py
"""Unit tests for DomainPack registry."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain_packs.registry import (
    DomainPack,
    DomainPackNotFoundError,
    get_domain_pack,
)


def test_get_domain_pack_returns_pack_for_known_id():
    pack = get_domain_pack("housing.repairs_social.v1")
    assert pack.domain_id == "housing.repairs_social.v1"
    assert len(pack.factors.factors) == 15  # per Stream B catalog
    assert pack.outcomes.domain_id == "housing.repairs_social.v1"


def test_get_domain_pack_unknown_id_raises():
    with pytest.raises(DomainPackNotFoundError):
        get_domain_pack("nonexistent.domain.v99")


def test_domain_pack_is_frozen():
    pack = get_domain_pack("housing.repairs_social.v1")
    with pytest.raises((AttributeError, ValueError)):
        pack.domain_id = "modified"


def test_domain_pack_has_all_required_attrs():
    pack = get_domain_pack("housing.repairs_social.v1")
    for attr in (
        "domain_id", "spec", "factors", "outcomes", "remedies",
        "retrieval_profile", "graph_quality_gate", "extractor_strategy",
        "annotation_rubric",
    ):
        assert hasattr(pack, attr), f"missing attr: {attr}"


def test_render_factor_card_method_exists():
    pack = get_domain_pack("housing.repairs_social.v1")
    assert callable(pack.render_factor_card)


def test_is_kg_usable_method_exists():
    pack = get_domain_pack("housing.repairs_social.v1")
    assert callable(pack.is_kg_usable)


def test_loading_caches_per_domain_id():
    """Repeated lookup returns the same instance."""
    p1 = get_domain_pack("housing.repairs_social.v1")
    p2 = get_domain_pack("housing.repairs_social.v1")
    assert p1 is p2
```

- [ ] **Step 2 — Run, expect failure**

Run: `pytest packages/domain_packs/tests/test_registry.py -v`
Expected: `ImportError: cannot import name 'DomainPack' from 'domain_packs.registry'`.

- [ ] **Step 3 — Implement**

```python
# packages/domain_packs/registry.py
"""DomainPack registry: load and cache the bundled pack artefacts per domain.

Per spec §6 + Stream C design decision D2: this module sits alongside
domain_core.registry but is the canonical lookup for full domain packs
(catalog + outcomes + remedies + retrieval + gate + extractor + rubric).

Usage:
    from domain_packs.registry import get_domain_pack
    pack = get_domain_pack("housing.repairs_social.v1")
    card = pack.render_factor_card(case_graph)
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from domain_core.registry import get_domain_spec
from domain_core.spec import DomainSpec
from legal_core.graph.graph_quality import GraphQualityScore

from domain_packs.loaders import (
    ExtractorStrategy,
    FactorCatalog,
    GraphQualityGate,
    OutcomeSchema,
    RemedySchema,
    RetrievalProfile,
)


_PACK_ROOT = Path(__file__).resolve().parent


class DomainPackNotFoundError(Exception):
    """Raised when get_domain_pack is called with an unknown domain_id."""


# Domain ID → pack subdirectory mapping. The dotted form
# "housing.repairs_social.v1" maps to packages/domain_packs/housing/repairs_social/.
_KNOWN_PACK_DIRS: dict[str, Path] = {
    "housing.repairs_social.v1": _PACK_ROOT / "housing" / "repairs_social",
    "housing.deposit.v1": _PACK_ROOT / "housing" / "deposit",
}


@dataclass(frozen=True)
class DomainPack:
    """Bundle of domain pack YAMLs + rubric for a single domain."""

    domain_id: str
    spec: DomainSpec
    factors: FactorCatalog
    outcomes: OutcomeSchema
    remedies: RemedySchema
    retrieval_profile: RetrievalProfile
    graph_quality_gate: GraphQualityGate
    extractor_strategy: ExtractorStrategy
    annotation_rubric: str

    def render_factor_card(self, case_graph: Any) -> str:
        """Delegate to the per-pack renderer.py module.

        Per spec §19 PR 4: returns markdown string for the kg_fact_card
        slot in IRAC_USER_PROMPT and _format_repairs_user_prompt.
        """
        # Lazy import to avoid circular deps at module load
        import importlib

        # Map domain_id to the renderer module path.
        # housing.repairs_social.v1 -> domain_packs.housing.repairs_social.renderer
        family, sub_family, _version = self.domain_id.split(".")
        module_path = f"domain_packs.{family}.{sub_family}.renderer"
        renderer = importlib.import_module(module_path)
        return renderer.render_factor_card(case_graph, self)

    def is_kg_usable(self, score: GraphQualityScore) -> bool:
        """Check whether the graph quality score passes this pack's gate.

        Per spec §8.1: thresholds live on the domain pack, not in shared
        core code. Reads packages/domain_packs/<pack>/graph_quality_gate.yaml.
        """
        gate = self.graph_quality_gate
        return (
            score.evidence_backed_factor_count >= gate.evidence_backed_factor_count_min
            and score.dated_event_count >= gate.dated_event_count_min
            and score.issue_count >= gate.issue_count_min
            and score.outcome_or_remedy_candidate_count
                >= gate.outcome_or_remedy_candidate_count_min
            and score.unsupported_factor_rate <= gate.unsupported_factor_rate_max
            and score.source_span_coverage >= gate.source_span_coverage_min
            and score.contradiction_count <= gate.contradiction_count_max
        )


@lru_cache(maxsize=None)
def get_domain_pack(domain_id: str) -> DomainPack:
    """Resolve and cache the domain pack for `domain_id`.

    Raises DomainPackNotFoundError if the domain_id is not registered or
    its YAML files are not on disk.
    """
    if domain_id not in _KNOWN_PACK_DIRS:
        raise DomainPackNotFoundError(
            f"No domain pack registered for {domain_id!r}. "
            f"Known: {sorted(_KNOWN_PACK_DIRS)}"
        )

    pack_dir = _KNOWN_PACK_DIRS[domain_id]
    if not pack_dir.exists():
        raise DomainPackNotFoundError(
            f"Domain pack {domain_id!r} registered but directory missing: {pack_dir}"
        )

    spec = get_domain_spec(domain_id)
    factors = FactorCatalog.from_yaml(pack_dir / "factors.yaml")
    outcomes = OutcomeSchema.from_yaml(pack_dir / "outcomes.yaml")
    remedies = RemedySchema.from_yaml(pack_dir / "remedies.yaml")
    retrieval_profile = RetrievalProfile.from_yaml(pack_dir / "retrieval_profile.yaml")
    graph_quality_gate = GraphQualityGate.from_yaml(pack_dir / "graph_quality_gate.yaml")
    extractor_strategy = ExtractorStrategy.from_yaml(pack_dir / "extractor_strategy.yaml")
    rubric_path = pack_dir / "annotation_rubric.md"
    annotation_rubric = rubric_path.read_text(encoding="utf-8") if rubric_path.exists() else ""

    return DomainPack(
        domain_id=domain_id,
        spec=spec,
        factors=factors,
        outcomes=outcomes,
        remedies=remedies,
        retrieval_profile=retrieval_profile,
        graph_quality_gate=graph_quality_gate,
        extractor_strategy=extractor_strategy,
        annotation_rubric=annotation_rubric,
    )
```

- [ ] **Step 4 — Run, expect partial pass**

Run: `pytest packages/domain_packs/tests/test_registry.py -v`
Expected:
- 6 tests pass (registry lookup, unknown-domain error, frozen, attrs, methods exist, caching)
- The "renderer" test fails because `domain_packs.housing.repairs_social.renderer` doesn't exist yet

This is OK — the renderer module is Task 4.3.

- [ ] **Step 5 — Update package exports**

Edit `packages/domain_packs/__init__.py`:
```python
"""domain_packs: per-domain pack registry and renderers.

Public API:
    from domain_packs import DomainPack, get_domain_pack, DomainPackNotFoundError
"""

from domain_packs.registry import DomainPack, DomainPackNotFoundError, get_domain_pack

__all__ = ["DomainPack", "DomainPackNotFoundError", "get_domain_pack"]
```

- [ ] **Step 6 — Commit**

```bash
git add packages/domain_packs/registry.py \
        packages/domain_packs/__init__.py \
        packages/domain_packs/tests/test_registry.py
git commit -m "feat(domain_packs): add DomainPack registry with get_domain_pack()

Per spec §6 + Stream C D2: new packages/domain_packs/registry.py providing
DomainPack frozen dataclass that bundles factors+outcomes+remedies+
retrieval_profile+graph_quality_gate+extractor_strategy+annotation_rubric
for a single domain_id. get_domain_pack(domain_id) is lru_cache-d.
.render_factor_card(case_graph) delegates to per-pack renderer.py.
.is_kg_usable(score) implements the §8.1 gate thresholds.

Renderer module is Task 4.3; this PR's first task lands the registry only.

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §6, §8.1"
```

### Task 4.2 — `housing.deposit.v1` pack scaffolding + renderer

**Files:**
- Create: `packages/domain_packs/housing/deposit/__init__.py`
- Create: `packages/domain_packs/housing/deposit/factors.yaml` — minimal 3-factor pack mirroring the existing kg_facts.py logic
- Create: `packages/domain_packs/housing/deposit/outcomes.yaml`
- Create: `packages/domain_packs/housing/deposit/remedies.yaml`
- Create: `packages/domain_packs/housing/deposit/retrieval_profile.yaml`
- Create: `packages/domain_packs/housing/deposit/graph_quality_gate.yaml`
- Create: `packages/domain_packs/housing/deposit/extractor_strategy.yaml`
- Create: `packages/domain_packs/housing/deposit/annotation_rubric.md`
- Create: `packages/domain_packs/housing/deposit/renderer.py`
- Create: `packages/domain_packs/tests/test_deposit_renderer.py`

The deposit pack currently has NO YAMLs (only Stream B's `housing.repairs_social.v1` pack does). PR 4 introduces a thin deposit pack so the registry can find it. The factor catalog mirrors the existing 3 deposit-specific facts:

- [ ] **Step 1 — Write deposit YAMLs**

`factors.yaml`:
```yaml
# housing.deposit.v1 — minimal v1 catalog (mirrors legacy kg_facts.py)
domain_id: housing.deposit.v1
factors:
  - id: deposit_protection_status
    value_type: enum
    polarity: pro_claimant
    requires_evidence: true
    enum_values: [not_protected, protected_late, protected_on_time, unknown]
    maps_to_outcomes: [tenant_wins_protection_breach, landlord_wins, split]
    description: Whether deposit was protected in a TDP scheme on time, late, or never.

  - id: prescribed_information_status
    value_type: enum
    polarity: pro_claimant
    requires_evidence: true
    enum_values: [not_provided, provided_late, provided_on_time, unknown]
    maps_to_outcomes: [tenant_wins_protection_breach, landlord_wins, split]
    description: Whether prescribed information was given on time, late, or never.

  - id: check_in_inventory_baseline
    value_type: enum
    polarity: pro_respondent
    requires_evidence: true
    enum_values: [present, absent, unknown]
    maps_to_outcomes: [tenant_wins_damages, landlord_wins, split]
    description: Whether a check-in inventory exists as a baseline for damage claims.
```

`outcomes.yaml`:
```yaml
domain_id: housing.deposit.v1
outcomes:
  - id: tenant_wins_protection_breach
    description: Tenant wins on TDP protection breach grounds.
  - id: tenant_wins_damages
    description: Tenant wins on damage/cleaning claims.
  - id: landlord_wins
    description: Landlord successfully defends claim.
  - id: split
    description: Mixed outcome with partial recovery for both parties.
```

`remedies.yaml`:
```yaml
domain_id: housing.deposit.v1
remedies:
  - id: deposit_return_full
    description: Full deposit returned to tenant.
  - id: deposit_return_partial
    description: Partial deposit returned to tenant.
  - id: deposit_retained_landlord
    description: Landlord retains deposit.
  - id: tdp_penalty_award
    description: 1x-3x deposit penalty awarded to tenant.
```

`retrieval_profile.yaml` — copy structure from Stream B's housing.repairs_social.v1 with same default weights (per spec §9.2 starting hyperparameters), counterexample config (n=2, k_overlap_min=2 — lower than repairs because deposit has fewer factors), bucket definitions same.

`graph_quality_gate.yaml` — per Stream A spec §8.1 deposit thresholds (lower because deposit cases have fewer factors):
```yaml
domain_id: housing.deposit.v1
evidence_backed_factor_count_min: 2
dated_event_count_min: 2
issue_count_min: 1
outcome_or_remedy_candidate_count_min: 1
unsupported_factor_rate_max: 0.30
source_span_coverage_min: 0.80
contradiction_count_max: 0
notes:
  - "Deposit cases have fewer factors than repairs; threshold reflects that."
```

`extractor_strategy.yaml` — all three deposit factors as `deterministic` (the existing `derive_kg_facts` logic IS deterministic, reading dates from `LeaseNode`):
```yaml
domain_id: housing.deposit.v1
entries:
  - factor_id: deposit_protection_status
    strategy: deterministic
    calculator_id: deposit_protection_calculator
    verifier_required: false
    gate_counted: true
    min_confidence_threshold: 1.0

  - factor_id: prescribed_information_status
    strategy: deterministic
    calculator_id: prescribed_information_calculator
    verifier_required: false
    gate_counted: true
    min_confidence_threshold: 1.0

  - factor_id: check_in_inventory_baseline
    strategy: deterministic
    calculator_id: inventory_baseline_calculator
    verifier_required: false
    gate_counted: true
    min_confidence_threshold: 1.0
```

`annotation_rubric.md` — minimal stub (3 sections, factor IDs as H2 headings, mirroring Stream B's structure but with deposit-specific operational definitions). ≥800 chars total to satisfy the existing rubric-coverage test pattern.

`__init__.py` — empty marker.

- [ ] **Step 2 — Failing test**

```python
# packages/domain_packs/tests/test_deposit_renderer.py
"""Tests for housing.deposit.v1 renderer.

Critical regression guard: the deposit renderer MUST produce byte-equivalent
output to the legacy IssuePredictor._format_kg_fact_card(kg_facts) for the
same input. Stream C PR 4 D6 hard requirement.
"""

from __future__ import annotations

import pytest

from domain_packs.registry import get_domain_pack
from llm_orchestrator.pipeline.kg_facts import KGFacts


def test_renderer_loads_via_pack():
    pack = get_domain_pack("housing.deposit.v1")
    assert pack.domain_id == "housing.deposit.v1"
    assert callable(pack.render_factor_card)


def test_renderer_returns_empty_for_all_unknown():
    pack = get_domain_pack("housing.deposit.v1")
    card = pack.render_factor_card(KGFacts())  # all-unknown defaults
    assert card == ""


def test_renderer_returns_empty_for_none():
    pack = get_domain_pack("housing.deposit.v1")
    card = pack.render_factor_card(None)
    assert card == ""


def test_renderer_renders_late_protection_with_days():
    pack = get_domain_pack("housing.deposit.v1")
    facts = KGFacts(
        deposit_protection_status="protected_late",
        deposit_scheme="DPS",
        deposit_late_by_days=90,
    )
    card = pack.render_factor_card(facts)
    assert "KEY KG FACTS" in card
    assert "deposit_protection_status: protected_late" in card
    assert "DPS" in card
    assert "90" in card


def test_renderer_renders_not_protected():
    pack = get_domain_pack("housing.deposit.v1")
    facts = KGFacts(deposit_protection_status="not_protected")
    card = pack.render_factor_card(facts)
    assert "deposit_protection_status: not_protected" in card
    assert "scheme:" not in card  # not_protected has no scheme info
    assert "late by" not in card


def test_renderer_renders_prescribed_info_late():
    pack = get_domain_pack("housing.deposit.v1")
    facts = KGFacts(
        prescribed_information_status="provided_late",
        prescribed_late_by_days=45,
    )
    card = pack.render_factor_card(facts)
    assert "prescribed_information_status: provided_late" in card
    assert "45" in card


def test_renderer_renders_inventory_absent():
    pack = get_domain_pack("housing.deposit.v1")
    facts = KGFacts(check_in_inventory_baseline="absent")
    card = pack.render_factor_card(facts)
    assert "check_in_inventory_baseline: absent" in card


def test_renderer_byte_equivalent_to_legacy_format():
    """The deposit renderer MUST produce byte-equivalent output to the
    legacy IssuePredictor._format_kg_fact_card method for any input."""
    from llm_orchestrator.pipeline.issue_predictor import IssuePredictor

    pack = get_domain_pack("housing.deposit.v1")

    test_cases = [
        KGFacts(),
        KGFacts(deposit_protection_status="not_protected"),
        KGFacts(
            deposit_protection_status="protected_late",
            deposit_scheme="MyDeposits",
            deposit_late_by_days=30,
        ),
        KGFacts(
            deposit_protection_status="protected_on_time",
            prescribed_information_status="provided_late",
            prescribed_late_by_days=14,
            check_in_inventory_baseline="present",
        ),
    ]

    for facts in test_cases:
        new_card = pack.render_factor_card(facts)
        legacy_card = IssuePredictor._format_kg_fact_card(facts)
        assert new_card == legacy_card, (
            f"Renderer drift on {facts!r}:\n"
            f"  new:    {new_card!r}\n"
            f"  legacy: {legacy_card!r}"
        )
```

- [ ] **Step 3 — Run, expect failure**

Run: `pytest packages/domain_packs/tests/test_deposit_renderer.py -v`
Expected: import error for `domain_packs.housing.deposit.renderer`.

- [ ] **Step 4 — Implement renderer**

```python
# packages/domain_packs/housing/deposit/renderer.py
"""housing.deposit.v1 factor card renderer.

Mirrors the legacy IssuePredictor._format_kg_fact_card byte-for-byte to
preserve the deposit regression suite. Will be replaced by a more general
renderer once kg_facts.py is fully deprecated (post-Stream-C cleanup PR).
"""

from __future__ import annotations

from typing import Any


def render_factor_card(case_graph: Any, pack: Any) -> str:
    """Render the deposit factor card.

    case_graph: a KGFacts instance (or None / instance with all-unknown values).
    pack: the DomainPack (unused here; signature uniformity).
    """
    # Mirror legacy logic from issue_predictor.py:1206-1237.
    # Importing here (not at module top) to keep this renderer side-effect-free
    # at module load.
    from llm_orchestrator.pipeline.kg_facts import KGFacts

    if case_graph is None or not isinstance(case_graph, KGFacts):
        return ""
    if case_graph.is_empty():
        return ""

    lines: list[str] = ["KEY KG FACTS (typed):"]

    if case_graph.deposit_protection_status != "unknown":
        line = f"- deposit_protection_status: {case_graph.deposit_protection_status}"
        if case_graph.deposit_scheme:
            line += f" (scheme: {case_graph.deposit_scheme})"
        if case_graph.deposit_late_by_days is not None:
            line += f" (late by {case_graph.deposit_late_by_days} days)"
        lines.append(line)

    if case_graph.prescribed_information_status != "unknown":
        line = f"- prescribed_information_status: {case_graph.prescribed_information_status}"
        if case_graph.prescribed_late_by_days is not None:
            line += f" (late by {case_graph.prescribed_late_by_days} days)"
        lines.append(line)

    if case_graph.check_in_inventory_baseline != "unknown":
        lines.append(
            f"- check_in_inventory_baseline: {case_graph.check_in_inventory_baseline}"
        )

    if len(lines) == 1:
        return ""  # only the header — nothing to say

    return "\n".join(lines)
```

- [ ] **Step 5 — Run, expect pass**

Run: `pytest packages/domain_packs/tests/test_deposit_renderer.py -v`
Expected: all 8 tests pass, especially the byte-equivalence test.

- [ ] **Step 6 — Commit**

```bash
git add packages/domain_packs/housing/deposit/ \
        packages/domain_packs/tests/test_deposit_renderer.py
git commit -m "feat(domain_packs/deposit): add housing.deposit.v1 pack + renderer

PR 4 Task 4.2: introduce a thin deposit pack so the DomainPack registry
can find it. 3-factor catalog mirrors the legacy kg_facts.py logic.
Renderer is byte-equivalent to IssuePredictor._format_kg_fact_card —
deposit regression suite must be preserved per Stream C hard constraint #6.

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §19 PR 4"
```

### Task 4.3 — `housing.repairs_social.v1` renderer

**Files:**
- Create: `packages/domain_packs/housing/repairs_social/renderer.py`
- Create: `packages/domain_packs/tests/test_repairs_renderer.py`

The repairs renderer is the *new* thing PR 4 introduces. It receives a `KnowledgeGraph` with `FactorAssertion` nodes and renders a compact markdown card listing each gate-countable factor with its value, evidence-span ID(s), and confidence. Factors with `requires_human_review=True` render with a `(uncertain)` badge and are excluded from the gate count.

- [ ] **Step 1 — Failing tests**

Write `packages/domain_packs/tests/test_repairs_renderer.py` covering:

1. `test_renderer_returns_empty_when_no_factor_assertions` — empty KG → `""`.
2. `test_renderer_returns_empty_when_kg_none` — `None` input → `""`.
3. `test_renderer_renders_single_boolean_factor_with_evidence` — KG with one `FactorAssertion(factor_id="inspection_offered", value=FactorValue(boolean=True), supported_by=["span_1"], confidence=0.92)` → card contains "inspection_offered: True", "evidence: span_1", "confidence: 0.92".
4. `test_renderer_renders_numeric_factor_with_bucket_label` — `FactorAssertion(factor_id="inspection_delay_days", value=FactorValue(number=90.0), ...)` → card contains "inspection_delay_days: 90 days (bucket: 30-90d)" using bucket definitions from the pack's `retrieval_profile.yaml`.
5. `test_renderer_renders_money_factor_with_pence_to_pounds` — `FactorValue(money_minor_units=12345, money_currency="GBP")` → "£123.45".
6. `test_renderer_renders_enum_factor` — `impact_severity_reported` with enum=`severe` → "impact_severity_reported: severe".
7. `test_renderer_excludes_requires_human_review_factors_from_main_block` — factor with `requires_human_review=True` renders in a separate "Uncertain (excluded from gate)" section.
8. `test_renderer_omits_factors_not_in_pack_catalog` — `FactorAssertion` whose `factor_id` isn't in `pack.factors.factors` → silently dropped, log warning.
9. `test_renderer_uses_pack_polarity_to_label` — pack defines polarity = `pro_claimant`; renderer adds "(favours resident)" surface label per the deposit pack convention; `pro_respondent` → "(favours landlord)"; `neutral` → no label.
10. `test_renderer_total_size_under_2000_chars_for_15_factor_case` — full 15-factor case with all factors populated → card stays under 2000 chars (prompt-budget hygiene).
11. `test_renderer_emits_no_unresolved_format_placeholders` — output contains no `{...}` substrings (would crash `.format(**prompt_kwargs)` per risk R-PR4-2).

- [ ] **Step 2 — Run, expect failure**

Run: `pytest packages/domain_packs/tests/test_repairs_renderer.py -v`
Expected: import error.

- [ ] **Step 3 — Implement**

`packages/domain_packs/housing/repairs_social/renderer.py`:

```python
"""housing.repairs_social.v1 factor card renderer.

Reads FactorAssertion nodes from the case_graph, dispatches on value_type,
applies bucket labels for numeric/money/duration via the pack's
retrieval_profile bucket_definitions, and surfaces polarity as a
domain-aware surface label (favours resident / favours landlord).

Per spec §17.6: factors with requires_human_review=True render in a
separate "Uncertain (excluded from gate)" section.

Per Stream C hard constraint #11 + R-PR4-2: the output is NEVER allowed
to contain unescaped `{` or `}` braces (would crash IRAC_USER_PROMPT.format).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable, List

logger = logging.getLogger(__name__)


# Domain-specific surface labels. The abstract polarity enum
# (pro_claimant / pro_respondent / neutral) maps to these in the prompt.
_POLARITY_SURFACE_LABEL = {
    "pro_claimant": "favours resident",
    "pro_respondent": "favours landlord",
    "neutral": "",
}

_HEADER_MAIN = "KEY FACTORS (factor-graph derived):"
_HEADER_UNCERTAIN = "Uncertain (excluded from gate):"


def render_factor_card(case_graph: Any, pack: Any) -> str:
    """Render the housing.repairs_social.v1 factor card.

    case_graph: a KnowledgeGraph (or KnowledgeGraph-like) with a
        `factor_assertions` attribute holding a list of FactorAssertion
        objects from legal_core.
    pack: the DomainPack instance (provides factors.yaml + bucket defs).

    Returns markdown-friendly string for the {kg_fact_card} prompt slot.
    Returns empty string for any of: kill switch, missing graph, no
    renderable factor assertions.
    """
    # Kill switch
    if os.getenv("STREAM_C_PR4_REPAIRS", "1") == "0":
        return ""

    # Defensive: handle missing/empty graph
    if case_graph is None:
        return ""
    factor_assertions = getattr(case_graph, "factor_assertions", None)
    if not factor_assertions:
        return ""

    # Build O(1) catalog lookup
    factor_id_to_entry = {f.id: f for f in pack.factors.factors}

    # Bucket definitions for numeric/money/duration rendering
    bucket_defs = pack.retrieval_profile.bucket_definitions

    main_lines: List[str] = []
    uncertain_lines: List[str] = []

    for fa in factor_assertions:
        catalog_entry = factor_id_to_entry.get(fa.factor_id)
        if catalog_entry is None:
            logger.warning(
                "factor_assertion_not_in_catalog",
                extra={"factor_id": fa.factor_id, "domain_id": pack.domain_id},
            )
            continue

        rendered_value = _render_value(fa, bucket_defs)
        polarity_label = _POLARITY_SURFACE_LABEL.get(catalog_entry.polarity, "")
        polarity_paren = f" ({polarity_label})" if polarity_label else ""
        evidence_csv = ", ".join(fa.supported_by) if fa.supported_by else "—"

        line = (
            f"- {fa.factor_id}: {rendered_value}{polarity_paren} "
            f"[confidence: {fa.confidence:.2f}, evidence: {evidence_csv}]"
        )

        if fa.requires_human_review:
            uncertain_lines.append(line)
        else:
            main_lines.append(line)

    if not main_lines and not uncertain_lines:
        return ""

    sections: List[str] = []
    if main_lines:
        sections.append(_HEADER_MAIN)
        sections.extend(main_lines)
    if uncertain_lines:
        if sections:
            sections.append("")  # blank separator
        sections.append(_HEADER_UNCERTAIN)
        sections.extend(uncertain_lines)

    rendered = "\n".join(sections)

    # Hard guard: no unescaped format-string placeholders allowed
    # (would crash IRAC_USER_PROMPT.format(**prompt_kwargs) downstream).
    # If a factor description contains literal { or }, escape by doubling.
    rendered = rendered.replace("{", "{{").replace("}", "}}")
    return rendered


def _render_value(fa, bucket_defs) -> str:
    """Dispatch on value_type. Numeric/money/duration include bucket label."""
    vt = fa.value_type
    val = fa.value  # FactorValue from legal_core

    if vt == "boolean":
        return "True" if val.boolean else "False"

    if vt == "enum":
        return str(val.enum)

    if vt == "number":
        n = val.number
        return f"{n:g}"

    if vt == "money":
        # Stream A FactorValue stores money_minor_units (GBP pence).
        pence = val.money_minor_units or 0
        pounds = pence / 100.0
        bucket = _money_bucket_label(pence, bucket_defs.money.bucket_edges_pence)
        return f"£{pounds:.2f} (bucket: {bucket})"

    if vt == "date":
        return val.date.isoformat() if val.date else "unknown"

    if vt == "duration":
        days = val.duration_days or 0
        bucket = _duration_bucket_label(days, bucket_defs.duration.bucket_edges_days)
        return f"{days} days (bucket: {bucket})"

    # Defensive default (unknown value_type)
    return "unknown"


def _money_bucket_label(pence: int, edges: List[int]) -> str:
    """Return human-readable bucket label like '£100-£500' or '>£10k'."""
    # edges from retrieval_profile.yaml: e.g. [0, 10000, 50000, 200000, 1000000]
    for i, edge in enumerate(edges[:-1]):
        next_edge = edges[i + 1]
        if edge <= pence < next_edge:
            return f"£{edge//100}-£{next_edge//100}"
    if pence >= edges[-1]:
        return f">£{edges[-1]//100}"
    return "<£0"


def _duration_bucket_label(days: int, edges: List[int]) -> str:
    """Return human-readable bucket label like '7-30d' or '>365d'."""
    # edges from retrieval_profile.yaml: e.g. [1, 7, 30, 90, 365]
    for i, edge in enumerate(edges[:-1]):
        next_edge = edges[i + 1]
        if edge <= days < next_edge:
            return f"{edge}-{next_edge}d"
    if days >= edges[-1]:
        return f">{edges[-1]}d"
    return f"<{edges[0]}d"
```

- [ ] **Step 4 — Run, expect pass**

Run: `pytest packages/domain_packs/tests/test_repairs_renderer.py -v`
Expected: 11 tests pass.

- [ ] **Step 5 — Commit**

```bash
git add packages/domain_packs/housing/repairs_social/renderer.py \
        packages/domain_packs/tests/test_repairs_renderer.py
git commit -m "feat(domain_packs/repairs_social): add render_factor_card

PR 4 Task 4.3: per-factor renderer for housing.repairs_social.v1.
Reads FactorAssertion nodes from the case_graph, dispatches on
value_type, applies bucket labels for numeric/money/duration via the
pack's retrieval_profile bucket_definitions, and surfaces polarity as
a domain-aware surface label (favours resident / favours landlord).

Factors with requires_human_review=True render in a separate section
and are excluded from gate counting per spec §17.6.

STREAM_C_PR4_REPAIRS=0 kill switch returns empty card.

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §19 PR 4"
```

### Task 4.4 — Wire `pack.render_factor_card` into `issue_predictor.py`

**Files:**
- Modify: `packages/llm_orchestrator/pipeline/issue_predictor.py:1206-1237` (`_format_kg_fact_card` method)
- Modify: `packages/llm_orchestrator/pipeline/issue_predictor.py:113-315` (`_predict_issue_no_rag` method — KG_ONLY / LLM_ONLY paths at lines 192 and 258)
- Modify: `packages/llm_orchestrator/pipeline/issue_predictor.py:499-560` (the main `_predict_issue` method — HYBRID / RAG_ONLY paths; line 499 is a THIRD `_format_kg_fact_card` call site that the audit caught)
- Modify: `packages/llm_orchestrator/tests/test_kg_fact_card.py` — update for pack-based path

This is the hot-path change. Behind `STREAM_C_PR4=1` (default), the predictor calls `pack.render_factor_card(case_graph)`; behind `STREAM_C_PR4=0`, it calls the existing `_format_kg_fact_card(kg_facts)`.

**Critical correctness:** the spec §19 PR 4 acceptance criterion "RAG-only hides factor card" requires the kg_fact_card variable to be `""` when `prompt_mode == "rag_only"` — currently line 499 in `_predict_issue` calls `_format_kg_fact_card` *unconditionally*, populating `kg_fact_card` for both hybrid AND rag_only paths, and the prompt template at line 518 includes it whenever non-empty. PR 4 must add the `prompt_mode != "rag_only"` gate at line 499 and add a test that asserts the full prompt for `prompt_mode="rag_only"` contains no "KEY KG FACTS" or "KEY FACTORS" headers.

- [ ] **Step 1 — Failing tests** in `test_kg_fact_card.py`

Add new tests that assert pack-based dispatch:

```python
def test_predictor_uses_pack_renderer_when_flag_set(monkeypatch):
    monkeypatch.setenv("STREAM_C_PR4", "1")
    # Build a CaseFile with domain_id="housing.deposit.v1"
    # Build a KGFacts (because deposit case_graph IS KGFacts)
    # Assert IssuePredictor._render_factor_card_via_pack(case_file, kg_facts)
    # returns the same string as pack.render_factor_card(kg_facts)


def test_predictor_uses_legacy_when_flag_unset(monkeypatch):
    monkeypatch.setenv("STREAM_C_PR4", "0")
    # Same setup, assert _format_kg_fact_card(kg_facts) is called instead


def test_predictor_uses_repairs_pack_for_repairs_domain(monkeypatch):
    monkeypatch.setenv("STREAM_C_PR4", "1")
    # CaseFile with domain_id="housing.repairs_social.v1"
    # case_graph is a KnowledgeGraph with factor_assertions
    # Assert pack.render_factor_card returns the repairs-style card


def test_predictor_returns_empty_card_when_pack_unknown(monkeypatch):
    monkeypatch.setenv("STREAM_C_PR4", "1")
    # CaseFile with domain_id="unknown.v1"
    # Assert no exception, empty card returned, warning logged


def test_predictor_returns_empty_card_when_gate_fails(monkeypatch):
    monkeypatch.setenv("STREAM_C_PR4", "1")
    # CaseFile with domain_id="housing.repairs_social.v1"
    # case_graph with a deliberately failing GraphQualityScore
    # Assert empty card; assert metadata records kg_used_for_prediction=False,
    # kg_fallback_mode="rag_only", kg_gate_failure_reasons populated


def test_rag_only_hides_factor_card(monkeypatch):
    """Spec §19 PR 4: RAG-only mode must NOT inject the factor card.

    This guards the line-499 callsite (the main _predict_issue path) which
    historically populated kg_fact_card unconditionally for both HYBRID and
    RAG_ONLY modes. After PR 4 the gate is `prompt_mode != "rag_only"`.
    """
    monkeypatch.setenv("STREAM_C_PR4", "1")
    # Build a CaseFile with domain_id="housing.repairs_social.v1"
    # Build a populated KG with FactorAssertion nodes (so the card WOULD be
    # non-empty if rendered)
    # Spy on the prompt sent to the (mocked) LLM client
    # Assert the prompt for prompt_mode="rag_only" contains neither
    # "KEY KG FACTS" nor "KEY FACTORS (factor-graph derived)"
    # Assert the prompt for prompt_mode="hybrid" DOES contain "KEY FACTORS"


def test_hybrid_mode_includes_factor_card_via_pack(monkeypatch):
    """Spec §19 PR 4: hybrid mode must include the new factor card."""
    monkeypatch.setenv("STREAM_C_PR4", "1")
    # Same setup as above, but assert prompt_mode="hybrid" produces a prompt
    # that contains "KEY FACTORS (factor-graph derived):"
```

- [ ] **Step 2 — Implement**

In `issue_predictor.py`, add a new private method `_render_factor_card_via_pack(self, case_file, case_graph) -> tuple[str, dict]`:

```python
import os
from typing import Any
from legal_core.graph.graph_quality import GraphQualityScore  # if not already imported

def _render_factor_card_via_pack(
    self, case_file: Any, case_graph: Any
) -> tuple[str, dict]:
    """Render the factor card via the domain pack.

    Returns (card_markdown, gate_metadata). Falls back to empty card +
    metadata recording the failure when:
      - STREAM_C_PR4=0 (flag disabled)
      - domain_id has no registered pack
      - graph_quality_score fails the pack's gate
    """
    use_pack = os.getenv("STREAM_C_PR4", "1") == "1"
    if not use_pack:
        # Legacy path: use existing _format_kg_fact_card
        return self._format_kg_fact_card(case_graph), {
            "kg_used_for_prediction": case_graph is not None,
            "kg_fallback_mode": None,
            "kg_gate_failure_reasons": [],
        }

    domain_id = getattr(case_file, "domain_id", None)
    if domain_id is None:
        # Defensive: legacy fallback
        return self._format_kg_fact_card(case_graph), {
            "kg_used_for_prediction": False,
            "kg_fallback_mode": "legacy_no_domain_id",
            "kg_gate_failure_reasons": ["case_file.domain_id is None"],
        }

    try:
        from domain_packs.registry import get_domain_pack, DomainPackNotFoundError
        pack = get_domain_pack(domain_id)
    except DomainPackNotFoundError as e:
        # Unknown pack: log + empty card; do NOT crash
        import structlog
        structlog.get_logger().warning("domain_pack_unknown", domain_id=domain_id)
        return "", {
            "kg_used_for_prediction": False,
            "kg_fallback_mode": "rag_only",
            "kg_gate_failure_reasons": [f"unknown domain pack: {domain_id}"],
        }

    # Compute graph quality score (placeholder for now; PR 5 + actual
    # extractor populate this properly).
    score = self._compute_graph_quality_score(case_file, case_graph)

    if not pack.is_kg_usable(score):
        return "", {
            "kg_used_for_prediction": False,
            "kg_fallback_mode": "rag_only",
            "kg_gate_failure_reasons": _gate_failure_reasons(score, pack.graph_quality_gate),
            "graph_quality_score": score.score,
        }

    card = pack.render_factor_card(case_graph)
    return card, {
        "kg_used_for_prediction": True,
        "kg_fallback_mode": None,
        "kg_gate_failure_reasons": [],
        "graph_quality_score": score.score,
    }


def _compute_graph_quality_score(self, case_file, case_graph) -> GraphQualityScore:
    """Compute a GraphQualityScore for the case_graph.

    For PR 4 this is a minimal implementation: counts factor_assertions
    with non-empty supported_by, dated events, etc. PR 5 may extend.
    """
    if case_graph is None:
        return GraphQualityScore(
            score=0.0,
            evidence_backed_factor_count=0,
            dated_event_count=0,
            issue_count=0,
            outcome_or_remedy_candidate_count=0,
            unsupported_factor_rate=0.0,
            source_span_coverage=0.0,
            contradiction_count=0,
            usable_for_prediction=False,
            failure_reasons=["case_graph is None"],
        )

    # If case_graph is a KGFacts (deposit), count populated typed facts.
    from llm_orchestrator.pipeline.kg_facts import KGFacts
    if isinstance(case_graph, KGFacts):
        populated = sum([
            case_graph.deposit_protection_status != "unknown",
            case_graph.prescribed_information_status != "unknown",
            case_graph.check_in_inventory_baseline != "unknown",
        ])
        return GraphQualityScore(
            score=populated / 3.0,
            evidence_backed_factor_count=populated,
            dated_event_count=2 if populated > 0 else 0,  # deposit cases have receipt + protection dates
            issue_count=1,
            outcome_or_remedy_candidate_count=1,
            unsupported_factor_rate=0.0,
            source_span_coverage=1.0,  # deterministic, always 'sourced'
            contradiction_count=0,
            usable_for_prediction=populated >= 2,
            failure_reasons=[] if populated >= 2 else ["fewer than 2 typed facts populated"],
        )

    # Else assume a KnowledgeGraph with factor_assertions (repairs).
    factor_assertions = getattr(case_graph, "factor_assertions", []) or []
    evidence_backed = [fa for fa in factor_assertions if fa.supported_by]
    return GraphQualityScore(
        score=len(evidence_backed) / max(len(factor_assertions), 1),
        evidence_backed_factor_count=len(evidence_backed),
        dated_event_count=len(getattr(case_graph, "dated_events", []) or []),
        issue_count=len(getattr(case_graph, "issues", []) or []),
        outcome_or_remedy_candidate_count=len(getattr(case_graph, "candidate_outcomes", []) or []),
        unsupported_factor_rate=1.0 - (len(evidence_backed) / max(len(factor_assertions), 1)),
        source_span_coverage=len(evidence_backed) / max(len(factor_assertions), 1),
        contradiction_count=0,  # PR 6 may compute this
        usable_for_prediction=len(evidence_backed) >= 5,
        failure_reasons=[] if len(evidence_backed) >= 5 else [
            f"only {len(evidence_backed)} evidence-backed factors (min 5)"
        ],
    )


def _gate_failure_reasons(score: GraphQualityScore, gate) -> list[str]:
    """Enumerate every threshold the score fails. Mirrors the 7-condition
    AND in DomainPack.is_kg_usable so downstream consumers see exactly which
    threshold(s) tripped the gate.
    """
    reasons: list[str] = []
    if score.evidence_backed_factor_count < gate.evidence_backed_factor_count_min:
        reasons.append(
            f"evidence_backed_factor_count {score.evidence_backed_factor_count} "
            f"< min {gate.evidence_backed_factor_count_min}"
        )
    if score.dated_event_count < gate.dated_event_count_min:
        reasons.append(
            f"dated_event_count {score.dated_event_count} "
            f"< min {gate.dated_event_count_min}"
        )
    if score.issue_count < gate.issue_count_min:
        reasons.append(
            f"issue_count {score.issue_count} < min {gate.issue_count_min}"
        )
    if score.outcome_or_remedy_candidate_count < gate.outcome_or_remedy_candidate_count_min:
        reasons.append(
            f"outcome_or_remedy_candidate_count {score.outcome_or_remedy_candidate_count} "
            f"< min {gate.outcome_or_remedy_candidate_count_min}"
        )
    if score.unsupported_factor_rate > gate.unsupported_factor_rate_max:
        reasons.append(
            f"unsupported_factor_rate {score.unsupported_factor_rate:.2f} "
            f"> max {gate.unsupported_factor_rate_max:.2f}"
        )
    if score.source_span_coverage < gate.source_span_coverage_min:
        reasons.append(
            f"source_span_coverage {score.source_span_coverage:.2f} "
            f"< min {gate.source_span_coverage_min:.2f}"
        )
    if score.contradiction_count > gate.contradiction_count_max:
        reasons.append(
            f"contradiction_count {score.contradiction_count} "
            f"> max {gate.contradiction_count_max}"
        )
    return reasons
```

Then update the THREE existing `_format_kg_fact_card` call sites to use `_render_factor_card_via_pack`:

**Site 1 — `_predict_issue_no_rag` line 192 (KG_ONLY / LLM_ONLY repairs path):**
```python
# OLD (line 192):
kg_fact_card = (
    self._format_kg_fact_card(self._kg_facts_by_issue.get(issue.issue_type))
    if prompt_mode == "kg_only"
    else ""
)

# NEW:
if prompt_mode == "kg_only":
    case_graph = self._case_graph_by_issue.get(issue.issue_type) \
                 or self._kg_facts_by_issue.get(issue.issue_type)
    kg_fact_card, kg_metadata = self._render_factor_card_via_pack(
        self._case_file, case_graph,
    )
    self._last_kg_metadata = kg_metadata  # for prediction artifact
else:
    kg_fact_card = ""
```

**Site 2 — `_predict_issue_no_rag` line 258 (KG_ONLY non-repairs IRAC path):**
```python
# OLD (line 258):
kg_fact_card = self._format_kg_fact_card(
    self._kg_facts_by_issue.get(issue.issue_type)
)

# NEW (only render when KG_ONLY mode; LLM_ONLY skipped at callsite already):
case_graph = self._case_graph_by_issue.get(issue.issue_type) \
             or self._kg_facts_by_issue.get(issue.issue_type)
kg_fact_card, kg_metadata = self._render_factor_card_via_pack(
    self._case_file, case_graph,
)
self._last_kg_metadata = kg_metadata
```

**Site 3 — `_predict_issue` line 499 (HYBRID / RAG_ONLY hot path — THE CRITICAL FIX):**
```python
# OLD (line 499 — UNCONDITIONAL, populates card for both hybrid AND rag_only):
kg_fact_card = self._format_kg_fact_card(
    self._kg_facts_by_issue.get(issue.issue_type)
)

# NEW — gate on prompt_mode so rag_only gets empty card per spec §19 PR 4:
if prompt_mode == "rag_only":
    kg_fact_card = ""
    self._last_kg_metadata = {
        "kg_used_for_prediction": False,
        "kg_fallback_mode": None,  # rag_only is the intended mode, not a fallback
        "kg_gate_failure_reasons": [],
    }
else:
    case_graph = self._case_graph_by_issue.get(issue.issue_type) \
                 or self._kg_facts_by_issue.get(issue.issue_type)
    kg_fact_card, kg_metadata = self._render_factor_card_via_pack(
        self._case_file, case_graph,
    )
    self._last_kg_metadata = kg_metadata
```

(`_case_graph_by_issue` is a new attribute populated by `prediction_engine_v2.py` in Task 4.5 below; for now it can default to empty dict, falling back to the legacy `_kg_facts_by_issue` path.)

**Note on `prompt_mode` availability at line 499**: the existing `_predict_issue` accepts `prompt_mode` as a parameter passed down from `_predict_issue_for_mode` (or similar). Verify by reading the surrounding 30 lines before editing — if `prompt_mode` isn't already in scope at line 499, the wrapping function signature must be extended to thread it through. This is a small refactor and should be a separate sub-step of Task 4.4 with its own TDD test.

- [ ] **Step 3 — Run, expect pass**

Run: `pytest packages/llm_orchestrator/tests/test_kg_fact_card.py -v`
Expected: existing 8 tests + 5 new = 13 tests pass.

- [ ] **Step 4 — Run regression suite**

Run: `pytest packages/llm_orchestrator/tests/test_kg_in_prompt_golden.py -v`
Expected: pass with `STREAM_C_PR4=1`. If golden snapshots changed, regenerate them and verify the diff is only the new "KEY FACTORS" header (deposit byte-equivalence preserves content).

- [ ] **Step 5 — Commit**

```bash
git add packages/llm_orchestrator/pipeline/issue_predictor.py \
        packages/llm_orchestrator/tests/test_kg_fact_card.py
git commit -m "feat(issue_predictor): wire domain_pack.render_factor_card behind STREAM_C_PR4

PR 4 Task 4.4: replace static IssuePredictor._format_kg_fact_card call
with domain-aware pack lookup + render. Behind STREAM_C_PR4=1 (default)
the new path runs; STREAM_C_PR4=0 reverts to legacy.

New _render_factor_card_via_pack returns (card, gate_metadata) tuple.
Gate metadata records kg_used_for_prediction, kg_fallback_mode,
kg_gate_failure_reasons, graph_quality_score per spec §6 + §8.2 +
§17.6 artifact schema (Cross-PR Contract C5).

Unknown pack -> empty card + warning log + rag_only fallback metadata.
Pack gate failure -> empty card + structured failure reasons.

Deposit byte-equivalence preserved per Stream C hard constraint #6
(verified by test_deposit_renderer.test_renderer_byte_equivalent_to_legacy_format).

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §6, §8.2, §19 PR 4"
```

### Task 4.5 — Threading `case_graph` per-issue + artifact metadata

**Files:**
- Modify: `packages/llm_orchestrator/pipeline/prediction_engine_v2.py:144-152` — populate `case_graph_by_issue` alongside `kg_facts_by_issue`
- Modify: `packages/llm_orchestrator/pipeline/output_assembler.py` — surface kg_metadata in artifact

(Implementation outline; full code per the patterns above.)

In `prediction_engine_v2.py`, after the existing `kg_facts_by_issue` block, add:

```python
case_graph_by_issue: Dict[Any, Any] = {}
if (
    mode in (PredictionMode.HYBRID, PredictionMode.KG_ONLY)
    and knowledge_graph is not None
):
    for issue in issues:
        # For deposit cases, KGFacts is the case_graph; for repairs,
        # the full KnowledgeGraph (with FactorAssertion nodes) is.
        if case_file.domain_id == "housing.deposit.v1":
            case_graph_by_issue[issue.issue_type] = kg_facts_by_issue.get(issue.issue_type)
        else:
            case_graph_by_issue[issue.issue_type] = knowledge_graph

self.issue_predictor._case_graph_by_issue = case_graph_by_issue
self.issue_predictor._case_file = case_file
```

In `output_assembler.py`, in the `assemble()` method, after building `pipeline_metadata`, append the kg metadata:

```python
last_kg_metadata = getattr(issue_predictor, "_last_kg_metadata", None)
if last_kg_metadata is not None:
    pipeline_metadata.update({
        "graph_quality_score": last_kg_metadata.get("graph_quality_score"),
        "kg_used_for_prediction": last_kg_metadata.get("kg_used_for_prediction"),
        "kg_fallback_mode": last_kg_metadata.get("kg_fallback_mode"),
        "kg_gate_failure_reasons": last_kg_metadata.get("kg_gate_failure_reasons", []),
    })
```

Tests: extend `test_prediction_engine_agentic.py` to assert that a deposit fixture case with `STREAM_C_PR4=1` produces an artifact containing `kg_used_for_prediction: true`. Extend with a repairs fixture asserting same.

Single commit:
```
feat(prediction_engine_v2): thread case_graph per-issue + record gate metadata
```

### Task 4.6 — Deprecate `kg_facts.py` rendering helper

**Files:**
- Modify: `packages/llm_orchestrator/pipeline/kg_facts.py` — keep `KGFacts` and `derive_kg_facts`; add `DeprecationWarning` if anyone imports a hypothetical `format_kg_fact_card` (we never had one — just defensive)
- Modify: `packages/llm_orchestrator/pipeline/issue_predictor.py:1206-1237` — keep `_format_kg_fact_card` for now (legacy path), add a docstring noting it's deprecated and only called when `STREAM_C_PR4=0`

This is a documentation change, not a deletion. Single small commit.

### Task 4.6b — Prediction artifact schema regression test

**Files:**
- Create: `packages/llm_orchestrator/tests/test_prediction_artifact_schema_stable.py`
- Create: `packages/llm_orchestrator/tests/fixtures/stream_c_artifact_v1.json` — committed reference artifact

This test backstops Cross-PR Contract C5. It guards against PR 5 / PR 6 (and any future PR) accidentally renaming or dropping fields that the eval pipeline reads.

- [ ] **Step 1 — Write the failing test**

```python
# packages/llm_orchestrator/tests/test_prediction_artifact_schema_stable.py
"""Cross-PR Contract C5: prediction artifact metadata schema must be stable.

Any PR that renames or removes a field in pipeline_metadata MUST update the
fixture artifact AND get explicit reviewer approval. The fixture is the
single source of truth for what the eval pipeline expects.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "stream_c_artifact_v1.json"

# Keys that MUST appear in pipeline_metadata after PR 4 lands.
PR4_REQUIRED_KEYS = {
    "core_schema",
    "domain_pack",
    "factor_catalog_version",
    "graph_quality_score",
    "kg_used_for_prediction",
    "kg_fallback_mode",
    "kg_gate_failure_reasons",
}

# Keys that MUST appear after PR 5 lands.
PR5_REQUIRED_KEYS = PR4_REQUIRED_KEYS | {
    "retrieval_profile",
    "comparator_pass_n_retrieved",
    "counterexample_pass_n_retrieved",
    "abstention_recommended",
}

# Keys that MUST appear after PR 6 lands.
PR6_REQUIRED_KEYS = PR5_REQUIRED_KEYS | {
    "evidence_path_results",
}


def _load_fixture():
    return json.loads(_FIXTURE_PATH.read_text())


def test_fixture_artifact_loads():
    artifact = _load_fixture()
    assert "pipeline_metadata" in artifact


def test_pr4_metadata_keys_present():
    artifact = _load_fixture()
    meta = artifact["pipeline_metadata"]
    missing = PR4_REQUIRED_KEYS - set(meta)
    assert not missing, f"PR 4 keys missing from artifact: {missing}"


def test_kg_used_for_prediction_is_bool():
    artifact = _load_fixture()
    assert isinstance(artifact["pipeline_metadata"]["kg_used_for_prediction"], bool)


def test_kg_gate_failure_reasons_is_list_of_strings():
    artifact = _load_fixture()
    reasons = artifact["pipeline_metadata"]["kg_gate_failure_reasons"]
    assert isinstance(reasons, list)
    for r in reasons:
        assert isinstance(r, str)


def test_graph_quality_score_in_unit_interval():
    artifact = _load_fixture()
    score = artifact["pipeline_metadata"]["graph_quality_score"]
    assert 0.0 <= score <= 1.0
```

(PR 5 and PR 6 each extend this test with their own `test_prX_metadata_keys_present` assertion using `PR5_REQUIRED_KEYS` / `PR6_REQUIRED_KEYS`.)

- [ ] **Step 2 — Generate the fixture**

After Task 4.5 wires gate metadata into `output_assembler.py`, run the smoke CLI from Task 4.9 Step 2 with `--limit 1` and copy ONE row of `kg_only.jsonl` into `tests/fixtures/stream_c_artifact_v1.json`. Strip any per-run timestamps. Commit the fixture.

- [ ] **Step 3 — Run, expect pass**

Run: `pytest packages/llm_orchestrator/tests/test_prediction_artifact_schema_stable.py -v`
Expected: 5 PR-4 tests pass.

- [ ] **Step 4 — Commit**

```bash
git add packages/llm_orchestrator/tests/test_prediction_artifact_schema_stable.py \
        packages/llm_orchestrator/tests/fixtures/stream_c_artifact_v1.json
git commit -m "test(llm_orchestrator): pin prediction artifact schema (Contract C5)

Cross-PR Contract C5 regression test. Loads a committed fixture artifact
and asserts that the Stream C pipeline_metadata field set is present and
typed correctly. PR 5 and PR 6 will extend with their own field-set
assertions.

This is the gate that catches silent field renames between PR 4-6."
```

### Task 4.7 — Snapshot tests for both pack prompt outputs

**Files:**
- Create: `packages/llm_orchestrator/tests/test_issue_predictor_factor_card.py`
- Create: `packages/llm_orchestrator/tests/snapshots/factor_card_deposit_full.txt` (committed)
- Create: `packages/llm_orchestrator/tests/snapshots/factor_card_repairs_full.txt` (committed)

Snapshot tests guard against silent prompt drift. Each test:
1. Constructs a deterministic fixture (KGFacts for deposit, KnowledgeGraph with 8 FactorAssertions for repairs).
2. Calls `pack.render_factor_card(case_graph)`.
3. Asserts the output equals the snapshot file (read from disk).
4. If you intend to change the renderer output, regenerate the snapshot via an `--update-snapshots` flag (or env var `UPDATE_SNAPSHOTS=1`).

This is the canonical "the prompt didn't drift" gate. Single commit.

### Task 4.8 — PR 4 integration smoke test

**Files:**
- Create: `packages/llm_orchestrator/tests/test_pr4_integration.py`

End-to-end: build a deposit fixture case → run `PredictionEngineV2.predict(mode=KG_ONLY)` with `STREAM_C_PR4=1` → assert the prompt sent to the (mocked) LLM contains the "KEY KG FACTS" header. Repeat for repairs with `mode=HYBRID` → assert "KEY FACTORS (factor-graph derived):" header.

Single commit. PR 4 ready to ship.

### Task 4.9 — PR 4 self-verification + open PR

- [ ] **Step 1 — Full test suite**

```bash
./venv/bin/python -m pytest packages/legal_core/tests/ \
                              packages/domain_core/tests/ \
                              packages/domain_packs/tests/ \
                              packages/llm_orchestrator/tests/ \
                              -v -W error::DeprecationWarning
```
Expected: all green.

- [ ] **Step 2 — Smoke-test the CLI**

```bash
./venv/bin/python -m scripts.eval.predict_all \
  --gold data/eval/housing_ombudsman_balanced_50_20260506.jsonl \
  --out-dir /tmp/pr4_smoke \
  --engine stub \
  --modes kg_only \
  --limit 5
```
Expected: 5 stub predictions; `/tmp/pr4_smoke/kg_only.jsonl` exists; each row has `kg_used_for_prediction: true` for cases where the gate passes.

- [ ] **Step 3 — Open PR against main**

```bash
git push -u origin codex/stream-c-pr4
gh pr create --base main --head codex/stream-c-pr4 \
  --title "feat: Stream C PR 4 — domain-pack factor card rendering" \
  --body-file docs/superpowers/plans/2026-05-07-stream-c-prediction-path-swap.md  # or a short PR body referencing this plan
```

PR 4 done. Move to PR 5.

---

## PR 5 — Factor-constrained proposition retrieval

PR 5 lands `factor_retrieval.py` and `comparator_pack.py`, extends the `Proposition` model with factor/outcome/remedy IDs, adds bucketed similarity scoring, the separate counterexample pass per spec §9.3, and the `RetrievalStrategy.FACTOR_CONSTRAINED` mode in `prediction_engine_v2.py`. Behind `STREAM_C_FACTOR_RETRIEVAL=0` (default off until verified), the legacy `IssueRetriever` path is used.

### Task 5.1 — `ComparatorPack` + supporting models

**Files:**
- Create: `packages/llm_orchestrator/pipeline/comparator_pack.py`
- Create: `packages/llm_orchestrator/tests/test_comparator_pack.py`

Implement Contract C2 (above) verbatim. Tests:
1. Round-trip JSON serialization for full ComparatorPack.
2. `RankedProposition` rejects score outside [0, 1].
3. `RankedProposition` rejects unknown `authority_level` / `proposition_role` enum values.
4. Frozen + extra=forbid on every model.
5. `ComparatorPack` accepts empty `comparators` and `counterexamples` lists.
6. `CounterexamplePassMetadata.abstention_recommended=True` round-trips.

Single commit.

### Task 5.2 — Bucketed similarity helpers

**Files:**
- Create: `packages/llm_orchestrator/pipeline/_factor_overlap.py`
- Create: `packages/llm_orchestrator/tests/test_factor_overlap.py`

Per spec §9.2.1. Public functions:

```python
def money_similarity(a_pence: int, b_pence: int, edges: List[int]) -> float:
    """Same bucket → 1.0; adjacent → 0.5; else 0.0."""

def duration_similarity(a_days: int, b_days: int, edges: List[int]) -> float:
    """Same as money but for duration."""

def date_similarity(a: date, b: date, *, same_year: float, same_month: float, other: float) -> float:
    """Per spec §9.2.1 date semantics."""

def boolean_similarity(a: bool, b: bool) -> float:
    """1.0 if equal, 0.0 otherwise."""

def enum_similarity(a: str, b: str) -> float:
    """1.0 if equal, 0.0 otherwise (per spec: equality only)."""

def factor_overlap(
    a: FactorAssertion, b: FactorAssertion,
    bucket_definitions: BucketDefinitions,
) -> float:
    """Dispatch on value_type; returns similarity score in [0, 1]."""
```

Tests cover each helper with boundary cases (same bucket, adjacent buckets, non-adjacent, exact equality, equality-by-bucket). Single commit.

### Task 5.3 — `FactorRetriever` core

**Files:**
- Create: `packages/llm_orchestrator/pipeline/factor_retrieval.py`
- Create: `packages/llm_orchestrator/tests/test_factor_retrieval.py`

Implement:
- `RetrievalControlInput` model (Contract C3).
- `AuthorityPolicy` model (small enum-based policy: `forum_compatible_only: bool`, `accept_first_instance_as_fact_comparator: bool`).
- `FactorRetriever(repository: PropositionGraphRepository, pack: DomainPack)` class with:
  - `async retrieve_comparators(input: RetrievalControlInput) -> List[RankedProposition]`
  - `async retrieve_counterexamples(input: RetrievalControlInput, primary_outcome: str) -> List[RankedProposition]`
  - `async build_comparator_pack(input: RetrievalControlInput, primary_outcome: str) -> ComparatorPack`
- Score formula per spec §9.2 (defaults from `pack.retrieval_profile.comparator_weights`).
- Counterexample pass per spec §9.3 algorithm.
- Empty-asserted-factors fallback per design decision D5.
- Cross-domain retrieval gating per spec R5: filter on same `domain_id` by default; `RetrievalProfile.notes` may opt-in to cross-domain (PR 5 doesn't implement opt-in; defaults strict).

Tests cover:
1. `retrieve_comparators` returns top-N positive analogues with score > 0.
2. Comparator scoring honours `pack.retrieval_profile.comparator_weights` exactly.
3. `retrieve_counterexamples` returns cases with shared factors AND different outcome.
4. Counterexample pass returns empty when no candidates → `abstention_recommended=True`.
5. `STREAM_C_K_OVERLAP_MIN` env override.
6. `STREAM_C_COUNTEREXAMPLE_ABSTAIN=0` env override.
7. Empty `asserted_factors` → empty `ComparatorPack` + `fallback_reason` set.
8. Authority policy: ET first-instance proposition cannot enter as `proposition_role="legal_test"`.
9. Cross-domain filtering: only same-domain propositions returned.
10. Bucketed similarity wired correctly (money, duration, date factors).

Single commit.

### Task 5.4 — Extend `Proposition` model with new fields

**Files:**
- Modify: `packages/kg_builder/propositions/models.py` — add optional fields
- Modify: `packages/kg_builder/tests/test_propositions_models.py` — coverage

Additive changes (all default to empty list / None):
```python
class Proposition(BaseModel):
    # ... existing fields ...
    factor_ids: List[str] = Field(default_factory=list)
    outcome_component_ids: List[str] = Field(default_factory=list)
    remedy_component_ids: List[str] = Field(default_factory=list)
    claim_head_ids: List[str] = Field(default_factory=list)
    authority_level: Literal[
        "statute", "regulation", "official_guidance",
        "binding_precedent", "persuasive", "comparator",
    ] = "comparator"
    proposition_role: Literal[
        "legal_test", "factual_finding", "fact_comparator", "remedy_rationale",
    ] = "fact_comparator"
```

Existing data must continue to load (defaults preserve backward compat). Tests verify both:
1. New propositions can populate the new fields.
2. Existing propositions (without the new fields in JSON) load with defaults.

Single commit.

### Task 5.5 — `RetrievalStrategy.FACTOR_CONSTRAINED` integration

**Files:**
- Modify: `packages/llm_orchestrator/pipeline/prediction_engine_v2.py` — add new strategy enum value + routing
- Modify: `packages/llm_orchestrator/pipeline/issue_retrieval.py` — dispatch to `FactorRetriever` when strategy = FACTOR_CONSTRAINED
- Create: `packages/llm_orchestrator/tests/test_factor_retrieval_integration.py`

Add `FACTOR_CONSTRAINED = "factor_constrained"` to the `RetrievalStrategy` enum.

In `IssueRetriever._retrieve_for_issue`, add a new branch: when strategy is `FACTOR_CONSTRAINED`, build a `RetrievalControlInput` from `case_file`, `issue`, and `case_graph`, then call `FactorRetriever.build_comparator_pack(...)`. Convert the resulting `ComparatorPack` to `IssueRetrievalResult.results` format.

In `PredictionEngineV2.predict`, behind `STREAM_C_FACTOR_RETRIEVAL=1`, set `retrieval_strategy = RetrievalStrategy.FACTOR_CONSTRAINED` for HYBRID and KG_ONLY modes.

Tests:
1. With `STREAM_C_FACTOR_RETRIEVAL=1`, engine routes to `FactorRetriever`.
2. With `STREAM_C_FACTOR_RETRIEVAL=0`, engine uses legacy `IssueRetriever` path (regression guard).
3. Empty asserted_factors → falls back to chunk-RAG (regression to legacy behavior).
4. Comparator pack metadata appears in prediction artifact.

Single commit.

### Task 5.6 — Surface comparator + counterexample in prompt

**Files:**
- Modify: `packages/llm_orchestrator/pipeline/issue_predictor.py` — extend `_predict_issue` and prompt template to read comparators + counterexamples separately
- Modify: `packages/llm_orchestrator/prompts/prediction_v2.py` — add comparator/counterexample placeholders

Change `IRAC_USER_PROMPT` to include:
```
COMPARATOR CASES (similar facts, same outcome):
{comparators_section}

COUNTEREXAMPLES (similar facts, different outcome):
{counterexamples_section}
{abstention_warning}
```

When `abstention_recommended=True`, set `{abstention_warning}` to:
```
NOTE: Counterexample pass found no differential cases. Treat any prediction as low-confidence.
```

Tests:
1. Prompt contains both sections.
2. When counterexamples is empty, "no counterexamples available" placeholder used.
3. `abstention_recommended=True` adds the warning line.
4. Snapshot test for full repairs prompt.

Single commit.

### Task 5.7 — Retrieval-quality metrics

**Files:**
- Create: `packages/eval/metrics/retrieval_quality.py`
- Create: `packages/eval/tests/test_retrieval_quality_metrics.py`

Implement (per spec §17.2):
```python
def retrieval_context_precision_at_k(retrieved: List[str], relevant: Set[str], k: int) -> float:
    """Share of top-k retrieved that are in the relevant set."""

def retrieval_context_recall_at_k(retrieved: List[str], relevant: Set[str], k: int) -> float:
    """Share of relevant set covered by top-k retrieved."""

def citation_validity(predictions: List[dict], gold_citations: Dict[str, Set[str]]) -> float:
    """Per LegalBench-RAG: share of cited propositions that genuinely support the claim."""
```

All metrics must be wrappable in `bootstrap_ci` (existing `eval.metrics.uncertainty.bootstrap_ci`). Tests verify behavior + bootstrap CI compatibility. Single commit.

### Task 5.8 — PR 5 self-verification + open PR

```bash
./venv/bin/python -m pytest packages/llm_orchestrator/tests/ packages/eval/tests/ -v -W error::DeprecationWarning
```
Expected: all pass.

```bash
./venv/bin/python -m scripts.eval.predict_all \
  --gold data/eval/housing_ombudsman_balanced_50_20260506.jsonl \
  --out-dir /tmp/pr5_smoke --engine stub --modes hybrid --limit 5
```
Expected: with `STREAM_C_FACTOR_RETRIEVAL=1`, comparator_pass / counterexample_pass metadata present in artifacts.

Open PR.

---

## PR 6 — Evidence-path validator

PR 6 adds the `EvidencePathValidator`, wires it into `output_assembler.py` after `CitationVerifier`, surfaces gate-pass-rate as a first-class metric, and lays the harness for counterfactual-sensitivity (per spec §17.7). Behind `STREAM_C_EVIDENCE_PATH_STRICT=0` (audit-only default), the validator logs rejections without enforcement; flip to `1` after verifying the rejection rate is < 20%.

### Task 6.1 — `EvidencePathValidator` core

**Files:**
- Create: `packages/llm_orchestrator/pipeline/evidence_path_validator.py`
- Create: `packages/llm_orchestrator/tests/test_evidence_path_validator.py`

Implement:
- `EvidencePathValidator(case_graph: Any)` class.
- `validate_outcome_component(oc: OutcomeComponent) -> EvidencePathResult` — returns chain or rejection reason.
- Iterative BFS traversal (NOT recursive, to avoid stack overflow on cycles).
- Cycle detection via `visited: Set[str]`.
- Returns `EvidencePathResult(is_supported, chain, rejection_reason, abstention_required)`.

Tests:
1. Happy path: a complete chain `EvidenceSpan → FactorAssertion → Proposition → OutcomeComponent` validates as `is_supported=True`.
2. Missing FactorAssertion link: rejected with reason "no FactorAssertion supports outcome_component_id={...}".
3. Missing Proposition link: rejected with reason.
4. Cycle in graph: detected, validator returns `is_supported=False` with reason "cycle detected at node {...}", does NOT infinite-loop.
5. Audit mode (`STREAM_C_EVIDENCE_PATH_STRICT=0`): `abstention_required=False` even when rejected.
6. Strict mode (`STREAM_C_EVIDENCE_PATH_STRICT=1`): `abstention_required=True` when rejected.
7. Empty case_graph: every outcome component rejected with reason "case_graph is empty".

Single commit.

### Task 6.2 — Wire validator into `output_assembler.py`

**Files:**
- Modify: `packages/llm_orchestrator/pipeline/output_assembler.py:574-594`
- Create: `packages/llm_orchestrator/tests/test_output_assembler_validator_wiring.py`

In `assemble()`, AFTER `CitationVerifier.verify()` and BEFORE the existing `IssueOutcome.UNCERTAIN` enforcement:

```python
from llm_orchestrator.pipeline.evidence_path_validator import EvidencePathValidator

validator = EvidencePathValidator(case_graph=case_graph)
evidence_path_results = []
for issue_pred in issue_predictions:
    for oc in getattr(issue_pred, "outcome_components", []):
        result = validator.validate_outcome_component(oc)
        evidence_path_results.append(result)
        if result.abstention_required:
            issue_pred.outcome = IssueOutcome.UNCERTAIN
            issue_pred.uncertainties.append(
                f"evidence_path_rejected: {result.rejection_reason}"
            )

pipeline_metadata["evidence_path_results"] = [r.model_dump() for r in evidence_path_results]
```

Tests:
1. Audit mode: validator runs, results recorded in metadata, no outcomes forced to UNCERTAIN.
2. Strict mode: rejected outcomes become UNCERTAIN; uncertainties list updated.
3. Validator results round-trip in the prediction artifact.

Single commit.

### Task 6.3 — Gate-pass-rate metric

**Files:**
- Create: `packages/eval/metrics/gate_pass_rate.py`
- Create: `packages/eval/tests/test_gate_pass_rate.py`

Per spec §17.6 first-class metric:
```python
def gate_pass_rate(predictions: List[dict]) -> MetricResult:
    """Share of predictions where kg_used_for_prediction == True."""
    if not predictions:
        return MetricResult(point=0.0, lower_95=0.0, upper_95=0.0, n=0, n_resamples=0)
    passed = sum(1 for p in predictions if p.get("kg_used_for_prediction") is True)
    return bootstrap_ci(
        lambda gold, preds: passed / len(preds),
        gold=[None] * len(predictions),
        predictions=predictions,
        n_resamples=1000, seed=42,
    )

def fallback_mode_distribution(predictions: List[dict]) -> Dict[str, int]:
    """Histogram of kg_fallback_mode values."""
```

Tests verify computation and bootstrap CI compatibility. Single commit.

### Task 6.4 — Two-slice reporter

**Files:**
- Create: `packages/eval/metrics/two_slice_reporter.py`
- Create: `packages/eval/tests/test_two_slice_reporter.py`

Per spec §17.6 / §8.3:
```python
def two_slice_report(
    metric_fn: Callable,
    gold: list,
    predictions: list,
) -> Dict[str, MetricResult]:
    """Run metric_fn on both full corpus and gate-passing subset."""
    full = bootstrap_ci(metric_fn, gold, predictions)
    gate_passing_ix = [
        i for i, p in enumerate(predictions)
        if p.get("kg_used_for_prediction") is True
    ]
    if not gate_passing_ix:
        gate = MetricResult(point=float("nan"), lower_95=float("nan"), upper_95=float("nan"), n=0, n_resamples=0)
    else:
        gate = bootstrap_ci(
            metric_fn,
            gold=[gold[i] for i in gate_passing_ix],
            predictions=[predictions[i] for i in gate_passing_ix],
        )
    return {"full_corpus": full, "gate_passing_subset": gate}
```

Tests with synthetic data verify both slices report correctly + edge cases (no gate-passing cases, all gate-passing cases). Single commit.

### Task 6.5 — Counterfactual sensitivity harness (no CI run)

**Files:**
- Create: `packages/eval/metrics/counterfactual_sensitivity.py`
- Create: `packages/eval/tests/test_counterfactual_sensitivity.py`

Per spec §17.7. The harness exists but is not run in CI (compute cost is high — `factors × cases × LLM calls`). Provides:

```python
async def counterfactual_factor_sensitivity(
    case: Any,
    factor_ids: List[str],
    predict_fn: Callable[[Any], Any],
) -> Dict[str, bool]:
    """For each factor, flip its value and check if prediction changes.
    
    Returns dict factor_id → True (prediction changed) or False (unchanged).
    Sensitivity = sum(values) / len(values).
    """
```

Tests use a fake `predict_fn` that returns deterministic predictions. Single commit.

### Task 6.6 — PR 6 self-verification + open PR

Same pattern as PR 4 / PR 5 closeout: full test suite, smoke test with `--engine stub`, open PR.

---

## Post-PR-6 Ablation Rerun

After all three PRs merge to main and the `STREAM_C_FACTOR_RETRIEVAL` and `STREAM_C_EVIDENCE_PATH_STRICT` flags are flipped to `"1"`:

### Task R.1 — Ablation cost approval (CHECKPOINT)

Estimated cost: 50 cases × 4 modes × ~5 LLM calls/mode × ~5K input tokens × frontier extractor = **~£8 total**. User approval required.

### Task R.2 — Run 4-mode ablation

```bash
./venv/bin/python scripts/eval/predict_all.py \
  --gold data/eval/housing_ombudsman_balanced_50_20260506.jsonl \
  --out-dir eval/predictions/stream_c_post_merge_2026_05_XX \
  --engine live \
  --client claude \
  --modes hybrid,rag_only,kg_only,llm_only \
  --top-k 10
```

Then run `scripts/eval/run_full_eval.py` with the same out-dir and write to `eval/results/stream_c_post_merge_2026_05_XX/`.

### Task R.3 — Comparative report

Create `docs/eval/stream-c-ablation-2026-05-XX.md` modeled on `docs/eval/extractor_f1_reports/housing.repairs_social.v1-2026-05-07-gold-iaa-comparative.md`:

Sections:
1. Executive summary — does Stream C move the needle?
2. Side-by-side Task 18 baseline vs Stream C results (per-mode, full corpus + gate-passing subset).
3. Gate-pass rate per mode.
4. Citation validity per mode.
5. Counterexample-flagged abstention rate per mode.
6. Per-mode prediction-artifact size (sanity check on metadata bloat).
7. Cost report.
8. Decision: do we flip `STREAM_C_FACTOR_RETRIEVAL` and `STREAM_C_EVIDENCE_PATH_STRICT` to "1" by default in the next release? Recommendations based on the data.

Commit with appropriate message and PR.

---

## How to know Stream C is done

Run all of these — every one must pass:

```bash
# 1. Full leaf-package test suites
./venv/bin/python -m pytest packages/legal_core/tests/ -v -W error::DeprecationWarning
./venv/bin/python -m pytest packages/domain_core/tests/ -v -W error::DeprecationWarning
./venv/bin/python -m pytest packages/domain_packs/tests/ -v -W error::DeprecationWarning

# 2. Hot-prediction-path tests
./venv/bin/python -m pytest packages/llm_orchestrator/tests/ -v -W error::DeprecationWarning

# 3. Eval metrics tests
./venv/bin/python -m pytest packages/eval/tests/ -v -W error::DeprecationWarning

# 4. End-to-end smoke
./venv/bin/python -m scripts.eval.predict_all \
  --gold data/eval/housing_ombudsman_balanced_50_20260506.jsonl \
  --out-dir /tmp/stream_c_e2e --engine stub \
  --modes hybrid,rag_only,kg_only,llm_only --limit 5

# 5. Verify artifacts contain Stream C metadata
./venv/bin/python -c "
import json
for mode in ('hybrid', 'rag_only', 'kg_only', 'llm_only'):
    rows = [json.loads(l) for l in open(f'/tmp/stream_c_e2e/{mode}.jsonl')]
    for r in rows:
        meta = r.get('pipeline_metadata', {})
        assert 'kg_used_for_prediction' in meta, f'{mode}: missing kg_used_for_prediction'
        if mode in ('hybrid', 'kg_only'):
            assert 'evidence_path_results' in meta, f'{mode}: missing evidence_path_results'
print('e2e ok')
"
```

Plus: comparative ablation report committed at `docs/eval/stream-c-ablation-2026-05-XX.md`.

---

## Risk Register

| ID | Risk | Trigger | Blast radius | Detection | Mitigation |
|---|---|---|---|---|---|
| R-PR4-1 | Domain pack lookup misses housing.deposit.v1 | Registry returns empty for deposit; `_render_factor_card_via_pack` falls into "unknown pack" branch | Deposit predictions silently get empty card; det.accuracy may regress | `test_deposit_renderer.test_renderer_byte_equivalent_to_legacy_format` | `STREAM_C_PR4=0` reverts to legacy `_format_kg_fact_card` |
| R-PR4-2 | Repairs renderer emits unresolved `{...}` placeholders | Renderer includes a literal `{factor_id}` that conflicts with `IRAC_USER_PROMPT.format()` | KeyError → repairs predictions silently lose all factor card content | `test_renderer_emits_no_unresolved_format_placeholders` + snapshot drift test | `STREAM_C_PR4_REPAIRS=0` returns empty card |
| R-PR4-3 | `kg_facts.py` shim breaks an unknown caller | Hidden caller in scripts/notebooks/worktrees imports `KGFacts` and breaks on the deprecation warning | Scripts crash with DeprecationWarning treated as error in `-W error` env | `grep -rn 'from.*kg_facts\|import kg_facts'` across full repo before deletion | Keep shim with `warnings.warn` (not `raise`) for one release cycle |
| R-PR5-1 | Factor-constrained retrieval returns empty for all cases | Existing propositions in DB don't have the new `factor_ids` etc populated | All hybrid/kg_only modes fall back to chunk-RAG; new architecture invisible in metrics | `test_factor_retrieval_returns_results_with_minimum_proposition_index` | `STREAM_C_FACTOR_RETRIEVAL=0` reverts to legacy retrieval; PR 5 lands the new fields as additive defaults so existing data still loads |
| R-PR5-2 | Counterexample pass abstains in wrong direction | `abstain_if_none=True` + sparse counterexamples for one claim head | Near-100% abstention on that claim head; hybrid/kg_only collapse to RAG-equivalent | Per-issue-type abstain rate in eval | `STREAM_C_COUNTEREXAMPLE_ABSTAIN=0` reverts to soft-flag only |
| R-PR6-1 | Validator over-rejects | Sparse FactorAssertion → many outcome components lack a chain | covered_accuracy drops without quality drop | `test_evidence_path_validator_rejection_rate_under_20pct_on_gold` | `STREAM_C_EVIDENCE_PATH_STRICT=0` puts validator in audit-only mode |
| R-PR6-2 | Cycle in case_graph crashes validator | Case graph has a cycle from FactorAssertion to Proposition back to itself | Stack overflow / infinite loop / prediction service crash | `test_evidence_path_validator_cycles.py` (must not infinite-loop) | Iterative BFS with `visited: Set[str]` (not recursive) |
| R-cross-1 | Stream C lands without ablation rerun | All three PRs merge but Task R.2 is skipped | Thesis evaluation cites stale baseline; no measure of impact | Task R.2 is in this plan | This plan documents the rerun as required |
| R-cross-2 | Prediction artifact schema drifts across PRs | PR 4 emits `kg_used_for_prediction`; PR 5 / PR 6 use a different field name | Eval machinery breaks; comparative report can't read artifacts | Cross-PR Contract C5 in this plan | Add `test_prediction_artifact_schema_stable.py` that loads a fixture artifact and asserts the full Contract C5 field set is present |

---

## Self-Review (already done by the plan author)

**Spec coverage**:
- §4 (FactorAssertion) → renderer reads it (PR 4 Task 4.3)
- §5 (Shared core) → EvidenceSpan, OutcomeComponent, RemedyComponent, ReasoningPath all stubbed (Pre-PR-4 Tasks 0.1-0.3)
- §5.1 (LegalAuthority ↔ AtomicProposition) → Proposition extension in PR 5 Task 5.4 (`authority_level`, `proposition_role` fields added; per D11 note the existing `Proposition` class fills the spec's `AtomicProposition` role)
- §5.2 (Money as typed value) → RemedyComponent uses money_minor_units (Task 0.2)
- §6 (Domain Pack Contract) → DomainPack class (PR 4 Task 4.1)
- §7 (Domain Pack YAML Shape) → consumed via Stream B loaders
- §8 / §8.1 / §8.2 / §8.3 (Graph quality gate) → `pack.is_kg_usable()` + gate metadata in artifact (PR 4 Tasks 4.4, 4.5)
- §9 / §9.1 / §9.2 / §9.2.1 / §9.3 (factor-constrained retrieval) → PR 5 Tasks 5.1, 5.2, 5.3, 5.5, 5.6
- §10 (Corpus proposition KG) → Proposition extension in PR 5 Task 5.4
- §11 (Authority hierarchy) → AuthorityPolicy in factor_retrieval (PR 5 Task 5.3)
- §17.1 (Statistical power) → ablation gated to post-PR-6
- §17.2 (Shared metrics) → retrieval_quality.py (PR 5 Task 5.7)
- §17.6 (Gate-pass rate, two-slice) → gate_pass_rate.py + two_slice_reporter.py (PR 6 Tasks 6.3, 6.4)
- §17.7 (Counterfactual sensitivity) → counterfactual_sensitivity.py (PR 6 Task 6.5)
- §17.8 (Lift discipline) → ablation report includes CIs (Task R.3)
- §19 PR 4 → all PR 4 tasks
- §19 PR 5 → all PR 5 tasks
- §19 PR 6 → all PR 6 tasks
- §22 (DoD) → "How to know Stream C is done" + risk register

**Placeholder scan**: searched for "TODO", "TBD", "implement later", "fill in details" across the plan — none found. All design choices are locked in [Locked-in Design Decisions](#locked-in-design-decisions).

**Type consistency**: `DomainPack`, `ComparatorPack`, `RankedProposition`, `RetrievalControlInput`, `EvidencePathResult`, `EvidenceSpan`, `OutcomeComponent`, `RemedyComponent`, `ReasoningPath`, `GraphQualityScore`, `FactorAssertion`, `FactorValue` all have consistent names across tasks. Field names from Stream A and Stream B are referenced exactly (verified against `legal_core/__init__.py` and `domain_packs/loaders.py`).

**File-list coherence**: every file mentioned in the task descriptions appears in the [File Structure](#file-structure) section. Every file in File Structure has at least one task that creates or modifies it.

**Cross-PR contracts (C1-C5)** are referenced from each PR's tasks; no PR may drift from the Contract section without updating this plan first.

**Risk register coverage**: every flagged risk has a feature flag or test guard. R-cross-2 (artifact schema drift) is addressed by Contract C5 + a dedicated cross-PR regression test (`test_prediction_artifact_schema_stable.py`) added in PR 4.

**Hard constraints (#1-#10) are restated in plan task descriptions where relevant** — leaf-package discipline in Pre-PR-4 setup; Pydantic v2 idioms in every model task; feature-flag wiring in every behavioural-change task; TDD discipline in every task; no real LLM calls in tests.

**What this plan does NOT do** is explicit in the [Executive Scope](#executive-scope) section so reviewers don't expect it.

End of plan.
