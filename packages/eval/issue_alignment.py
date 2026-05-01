"""Bridge between `ClaimType` (eval) and `DisputeIssue` (orchestrator).

The two enums diverged: eval is annotator-facing categories of *claims*
made in tribunal decisions; `DisputeIssue` is intake/UI categories of
*issues* the user reports during a chat session. They overlap heavily
but not perfectly:

- `damages` (eval) ↔ `damage` (orch) — spelling
- `deposit_non_protection` (eval) ↔ `deposit_protection` (orch) —
  eval names the breach, orchestrator names the issue area; same dispute
- `disrepair`, `end_of_tenancy` (eval) — no clean orch equivalent
- `garden`, `redecoration`, `keys`, `inventory`, `fair_wear_and_tear`,
  `missing_items`, `utilities`, `rent_arrears`, `other` (orch) — no
  eval equivalent (eval doesn't track these as distinct claim types)

When a value can't be mapped, raise `UnmappableIssue` and let the caller
decide. The Phase 5b live runner currently falls eval-only values back to
`DisputeIssue.OTHER` for prediction while logging a count for the alignment
report; the adapter lets orchestrator-only prediction labels pass through so
they score as missing rather than being coerced into a fake gold label.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Union

from eval.schema import ClaimType

if TYPE_CHECKING:
    from llm_orchestrator.models.case_file import DisputeIssue


class UnmappableIssue(ValueError):
    """Raised when an issue label has no equivalent in the target vocabulary."""


# Forward map: eval ClaimType → orchestrator DisputeIssue value.
_EVAL_TO_ORCH = {
    ClaimType.CLEANING: "cleaning",
    ClaimType.DAMAGES: "damage",
    ClaimType.DEPOSIT_NON_PROTECTION: "deposit_protection",
    # disrepair, end_of_tenancy: no orch equivalent → unmappable
}

# Inverse map: derived from the forward map plus explicit gaps for
# orchestrator-only values.
_ORCH_TO_EVAL = {orch_value: ct for ct, orch_value in _EVAL_TO_ORCH.items()}


def eval_to_orchestrator(value: Union[ClaimType, str]):
    """Map an eval `ClaimType` (or its string value) to a `DisputeIssue`."""
    from llm_orchestrator.models.case_file import DisputeIssue

    claim_type = _coerce_to_claim_type(value)
    if claim_type is None:
        raise UnmappableIssue(
            f"eval_to_orchestrator: {value!r} is not a known ClaimType"
        )
    orch_value = _EVAL_TO_ORCH.get(claim_type)
    if orch_value is None:
        raise UnmappableIssue(
            f"eval_to_orchestrator: ClaimType {claim_type.value!r} has no "
            "DisputeIssue equivalent; runner should skip or fall back."
        )
    return DisputeIssue(orch_value)


def orchestrator_to_eval(value) -> ClaimType:
    """Map a `DisputeIssue` (or its string value) to an eval `ClaimType`."""
    orch_value = _coerce_to_orch_value(value)
    if orch_value is None:
        raise UnmappableIssue(
            f"orchestrator_to_eval: {value!r} is not a known DisputeIssue"
        )
    claim_type = _ORCH_TO_EVAL.get(orch_value)
    if claim_type is None:
        raise UnmappableIssue(
            f"orchestrator_to_eval: DisputeIssue {orch_value!r} has no "
            "ClaimType equivalent; runner should drop the prediction."
        )
    return claim_type


def _coerce_to_claim_type(value: Union[ClaimType, str]):
    if isinstance(value, ClaimType):
        return value
    try:
        return ClaimType(value)
    except ValueError:
        return None


def _coerce_to_orch_value(value) -> str | None:
    """Accept a `DisputeIssue` enum or a raw string value; return the
    canonical string value if recognised, else None."""
    from llm_orchestrator.models.case_file import DisputeIssue

    if isinstance(value, DisputeIssue):
        return value.value
    try:
        return DisputeIssue(value).value
    except (ValueError, TypeError):
        return None
