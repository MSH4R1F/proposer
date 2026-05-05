# Hybrid RAG Improvement Investigation — Index (2026-05-05)

This is the entry point for the multi-agent investigation of the
Housing Ombudsman hybrid RAG + KG pipeline. Five deliverables, one
synthesis. Read in order.

## Reading order

1. **[Implementation Plan](hybrid-rag-improvement-plan-2026-05-05.md)** —
   the ranked, ticket-ready synthesis. Start here for decisions.
2. **[Agentic Retrieval Plan](hybrid-rag-agentic-retrieval-plan-2026-05-05.md)** —
   ticket-ready spec for Architecture B (single-shot query decomposer)
   and Architecture C (iterative retrieval agent). Extends Tier 2/3 of
   the master plan. Read after #1.
3. **[Failure Taxonomy](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md)** —
   what's actually broken in the latest 50-case run, recomputed from
   prediction artifacts. The most important finding is that the
   headline "hybrid 0.68 vs rag 0.70" gap is one abstention, not a
   real regression.
4. **[Pipeline Audit](hybrid-rag-current-pipeline-audit-2026-05-05.md)** —
   line-by-line audit of the live pipeline; 15 architectural weaknesses
   with file:line evidence and dead-code findings.
5. **[Retrieval & Architecture Research](hybrid-rag-improvement-research-retrieval-2026-05-05.md)** —
   primary-source evidence on legal-RAG hallucination, contextual
   retrieval, late chunking, hybrid fusion, GraphRAG failure modes,
   chunking strategies, multi-pass retrieval.
6. **[Prompting, Calibration, Amount-Prediction Research](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md)** —
   primary-source evidence on IRAC prompting, Self-RAG/CoVe, temperature
   scaling, conformal abstention, two-stage band-classifier-then-CQR
   for damages, imbalanced-eval methodology.

## What triggered this investigation

[`docs/prompts/hybrid-rag-prompt-pipeline-investigation.md`](../prompts/hybrid-rag-prompt-pipeline-investigation.md)
— the full mission brief with hypotheses, required research areas, and
deliverable spec. This investigation produced all five deliverables
above.

## TL;DR

The pipeline is not as broken as the headline numbers suggest, but the
real failures are different from the ones the headline implies:

- **Hybrid ≈ rag_only by construction** because the KG fact card is
  deposit-only and always-empty for repairs (audit W3).
- **kg_only / llm_only are universal abstainers**, not 0%-accurate
  models (taxonomy §B). Ablation claims need rephrasing.
- **The amount head is structurally truncated above £600**; closing
  this needs band classification + within-band CQR, not retrieval
  ranking tweaks alone (taxonomy §H#2; prompting §3.4).
- **The 49/1 gold imbalance dominates every metric**;
  always_tenant=0.98 acc beats the model on every classification
  metric. Gold expansion is a hard prerequisite for thesis claims
  (taxonomy §G).
- **The artifact pipeline drops citation and retrieval evidence**
  before persistence, so we can't actually measure citation quality
  on this run (taxonomy §A, §E).

The implementation plan ranks ten Tier-1 quick wins, eight Tier-2
structural fixes, and four Tier-3 thesis-grade architectural changes.
See its §6 for what to implement now vs. ticket-only and §8 for the
bright lines on what cannot be claimed in the thesis.

## Investigation provenance

Four agents ran in parallel on 2026-05-05 from the
`feature/housing-ombudsman-live-eval` branch (commit `9082eeb`):

| Agent | Subagent type | Output |
|---|---|---|
| Code audit | technical-researcher | [pipeline-audit doc](hybrid-rag-current-pipeline-audit-2026-05-05.md) |
| Failure taxonomy | data-analyst | [failure-taxonomy doc](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md) |
| Retrieval research | academic-research-synthesizer | [retrieval-research doc](hybrid-rag-improvement-research-retrieval-2026-05-05.md) |
| Prompting / calibration research | academic-research-synthesizer | [prompting-calibration-research doc](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md) |

Synthesis (the implementation plan) was written by the coordinator
session over those four outputs.
