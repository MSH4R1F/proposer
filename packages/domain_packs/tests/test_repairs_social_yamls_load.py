"""Tests for housing.repairs_social.v1 factor catalog YAML and B2 supporting YAMLs.

Acceptance criteria (per task spec):
1. YAML loads via FactorCatalog.from_yaml(path) without errors.
2. Loader rejects unknown value_type / polarity values (extra="forbid").
3. Exactly 15 factors present (matches §12 v1 list).
4. All maps_to_outcomes IDs are in the closed outcome set.
5. No factor uses forbidden judgment labels.
6. Factor catalog model is frozen=True and rejects extra fields.
7. Loader works with pyyaml.

B2 acceptance criteria:
B2-1. outcomes.yaml, remedies.yaml, retrieval_profile.yaml, graph_quality_gate.yaml load without errors.
B2-2. RetrievalProfile rejects comparator_weights that don't sum to 1.0.
B2-3. GraphQualityGate rejects negative thresholds.
B2-4. GraphQualityGate rejects rate fields outside [0, 1].
B2-5. Cross-reference: factor.maps_to_outcomes ⊆ outcomes.yaml IDs.
B2-6. All B2 loaders are frozen + extra="forbid".
B2-7. from_yaml raises ValueError for missing path (mirrors B1 pattern).

B7 acceptance criteria:
B7-1. extractor_strategy.yaml loads via ExtractorStrategy.from_yaml(path) without errors.
B7-2. Loader rejects unknown strategy values (Literal + extra="forbid").
B7-3. Validator enforces strategy=deterministic ↔ calculator_id present (both directions).
B7-4. Validator enforces strategy=llm_verified ↔ verifier_required=True (both directions).
B7-5. Loader rejects min_confidence_threshold outside [0, 1].
B7-6. Loader rejects duplicate factor_id entries.
B7-7. Cross-reference: every factor_id in extractor_strategy.yaml exists in factors.yaml;
      every factor_id in factors.yaml has exactly one entry in extractor_strategy.yaml.
B7-8. ExtractorStrategy and ExtractorEntry are frozen + extra="forbid".
B7-9. from_yaml for missing path raises ValueError (mirrors existing pattern).
B7-10. strategy=llm_extracted must have gate_counted=False (spec §4.1).

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §8.1, §9.2, §9.3, §12, §19 PR 3a
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from domain_packs.loaders import (
    ExtractorEntry,
    ExtractorStrategy,
    FactorCatalog,
    FactorEntry,
    GraphQualityGate,
    OutcomeSchema,
    RemedySchema,
    RetrievalProfile,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PACK_DIR = (
    Path(__file__).resolve().parents[2]
    / "domain_packs"
    / "housing"
    / "repairs_social"
)

FACTORS_YAML = _PACK_DIR / "factors.yaml"
OUTCOMES_YAML = _PACK_DIR / "outcomes.yaml"
REMEDIES_YAML = _PACK_DIR / "remedies.yaml"
RETRIEVAL_PROFILE_YAML = _PACK_DIR / "retrieval_profile.yaml"
GRAPH_QUALITY_GATE_YAML = _PACK_DIR / "graph_quality_gate.yaml"
EXTRACTOR_STRATEGY_YAML = _PACK_DIR / "extractor_strategy.yaml"

# Closed outcome ID set (canonical in B2; defined inline here per task spec)
CLOSED_OUTCOME_IDS = frozenset(
    {
        "no_maladministration",
        "service_failure",
        "maladministration",
        "severe_maladministration",
        "reasonable_redress",
        "outside_jurisdiction",
        "resolved_with_intervention",
    }
)

# v1 canonical factor IDs from §12 (must match exactly)
V1_FACTOR_IDS = frozenset(
    {
        "repair_responsibility_established",
        "hazard_or_disrepair_reported",
        "landlord_notice_established",
        "inspection_offered",
        "inspection_delay_days",
        "repair_attempted",
        "repair_delay_days",
        "records_inadequate",
        "communication_gap_days",
        "complaint_response_delay_days",
        "vulnerability_known",
        "impact_severity_reported",
        "temporary_decant_or_alternative_offered",
        "prior_compensation_or_apology_offered",
        "issue_outside_jurisdiction",
    }
)

# Forbidden IDs (removed in leakage audit, must not appear in any form)
FORBIDDEN_IDS = frozenset(
    {
        "landlord_actions_reasonable",
        "landlord_prior_offer_reasonable",
        "no_maladministration_due_to_reasonable_response",
        "impact_on_resident_significant",
        "inspection_delay_excessive",
        "repair_delay_excessive",
        "complaint_response_delay",
        "communication_failure",
    }
)

# Valid controlled vocabulary
VALID_VALUE_TYPES = frozenset({"boolean", "enum", "number", "duration", "money"})
VALID_POLARITIES = frozenset({"pro_claimant", "pro_respondent", "neutral"})


# ---------------------------------------------------------------------------
# AC 1: YAML loads without errors
# ---------------------------------------------------------------------------


def test_yaml_file_exists():
    """factors.yaml must be present at the expected path."""
    assert FACTORS_YAML.exists(), f"factors.yaml not found at {FACTORS_YAML}"


def test_yaml_loads_via_factor_catalog():
    """AC1: FactorCatalog.from_yaml(path) succeeds without errors."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    assert isinstance(catalog, FactorCatalog)
    assert len(catalog.factors) > 0


# ---------------------------------------------------------------------------
# AC 2: Loader rejects unknown value_type / polarity (extra="forbid")
# ---------------------------------------------------------------------------


