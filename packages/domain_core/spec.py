"""Pydantic v2 models for the SHA-20 domain spec contract.

These are pure config models. They do not import implementation packages.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain_core.ids import DomainFamily, DomainId
from domain_core.pack_refs import PackReferenceSet


# ---------------------------------------------------------------------------
# Controlled taxonomies (closed enums on purpose).
# ---------------------------------------------------------------------------


class Forum(str, Enum):
    """Adjudicating body / forum where a matter is resolved.

    Closed because each new forum changes citation framing, output language,
    and what counts as a valid precedent.
    """

    DEPOSIT_SCHEME_ADJUDICATION = "deposit_scheme_adjudication"
    FIRST_TIER_PROPERTY_CHAMBER = "first_tier_property_chamber"
    HOUSING_OMBUDSMAN = "housing_ombudsman"
    EMPLOYMENT_TRIBUNAL = "employment_tribunal"
    COUNTY_COURT = "county_court"
    LOCAL_AUTHORITY_ENFORCEMENT = "local_authority_enforcement"


class LaunchStage(str, Enum):
    """Coarse launch stage for a domain."""

    PRODUCTION = "production"
    BETA = "beta"
    RESEARCH = "research"
    DISABLED = "disabled"


class SourcePublisher(str, Enum):
    """Publisher / origin of a source document."""

    BAILII = "bailii"
    GOVUK = "govuk"
    HOUSING_OMBUDSMAN = "housing_ombudsman"
    LEGISLATION_GOV_UK = "legislation_gov_uk"
    ACAS = "acas"
    MANUAL = "manual"
    INTERNAL = "internal"


class SourceKind(str, Enum):
    """High-level kind of a retrieved source."""

    CASE_DECISION = "case_decision"
    OMBUDSMAN_DETERMINATION = "ombudsman_determination"
    STATUTE = "statute"
    GUIDANCE = "guidance"
    CALCULATOR_TRACE = "calculator_trace"
    USER_EVIDENCE = "user_evidence"
    SYNTHETIC = "synthetic"


class CitationKind(str, Enum):
    """Kind of citation slot in produced reasoning."""

    USER_FACT = "user_fact"
    UPLOADED_EVIDENCE = "uploaded_evidence"
    RETRIEVED_LEGAL_SOURCE = "retrieved_legal_source"
    DETERMINISTIC_CALCULATOR_TRACE = "deterministic_calculator_trace"
    STATUTE_OR_GUIDANCE = "statute_or_guidance"


class ChunkKind(str, Enum):
    """Allowed chunk kinds in a retrieval namespace."""

    DOCUMENT_CHUNK = "document_chunk"
    PROPOSITION = "proposition"


# ---------------------------------------------------------------------------
# Reference URI validation: ref://{kind}/{id}
# ---------------------------------------------------------------------------

_REF_PATTERN = re.compile(r"^ref://(?P<kind>[a-z_]+)/(?P<id>[a-zA-Z0-9_.\-:/]+)$")
_ALLOWED_REF_KINDS = {
    "intake_schema",
    "case_file_adapter",
    "ontology",
    "prompt_pack",
}


def _validate_ref(value: str, allowed_kinds: Optional[set] = None) -> str:
    if not isinstance(value, str):
        raise ValueError(f"reference must be a string, got {type(value).__name__}")
    match = _REF_PATTERN.match(value)
    if not match:
        raise ValueError(
            f"reference {value!r} does not match ref://<kind>/<id> "
            "(allowed kinds: intake_schema, case_file_adapter, ontology, prompt_pack)"
        )
    kind = match.group("kind")
    allowed = allowed_kinds if allowed_kinds is not None else _ALLOWED_REF_KINDS
    if kind not in allowed:
        raise ValueError(
            f"reference {value!r} uses kind {kind!r}; allowed kinds: "
            f"{sorted(allowed)}"
        )
    return value


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------


class ForumProfile(BaseModel):
    """Per-forum framing, source policy, and prompt-injection guards."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    forum: Forum
    source_publishers: List[SourcePublisher]
    source_kinds: List[SourceKind]
    citation_kinds: List[CitationKind]
    matter_types: List[str]
    remedies: List[str]
    output_framing: str
    citation_label: str
    prohibited_phrases: List[str] = Field(default_factory=list)
    required_disclaimers: List[str] = Field(default_factory=list)


