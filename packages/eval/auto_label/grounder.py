"""Phase 8 — auto-grounder orchestration.

Per sparring §3, the grounder is a deterministic pre-adjudication gate
that decides whether each candidate cell on a ``PartialGoldCase`` is
admissible *before* a human reviewer ever sees the row. It runs a fixed
set of per-field checks (quote span match, authority/statute lookups,
outcome/label basis spans, facts leakage, date and amount sanity, schema
invariants, and the real-gold append gate) and emits a
``GroundingResult`` mapping every field path it touches to a
``"GROUNDED"`` / ``"UNGROUNDED"`` verdict plus a one-line reason.

A field path is only ``GROUNDED`` if its applicable check passes. Cells
that the grounder cannot resolve are emitted as ``UNGROUNDED`` with a
specific reason; the disagreement builder then routes them to the
adjudicator.

``GROUNDER_VERSION`` is recorded in
``LabelingProvenance.grounder_version`` per case. Bump it whenever a
check function changes semantics (or a new check is added) so a
published gold set's provenance can never drift behind the live grounder.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Optional, Tuple

from pydantic import BaseModel

from eval.auto_label.append_gate import AppendGateError, assert_real_gold_appendable
from eval.auto_label.leakage_scan import scan_facts_for_leakage
from eval.auto_label.lookups.authorities import AuthorityLookup
from eval.auto_label.lookups.statutes import StatuteLookup
from eval.auto_label.span_match import MatchStrategy, match_quote_in_span
from eval.schema import GoldCase, Provenance


GROUNDER_VERSION = "1.0.0"


Verdict = Literal["GROUNDED", "UNGROUNDED"]
CheckRow = Tuple[str, Verdict, str]


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass
class GroundingResult:
    """Aggregate output of a single ``ground(...)`` invocation.

    ``field_path`` maps each granular path to ``GROUNDED`` /
    ``UNGROUNDED``; ``reasons`` carries a one-line reason per path
    (kept for both verdicts so reviewers can see *why* a cell passed or
    failed). ``match_strategy`` records, for cells where it applies (e.g.
    quote matching), which span-match strategy resolved the cell.
    """

    field_path: dict[str, Verdict] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    match_strategy: dict[str, str] = field(default_factory=dict)
    grounding_pass_rate: float = 0.0

    def is_ungrounded(self, path: str) -> bool:
        return self.field_path.get(path) == "UNGROUNDED"

    def ingest(self, rows: Iterable[CheckRow]) -> None:
        for path, verdict, reason in rows:
            self.field_path[path] = verdict
            self.reasons[path] = reason

    def recompute_pass_rate(self) -> None:
        total = len(self.field_path)
        grounded = sum(1 for v in self.field_path.values() if v == "GROUNDED")
        self.grounding_pass_rate = grounded / total if total else 0.0


@dataclass
class GroundingDeps:
    """Bundle of external dependencies the grounder reaches out to.

    The runner constructs one of these per case so ``ground(...)`` stays
    a pure function of (case, page text, page sections, spans, deps).
    """

    authority_lookup: AuthorityLookup
    statute_lookup: StatuteLookup
    run_artifact_path: Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_dict(obj: Any) -> Any:
    """Recursively normalise pydantic / Decimal / date values to JSON-native."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _as_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_as_dict(v) for v in obj]
    return obj


def _coerce_provenance(value: Any) -> Optional[Provenance]:
    """Accept either a ``Provenance`` instance or a dict; yield a Provenance."""
    if value is None:
        return None
    if isinstance(value, Provenance):
        return value
    if isinstance(value, Mapping):
        return Provenance.model_validate(dict(value))
    return None


