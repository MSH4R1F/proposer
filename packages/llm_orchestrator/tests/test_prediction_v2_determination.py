"""Tests for the orchestrator-side Determination + amount_construct fields."""
import pytest

from llm_orchestrator.models.prediction_v2 import (
    Determination,
    IssueOutcome,
    IssuePrediction,
    IssueType,
    OutcomeType,
    PredictionResult,
)


def test_determination_enum_values():
    assert {d.value for d in Determination} == {
        "maladministration",
        "severe_maladministration",
        "service_failure",
        "reasonable_redress",
        "no_maladministration",
        "resolved_with_intervention",
        "outside_jurisdiction",
    }


def test_issue_prediction_carries_amount_construct():
    ip = IssuePrediction(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        outcome=IssueOutcome.TENANT_WINS,
        raw_confidence=0.7,
        predicted_amount=500.0,
        amount_construct="ordered_now",
    )
    assert ip.amount_construct == "ordered_now"


def test_issue_prediction_default_amount_construct_is_none():
    ip = IssuePrediction(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        outcome=IssueOutcome.TENANT_WINS,
        raw_confidence=0.7,
    )
    assert ip.amount_construct is None


def test_issue_prediction_invalid_amount_construct_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        IssuePrediction(
            issue_type=IssueType.REPAIRS_DISREPAIR,
            outcome=IssueOutcome.TENANT_WINS,
            raw_confidence=0.7,
            amount_construct="bogus_value",
        )


def test_issue_prediction_carries_predicted_determination():
    ip = IssuePrediction(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        outcome=IssueOutcome.TENANT_WINS,
        raw_confidence=0.7,
        predicted_determination=Determination.MALADMINISTRATION,
    )
    assert ip.predicted_determination == Determination.MALADMINISTRATION


def test_prediction_result_carries_predicted_determination():
    pr = PredictionResult(
        case_id="x",
        overall_outcome=OutcomeType.TENANT_WIN,
        overall_confidence=0.7,
        issue_predictions=[],
        predicted_determination=Determination.MALADMINISTRATION,
    )
    assert pr.predicted_determination == Determination.MALADMINISTRATION


def test_prediction_result_default_predicted_determination_is_none():
    pr = PredictionResult(
        case_id="x",
        overall_outcome=OutcomeType.TENANT_WIN,
        overall_confidence=0.7,
        issue_predictions=[],
    )
    assert pr.predicted_determination is None


class TestAssemblerAggregateDetermination:
    """Tests for output_assembler._aggregate_determination."""

    def test_returns_none_when_no_issue_has_determination(self):
        from llm_orchestrator.pipeline.output_assembler import _aggregate_determination
        ips = [
            IssuePrediction(
                issue_type=IssueType.REPAIRS_DISREPAIR,
                outcome=IssueOutcome.TENANT_WINS,
                raw_confidence=0.5,
            )
        ]
        assert _aggregate_determination(ips) is None

    def test_returns_modal_value(self):
        from llm_orchestrator.pipeline.output_assembler import _aggregate_determination
        ips = [
            IssuePrediction(
                issue_type=IssueType.REPAIRS_DISREPAIR,
                outcome=IssueOutcome.TENANT_WINS,
                raw_confidence=0.5,
                predicted_determination=Determination.MALADMINISTRATION,
            ),
            IssuePrediction(
                issue_type=IssueType.REPAIRS_DAMP_MOULD,
                outcome=IssueOutcome.TENANT_WINS,
                raw_confidence=0.5,
                predicted_determination=Determination.MALADMINISTRATION,
            ),
            IssuePrediction(
                issue_type=IssueType.COMPLAINT_HANDLING_FAILURE,
                outcome=IssueOutcome.TENANT_WINS,
                raw_confidence=0.5,
                predicted_determination=Determination.SERVICE_FAILURE,
            ),
        ]
        assert _aggregate_determination(ips) == Determination.MALADMINISTRATION

    def test_severity_tiebreak(self):
        from llm_orchestrator.pipeline.output_assembler import _aggregate_determination
        # One each of MALADMINISTRATION and SERVICE_FAILURE — severity-tiebreak
        # picks MALADMINISTRATION.
        ips = [
            IssuePrediction(
                issue_type=IssueType.REPAIRS_DISREPAIR,
                outcome=IssueOutcome.TENANT_WINS,
                raw_confidence=0.5,
                predicted_determination=Determination.SERVICE_FAILURE,
            ),
            IssuePrediction(
                issue_type=IssueType.REPAIRS_DAMP_MOULD,
                outcome=IssueOutcome.TENANT_WINS,
                raw_confidence=0.5,
                predicted_determination=Determination.MALADMINISTRATION,
            ),
        ]
        assert _aggregate_determination(ips) == Determination.MALADMINISTRATION


class TestIssuePredictorParserDeterminationField:
    """Tests that the JSON parser populates predicted_determination + amount_construct."""

    @staticmethod
    def _make_predictor():
        # IssuePredictor.__init__ stores the client but _parse_prediction_response
        # does not invoke any LLM, so a None client is fine for parser tests.
        from llm_orchestrator.pipeline.issue_predictor import IssuePredictor
        return IssuePredictor(llm_client=None)

    @staticmethod
    def _make_issue():
        from llm_orchestrator.models.prediction_v2 import IssueContext
        return IssueContext(
            issue_type=IssueType.REPAIRS_DISREPAIR,
            issue_description="test issue",
            data_completeness=0.8,
        )

    def test_parses_determination_and_construct_from_json(self):
        import json

        predictor = self._make_predictor()
        issue = self._make_issue()
        json_payload = {
            "outcome": "tenant_win",
            "raw_confidence": 0.7,
            "predicted_amount": 500,
            "amount_band": "251-600",
            "predicted_determination": "maladministration",
            "amount_construct": "ordered_now",
            "reasoning": "test",
        }
        parsed = predictor._parse_prediction_response(json.dumps(json_payload), issue)
        assert parsed.predicted_determination == Determination.MALADMINISTRATION
        assert parsed.amount_construct == "ordered_now"

    def test_parser_ignores_invalid_determination_value(self):
        import json

        predictor = self._make_predictor()
        issue = self._make_issue()
        json_payload = {
            "outcome": "tenant_win",
            "raw_confidence": 0.7,
            "predicted_determination": "not_a_real_class",
            "reasoning": "test",
        }
        parsed = predictor._parse_prediction_response(json.dumps(json_payload), issue)
        # Invalid value silently coerced to None — must NOT raise.
        assert parsed.predicted_determination is None

    def test_parser_ignores_invalid_amount_construct(self):
        import json

        predictor = self._make_predictor()
        issue = self._make_issue()
        json_payload = {
            "outcome": "tenant_win",
            "raw_confidence": 0.7,
            "amount_construct": "bogus_construct",
            "reasoning": "test",
        }
        parsed = predictor._parse_prediction_response(json.dumps(json_payload), issue)
        assert parsed.amount_construct is None

    def test_parser_omits_fields_when_absent(self):
        """Sanity: legacy / non-housing prompts that don't emit these fields parse cleanly."""
        import json

        predictor = self._make_predictor()
        issue = self._make_issue()
        json_payload = {
            "outcome": "tenant_win",
            "raw_confidence": 0.7,
            "reasoning": "test",
        }
        parsed = predictor._parse_prediction_response(json.dumps(json_payload), issue)
        assert parsed.predicted_determination is None
        assert parsed.amount_construct is None
