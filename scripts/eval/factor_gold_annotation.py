"""Factor Gold Annotation CLI — double-pass LLM annotation with Krippendorff α.

Dispatches two independent LLM annotators against N cases × all factors,
producing a JSONL annotation file and a per-factor inter-annotator-agreement
(IAA) summary computed via Krippendorff's alpha.

Usage (dry run):
    python scripts/eval/factor_gold_annotation.py \\
        --domain housing.repairs_social.v1 \\
        --dry-run

Usage (real run — gated for B11 checkpoint):
    python scripts/eval/factor_gold_annotation.py \\
        --domain housing.repairs_social.v1 \\
        --execute \\
        --n 30 \\
        --annotators claude-opus-4-7,claude-sonnet-4-6 \\
        --seed 42 \\
        --output data/eval_artifacts/gold_annotation/housing_v1_annotations.jsonl

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §19 PR 3a
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type, TypeVar

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, field_validator

# ---------------------------------------------------------------------------
# Path bootstrap — make packages importable when run as a script
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGES_DIR = str(_REPO_ROOT / "packages")
if _PACKAGES_DIR not in sys.path:
    sys.path.insert(0, _PACKAGES_DIR)

from llm_orchestrator.clients.base import BaseLLMClient  # noqa: E402

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Re-export the determination-stripping function from factor_catalog_review
# (do NOT duplicate the regex — import it)
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from factor_catalog_review import (  # noqa: E402
        load_domain_pack,
        strip_determination,
    )
except ImportError:
    import importlib.util as _ilu

    _spec = _ilu.spec_from_file_location(
        "factor_catalog_review",
        _SCRIPTS_DIR / "factor_catalog_review.py",
    )
    assert _spec and _spec.loader
    _fcr = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_fcr)  # type: ignore[union-attr]
    strip_determination = _fcr.strip_determination  # type: ignore[assignment]
    load_domain_pack = _fcr.load_domain_pack  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

# Ordered enum levels for ordinal IAA encoding
_IMPACT_ORDINAL: Dict[str, int] = {"none": 0, "minor": 1, "moderate": 2, "severe": 3}


class Annotation(BaseModel):
    """One annotator's assessment of one factor for one case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    factor_id: str
    annotator_id: str
    value: Any  # bool | str | int | float | None — typed by factor's value_type
    value_type: str  # mirrored for serialisation
    confidence: float
    source_span: Optional[str]
    requires_human_review: bool
    reasoning: str

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v


class PerFactorAlpha(BaseModel):
    """IAA summary row for one factor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    factor_id: str
    alpha: Optional[float]  # None when skipped
    n_pairs: int
    level_of_measurement: str
    note: str


# ---------------------------------------------------------------------------
# Corpus loading (returns full rows with metadata + stripped text)
# ---------------------------------------------------------------------------

_DEFAULT_CORPUS_PATH = (
    _REPO_ROOT / "data" / "eval" / "housing_ombudsman_balanced_50_20260506.jsonl"
)
_RAW_BASE = _REPO_ROOT / "data"


def load_cases(
    n: int,
    seed: int,
    corpus_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Load *n* cases deterministically from the corpus JSONL.

    Returns a list of dicts, each with at least:
        ``case_id``       — unique identifier
        ``narrative``     — stripped narrative text (determination removed)
        ``raw_meta``      — the original JSONL row

    Falls back to a metadata-derived stub when raw text is missing.
    """
    path = corpus_path or _DEFAULT_CORPUS_PATH
    if not path.exists():
        raise FileNotFoundError(f"Corpus JSONL not found: {path}")

    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if len(rows) < n:
        raise ValueError(
            f"Corpus has only {len(rows)} rows but --n={n} was requested."
        )

    selected = random.Random(seed).sample(rows, n)

    cases: List[Dict[str, Any]] = []
    for row in selected:
        raw_rel = row.get("raw_text_path", "")
        raw_abs = _RAW_BASE / raw_rel if raw_rel else None
        if raw_abs and raw_abs.exists():
            full_text = raw_abs.read_text(encoding="utf-8", errors="replace")
        else:
            # Stub from metadata — avoids crashing in dev where corpus isn't fetched
            full_text = (
                f"Case: {row.get('title', row.get('case_id', 'unknown'))}\n"
                f"Outcome: {row.get('outcome_raw', 'unknown')}\n"
                f"Matter types: {', '.join(row.get('matter_types', []))}\n"
                f"Landlord: {row.get('landlord_name', 'unknown')}\n"
            )
        narrative = strip_determination(full_text)
        cases.append(
            {
                "case_id": row["case_id"],
                "narrative": narrative,
                "raw_meta": row,
            }
        )

    return cases


