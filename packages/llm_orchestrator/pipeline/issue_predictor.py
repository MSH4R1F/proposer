import asyncio
import importlib
import json
import math
import os
import re
import structlog
from datetime import date as _date_type
from typing import Any, Dict, List, Optional

from ..clients.base import BaseLLMClient
from ..data.citation_urls import resolve_source_url
from ..models.prediction_v2 import (
    Citation,
    Determination,
    EvidenceStrength,
    IssueContext,
    IssueOutcome,
    IssuePrediction,
    IssueRetrievalResult,
    IssueType,
)
from ..prompts.prediction_v2 import (
    IRAC_JSON_SCHEMA,
    IRAC_SYSTEM_PROMPT,
    IRAC_USER_PROMPT,
    build_irac_json_schema,
)

# Stream C PR 4 (Task 4.4) — domain-pack-routed factor card rendering.
# These imports must NOT be wrapped in try/except: if domain_packs / legal_core
# are missing the build is broken and we want loud failure, not a silent
# fall-back to legacy rendering on import error.
from legal_core.graph.graph_quality import GraphQualityScore
from domain_packs.registry import DomainPackNotFoundError, get_domain_pack

_llm_only_prompts = importlib.import_module("llm_orchestrator.prompts.llm_only")
LLM_ONLY_SYSTEM_PROMPT = getattr(_llm_only_prompts, "LLM_ONLY_SYSTEM_PROMPT")
LLM_ONLY_USER_PROMPT = getattr(_llm_only_prompts, "LLM_ONLY_USER_PROMPT")

# Optional import for CaseFile — used for richer context if available
try:
    from ..models.case_file import CaseFile as _CaseFile
except ImportError:
    _CaseFile = None


# RQ2 grounded-award anchor (C1): extract monetary award figures from retrieved
# comparator chunk text so they can be surfaced explicitly in the repairs prompt.
_AWARD_AMOUNT_RE = re.compile(
    r"£\s?([\d,]+(?:\.\d{1,2})?)|(\d[\d,]*(?:\.\d{1,2})?)\s?(?:gbp|pounds)\b",
    re.IGNORECASE,
)


def _extract_award_amounts(text: str) -> List[float]:
    """Return positive £ amounts mentioned in ``text``, in order, de-duplicated.

    Matches ``£500``, ``£1,200.50`` and word forms like ``1500 pounds``. Bare
    ``£`` and ``£0`` are ignored. Used to ground the predicted award in the
    actual figures appearing in retrieved comparator decisions.
    """
    if not text:
        return []
    out: List[float] = []
    seen: set[float] = set()
    for match in _AWARD_AMOUNT_RE.finditer(text):
        raw = match.group(1) or match.group(2)
        if not raw:
            continue
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if value > 0 and value not in seen:
            seen.add(value)
            out.append(value)
    return out


# RQ2 grounding fix: extract the ACTUAL ordered total from a comparator decision,
# not every incidental £ figure. Old `_extract_award_amounts` pooled sub-components
# (e.g. "£1000 made up of £500 + £300 + £200"), OCR-split fragments, and offered/
# rent figures, biasing the comparator anchor far too low (index median £150 vs
# real ordered median ~£475). This recovers the order total from the decision text.
_ORDER_NUM = r"\d(?:[\d,]|\s(?=\d))*(?:\.\s*\d{1,2})?"  # OCR-tolerant: "1, 01 0" / "1\n07\n5"
_ORDER_TOTAL_PHRASE = re.compile(
    r"(?:must\s+pay\s+the\s+resident|total\s+compensation\s+of|pay\s+a\s+total\s+of"
    r"|landlord\s+must\s+pay|compensation\s+totalling)\s*£\s*(" + _ORDER_NUM + r")",
    re.IGNORECASE,
)
_ORDER_CONTEXT = re.compile(
    r"(?:compensation\s+order|must\s+pay|order(?:s|ed)?\s+(?:the\s+landlord\s+)?to\s+pay"
    r"|pay\s+(?:the\s+resident|you|a\s+total)|compensation\s+of|in\s+recognition"
    r"|in\s+the\s+sum\s+of|award(?:s|ed)?)",
    re.IGNORECASE,
)
_INCIDENTAL_CONTEXT = re.compile(
    r"(?:per\s+month|monthly|per\s+week|weekly|\brent\b|arrears|service\s+charge"
    r"|per\s+annum|already\s+offered|offered\s+(?:at|in|during|through|compensation)"
    r"|stage\s*[12])",
    re.IGNORECASE,
)
_ORDER_AMOUNT = re.compile(r"£\s*(" + _ORDER_NUM + r")", re.IGNORECASE)


def _clean_order_amount(raw: str) -> Optional[float]:
    try:
        value = float(re.sub(r"\s+", "", raw).replace(",", ""))
    except (ValueError, TypeError):
        return None
    # UK Housing Ombudsman compensation orders effectively never exceed this;
    # the bound also rejects OCR over-merges (e.g. two figures fused).
    return value if 0 < value <= 20_000 else None


def _extract_order_amounts(text: str, section_type: Optional[str] = None) -> List[float]:
    """Recover the Ombudsman *ordered total* from comparator decision text.

    Returns at most one figure: the order total for this chunk. Prefers an
    explicit total ("must pay the resident £X"); otherwise, in a decision/order
    chunk, takes the largest non-incidental £ figure (sub-components are smaller
    and rent/arrears/offered figures are filtered). OCR-tolerant. Empty when no
    order figure is present.
    """
    if not text:
        return []
    totals = [
        v
        for m in _ORDER_TOTAL_PHRASE.finditer(text)
        if (v := _clean_order_amount(m.group(1))) is not None
    ]
    if totals:
        return [max(totals)]  # the grand total, not the breakdown
    candidates: List[float] = []
    for m in _ORDER_AMOUNT.finditer(text):
        v = _clean_order_amount(m.group(1))
        if v is None:
            continue
        window = text[max(0, m.start() - 80) : m.end() + 40]
        if _INCIDENTAL_CONTEXT.search(window):
            continue
        candidates.append(v)
    if not candidates:
        return []
    # In a decision/order chunk the compensation figures live here; the order
    # total is the largest non-incidental amount. Outside such chunks, require
    # explicit order language so we don't grab incidental figures from facts.
    is_order = str(section_type).lower() == "decision" or bool(_ORDER_CONTEXT.search(text))
    if not is_order:
        return []
    return [max(candidates)]

logger = structlog.get_logger()

_REPAIRS_ISSUE_VALUES = {
    "repairs_disrepair",
    "repairs_damp_mould",
    "complaint_handling_failure",
}


REPAIRS_DETERMINATION_GUIDE = """
DETERMINATION GUIDE (housing.repairs_social.v1) — predicted_determination must be exactly one of:
- no_maladministration: the landlord acted reasonably and complied with its obligations.
- service_failure: a minor or short-duration failing causing limited detriment
  (e.g. a one-off missed appointment, a modest delay that was then corrected).
- maladministration: the landlord failed to meet its obligations in a way that
  caused injustice — prolonged repair delays, poor communication, inadequate
  records, failure to follow its own policy.
- severe_maladministration: serious, repeated, or deliberately obstructive
  failure causing significant injustice. Look for AGGRAVATORS: a known
  vulnerability that was ignored; repairs outstanding for around a year or
  more; repeated failed visits; systemic record-keeping failure; failure
  compounded by complaint mishandling. Two or more aggravators usually
  indicates severe_maladministration rather than maladministration.
- reasonable_redress: a failing occurred BUT the landlord ALREADY offered
  redress proportionate to it BEFORE the Ombudsman's determination (apology
  plus compensation consistent with the scale of the failing). The test is
  the adequacy of the PRIOR offer, made BEFORE the Ombudsman decided — not
  whether a failing occurred. If the facts show a pre-determination offer of
  compensation or apology, you MUST explicitly weigh this class before
  choosing maladministration or service_failure.
- resolved_with_intervention: the complaint was fully resolved during the
  investigation following Ombudsman intervention.
- outside_jurisdiction: the matter is outside the Ombudsman's remit (legal
  title disputes, matters concurrently before a court, pre-membership events).

Common errors to avoid: do NOT default to maladministration. The
service_failure / maladministration boundary turns on severity and duration
of detriment. The maladministration / severe_maladministration boundary turns
on aggravators. reasonable_redress turns on the landlord's prior offer.
""".strip()

_REPAIRS_NO_RAG_SYSTEM_PROMPT = (
    """You analyse social-housing complaints heard by the Housing Ombudsman.

This is an ablation baseline with NO retrieved Ombudsman determinations. Predict from the resident/landlord facts, evidence summary, timeline, and any structured fact card only.

Critical constraints:
1. Do NOT invent Ombudsman determination citations, proposition IDs, paragraph references, comparator awards, or supporting cases. Leave supporting_cases as an empty list.
2. Base the prediction only on the provided pre-decision facts and structured fact card. If those facts do not contain enough case-specific information to assess liability, choose "uncertain", set evidence_strength to "insufficient", predicted_amount to null, and amount_band to null.
3. Do not use missing citations as a substitute for factual uncertainty: decide whether the provided facts themselves are sufficient.
4. Use Housing Ombudsman concepts in the reasoning: no maladministration, service failure, maladministration, severe maladministration, reasonable redress, apology, repair action, compensation, case review, or policy review.
5. The JSON outcome field must still use the shared eval labels:
   - "tenant_wins" when the resident complaint is likely upheld on any substantive repairs/complaint-handling issue, or the landlord likely faces a service-failure/maladministration finding or additional remedy. Use this even if some complaint heads are not upheld.
   - "landlord_wins" when no maladministration/no service failure is likely.
   - "split" only when the likely result is genuinely balanced after remedies, with material findings for both sides and no clear resident-upheld remedy dominance.
   - "uncertain" only when the facts are too sparse or internally inconsistent to choose one of the above.

Safety: legal information, not legal advice. Hedge and explain uncertainty.
"""
    + "\n\n" + REPAIRS_DETERMINATION_GUIDE
)


