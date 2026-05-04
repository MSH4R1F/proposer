"""
Configuration and data models for RAG Engine.

Handles environment variables, paths, and defines core data structures
used throughout the RAG pipeline.

SHA-20 Phase 4 additions:

* Optional :class:`SourceMetadata` on :class:`CaseDocument` and
  :class:`DocumentChunk` so multi-domain ingestion can carry the full
  Phase 4 metadata bag (forum, source_publisher, source_kind,
  corpus_version, etc.). Existing constructors that did not pass
  ``source_metadata`` keep working — the field defaults to ``None``.
* :class:`RetrievalFilterEnvelope` — the *single* filter shape that
  Chroma and BM25 must agree on. Hybrid retrieval is only correct when
  both backends apply the *same* filter set, so we route through one
  envelope rather than letting each backend interpret raw kwargs.
* :meth:`RAGConfig.from_namespace` — factory that opens the legacy
  ``tribunal_cases`` collection for the deposit namespace and a
  per-namespace path otherwise; fails fast on embedding-model mismatch.

``te3s`` in path/collection names is shorthand for the OpenAI embedding
model ``text-embedding-3-small`` (see ``rag_engine.namespaces``).
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator
from dotenv import load_dotenv

if TYPE_CHECKING:  # pragma: no cover
    from domain_core.spec import (
        Forum as _Forum,
        RetrievalNamespace as _RetrievalNamespace,
        SourceKind as _SourceKind,
        SourcePublisher as _SourcePublisher,
    )

load_dotenv()


class SectionType(str, Enum):
    """Types of sections in tribunal decisions."""
    BACKGROUND = "background"
    FACTS = "facts"
    REASONING = "reasoning"
    DECISION = "decision"
    UNKNOWN = "unknown"


class CaseDocument(BaseModel):
    """Represents a parsed tribunal case document."""

    case_reference: str = Field(..., description="Unique case identifier, e.g., LON_00BK_HMF_2022_0227")
    year: int = Field(..., ge=2000, le=2030, description="Year of decision")
    region: Optional[str] = Field(None, description="Tribunal region code, e.g., LON, CHI, MAN")
    region_name: Optional[str] = Field(None, description="Full region name, e.g., London")
    case_type: Optional[str] = Field(None, description="Case type code, e.g., HNA, HMF")
    case_type_name: Optional[str] = Field(None, description="Full case type name")
    title: Optional[str] = Field(None, description="Case title from document")
    decision_date: Optional[str] = Field(None, description="Date of decision (ISO format)")

    full_text: str = Field(..., description="Complete extracted text from PDF")
    sections: Dict[str, str] = Field(
        default_factory=dict,
        description="Document sections: background, facts, reasoning, decision"
    )

    source_path: str = Field(..., description="Path to source PDF file")
    metadata: Dict = Field(default_factory=dict, description="Additional metadata")

    # SHA-20 Phase 4: optional Phase-4 metadata bag. Default-None so
    # legacy callers that build CaseDocument without it keep working.
    source_metadata: Optional["SourceMetadata"] = Field(
        default=None,
        description=(
            "SHA-20 Phase 4 SourceMetadata bag. Optional for legacy callers; "
            "required for multi-domain ingestion paths."
        ),
    )

    @property
    def category(self) -> str:
        """Infer category from source path."""
        path_lower = self.source_path.lower()
        if "deposit" in path_lower:
            return "deposit"
        elif "adjacent" in path_lower:
            return "adjacent"
        return "other"


class DocumentChunk(BaseModel):
    """A chunk of text from a case document."""

    chunk_id: str = Field(..., description="Unique chunk identifier")
    case_reference: str = Field(..., description="Parent case reference")
    chunk_index: int = Field(..., ge=0, description="Position in document")

    text: str = Field(..., description="Chunk text content")
    section_type: SectionType = Field(
        default=SectionType.UNKNOWN,
        description="Which section this chunk belongs to"
    )

    # Metadata for filtering
    year: int = Field(..., description="Year of case")
    region: Optional[str] = Field(None, description="Region code")
    case_type: Optional[str] = Field(None, description="Case type code")

    # Token count for cost tracking
    token_count: int = Field(default=0, description="Approximate token count")

    # SHA-20 Phase 4: optional SourceMetadata. ``None`` means "legacy
    # deposit chunk" which is fine for the default deposit namespace.
    source_metadata: Optional["SourceMetadata"] = Field(
        default=None,
        description=(
            "SHA-20 Phase 4 SourceMetadata. Defaults to None for "
            "back-compat with legacy deposit ingestion."
        ),
    )

    def to_chroma_metadata(self) -> Dict:
        """Convert to ChromaDB-compatible metadata dict.

        Existing keys (``case_reference``, ``chunk_index``, ``section_type``,
        ``year``, ``region``, ``case_type``, ``token_count``) are preserved
        for backward compatibility with the legacy deposit collection.
        Phase 4 keys are merged in only when ``source_metadata`` is set.
        """
        out: Dict[str, Any] = {
            "case_reference": self.case_reference,
            "chunk_index": self.chunk_index,
            "section_type": self.section_type.value,
            "year": self.year,
            "region": self.region or "",
            "case_type": self.case_type or "",
            "token_count": self.token_count,
        }
        if self.source_metadata is not None:
            # Don't let Phase-4 keys clobber the legacy keys above.
            phase4 = self.source_metadata.to_chroma_metadata()
            for k, v in phase4.items():
                # case_reference is doubly-named — keep the legacy value
                # which always exists; only fill if missing.
                if k == "case_reference" and out.get("case_reference"):
                    continue
                out[k] = v
        return out


class RetrievalResult(BaseModel):
    """Result from hybrid retrieval with scoring details."""

    chunk_id: str = Field(..., description="Chunk identifier")
    case_reference: str = Field(..., description="Source case reference")
    chunk_text: str = Field(..., description="Retrieved text content")
    section_type: str = Field(..., description="Section type of chunk")

    # Scoring
    semantic_score: float = Field(..., ge=0, le=1, description="Cosine similarity score")
    semantic_rank: int = Field(..., ge=1, description="Rank in semantic results")
    bm25_score: float = Field(..., ge=0, description="BM25 relevance score")
    bm25_rank: int = Field(..., ge=1, description="Rank in BM25 results")
    combined_score: float = Field(..., ge=0, description="RRF combined score")

    # Metadata
    year: int = Field(..., description="Year of case")
    region: Optional[str] = Field(None, description="Region code")
    case_type: Optional[str] = Field(None, description="Case type")

    # Re-ranking
    rerank_score: Optional[float] = Field(None, description="Score after re-ranking")
    relevance_explanation: Optional[str] = Field(None, description="Why this result is relevant")


class QueryResult(BaseModel):
    """Final result from RAG query including confidence."""

    query: str = Field(..., description="Original query text")
    results: List[RetrievalResult] = Field(..., description="Retrieved results")

    confidence: float = Field(..., ge=0, le=1, description="Confidence in results")
    is_uncertain: bool = Field(default=False, description="True if no similar cases found")
    uncertainty_reason: Optional[str] = Field(None, description="Explanation if uncertain")

    # Stats
    total_candidates: int = Field(..., description="Total candidates before filtering")
    retrieval_time_ms: float = Field(..., description="Time taken for retrieval")


class RAGConfig(BaseModel):
    """Configuration for RAG pipeline."""

    # API Keys
    openai_api_key: str = Field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", ""),
        description="OpenAI API key for embeddings"
    )

    # Paths
    data_dir: Path = Field(
        default=Path("./data"),
        description="Base data directory"
    )
    chroma_persist_dir: Path = Field(
        default=Path("./data/embeddings"),
        description="ChromaDB persistence directory"
    )
    bm25_index_path: Path = Field(
        default=Path("./data/embeddings/bm25_index.pkl"),
        description="Path to BM25 index pickle file"
    )

    # Embedding settings
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model"
    )
    embedding_dimensions: int = Field(
        default=1536,
        description="Embedding vector dimensions"
    )
    embedding_batch_size: int = Field(
        default=50,
        description="Batch size for embedding generation"
    )

    # Chunking settings
    chunk_size: int = Field(
        default=500,
        description="Target chunk size in tokens"
    )
    chunk_overlap: int = Field(
        default=50,
        description="Overlap between chunks in tokens"
    )

    # Retrieval settings
    initial_retrieval_k: int = Field(
        default=20,
        description="Number of candidates to retrieve before re-ranking"
    )
    final_top_k: int = Field(
        default=5,
        description="Final number of results to return"
    )
    rrf_k: int = Field(
        default=60,
        description="K parameter for Reciprocal Rank Fusion"
    )
    semantic_weight: float = Field(
        default=0.7,
        ge=0, le=1,
        description="Weight for semantic search (BM25 gets 1-this)"
    )

    # Confidence thresholds
    min_confidence_threshold: float = Field(
        default=0.5,
        description="Minimum confidence to not flag as uncertain"
    )
    min_similarity_threshold: float = Field(
        default=0.3,
        description="Minimum similarity score for a result to be considered"
    )

    # ChromaDB settings
    collection_name: str = Field(
        default="tribunal_cases",
        description="ChromaDB collection name"
    )

    # Memory optimization
    bm25_lite_mode: bool = Field(
        default=False,
        description="Use lite mode for BM25 index (lower RAM for 8000+ cases)"
    )

    @field_validator("openai_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Warn if API key is not set."""
        if not v:
            import structlog
            logger = structlog.get_logger()
            logger.warning("OPENAI_API_KEY not set - embedding generation will fail")
        return v

    @field_validator("data_dir", "chroma_persist_dir", mode="before")
    @classmethod
    def resolve_path(cls, v):
        """Convert string paths to Path objects."""
        if isinstance(v, str):
            return Path(v)
        return v

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        self.bm25_index_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "RAGConfig":
        """Create config from environment variables."""
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            data_dir=Path(os.getenv("DATA_DIR", "./data")),
            chroma_persist_dir=Path(os.getenv("CHROMA_PERSIST_DIR", "./data/embeddings")),
        )

    # ------------------------------------------------------------------
    # SHA-20 Phase 4: namespace-aware factory
    # ------------------------------------------------------------------

    @classmethod
    def from_namespace(
        cls,
        namespace: "_RetrievalNamespace",
        *,
        base: Optional["RAGConfig"] = None,
        project_root: Optional[Path] = None,
    ) -> "RAGConfig":
        """Build a :class:`RAGConfig` bound to a specific retrieval namespace.

        * Opens the namespace's declared Chroma collection
          (``vector_collection``) — for the legacy deposit namespace this
          is literally ``tribunal_cases``.
        * Resolves the BM25 path: legacy deposit goes to
          ``data/embeddings/bm25_index.pkl``; everything else goes to
          ``data/indices/{namespace_id}/{corpus_version}/bm25.pkl``.
        * Verifies the embedding model encoded in the namespace matches
          the live config — mismatches raise
          :class:`rag_engine.namespaces.EmbeddingModelMismatch` because
          embedding-model changes invalidate stored vectors.

        Args:
            namespace: A :class:`domain_core.spec.RetrievalNamespace`.
            base: Optional template config to inherit non-path settings
                from (chunk_size, retrieval k, etc.). Defaults to
                ``RAGConfig.from_env()``.
            project_root: Root directory paths are resolved against.
                Defaults to the parent of ``base.data_dir``.
        """
        from .namespaces import (
            EmbeddingModelMismatch,
            bm25_index_path_for,
            is_legacy_deposit_namespace,
            resolve_embedding_model,
            vector_collection_for,
        )

        base = base or cls.from_env()
        if project_root is None:
            project_root = base.data_dir.parent if base.data_dir.is_absolute() else Path.cwd()
        else:
            project_root = Path(project_root)

        bm25_path = bm25_index_path_for(namespace, project_root)
        collection = vector_collection_for(namespace)

        # Embedding-model fail-fast. Legacy deposit namespace predates
        # the tagging convention so resolve_embedding_model returns None;
        # in that case we accept whatever the live config says.
        ns_model = resolve_embedding_model(namespace)
        if ns_model is not None and ns_model != base.embedding_model:
            raise EmbeddingModelMismatch(
                f"namespace {namespace.namespace_id!r} declares embedding "
                f"model {ns_model!r} but live RAGConfig uses "
                f"{base.embedding_model!r}; rebuild the corpus under a new "
                "corpus_version before switching"
            )

        # Reuse most settings from base; override the namespace-specific ones.
        data = base.model_dump()
        data["openai_api_key"] = base.openai_api_key
        data["bm25_index_path"] = bm25_path
        data["collection_name"] = collection
        # Chroma persistence dir for non-legacy namespaces lives under
        # data/indices/{ns_id}/{corpus_version}/chroma; legacy stays put.
        if not is_legacy_deposit_namespace(namespace):
            cv = namespace.corpus_version or "unversioned"
            data["chroma_persist_dir"] = (
                project_root / "data" / "indices" / namespace.namespace_id / cv / "chroma"
            )
        return cls(**data)


