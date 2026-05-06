import json
from types import SimpleNamespace

import pytest

from ..clients.base import BaseLLMClient
from ..models.prediction_v2 import EvidenceStrength, IssueContext, IssueOutcome, IssueType
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


class _CaptureLLM(_DummyLLM):
    def __init__(self):
        self.calls = []

    async def generate(self, messages, system_prompt, max_tokens=4096, temperature=0.7):
        self.calls.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        return (
            '{"outcome":"tenant_wins","raw_confidence":0.7,'
            '"reasoning":"Likely maladministration on similar Ombudsman facts.",'
            '"evidence_strength":"moderate","data_completeness_impact":"ok"}'
        )


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


def test_parse_prediction_response_keeps_missing_amount_unknown() -> None:
    predictor = IssuePredictor(_DummyLLM())
    issue = IssueContext(
        issue_type=IssueType.CLEANING,
        issue_description="cleaning deduction",
        claimed_amount=999.0,
        data_completeness=0.8,
    )

    parsed = predictor._parse_prediction_response(
        json.dumps(
            {
                "outcome": "tenant_wins",
                "raw_confidence": 0.78,
                "reasoning": "Tenant likely succeeds, but amount is not estimated.",
                "evidence_strength": "strong",
            }
        ),
        issue,
    )

    assert parsed.predicted_amount is None


def test_parse_prediction_response_preserves_explicit_numeric_amounts() -> None:
    predictor = IssuePredictor(_DummyLLM())
    issue = IssueContext(
        issue_type=IssueType.CLEANING,
        issue_description="cleaning deduction",
        claimed_amount=999.0,
        data_completeness=0.8,
    )

    parsed = predictor._parse_prediction_response(
        json.dumps(
            {
                "outcome": "tenant_wins",
                "raw_confidence": 0.78,
                "predicted_amount": 0,
                "reasoning": "Tenant succeeds, with no monetary recovery.",
                "evidence_strength": "strong",
            }
        ),
        issue,
    )

    assert parsed.predicted_amount == 0.0


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


def test_format_party_position_uses_narrative_when_no_structured_claim() -> None:
    text = IssuePredictor._format_party_position(
        claim=None,
        narrative="Tenant rented a 1-bedroom flat in London for 14 months and disputes the cleaning deduction.",
    )

    assert "Party narrative (no structured claim filed)" in text
    assert "1-bedroom flat" in text


def test_format_party_position_returns_not_provided_when_both_missing() -> None:
    assert IssuePredictor._format_party_position(claim=None, narrative=None) == "Not provided"
    assert IssuePredictor._format_party_position(claim=None, narrative="   ") == "Not provided"


def test_format_party_position_combines_claim_and_narrative() -> None:
    class _Claim:
        description = "Cleaning charge of £250 disputed"
        claimed_amount = 250.0

    text = IssuePredictor._format_party_position(
        claim=_Claim(),
        narrative="Tenant left the property professionally cleaned with receipts.",
    )

    assert "Cleaning charge of £250 disputed" in text
    assert "Amount claimed: £250.00" in text
    assert "Narrative:" in text
    assert "professionally cleaned" in text


@pytest.mark.asyncio
async def test_repairs_no_rag_prompt_uses_ombudsman_framing() -> None:
    from llm_orchestrator.prompts.packs import get_prompt_pack

    llm = _CaptureLLM()
    case_file = SimpleNamespace(
        metadata={
            "domain_id": "housing.repairs_social.v1",
            "matter_type": "repairs_damp_mould",
        },
        tenancy=SimpleNamespace(
            deposit_amount=None,
            start_date=None,
            end_date=None,
            tenancy_type=None,
        ),
        property=SimpleNamespace(region="london", postcode=None),
        tenant_narrative="Resident reported damp and mould for months.",
        landlord_narrative=None,
    )
    predictor = IssuePredictor(
        llm,
        case_file=case_file,
        prompt_pack=get_prompt_pack("housing.repairs_social.v1"),
    )
    issue = IssueContext(
        issue_type=IssueType.REPAIRS_DAMP_MOULD,
        issue_description="damp and mould repairs",
        data_completeness=0.8,
    )

    await predictor.predict_no_rag([issue], prompt_mode="llm_only")

    prompt = llm.calls[0]["messages"][0]["content"]
    system_prompt = llm.calls[0]["system_prompt"]
    assert "Housing Ombudsman Service" in prompt
    assert "Deposit Amount" not in prompt
    assert "repairs_damp_mould" in prompt
    assert "Leave supporting_cases empty" in prompt
    assert "Do not include comparator awards" in prompt
    assert "Resident reported damp and mould for months." in prompt
    assert "cited comparator award amounts" not in prompt
    assert "cited determination" not in prompt
    assert "IRAC_JSON_SCHEMA" not in system_prompt
    assert "Output your prediction as a single JSON object" in system_prompt
    assert "Do NOT invent Ombudsman determination citations" in system_prompt
    assert "tenant_wins" in system_prompt
    assert "supporting_cases MUST be an empty list" in system_prompt
    assert "case citations in format" not in system_prompt
    assert "Include at least 1 supporting case citation" not in system_prompt


