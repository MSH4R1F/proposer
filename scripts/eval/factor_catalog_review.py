"""§22.1 LLM Panel Adversarial Review CLI.

Dispatches N panelists (default 3) against a domain pack's factor catalog
using a skeptical UK housing/employment paralegal role prompt with a
6-criterion rubric (labelability / operational definition / polarity /
authority / redundancy / other concerns).

Aggregates outputs into a disagreement matrix and writes a markdown artifact.

Usage:
    python scripts/eval/factor_catalog_review.py \\
        --domain housing.repairs_social.v1 \\
        --dry-run

    python scripts/eval/factor_catalog_review.py \\
        --domain housing.repairs_social.v1 \\
        --execute \\
        --panelists 3 \\
        --seed 42

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §22.1
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Type, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Path bootstrap — make packages importable when run as a script
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
# Add packages/ parent dir so `import llm_orchestrator` resolves correctly.
_PACKAGES_DIR = str(_REPO_ROOT / "packages")
if _PACKAGES_DIR not in sys.path:
    sys.path.insert(0, _PACKAGES_DIR)

# Load .env early so ANTHROPIC_API_KEY / OPENAI_API_KEY / LLM_* vars are set
# before any client construction.  Mirrors scripts/eval/predict_all.py:50,57.
from dotenv import load_dotenv  # noqa: E402 (after path fixup)
load_dotenv(_REPO_ROOT / ".env")

from llm_orchestrator.clients.base import BaseLLMClient  # noqa: E402 (after path fixup)

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# §22.1 Reviewer prompt (verbatim from task spec)
# ---------------------------------------------------------------------------

REVIEWER_PROMPT = """You are a skeptical UK housing/employment paralegal reviewing a junior associate's draft factor catalog for a hybrid RAG + KG legal-prediction system. Your job is to flag every plausible problem.

You will receive:
1. A factor catalog (YAML) defining the legal factors to be extracted from case narratives.
2. The annotation rubric explaining how each factor is operationalised.
3. The closed outcome ID set the factors map to.
4. 3-5 corpus narrative excerpts (with determinations stripped) — these are realistic inputs the catalog must handle.

For EACH factor in the catalog, answer these six questions:

A. Labelability: Can this factor be assigned by reading the narrative ALONE — without reading the determination paragraph? If not, it's leaking the outcome. Yes/No, with brief reasoning if No.

B. Operational definition: Is the rubric definition specific enough that two annotators reading only the rubric would agree on borderline cases? If ambiguous, name the ambiguity.

C. Polarity check: Does the declared polarity (pro_claimant / pro_respondent / neutral) match how UK case law and Ombudsman practice actually treat this fact pattern? If wrong, give the correct polarity.

D. Authority alignment: Which statute / Ombudsman scheme provision / ACAS code / official guidance grounds this factor? If you can't identify any real ground, flag it. Do NOT fabricate citations — if you don't know, say so.

E. Redundancy: Does this factor duplicate or substantially overlap another factor in the catalog? Name the duplicate(s).

F. Other concerns: Anything else (vague language, hidden assumptions, biased framing, etc.)

THEN at the end: List any IMPORTANT FACTORS MISSING from the catalog that the corpus excerpts suggest are needed.

Output STRICTLY as JSON matching this schema:
{
  "panelist_id": "<your model identifier>",
  "per_factor_findings": [
    {
      "factor_id": "...",
      "labelable_from_narrative": true,
      "definition_clear": true,
      "polarity_correct": true,
      "authority_grounded": true,
      "redundant_with": [],
      "flags": ["..."]
    }
  ],
  "missing_factors_suggested": ["..."],
  "overall_notes": "..."
}

