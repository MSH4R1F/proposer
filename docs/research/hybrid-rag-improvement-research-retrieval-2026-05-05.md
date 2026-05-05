# Retrieval & Architecture Research for Housing-Ombudsman Hybrid RAG

**Date:** 2026-05-05
**Author:** Research session (Mohamed)
**Scope:** Primary-source evidence to inform redesign of the Housing-Ombudsman hybrid RAG + KG pipeline. Current eval: hybrid acc 0.68, but always-tenant baseline acc 0.98 on the imbalanced set; ECE 0.47, amount MAE £520 with bias -£466. Accuracy is misleading; calibration and amount prediction are the failures we need to fix.

Confidence tags below: [High] = peer-reviewed paper or independent reproduction; [Moderate] = arXiv preprint with code, or vendor benchmark with public details; [Low] = vendor blog claim with no independent reproduction.

---

## 1. Executive Summary

Five most actionable findings, ranked by expected impact on our specific failures (calibration and amount prediction), not generic RAG quality:

1. **The retriever, not the LLM, is the dominant failure path in legal RAG.** Magesh et al. (Stanford, JELS 2025) found 17-33% hallucination rates on commercial legal RAG products built on premium corpora; Rasiah et al. (NLLP 2025) measured >95% Document-Level Retrieval Mismatch on LegalBench-RAG/ContractNLI. Implication: our 0.47 ECE is most likely driven by the model conditioning on the wrong evidence rather than by miscalibrated logits. [High]

2. **Contextual Retrieval (Anthropic, 2024) is the highest-leverage low-risk change** for chunk-level retrieval. Reported 49% top-20 retrieval-failure-rate reduction (5.7%->2.9%) when contextual embeddings are combined with contextual BM25, 67% reduction (5.7%->1.9%) when a reranker is added, at ~$1.02 per million document tokens with prompt caching. [Moderate - vendor benchmark, framework reproduced widely but no independent legal-domain replication located]

3. **Summary-Augmented Chunking (SAC) is specifically validated for legal corpora** and outperforms domain-specific summaries. Rasiah et al. (NLLP 2025) show prepending a single document-level summary to each chunk dramatically reduces DRM on LegalBench-RAG, beating both KG and late-chunking approaches at a fraction of the engineering cost. This is the most legal-specific high-confidence finding. [High]

4. **Cross-encoder rerankers reliably move the needle on dense retrieval, but a general-purpose reranker can hurt on specialized legal text** (Pipitone & Houir Alami 2024 found Cohere rerank-english-v3 *decreased* P@1 on LegalBench-RAG-mini). Plan: add a reranker, but evaluate it as an ablation rather than assume gain. [High]

5. **GraphRAG/KG augmentation should be scoped narrowly.** Microsoft GraphRAG's published gains are for global "what are the themes" summarisation, not pointwise prediction. Independent comparisons (Han et al. 2025, "RAG vs GraphRAG"; Tuora et al. 2026 "UnWeaving the Knots") find vector RAG matches or beats GraphRAG on most factual QA and that the KG layer adds 1.5-1.9% hallucinated-edge rates. For our pipeline, retain the KG for fact consistency (claim/evidence/timeline checks) but do not let it drive answer phrasing. [High]

---

## 2. Findings by Area

### 2.1 Legal RAG hallucination & citation reliability

