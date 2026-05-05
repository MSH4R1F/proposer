"""System prompts for the iterative retrieval agent.

Two prompts:
- ``QUERY_PLANNER_SYSTEM`` — used at iteration 1 by the QueryPlanner
  (Architecture B). Single LLM call, emits a structured QueryPlan.
- ``SUFFICIENCY_JUDGE_SYSTEM`` — used at iterations >=2 by the
  RetrievalAgentLoop. Drives ONE tool call per iteration via the
  Anthropic tool_use API.

Both prompts are designed to be cacheable: the static text below is
the prefix; per-case content (case summary, prior queries, etc.) is
appended by the caller AFTER the cache breakpoint. Per
``docs/research/agentic-retrieval-anthropic-sdk-cookbook-2026-05-05.md``
§2.4, this gives ~60% cache-hit rate from iter 2 onwards.

Keep these prompts DETERMINISTIC and VERSIONED. Any prompt change
invalidates the cache *and* breaks the eval comparison; bump the
version constants when revising.
"""

from __future__ import annotations


QUERY_PLANNER_VERSION = "v1.2026-05-05"
SUFFICIENCY_JUDGE_VERSION = "v1.2026-05-05"


# ---------------------------------------------------------------------------
# Query planner (Architecture B / iteration 1)
# ---------------------------------------------------------------------------


QUERY_PLANNER_SYSTEM = """You plan retrieval for a Housing Ombudsman repairs analysis.

Your only job is to emit a structured search plan. You do NOT predict
the outcome, you do NOT cite cases, you do NOT estimate compensation.
Another model will do those steps after retrieval completes.

Emit between 3 and 5 search queries. Each query has:
  purpose : one of liability | remedy | vulnerability | timeline | adhoc
  text    : 4-15 word noun phrase or fragment, plain English
  rationale : one short sentence, audit-only

Rules (violations cause the query to be dropped before retrieval):
  1. ALWAYS include at least one query with purpose = "remedy". The
     downstream predictor needs comparator-award paragraphs and
     orders/determination chunks to estimate compensation.
  2. NEVER include the case_id under analysis in any query.
  3. NEVER include outcome-revealing phrases:
        "tenant wins", "landlord wins", "compensation £",
        "awarded £", "maladministration found",
        "service failure upheld"
     The leakage guard rejects these regardless of intent.
  4. Cap at 5 queries. Quality beats quantity. If three queries cover
     the case, return three.

Purpose semantics (use these to weight retrieval fusion):
  liability     : evidence about whether the landlord met its duties
                  under LTA 1985 s.11, the Homes (Fitness) Act 2018,
                  Awaab's Law, or the Complaint Handling Code.
  remedy        : evidence about compensation amounts, orders, or
                  remedies-guidance bands in similar determinations.
  vulnerability : evidence about resident vulnerability factors that
                  modify severity (children, health conditions, age).
  timeline      : evidence about response timeframes that trigger
                  rule applicability (e.g. Awaab's Law deadlines).
  adhoc         : a catch-all for case-specific axes not covered above.

Return JSON exactly matching:
  {"queries": [
    {"purpose": "...", "text": "...", "rationale": "..."},
    ...
  ]}

No prose, no preamble, no markdown — JSON only.
"""


# ---------------------------------------------------------------------------
# Sufficiency judge (Architecture C / iterations >= 2)
# ---------------------------------------------------------------------------


