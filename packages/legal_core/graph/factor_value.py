"""FactorValue: typed value carrier for FactorAssertion (spec section 4.1).

Exactly one typed payload category is populated, matching ``value_type``.
Money is carried as integer minor units (GBP pence) to avoid float drift.
Currency is restricted to GBP for now; extend explicitly when needed.
"""

from __future__ import annotations

from datetime import date as _date
from enum import Enum
from typing import ClassVar, Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class FactorValueType(str, Enum):
    """Discriminator for FactorValue's typed payload."""

    BOOLEAN = "boolean"
    ENUM = "enum"
    NUMBER = "number"
    MONEY = "money"
    DATE = "date"
    DURATION = "duration"


class FactorValue(BaseModel):
    """Typed value carrier with a discriminator-matched payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value_type: FactorValueType

    boolean: Optional[bool] = None
    enum: Optional[str] = None
    number: Optional[float] = None
    money_minor_units: Optional[int] = None
    money_currency: Optional[Literal["GBP"]] = None
    date: Optional[_date] = None
    duration_days: Optional[int] = None

    _TYPE_TO_FIELDS: ClassVar[dict[FactorValueType, tuple[str, ...]]] = {
        FactorValueType.BOOLEAN: ("boolean",),
        FactorValueType.ENUM: ("enum",),
        FactorValueType.NUMBER: ("number",),
        FactorValueType.MONEY: ("money_minor_units", "money_currency"),
        FactorValueType.DATE: ("date",),
        FactorValueType.DURATION: ("duration_days",),
    }

    _ALL_TYPED_FIELDS: ClassVar[tuple[str, ...]] = (
        "boolean",
        "enum",
        "number",
        "money_minor_units",
        "money_currency",
        "date",
        "duration_days",
    )

    @model_validator(mode="after")
    def _validate_typed_payload(self) -> "FactorValue":
        required = type(self)._TYPE_TO_FIELDS[self.value_type]
        for field_name in required:
            if getattr(self, field_name) is None:
                raise ValueError(
                    f"value_type={self.value_type.value!r} requires "
                    f"{field_name!r} to be populated"
                )

        for field_name in type(self)._ALL_TYPED_FIELDS:
            if field_name in required:
                continue
            if getattr(self, field_name) is not None:
                raise ValueError(
                    f"value_type={self.value_type.value!r} forbids "
                    f"populating {field_name!r}; got "
                    f"{getattr(self, field_name)!r}"
                )
        return self