def test_factor_entry_rejects_unknown_value_type(tmp_path):
    """AC2a: FactorEntry rejects unknown value_type."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "factors": [
                    {
                        "id": "test_factor",
                        "value_type": "invalid_type",
                        "polarity": "neutral",
                        "requires_evidence": True,
                        "maps_to_outcomes": [],
                        "description": "test",
                    }
                ]
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        FactorCatalog.from_yaml(bad_yaml)


def test_factor_entry_rejects_unknown_polarity(tmp_path):
    """AC2b: FactorEntry rejects unknown polarity."""
    bad_yaml = tmp_path / "bad_polarity.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "factors": [
                    {
                        "id": "test_factor",
                        "value_type": "boolean",
                        "polarity": "pro_judge",  # invalid
                        "requires_evidence": True,
                        "maps_to_outcomes": [],
                        "description": "test",
                    }
                ]
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        FactorCatalog.from_yaml(bad_yaml)


def test_factor_entry_rejects_extra_fields(tmp_path):
    """AC6 / AC2c: extra fields are rejected (extra='forbid')."""
    bad_yaml = tmp_path / "extra_field.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "factors": [
                    {
                        "id": "test_factor",
                        "value_type": "boolean",
                        "polarity": "neutral",
                        "requires_evidence": True,
                        "maps_to_outcomes": [],
                        "description": "test",
                        "unexpected_field": "should_be_rejected",
                    }
                ]
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        FactorCatalog.from_yaml(bad_yaml)


# ---------------------------------------------------------------------------
# AC 3: Exactly 15 factors
# ---------------------------------------------------------------------------


def test_exactly_15_factors():
    """AC3: Catalog contains exactly 15 v1 factors."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    assert len(catalog.factors) == 15, (
        f"Expected 15 factors, got {len(catalog.factors)}: "
        f"{sorted(f.id for f in catalog.factors)}"
    )


def test_factor_ids_match_v1_canonical_list():
    """AC3: Factor IDs match the canonical §12 v1 list exactly (no extras, none missing)."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    actual_ids = frozenset(f.id for f in catalog.factors)
    missing = V1_FACTOR_IDS - actual_ids
    extra = actual_ids - V1_FACTOR_IDS
    assert not missing, f"Missing factors: {sorted(missing)}"
    assert not extra, f"Extra factors (not in v1 list): {sorted(extra)}"


# ---------------------------------------------------------------------------
# AC 4: All maps_to_outcomes IDs are in the closed outcome set
# ---------------------------------------------------------------------------


def test_all_maps_to_outcomes_in_closed_set():
    """AC4: Every maps_to_outcomes ID must be in the closed outcome set."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    violations: list[str] = []
    for factor in catalog.factors:
        for outcome_id in factor.maps_to_outcomes:
            if outcome_id not in CLOSED_OUTCOME_IDS:
                violations.append(
                    f"Factor {factor.id!r} references unknown outcome {outcome_id!r}"
                )
    assert not violations, "\n".join(violations)


def test_each_factor_maps_to_at_least_one_outcome():
    """Each factor must map to at least one outcome (non-empty list)."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    empty = [f.id for f in catalog.factors if not f.maps_to_outcomes]
    assert not empty, f"Factors with empty maps_to_outcomes: {empty}"


# ---------------------------------------------------------------------------
# AC 5: No forbidden judgment labels
# ---------------------------------------------------------------------------


def test_no_forbidden_factor_ids():
    """AC5: No factor uses a forbidden judgment label ID."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    actual_ids = {f.id for f in catalog.factors}
    forbidden_used = actual_ids & FORBIDDEN_IDS
    assert not forbidden_used, (
        f"Forbidden factor IDs present (leakage audit failures): "
        f"{sorted(forbidden_used)}"
    )


# ---------------------------------------------------------------------------
# AC 6: frozen=True and extra="forbid"
# ---------------------------------------------------------------------------


def test_factor_entry_is_frozen():
    """AC6: FactorEntry model is frozen — direct attribute assignment raises."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    factor = catalog.factors[0]
    # Pydantic v2 frozen=True raises ValidationError on direct attribute mutation.
    # object.__setattr__ bypasses __setattr__ at the C level and is not a valid
    # mutation path in production code; the guard that matters is the public API.
    with pytest.raises(Exception):  # pydantic ValidationError (frozen_instance)
        factor.id = "mutated_id"  # type: ignore[misc]


def test_factor_catalog_is_frozen():
    """AC6: FactorCatalog model is frozen — direct attribute assignment raises."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    with pytest.raises(Exception):  # pydantic ValidationError (frozen_instance)
        catalog.factors = []  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AC 7: pyyaml-based loader (structural verification)
# ---------------------------------------------------------------------------


def test_loader_uses_pyyaml(tmp_path):
    """AC7: Verify loader works with a minimal valid YAML (pyyaml path)."""
    minimal = tmp_path / "minimal.yaml"
    minimal.write_text(
        yaml.dump(
            {
                "factors": [
                    {
                        "id": "repair_delay_days",
                        "value_type": "duration",
                        "polarity": "pro_claimant",
                        "requires_evidence": True,
                        "maps_to_outcomes": ["maladministration"],
                        "description": "Duration between report and repair.",
                        "bucket_strategy": "log_days",
                    }
                ]
            }
        )
    )
    catalog = FactorCatalog.from_yaml(minimal)
    assert len(catalog.factors) == 1
    assert catalog.factors[0].id == "repair_delay_days"


# ---------------------------------------------------------------------------
# Schema-level field validation tests
# ---------------------------------------------------------------------------


