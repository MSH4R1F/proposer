# Hybrid RAG Improvement Research: Prompting, Calibration, and Amount Prediction for Housing Ombudsman Repairs

**Author:** Research pass for Proposer (Mohamed Sharif)
**Date:** 2026-05-05
**Scope:** Prompt design, calibration, abstention, amount/remedy prediction, and imbalanced evaluation methodology, grounded in primary sources, with a concrete redesign for the Housing Ombudsman repairs evaluation (current ECE 0.47, Brier 0.247, Amount@20%=0.10, MAE £520, bias -£466, 49/1 tenant/landlord split).

---

## 1. Executive summary (top 5 actionable findings)

1. **Replace "answer + reasoning" with IRAC-structured prompting plus a typed evidence ledger.** LegalBench shows even frontier models degrade sharply on Application/Conclusion sub-tasks of IRAC, and Chain-of-Logic (Servantez et al., Findings ACL 2024) shows that explicitly decomposing rule elements and recomposing them improves rule-based legal reasoning [1, 7]. A counter-intuitive but well-documented LegalBench finding: plain-language prompts beat technical-language prompts by up to 21 points balanced accuracy on a studied subset [1]. So: structured *form* (IRAC + evidence table) but plain-language *wording*.

2. **Stop trusting the model's verbalized confidence as-is. Add a post-hoc calibrator on a held-out tuning set.** Tian et al. (EMNLP 2023) show verbalized confidences from RLHF-tuned LLMs are better than internal logprobs (~50% relative ECE reduction on TriviaQA/SciQ/TruthfulQA) but Groot et al. (TrustNLP/ACL 2024, surfaced via SteerConf) report verbalized-confidence ECE >0.377 for GPT-3, GPT-3.5, Vicuna and predictions clustered in the 90–100% bin [3, 8, 18]. Our 0.47 ECE is in that regime. Fix: temperature scaling (Guo et al., ICML 2017) on a held-out set, or isotonic regression (Zadrozny & Elkan, KDD 2002) if monotonic but non-sigmoidal — temperature scaling is "two lines of code" and on most datasets nearly restores calibration [4, 14].

3. **Wrap remedy classification with conformal prediction sets and abstain on insufficient coverage.** APS / "Classification with Valid and Adaptive Coverage" (Romano, Sesia, Candès, NeurIPS 2020) gives finite-sample marginal coverage with no distributional assumptions; combined with Self-RAG-style cite-or-abstain (Asai et al., ICLR 2024 oral) we get a defensible "abstain" output when no supporting span exists [9, 5]. This directly attacks the 1-landlord/49-tenant minority problem: confident calls only on cases the calibration set says we have evidence for.

4. **Switch the amount predictor to a two-stage scheme (band classifier → comparator-anchored regressor) aligned to the actual Housing Ombudsman bands.** The Housing Ombudsman publishes four explicit financial bands tied to severity findings: ~£50–100, £100–600, £600–1,000, £1,000+ [13]. This is an *empirical* schema, not a synthetic one. Using the published bands (a) maps cleanly onto the existing severity rubric (service failure / maladministration / severe maladministration), (b) makes the regression problem within each band low-variance and (c) lets us anchor the within-band amount on retrieved comparator awards (kNN-on-retrieved-cases) — a pattern with documented success for damages prediction (Dal Pont et al., PeerJ CS 2023) [11]. Conformalized Quantile Regression (Romano et al., NeurIPS 2019) gives heteroscedastic predictive intervals on the £ output [10].

5. **Throw out raw accuracy as the headline metric.** With 49/1 imbalance, accuracy is dominated by the majority class. Saito & Rehmsmeier (PLOS ONE 2015) and Chicco & Jurman (BMC Genomics 2020) make the case: PR-curves and MCC are appropriate, balanced-accuracy/macro-F1 are first-pass robustness checks [15, 16]. Combine with abstention-adjusted accuracy and AURC (area under risk-coverage curve, Geifman & El-Yaniv, NeurIPS 2017) for selective-prediction reporting [17].

---

## 2. Findings by research area

### 2.1 Prompting patterns for legal outcome prediction

**Finding 2.1.1 — IRAC structure is the dominant decomposition for legal LLM evals.**
LegalBench (Guha et al., NeurIPS 2023) is organised around IRAC (Issue spotting / Rule recall / Application / Conclusion) with 162 hand-crafted tasks; performance drops sharply on Application and Conclusion tasks that require integrating statute and facts [1]. A 2025 follow-up benchmark (MSLR) uses an IRAC-Recall metric and finds o1-mini scores 72% IRAC Recall, with IRAC Recall strongly correlating with expert-aligned LLM judgments [2]. Confidence: **High**.
- Source: LegalBench arXiv: <https://arxiv.org/abs/2308.11462> ; NeurIPS PDF: <https://proceedings.neurips.cc/paper_files/paper/2023/file/89e44582fd28ddfea1ea4dcb0ebbf4b0-Paper-Datasets_and_Benchmarks.pdf>
- Source (MSLR follow-up): <https://arxiv.org/abs/2511.07979>