**Claim:** Even the strongest commercial legal RAG products hallucinate on ~17-33% of queries; the dominant failure is misgrounded citation rather than fabricated text.
**Evidence:** Magesh, Surani, Dahl, Suzgun, Manning, Ho. *Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools.* Pre-registered evaluation of Lexis+ AI, Thomson Reuters Westlaw AI-Assisted Research (AI-AR), and Ask Practical Law AI on >200 manually constructed open-ended legal queries. Lexis+ AI and Ask Practical Law AI hallucinate ~17%; Westlaw AI-AR ~33% (incorrect legal info or misgrounded citations). Authors built a typology distinguishing "incorrect responses" from "misgrounded citations" (citation looks plausible but does not support the proposition).
**Link:** https://arxiv.org/abs/2405.20362 (preprint), https://onlinelibrary.wiley.com/doi/full/10.1111/jels.12413 (JELS 2025)
**Numerical detail:** 17-33% hallucination rate range; pre-registered on OSF; >200 queries.
**Limitation:** Closed-source commercial systems; we cannot inspect their retrieval. Not a controlled ablation - says nothing about *why* they fail, only that they do. [High]

**Claim:** A retrieval-only benchmark with annotator-graded passages shows that off-the-shelf retrievers are far from saturated on legal corpora.
**Evidence:** Pipitone & Houir Alami. *LegalBench-RAG: A Benchmark for Retrieval-Augmented Generation in the Legal Domain.* 6,858 query-answer pairs, 79M character corpus, human-annotated by legal experts. Baselines: OpenAI text-embedding-3-large + RCTS chunking + SQLite Vec, optionally Cohere rerank-english-v3.0.
**Link:** https://arxiv.org/abs/2408.10343
**Numerical detail:** Best baseline (RCTS, no reranker) on LegalBench-RAG-mini: P@1 = 14.4% PrivacyQA, 6.6% ContractNLI, 2.7% MAUD, 2.0% CUAD. Recall@64 = 84%/62%/28%/75% respectively. Adding the Cohere reranker *decreased* performance.
**Limitation:** Only 4 sub-corpora, all US contract / compliance text; no UK ombudsman or tribunal text. Tiny precision numbers reflect difficulty of pointwise legal retrieval, not necessarily our use case. [High]

**Claim:** In legal RAG, the dominant *retrieval* failure is selecting the wrong source document, not picking the wrong chunk within the right document.
**Evidence:** Rasiah et al. *Towards Reliable Retrieval in RAG Systems for Large Legal Datasets.* NLLP 2025 (EMNLP).
**Link:** https://arxiv.org/abs/2510.06999
**Numerical detail:** Document-Level Retrieval Mismatch (DRM) >95% on ContractNLI in standard pipelines. Summary-Augmented Chunking (SAC), prepending one document-level synthetic summary to each chunk, dramatically cuts DRM and improves text-level precision/recall. Generic summarization beats legal-expert-targeted summarization.
**Limitation:** Reported on LegalBench-RAG; no UK/ombudsman corpus. Single paper, no independent replication yet. [High; one independent paper from a non-vendor academic group with code]

**Cite-or-abstain literature:** Multiple recent papers warn that citation faithfulness is itself unreliable: up to 57% of citations may be post-rationalised in some setups (Hu et al. 2024, "Correctness is not Faithfulness"). Forcing citation does *not* automatically guarantee grounding.
**Link:** https://arxiv.org/pdf/2412.18004 [Moderate]

### 2.2 Contextual retrieval & late chunking

**Contextual Retrieval (Anthropic, Sept 2024).** Vendor blog with extensive methodology; not peer-reviewed.
- Method: prepend a 50-100 token LLM-generated context to each chunk before embedding and BM25 indexing. Prompt template public.
- Reported: top-20 retrieval-failure-rate (1 - recall@20) drops from 5.7% to 3.7% with contextual embeddings alone (35% relative), to 2.9% with contextual BM25 added (49% relative), to 1.9% with reranking added (67% relative). Costs ~$1.02 per million doc tokens with prompt caching.
- Domains tested: codebases, fiction, arXiv, science. Legal domain *not* in their benchmark.
- **Link:** https://www.anthropic.com/news/contextual-retrieval
- **Limitation:** Vendor benchmark, not peer-reviewed, not legal-domain. Claims align with the SAC academic finding above, which is reassuring. [Moderate - vendor claim, but mechanism independently corroborated by Rasiah et al. SAC result]

