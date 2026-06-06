"""Agentic GraphRAG ZOPA predictor.

A tool-calling agent that reads the case knowledge graph as memory, uses its
factors to shape comparator retrieval, reads the *actual ordered amounts* from
comparable decisions, and converges on a grounded final ZOPA that cites both
graph and text.

Design notes:
- Self-contained loop (drives ``ToolSet.dispatch`` directly and reads the
  verdict off a ``ToolContext`` subclass). We do NOT use ``AgentLoop`` because
  it only surfaces ``final_text``; we need a structured verdict.
- Tools are defined here with OpenAI-strict-mode-safe schemas (no
  ``minLength``/``maxLength``/``ge``/``le`` keywords — those are rejected by the
  OpenAI Responses strict schema rewriter). They wrap the same RAG retrieval +
  £-amount extraction the retrieval agent uses.
- Leakage: ``search_cases`` calls ``assert_query_safe`` and relies on the
  eval-filtered RAG wrapper (``_EvalFilteredRAGPipeline``) for source exclusion.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Literal, Optional

import structlog
from pydantic import BaseModel, Field

from ..agent_loop.tool import ToolContext, ToolSet, tool
from ..clients.types import LLMProvider
from ..models.agent_state import AgentAmount, AgentState
from ..models.prediction_v2 import (
    Citation,
    Determination,
    EvidenceStrength,
    IssueContext,
    IssueOutcome,
    IssuePrediction,
)
from .comparator_extractor import extract_pound_amounts
from .issue_predictor import _extract_order_amounts
from .retrieval_agent_tools import (
    RetrievalToolContext,
    _call_rag_retrieve,
    _to_agent_chunk,
    assert_query_safe,
)

logger = structlog.get_logger()


@dataclass
class AgenticPredictContext(RetrievalToolContext):
    """RetrievalToolContext + a slot for the agent's final verdict."""

    verdict: Optional[dict] = None


def _as_agentic_ctx(ctx: ToolContext) -> AgenticPredictContext:
    if not isinstance(ctx, AgenticPredictContext):
        raise RuntimeError("agentic-predict tools require AgenticPredictContext")
    return ctx


# --- Tools (OpenAI-strict-safe arg models: no length/range constraints) ------


class _EmptyArgs(BaseModel):
    pass


@tool(
    description=(
        "List the structured legal factors asserted for THIS case (from the "
        "knowledge graph). Use them to craft factor-aware comparator searches."
    )
)
async def list_case_factors(ctx: ToolContext, args: _EmptyArgs) -> dict:
    actx = _as_agentic_ctx(ctx)
    kg = actx.kg
    factors: List[dict] = []
    assertions = getattr(kg, "factor_assertions", None) if kg is not None else None
    for fa in assertions or []:
        fid = getattr(fa, "factor_id", None) or getattr(fa, "factor", None)
        if fid is None:
            continue
        supported = bool(getattr(fa, "supported_by", None))
        factors.append(
            {"factor_id": str(fid), "label": str(fid).replace("_", " "), "supported": supported}
        )
    return {"factors": factors, "count": len(factors)}


class SearchCasesArgs(BaseModel):
    query: str = Field(description="Search query (~4-200 chars). Include factor terms.")
    section_type: Optional[Literal["facts", "reasoning", "orders", "determination"]] = None
    k: Optional[int] = Field(default=None, description="How many comparable cases to return (1-8, default 5).")


@tool(
    description=(
        "Search for comparable Housing Ombudsman decisions. Returns chunk ids + "
        "text snippets. Prefer section_type='orders' to find the actual "
        "compensation ordered. Call several times with refined queries."
    )
)
async def search_cases(ctx: ToolContext, args: SearchCasesArgs) -> dict:
    actx = _as_agentic_ctx(ctx)
    state = actx.agent_state
    q = (args.query or "").strip()
    if len(q) < 4:
        raise RuntimeError("query too short (need >= 4 chars)")
    if state is not None and state.has_query("adhoc", q):
        return {"note": "duplicate query; try a different angle", "chunks": []}
    assert_query_safe(q, actx.gold_case_id)
    if actx.rag is None:
        raise RuntimeError("retrieval is not available in this run")
    k = max(1, min(int(args.k or 5), 8))
    # Call the (eval-filtered) RAG wrapper directly: real RAGPipeline.retrieve
    # takes `top_k` and returns a QueryResult, not a list.
    query_result = await actx.rag.retrieve(q, top_k=k)
    rag_results = getattr(query_result, "results", None)
    if rag_results is None:
        rag_results = query_result if isinstance(query_result, list) else []
    new_chunks = [_to_agent_chunk(r, purpose="adhoc") for r in rag_results]
    added = state.add_chunks(new_chunks) if state is not None else 0
    if state is not None:
        state.queries_so_far.append(("adhoc", q))
    return {
        "added": added,
        "total_seen": len(state.chunks_so_far) if state else 0,
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "section_type": c.section_type,
                "score": round(c.score, 3),
                "text": c.text[:400],
            }
            for c in new_chunks
        ],
    }