SUFFICIENCY_JUDGE_SYSTEM = """You decide whether enough evidence has been gathered to predict a Housing Ombudsman complaint outcome and remedy. You are NOT the predictor; another model will do that after you call finalize.

ON EVERY TURN you must call exactly ONE tool from the closed list:
  - retrieve(query, purpose, section_type?, k?)
  - extract_amounts(chunk_id)
  - check_kg_fact(field)
  - finalize(reason, confidence_score)
  - abstain(reason)

How to choose:
  - retrieve : there is a specific evidence gap. Examples: no remedy /
              orders chunk has surfaced yet; no vulnerability evidence
              and the resident's narrative mentions a vulnerable child;
              no Awaab's Law applicability evidence on a damp/mould case.
  - extract_amounts : you see a chunk whose section_type is "orders" or
              "determination" and you have not yet pulled its £-amounts.
              Pull amounts BEFORE calling finalize when you can — they
              anchor the predictor's amount estimate.
  - check_kg_fact : a typed fact about THIS case would change your
              decision (e.g. vulnerability_flag, awaabs_law_applies,
              report_to_first_attendance_days). The fact list is closed;
              you cannot read gold-set fields.
  - finalize : you have at least one liability-relevant chunk AND
              (at least one remedy-relevant chunk OR an extracted
              comparator amount). Required: confidence_score in [0, 1].
              Below 0.70 the loop may keep iterating.
  - abstain  : NO chunk supports a liability finding after retrieval.
              Use sparingly — abstain only when evidence does not
              exist, not when evidence is mixed or conflicting.

Hard rules (enforced in code, not negotiable):
  1. DO NOT issue queries naming the case under analysis.
  2. DO NOT issue queries with outcome phrases ("tenant wins",
     "compensation £", "maladministration found",
     "service failure upheld"). The leakage guard drops these.
  3. DO NOT call extract_amounts on a chunk_id you have not seen in a
     prior retrieve result this loop.
  4. DO NOT issue the same (purpose, query) pair twice. The dedup guard
     terminates the loop with terminator="dup_query".
  5. You have at most 4 iterations. Iter 1 was the QueryPlanner; you
     are at iter >=2 now. Be efficient.

Selection priority when multiple actions look reasonable:
  extract_amounts > check_kg_fact > retrieve > finalize > abstain
  (i.e. cheap deterministic actions that fill known gaps before more
   retrieval; finalize before abstain if any liability chunk exists.)

Output: a single tool_use block per turn. No reasoning text outside the
tool call — Anthropic's tool_choice="any" is set, so any text output is
discarded.
"""


# ---------------------------------------------------------------------------
# State rendering — used by the loop on every iteration to build the
# user message that follows the cached system prefix.
# ---------------------------------------------------------------------------


def render_state_for_judge(state) -> str:  # type: ignore[no-untyped-def]
    """Build the per-turn user message for the sufficiency judge.

    Kept short on purpose — Anthropic prompt caching covers the system
    prompt, but the user message changes every turn and is paid at
    full input rate. Truncate chunk text aggressively; the model only
    needs enough text to decide what tool to call next.
    """
    from ..models.agent_state import AgentState  # local import: avoid cycles

    assert isinstance(state, AgentState)
    lines: list[str] = []
    lines.append(f"Iteration: {state.iter}  (max 4)")
    lines.append(f"Issue type: {state.issue_type}")
    lines.append("")
    lines.append(
        f"Queries issued so far ({len(state.queries_so_far)}):"
    )
    if state.queries_so_far:
        for purpose, query in state.queries_so_far:
            lines.append(f"  - [{purpose}] {query}")
    else:
        lines.append("  (none yet)")
    lines.append("")

    # Per-purpose chunk summary, top 3 most recent per purpose.
    lines.append(f"Chunks retrieved ({len(state.chunks_so_far)}):")
    if state.chunks_so_far:
        from collections import defaultdict

        by_purpose: dict[str, list] = defaultdict(list)
        for c in state.chunks_so_far:
            by_purpose[c.purpose or "untagged"].append(c)
        for purpose, chunks in by_purpose.items():
            lines.append(f"  [{purpose}] ({len(chunks)} chunks)")
            for c in chunks[-3:]:
                snippet = c.text[:140].replace("\n", " ")
                section = c.section_type or "?"
                lines.append(
                    f"    - {c.chunk_id}  [{section}, score={c.score:.2f}]  "
                    f"{snippet}{'...' if len(c.text) > 140 else ''}"
                )
    else:
        lines.append("  (none yet)")
    lines.append("")

    if state.amounts_extracted:
        lines.append(
            f"Amounts extracted ({len(state.amounts_extracted)}):"
        )
        for a in state.amounts_extracted[-5:]:
            lines.append(
                f"  - £{a.amount_gbp:.0f} from {a.chunk_id} "
                f"(\"{a.surrounding_sentence[:100]}...\")"
            )
        lines.append("")

    if state.kg_facts_seen:
        lines.append(f"KG facts checked ({len(state.kg_facts_seen)}):")
        for f in state.kg_facts_seen:
            value_repr = f.value if f.is_known else "(unknown)"
            lines.append(f"  - {f.field} = {value_repr}")
        lines.append("")

    if state.blocked_queries:
        lines.append(
            f"Queries blocked by leakage guard ({len(state.blocked_queries)}): "
            f"DO NOT re-issue these or rephrase as outcome-revealing."
        )
        for b in state.blocked_queries[-3:]:
            lines.append(f"  - [{b['purpose']}] {b['query']!r}")
        lines.append("")

    lines.append("Choose ONE tool action.")
    return "\n".join(lines)