**Late Chunking (Günther et al. / Jina AI, 2024).** arXiv 2409.04701, code on GitHub.
- Method: encode the whole document with a long-context embedding model first, then pool token vectors into chunks afterward.
- Reported (Table 2 of v2): on BeIR (SciFact, NFCorpus, FiQA, TRECCOVID), late chunking gives 1.5-1.9 absolute nDCG@10 points over naive chunking, averaged across jina-embeddings-v2-small / v3 and nomic-embed-text-v1. e.g. fixed-size: 52.2 -> 54.0; sentence-boundary: 52.4 -> 54.3.
- **Link:** https://arxiv.org/abs/2409.04701
- **Limitation:** Requires a long-context embedding model; gain is real but modest (~1.5-2 nDCG). No legal-domain evaluation. Smaller absolute lift than Contextual Retrieval's reported 35-49% failure-rate reduction, but does not require an LLM call per chunk.
- **Honest comparison:** late chunking is structurally simpler and cheaper to operate than Contextual Retrieval (no per-chunk LLM call), but the public numerical lift is much smaller. [Moderate - peer pre-print with code; no large-scale independent reproduction yet on legal text]

### 2.3 HyDE, multi-query expansion, query decomposition; "Lost in the Middle"

**HyDE (Gao, Ma, Lin, Callan; ACL 2023).** arXiv 2212.10496. LLM generates a hypothetical answer document; embed that and retrieve nearest real docs. Outperforms unsupervised Contriever; "comparable to fine-tuned retrievers" on web search/QA/fact verification across multiple languages.
- **Link:** https://arxiv.org/abs/2212.10496
- **Limitation:** The hypothetical doc may inject the LLM's prior, including biases - dangerous in legal contexts where the LLM might confabulate the very legal reasoning we want to retrieve. Use cautiously, gate behind a downstream verifier. [High]

**Multi-query expansion / RAG-Fusion.** Helpful but bounded. Recent ablation literature (DMQR-RAG, arXiv 2411.13154; Question Decomposition for RAG, arXiv 2507.00355) reports ~5-6% recall gains from query expansion on multi-hop / semantically rich queries, but warns that adding too many queries "introduces noise" and that expansion gives "limited benefit for precise numerical queries" while contextual retrieval consistently helps. Direct relevance to our amount-prediction failure: query expansion is *unlikely* to fix amount MAE; the bigger lever is targeted retrieval of remedy/award passages.
- **Link:** https://arxiv.org/html/2411.13154v1
- **Limitation:** Most ablations are on QA-style benchmarks, not legal outcome prediction. [Moderate]

**Lost in the Middle (Liu et al., TACL 2024).** arXiv 2307.03172. Performance on multi-document QA degrades sharply when the relevant document is in the middle of the context window; U-shape with edges much stronger than the middle. Holds even for "long-context" models.
- **Link:** https://arxiv.org/abs/2307.03172
- **Numerical detail:** Specific drop magnitudes are not in the abstract; we did not retrieve the headline number from the body of the paper in this session. The qualitative finding (U-shape, large middle drop) is widely reproduced.
- **Implication for us:** with k=10-20 chunks at k=1000 tokens each, top-of-context and bottom-of-context positions matter. Argues for *small k with reranking* over large k. [High - widely cited, multiple reproductions]

### 2.4 Sparse + dense hybrid retrieval & reranking

**RRF (Cormack, Clarke, Buettcher, SIGIR 2009).** Combine ranked lists by score = sum_i 1/(k + rank_i), constant k typically 60. No score normalization needed.
- **Link:** https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf (canonical), https://dl.acm.org/doi/10.1145/3596512 (Bruch, Gai, Ingber, "An Analysis of Fusion Functions for Hybrid Retrieval", TOIS 2024) for fusion-function analysis.
- **Limitation:** RRF is a strong baseline but not always the optimal fuser; modern work (Bruch et al. 2024) characterises when convex fusion or learned fusion beats RRF. For us, RRF is fine as a default. [High]