class ReadAmountsArgs(BaseModel):
    chunk_id: str = Field(description="A chunk_id from a prior search_cases result.")


@tool(
    description=(
        "Read the £ amounts in a retrieved chunk, each with its surrounding "
        "sentence, so you can judge which is the actual compensation order "
        "(ignore rent, arrears, service charges, and amounts merely OFFERED)."
    )
)
async def read_amounts(ctx: ToolContext, args: ReadAmountsArgs) -> dict:
    actx = _as_agentic_ctx(ctx)
    state = actx.agent_state
    chunks = state.chunks_so_far if state else []
    chunk = next((c for c in chunks if c.chunk_id == args.chunk_id), None)
    if chunk is None:
        raise RuntimeError(f"chunk_id {args.chunk_id!r} was not seen in prior searches")
    # The compensation ORDER total (filters rent/arrears/offered + OCR splits).
    order_totals = _extract_order_amounts(chunk.text, chunk.section_type)
    likely_order_total = order_totals[0] if order_totals else None
    # All raw £ figures + their sentences, so the agent can sanity-check.
    raw = extract_pound_amounts(
        chunk_id=chunk.chunk_id, text=chunk.text, paragraph_id=chunk.paragraph_id
    )
    out: List[dict] = []
    for a in raw:
        amt = getattr(a, "amount_gbp", None)
        if amt is None:
            continue
        sentence = str(getattr(a, "surrounding_sentence", ""))
        out.append({"amount_gbp": float(amt), "sentence": sentence[:200]})
    # Store ONLY the order total as the comparator's award (so the grounding
    # clamp + fallback anchor on real ordered totals, not low sub-components).
    if state is not None and likely_order_total is not None:
        state.amounts_extracted.append(
            AgentAmount(
                chunk_id=chunk.chunk_id,
                paragraph_id=chunk.paragraph_id,
                amount_gbp=float(likely_order_total),
                surrounding_sentence="order total",
                raw_match="",
            )
        )
    return {
        "chunk_id": chunk.chunk_id,
        "section_type": chunk.section_type,
        "likely_order_total": likely_order_total,
        "all_amounts": out,
    }


class FinalizePredictionArgs(BaseModel):
    outcome: Literal["tenant_wins", "landlord_wins", "split", "uncertain"]
    determination: Optional[str] = None
    predicted_amount: float = Field(description="Most likely total award, GBP")
    low: float = Field(description="ZOPA lower bound, GBP")
    high: float = Field(description="ZOPA upper bound, GBP")
    confidence: float = Field(description="Your confidence, 0..1")
    rationale: str = Field(description="Why this amount follows from the comparator orders + case factors")
    comparator_source_ids: List[str] = Field(default_factory=list)
    comparator_amounts: List[float] = Field(default_factory=list)
    kg_factors_used: List[str] = Field(default_factory=list)


@tool(
    description=(
        "Record your FINAL grounded prediction: the most likely award "
        "(predicted_amount) and ZOPA bounds (low/high), citing the comparator "
        "decisions (source/chunk ids) and ordered amounts you relied on, and the "
        "KG factors that drove it. Call this exactly once, as your last action."
    )
)
async def finalize_prediction(ctx: ToolContext, args: FinalizePredictionArgs) -> dict:
    actx = _as_agentic_ctx(ctx)
    actx.verdict = args.model_dump()
    return {"status": "recorded", "predicted_amount": args.predicted_amount}


def build_agentic_predict_toolset() -> ToolSet:
    return ToolSet(
        name="agentic_predict_v1",
        tools=(search_cases, read_amounts, list_case_factors, finalize_prediction),
    )