Be rigorous. Bad work is worse than no work."""

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class FactorFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    factor_id: str
    labelable_from_narrative: bool
    definition_clear: bool
    polarity_correct: bool
    authority_grounded: bool
    redundant_with: List[str]
    flags: List[str]


class PanelistReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    panelist_id: str
    per_factor_findings: List[FactorFinding]
    missing_factors_suggested: List[str]
    overall_notes: str


class _DisagreementRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    factor_id: str
    # one entry per panelist: {"panelist_id": ..., "axes_flagged": [...]}
    by_panelist: List[Dict[str, Any]]
    # "unanimous" | "majority" | "single" | "clean"
    consensus_level: str


class PanelReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    panelist_reviews: List[PanelistReview]
    disagreement_matrix: List[Dict[str, Any]]
    unanimous_flags: List[Dict[str, Any]]
    majority_flags: List[Dict[str, Any]]
    single_flags: List[Dict[str, Any]]
    cost_report: Dict[str, Any]


# ---------------------------------------------------------------------------
# Determination stripping
# ---------------------------------------------------------------------------

_STRIP_PATTERN = re.compile(
    r"^#{1,6}\s*(?:Determination|Decision|Findings|Outcome|Order|Compensation)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)


def strip_determination(text: str) -> str:
    """Return *text* with everything from the first determination-style header
    to the end of the document removed.

    If no such header is found, the full text is returned unchanged.
    """
    m = _STRIP_PATTERN.search(text)
    if m is None:
        return text
    return text[: m.start()].rstrip()


def cap_excerpt(text: str, max_chars: int = 1500) -> str:
    """Truncate *text* to at most *max_chars* characters."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


# ---------------------------------------------------------------------------
# Domain pack loading
# ---------------------------------------------------------------------------

_DOMAIN_PACK_ROOTS = {
    "housing.repairs_social.v1": Path("packages/domain_packs/housing/repairs_social"),
}