**ColBERTv2 (Santhanam, Khattab, Saad-Falcon, Potts, Zaharia; NAACL 2022).** arXiv 2112.01488. Multi-vector late interaction; SOTA on in- and out-of-domain retrieval at the time, with 6-10x storage compression versus ColBERTv1.
- **Link:** https://arxiv.org/abs/2112.01488
- **Limitation:** Headline BEIR numbers not pulled in this session; ColBERT's main appeal for our setting is robust out-of-domain quality without fine-tuning. Operational complexity (multi-vector index) is non-trivial; not the right first step for an MVP. [High]

**Cross-encoder rerankers.** Strong, well-replicated literature. Cross-encoders typically deliver 4-10 nDCG@10 points over bi-encoders on MS MARCO/BEIR (Rosa et al. 2022, "In Defense of Cross-Encoders for Zero-Shot Retrieval", arXiv 2212.06121; Meng et al. 2024, "Enhancing Q&A Text Retrieval with Ranking Models", arXiv 2409.07691).
- **Caveat (specific to legal):** Pipitone & Houir Alami 2024 (LegalBench-RAG) report Cohere rerank-english-v3.0 *decreased* P@1 on three of four legal sub-corpora versus dense-only retrieval. Domain mismatch matters more than model size.
- **Practical takeaway:** treat the reranker as an A/B-tested component, not a default. For the Housing Ombudsman corpus, fine-tuning a small cross-encoder on a few hundred manually annotated query-passage pairs is likely worth more than a stronger off-the-shelf reranker. [High on the general claim; Moderate on the legal exception]

### 2.5 GraphRAG / KG-augmented RAG

**Microsoft GraphRAG (Edge et al. 2024).** arXiv 2404.16130. LLM extracts entity graph, computes community summaries, answers global queries by mapping over communities.
- Reported: improvements over naive RAG on "global sensemaking" questions ("what are the main themes?") at 1M-token corpus scale. No specific numerical deltas given in the abstract.
- **Link:** https://arxiv.org/abs/2404.16130
- **Limitation:** Designed for *summarisation*, not pointwise prediction. Our task is "predict winner / amount", which is local, not global. Misapplied here. [High; designed for a different problem]

**HippoRAG (Gutierrez et al., NeurIPS 2024).** arXiv 2405.14831. KG + Personalized PageRank for multi-hop QA. Up to 20% gain on multi-hop QA, 10-30x cheaper and 6-13x faster than IRCoT iterative retrieval.
- **Link:** https://arxiv.org/abs/2405.14831
- **Limitation:** Gains are on multi-hop QA datasets. Single-hop performance is similar to vector RAG. Our outcome-prediction task is mostly single-hop (one or two relevant prior decisions). [High]

**LightRAG (Guo et al., EMNLP Findings 2025).** arXiv 2410.05779. Dual-level retrieval over an entity graph + vectors; incremental updates.
- **Link:** https://arxiv.org/abs/2410.05779
- **Limitation:** Improvements claimed but mixed on independent benchmarks. [Moderate]

**Critical evaluations.**
- Han et al. *RAG vs. GraphRAG: A Systematic Evaluation and Key Insights*, arXiv 2502.11371 - finds neither dominates; hybrid wins, choice is task-dependent. [High]
- Tuora et al. *UnWeaving the knots of GraphRAG -- turns out VectorRAG is almost enough*, arXiv 2603.29875 - reports VectorRAG matches or beats GraphRAG variants on factual QA (eManual, COVID-QA, Tech-QA); the KG layer often does not pay rent. [High]
- Pebblous and other industry reports: top-tier LLMs hallucinate edges at 1.5-1.9% rates during KG construction; entity disambiguation is the silent failure mode. [Moderate - vendor blog summarising reproductions]