# ---------------------------------------------------------------------------
# SHA-20 Phase 4: shared retrieval filter envelope.
#
# The legal contract is: hybrid retrieval is only correct when the semantic
# (Chroma) and keyword (BM25) backends apply the *same* filter set. Each
# backend has historically interpreted "where" kwargs differently — Chroma
# wants its own ``$and`` clause, BM25 had no filter API at all. Phase 4
# introduces this single envelope as the source of truth; both backends
# convert *from* the envelope, never the other way round, so divergence is
# a deterministic test failure rather than a silent precision drop.
# ---------------------------------------------------------------------------


class RetrievalFilterEnvelope(BaseModel):
    """Backend-agnostic filter spec for hybrid retrieval.

    All fields are optional; ``None`` / empty list means "no filter".
    Both Chroma and BM25 backends MUST honour the same envelope when
    used inside a hybrid call — see ``HybridRetriever`` for the
    enforcement point.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    # Phase 4 metadata filters (all optional)
    excluded_source_ids: List[str] = Field(default_factory=list)
    max_decision_date: Optional[date] = None
    as_of_date: Optional[date] = None
    forum: Optional["_Forum"] = None
    source_kind: Optional["_SourceKind"] = None
    source_publisher: Optional["_SourcePublisher"] = None
    matter_type: Optional[str] = None

    # Cross-domain authorization. Setting ``cross_domain_allowed=True``
    # alone is NOT enough; ``eval_only=True`` must also be set.
    cross_domain_allowed: bool = False
    eval_only: bool = False

    # Pass-through legacy ``where`` dict (year/region/case_type) so the
    # deposit pipeline keeps working unchanged.
    legacy_where: Dict[str, Any] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return (
            not self.excluded_source_ids
            and self.max_decision_date is None
            and self.as_of_date is None
            and self.forum is None
            and self.source_kind is None
            and self.source_publisher is None
            and self.matter_type is None
            and not self.legacy_where
        )

    def matches_metadata(self, meta: Dict[str, Any]) -> bool:
        """Test a single chunk's metadata dict against this envelope.

        Used by BM25 (which scores then filters in Python) and as the
        canonical reference for the Chroma where-clause translation.
        Date filters compare ISO strings if ``decision_date`` is stored
        as a string in the metadata.
        """
        # Excluded source ids
        sid = meta.get("source_id") or meta.get("case_reference")
        if sid and self.excluded_source_ids and sid in self.excluded_source_ids:
            return False

        # Decision-date max (e.g. "decisions on or before YYYY-MM-DD")
        if self.max_decision_date is not None:
            d = meta.get("decision_date")
            if d:
                try:
                    parsed = (
                        date.fromisoformat(d) if isinstance(d, str) else d
                    )
                except ValueError:
                    parsed = None
                if parsed and parsed > self.max_decision_date:
                    return False

        # as_of_date: a chunk is valid iff its law_effective_date <= as_of
        if self.as_of_date is not None:
            led = meta.get("law_effective_date")
            if led:
                try:
                    parsed = (
                        date.fromisoformat(led) if isinstance(led, str) else led
                    )
                except ValueError:
                    parsed = None
                if parsed and parsed > self.as_of_date:
                    return False

        # Enum filters (compare to .value)
        if self.forum is not None and meta.get("forum") != self.forum.value:
            return False
        if (
            self.source_kind is not None
            and meta.get("source_kind") != self.source_kind.value
        ):
            return False
        if (
            self.source_publisher is not None
            and meta.get("source_publisher") != self.source_publisher.value
        ):
            return False

        # matter_type lives in a "|"-joined string in chroma; in lists in BM25.
        if self.matter_type is not None:
            mt = meta.get("matter_types")
            if isinstance(mt, list):
                if self.matter_type not in mt:
                    return False
            elif isinstance(mt, str):
                if self.matter_type not in {p for p in mt.split("|") if p}:
                    return False
            else:
                return False

        # Legacy where-clause (year, region, case_type) — exact equality only.
        for k, v in self.legacy_where.items():
            if meta.get(k) != v:
                return False
        return True

    def to_chroma_where(self) -> Optional[Dict[str, Any]]:
        """Translate to a ChromaDB ``where`` clause (or ``None``).

        Date comparisons are intentionally not pushed into Chroma. The
        Chroma version used by this project rejects string operands for
        range operators such as ``$lte``; date limits are still enforced by
        the shared Python post-filter in ``matches_metadata``.
        """
        clauses: List[Dict[str, Any]] = []
        if self.excluded_source_ids:
            # Do not push this into Chroma. New rows use source_id while
            # legacy deposit rows use case_reference; Chroma cannot express
            # that OR safely. The shared Python post-filter applies the
            # exclusion for both backends after retrieval.
            pass
        if self.max_decision_date is not None:
            pass
        if self.as_of_date is not None:
            pass
        if self.forum is not None:
            clauses.append({"forum": {"$eq": self.forum.value}})
        if self.source_kind is not None:
            clauses.append({"source_kind": {"$eq": self.source_kind.value}})
        if self.source_publisher is not None:
            clauses.append({"source_publisher": {"$eq": self.source_publisher.value}})
        for k, v in self.legacy_where.items():
            if isinstance(v, dict):
                clauses.append({k: v})
            else:
                clauses.append({k: {"$eq": v}})

        # NOTE: matter_type is intentionally omitted here. Chroma stores
        # matter_types as a "|"-joined string, which Chroma's where-clause
        # cannot substring-match safely. We document the limitation and
        # apply matter_type filtering on the Python side (see
        # ``matches_metadata``) for both backends, keeping the filter
        # envelopes aligned.
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}


# Legal domain keywords for re-ranking relevance
DEPOSIT_ISSUE_KEYWORDS = {
    "deposit_protection": [
        "deposit protection", "section 213", "section 214",
        "tenancy deposit scheme", "tds", "dps", "mydeposits",
        "protected deposit", "unprotected deposit", "prescribed information"
    ],
    "cleaning": [
        "cleaning", "professional clean", "end of tenancy clean",
        "cleanliness", "dirty", "filthy", "clean condition"
    ],
    "damage": [
        "damage", "damages", "broken", "stain", "mark", "scratch",
        "hole", "burn", "tear", "worn", "deterioration"
    ],
    "fair_wear_and_tear": [
        "fair wear and tear", "reasonable wear", "natural wear",
        "normal use", "betterment"
    ],
    "inventory": [
        "inventory", "check-in", "check-out", "schedule of condition",
        "photographic evidence", "inspection report"
    ],
    "rent_arrears": [
        "rent arrears", "unpaid rent", "outstanding rent",
        "rent owed", "arrears"
    ],
    "garden": [
        "garden", "lawn", "grass", "overgrown", "landscaping",
        "outdoor area", "patio"
    ],
    "decoration": [
        "redecoration", "painting", "redecorating", "walls",
        "paintwork", "marks on walls"
    ],
    "repairs_damp_mould": [
        "repairs_damp_mould",
        "damp and mould",
        "damp",
        "mould",
        "mold",
        "condensation",
        "black mould",
        "humidity",
        "ventilation",
        "respiratory",
        "asthma",
        "fungal",
    ],
    "repairs_disrepair": [
        "repairs_disrepair",
        "disrepair",
        "repair",
        "repairs",
        "leak",
        "leaking",
        "water ingress",
        "roof",
        "boiler",
        "heating",
        "hot water",
        "blocked drain",
        "drainpipe",
        "flooding",
        "subsidence",
        "cracks",
        "balcony",
        "window",
        "door",
        "plaster",
        "electrical",
    ],
    "complaint_handling_failure": [
        "complaint_handling_failure",
        "complaint handling",
        "stage 1",
        "stage 2",
        "complaint response",
        "delayed response",
        "complaints policy",
        "complaint handling code",
        "poor communication",
        "failure to respond",
    ],
}


# ---------------------------------------------------------------------------
# Resolve forward references for Phase 4 metadata. These imports happen at
# module-load time but AFTER the model classes are defined, so they don't
# create circularity. ``model_rebuild`` makes the optional
# ``source_metadata`` annotation resolvable on Pydantic v2.
# ---------------------------------------------------------------------------
from .source_metadata import SourceMetadata as SourceMetadata  # noqa: E402,F401
from domain_core.spec import (  # noqa: E402
    Forum as _Forum,  # type: ignore[misc]
    SourceKind as _SourceKind,  # type: ignore[misc]
    SourcePublisher as _SourcePublisher,  # type: ignore[misc]
)

CaseDocument.model_rebuild()
DocumentChunk.model_rebuild()
RetrievalFilterEnvelope.model_rebuild()
