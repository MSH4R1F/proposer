"""Shared helpers for projecting SHA-124 domain metadata from canonical payloads.

The Pydantic models (ConversationState, DisputeCase, PredictionResult, etc.)
do not yet expose dedicated domain-routing fields. Until they do, repositories
project domain metadata from a known dotted location inside the canonical
``payload``/``metadata`` blob, falling back to the Phase 0 audit's D1 default
(``housing.deposit.v1`` / ``v1`` / ``[]`` / ``{}``).

Both write and read paths use these helpers so the projection columns and the
canonical payload stay in sync. Existing rows that pre-date this migration
were backfilled to the same defaults by Alembic revision 0002.
"""

from __future__ import annotations

from typing import Any

DEFAULT_DOMAIN_ID = "housing.deposit.v1"
DEFAULT_DOMAIN_VERSION = "v1"


def _coerce_str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _domain_section(payload: dict[str, Any]) -> dict[str, Any]:
    """Find the ``domain`` block inside payload or its ``metadata`` sub-object."""
    section = payload.get("domain")
    if isinstance(section, dict):
        return section
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        nested = metadata.get("domain")
        if isinstance(nested, dict):
            return nested
    return {}


def _top_level_domain_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Phase 3: read domain fields directly off the Pydantic-dumped top level.

    Models that gained dedicated fields (``ConversationState``, ``DisputeCase``,
    ``PredictionResult``, ``MediationSession``, ``EvidenceMetadata``,
    ``KnowledgeGraph``) put the values at top level. The projection helper
    prefers these over the legacy ``payload["domain"]`` block while still
    falling back to it for any older rows.
    """
    keys = {
        "domain_id",
        "domain_version",
        "forum",
        "matter_types",
        "routing_confidence",
        "routing_metadata",
        "domain_spec_hash",
        "prompt_pack_hash",
        "ontology_hash",
        "corpus_version",
    }
    out: dict[str, Any] = {}
    for k in keys:
        if k in payload:
            out[k] = payload[k]
    # Also read CaseFile-nested fields for ConversationState payloads.
    case_file = payload.get("case_file") if isinstance(payload, dict) else None
    if isinstance(case_file, dict):
        for k in keys:
            if k in case_file and k not in out:
                out[k] = case_file[k]
    return out


def extract_domain_block(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return a fully-defaulted domain-routing dict for a row's projections.

    Always returns the same keys: ``domain_id``, ``domain_version``,
    ``matter_types``, ``routing_confidence``, ``routing_metadata``.
    """
    payload = payload or {}
    top = _top_level_domain_fields(payload)
    section = _domain_section(payload)

    def _pick(key: str, coerce):
        # Prefer top-level Pydantic field; fall back to legacy domain block.
        if key in top:
            value = coerce(top[key])
            if value is not None and value != "" and value != []:
                return value
        return coerce(section.get(key))

    domain_id = _coerce_str(top.get("domain_id")) or _coerce_str(section.get("domain_id")) or DEFAULT_DOMAIN_ID
    domain_version = (
        _coerce_str(top.get("domain_version"))
        or _coerce_str(section.get("domain_version"))
        or DEFAULT_DOMAIN_VERSION
    )
    matter_types = _coerce_list(top.get("matter_types") if "matter_types" in top else section.get("matter_types"))
    routing_confidence = _coerce_float(
        top.get("routing_confidence") if "routing_confidence" in top else section.get("routing_confidence")
    )
    routing_metadata = _coerce_dict(
        top.get("routing_metadata") if "routing_metadata" in top else section.get("routing_metadata")
    )
    return {
        "domain_id": domain_id,
        "domain_version": domain_version,
        "matter_types": matter_types,
        "routing_confidence": routing_confidence,
        "routing_metadata": routing_metadata,
    }


def extract_forum(payload: dict[str, Any] | None) -> str | None:
    """Return the ``forum`` value from the top-level field or domain section.

    The Phase 0 audit explicitly forbids guessing a forum for legacy rows.
    """
    payload = payload or {}
    top = _top_level_domain_fields(payload)
    if "forum" in top:
        return _coerce_str(top.get("forum"))
    section = _domain_section(payload)
    return _coerce_str(section.get("forum"))


def extract_reproducibility_hashes(payload: dict[str, Any] | None) -> dict[str, str | None]:
    """Return the four reproducibility hashes from the payload.

    Phase 3: hashes are stored as Pydantic fields at the top level of
    ``PredictionResult`` and ``KnowledgeGraph``. The legacy fallback path
    (``payload["domain"]`` / ``payload["pipeline_metadata"]``) is preserved so
    that already-persisted rows continue to project unchanged.
    """
    payload = payload or {}
    top = _top_level_domain_fields(payload)
    section = _domain_section(payload)
    pipeline_meta = payload.get("pipeline_metadata") if isinstance(payload, dict) else None
    if not isinstance(pipeline_meta, dict):
        pipeline_meta = {}

    def _pick(key: str) -> str | None:
        return (
            _coerce_str(top.get(key))
            or _coerce_str(section.get(key))
            or _coerce_str(pipeline_meta.get(key))
        )

    return {
        "domain_spec_hash": _pick("domain_spec_hash"),
        "prompt_pack_hash": _pick("prompt_pack_hash"),
        "ontology_hash": _pick("ontology_hash"),
        "corpus_version": _pick("corpus_version"),
    }


def extract_source_provenance(payload: dict[str, Any] | None) -> dict[str, str | None]:
    """Return ``source_kind``/``source_publisher``/``source_id`` from payload.

    Used by evidence_metadata and prediction_citations. Phase 3: prefers
    top-level Pydantic fields (``EvidenceMetadata.source_kind`` etc.) before
    falling back to ``payload["source"]`` and ``payload["domain"]["source"]``.
    """
    payload = payload or {}

    # Top-level field path (Phase 3 EvidenceMetadata).
    top_kind = _coerce_str(payload.get("source_kind"))
    top_publisher = _coerce_str(payload.get("source_publisher"))
    top_id = _coerce_str(payload.get("source_id"))

    section = payload.get("source")
    if not isinstance(section, dict):
        domain_section = _domain_section(payload)
        nested = domain_section.get("source")
        section = nested if isinstance(nested, dict) else {}
    return {
        "source_kind": top_kind
        or _coerce_str(section.get("source_kind") or section.get("kind")),
        "source_publisher": top_publisher
        or _coerce_str(section.get("source_publisher") or section.get("publisher")),
        "source_id": top_id
        or _coerce_str(section.get("source_id") or section.get("id")),
    }


def extract_citation_provenance(payload: dict[str, Any] | None) -> dict[str, str | None]:
    """Return the seven provenance columns for prediction_citations.

    Combines :func:`extract_source_provenance` with ``namespace_id``,
    ``canonical_url``, and ``source_license``.
    """
    payload = payload or {}
    base = extract_source_provenance(payload)
    section = payload.get("source")
    if not isinstance(section, dict):
        domain_section = _domain_section(payload)
        nested = domain_section.get("source")
        section = nested if isinstance(nested, dict) else {}
    base["namespace_id"] = _coerce_str(section.get("namespace_id"))
    base["canonical_url"] = _coerce_str(section.get("canonical_url"))
    base["source_license"] = _coerce_str(section.get("source_license") or section.get("license"))
    return base