def test_all_factors_have_valid_value_types():
    """All factors use a value_type from the allowed closed set."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    for factor in catalog.factors:
        assert factor.value_type in VALID_VALUE_TYPES, (
            f"Factor {factor.id!r} has invalid value_type {factor.value_type!r}"
        )


def test_all_factors_have_valid_polarity():
    """All factors use a polarity from the allowed closed set."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    for factor in catalog.factors:
        assert factor.polarity in VALID_POLARITIES, (
            f"Factor {factor.id!r} has invalid polarity {factor.polarity!r}"
        )


def test_duration_factors_have_bucket_strategy():
    """Numeric *_days factors must declare bucket_strategy: log_days."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    days_factors = [f for f in catalog.factors if f.id.endswith("_days")]
    for factor in days_factors:
        assert factor.bucket_strategy == "log_days", (
            f"Factor {factor.id!r} (duration) missing bucket_strategy='log_days'; "
            f"got {factor.bucket_strategy!r}"
        )


def test_impact_severity_has_closed_enum_values():
    """impact_severity_reported must have closed enum_values list."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    severity = next(
        (f for f in catalog.factors if f.id == "impact_severity_reported"), None
    )
    assert severity is not None, "impact_severity_reported factor not found"
    assert severity.enum_values == [
        "none",
        "minor",
        "moderate",
        "severe",
    ], (
        f"impact_severity_reported enum_values mismatch: {severity.enum_values}"
    )


def test_requires_evidence_defaults_true():
    """All factors should default requires_evidence to True."""
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    # issue_outside_jurisdiction is a rule-derived factor, may be False
    # All others should be True
    factual_factors = [
        f for f in catalog.factors if f.id != "issue_outside_jurisdiction"
    ]
    for factor in factual_factors:
        assert factor.requires_evidence is True, (
            f"Factor {factor.id!r} has requires_evidence=False "
            "(expected True for non-rule factors)"
        )


# ---------------------------------------------------------------------------
# Issue 3 fix: FileNotFoundError is converted to ValueError
# ---------------------------------------------------------------------------


def test_from_yaml_raises_value_error_for_missing_file(tmp_path):
    """from_yaml must raise ValueError (not FileNotFoundError) for a missing path."""
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(ValueError, match="Factor catalog YAML file not found"):
        FactorCatalog.from_yaml(missing)


# ---------------------------------------------------------------------------
# Issue 5 fix: direct FactorEntry construction (makes import live + schema coverage)
# ---------------------------------------------------------------------------


def test_factor_entry_constructs_with_minimum_valid_fields():
    """FactorEntry must accept only the required fields and apply correct defaults."""
    entry = FactorEntry(
        id="some_factor",
        value_type="boolean",
        polarity="neutral",
        maps_to_outcomes=["service_failure"],
        description="A minimal boolean factor.",
    )
    assert entry.id == "some_factor"
    assert entry.value_type == "boolean"
    assert entry.polarity == "neutral"
    assert entry.maps_to_outcomes == ["service_failure"]
    # Check defaults
    assert entry.requires_evidence is True
    assert entry.bucket_strategy is None
    assert entry.enum_values is None


# ---------------------------------------------------------------------------
# Issue 1 fix: bucket_strategy Literal rejects unknown strategies
# ---------------------------------------------------------------------------


def test_factor_entry_rejects_unknown_bucket_strategy(tmp_path):
    """bucket_strategy must only accept 'log_days'; unknown values raise ValueError."""
    bad_yaml = tmp_path / "bad_bucket.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "factors": [
                    {
                        "id": "repair_delay_days",
                        "value_type": "duration",
                        "polarity": "pro_claimant",
                        "requires_evidence": True,
                        "maps_to_outcomes": ["maladministration"],
                        "description": "Duration between report and repair.",
                        "bucket_strategy": "linear",  # invalid: only log_days is allowed
                    }
                ]
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        FactorCatalog.from_yaml(bad_yaml)


# ===========================================================================
# B2 tests: outcomes.yaml, remedies.yaml, retrieval_profile.yaml, graph_quality_gate.yaml
# ===========================================================================

# ---------------------------------------------------------------------------
# B2-1 / B2-7: YAML files exist and load without errors
# ---------------------------------------------------------------------------

EXPECTED_REMEDY_IDS = frozenset(
    {
        "compensation_ordered",
        "apology",
        "repair_action",
        "inspection_ordered",
        "case_review",
        "policy_review",
        "training_order",
        "no_further_order",
    }
)


def test_outcomes_yaml_exists():
    assert OUTCOMES_YAML.exists(), f"outcomes.yaml not found at {OUTCOMES_YAML}"


def test_outcomes_yaml_loads():
    """B2-1: OutcomeSchema.from_yaml loads without errors."""
    schema = OutcomeSchema.from_yaml(OUTCOMES_YAML)
    assert isinstance(schema, OutcomeSchema)
    assert len(schema.outcomes) == 7


def test_outcomes_yaml_ids_match_closed_set():
    """outcomes.yaml must contain exactly the 7 closed outcome IDs."""
    schema = OutcomeSchema.from_yaml(OUTCOMES_YAML)
    actual_ids = frozenset(o.id for o in schema.outcomes)
    assert actual_ids == CLOSED_OUTCOME_IDS, (
        f"outcomes.yaml IDs mismatch.\nExpected: {sorted(CLOSED_OUTCOME_IDS)}\n"
        f"Got: {sorted(actual_ids)}"
    )


def test_outcomes_yaml_descriptions_non_empty():
    """Each outcome entry must have a non-empty description."""
    schema = OutcomeSchema.from_yaml(OUTCOMES_YAML)
    for outcome in schema.outcomes:
        assert outcome.description.strip(), (
            f"Outcome {outcome.id!r} has empty description"
        )


