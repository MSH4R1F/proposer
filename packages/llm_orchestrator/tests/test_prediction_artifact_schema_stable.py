"""Cross-PR Contract C5: prediction artifact metadata schema must be stable.

Any PR that renames or removes a field in pipeline_metadata MUST update the
fixture artifact AND get explicit reviewer approval. The fixture is the
single source of truth for what the eval pipeline expects.

PR 4 fields are required today.
PR 5 will extend with retrieval_profile / comparator_pass_n_retrieved /
counterexample_pass_n_retrieved / abstention_recommended.
PR 6 will extend with evidence_path_results.

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md
      §17.6 Cross-PR Contract C5
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "stream_c_artifact_v1.json"

# Repo root: packages/llm_orchestrator/tests/<this file>.py → up 4 levels.
_REPO_ROOT = Path(__file__).resolve().parents[3]


# Keys that MUST appear in pipeline_metadata after PR 4 lands.
PR4_REQUIRED_KEYS = {
    "core_schema",
    "domain_pack",
    "factor_catalog_version",
    "graph_quality_score",
    "kg_used_for_prediction",
    "kg_fallback_mode",
    "kg_gate_failure_reasons",
}


def _load_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_fixture_artifact_loads():
    artifact = _load_fixture()
    assert "pipeline_metadata" in artifact


def test_pr4_metadata_keys_present():
    artifact = _load_fixture()
    meta = artifact["pipeline_metadata"]
    missing = PR4_REQUIRED_KEYS - set(meta)
    assert not missing, f"PR 4 keys missing from artifact: {missing}"


def test_kg_used_for_prediction_is_bool_or_none():
    artifact = _load_fixture()
    val = artifact["pipeline_metadata"]["kg_used_for_prediction"]
    assert val is None or isinstance(val, bool)


def test_kg_gate_failure_reasons_is_list_of_strings():
    artifact = _load_fixture()
    reasons = artifact["pipeline_metadata"]["kg_gate_failure_reasons"]
    assert isinstance(reasons, list)
    for r in reasons:
        assert isinstance(r, str)


def test_graph_quality_score_in_unit_interval_or_none():
    artifact = _load_fixture()
    score = artifact["pipeline_metadata"]["graph_quality_score"]
    assert score is None or 0.0 <= score <= 1.0


def test_core_schema_is_legal_core_v1():
    artifact = _load_fixture()
    assert artifact["pipeline_metadata"]["core_schema"] == "legal.core.v1"


def test_domain_pack_is_known_id():
    artifact = _load_fixture()
    pack = artifact["pipeline_metadata"]["domain_pack"]
    assert pack in {"housing.deposit.v1", "housing.repairs_social.v1"}


def test_factor_catalog_version_format():
    """Should be a 16-char hex SHA prefix (or None if pack lookup failed)."""
    artifact = _load_fixture()
    version = artifact["pipeline_metadata"]["factor_catalog_version"]
    if version is not None:
        assert isinstance(version, str)
        assert len(version) == 16
        assert all(c in "0123456789abcdef" for c in version.lower())


def test_factor_catalog_version_matches_live_yaml():
    """Catches accidental factors.yaml edits without fixture regeneration.

    If factors.yaml content drifts from the fixture's recorded hash, this
    test fails — forcing the author to regenerate the fixture (and explain
    why the ontology changed) rather than letting the contract silently
    decay.
    """
    artifact = _load_fixture()
    pack_id = artifact["pipeline_metadata"]["domain_pack"]
    family, sub_family, _version = pack_id.split(".")
    yaml_path = (
        _REPO_ROOT
        / "packages"
        / "domain_packs"
        / family
        / sub_family
        / "factors.yaml"
    )
    live_hash = hashlib.sha256(yaml_path.read_bytes()).hexdigest()[:16]
    fixture_hash = artifact["pipeline_metadata"]["factor_catalog_version"]
    assert fixture_hash == live_hash, (
        f"factor_catalog_version drift: fixture={fixture_hash} "
        f"live={live_hash}. Either regenerate the fixture (factors.yaml "
        f"content changed) or revert the factors.yaml edit if unintended."
    )


@pytest.mark.skip(reason="Enabled by Stream C PR 5 — extends with retrieval_profile, comparator/counterexample counts, abstention_recommended.")
def test_pr5_metadata_keys_present():
    """When PR 5 lands, regenerate fixtures/stream_c_artifact_v1.json with
    the PR-5 metadata fields populated (or commit a separate
    stream_c_artifact_v2.json) and remove the skip marker."""
    pr5_required = PR4_REQUIRED_KEYS | {
        "retrieval_profile",
        "comparator_pass_n_retrieved",
        "counterexample_pass_n_retrieved",
        "abstention_recommended",
    }
    artifact = _load_fixture()
    meta = artifact["pipeline_metadata"]
    missing = pr5_required - set(meta)
    assert not missing, f"PR 5 keys missing from artifact: {missing}"


@pytest.mark.skip(reason="Enabled by Stream C PR 6 — extends with evidence_path_results.")
def test_pr6_metadata_keys_present():
    """When PR 6 lands, regenerate the fixture with evidence_path_results
    populated and remove the skip marker."""
    pr6_required = PR4_REQUIRED_KEYS | {
        "retrieval_profile",
        "comparator_pass_n_retrieved",
        "counterexample_pass_n_retrieved",
        "abstention_recommended",
        "evidence_path_results",
    }
    artifact = _load_fixture()
    meta = artifact["pipeline_metadata"]
    missing = pr6_required - set(meta)
    assert not missing, f"PR 6 keys missing from artifact: {missing}"
