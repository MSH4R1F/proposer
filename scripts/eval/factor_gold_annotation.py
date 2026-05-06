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
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# ---------------------------------------------------------------------------
# Path bootstrap — make packages importable when run as a script
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGES_DIR = str(_REPO_ROOT / "packages")
if _PACKAGES_DIR not in sys.path:
    sys.path.insert(0, _PACKAGES_DIR)

# Load .env early so ANTHROPIC_API_KEY / OPENAI_API_KEY / LLM_* vars are set
# before any client construction.  override=True so empty shell-env values
# (e.g. inherited ANTHROPIC_API_KEY="") don't beat the real .env value.
from dotenv import load_dotenv  # noqa: E402 (after path fixup)
load_dotenv(_REPO_ROOT / ".env", override=True)

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


class AnnotationValue(BaseModel):
    """Typed value carrier — mirrors the FactorValue pattern from legal_core.

    Exactly one of ``boolean``, ``enum``, ``number``, ``duration_days`` must
    be populated, OR ``is_null=True`` with all typed fields left as ``None``.

    This nested shape serialises to ``{"type": "object", ...}`` which OpenAI
    strict-mode JSON-schema accepts (flat unions of primitives do not).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    boolean: Optional[bool] = None
    enum: Optional[str] = None
    number: Optional[float] = None
    duration_days: Optional[int] = None
    is_null: bool = False  # explicit "annotator says no value applies"

    @model_validator(mode="after")
    def _exactly_one_populated_or_null(self) -> "AnnotationValue":
        populated = [
            f for f in ("boolean", "enum", "number", "duration_days")
            if getattr(self, f) is not None
        ]
        if self.is_null and populated:
            raise ValueError(
                f"is_null=True forbids populated typed fields, got {populated}"
            )
        if not self.is_null and not populated:
            raise ValueError(
                "must populate exactly one of boolean/enum/number/duration_days, "
                "or set is_null=True"
            )
        if len(populated) > 1:
            raise ValueError(
                f"at most one typed field may be populated, got {populated}"
            )
        return self


def _extract_typed_value(av: "AnnotationValue", value_type: str) -> Any:
    """Return the populated typed field from *av*, or ``None`` if ``is_null``.

    Args:
        av: The ``AnnotationValue`` instance.
        value_type: One of ``"boolean"``, ``"enum"``, ``"number"``, ``"duration"``.

    Returns:
        The concrete Python value (``bool``, ``str``, ``float``, ``int``) or
        ``None`` when ``av.is_null`` is ``True``.

    Raises:
        ValueError: if *value_type* is unrecognised.
    """
    if av.is_null:
        return None
    if value_type == "boolean":
        return av.boolean
    if value_type == "enum":
        return av.enum
    if value_type == "number":
        return av.number
    if value_type == "duration":
        return av.duration_days
    raise ValueError(f"unknown value_type: {value_type!r}")


class Annotation(BaseModel):
    """One annotator's assessment of one factor for one case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    factor_id: str
    annotator_id: str
    value: AnnotationValue  # nested typed — OpenAI strict-mode compatible
    value_type: str  # one of: boolean | enum | number | duration
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


