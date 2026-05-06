"""domain_packs.loaders: Pydantic v2 loaders for domain-pack YAMLs.

Provides:
  - FactorCatalog / FactorEntry
  - OutcomeSchema / OutcomeEntry
  - RemedySchema / RemedyEntry
  - RetrievalProfile (with nested ComparatorWeights, CounterexampleConfig, BucketDefinitions)
  - GraphQualityGate

All models: extra="forbid" + frozen=True.

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §8.1, §9.2, §9.3, §12
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

FactorValueType = Literal["boolean", "enum", "number", "duration", "money"]
FactorPolarity = Literal["pro_claimant", "pro_respondent", "neutral"]


# ---------------------------------------------------------------------------
# Factor entry model
# ---------------------------------------------------------------------------


class FactorEntry(BaseModel):
    """Single factor definition from a domain pack factor catalog.

    All fields are validated strictly; extra fields are rejected.
    The model is immutable (frozen=True).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    value_type: FactorValueType
    polarity: FactorPolarity
    requires_evidence: bool = True
    maps_to_outcomes: List[str]
    description: str

    # Optional: present on numeric *_days factors (value_type=duration or number).
    # Only "log_days" is a legal value; other strategies will be added here when needed.
    bucket_strategy: Optional[Literal["log_days"]] = None

    # Optional: present on enum factors
    enum_values: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Factor catalog model
# ---------------------------------------------------------------------------


class FactorCatalog(BaseModel):
    """A collection of FactorEntry items loaded from a YAML file.

    Immutable; extra fields rejected.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    factors: List[FactorEntry]

    # ---------------------------------------------------------------------------
    # Class-method loader
    # ---------------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Path | str) -> "FactorCatalog":
        """Load a FactorCatalog from a YAML file.

        Parameters
        ----------
        path:
            Filesystem path to the YAML file.

        Returns
        -------
        FactorCatalog
            Validated, immutable catalog.

        Raises
        ------
        ValueError
            If the YAML cannot be parsed, is empty, or fails Pydantic validation.
        """
        path = Path(path)
        try:
            with path.open("r", encoding="utf-8") as fh:
                data: Any = yaml.safe_load(fh)
        except FileNotFoundError as exc:
            raise ValueError(f"Factor catalog file not found: {path}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML parse error in {path}: {exc}") from exc

        if data is None:
            raise ValueError(f"YAML file is empty: {path}")
        if not isinstance(data, dict):
            raise ValueError(
                f"YAML file {path} must contain a mapping at top level, "
                f"got {type(data).__name__}"
            )

        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ValueError(
                f"Factor catalog validation failed for {path.name}:\n{exc}"
            ) from exc


# ===========================================================================
# OutcomeSchema
# ===========================================================================


class OutcomeEntry(BaseModel):
    """Single outcome definition from outcomes.yaml."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    description: str


class OutcomeSchema(BaseModel):
    """Closed outcome ID list for a domain pack.

    Immutable; extra fields rejected.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_id: str
    outcomes: List[OutcomeEntry]

    @classmethod
    def from_yaml(cls, path: "Path | str") -> "OutcomeSchema":
        """Load an OutcomeSchema from a YAML file.

        Raises
        ------
        ValueError
            If the file is missing, unparseable, empty, or fails validation.
        """
        path = Path(path)
        try:
            with path.open("r", encoding="utf-8") as fh:
                data: Any = yaml.safe_load(fh)
        except FileNotFoundError as exc:
            raise ValueError(f"Outcomes YAML file not found: {path}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML parse error in {path}: {exc}") from exc

        if data is None:
            raise ValueError(f"YAML file is empty: {path}")
        if not isinstance(data, dict):
            raise ValueError(
                f"YAML file {path} must contain a mapping at top level, "
                f"got {type(data).__name__}"
            )

        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ValueError(
                f"OutcomeSchema validation failed for {path.name}:\n{exc}"
            ) from exc


# ===========================================================================
# RemedySchema
# ===========================================================================


class RemedyEntry(BaseModel):
    """Single remedy definition from remedies.yaml."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    description: str