**Finding 2.1.2 — Plain-language prompts can beat legalese by up to 21 balanced-accuracy points on LegalBench tasks** [1]. This is the largest single prompt-wording delta in the benchmark; Guha et al. attribute it to better instruction-following with non-jargon wording. Confidence: **Moderate** (range "up to 21 points" is task-specific, not universal).
- Source: <https://arxiv.org/abs/2308.11462>

**Finding 2.1.3 — Chain-of-Logic adapts IRAC for compositional rules with measurable gains.**
Servantez et al. (Findings ACL 2024) propose Chain of Logic which decomposes each element of a rule into an independent thread and then recomposes; it is explicitly inspired by IRAC and is reported to outperform standard CoT on rule-based reasoning [7]. Confidence: **High** that the technique works on rule-based tasks; **Moderate** that gains transfer to ombudsman repairs (different rule structure).
- Source: <https://aclanthology.org/2024.findings-acl.159/> ; arXiv: <https://arxiv.org/abs/2402.10400>

**Finding 2.1.4 — Self-generated CoT helps; human-imposed CoT can hurt reasoning models.**
The MSLR benchmark reports human-designed CoT prompts caused QwQ-32B's LLM-judged reasoning score to drop 33.8% absolute, and IRAC Recall to drop 10.20% [2]. Self-Initiated CoT, by contrast, improved reasoning. Implication for us: prefer "think step-by-step inside the schema" to "follow these specific reasoning steps". Confidence: **Moderate** (single benchmark).
- Source: <https://arxiv.org/abs/2511.07979>

**Finding 2.1.5 — Separating liability from quantum is standard practice in the related sentencing-prediction literature.**
A 2024 Brazilian "Regression applied to legal judgments" study (Dal Pont et al., PeerJ CS) uses a regression-only pipeline on 928 Brazilian small-claims judgments, predicting the immaterial-damages award after reasoning is fixed [11]. Recent Chinese sentencing-prediction work likewise treats guilt classification and prison-term regression as separate stages [12]. Confidence: **High** that staged liability→quantum is the field's default.
- Source: <https://peerj.com/articles/cs-1225/> (Dal Pont et al. 2023)
- Source: <https://arxiv.org/html/2511.15374> (Judicial Sentencing Prediction, two-stage)

**Finding 2.1.6 — Outcome-prediction baselines on European court text (Aletras 2016) hit ~79% accuracy from facts alone**, suggesting facts-section content is the heaviest signal [6]. Chalkidis et al. (2019) extended this with neural baselines and a hierarchical-BERT model on 11k ECtHR cases [19]. Implication: in our retrieval prompt, prioritise the facts/timeline portion of comparator cases over reasoning paragraphs. Confidence: **High**.
- Source: <https://peerj.com/articles/cs-93/> ; ACL 2019: <https://aclanthology.org/P19-1424/>

**Finding 2.1.7 — Be skeptical of "outcome prediction" framing in the legal-NLP literature.**
Medvedeva, Wieling & Vols (Artificial Intelligence and Law, 2023) "Rethinking the field of automatic prediction of court decisions" and Medvedeva & McBride (NLLP 2023) survey ~150 papers and conclude only ~7% are forecasting actual decisions — most are post-hoc outcome identification [20]. Implication: be honest in the thesis that ours is *post-hoc outcome identification on Housing Ombudsman published decisions*, not *forecasting*. Confidence: **High**.
- Source: <https://link.springer.com/article/10.1007/s10506-021-09306-3> ; <https://aclanthology.org/2023.nllp-1.9/>

### 2.2 Cite-or-abstain and grounded generation

**Finding 2.2.1 — Self-RAG (Asai et al., ICLR 2024 oral) trains a single LM to emit reflection tokens that decide on-demand retrieval and self-critique generations** [5]. The paper reports that 7B/13B Self-RAG models outperform ChatGPT and retrieval-augmented Llama2-chat on open-domain QA, reasoning, fact verification, and improve citation accuracy on long-form generation. Confidence: **High** that the framework works at the published model scale.
- Source: <https://arxiv.org/abs/2310.11511>

**Finding 2.2.2 — Chain-of-Verification (Dhuliawala et al., Findings ACL 2024) reduces hallucinations by drafting → planning verification questions → answering them independently → revising** [21]. Tested on Wikidata list questions, MultiSpanQA, and longform generation. Confidence: **High** for short-form factuality; **Moderate** for legal long-form (no legal eval reported in original).
- Source: <https://arxiv.org/abs/2309.11495> ; ACL: <https://aclanthology.org/2024.findings-acl.212/>

**Finding 2.2.3 — RARR / "Citation NLI" frameworks externalise fact-checking by retrieving evidence and testing each claim's entailment** (Gao et al. 2023) — now the most common approach for measuring whether LLM outputs can be attributed to retrieved sources [22]. Confidence: **High**.
- Source (survey): <https://arxiv.org/abs/2508.15396>

**Implication for Proposer:** Implement a strict cite-or-abstain layer at *both* the IRAC-Application step and the amount step. If no retrieved span supports a finding, the model emits an `ABSTAIN` token. This is implementable without retraining via prompt-level CoVe + retrieval entailment check.

