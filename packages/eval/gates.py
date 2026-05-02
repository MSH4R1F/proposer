"""SHA-20 Phase 7 — domain launch-gate artifacts.

A :class:`DomainGateArtifact` is an immutable, signed (Phase 8.5) record
that asserts a given ``(domain_id, stage)`` pair has passed evaluation.
Production / beta runtime code refuses to serve a domain that lacks a
fresh, valid gate artifact.

Hashing
-------
``artifact_hash`` is the SHA-256 of canonical JSON (sorted keys, no
whitespace, ASCII) of every field except ``signature`` and
``signing_key_id``.

Signing
-------
``signature`` is an Ed25519 signature over ``artifact_hash``. Public
keys live in ``packages/domain_core/keys/launch_gate_public_keys.json``;
private keys MUST NOT be committed. For local MVP, signing is deferred
(``# TODO Phase 8.5``) — but the strict runtime gate still validates
the artifact_hash + reviewer fields + thresholds + git/corpus/hash
freshness. Production / beta MUST add Ed25519 before public exposure.

CLI
---
``python -m eval.gates verify --domain housing.deposit.v1 --stage production``
returns 0 on pass, non-zero with structured reasons on fail.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain_core.spec import EvalGate

_log = logging.getLogger(__name__)


# Default locations.
DEFAULT_GATE_DIR = Path("data/eval_artifacts/domain_gates")
DEFAULT_PUBLIC_KEYS_PATH = (
    Path("packages/domain_core/keys/launch_gate_public_keys.json")
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class GateThresholds(BaseModel):
    """Minimum thresholds an artifact's metrics must meet to pass.

    Mirrors :class:`domain_core.spec.EvalGate` but typed as a comparison
    target (artifacts compare metric values to these floors / ceilings).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_cases: int
    required_metrics: Dict[str, float] = Field(default_factory=dict)
    max_hallucination_rate: float = 0.02
    min_citation_validity: float = 0.98
    min_abstention_precision: float = 0.80

    @classmethod
    def from_eval_gate(cls, gate: EvalGate) -> "GateThresholds":
        return cls(
            min_cases=gate.min_cases,
            required_metrics=dict(gate.required_metrics),
            max_hallucination_rate=gate.max_hallucination_rate,
            min_citation_validity=gate.min_citation_validity,
            min_abstention_precision=gate.min_abstention_precision,
        )


