"""housing.repairs_social.v1 factor card renderer.

Reads FactorAssertion nodes from the case_graph, dispatches on value_type,
applies bucket labels for numeric/money/duration via the pack's
retrieval_profile bucket_definitions, and surfaces polarity as a
domain-aware surface label (favours resident / favours landlord).

Per spec section 17.6: factors with requires_human_review=True render in a
separate "Uncertain (excluded from gate)" section.

Per Stream C hard constraint #11 + R-PR4-2: the output is NEVER allowed
to contain unescaped `{` or `}` braces (would crash IRAC_USER_PROMPT.format).
"""

from __future__ import annotations

import logging
import os
from typing import Any, List

logger = logging.getLogger(__name__)


# Domain-specific surface labels. The abstract polarity enum
# (pro_claimant / pro_respondent / neutral) maps to these in the prompt.
_POLARITY_SURFACE_LABEL = {
    "pro_claimant": "favours resident",
    "pro_respondent": "favours landlord",
    "neutral": "",
}

_HEADER_MAIN = "KEY FACTORS (factor-graph derived):"
_HEADER_UNCERTAIN = "Uncertain (excluded from gate):"


def render_factor_card(case_graph: Any, pack: Any) -> str:
    """Render the housing.repairs_social.v1 factor card.

    case_graph: a KnowledgeGraph (or KnowledgeGraph-like) with a
        ``factor_assertions`` attribute holding a list of FactorAssertion
        objects from legal_core.
    pack: the DomainPack instance (provides factors.yaml + bucket defs).

    Returns markdown-friendly string for the {kg_fact_card} prompt slot.
    Returns empty string for any of: kill switch, missing graph, no
    renderable factor assertions.
    """
    # Kill switch
    if os.getenv("STREAM_C_PR4_REPAIRS", "1") == "0":
        return ""

    # Defensive: handle missing/empty graph
    if case_graph is None:
        return ""
    factor_assertions = getattr(case_graph, "factor_assertions", None)
    if not factor_assertions:
        return ""

    # Build O(1) catalog lookup
    factor_id_to_entry = {f.id: f for f in pack.factors.factors}

    # Bucket definitions for numeric/money/duration rendering
    bucket_defs = pack.retrieval_profile.bucket_definitions

    main_lines: List[str] = []
    uncertain_lines: List[str] = []

    for fa in factor_assertions:
        catalog_entry = factor_id_to_entry.get(fa.factor_id)
        if catalog_entry is None:
            logger.warning(
                "factor_assertion_not_in_catalog factor_id=%s domain_id=%s",
                fa.factor_id,
                pack.domain_id,
            )
            continue

        rendered_value = _render_value(fa, bucket_defs)
        # FactorPolarity is a str-based Enum, so equality/hashing with plain str works.
        polarity_label = _POLARITY_SURFACE_LABEL.get(catalog_entry.polarity, "")
        polarity_paren = f" ({polarity_label})" if polarity_label else ""
        evidence_csv = ", ".join(fa.supported_by) if fa.supported_by else "-"

        line = (
            f"- {fa.factor_id}: {rendered_value}{polarity_paren} "
            f"[confidence: {fa.confidence:.2f}, evidence: {evidence_csv}]"
        )

        if fa.requires_human_review:
            uncertain_lines.append(line)
        else:
            main_lines.append(line)

    if not main_lines and not uncertain_lines:
        return ""

    sections: List[str] = []
    if main_lines:
        sections.append(_HEADER_MAIN)
        sections.extend(main_lines)
    if uncertain_lines:
        if sections:
            sections.append("")  # blank separator
        sections.append(_HEADER_UNCERTAIN)
        sections.extend(uncertain_lines)

    rendered = "\n".join(sections)

    # Hard guard: no unescaped format-string placeholders allowed
    # (would crash IRAC_USER_PROMPT.format(**prompt_kwargs) downstream).
    # If a factor description or value contains literal { or }, escape by doubling.
    rendered = rendered.replace("{", "{{").replace("}", "}}")
    return rendered


def _render_value(fa: Any, bucket_defs: Any) -> str:
    """Dispatch on value_type. Numeric/money/duration include bucket label."""
    vt = fa.value_type
    val = fa.value  # FactorValue from legal_core

    # FactorValueType is str-Enum, so comparing to literals works
    if vt == "boolean":
        return "True" if val.boolean else "False"

    if vt == "enum":
        return str(val.enum)

    if vt == "number":
        n = val.number
        return f"{n:g}"

    if vt == "money":
        # Stream A FactorValue stores money_minor_units (GBP pence).
        pence = val.money_minor_units or 0
        pounds = pence / 100.0
        bucket = _money_bucket_label(pence, bucket_defs.money.bucket_edges_pence)
        return f"£{pounds:.2f} (bucket: {bucket})"

    if vt == "date":
        return val.date.isoformat() if val.date else "unknown"

    if vt == "duration":
        days = val.duration_days or 0
        bucket = _duration_bucket_label(days, bucket_defs.duration.bucket_edges_days)
        return f"{days} days (bucket: {bucket})"

    # Defensive default (unknown value_type)
    return "unknown"


def _money_bucket_label(pence: int, edges: List[int]) -> str:
    """Return human-readable bucket label like '£100-£500' or '>£10k'."""
    # edges from retrieval_profile.yaml: e.g. [0, 10000, 50000, 200000, 1000000]
    for i, edge in enumerate(edges[:-1]):
        next_edge = edges[i + 1]
        if edge <= pence < next_edge:
            return f"£{edge//100}-£{next_edge//100}"
    if pence >= edges[-1]:
        return f">£{edges[-1]//100}"
    return "<£0"


def _duration_bucket_label(days: int, edges: List[int]) -> str:
    """Return human-readable bucket label like '7-30d' or '>365d'."""
    # edges from retrieval_profile.yaml: e.g. [1, 7, 30, 90, 365]
    for i, edge in enumerate(edges[:-1]):
        next_edge = edges[i + 1]
        if edge <= days < next_edge:
            return f"{edge}-{next_edge}d"
    if days >= edges[-1]:
        return f">{edges[-1]}d"
    return f"<{edges[0]}d"
