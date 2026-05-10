"""Factor-assertion sidecar — case-side backfill for the Stream C KG path.

The eval gold corpus (``data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl``)
does not carry ``factor_assertions``. Without them, the FactorRetriever's
``asserted_factors`` input is empty and the KG path silently falls back to
chunk-RAG.

This sidecar lives next to the gold corpus and is hydrated at engine-input
time (in the live eval runner's ``_build_eval_knowledge_graph``). The
hydration deliberately attaches the pre-validated
``legal_core.graph.factor_assertion.FactorAssertion`` Pydantic instances
onto the ``KnowledgeGraph`` as the ``factor_assertions`` field — the exact
attribute the FactorRetriever / EvidencePathValidator already read.

Sidecar shape (single JSON file)::

    {
      "schema_version": "v1",
      "domain_id": "housing.repairs_social.v1",
      "extractor_version": "<annotator-models>+<date>",
      "factor_assertions_by_case_id": {
        "<case_id>": [<FactorAssertion dict>, ...],
        ...
      }
    }

Why a single file (not one-per-case)?
  - Smaller surface for promote tooling: write once, atomic move
  - Faster hydration: one disk read per eval run, not 48
  - Idempotency check: trivial to compare two runs

Why not on ``GoldCase``?
  - GoldCase is ``extra="forbid"`` and round-trips through promote tooling;
    a new field there would require coordinated tooling changes and risks
    breaking the 1830+ existing tests on the branch.
  - Decouples the factor-data lifecycle from the gold corpus — when the
    extractor improves, refresh the sidecar without rewriting gold rows.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict


SIDECAR_SCHEMA_VERSION = "v1"


class FactorAssertionSidecar(TypedDict):
    """Validated Stream C sidecar payload."""

    factor_assertions_by_case_id: Dict[str, List[Any]]
    evidence_spans_by_case_id: Dict[str, List[Any]]


def default_sidecar_path(repo_root: Path, gold_corpus_filename: str) -> Path:
    """Canonical sidecar location for *gold_corpus_filename*.

    e.g. ``housing_repairs_social_v2_strict_clean.jsonl`` →
    ``data/eval_artifacts/factor_assertions/housing_repairs_social_v2_strict_clean.factor_assertions.json``.
    """
    stem = Path(gold_corpus_filename).stem
    return (
        repo_root
        / "data"
        / "eval_artifacts"
        / "factor_assertions"
        / f"{stem}.factor_assertions.json"
    )


def load_sidecar(path: Path) -> Dict[str, List[Any]]:
    """Load a sidecar JSON file. Returns an empty dict if the file is missing.

    The returned dict maps ``case_id -> list[FactorAssertion]`` with the
    FactorAssertion objects already validated through the legal_core
    Pydantic model. Validation is lazy-imported so non-eval callers don't
    pay the legal_core import cost.

    Raises:
      FileNotFoundError: never — missing sidecar returns ``{}``
      ValueError: if the sidecar has a non-v1 schema_version we cannot read
      ValidationError: if any factor assertion fails Pydantic validation
    """
    if not path.exists():
        return {}

    return load_full_sidecar(path)["factor_assertions_by_case_id"]


def load_full_sidecar(path: Path) -> FactorAssertionSidecar:
    """Load factor assertions plus optional evidence spans from *path*.

    ``load_sidecar`` is intentionally preserved for older callers that expect
    only ``case_id -> List[FactorAssertion]``.
    """
    if not path.exists():
        return {
            "factor_assertions_by_case_id": {},
            "evidence_spans_by_case_id": {},
        }

    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = payload.get("schema_version")
    if schema_version != SIDECAR_SCHEMA_VERSION:
        raise ValueError(
            f"factor-assertion sidecar at {path} has unsupported "
            f"schema_version={schema_version!r}; expected "
            f"{SIDECAR_SCHEMA_VERSION!r}"
        )

    raw_factor_by_case: Dict[str, List[Dict[str, Any]]] = (
        payload.get("factor_assertions_by_case_id") or {}
    )
    raw_spans_by_case: Dict[str, List[Dict[str, Any]]] = (
        payload.get("evidence_spans_by_case_id") or {}
    )
    if not isinstance(raw_factor_by_case, dict):
        raise ValueError(
            f"factor-assertion sidecar at {path} has malformed "
            "factor_assertions_by_case_id (must be an object/dict)"
        )
    if not isinstance(raw_spans_by_case, dict):
        raise ValueError(
            f"factor-assertion sidecar at {path} has malformed "
            "evidence_spans_by_case_id (must be an object/dict)"
        )

    # Lazy imports: eval remains cheap for non-Stream-C callers.
    from legal_core.graph.evidence_span import EvidenceSpan  # noqa: PLC0415
    from legal_core.graph.factor_assertion import FactorAssertion  # noqa: PLC0415

    factors: Dict[str, List[Any]] = {}
    for case_id, raw_list in raw_factor_by_case.items():
        if not isinstance(raw_list, list):
            raise ValueError(
                f"factor-assertion sidecar at {path}: case_id={case_id!r} "
                f"value is not a list"
            )
        factors[case_id] = [FactorAssertion.model_validate(item) for item in raw_list]

    spans: Dict[str, List[Any]] = {}
    for case_id, raw_list in raw_spans_by_case.items():
        if not isinstance(raw_list, list):
            raise ValueError(
                f"factor-assertion sidecar at {path}: evidence spans for "
                f"case_id={case_id!r} are not a list"
            )
        spans[case_id] = [EvidenceSpan.model_validate(item) for item in raw_list]

    return {
        "factor_assertions_by_case_id": factors,
        "evidence_spans_by_case_id": spans,
    }


def write_sidecar(
    path: Path,
    *,
    domain_id: str,
    extractor_version: str,
    factor_assertions_by_case_id: Dict[str, List[Any]],
    evidence_spans_by_case_id: Optional[Dict[str, List[Any]]] = None,
) -> None:
    """Write the sidecar JSON atomically.

    Each entry in *factor_assertions_by_case_id* must be a sequence of
    FactorAssertion Pydantic instances OR plain dicts already in the
    JSON-serialisable shape. This is enforced via duck-typing on
    ``model_dump`` for forwards compatibility with sub-classes.
    """
    serialised: Dict[str, List[Dict[str, Any]]] = {}
    for case_id, entries in factor_assertions_by_case_id.items():
        rows: List[Dict[str, Any]] = []
        for entry in entries:
            if hasattr(entry, "model_dump"):
                rows.append(entry.model_dump(mode="json"))
            elif isinstance(entry, dict):
                rows.append(entry)
            else:
                raise TypeError(
                    f"factor_assertion entry must be a Pydantic model or "
                    f"dict; got {type(entry).__name__}"
                )
        serialised[case_id] = rows

    serialised_spans: Dict[str, List[Dict[str, Any]]] = {}
    for case_id, entries in (evidence_spans_by_case_id or {}).items():
        rows = []
        for entry in entries:
            if hasattr(entry, "model_dump"):
                rows.append(entry.model_dump(mode="json"))
            elif isinstance(entry, dict):
                rows.append(entry)
            else:
                raise TypeError(
                    f"evidence_span entry must be a Pydantic model or dict; "
                    f"got {type(entry).__name__}"
                )
        serialised_spans[case_id] = rows

    payload = {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "domain_id": domain_id,
        "extractor_version": extractor_version,
        "factor_assertions_by_case_id": serialised,
        "evidence_spans_by_case_id": serialised_spans,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # sort_keys=True for byte-stable output (idempotency check downstream)
    body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)


def hydrate_knowledge_graph(
    knowledge_graph: Any,
    case_id: str,
    sidecar: Dict[str, List[Any]] | FactorAssertionSidecar,
) -> Any:
    """Attach factor assertions for *case_id* onto *knowledge_graph*.

    No-op when the sidecar carries no entry for this case — the KG keeps
    its default empty ``factor_assertions`` list and the FactorRetriever
    falls back exactly as before. Returns the knowledge_graph unchanged
    so callers can chain.

    The KG's ``factor_assertions`` field is declared as ``List[Any]`` so
    we can attach the typed Pydantic instances directly without forcing
    kg_builder to depend on legal_core.
    """
    if (
        isinstance(sidecar, dict)
        and "factor_assertions_by_case_id" in sidecar
    ):
        factor_sidecar = sidecar.get("factor_assertions_by_case_id") or {}
        evidence_sidecar = sidecar.get("evidence_spans_by_case_id") or {}
    else:
        factor_sidecar = sidecar
        evidence_sidecar = {}

    entries = factor_sidecar.get(case_id) or []
    if not entries:
        span_entries = evidence_sidecar.get(case_id) or []
    else:
        span_entries = evidence_sidecar.get(case_id) or []
        # KnowledgeGraph carries a typed ``factor_assertions: List[Any]`` field
        # (added 2026-05-08). On legacy KGs that don't yet have it (e.g. mocks
        # in tests), fall back to ``setattr`` so we don't crash the eval run.
        try:
            knowledge_graph.factor_assertions = list(entries)
        except (ValueError, AttributeError):
            setattr(knowledge_graph, "factor_assertions", list(entries))

    if span_entries:
        try:
            knowledge_graph.evidence_spans = list(span_entries)
        except (ValueError, AttributeError):
            setattr(knowledge_graph, "evidence_spans", list(span_entries))
    return knowledge_graph


def resolve_sidecar_for_gold_path(
    gold_path: Path,
    *,
    repo_root: Optional[Path] = None,
) -> Path:
    """Resolve the canonical sidecar path for an absolute gold-corpus path.

    Used by the live runner so the runner doesn't have to know the
    sidecar layout — pass it the gold path it already has and it hands
    back the sidecar to load.
    """
    if repo_root is None:
        repo_root = gold_path.resolve().parents[2]
    return default_sidecar_path(repo_root, gold_path.name)