def load_domain_pack(domain_id: str, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load factors.yaml, outcomes.yaml, and annotation_rubric.md for *domain_id*.

    Returns a dict with keys:
        ``factors``  — list of factor dicts
        ``outcomes`` — list of outcome dicts
        ``rubric``   — raw markdown string
        ``domain_id`` — echoed back
    """
    if repo_root is None:
        repo_root = _REPO_ROOT

    rel = _DOMAIN_PACK_ROOTS.get(domain_id)
    if rel is None:
        # Try to derive path from dotted id:
        # housing.repairs_social.v1 → packages/domain_packs/housing/repairs_social
        parts = domain_id.split(".")
        # strip trailing version-like segment (vN)
        if re.match(r"^v\d+$", parts[-1]):
            parts = parts[:-1]
        rel = Path("packages/domain_packs") / Path(*parts)

    pack_dir = repo_root / rel
    if not pack_dir.exists():
        raise FileNotFoundError(
            f"Domain pack directory not found: {pack_dir} (domain_id={domain_id!r})"
        )

    factors_path = pack_dir / "factors.yaml"
    outcomes_path = pack_dir / "outcomes.yaml"
    rubric_path = pack_dir / "annotation_rubric.md"

    if not factors_path.exists():
        raise FileNotFoundError(f"factors.yaml missing in {pack_dir}")
    if not outcomes_path.exists():
        raise FileNotFoundError(f"outcomes.yaml missing in {pack_dir}")
    if not rubric_path.exists():
        raise FileNotFoundError(f"annotation_rubric.md missing in {pack_dir}")

    with factors_path.open() as f:
        raw_factors = yaml.safe_load(f)
    with outcomes_path.open() as f:
        raw_outcomes = yaml.safe_load(f)

    factors = raw_factors.get("factors", []) if isinstance(raw_factors, dict) else raw_factors
    outcomes_block = raw_outcomes.get("outcomes", []) if isinstance(raw_outcomes, dict) else raw_outcomes
    rubric = rubric_path.read_text()

    return {
        "domain_id": domain_id,
        "factors": factors,
        "outcomes": outcomes_block,
        "rubric": rubric,
        "pack_dir": pack_dir,
    }


# ---------------------------------------------------------------------------
# Catalog SHA hash
# ---------------------------------------------------------------------------


def catalog_sha(pack: Dict[str, Any]) -> str:
    """SHA-256 of the serialised factor catalog (deterministic, sorted keys)."""
    payload = json.dumps(pack["factors"], sort_keys=True, ensure_ascii=True).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Corpus excerpt loading
# ---------------------------------------------------------------------------

_DEFAULT_CORPUS_PATH = (
    _REPO_ROOT / "data" / "eval" / "housing_ombudsman_balanced_50_20260506.jsonl"
)
_RAW_BASE = _REPO_ROOT / "data"


def load_corpus_excerpts(
    n: int = 5,
    seed: int = 42,
    corpus_path: Optional[Path] = None,
    max_chars: int = 1500,
) -> List[str]:
    """Load *n* corpus narrative excerpts, stripped of determination sections.

    Reads the JSONL manifest, resolves ``raw_text_path`` for each entry,
    and returns up to *n* capped excerpts chosen deterministically via *seed*.

    If raw text files are missing (common in dev environments where the full
    corpus has not been fetched), falls back to a metadata-derived stub so
    the CLI still runs.
    """
    path = corpus_path or _DEFAULT_CORPUS_PATH
    if not path.exists():
        return []

    rng = random.Random(seed)
    rows: List[Dict[str, Any]] = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    rng.shuffle(rows)
    selected = rows[:n]

    excerpts: List[str] = []
    for row in selected:
        raw_rel = row.get("raw_text_path", "")
        raw_abs = _RAW_BASE / raw_rel if raw_rel else None
        if raw_abs and raw_abs.exists():
            text = raw_abs.read_text(encoding="utf-8", errors="replace")
        else:
            # Stub: compose a brief description from available metadata
            text = (
                f"Case: {row.get('title', row.get('case_id', 'unknown'))}\n"
                f"Outcome: {row.get('outcome_raw', 'unknown')}\n"
                f"Matter types: {', '.join(row.get('matter_types', []))}\n"
                f"Landlord: {row.get('landlord_name', 'unknown')}\n"
            )
        stripped = strip_determination(text)
        excerpts.append(cap_excerpt(stripped, max_chars=max_chars))

    return excerpts


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_user_message(
    pack: Dict[str, Any],
    excerpts: List[str],
) -> str:
    """Build the user-turn message for the panelist."""
    factor_yaml = yaml.dump({"factors": pack["factors"]}, default_flow_style=False, allow_unicode=True)
    outcome_yaml = yaml.dump({"outcomes": pack["outcomes"]}, default_flow_style=False, allow_unicode=True)

    excerpts_block = ""
    if excerpts:
        parts = []
        for i, ex in enumerate(excerpts, 1):
            parts.append(f"### Excerpt {i}\n\n{ex}")
        excerpts_block = "\n\n".join(parts)
    else:
        excerpts_block = "_No corpus excerpts available._"

    return f"""## 1. Factor Catalog (YAML)

```yaml
{factor_yaml}
```

## 2. Annotation Rubric

{pack["rubric"]}

## 3. Closed Outcome ID Set

```yaml
{outcome_yaml}
```

## 4. Corpus Narrative Excerpts (determinations stripped)

{excerpts_block}
"""


# ---------------------------------------------------------------------------
# Panel — dispatches N clients
# ---------------------------------------------------------------------------


class Panel:
    """Dispatches the reviewer prompt to a list of LLM clients."""

    def __init__(self, clients: List[BaseLLMClient]) -> None:
        self.clients = clients

    async def run(
        self,
        pack: Dict[str, Any],
        excerpts: List[str],
    ) -> "tuple[List[PanelistReview], Dict[str, Any]]":
        """Dispatch prompts to all clients concurrently.

        Returns a ``(reviews, cost_report)`` tuple so the caller can pass the
        cost data directly into ``Aggregator.aggregate`` without a rebuild.
        """
        user_msg = build_user_message(pack, excerpts)
        tasks = [
            self._call_one(client, user_msg)
            for client in self.clients
        ]
        reviews = list(await asyncio.gather(*tasks))
        cost_report = _build_cost_report(self.clients)
        return reviews, cost_report

    async def _call_one(
        self, client: BaseLLMClient, user_msg: str
    ) -> PanelistReview:
        # Prefer the explicit provider:model label set by _build_clients_from_providers;
        # fall back to bare model attribute for injected-test clients.
        model_id = getattr(client, "_panelist_label", None) or getattr(client, "model", "unknown-model")
        # Inject the model identifier into the system prompt so the panelist
        # fills in panelist_id correctly (the fake client ignores this and
        # returns its canned value; real clients will use it).
        system = REVIEWER_PROMPT + f"\n\nYour model identifier for the panelist_id field is: {model_id}"
        messages = [{"role": "user", "content": user_msg}]
        return await client.generate_structured(
            messages=messages,
            system_prompt=system,
            response_model=PanelistReview,
            max_tokens=8192,
        )

    def dry_run_info(
        self,
        pack: Dict[str, Any],
        excerpts: List[str],
    ) -> Dict[str, Any]:
        """Return a preview dict without calling any LLM (synchronous)."""
        user_msg = build_user_message(pack, excerpts)
        model_ids = [
            getattr(c, "_panelist_label", None) or getattr(c, "model", "unknown")
            for c in self.clients
        ]
        prompt_preview = REVIEWER_PROMPT[:400] + "\n...[truncated]..."
        return {
            "panelist_count": len(self.clients),
            "model_ids": model_ids,
            "domain_id": pack["domain_id"],
            "factor_count": len(pack["factors"]),
            "excerpt_count": len(excerpts),
            "system_prompt": prompt_preview,
            "user_message_length": len(user_msg),
        }


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

_BINARY_AXES = [
    "labelable_from_narrative",
    "definition_clear",
    "polarity_correct",
    "authority_grounded",
]


def _axes_flagged(finding: FactorFinding) -> List[str]:
    """Return the list of boolean axes that are *False* (flagged) for this finding.

    Boolean axes are driven by ``_BINARY_AXES`` so that adding a new axis to
    ``FactorFinding`` only requires one update site.
    """
    axes = [ax for ax in _BINARY_AXES if not getattr(finding, ax)]
    if finding.redundant_with:
        axes.append("redundancy")
    if finding.flags:
        axes.append("other_flags")
    return axes


class Aggregator:
    """Combines multiple PanelistReview objects into a PanelReview."""

    def __init__(self, reviews: List[PanelistReview]) -> None:
        self.reviews = reviews

    def aggregate(self, cost_report: Optional[Dict[str, Any]] = None) -> PanelReview:
        """Build a complete PanelReview.

        *cost_report* is the dict returned by ``_build_cost_report``; when
        omitted (e.g. tests that don't have real clients), a zeroed placeholder
        is substituted so the object is always well-formed.
        """
        n_panelists = len(self.reviews)

        # Collect all unique factor IDs across all reviews
        factor_ids: List[str] = []
        seen: set = set()
        for review in self.reviews:
            for ff in review.per_factor_findings:
                if ff.factor_id not in seen:
                    factor_ids.append(ff.factor_id)
                    seen.add(ff.factor_id)

        matrix: List[Dict[str, Any]] = []
        unanimous: List[Dict[str, Any]] = []
        majority: List[Dict[str, Any]] = []
        single: List[Dict[str, Any]] = []

        for fid in factor_ids:
            by_panelist = []
            # count how many panelists flagged this factor on ANY axis
            flag_count = 0
            for review in self.reviews:
                finding = next(
                    (ff for ff in review.per_factor_findings if ff.factor_id == fid),
                    None,
                )
                if finding is None:
                    axes = []
                else:
                    axes = _axes_flagged(finding)

                by_panelist.append({
                    "panelist_id": review.panelist_id,
                    "axes_flagged": axes,
                })
                if axes:
                    flag_count += 1

            if flag_count == 0:
                level = "clean"
            elif flag_count == 1:
                level = "single"
            elif flag_count < n_panelists:
                level = "majority"
            else:
                level = "unanimous"

            row: Dict[str, Any] = {
                "factor_id": fid,
                "by_panelist": by_panelist,
                "consensus_level": level,
            }
            matrix.append(row)

            entry = {"factor_id": fid, "by_panelist": by_panelist}
            if level == "unanimous":
                unanimous.append(entry)
            elif level == "majority":
                majority.append(entry)
            elif level == "single":
                single.append(entry)

        # Use provided cost report or a zeroed placeholder
        if cost_report is None:
            cost_report = {
                "total_tokens_in": 0,
                "total_tokens_out": 0,
                "estimated_cost_usd": 0.0,
                "estimated_cost_gbp": 0.0,
                "panelist_stats": [],
                "note": "No cost data available (aggregated without client stats).",
            }

        return PanelReview(
            panelist_reviews=self.reviews,
            disagreement_matrix=matrix,
            unanimous_flags=unanimous,
            majority_flags=majority,
            single_flags=single,
            cost_report=cost_report,
        )


def _build_cost_report(clients: List[BaseLLMClient]) -> Dict[str, Any]:
    """Collect stats from clients after run() and compute costs."""
    total_in = 0
    total_out = 0
    total_usd = 0.0
    panelist_stats = []
    for client in clients:
        stats = client.get_stats()
        total_in += stats.get("tokens_in", 0)
        total_out += stats.get("tokens_out", 0)
        usd = stats.get("estimated_cost_usd") or 0.0
        total_usd += usd
        panelist_stats.append({
            "model": stats.get("model", "unknown"),
            "provider": stats.get("provider", "unknown"),
            "tokens_in": stats.get("tokens_in", 0),
            "tokens_out": stats.get("tokens_out", 0),
            "estimated_cost_usd": usd,
        })
    # USD → GBP at a fixed rate for cost reporting (not financial advice)
    gbp = total_usd * 0.80
    return {
        "total_tokens_in": total_in,
        "total_tokens_out": total_out,
        "estimated_cost_usd": round(total_usd, 6),
        "estimated_cost_gbp": round(gbp, 6),
        "panelist_stats": panelist_stats,
        "note": "Estimated costs are approximate; exchange rate fixed at 0.80 USD/GBP.",
    }


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class Renderer:
    """Writes the PanelReview as a markdown artifact."""

    def write(
        self,
        *,
        panel_review: PanelReview,
        pack: Dict[str, Any],
        output_path: Path,
        date_str: str,
    ) -> None:
        content = self._render(panel_review=panel_review, pack=pack, date_str=date_str)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

    def _render(
        self,
        *,
        panel_review: PanelReview,
        pack: Dict[str, Any],
        date_str: str,
    ) -> str:
        domain_id = pack["domain_id"]
        sha = catalog_sha(pack)
        panelist_ids = [r.panelist_id for r in panel_review.panelist_reviews]
        n = len(panelist_ids)

        lines: List[str] = []

        # Header
        lines.append(f"# §22.1 Factor Catalog Panel Review")
        lines.append(f"")
        lines.append(f"## Panel Composition")
        lines.append(f"")
        lines.append(f"| # | Panelist ID |")
        lines.append(f"|---|-------------|")
        for i, pid in enumerate(panelist_ids, 1):
            lines.append(f"| {i} | `{pid}` |")
        lines.append(f"")
        lines.append(f"- **Domain:** `{domain_id}`")
        lines.append(f"- **Date:** {date_str}")
        lines.append(f"- **Catalog SHA (first 16 hex):** `{sha}`")
        lines.append(f"- **Factor count:** {len(pack['factors'])}")
        lines.append(f"- **Panelist count:** {n}")
        lines.append(f"")

        # Per-panelist raw output sections
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## Per-Panelist Raw Output")
        lines.append(f"")
        for review in panel_review.panelist_reviews:
            lines.append(f"### Panelist: `{review.panelist_id}`")
            lines.append(f"")
            lines.append(f"**Overall notes:** {review.overall_notes or '_none_'}")
            lines.append(f"")
            if review.missing_factors_suggested:
                lines.append(f"**Missing factors suggested:**")
                for mf in review.missing_factors_suggested:
                    lines.append(f"- {mf}")
                lines.append(f"")
            lines.append(f"**Per-factor findings:**")
            lines.append(f"")
            lines.append(f"| Factor ID | Labelable | Def Clear | Polarity OK | Authority | Redundant | Flags |")
            lines.append(f"|-----------|-----------|-----------|-------------|-----------|-----------|-------|")
            for ff in review.per_factor_findings:
                redundant = ", ".join(ff.redundant_with) if ff.redundant_with else "—"
                flags_str = "; ".join(ff.flags) if ff.flags else "—"
                lines.append(
                    f"| `{ff.factor_id}` "
                    f"| {'✓' if ff.labelable_from_narrative else '✗'} "
                    f"| {'✓' if ff.definition_clear else '✗'} "
                    f"| {'✓' if ff.polarity_correct else '✗'} "
                    f"| {'✓' if ff.authority_grounded else '✗'} "
                    f"| {redundant} "
                    f"| {flags_str} |"
                )
            lines.append(f"")

        # Disagreement Matrix
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## Disagreement Matrix")
        lines.append(f"")
        lines.append(f"Legend: **U** = unanimous flag, **M** = majority flag, **S** = single flag, **—** = clean")
        lines.append(f"")
        # Dynamic header with panelist columns
        header_cols = ["Factor ID", "Consensus"] + panelist_ids
        lines.append("| " + " | ".join(header_cols) + " |")
        lines.append("|" + "|".join("---" for _ in header_cols) + "|")

        for row in panel_review.disagreement_matrix:
            fid = row["factor_id"]
            level = row["consensus_level"]
            level_marker = {"unanimous": "**U**", "majority": "**M**", "single": "**S**", "clean": "—"}.get(level, level)
            panelist_cells = []
            for pid in panelist_ids:
                entry = next((bp for bp in row["by_panelist"] if bp["panelist_id"] == pid), None)
                if entry and entry["axes_flagged"]:
                    panelist_cells.append(", ".join(entry["axes_flagged"]))
                else:
                    panelist_cells.append("—")
            lines.append("| `" + fid + "` | " + level_marker + " | " + " | ".join(panelist_cells) + " |")

        lines.append(f"")

        # Unanimous flag summary
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## Unanimous-Flag Summary")
        lines.append(f"")
        if panel_review.unanimous_flags:
            lines.append(f"Factors flagged on at least one axis by **all {n} panelists**:")
            lines.append(f"")
            for entry in panel_review.unanimous_flags:
                fid = entry["factor_id"]
                axes_all = sorted({ax for bp in entry["by_panelist"] for ax in bp.get("axes_flagged", [])})
                lines.append(f"- **`{fid}`**: axes flagged — {', '.join(axes_all)}")
        else:
            lines.append(f"_No factors unanimously flagged by all panelists._")
        lines.append(f"")

        # Majority flag summary
        lines.append(f"### Majority Flags (≥2 panelists, not unanimous)")
        lines.append(f"")
        if panel_review.majority_flags:
            for entry in panel_review.majority_flags:
                fid = entry["factor_id"]
                axes_all = sorted({ax for bp in entry["by_panelist"] for ax in bp.get("axes_flagged", [])})
                lines.append(f"- **`{fid}`**: axes — {', '.join(axes_all)}")
        else:
            lines.append(f"_None._")
        lines.append(f"")

        # Single flag summary
        lines.append(f"### Single Flags (1 panelist)")
        lines.append(f"")
        if panel_review.single_flags:
            for entry in panel_review.single_flags:
                fid = entry["factor_id"]
                panelist = next(
                    (bp["panelist_id"] for bp in entry["by_panelist"] if bp.get("axes_flagged")),
                    "unknown",
                )
                axes_all = sorted({ax for bp in entry["by_panelist"] for ax in bp.get("axes_flagged", [])})
                lines.append(f"- **`{fid}`** (by `{panelist}`): {', '.join(axes_all)}")
        else:
            lines.append(f"_None._")
        lines.append(f"")

        # Cost report
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## Cost Report")
        lines.append(f"")
        cr = panel_review.cost_report
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total tokens in | {cr.get('total_tokens_in', 0):,} |")
        lines.append(f"| Total tokens out | {cr.get('total_tokens_out', 0):,} |")
        lines.append(f"| Estimated cost (USD) | ${cr.get('estimated_cost_usd', 0.0):.6f} |")
        lines.append(f"| Estimated cost (GBP) | £{cr.get('estimated_cost_gbp', 0.0):.6f} |")
        lines.append(f"")
        if cr.get("panelist_stats"):
            lines.append(f"**Per-panelist breakdown:**")
            lines.append(f"")
            lines.append(f"| Model | Provider | Tokens in | Tokens out | Cost (USD) |")
            lines.append(f"|-------|----------|-----------|------------|------------|")
            for ps in cr["panelist_stats"]:
                lines.append(
                    f"| `{ps.get('model', '?')}` "
                    f"| {ps.get('provider', '?')} "
                    f"| {ps.get('tokens_in', 0):,} "
                    f"| {ps.get('tokens_out', 0):,} "
                    f"| ${ps.get('estimated_cost_usd', 0.0):.6f} |"
                )
            lines.append(f"")
        if cr.get("note"):
            lines.append(f"_{cr['note']}_")
        lines.append(f"")

        # Reviewer prompt (§22.1 requirement: embed full prompt in artifact)
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## Reviewer Prompt")
        lines.append(f"")
        lines.append(f"```")
        lines.append(REVIEWER_PROMPT)
        lines.append(f"```")
        lines.append(f"")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Multi-provider client factory helpers
# ---------------------------------------------------------------------------

_SUPPORTED_PROVIDERS = frozenset({"anthropic", "openai"})


def _build_clients_from_providers(
    providers_csv: str,
) -> "List[BaseLLMClient] | str":
    """Parse *providers_csv* (``provider:model[,provider:model,...]``) and
    construct one :class:`BaseLLMClient` per entry.

    Returns a list of clients on success, or an error message string on failure.
    Supported providers: ``anthropic``, ``openai``.
    """
    import os

    pairs = [p.strip() for p in providers_csv.split(",") if p.strip()]
    if not pairs:
        return "Empty --panelist-providers CSV."

    clients: List[BaseLLMClient] = []
    for pair in pairs:
        if ":" not in pair:
            return (
                f"Invalid provider:model pair {pair!r}: missing colon. "
                f"Format: provider:model (e.g. anthropic:claude-opus-4-20250514)."
            )
        provider, _, model_id = pair.partition(":")
        if not model_id:
            return f"Invalid provider:model pair {pair!r}: empty model ID after colon."
        if provider not in _SUPPORTED_PROVIDERS:
            return (
                f"Unknown provider {provider!r} in {pair!r}. "
                f"Supported: {sorted(_SUPPORTED_PROVIDERS)}."
            )

        if provider == "anthropic":
            from llm_orchestrator.clients.claude_client import ClaudeClient  # noqa: PLC0415
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                return (
                    "ANTHROPIC_API_KEY is not set. "
                    "Set it in .env or the environment before using anthropic provider."
                )
            client: BaseLLMClient = ClaudeClient(api_key=api_key, model=model_id)
        else:  # openai
            from llm_orchestrator.clients.openai_client import OpenAIClient  # noqa: PLC0415
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                return (
                    "OPENAI_API_KEY is not set. "
                    "Set it in .env or the environment before using openai provider."
                )
            client = OpenAIClient(api_key=api_key, model=model_id)

        # Tag the client so Panel._call_one uses the full provider:model label
        # as the panelist_id in the system-prompt injection.
        client._panelist_label = pair  # type: ignore[attr-defined]
        clients.append(client)

    return clients


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "docs" / "eval" / "factor_catalog_reviews"


def cli_main(
    argv: Optional[Sequence[str]] = None,
    injected_clients: Optional[List[BaseLLMClient]] = None,
    repo_root: Optional[Path] = None,
) -> int:
    """CLI entry-point. Returns exit code (0 = success, non-zero = error).

    *injected_clients* bypasses factory construction for tests.
    *repo_root* overrides the default repo root path.
    """
    effective_repo_root = repo_root or _REPO_ROOT

    parser = argparse.ArgumentParser(
        description="§22.1 Factor Catalog LLM Panel Review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--domain", required=True, help="Domain ID, e.g. housing.repairs_social.v1")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Print panel info without calling LLMs")
    mode_group.add_argument("--execute", action="store_true", help="Run the panel and write the artifact")
    parser.add_argument("--output", default=None, help="Override output path")
    parser.add_argument("--panelists", type=int, default=3, help="Number of panelists (default 3)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for excerpt selection")
    parser.add_argument(
        "--corpus-path",
        default=None,
        help="Override path to corpus JSONL for excerpt selection",
    )
    parser.add_argument(
        "--panelist-providers",
        default=None,
        help=(
            "CSV of provider:model pairs for explicit multi-model panels, e.g. "
            "'anthropic:claude-opus-4-20250514,openai:gpt-4o'. "
            "When set, constructs one client per pair directly (bypassing the role-router). "
            "Overrides --panelists count with a warning if both are given. "
            "Supported providers: anthropic, openai."
        ),
    )

    args = parser.parse_args(argv)

    if not args.dry_run and not args.execute:
        print("Error: specify --dry-run or --execute", file=sys.stderr)
        return 2

    # Load domain pack
    try:
        pack = load_domain_pack(args.domain, repo_root=effective_repo_root)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Load corpus excerpts
    corpus_path = Path(args.corpus_path) if args.corpus_path else None
    excerpts = load_corpus_excerpts(
        n=5,
        seed=args.seed,
        corpus_path=corpus_path,
        max_chars=1500,
    )

    # Build output path
    today = date.today().isoformat()
    if args.output:
        out_path = Path(args.output)
    else:
        fname = f"{args.domain}-{today}-llm_panel.md"
        out_path = _DEFAULT_OUTPUT_DIR / fname

    # Build clients
    if injected_clients is not None:
        clients: List[BaseLLMClient] = list(injected_clients)
        # If fewer injected clients than requested panelists, pad with copies
        if clients and len(clients) < args.panelists:
            print(
                f"WARNING: {len(clients)} client(s) provided but {args.panelists} panelists "
                f"requested; padding by repeating the first client. "
                f"Independent opinions may be compromised.",
                file=sys.stderr,
            )
            while len(clients) < args.panelists:
                clients.append(clients[0])
        clients = clients[: args.panelists]
    elif args.panelist_providers:
        # Explicit multi-provider panel — construct one client per provider:model pair.
        result = _build_clients_from_providers(args.panelist_providers)
        if isinstance(result, str):
            # Error message returned
            print(f"Error: {result}", file=sys.stderr)
            return 1
        clients = result
        # Override --panelists with the derived count, warning if they differ.
        if args.panelists != 3 and args.panelists != len(clients):
            print(
                f"WARNING: --panelists={args.panelists} overridden by "
                f"--panelist-providers CSV length ({len(clients)}). "
                f"Using {len(clients)} panelists.",
                file=sys.stderr,
            )
    else:
        try:
            from llm_orchestrator.clients.factory import get_llm_client
            from llm_orchestrator.clients.types import LLMRole
            clients = [get_llm_client(LLMRole.PREDICTION) for _ in range(args.panelists)]
        except Exception as e:
            print(f"Error building LLM clients: {e}", file=sys.stderr)
            return 1

    panel = Panel(clients=clients)

    if args.dry_run:
        info = panel.dry_run_info(pack=pack, excerpts=excerpts)
        print("=== §22.1 Factor Catalog Panel Review — DRY RUN ===")
        print(f"Domain:         {args.domain}")
        print(f"Date:           {today}")
        print(f"Catalog SHA:    {catalog_sha(pack)}")
        print(f"Factor count:   {len(pack['factors'])}")
        print(f"Panelists:      {info['panelist_count']}")
        print(f"Model IDs:      {', '.join(info['model_ids'])}")
        print(f"Excerpt count:  {info['excerpt_count']}")
        print(f"Expected output: {out_path}")
        print(f"")
        print(f"=== System prompt preview (first 400 chars) ===")
        print(REVIEWER_PROMPT[:400])
        print("...[truncated]...")
        print(f"")
        print(f"=== User message length ===")
        print(f"{info['user_message_length']} characters")
        return 0

    # Execute mode
    try:
        reviews, cost_report = asyncio.run(
            panel.run(pack=pack, excerpts=excerpts)
        )
    except Exception as e:
        print(f"Error running panel: {e}", file=sys.stderr)
        return 1

    # Aggregate — pass cost_report directly so no frozen-rebuild needed
    agg = Aggregator(reviews)
    panel_review = agg.aggregate(cost_report=cost_report)

    # Render
    renderer = Renderer()
    renderer.write(
        panel_review=panel_review,
        pack=pack,
        output_path=out_path,
        date_str=today,
    )

    print(f"Panel review written to: {out_path}")
    print(f"Unanimous flags: {len(panel_review.unanimous_flags)}")
    print(f"Majority flags:  {len(panel_review.majority_flags)}")
    print(f"Single flags:    {len(panel_review.single_flags)}")
    return 0


# ---------------------------------------------------------------------------
# __main__
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(cli_main())
