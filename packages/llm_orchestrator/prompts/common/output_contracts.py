"""Shared JSON output contract used by every per-issue prediction prompt.

This is a minimal envelope. Domain packs may extend ``required`` or
``properties`` with forum-specific fields, but the common keys below MUST be
present in every output schema so downstream verifiers and assemblers can
treat output uniformly.

The schema is intentionally a plain dict (not a pydantic model) so it stays
JSON-serialisable for ``hash_prompt_pack`` without import-time side effects.
"""

from __future__ import annotations

import copy
from typing import Any, Dict

OUTPUT_CONTRACT_VERSION = "1.0.0"


PREDICTION_OUTPUT_CONTRACT: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "PromptPackPredictionEnvelope",
    "type": "object",
    "required": [
        "issue_type",
        "outcome",
        "raw_confidence",
        "reasoning",
        "supporting_cases",
        "evidence_strength",
        "matter_type",
        "forum",
    ],
    "properties": {
        "issue_type": {"type": "string"},
        "issue_description": {"type": "string"},
        "outcome": {
            "type": "string",
            "enum": ["tenant_wins", "landlord_wins", "split", "uncertain"],
        },
        "raw_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "predicted_amount": {"type": ["number", "null"]},
        "reasoning": {"type": "string"},
        "key_factors": {"type": "array", "items": {"type": "string"}},
        "supporting_cases": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["case_reference"],
                "properties": {
                    "case_reference": {"type": "string"},
                    "year": {"type": ["integer", "null"]},
                    "quote": {"type": "string"},
                    "relevance": {"type": "string"},
                    "source_id": {"type": ["string", "null"]},
                    "source_kind": {"type": ["string", "null"]},
                    "cited_span": {"type": ["string", "null"]},
                    "citation_kind": {"type": ["string", "null"]},
                },
            },
        },
        "counterfactuals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "condition": {"type": "string"},
                    "alternative_outcome": {"type": "string"},
                    "confidence_shift": {"type": "number"},
                },
            },
        },
        "evidence_strength": {
            "type": "string",
            "enum": ["strong", "moderate", "weak", "insufficient"],
        },
        "data_completeness_impact": {"type": "string"},
        "matter_type": {"type": "string"},
        "forum": {"type": "string"},
        "calculator_trace": {
            "type": ["object", "null"],
            "description": (
                "When the predicted amount uses a deterministic calculator "
                "(e.g., basic-award formula, 1x-3x deposit penalty), the "
                "trace inputs and resulting figure go here."
            ),
        },
        "forum_policy_warnings": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Populated by the forum-policy verifier in research mode "
                "when violations were detected but not suppressed."
            ),
        },
    },
}


def render_output_contract() -> Dict[str, Any]:
    """Return a deep-copy of the envelope so packs can extend safely."""
    return copy.deepcopy(PREDICTION_OUTPUT_CONTRACT)
