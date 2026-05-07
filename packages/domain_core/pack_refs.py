"""Optional pack-reference fields for the DomainSpec extension.

Each field is a ``ref://{kind}/{id}`` URI pointing at a domain-pack
artefact (factor catalog, outcome schema, remedy schema, retrieval
profile, evaluation profile). All fields are optional during the
transition period; callers can use ``warn_if_missing`` to emit a
UserWarning when a spec has no pack artefacts configured.

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §6.
"""

from __future__ import annotations

import re
import warnings
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

_REF_PATTERN = re.compile(r"^ref://([a-z_]+)/([^/]+)$")
_PACK_REF_FIELDS = (
    "factor_catalog_ref",
    "outcome_schema_ref",
    "remedy_schema_ref",
    "retrieval_profile_ref",
    "evaluation_profile_ref",
)


def _validate_kind(value: str, allowed_kind: str) -> str:
    match = _REF_PATTERN.match(value)
    if not match:
        raise ValueError(
            f"pack ref must match 'ref://{{kind}}/{{id}}'; got {value!r}"
        )
    kind = match.group(1)
    if kind != allowed_kind:
        raise ValueError(
            f"pack ref kind must be {allowed_kind!r}; got {kind!r} "
            f"in {value!r}"
        )
    return value


class PackReferenceSet(BaseModel):
    """Five optional ref:// pointers added to DomainSpec."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    factor_catalog_ref: Optional[str] = None
    outcome_schema_ref: Optional[str] = None
    remedy_schema_ref: Optional[str] = None
    retrieval_profile_ref: Optional[str] = None
    evaluation_profile_ref: Optional[str] = None

    @field_validator("factor_catalog_ref")
    @classmethod
    def _v_factor_catalog(cls, v: Optional[str]) -> Optional[str]:
        return _validate_kind(v, "factor_catalog") if v is not None else v

    @field_validator("outcome_schema_ref")
    @classmethod
    def _v_outcome_schema(cls, v: Optional[str]) -> Optional[str]:
        return _validate_kind(v, "outcome_schema") if v is not None else v

    @field_validator("remedy_schema_ref")
    @classmethod
    def _v_remedy_schema(cls, v: Optional[str]) -> Optional[str]:
        return _validate_kind(v, "remedy_schema") if v is not None else v

    @field_validator("retrieval_profile_ref")
    @classmethod
    def _v_retrieval_profile(cls, v: Optional[str]) -> Optional[str]:
        return _validate_kind(v, "retrieval_profile") if v is not None else v

    @field_validator("evaluation_profile_ref")
    @classmethod
    def _v_evaluation_profile(cls, v: Optional[str]) -> Optional[str]:
        return _validate_kind(v, "evaluation_profile") if v is not None else v


def warn_if_missing(
    *, spec_id: str, pack_refs: Optional[PackReferenceSet]
) -> None:
    """Warn when a spec has no usable pack refs configured.

    This is the transition-period hook: it emits ``UserWarning`` for missing
    or empty pack refs, and never raises.
    """
    if pack_refs is None:
        warnings.warn(
            f"DomainSpec {spec_id!r}: pack_refs is None. Add a "
            "PackReferenceSet pointing at the domain pack artefacts "
            "(spec §6).",
            UserWarning,
            stacklevel=2,
        )
        return

    if all(getattr(pack_refs, field) is None for field in _PACK_REF_FIELDS):
        warnings.warn(
            f"DomainSpec {spec_id!r}: pack_refs is present but every "
            "field is None. Populate at least factor_catalog_ref.",
            UserWarning,
            stacklevel=2,
        )
