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


from eval.schema import FieldLabelProvenance, Provenance


class TestFieldLabelProvenance:
    def test_minimal_deterministic(self) -> None:
        p = FieldLabelProvenance(field_path="domain_id", source="deterministic_manifest")
        assert p.source == "deterministic_manifest"
        assert p.source_spans == []
        assert p.match_strategy is None
        assert p.reviewer_rationale is None

    def test_with_source_span_and_strategy(self) -> None:
        p = FieldLabelProvenance(
            field_path="key_reasoning_quotes[0].text",
            source="model_agreement",
            source_spans=[Provenance(page=3, paragraph=12, text_span=(120, 380))],
            match_strategy="canonical_exact",
        )
        assert p.match_strategy == "canonical_exact"
        assert len(p.source_spans) == 1

    def test_rejects_unknown_source(self) -> None:
        with pytest.raises(Exception):
            FieldLabelProvenance(field_path="facts", source="model_lone_wolf")
