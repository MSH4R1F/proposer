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


from eval.schema import LabelingProvenance


def _valid_provenance_kwargs() -> dict:
    return dict(
        run_id="run-2026-05-02-001",
        labeled_at=datetime(2026, 5, 2, 14, 30, tzinfo=timezone.utc),
        labeler_models=[
            LabelerModel(provider="anthropic", model="claude-sonnet-4-20250514"),
            LabelerModel(provider="openai", model="gpt-5.5"),
        ],
        source_pdf_sha256="a" * 64,
        ocr_text_sha256="b" * 64,
        prompt_template_hash="t" * 16,
        gold_schema_hash="s" * 16,
        corpus_manifest_hash="c" * 16,
        canonicalizer_version="1.0.0",
        grounder_version="1.0.0",
        audit_seed=42,
        adjudicated_fields=[],
        inter_model_agreement_rate=0.92,
        grounding_pass_rate=0.88,
        audit_flip_rate=0.04,
        mandatory_review_flip_rate=0.10,
        field_provenance=[],
    )


class TestLabelingProvenance:
    def test_minimal_round_trip(self) -> None:
        lp = LabelingProvenance(**_valid_provenance_kwargs())
        round_tripped = LabelingProvenance.model_validate(lp.model_dump())
        assert round_tripped.run_id == lp.run_id
        assert round_tripped.is_human_only_anchor is False

    def test_requires_at_least_one_labeler_model(self) -> None:
        kwargs = _valid_provenance_kwargs()
        kwargs["labeler_models"] = []
        with pytest.raises(Exception, match="labeler_models"):
            LabelingProvenance(**kwargs)

    def test_anchor_case_flag(self) -> None:
        kwargs = _valid_provenance_kwargs()
        kwargs["is_human_only_anchor"] = True
        kwargs["anchor_set_id"] = "anchor-housing-v1-2026-05"
        lp = LabelingProvenance(**kwargs)
        assert lp.is_human_only_anchor is True

    @pytest.mark.parametrize("rate", [0.0, 0.5, 1.0])
    def test_rates_within_unit_interval(self, rate: float) -> None:
        kwargs = _valid_provenance_kwargs()
        kwargs["inter_model_agreement_rate"] = rate
        lp = LabelingProvenance(**kwargs)
        assert lp.inter_model_agreement_rate == rate

    def test_rejects_rate_out_of_unit_interval(self) -> None:
        kwargs = _valid_provenance_kwargs()
        kwargs["audit_flip_rate"] = 1.5
        with pytest.raises(Exception, match="audit_flip_rate"):
            LabelingProvenance(**kwargs)


# The eval-package conftest exposes only helper functions, not a pytest
# fixture. Define a local ``gold_case_minimal`` fixture here so Task 1.4's
# tests can take it as a parameter without modifying the shared conftest.
import json as _json
from pathlib import Path as _Path


@pytest.fixture
def gold_case_minimal() -> dict:
    fixtures_dir = _Path(__file__).parent / "fixtures"
    return _json.loads((fixtures_dir / "gold_case_minimal.json").read_text())


class TestGoldCaseLabelingProvenance:
    def test_optional_default_none(self, gold_case_minimal: dict) -> None:
        from eval.schema import GoldCase

        gc = GoldCase(**gold_case_minimal)
        assert gc.labeling_provenance is None

    def test_round_trip_with_provenance(self, gold_case_minimal: dict) -> None:
        from eval.schema import GoldCase

        gold_case_minimal["labeling_provenance"] = LabelingProvenance(
            **_valid_provenance_kwargs()
        ).model_dump(mode="json")
        gc = GoldCase(**gold_case_minimal)
        assert gc.labeling_provenance is not None
        assert gc.labeling_provenance.run_id == "run-2026-05-02-001"
