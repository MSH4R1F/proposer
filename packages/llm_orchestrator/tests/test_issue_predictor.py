import json

from ..clients.base import BaseLLMClient
from ..models.prediction_v2 import IssueContext, IssueOutcome, IssueType
from ..pipeline.issue_predictor import IssuePredictor


class _DummyLLM(BaseLLMClient):
    async def generate(self, messages, system_prompt, max_tokens=4096, temperature=0.7):
        return "{}"

    async def generate_structured(
        self,
        messages,
        system_prompt,
        response_model,
        max_tokens=4096,
    ):
        raise NotImplementedError

    def get_stats(self):
        return {}

    def reset_stats(self):
        return None


def test_parse_prediction_response_recovers_json_in_wrapped_text() -> None:
    predictor = IssuePredictor(_DummyLLM())
    issue = IssueContext(
        issue_type=IssueType.CLEANING,
        issue_description="cleaning deduction",
        data_completeness=0.8,
    )

    payload = {
        "prediction": {
            "outcome": "tenant_wins",
            "raw_confidence": 0.78,
            "reasoning": "Based on similar cases, tenant likely succeeds.",
            "evidence_strength": "strong",
            "key_factors": ["professional cleaning receipt"],
        }
    }
    response = "Model analysis follows:\n```json\n" + json.dumps(payload) + "\n```"

    parsed = predictor._parse_prediction_response(response, issue)

    assert parsed.outcome == IssueOutcome.TENANT_WINS
    assert parsed.raw_confidence == 0.78
    assert parsed.evidence_strength.value == "strong"


def test_parse_prediction_response_falls_back_to_uncertain_on_invalid_payload() -> None:
    predictor = IssuePredictor(_DummyLLM())
    issue = IssueContext(
        issue_type=IssueType.DAMAGE,
        issue_description="carpet damage",
        data_completeness=0.6,
    )

    parsed = predictor._parse_prediction_response("no valid json here", issue)

    assert parsed.outcome == IssueOutcome.UNCERTAIN
    assert parsed.data_completeness_impact == "parse_error"
    assert "Unable to parse" in parsed.reasoning
