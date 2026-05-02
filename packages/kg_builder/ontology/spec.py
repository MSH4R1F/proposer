"""Pydantic v2 models for the KG ontology contract.

An :class:`OntologySpec` describes the allowed shape of a KnowledgeGraph
within a single domain: which node kinds may appear, which edge kinds may
connect them, and which (if any) edge kinds are permitted to bridge
between two domains. Hash-stable across YAML cosmetic changes (see
``packages/kg_builder/ontology/registry.py:hash_ontology_spec``).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Cardinality enum
# ---------------------------------------------------------------------------


class EdgeCardinality(str, Enum):
    """Allowed edge cardinalities."""

    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_MANY = "many_to_many"


# ---------------------------------------------------------------------------
# Node + edge kinds
# ---------------------------------------------------------------------------


class AllowedNodeKind(BaseModel):
    """A node kind that may appear in a graph for this ontology."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: Optional[str] = None
    attributes: List[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name_pattern(cls, v: str) -> str:
        if not v or not re.match(r"^[A-Z][A-Za-z0-9_]*$", v):
            raise ValueError(
                f"AllowedNodeKind.name must be PascalCase, got {v!r}"
            )
        return v


class AllowedEdgeKind(BaseModel):
    """An edge kind that may connect two node kinds in this ontology."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    from_kind: str
    to_kind: str
    cardinality: EdgeCardinality = EdgeCardinality.MANY_TO_MANY
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name_pattern(cls, v: str) -> str:
        if not v or not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(
                f"AllowedEdgeKind.name must be snake_case, got {v!r}"
            )
        return v


# ---------------------------------------------------------------------------
# OntologySpec
# ---------------------------------------------------------------------------


_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*\.v\d+$")


class OntologySpec(BaseModel):
    """The ontology contract loaded from YAML.

    See the per-domain ``*_v1.yaml`` files in this directory for examples.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    schema_version: int = 1
    extends: Optional[str] = None
    description: Optional[str] = None
    node_kinds: List[AllowedNodeKind] = Field(default_factory=list)
    edge_kinds: List[AllowedEdgeKind] = Field(default_factory=list)
    cross_domain_bridges: List[str] = Field(default_factory=list)

    @field_validator("id", "extends")
    @classmethod
    def _validate_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _ID_PATTERN.match(v):
            raise ValueError(
                f"ontology id must match '<dotted>.vN', got {v!r}"
            )
        return v

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, v: int) -> int:
        if v < 1:
            raise ValueError("schema_version must be >= 1")
        return v

    @model_validator(mode="after")
    def _validate_invariants(self) -> "OntologySpec":
        # No duplicate node kind names
        node_names = [n.name for n in self.node_kinds]
        if len(set(node_names)) != len(node_names):
            raise ValueError(
                f"OntologySpec.node_kinds has duplicates: {node_names}"
            )

        # Edge kinds: same name may be declared for different (from_kind,
        # to_kind) tuples (e.g. evidence_supports may target ClaimedAmount or
        # Issue). The (name, from_kind, to_kind) triple must be unique.
        edge_triples = [
            (e.name, e.from_kind, e.to_kind) for e in self.edge_kinds
        ]
        if len(set(edge_triples)) != len(edge_triples):
            raise ValueError(
                f"OntologySpec.edge_kinds has duplicate (name, from, to) "
                f"triples: {edge_triples}"
            )
        edge_names = [e.name for e in self.edge_kinds]

        # NOTE: cross_domain_bridges may reference edges declared by a
        # parent ontology via ``extends``. We therefore defer the
        # "bridges must point at declared edges" check to the registry,
        # which has the merged edge set. Local YAMLs that don't extend
        # anything are checked there too.

        return self

    # ---- helper accessors used by validators / registry ----

    def node_kind(self, name: str) -> Optional[AllowedNodeKind]:
        for n in self.node_kinds:
            if n.name == name:
                return n
        return None

    def edge_kind(self, name: str) -> Optional[AllowedEdgeKind]:
        for e in self.edge_kinds:
            if e.name == name:
                return e
        return None

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Canonical, JSON-safe dict used for hashing."""
        return self.model_dump(mode="json")
