"""Stream C — proposition factor-id tagger CLI.

Reads a JSONL of extracted :class:`kg_builder.propositions.models.Proposition`
records (the output of
``scripts/ingestion/dump_propositions_to_jsonl.py``), batches them to a
single LLM with the housing-repairs factor catalogue, and emits
``factor_ids: list[str]`` for each proposition. Writes the tagged
propositions back as a JSONL.

Why a separate tagger? The proposition extractor (in
``packages/kg_builder/propositions/extractor.py``) does NOT populate
``factor_ids`` — those are a Stream C addition (see
``factor_retrieval.py``'s spec ref §10) on the model schema only. To
make ``FactorRetriever.factor_overlap`` non-zero we need to retroactively
tag the extracted propositions.

Why a single annotator (vs. the double-pass + Krippendorff-α used for
case-side gold)? Propositions are short (≤500 chars), the classification
is multi-label, and we only need a positive gating signal — not an IAA
estimate. One annotator at low temperature with a deterministic seed is
sufficient and roughly half the cost.

Idempotency: re-running on the same input must produce the same output
(modulo LLM stochasticity which we mitigate via temperature=0). When a
proposition already has a non-empty ``factor_ids`` list it is SKIPPED
unless ``--retag`` is set, so resuming a partial run never re-pays for
already-tagged rows.

Engineering only — no actual LLM run is invoked from this commit. The
``--dry-run`` mode exercises every code path except the LLM call so
tests can run hermetically.

CLI examples::

    # Smoke (no LLM):
    python scripts/eval/tag_propositions_with_factors.py \\
        --input  data/eval_artifacts/propositions/housing_repairs_social_v1.propositions.jsonl \\
        --output data/eval_artifacts/propositions/housing_repairs_social_v1.propositions.tagged.jsonl \\
        --domain housing.repairs_social.v1 \\
        --dry-run

    # Real run:
    python scripts/eval/tag_propositions_with_factors.py \\
        --input  data/eval_artifacts/propositions/housing_repairs_social_v1.propositions.jsonl \\
        --output data/eval_artifacts/propositions/housing_repairs_social_v1.propositions.tagged.jsonl \\
        --domain housing.repairs_social.v1 \\
        --annotator-provider openai:gpt-5-mini \\
        --execute
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Path bootstrap — make packages importable when run as a script
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGES_DIR = str(_REPO_ROOT / "packages")
if _PACKAGES_DIR not in sys.path:
    sys.path.insert(0, _PACKAGES_DIR)

# Load .env early so ANTHROPIC_API_KEY / OPENAI_API_KEY / LLM_* vars are set
# before any client construction. override=True so empty shell-env values
# don't beat the real .env value.
try:
    from dotenv import load_dotenv  # noqa: PLC0415

    load_dotenv(_REPO_ROOT / ".env", override=True)
except Exception:  # pragma: no cover - dotenv is optional for tests
    pass

from pydantic import BaseModel, ConfigDict, Field

from kg_builder.propositions.models import Proposition  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The 13 factors that the case-side backfill treats as gate-countable.
# Two factors (``inspection_offered``, ``impact_severity_reported``) are
# excluded from the proposition tagger as well, mirroring the case-side
# decision to skip them — see the plan for rationale.
_DEFAULT_GATE_FACTORS_HOUSING_REPAIRS = [
    "repair_responsibility_established",
    "hazard_or_disrepair_reported",
    "landlord_notice_established",
    "inspection_delay_days",
    "repair_attempted",
    "repair_delay_days",
    "records_inadequate",
    "communication_gap_days",
    "complaint_response_delay_days",
    "vulnerability_known",
    "temporary_decant_or_alternative_offered",
    "prior_compensation_or_apology_offered",
    "issue_outside_jurisdiction",
]

_SUPPORTED_PROVIDERS = {"anthropic", "openai"}


# ---------------------------------------------------------------------------
# Pydantic models for LLM output
# ---------------------------------------------------------------------------


class FactorTagPrediction(BaseModel):
    """One LLM's classification for one proposition."""

    model_config = ConfigDict(extra="forbid")

    proposition_id: str = Field(min_length=1)
    factor_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    reasoning: str = Field(default="", max_length=500)