class RetrievalNamespace(BaseModel):
    """Pointer to a retrieval namespace (Chroma collection + BM25 index).

    Paths are stored as strings (POSIX shape) so that the spec hash is stable
    across machines/CWDs. Existence is NOT validated at registry-load time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    namespace_id: str
    vector_collection: str
    bm25_index_path: str
    corpus_root: str
    chunk_kinds: List[ChunkKind] = Field(
        default_factory=lambda: [ChunkKind.DOCUMENT_CHUNK]
    )
    source_publishers: List[SourcePublisher]
    source_kinds: List[SourceKind]
    forums: List[Forum]
    allowed_cross_namespace_ids: List[str] = Field(default_factory=list)
    metadata_filters: Dict[str, Any] = Field(default_factory=dict)
    corpus_version: Optional[str] = None

    @field_validator("namespace_id")
    @classmethod
    def _validate_namespace_id(cls, v: str) -> str:
        if not v or not re.match(r"^[a-z0-9][a-z0-9_.\-]*$", v):
            raise ValueError(
                f"namespace_id must be lowercase identifier-like, got {v!r}"
            )
        return v

    @field_validator("bm25_index_path", "corpus_root")
    @classmethod
    def _normalize_paths(cls, v: str) -> str:
        # Normalize to POSIX so spec hash is stable across OSes.
        if not isinstance(v, str) or not v:
            raise ValueError("path must be a non-empty string")
        return str(PurePosixPath(v))


class EvalGate(BaseModel):
    """Launch-gate eval config. Existence of files is checked elsewhere."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gold_set_path: str
    min_cases: int
    required_metrics: Dict[str, float] = Field(default_factory=dict)
    max_hallucination_rate: float = 0.02
    min_citation_validity: float = 0.98
    min_abstention_precision: float = 0.80

    @field_validator("gold_set_path")
    @classmethod
    def _normalize_path(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("gold_set_path must be a non-empty string")
        return str(PurePosixPath(v))

    @field_validator("min_cases")
    @classmethod
    def _min_cases_nonneg(cls, v: int) -> int:
        if v < 0:
            raise ValueError("min_cases must be >= 0")
        return v

    @field_validator(
        "max_hallucination_rate",
        "min_citation_validity",
        "min_abstention_precision",
    )
    @classmethod
    def _rate_in_unit_interval(cls, v: float) -> float:
        if not 0.0 <= float(v) <= 1.0:
            raise ValueError("rate must be in [0.0, 1.0]")
        return float(v)


class TemporalLawMarker(BaseModel):
    """Temporal-law marker: e.g. an effective date for a statute version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    effective_date: str  # ISO-8601 date string
    note: Optional[str] = None


class DomainSpec(BaseModel):
    """The domain contract loaded from YAML.

    See ``docs/superpowers/specs/2026-05-01-multi-domain-architecture-expansion-design.md``
    section 5.3 for field semantics.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: DomainId
    family: DomainFamily
    domain_version: str
    schema_version: int = 1
    display_name: str
    user_facing_name: str
    stage: LaunchStage
    jurisdiction: List[str]
    forums: List[Forum]
    forum_profiles: List[ForumProfile]
    party_roles: List[str]
    matter_types: List[str]
    remedies: List[str]
    intake_schema_ref: str
    case_file_adapter_ref: str
    ontology_ref: str
    prompt_pack_ref: str
    retrieval_namespaces: List[RetrievalNamespace]
    eval_gate: EvalGate
    safety_notes: List[str] = Field(default_factory=list)
    temporal_law_markers: List[TemporalLawMarker] = Field(default_factory=list)
    pack_refs: Optional[PackReferenceSet] = None

    # ---- ref:// validators ----

    @field_validator("intake_schema_ref")
    @classmethod
    def _validate_intake_ref(cls, v: str) -> str:
        return _validate_ref(v, {"intake_schema"})

    @field_validator("case_file_adapter_ref")
    @classmethod
    def _validate_adapter_ref(cls, v: str) -> str:
        return _validate_ref(v, {"case_file_adapter"})

    @field_validator("ontology_ref")
    @classmethod
    def _validate_ontology_ref(cls, v: str) -> str:
        return _validate_ref(v, {"ontology"})

    @field_validator("prompt_pack_ref")
    @classmethod
    def _validate_prompt_pack_ref(cls, v: str) -> str:
        return _validate_ref(v, {"prompt_pack"})

    # ---- domain_version pattern ----

    @field_validator("domain_version")
    @classmethod
    def _validate_domain_version(cls, v: str) -> str:
        if not re.match(r"^v\d+$", v):
            raise ValueError(
                f"domain_version must match 'vN' (e.g. 'v1'), got {v!r}"
            )
        return v

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, v: int) -> int:
        if v < 1:
            raise ValueError("schema_version must be >= 1")
        return v

    # ---- cross-field invariants ----

    @model_validator(mode="after")
    def _validate_invariants(self) -> "DomainSpec":
        # final id segment must equal domain_version
        if not str(self.id).endswith(f".{self.domain_version}"):
            raise ValueError(
                f"DomainSpec.id ({self.id!r}) must end with "
                f".{self.domain_version!r}"
            )
        # first id segment must equal family
        first_seg = str(self.id).split(".", 1)[0]
        if first_seg != self.family.value:
            raise ValueError(
                f"DomainSpec.id first segment {first_seg!r} must equal "
                f"family {self.family.value!r}"
            )
        # every forum has exactly one matching ForumProfile
        forums_set = list(self.forums)
        profile_forums = [p.forum for p in self.forum_profiles]
        if sorted(f.value for f in forums_set) != sorted(
            f.value for f in profile_forums
        ):
            raise ValueError(
                "forums and forum_profiles must align exactly: "
                f"forums={[f.value for f in forums_set]} "
                f"profiles={[f.value for f in profile_forums]}"
            )
        # no duplicate ForumProfile entries
        if len(set(profile_forums)) != len(profile_forums):
            raise ValueError(
                "forum_profiles contains duplicate forums: "
                f"{[f.value for f in profile_forums]}"
            )
        # no duplicate retrieval namespace ids
        ns_ids = [ns.namespace_id for ns in self.retrieval_namespaces]
        if len(set(ns_ids)) != len(ns_ids):
            raise ValueError(
                f"retrieval_namespaces has duplicate namespace_id values: {ns_ids}"
            )
        return self
