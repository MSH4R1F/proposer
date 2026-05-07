"""Factor-constrained proposition retrieval (Stream C PR 5 — Task 5.3).

Implements the factor-constrained retrieval controller per
``docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md``
sections 9.2 (comparator pass scoring) and 9.3 (counterexample pass), and
satisfies Cross-PR Contract C3 by exposing :class:`RetrievalControlInput`
and :class:`AuthorityPolicy` as the public input types for the new path.

Two-pass retrieval semantics
----------------------------
1. Comparator pass — positive analogues (similar facts, same outcome).
   Scored via the active pack's
   ``retrieval_profile.comparator_weights``. Returns up to ``n`` ranked
   propositions with score > 0.

2. Counterexample pass — differential analogues (similar facts, different
   outcome). Independent of comparator scoring per spec §9.3. Filters
   candidates to those sharing at least ``k_overlap_min`` factors with
   the asserted factors AND whose outcome differs from ``primary_outcome``.

Hard Constraint #11 — :class:`PersonalizedPageRank` in
``proposition_retrieval.py`` is NOT touched. :class:`FactorRetriever` is
the alternate path selected when :class:`RetrievalStrategy.FACTOR_CONSTRAINED`
is active (wired in Task 5.5).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from kg_builder.propositions.models import Proposition
from legal_core.graph.factor_assertion import FactorAssertion

from domain_packs.registry import DomainPack

from llm_orchestrator.pipeline.comparator_pack import (
    ComparatorPack,
    ComparatorPassMetadata,
    CounterexamplePassMetadata,
    RankedProposition,
)


# ---------------------------------------------------------------------------
# Public Pydantic models — Cross-PR Contract C3
# ---------------------------------------------------------------------------


class AuthorityPolicy(BaseModel):
    """Authority + forum filtering policy per spec §11.

    Attributes
    ----------
    forum_compatible_only:
        If True, only propositions whose case forum is compatible with the
        query forum are eligible. Wiring deferred to PR 5+.
    accept_first_instance_as_fact_comparator:
        If True (default), first-instance / comparator-level propositions
        may surface only as ``proposition_role="fact_comparator"``. If
        False, a comparator-level proposition with role
        ``"legal_test"`` is disqualified (its
        ``authority_level_match`` score component drops to 0).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    forum_compatible_only: bool = True
    accept_first_instance_as_fact_comparator: bool = True