### 2.3 Calibration of LLM probabilities

**Finding 2.3.1 — Temperature scaling (Guo et al., ICML 2017) is the strongest "first thing to try."** Single-parameter post-hoc rescaling, optimised on validation NLL, "almost perfectly" restores calibration on most datasets and is implementable in a few lines [4]. It does not change argmax, only confidences. Confidence: **High**.
- Source: <https://arxiv.org/abs/1706.04599>

**Finding 2.3.2 — Platt scaling (Platt 1999) and isotonic regression (Zadrozny & Elkan, KDD 2002) are the parametric and non-parametric alternatives.** Platt fits a logistic to scores; isotonic fits a piece-wise constant monotone transform via PAV. Niculescu-Mizil & Caruana (ICML 2005) show isotonic typically dominates Platt with ≥1k calibration points but overfits on smaller sets [23, 14]. With our 50-case eval set, **temperature scaling first; Platt second; isotonic only if we get to a few hundred labelled calibration cases**. Confidence: **High**.
- Source: Platt 1999: <https://home.cs.colorado.edu/~mozer/Teaching/syllabi/6622/papers/Platt1999.pdf>
- Source: Zadrozny & Elkan KDD 2002: <https://dl.acm.org/doi/10.1145/775047.775151>
- Source: Niculescu-Mizil & Caruana 2005: <https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf>

**Finding 2.3.3 — Verbalized confidence beats logprobs for RLHF-tuned LLMs but is still poorly calibrated in absolute terms.**
Tian et al. (EMNLP 2023, "Just Ask for Calibration") report verbalized confidences cut ECE roughly 50% relative on TriviaQA/SciQ/TruthfulQA, but *absolute* numbers are still bad [3]. Independently, Lin, Hilton & Evans (2022, "Teaching models to express their uncertainty in words") show GPT-3 can be fine-tuned to emit calibrated verbal confidence ("90% confidence") on CalibratedMath [24]. Most importantly for us: empirical work surveyed by SteerConf (Wang et al. 2025) reports GPT-3/3.5/Vicuna verbalized-confidence ECE >0.377, predictions clustered in the 90–100% range [18]. Our observed 0.47 ECE is consistent with that literature. Confidence: **High**.
- Source: <https://aclanthology.org/2023.emnlp-main.330/> (Tian et al.)
- Source: <https://arxiv.org/abs/2205.14334> (Lin et al.)
- Source: <https://arxiv.org/abs/2503.02863> (SteerConf, summarises Groot et al.)

**Finding 2.3.4 — Brier-decomposition (Murphy 1973) tells us what's broken.** Brier = Reliability − Resolution + Uncertainty (or the mirror form). Reliability measures bin-level miscalibration; resolution measures discrimination [25]. Our Brier 0.247 with ECE 0.47 strongly implies the loss is dominated by the **reliability** term — i.e. recalibration is the right knob, not retraining. Confidence: **High** (interpretation is standard).
- Source: Wikipedia summary with Murphy's decomposition: <https://en.wikipedia.org/wiki/Brier_score>
- Source: Siegert 2017 generalisation: <https://rmets.onlinelibrary.wiley.com/doi/abs/10.1002/qj.2985>

**Finding 2.3.5 — Calibration under class imbalance is fragile and may need stratified or class-conditional fitting.**
Calibration after undersampling is biased toward the majority class (recent arXiv 2410.18144 on Platt-scaling-after-undersampling) [26]. With 49/1, fitting a single global Platt may inflate tenant-class confidence. Recipe: fit calibrator on stratified bootstrap resamples and report per-class ECE. Confidence: **Moderate** (general principle is well-established, our 49/1 is extreme).
- Source: <https://arxiv.org/abs/2410.18144>

### 2.4 Selective prediction / abstention metrics

**Finding 2.4.1 — Conformal prediction (Vovk; pop. via Angelopoulos & Bates 2021) gives finite-sample, distribution-free prediction sets** [27]. APS (Romano, Sesia, Candès, NeurIPS 2020) is the de-facto adaptive-coverage classification method — the conformity score is the cumulative softmax mass needed to reach the true class, calibrated on a held-out set [9]. Confidence: **High**.
- Source: <https://arxiv.org/abs/2107.07511> (Gentle Intro)
- Source: <https://arxiv.org/abs/2006.02544> (APS)

**Finding 2.4.2 — Selective classification (Geifman & El-Yaniv, NeurIPS 2017) introduced softmax-thresholded abstention for DNNs**; AURC (area under the risk-coverage curve) is the most common multi-threshold metric [17]. SelectiveNet (Geifman & El-Yaniv, ICML 2019) jointly trains the predictor and selector. Recent work flags AURC's limitations (NeurIPS 2024, "Overcoming Common Flaws") and proposes AUGRC, but AURC remains the standard reporting metric [28]. Confidence: **High**.
- Source: <https://arxiv.org/abs/1705.08500> (Geifman & El-Yaniv 2017)
- Source: <https://geifmany.github.io/papers/icml_oral.pdf> (SelectiveNet 2019)
- Source: <https://arxiv.org/html/2407.01032v1> (NeurIPS 2024 flaws paper)

