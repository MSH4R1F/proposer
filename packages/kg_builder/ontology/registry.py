"""Ontology spec registry: load YAML files in ``kg_builder/ontology/``.

The registry loads all ``*_v1.yaml`` files (and any future ``*_vN.yaml``),
parses them into :class:`OntologySpec` instances, resolves the optional
``extends`` chain by merging the parent's ``node_kinds`` and ``edge_kinds``
into the child, and exposes lookup helpers.

Hash semantics mirror :func:`packages.domain_core.hashing.hash_domain_spec`:
canonical JSON, recursively-sorted keys, list order preserved.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import ValidationError

from kg_builder.ontology.spec import OntologySpec

_ONTOLOGY_DIR = Path(__file__).resolve().parent


class OntologyConfigError(ValueError):
    """Raised when an ontology YAML fails to load or validate."""


class OntologyNotFoundError(LookupError):
    """Raised when ``get_ontology(id)`` cannot find a registered id."""


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


def _expected_filename_stem(ontology_id: str) -> str:
    """``housing.deposit.v1`` -> ``housing_deposit_v1``."""
    return ontology_id.replace(".", "_")


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise OntologyConfigError(
            f"YAML parse error in {path}: {exc}"
        ) from exc
    if data is None:
        raise OntologyConfigError(f"YAML file is empty: {path}")
    if not isinstance(data, dict):
        raise OntologyConfigError(
            f"YAML file {path} must be a mapping, got {type(data).__name__}"
        )
    return data


def _build_spec(path: Path, data: Dict[str, Any]) -> OntologySpec:
    try:
        return OntologySpec.model_validate(data)
    except ValidationError as exc:
        raise OntologyConfigError(
            f"Ontology spec validation failed for {path.name}:\n{exc}"
        ) from exc


def _validate_filename_consistency(path: Path, spec: OntologySpec) -> None:
    expected_stem = _expected_filename_stem(spec.id)
    if path.stem != expected_stem:
        raise OntologyConfigError(
            f"Ontology file {path.name} has id {spec.id!r}; "
            f"expected filename stem {expected_stem!r} (got {path.stem!r})"
        )


# ---------------------------------------------------------------------------
# extends chain resolution
# ---------------------------------------------------------------------------


def _resolve_extends(
    spec: OntologySpec, raw_specs: Dict[str, OntologySpec]
) -> OntologySpec:
    """Return a new OntologySpec whose node_kinds/edge_kinds include parents'.

    Detects cycles (raises). Child entries override parent entries with the
    same name. ``cross_domain_bridges`` from the parent are merged in.
    """
    seen: List[str] = [spec.id]
    chain: List[OntologySpec] = [spec]
    cur = spec
    while cur.extends is not None:
        parent_id = cur.extends
        if parent_id in seen:
            raise OntologyConfigError(
                f"Ontology extends cycle detected: {seen + [parent_id]}"
            )
        if parent_id not in raw_specs:
            raise OntologyConfigError(
                f"Ontology {cur.id!r} extends unknown id {parent_id!r}; "
                f"known: {sorted(raw_specs.keys())}"
            )
        seen.append(parent_id)
        cur = raw_specs[parent_id]
        chain.append(cur)

    # Merge from root down so children override parents. Node kinds are
    # keyed by name; edge kinds by (name, from_kind, to_kind) triple so
    # the same logical edge name can target multiple kind pairs.
    merged_nodes: Dict[str, Any] = {}
    merged_edges: Dict[Any, Any] = {}
    merged_bridges: List[str] = []
    for node in reversed(chain):
        for n in node.node_kinds:
            merged_nodes[n.name] = n
        for e in node.edge_kinds:
            merged_edges[(e.name, e.from_kind, e.to_kind)] = e
        for b in node.cross_domain_bridges:
            if b not in merged_bridges:
                merged_bridges.append(b)

    # Validate cross_domain_bridges against the *merged* edge name set.
    declared_edge_names = {e.name for e in merged_edges.values()}
    unknown_bridges = [
        b for b in merged_bridges if b not in declared_edge_names
    ]
    if unknown_bridges:
        raise OntologyConfigError(
            f"Ontology {spec.id!r} cross_domain_bridges references unknown "
            f"edge kinds: {unknown_bridges} "
            f"(declared after merge: {sorted(declared_edge_names)})"
        )

    # Construct merged spec — keep the child's id, schema_version, description.
    return OntologySpec(
        id=spec.id,
        schema_version=spec.schema_version,
        extends=spec.extends,
        description=spec.description,
        node_kinds=list(merged_nodes.values()),
        edge_kinds=list(merged_edges.values()),
        cross_domain_bridges=merged_bridges,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_ontology(
    ontology_dir: Optional[Path] = None,
) -> Dict[str, OntologySpec]:
    """Load all ontology YAMLs and return ``{id: resolved_spec}``.

    The returned specs have their ``extends`` chains resolved (merged
    node/edge kinds). The raw (unresolved) ``base.v1`` is also returned so
    that the validator can still introspect it directly.
    """
    base = Path(ontology_dir) if ontology_dir else _ONTOLOGY_DIR
    if not base.is_dir():
        raise OntologyConfigError(f"Ontology directory not found: {base}")

    raw: Dict[str, OntologySpec] = {}
    files: List[Path] = []
    for yaml_path in sorted(base.glob("*.yaml")):
        if yaml_path.name.startswith("_") or yaml_path.name.startswith("."):
            continue
        data = _load_yaml_file(yaml_path)
        spec = _build_spec(yaml_path, data)
        _validate_filename_consistency(yaml_path, spec)
        if spec.id in raw:
            raise OntologyConfigError(
                f"Duplicate ontology id {spec.id!r} in {yaml_path.name}"
            )
        raw[spec.id] = spec
        files.append(yaml_path)

    # Resolve extends for each
    resolved: Dict[str, OntologySpec] = {}
    for oid, spec in raw.items():
        resolved[oid] = _resolve_extends(spec, raw)

    return resolved


@lru_cache(maxsize=1)
def _cached_load() -> Dict[str, OntologySpec]:
    return load_ontology()


def get_ontology(ontology_id: str) -> OntologySpec:
    """Return the resolved :class:`OntologySpec` for ``ontology_id``.

    Raises :class:`OntologyNotFoundError` if the id is not registered.
    """
    specs = _cached_load()
    if ontology_id not in specs:
        raise OntologyNotFoundError(
            f"Unknown ontology_id {ontology_id!r}; "
            f"registered: {sorted(specs.keys())}"
        )
    return specs[ontology_id]


def list_ontologies() -> List[OntologySpec]:
    """List all registered (resolved) ontology specs."""
    return list(_cached_load().values())


def reset_ontology_cache() -> None:
    """Drop the cached load. Tests should call this between runs."""
    _cached_load.cache_clear()


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canonicalize(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [_canonicalize(v) for v in value]
    if isinstance(value, tuple):
        return [_canonicalize(v) for v in value]
    return value


def hash_ontology_spec(spec: OntologySpec) -> str:
    """Stable hex SHA-256 of the canonicalized OntologySpec.

    Mirrors :func:`packages.domain_core.hashing.hash_domain_spec` so callers
    can use the same JSON canonicalization rules across repos.
    """
    canonical = _canonicalize(spec.to_canonical_dict())
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