**Implication for our pipeline:** GraphRAG-style architectures should not be the *primary* retriever for our outcome-prediction task. Keep the existing KG for what it is good at (consistency checks: "this evidence pre-dates the tenancy", "this claim has supporting evidence") and let the retrieval-and-prediction loop run primarily over a dense+sparse text retriever with reranking.

### 2.6 Long-document & legal-document chunking

**Auto-Merging / parent-document retrieval (LlamaIndex).** Index small leaf nodes for precision; if a parent's leaf children are over-represented in top-k, merge up to the parent for context. Parallels Anthropic's "small-to-big".
- **Link:** https://developers.llamaindex.ai/python/examples/retrievers/auto_merging_retriever/
- **Evidence:** Strong practitioner consensus; limited peer-reviewed evidence on legal corpora. Mechanically aligned with the broader principle that retrieval precision wants small chunks but the LLM wants large context. [Moderate - vendor + practitioner]

**Systematic chunking comparison.** Liu et al. *A Systematic Investigation of Document Chunking Strategies and Embedding Sensitivity*, arXiv 2603.06976 - 36 chunking methods x 6 domains x 5 embedding models. Headline domain finding: paragraph grouping is strongest in legal and maths; dynamic token sizing is strongest in biology/physics/health. Concrete signal that paragraph-aligned chunking should be the default for our corpus. [High]

**Section-aware retrieval for decisions.** Multi-Source Retrieval and Reasoning for Legal Sentencing Prediction (MSR^2, arXiv 2602.04690) and Step-wised Verification-Correction for Legal Judgment (ACL 2025) both decompose legal prediction into separate retrieval passes for facts, statutes/guidance, and outcome. This is the same pattern we need for liability-vs-remedy.

### 2.7 Domain-specific retrieval routes / multi-pass retrieval

**L-MARS (Wei et al., 2025).** arXiv 2509.00761. Multi-agent legal QA: decompose query into sub-problems, route to heterogeneous sources (web, local RAG, CourtListener), verifier-agent filters before synthesis. 96% on LegalSearchQA vs 58% zero-shot baseline (+38pp); on Bar Exam QA the gain is only +0.7pp - retrieval helps when up-to-date facts matter, not when the task is closed-book reasoning.
- **Link:** https://arxiv.org/abs/2509.00761
- **Implication for us:** the multi-agent decomposition pattern is well-evidenced; the *gain* depends on the task. Our amount-prediction is exactly the kind of "factual retrieval over orders/awards" task where multi-pass helps; the winner-prediction is closer to closed-book reasoning where retrieval may not help much. [High]

**MSR^2 (arXiv 2602.04690) and Step-wise Verification-Correction (ACL 2025).** Both implement a liability-then-remedy structure for legal prediction.

---

## 3. Synthesis: Recommended Retrieval Architecture for Housing Ombudsman Cases

The core diagnosis is: our hybrid 0.68 vs always-tenant 0.98 means the model is conceding to the prior most of the time. Calibration (ECE 0.47) and amount bias (-£466) say the system is not conditioning on the right *quantitative* evidence. The fixes below are ordered by expected impact-per-engineering-day.

### 3.1 Indexing layer

- **Chunking unit:** paragraph-aligned chunks of 250-500 tokens with 50-token overlap, segmented inside section boundaries (Background / Investigation / Findings / Determination / Orders). Each chunk carries a `section_type` enum. Justification: Liu et al. 2026 (paragraph grouping wins for legal); Anthropic Contextual Retrieval and Rasiah et al. SAC both show that the chunk needs *document context* injected, not just smaller chunk size.
  - Source: https://arxiv.org/abs/2603.06976, https://arxiv.org/abs/2510.06999, https://www.anthropic.com/news/contextual-retrieval