# ---------------------------------------------------------------------------
# Rubric section extractor — pulls the per-factor block from the rubric
# ---------------------------------------------------------------------------

def extract_rubric_section(rubric: str, factor_id: str) -> str:
    """Return the rubric section for *factor_id* (the H2 block), or empty str.

    The rubric uses `## <factor_id>` headings (exact match, case-insensitive).
    The section runs from that heading up to (but not including) the next
    H2 heading or end of document.
    """
    pattern = re.compile(
        r"^##\s+" + re.escape(factor_id) + r"\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern.search(rubric)
    if m is None:
        return ""

    section_start = m.start()
    # Find the next H2 heading after this one
    next_h2 = re.search(r"^##\s+\w", rubric[m.end():], re.MULTILINE)
    if next_h2:
        section_end = m.end() + next_h2.start()
        return rubric[section_start:section_end].strip()
    return rubric[section_start:].strip()


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """\
You are a precision annotation tool for UK Housing Ombudsman case narratives.

Your task: examine the provided case narrative and determine the presence/value
of a single legal factor according to the authoritative rubric below.

ANNOTATION RUBRIC FOR THIS FACTOR
==================================
{rubric_section}

FACTOR SPECIFICATION
====================
Factor ID    : {factor_id}
Value type   : {value_type}
{enum_hint}

OUTPUT SCHEMA (respond ONLY with valid JSON matching this schema exactly):
{{
  "case_id": "<the case_id you receive in the user message>",
  "factor_id": "{factor_id}",
  "annotator_id": "<your model identifier>",
  "value": <annotated value — type matches value_type; null if unclear>,
  "value_type": "{value_type}",
  "confidence": <float in [0.0, 1.0]>,
  "source_span": <"short supporting quote from narrative, or null if absent">,
  "requires_human_review": <true if ambiguous or the rubric edge-cases apply>,
  "reasoning": "<one sentence: why you chose this value>"
}}

RULES:
- Annotate ONLY from the narrative text. Do not infer facts not stated.
- "Unclear" defaults to null for boolean and numeric factors.
- Never guess a duration — set null if dates are not explicit.
- source_span must be ≤ 60 words verbatim from the narrative, or null.
- Your annotator_id field MUST be exactly: {annotator_id}
"""

_USER_PROMPT_TEMPLATE = """\
CASE ID: {case_id}

NARRATIVE (determination section has been removed):
---
{narrative}
---

Annotate factor `{factor_id}` for the case above.
"""


def build_system_prompt(
    factor: Dict[str, Any],
    rubric_section: str,
    annotator_id: str,
) -> str:
    """Build the system prompt for one (factor, annotator) pair."""
    enum_hint = ""
    if factor.get("value_type") == "enum":
        vals = factor.get("enum_values", [])
        enum_hint = f"Allowed enum values: {vals}\n"

    return _SYSTEM_PROMPT_TEMPLATE.format(
        rubric_section=rubric_section,
        factor_id=factor["id"],
        value_type=factor.get("value_type", "boolean"),
        enum_hint=enum_hint,
        annotator_id=annotator_id,
    )


def build_user_prompt(case_id: str, narrative: str, factor_id: str) -> str:
    """Build the user prompt for one (case, factor) pair."""
    return _USER_PROMPT_TEMPLATE.format(
        case_id=case_id,
        narrative=narrative,
        factor_id=factor_id,
    )


# ---------------------------------------------------------------------------
# Annotator dispatch
# ---------------------------------------------------------------------------


class AnnotationDispatcher:
    """Dispatches annotation tasks to two LLM clients in parallel."""

    def __init__(
        self,
        clients: List[BaseLLMClient],
        pack: Dict[str, Any],
        annotator_ids: List[str],
    ) -> None:
        if len(clients) != 2 or len(annotator_ids) != 2:
            raise ValueError("AnnotationDispatcher requires exactly 2 clients and 2 annotator_ids.")
        self.clients = clients
        self.pack = pack
        self.annotator_ids = annotator_ids

        # Pre-build factor lookup and rubric sections
        self._factors: Dict[str, Dict[str, Any]] = {
            f["id"]: f for f in pack["factors"]
        }
        rubric: str = pack.get("rubric", "")
        self._rubric_sections: Dict[str, str] = {
            fid: extract_rubric_section(rubric, fid)
            for fid in self._factors
        }

    async def annotate_all(
        self, cases: List[Dict[str, Any]], factor_ids: List[str]
    ) -> List[Annotation]:
        """Dispatch all (case × factor × annotator) triples concurrently.

        Returns a flat list of Annotation objects, ordered deterministically:
            for case in cases:
              for factor_id in factor_ids:
                for (client, annotator_id) in zip(self.clients, self.annotator_ids):
        """
        tasks = []
        task_keys: List[Tuple[str, str, str]] = []  # (case_id, factor_id, annotator_id)

        for case in cases:
            for factor_id in factor_ids:
                for client, annotator_id in zip(self.clients, self.annotator_ids):
                    tasks.append(
                        self._annotate_one(case, factor_id, client, annotator_id)
                    )
                    task_keys.append((case["case_id"], factor_id, annotator_id))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        annotations: List[Annotation] = []
        for key, result in zip(task_keys, results):
            if isinstance(result, BaseException):
                raise RuntimeError(
                    f"Annotator failed for case={key[0]}, factor={key[1]}, "
                    f"annotator={key[2]}: {result}"
                ) from result
            annotations.append(result)  # type: ignore[arg-type]

        return annotations

    async def _annotate_one(
        self,
        case: Dict[str, Any],
        factor_id: str,
        client: BaseLLMClient,
        annotator_id: str,
    ) -> Annotation:
        factor = self._factors[factor_id]
        rubric_section = self._rubric_sections.get(factor_id, "")

        system_prompt = build_system_prompt(factor, rubric_section, annotator_id)
        user_prompt = build_user_prompt(case["case_id"], case["narrative"], factor_id)
        messages = [{"role": "user", "content": user_prompt}]

        return await client.generate_structured(
            messages=messages,
            system_prompt=system_prompt,
            response_model=Annotation,
            max_tokens=1024,
        )

    def dry_run_info(
        self, cases: List[Dict[str, Any]], factor_ids: List[str]
    ) -> Dict[str, Any]:
        """Return a preview dict without calling any LLM."""
        sample_case = cases[0] if cases else {"case_id": "(none)", "narrative": ""}
        sample_factor_id = factor_ids[0] if factor_ids else "(none)"
        sample_factor = self._factors.get(sample_factor_id, {"id": sample_factor_id, "value_type": "boolean"})
        sample_rubric = self._rubric_sections.get(sample_factor_id, "")
        sample_system = build_system_prompt(sample_factor, sample_rubric, self.annotator_ids[0])
        sample_user = build_user_prompt(
            sample_case["case_id"], sample_case["narrative"][:200], sample_factor_id
        )

        return {
            "n_cases": len(cases),
            "n_factors": len(factor_ids),
            "n_annotators": len(self.clients),
            "total_calls": len(cases) * len(factor_ids) * len(self.clients),
            "annotator_ids": self.annotator_ids,
            "sample_system_prompt_length": len(sample_system),
            "sample_user_prompt_length": len(sample_user),
            "sample_system_prompt_preview": sample_system[:400],
        }


# ---------------------------------------------------------------------------
# Krippendorff α computation
# ---------------------------------------------------------------------------

_LEVEL_OF_MEASUREMENT: Dict[str, str] = {
    "boolean": "nominal",
    "enum": "ordinal",
    "duration": "interval",
}


def _value_to_numeric(value: Any, factor: Dict[str, Any]) -> float:
    """Encode an annotation value as a float for krippendorff.

    - boolean: True→1.0, False→0.0, None→nan
    - enum (impact_severity_reported): ordinal integers per _IMPACT_ORDINAL, None→nan
    - duration/numeric: float(value), None→nan
    """
    if value is None:
        return float("nan")

    vtype = factor.get("value_type", "boolean")

    if vtype == "boolean":
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, int):
            return float(value)
        return float("nan")

    if vtype == "enum":
        if isinstance(value, str):
            return float(_IMPACT_ORDINAL.get(value.lower(), float("nan")))
        if isinstance(value, int):
            return float(value)
        return float("nan")

    # duration or other numeric
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def compute_krippendorff_alpha(
    annotations: List[Annotation],
    factor: Dict[str, Any],
) -> PerFactorAlpha:
    """Compute Krippendorff α for a single factor across all cases.

    Assumes exactly 2 annotators.  The 2D reliability_data array is
    shape [2, n_cases].
    """
    import krippendorff  # local import to keep module importable w/o the dep in tests

    factor_id = factor["id"]
    vtype = factor.get("value_type", "boolean")
    level = _LEVEL_OF_MEASUREMENT.get(vtype, "nominal")

    # Filter to this factor's annotations only
    factor_annotations = [a for a in annotations if a.factor_id == factor_id]

    # Split by annotator (preserve insertion order → same as dispatch order)
    annotator_ids_seen: List[str] = []
    by_annotator: Dict[str, List[Annotation]] = {}
    for ann in factor_annotations:
        if ann.annotator_id not in by_annotator:
            annotator_ids_seen.append(ann.annotator_id)
            by_annotator[ann.annotator_id] = []
        by_annotator[ann.annotator_id].append(ann)

    if len(annotator_ids_seen) < 2:
        return PerFactorAlpha(
            factor_id=factor_id,
            alpha=None,
            n_pairs=0,
            level_of_measurement=level,
            note="insufficient annotator data (< 2 annotators)",
        )

    ann_a = by_annotator[annotator_ids_seen[0]]
    ann_b = by_annotator[annotator_ids_seen[1]]
    n_pairs = min(len(ann_a), len(ann_b))

    # Check: all flagged for human review → skip
    all_flagged = all(a.requires_human_review for a in ann_a[:n_pairs]) and all(
        a.requires_human_review for a in ann_b[:n_pairs]
    )
    if all_flagged:
        return PerFactorAlpha(
            factor_id=factor_id,
            alpha=None,
            n_pairs=n_pairs,
            level_of_measurement=level,
            note="alpha=N/A, all flagged for human review",
        )

    row_a = np.array([_value_to_numeric(a.value, factor) for a in ann_a[:n_pairs]])
    row_b = np.array([_value_to_numeric(a.value, factor) for a in ann_b[:n_pairs]])

    reliability_data = np.array([row_a, row_b])

    # Count non-nan pairs
    valid_mask = ~(np.isnan(row_a) | np.isnan(row_b))
    n_valid = int(valid_mask.sum())

    if n_valid < 2:
        return PerFactorAlpha(
            factor_id=factor_id,
            alpha=None,
            n_pairs=n_pairs,
            level_of_measurement=level,
            note="insufficient non-null annotation pairs (< 2)",
        )

    # Check that there are at least 2 distinct values (krippendorff requirement)
    all_values = reliability_data[~np.isnan(reliability_data)]
    if len(set(all_values.tolist())) < 2:
        return PerFactorAlpha(
            factor_id=factor_id,
            alpha=None,
            n_pairs=n_pairs,
            level_of_measurement=level,
            note="all annotations have identical value — alpha undefined (trivial agreement)",
        )

    try:
        alpha_val = float(
            krippendorff.alpha(
                reliability_data=reliability_data,
                level_of_measurement=level,
            )
        )
    except Exception as exc:
        return PerFactorAlpha(
            factor_id=factor_id,
            alpha=None,
            n_pairs=n_pairs,
            level_of_measurement=level,
            note=f"krippendorff computation error: {exc}",
        )

    return PerFactorAlpha(
        factor_id=factor_id,
        alpha=round(alpha_val, 4),
        n_pairs=n_pairs,
        level_of_measurement=level,
        note="",
    )