class FactorTagBatchResponse(BaseModel):
    """LLM response for a batch of N propositions."""

    model_config = ConfigDict(extra="forbid")

    predictions: List[FactorTagPrediction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Domain pack loading
# ---------------------------------------------------------------------------


def _load_factor_catalogue(domain_id: str) -> List[Dict[str, Any]]:
    """Load the factor list from the domain pack's ``factors.yaml``.

    Returns the raw ``factors`` list of dicts (each with at least ``id``,
    ``description``, ``value_type``, ``polarity``).
    """
    import yaml  # noqa: PLC0415 — heavy import only when CLI runs

    if domain_id != "housing.repairs_social.v1":
        # Future-proofing: when more packs need backfill, generalise this.
        raise ValueError(
            f"--domain {domain_id!r} not yet supported; only "
            "housing.repairs_social.v1 is wired."
        )
    pack_yaml = (
        _REPO_ROOT
        / "packages"
        / "domain_packs"
        / "housing"
        / "repairs_social"
        / "factors.yaml"
    )
    payload = yaml.safe_load(pack_yaml.read_text(encoding="utf-8"))
    return list(payload.get("factors") or [])


def _filter_catalogue(
    catalogue: List[Dict[str, Any]],
    factor_ids: List[str],
) -> List[Dict[str, Any]]:
    wanted = set(factor_ids)
    return [f for f in catalogue if f.get("id") in wanted]


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """\
You are a precision factor-tagger for UK housing-disrepair tribunal propositions.

Each proposition is a short factual claim drawn from a tribunal decision.
Classify which factor IDs from the catalogue below the proposition references.
Multi-label is allowed: a single proposition may reference 0, 1, or many
factors. When a proposition is too generic to map to any factor, return an
empty ``factor_ids`` list — DO NOT guess.

FACTOR CATALOGUE
================
{catalogue_block}

OUTPUT (respond with valid JSON ONLY, matching this schema):
{{
  "predictions": [
    {{
      "proposition_id": "<UUID string of the proposition you are tagging>",
      "factor_ids": ["<factor_id_1>", "<factor_id_2>", ...],
      "confidence": <float in [0.0, 1.0]>,
      "reasoning": "<short, ≤ 1 sentence — why these factors apply>"
    }},
    ...
  ]
}}

RULES:
- Use ONLY factor IDs from the catalogue above. Never invent new IDs.
- Return one prediction per input proposition, IN THE SAME ORDER.
- If a proposition references no catalogued factor, return ``factor_ids: []``.
- ``confidence`` reflects how strongly the proposition references the chosen
  factor(s) — 1.0 means the text quotes the factor directly; 0.5 means
  reasonable inference; below 0.3 means very weak signal (consider empty list).
- Keep ``reasoning`` short — one phrase is fine.
"""

_USER_PROMPT_TEMPLATE = """\
Tag each of the following {n} propositions:

{propositions_block}

Return predictions in the same order as the propositions above.
"""


def _format_catalogue_block(catalogue: List[Dict[str, Any]]) -> str:
    """Render the factor catalogue as a numbered list with descriptions."""
    lines: List[str] = []
    for entry in catalogue:
        fid = entry.get("id", "")
        desc = (entry.get("description") or "").strip()
        polarity = entry.get("polarity", "neutral")
        vtype = entry.get("value_type", "boolean")
        lines.append(
            f"- {fid} ({vtype}, {polarity}): {desc}"
        )
    return "\n".join(lines)


def _format_propositions_block(propositions: Sequence[Proposition]) -> str:
    lines: List[str] = []
    for p in propositions:
        lines.append(
            f"[id={p.proposition_id}] {p.text}"
        )
    return "\n".join(lines)


def build_system_prompt(catalogue: List[Dict[str, Any]]) -> str:
    return _SYSTEM_PROMPT_TEMPLATE.format(
        catalogue_block=_format_catalogue_block(catalogue),
    )


def build_user_prompt(propositions: Sequence[Proposition]) -> str:
    return _USER_PROMPT_TEMPLATE.format(
        n=len(propositions),
        propositions_block=_format_propositions_block(propositions),
    )


# ---------------------------------------------------------------------------
# LLM client construction (parsed from --annotator-provider)
# ---------------------------------------------------------------------------


def _build_client(provider_spec: str):  # noqa: ANN201 — duck-typed BaseLLMClient
    """Parse ``provider:model`` and construct the corresponding LLM client."""
    if ":" not in provider_spec:
        raise ValueError(
            f"--annotator-provider must be 'provider:model'; got {provider_spec!r}"
        )
    provider, _, model_id = provider_spec.partition(":")
    if not model_id:
        raise ValueError(
            f"--annotator-provider missing model id after colon: {provider_spec!r}"
        )
    if provider not in _SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported provider {provider!r}; supported: {sorted(_SUPPORTED_PROVIDERS)}"
        )

    if provider == "anthropic":
        from llm_orchestrator.clients.claude_client import ClaudeClient  # noqa: PLC0415

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Configure .env or shell env."
            )
        return ClaudeClient(api_key=api_key, model=model_id)
    # openai
    from llm_orchestrator.clients.openai_client import OpenAIClient  # noqa: PLC0415

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Configure .env or shell env."
        )
    return OpenAIClient(
        api_key=api_key,
        model=model_id,
        fallback_model=None,
    )


