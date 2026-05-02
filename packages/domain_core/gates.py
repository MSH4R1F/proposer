"""Launch-gate artifact placeholder.

The signing/verification implementation is deferred to SHA-122. We define
the model here so other packages can already type-check against it. A
``GateArtifact`` is the on-disk JSON record at
``data/eval_artifacts/domain_gates/<domain_id>.json`` once SHA-122 lands.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GateArtifact(BaseModel):
    """Immutable record of a passing eval run for a domain launch gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_id: str
    domain_spec_hash: str
    eval_run_id: str
    eval_timestamp: str  # ISO-8601
    gold_set_path: str
    gold_set_sha256: str
    metrics: Dict[str, float]
    passed_metrics: List[str] = Field(default_factory=list)
    failed_metrics: List[str] = Field(default_factory=list)
    signed_by_key_id: Optional[str] = None
    signature_b64: Optional[str] = None
    notes: Optional[str] = None
