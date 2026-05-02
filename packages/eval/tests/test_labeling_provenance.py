from datetime import datetime, timezone

import pytest

from eval.schema import LabelerModel


class TestLabelerModel:
    def test_minimal_round_trip(self) -> None:
        m = LabelerModel(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )
        assert m.provider == "anthropic"
        assert m.model == "claude-sonnet-4-20250514"
        assert m.api_version is None

    def test_rejects_unknown_provider(self) -> None:
        with pytest.raises(Exception):
            LabelerModel(provider="palm", model="bison-001")

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(Exception):
            LabelerModel(provider="openai", model="gpt-5", store=True)
