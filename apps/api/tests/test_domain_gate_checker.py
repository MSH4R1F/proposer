"""SHA-20 Phase 8: tests for ``DomainGateChecker``.

These exercise the integration between ``apps.api.src.domain_runtime``'s
``DomainGateChecker`` and ``packages.eval.gates``. The checker maps the
verifier's structured outcome onto :class:`DomainGateStatus`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from apps.api.src.domain_runtime import (
    DomainGateChecker,
    DomainGateStatus,
)
from domain_core import get_domain_spec
from eval.gates import (
    DomainGateArtifact,
    build_artifact,
    compute_artifact_hash,
)


def _write_artifact(path: Path, art: DomainGateArtifact) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(art.model_dump(mode="json"), indent=2))


def _build_artifact_for_research(domain_id: str = "housing.deposit.v1", **overrides):
    base = dict(
        domain_id=domain_id,
        stage_requested="research",
        git_sha="0" * 40,
        corpus_version="v1",
        gold_set_path="data/gold_standard/test_v1.jsonl",
        n_cases=50,
        metrics={
            "accuracy": 0.85,
            "brier_score_max": 0.15,
            "hallucination_rate": 0.01,
            "citation_validity": 0.99,
            "abstention_precision": 0.85,
        },
        prompt_pack_hash="a" * 64,
        ontology_hash="b" * 64,
        domain_spec_hash="c" * 64,
        verifier_hash="d" * 64,
        reviewer_roles=["housing_legal"],
        approved_by=["reviewer@example.com"],
        approved_at=datetime.now(timezone.utc).isoformat(),
        notes=None,
    )
    base.update(overrides)
    return build_artifact(**base)


class TestDomainGateChecker:
    def test_missing_file_returns_gate_missing(self, tmp_path):
        spec = get_domain_spec("housing.deposit.v1")
        checker = DomainGateChecker(gate_dir=tmp_path)
        result = checker.check(spec, requested_mode="production")
        assert result.status == DomainGateStatus.GATE_MISSING
        assert result.artifact_id is None
        assert result.artifact_hash is None
        assert any("no gate artifact" in r for r in result.reasons)

    def test_corrupt_json_returns_stale(self, tmp_path):
        spec = get_domain_spec("housing.deposit.v1")
        artifact_path = tmp_path / "housing.deposit.v1.json"
        artifact_path.write_text("{not: valid json")
        checker = DomainGateChecker(gate_dir=tmp_path)
        result = checker.check(spec, requested_mode="production")
        assert result.status == DomainGateStatus.GATE_STALE

    def test_stage_mismatch_returns_stale(self, tmp_path):
        spec = get_domain_spec("housing.deposit.v1")
        # Build a research artifact, ask for production.
        art = _build_artifact_for_research(domain_id="housing.deposit.v1")
        _write_artifact(tmp_path / "housing.deposit.v1.json", art)
        checker = DomainGateChecker(gate_dir=tmp_path)
        result = checker.check(spec, requested_mode="production")
        assert result.status == DomainGateStatus.GATE_STALE
        assert any(
            "stage_requested" in reason for reason in result.reasons
        )

    def test_research_artifact_for_research_passes(self, tmp_path, monkeypatch):
        """A research artifact pointing at an existing gold file with
        n_cases >= min_cases should verify cleanly."""
        spec = get_domain_spec("housing.deposit.v1")
        # Provide a gold file the verifier can stat.
        gold = tmp_path / "fake_gold.jsonl"
        gold.write_text("\n".join("{}" for _ in range(60)))

        art = _build_artifact_for_research(
            domain_id="housing.deposit.v1",
            gold_set_path=str(gold),
            n_cases=60,
        )
        _write_artifact(tmp_path / "housing.deposit.v1.json", art)
        checker = DomainGateChecker(gate_dir=tmp_path)
        result = checker.check(spec, requested_mode="research")
        assert result.status == DomainGateStatus.ENABLED
        assert result.artifact_id == "housing.deposit.v1"
        assert result.artifact_hash == art.artifact_hash

    def test_below_threshold_metrics_return_stale(self, tmp_path):
        """If artifact metrics violate the spec's eval_gate thresholds,
        the checker reports GATE_STALE."""
        spec = get_domain_spec("housing.deposit.v1")
        gold = tmp_path / "fake_gold.jsonl"
        gold.write_text("\n".join("{}" for _ in range(60)))

        # The deposit YAML demands accuracy>=0.70; force a low value.
        art = _build_artifact_for_research(
            domain_id="housing.deposit.v1",
            gold_set_path=str(gold),
            n_cases=60,
            metrics={
                "accuracy": 0.50,  # below 0.70 floor
                "brier_score_max": 0.15,
                "hallucination_rate": 0.01,
                "citation_validity": 0.99,
                "abstention_precision": 0.85,
            },
        )
        _write_artifact(tmp_path / "housing.deposit.v1.json", art)
        checker = DomainGateChecker(gate_dir=tmp_path)
        result = checker.check(spec, requested_mode="research")
        assert result.status == DomainGateStatus.GATE_STALE
        assert any("accuracy" in r for r in result.reasons)

    def test_audit_d2_deposit_production_fail_closed(self, tmp_path):
        """Audit D2: deposit production gate must fail-closed when the
        gold set is missing on disk OR has < 50 cases.

        We synthesise a production-stage artifact pointing at a gold file
        that does not exist; verifier must reject it even though all
        other fields look fine.
        """
        spec = get_domain_spec("housing.deposit.v1")
        # A fake (non-existent) gold path. Verifier should fail-close.
        bad_gold = tmp_path / "ghost.jsonl"
        art_payload = dict(
            domain_id="housing.deposit.v1",
            stage_requested="production",
            git_sha="0" * 40,
            corpus_version="v1",
            gold_set_path=str(bad_gold),
            n_cases=60,
            metrics={
                "accuracy": 0.85,
                "brier_score_max": 0.15,
                "hallucination_rate": 0.01,
                "citation_validity": 0.99,
                "abstention_precision": 0.85,
            },
            prompt_pack_hash="a" * 64,
            ontology_hash="b" * 64,
            domain_spec_hash="c" * 64,
            verifier_hash="d" * 64,
            reviewer_roles=["housing_legal"],
            approved_by=["reviewer@example.com"],
            approved_at=datetime.now(timezone.utc).isoformat(),
            notes=None,
        )
        art = build_artifact(**art_payload)
        _write_artifact(tmp_path / "housing.deposit.v1.json", art)
        checker = DomainGateChecker(gate_dir=tmp_path)
        result = checker.check(spec, requested_mode="production")
        assert result.status == DomainGateStatus.GATE_STALE
        # The audit-D2 reason text is surfaced.
        assert any("audit D2" in r or "gold_set" in r for r in result.reasons)