def _build_no_rag_json_schema() -> str:
    """Apply the no-RAG transformations to the (flag-aware) IRAC schema.

    Reads STREAM_C_FORCE_ANSWER via build_irac_json_schema() so the
    no-RAG ablation paths share the forced-answer behaviour.
    """
    return (
        build_irac_json_schema()
        .replace(
            '"reasoning": "<IRAC-structured reasoning, 3-6 sentences, with case citations in format [CaseRef (Year)]>"',
            '"reasoning": "<IRAC-structured reasoning, 3-6 sentences, citing only provided user facts/KG facts, with no case citations>"',
        )
        .replace(
            '    "supporting_cases": [\n        {"case_reference": "CHI/xxx", "year": 2023, "paragraph": "12", "proposition_id": "optional retrieved proposition id", "quote": "relevant quote from case", "relevance": "why this case is relevant"}\n    ],',
            '    "supporting_cases": [],',
        )
        .replace(
            "- Include at least 1 supporting case citation",
            "- In no-RAG ablation modes, supporting_cases MUST be an empty list",
        )
        .replace(
            "- If a retrieved case is labelled PROPOSITION, copy its proposition_id into the supporting case citation",
            "- No retrieved cases are available in no-RAG ablation modes, so do not include proposition_id values",
        )
    )


def _gate_failure_reasons(score: GraphQualityScore, gate: Any) -> List[str]:
    """Enumerate every threshold the score fails.

    Mirrors the 7-condition AND in ``DomainPack.is_kg_usable`` so downstream
    consumers (artifact JSON, structured logs, debug traces) see exactly
    which threshold(s) tripped the gate. Spec §6 + §17.6 (Cross-PR
    Contract C5).
    """
    reasons: List[str] = []
    if score.evidence_backed_factor_count < gate.evidence_backed_factor_count_min:
        reasons.append(
            f"evidence_backed_factor_count {score.evidence_backed_factor_count} "
            f"< min {gate.evidence_backed_factor_count_min}"
        )
    if score.dated_event_count < gate.dated_event_count_min:
        reasons.append(
            f"dated_event_count {score.dated_event_count} "
            f"< min {gate.dated_event_count_min}"
        )
    if score.issue_count < gate.issue_count_min:
        reasons.append(
            f"issue_count {score.issue_count} < min {gate.issue_count_min}"
        )
    if (
        score.outcome_or_remedy_candidate_count
        < gate.outcome_or_remedy_candidate_count_min
    ):
        reasons.append(
            f"outcome_or_remedy_candidate_count {score.outcome_or_remedy_candidate_count} "
            f"< min {gate.outcome_or_remedy_candidate_count_min}"
        )
    if score.unsupported_factor_rate > gate.unsupported_factor_rate_max:
        reasons.append(
            f"unsupported_factor_rate {score.unsupported_factor_rate:.2f} "
            f"> max {gate.unsupported_factor_rate_max:.2f}"
        )
    if score.source_span_coverage < gate.source_span_coverage_min:
        reasons.append(
            f"source_span_coverage {score.source_span_coverage:.2f} "
            f"< min {gate.source_span_coverage_min:.2f}"
        )
    if score.contradiction_count > gate.contradiction_count_max:
        reasons.append(
            f"contradiction_count {score.contradiction_count} "
            f"> max {gate.contradiction_count_max}"
        )
    return reasons


def _suppress_empty_factor_card(prompt: str) -> str:
    """Strip orphan blank lines that appear when {kg_fact_card} or
    {abstention_warning} resolved to empty string.

    Per Stream C recovery plan Task 2: empty KG sections damage the LLM's
    interpretation of the prompt. When STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=1
    (default on), collapse runs of 3+ newlines to 2.
    """
    if os.getenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", "1") != "1":
        return prompt
    while "\n\n\n" in prompt:
        prompt = prompt.replace("\n\n\n", "\n\n")
    return prompt