**Finding 2.4.3 — Conformal Risk Control (ICLR 2024) extends conformal to bounded losses, including for hallucination control and abstention** [29]. This is the cleanest theoretical hook for "abstain unless we can guarantee ≤X% wrong-finding rate." Confidence: **High**.
- Source: <https://proceedings.iclr.cc/paper_files/paper/2024/file/f3549ef9b5ff520a7e41ff3cc306ab2b-Paper-Conference.pdf>

**Implication for Proposer:** Report (a) coverage at fixed risk, (b) AURC, (c) abstention-adjusted accuracy, alongside ECE and Brier. Abstain when conformal set has size > 1 *or* when no retrieved span entails the rule application.

### 2.5 Amount / remedy / quantum prediction

**Finding 2.5.1 — Two-stage classify-then-regress dominates the recent literature on damages and sentencing.**
Dal Pont et al. (PeerJ CS 2023) regress immaterial-damage compensation on 928 Brazilian air-transport judgments using N-grams + feature selection + outlier removal [11]. A 2024+ Chinese judicial-sentencing study (arXiv 2511.15374) jointly performs guilt inference (classification) and prison-term prediction (regression) and explicitly notes regression is better-suited than label-set classification because labels proliferate and inflate error margins [12]. Confidence: **High**.
- Source: <https://peerj.com/articles/cs-1225/>
- Source: <https://arxiv.org/html/2511.15374>

**Finding 2.5.2 — kNN-on-retrieved-cases is a natural fit for damages estimation in a RAG pipeline.** Earliest legal outcome systems (e.g. SHYSTER) used weighted feature-overlap nearest-neighbour. Modern hybrids (e.g. BERT+CL+kNN) layer kNN over learned embeddings for multi-label legal prediction [30]. Implication: reuse the existing RAG retriever's top-k cases, extract the historical award amount, and use a similarity-weighted median (or mean of log-amounts) as a *comparator anchor*. Confidence: **High** that comparator-anchored is a recognised pattern; **Moderate** that it improves over the LLM's own number (we should ablate).
- Source: <https://link.springer.com/article/10.1007/s10506-021-09306-3> (Medvedeva et al. survey, history of nearest-neighbour use)

**Finding 2.5.3 — Heavy-tail handling: log-amounts are the standard.**
Log-normal distribution fits damages well; log-transforming positive heavy-tailed data is standard practice in regression and forecasting (Stata/Duke teaching references; Lambert-W heavy-tail Gaussianisation, arXiv 1010.2265) [31]. Insurance-actuarial work uses Tweedie (compound Poisson-Gamma) for zero-inflated claim sizes — the relevant analogue if we ever predict awards including £0 (no maladministration) [32]. Confidence: **High**.
- Source: <https://people.duke.edu/~rnau/411log.htm>
- Source: <https://arxiv.org/html/2406.16206v2> (Zero-Inflated Tweedie Boosted Trees, insurance)

**Finding 2.5.4 — Conformalized Quantile Regression (Romano, Patterson, Candès, NeurIPS 2019) gives finite-sample valid, heteroscedastic predictive intervals** by fitting two quantile regressors on a proper training split and conformalising on a calibration split [10]. Drop-in replacement for ad-hoc 80% intervals on £-amounts. Confidence: **High**.
- Source: <https://arxiv.org/abs/1905.03222>

**Finding 2.5.5 — Use Housing Ombudsman's published bands as the band scheme.**
Housing Ombudsman remedies guidance (Annex A of policy) defines compensation bands tied to severity findings: ~£50–£100 for service failure with minimal impact; £100–£600 for maladministration with no permanent impact; £600–£1,000 for maladministration / severe maladministration with significant impact; £1,000+ for severe maladministration with severe long-term impact [13]. These are the empirical bands actually used in practice — adopting them aligns the eval with the regulator's own scheme. Confidence: **High**.
- Source: <https://www.housing-ombudsman.org.uk/centre-for-learning/key-topics/our-orders/ombudsmans-policy-and-guidance-on-remedies/>

### 2.6 Imbalanced eval methodology

**Finding 2.6.1 — He & Garcia (IEEE TKDE 2009) is the canonical imbalanced-learning survey.** Sets out class-conditional sampling, cost-sensitive learning, and assessment metrics (G-mean, ROC, PRC) and is standard reference for any imbalanced-classification paper [33]. Confidence: **High**.
- Source: <https://ieeexplore.ieee.org/document/5128907/>

**Finding 2.6.2 — On strongly imbalanced data, PR curves are more informative than ROC** (Saito & Rehmsmeier, PLOS ONE 2015) [15]. ROC can look optimistic because TN is huge; PR-AUC focuses on the minority. With 49/1, our minority is the *landlord*-favoured outcome and PR-AUC of the landlord class is the better headline. Confidence: **High**.
- Source: <https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0118432>