class RunSummary(BaseModel):
    """Sidecar artifact written alongside the JSONL output.

    Persists run metadata, per-factor IAA, and cost for CI / audit trails.
    Written to ``{output_path}.summary.json``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_id: str
    n_cases: int
    factors: List[str]
    annotators: List[str]
    seed: int
    date: str
    per_factor_alpha: List[PerFactorAlpha]
    cost_report: Dict[str, Any]
    catalog_sha: Optional[str]


# ---------------------------------------------------------------------------
# Corpus loading (returns full rows with metadata + stripped text)
# ---------------------------------------------------------------------------

_DEFAULT_CORPUS_PATH = (
    _REPO_ROOT / "data" / "eval" / "housing_ombudsman_balanced_50_20260506.jsonl"
)
_RAW_BASE = _REPO_ROOT  # raw_text_path values in JSONL are repo-root-relative ("raw/...")


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
  "value": {{
    "boolean": <true|false|null — populate for value_type=boolean, else null>,
    "enum": <"none"|"minor"|"moderate"|"severe"|null — populate for value_type=enum, else null>,
    "number": <float|null — populate for value_type=number, else null>,
    "duration_days": <integer|null — populate for value_type=duration, else null>,
    "is_null": <true ONLY when the factor genuinely has no value; leave all typed fields null>
  }},
  "value_type": "{value_type}",
  "confidence": <float in [0.0, 1.0]>,
  "source_span": <"short supporting quote from narrative, or null if absent">,
  "requires_human_review": <true if ambiguous or the rubric edge-cases apply>,
  "reasoning": "<one sentence: why you chose this value>"
}}

VALUE FIELD RULES:
- Populate EXACTLY ONE of boolean/enum/number/duration_days that matches value_type.
- Set is_null=true (and leave all typed fields null) when the factor is absent/unclear.
- Example for value_type=boolean, affirmative: {{"boolean": true, "enum": null, "number": null, "duration_days": null, "is_null": false}}
- Example for value_type=boolean, absent/unclear: {{"boolean": null, "enum": null, "number": null, "duration_days": null, "is_null": true}}
- Example for value_type=enum, value "moderate": {{"boolean": null, "enum": "moderate", "number": null, "duration_days": null, "is_null": false}}

RULES:
- Annotate ONLY from the narrative text. Do not infer facts not stated.
- "Unclear" → set is_null=true for all value types.
- Never guess a duration — set is_null=true if dates are not explicit.
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
        self,
        cases: List[Dict[str, Any]],
        factor_ids: List[str],
        max_concurrency: int = 8,
        progress_every: int = 0,
    ) -> List[Annotation]:
        """Dispatch all (case × factor × annotator) triples concurrently.

        Bounded by ``max_concurrency`` to avoid hitting LLM rate limits at
        scale (900-call runs will exhaust default OpenAI TPM otherwise).

        If ``progress_every > 0``, prints "[N/total] elapsed=Xs rate=Y/min
        ETA=Zmin" to stderr after every Nth completion. ``0`` disables.

        Returns a flat list of Annotation objects, ordered deterministically:
            for case in cases:
              for factor_id in factor_ids:
                for (client, annotator_id) in zip(self.clients, self.annotator_ids):
        """
        import time as _time

        sem = asyncio.Semaphore(max_concurrency)
        # Mutable counter wrapped in a list to keep it shared across closures
        # without nonlocal gymnastics; an asyncio.Lock guards mutation.
        progress = {"done": 0, "start": _time.monotonic()}
        progress_lock = asyncio.Lock()

        # Bind these for the closure so we know the total up front
        total = len(cases) * len(factor_ids) * len(self.clients)

        async def _bounded(case, fid, client, aid):
            async with sem:
                result = await self._annotate_one(case, fid, client, aid)
            if progress_every > 0:
                async with progress_lock:
                    progress["done"] += 1
                    done = progress["done"]
                    if done % progress_every == 0 or done == total:
                        elapsed = _time.monotonic() - progress["start"]
                        rate = done / elapsed * 60 if elapsed > 0 else 0
                        eta_min = ((total - done) / rate) if rate > 0 else 0
                        print(
                            f"[{done}/{total}] elapsed={elapsed:.0f}s "
                            f"rate={rate:.1f}/min ETA={eta_min:.1f}min",
                            file=sys.stderr,
                            flush=True,
                        )
            return result

        tasks = []
        task_keys: List[Tuple[str, str, str]] = []  # (case_id, factor_id, annotator_id)

        for case in cases:
            for factor_id in factor_ids:
                for client, annotator_id in zip(self.clients, self.annotator_ids):
                    tasks.append(_bounded(case, factor_id, client, annotator_id))
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
            # 4096 covers GPT-5-class models which spend many tokens on
            # reasoning before emitting structured output; gpt-4o-class
            # only used ~150 of these.
            max_tokens=4096,
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


def _value_to_numeric(value: "AnnotationValue", factor: Dict[str, Any]) -> float:
    """Encode an ``AnnotationValue`` as a float for Krippendorff α.

    - boolean: True→1.0, False→0.0, is_null→nan
    - enum (impact_severity_reported): ordinal integers per _IMPACT_ORDINAL, is_null→nan
    - duration/number: float(duration_days or number), is_null→nan
    """
    vtype = factor.get("value_type", "boolean")
    raw = _extract_typed_value(value, vtype)

    if raw is None:
        return float("nan")

    if vtype == "boolean":
        if isinstance(raw, bool):
            return 1.0 if raw else 0.0
        if isinstance(raw, int):
            return float(raw)
        return float("nan")

    if vtype == "enum":
        if isinstance(raw, str):
            return float(_IMPACT_ORDINAL.get(raw.lower(), float("nan")))
        if isinstance(raw, int):
            return float(raw)
        return float("nan")

    # duration or other numeric
    try:
        return float(raw)
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


def write_run_summary(
    summary: "RunSummary",
    output_path: Path,
) -> Path:
    """Write *summary* as pretty-printed JSON to ``{output_path}.summary.json``.

    Returns the sidecar path so callers can log it.
    """
    sidecar = output_path.parent / (output_path.name + ".summary.json")
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    return sidecar


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
# Multi-provider annotator factory helpers
# ---------------------------------------------------------------------------

_SUPPORTED_PROVIDERS = frozenset({"anthropic", "openai"})
_REQUIRED_ANNOTATOR_COUNT = 2


def _build_annotator_clients_from_providers(
    providers_csv: str,
) -> "List[BaseLLMClient] | str":
    """Parse *providers_csv* (``provider:model,provider:model``) and construct
    exactly 2 :class:`BaseLLMClient` instances.

    Returns a list of 2 clients on success, or an error message string on
    failure.  Supported providers: ``anthropic``, ``openai``.
    """
    import os

    pairs = [p.strip() for p in providers_csv.split(",") if p.strip()]
    if len(pairs) != _REQUIRED_ANNOTATOR_COUNT:
        return (
            f"--annotator-providers must have exactly {_REQUIRED_ANNOTATOR_COUNT} "
            f"comma-separated provider:model entries, got {len(pairs)}: {providers_csv!r}."
        )

    clients: List[BaseLLMClient] = []
    for pair in pairs:
        if ":" not in pair:
            return (
                f"Invalid provider:model pair {pair!r}: missing colon. "
                f"Format: provider:model (e.g. anthropic:claude-sonnet-4-20250514)."
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

        # Tag the client so annotator_id is the full provider:model label.
        client._annotator_label = pair  # type: ignore[attr-defined]
        clients.append(client)

    return clients


def _annotator_id_from_client(client: BaseLLMClient, fallback: str) -> str:
    """Return the annotator_id to use for *client*.

    Priority: ``_annotator_label`` (set by the multi-provider factory) >
    *fallback* (the value from ``--annotators`` or the default).
    """
    return getattr(client, "_annotator_label", None) or fallback


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
        help=(
            f"Comma-separated label IDs for 2 annotators (default: {_DEFAULT_ANNOTATORS!r}). "
            "When --injected-clients is used in tests, acts as label-only override. "
            "For real-LLM execution, prefer --annotator-providers."
        ),
    )
    parser.add_argument(
        "--annotator-providers",
        default=None,
        help=(
            "CSV of exactly 2 provider:model pairs for explicit multi-model annotation, e.g. "
            "'anthropic:claude-sonnet-4-20250514,openai:gpt-4o'. "
            "Constructs clients directly (bypassing the role-router). "
            "annotator_id becomes 'provider:model'. "
            "Supported providers: anthropic, openai. "
            "Falls back to two copies of get_llm_client(LLMRole.PREDICTION) if unset."
        ),
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
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Max concurrent in-flight LLM calls (default 8). Lower for "
             "tight TPM tiers; higher to saturate throughput.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10,
        help="Print '[N/total] elapsed=Xs rate=Y/min ETA=Zmin' to stderr "
             "every N completions (default 10). 0 disables progress output.",
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
        # annotator_ids: respect --annotators as label-only override when clients are injected.
        # (Backwards compat for tests that pass injected_clients with explicit annotator_ids.)
    elif args.annotator_providers:
        # Explicit multi-provider panel — construct one client per pair, derive annotator_ids.
        result = _build_annotator_clients_from_providers(args.annotator_providers)
        if isinstance(result, str):
            print(f"Error: {result}", file=sys.stderr)
            return 1
        clients = result
        # Override annotator_ids with the provider:model labels from the CSV.
        annotator_ids = [pair.strip() for pair in args.annotator_providers.split(",") if pair.strip()]
    else:
        print(
            "WARNING: --annotator-providers not set; falling back to two copies of "
            "get_llm_client(LLMRole.PREDICTION). Both annotators will use the same model — "
            "IAA scores will be inflated and the panel will not represent diverse opinions.",
            file=sys.stderr,
        )
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
            dispatcher.annotate_all(
                cases=cases,
                factor_ids=factor_ids,
                max_concurrency=args.concurrency,
                progress_every=args.progress_every,
            )
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

    # Write sidecar summary artifact
    catalog_sha: Optional[str] = pack.get("catalog_sha")  # present if pack loader sets it
    summary = RunSummary(
        domain_id=args.domain,
        n_cases=len(cases),
        factors=factor_ids,
        annotators=annotator_ids,
        seed=args.seed,
        date=today,
        per_factor_alpha=alphas,
        cost_report=cost,
        catalog_sha=catalog_sha,
    )
    sidecar_path = write_run_summary(summary, out_path)
    print(f"Summary written to:     {sidecar_path}")

    return 0


# ---------------------------------------------------------------------------
# __main__
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(cli_main())
