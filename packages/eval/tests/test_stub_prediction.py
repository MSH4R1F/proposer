"""Tests for eval._stub_prediction.make_stub_prediction.

The stub bypasses the LLM pipeline entirely and produces a structurally
valid PredictionResult per (CaseFile, PredictionMode). It exists so the
live-runner --dry-run path can exercise the full GoldCase → CaseFile →
PredictionResult → adapter → eval.ablate chain in CI without API keys.

It does NOT need to be accurate — it needs to be:
  - deterministic per (case_id, mode) — same input → same output
  - mode-differentiating — hybrid produces different numbers from llm_only
  - schema-valid — PredictionResult passes its own validators
"""
from __future__ import annotations

import pytest


def _orch_imports():
    from llm_orchestrator.models.case_file import CaseFile, DisputeIssue, PartyRole
    from llm_orchestrator.models.prediction_v2 import PredictionMode, PredictionResult

    return CaseFile, DisputeIssue, PartyRole, PredictionMode, PredictionResult


def _build_minimal_case_file(case_id: str = "case-001"):
    CaseFile, DisputeIssue, PartyRole, _, _ = _orch_imports()
    return CaseFile(
        case_id=case_id,
        user_role=PartyRole.TENANT,
        issues=[DisputeIssue.CLEANING, DisputeIssue.DAMAGE],
        dispute_amount=500.0,
        intake_complete=True,
        completeness_score=1.0,
    )


class TestSchemaValidity:
    def test_returns_prediction_result_instance(self):
        from eval._stub_prediction import make_stub_prediction

        _, _, _, PredictionMode, PredictionResult = _orch_imports()
        out = make_stub_prediction(_build_minimal_case_file(), PredictionMode.HYBRID)
        assert isinstance(out, PredictionResult)

    def test_case_id_carries_across(self):
        from eval._stub_prediction import make_stub_prediction

        _, _, _, PredictionMode, _ = _orch_imports()
        cf = _build_minimal_case_file(case_id="HOU-2024-007")
        out = make_stub_prediction(cf, PredictionMode.HYBRID)
        assert out.case_id == "HOU-2024-007"

    def test_overall_confidence_in_unit_interval(self):
        from eval._stub_prediction import make_stub_prediction

        _, _, _, PredictionMode, _ = _orch_imports()
        for mode in PredictionMode:
            out = make_stub_prediction(_build_minimal_case_file(), mode)
            assert 0.0 <= out.overall_confidence <= 1.0

    def test_one_issue_prediction_per_case_file_issue(self):
        from eval._stub_prediction import make_stub_prediction

        _, _, _, PredictionMode, _ = _orch_imports()
        cf = _build_minimal_case_file()  # 2 issues
        out = make_stub_prediction(cf, PredictionMode.HYBRID)
        assert len(out.issue_predictions) == 2

    def test_pipeline_metadata_records_mode(self):
        from eval._stub_prediction import make_stub_prediction

        _, _, _, PredictionMode, _ = _orch_imports()
        out = make_stub_prediction(_build_minimal_case_file(), PredictionMode.RAG_ONLY)
        # PipelineMetadata.mode is a string carrying PredictionMode.value.
        assert out.pipeline_metadata is not None
        assert out.pipeline_metadata.mode == "rag_only"


class TestDeterminism:
    def test_same_input_yields_identical_overall_confidence(self):
        from eval._stub_prediction import make_stub_prediction

        _, _, _, PredictionMode, _ = _orch_imports()
        cf = _build_minimal_case_file()
        a = make_stub_prediction(cf, PredictionMode.HYBRID)
        b = make_stub_prediction(cf, PredictionMode.HYBRID)
        assert a.overall_confidence == b.overall_confidence

    def test_same_input_yields_identical_per_issue_outputs(self):
        from eval._stub_prediction import make_stub_prediction

        _, _, _, PredictionMode, _ = _orch_imports()
        cf = _build_minimal_case_file()
        a = make_stub_prediction(cf, PredictionMode.HYBRID)
        b = make_stub_prediction(cf, PredictionMode.HYBRID)
        confidences_a = [i.raw_confidence for i in a.issue_predictions]
        confidences_b = [i.raw_confidence for i in b.issue_predictions]
        assert confidences_a == confidences_b


class TestModeDifferentiation:
    """The runner needs different modes to produce different outputs so the
    comparison report tells a story. Hybrid most confident; LLM_ONLY least."""

    def test_hybrid_more_confident_than_llm_only(self):
        from eval._stub_prediction import make_stub_prediction

        _, _, _, PredictionMode, _ = _orch_imports()
        cf = _build_minimal_case_file()
        hybrid = make_stub_prediction(cf, PredictionMode.HYBRID)
        llm_only = make_stub_prediction(cf, PredictionMode.LLM_ONLY)
        assert hybrid.overall_confidence > llm_only.overall_confidence

    def test_modes_produce_different_overall_confidence(self):
        from eval._stub_prediction import make_stub_prediction

        _, _, _, PredictionMode, _ = _orch_imports()
        cf = _build_minimal_case_file()
        confidences = {
            mode.value: make_stub_prediction(cf, mode).overall_confidence
            for mode in PredictionMode
        }
        # All four values are distinct
        assert len(set(confidences.values())) == 4


class TestEdgeCases:
    def test_case_file_with_no_issues_yields_empty_issue_predictions(self):
        from eval._stub_prediction import make_stub_prediction

        CaseFile, _, PartyRole, PredictionMode, _ = _orch_imports()
        cf = CaseFile(case_id="bare", user_role=PartyRole.TENANT, issues=[])
        out = make_stub_prediction(cf, PredictionMode.HYBRID)
        assert out.issue_predictions == []