@pytest.mark.asyncio
async def test_repairs_no_rag_empty_context_short_circuits_uncertain() -> None:
    from llm_orchestrator.prompts.packs import get_prompt_pack

    llm = _CaptureLLM()
    case_file = SimpleNamespace(
        metadata={
            "domain_id": "housing.repairs_social.v1",
            "matter_type": "repairs_damp_mould",
        },
        tenancy=SimpleNamespace(
            deposit_amount=None,
            start_date=None,
            end_date=None,
            tenancy_type=None,
        ),
        property=SimpleNamespace(region="london", postcode=None),
        tenant_narrative=None,
        landlord_narrative=None,
        events=[],
    )
    predictor = IssuePredictor(
        llm,
        case_file=case_file,
        prompt_pack=get_prompt_pack("housing.repairs_social.v1"),
    )
    issue = IssueContext(
        issue_type=IssueType.REPAIRS_DAMP_MOULD,
        issue_description="damp and mould repairs",
        supporting_evidence=[
            {
                "description": (
                    "Housing Ombudsman determination records the resident's "
                    "complaint history, repair reports, and landlord response."
                ),
                "confidence": 1.0,
            }
        ],
        data_completeness=0.23,
    )

    predictions = await predictor.predict_no_rag([issue], prompt_mode="kg_only")

    assert llm.calls == []
    assert predictions[0].outcome == IssueOutcome.UNCERTAIN
    assert predictions[0].raw_confidence == 0.2
    assert predictions[0].predicted_amount is None
    assert predictions[0].amount_band is None
    assert predictions[0].supporting_cases == []
    assert predictions[0].evidence_strength == EvidenceStrength.INSUFFICIENT
    assert "Empty no-RAG context" in predictions[0].data_completeness_impact


def test_parse_prediction_response_maps_ombudsman_outcome_language() -> None:
    predictor = IssuePredictor(_DummyLLM())
    issue = IssueContext(
        issue_type=IssueType.REPAIRS_DAMP_MOULD,
        issue_description="damp and mould repairs",
        data_completeness=0.8,
    )

    service_failure = predictor._parse_prediction_response(
        json.dumps(
            {
                "outcome": "service failure",
                "raw_confidence": 0.68,
                "reasoning": "Likely service failure.",
                "evidence_strength": "moderate",
            }
        ),
        issue,
    )
    no_maladministration = predictor._parse_prediction_response(
        json.dumps(
            {
                "outcome": "no maladministration",
                "raw_confidence": 0.61,
                "reasoning": "Likely no maladministration.",
                "evidence_strength": "moderate",
            }
        ),
        issue,
    )
    partial_maladministration = predictor._parse_prediction_response(
        json.dumps(
            {
                "outcome": "partial maladministration",
                "raw_confidence": 0.58,
                "reasoning": "Resident likely succeeds on at least one complaint head.",
                "evidence_strength": "moderate",
            }
        ),
        issue,
    )
    mixed = predictor._parse_prediction_response(
        json.dumps(
            {
                "outcome": "mixed findings",
                "raw_confidence": 0.58,
                "reasoning": "Balanced findings.",
                "evidence_strength": "moderate",
            }
        ),
        issue,
    )

    assert service_failure.outcome == IssueOutcome.TENANT_WINS
    assert no_maladministration.outcome == IssueOutcome.LANDLORD_WINS
    assert partial_maladministration.outcome == IssueOutcome.TENANT_WINS
    assert mixed.outcome == IssueOutcome.SPLIT


def test_parse_prediction_response_accepts_amount_band() -> None:
    predictor = IssuePredictor(_DummyLLM())
    issue = IssueContext(
        issue_type=IssueType.REPAIRS_DAMP_MOULD,
        issue_description="damp and mould repairs",
        data_completeness=0.8,
    )

    prediction = predictor._parse_prediction_response(
        json.dumps(
            {
                "outcome": "service failure",
                "raw_confidence": 0.68,
                "predicted_amount": 450,
                "amount_band": "251 to 600",
                "reasoning": "Likely service failure with a mid-band remedy.",
                "evidence_strength": "moderate",
            }
        ),
        issue,
    )

    assert prediction.amount_band == "251-600"
    assert prediction.predicted_amount == 450


@pytest.mark.asyncio
async def test_repairs_prompt_requires_liability_remedy_and_comparator_amounts() -> None:
    from llm_orchestrator.prompts.packs import get_prompt_pack

    llm = _CaptureLLM()
    case_file = SimpleNamespace(
        metadata={
            "domain_id": "housing.repairs_social.v1",
            "matter_type": "repairs_damp_mould",
        },
        tenancy=SimpleNamespace(
            deposit_amount=None,
            start_date=None,
            end_date=None,
            tenancy_type=None,
        ),
        property=SimpleNamespace(region="london", postcode=None),
        tenant_narrative="Resident reported damp and mould for months.",
        landlord_narrative="Landlord says it inspected promptly.",
    )
    predictor = IssuePredictor(
        llm,
        case_file=case_file,
        prompt_pack=get_prompt_pack("housing.repairs_social.v1"),
    )
    issue = IssueContext(
        issue_type=IssueType.REPAIRS_DAMP_MOULD,
        issue_description="damp and mould repairs",
        data_completeness=0.8,
    )

    await predictor._predict_issue(
        issue,
        SimpleNamespace(
            results=[
                {
                    "case_reference": "HOS-1",
                    "year": 2025,
                    "chunk_text": "The landlord must pay £400 compensation.",
                    "combined_score": 0.8,
                }
            ]
        ),
        case_file=case_file,
    )

    prompt = llm.calls[0]["messages"][0]["content"]
    assert "separate liability from remedy" in prompt
    assert "cited comparator award amounts" in prompt
    assert "amount_band" in prompt
    assert "predicted_amount to null" in prompt