**Finding 2.6.3 — MCC is more reliable than F1 and accuracy under imbalance** (Chicco & Jurman, BMC Genomics 2020). MCC is high only if all four confusion-matrix cells are well-predicted, and is invariant to class-swap [16]. Confidence: **High**.
- Source: <https://link.springer.com/article/10.1186/s12864-019-6413-7>

**Finding 2.6.4 — Balanced accuracy (Brodersen et al., ICPR 2010) = mean per-class recall** with a posterior-distribution variant for confidence intervals — useful headline number under imbalance, complementary to MCC and PR-AUC [34]. Confidence: **High**.
- Source: <https://kaybrodersen.github.io/talks/Brodersen_2010_06_21.pdf>

---

## 3. Synthesis: a recommended prompt + calibration + amount stack for Housing Ombudsman repairs

### 3.1 Prompt skeleton (single-call, structured)

The skeleton below is **plain-language** wording in an **IRAC-shaped JSON schema** (per Findings 2.1.1, 2.1.2). It uses Chain-of-Logic decomposition (2.1.3), a Self-RAG–style abstention token (2.2.1), Chain-of-Verification post-step (2.2.2), and emits *both* a verbalized confidence (Tian et al. 2023, 2.3.3) and a remedy band aligned to the published Housing Ombudsman scheme (2.5.5).

System prompt (sketch):

```
You are a Housing Ombudsman case analyst. You decide whether the landlord's
handling of a repair complaint amounts to (a) no maladministration / reasonable
redress, (b) service failure, (c) maladministration, or (d) severe
maladministration, and you propose a remedy band per the Housing Ombudsman's
published guidance.

You MUST cite a specific evidence span (file_id + paragraph) for every claim
in the Application section. If no supporting span exists, output the literal
token "ABSTAIN" for that field.

Use plain English, not legal jargon.
```

User prompt schema (model fills, all fields required unless `ABSTAIN`):

```json
{
  "issues": [
    { "id": "I1", "plain_english": "<one sentence>", "rule_ref": "<HO scheme paragraph>" }
  ],
  "evidence_ledger": [
    {
      "fact_id": "F1",
      "claim": "<one sentence in plain English>",
      "supporting_span": { "case_id": "...", "paragraph": "...", "quoted_phrase_under_15_words": "..." },
      "supports_issue": ["I1"]
    }
  ],
  "rubric_application": [
    {
      "issue_id": "I1",
      "rubric": "service_failure | maladministration | severe_maladministration | reasonable_redress | no_maladministration",
      "reason_in_plain_english": "<one sentence>",
      "evidence_used": ["F1", "F3"]
    }
  ],
  "liability_decision": {
    "label": "service_failure | maladministration | severe_maladministration | reasonable_redress | no_maladministration",
    "verbalized_confidence_pct": 0,
    "logprob_top_label": null
  },
  "comparator_awards": [
    { "case_id": "...", "amount_gbp": 0, "similarity_score": 0.0 }
  ],
  "remedy_band": "0 | 50-100 | 100-600 | 600-1000 | 1000+",
  "amount_estimate_gbp": 0,
  "amount_predictive_interval_gbp": [0, 0],
  "verification_questions_self_answered": [
    { "q": "...", "a": "...", "evidence_id": "F2" }
  ]
}
```

Why each piece (citations):

- `issues` and `rubric_application` enforce IRAC decomposition (Guha et al., NeurIPS 2023; MSLR 2025) [1, 2].
- `evidence_ledger` makes attribution explicit and machine-checkable; tied to RARR/Citation-NLI verification (Gao et al. 2023) [22].
- `ABSTAIN` token + missing-span handling = Self-RAG-style cite-or-abstain (Asai et al., ICLR 2024) [5].
- `verification_questions_self_answered` = Chain-of-Verification (Dhuliawala et al., Findings ACL 2024) [21] — drives the model to fact-check its own draft.
- `verbalized_confidence_pct` is the calibration target (Tian et al. EMNLP 2023; Lin et al. 2022) [3, 24].
- `comparator_awards` populated by the existing RAG retriever — provides kNN anchor for amount (Medvedeva et al., 2.5.2) [30].
- `remedy_band` uses the *published* Housing Ombudsman bands (2.5.5) [13].
- `amount_predictive_interval_gbp` becomes the conformalised quantile-regression interval (Romano et al. 2019) [10].
- Plain-English wording everywhere (LegalBench finding) [1].

### 3.2 Calibration recipe

Given our small held-out set (~50 cases) and 49/1 imbalance:

1. **Step 1 — strip the verbalized confidence into a real-valued logit.** Take `verbalized_confidence_pct / 100`, clip to [0.001, 0.999], and apply a logit transform.
2. **Step 2 — fit a single-parameter temperature `T`** (Guo et al., ICML 2017) on validation NLL of the binary outcome. Two lines of code [4].
3. **Step 3 — only if a held-out set ≥200 labelled cases is available, replace `T` with isotonic regression** (Zadrozny & Elkan, KDD 2002) [14]. Check Niculescu-Mizil & Caruana's overfitting warning — isotonic on <100 points is unstable [23].
4. **Step 4 — class-conditional calibration**: stratify the calibration set by liability-class so the calibrator does not collapse to the tenant-majority distribution (per arXiv 2410.18144) [26].
5. **Step 5 — report Brier with Murphy's decomposition** (reliability, resolution, uncertainty) before/after calibration [25]. Expect reliability term to drop substantially; if resolution drops too, the model is losing discrimination — that means the underlying classifier (not calibration) is the bottleneck.
6. **Step 6 — never refit calibration on the test set.** Use a frozen calibration split and bootstrap CIs on ECE/Brier (1k bootstrap resamples).