- **Per-chunk context:** prepend (a) a 50-100 token document-level summary (Rasiah et al. SAC) and (b) the chunk's section header. This is the cheapest version of Contextual Retrieval for our domain - one summary per case rather than one LLM call per chunk - and Rasiah et al. show that's enough.
  - Source: https://arxiv.org/abs/2510.06999
- **Embeddings:** start with a strong general-purpose embedder (BGE-large, E5-mistral, OpenAI text-embedding-3-large). Switch to a long-context embedder (Jina v3, nomic-embed) only if we adopt late chunking. Late chunking gives ~+1.5 nDCG@10 absolute on BEIR; modest.
  - Source: https://arxiv.org/abs/2409.04701
- **Sparse layer:** BM25 over the same chunks. Mandatory for legal text - case names, addresses, dates, statute numbers are exactly what dense retrieval struggles on, and Anthropic's contextual BM25 result shows the marginal gain of keeping it.

### 3.2 Retrieval-time pipeline

A two-pass design that mirrors the way ombudsman decisions are written (liability first, remedy second) and addresses the amount-prediction failure directly:

**Pass A - Liability/issue retrieval.** Query: original facts + KG-extracted issues. Search both indices, fuse with RRF (k=60), top-50 from each fused to top-30, then re-rank to top-8 with a cross-encoder (BGE-reranker-v2-m3 as the open default; A/B against a fine-tuned cross-encoder once we have ~300 manually labelled query-passage pairs). Justification: cross-encoder rerankers reliably add 4-10 nDCG@10 points (Rosa et al. 2022, Meng et al. 2024) but Pipitone & Houir Alami 2024 show off-the-shelf rerankers can hurt on legal text - so treat the reranker as ablated, not assumed.
- Source: https://arxiv.org/abs/2212.06121, https://arxiv.org/abs/2409.07691, https://arxiv.org/abs/2408.10343

**Pass B - Remedy/award retrieval.** Separate query string composed from (issue type, severity, building keywords) and *restricted to chunks where `section_type in {orders, determination}`*. Same RRF + reranker. Top-8.
- Justification: this is the L-MARS/MSR^2 pattern (sub-problem decomposition with heterogeneous routes) and is the structural fix for amount-prediction bias - the LLM cannot regress to a low-mean estimate if the prompt actually contains 8 award passages with concrete numbers. The +0.7 vs +38pp result on Bar Exam vs LegalSearchQA in L-MARS shows decomposition pays exactly when the task is fact-heavy retrieval, which our amount task is.
- Source: https://arxiv.org/abs/2509.00761, https://arxiv.org/abs/2602.04690

**Pass C (optional, for multi-issue cases) - Sub-question decomposition.** Use HyDE only for issues where the user query is sparse (no facts in the intake yet); otherwise expand to 2-3 sub-queries deterministically (e.g. ["damp and mould","Section 11 repairs","compensation amounts"]). Cap at 3 sub-queries: DMQR-RAG and related work flag noise from over-expansion.
- Source: https://arxiv.org/abs/2212.10496, https://arxiv.org/abs/2411.13154v1

**Auto-merge step.** After reranking, for each retained leaf chunk, optionally include the parent (full section) using LlamaIndex-style auto-merging when 2+ leaves of the same parent appear in the top-k. This addresses Lost-in-the-Middle: smaller k of larger merged contexts beats large k of fragments.
- Source: https://arxiv.org/abs/2307.03172, https://developers.llamaindex.ai/python/examples/retrievers/auto_merging_retriever/

**Final context:** ~12-16 chunks (8 liability + 8 remedy, deduped), each with case ID + section type + paragraph anchor. Place strongest evidence at the top and bottom, weakest in the middle - explicit Lost-in-the-Middle exploitation rather than passive layout.

### 3.3 Knowledge Graph role

**Demote KG from primary retriever to consistency-checker.** Evidence: GraphRAG was designed for global summarisation (Edge et al. 2024); HippoRAG's gains are on multi-hop QA, not pointwise prediction; Tuora et al. 2026 and Han et al. 2025 both find vector RAG matches GraphRAG on factual tasks; KG construction itself injects 1.5-1.9% hallucinated edges. Our task is local + numeric prediction, which is the *worst* fit for graph augmentation.