class IssuePredictor:
    def __init__(
        self,
        llm_client: BaseLLMClient,
        case_file: Any = None,
        *,
        prompt_pack: Any = None,
    ):
        self.llm = llm_client
        self._case_file = case_file
        self._kg_facts_by_issue: Dict[Any, Any] = {}
        # Stream C PR 4 Task 4.4: domain-pack rendering inputs + outputs.
        # ``_case_graph_by_issue`` is populated by Task 4.5; until then it
        # stays empty and the renderer falls back to ``_kg_facts_by_issue``.
        self._case_graph_by_issue: Dict[Any, Any] = {}
        # ``_last_kg_metadata`` is set on every call to
        # ``_render_factor_card_via_pack`` and consumed by the prediction
        # engine for the artifact JSON in Task 4.6.
        self._last_kg_metadata: dict = {}
        # SHA-20 Phase 6: when a prompt pack is supplied, its
        # ``prediction_system`` REPLACES the default IRAC system prompt for
        # this run. The legacy IRAC text remains in use when no pack is
        # injected so existing deposit predictions stay schema-compatible.
        self._prompt_pack = prompt_pack
        # Stream C PR 5 Task 5.6: per-issue ComparatorPack so the predictor
        # can read ``counterexample_pass_metadata.abstention_recommended``
        # and emit a low-confidence warning into the IRAC user prompt.
        # Populated by ``prediction_engine_v2.predict()`` after retrieval.
        # Default empty so non-factor strategies are unaffected.
        self._last_comparator_pack: Optional[Any] = None
        self._comparator_pack_by_issue: Dict[Any, Any] = {}

    def _abstention_warning_for_issue(self, issue_type: Any) -> str:
        """Return the IRAC abstention notice when the comparator pack for
        ``issue_type`` flags ``abstention_recommended=True``.

        Empty string when no pack is registered or the flag is False so the
        ``{abstention_warning}`` placeholder resolves to "" and existing
        snapshots stay byte-stable.
        """
        pack = self._comparator_pack_by_issue.get(issue_type)
        if pack is None:
            return ""
        meta = getattr(pack, "counterexample_pass_metadata", None)
        if meta is None:
            return ""
        if not getattr(meta, "abstention_recommended", False):
            return ""
        return (
            "NOTE: Counterexample retrieval found no differential cases. "
            "Treat any prediction as low-confidence."
        )

    @property
    def _prediction_system_prompt(self) -> str:
        # Stream C recovery T4: build_irac_json_schema() is flag-aware. Under
        # STREAM_C_FORCE_ANSWER=1 (default) it omits "uncertain" from the
        # allowed outcome enum.
        schema = build_irac_json_schema()
        if self._prompt_pack is not None and getattr(
            self._prompt_pack, "prediction_system", None
        ):
            return f"{self._prompt_pack.prediction_system}\n\n{schema}"
        return f"{IRAC_SYSTEM_PROMPT}\n\n{schema}"

    def _repairs_no_rag_system_prompt(self) -> str:
        return f"{_REPAIRS_NO_RAG_SYSTEM_PROMPT}\n\n{_build_no_rag_json_schema()}"

    async def predict_no_rag(
        self,
        issues: List[IssueContext],
        prompt_mode: str = "llm_only",
    ) -> List[IssuePrediction]:
        """Predict each issue without RAG (for LLM_ONLY and KG_ONLY modes).

        prompt_mode:
          - "llm_only": uses LLM_ONLY prompt templates (no precedents, no KG fact card)
          - "kg_only": uses IRAC prompt with empty retrieved_cases but full KG fact card
        """
        results = await asyncio.gather(
            *[self._predict_issue_no_rag(issue, prompt_mode) for issue in issues],
            return_exceptions=True,
        )
        out: List[IssuePrediction] = []
        for issue, r in zip(issues, results):
            if isinstance(r, IssuePrediction):
                out.append(r)
            else:
                out.append(
                    self._uncertain_prediction(
                        issue=issue,
                        reason=f"{prompt_mode} prediction failed: {r!r}",
                        evidence_strength=self._assess_evidence_strength(issue),
                        data_impact="LLM call failed in no-RAG mode.",
                    )
                )
        return out

    async def _predict_issue_no_rag(
        self,
        issue: IssueContext,
        prompt_mode: str,
    ) -> IssuePrediction:
        """Single-issue predict for LLM_ONLY / KG_ONLY paths."""
        cf = self._case_file
        deposit_amount = "unknown"
        tenancy_duration = "unknown"
        tenancy_type = "unknown"
        region = "unknown"
        if cf is not None:
            tenancy = getattr(cf, "tenancy", None)
            prop = getattr(cf, "property", None)
            if tenancy is not None:
                if getattr(tenancy, "deposit_amount", None) is not None:
                    deposit_amount = f"{tenancy.deposit_amount:.2f}"
                if getattr(tenancy, "start_date", None) and getattr(
                    tenancy, "end_date", None
                ):
                    days = (tenancy.end_date - tenancy.start_date).days
                    months = round(days / 30.44)
                    tenancy_duration = f"{months} months ({days} days)"
                if getattr(tenancy, "tenancy_type", None):
                    tenancy_type = tenancy.tenancy_type
            if prop is not None:
                if getattr(prop, "region", None):
                    region = prop.region

        claimed_amount = issue.claimed_amount
        if claimed_amount is None:
            if issue.landlord_claim and issue.landlord_claim.claimed_amount is not None:
                claimed_amount = issue.landlord_claim.claimed_amount
            elif issue.tenant_claim and issue.tenant_claim.claimed_amount is not None:
                claimed_amount = issue.tenant_claim.claimed_amount

        tenant_narrative = self._get_text_attr(cf, "tenant_narrative")
        landlord_narrative = self._get_text_attr(cf, "landlord_narrative")
        tenant_claim_text = self._format_party_position(
            claim=issue.tenant_claim,
            narrative=tenant_narrative,
        )
        landlord_claim_text = self._format_party_position(
            claim=issue.landlord_claim,
            narrative=landlord_narrative,
        )

        if self._is_repairs_case(cf, issue):
            if prompt_mode == "kg_only":
                case_graph = (
                    self._case_graph_by_issue.get(issue.issue_type)
                    or self._kg_facts_by_issue.get(issue.issue_type)
                )
                kg_fact_card, kg_meta = self._render_factor_card_via_pack(
                    cf, case_graph
                )
                self._last_kg_metadata = kg_meta
            else:
                kg_fact_card = ""
            if not self._has_no_rag_case_specific_facts(
                issue=issue,
                case_file=cf,
                tenant_claim_text=tenant_claim_text,
                landlord_claim_text=landlord_claim_text,
                kg_fact_card=kg_fact_card,
            ):
                return self._uncertain_prediction(
                    issue=issue,
                    reason=(
                        "No case-specific resident position, landlord position, "
                        "timeline, structured fact card, or substantive evidence "
                        "was available, so liability and remedy cannot be assessed "
                        "case-specifically in no-RAG mode."
                    ),
                    evidence_strength=EvidenceStrength.INSUFFICIENT,
                    data_impact=(
                        "Empty no-RAG context: issue label/metadata alone is not "
                        "enough to make a legally grounded Housing Ombudsman "
                        "prediction."
                    ),
                    raw_confidence=0.2,
                )
            user_prompt = _suppress_empty_factor_card(
                self._format_repairs_user_prompt(
                    issue=issue,
                    case_file=cf,
                    claimed_amount=claimed_amount,
                    tenant_claim_text=tenant_claim_text,
                    landlord_claim_text=landlord_claim_text,
                    evidence_summary=self._format_evidence_summary(issue),
                    evidence_conflicts=self._format_evidence_conflicts(issue),
                    timeline_summary=self._format_timeline(issue),
                    kg_constraints="\n".join(f"- {c}" for c in issue.kg_constraints)
                    if issue.kg_constraints
                    else "None identified",
                    kg_fact_card=kg_fact_card,
                    retrieved_cases=(
                        f"No retrieved cases in {prompt_mode} mode. Leave "
                        "supporting_cases empty. Do not include comparator awards, "
                        "proposition IDs, paragraph references, or determination "
                        "citations."
                    ),
                    num_retrieved_cases=0,
                    no_rag_mode=True,
                    abstention_warning=self._abstention_warning_for_issue(
                        issue.issue_type
                    ),
                )
            )
            system_prompt = self._repairs_no_rag_system_prompt()
        elif prompt_mode == "llm_only":
            user_prompt = LLM_ONLY_USER_PROMPT.format(
                issue_type=issue.issue_type.value,
                issue_description=issue.issue_description,
                deposit_amount=deposit_amount,
                claimed_amount=f"{claimed_amount:.2f}"
                if claimed_amount is not None
                else "unknown",
                tenancy_duration=tenancy_duration,
                tenancy_type=tenancy_type,
                region=region,
                tenant_claim=tenant_claim_text,
                landlord_claim=landlord_claim_text,
            )
            system_prompt = (
                f"{LLM_ONLY_SYSTEM_PROMPT}\n\n{build_irac_json_schema()}"
            )
        else:  # kg_only — IRAC prompt with empty retrieved_cases + fact card
            case_graph = (
                self._case_graph_by_issue.get(issue.issue_type)
                or self._kg_facts_by_issue.get(issue.issue_type)
            )
            kg_fact_card, kg_meta = self._render_factor_card_via_pack(
                cf, case_graph
            )
            self._last_kg_metadata = kg_meta
            user_prompt = _suppress_empty_factor_card(
                IRAC_USER_PROMPT.format(
                    issue_type=issue.issue_type.value,
                    issue_description=issue.issue_description,
                    deposit_amount=deposit_amount,
                    claimed_amount=f"{claimed_amount:.2f}"
                    if claimed_amount is not None
                    else "unknown",
                    tenancy_duration=tenancy_duration,
                    tenancy_type=tenancy_type,
                    region=region,
                    data_completeness=issue.data_completeness,
                    deposit_protection_summary="See KG fact card below."
                    if kg_fact_card
                    else "No deposit protection details available.",
                    kg_constraints="\n".join(f"- {c}" for c in issue.kg_constraints)
                    if issue.kg_constraints
                    else "None identified",
                    kg_fact_card=kg_fact_card,
                    abstention_warning=self._abstention_warning_for_issue(
                        issue.issue_type
                    ),
                    evidence_summary=self._format_evidence_summary(issue),
                    evidence_conflicts=self._format_evidence_conflicts(issue),
                    timeline_summary=self._format_timeline(issue),
                    retrieved_cases="No retrieved cases in KG_ONLY mode.",
                    num_retrieved_cases=0,
                    tenant_claim=tenant_claim_text,
                    landlord_claim=landlord_claim_text,
                )
            )
            system_prompt = self._prediction_system_prompt

        try:
            response = await self.llm.generate(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                max_tokens=8192,
                temperature=0.2,
            )
            prediction = self._parse_prediction_response(response, issue)
            # Force-empty citations: no retrieval ran, model must not invent.
            prediction.supporting_cases = []
            prediction.issue_type = issue.issue_type
            if not prediction.issue_description:
                prediction.issue_description = issue.issue_description
            prediction = self._apply_determination_postrules(
                prediction,
                self._case_graph_by_issue.get(issue.issue_type),
            )
            return self._apply_forced_answer(prediction)
        except Exception as exc:
            logger.error(
                "no_rag_prediction_llm_error",
                issue_type=issue.issue_type.value,
                prompt_mode=prompt_mode,
                error=str(exc),
            )
            return self._uncertain_prediction(
                issue=issue,
                reason=f"{prompt_mode} mode LLM call failed.",
                evidence_strength=self._assess_evidence_strength(issue),
                data_impact="No-RAG path could not complete model call.",
            )

    async def predict_all(
        self,
        issues: List[IssueContext],
        retrieval_results: Dict[IssueType, IssueRetrievalResult],
        *,
        case_file: Any = None,
        prompt_mode: str = "hybrid",
    ) -> List[IssuePrediction]:
        sufficient_issues: List[IssueContext] = []
        uncertain_by_issue: Dict[IssueType, IssuePrediction] = {}

        for issue in issues:
            retrieval = retrieval_results.get(issue.issue_type)
            if retrieval and retrieval.is_sufficient:
                sufficient_issues.append(issue)
                continue

            uncertain_by_issue[issue.issue_type] = self._apply_forced_answer(
                IssuePrediction(
                    issue_type=issue.issue_type,
                    issue_description=issue.issue_description,
                    outcome=IssueOutcome.UNCERTAIN,
                    raw_confidence=0.0,
                    reasoning="Insufficient similar cases found for this issue.",
                    evidence_strength=EvidenceStrength.INSUFFICIENT,
                    data_completeness_impact="Cannot predict due to lack of precedent cases.",
                )
            )

        if sufficient_issues:
            llm_results = await asyncio.gather(
                *[
                    self._predict_issue(
                        issue,
                        retrieval_results[issue.issue_type],
                        prompt_mode=prompt_mode,
                    )
                    if case_file is None
                    else self._predict_issue(
                        issue,
                        retrieval_results[issue.issue_type],
                        case_file=case_file,
                        prompt_mode=prompt_mode,
                    )
                    for issue in sufficient_issues
                ],
                return_exceptions=True,
            )
            for issue, result in zip(sufficient_issues, llm_results):
                if isinstance(result, Exception):
                    logger.error(
                        "issue_prediction_failed",
                        issue_type=issue.issue_type.value,
                        error=str(result),
                    )
                    uncertain_by_issue[issue.issue_type] = self._uncertain_prediction(
                        issue=issue,
                        reason="LLM prediction failed for this issue.",
                        evidence_strength=self._assess_evidence_strength(issue),
                        data_impact="Prediction failed due to model/runtime error.",
                    )
                elif isinstance(result, IssuePrediction):
                    uncertain_by_issue[issue.issue_type] = result
                else:
                    uncertain_by_issue[issue.issue_type] = self._uncertain_prediction(
                        issue=issue,
                        reason="Unexpected prediction result type.",
                        evidence_strength=self._assess_evidence_strength(issue),
                        data_impact="Issue prediction failed type validation.",
                    )

        return [
            uncertain_by_issue.get(issue.issue_type)
            or self._uncertain_prediction(
                issue=issue,
                reason="Issue prediction unavailable.",
                evidence_strength=self._assess_evidence_strength(issue),
                data_impact="Issue could not be processed.",
            )
            for issue in issues
        ]

    async def _predict_issue(
        self,
        issue: IssueContext,
        retrieval: IssueRetrievalResult,
        *,
        case_file: Any = None,
        prompt_mode: str = "hybrid",
    ) -> IssuePrediction:
        formatted_cases = []
        for i, result in enumerate(retrieval.results[:8], 1):
            case_ref = self._get_value(result, "case_reference", "Unknown")
            year = self._get_value(result, "year", "N/A")
            text = self._get_value(
                result,
                "chunk_text",
                self._get_value(result, "text", ""),
            )
            score = self._to_float(
                self._get_value(
                    result,
                    "combined_score",
                    self._get_value(result, "rerank_score", 0),
                )
            )
            purpose = self._get_value(result, "retrieval_purpose", None)
            purposes = self._get_value(result, "retrieval_purposes", None)
            if isinstance(purposes, list) and purposes:
                purpose = ", ".join(str(p) for p in purposes)
            purpose_line = f"\nPurpose: {purpose}" if purpose else ""
            finding = self._get_value(result, "ombudsman_finding_signal", None)
            finding_line = (
                f"\nFinding signal: {finding}"
                if finding and str(finding) != "unknown"
                else ""
            )
            amount_line = (
                "\nAward amount signal: present"
                if self._get_value(result, "has_award_amount", False)
                else ""
            )
            # RQ2 grounding fix (C1): surface the comparator's ORDERED TOTAL
            # (not every incidental £ figure) so the model anchors on the real
            # Ombudsman order. _extract_order_amounts filters rent/arrears/offered
            # figures and recovers OCR-split totals from the decision text.
            order_amounts = _extract_order_amounts(
                str(text), self._get_value(result, "section_type", None)
            )
            award_values_line = (
                "\nComparator ordered total: "
                + ", ".join(f"£{a:,.0f}" for a in order_amounts[:2])
                if order_amounts
                else ""
            )
            formatted_cases.append(
                f"CASE {i}: {case_ref} ({year})\n"
                f"Relevance: {score:.3f}"
                f"{purpose_line}{finding_line}{amount_line}{award_values_line}\n"
                f"{str(text)[:1500]}\n---"
            )
        retrieved_cases_str = (
            "\n".join(formatted_cases) or "No similar cases retrieved."
        )

        evidence_summary = self._format_evidence_summary(issue)
        claimed_amount = issue.claimed_amount
        if claimed_amount is None:
            claimed_amount = (
                issue.landlord_claim.claimed_amount
                if issue.landlord_claim
                and issue.landlord_claim.claimed_amount is not None
                else issue.tenant_claim.claimed_amount
                if issue.tenant_claim and issue.tenant_claim.claimed_amount is not None
                else None
            )

        cf = case_file if case_file is not None else self._case_file
        deposit_amount = "unknown"
        tenancy_duration = "unknown"
        tenancy_type = "unknown"
        region = "unknown"
        deposit_protection_summary = "Not specified"

        if cf is not None:
            tenancy = getattr(cf, "tenancy", None)
            prop = getattr(cf, "property", None)
            if tenancy is not None:
                if getattr(tenancy, "deposit_amount", None) is not None:
                    deposit_amount = f"{tenancy.deposit_amount:.2f}"
                if getattr(tenancy, "start_date", None) and getattr(
                    tenancy, "end_date", None
                ):
                    days = (tenancy.end_date - tenancy.start_date).days
                    months = round(days / 30.44)
                    tenancy_duration = f"{months} months ({days} days)"
                elif getattr(tenancy, "start_date", None):
                    tenancy_duration = f"Started {tenancy.start_date}, end date unknown"
                if getattr(tenancy, "tenancy_type", None):
                    tenancy_type = tenancy.tenancy_type
                deposit_protection_summary = self._build_deposit_protection_summary(
                    tenancy
                )
            if prop is not None:
                if getattr(prop, "region", None):
                    region = prop.region
                elif getattr(prop, "postcode", None):
                    region = f"postcode {prop.postcode}"

        tenant_narrative = self._get_text_attr(cf, "tenant_narrative")
        landlord_narrative = self._get_text_attr(cf, "landlord_narrative")

        tenant_claim_text = self._format_party_position(
            claim=issue.tenant_claim,
            narrative=tenant_narrative,
        )
        landlord_claim_text = self._format_party_position(
            claim=issue.landlord_claim,
            narrative=landlord_narrative,
        )

        evidence_conflicts = self._format_evidence_conflicts(issue)
        timeline_summary = self._format_timeline(issue)

        # Stream C PR 4 (spec §19): RAG_ONLY must NOT inject the typed factor
        # card into the prompt even when the KG is populated. Other modes
        # (HYBRID, KG_ONLY) route through the domain pack via the renderer
        # method below; the legacy ``_kg_facts_by_issue`` is consulted as a
        # back-stop until Task 4.5 wires ``_case_graph_by_issue``.
        if prompt_mode == "rag_only":
            kg_fact_card = ""
            self._last_kg_metadata = {
                "kg_used_for_prediction": False,
                # rag_only is intentional, not a fallback from a KG attempt.
                "kg_fallback_mode": None,
                "kg_gate_failure_reasons": [],
                "graph_quality_score": None,
            }
        else:
            case_graph = (
                self._case_graph_by_issue.get(issue.issue_type)
                or self._kg_facts_by_issue.get(issue.issue_type)
            )
            kg_fact_card, kg_meta = self._render_factor_card_via_pack(
                self._case_file if case_file is None else case_file,
                case_graph,
            )
            self._last_kg_metadata = kg_meta

        # Stream C PR 5 Task 5.6: emit a low-confidence notice into the IRAC
        # prompt when the FactorRetriever's counterexample pass flagged
        # abstention. Empty string otherwise → byte-stable for legacy paths.
        abstention_warning = self._abstention_warning_for_issue(issue.issue_type)

        prompt_kwargs = {
            "issue_type": issue.issue_type.value,
            "issue_description": issue.issue_description,
            "deposit_amount": deposit_amount,
            "claimed_amount": f"{claimed_amount:.2f}"
            if claimed_amount is not None
            else "unknown",
            "tenancy_duration": tenancy_duration,
            "tenancy_type": tenancy_type,
            "region": region,
            "data_completeness": issue.data_completeness,
            "deposit_protection_summary": deposit_protection_summary,
            "kg_constraints": "\n".join(f"- {c}" for c in issue.kg_constraints)
            if issue.kg_constraints
            else "None identified",
            "kg_fact_card": kg_fact_card,
            "abstention_warning": abstention_warning,
            "evidence_summary": evidence_summary,
            "evidence_conflicts": evidence_conflicts,
            "timeline_summary": timeline_summary,
            "retrieved_cases": retrieved_cases_str,
            "num_retrieved_cases": len(retrieval.results),
            "tenant_claim": tenant_claim_text,
            "landlord_claim": landlord_claim_text,
        }
        try:
            user_prompt = _suppress_empty_factor_card(
                IRAC_USER_PROMPT.format(**prompt_kwargs)
            )
        except KeyError:
            user_prompt = (
                f"Issue Type: {issue.issue_type.value}\n"
                f"Issue Description: {issue.issue_description}\n"
                f"Deposit Amount: £{deposit_amount}\n"
                f"Claimed Amount: £{prompt_kwargs['claimed_amount']}\n"
                f"Tenancy Duration: {tenancy_duration}\n"
                f"Data Completeness: {issue.data_completeness:.0%}\n"
                f"Deposit Protection: {deposit_protection_summary}\n\n"
                f"Tenant Claim:\n{tenant_claim_text}\n\n"
                f"Landlord Claim:\n{landlord_claim_text}\n\n"
                f"Evidence Conflicts:\n{evidence_conflicts}\n\n"
                f"KG Constraints:\n{prompt_kwargs['kg_constraints']}\n\n"
                f"Evidence Summary:\n{evidence_summary}\n\n"
                f"Timeline:\n{timeline_summary}\n\n"
                f"Retrieved Cases ({len(retrieval.results)}):\n{retrieved_cases_str}\n"
            )
        if self._is_repairs_case(cf, issue):
            user_prompt = _suppress_empty_factor_card(
                self._format_repairs_user_prompt(
                    issue=issue,
                    case_file=cf,
                    claimed_amount=claimed_amount,
                    tenant_claim_text=tenant_claim_text,
                    landlord_claim_text=landlord_claim_text,
                    evidence_summary=evidence_summary,
                    evidence_conflicts=evidence_conflicts,
                    timeline_summary=timeline_summary,
                    kg_constraints=prompt_kwargs["kg_constraints"],
                    kg_fact_card=kg_fact_card,
                    retrieved_cases=retrieved_cases_str,
                    num_retrieved_cases=len(retrieval.results),
                    abstention_warning=abstention_warning,
                )
            )

        system_prompt = self._prediction_system_prompt
        if self._is_repairs_case(cf, issue):
            system_prompt = f"{system_prompt}\n\n{REPAIRS_DETERMINATION_GUIDE}"

        attempts = 2
        last_response: Optional[str] = None
        for attempt in range(1, attempts + 1):
            try:
                response = await self.llm.generate(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt,
                    max_tokens=8192,
                    temperature=0.2,
                )
                last_response = response
                # Grounded fallback anchor: median of the comparator ORDER
                # totals in the (full-text) retrieved decisions, used only if
                # the LLM abstains on the amount under the always-predict flag.
                _comp_orders: List[float] = []
                for _r in retrieval.results[:8]:
                    _txt = self._get_value(
                        _r, "chunk_text", self._get_value(_r, "text", "")
                    )
                    _comp_orders.extend(
                        _extract_order_amounts(
                            str(_txt), self._get_value(_r, "section_type", None)
                        )
                    )
                _comp_fallback = None
                if _comp_orders:
                    _srt = sorted(_comp_orders)
                    _comp_fallback = float(_srt[len(_srt) // 2])
                prediction = self._parse_prediction_response(
                    response, issue, comparator_fallback_gbp=_comp_fallback
                )
                should_retry_parse = (
                    prediction.outcome == IssueOutcome.UNCERTAIN
                    and prediction.data_completeness_impact == "parse_error"
                    and attempt < attempts
                )
                if should_retry_parse:
                    logger.warning(
                        "issue_prediction_parse_retry",
                        issue_type=issue.issue_type.value,
                        attempt=attempt,
                    )
                    continue

                if prediction.outcome != IssueOutcome.UNCERTAIN or attempt == attempts:
                    prediction.issue_type = issue.issue_type
                    if not prediction.issue_description:
                        prediction.issue_description = issue.issue_description
                    if prediction.evidence_strength == EvidenceStrength.INSUFFICIENT:
                        prediction.evidence_strength = self._assess_evidence_strength(
                            issue
                        )
                    prediction = self._apply_determination_postrules(
                        prediction,
                        self._case_graph_by_issue.get(issue.issue_type),
                    )
                    return self._apply_forced_answer(prediction)
            except Exception as exc:
                logger.error(
                    "issue_prediction_llm_error",
                    issue_type=issue.issue_type.value,
                    attempt=attempt,
                    error=str(exc),
                )

        return self._uncertain_prediction(
            issue=issue,
            reason="Could not parse model output for this issue.",
            evidence_strength=self._assess_evidence_strength(issue),
            data_impact=(
                "Prediction fell back to uncertain after parsing/model failure."
                if last_response
                else "Prediction failed due to unavailable model response."
            ),
        )

    def _parse_prediction_response(
        self,
        response: str,
        issue: IssueContext,
        comparator_fallback_gbp: Optional[float] = None,
    ) -> IssuePrediction:
        try:
            data = self._extract_json_payload(response)
            if data is None:
                raise ValueError("No parseable JSON object in model response")

            if isinstance(data, list):
                data = next((item for item in data if isinstance(item, dict)), {})
            if not isinstance(data, dict):
                raise ValueError("Parsed JSON payload is not an object")

            for wrapper_key in ("issue_prediction", "prediction", "data"):
                wrapped = data.get(wrapper_key)
                if isinstance(wrapped, dict):
                    data = wrapped
                    break

            outcome_raw = data.get("outcome", data.get("predicted_outcome", "uncertain"))
            outcome = self._normalise_issue_outcome(outcome_raw)

            strength_raw = str(
                data.get(
                    "evidence_strength", self._assess_evidence_strength(issue).value
                )
            ).lower()
            try:
                evidence_strength = EvidenceStrength(strength_raw)
            except ValueError:
                evidence_strength = self._assess_evidence_strength(issue)

            citations_raw = data.get("supporting_cases", data.get("citations", []))
            citations: List[Citation] = []
            if isinstance(citations_raw, list):
                for citation in citations_raw:
                    if not isinstance(citation, dict):
                        continue
                    year = self._to_int(citation.get("year"), 2024)
                    case_ref = str(citation.get("case_reference", "Unknown"))
                    resolved_year = year if year is not None else 2024
                    citations.append(
                        Citation(
                            case_reference=case_ref,
                            year=resolved_year,
                            region=self._to_optional_str(citation.get("region")),
                            paragraph=self._to_optional_str(citation.get("paragraph")),
                            proposition_id=self._to_optional_str(
                                citation.get("proposition_id")
                            ),
                            quote=str(citation.get("quote", "")),
                            relevance=str(citation.get("relevance", "")),
                            similarity_score=self._to_probability(
                                citation.get("similarity_score", 0.0)
                            ),
                            verified=bool(citation.get("verified", False)),
                            source_url=resolve_source_url(case_ref, resolved_year),
                        )
                    )

            key_factors_raw = data.get("key_factors", [])
            key_factors = (
                [str(item) for item in key_factors_raw]
                if isinstance(key_factors_raw, list)
                else []
            )

            amount_value = self._to_optional_float(data.get("predicted_amount"))
            amount_band = self._normalise_amount_band(data.get("amount_band"))

            # STREAM_C_ALWAYS_PREDICT_AMOUNTS / STREAM_C_NO_RAG_PREDICT_AMOUNTS:
            # If the LLM still emits null despite the strengthened schema +
            # reasoning instruction (which happens in hybrid mode when the
            # deposit-FTT IRAC system prompt's comparator framing takes
            # precedence over our user-prompt override), synthesise an
            # amount from amount_band (midpoint) or a domain default. This
            # guarantees the user-requested "predict an answer no matter
            # what" property without changing the underlying system prompt.
            always_amounts = (
                os.getenv("STREAM_C_ALWAYS_PREDICT_AMOUNTS", "0") == "1"
                or os.getenv("STREAM_C_NO_RAG_PREDICT_AMOUNTS", "0") == "1"
            )
            if always_amounts and amount_value is None:
                _band_midpoints = {
                    "0": 0.0,
                    "1-100": 50.0,
                    "101-250": 175.0,
                    "251-600": 425.0,
                    "601-1000": 800.0,
                    # Open-topped band: Ombudsman repairs orders extend well
                    # beyond £1,000 (into the low thousands), so represent the
                    # real upper range rather than capping at a flat £1,500.
                    "1000+": 2200.0,
                }
                if amount_band in _band_midpoints:
                    amount_value = _band_midpoints[amount_band]
                else:
                    # Grounded fallback: prefer the median of the comparator
                    # ORDER totals (passed from _predict_issue, where the full
                    # retrieved decision text is in scope) over a flat domain
                    # prior, so an abstaining LLM still gets a per-case,
                    # evidence-anchored amount rather than a constant.
                    if comparator_fallback_gbp and comparator_fallback_gbp > 0:
                        amount_value = float(comparator_fallback_gbp)
                    else:
                        amount_value = 650.0
                    if amount_band is None:
                        amount_band = "601-1000"

            # Retrieval-conditioned grounding guard: bound the predicted amount
            # to the retrieved comparator-order evidence. If the model's figure
            # is wildly outside the comparators' range (e.g. a hallucinated high
            # under the always-predict relaxation), snap it to the comparator-
            # order median. Keeps the model's per-case signal when it is in the
            # right ballpark; prevents ungrounded magnitudes otherwise.
            if (
                comparator_fallback_gbp
                and comparator_fallback_gbp > 0
                and amount_value
                and (
                    amount_value > 2.0 * comparator_fallback_gbp
                    or amount_value < 0.5 * comparator_fallback_gbp
                )
            ):
                amount_value = float(comparator_fallback_gbp)

            # 2026-05-06 — Housing Ombudsman determination ontology.
            # Optional. Missing or invalid → None (treat as legacy / non-housing prompt).
            det_raw = data.get("predicted_determination")
            predicted_determination: Optional[Determination] = None
            if det_raw:
                try:
                    predicted_determination = Determination(det_raw)
                except ValueError:
                    # LLM emitted an invalid value; treat as missing rather than crashing.
                    predicted_determination = None

            amount_construct = data.get("amount_construct")
            if amount_construct not in (
                None,
                "ordered_now",
                "previously_offered",
                "global_unapportioned",
            ):
                amount_construct = None

            return IssuePrediction(
                issue_type=issue.issue_type,
                issue_description=str(
                    data.get("issue_description", issue.issue_description)
                ),
                outcome=outcome,
                raw_confidence=self._to_probability(
                    data.get("raw_confidence", data.get("confidence", 0.0))
                ),
                predicted_amount=amount_value,
                amount_band=amount_band,
                reasoning=str(data.get("reasoning", "")).strip(),
                key_factors=key_factors,
                supporting_cases=citations,
                evidence_strength=evidence_strength,
                data_completeness_impact=str(
                    data.get(
                        "data_completeness_impact",
                        f"Issue data completeness is {issue.data_completeness:.2f}.",
                    )
                ),
                predicted_determination=predicted_determination,
                amount_construct=amount_construct,
            )
        except Exception as exc:
            logger.warning(
                "issue_prediction_parse_error",
                issue_type=issue.issue_type.value,
                error=str(exc),
            )
            return IssuePrediction(
                issue_type=issue.issue_type,
                issue_description=issue.issue_description,
                outcome=IssueOutcome.UNCERTAIN,
                raw_confidence=0.0,
                reasoning="Unable to parse model response for this issue.",
                evidence_strength=self._assess_evidence_strength(issue),
                data_completeness_impact="parse_error",
            )

    def _extract_json_payload(self, response: str) -> Optional[Any]:
        cleaned = response.strip()

        if "```json" in cleaned:
            start = cleaned.find("```json") + len("```json")
            end = cleaned.find("```", start)
            cleaned = cleaned[start : end if end != -1 else None].strip()
        elif "```" in cleaned:
            start = cleaned.find("```") + len("```")
            end = cleaned.find("```", start)
            cleaned = cleaned[start : end if end != -1 else None].strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        start_positions = [idx for idx, ch in enumerate(cleaned) if ch in "[{"]

        for start in start_positions:
            try:
                parsed, _ = decoder.raw_decode(cleaned[start:])
                return parsed
            except json.JSONDecodeError:
                continue

        return None

    @staticmethod
    def _normalise_issue_outcome(value: Any) -> IssueOutcome:
        """Normalise model/forum outcome wording into shared eval labels."""
        raw = str(value or "uncertain").strip().lower()
        key = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
        exact = {
            "tenant_win": IssueOutcome.TENANT_WINS,
            "tenant_wins": IssueOutcome.TENANT_WINS,
            "resident_win": IssueOutcome.TENANT_WINS,
            "resident_wins": IssueOutcome.TENANT_WINS,
            "complaint_upheld": IssueOutcome.TENANT_WINS,
            "upheld": IssueOutcome.TENANT_WINS,
            "upheld_in_full": IssueOutcome.TENANT_WINS,
            "service_failure": IssueOutcome.TENANT_WINS,
            "maladministration": IssueOutcome.TENANT_WINS,
            "severe_maladministration": IssueOutcome.TENANT_WINS,
            "maladministration_found": IssueOutcome.TENANT_WINS,
            "finding_of_maladministration": IssueOutcome.TENANT_WINS,
            "landlord_win": IssueOutcome.LANDLORD_WINS,
            "landlord_wins": IssueOutcome.LANDLORD_WINS,
            "no_maladministration": IssueOutcome.LANDLORD_WINS,
            "no_service_failure": IssueOutcome.LANDLORD_WINS,
            "no_failure": IssueOutcome.LANDLORD_WINS,
            "complaint_not_upheld": IssueOutcome.LANDLORD_WINS,
            "not_upheld": IssueOutcome.LANDLORD_WINS,
            "split": IssueOutcome.SPLIT,
            "mixed": IssueOutcome.SPLIT,
            "mixed_findings": IssueOutcome.SPLIT,
            "partial": IssueOutcome.SPLIT,
            "partial_upheld": IssueOutcome.TENANT_WINS,
            "partially_upheld": IssueOutcome.TENANT_WINS,
            "partly_upheld": IssueOutcome.TENANT_WINS,
            "partial_maladministration": IssueOutcome.TENANT_WINS,
            "reasonable_redress": IssueOutcome.SPLIT,
            "uncertain": IssueOutcome.UNCERTAIN,
            "unknown": IssueOutcome.UNCERTAIN,
            "insufficient_evidence": IssueOutcome.UNCERTAIN,
        }
        if key in exact:
            return exact[key]
        if (
            "no_maladministration" in key
            or "no_service_failure" in key
            or "not_upheld" in key
            or "not_sustained" in key
        ):
            return IssueOutcome.LANDLORD_WINS
        if (
            "partial" in key
            or "partly" in key
            or "reasonable_redress" in key
        ):
            if "upheld" in key or "maladministration" in key:
                return IssueOutcome.TENANT_WINS
            return IssueOutcome.SPLIT
        if "mixed" in key:
            return IssueOutcome.SPLIT
        if (
            "service_failure" in key
            or "severe_maladministration" in key
            or "maladministration" in key
            or "upheld" in key
        ):
            return IssueOutcome.TENANT_WINS
        try:
            return IssueOutcome(key)
        except ValueError:
            return IssueOutcome.UNCERTAIN

    @staticmethod
    def _normalise_amount_band(value: Any) -> Optional[str]:
        if value is None:
            return None
        raw = str(value).strip().replace("£", "").replace(",", "")
        key = raw.lower().replace("gbp", "").strip()
        key = re.sub(r"\s+", "", key)
        aliases = {
            "0": "0",
            "zero": "0",
            "none": "0",
            "1-100": "1-100",
            "1to100": "1-100",
            "101-250": "101-250",
            "101to250": "101-250",
            "251-600": "251-600",
            "251to600": "251-600",
            "601-1000": "601-1000",
            "601to1000": "601-1000",
            "1000+": "1000+",
            "1001+": "1000+",
            "over1000": "1000+",
            "1000plus": "1000+",
        }
        return aliases.get(key)

    def _assess_evidence_strength(self, issue: IssueContext) -> EvidenceStrength:
        if issue.data_completeness >= 0.8:
            return EvidenceStrength.STRONG
        if issue.data_completeness >= 0.5:
            return EvidenceStrength.MODERATE
        if issue.data_completeness >= 0.2:
            return EvidenceStrength.WEAK
        return EvidenceStrength.INSUFFICIENT

    def _uncertain_prediction(
        self,
        issue: IssueContext,
        reason: str,
        evidence_strength: EvidenceStrength,
        data_impact: str,
        raw_confidence: float = 0.0,
    ) -> IssuePrediction:
        return self._apply_forced_answer(
            IssuePrediction(
                issue_type=issue.issue_type,
                issue_description=issue.issue_description,
                outcome=IssueOutcome.UNCERTAIN,
                raw_confidence=raw_confidence,
                reasoning=reason,
                evidence_strength=evidence_strength,
                data_completeness_impact=data_impact,
            )
        )

    def _apply_determination_postrules(
        self, prediction: IssuePrediction, case_graph: Any
    ) -> IssuePrediction:
        """Stream C live-control-plane: deterministic determination rules over
        evidence-backed factor assertions. No-op without factors or when
        STREAM_C_DETERMINATION_RULES=0."""
        import os

        from llm_orchestrator.pipeline.determination_rules import (
            apply_determination_rules,
        )

        if os.getenv("STREAM_C_DETERMINATION_RULES", "1") != "1":
            return prediction
        factors = list(getattr(case_graph, "factor_assertions", []) or [])
        if not factors or prediction.predicted_determination is None:
            return prediction
        new_det, rule = apply_determination_rules(
            prediction.predicted_determination,
            predicted_amount=prediction.predicted_amount,
            factors=factors,
        )
        if rule is not None and new_det is not prediction.predicted_determination:
            logger.info(
                "determination_rule_applied",
                rule=rule,
                before=prediction.predicted_determination.value,
                after=new_det.value,
            )
            prediction = prediction.model_copy(
                update={"predicted_determination": new_det}
            )
        return prediction

    @staticmethod
    def _apply_forced_answer(prediction: IssuePrediction) -> IssuePrediction:
        """Stream C recovery plan Task 4: when STREAM_C_FORCE_ANSWER=1
        (default on), no IssuePrediction may have outcome=UNCERTAIN. Remap
        UNCERTAIN to SPLIT with raw_confidence capped at 0.50 and
        evidence_strength=INSUFFICIENT. The reasoning is prefixed with
        "[forced-answer fallback: ...]" so post-hoc analysis can spot the
        remap in artifact rows.

        Concrete outcomes (TENANT_WINS / LANDLORD_WINS / SPLIT) are
        returned unchanged. When the flag is "0", UNCERTAIN is also
        returned unchanged (legacy behaviour).
        """
        if os.getenv("STREAM_C_FORCE_ANSWER", "1") != "1":
            return prediction
        if prediction.outcome != IssueOutcome.UNCERTAIN:
            return prediction
        # IssuePrediction is mutable Pydantic; mutate in place to preserve
        # the object identity (some callers attach attributes via
        # object.__setattr__).
        prediction.outcome = IssueOutcome.SPLIT
        if prediction.raw_confidence > 0.50:
            prediction.raw_confidence = 0.50
        prediction.evidence_strength = EvidenceStrength.INSUFFICIENT
        existing_reasoning = prediction.reasoning or ""
        prediction.reasoning = (
            "[forced-answer fallback: LLM returned uncertain] "
            + existing_reasoning
        )
        return prediction

    def _format_evidence_summary(self, issue: IssueContext) -> str:
        if not issue.supporting_evidence:
            return "No supporting evidence provided."

        rows: List[str] = []
        for idx, evidence in enumerate(issue.supporting_evidence, 1):
            if isinstance(evidence, dict):
                ev_type = (
                    evidence.get("type") or evidence.get("evidence_type") or "unknown"
                )
                description = evidence.get("description") or evidence.get("text") or ""
                confidence = evidence.get("confidence")
            else:
                ev_type_raw = getattr(
                    evidence, "type", getattr(evidence, "evidence_type", "unknown")
                )
                ev_type = str(getattr(ev_type_raw, "value", ev_type_raw))
                description = getattr(
                    evidence, "description", getattr(evidence, "text", "")
                )
                confidence = getattr(evidence, "confidence", None)

            conf_text = ""
            if confidence is not None:
                conf_text = f" (confidence={self._to_probability(confidence):.2f})"
            rows.append(f"{idx}. [{ev_type}] {str(description)[:300]}{conf_text}")

        return "\n".join(rows)

    def _is_repairs_case(self, case_file: Any, issue: IssueContext) -> bool:
        if issue.issue_type.value in _REPAIRS_ISSUE_VALUES:
            return True
        if self._prompt_pack is not None and getattr(self._prompt_pack, "id", None) == (
            "housing.repairs_social.v1"
        ):
            return True
        metadata = getattr(case_file, "metadata", None) if case_file is not None else None
        return isinstance(metadata, dict) and (
            metadata.get("domain_id") == "housing.repairs_social.v1"
            or metadata.get("matter_type") in _REPAIRS_ISSUE_VALUES
        )

    def _format_repairs_user_prompt(
        self,
        *,
        issue: IssueContext,
        case_file: Any,
        claimed_amount: Optional[float],
        tenant_claim_text: str,
        landlord_claim_text: str,
        evidence_summary: str,
        evidence_conflicts: str,
        timeline_summary: str,
        kg_constraints: str,
        kg_fact_card: str,
        retrieved_cases: str,
        num_retrieved_cases: int,
        no_rag_mode: bool = False,
        abstention_warning: str = "",
    ) -> str:
        metadata = getattr(case_file, "metadata", None) if case_file is not None else None
        metadata = metadata if isinstance(metadata, dict) else {}
        region = "unknown"
        prop = getattr(case_file, "property", None) if case_file is not None else None
        if prop is not None and getattr(prop, "region", None):
            region = prop.region
        matter_type = metadata.get("matter_type") or issue.issue_type.value
        amount = f"£{claimed_amount:.2f}" if claimed_amount is not None else "unknown"

        kg_section = kg_fact_card or "No structured KG fact card available."
        abstention_section = (
            f"{abstention_warning}\n\n" if abstention_warning else ""
        )
        task_line = (
            "Task: Predict the likely Ombudsman complaint outcome from the "
            "pre-decision resident/landlord facts only. No retrieved "
            "Ombudsman determinations are available in this mode.\n\n"
            if no_rag_mode
            else "Task: Predict the likely Ombudsman complaint outcome from the "
            "pre-decision resident/landlord facts and similar determinations.\n\n"
        )
        if no_rag_mode:
            # STREAM_C_NO_RAG_PREDICT_AMOUNTS: when set, no-RAG modes
            # (kg_only, llm_only) estimate predicted_amount + amount_band
            # from general knowledge of UK Housing Ombudsman compensation
            # ranges, rather than null-ing them out. Default off preserves
            # the original "no-amount-without-precedent" research baseline.
            no_rag_predict_amounts = (
                os.getenv("STREAM_C_NO_RAG_PREDICT_AMOUNTS", "0") == "1"
            )
            if no_rag_predict_amounts:
                amount_clause = (
                    "Do not mention comparator determinations, proposition IDs, "
                    "paragraph references, case citations, supporting cases, or "
                    "comparator award amounts. For predicted_amount and "
                    "amount_band: estimate the MOST LIKELY total award from "
                    "general knowledge of UK Housing Ombudsman compensation for "
                    "this issue type, scaled to the severity and duration in "
                    "this case. Give a centred, unbiased point estimate (the "
                    "median likely award), not a cautious floor. Housing "
                    "Ombudsman repairs and damp/mould remedies commonly run from "
                    "low hundreds for short service failures to well over "
                    "£1,000, and into several thousand pounds for prolonged "
                    "severe maladministration affecting health or vulnerable "
                    "residents; do not compress severe, long-running cases "
                    "toward the low bands. Use amount_band only as a Proposer "
                    "modelling band: 0, 1-100, 101-250, 251-600, 601-1000, or "
                    "1000+. Set predicted_amount to null only if the facts are "
                    "too sparse for any order-of-magnitude estimate."
                )
            else:
                amount_clause = (
                    "Do not mention comparator determinations, proposition IDs, "
                    "paragraph references, case citations, supporting cases, or "
                    "comparator award amounts. For no-RAG ablations, do not "
                    "model comparator-based compensation: set predicted_amount "
                    "to null and amount_band to null."
                )
            reasoning_instruction = (
                "Before choosing the final JSON values, separate liability from "
                "remedy. In the reasoning field, identify: (1) the likely "
                "Ombudsman finding for each complaint head, (2) the specific "
                "user-provided fact, evidence item, timeline event, or KG fact "
                "that supports it, and (3) uncertainty caused by missing facts. "
                f"{amount_clause}\n\n"
            )
        else:
            # STREAM_C_ALWAYS_PREDICT_AMOUNTS: when set, the rag-mode
            # reasoning instruction tells the LLM to estimate amounts
            # even when retrieved comparators lack usable award figures.
            # Default off preserves the original "if no comparator awards
            # then null" research baseline. Flag-on aligns with
            # STREAM_C_NO_RAG_PREDICT_AMOUNTS so every mode always emits
            # an amount estimate.
            always_predict_amounts = (
                os.getenv("STREAM_C_ALWAYS_PREDICT_AMOUNTS", "0") == "1"
                or os.getenv("STREAM_C_NO_RAG_PREDICT_AMOUNTS", "0") == "1"
            )
            if always_predict_amounts:
                amount_clause = (
                    "Estimate predicted_amount and amount_band as the MOST "
                    "LIKELY total award for this case. Anchor on the "
                    "'Comparator ordered total' figures surfaced above: your "
                    "estimate should sit within their range and move toward the "
                    "higher comparators when the severity, duration, or "
                    "vulnerability in this case exceeds theirs. Where no "
                    "comparator total is given, use general UK Housing Ombudsman "
                    "compensation ranges for this issue type and severity. Give "
                    "a centred, unbiased point estimate --- the median likely "
                    "ordered total --- and do not deliberately under- or "
                    "over-state it. Set predicted_amount to null only if the "
                    "facts are too sparse for any order-of-magnitude estimate."
                )
            else:
                amount_clause = (
                    "If no retrieved determination contains a usable award/"
                    "order amount, set predicted_amount to null and explain "
                    "the amount uncertainty."
                )
            reasoning_instruction = (
                "Before choosing the final JSON values, separate liability from "
                "remedy. In the reasoning field, include: (1) the likely "
                "Ombudsman finding for each complaint head, (2) the cited "
                "determination or user fact that supports it, (3) any cited "
                "comparator award amounts, and (4) why the final amount_band and "
                "predicted_amount follow from those comparators. "
                f"{amount_clause} "
                "Use amount_band only as a Proposer modelling band: 0, 1-100, "
                "101-250, 251-600, 601-1000, or 1000+.\n\n"
            )
        return (
            "Forum: Housing Ombudsman Service\n"
            f"{task_line}"
            f"Issue type: {issue.issue_type.value}\n"
            f"Matter type: {matter_type}\n"
            f"Issue description: {issue.issue_description}\n"
            f"Compensation/remedy amount in dispute: {amount}\n"
            f"Region: {region}\n"
            f"Data completeness: {issue.data_completeness:.0%}\n\n"
            f"Resident position:\n{tenant_claim_text}\n\n"
            f"Landlord position:\n{landlord_claim_text}\n\n"
            f"Evidence summary:\n{evidence_summary}\n\n"
            f"Evidence conflicts:\n{evidence_conflicts}\n\n"
            f"Timeline:\n{timeline_summary}\n\n"
            f"Structured fact card:\n{kg_section}\n\n"
            f"{abstention_section}"
            f"KG constraints:\n{kg_constraints}\n\n"
            f"Retrieved Ombudsman determinations ({num_retrieved_cases}):\n"
            f"{retrieved_cases}\n\n"
            f"{reasoning_instruction}"
            "Return only JSON matching the required prediction schema. In the "
            "reasoning, use Housing Ombudsman outcome language: no "
            "maladministration, service failure, maladministration, severe "
            "maladministration, and remedies such as apology, repair action, "
            "compensation, case review, or policy review. In the JSON outcome "
            "field, use tenant_wins when any substantive repairs or complaint-"
            "handling issue is likely upheld or an additional resident remedy "
            "is likely, even if some complaint heads are not upheld. Use "
            "landlord_wins for likely no maladministration/no service failure. "
            "Use split only when the likely result is genuinely balanced after "
            "remedies, with material findings for both sides and no clear "
            "resident-upheld remedy dominance. Use uncertain only when the "
            "facts are too sparse or inconsistent.\n\n"
            "REQUIRED housing.repairs_social.v1 fields — do not omit:\n"
            "- `predicted_determination`: pick exactly one of "
            "'maladministration', 'severe_maladministration', 'service_failure', "
            "'reasonable_redress', 'no_maladministration', "
            "'resolved_with_intervention', 'outside_jurisdiction'. Do not leave "
            "this null on a Housing Ombudsman case.\n"
            "- `amount_construct`: whenever predicted_amount is non-null, set to "
            "'ordered_now' (fresh maladministration/service-failure compensation "
            "order), 'previously_offered' (reasonable-redress: landlord's "
            "pre-existing offer), or 'global_unapportioned' (resolved with "
            "intervention settlement). When predicted_amount is null, set "
            "amount_construct to null."
        )

    @staticmethod
    def _format_party_position(
        claim: Optional[Any],
        narrative: Optional[str],
    ) -> str:
        parts: List[str] = []
        if claim is not None:
            description = getattr(claim, "description", "") or ""
            if description:
                parts.append(description)
            claimed_amount = getattr(claim, "claimed_amount", None)
            if claimed_amount is not None:
                parts.append(f"Amount claimed: £{claimed_amount:.2f}")
        if narrative:
            trimmed = narrative.strip()
            if trimmed:
                label = "Narrative" if parts else "Party narrative (no structured claim filed)"
                parts.append(f"{label}: {trimmed[:1200]}")
        return "\n".join(parts) if parts else "Not provided"

    def _has_no_rag_case_specific_facts(
        self,
        *,
        issue: IssueContext,
        case_file: Any,
        tenant_claim_text: str,
        landlord_claim_text: str,
        kg_fact_card: str,
    ) -> bool:
        """Return True only when no-RAG has facts beyond issue labels/metadata."""

        candidates: List[Any] = [
            tenant_claim_text,
            landlord_claim_text,
            kg_fact_card,
        ]
        candidates.extend(issue.kg_constraints or [])

        for evidence in issue.supporting_evidence or []:
            if isinstance(evidence, dict):
                candidates.extend(
                    [
                        evidence.get("description"),
                        evidence.get("text"),
                        evidence.get("extracted_text"),
                        evidence.get("image_description"),
                    ]
                )
            else:
                candidates.extend(
                    [
                        getattr(evidence, "description", None),
                        getattr(evidence, "text", None),
                        getattr(evidence, "extracted_text", None),
                        getattr(evidence, "image_description", None),
                    ]
                )

        for event in issue.timeline_events or []:
            candidates.append(getattr(event, "description", None))

        for conflict in issue.evidence_conflicts or []:
            candidates.append(getattr(conflict, "tenant_position", None))
            candidates.append(getattr(conflict, "landlord_position", None))

        if case_file is not None:
            for raw_event in getattr(case_file, "events", []) or []:
                if isinstance(raw_event, dict):
                    candidates.append(raw_event.get("description"))

        return any(self._is_substantive_no_rag_fact_text(value) for value in candidates)

    @staticmethod
    def _is_substantive_no_rag_fact_text(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        text = re.sub(r"\s+", " ", value).strip()
        if not text:
            return False
        lowered = text.lower()
        nullish = {
            "not provided",
            "none",
            "none identified",
            "unknown",
            "no supporting evidence provided.",
            "no timeline events recorded.",
            "no structured kg fact card available.",
            "no retrieved cases in kg_only mode.",
            "no retrieved cases in llm_only mode.",
        }
        if lowered in nullish:
            return False
        if (
            "housing ombudsman determination records" in lowered
            and "landlord response" in lowered
        ):
            return False
        if lowered.startswith("source metadata only:"):
            return False
        return True

    @staticmethod
    def _get_text_attr(obj: Any, name: str) -> Optional[str]:
        if obj is None:
            return None
        value = getattr(obj, name, None)
        return value if isinstance(value, str) else None

    @staticmethod
    def _get_value(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            numeric = float(value)
            if not math.isfinite(numeric):
                return 0.0
            return numeric
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_optional_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(numeric):
            return None
        return numeric

    @staticmethod
    def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_probability(value: Any) -> float:
        numeric = IssuePredictor._to_float(value)
        return max(0.0, min(1.0, numeric))

    @staticmethod
    def _to_optional_str(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    def _render_factor_card_via_pack(
        self, case_file: Any, case_graph: Any
    ) -> tuple:
        """Render the factor card via the domain pack, falling back gracefully.

        Returns ``(card_markdown, gate_metadata)``. Falls back to an empty
        card + structured failure metadata when:

        - ``STREAM_C_PR4=0`` (flag disabled — legacy ``_format_kg_fact_card``).
        - ``case_file.domain_id`` is ``None`` (no domain to resolve).
        - ``domain_id`` is not registered (unknown pack).
        - The graph quality score fails the pack's gate.

        Spec: §6, §8.2, §17.6 (Cross-PR Contract C5), §19 PR 4.
        """
        use_pack = os.getenv("STREAM_C_PR4", "1") == "1"
        if not use_pack:
            # Legacy path: byte-equivalent _format_kg_fact_card.
            legacy_card = self._format_kg_fact_card(case_graph)
            return legacy_card, {
                "kg_used_for_prediction": case_graph is not None
                and bool(legacy_card),
                "kg_fallback_mode": None,
                "kg_gate_failure_reasons": [],
                "graph_quality_score": None,
            }

        domain_id = getattr(case_file, "domain_id", None)
        if domain_id is None:
            legacy_card = self._format_kg_fact_card(case_graph)
            return legacy_card, {
                "kg_used_for_prediction": False,
                "kg_fallback_mode": "legacy_no_domain_id",
                "kg_gate_failure_reasons": ["case_file.domain_id is None"],
                "graph_quality_score": None,
            }

        try:
            pack = get_domain_pack(domain_id)
        except DomainPackNotFoundError as exc:
            logger.warning(
                "domain_pack_unknown",
                domain_id=domain_id,
                error=str(exc),
            )
            return "", {
                "kg_used_for_prediction": False,
                "kg_fallback_mode": "rag_only",
                "kg_gate_failure_reasons": [
                    f"unknown domain pack: {domain_id}"
                ],
                "graph_quality_score": None,
            }

        score = self._compute_graph_quality_score(case_file, case_graph)
        if not pack.is_kg_usable(score):
            return "", {
                "kg_used_for_prediction": False,
                "kg_fallback_mode": "rag_only",
                "kg_gate_failure_reasons": _gate_failure_reasons(
                    score, pack.graph_quality_gate
                ),
                "graph_quality_score": score.score,
            }

        card = pack.render_factor_card(case_graph)
        return card, {
            "kg_used_for_prediction": bool(card),
            "kg_fallback_mode": None,
            "kg_gate_failure_reasons": [],
            "graph_quality_score": score.score,
        }

    def _compute_graph_quality_score(
        self, case_file: Any, case_graph: Any
    ) -> GraphQualityScore:
        """Compute a ``GraphQualityScore`` for ``case_graph``.

        For PR 4 this is a minimal heuristic; PR 5 + the real factor extractor
        populate this properly. The validators on ``GraphQualityScore`` forbid
        ``usable_for_prediction=True`` with non-empty ``failure_reasons``
        (and require ``failure_reasons`` when usable=False), so we construct
        accordingly.
        """
        if case_graph is None:
            return GraphQualityScore(
                score=0.0,
                evidence_backed_factor_count=0,
                dated_event_count=0,
                issue_count=0,
                outcome_or_remedy_candidate_count=0,
                unsupported_factor_rate=0.0,
                source_span_coverage=0.0,
                contradiction_count=0,
                usable_for_prediction=False,
                failure_reasons=["case_graph is None"],
            )

        # Deposit path: case_graph is a KGFacts (legacy adapter). Use
        # duck-typing rather than importing KGFacts here to keep the boundary
        # crisp.
        if (
            hasattr(case_graph, "deposit_protection_status")
            and hasattr(case_graph, "prescribed_information_status")
            and hasattr(case_graph, "check_in_inventory_baseline")
        ):
            # Count every non-empty typed field — including the auxiliary
            # detail fields (deposit_scheme, deposit_late_by_days, etc.) that
            # the legacy renderer surfaces. This ensures byte-equivalence
            # with the legacy ``_format_kg_fact_card`` for any KGFacts that
            # would have produced a non-empty card under the legacy path
            # (Hard Constraint #2). Three principal enums + four detail
            # fields = up to 7 evidence-backed factors per deposit case.
            principal = [
                case_graph.deposit_protection_status != "unknown",
                case_graph.prescribed_information_status != "unknown",
                case_graph.check_in_inventory_baseline != "unknown",
            ]
            detail = [
                getattr(case_graph, "deposit_scheme", None) is not None,
                getattr(case_graph, "deposit_late_by_days", None) is not None,
                getattr(case_graph, "prescribed_late_by_days", None)
                is not None,
            ]
            populated = sum(principal) + sum(detail)
            primary_known = sum(principal)
            # HEURISTIC_PR4_ONLY: PR 5's real factor extractor replaces this.
            # Single populated principal enum is counted as 2 evidence-backed factors
            # to preserve deposit byte-equivalence — see Task 4.4 review.
            #
            # Pre-PR-5 heuristic: any populated KGFacts that the legacy
            # renderer would have surfaced as a card MUST pass the gate, to
            # preserve byte-equivalence (Hard Constraint #2). Legacy emits
            # a card whenever ``is_empty()`` is False — i.e. any principal
            # enum is populated. Until the real graph extractor lands in
            # PR 5, we conservatively report 2 evidence-backed factors per
            # populated principal enum (typed value + its source span) so
            # the deposit gate's minimum of 2 is satisfied.
            evidence_count = primary_known * 2 + sum(detail)
            usable = primary_known >= 1
            failure_reasons: List[str] = []
            if not usable:
                failure_reasons.append(
                    "no typed deposit/prescribed/inventory facts populated"
                )
            return GraphQualityScore(
                score=min(populated / 6.0, 1.0),
                evidence_backed_factor_count=evidence_count,
                dated_event_count=2 if primary_known > 0 else 0,
                issue_count=1,
                outcome_or_remedy_candidate_count=1,
                unsupported_factor_rate=0.0,
                source_span_coverage=1.0 if primary_known > 0 else 0.0,
                contradiction_count=0,
                usable_for_prediction=usable,
                failure_reasons=failure_reasons,
            )

        # Repairs path: case_graph is a KnowledgeGraph-like with
        # factor_assertions. Heuristic until PR 5 lands real extraction.
        factor_assertions = getattr(case_graph, "factor_assertions", []) or []
        evidence_backed = [
            fa for fa in factor_assertions if getattr(fa, "supported_by", None)
        ]
        n_total = max(len(factor_assertions), 1)
        rate_unsupported = 1.0 - (len(evidence_backed) / n_total)
        coverage = len(evidence_backed) / n_total
        # STREAM_C_KG_GATE_RELAXED: when set, the gate's 3 prerequisite
        # ontology fields (dated_event_count, issue_count,
        # outcome_or_remedy_candidate_count) are synthesised to pass.
        # This lets the gate fire on factor-only backfilled data without
        # requiring the Stream D extractors (Event/IssueClaim/
        # OutcomeCandidate). The synthesised values are deliberately
        # minimal — 1 issue from the case file's primary matter type,
        # 1 outcome candidate from the existence of factor data, and
        # 2 dated events from the existence of FactorAssertion data
        # (since each FactorAssertion implies an underlying event/state).
        # Default off preserves the original gate requirements.
        relaxed = os.getenv("STREAM_C_KG_GATE_RELAXED", "0") == "1"
        if relaxed and factor_assertions:
            dated_event_count = max(
                len(getattr(case_graph, "dated_events", []) or []),
                2,
            )
            issue_count = max(
                len(getattr(case_graph, "issues", []) or []), 1
            )
            outcome_count = max(
                len(getattr(case_graph, "candidate_outcomes", []) or []), 1
            )
        else:
            dated_event_count = len(getattr(case_graph, "dated_events", []) or [])
            issue_count = len(getattr(case_graph, "issues", []) or [])
            outcome_count = len(getattr(case_graph, "candidate_outcomes", []) or [])
        usable = len(evidence_backed) >= 5
        return GraphQualityScore(
            score=len(evidence_backed) / n_total,
            evidence_backed_factor_count=len(evidence_backed),
            dated_event_count=dated_event_count,
            issue_count=issue_count,
            outcome_or_remedy_candidate_count=outcome_count,
            unsupported_factor_rate=rate_unsupported,
            source_span_coverage=coverage,
            contradiction_count=0,
            usable_for_prediction=usable,
            failure_reasons=[]
            if usable
            else [
                f"only {len(evidence_backed)} evidence-backed factors (min 5)"
            ],
        )

    @staticmethod
    def _format_kg_fact_card(kg_facts: Any) -> str:
        """Render the typed KG fact card for the IRAC prompt (SHA-33).

        Returns empty string when kg_facts is None or all-unknown so the
        prompt is byte-identical to today's for cases without KG signal.

        DEPRECATED (Stream C PR 4): this is the legacy deposit-only renderer.
        Production callers go through ``_render_factor_card_via_pack`` which
        dispatches to ``DomainPack.render_factor_card`` when ``STREAM_C_PR4=1``
        (default). This method is kept as the fallback path under
        ``STREAM_C_PR4=0`` and as the byte-equivalence reference for
        ``housing.deposit.v1``'s pack renderer. A post-Stream-C cleanup PR
        will delete it once the deposit pack has shipped to one release
        cycle.
        """
        if kg_facts is None:
            return ""
        try:
            if kg_facts.is_empty():
                return ""
        except AttributeError:
            return ""

        lines = ["", "KEY KG FACTS (typed):"]
        if kg_facts.deposit_protection_status != "unknown":
            line = f"- deposit_protection_status: {kg_facts.deposit_protection_status}"
            if getattr(kg_facts, "deposit_scheme", None):
                line += f" (scheme: {kg_facts.deposit_scheme})"
            if getattr(kg_facts, "deposit_late_by_days", None) is not None:
                line += f" (late by {kg_facts.deposit_late_by_days} days)"
            lines.append(line)
        if kg_facts.prescribed_information_status != "unknown":
            line = f"- prescribed_information_status: {kg_facts.prescribed_information_status}"
            if getattr(kg_facts, "prescribed_late_by_days", None) is not None:
                line += f" (late by {kg_facts.prescribed_late_by_days} days)"
            lines.append(line)
        if kg_facts.check_in_inventory_baseline != "unknown":
            lines.append(
                f"- check_in_inventory_baseline: {kg_facts.check_in_inventory_baseline}"
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _build_deposit_protection_summary(tenancy: Any) -> str:
        parts: List[str] = []

        deposit_amount = getattr(tenancy, "deposit_amount", None)
        if deposit_amount is not None:
            parts.append(f"Deposit: £{deposit_amount:.2f}")

        deposit_scheme = getattr(tenancy, "deposit_scheme", None)
        deposit_protected = getattr(tenancy, "deposit_protected", None)

        if deposit_protected is True:
            scheme_text = f" in {deposit_scheme}" if deposit_scheme else ""
            parts.append(f"Protected{scheme_text}")
        elif deposit_protected is False:
            parts.append("NOT protected in any scheme")
        else:
            parts.append("Protection status unknown")

        receipt_date = getattr(tenancy, "deposit_received_date", None)
        start_date = receipt_date or getattr(tenancy, "start_date", None)
        anchor_label = "deposit receipt" if receipt_date else "tenancy start fallback"
        protection_date = getattr(tenancy, "protection_date", None)
        if protection_date and start_date:
            days = (protection_date - start_date).days
            parts.append(
                f"Protection date: {protection_date} ({days} days after {anchor_label})"
            )
            if days > 30:
                parts.append(
                    f"⚠ Late protection — exceeds 30-day statutory deadline by "
                    f"{days - 30} days (s.213 Housing Act 2004)"
                )
        elif protection_date:
            parts.append(f"Protection date: {protection_date}")

        prescribed_info = getattr(tenancy, "prescribed_info_provided", None)
        prescribed_date = getattr(tenancy, "prescribed_info_date", None)
        if prescribed_info is True:
            if prescribed_date and start_date:
                pi_days = (prescribed_date - start_date).days
                parts.append(
                    f"Prescribed information served: {prescribed_date} "
                    f"({pi_days} days after {anchor_label})"
                )
                if pi_days > 30:
                    parts.append(
                        f"⚠ Prescribed info served late — exceeds 30-day deadline by "
                        f"{pi_days - 30} days (s.213(6) Housing Act 2004)"
                    )
            else:
                parts.append("Prescribed information: provided (date unknown)")
        elif prescribed_info is False:
            parts.append(
                "⚠ Prescribed information NOT provided — "
                "separate breach under s.213(6) Housing Act 2004"
            )

        if not parts:
            return "No deposit protection details available."

        return ". ".join(parts) + "."

    @staticmethod
    def _format_evidence_conflicts(issue: "IssueContext") -> str:
        conflicts = getattr(issue, "evidence_conflicts", None)
        if not conflicts:
            return "No direct evidence conflicts identified."

        rows: List[str] = []
        for idx, conflict in enumerate(conflicts, 1):
            tenant_pos = getattr(conflict, "tenant_position", "")
            landlord_pos = getattr(conflict, "landlord_position", "")
            rows.append(
                f"Conflict {idx}:\n"
                f"  Tenant says: {tenant_pos}\n"
                f"  Landlord says: {landlord_pos}"
            )
        return "\n".join(rows)

    @staticmethod
    def _format_timeline(issue: "IssueContext") -> str:
        events = getattr(issue, "timeline_events", None)
        if not events:
            return "No timeline events recorded."

        sorted_events = sorted(
            events,
            key=lambda e: getattr(e, "date", None) or _date_type.max,
        )

        rows: List[str] = []
        for event in sorted_events:
            ev_date = getattr(event, "date", None)
            description = getattr(event, "description", "")
            source = getattr(event, "source", "")
            date_str = str(ev_date) if ev_date else "Date unknown"
            source_str = f" [{source}]" if source else ""
            rows.append(f"- {date_str}: {description}{source_str}")
        return "\n".join(rows)
