import json
from datetime import date

import pytest

from ..clients.base import BaseLLMClient
from ..extractors.fact_extractor import FactExtractor
from ..models.case_file import CaseFile, PartyRole


class _BulkLLM(BaseLLMClient):
    async def generate(self, messages, system_prompt, max_tokens=4096, temperature=0.7):
        payload = {
            "tenancy": {
                "start_date": {"value": "15 January 2023", "confidence": 0.9},
                "end_date": {"value": "31 December 2024", "confidence": 0.9},
                "deposit_protected": {"value": "unknown", "confidence": 0.4},
            },
            "issues": [
                {
                    "issue_type": "deposit_protection",
                    "description": "late prescribed information",
                    "confidence": 0.9,
                }
            ],
            "narrative": "Deposit details are discussed in the statement.",
            "no_new_info": False,
        }
        return json.dumps(payload)

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


@pytest.mark.asyncio
async def test_bulk_extraction_fallback_populates_deposit_fields_from_case_text() -> (
    None
):
    extractor = FactExtractor(_BulkLLM())
    case_file = CaseFile(user_role=PartyRole.TENANT)

    case_text = (
        "I paid a £1,450 deposit before move-in. The deposit was protected in DPS, "
        "and prescribed information was received around 5 March 2023."
    )

    result = await extractor.extract_bulk(case_text=case_text, case_file=case_file)
    updated = result.updated_case_file

    assert updated.tenancy.start_date == date(2023, 1, 15)
    assert updated.tenancy.end_date == date(2024, 12, 31)
    assert updated.tenancy.deposit_amount == 1450.0
    assert updated.tenancy.deposit_protected is True
    assert updated.tenancy.deposit_scheme == "DPS"
    assert updated.tenancy.prescribed_info_provided is True
