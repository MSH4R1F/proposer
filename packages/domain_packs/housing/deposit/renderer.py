"""housing.deposit.v1 factor card renderer.

Mirrors the legacy ``IssuePredictor._format_kg_fact_card`` byte-for-byte to
preserve the deposit regression suite. Will be replaced by a more general
renderer once kg_facts.py is fully deprecated (post-Stream-C cleanup PR).

The renderer uses duck-typing on the case_graph object rather than importing
``KGFacts`` directly: ``domain_packs`` is a leaf-adjacent package and must
not depend on ``llm_orchestrator``. The legacy ``_format_kg_fact_card`` itself
already uses ``getattr(...)`` defensively for the optional sub-fields, so this
matches the legacy style.

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §19 PR 4
"""

from __future__ import annotations

from typing import Any


# Sentinel string that indicates "no value extracted". Matches the
# ``Literal["..."]`` defaults used by KGFacts in llm_orchestrator. Stored as
# a constant so the contract is visible.
_UNKNOWN = "unknown"


def render_factor_card(case_graph: Any, pack: Any) -> str:
    """Render the deposit factor card for the IRAC prompt.

    Parameters
    ----------
    case_graph:
        A KGFacts-shaped object (or ``None``). Treated as opaque via
        duck-typing — must expose ``is_empty()`` and the three deposit
        enum attributes for a card to be rendered.
    pack:
        The DomainPack instance. Unused here; accepted for signature
        uniformity with future per-pack renderers.

    Returns
    -------
    str
        Either ``""`` (empty / unknown / wrong-shape) or a string that is
        byte-equivalent to the legacy ``IssuePredictor._format_kg_fact_card``
        for the same input — i.e. with a single leading ``"\\n"`` and a
        single trailing ``"\\n"``.

    Notes
    -----
    If ``case_graph`` has ``is_empty()`` but is missing the deposit attrs
    (e.g. is not a real ``KGFacts``), ``AttributeError`` will propagate —
    matching legacy ``_format_kg_fact_card`` behavior, which uses direct
    attribute access for the required fields.
    """
    del pack  # unused — kept for registry call-shape

    if case_graph is None:
        return ""

    # Duck-typed empty check. Matches legacy guard: if .is_empty() raises
    # AttributeError (wrong shape), return "".
    try:
        if case_graph.is_empty():
            return ""
    except AttributeError:
        return ""

    # Match legacy: start with empty leading element so the joined output
    # has a leading "\n", and append a trailing "\n" at the end.
    lines: list[str] = ["", "KEY KG FACTS (typed):"]

    if case_graph.deposit_protection_status != _UNKNOWN:
        line = (
            f"- deposit_protection_status: {case_graph.deposit_protection_status}"
        )
        if getattr(case_graph, "deposit_scheme", None):
            line += f" (scheme: {case_graph.deposit_scheme})"
        if getattr(case_graph, "deposit_late_by_days", None) is not None:
            line += f" (late by {case_graph.deposit_late_by_days} days)"
        lines.append(line)

    if case_graph.prescribed_information_status != _UNKNOWN:
        line = (
            f"- prescribed_information_status: "
            f"{case_graph.prescribed_information_status}"
        )
        if getattr(case_graph, "prescribed_late_by_days", None) is not None:
            line += f" (late by {case_graph.prescribed_late_by_days} days)"
        lines.append(line)

    if case_graph.check_in_inventory_baseline != _UNKNOWN:
        lines.append(
            f"- check_in_inventory_baseline: "
            f"{case_graph.check_in_inventory_baseline}"
        )

    return "\n".join(lines) + "\n"
