"""Deterministic post-generation forum-policy verifier (SHA-62).

The model-side prompt instructions are best-effort. This verifier is the
fail-closed gate that runs AFTER the model produces output. In production
and beta modes a violation suppresses (truncates / quarantines) the
user-facing payload; in research mode violations are logged + annotated
into ``output["forum_policy_warnings"]`` but the payload still flows so
researchers can study the failure.

Checks (minimum):

1. Prohibited phrases from the matched ``ForumProfile.prohibited_phrases``
   are not present anywhere in the textual fields.
2. Required disclaimers are present verbatim or in the documented canonical
   paraphrase set.
3. Citation kinds (when annotated on supporting cases) are inside the
   forum's ``citation_kinds`` allowlist.
4. Citation source kinds (when annotated) are inside the forum's
   ``source_kinds`` allowlist.
5. Output framing — the output's narrative does not use court-damages
   language for an Ombudsman forum, RRO scope-fence terms for the RRO pack,
   or directive-advice terms for any forum that has them prohibited.
6. Statutory-limit claims (1x-3x deposit, basic award £751 cap) MUST come
   with a deterministic calculator trace; flag ``calculator_trace_required``
   if the trace is missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from domain_core.spec import ForumProfile

from ..models.prediction_v2 import PredictionMode


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class ForumPolicyViolationKind(str, Enum):
    PROHIBITED_PHRASE = "prohibited_phrase"
    MISSING_DISCLAIMER = "missing_disclaimer"
    CITATION_KIND_MISUSE = "citation_kind_misuse"
    SOURCE_KIND_MISUSE = "source_kind_misuse"
    OUTPUT_FRAMING = "output_framing"
    DIRECTIVE_ADVICE = "directive_advice"
    CALCULATOR_TRACE_REQUIRED = "calculator_trace_required"


@dataclass(frozen=True)
class ForumPolicyViolation:
    kind: ForumPolicyViolationKind
    message: str
    field_path: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "kind": self.kind.value,
            "message": self.message,
            "field_path": self.field_path,
        }


@dataclass
class ForumPolicyResult:
    passed: bool
    violations: List[ForumPolicyViolation] = field(default_factory=list)
    output_after_redaction: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Canonical paraphrase set for required disclaimers
# ---------------------------------------------------------------------------


_DISCLAIMER_PARAPHRASES: Dict[str, List[str]] = {
    "This is legal information based on similar published decisions, not legal advice.": [
        "this is legal information based on similar published decisions, not legal advice",
        "this is information from similar published decisions, not legal advice",
        "this is legal information based on analysis of similar tribunal cases",
    ],
    "This is information about Housing Ombudsman determinations, not legal advice.": [
        "this is information about housing ombudsman determinations, not legal advice",
        "this is information based on housing ombudsman determinations, not legal advice",
    ],
    "This is legal information based on similar published Property Chamber decisions, not legal advice.": [
        "this is legal information based on similar published property chamber decisions, not legal advice",
        "this is information based on property chamber decisions, not legal advice",
    ],
    "This is legal information based on similar published Employment Tribunal decisions, not legal advice.": [
        "this is legal information based on similar published employment tribunal decisions, not legal advice",
        "this is information based on employment tribunal decisions, not legal advice",
    ],
    "Employment claims have strict time limits - see ACAS early conciliation.": [
        "employment claims have strict time limits - see acas early conciliation",
        "employment claims have strict time limits — see acas early conciliation",
        "employment claims have strict time limits, see acas early conciliation",
    ],
}


# Phrases that are directive legal advice — never acceptable from any pack.
_UNIVERSAL_DIRECTIVE_PHRASES = [
    "you should accept",
    "you should sue",
    "you should reject",
    "we recommend you sue",
    "we recommend you accept",
    "you must accept",
]


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


class ForumPolicyVerifier:
    """Deterministic gate over a model-generated prediction payload."""

    # Statutory-limit phrases that REQUIRE a calculator trace citation.
    _STATUTORY_LIMIT_TRIGGERS = [
        "1x-3x",
        "1x to 3x",
        "1×-3×",
        "1× to 3×",
        "one to three times the deposit",
        "basic award weekly cap",
        "£751",
        "weekly pay cap",
        "twelve months' rent",
        "12 months' rent",
        "12 months of rent",
    ]

    def __init__(
        self,
        forum_profile: ForumProfile,
        mode: PredictionMode,
        *,
        extra_prohibited_phrases: Optional[Iterable[str]] = None,
    ):
        self.forum_profile = forum_profile
        self.mode = mode
        # Pack-level prohibited phrases augment the YAML profile's list. RRO
        # uses this to enforce its hard scope-fence (leasehold, Tenant Fees
        # Act, park homes, building safety).
        self._extra_prohibited_phrases = tuple(extra_prohibited_phrases or ())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(self, output: Dict[str, Any]) -> ForumPolicyResult:
        violations: List[ForumPolicyViolation] = []

        text_blob, text_fields = self._collect_text(output)
        lower_blob = text_blob.lower()

        violations.extend(self._check_prohibited_phrases(lower_blob, text_fields))
        violations.extend(self._check_universal_directives(lower_blob))
        violations.extend(self._check_required_disclaimers(lower_blob))
        violations.extend(self._check_citations(output))
        violations.extend(
            self._check_calculator_trace_for_statutory_limits(lower_blob, output)
        )

        passed = not violations

        # Redaction / quarantine behaviour depends on mode.
        redacted = dict(output)
        if not passed:
            warning_strings = [v.message for v in violations]
            existing = list(redacted.get("forum_policy_warnings") or [])
            redacted["forum_policy_warnings"] = existing + warning_strings

            if self.mode in (PredictionMode.HYBRID, PredictionMode.RAG_ONLY):
                # Treat HYBRID and RAG_ONLY as production/beta posture for the
                # purposes of forum-policy enforcement — quarantine the
                # narrative reasoning + zero out predicted amount + force the
                # outcome to "uncertain" so the user-facing product cannot
                # surface non-compliant content.
                redacted = self._quarantine(redacted, violations)
            # In other modes (LLM_ONLY, KG_ONLY) we stay in research posture:
            # warnings annotated, output otherwise unchanged.

        return ForumPolicyResult(
            passed=passed, violations=violations, output_after_redaction=redacted
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _collect_text(
        self, output: Dict[str, Any]
    ) -> tuple[str, Dict[str, str]]:
        """Concatenate textual fields and keep a per-field map for diagnostics."""
        fields: Dict[str, str] = {}
        for key in (
            "reasoning",
            "issue_description",
            "data_completeness_impact",
            "outcome_summary",
            "disclaimer",
        ):
            value = output.get(key)
            if isinstance(value, str):
                fields[key] = value
        # Pull narrative fields out of nested supporting cases too.
        cases = output.get("supporting_cases")
        if isinstance(cases, list):
            for idx, case in enumerate(cases):
                if not isinstance(case, dict):
                    continue
                for sub in ("quote", "relevance"):
                    sub_val = case.get(sub)
                    if isinstance(sub_val, str):
                        fields[f"supporting_cases[{idx}].{sub}"] = sub_val
        blob = "\n".join(fields.values())
        return blob, fields

    def _check_prohibited_phrases(
        self, lower_blob: str, text_fields: Dict[str, str]
    ) -> Iterable[ForumPolicyViolation]:
        all_phrases = list(self.forum_profile.prohibited_phrases) + list(
            self._extra_prohibited_phrases
        )
        for phrase in all_phrases:
            phrase_lower = phrase.lower()
            if phrase_lower in lower_blob:
                # Find which field triggered it for nicer diagnostics.
                offending_field = ""
                for fname, fval in text_fields.items():
                    if phrase_lower in fval.lower():
                        offending_field = fname
                        break
                yield ForumPolicyViolation(
                    kind=ForumPolicyViolationKind.PROHIBITED_PHRASE,
                    message=(
                        f"Prohibited phrase {phrase!r} appeared in output "
                        f"(forum={self.forum_profile.forum.value})."
                    ),
                    field_path=offending_field,
                )

    def _check_universal_directives(
        self, lower_blob: str
    ) -> Iterable[ForumPolicyViolation]:
        for phrase in _UNIVERSAL_DIRECTIVE_PHRASES:
            if phrase in lower_blob:
                yield ForumPolicyViolation(
                    kind=ForumPolicyViolationKind.DIRECTIVE_ADVICE,
                    message=(
                        f"Directive-advice phrase {phrase!r} is never permitted "
                        "(legal information only)."
                    ),
                )

    def _check_required_disclaimers(
        self, lower_blob: str
    ) -> Iterable[ForumPolicyViolation]:
        for required in self.forum_profile.required_disclaimers:
            req_lower = required.lower()
            if req_lower in lower_blob:
                continue
            paraphrases = _DISCLAIMER_PARAPHRASES.get(required, [])
            if any(p in lower_blob for p in paraphrases):
                continue
            yield ForumPolicyViolation(
                kind=ForumPolicyViolationKind.MISSING_DISCLAIMER,
                message=(
                    f"Required disclaimer missing (verbatim or canonical paraphrase): {required!r}"
                ),
            )

    def _check_citations(
        self, output: Dict[str, Any]
    ) -> Iterable[ForumPolicyViolation]:
        cases = output.get("supporting_cases")
        if not isinstance(cases, list):
            return
        allowed_citation_kinds = {ck.value for ck in self.forum_profile.citation_kinds}
        allowed_source_kinds = {sk.value for sk in self.forum_profile.source_kinds}
        for idx, case in enumerate(cases):
            if not isinstance(case, dict):
                continue
            ck = case.get("citation_kind")
            if ck and ck not in allowed_citation_kinds:
                yield ForumPolicyViolation(
                    kind=ForumPolicyViolationKind.CITATION_KIND_MISUSE,
                    message=(
                        f"supporting_cases[{idx}].citation_kind={ck!r} is "
                        f"not in forum allowlist {sorted(allowed_citation_kinds)}."
                    ),
                    field_path=f"supporting_cases[{idx}].citation_kind",
                )
            sk = case.get("source_kind")
            if sk and sk not in allowed_source_kinds:
                yield ForumPolicyViolation(
                    kind=ForumPolicyViolationKind.SOURCE_KIND_MISUSE,
                    message=(
                        f"supporting_cases[{idx}].source_kind={sk!r} is "
                        f"not in forum allowlist {sorted(allowed_source_kinds)}."
                    ),
                    field_path=f"supporting_cases[{idx}].source_kind",
                )

    def _check_calculator_trace_for_statutory_limits(
        self, lower_blob: str, output: Dict[str, Any]
    ) -> Iterable[ForumPolicyViolation]:
        if not any(trigger in lower_blob for trigger in self._STATUTORY_LIMIT_TRIGGERS):
            return
        if output.get("calculator_trace"):
            return
        # Also accept a calculator-trace citation kind among supporting cases.
        cases = output.get("supporting_cases")
        if isinstance(cases, list):
            for case in cases:
                if (
                    isinstance(case, dict)
                    and case.get("citation_kind") == "deterministic_calculator_trace"
                ):
                    return
        yield ForumPolicyViolation(
            kind=ForumPolicyViolationKind.CALCULATOR_TRACE_REQUIRED,
            message=(
                "Output references a statutory limit / formulaic figure but "
                "provides no calculator_trace and no deterministic_calculator_trace "
                "citation. Calculator trace is required for these claims."
            ),
        )

    def _quarantine(
        self,
        output: Dict[str, Any],
        violations: List[ForumPolicyViolation],
    ) -> Dict[str, Any]:
        quarantined = dict(output)
        quarantined["outcome"] = "uncertain"
        quarantined["raw_confidence"] = 0.0
        quarantined["predicted_amount"] = None
        quarantined["reasoning"] = (
            "This issue could not be presented because the forum-policy "
            "verifier flagged one or more violations. See "
            "forum_policy_warnings for details."
        )
        quarantined["supporting_cases"] = []
        # Make sure the warnings array is present even after quarantine.
        existing = list(quarantined.get("forum_policy_warnings") or [])
        warning_strings = [v.message for v in violations]
        quarantined["forum_policy_warnings"] = existing + [
            w for w in warning_strings if w not in existing
        ]
        return quarantined


# ---------------------------------------------------------------------------
# Convenience helper
# ---------------------------------------------------------------------------


def verify_output(
    output: Dict[str, Any],
    forum_profile: ForumProfile,
    mode: PredictionMode = PredictionMode.HYBRID,
    *,
    extra_prohibited_phrases: Optional[Iterable[str]] = None,
) -> ForumPolicyResult:
    """One-shot helper that constructs the verifier and runs ``verify``."""
    return ForumPolicyVerifier(
        forum_profile,
        mode,
        extra_prohibited_phrases=extra_prohibited_phrases,
    ).verify(output)


def verify_output_with_pack(
    output: Dict[str, Any],
    forum_profile: ForumProfile,
    pack: Any,
    mode: PredictionMode = PredictionMode.HYBRID,
) -> ForumPolicyResult:
    """Run the verifier with the prohibited list augmented from ``pack``.

    Use this from runtime call-sites that already have a prompt pack handle —
    it pulls ``pack.extra_prohibited_phrases`` automatically.
    """
    extra = getattr(pack, "extra_prohibited_phrases", ()) or ()
    return ForumPolicyVerifier(
        forum_profile,
        mode,
        extra_prohibited_phrases=extra,
    ).verify(output)
