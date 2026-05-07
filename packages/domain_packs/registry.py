"""DomainPack registry: load and cache the bundled pack artefacts per domain.

Per spec §6 + Stream C design decision D2: this module sits alongside
domain_core.registry but is the canonical lookup for full domain packs
(catalog + outcomes + remedies + retrieval + gate + extractor + rubric).

Usage:
    from domain_packs.registry import get_domain_pack
    pack = get_domain_pack("housing.repairs_social.v1")
    card = pack.render_factor_card(case_graph)
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from domain_core.registry import get_domain_spec
from domain_core.spec import DomainSpec
from legal_core.graph.graph_quality import GraphQualityScore

from domain_packs.loaders import (
    ExtractorStrategy,
    FactorCatalog,
    GraphQualityGate,
    OutcomeSchema,
    RemedySchema,
    RetrievalProfile,
)


_PACK_ROOT = Path(__file__).resolve().parent


class DomainPackNotFoundError(Exception):
    """Raised when get_domain_pack is called with an unknown domain_id."""


# Domain ID → pack subdirectory mapping. The dotted form
# "housing.repairs_social.v1" maps to packages/domain_packs/housing/repairs_social/.
_KNOWN_PACK_DIRS: dict[str, Path] = {
    "housing.repairs_social.v1": _PACK_ROOT / "housing" / "repairs_social",
    "housing.deposit.v1": _PACK_ROOT / "housing" / "deposit",
}


@dataclass(frozen=True)
class DomainPack:
    """Bundle of domain pack YAMLs + rubric for a single domain."""

    domain_id: str
    spec: DomainSpec
    factors: FactorCatalog
    outcomes: OutcomeSchema
    remedies: RemedySchema
    retrieval_profile: RetrievalProfile
    graph_quality_gate: GraphQualityGate
    extractor_strategy: ExtractorStrategy
    annotation_rubric: str

    def render_factor_card(self, case_graph: Any) -> str:
        """Delegate to the per-pack renderer.py module.

        Per spec §19 PR 4: returns markdown string for the kg_fact_card
        slot in IRAC_USER_PROMPT and _format_repairs_user_prompt.

        Raises DomainPackNotFoundError if the renderer module for this
        domain has not been implemented yet (Tasks 4.2 / 4.3).
        """
        import importlib

        family, sub_family, _version = self.domain_id.split(".")
        module_path = f"domain_packs.{family}.{sub_family}.renderer"
        try:
            renderer = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            raise DomainPackNotFoundError(
                f"Renderer module {module_path!r} not found for domain "
                f"{self.domain_id!r}; this pack has no renderer.py yet."
            ) from exc
        return renderer.render_factor_card(case_graph, self)

    def is_kg_usable(self, score: GraphQualityScore) -> bool:
        """Check whether the graph quality score passes this pack's gate.

        Per spec §8.1: thresholds live on the domain pack, not in shared
        core code. Reads packages/domain_packs/<pack>/graph_quality_gate.yaml.
        """
        gate = self.graph_quality_gate
        return (
            score.evidence_backed_factor_count >= gate.evidence_backed_factor_count_min
            and score.dated_event_count >= gate.dated_event_count_min
            and score.issue_count >= gate.issue_count_min
            and score.outcome_or_remedy_candidate_count
                >= gate.outcome_or_remedy_candidate_count_min
            and score.unsupported_factor_rate <= gate.unsupported_factor_rate_max
            and score.source_span_coverage >= gate.source_span_coverage_min
            and score.contradiction_count <= gate.contradiction_count_max
        )


@lru_cache(maxsize=None)
def get_domain_pack(domain_id: str) -> DomainPack:
    """Resolve and cache the domain pack for `domain_id`.

    Raises DomainPackNotFoundError if the domain_id is not registered or
    its YAML files are not on disk.
    """
    if domain_id not in _KNOWN_PACK_DIRS:
        raise DomainPackNotFoundError(
            f"No domain pack registered for {domain_id!r}. "
            f"Known: {sorted(_KNOWN_PACK_DIRS)}"
        )

    pack_dir = _KNOWN_PACK_DIRS[domain_id]
    if not pack_dir.exists():
        raise DomainPackNotFoundError(
            f"Domain pack {domain_id!r} registered but directory missing: {pack_dir}"
        )

    spec = get_domain_spec(domain_id)
    factors = FactorCatalog.from_yaml(pack_dir / "factors.yaml")
    outcomes = OutcomeSchema.from_yaml(pack_dir / "outcomes.yaml")
    remedies = RemedySchema.from_yaml(pack_dir / "remedies.yaml")
    retrieval_profile = RetrievalProfile.from_yaml(pack_dir / "retrieval_profile.yaml")
    graph_quality_gate = GraphQualityGate.from_yaml(pack_dir / "graph_quality_gate.yaml")
    extractor_strategy = ExtractorStrategy.from_yaml(pack_dir / "extractor_strategy.yaml")
    rubric_path = pack_dir / "annotation_rubric.md"
    annotation_rubric = rubric_path.read_text(encoding="utf-8") if rubric_path.exists() else ""

    return DomainPack(
        domain_id=domain_id,
        spec=spec,
        factors=factors,
        outcomes=outcomes,
        remedies=remedies,
        retrieval_profile=retrieval_profile,
        graph_quality_gate=graph_quality_gate,
        extractor_strategy=extractor_strategy,
        annotation_rubric=annotation_rubric,
    )