class RetrievalControlInput(BaseModel):
    """Input to the factor-constrained retrieval controller per spec §9.1.

    Verbatim shape from Cross-PR Contract C3.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_id: str
    claim_head_id: str
    issue_ids: List[str]
    asserted_factors: List[FactorAssertion]
    target_outcomes: List[str]
    target_remedies: List[str]
    forum: str
    authority_policy: AuthorityPolicy
    retrieval_profile_id: str


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


_HIGH_AUTHORITY_LEVELS = frozenset(
    {
        "statute",
        "regulation",
        "official_guidance",
        "binding_precedent",
    }
)

_DEFAULT_TOP_N = 5
_SEED_LIMIT = 50


# ---------------------------------------------------------------------------
# FactorRetriever
# ---------------------------------------------------------------------------


class FactorRetriever:
    """Factor-constrained proposition retrieval per spec §9 + §10.

    The repository is duck-typed — only ``search_by_issue_tags`` is invoked
    by the seed pass, matching :class:`PropositionGraphRepository`'s Protocol.
    """

    def __init__(
        self,
        repository: Any,
        pack: DomainPack,
    ) -> None:
        self.repository = repository
        self.pack = pack

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve_comparators(
        self,
        input: RetrievalControlInput,
        n: int = _DEFAULT_TOP_N,
    ) -> List[RankedProposition]:
        """Return top-N positive analogues with score > 0."""
        candidates = await self._seed_candidates(input)

        # Same-domain gating per R5.
        candidates = [
            p for p in candidates if self._matches_domain(p, input.domain_id)
        ]

        weights = self.pack.retrieval_profile.comparator_weights
        scored: List[Tuple[Proposition, float, Dict[str, float]]] = []
        for p in candidates:
            score, breakdown = self._score_proposition(p, input, weights)
            if score > 0:
                scored.append((p, score, breakdown))

        scored.sort(key=lambda t: t[1], reverse=True)
        scored = scored[:n]

        return [self._to_ranked(p, s, b) for p, s, b in scored]

    async def retrieve_counterexamples(
        self,
        input: RetrievalControlInput,
        primary_outcome: str,
    ) -> List[RankedProposition]:
        """Return cases sharing >= k_overlap_min factors but different outcome.

        Spec §9.3: independent of comparator scoring. Candidates with no
        outcome data are skipped.
        """
        candidates = await self._seed_candidates(input)

        # Same-domain gating applies here too — counterexamples must be from
        # the same legal domain to count as counter-evidence.
        candidates = [
            p for p in candidates if self._matches_domain(p, input.domain_id)
        ]

        k_min = self._k_overlap_min()

        out: List[Tuple[Proposition, float, Dict[str, float]]] = []
        denom = len(input.asserted_factors) or 1
        for p in candidates:
            shared = self._count_shared_factors(p, input.asserted_factors)
            if shared < k_min:
                continue
            # Must reference an outcome different from primary.
            if not p.outcome_component_ids:
                continue
            if any(oc == primary_outcome for oc in p.outcome_component_ids):
                continue
            score = shared / denom
            out.append((p, score, {"shared_factors": float(shared)}))

        out.sort(key=lambda t: t[1], reverse=True)
        return [self._to_ranked(p, s, b) for p, s, b in out]

    async def build_comparator_pack(
        self,
        input: RetrievalControlInput,
        primary_outcome: str,
    ) -> ComparatorPack:
        """Compose comparator + counterexample passes with metadata.

        Empty-asserted-factors fallback per design decision D5 returns an
        empty pack with ``comparator_pass_metadata.fallback_reason`` set.
        """
        if not input.asserted_factors:
            return ComparatorPack(
                comparators=[],
                counterexamples=[],
                comparator_pass_metadata=ComparatorPassMetadata(
                    n_retrieved=0,
                    weights_used={},
                    fallback_reason="no_asserted_factors",
                ),
                counterexample_pass_metadata=CounterexamplePassMetadata(
                    n_retrieved=0,
                    k_overlap_min=self._k_overlap_min(),
                    abstention_recommended=False,
                ),
            )

        comparators = await self.retrieve_comparators(input, n=_DEFAULT_TOP_N)
        counterexamples = await self.retrieve_counterexamples(
            input, primary_outcome
        )

        weights = self.pack.retrieval_profile.comparator_weights
        weights_dict = {
            "factor_overlap": weights.factor_overlap,
            "text_relevance": weights.text_relevance,
            "outcome_component_match": weights.outcome_component_match,
            "remedy_similarity": weights.remedy_similarity,
            "authority_level_match": weights.authority_level_match,
            "chronology_match": weights.chronology_match,
            "claim_head_exact_match": weights.claim_head_exact_match,
        }

        # Counterexample abstention per spec §9.3 + soft-flag per D6.
        abstain_if_none = self._abstain_if_none()
        abstention = abstain_if_none and len(counterexamples) == 0

        return ComparatorPack(
            comparators=comparators,
            counterexamples=counterexamples,
            comparator_pass_metadata=ComparatorPassMetadata(
                n_retrieved=len(comparators),
                weights_used=weights_dict,
                fallback_reason=None,
            ),
            counterexample_pass_metadata=CounterexamplePassMetadata(
                n_retrieved=len(counterexamples),
                k_overlap_min=self._k_overlap_min(),
                abstention_recommended=abstention,
            ),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _seed_candidates(
        self,
        input: RetrievalControlInput,
    ) -> List[Proposition]:
        """Issue-tag seed pass via the repository.

        With no issue tags we cannot seed; return an empty list rather
        than scanning the entire graph.
        """
        if not input.issue_ids:
            return []
        return await self.repository.search_by_issue_tags(
            tags=input.issue_ids, limit=_SEED_LIMIT,
        )

    def _score_proposition(
        self,
        p: Proposition,
        input: RetrievalControlInput,
        weights: Any,
    ) -> Tuple[float, Dict[str, float]]:
        """Compute weighted score per spec §9.2.

        The PR-5 implementation uses heuristic components for
        ``text_relevance`` and ``chronology_match``; both can be upgraded
        later without changing the public contract.
        """
        # 1. Factor overlap component: count of asserted factors whose
        #    factor_id appears in p.factor_ids, normalized by the number
        #    of asserted factors.
        if input.asserted_factors:
            proposition_factor_set = set(p.factor_ids)
            factor_ids_overlap = sum(
                1
                for fa in input.asserted_factors
                if fa.factor_id in proposition_factor_set
            )
            factor_overlap_score = factor_ids_overlap / len(
                input.asserted_factors
            )
        else:
            factor_overlap_score = 0.0

        # 2. text_relevance: simple heuristic — proportion of asserted
        #    factor IDs (in spaced/lowercased form) found in p.text. PR 5+
        #    may upgrade to embeddings.
        text_relevance = 0.0
        if input.asserted_factors and p.text:
            text_lower = p.text.lower()
            mentioned = sum(
                1
                for fa in input.asserted_factors
                if fa.factor_id.lower().replace("_", " ") in text_lower
            )
            text_relevance = mentioned / len(input.asserted_factors)

        # 3. outcome_component_match
        outcome_match = 0.0
        if input.target_outcomes and p.outcome_component_ids:
            shared = set(input.target_outcomes) & set(
                p.outcome_component_ids
            )
            outcome_match = len(shared) / max(len(input.target_outcomes), 1)

        # 4. remedy_similarity
        remedy_sim = 0.0
        if input.target_remedies and p.remedy_component_ids:
            shared_r = set(input.target_remedies) & set(
                p.remedy_component_ids
            )
            remedy_sim = len(shared_r) / max(len(input.target_remedies), 1)

        # 5. authority_level_match: 1.0 if proposition is from a high-
        #    authority source (statute / regulation / official_guidance /
        #    binding_precedent), else 0.0.
        authority_match = (
            1.0 if p.authority_level in _HIGH_AUTHORITY_LEVELS else 0.0
        )
        # Authority policy: gate first-instance comparator-level
        # propositions claiming role=legal_test.
        if (
            not input.authority_policy.accept_first_instance_as_fact_comparator
            and p.authority_level == "comparator"
            and p.proposition_role == "legal_test"
        ):
            authority_match = 0.0

        # 6. chronology_match: heuristic placeholder. The current
        #    Proposition model does not surface a normalized decision
        #    year, so we return 0.0 until the schema grows that field
        #    (tracked in §10 follow-ups).
        chronology_match = 0.0

        # 7. claim_head_exact_match
        claim_head_match = (
            1.0 if input.claim_head_id in p.claim_head_ids else 0.0
        )

        score = (
            weights.factor_overlap * factor_overlap_score
            + weights.text_relevance * text_relevance
            + weights.outcome_component_match * outcome_match
            + weights.remedy_similarity * remedy_sim
            + weights.authority_level_match * authority_match
            + weights.chronology_match * chronology_match
            + weights.claim_head_exact_match * claim_head_match
        )

        breakdown = {
            "factor_overlap": factor_overlap_score,
            "text_relevance": text_relevance,
            "outcome_component_match": outcome_match,
            "remedy_similarity": remedy_sim,
            "authority_level_match": authority_match,
            "chronology_match": chronology_match,
            "claim_head_exact_match": claim_head_match,
        }
        return min(max(score, 0.0), 1.0), breakdown

    def _count_shared_factors(
        self,
        p: Proposition,
        asserted_factors: List[FactorAssertion],
    ) -> int:
        """Count asserted_factors whose factor_id appears in p.factor_ids."""
        proposition_factor_set = set(p.factor_ids)
        return sum(
            1
            for fa in asserted_factors
            if fa.factor_id in proposition_factor_set
        )

    def _to_ranked(
        self,
        p: Proposition,
        score: float,
        breakdown: Dict[str, float],
    ) -> RankedProposition:
        return RankedProposition(
            proposition_id=str(p.proposition_id),
            case_reference=p.case_reference,
            text=p.text,
            source_passage=p.source_passage,
            authority_level=p.authority_level,
            proposition_role=p.proposition_role,
            score=score,
            score_breakdown=breakdown,
        )

    def _matches_domain(self, p: Proposition, domain_id: str) -> bool:
        """Heuristic same-domain gate.

        For PR 5 we accept any proposition whose ``issue_tags`` contain
        the literal ``domain_id`` (the seed convention). A real per-pack
        mapping is tracked in spec §10 follow-ups.
        """
        return any(domain_id in tag for tag in (p.issue_tags or []))

    def _k_overlap_min(self) -> int:
        """Read ``k_overlap_min`` from env or fall back to the pack."""
        env = os.getenv("STREAM_C_K_OVERLAP_MIN")
        if env is not None:
            return int(env)
        return self.pack.retrieval_profile.counterexample.k_overlap_min

    def _abstain_if_none(self) -> bool:
        """Read ``abstain_if_none`` from env or fall back to the pack."""
        env = os.getenv("STREAM_C_COUNTEREXAMPLE_ABSTAIN")
        if env is not None:
            return env == "1"
        return self.pack.retrieval_profile.counterexample.abstain_if_none


__all__ = [
    "AuthorityPolicy",
    "RetrievalControlInput",
    "FactorRetriever",
]