class RemedySchema(BaseModel):
    """Closed remedy ID list for a domain pack.

    Immutable; extra fields rejected.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_id: str
    remedies: List[RemedyEntry]

    @classmethod
    def from_yaml(cls, path: "Path | str") -> "RemedySchema":
        """Load a RemedySchema from a YAML file.

        Raises
        ------
        ValueError
            If the file is missing, unparseable, empty, or fails validation.
        """
        path = Path(path)
        try:
            with path.open("r", encoding="utf-8") as fh:
                data: Any = yaml.safe_load(fh)
        except FileNotFoundError as exc:
            raise ValueError(f"Remedies YAML file not found: {path}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML parse error in {path}: {exc}") from exc

        if data is None:
            raise ValueError(f"YAML file is empty: {path}")
        if not isinstance(data, dict):
            raise ValueError(
                f"YAML file {path} must contain a mapping at top level, "
                f"got {type(data).__name__}"
            )

        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ValueError(
                f"RemedySchema validation failed for {path.name}:\n{exc}"
            ) from exc


# ===========================================================================
# RetrievalProfile
# ===========================================================================


class ComparatorWeights(BaseModel):
    """Per-spec §9.2 comparator pass weights. Must sum to 1.0 within 1e-6 tolerance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    factor_overlap: float
    text_relevance: float
    outcome_component_match: float
    remedy_similarity: float
    authority_level_match: float
    chronology_match: float
    claim_head_exact_match: float

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> "ComparatorWeights":
        total = (
            self.factor_overlap
            + self.text_relevance
            + self.outcome_component_match
            + self.remedy_similarity
            + self.authority_level_match
            + self.chronology_match
            + self.claim_head_exact_match
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"comparator_weights must sum to 1.0 (got {total:.8f})"
            )
        return self


class CounterexampleConfig(BaseModel):
    """Per-spec §9.3 counterexample pass configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    n_counterexamples: int = Field(ge=1)
    k_overlap_min: int = Field(ge=1)
    abstain_if_none: bool


class MoneyBucketDef(BaseModel):
    """Bucket definition for monetary amounts (pence)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: Literal["log_pence"]
    bucket_edges_pence: List[int]


class DurationBucketDef(BaseModel):
    """Bucket definition for durations (days)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: Literal["log_days"]
    bucket_edges_days: List[int]


class DateBucketDef(BaseModel):
    """Bucket definition for date proximity scoring."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: Literal["granularity"]
    same_year_score: float
    same_month_score: float
    other_score: float


class BucketDefinitions(BaseModel):
    """Container for all bucket definition sub-models."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    money: MoneyBucketDef
    duration: DurationBucketDef
    date: DateBucketDef


class RetrievalProfile(BaseModel):
    """Retrieval hyperparameters for the comparator pass.

    Per spec §9.2, §9.2.1, §9.3. Immutable; extra fields rejected.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_id: str
    comparator_weights: ComparatorWeights
    counterexample: CounterexampleConfig
    bucket_definitions: BucketDefinitions
    notes: Optional[List[str]] = None

    @classmethod
    def from_yaml(cls, path: "Path | str") -> "RetrievalProfile":
        """Load a RetrievalProfile from a YAML file.

        Raises
        ------
        ValueError
            If the file is missing, unparseable, empty, or fails validation.
        """
        path = Path(path)
        try:
            with path.open("r", encoding="utf-8") as fh:
                data: Any = yaml.safe_load(fh)
        except FileNotFoundError as exc:
            raise ValueError(f"Retrieval profile YAML file not found: {path}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML parse error in {path}: {exc}") from exc

        if data is None:
            raise ValueError(f"YAML file is empty: {path}")
        if not isinstance(data, dict):
            raise ValueError(
                f"YAML file {path} must contain a mapping at top level, "
                f"got {type(data).__name__}"
            )

        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ValueError(
                f"RetrievalProfile validation failed for {path.name}:\n{exc}"
            ) from exc


# ===========================================================================
# GraphQualityGate
# ===========================================================================


class GraphQualityGate(BaseModel):
    """Per-domain graph quality thresholds.

    Per spec §8.1. Immutable; extra fields rejected.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_id: str
    evidence_backed_factor_count_min: int = Field(ge=0)
    dated_event_count_min: int = Field(ge=0)
    issue_count_min: int = Field(ge=0)
    outcome_or_remedy_candidate_count_min: int = Field(ge=0)
    unsupported_factor_rate_max: float = Field(ge=0.0, le=1.0)
    source_span_coverage_min: float = Field(ge=0.0, le=1.0)
    contradiction_count_max: int = Field(ge=0)
    notes: Optional[List[str]] = None

    @classmethod
    def from_yaml(cls, path: "Path | str") -> "GraphQualityGate":
        """Load a GraphQualityGate from a YAML file.

        Raises
        ------
        ValueError
            If the file is missing, unparseable, empty, or fails validation.
        """
        path = Path(path)
        try:
            with path.open("r", encoding="utf-8") as fh:
                data: Any = yaml.safe_load(fh)
        except FileNotFoundError as exc:
            raise ValueError(f"Graph quality gate YAML file not found: {path}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML parse error in {path}: {exc}") from exc

        if data is None:
            raise ValueError(f"YAML file is empty: {path}")
        if not isinstance(data, dict):
            raise ValueError(
                f"YAML file {path} must contain a mapping at top level, "
                f"got {type(data).__name__}"
            )

        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ValueError(
                f"GraphQualityGate validation failed for {path.name}:\n{exc}"
            ) from exc