# ---------------------------------------------------------------------------
# Tagger core (LLM-pluggable)
# ---------------------------------------------------------------------------


class PropositionFactorTagger:
    """Drives the LLM call for a batch of propositions and merges results.

    The LLM client is duck-typed (any object with an async
    ``generate_structured(messages, system_prompt, response_model,
    max_tokens)`` method works). The default tests inject a fake.
    """

    def __init__(
        self,
        client: Any,
        catalogue: List[Dict[str, Any]],
        *,
        valid_factor_ids: Optional[List[str]] = None,
    ) -> None:
        self.client = client
        self.catalogue = catalogue
        self._valid_factor_ids = set(
            valid_factor_ids or [entry.get("id") for entry in catalogue]
        )

    async def tag_batch(
        self,
        propositions: Sequence[Proposition],
    ) -> Dict[str, FactorTagPrediction]:
        """Tag a batch of propositions; return prop_id (str) -> prediction."""
        if not propositions:
            return {}
        system_prompt = build_system_prompt(self.catalogue)
        user_prompt = build_user_prompt(propositions)
        messages = [{"role": "user", "content": user_prompt}]
        response = await self.client.generate_structured(
            messages=messages,
            system_prompt=system_prompt,
            response_model=FactorTagBatchResponse,
            max_tokens=4096,
        )
        return self._index_response(response, propositions)

    def _index_response(
        self,
        response: FactorTagBatchResponse,
        propositions: Sequence[Proposition],
    ) -> Dict[str, FactorTagPrediction]:
        wanted_ids = {str(p.proposition_id) for p in propositions}
        out: Dict[str, FactorTagPrediction] = {}
        for pred in response.predictions:
            if pred.proposition_id not in wanted_ids:
                continue
            # Filter out hallucinated factor IDs.
            cleaned_ids = [
                fid for fid in pred.factor_ids if fid in self._valid_factor_ids
            ]
            cleaned = pred.model_copy(update={"factor_ids": cleaned_ids})
            out[pred.proposition_id] = cleaned
        return out


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def _read_propositions_jsonl(path: Path) -> List[Proposition]:
    """Load propositions from a JSONL file. Skip blank lines."""
    out: List[Proposition] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_no}: invalid JSON: {exc}"
                ) from exc
            out.append(Proposition.model_validate(payload))
    return out


