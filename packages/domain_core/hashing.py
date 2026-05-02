"""Stable hashing of a DomainSpec.

The hash is computed from canonical JSON: keys sorted recursively, no
whitespace, ASCII-only output. YAML comments, whitespace, key order, and
absolute machine paths must NOT change the hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from domain_core.spec import DomainSpec


def _canonicalize(value: Any) -> Any:
    """Coerce a value into a canonical, JSON-serializable form.

    - Pydantic models -> dict (via model_dump with mode='json' for enum/Path).
    - Enums -> their `.value` (handled by mode='json').
    - Lists -> recursively canonicalized lists (preserves order: list order is
      semantically meaningful here, e.g. forum order in a profile).
    - Dicts -> recursively canonicalized with sorted keys.
    """
    if isinstance(value, dict):
        return {k: _canonicalize(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [_canonicalize(v) for v in value]
    if isinstance(value, tuple):
        return [_canonicalize(v) for v in value]
    return value


def canonical_spec_dict(spec: DomainSpec) -> dict:
    """Return the canonical dict form used as the hash input."""
    raw = spec.model_dump(mode="json")
    return _canonicalize(raw)


def hash_domain_spec(spec: DomainSpec) -> str:
    """Return a stable hex SHA-256 of ``spec``.

    Stable across:

    - YAML comment changes
    - YAML whitespace changes
    - YAML key reordering
    - List rendering style ([a, b] vs block form)

    NOT stable across (intentionally):

    - actual semantic field changes
    - reordering of lists (forum order matters)
    """
    canonical = canonical_spec_dict(spec)
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
