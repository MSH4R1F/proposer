"""Tests for housing.repairs_social.v1 factor catalog YAML.

Acceptance criteria (per task spec):
1. YAML loads via FactorCatalog.from_yaml(path) without errors.
2. Loader rejects unknown value_type / polarity values (extra="forbid").
3. Exactly 15 factors present (matches §12 v1 list).
4. All maps_to_outcomes IDs are in the closed outcome set.
5. No factor uses forbidden judgment labels.
6. Factor catalog model is frozen=True and rejects extra fields.
7. Loader works with pyyaml.

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §12
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from domain_packs.loaders import FactorCatalog, FactorEntry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FACTORS_YAML = (
    Path(__file__).resolve().parents[2]
    / "domain_packs"
    / "housing"
    / "repairs_social"
    / "factors.yaml"
)

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
    with pytest.raises(ValueError, match="Factor catalog file not found"):
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
