"""Runtime-context placeholder.

The full ``DomainRuntimeContext`` is composed by ``apps/api`` once
implementation packages have resolved ``ref://`` URIs into concrete classes.
This module just declares the shape so that ``domain_core`` consumers can
type-hint the eventual context without importing implementation packages.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from domain_core.spec import DomainSpec


class DomainRuntimeContext(BaseModel):
    """Composed runtime context for a domain.

    Implementation packages plug in ``intake_schema``, ``case_file_adapter``,
    ``ontology``, ``prompt_pack``, and ``rag_pipeline`` instances. We keep
    them typed as ``Any`` here because typing them concretely would force
    cross-package imports that would break the leaf-dependency invariant.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    spec: DomainSpec
    intake_schema: Optional[Any] = None
    case_file_adapter: Optional[Any] = None
    ontology: Optional[Any] = None
    prompt_pack: Optional[Any] = None
    rag_pipeline: Optional[Any] = None
