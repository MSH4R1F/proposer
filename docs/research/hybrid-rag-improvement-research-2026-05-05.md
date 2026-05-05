# Hybrid RAG Improvement Research Notes - 2026-05-05

## Summary

The literature supports the local diagnosis: retrieval improves legal grounding
but does not make answers safe by itself. The next improvement should increase
verified remedy/order coverage, keep KG facts subordinate to cited evidence,
and report abstention plus imbalance metrics beside headline accuracy.

## Legal RAG And Citation Reliability

| Claim | Source | Source type | Application to Proposer |
| --- | --- | --- | --- |
| RAG reduces but does not eliminate legal hallucinations; evaluated legal research tools still hallucinated material legal claims. | [Magesh et al., "Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools"](https://arxiv.org/abs/2405.20362) | Paper | Keep cite-or-abstain. Evaluate citation validity separately from answer correctness. |
| General-purpose LLMs hallucinate on verifiable legal case-law questions, and legal hallucination is especially harmful when users rely on it. | [Dahl et al., "Large Legal Fictions"](https://academic.oup.com/jla/article/16/1/64/7699227) | Peer-reviewed article | Frame predictions as legal information, not advice; suppress unsupported legal claims. |
| Legal RAG benchmarks distinguish retrieval failure from generation failure. | [LegalBench-RAG](https://arxiv.org/abs/2408.10343) | Paper / benchmark | Failure taxonomy should separate retrieval miss, citation mismatch, reasoning error, amount error, and abstention. |

## Retrieval Design

| Claim | Source | Source type | Application to Proposer |
| --- | --- | --- | --- |
| Naive chunking can lose document context; late chunking embeds larger context before deriving chunk vectors. | [Guenether et al., "Late Chunking"](https://arxiv.org/abs/2409.04701) | Paper | Ombudsman order paragraphs often depend on earlier findings, so ingestion should eventually test contextual or late chunking. |
| HyDE retrieves by embedding a hypothetical answer/document, then grounding back to real corpus neighbors. | [Gao et al., "Precise Zero-Shot Dense Retrieval without Relevance Labels"](https://arxiv.org/abs/2212.10496) | ACL paper | Useful as an experiment for lay-language repair facts, but generated hypotheticals must never become evidence. |
| Interleaving retrieval with reasoning helps multi-step QA compared with one-shot retrieve-and-read. | [Trivedi et al., IRCoT](https://arxiv.org/abs/2212.10509) | ACL paper | Split retrieval into liability, delay, vulnerability, complaint handling, and remedy/order passes. |
| Hierarchical retrieval can search multiple abstraction levels across long documents. | [RAPTOR](https://arxiv.org/abs/2401.18059) | ICLR paper | Longer-term option for Ombudsman decisions; final citations must still point to raw spans. |
| BM25 remains a strong zero-shot baseline in heterogeneous retrieval. | [BEIR](https://arxiv.org/abs/2104.08663) | Benchmark paper | Keep sparse+dense retrieval for exact Ombudsman phrases like "reasonable redress", "must pay", and "severe maladministration". |
| Cross-encoders score query-document pairs with full token interaction. | [SentenceTransformers CrossEncoder docs](https://www.sbert.net/examples/cross_encoder/applications/README.html) | Library docs | Rerank 30-100 candidates before prompt assembly once latency budget allows. |
| ColBERT late interaction preserves token-level matching while precomputing document representations. | [ColBERT](https://arxiv.org/abs/2004.12832) and [ColBERTv2](https://arxiv.org/abs/2112.01488) | SIGIR / NAACL papers | Longer-term retriever candidate for legal terminology and exact remedy phrases. |

## Graph-Augmented RAG

| Claim | Source | Source type | Application to Proposer |
| --- | --- | --- | --- |
| GraphRAG is useful for corpus sensemaking but does not replace precise evidence retrieval. | [Microsoft GraphRAG paper](https://arxiv.org/abs/2404.16130) | Paper | KG should support issue decomposition and consistency checks, not outrank cited determination text. |
| LLM-generated KGs can contain redundant entities and unreliable relations; denoising and provenance matter. | [Less is More: Denoising Knowledge Graphs for RAG](https://arxiv.org/abs/2510.14271) | Paper | Present KG as a provenance-backed evidence ledger with confidence and missingness. |
| GraphRAG evaluation should inspect graph construction, retrieval, answer generation, and reasoning coherence separately. | [GraphRAG-Bench](https://arxiv.org/abs/2506.02404) | Benchmark paper | Log whether KG facts helped, were ignored, contradicted retrieval, or caused over-conservative answers. |

## Prompting And Legal Outcome Prediction

| Claim | Source | Source type | Application to Proposer |
| --- | --- | --- | --- |
| Legal reasoning benchmarks separate issue spotting, rule application, interpretation, and case comparison. | [LegalBench](https://arxiv.org/abs/2308.11462) | NeurIPS benchmark | Prompt should separate issue/finding analysis from remedy estimation. |
| Legal judgment prediction is multi-task: facts, applicable standard, outcome, and sometimes remedy/penalty. | [Feng et al., "Legal Judgment Prediction: A Survey"](https://www.ijcai.org/proceedings/2022/765) | IJCAI survey | Avoid one-shot "winner plus amount"; stage liability, label mapping, remedy band, then point estimate. |
| LegalBench-RAG emphasizes precise snippets over broad document-level context. | [LegalBench-RAG](https://arxiv.org/abs/2408.10343) | Paper / benchmark | Final reasoning should cite exact supporting passages; unsupported predictions should abstain. |

## Calibration And Imbalance

| Claim | Source | Source type | Application to Proposer |
| --- | --- | --- | --- |
| Platt scaling and isotonic regression are standard post-hoc calibration methods. | [Niculescu-Mizil and Caruana, "Predicting Good Probabilities"](https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf) | ICML paper | Use held-out calibration data before treating raw LLM confidence as a probability. |
| Temperature scaling can substantially improve neural model calibration. | [Guo et al., "On Calibration of Modern Neural Networks"](https://arxiv.org/abs/1706.04599) | ICML paper | Candidate method if model logits or stable confidence scores are available. |
| Balanced accuracy macro-averages recall over classes and is designed for imbalanced data. | [scikit-learn balanced accuracy docs](https://scikit-learn.org/stable/modules/model_evaluation.html#balanced-accuracy-score) | Official docs | The 49/1 Ombudsman set must report balanced accuracy, macro-F1, per-class recall, abstention rate, and majority baseline. |
| Reject/abstention methods expose an error/coverage trade-off. | [Conformal prediction tutorial](https://arxiv.org/abs/2107.07511) | Tutorial paper | Treat raw `uncertain` as abstention and report covered accuracy plus coverage-adjusted accuracy. |

## Amount And Remedy Prediction

| Claim | Source | Source type | Application to Proposer |
| --- | --- | --- | --- |
| Ombudsman remedies are fair, proportionate, non-punitive, and tied to impact, duration, vulnerability, distress, inconvenience, time, and trouble. | [Housing Ombudsman remedies guidance](https://www.housing-ombudsman.org.uk/centre-for-learning/key-topics/our-orders/ombudsmans-policy-and-guidance-on-remedies/) | Official regulator guidance | Estimate amount after finding severity, impact, duration, vulnerability, complaint handling, and comparable awards. |
| The Ombudsman guidance does not create fixed compensation tariffs. | [Housing Ombudsman remedies guidance](https://www.housing-ombudsman.org.uk/centre-for-learning/key-topics/our-orders/ombudsmans-policy-and-guidance-on-remedies/) | Official regulator guidance | Repo bands must be described as modelling/eval bands, not official Ombudsman bands. |
| Award decisions often move from categorical severity judgments to numeric award selection. | [The Gist of Juries](https://pmc.ncbi.nlm.nih.gov/articles/PMC5654568/) | Peer-reviewed law/psychology article | Predict remedy band first, then a calibrated point estimate inside the band. |

## Ranked Research Hypotheses

1. Add issue-specific and remedy/order retrieval passes, then dedupe and rerank.
2. Require a liability ledger, comparator-award ledger, remedy band, and final calibrated estimate in the Ombudsman prompt.
3. Keep KG facts as provenance-backed context with missingness, not as authoritative replacement for cited determinations.
4. Report macro-F1, balanced accuracy, abstention rate, covered accuracy, and coverage-adjusted accuracy beside accuracy/Brier/ECE.