def test_outcomes_yaml_domain_id():
    """domain_id must be housing.repairs_social.v1."""
    schema = OutcomeSchema.from_yaml(OUTCOMES_YAML)
    assert schema.domain_id == "housing.repairs_social.v1"


def test_outcomes_schema_is_frozen():
    """B2-6: OutcomeSchema and its entries must be frozen."""
    schema = OutcomeSchema.from_yaml(OUTCOMES_YAML)
    with pytest.raises(ValidationError):
        schema.outcomes = []  # type: ignore[misc]


def test_outcomes_from_yaml_missing_path_raises_value_error(tmp_path):
    """B2-7: from_yaml for missing path raises ValueError."""
    missing = tmp_path / "no_such_file.yaml"
    with pytest.raises(ValueError):
        OutcomeSchema.from_yaml(missing)


def test_remedies_yaml_exists():
    assert REMEDIES_YAML.exists(), f"remedies.yaml not found at {REMEDIES_YAML}"


def test_remedies_yaml_loads():
    """B2-1: RemedySchema.from_yaml loads without errors."""
    schema = RemedySchema.from_yaml(REMEDIES_YAML)
    assert isinstance(schema, RemedySchema)
    assert len(schema.remedies) == 8


def test_remedies_yaml_ids_match_closed_set():
    """remedies.yaml must contain exactly the 8 closed remedy IDs."""
    schema = RemedySchema.from_yaml(REMEDIES_YAML)
    actual_ids = frozenset(r.id for r in schema.remedies)
    assert actual_ids == EXPECTED_REMEDY_IDS, (
        f"remedies.yaml IDs mismatch.\nExpected: {sorted(EXPECTED_REMEDY_IDS)}\n"
        f"Got: {sorted(actual_ids)}"
    )


def test_remedies_yaml_domain_id():
    """domain_id must be housing.repairs_social.v1."""
    schema = RemedySchema.from_yaml(REMEDIES_YAML)
    assert schema.domain_id == "housing.repairs_social.v1"


def test_remedies_schema_is_frozen():
    """B2-6: RemedySchema must be frozen."""
    schema = RemedySchema.from_yaml(REMEDIES_YAML)
    with pytest.raises(ValidationError):
        schema.remedies = []  # type: ignore[misc]


def test_remedies_from_yaml_missing_path_raises_value_error(tmp_path):
    """B2-7: from_yaml for missing path raises ValueError."""
    missing = tmp_path / "no_such_file.yaml"
    with pytest.raises(ValueError):
        RemedySchema.from_yaml(missing)


def test_retrieval_profile_yaml_exists():
    assert RETRIEVAL_PROFILE_YAML.exists(), (
        f"retrieval_profile.yaml not found at {RETRIEVAL_PROFILE_YAML}"
    )


def test_retrieval_profile_yaml_loads():
    """B2-1: RetrievalProfile.from_yaml loads without errors."""
    profile = RetrievalProfile.from_yaml(RETRIEVAL_PROFILE_YAML)
    assert isinstance(profile, RetrievalProfile)


def test_retrieval_profile_weights_sum_to_one():
    """comparator_weights must sum to 1.0 (within 1e-6 tolerance)."""
    profile = RetrievalProfile.from_yaml(RETRIEVAL_PROFILE_YAML)
    w = profile.comparator_weights
    total = (
        w.factor_overlap
        + w.text_relevance
        + w.outcome_component_match
        + w.remedy_similarity
        + w.authority_level_match
        + w.chronology_match
        + w.claim_head_exact_match
    )
    assert abs(total - 1.0) < 1e-6, f"Weights sum to {total}, not 1.0"


def test_retrieval_profile_domain_id():
    profile = RetrievalProfile.from_yaml(RETRIEVAL_PROFILE_YAML)
    assert profile.domain_id == "housing.repairs_social.v1"


def test_retrieval_profile_is_frozen():
    """B2-6: RetrievalProfile must be frozen."""
    profile = RetrievalProfile.from_yaml(RETRIEVAL_PROFILE_YAML)
    with pytest.raises(ValidationError):
        profile.domain_id = "other"  # type: ignore[misc]


def test_retrieval_profile_from_yaml_missing_path_raises_value_error(tmp_path):
    """B2-7: from_yaml for missing path raises ValueError."""
    missing = tmp_path / "no_such_file.yaml"
    with pytest.raises(ValueError):
        RetrievalProfile.from_yaml(missing)


def test_graph_quality_gate_yaml_exists():
    assert GRAPH_QUALITY_GATE_YAML.exists(), (
        f"graph_quality_gate.yaml not found at {GRAPH_QUALITY_GATE_YAML}"
    )


def test_graph_quality_gate_yaml_loads():
    """B2-1: GraphQualityGate.from_yaml loads without errors."""
    gate = GraphQualityGate.from_yaml(GRAPH_QUALITY_GATE_YAML)
    assert isinstance(gate, GraphQualityGate)


def test_graph_quality_gate_domain_id():
    gate = GraphQualityGate.from_yaml(GRAPH_QUALITY_GATE_YAML)
    assert gate.domain_id == "housing.repairs_social.v1"


def test_graph_quality_gate_is_frozen():
    """B2-6: GraphQualityGate must be frozen."""
    gate = GraphQualityGate.from_yaml(GRAPH_QUALITY_GATE_YAML)
    with pytest.raises(ValidationError):
        gate.domain_id = "other"  # type: ignore[misc]


