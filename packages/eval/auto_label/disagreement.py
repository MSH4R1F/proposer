"""Field-path DisagreementSet builder for the LLM-labeling pipeline.

Per §4 of ``.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md``: the
adjudication CLI consumes ``(case, field_path)`` cells, NOT whole top-level
fields. List-valued fields (``evidence``, ``claimed_amounts``,
``cited_authorities``, ``statutory_basis``, ``ground_truth_outcome.per_issue``)
are matched element-wise via stable identity keys derived from canonicalised
content, then compared subfield-by-subfield. Two list elements that share an
identity key inside a single labeler's output (a collision) escalate the whole
list to ``list_identity_unresolved`` rather than being silently de-duplicated.

Set-membership predicate, paraphrased from the codex doc::

    DisagreementSet = {
       (case, field_path) | canonical(A[field_path]) != canonical(B[field_path])
       OR A.field_path UNGROUNDED OR B.field_path UNGROUNDED
       OR A.field_path basis_span_missing OR B.field_path basis_span_missing
       OR (A is None) XOR (B is None)
       OR list-key collision unresolved
    }

`PartialGoldCase` design choice
-------------------------------
We use ``TypedDict(total=False)`` rather than a Pydantic model with all
fields ``Optional``. Reasons:

1. Labeler output that fails to ground a cell emits ``None`` or omits the
   key entirely. A Pydantic-all-Optional approach would force every nested
   schema (e.g. ``IssueOutcome.winner``) to also become Optional, which
   ripples into the live ``GoldCase`` validators. The Phase 5 brief
   explicitly forbids touching ``schema.py``.
2. The disagreement walker is a pure function of presence/absence and value
   equality; it does not need Pydantic validation. Validation happens at
   the auto-grounder boundary (Phase 8).
3. List elements inside a partial case are still real ``Evidence`` /
   ``IssueOutcome`` model instances — the partial-ness is at top-level
   field presence and at scalar None-ability. Labelers that cannot ground
   an entire list emit no entry; partial within-element labelling is
   represented by simply omitting the offending list element rather than
   carrying half an element forward.

This keeps the seam between labeler -> grounder -> adjudication a plain
``dict[str, Any]`` shape.

`GroundingResult` is a placeholder for the Phase 8 grounder's output. It
gives ``build_disagreement_set`` the GROUNDED/UNGROUNDED verdict per field
path. The grounder will replace/extend this dataclass; current code only
needs the input shape it consumes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Literal, TypedDict

from eval.auto_label.canonicalize import canonicalize_text
from eval.schema import (
    Authority,
    ClaimedAmount,
    Evidence,
    IssueOutcome,
    StatutoryReference,
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class PartialGoldCase(TypedDict, total=False):
    """A labeler's emitted ``GoldCase`` view with optional fields.

    Mirrors ``GoldCase`` field names. Any field a labeler could not ground
    is either omitted or set to ``None``. List elements are concrete
    Pydantic instances (``Evidence``, ``IssueOutcome``, etc.); a labeler
    that cannot ground a list element drops the element entirely rather
    than emitting a half-built model.
    """

    schema_version: Any
    case_id: str | None
    decision_date: Any
    region: Any
    region_source: str | None
    case_size: Any
    disputed_amount_gbp: Decimal | None
    claim_types: list[Any] | None
    source_pdf_sha256: str | None
    ocr_confidence: float | None
    parties: list[Any] | None
    facts: str | None
    evidence: list[Evidence] | None
    evidence_unavailable_reason: str | None
    statutory_basis: list[StatutoryReference] | None
    statutory_basis_unavailable_reason: str | None
    cited_authorities: list[Authority] | None
    claimed_amounts: list[ClaimedAmount] | None
    ground_truth_outcome: dict[str, Any] | None
    key_reasoning_quotes: list[Any] | None
    domain_id: str | None
    forum: str | None
    source_url: str | None
    source_license: str | None
    retrieval_namespace_id: str | None
    target_source_id: str | None
    excluded_source_ids: list[str] | None
    law_effective_date: Any
    train_test_split: Any
    source_publisher: str | None
    source_kind: str | None
    corpus_version: str | None
    matter_type: str | None
    negative_kind: str | None
    expected_outcome: str | None
    expected_redactions: list[str] | None
    expected_redacted_text: str | None


# Reason codes — every cell that fails the set-membership predicate gets
# exactly one row tagged with one of these.
DisagreementReason = Literal[
    "a_b_mismatch",
    "a_ungrounded",
    "b_ungrounded",
    "invariant_failed",
    "basis_span_missing",
    "null_xor",
    "list_identity_unresolved",
]


@dataclass(frozen=True)
class DisagreementRow:
    field_path: str
    a_value: Any
    b_value: Any
    reason: DisagreementReason


@dataclass
class GroundingResult:
    """Phase 8 auto-grounder output.

    ``field_path`` maps each granular path to a verdict; ``reasons`` carries
    a one-line explanation per path. ``grounding_pass_rate`` is
    |GROUNDED| / |GROUNDED ∪ UNGROUNDED| over emitted cells (used by
    ``LabelingProvenance.grounding_pass_rate``).
    """

    field_path: dict[str, Literal["GROUNDED", "UNGROUNDED"]] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    grounding_pass_rate: float = 0.0

    def is_ungrounded(self, path: str) -> bool:
        return self.field_path.get(path) == "UNGROUNDED"

    @classmethod
    def from_rows(
        cls,
        rows: Iterable[tuple[str, str, str]],
    ) -> "GroundingResult":
        """Build a ``GroundingResult`` from ``(path, verdict, reason)`` rows.

        ``verdict`` must be ``"GROUNDED"`` or ``"UNGROUNDED"``. Pass rate is
        computed over emitted rows; an empty input yields ``0.0`` (no
        signal to report). Later rows override earlier rows on the same
        path — callers should not emit duplicate paths but the
        last-write-wins rule keeps the function total.
        """
        field_path: dict[str, Literal["GROUNDED", "UNGROUNDED"]] = {}
        reasons: dict[str, str] = {}
        for path, verdict, reason in rows:
            if verdict not in ("GROUNDED", "UNGROUNDED"):
                raise ValueError(
                    f"GroundingResult.from_rows got verdict={verdict!r} "
                    f"for path={path!r}; expected GROUNDED or UNGROUNDED"
                )
            field_path[path] = verdict  # type: ignore[assignment]
            reasons[path] = reason
        total = len(field_path)
        grounded = sum(1 for v in field_path.values() if v == "GROUNDED")
        rate = grounded / total if total else 0.0
        return cls(
            field_path=field_path,
            reasons=reasons,
            grounding_pass_rate=rate,
        )


# ---------------------------------------------------------------------------
# Identity key builders
# ---------------------------------------------------------------------------


def _norm_token(text: str, *, max_len: int | None = None) -> str:
    """Canonicalise a string for use as an identity-key component."""
    out = canonicalize_text(text or "").lower()
    if max_len is not None:
        out = out[:max_len]
    return out


def field_path_for_evidence(idx: int, ev: Evidence) -> str:
    """Stable ``evidence[...]`` path for an Evidence row.

    The ``idx`` is accepted for parity with the other helpers but is NOT
    used in the key — identity must survive list reordering. The key uses
    the first whitespace-stripped word of the canonicalised ``kind`` plus
    the first 32 chars of the canonicalised ``description``.
    """
    del idx  # unused; identity must not depend on position
    kind_tokens = _norm_token(ev.kind).split()
    kind_head = kind_tokens[0] if kind_tokens else ""
    desc_head = _norm_token(ev.description, max_len=32)
    return f"evidence[{desc_head}|kind={kind_head}]"


def field_path_for_claimed_amount(idx: int, ca: ClaimedAmount) -> str:
    """Stable ``claimed_amounts[issue=...|by_party=...]`` path."""
    del idx
    issue = _norm_token(ca.issue)
    party = ca.by_party.value if hasattr(ca.by_party, "value") else str(ca.by_party)
    return f"claimed_amounts[issue={issue}|by_party={party}]"


def field_path_for_per_issue(idx: int, io: IssueOutcome) -> str:
    """Stable ``ground_truth_outcome.per_issue[issue=...]`` path."""
    del idx
    issue = _norm_token(io.issue)
    return f"ground_truth_outcome.per_issue[issue={issue}]"


def field_path_for_authority(idx: int, auth: Authority) -> str:
    """Stable ``cited_authorities[name=...|cited_date=...]`` path."""
    del idx
    name = _norm_token(auth.name)
    cited = auth.cited_date.isoformat() if auth.cited_date is not None else ""
    return f"cited_authorities[name={name}|cited_date={cited}]"


def field_path_for_statutory_basis(idx: int, ref: StatutoryReference) -> str:
    """Stable ``statutory_basis[statute=...|section=...]`` path."""
    del idx
    statute = _norm_token(ref.statute)
    section = _norm_token(ref.section)
    return f"statutory_basis[statute={statute}|section={section}]"


# ---------------------------------------------------------------------------
# Comparison core
# ---------------------------------------------------------------------------


# Top-level scalar / enum / decimal fields whose canonical equality is plain
# ``==``. Lists and the per-issue nested object are walked separately.
_SCALAR_FIELDS: tuple[str, ...] = (
    "schema_version",
    "case_id",
    "decision_date",
    "region",
    "region_source",
    "case_size",
    "disputed_amount_gbp",
    "claim_types",  # list[ClaimType] — order-insensitive set compare below
    "source_pdf_sha256",
    "ocr_confidence",
    "parties",  # list[Party] — order-insensitive set compare below
    "facts",
    "evidence_unavailable_reason",
    "statutory_basis_unavailable_reason",
    "domain_id",
    "forum",
    "source_url",
    "source_license",
    "retrieval_namespace_id",
    "target_source_id",
    "excluded_source_ids",
    "law_effective_date",
    "train_test_split",
    "source_publisher",
    "source_kind",
    "corpus_version",
    "matter_type",
    "negative_kind",
    "expected_outcome",
    "expected_redactions",
    "expected_redacted_text",
)


_LIST_FIELD_HANDLERS = {
    "evidence": ("evidence", field_path_for_evidence, ("kind", "description", "provenance")),
    "claimed_amounts": (
        "claimed_amounts",
        field_path_for_claimed_amount,
        ("issue", "amount_gbp", "by_party"),
    ),
    "cited_authorities": (
        "cited_authorities",
        field_path_for_authority,
        ("name", "court", "cited_date", "provenance"),
    ),
    "statutory_basis": (
        "statutory_basis",
        field_path_for_statutory_basis,
        ("statute", "section", "provenance"),
    ),
}


def _canonical(value: Any) -> Any:
    """Return a comparison-stable representation for a cell value.

    Strings are canonicalised; everything else is returned unchanged.
    Pydantic enums compare by identity already.
    """
    if isinstance(value, str):
        return canonicalize_text(value)
    return value


def _emit_grounding(
    rows: list[DisagreementRow],
    path: str,
    a_val: Any,
    b_val: Any,
    grounding_a: GroundingResult,
    grounding_b: GroundingResult,
) -> bool:
    """If either side is ungrounded for ``path``, emit and return True."""
    a_un = grounding_a.is_ungrounded(path)
    b_un = grounding_b.is_ungrounded(path)
    if a_un and b_un:
        # Both ungrounded — emit one row per side so adjudication sees both.
        rows.append(DisagreementRow(path, a_val, b_val, "a_ungrounded"))
        rows.append(DisagreementRow(path, a_val, b_val, "b_ungrounded"))
        return True
    if a_un:
        rows.append(DisagreementRow(path, a_val, b_val, "a_ungrounded"))
        return True
    if b_un:
        rows.append(DisagreementRow(path, a_val, b_val, "b_ungrounded"))
        return True
    return False


def _compare_scalar(
    rows: list[DisagreementRow],
    path: str,
    a_val: Any,
    b_val: Any,
    grounding_a: GroundingResult,
    grounding_b: GroundingResult,
) -> None:
    a_present = a_val is not None
    b_present = b_val is not None
    if not a_present and not b_present:
        return
    # Null XOR: one side has a value, the other emitted None
    if a_present != b_present:
        rows.append(DisagreementRow(path, a_val, b_val, "null_xor"))
        return
    # Both present: check grounding first, then value equality.
    if _emit_grounding(rows, path, a_val, b_val, grounding_a, grounding_b):
        return
    if _canonical(a_val) != _canonical(b_val):
        rows.append(DisagreementRow(path, a_val, b_val, "a_b_mismatch"))


def _bucket_by_key(items: list[Any], key_fn) -> tuple[dict[str, Any], bool]:
    """Bucket list elements by identity key. Returns (mapping, collision_seen).

    On collision (two elements share a key inside the same labeler's output)
    the bucket value is left as the FIRST seen element and ``collision_seen``
    is set True so the caller can emit a single ``list_identity_unresolved``.
    """
    out: dict[str, Any] = {}
    collision = False
    for i, el in enumerate(items):
        k = key_fn(i, el)
        if k in out:
            collision = True
        else:
            out[k] = el
    return out, collision


def _compare_list_field(
    rows: list[DisagreementRow],
    parent_path: str,
    a_items: list[Any] | None,
    b_items: list[Any] | None,
    key_fn,
    subfields: tuple[str, ...],
    grounding_a: GroundingResult,
    grounding_b: GroundingResult,
) -> None:
    """Bucket A and B by identity key, then compare element subfields."""
    a_items = list(a_items or [])
    b_items = list(b_items or [])
    if not a_items and not b_items:
        return

    a_buckets, a_collision = _bucket_by_key(a_items, key_fn)
    b_buckets, b_collision = _bucket_by_key(b_items, key_fn)

    if a_collision or b_collision:
        rows.append(
            DisagreementRow(
                field_path=parent_path,
                a_value=a_items if a_collision else None,
                b_value=b_items if b_collision else None,
                reason="list_identity_unresolved",
            )
        )
        return

    all_keys = set(a_buckets) | set(b_buckets)
    for key in sorted(all_keys):
        a_el = a_buckets.get(key)
        b_el = b_buckets.get(key)
        if (a_el is None) != (b_el is None):
            # Element present on one side only -> null XOR at element-level path
            rows.append(
                DisagreementRow(
                    field_path=key,
                    a_value=a_el,
                    b_value=b_el,
                    reason="null_xor",
                )
            )
            continue
        # Both sides have the element by key — compare subfields
        for sub in subfields:
            sub_path = f"{key}.{sub}"
            a_sv = getattr(a_el, sub, None)
            b_sv = getattr(b_el, sub, None)
            _compare_scalar(rows, sub_path, a_sv, b_sv, grounding_a, grounding_b)


def _compare_per_issue(
    rows: list[DisagreementRow],
    a_outcome: dict[str, Any] | None,
    b_outcome: dict[str, Any] | None,
    grounding_a: GroundingResult,
    grounding_b: GroundingResult,
) -> None:
    """Compare the per_issue list inside ground_truth_outcome.

    Outcome may be a dict-shaped partial OR a real GroundTruthOutcome
    instance. We only need ``per_issue`` for Phase 5; full-outcome scalar
    comparison is handled by the parent walker.
    """
    def _per_issue_of(o: Any) -> list[Any]:
        if o is None:
            return []
        if isinstance(o, dict):
            return list(o.get("per_issue") or [])
        return list(getattr(o, "per_issue", []) or [])

    a_items = _per_issue_of(a_outcome)
    b_items = _per_issue_of(b_outcome)
    _compare_list_field(
        rows,
        parent_path="ground_truth_outcome.per_issue",
        a_items=a_items,
        b_items=b_items,
        key_fn=field_path_for_per_issue,
        subfields=("winner", "awarded_gbp"),
        grounding_a=grounding_a,
        grounding_b=grounding_b,
    )


def _outcome_scalar(outcome: Any, field_name: str) -> Any:
    if outcome is None:
        return None
    if isinstance(outcome, dict):
        return outcome.get(field_name)
    return getattr(outcome, field_name, None)


def _compare_outcome_scalars(
    rows: list[DisagreementRow],
    a_outcome: Any,
    b_outcome: Any,
    grounding_a: GroundingResult,
    grounding_b: GroundingResult,
) -> None:
    """Compare scalar cells under ``ground_truth_outcome``.

    These cells are MandatoryReviewSet fields, but they still need to
    appear in DisagreementSet when A/B disagree or either side is ungrounded
    so adjudication queues can explain why the field is being surfaced.
    """
    for subfield in (
        "overall_winner",
        "total_awarded_gbp",
        "unapportioned_reason",
    ):
        path = f"ground_truth_outcome.{subfield}"
        _compare_scalar(
            rows,
            path,
            _outcome_scalar(a_outcome, subfield),
            _outcome_scalar(b_outcome, subfield),
            grounding_a,
            grounding_b,
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_disagreement_set(
    a: PartialGoldCase | dict[str, Any],
    b: PartialGoldCase | dict[str, Any],
    grounding_a: GroundingResult,
    grounding_b: GroundingResult,
) -> list[DisagreementRow]:
    """Walk every comparable cell of ``a`` and ``b`` and return one
    ``DisagreementRow`` per disagreeing/ungrounded/null-XOR cell.

    Lists are matched by their identity keys and compared subfield-by-subfield.
    A within-list identity collision (two elements sharing a key inside the
    same labeler's output) emits a single ``list_identity_unresolved`` row at
    the parent path; per-element rows are suppressed in that case so the
    human adjudicator addresses the collision before drilling into subfields.
    """
    rows: list[DisagreementRow] = []

    # 1. Top-level scalar / order-insensitive list fields
    for fname in _SCALAR_FIELDS:
        a_val = a.get(fname)
        b_val = b.get(fname)
        if fname in ("claim_types", "parties", "excluded_source_ids", "expected_redactions"):
            # Order-insensitive set comparison for these list-typed scalars.
            # We compare by canonicalised representation.
            a_present = a_val is not None
            b_present = b_val is not None
            if not a_present and not b_present:
                continue
            if a_present != b_present:
                rows.append(DisagreementRow(fname, a_val, b_val, "null_xor"))
                continue
            if _emit_grounding(rows, fname, a_val, b_val, grounding_a, grounding_b):
                continue
            try:
                a_set = set(_canonical(x) if isinstance(x, str) else x for x in a_val)
                b_set = set(_canonical(x) if isinstance(x, str) else x for x in b_val)
                if a_set != b_set:
                    rows.append(DisagreementRow(fname, a_val, b_val, "a_b_mismatch"))
            except TypeError:
                # Unhashable elements (e.g. Pydantic Party). Fall back to
                # element-wise equality on canonical repr.
                if [_canonical(x) for x in a_val] != [_canonical(x) for x in b_val]:
                    rows.append(DisagreementRow(fname, a_val, b_val, "a_b_mismatch"))
            continue
        _compare_scalar(rows, fname, a_val, b_val, grounding_a, grounding_b)

    # 2. List fields with identity keys
    for fname, (_alias, key_fn, subfields) in _LIST_FIELD_HANDLERS.items():
        _compare_list_field(
            rows,
            parent_path=fname,
            a_items=a.get(fname),
            b_items=b.get(fname),
            key_fn=key_fn,
            subfields=subfields,
            grounding_a=grounding_a,
            grounding_b=grounding_b,
        )

    # 3. Nested ground_truth_outcome scalar cells + per_issue
    _compare_outcome_scalars(
        rows,
        a.get("ground_truth_outcome"),
        b.get("ground_truth_outcome"),
        grounding_a,
        grounding_b,
    )
    _compare_per_issue(
        rows,
        a.get("ground_truth_outcome"),
        b.get("ground_truth_outcome"),
        grounding_a,
        grounding_b,
    )

    return rows
