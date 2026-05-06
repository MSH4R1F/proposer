"""domain_packs.loaders: Pydantic v2 loader for domain-pack factor catalogs.

Provides FactorCatalog and FactorEntry models. Loads from YAML via pyyaml.

Design notes:
- extra="forbid" + frozen=True on all models per task spec AC2/AC6.
- value_type and polarity use closed Literal unions so Pydantic v2 validates them.
- Numeric *_days factors must carry bucket_strategy: log_days.
- enum factors carry a closed enum_values list.

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §12
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError


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