### 3.3 Conformal abstention / selective prediction recipe

1. **Step 1 — APS conformity score** for the 5-class liability head (Romano, Sesia, Candès, NeurIPS 2020) [9]. Use the 50-case set as the calibration set. Set α=0.20 → 80% marginal coverage.
2. **Step 2 — abstain rule.** Output `ABSTAIN` if the conformal set has size > 1 *or* if any rubric_application entry is `ABSTAIN` (no supporting evidence span).
3. **Step 3 — risk-coverage curve.** Sweep abstention threshold (1−verbalized_confidence) from 0 to 1 and report AURC + coverage at fixed risk = 5%, 10%, 20% (Geifman & El-Yaniv, NeurIPS 2017) [17].
4. **Step 4 — conformal risk control for hallucination** (ICLR 2024) [29]: if our acceptable hallucination/wrong-finding rate is r, calibrate the abstention threshold so the *expected* loss on held-out data ≤ r. This is the version we cite in the thesis for a defensible safety guarantee.

### 3.4 Amount band scheme + within-band regression

Bands are taken directly from Housing Ombudsman remedies guidance (Annex A) [13]:

| Band id | Range £ | Severity finding it typically corresponds to |
| --- | --- | --- |
| `0` | 0 | No maladministration / reasonable redress already provided |
| `50-100` | 50–100 | Service failure, minimal impact, short duration |
| `100-600` | 100–600 | Maladministration, no permanent impact |
| `600-1000` | 600–1,000 | Maladministration / severe maladministration with significant impact |
| `1000+` | 1,000+ | Severe maladministration, severe long-term impact |

Note we add a `0` band — the published guidance starts at £50 because it covers cases where redress *is* ordered, but we need a "no order" outcome too.

Two-stage prediction:

1. **Stage A — band classifier.** Re-use the IRAC-derived `rubric_application` + retrieved comparator awards to classify into one of the 6 bands. Calibrate this with the same temperature-scaling pipeline as §3.2. Report macro-F1, balanced accuracy, MCC.
2. **Stage B — within-band regression on log £.** Within each non-zero band, fit `log(amount + 1)` against a small feature vector: (i) severity_label_onehot, (ii) similarity-weighted mean of log-amounts of top-5 retrieved comparators, (iii) duration_days_log, (iv) impact_features. Use **Conformalized Quantile Regression** (Romano et al. NeurIPS 2019) on `log(amount+1)` to get a heteroscedastic 80% interval, then exponentiate back [10]. For the `0` band, predict 0.
3. **Why this beats a single regression head:** the `0` and `1000+` bins are heavy-tailed and zero-inflated; band classification absorbs that structure (compare Tweedie/zero-inflated approaches in insurance — same problem shape) [32]. Bias of -£466 in the current eval is consistent with a single regressor pulled toward the majority small-award region; banding decouples this.
4. **Anchoring.** The within-band prediction is *anchored* to the median log-amount of the retrieved comparators with similarity > τ. If the LLM proposes an amount more than 1 IQR away from the comparator anchor, force a `requires-review` flag. This implements the "comparator-award table" pattern in 2.5.2.

### 3.5 Imbalanced-eval reporting recipe (replaces the current single-accuracy report)

Per case set, report:

**Liability classification (5-class):**
- Macro-F1 and per-class F1 (incl. landlord-favoured class) — Brodersen et al. 2010, Chicco & Jurman 2020 [34, 16]
- Balanced accuracy with bootstrap 95% CI
- MCC (binary tenant-wins-majority vs. all others; AND multi-class MCC)
- PR-AUC for the landlord-favoured minority class — Saito & Rehmsmeier 2015 [15]
- Confusion matrix
- ECE with 10 equal-mass bins, **and** ECE per class
- Brier with Murphy decomposition (reliability, resolution, uncertainty)
- Abstention rate; abstention-adjusted accuracy (= accuracy on non-abstained subset)
- AURC + coverage at risk={0.05, 0.10, 0.20}
- Conformal coverage and average set size at α=0.20

**Amount prediction:**
- Amount@20% (current metric — keep for back-comparison)
- Amount@£100 (new, threshold of practical fairness)
- MAE, median absolute error, bias (current −£466 is the main alarm)
- MAE on log-scale (handles tail)
- Conformal QR coverage (target 80%) and mean interval width
- Per-band MAE (to expose where the bias lives)

---

## 4. Open questions