# ---------------------------------------------------------------------------
# JSONL writer
# ---------------------------------------------------------------------------


def write_annotations_jsonl(annotations: List[Annotation], output_path: Path) -> None:
    """Write annotations to *output_path* as JSONL, one row per annotation."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for ann in annotations:
            fh.write(ann.model_dump_json() + "\n")


# ---------------------------------------------------------------------------
# Cost report
# ---------------------------------------------------------------------------


def _build_cost_report(
    clients: List[BaseLLMClient],
    annotator_ids: List[str],
) -> Dict[str, Any]:
    total_in = 0
    total_out = 0
    total_usd = 0.0
    per_annotator = []
    for client, ann_id in zip(clients, annotator_ids):
        stats = client.get_stats()
        t_in = stats.get("tokens_in", 0)
        t_out = stats.get("tokens_out", 0)
        usd = stats.get("estimated_cost_usd") or 0.0
        total_in += t_in
        total_out += t_out
        total_usd += usd
        per_annotator.append(
            {
                "annotator_id": ann_id,
                "model": stats.get("model", "unknown"),
                "provider": stats.get("provider", "unknown"),
                "tokens_in": t_in,
                "tokens_out": t_out,
                "estimated_cost_usd": usd,
            }
        )
    gbp = total_usd * 0.80
    return {
        "total_tokens_in": total_in,
        "total_tokens_out": total_out,
        "estimated_cost_usd": round(total_usd, 6),
        "estimated_cost_gbp": round(gbp, 6),
        "per_annotator": per_annotator,
        "note": "Estimated costs approximate; exchange rate fixed 0.80 USD/GBP.",
    }


# ---------------------------------------------------------------------------
# IAA summary printer
# ---------------------------------------------------------------------------

_ALPHA_COL_WIDTH = 8
_FACTOR_COL_WIDTH = 42
_LEVEL_COL_WIDTH = 10


def print_alpha_summary(alphas: List[PerFactorAlpha]) -> None:
    header = (
        f"{'Factor':<{_FACTOR_COL_WIDTH}}"
        f"{'Alpha':>{_ALPHA_COL_WIDTH}}"
        f"  {'Level':<{_LEVEL_COL_WIDTH}}"
        f"  {'N pairs':>7}"
        f"  Note"
    )
    sep = "-" * (len(header) + 10)
    print()
    print("=== Krippendorff α per-factor IAA summary ===")
    print(sep)
    print(header)
    print(sep)
    for pfa in alphas:
        alpha_str = f"{pfa.alpha:.4f}" if pfa.alpha is not None else "   N/A"
        note_str = pfa.note if pfa.note else ""
        print(
            f"{pfa.factor_id:<{_FACTOR_COL_WIDTH}}"
            f"{alpha_str:>{_ALPHA_COL_WIDTH}}"
            f"  {pfa.level_of_measurement:<{_LEVEL_COL_WIDTH}}"
            f"  {pfa.n_pairs:>7}"
            f"  {note_str}"
        )
    print(sep)
    valid_alphas = [pfa.alpha for pfa in alphas if pfa.alpha is not None]
    if valid_alphas:
        print(f"Mean α (computed factors): {sum(valid_alphas) / len(valid_alphas):.4f}")
    print()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "data" / "eval_artifacts" / "gold_annotation"
_DEFAULT_ANNOTATORS = "claude-opus-4-7,claude-sonnet-4-6"


def cli_main(
    argv: Optional[Sequence[str]] = None,
    injected_clients: Optional[List[BaseLLMClient]] = None,
    repo_root: Optional[Path] = None,
) -> int:
    """CLI entry-point.  Returns exit code (0 = success, non-zero = error).

    *injected_clients* bypasses factory construction for tests.
    *repo_root* overrides the default repo root path.
    """
    effective_repo_root = repo_root or _REPO_ROOT

    parser = argparse.ArgumentParser(
        description="Factor Gold Annotation CLI — double-pass annotation with Krippendorff α",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--domain",
        required=True,
        help="Domain ID, e.g. housing.repairs_social.v1",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without LLM calls",
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        help="Run annotation and write JSONL artifact",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=30,
        help="Number of cases to annotate (default 30)",
    )
    parser.add_argument(
        "--factors",
        default=None,
        help="Comma-separated factor IDs to annotate (default: all)",
    )
    parser.add_argument(
        "--corpus-path",
        default=None,
        help="Override path to corpus JSONL",
    )
    parser.add_argument(
        "--annotators",
        default=_DEFAULT_ANNOTATORS,
        help=f"Comma-separated model IDs for 2 annotators (default: {_DEFAULT_ANNOTATORS!r})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for case selection (default 42)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSONL path",
    )

    args = parser.parse_args(argv)

    if not args.dry_run and not args.execute:
        print("Error: specify --dry-run or --execute", file=sys.stderr)
        return 2

    # Parse annotator IDs
    annotator_ids = [s.strip() for s in args.annotators.split(",")]
    if len(annotator_ids) != 2:
        print(
            f"Error: --annotators must have exactly 2 comma-separated model IDs, "
            f"got: {args.annotators!r}",
            file=sys.stderr,
        )
        return 1

    # Load domain pack
    try:
        pack = load_domain_pack(args.domain, repo_root=effective_repo_root)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Resolve factor IDs
    all_factor_ids = [f["id"] for f in pack["factors"]]
    if args.factors:
        requested = [s.strip() for s in args.factors.split(",")]
        unknown = [fid for fid in requested if fid not in all_factor_ids]
        if unknown:
            print(
                f"Error: unknown factor IDs: {unknown}. "
                f"Valid IDs: {all_factor_ids}",
                file=sys.stderr,
            )
            return 1
        factor_ids = requested
    else:
        factor_ids = all_factor_ids

    # Load cases
    corpus_path = Path(args.corpus_path) if args.corpus_path else None
    try:
        cases = load_cases(n=args.n, seed=args.seed, corpus_path=corpus_path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Build output path
    today = date.today().isoformat()
    if args.output:
        out_path = Path(args.output)
    else:
        fname = f"{args.domain}-gold-annotations-n{args.n}-seed{args.seed}-{today}.jsonl"
        out_path = _DEFAULT_OUTPUT_DIR / fname

    # Build clients
    if injected_clients is not None:
        clients: List[BaseLLMClient] = list(injected_clients)
        if len(clients) != 2:
            print(
                f"Error: exactly 2 injected clients required, got {len(clients)}",
                file=sys.stderr,
            )
            return 1
    else:
        try:
            from llm_orchestrator.clients.factory import get_llm_client  # noqa: PLC0415
            from llm_orchestrator.clients.types import LLMRole  # noqa: PLC0415

            clients = [get_llm_client(LLMRole.PREDICTION) for _ in range(2)]
        except Exception as exc:
            print(f"Error building LLM clients: {exc}", file=sys.stderr)
            return 1

    dispatcher = AnnotationDispatcher(
        clients=clients,
        pack=pack,
        annotator_ids=annotator_ids,
    )

    if args.dry_run:
        info = dispatcher.dry_run_info(cases=cases, factor_ids=factor_ids)
        print("=== Factor Gold Annotation CLI — DRY RUN ===")
        print(f"Domain:          {args.domain}")
        print(f"Date:            {today}")
        print(f"Cases (N):       {info['n_cases']}")
        print(f"Factors:         {info['n_factors']}")
        print(f"Annotators:      {', '.join(info['annotator_ids'])}")
        print(f"Total LLM calls: {info['total_calls']}")
        print(f"Output path:     {out_path}")
        print()
        print(f"=== Sample system prompt preview (first 400 chars) ===")
        print(info["sample_system_prompt_preview"])
        print("...[truncated]...")
        return 0

    # Execute mode
    try:
        annotations = asyncio.run(
            dispatcher.annotate_all(cases=cases, factor_ids=factor_ids)
        )
    except RuntimeError as exc:
        print(f"Error during annotation: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error during annotation: {exc}", file=sys.stderr)
        return 1

    # Write JSONL
    write_annotations_jsonl(annotations, out_path)
    print(f"Annotations written to: {out_path}")
    print(f"Total annotations: {len(annotations)}")

    # Compute Krippendorff α per factor
    factors_by_id = {f["id"]: f for f in pack["factors"]}
    alphas: List[PerFactorAlpha] = []
    for fid in factor_ids:
        factor = factors_by_id[fid]
        pfa = compute_krippendorff_alpha(annotations, factor)
        alphas.append(pfa)

    print_alpha_summary(alphas)

    # Cost report
    cost = _build_cost_report(clients, annotator_ids)
    print("=== Cost Report ===")
    print(f"  Total tokens in:      {cost['total_tokens_in']:,}")
    print(f"  Total tokens out:     {cost['total_tokens_out']:,}")
    print(f"  Estimated cost (USD): ${cost['estimated_cost_usd']:.6f}")
    print(f"  Estimated cost (GBP): £{cost['estimated_cost_gbp']:.6f}")
    for pa in cost["per_annotator"]:
        print(
            f"    [{pa['annotator_id']}] tokens_in={pa['tokens_in']} "
            f"tokens_out={pa['tokens_out']} "
            f"cost_usd=${pa['estimated_cost_usd']:.6f}"
        )

    return 0


# ---------------------------------------------------------------------------
# __main__
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(cli_main())
