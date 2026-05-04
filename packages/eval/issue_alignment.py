"""Bridge between `ClaimType` (eval) and `DisputeIssue` (orchestrator).

The two enums diverged: eval is annotator-facing categories of *claims*
made in tribunal / Ombudsman decisions; `DisputeIssue` is intake/UI
categories of *issues* the user reports during a chat session. They
overlap heavily but not perfectly:

- `damages` (eval) ↔ `damage` (orch) — spelling
- `deposit_non_protection` (eval) ↔ `deposit_protection` (orch) —
  eval names the breach, orchestrator names the issue area; same dispute
- `disrepair` (eval) maps to repairs-domain issues only when the
  gold row's ``matter_type`` is a Housing Ombudsman repairs matter
- `end_of_tenancy` (eval) — no clean orch equivalent
- `garden`, `redecoration`, `keys`, `inventory`, `fair_wear_and_tear`,
  `missing_items`, `utilities`, `rent_arrears`, `other` (orch) — no
  eval equivalent (eval doesn't track these as distinct claim types)

When a value can't be mapped, raise `UnmappableIssue` and let the caller
decide. The Phase 5b live runner currently falls eval-only values back to
`DisputeIssue.OTHER` for prediction while logging a count for the alignment
report; the adapter lets orchestrator-only prediction labels pass through so
they score as missing rather than being coerced into a fake gold label.

SHA-20 Phase 7 / audit D3 split
-------------------------------
``deposit_non_protection`` and ``deposit_deduction`` are now distinct
``matter_type`` values. The orchestrator's
``DisputeIssue.deposit_protection`` covers the *non-protection penalty*
branch only; the deduction branch maps to ``DisputeIssue.damage`` /
``DisputeIssue.cleaning`` etc. depending on the specific deduction.

For backwards compatibility, this module still maps
``ClaimType.DEPOSIT_NON_PROTECTION`` -> ``deposit_protection`` UNLESS a
caller explicitly passes ``matter_type=deposit_deduction``, in which
case it maps to the standard recovery branch. When ``matter_type`` is
missing on legacy gold rows, default to ``deposit_deduction`` for
safety and emit a deprecation warning.
"""
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Optional, Union

from eval.schema import ClaimType

if TYPE_CHECKING:
    from llm_orchestrator.models.case_file import DisputeIssue


class UnmappableIssue(ValueError):
    """Raised when an issue label has no equivalent in the target vocabulary."""


# Forward map: eval ClaimType → orchestrator DisputeIssue value.
# NB: ``DEPOSIT_NON_PROTECTION`` is matter-type sensitive; see
# ``eval_to_orchestrator``.
_EVAL_TO_ORCH = {
    ClaimType.CLEANING: "cleaning",
    ClaimType.DAMAGES: "damage",
    ClaimType.DEPOSIT_NON_PROTECTION: "deposit_protection",
    # disrepair is matter-type-sensitive; see eval_to_orchestrator.
    # end_of_tenancy: no orch equivalent → unmappable
}

# Inverse map: derived from the forward map plus explicit gaps for
# orchestrator-only values.
_ORCH_TO_EVAL = {orch_value: ct for ct, orch_value in _EVAL_TO_ORCH.items()}
_ORCH_TO_EVAL.update(
    {
        "repairs_disrepair": ClaimType.DISREPAIR,
        "repairs_damp_mould": ClaimType.DISREPAIR,
        "complaint_handling_failure": ClaimType.DISREPAIR,
    }
)

_REPAIRS_MATTER_TO_ORCH = {
    "repairs_disrepair": "repairs_disrepair",
    "repairs_damp_mould": "repairs_damp_mould",
    "complaint_handling_failure": "complaint_handling_failure",
}


def eval_to_orchestrator(
    value: Union[ClaimType, str],
    *,
    matter_type: Optional[str] = None,
):
    """Map an eval `ClaimType` (or its string value) to a `DisputeIssue`.

    The ``matter_type`` keyword controls the audit D3 split:

    * ``matter_type='deposit_non_protection'``: ``DEPOSIT_NON_PROTECTION``
      maps to ``DisputeIssue.deposit_protection`` (penalty branch).
    * ``matter_type='deposit_deduction'``: maps to ``DisputeIssue.damage``
      (the deduction-recovery branch's most common value).
    * ``matter_type=None`` on a deposit row: emits a DeprecationWarning
      and defaults to ``deposit_deduction`` for safety.
    """
    from llm_orchestrator.models.case_file import DisputeIssue

    claim_type = _coerce_to_claim_type(value)
    if claim_type is None:
        raise UnmappableIssue(
            f"eval_to_orchestrator: {value!r} is not a known ClaimType"
        )
    if claim_type is ClaimType.DEPOSIT_NON_PROTECTION:
        # Audit D3 split: the eval ClaimType is forum-agnostic, but the
        # orchestrator DisputeIssue depends on the matter_type.
        if matter_type == "deposit_deduction":
            return DisputeIssue("damage")
        if matter_type == "deposit_non_protection":
            return DisputeIssue("deposit_protection")
        if matter_type is None:
            warnings.warn(
                "eval_to_orchestrator received DEPOSIT_NON_PROTECTION "
                "without an explicit matter_type; defaulting to "
                "'deposit_deduction' (audit D3). Please add matter_type "
                "to gold rows.",
                DeprecationWarning,
                stacklevel=2,
            )
            return DisputeIssue("deposit_protection")  # legacy default
        raise UnmappableIssue(
            f"eval_to_orchestrator: matter_type {matter_type!r} not "
            "recognised for DEPOSIT_NON_PROTECTION (expected "
            "'deposit_non_protection' or 'deposit_deduction')"
        )
    if claim_type is ClaimType.DISREPAIR:
        orch_value = _REPAIRS_MATTER_TO_ORCH.get(matter_type or "")
        if orch_value is not None:
            return DisputeIssue(orch_value)
        raise UnmappableIssue(
            f"eval_to_orchestrator: ClaimType {claim_type.value!r} requires "
            "a Housing Ombudsman repairs matter_type "
            f"({sorted(_REPAIRS_MATTER_TO_ORCH)}); got {matter_type!r}"
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
