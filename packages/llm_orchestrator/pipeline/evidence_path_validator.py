"""EvidencePathValidator: walks EvidenceSpan → FactorAssertion → Proposition
→ OutcomeComponent and rejects unsupported outcome components.

Per spec §1 (cite-or-abstain) + §17.6 / Cross-PR Contract C4.

Iterative BFS with cycle detection; never recurses. Audit-only by default
(STREAM_C_EVIDENCE_PATH_STRICT=0): rejected outcomes get
abstention_required=False, just logged. Strict mode flips abstention_required
to True so output_assembler can force the outcome to UNCERTAIN.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field


class EvidencePathResult(BaseModel):
    """Validator output per OutcomeComponent claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome_component_id: str
    is_supported: bool
    chain: List[str] = Field(default_factory=list)  # ordered node IDs
    rejection_reason: Optional[str] = None
    abstention_required: bool = False


class EvidencePathValidator:
    """Walks the chain EvidenceSpan → FactorAssertion → Proposition →
    OutcomeComponent for each claimed outcome component."""

    def __init__(self, case_graph: Any):
        self.case_graph = case_graph

    def validate_outcome_component(self, oc: Any) -> EvidencePathResult:
        """Validate that a chain exists from at least one EvidenceSpan to
        this OutcomeComponent. Returns is_supported=True with the chain when
        found; is_supported=False with rejection_reason when not.

        oc must have:
          - outcome_component_id: str
          - supporting_factor_ids: List[str]
          - supported_by_propositions: List[str]
        """
        strict = os.getenv("STREAM_C_EVIDENCE_PATH_STRICT", "0") == "1"
        oc_id = getattr(oc, "outcome_component_id", "<unknown>")

        if self.case_graph is None:
            return EvidencePathResult(
                outcome_component_id=oc_id,
                is_supported=False,
                chain=[],
                rejection_reason="case_graph is None",
                abstention_required=strict,
            )

        # Pull the relevant collections off the case graph (duck-typed).
        factor_assertions = getattr(self.case_graph, "factor_assertions", []) or []
        propositions = getattr(self.case_graph, "propositions", []) or []
        evidence_spans = getattr(self.case_graph, "evidence_spans", []) or []

        # Fast-path: empty case graph
        if not factor_assertions and not propositions and not evidence_spans:
            return EvidencePathResult(
                outcome_component_id=oc_id,
                is_supported=False,
                chain=[],
                rejection_reason="case_graph is empty",
                abstention_required=strict,
            )

        # Walk OutcomeComponent → Proposition → FactorAssertion → EvidenceSpan
        # via BFS. Required: at least one OC.supported_by_proposition that
        # leads back to an EvidenceSpan via a FactorAssertion in the OC's
        # supporting_factor_ids.

        supporting_factor_ids: Set[str] = set(
            getattr(oc, "supporting_factor_ids", []) or []
        )
        supported_by_propositions: List[str] = list(
            getattr(oc, "supported_by_propositions", []) or []
        )

        if not supporting_factor_ids and not supported_by_propositions:
            return EvidencePathResult(
                outcome_component_id=oc_id,
                is_supported=False,
                chain=[],
                rejection_reason=(
                    f"OutcomeComponent {oc_id!r} has neither supporting_factor_ids "
                    "nor supported_by_propositions"
                ),
                abstention_required=strict,
            )

        # Build lookup maps (proposition ids may be UUIDs or strings — coerce to str).
        prop_by_id = {
            str(getattr(p, "proposition_id", None)): p for p in propositions
        }

        # BFS through the chain — track visited to prevent cycles.
        visited: Set[str] = set()
        # Start at the OC; its supported_by_propositions are the first hop.
        for raw_prop_id in supported_by_propositions:
            prop_id = str(raw_prop_id)
            if prop_id in visited:
                # Cycle — bail out cleanly. (BFS-style: visited tracks all
                # nodes already enqueued/processed at this level.)
                return EvidencePathResult(
                    outcome_component_id=oc_id,
                    is_supported=False,
                    chain=[],
                    rejection_reason=f"cycle detected at proposition {prop_id!r}",
                    abstention_required=strict,
                )
            visited.add(prop_id)
            prop = prop_by_id.get(prop_id)
            if prop is None:
                continue
            # The proposition must reference at least one factor_id in the OC's
            # supporting_factor_ids (so the chain truly supports this OC).
            prop_factor_ids = set(getattr(prop, "factor_ids", []) or [])
            if supporting_factor_ids and not (prop_factor_ids & supporting_factor_ids):
                continue  # this proposition doesn't link to a supporting factor — skip
            # Find a FactorAssertion with that factor_id AND has at least one
            # EvidenceSpan in supported_by.
            relevant_factor_ids = (
                prop_factor_ids & supporting_factor_ids
                if supporting_factor_ids
                else prop_factor_ids
            )
            for fa in factor_assertions:
                fa_factor_id = getattr(fa, "factor_id", None)
                if fa_factor_id and fa_factor_id in relevant_factor_ids:
                    # supported_by is a list of evidence_span_ids
                    fa_evidence = list(getattr(fa, "supported_by", []) or [])
                    if not fa_evidence:
                        continue  # FA has no evidence — skip
                    # Found a complete chain!
                    chain = [
                        fa_evidence[0],  # first EvidenceSpan id
                        getattr(fa, "factor_assertion_id", "<fa>"),
                        prop_id,
                        oc_id,
                    ]
                    return EvidencePathResult(
                        outcome_component_id=oc_id,
                        is_supported=True,
                        chain=chain,
                        rejection_reason=None,
                        abstention_required=False,
                    )

        # No chain found
        return EvidencePathResult(
            outcome_component_id=oc_id,
            is_supported=False,
            chain=[],
            rejection_reason=(
                f"no EvidenceSpan → FactorAssertion → Proposition → "
                f"OutcomeComponent chain found for {oc_id!r}"
            ),
            abstention_required=strict,
        )