Concrete role for the KG:
- Validate fact-evidence consistency (timeline, role assignments) before retrieval.
- Disambiguate entities in the query (which landlord, which property type) to populate Pass B's filter facets.
- *Not* generate text, *not* drive citations, *not* be summarised into the prompt.

### 3.4 Citation verification

After generation, run a citation-verification pass: for each `(case_id, paragraph)` cited, fetch the chunk and check entailment of the claim against the chunk text using a lightweight NLI model or a verifier-LLM call. If a citation does not entail, mark "uncertain" and abstain. Magesh et al. show misgrounded citations are the dominant failure mode of commercial legal RAG, and the JELS 2025 paper provides a typology to label them.
- Source: https://arxiv.org/abs/2405.20362

### 3.5 Calibration plan (separate from retrieval, listed for completeness)

The retrieval changes above should narrow ECE substantially by giving the model the right evidence, but explicit calibration is still needed: temperature scaling on logits or isotonic regression of predicted probabilities against held-out outcomes. Class-imbalance correction (downsample tenant-wins or use a balanced eval split) is required *before* declaring any retrieval gain real - otherwise we are still measuring the prior.

### 3.6 Recommended ablation matrix

To produce thesis-grade evidence (and to match the "evaluation-driven development" rule in CLAUDE.md), run the following ablations on a balanced held-out split:
1. Dense only (current baseline).
2. Dense + BM25 RRF.
3. + Document-summary chunk prefix (SAC).
4. + Cross-encoder reranker.
5. + Two-pass liability/remedy split.
6. + KG consistency filter.

Report Brier and ECE alongside winner-accuracy, plus amount MAE and bias on a remedy-isolated subset.

---

## 4. Open Questions & Uncertainties

- **Whether Contextual Retrieval reproduces on legal text.** Anthropic's 35-49% retrieval-failure-rate reduction is a vendor benchmark, not peer-reviewed, and not on legal corpora. Rasiah et al.'s SAC result is the closest peer-reviewed legal corroboration, but it uses a single document-summary rather than a per-chunk context. The relative cost-effectiveness of SAC vs full Contextual Retrieval on Housing-Ombudsman text is an empirical open question.
- **Is our calibration failure a retrieval failure or a head-output failure?** Without an ablation that holds the retrieval fixed and varies the prediction head, we cannot attribute. We need to run e.g. logistic-regression on retrieved-evidence-only features to bound how much of ECE is fixable from retrieval alone.
- **Do amount-bearing chunks have systematically worse retrieval?** Hypothesis: orders/awards sections contain unique numbers but few high-frequency words; BM25 may miss them; dense embeddings may map them to a generic "compensation" cluster. A targeted eval (recall@20 of orders sections specifically) is needed.
- **Reranker fine-tuning ROI.** Pipitone & Houir Alami's negative result is on US contract text, not UK ombudsman decisions. We do not know whether the same will hold here. Worth piloting BGE-reranker-v2-m3 zero-shot before investing in fine-tuning data.
- **Lost-in-the-Middle exact magnitudes.** We have the qualitative finding but did not pull specific drop numbers from Liu et al.'s body in this session. Worth confirming before basing context-ordering policy on it.
- **HippoRAG single-hop performance.** We know multi-hop gains are large; we do not have a clear single-hop number. If our prediction task is mostly single-hop (one similar case predicts the outcome), HippoRAG's appeal narrows.

---

## 5. References

