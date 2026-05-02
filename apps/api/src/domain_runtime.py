"""SHA-20 Phase 3 + Phase 8: API-layer runtime resolution for domain specs.

Phase 3 introduced the resolver and the simple gate-status enum. Phase 8
adds:

- :class:`DomainGateChecker`, which loads a signed launch-gate artifact
  from disk via :func:`eval.gates.load_gate_artifact` and verifies it
  against the domain's eval-gate thresholds via
  :func:`eval.gates.verify_gate_artifact`.
- Stage-aware resolution (``LaunchStage`` -> allowed ``requested_mode``).
- Allowlist policy that requires authenticated user IDs in production
  (no anonymous access for ``beta``/``research`` domains).
- Strict-eval-gates fail-closed enforcement (``DOMAIN_STRICT_EVAL_GATES``).
  Even ``housing.deposit.v1`` (the configured ``DEFAULT_DOMAIN``) is
  rejected when strict gates are on AND no passing artifact is on disk.
- Compatibility carve-out: when strict gates are OFF (e.g. local dev) the
  default deposit baseline still resolves to ``unrestricted`` even if the
  YAML stage is ``research``.

The Phase 8 implementation must not break the Phase 3 contract:
``housing.deposit.v1`` keeps resolving to ``gate_status=enabled`` whenever
strict gates are off, and existing trace tags + cache-key segments are
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    * ``enabled`` — the gate is open: domain is in ``ENABLED_DOMAINS`` and
      (if strict gates are on) a passing artifact is on disk.
    * ``disabled`` — domain is registered but not in ``ENABLED_DOMAINS``.
    * ``gate_missing`` — strict gates are on but no artifact exists.
    * ``gate_stale`` — artifact loads but verification fails (hash
      mismatch, threshold violation, missing reviewer fields, …).
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
# Stage / mode policy
# ---------------------------------------------------------------------------


# What ``requested_mode`` values may run for each ``LaunchStage``.
# - ``production`` stage: serves all three modes.
# - ``beta`` stage: never production traffic.
# - ``research`` stage: research only (eval runners + internal tools).
# - ``disabled`` stage: nothing.
_STAGE_MODES: Dict[LaunchStage, set[str]] = {
    LaunchStage.PRODUCTION: {"production", "beta", "research"},
    LaunchStage.BETA: {"beta", "research"},
    LaunchStage.RESEARCH: {"research"},
    LaunchStage.DISABLED: set(),
}


def _mode_allowed_for_stage(stage: LaunchStage, requested_mode: str) -> bool:
    return requested_mode in _STAGE_MODES.get(stage, set())


# ---------------------------------------------------------------------------
# Composed runtime context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainRuntimeContext:
    """Composed runtime context for a single resolved domain."""

    domain_spec: DomainSpec
    gate_status: DomainGateStatus
    allowlist_status: DomainAllowlistStatus
    routing_metadata: Dict[str, Any] = field(default_factory=dict)
    core: Optional[_CoreRuntimeContext] = None
    prediction_mode: str = "production"
    cross_domain_retrieval: bool = False
    # Phase 8: artifact identifiers carried through to traces. ``None`` when
    # no artifact was loaded (strict gates off OR file missing).
    gate_artifact_id: Optional[str] = None
    gate_artifact_hash: Optional[str] = None

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
        """Return the SHA-20 Phase 8 trace-tag superset.

        Tags whose values are unknown at trace-start (e.g. per-citation
        ``source.publisher``) are simply omitted; the trace logger drops
        ``None`` values.
        """
        spec = self.domain_spec
        ns = spec.retrieval_namespaces
        namespace_id = ns[0].namespace_id if ns else None
        forum_value = spec.forums[0].value if spec.forums else None
        tags: Dict[str, Optional[str]] = {
            "domain.id": self.domain_id,
            "domain.family": spec.family.value,
            "domain.domain_version": spec.domain_version,
            "domain.stage": spec.stage.value,
            "forum": forum_value,
            "retrieval.namespace": namespace_id,
            "prompt_pack.id": str(spec.id),  # one pack per domain in Phase 6
            "ontology.id": str(spec.id),  # one ontology per domain in Phase 5
            "eval_suite.id": str(spec.id),
            "prediction_mode": self.prediction_mode,
            "cross_domain_retrieval": "true" if self.cross_domain_retrieval else "false",
            # ``llm.role`` / ``llm.provider`` / ``source.*`` are populated by
            # tools at call-time, not at trace start.
            "llm.role": None,
            "llm.provider": None,
            "source.publisher": None,
            "source.kind": None,
            "domain_gate.artifact_id": self.gate_artifact_id,
            "domain_gate.artifact_hash": self.gate_artifact_hash,
            # Compatibility tags retained from Phase 3 callers.
            "domain.gate_status": self.gate_status.value,
            "domain.allowlist_status": self.allowlist_status.value,
        }
        # Drop ``None`` so the LangFuse / no-op metadata doesn't carry empty
        # values into the trace store.
        return {k: v for k, v in tags.items() if v is not None}


# ---------------------------------------------------------------------------
# Gate checker (Phase 8)
# ---------------------------------------------------------------------------


@dataclass
class DomainGateCheckResult:
    """Outcome of :meth:`DomainGateChecker.check`.

    ``status`` mirrors :class:`DomainGateStatus` plus a small compatibility
    layer for callers that only need a yes/no answer.
    """

    status: DomainGateStatus
    artifact_id: Optional[str] = None
    artifact_hash: Optional[str] = None
    reasons: List[str] = field(default_factory=list)


class DomainGateChecker:
    """Loads + verifies a domain's launch-gate artifact.

    Stateless wrapper around :func:`eval.gates.load_gate_artifact` /
    :func:`eval.gates.verify_gate_artifact` that maps the verifier's
    structured result onto :class:`DomainGateStatus`. Kept in the apps
    layer (rather than ``packages/eval``) so the ``eval`` package stays
    importable from offline scripts.
    """

    def __init__(self, *, gate_dir: Path) -> None:
        self.gate_dir = Path(gate_dir)

    def check(
        self,
        spec: DomainSpec,
        *,
        requested_mode: str,
    ) -> DomainGateCheckResult:
        """Return the gate status for ``spec`` at ``requested_mode``.

        The artifact's ``stage_requested`` must match the requested mode
        for the gate to count as passing. ``research`` mode is the only
        mode that can run without a passing artifact (callers gate that
        themselves via ``DOMAIN_STRICT_EVAL_GATES``).
        """
        # Local imports to avoid pulling ``eval`` at module import time.
        from eval.gates import (
            GateThresholds,
            load_gate_artifact,
            verify_gate_artifact,
        )

        domain_id = str(spec.id)

        try:
            artifact = load_gate_artifact(domain_id, gate_dir=self.gate_dir)
        except Exception as exc:  # corrupt JSON, bad pydantic, etc.
            return DomainGateCheckResult(
                status=DomainGateStatus.GATE_STALE,
                reasons=[f"failed to load gate artifact: {exc}"],
            )

        if artifact is None:
            return DomainGateCheckResult(
                status=DomainGateStatus.GATE_MISSING,
                reasons=[
                    f"no gate artifact at {self.gate_dir}/{domain_id}.json"
                ],
            )

        # The artifact must explicitly target the requested mode. A
        # production gate does NOT vouch for beta runs and vice versa.
        if artifact.stage_requested != requested_mode:
            return DomainGateCheckResult(
                status=DomainGateStatus.GATE_STALE,
                artifact_id=domain_id,
                artifact_hash=artifact.artifact_hash,
                reasons=[
                    f"artifact stage_requested={artifact.stage_requested!r} "
                    f"does not match requested_mode={requested_mode!r}"
                ],
            )

        thresholds = GateThresholds.from_eval_gate(spec.eval_gate)
        artifact_path = self.gate_dir / f"{domain_id}.json"
        verification = verify_gate_artifact(
            artifact_path,
            thresholds=thresholds,
        )

        if verification.passed:
            return DomainGateCheckResult(
                status=DomainGateStatus.ENABLED,
                artifact_id=domain_id,
                artifact_hash=artifact.artifact_hash,
                reasons=list(verification.warnings),
            )
        return DomainGateCheckResult(
            status=DomainGateStatus.GATE_STALE,
            artifact_id=domain_id,
            artifact_hash=artifact.artifact_hash,
            reasons=list(verification.reasons),
        )


# ---------------------------------------------------------------------------
# Allowlist resolution
# ---------------------------------------------------------------------------


def _allowlist_for_family(family: str) -> List[str]:
    """Return the configured beta/research allowlist for ``family``.

    Stable user IDs only (Supabase UUIDs once auth lands). Email addresses
    and API keys MUST NOT be passed in as ``user_id``.
    """
    cfg = _global_config
    if family == "employment":
        return list(cfg.domain_employment_beta_allowlist_user_ids) or list(
            cfg.domain_beta_allowlist_user_ids
        )
    return list(cfg.domain_beta_allowlist_user_ids)


def _allowlist_status(
    spec: DomainSpec,
    *,
    user_id: Optional[str],
    requested_mode: str,
    is_default_domain: bool,
    strict_gates: bool,
) -> DomainAllowlistStatus:
    """Compute the per-user allowlist outcome.

    Production-stage domains are uniformly unrestricted. Beta and research
    domains require an authenticated stable user ID matching the
    configured allowlist — except for the configured ``DEFAULT_DOMAIN``
    when strict gates are off (the deposit-baseline carve-out).
    """
    if spec.stage == LaunchStage.DISABLED:
        return DomainAllowlistStatus.BLOCKED

    if spec.stage == LaunchStage.PRODUCTION:
        return DomainAllowlistStatus.UNRESTRICTED

    # beta / research below.

    # Carve-out: the configured ``DEFAULT_DOMAIN`` keeps anonymous-access
    # behaviour as long as strict gates are off (local/dev/test). Once
    # strict gates flip on the carve-out is consumed by the gate check
    # path; this branch only governs allowlist outcomes.
    if is_default_domain and not strict_gates:
        return DomainAllowlistStatus.UNRESTRICTED

    if not user_id:
        return DomainAllowlistStatus.BLOCKED

    allowed = _allowlist_for_family(spec.family.value)
    if user_id in allowed:
        return DomainAllowlistStatus.ALLOWLISTED
    return DomainAllowlistStatus.BLOCKED


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_domain_runtime(
    domain_id: Optional[str],
    *,
    user_id: Optional[str] = None,
    requested_mode: str = "production",
    cross_domain_retrieval: bool = False,
    selected_via: str = "default",
    gate_checker: Optional[DomainGateChecker] = None,
) -> DomainRuntimeContext:
    """Resolve a :class:`DomainRuntimeContext` for an incoming request.

    Resolution order (Phase 8):

    1. Domain exists in registry (``DomainNotFoundError`` otherwise).
    2. Domain enabled in ``ENABLED_DOMAINS`` (else ``DISABLED``).
    3. ``requested_mode`` allowed by the spec's ``LaunchStage`` mapping.
    4. Per-user allowlist (beta / research domains).
    5. Strict-gate verification when ``DOMAIN_STRICT_EVAL_GATES=true``.

    User-facing API calls default to ``requested_mode="production"``. Eval
    runners and internal research tools must explicitly set
    ``requested_mode="research"``.
    """
    cfg = _global_config

    # Step 1: resolve to a concrete id.
    target_id = (domain_id or "").strip() or cfg.default_domain
    if domain_id and domain_id.strip() and domain_id.strip() != cfg.default_domain:
        actual_selected_via = (
            "explicit_request" if selected_via == "default" else selected_via
        )
    else:
        actual_selected_via = selected_via

    # Step 2: load the spec (raises DomainNotFoundError for unknown ids).
    spec = get_domain_spec(target_id)
    is_default_domain = target_id == cfg.default_domain

    # Step 3: enabled in ENABLED_DOMAINS?
    if target_id not in cfg.enabled_domains:
        gate_status = DomainGateStatus.DISABLED
        gate_artifact_id: Optional[str] = None
        gate_artifact_hash: Optional[str] = None
        gate_reasons: List[str] = [f"{target_id!r} not in ENABLED_DOMAINS"]
    else:
        gate_status = DomainGateStatus.ENABLED
        gate_artifact_id = None
        gate_artifact_hash = None
        gate_reasons = []

        # Compatibility carve-out for the configured ``DEFAULT_DOMAIN`` when
        # strict gates are off: skip BOTH the stage-mode policy check and
        # the artifact verification. This preserves the legacy deposit
        # baseline (anonymous traffic, ``stage=research``) for local /
        # test deployments. Once strict gates flip on, even the default
        # domain falls through to fail-closed.
        carve_out_active = (
            is_default_domain and not cfg.domain_strict_eval_gates
        )

        # Step 3b: stage allows the requested mode?
        if not carve_out_active and not _mode_allowed_for_stage(
            spec.stage, requested_mode
        ):
            # We surface this as DISABLED (the ``stage`` itself prevents
            # the requested_mode). It's not GATE_MISSING — there's nothing
            # missing, the policy says no.
            gate_status = DomainGateStatus.DISABLED
            gate_reasons.append(
                f"stage={spec.stage.value!r} does not permit "
                f"requested_mode={requested_mode!r}"
            )

        # Step 5: strict-gates artifact verification.
        # Research mode: artifact is OPTIONAL even with strict gates on.
        # Production / beta mode: artifact REQUIRED with strict gates on.
        elif cfg.domain_strict_eval_gates and requested_mode in {
            "production",
            "beta",
        }:
            checker = gate_checker or DomainGateChecker(
                gate_dir=cfg.domain_gate_artifact_dir
            )
            check = checker.check(spec, requested_mode=requested_mode)
            if check.status != DomainGateStatus.ENABLED:
                gate_status = check.status
                gate_reasons.extend(check.reasons)
            gate_artifact_id = check.artifact_id
            gate_artifact_hash = check.artifact_hash

    # Step 4: allowlist (independent of gate status so callers can tell
    # ``user blocked`` apart from ``gate blocked``).
    allowlist_status = _allowlist_status(
        spec,
        user_id=user_id,
        requested_mode=requested_mode,
        is_default_domain=is_default_domain,
        strict_gates=cfg.domain_strict_eval_gates,
    )

    routing_metadata: Dict[str, Any] = {
        "selected_via": actual_selected_via,
        "confidence": None,
        "requested_domain_id": domain_id,
        "resolved_domain_id": target_id,
        "requested_mode": requested_mode,
        "gate_reasons": gate_reasons,
    }

    return DomainRuntimeContext(
        domain_spec=spec,
        gate_status=gate_status,
        allowlist_status=allowlist_status,
        routing_metadata=routing_metadata,
        core=_CoreRuntimeContext(spec=spec),
        prediction_mode=requested_mode,
        cross_domain_retrieval=bool(cross_domain_retrieval)
        and cfg.domain_cross_retrieval_allowed,
        gate_artifact_id=gate_artifact_id,
        gate_artifact_hash=gate_artifact_hash,
    )


__all__ = [
    "DomainAllowlistStatus",
    "DomainGateChecker",
    "DomainGateCheckResult",
    "DomainGateStatus",
    "DomainNotFoundError",
    "DomainRuntimeContext",
    "DomainUnavailableError",
    "resolve_domain_runtime",
]
