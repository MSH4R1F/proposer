"""SHA-20 Phase 7 — tests for ``packages/eval/gates.py``.

Covers:

* :class:`DomainGateArtifact` field requirements + optional signature.
* :func:`compute_artifact_hash` canonical-JSON stability.
* :func:`verify_gate_artifact` outcomes (missing file, stale git_sha,
  below-threshold metrics, all-pass).
* :func:`load_gate_artifact` returns None on missing.
* ``housing.deposit.v1`` audit D2 fail-closed (gold file missing OR
  ``n_cases < 50``).
* PII negative set is 50 entries with the required identifier markers.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.gates import (
    DomainGateArtifact,
    GateThresholds,
    build_artifact,
    compute_artifact_hash,
    load_gate_artifact,
    verify_gate_artifact,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
PII_SET_PATH = REPO_ROOT / "data/eval/negative_sets/pii_leakage_v1.jsonl"


def _base_artifact_payload(**overrides) -> dict:
    p = {
        "domain_id": "test.domain.v1",
        "stage_requested": "research",
        "git_sha": "0" * 40,
        "corpus_version": "v1",
        "gold_set_path": "data/gold_standard/test_v1.jsonl",
        "n_cases": 50,
        "metrics": {
            "accuracy": 0.85,
            "brier_score_max": 0.15,
            "hallucination_rate": 0.01,
            "citation_validity": 0.99,
            "abstention_precision": 0.85,
        },
        "prompt_pack_hash": "a" * 64,
        "ontology_hash": "b" * 64,
        "domain_spec_hash": "c" * 64,
        "verifier_hash": "d" * 64,
        "reviewer_roles": ["housing_legal"],
        "approved_by": ["reviewer@example.com"],
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "notes": None,
    }
    p.update(overrides)
    return p


def _artifact(**overrides) -> DomainGateArtifact:
    payload = _base_artifact_payload(**overrides)
    artifact_hash = compute_artifact_hash(payload)
    return DomainGateArtifact(**payload, artifact_hash=artifact_hash)


def _write_artifact(path: Path, art: DomainGateArtifact) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(art.model_dump(mode="json"), indent=2))


# ---------------------------------------------------------------------------
# DomainGateArtifact model
# ---------------------------------------------------------------------------


class TestDomainGateArtifactModel:
    def test_required_fields_enforced(self):
        # Missing every field — pydantic should reject.
        with pytest.raises(ValidationError):
            DomainGateArtifact()  # type: ignore[call-arg]

    def test_signature_is_optional(self):
        art = _artifact()
        assert art.signature is None
        assert art.signing_key_id is None

    def test_signature_field_round_trips(self):
        art = _artifact()
        sig_payload = {
            **art.model_dump(mode="json"),
            "signature": "abcd",
            "signing_key_id": "key-1",
        }
        signed = DomainGateArtifact.model_validate(sig_payload)
        assert signed.signature == "abcd"
        assert signed.signing_key_id == "key-1"

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            DomainGateArtifact.model_validate(
                {**_base_artifact_payload(), "artifact_hash": "x" * 64, "rogue": 1}
            )

    def test_invalid_git_sha_rejected(self):
        with pytest.raises(ValidationError):
            DomainGateArtifact.model_validate(
                {
                    **_base_artifact_payload(git_sha="not-hex"),
                    "artifact_hash": "x" * 64,
                }
            )


# ---------------------------------------------------------------------------
# compute_artifact_hash — canonical-JSON stability
# ---------------------------------------------------------------------------


class TestComputeArtifactHash:
    # Use a frozen approved_at so hashes are reproducible across calls.
    _FROZEN_TS = "2026-05-01T00:00:00+00:00"

    def test_same_payload_same_hash(self):
        p1 = _base_artifact_payload(approved_at=self._FROZEN_TS)
        p2 = _base_artifact_payload(approved_at=self._FROZEN_TS)
        assert compute_artifact_hash(p1) == compute_artifact_hash(p2)

    def test_key_reorder_does_not_change_hash(self):
        p = _base_artifact_payload(approved_at=self._FROZEN_TS)
        # Build a reordered copy by re-inserting keys in reverse order.
        reordered = {k: p[k] for k in reversed(list(p.keys()))}
        assert compute_artifact_hash(p) == compute_artifact_hash(reordered)

    def test_nested_metric_reorder_does_not_change_hash(self):
        p1 = _base_artifact_payload(
            approved_at=self._FROZEN_TS,
            metrics={"accuracy": 0.85, "brier_score_max": 0.15},
        )
        p2 = _base_artifact_payload(
            approved_at=self._FROZEN_TS,
            metrics={"brier_score_max": 0.15, "accuracy": 0.85},
        )
        assert compute_artifact_hash(p1) == compute_artifact_hash(p2)

    def test_value_change_changes_hash(self):
        p1 = _base_artifact_payload(approved_at=self._FROZEN_TS)
        p2 = _base_artifact_payload(approved_at=self._FROZEN_TS, n_cases=999)
        assert compute_artifact_hash(p1) != compute_artifact_hash(p2)

    def test_hash_is_64_hex(self):
        h = compute_artifact_hash(_base_artifact_payload(approved_at=self._FROZEN_TS))
        assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# verify_gate_artifact
# ---------------------------------------------------------------------------


class TestVerifyGateArtifact:
    def test_missing_file_fails_with_structured_reason(self, tmp_path):
        result = verify_gate_artifact(tmp_path / "does_not_exist.json")
        assert result.passed is False
        assert any("missing" in r for r in result.reasons)

    def test_malformed_json_fails_closed_without_crashing(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{not valid json")

        result = verify_gate_artifact(path)

        assert result.passed is False
        assert result.domain_id == "<unknown>"
        assert any("failed to parse artifact" in r for r in result.reasons)

    def test_all_pass_research_artifact_succeeds(self, tmp_path):
        # research stage: no reviewer requirement, signature optional.
        art = _artifact(stage_requested="research")
        path = tmp_path / "art.json"
        _write_artifact(path, art)
        result = verify_gate_artifact(path)
        assert result.passed is True, result.reasons

    def test_below_threshold_metrics_fail(self, tmp_path):
        art = _artifact(
            stage_requested="research",
            metrics={
                "accuracy": 0.40,
                "hallucination_rate": 0.20,
                "citation_validity": 0.50,
                "abstention_precision": 0.30,
            },
        )
        _write_artifact(tmp_path / "art.json", art)
        thresholds = GateThresholds(
            min_cases=50,
            required_metrics={"accuracy": 0.70},
            max_hallucination_rate=0.02,
            min_citation_validity=0.98,
            min_abstention_precision=0.80,
        )
        result = verify_gate_artifact(
            tmp_path / "art.json", thresholds=thresholds
        )
        assert result.passed is False
        # Each control class should have flagged at least one reason.
        joined = " ".join(result.reasons)
        assert "accuracy" in joined
        assert "hallucination_rate" in joined
        assert "citation_validity" in joined
        assert "abstention_precision" in joined

    def test_min_cases_below_threshold_fails(self, tmp_path):
        art = _artifact(stage_requested="research", n_cases=10)
        _write_artifact(tmp_path / "art.json", art)
        thresholds = GateThresholds(min_cases=50)
        result = verify_gate_artifact(
            tmp_path / "art.json", thresholds=thresholds
        )
        assert result.passed is False
        assert any("n_cases" in r for r in result.reasons)

    def test_stale_artifact_hash_fails(self, tmp_path):
        # Tamper with stored artifact_hash to simulate a stale/modified file.
        art = _artifact()
        path = tmp_path / "art.json"
        _write_artifact(path, art)
        data = json.loads(path.read_text())
        data["artifact_hash"] = "0" * 64
        path.write_text(json.dumps(data))
        result = verify_gate_artifact(path)
        assert result.passed is False
        assert any("artifact_hash mismatch" in r for r in result.reasons)

    def test_production_requires_reviewer_roles_and_approved_by(self, tmp_path):
        art = _artifact(
            stage_requested="production",
            reviewer_roles=[],
            approved_by=[],
        )
        _write_artifact(tmp_path / "art.json", art)
        result = verify_gate_artifact(tmp_path / "art.json")
        assert result.passed is False
        joined = " ".join(result.reasons)
        assert "reviewer_roles" in joined
        assert "approved_by" in joined


# ---------------------------------------------------------------------------
# load_gate_artifact
# ---------------------------------------------------------------------------


class TestLoadGateArtifact:
    def test_missing_returns_none(self, tmp_path):
        assert load_gate_artifact("nope.v1", gate_dir=tmp_path) is None

    def test_loads_when_present(self, tmp_path):
        art = _artifact(domain_id="present.v1")
        _write_artifact(tmp_path / "present.v1.json", art)
        loaded = load_gate_artifact("present.v1", gate_dir=tmp_path)
        assert loaded is not None
        assert loaded.domain_id == "present.v1"


# ---------------------------------------------------------------------------
# Audit D2 fail-closed for housing.deposit.v1 production
# ---------------------------------------------------------------------------


class TestHousingDepositV1ProductionFailsClosed:
    def test_refuses_when_gold_set_missing(self, tmp_path):
        # Gold set path under tmp_path will not exist.
        art = _artifact(
            domain_id="housing.deposit.v1",
            stage_requested="production",
            gold_set_path=str(tmp_path / "missing_gold.jsonl"),
            n_cases=50,
        )
        _write_artifact(tmp_path / "art.json", art)
        result = verify_gate_artifact(tmp_path / "art.json")
        assert result.passed is False
        assert any("audit D2" in r for r in result.reasons)

    def test_refuses_when_n_cases_below_50(self, tmp_path):
        gold_path = tmp_path / "exists.jsonl"
        gold_path.write_text("")  # exists but n_cases is the dispositive field
        art = _artifact(
            domain_id="housing.deposit.v1",
            stage_requested="production",
            gold_set_path=str(gold_path),
            n_cases=10,
        )
        _write_artifact(tmp_path / "art.json", art)
        result = verify_gate_artifact(tmp_path / "art.json")
        assert result.passed is False
        assert any("audit D2" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# PII negative set: 50 entries with NI/payroll/health markers
# ---------------------------------------------------------------------------


class TestPiiLeakageNegativeSet:
    def test_pii_set_has_50_entries(self):
        assert PII_SET_PATH.exists(), f"missing {PII_SET_PATH}"
        rows = [
            json.loads(line)
            for line in PII_SET_PATH.read_text().splitlines()
            if line.strip()
        ]
        assert len(rows) == 50

    def test_every_pii_row_has_required_identifier_markers(self):
        rows = [
            json.loads(line)
            for line in PII_SET_PATH.read_text().splitlines()
            if line.strip()
        ]
        # The spec requires at least one of {ni_number, payroll_id, health_data}.
        required = {"ni_number", "payroll_id", "health_data"}
        for row in rows:
            redactions = row.get("expected_redactions", [])
            facts = row.get("facts", "")
            # We accept either bracketed marker form ("[ni_number]") in
            # expected_redactions, or the literal identifier appearing in
            # facts (e.g. "NI: QQ000001D" implies ni_number coverage).
            redaction_keys = {
                r.strip("[]").lower() for r in redactions if isinstance(r, str)
            }
            facts_lower = facts.lower()
            has_marker = bool(required & redaction_keys) or any(
                k in facts_lower for k in ("ni:", "payroll", "disability")
            )
            assert has_marker, (
                f"row {row.get('case_id')!r} missing required PII markers: "
                f"redactions={sorted(redaction_keys)}"
            )

    def test_every_pii_row_is_marked_as_pii_negative(self):
        rows = [
            json.loads(line)
            for line in PII_SET_PATH.read_text().splitlines()
            if line.strip()
        ]
        for row in rows:
            assert row.get("negative_kind") == "pii_leakage"


# ---------------------------------------------------------------------------
# build_artifact helper
# ---------------------------------------------------------------------------


class TestBuildArtifact:
    def test_build_artifact_stamps_hash(self):
        art = build_artifact(
            domain_id="x.v1",
            stage_requested="research",
            git_sha="0" * 40,
            corpus_version="v1",
            gold_set_path="data/gold_standard/x.jsonl",
            n_cases=10,
            metrics={"accuracy": 0.9},
            prompt_pack_hash="a" * 64,
            ontology_hash="b" * 64,
            domain_spec_hash="c" * 64,
            verifier_hash="d" * 64,
        )
        assert art.artifact_hash == compute_artifact_hash(art.hashable_payload())