AGENTIC_PREDICT_SYSTEM_PROMPT = (
    "You estimate the likely COMPENSATION AWARD for a UK Housing Ombudsman "
    "repairs/complaint case, and express it as a settlement range (ZOPA).\n\n"
    "Work like a grounded analyst, using your tools:\n"
    "1. Call list_case_factors to read this case's structured factors (severity, "
    "duration, vulnerability, complaint-handling, prior offers).\n"
    "2. Use those factors to search for comparable decisions: call search_cases "
    "with factor-aware queries (e.g. 'damp mould vulnerable resident prolonged "
    "delay compensation order'), preferring section_type='orders'. Search more "
    "than once, refining, until you have several genuinely comparable orders.\n"
    "3. For the most relevant retrieved cases, call read_amounts(chunk_id). It "
    "returns 'likely_order_total' (the system's best extraction of the actual "
    "Ombudsman compensation order) plus all_amounts with sentences. Use "
    "likely_order_total as that comparator's award unless its sentences clearly "
    "show a different ordered total; ignore rent, arrears, service charges, and "
    "amounts the landlord merely OFFERED.\n"
    "4. Estimate the MOST LIKELY total award for THIS case, anchored within the "
    "comparator orders: move toward the higher comparators when this case's "
    "severity/duration/vulnerability exceeds theirs, lower when it is milder. Do "
    "NOT lowball, and do not exceed the comparator range without a factor-"
    "grounded reason. Give a centred estimate, not a cautious floor.\n"
    "5. Call finalize_prediction once with predicted_amount (the centre), "
    "low/high (your ZOPA), the outcome, the determination class, confidence, a "
    "rationale, and the comparator source ids / amounts and kg factors you used.\n\n"
    "Cite-or-abstain: every number must trace to retrieved comparator orders. If "
    "no comparable order can be found, finalize with outcome='uncertain' and your "
    "best-supported low estimate.\n\n"
    "BE FAST — you have a tight step budget. Aim to finalize within ~5 tool steps. "
    "Do AT MOST 2 searches, then read_amounts on the 3-4 most relevant comparators "
    "(prefer the orders/decision sections), then finalize. You may call several "
    "tools in a single turn to save steps. Do not keep searching once you have a "
    "handful of comparable ordered amounts."
)