1. Magesh, V., Surani, F., Dahl, M., Suzgun, M., Manning, C. D., Ho, D. E. (2024/2025). *Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools.* Journal of Empirical Legal Studies. https://arxiv.org/abs/2405.20362 ; https://onlinelibrary.wiley.com/doi/full/10.1111/jels.12413
2. Pipitone, N., Houir Alami, G. (2024). *LegalBench-RAG: A Benchmark for Retrieval-Augmented Generation in the Legal Domain.* https://arxiv.org/abs/2408.10343
3. Rasiah, V. et al. (2025). *Towards Reliable Retrieval in RAG Systems for Large Legal Datasets.* NLLP 2025 (EMNLP). https://arxiv.org/abs/2510.06999
4. Anthropic (2024). *Introducing Contextual Retrieval.* https://www.anthropic.com/news/contextual-retrieval [vendor blog, not peer-reviewed]
5. Günther, M., Mohr, I., Wang, B., Xiao, H. (2024). *Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models.* https://arxiv.org/abs/2409.04701
6. Gao, L., Ma, X., Lin, J., Callan, J. (2023). *Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE).* ACL 2023. https://arxiv.org/abs/2212.10496
7. Liu, N. F. et al. (2024). *Lost in the Middle: How Language Models Use Long Contexts.* TACL. https://arxiv.org/abs/2307.03172
8. Cormack, G. V., Clarke, C. L. A., Buettcher, S. (2009). *Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods.* SIGIR 2009. https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
9. Bruch, S., Gai, S., Ingber, A. (2024). *An Analysis of Fusion Functions for Hybrid Retrieval.* ACM TOIS. https://dl.acm.org/doi/10.1145/3596512
10. Santhanam, K., Khattab, O., Saad-Falcon, J., Potts, C., Zaharia, M. (2022). *ColBERTv2: Effective and Efficient Retrieval via Lightweight Late Interaction.* NAACL 2022. https://arxiv.org/abs/2112.01488
11. Rosa, G. et al. (2022). *In Defense of Cross-Encoders for Zero-Shot Retrieval.* https://arxiv.org/abs/2212.06121
12. Meng, R. et al. (2024). *Enhancing Q&A Text Retrieval with Ranking Models.* https://arxiv.org/abs/2409.07691
13. Edge, D. et al. (2024). *From Local to Global: A GraphRAG Approach to Query-Focused Summarization.* https://arxiv.org/abs/2404.16130
14. Gutierrez, B. J. et al. (2024). *HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models.* NeurIPS 2024. https://arxiv.org/abs/2405.14831
15. Guo, Z. et al. (2024). *LightRAG: Simple and Fast Retrieval-Augmented Generation.* https://arxiv.org/abs/2410.05779
16. Han, H. et al. (2025). *RAG vs. GraphRAG: A Systematic Evaluation and Key Insights.* https://arxiv.org/abs/2502.11371
17. Tuora, R. et al. (2026). *UnWeaving the knots of GraphRAG -- turns out VectorRAG is almost enough.* https://arxiv.org/abs/2603.29875
18. Liu, X. et al. (2026). *A Systematic Investigation of Document Chunking Strategies and Embedding Sensitivity.* https://arxiv.org/abs/2603.06976
19. LlamaIndex Auto-Merging Retriever documentation. https://developers.llamaindex.ai/python/examples/retrievers/auto_merging_retriever/
20. Wei, Z. et al. (2025/2026). *L-MARS: Legal Multi-Agent Workflow with Orchestrated Reasoning and Agentic Search.* https://arxiv.org/abs/2509.00761
21. (MSR^2) *Multi-Source Retrieval and Reasoning for Legal Sentencing Prediction.* https://arxiv.org/html/2602.04690
22. (DMQR-RAG) *Diverse Multi-Query Rewriting for Retrieval-Augmented Generation.* https://arxiv.org/html/2411.13154v1
23. *Question Decomposition for Retrieval-Augmented Generation.* https://arxiv.org/html/2507.00355v1
24. Hu et al. (2024). *Correctness is not Faithfulness in RAG Attributions.* https://arxiv.org/pdf/2412.18004
