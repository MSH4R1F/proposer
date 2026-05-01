"""SHA-20 Phase 3: API-layer runtime resolution for domain specs.

This module is the *composition* point for ``domain_core.DomainRuntimeContext``.
``domain_core`` declares the shape (spec + optional implementation handles);
this module adds the gate / allowlist / routing-metadata bookkeeping that the
HTTP layer needs to decide whether a request may proceed under a given domain.

Phase 3 scope:

- Resolution honours ``ENABLED_DOMAINS`` (gate enabled/disabled) and the
  configured beta allowlists for ``stage=research`` domains.
- Full launch-gate enforcement (signed artifact, freshness checks, eval-gate
  thresholds) lands in Phase 8 / SHA-122. The placeholder enum values
  ``gate_missing`` / ``gate_stale`` are reserved here so callers can already
  branch on them.
- ``housing.deposit.v1`` MUST resolve to ``gate_status=enabled`` whenever
  ``DEFAULT_DOMAIN`` is the deposit baseline (compatibility invariant from
  the SHA-20 plan).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from domain_core import (
    DomainNotFoundError,
    DomainRuntimeContext as _CoreRuntimeContext,
    DomainSpec,
    LaunchStage,
    get_domain_spec,
    hash_domain_spec,
)

from apps.api.src.config import config as _global_config


# ---------------------------------------------------------------------------
# Status enums
# ---------------------------------------------------------------------------


class DomainGateStatus(str, Enum):
    """Status of the launch gate for a resolved domain.

    Phase 3 only emits ``enabled`` / ``disabled``. The remaining values are
    reserved for the Phase 8 launch-gate enforcement work (SHA-122).
    """

    ENABLED = "enabled"
    DISABLED = "disabled"
    GATE_MISSING = "gate_missing"
    GATE_STALE = "gate_stale"


class DomainAllowlistStatus(str, Enum):
    """Per-user allowlist outcome for the resolved domain."""

    UNRESTRICTED = "unrestricted"
    ALLOWLISTED = "allowlisted"
    BLOCKED = "blocked"


class DomainUnavailableError(Exception):
    """Raised by callers when ``DomainRuntimeContext`` is not usable.

    Carries a stable ``code`` so the HTTP layer can map it to a 4xx response.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        domain_id: str,
        gate_status: DomainGateStatus,
        allowlist_status: DomainAllowlistStatus,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.domain_id = domain_id
        self.gate_status = gate_status
        self.allowlist_status = allowlist_status


# ---------------------------------------------------------------------------
# Composed runtime context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainRuntimeContext:
    """Composed runtime context for a single resolved domain.

    Wraps ``domain_core.DomainRuntimeContext`` with API-layer status fields.
    The ``core`` attribute is what tooling (intake schema, prompt pack, etc.)
    will eventually attach; we keep it here so that the rest of the API can
    type-hint a single context object.
    """

    domain_spec: DomainSpec
    gate_status: DomainGateStatus
    allowlist_status: DomainAllowlistStatus
    routing_metadata: Dict[str, Any] = field(default_factory=dict)
    core: Optional[_CoreRuntimeContext] = None
    prediction_mode: str = "production"
    cross_domain_retrieval: bool = False

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def domain_id(self) -> str:
        return str(self.domain_spec.id)

    @property
    def is_usable(self) -> bool:
        """True iff the gate is enabled and the user is not blocked."""
        return (
            self.gate_status == DomainGateStatus.ENABLED
            and self.allowlist_status != DomainAllowlistStatus.BLOCKED
        )

    @property
    def domain_spec_hash(self) -> str:
        return hash_domain_spec(self.domain_spec)

    # ------------------------------------------------------------------
    # Trace tagging
    # ------------------------------------------------------------------

    def domain_tags(self) -> Dict[str, str]:
        """Return Phase-3 domain tags for trace logging.

        Includes the Phase-8 superset where the data is already available
        (gate / allowlist) so traces are forward-compatible.
        """
        tags: Dict[str, str] = {
            "domain.id": self.domain_id,
            "domain.family": self.domain_spec.family.value,
            "domain.domain_version": self.domain_spec.domain_version,
            "domain.stage": self.domain_spec.stage.value,
            "domain.gate_status": self.gate_status.value,
            "domain.allowlist_status": self.allowlist_status.value,
            "prediction_mode": self.prediction_mode,
            "cross_domain_retrieval": "true" if self.cross_domain_retrieval else "false",
        }
        return tags


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _allowlist_for_family(family: str) -> list[str]:
    """Return the configured beta allowlist for a given domain family.

    Phase 3 supports the generic ``DOMAIN_BETA_ALLOWLIST_USER_IDS`` plus a
    per-family override for ``employment``. Other families fall back to the
    generic list.
    """
    cfg = _global_config
    if family == "employment":
        return list(cfg.domain_employment_beta_allowlist_user_ids) or list(
            cfg.domain_beta_allowlist_user_ids
        )
    return list(cfg.domain_beta_allowlist_user_ids)


