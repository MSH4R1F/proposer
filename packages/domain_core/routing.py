"""Routing model placeholder.

A ``DomainRoute`` describes how user-supplied intake input was classified to
a specific ``domain_id``. The classifier itself lives in ``apps/api``; this
package just types the route shape.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DomainRoute(BaseModel):
    """Result of intake routing to a domain."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    matched_signals: List[str] = Field(default_factory=list)
    fallback_used: bool = False
    note: Optional[str] = None
