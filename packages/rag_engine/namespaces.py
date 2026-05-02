"""SHA-20 Phase 4: namespace resolution + cross-domain guard.

Maps a :class:`domain_core.spec.RetrievalNamespace` (declared in a domain
YAML) to the runtime path / collection bindings used by Chroma and BM25.

Cutover policy
--------------
* New corpus versions are *built side-by-side* under a new
  ``corpus_version`` label (e.g. ``2026Q2_te3s``). The Chroma collection
  name and BM25 path encode that version.
* Runtime traffic stays on the previous approved
  ``(namespace_id, corpus_version)`` until the gate artifact is published
  (Phase 7).
* At least the latest two approved corpus versions, plus any version
  referenced by persisted predictions, must be retained.
* Old collections are deleted only via an explicit cleanup CLI.

  TODO Phase 8: cleanup CLI for retired ``(namespace_id, corpus_version)``
  pairs. Until then, leave old collections alone.

Embedding-model encoding
------------------------
``te3s`` in path/collection names is shorthand for the OpenAI embedding
model ``text-embedding-3-small``. Embedding-model changes are *not*
backward compatible (vectors are model-specific), so the convention is
that the ``corpus_version`` label *must* encode the embedding model.
:func:`RAGConfig.from_namespace` enforces this by failing fast when the
namespace's embedding-model encoding diverges from the live config.

Cross-domain retrieval
----------------------
Cross-domain retrieval is impossible by default. The path that allows it
requires *both*:

* ``cross_domain_allowed=True`` on the :class:`RetrievalNamespace`
  (encoded in the domain YAML), AND
* ``eval_only=True`` passed at the call site (Phase 7 eval runner).

Otherwise :class:`CrossDomainRetrievalNotAllowed` is raised.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from domain_core.spec import RetrievalNamespace

if TYPE_CHECKING:  # pragma: no cover
    from .config import RAGConfig

# Legacy compatibility constants ---------------------------------------------

#: Legacy Chroma collection that holds the deposit corpus today (audit D1).
LEGACY_DEPOSIT_COLLECTION = "tribunal_cases"

#: Legacy BM25 path that the deposit pipeline must keep using by default.
LEGACY_DEPOSIT_BM25_PATH = "data/embeddings/bm25_index.pkl"

#: Legacy corpus_version label for the pre-SHA-20 deposit snapshot.
LEGACY_DEPOSIT_CORPUS_VERSION = "legacy_2025_pre_sha20"

#: Embedding-model shorthand used in namespace identifiers and paths.
#: ``te3s`` => OpenAI ``text-embedding-3-small``.
EMBED_MODEL_TAG_TE3S = "te3s"
EMBED_MODEL_NAME_TE3S = "text-embedding-3-small"

# Map shorthand <-> full model id.
EMBED_TAG_TO_MODEL = {EMBED_MODEL_TAG_TE3S: EMBED_MODEL_NAME_TE3S}
MODEL_TO_EMBED_TAG = {v: k for k, v in EMBED_TAG_TO_MODEL.items()}


class CrossDomainRetrievalNotAllowed(RuntimeError):
    """Raised when a retrieval call attempts to cross domain boundaries
    without satisfying both ``cross_domain_allowed`` (namespace) and
    ``eval_only`` (call-site) preconditions.
    """


class EmbeddingModelMismatch(RuntimeError):
    """Raised when a namespace's declared embedding model does not match
    the live :class:`RAGConfig`. Embedding changes require a full corpus
    rebuild, so we fail fast rather than silently mixing vectors.
    """


def is_legacy_deposit_namespace(ns: RetrievalNamespace) -> bool:
    """Return True iff this namespace is the legacy deposit binding.

    A namespace is legacy iff it points at the historical ``tribunal_cases``
    Chroma collection AND the legacy BM25 pickle. We use both checks
    instead of just the namespace_id so that any domain spec can opt into
    the legacy compat path simply by declaring those values.
    """
    return (
        ns.vector_collection == LEGACY_DEPOSIT_COLLECTION
        and Path(ns.bm25_index_path).as_posix() == LEGACY_DEPOSIT_BM25_PATH
    )


def _extract_embed_tag(value: str) -> Optional[str]:
    """Pull a known embedding-model tag (e.g. ``te3s``) out of a string."""
    for tag in EMBED_TAG_TO_MODEL:
        if re.search(rf"(?:^|[_\-./]){re.escape(tag)}(?:$|[_\-./])", value):
            return tag
    return None


def resolve_embedding_model(ns: RetrievalNamespace) -> Optional[str]:
    """Return the OpenAI embedding model implied by a namespace.

    Looks at (in order) the ``corpus_version`` label, the namespace_id,
    and the vector_collection name for a known embedding-model tag.
    Returns ``None`` if nothing is encoded — the caller decides whether
    that is acceptable (the legacy deposit namespace predates this
    convention, so it returns ``None``).
    """
    for candidate in (ns.corpus_version, ns.namespace_id, ns.vector_collection):
        if not candidate:
            continue
        tag = _extract_embed_tag(candidate)
        if tag:
            return EMBED_TAG_TO_MODEL[tag]
    return None


def bm25_index_path_for(ns: RetrievalNamespace, project_root: Path) -> Path:
    """Resolve the on-disk BM25 index path for a namespace.

    * Legacy deposit: ``<root>/data/embeddings/bm25_index.pkl``.
    * Otherwise: ``<root>/data/indices/{namespace_id}/{corpus_version}/bm25.pkl``.
    """
    project_root = Path(project_root)
    if is_legacy_deposit_namespace(ns):
        return project_root / LEGACY_DEPOSIT_BM25_PATH
    cv = ns.corpus_version or "unversioned"
    return project_root / "data" / "indices" / ns.namespace_id / cv / "bm25.pkl"


def vector_collection_for(ns: RetrievalNamespace) -> str:
    """Return the Chroma collection name for a namespace.

    The namespace YAML is authoritative — for the legacy deposit binding
    this is literally ``tribunal_cases``; for new namespaces it is
    typically ``{namespace_id}__{corpus_version}``.
    """
    return ns.vector_collection


def assert_cross_domain_allowed(
    *,
    target_namespace: RetrievalNamespace,
    requesting_namespace: Optional[RetrievalNamespace],
    cross_domain_allowed: bool,
    eval_only: bool,
) -> None:
    """Raise :class:`CrossDomainRetrievalNotAllowed` when the call would
    bridge two namespaces without proper authorization.

    Both flags must be true and the target namespace must explicitly
    list the requester's id in ``allowed_cross_namespace_ids``.
    """
    if requesting_namespace is None:
        return
    if requesting_namespace.namespace_id == target_namespace.namespace_id:
        return  # same namespace; no cross-domain hop

    if not cross_domain_allowed:
        raise CrossDomainRetrievalNotAllowed(
            "cross-domain retrieval requires eval_only=True and "
            "cross_domain_allowed=True; cross_domain_allowed was False"
        )
    if not eval_only:
        raise CrossDomainRetrievalNotAllowed(
            "cross-domain retrieval requires eval_only=True"
        )
    if (
        requesting_namespace.namespace_id
        not in target_namespace.allowed_cross_namespace_ids
    ):
        raise CrossDomainRetrievalNotAllowed(
            f"namespace {target_namespace.namespace_id!r} does not list "
            f"{requesting_namespace.namespace_id!r} in "
            "allowed_cross_namespace_ids"
        )


__all__ = [
    "CrossDomainRetrievalNotAllowed",
    "EmbeddingModelMismatch",
    "EMBED_MODEL_TAG_TE3S",
    "EMBED_MODEL_NAME_TE3S",
    "EMBED_TAG_TO_MODEL",
    "MODEL_TO_EMBED_TAG",
    "LEGACY_DEPOSIT_COLLECTION",
    "LEGACY_DEPOSIT_BM25_PATH",
    "LEGACY_DEPOSIT_CORPUS_VERSION",
    "is_legacy_deposit_namespace",
    "resolve_embedding_model",
    "bm25_index_path_for",
    "vector_collection_for",
    "assert_cross_domain_allowed",
]