def test_graph_quality_gate_from_yaml_missing_path_raises_value_error(tmp_path):
    """B2-7: from_yaml for missing path raises ValueError."""
    missing = tmp_path / "no_such_file.yaml"
    with pytest.raises(ValueError):
        GraphQualityGate.from_yaml(missing)


# ---------------------------------------------------------------------------
# B2-2: RetrievalProfile rejects weights that don't sum to 1.0
# ---------------------------------------------------------------------------


def test_retrieval_profile_rejects_weights_not_summing_to_one(tmp_path):
    """B2-2: comparator_weights that don't sum to 1.0 raise ValidationError."""
    bad_yaml = tmp_path / "bad_weights.yaml"
    bad_data = {
        "domain_id": "housing.repairs_social.v1",
        "comparator_weights": {
            "factor_overlap": 0.30,
            "text_relevance": 0.30,  # changed: now sums > 1
            "outcome_component_match": 0.15,
            "remedy_similarity": 0.10,
            "authority_level_match": 0.10,
            "chronology_match": 0.05,
            "claim_head_exact_match": 0.05,
        },
        "counterexample": {
            "n_counterexamples": 2,
            "k_overlap_min": 3,
            "abstain_if_none": True,
        },
        "bucket_definitions": {
            "money": {
                "strategy": "log_pence",
                "bucket_edges_pence": [0, 10000, 50000, 200000, 1000000],
            },
            "duration": {
                "strategy": "log_days",
                "bucket_edges_days": [1, 7, 30, 90, 365],
            },
            "date": {
                "strategy": "granularity",
                "same_year_score": 0.5,
                "same_month_score": 1.0,
                "other_score": 0.0,
            },
        },
    }
    bad_yaml.write_text(yaml.dump(bad_data))
    with pytest.raises((ValidationError, ValueError)):
        RetrievalProfile.from_yaml(bad_yaml)


# ---------------------------------------------------------------------------
# B2-3: GraphQualityGate rejects negative thresholds
# ---------------------------------------------------------------------------


def test_graph_quality_gate_rejects_negative_min_threshold(tmp_path):
    """B2-3: evidence_backed_factor_count_min: -1 raises ValidationError."""
    bad_yaml = tmp_path / "bad_gate.yaml"
    bad_data = {
        "domain_id": "housing.repairs_social.v1",
        "evidence_backed_factor_count_min": -1,
        "dated_event_count_min": 2,
        "issue_count_min": 1,
        "outcome_or_remedy_candidate_count_min": 1,
        "unsupported_factor_rate_max": 0.30,
        "source_span_coverage_min": 0.80,
        "contradiction_count_max": 0,
    }
    bad_yaml.write_text(yaml.dump(bad_data))
    with pytest.raises((ValidationError, ValueError)):
        GraphQualityGate.from_yaml(bad_yaml)


# ---------------------------------------------------------------------------
# B2-4: GraphQualityGate rejects rate fields outside [0, 1]
# ---------------------------------------------------------------------------


def test_graph_quality_gate_rejects_rate_above_one(tmp_path):
    """B2-4: unsupported_factor_rate_max: 1.5 raises ValidationError."""
    bad_yaml = tmp_path / "bad_rate.yaml"
    bad_data = {
        "domain_id": "housing.repairs_social.v1",
        "evidence_backed_factor_count_min": 5,
        "dated_event_count_min": 2,
        "issue_count_min": 1,
        "outcome_or_remedy_candidate_count_min": 1,
        "unsupported_factor_rate_max": 1.5,
        "source_span_coverage_min": 0.80,
        "contradiction_count_max": 0,
    }
    bad_yaml.write_text(yaml.dump(bad_data))
    with pytest.raises((ValidationError, ValueError)):
        GraphQualityGate.from_yaml(bad_yaml)


def test_graph_quality_gate_rejects_coverage_below_zero(tmp_path):
    """B2-4: source_span_coverage_min: -0.1 raises ValidationError."""
    bad_yaml = tmp_path / "bad_coverage.yaml"
    bad_data = {
        "domain_id": "housing.repairs_social.v1",
        "evidence_backed_factor_count_min": 5,
        "dated_event_count_min": 2,
        "issue_count_min": 1,
        "outcome_or_remedy_candidate_count_min": 1,
        "unsupported_factor_rate_max": 0.30,
        "source_span_coverage_min": -0.1,
        "contradiction_count_max": 0,
    }
    bad_yaml.write_text(yaml.dump(bad_data))
    with pytest.raises((ValidationError, ValueError)):
        GraphQualityGate.from_yaml(bad_yaml)


# ---------------------------------------------------------------------------
# B2-5: Cross-reference: factor.maps_to_outcomes ⊆ outcomes.yaml IDs
# ---------------------------------------------------------------------------


def test_cross_reference_factor_outcomes_subset_of_outcomes_yaml():
    """B2-5: Every factor.maps_to_outcomes value must exist in outcomes.yaml IDs."""
    factor_catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    outcome_schema = OutcomeSchema.from_yaml(OUTCOMES_YAML)

    valid_outcome_ids = frozenset(o.id for o in outcome_schema.outcomes)

    violations: list[str] = []
    for factor in factor_catalog.factors:
        for outcome_id in factor.maps_to_outcomes:
            if outcome_id not in valid_outcome_ids:
                violations.append(
                    f"Factor {factor.id!r} references unknown outcome {outcome_id!r} "
                    f"(not in outcomes.yaml)"
                )

    assert not violations, (
        f"Cross-reference failures ({len(violations)}):\n" + "\n".join(violations)
    )


# ===========================================================================
# B3 tests: per-factor annotation rubric
# ===========================================================================