def resolve_domain_runtime(
    domain_id: Optional[str],
    *,
    user_id: Optional[str] = None,
    requested_mode: str = "production",
    cross_domain_retrieval: bool = False,
    selected_via: str = "default",
) -> DomainRuntimeContext:
    """Resolve a ``DomainRuntimeContext`` for an incoming request.

    Args:
        domain_id: The requested domain id. ``None`` falls back to
            ``DEFAULT_DOMAIN`` from config.
        user_id: Stable authenticated user id (Supabase UUID once auth lands).
            Used to evaluate ``stage=research`` allowlists. Email addresses
            and API keys MUST NOT be passed in here.
        requested_mode: Prediction mode for the resolved run (production,
            shadow, evaluation). Carried through to traces; not used to gate.
        cross_domain_retrieval: Whether the caller wants cross-namespace
            retrieval. Cross-domain is gated by
            ``DOMAIN_CROSS_RETRIEVAL_ALLOWED`` in config; until that flag is
            true (Phase 4+) the value here is treated as informational only.
        selected_via: How this domain was chosen (``default``,
            ``explicit_request``, ``router``, ...). Recorded in
            ``routing_metadata`` for audit.

    Raises:
        DomainNotFoundError: when the requested id is not in the registry.
    """
    cfg = _global_config

    # Step 1: resolve to a concrete id.
    target_id = (domain_id or "").strip() or cfg.default_domain
    if domain_id and domain_id.strip() and domain_id.strip() != cfg.default_domain:
        actual_selected_via = "explicit_request" if selected_via == "default" else selected_via
    else:
        actual_selected_via = selected_via

    # Step 2: load the spec (raises DomainNotFoundError for unknown ids).
    spec = get_domain_spec(target_id)

    # Step 3: gate status — Phase 3 only checks ENABLED_DOMAINS.
    if target_id in cfg.enabled_domains:
        gate_status = DomainGateStatus.ENABLED
    else:
        gate_status = DomainGateStatus.DISABLED

    # Step 4: allowlist status.
    #
    # Compatibility carve-out (SHA-20 Phase 3, plan §"Hard constraints"):
    # the configured ``DEFAULT_DOMAIN`` is treated as ``unrestricted`` even if
    # its YAML stage is ``research``. This preserves the existing deposit
    # baseline (``housing.deposit.v1`` ships at stage=research per the audit's
    # D1/D2 decisions, but must remain accessible to anonymous traffic until
    # the V2 launch gate is signed). Non-default research domains still enforce
    # the family allowlist.
    #
    # Production/beta domains are uniformly unrestricted. Disabled-stage
    # domains short-circuit to blocked.
    allowlist_status: DomainAllowlistStatus
    is_default_domain = target_id == cfg.default_domain
    if spec.stage == LaunchStage.DISABLED:
        allowlist_status = DomainAllowlistStatus.BLOCKED
    elif spec.stage == LaunchStage.RESEARCH and not is_default_domain:
        if not user_id:
            allowlist_status = DomainAllowlistStatus.BLOCKED
        else:
            allowed = _allowlist_for_family(spec.family.value)
            allowlist_status = (
                DomainAllowlistStatus.ALLOWLISTED
                if user_id in allowed
                else DomainAllowlistStatus.BLOCKED
            )
    elif spec.stage == LaunchStage.RESEARCH and is_default_domain:
        # Default research domain is the deposit compatibility baseline.
        allowlist_status = DomainAllowlistStatus.UNRESTRICTED
    else:
        allowlist_status = DomainAllowlistStatus.UNRESTRICTED

    routing_metadata: Dict[str, Any] = {
        "selected_via": actual_selected_via,
        "confidence": None,
        "requested_domain_id": domain_id,
        "resolved_domain_id": target_id,
    }

    return DomainRuntimeContext(
        domain_spec=spec,
        gate_status=gate_status,
        allowlist_status=allowlist_status,
        routing_metadata=routing_metadata,
        core=_CoreRuntimeContext(spec=spec),
        prediction_mode=requested_mode,
        cross_domain_retrieval=bool(cross_domain_retrieval) and cfg.domain_cross_retrieval_allowed,
    )


__all__ = [
    "DomainAllowlistStatus",
    "DomainGateStatus",
    "DomainRuntimeContext",
    "DomainUnavailableError",
    "resolve_domain_runtime",
    "DomainNotFoundError",
]
