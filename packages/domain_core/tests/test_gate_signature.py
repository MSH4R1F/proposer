"""SHA-20 Phase 7 — gate signature + artifact-hash stability test.

The runtime gate validation lives in ``eval.gates`` (so domain_core can
remain a leaf package). This test asserts:

* a ``DomainGateArtifact`` round-trips with a stable ``artifact_hash``
  across canonical-JSON serializations,
* the strict verifier still passes a research-stage artifact when no
  cryptographic signature is present (Phase 8.5 will tighten this).

NOTE: This is the only file Phase 7 is allowed to add under
``packages/domain_core/``. Do not modify other domain_core files.

# TODO Phase 8.5: Ed25519 signing
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from eval.gates import (
    DomainGateArtifact,
    build_artifact,
    compute_artifact_hash,
    verify_gate_artifact,
)


_FROZEN_TS = "2026-05-01T00:00:00+00:00"


def _make_artifact() -> DomainGateArtifact:
    return build_artifact(
        domain_id="housing.deposit.v1",
        stage_requested="research",
        git_sha="0" * 40,
        corpus_version="legacy_2025_pre_sha20",
        gold_set_path="data/gold_standard/housing_v1.jsonl",
        n_cases=50,
        metrics={"accuracy": 0.85},
        prompt_pack_hash="a" * 64,
        ontology_hash="b" * 64,
        domain_spec_hash="c" * 64,
        verifier_hash="d" * 64,
        reviewer_roles=["housing_legal"],
        approved_by=["reviewer@example.com"],
        approved_at=_FROZEN_TS,
    )


def test_artifact_hash_is_stable_across_serialisations():
    art = _make_artifact()
    blob1 = json.dumps(art.model_dump(mode="json"), sort_keys=True)
    blob2 = json.dumps(art.model_dump(mode="json"), sort_keys=True)
    assert blob1 == blob2

    # Re-deriving the hash from the canonical payload must match the stored value.
    rederived = compute_artifact_hash(art.hashable_payload())
    assert rederived == art.artifact_hash


def test_artifact_hash_excludes_signature_fields():
    """Signing must be a pure wrapper around the hash — adding a
    signature MUST NOT change ``artifact_hash``."""
    art = _make_artifact()
    payload_signed = {
        **art.model_dump(mode="json"),
        "signature": "sig-bytes",
        "signing_key_id": "key-1",
    }
    signed = DomainGateArtifact.model_validate(payload_signed)
    assert signed.artifact_hash == art.artifact_hash


def test_research_stage_passes_without_signature(tmp_path: Path):
    """Strict verifier accepts a research-stage artifact with no
    signature, validating artifact_hash + reviewer fields. # TODO Phase 8.5
    will require Ed25519 for production/beta before public exposure."""
    art = _make_artifact()
    path = tmp_path / "housing.deposit.v1.json"
    path.write_text(json.dumps(art.model_dump(mode="json"), indent=2))

    result = verify_gate_artifact(path)
    assert result.passed is True, result.reasons
    # Phase 8.5 placeholder.
    assert art.signature is None