class AgenticPredictor:
    """Runs the agentic GraphRAG loop for one issue and returns an IssuePrediction."""

    def __init__(
        self,
        llm_client: Any,
        *,
        provider: LLMProvider = LLMProvider.OPENAI,
        model: Optional[str] = None,
        max_turns: int = 6,
        max_tokens: int = 3500,
    ) -> None:
        self.llm = llm_client
        self.provider = provider
        self.model = model
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.toolset = build_agentic_predict_toolset()

    async def predict_issue(
        self,
        *,
        case_file: Any,
        issue: IssueContext,
        rag: Any,
        knowledge_graph: Any,
        gold_case_id: str,
        case_summary: str,
    ) -> IssuePrediction:
        case_id = gold_case_id or getattr(case_file, "case_id", "") or ""
        ctx = AgenticPredictContext(
            rag=rag,
            kg=knowledge_graph,
            agent_state=AgentState(case_id=case_id, issue_type=issue.issue_type.value),
            gold_case_id=case_id,
        )
        schemas = self.toolset.schemas_for(self.provider)
        user_prompt = (
            "Predict the likely compensation award for this housing case.\n\n"
            f"Issue under analysis: {issue.issue_type.value} — {issue.issue_description}\n\n"
            f"Case summary:\n{case_summary}\n\n"
            "Use your tools to read the case factors, find comparable decisions, "
            "read their actual ordered amounts, then finalize a grounded ZOPA."
        )
        messages: List[dict] = [{"role": "user", "content": user_prompt}]
        turns = 0
        for _turn_idx in range(self.max_turns):
            turns += 1
            try:
                resp = await self.llm.run_agent_turn(
                    system_prompt=AGENTIC_PREDICT_SYSTEM_PROMPT,
                    messages=messages,
                    tool_schemas=schemas,
                    model=self.model,
                    max_tokens=self.max_tokens,
                )
            except Exception as exc:  # malformed tool JSON, rate limit, etc.
                logger.warning(
                    "agentic_turn_failed", error=str(exc)[:200], turn=turns
                )
                break  # fall back to comparator-median / abstain below

            messages.append({"role": "assistant", "content": resp.content_blocks})
            tool_uses = [
                b
                for b in resp.content_blocks
                if isinstance(b, dict) and b.get("type") == "tool_use"
            ]
            if not tool_uses:
                break
            result_blocks: List[dict] = []
            for b in tool_uses:
                _tname = str(b.get("name", ""))
                r = await self.toolset.dispatch(_tname, b.get("input") or {}, ctx)
                logger.debug(
                    "agentic_tool_call",
                    tool=_tname,
                    is_error=r.is_error,
                    payload=str(r.model_payload)[:200],
                )
                try:
                    payload = json.dumps(r.model_payload, default=str)
                except Exception:
                    payload = str(r.model_payload)
                result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": str(b.get("id", "")),
                        "content": payload,
                        "is_error": r.is_error,
                    }
                )
            messages.append({"role": "user", "content": result_blocks})
            if ctx.verdict is not None:
                break
            # Nudge toward finalizing as the turn budget runs out.
            if (
                _turn_idx >= self.max_turns - 3
                and ctx.agent_state is not None
                and ctx.agent_state.amounts_extracted
            ):
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You have gathered enough comparator orders. Do NOT "
                            "search again. Now call finalize_prediction with your "
                            "best grounded estimate: predicted_amount (the centre), "
                            "low/high (the ZOPA), outcome, determination, "
                            "confidence, rationale, and the comparator source ids + "
                            "amounts and kg factors you used."
                        ),
                    }
                )

        pred = self._build_issue_prediction(issue, ctx)
        logger.info(
            "agentic_predict_issue_complete",
            case_id=case_id,
            issue=issue.issue_type.value,
            turns=turns,
            finalized=ctx.verdict is not None,
            amounts_seen=len(ctx.agent_state.amounts_extracted) if ctx.agent_state else 0,
            predicted_amount=pred.predicted_amount,
        )
        return pred

    def _build_issue_prediction(
        self, issue: IssueContext, ctx: AgenticPredictContext
    ) -> IssuePrediction:
        v = ctx.verdict
        if v is None:
            amts = (
                [float(a.amount_gbp) for a in ctx.agent_state.amounts_extracted]
                if ctx.agent_state
                else []
            )
            if amts:
                srt = sorted(amts)
                amt = srt[len(srt) // 2]
                return IssuePrediction(
                    issue_type=issue.issue_type,
                    issue_description=issue.issue_description,
                    outcome=IssueOutcome.TENANT_WINS,
                    raw_confidence=0.4,
                    predicted_amount=amt,
                    amount_range=(round(amt * 0.85, 2), round(amt * 1.15, 2)),
                    reasoning="Agent did not finalize; fell back to median of comparator amounts read.",
                    evidence_strength=EvidenceStrength.WEAK,
                )
            return IssuePrediction(
                issue_type=issue.issue_type,
                issue_description=issue.issue_description,
                outcome=IssueOutcome.UNCERTAIN,
                raw_confidence=0.2,
                predicted_amount=None,
                reasoning="Agent did not finalize and no comparator amounts were found.",
                evidence_strength=EvidenceStrength.WEAK,
            )
        det: Optional[Determination] = None
        if v.get("determination"):
            try:
                det = Determination(str(v["determination"]))
            except Exception:
                det = None
        cites = [
            Citation(
                case_reference=str(s),
                year=0,
                quote="",
                relevance="comparator order",
                verified=False,
            )
            for s in (v.get("comparator_source_ids") or [])
        ]
        amount = v.get("predicted_amount")
        low, high = v.get("low"), v.get("high")
        # Grounding guard: bound the agent's amount to the comparator-order
        # evidence it actually read. If it is wildly outside (a hallucinated
        # high/low under the always-predict relaxation), snap to the median of
        # the extracted comparator amounts and rescale the ZOPA around it.
        extracted = (
            [float(a.amount_gbp) for a in ctx.agent_state.amounts_extracted]
            if ctx.agent_state
            else []
        )
        if extracted and amount is not None:
            srt = sorted(extracted)
            med = srt[len(srt) // 2]
            if med > 0 and (float(amount) > 2.0 * med or float(amount) < 0.5 * med):
                amount = med
                low, high = round(med * 0.85, 2), round(med * 1.15, 2)
        return IssuePrediction(
            issue_type=issue.issue_type,
            issue_description=issue.issue_description,
            outcome=IssueOutcome(str(v.get("outcome", "uncertain"))),
            raw_confidence=float(v.get("confidence", 0.5)),
            predicted_amount=float(amount) if amount is not None else None,
            amount_range=(
                (round(float(low), 2), round(float(high), 2))
                if low is not None and high is not None
                else None
            ),
            reasoning=str(v.get("rationale", ""))[:2000],
            predicted_determination=det,
            supporting_cases=cites,
            evidence_strength=EvidenceStrength.MODERATE,
            key_factors=[str(f) for f in (v.get("kg_factors_used") or [])],
        )
