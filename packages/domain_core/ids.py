"""Typed identifiers for domain_core.

``DomainId`` is intentionally a constrained string (regex pattern), NOT a closed
``Literal``. The point of the SHA-20 design is that domains are added by
dropping a YAML file in ``domain_core/domains/`` rather than editing code in
this leaf package.

``DomainFamily`` IS a closed enum because each new family changes routing,
ingestion, and product copy and warrants code review.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema


# Dotted shape: <family>.<sub_family>(.<sub_family>)*.<vN>
# Each segment is lowercase alphanumeric/underscore. Final segment is a version
# tag of the form vN (digits).
_DOMAIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+\.v\d+$")


class DomainId(str):
    """A constrained-string DomainId, e.g. ``housing.deposit.v1``.

    Validation rules (enforced at construction and via Pydantic v2):

    - Lowercase dotted form, at least three segments.
    - Final segment matches ``vN`` where N is one or more digits.
    - Intermediate segments are ``[a-z][a-z0-9_]*``.
    """

    __slots__ = ()

    def __new__(cls, value: str) -> "DomainId":
        if not isinstance(value, str):
            raise TypeError(f"DomainId must be str, got {type(value).__name__}")
        if not _DOMAIN_ID_PATTERN.match(value):
            raise ValueError(
                f"DomainId {value!r} does not match required pattern "
                f"{_DOMAIN_ID_PATTERN.pattern!r} "
                "(expected dotted lowercase with trailing .vN, "
                "e.g. 'housing.deposit.v1')"
            )
        return str.__new__(cls, value)

    @property
    def family(self) -> str:
        """Return the first segment of the id."""
        return self.split(".", 1)[0]

    @property
    def version(self) -> str:
        """Return the final segment (vN)."""
        return self.rsplit(".", 1)[-1]

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        # Validate inputs (str), coerce to DomainId on construction.
        return core_schema.no_info_after_validator_function(
            cls._validate,
            core_schema.str_schema(pattern=_DOMAIN_ID_PATTERN.pattern),
        )

    @classmethod
    def _validate(cls, value: str) -> "DomainId":
        if isinstance(value, cls):
            return value
        return cls(value)


class DomainFamily(str, Enum):
    """Closed enum of supported top-level domain families.

    Adding a new family is a code-review event because it changes ingestion
    and product copy. Sub-families remain configurable via ``DomainId``.
    """

    HOUSING = "housing"
    EMPLOYMENT = "employment"