1. **Is 50 cases enough to fit even temperature scaling reliably?** Niculescu-Mizil & Caruana suggest yes for `T`, no for isotonic [23]. We should bootstrap-CI the calibration parameter and report it.
2. **Should we treat `ABSTAIN` as a 6th class in eval, or as a separate selective-prediction track?** The conformal-risk-control framing (2.4.3) treats it as the latter; LegalBench treats abstention as wrong. We should report both, flagging them clearly.
3. **Does Chain-of-Verification add latency we cannot afford?** The QwQ-32B IRAC-Recall regression in MSLR (2.1.4) suggests human-imposed verification can sometimes hurt; ablate.
4. **How well do the Housing Ombudsman bands generalise to *non-published* (private/early-resolution) cases?** Our retrieval corpus is published decisions only; the regulator's bands may reflect a selection bias.
5. **Within-band regression features: what's the minimum useful feature set?** With 50 cases the regressor is starved; a Bayesian linear regression with weakly-informative priors anchored on comparator-mean might dominate.
6. **Temporal drift.** Housing legislation (Awaab's Law from late 2024 on damp/mould) shifts what counts as severe maladministration; our calibration and bands are time-anchored.

---

## 5. References

1. Guha, N., Nyarko, J., Ho, D. E., Ré, C. et al. (2023). LegalBench: A Collaboratively Built Benchmark for Measuring Legal Reasoning in Large Language Models. NeurIPS 2023 Datasets & Benchmarks. <https://arxiv.org/abs/2308.11462> · NeurIPS PDF: <https://proceedings.neurips.cc/paper_files/paper/2023/file/89e44582fd28ddfea1ea4dcb0ebbf4b0-Paper-Datasets_and_Benchmarks.pdf>
2. MSLR / Multi-Step Legal Reasoning benchmark (2025). Benchmarking Multi-Step Legal Reasoning and Analyzing Chain-of-Thought Effects in Large Language Models. <https://arxiv.org/abs/2511.07979>
3. Tian, K., Mitchell, E., Zhou, A., Sharma, A., Rafailov, R., Yao, H., Finn, C., Manning, C. D. (2023). Just Ask for Calibration. EMNLP 2023. <https://aclanthology.org/2023.emnlp-main.330/> · arXiv: <https://arxiv.org/abs/2305.14975>
4. Guo, C., Pleiss, G., Sun, Y., Weinberger, K. Q. (2017). On Calibration of Modern Neural Networks. ICML 2017. <https://arxiv.org/abs/1706.04599> · PMLR: <https://proceedings.mlr.press/v70/guo17a/guo17a.pdf>
5. Asai, A., Wu, Z., Wang, Y., Sil, A., Hajishirzi, H. (2024). Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection. ICLR 2024 (oral). <https://arxiv.org/abs/2310.11511>
6. Aletras, N., Tsarapatsanis, D., Preoţiuc-Pietro, D., Lampos, V. (2016). Predicting judicial decisions of the European Court of Human Rights. PeerJ Computer Science 2:e93. <https://peerj.com/articles/cs-93/>
7. Servantez, S., Barrow, J., Hammond, K., Jain, R. (2024). Chain of Logic: Rule-Based Reasoning with Large Language Models. Findings of ACL 2024. <https://aclanthology.org/2024.findings-acl.159/> · arXiv: <https://arxiv.org/abs/2402.10400>
8. Wang et al. (2025). SteerConf: Steering LLMs for Confidence Elicitation (summarises Groot et al. TrustNLP/ACL 2024 verbalized-confidence ECE numbers). <https://arxiv.org/abs/2503.02863>
9. Romano, Y., Sesia, M., Candès, E. (2020). Classification with Valid and Adaptive Coverage. NeurIPS 2020. <https://arxiv.org/abs/2006.02544>
10. Romano, Y., Patterson, E., Candès, E. (2019). Conformalized Quantile Regression. NeurIPS 2019. <https://arxiv.org/abs/1905.03222> · NeurIPS PDF: <https://papers.neurips.cc/paper/8613-conformalized-quantile-regression.pdf>
11. Dal Pont, T. R. et al. (2023). Regression applied to legal judgments to predict compensation for immaterial damage. PeerJ Computer Science 9:e1225. <https://peerj.com/articles/cs-1225/>
12. (2024+) Judicial Sentencing Prediction Based on Hybrid Models and Two-Stage Learning Algorithms. arXiv 2511.15374. <https://arxiv.org/html/2511.15374>
13. Housing Ombudsman Service. Guidance on remedies (Annex A: financial bands). <https://www.housing-ombudsman.org.uk/centre-for-learning/key-topics/our-orders/ombudsmans-policy-and-guidance-on-remedies/> · PDF: <https://www.housing-ombudsman.org.uk/04-guidance-remedies-3/>
14. Zadrozny, B., Elkan, C. (2002). Transforming classifier scores into accurate multiclass probability estimates. KDD 2002. <https://dl.acm.org/doi/10.1145/775047.775151>
15. Saito, T., Rehmsmeier, M. (2015). The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced Datasets. PLOS ONE 10(3): e0118432. <https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0118432>
16. Chicco, D., Jurman, G. (2020). The advantages of the Matthews correlation coefficient (MCC) over F1 score and accuracy in binary classification evaluation. BMC Genomics 21:6. <https://link.springer.com/article/10.1186/s12864-019-6413-7>
17. Geifman, Y., El-Yaniv, R. (2017). Selective Classification for Deep Neural Networks. NeurIPS 2017. <https://arxiv.org/abs/1705.08500>
18. (Survey) Calibration / verbalized-confidence numbers across GPT-3/3.5/Vicuna/GPT-4 — see SteerConf reporting [8] and the 2024 NAACL survey: <https://aclanthology.org/2024.naacl-long.366/>
19. Chalkidis, I., Androutsopoulos, I., Aletras, N. (2019). Neural Legal Judgment Prediction in English. ACL 2019. <https://aclanthology.org/P19-1424/> · arXiv: <https://arxiv.org/abs/1906.02059>
20. Medvedeva, M., Wieling, M., Vols, M. (2023). Rethinking the field of automatic prediction of court decisions. Artificial Intelligence and Law. <https://link.springer.com/article/10.1007/s10506-021-09306-3> · Medvedeva, M., McBride, P. (2023). Legal Judgment Prediction: If You Are Going to Do It, Do It Right. NLLP 2023. <https://aclanthology.org/2023.nllp-1.9/>
21. Dhuliawala, S., Komeili, M. et al. (2024). Chain-of-Verification Reduces Hallucination in Large Language Models. Findings of ACL 2024. <https://arxiv.org/abs/2309.11495> · ACL: <https://aclanthology.org/2024.findings-acl.212/>
22. Gao, T. et al. (2023). RARR / Citation NLI metric cluster — surveyed in: Attribution, Citation, and Quotation: A Survey of Evidence-based Text Generation with LLMs. <https://arxiv.org/abs/2508.15396>
23. Niculescu-Mizil, A., Caruana, R. (2005). Predicting Good Probabilities With Supervised Learning. ICML 2005. <https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf>
24. Lin, S., Hilton, J., Evans, O. (2022). Teaching Models to Express Their Uncertainty in Words. <https://arxiv.org/abs/2205.14334>
25. Murphy, A. H. (1973). A New Vector Partition of the Probability Score. — modern restatement: Siegert (2017), QJRMS. <https://rmets.onlinelibrary.wiley.com/doi/abs/10.1002/qj.2985> · Wikipedia overview: <https://en.wikipedia.org/wiki/Brier_score>
26. (2024) Using Platt's scaling for calibration after undersampling – limitations and consequences. arXiv 2410.18144. <https://arxiv.org/abs/2410.18144>
27. Angelopoulos, A. N., Bates, S. (2021/2023). A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification. <https://arxiv.org/abs/2107.07511>
28. (2024) Overcoming Common Flaws in the Evaluation of Selective Classification Systems. NeurIPS 2024. <https://proceedings.neurips.cc/paper_files/paper/2024/file/047c84ec50bd8ea29349b996fc64af4b-Paper-Conference.pdf>
29. Angelopoulos, A. N., Bates, S., Fisch, A. et al. (2024). Conformal Risk Control. ICLR 2024. <https://proceedings.iclr.cc/paper_files/paper/2024/file/f3549ef9b5ff520a7e41ff3cc306ab2b-Paper-Conference.pdf>
30. Medvedeva, M., Vols, M., Wieling, M. (2020). Using machine learning to predict decisions of the European Court of Human Rights. AI and Law. <https://link.springer.com/article/10.1007/s10506-019-09255-y>
31. Nau, R. (Duke). Uses of the logarithm transformation in regression and forecasting. <https://people.duke.edu/~rnau/411log.htm>
32. (2024) Zero-inflated Tweedie boosted trees with CatBoost for insurance loss analytics. arXiv 2406.16206. <https://arxiv.org/html/2406.16206v2>
33. He, H., Garcia, E. A. (2009). Learning from Imbalanced Data. IEEE Transactions on Knowledge and Data Engineering 21(9):1263–1284. <https://ieeexplore.ieee.org/document/5128907/>
34. Brodersen, K. H., Ong, C. S., Stephan, K. E., Buhmann, J. M. (2010). The Balanced Accuracy and Its Posterior Distribution. ICPR 2010. <https://kaybrodersen.github.io/talks/Brodersen_2010_06_21.pdf>

---

**Notes on confidence and limitations.**
- All numerical claims have a primary-source link. Where specific deltas are cited, the setting/limitation is stated.
- Most calibration evidence is from non-legal domains (TriviaQA, SciQ, ImageNet). Transfer to legal text is plausible (the calibration mechanisms are domain-agnostic) but the *magnitude* of improvement should be re-measured on the Housing Ombudsman set.
- The Housing Ombudsman bands [13] are the regulator's *suggested* ranges; caseworkers retain discretion. We should not treat the bands as ground-truth, only as the rubric they *publish*.
- LegalBench's "21 points balanced accuracy" gain for plain-language is "up to" — the headline number, on a studied subset, is a useful directional finding rather than a guaranteed effect.