def _attr(obj: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a Pydantic model OR a dict."""
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _provenance_for(case: Any, path: str) -> list[Provenance]:
    """Look up ``_field_provenance[path]`` on the partial case."""
    fp = _attr(case, "_field_provenance", {}) or {}
    raw = fp.get(path, []) if isinstance(fp, Mapping) else []
    out: list[Provenance] = []
    for entry in raw:
        coerced = _coerce_provenance(entry)
        if coerced is not None:
            out.append(coerced)
    return out


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # pragma: no cover - defensive
        return None


def _has_provenance(case: Any, path: str) -> bool:
    return bool(_provenance_for(case, path))


# ---------------------------------------------------------------------------
# check_quote
# ---------------------------------------------------------------------------


def check_quote(case: Any, page_text: dict[int, str]) -> list[CheckRow]:
    """Verify every ``key_reasoning_quotes[i]`` lands inside its declared span.

    Per sparring §3: a quote with no ``Provenance.text_span`` is
    ungrounded on the spot — we do not whole-document fuzzy-search. A
    quote with a span window calls into ``match_quote_in_span``;
    ``NO_MATCH`` is UNGROUNDED, ``CANONICAL_EXACT`` / ``BOUNDED_FUZZY``
    are GROUNDED with the strategy reported in the reason.
    """
    rows: list[CheckRow] = []
    quotes = _attr(case, "key_reasoning_quotes", []) or []
    for idx, quote in enumerate(quotes):
        path = f"key_reasoning_quotes[{idx}]"
        text = _attr(quote, "text", "")
        provenance = _coerce_provenance(_attr(quote, "provenance"))
        if provenance is None or provenance.text_span is None:
            rows.append((path, "UNGROUNDED", "missing text_span on provenance"))
            continue
        page_str = page_text.get(provenance.page, "")
        if not page_str:
            rows.append(
                (path, "UNGROUNDED", f"no page_text for page {provenance.page}")
            )
            continue
        char_start, char_end = provenance.text_span
        try:
            result = match_quote_in_span(
                quote=text,
                page_text=page_str,
                char_start=char_start,
                char_end=char_end,
            )
        except ValueError as exc:
            rows.append((path, "UNGROUNDED", f"invalid span: {exc}"))
            continue
        if result.strategy == MatchStrategy.NO_MATCH:
            rows.append((path, "UNGROUNDED", "quote not found in declared span"))
        else:
            rows.append((path, "GROUNDED", result.strategy.value))
    return rows


# ---------------------------------------------------------------------------
# check_authority / check_statute
# ---------------------------------------------------------------------------


def check_authority(case: Any, lookup: AuthorityLookup) -> list[CheckRow]:
    """Resolve every ``cited_authorities[i]`` against the authority index."""
    rows: list[CheckRow] = []
    authorities = _attr(case, "cited_authorities", []) or []
    for idx, authority in enumerate(authorities):
        name = _attr(authority, "name", "")
        cited = _attr(authority, "cited_date")
        path = f"cited_authorities[{idx}]"
        if not name or cited is None:
            rows.append((path, "UNGROUNDED", "missing name or cited_date"))
            continue
        if isinstance(cited, str):
            try:
                cited = date.fromisoformat(cited)
            except ValueError:
                rows.append((path, "UNGROUNDED", f"unparseable cited_date {cited!r}"))
                continue
        verdict = lookup.lookup(name=name, cited_date=cited)
        if verdict == "KNOWN":
            rows.append((path, "GROUNDED", "authority resolved against index"))
        elif verdict == "AMBIGUOUS":
            rows.append((path, "UNGROUNDED", "ambiguous match in authority index"))
        else:
            rows.append((path, "UNGROUNDED", "unknown authority"))
    return rows


def check_statute(case: Any, lookup: StatuteLookup) -> list[CheckRow]:
    """Resolve every ``statutory_basis[i]`` against the statutes index."""
    rows: list[CheckRow] = []
    statutes = _attr(case, "statutory_basis", []) or []
    for idx, ref in enumerate(statutes):
        name = _attr(ref, "statute", "")
        section = _attr(ref, "section", "")
        path = f"statutory_basis[{idx}]"
        if not name or not section:
            rows.append((path, "UNGROUNDED", "missing statute or section"))
            continue
        verdict = lookup.lookup(statute=name, section=section)
        if verdict == "KNOWN":
            rows.append((path, "GROUNDED", "statute+section resolved"))
        elif verdict == "WRONG_SECTION":
            rows.append(
                (path, "UNGROUNDED", "section not in statute index (wrong_section)")
            )
        else:
            rows.append((path, "UNGROUNDED", "unknown statute"))
    return rows


# ---------------------------------------------------------------------------
# check_outcome_basis
# ---------------------------------------------------------------------------


def check_outcome_basis(case: Any) -> list[CheckRow]:
    """Every outcome cell must have a basis span in ``_field_provenance``.

    Per sparring §1, ``ground_truth_outcome.{overall_winner,
    total_awarded_gbp}`` plus every ``per_issue[*].{winner, awarded_gbp}``
    and ``unapportioned_reason`` (when set) require a provenance entry.
    Missing provenance = UNGROUNDED.
    """
    rows: list[CheckRow] = []
    outcome = _attr(case, "ground_truth_outcome")
    if outcome is None:
        return rows

    targets = [
        "ground_truth_outcome.overall_winner",
        "ground_truth_outcome.total_awarded_gbp",
    ]
    per_issue = _attr(outcome, "per_issue", []) or []
    for io in per_issue:
        issue = _attr(io, "issue", "?")
        targets.append(f"ground_truth_outcome.per_issue[issue={issue}].winner")
        targets.append(f"ground_truth_outcome.per_issue[issue={issue}].awarded_gbp")
    if _attr(outcome, "unapportioned_reason"):
        targets.append("ground_truth_outcome.unapportioned_reason")

    for path in targets:
        if _has_provenance(case, path):
            rows.append((path, "GROUNDED", "basis span present"))
        else:
            rows.append((path, "UNGROUNDED", "missing basis span"))
    return rows


# ---------------------------------------------------------------------------
# check_label_basis
# ---------------------------------------------------------------------------


def check_label_basis(case: Any) -> list[CheckRow]:
    """``claim_types``, ``matter_type``, ``disputed_amount_gbp`` and every
    ``claimed_amounts[*].amount_gbp`` need a basis span."""
    rows: list[CheckRow] = []
    targets: list[str] = []
    if _attr(case, "claim_types") is not None:
        targets.append("claim_types")
    if _attr(case, "matter_type") is not None:
        targets.append("matter_type")
    if _attr(case, "disputed_amount_gbp") is not None:
        targets.append("disputed_amount_gbp")
    for ca in _attr(case, "claimed_amounts", []) or []:
        issue = _attr(ca, "issue", "?")
        by_party = _attr(ca, "by_party", "?")
        by_party_str = by_party.value if isinstance(by_party, Enum) else str(by_party)
        targets.append(
            f"claimed_amounts[issue={issue}|by_party={by_party_str}].amount_gbp"
        )

    for path in targets:
        if _has_provenance(case, path):
            rows.append((path, "GROUNDED", "basis span present"))
        else:
            rows.append((path, "UNGROUNDED", "missing basis span"))
    return rows


# ---------------------------------------------------------------------------
# check_facts_leakage
# ---------------------------------------------------------------------------


def check_facts_leakage(
    case: Any,
    page_text: dict[int, str],
    page_sections: dict[tuple[int, int], str],
) -> list[CheckRow]:
    """Wrap ``scan_facts_for_leakage`` for the grounder."""
    del page_text  # unused — leakage check is text-only on facts itself
    facts = _attr(case, "facts")
    if not facts:
        return []
    spans = _provenance_for(case, "facts")
    findings = scan_facts_for_leakage(facts, spans, page_sections)
    if not findings:
        return [("facts", "GROUNDED", "no leakage detected")]
    detail = "; ".join(f"{f.rule}:{f.detail}" for f in findings)
    return [("facts", "UNGROUNDED", f"facts leakage: {detail}")]


# ---------------------------------------------------------------------------
# check_date_sanity
# ---------------------------------------------------------------------------


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def check_date_sanity(case: Any) -> list[CheckRow]:
    """``decision_date`` is required; every ``cited_date`` must be ≤ it."""
    rows: list[CheckRow] = []
    decision = _to_date(_attr(case, "decision_date"))
    if decision is None:
        rows.append(("decision_date", "UNGROUNDED", "decision_date is required"))
        return rows
    rows.append(("decision_date", "GROUNDED", "decision_date present"))
    for idx, authority in enumerate(_attr(case, "cited_authorities", []) or []):
        cited = _to_date(_attr(authority, "cited_date"))
        path = f"cited_authorities[{idx}].cited_date"
        if cited is None:
            rows.append((path, "UNGROUNDED", "cited_date missing or unparseable"))
            continue
        if cited > decision:
            rows.append(
                (
                    path,
                    "UNGROUNDED",
                    f"cited_date {cited.isoformat()} > decision_date "
                    f"{decision.isoformat()} (temporal leakage)",
                )
            )
        else:
            rows.append((path, "GROUNDED", "cited_date <= decision_date"))
    return rows


# ---------------------------------------------------------------------------
# check_amount_sanity
# ---------------------------------------------------------------------------


def check_amount_sanity(case: Any) -> list[CheckRow]:
    """INV-5/6/9-style reconciliation for outcome and claimed amounts."""
    rows: list[CheckRow] = []
    outcome = _attr(case, "ground_truth_outcome")
    if outcome is not None:
        per_issue = _attr(outcome, "per_issue", []) or []
        unapp = _attr(outcome, "unapportioned_reason")
        total = _decimal(_attr(outcome, "total_awarded_gbp"))
        path = "ground_truth_outcome.total_awarded_gbp"
        if unapp and per_issue:
            rows.append(
                (
                    path,
                    "UNGROUNDED",
                    "unapportioned_reason set but per_issue is non-empty",
                )
            )
        elif per_issue and total is not None:
            issue_sum = sum(
                (
                    _decimal(_attr(io, "awarded_gbp")) or Decimal("0")
                    for io in per_issue
                ),
                start=Decimal("0"),
            )
            if issue_sum != total:
                rows.append(
                    (
                        path,
                        "UNGROUNDED",
                        f"sum(per_issue.awarded_gbp)={issue_sum} != "
                        f"total_awarded_gbp={total}",
                    )
                )
            else:
                rows.append((path, "GROUNDED", "per-issue sum matches total"))

    disputed = _decimal(_attr(case, "disputed_amount_gbp"))
    claimed = _attr(case, "claimed_amounts", []) or []
    if disputed is not None and claimed:
        claimed_sum = sum(
            (_decimal(_attr(ca, "amount_gbp")) or Decimal("0") for ca in claimed),
            start=Decimal("0"),
        )
        path = "disputed_amount_gbp"
        if disputed < claimed_sum:
            rows.append(
                (
                    path,
                    "UNGROUNDED",
                    f"disputed_amount_gbp={disputed} < sum(claimed_amounts)={claimed_sum}",
                )
            )
        else:
            rows.append((path, "GROUNDED", "disputed >= sum(claimed)"))
    return rows


# ---------------------------------------------------------------------------
# check_invariants
# ---------------------------------------------------------------------------


_FIXTURE_PATH = (
    Path(__file__).parent.parent / "tests" / "fixtures" / "gold_case_minimal.json"
)


def _fixture_defaults() -> dict[str, Any]:
    return json.loads(_FIXTURE_PATH.read_text())


def _strip_private_keys(case: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in case.items() if not k.startswith("_")}


def check_invariants(case: Any) -> list[CheckRow]:
    """Validate the partial case against ``GoldCase`` after merging defaults.

    Missing required fields are filled from the
    ``gold_case_minimal.json`` fixture so the partial case has a real
    ``GoldCase`` shape; INV-1..INV-10 then run as Pydantic validators. A
    failure surfaces the Pydantic error message in the reason string so
    the adjudicator can see which invariant tripped.
    """
    if isinstance(case, BaseModel):
        partial = case.model_dump(mode="json")
    elif isinstance(case, Mapping):
        partial = _as_dict(_strip_private_keys(case))
    else:
        partial = {}

    merged: dict[str, Any] = {**_fixture_defaults(), **partial}
    try:
        GoldCase.model_validate(merged)
    except Exception as exc:
        return [
            (
                "__invariants__",
                "UNGROUNDED",
                f"invariant violated: {type(exc).__name__}: {exc}",
            )
        ]
    return [("__invariants__", "GROUNDED", "GoldCase round-trip succeeded")]


# ---------------------------------------------------------------------------
# check_real_gold_audit
# ---------------------------------------------------------------------------


def check_real_gold_audit(case: Any, run_artifact_path: Path) -> list[CheckRow]:
    """Wrap the append gate for the grounder.

    Returns one synthetic ``__append_gate__`` row: GROUNDED iff the gate
    accepts. UNGROUNDED rows quote the rule name and detail from
    ``AppendGateError`` so the adjudicator can see which §8 rule refused
    the row.
    """
    if isinstance(case, GoldCase):
        gc: GoldCase = case
    else:
        if isinstance(case, BaseModel):
            partial = case.model_dump(mode="json")
        elif isinstance(case, Mapping):
            partial = _as_dict(_strip_private_keys(case))
        else:
            partial = {}
        try:
            gc = GoldCase.model_validate(partial)
        except Exception as exc:
            return [
                (
                    "__append_gate__",
                    "UNGROUNDED",
                    f"append gate refused: GoldCase did not validate: {exc}",
                )
            ]
    try:
        assert_real_gold_appendable(gc, run_artifact_path=run_artifact_path)
    except AppendGateError as exc:
        return [("__append_gate__", "UNGROUNDED", f"append gate refused: {exc}")]
    return [("__append_gate__", "GROUNDED", "append gate accepted")]


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def ground(
    case: Any,
    *,
    page_text: dict[int, str],
    page_sections: dict[tuple[int, int], str],
    spans: list[Provenance],
    lookups: GroundingDeps,
) -> GroundingResult:
    """Run every per-field check and aggregate verdicts.

    The runner calls this once per case after both labelers return. The
    output's ``grounding_pass_rate`` feeds
    ``LabelingProvenance.grounding_pass_rate``; ``field_path`` feeds the
    disagreement set; ``reasons`` feeds the adjudicator UI.
    """
    del spans  # currently consumed transitively via case._field_provenance
    result = GroundingResult()

    result.ingest(check_quote(case, page_text))
    result.ingest(check_authority(case, lookups.authority_lookup))
    result.ingest(check_statute(case, lookups.statute_lookup))
    result.ingest(check_outcome_basis(case))
    result.ingest(check_label_basis(case))
    result.ingest(check_facts_leakage(case, page_text, page_sections))
    result.ingest(check_date_sanity(case))
    result.ingest(check_amount_sanity(case))
    result.ingest(check_invariants(case))
    result.ingest(check_real_gold_audit(case, lookups.run_artifact_path))

    result.recompute_pass_rate()
    return result


__all__ = [
    "GROUNDER_VERSION",
    "CheckRow",
    "GroundingDeps",
    "GroundingResult",
    "Verdict",
    "check_amount_sanity",
    "check_authority",
    "check_date_sanity",
    "check_facts_leakage",
    "check_invariants",
    "check_label_basis",
    "check_outcome_basis",
    "check_quote",
    "check_real_gold_audit",
    "check_statute",
    "ground",
]