def test_annotation_rubric_file_exists_and_nontrivial():
    """B3: annotation_rubric.md must exist and have substantial content."""
    rubric_path = (
        Path(__file__).resolve().parents[2]
        / "domain_packs"
        / "housing"
        / "repairs_social"
        / "annotation_rubric.md"
    )
    assert rubric_path.exists(), f"annotation_rubric.md not found at {rubric_path}"
    text = rubric_path.read_text(encoding="utf-8")
    assert len(text) > 2000, (
        f"rubric is suspiciously short: {len(text)} chars"
    )


def test_annotation_rubric_covers_every_factor():
    """The rubric markdown must have a heading for every factor in factors.yaml.

    Heading set (h2 only) must equal the factor ID set exactly — no extras,
    none missing.
    """
    import re

    rubric_path = (
        Path(__file__).resolve().parents[2]
        / "domain_packs"
        / "housing"
        / "repairs_social"
        / "annotation_rubric.md"
    )
    text = rubric_path.read_text(encoding="utf-8")
    # H2 headings only; factor IDs are bare (no prefix).
    headings = set(re.findall(r"^## (\S+)$", text, re.MULTILINE))

    catalog = FactorCatalog.from_yaml(FACTORS_YAML)
    factor_ids = {f.id for f in catalog.factors}

    missing = factor_ids - headings
    extra = headings - factor_ids
    assert not missing and not extra, (
        f"Rubric heading set must equal factor ID set. "
        f"Missing: {sorted(missing)}. Extra: {sorted(extra)}."
    )


# ===========================================================================
# B7 tests: extractor_strategy.yaml and ExtractorStrategy loader
# ===========================================================================

# ---------------------------------------------------------------------------
# B7-1: YAML exists and loads without errors
# ---------------------------------------------------------------------------


def test_extractor_strategy_yaml_exists():
    """extractor_strategy.yaml must be present at the expected path."""
    assert EXTRACTOR_STRATEGY_YAML.exists(), (
        f"extractor_strategy.yaml not found at {EXTRACTOR_STRATEGY_YAML}"
    )


def test_extractor_strategy_yaml_loads():
    """B7-1: ExtractorStrategy.from_yaml loads without errors."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    assert isinstance(strategy, ExtractorStrategy)
    assert len(strategy.entries) > 0


def test_extractor_strategy_domain_id():
    """domain_id must be housing.repairs_social.v1."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    assert strategy.domain_id == "housing.repairs_social.v1"


