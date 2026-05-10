"""Retrieval quality metrics — context precision/recall + citation validity.

Per spec §17.2. Used by Stream C PR 5 to evaluate the FactorRetriever
against a held-out gold set. All metrics are pure functions returning
floats in [0, 1] (NaN-safe via 0.0 fallback when sets are empty).
"""

from __future__ import annotations

from typing import Dict, List, Set


def retrieval_context_precision_at_k(
    retrieved: List[str], relevant: Set[str], k: int,
) -> float:
    """Share of top-k retrieved that are in the relevant set.

    precision@k = |relevant ∩ top-k| / k

    Returns 0.0 if k <= 0 or retrieved is empty.
    """
    if k <= 0 or not retrieved:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for x in top_k if x in relevant)
    return hits / len(top_k)  # use len(top_k) not k — handles |retrieved| < k


def retrieval_context_recall_at_k(
    retrieved: List[str], relevant: Set[str], k: int,
) -> float:
    """Share of relevant set covered by top-k retrieved.

    recall@k = |relevant ∩ top-k| / |relevant|

    Returns 0.0 if k <= 0 or relevant is empty.
    """
    if k <= 0 or not relevant:
        return 0.0
    top_k = set(retrieved[:k])
    hits = len(top_k & relevant)
    return hits / len(relevant)


def citation_validity(
    predictions: List[Dict[str, Set[str]]],
    gold_citations: Dict[str, Set[str]],
) -> float:
    """Per LegalBench-RAG: share of cited propositions that genuinely
    support the claim.

    Each prediction is dict-shaped: {"prediction_id": str, "cited": Set[str]}.
    `gold_citations` maps prediction_id → set of valid citation IDs.

    For each prediction, validity = |cited ∩ gold| / |cited| (0 if no cites).
    Returns the macro-average across predictions, or 0.0 if no predictions.
    """
    if not predictions:
        return 0.0
    scores: list[float] = []
    for pred in predictions:
        pid = pred.get("prediction_id")
        cited = pred.get("cited") or set()
        if not cited:
            scores.append(0.0)
            continue
        gold = gold_citations.get(pid, set())
        scores.append(len(cited & gold) / len(cited))
    return sum(scores) / len(scores)