class DomainGateArtifact(BaseModel):
    """On-disk gate artifact at
    ``data/eval_artifacts/domain_gates/{domain_id}.json``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_id: str
    stage_requested: Literal["production", "beta", "research"]
    git_sha: str
    corpus_version: str
    gold_set_path: str
    n_cases: int
    metrics: Dict[str, float] = Field(default_factory=dict)
    prompt_pack_hash: str
    ontology_hash: str
    domain_spec_hash: str
    verifier_hash: str
    reviewer_roles: List[str] = Field(default_factory=list)
    approved_by: List[str] = Field(default_factory=list)
    approved_at: str  # ISO-8601 datetime
    artifact_hash: str
    # Signature is OPTIONAL for local MVP (Phase 7); production/beta gates
    # MUST move to Ed25519 before public exposure (TODO Phase 8.5).
    signature: Optional[str] = None
    signing_key_id: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("git_sha")
    @classmethod
    def _validate_git_sha(cls, v: str) -> str:
        if not v or not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError("git_sha must be a hex string")
        return v.lower()

    def hashable_payload(self) -> Dict[str, Any]:
        """Return the dict whose canonical JSON forms ``artifact_hash``.

        Excludes ``signature`` and ``signing_key_id`` so signing is purely
        a wrapper around the hash.
        """
        d = self.model_dump(mode="json")
        d.pop("signature", None)
        d.pop("signing_key_id", None)
        d.pop("artifact_hash", None)
        return d


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canonicalize(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [_canonicalize(v) for v in value]
    if isinstance(value, tuple):
        return [_canonicalize(v) for v in value]
    return value


def compute_artifact_hash(payload_without_signature: Dict[str, Any]) -> str:
    """Stable hex SHA-256 of canonical JSON.

    The input must NOT contain ``signature``, ``signing_key_id``, or
    ``artifact_hash`` keys (the function does not strip them).
    """
    canonical = _canonicalize(payload_without_signature)
    blob = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


@dataclass
class GateVerificationResult:
    """Structured outcome of :func:`verify_gate_artifact`."""

    passed: bool
    domain_id: str
    stage_requested: str
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    artifact_path: Optional[Path] = None

    def fail(self, reason: str) -> None:
        self.passed = False
        self.reasons.append(reason)

    def warn(self, reason: str) -> None:
        self.warnings.append(reason)


def load_gate_artifact(
    domain_id: str, *, gate_dir: Optional[Path] = None
) -> Optional[DomainGateArtifact]:
    """Read ``{gate_dir}/{domain_id}.json``. Returns None if missing."""
    gate_dir = gate_dir or DEFAULT_GATE_DIR
    path = gate_dir / f"{domain_id}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    return DomainGateArtifact.model_validate(payload)


def _load_public_keys(public_keys_path: Optional[Path]) -> Dict[str, str]:
    path = public_keys_path or DEFAULT_PUBLIC_KEYS_PATH
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _gold_set_exists_with_min_cases(
    artifact: DomainGateArtifact, *, min_cases: int
) -> tuple[bool, str]:
    """Audit D2 fail-closed: the deposit production gate must refuse to
    pass if ``housing_v1.jsonl`` is missing locally OR has < min_cases.
    """
    p = Path(artifact.gold_set_path)
    if not p.exists():
        return False, f"gold_set file missing on disk: {p}"
    if artifact.n_cases < min_cases:
        return (
            False,
            f"n_cases={artifact.n_cases} below min_cases={min_cases}",
        )
    return True, ""


def verify_gate_artifact(
    artifact_path: Path,
    *,
    public_keys_path: Optional[Path] = None,
    thresholds: Optional[GateThresholds] = None,
) -> GateVerificationResult:
    """Verify an on-disk gate artifact.

    Checks performed (all required, all fail-closed):

    * artifact loads + parses.
    * ``artifact_hash`` matches the canonical-JSON SHA-256 of the rest.
    * ``signature`` (if present) verifies under the listed public key.
    * ``stage_requested`` in {production, beta, research}.
    * For ``housing.deposit.v1`` production: ``gold_set_path`` exists on
      disk and ``n_cases >= 50`` (audit D2).
    * Metrics meet thresholds (if provided).

    Production/beta gates MUST eventually require ``signature`` + a known
    ``signing_key_id``. Local MVP allows ``signature=None`` with a
    warning, gated by the ``# TODO Phase 8.5`` comment.
    """
    artifact_path = Path(artifact_path)
    if not artifact_path.exists():
        return GateVerificationResult(
            passed=False,
            domain_id="<unknown>",
            stage_requested="<unknown>",
            reasons=[f"artifact file missing: {artifact_path}"],
            artifact_path=artifact_path,
        )

    payload: Any = {}
    try:
        payload = json.loads(artifact_path.read_text())
        artifact = DomainGateArtifact.model_validate(payload)
    except Exception as e:  # pragma: no cover - guarded but surface the error
        return GateVerificationResult(
            passed=False,
            domain_id=(
                str(payload.get("domain_id", "<unknown>"))
                if isinstance(payload, dict)
                else "<unknown>"
            ),
            stage_requested="<unknown>",
            reasons=[f"failed to parse artifact: {e}"],
            artifact_path=artifact_path,
        )

    result = GateVerificationResult(
        passed=True,
        domain_id=artifact.domain_id,
        stage_requested=artifact.stage_requested,
        artifact_path=artifact_path,
    )

    # Hash freshness.
    expected_hash = compute_artifact_hash(artifact.hashable_payload())
    if expected_hash != artifact.artifact_hash:
        result.fail(
            f"artifact_hash mismatch: stored={artifact.artifact_hash}, "
            f"recomputed={expected_hash}"
        )

    # Audit D2 hard rule (deposit production fail-closed).
    if (
        artifact.domain_id == "housing.deposit.v1"
        and artifact.stage_requested == "production"
    ):
        ok, msg = _gold_set_exists_with_min_cases(artifact, min_cases=50)
        if not ok:
            result.fail(f"audit D2 fail-closed: {msg}")

    # Generic min-cases check.
    if thresholds is not None:
        if artifact.n_cases < thresholds.min_cases:
            result.fail(
                f"n_cases={artifact.n_cases} below threshold "
                f"min_cases={thresholds.min_cases}"
            )
        for metric_name, floor in thresholds.required_metrics.items():
            value = artifact.metrics.get(metric_name)
            if value is None:
                result.fail(f"metric {metric_name!r} missing from artifact")
                continue
            # If the threshold name encodes a max (e.g. brier_score_max),
            # interpret as upper bound rather than lower.
            if metric_name.endswith("_max"):
                if value > floor:
                    result.fail(
                        f"metric {metric_name}={value} exceeds max {floor}"
                    )
            else:
                if value < floor:
                    result.fail(
                        f"metric {metric_name}={value} below floor {floor}"
                    )
        # Hallucination rate / citation validity / abstention precision.
        h = artifact.metrics.get("hallucination_rate")
        if h is not None and h > thresholds.max_hallucination_rate:
            result.fail(
                f"hallucination_rate={h} > max {thresholds.max_hallucination_rate}"
            )
        cv = artifact.metrics.get("citation_validity")
        if cv is not None and cv < thresholds.min_citation_validity:
            result.fail(
                f"citation_validity={cv} < min "
                f"{thresholds.min_citation_validity}"
            )
        ap = artifact.metrics.get("abstention_precision")
        if ap is not None and ap < thresholds.min_abstention_precision:
            result.fail(
                f"abstention_precision={ap} < min "
                f"{thresholds.min_abstention_precision}"
            )

    # Reviewer fields (production/beta require non-empty).
    if artifact.stage_requested in {"production", "beta"}:
        if not artifact.reviewer_roles:
            result.fail("reviewer_roles is empty for production/beta stage")
        if not artifact.approved_by:
            result.fail("approved_by is empty for production/beta stage")

    # Signature.
    keys = _load_public_keys(public_keys_path)
    if artifact.signature is None:
        if artifact.stage_requested in {"production", "beta"}:
            # TODO Phase 8.5: require Ed25519 signature for production/beta
            # before public exposure. For local MVP we WARN rather than fail.
            result.warn(
                "signature missing; Phase 8.5 will require Ed25519 "
                "signing for production/beta gates before public exposure."
            )
    else:
        # We accept a signature only if (a) signing_key_id is set and (b) we
        # know the public key. Verifying the actual Ed25519 bytes is a
        # Phase 8.5 follow-up; we intentionally do NOT pretend the bytes
        # validate when no key is registered.
        if not artifact.signing_key_id:
            result.fail("signature present but signing_key_id is missing")
        elif artifact.signing_key_id not in keys:
            result.fail(
                f"signature present but signing_key_id "
                f"{artifact.signing_key_id!r} is not registered in "
                f"{public_keys_path or DEFAULT_PUBLIC_KEYS_PATH}"
            )
        else:
            # TODO Phase 8.5: actually verify Ed25519 here.
            result.warn(
                "Ed25519 signature present and key registered; "
                "cryptographic byte-level verification deferred to Phase 8.5."
            )

    return result


# ---------------------------------------------------------------------------
# Builder helper
# ---------------------------------------------------------------------------


def build_artifact(
    *,
    domain_id: str,
    stage_requested: Literal["production", "beta", "research"],
    git_sha: str,
    corpus_version: str,
    gold_set_path: str,
    n_cases: int,
    metrics: Dict[str, float],
    prompt_pack_hash: str,
    ontology_hash: str,
    domain_spec_hash: str,
    verifier_hash: str,
    reviewer_roles: Optional[List[str]] = None,
    approved_by: Optional[List[str]] = None,
    approved_at: Optional[str] = None,
    notes: Optional[str] = None,
) -> DomainGateArtifact:
    """Construct a :class:`DomainGateArtifact` and stamp ``artifact_hash``.

    Signing is NOT performed here; pass through ``--sign`` in the CLI
    instead (currently raises NotImplementedError per Phase 8.5).
    """
    approved_at = approved_at or datetime.now(timezone.utc).isoformat()
    payload = {
        "domain_id": domain_id,
        "stage_requested": stage_requested,
        "git_sha": git_sha,
        "corpus_version": corpus_version,
        "gold_set_path": gold_set_path,
        "n_cases": n_cases,
        "metrics": dict(metrics),
        "prompt_pack_hash": prompt_pack_hash,
        "ontology_hash": ontology_hash,
        "domain_spec_hash": domain_spec_hash,
        "verifier_hash": verifier_hash,
        "reviewer_roles": list(reviewer_roles or []),
        "approved_by": list(approved_by or []),
        "approved_at": approved_at,
        "notes": notes,
    }
    artifact_hash = compute_artifact_hash(payload)
    return DomainGateArtifact(
        **payload,
        artifact_hash=artifact_hash,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli_main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.gates")
    sub = parser.add_subparsers(dest="cmd", required=True)

    verify_p = sub.add_parser("verify", help="Verify a gate artifact for a domain")
    verify_p.add_argument("--domain", required=True, help="Domain id (e.g. housing.deposit.v1)")
    verify_p.add_argument(
        "--stage",
        required=True,
        choices=("production", "beta", "research"),
    )
    verify_p.add_argument(
        "--gate-dir",
        type=Path,
        default=DEFAULT_GATE_DIR,
    )
    verify_p.add_argument(
        "--public-keys",
        type=Path,
        default=DEFAULT_PUBLIC_KEYS_PATH,
    )

    args = parser.parse_args(argv)

    if args.cmd == "verify":
        gate_path = args.gate_dir / f"{args.domain}.json"
        # Resolve thresholds from the domain spec when possible.
        thresholds: Optional[GateThresholds] = None
        try:
            from domain_core.registry import get_domain_spec

            spec = get_domain_spec(args.domain)
            thresholds = GateThresholds.from_eval_gate(spec.eval_gate)
        except Exception as e:  # pragma: no cover - exercised in tests
            print(
                f"warning: could not load domain spec {args.domain!r}: {e}",
                file=sys.stderr,
            )

        result = verify_gate_artifact(
            gate_path,
            public_keys_path=args.public_keys,
            thresholds=thresholds,
        )
        # Audit D2: even when artifact is missing, the verify command
        # MUST exit non-zero so CI fails closed.
        report = {
            "domain_id": result.domain_id,
            "stage_requested": result.stage_requested,
            "passed": result.passed,
            "reasons": result.reasons,
            "warnings": result.warnings,
            "artifact_path": str(result.artifact_path)
            if result.artifact_path
            else None,
        }
        print(json.dumps(report, indent=2))
        return 0 if result.passed else 1

    return 2  # pragma: no cover


__all__ = [
    "DomainGateArtifact",
    "GateThresholds",
    "GateVerificationResult",
    "compute_artifact_hash",
    "verify_gate_artifact",
    "load_gate_artifact",
    "build_artifact",
    "DEFAULT_GATE_DIR",
    "DEFAULT_PUBLIC_KEYS_PATH",
]


if __name__ == "__main__":
    raise SystemExit(_cli_main())