def test_extractor_strategy_has_15_entries():
    """Exactly 15 entries — one per v1 factor."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    assert len(strategy.entries) == 15, (
        f"Expected 15 extractor entries, got {len(strategy.entries)}: "
        f"{sorted(e.factor_id for e in strategy.entries)}"
    )


# ---------------------------------------------------------------------------
# B7-2: Loader rejects unknown strategy values
# ---------------------------------------------------------------------------


def test_extractor_entry_rejects_unknown_strategy(tmp_path):
    """B7-2: ExtractorEntry rejects unknown strategy values."""
    bad_yaml = tmp_path / "bad_strategy.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "repair_delay_days",
                        "strategy": "heuristic",  # invalid
                        "calculator_id": "some_calc",
                        "verifier_required": False,
                        "gate_counted": True,
                        "min_confidence_threshold": 0.5,
                    }
                ],
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        ExtractorStrategy.from_yaml(bad_yaml)


def test_extractor_entry_rejects_extra_fields(tmp_path):
    """B7-8: extra fields are rejected (extra='forbid')."""
    bad_yaml = tmp_path / "extra_field.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "repair_delay_days",
                        "strategy": "deterministic",
                        "calculator_id": "repair_delay_calculator",
                        "verifier_required": False,
                        "gate_counted": True,
                        "min_confidence_threshold": 0.5,
                        "unexpected_field": "should_be_rejected",
                    }
                ],
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        ExtractorStrategy.from_yaml(bad_yaml)


# ---------------------------------------------------------------------------
# B7-3: strategy=deterministic ↔ calculator_id present
# ---------------------------------------------------------------------------


def test_deterministic_without_calculator_id_raises(tmp_path):
    """B7-3a: strategy=deterministic without calculator_id must fail."""
    bad_yaml = tmp_path / "det_no_calc.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "repair_delay_days",
                        "strategy": "deterministic",
                        "verifier_required": False,
                        "gate_counted": True,
                        "min_confidence_threshold": 0.5,
                        # calculator_id intentionally absent
                    }
                ],
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        ExtractorStrategy.from_yaml(bad_yaml)


def test_non_deterministic_with_calculator_id_raises(tmp_path):
    """B7-3b: strategy=llm_verified with calculator_id must fail."""
    bad_yaml = tmp_path / "llm_with_calc.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "hazard_or_disrepair_reported",
                        "strategy": "llm_verified",
                        "calculator_id": "some_calculator",  # must be None
                        "verifier_required": True,
                        "gate_counted": True,
                        "min_confidence_threshold": 0.5,
                    }
                ],
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        ExtractorStrategy.from_yaml(bad_yaml)


def test_deterministic_with_calculator_id_is_valid(tmp_path):
    """B7-3c: strategy=deterministic with calculator_id must succeed."""
    good_yaml = tmp_path / "det_ok.yaml"
    good_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "repair_delay_days",
                        "strategy": "deterministic",
                        "calculator_id": "repair_delay_calculator",
                        "verifier_required": False,
                        "gate_counted": True,
                        "min_confidence_threshold": 1.0,
                    }
                ],
            }
        )
    )
    strategy = ExtractorStrategy.from_yaml(good_yaml)
    assert strategy.entries[0].calculator_id == "repair_delay_calculator"


# ---------------------------------------------------------------------------
# B7-4: strategy=llm_verified ↔ verifier_required=True
# ---------------------------------------------------------------------------


def test_llm_verified_without_verifier_required_raises(tmp_path):
    """B7-4a: strategy=llm_verified with verifier_required=False must fail."""
    bad_yaml = tmp_path / "llm_no_verifier.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "hazard_or_disrepair_reported",
                        "strategy": "llm_verified",
                        "verifier_required": False,  # must be True
                        "gate_counted": True,
                        "min_confidence_threshold": 0.5,
                    }
                ],
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        ExtractorStrategy.from_yaml(bad_yaml)


def test_non_llm_verified_with_verifier_required_raises(tmp_path):
    """B7-4b: strategy=deterministic with verifier_required=True must fail."""
    bad_yaml = tmp_path / "det_verifier.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "repair_delay_days",
                        "strategy": "deterministic",
                        "calculator_id": "repair_delay_calculator",
                        "verifier_required": True,  # must be False
                        "gate_counted": True,
                        "min_confidence_threshold": 1.0,
                    }
                ],
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        ExtractorStrategy.from_yaml(bad_yaml)


def test_llm_verified_with_verifier_required_is_valid(tmp_path):
    """B7-4c: strategy=llm_verified with verifier_required=True must succeed."""
    good_yaml = tmp_path / "llm_ok.yaml"
    good_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "hazard_or_disrepair_reported",
                        "strategy": "llm_verified",
                        "verifier_required": True,
                        "gate_counted": True,
                        "min_confidence_threshold": 0.5,
                    }
                ],
            }
        )
    )
    strategy = ExtractorStrategy.from_yaml(good_yaml)
    assert strategy.entries[0].verifier_required is True


# ---------------------------------------------------------------------------
# B7-5: min_confidence_threshold out of [0, 1] raises
# ---------------------------------------------------------------------------


def test_confidence_threshold_above_one_raises(tmp_path):
    """B7-5a: min_confidence_threshold > 1.0 must fail."""
    bad_yaml = tmp_path / "conf_high.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "repair_delay_days",
                        "strategy": "deterministic",
                        "calculator_id": "repair_delay_calculator",
                        "verifier_required": False,
                        "gate_counted": True,
                        "min_confidence_threshold": 1.5,  # invalid
                    }
                ],
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        ExtractorStrategy.from_yaml(bad_yaml)


def test_confidence_threshold_below_zero_raises(tmp_path):
    """B7-5b: min_confidence_threshold < 0.0 must fail."""
    bad_yaml = tmp_path / "conf_low.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "repair_delay_days",
                        "strategy": "deterministic",
                        "calculator_id": "repair_delay_calculator",
                        "verifier_required": False,
                        "gate_counted": True,
                        "min_confidence_threshold": -0.1,  # invalid
                    }
                ],
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        ExtractorStrategy.from_yaml(bad_yaml)


# ---------------------------------------------------------------------------
# B7-6: Duplicate factor_id entries raise
# ---------------------------------------------------------------------------


def test_duplicate_factor_id_raises(tmp_path):
    """B7-6: Duplicate factor_id entries must fail validation."""
    bad_yaml = tmp_path / "dup_factor.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "repair_delay_days",
                        "strategy": "deterministic",
                        "calculator_id": "repair_delay_calculator",
                        "verifier_required": False,
                        "gate_counted": True,
                        "min_confidence_threshold": 1.0,
                    },
                    {
                        "factor_id": "repair_delay_days",  # duplicate
                        "strategy": "deterministic",
                        "calculator_id": "repair_delay_calculator",
                        "verifier_required": False,
                        "gate_counted": True,
                        "min_confidence_threshold": 1.0,
                    },
                ],
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        ExtractorStrategy.from_yaml(bad_yaml)


# ---------------------------------------------------------------------------
# B7-7: Cross-reference: extractor_strategy.yaml factor_ids ↔ factors.yaml IDs
# ---------------------------------------------------------------------------


def test_extractor_strategy_factor_ids_subset_of_factors_yaml():
    """B7-7a: Every factor_id in extractor_strategy.yaml must exist in factors.yaml."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)

    catalog_ids = frozenset(f.id for f in catalog.factors)
    strategy_ids = frozenset(e.factor_id for e in strategy.entries)

    unknown = strategy_ids - catalog_ids
    assert not unknown, (
        f"extractor_strategy.yaml references factor_ids not in factors.yaml: "
        f"{sorted(unknown)}"
    )


def test_factors_yaml_factor_ids_subset_of_extractor_strategy():
    """B7-7b: Every factor_id in factors.yaml must have exactly one entry in extractor_strategy.yaml."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)

    catalog_ids = frozenset(f.id for f in catalog.factors)
    strategy_ids = frozenset(e.factor_id for e in strategy.entries)

    missing = catalog_ids - strategy_ids
    assert not missing, (
        f"factors.yaml factor_ids missing from extractor_strategy.yaml: "
        f"{sorted(missing)}"
    )


def test_extractor_strategy_factor_ids_exactly_match_factors_yaml():
    """B7-7c: extractor_strategy.yaml factor_id set must equal factors.yaml ID set exactly."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    catalog = FactorCatalog.from_yaml(FACTORS_YAML)

    catalog_ids = frozenset(f.id for f in catalog.factors)
    strategy_ids = frozenset(e.factor_id for e in strategy.entries)

    assert catalog_ids == strategy_ids, (
        f"Factor ID sets diverge.\n"
        f"Only in factors.yaml: {sorted(catalog_ids - strategy_ids)}\n"
        f"Only in extractor_strategy.yaml: {sorted(strategy_ids - catalog_ids)}"
    )


