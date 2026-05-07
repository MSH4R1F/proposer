"""domain_core: leaf-dependency contracts for multi-domain architecture (SHA-20).

This package MUST remain a leaf dependency. It must not import from
``rag_engine``, ``kg_builder``, ``llm_orchestrator``, ``eval``,
``apps.api``, ``apps.web``, or ``scripts``. Cross-checked by
``tests/test_import_boundary.py``.
"""

from domain_core.errors import (
    DomainConfigError,
    DomainError,
    DomainGateError,
    DomainNotFoundError,
)
from domain_core.gates import GateArtifact
from domain_core.hashing import hash_domain_spec
from domain_core.ids import DomainFamily, DomainId
from domain_core.pack_refs import PackReferenceSet, warn_if_missing
from domain_core.registry import (
    get_domain_spec,
    list_domain_specs,
    load_domain_specs,
)
from domain_core.routing import DomainRoute
from domain_core.runtime import DomainRuntimeContext
from domain_core.spec import (
    CitationKind,
    DomainSpec,
    EvalGate,
    Forum,
    ForumProfile,
    LaunchStage,
    RetrievalNamespace,
    SourceKind,
    SourcePublisher,
)

__all__ = [
    "CitationKind",
    "DomainConfigError",
    "DomainError",
    "DomainFamily",
    "DomainGateError",
    "DomainId",
    "DomainNotFoundError",
    "DomainRoute",
    "DomainRuntimeContext",
    "DomainSpec",
    "EvalGate",
    "Forum",
    "ForumProfile",
    "GateArtifact",
    "LaunchStage",
    "PackReferenceSet",
    "RetrievalNamespace",
    "SourceKind",
    "SourcePublisher",
    "get_domain_spec",
    "hash_domain_spec",
    "list_domain_specs",
    "load_domain_specs",
    "warn_if_missing",
]