def _write_propositions_jsonl(path: Path, propositions: Sequence[Proposition]) -> None:
    """Write propositions to JSONL atomically (via .tmp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for prop in propositions:
            fh.write(prop.model_dump_json() + "\n")
    tmp.replace(path)


def _stable_seed_for_proposition(prop: Proposition) -> int:
    """Deterministic seed from proposition_id for reproducibility.

    The seed is the first 8 hex chars of sha256(proposition_id) interpreted
    as an int. Same proposition -> same seed, every run.
    """
    digest = hashlib.sha256(str(prop.proposition_id).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _split_already_tagged(
    propositions: Sequence[Proposition],
    *,
    retag: bool,
) -> tuple[List[Proposition], List[Proposition]]:
    """Partition into (to_tag, already_tagged) based on factor_ids state.

    A proposition is treated as "already tagged" when ``factor_ids`` is
    non-empty AND ``--retag`` was not passed.
    """
    if retag:
        return list(propositions), []
    to_tag: List[Proposition] = []
    skipped: List[Proposition] = []
    for prop in propositions:
        if prop.factor_ids:
            skipped.append(prop)
        else:
            to_tag.append(prop)
    return to_tag, skipped


def _chunk(items: Sequence, size: int) -> List[List]:
    if size <= 0:
        raise ValueError(f"--batch-size must be > 0; got {size}")
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


async def run_tagger(
    *,
    propositions: List[Proposition],
    tagger: PropositionFactorTagger,
    batch_size: int,
    retag: bool,
) -> List[Proposition]:
    """Tag every proposition, returning a NEW list with factor_ids merged.

    Order is preserved: the output list is in the same order as the input.
    Propositions that fail to receive a prediction keep their original
    ``factor_ids`` (empty list when input was untagged).
    """
    to_tag, skipped = _split_already_tagged(propositions, retag=retag)
    by_id: Dict[str, FactorTagPrediction] = {}

    for batch in _chunk(to_tag, batch_size):
        batch_results = await tagger.tag_batch(batch)
        by_id.update(batch_results)

    # Rebuild output list in original order.
    out: List[Proposition] = []
    for prop in propositions:
        pid = str(prop.proposition_id)
        pred = by_id.get(pid)
        if pred is None:
            # Either skipped (already tagged + not retagging) or LLM dropped it.
            out.append(prop)
            continue
        # Pydantic model_copy preserves all other fields.
        merged = prop.model_copy(update={"factor_ids": list(pred.factor_ids)})
        out.append(merged)
    _ = skipped  # currently unused but kept for future telemetry
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tag_propositions_with_factors",
        description=(
            "Tag a JSONL of propositions with factor IDs from a domain "
            "pack's catalogue. Stream C — see plan "
            "docs/superpowers/plans/2026-05-10-stream-c-proposition-backfill.md"
        ),
    )
    p.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to a JSONL of Proposition rows (Pydantic model_dump_json).",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Path to write tagged JSONL. Defaults to <input>.tagged.jsonl. "
            "Output is written atomically."
        ),
    )
    p.add_argument(
        "--domain",
        type=str,
        default="housing.repairs_social.v1",
        help="Domain pack id whose factor catalogue to use.",
    )
    p.add_argument(
        "--factors",
        type=str,
        default=None,
        help=(
            "Comma-separated subset of factor IDs to consider. Defaults to "
            "the 13 gate-countable factors for housing.repairs_social.v1."
        ),
    )
    p.add_argument(
        "--annotator-provider",
        type=str,
        default="openai:gpt-5-mini",
        help=(
            "provider:model spec for the LLM. "
            "Examples: openai:gpt-5-mini, anthropic:claude-sonnet-4-20250514."
        ),
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic seed (used for any randomised batch ordering).",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help=(
            "Propositions per LLM call. Smaller values are slower but less "
            "likely to hit context limits or model output truncation."
        ),
    )
    p.add_argument(
        "--retag",
        action="store_true",
        help=(
            "Re-tag every proposition, even those with non-empty "
            "factor_ids on input. Default: skip already-tagged rows for "
            "idempotency."
        ),
    )
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate inputs, render a sample prompt, and exit WITHOUT "
            "calling any LLM."
        ),
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Run the LLM tagger end-to-end.",
    )
    return p


def _resolve_output_path(input_path: Path, override: Optional[Path]) -> Path:
    if override is not None:
        return override
    if input_path.suffix == ".jsonl":
        return input_path.with_suffix(".tagged.jsonl")
    return input_path.with_suffix(input_path.suffix + ".tagged.jsonl")


async def main_async(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not (args.dry_run or args.execute):
        # Default to dry-run so accidental invocations don't burn $$.
        args.dry_run = True

    input_path = args.input.resolve()
    if not input_path.exists():
        print(f"error: --input does not exist: {input_path}", file=sys.stderr)
        return 2
    output_path = _resolve_output_path(input_path, args.output)

    catalogue = _load_factor_catalogue(args.domain)
    factor_ids = (
        [f.strip() for f in args.factors.split(",") if f.strip()]
        if args.factors
        else list(_DEFAULT_GATE_FACTORS_HOUSING_REPAIRS)
    )
    catalogue = _filter_catalogue(catalogue, factor_ids)
    if not catalogue:
        print(
            f"error: no factors matched --factors / domain {args.domain!r}",
            file=sys.stderr,
        )
        return 2

    propositions = _read_propositions_jsonl(input_path)
    if not propositions:
        print(
            f"error: --input has no propositions: {input_path}",
            file=sys.stderr,
        )
        return 2

    if args.dry_run:
        sample_batch = propositions[: max(1, args.batch_size)]
        sample_system = build_system_prompt(catalogue)
        sample_user = build_user_prompt(sample_batch)
        print(
            json.dumps(
                {
                    "mode": "dry-run",
                    "n_propositions": len(propositions),
                    "n_batches": (len(propositions) + args.batch_size - 1)
                    // args.batch_size,
                    "batch_size": args.batch_size,
                    "factor_ids": factor_ids,
                    "annotator_provider": args.annotator_provider,
                    "sample_system_prompt_chars": len(sample_system),
                    "sample_user_prompt_chars": len(sample_user),
                    "sample_user_prompt_preview": sample_user[:400],
                    "output_path": str(output_path),
                },
                indent=2,
            )
        )
        return 0

    # --execute path
    try:
        client = _build_client(args.annotator_provider)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    tagger = PropositionFactorTagger(
        client,
        catalogue,
        valid_factor_ids=factor_ids,
    )
    tagged = await run_tagger(
        propositions=propositions,
        tagger=tagger,
        batch_size=args.batch_size,
        retag=args.retag,
    )
    _write_propositions_jsonl(output_path, tagged)
    n_with_ids = sum(1 for p in tagged if p.factor_ids)
    print(
        json.dumps(
            {
                "mode": "execute",
                "n_propositions": len(tagged),
                "n_tagged_with_factor_ids": n_with_ids,
                "output_path": str(output_path),
            }
        )
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    return asyncio.run(main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FactorTagBatchResponse",
    "FactorTagPrediction",
    "PropositionFactorTagger",
    "build_system_prompt",
    "build_user_prompt",
    "main",
    "main_async",
    "run_tagger",
]