# ---------------------------------------------------------------------------
# B7-8: frozen + extra="forbid"
# ---------------------------------------------------------------------------


def test_extractor_entry_is_frozen():
    """B7-8: ExtractorEntry is frozen — mutation raises."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    entry = strategy.entries[0]
    with pytest.raises(Exception):
        entry.factor_id = "mutated"  # type: ignore[misc]


def test_extractor_strategy_is_frozen():
    """B7-8: ExtractorStrategy is frozen — mutation raises."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    with pytest.raises(Exception):
        strategy.entries = []  # type: ignore[misc]


# ---------------------------------------------------------------------------
# B7-9: from_yaml raises ValueError for missing path
# ---------------------------------------------------------------------------


def test_extractor_strategy_from_yaml_missing_path_raises_value_error(tmp_path):
    """B7-9: from_yaml for missing path raises ValueError."""
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(ValueError, match="Extractor strategy YAML file not found"):
        ExtractorStrategy.from_yaml(missing)


# ---------------------------------------------------------------------------
# B7-10: strategy=llm_extracted must have gate_counted=False
# ---------------------------------------------------------------------------


def test_llm_extracted_with_gate_counted_true_raises(tmp_path):
    """B7-10a: strategy=llm_extracted with gate_counted=True must fail (spec §4.1)."""
    bad_yaml = tmp_path / "llm_extracted_gate.yaml"
    bad_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "hazard_or_disrepair_reported",
                        "strategy": "llm_extracted",
                        "verifier_required": False,
                        "gate_counted": True,  # must be False for llm_extracted
                        "min_confidence_threshold": 0.5,
                    }
                ],
            }
        )
    )
    with pytest.raises((ValidationError, ValueError)):
        ExtractorStrategy.from_yaml(bad_yaml)


def test_llm_extracted_with_gate_counted_false_is_valid(tmp_path):
    """B7-10b: strategy=llm_extracted with gate_counted=False must succeed."""
    good_yaml = tmp_path / "llm_extracted_ok.yaml"
    good_yaml.write_text(
        yaml.dump(
            {
                "domain_id": "housing.repairs_social.v1",
                "entries": [
                    {
                        "factor_id": "hazard_or_disrepair_reported",
                        "strategy": "llm_extracted",
                        "verifier_required": False,
                        "gate_counted": False,
                        "min_confidence_threshold": 0.5,
                    }
                ],
            }
        )
    )
    strategy = ExtractorStrategy.from_yaml(good_yaml)
    assert strategy.entries[0].gate_counted is False


# ---------------------------------------------------------------------------
# B7 - strategy distribution sanity checks on the real YAML
# ---------------------------------------------------------------------------


def test_extractor_strategy_has_5_deterministic():
    """v1 strategy assigns exactly 5 deterministic factors."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    det = [e for e in strategy.entries if e.strategy == "deterministic"]
    assert len(det) == 5, (
        f"Expected 5 deterministic entries, got {len(det)}: "
        f"{sorted(e.factor_id for e in det)}"
    )


def test_extractor_strategy_has_10_llm_verified():
    """v1 strategy assigns exactly 10 llm_verified factors."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    llm_v = [e for e in strategy.entries if e.strategy == "llm_verified"]
    assert len(llm_v) == 10, (
        f"Expected 10 llm_verified entries, got {len(llm_v)}: "
        f"{sorted(e.factor_id for e in llm_v)}"
    )


def test_all_deterministic_entries_have_calculator_id():
    """All deterministic entries must have a non-None calculator_id."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    violations = [
        e.factor_id
        for e in strategy.entries
        if e.strategy == "deterministic" and e.calculator_id is None
    ]
    assert not violations, (
        f"Deterministic entries missing calculator_id: {sorted(violations)}"
    )


def test_all_llm_verified_entries_have_verifier_required_true():
    """All llm_verified entries must have verifier_required=True."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    violations = [
        e.factor_id
        for e in strategy.entries
        if e.strategy == "llm_verified" and not e.verifier_required
    ]
    assert not violations, (
        f"llm_verified entries with verifier_required=False: {sorted(violations)}"
    )


def test_all_non_llm_verified_entries_have_verifier_required_false():
    """All non-llm_verified entries must have verifier_required=False."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    violations = [
        e.factor_id
        for e in strategy.entries
        if e.strategy != "llm_verified" and e.verifier_required
    ]
    assert not violations, (
        f"Non-llm_verified entries with verifier_required=True: {sorted(violations)}"
    )


def test_deterministic_entries_threshold_is_one():
    """Deterministic entries should have min_confidence_threshold=1.0 (exact derivation)."""
    strategy = ExtractorStrategy.from_yaml(EXTRACTOR_STRATEGY_YAML)
    violations = [
        e.factor_id
        for e in strategy.entries
        if e.strategy == "deterministic" and e.min_confidence_threshold != 1.0
    ]
    assert not violations, (
        f"Deterministic entries with threshold != 1.0: {sorted(violations)}"
    )


def test_extractor_entry_direct_construction():
    """ExtractorEntry constructs correctly with minimum valid fields (llm_verified)."""
    entry = ExtractorEntry(
        factor_id="some_factor",
        strategy="llm_verified",
        verifier_required=True,
    )
    assert entry.factor_id == "some_factor"
    assert entry.strategy == "llm_verified"
    assert entry.verifier_required is True
    assert entry.calculator_id is None
    assert entry.gate_counted is True
    assert entry.min_confidence_threshold == 0.5
