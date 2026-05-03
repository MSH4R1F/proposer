#!/usr/bin/env python
"""Phase 11 — adjudication + real-gold append CLI.

Subcommands::

    adjudicate.py list --run-id <id> [--artifacts-root <dir>]
        Print one line per case artifact in the run.

    adjudicate.py queues --run-id <id> --case-id <id> [--audit-seed N] \\
        [--audit-fraction F]
        Print MandatoryReviewSet, DisagreementSet, and the deterministic
        audit overlay derived from the per-case artifact. Used by the
        adjudicator's notebook / CLI shell to know what to confirm.

    adjudicate.py append --run-id <id> --case-id <id> \\
        --decisions <decisions.json> --gold-corpus <name>
        Build the final GoldCase from ``decisions.json``, run the
        real-gold append gate (``assert_real_gold_appendable``), and only
        on green-light append the row to
        ``data/gold_standard/<gold_corpus>.jsonl``. Reviewer log row is
        appended to ``docs/eval/reviewer-log.md``.

The decisions file is the adjudicator's full output for one case. It
contains the merged ``GoldCase`` payload (with human-corrected values)
plus the ``LabelingProvenance`` block and the rates the CLI cannot
compute on its own (``inter_model_agreement_rate``,
``mandatory_review_flip_rate``, ``audit_flip_rate``). The CLI fills in
hashes, run-id, ``labeled_at``, and the field-provenance entries from
the run artifact.

This CLI is the only path that writes to ``data/gold_standard/``. The
labeling CLI (``scripts/eval/auto_label.py``) refuses to do so.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

# Path bootstrap mirrors annotate.py / auto_label.py.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "packages"))

from eval.auto_label.append_gate import (  # noqa: E402
    MANDATORY_REVIEW_FIELDS,
    AppendGateError,
    assert_real_gold_appendable,
)
from eval.auto_label.disagreement import (  # noqa: E402
    DisagreementRow,
    GroundingResult as DisagreementGrounding,
    build_disagreement_set,
)
from eval.auto_label.grounder import GROUNDER_VERSION  # noqa: E402
from eval.auto_label.canonicalize import CANONICALIZER_VERSION  # noqa: E402
from eval.schema import GoldCase, LabelingProvenance  # noqa: E402


_GOLD_DIR_DEFAULT = _REPO_ROOT / "data" / "gold_standard"
_REVIEWER_LOG = _REPO_ROOT / "docs" / "eval" / "reviewer-log.md"


# ---------------------------------------------------------------------------
# Artifact + queue derivation
# ---------------------------------------------------------------------------


def _artifact_path(artifacts_root: Path, run_id: str, case_id: str) -> Path:
    return artifacts_root / run_id / f"{case_id}.json"


def _load_artifact(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _artifact_grounding(artifact: dict[str, Any], side: str) -> DisagreementGrounding:
    """Reconstruct a (disagreement-shape) GroundingResult from an artifact."""
    g = artifact.get(f"grounding_{side}", {}) or {}
    return DisagreementGrounding(
        field_path=dict(g.get("field_path", {})),
        reasons=dict(g.get("reasons", {})),
        grounding_pass_rate=float(g.get("grounding_pass_rate", 0.0)),
    )


def _expected_per_issue_paths(case: Mapping[str, Any]) -> set[str]:
    """MandatoryReviewSet expansion for per-issue cells, mirroring append_gate."""
    out: set[str] = set()
    outcome = case.get("ground_truth_outcome") or {}
    for io in outcome.get("per_issue", []) or []:
        issue = io.get("issue", "?")
        out.add(f"ground_truth_outcome.per_issue[issue={issue}].winner")
        out.add(f"ground_truth_outcome.per_issue[issue={issue}].awarded_gbp")
    return out


def derive_queues(
    artifact: dict[str, Any],
    *,
    audit_seed: int,
    audit_fraction: float = 0.10,
) -> dict[str, Any]:
    """Compute the three adjudicator queues from a per-case artifact.

    Returns a dict with three keys:

    * ``mandatory_review`` — every path in
      ``MANDATORY_REVIEW_FIELDS`` plus every per-issue expansion. Always
      populated regardless of A/B agreement.
    * ``disagreements`` — output of
      ``build_disagreement_set(a, b, grounding_a, grounding_b)``,
      flattened to a list of dicts.
    * ``audit_overlay`` — deterministic random sample of *agreed*
      ``(case, field_path)`` cells (cells where neither A nor B is
      ungrounded AND neither is in the disagreement set), at
      ``audit_fraction`` proportion.
    """
    a = artifact.get("labeler_a", {}).get("partial_case", {}) or {}
    b = artifact.get("labeler_b", {}).get("partial_case", {}) or {}
    grounding_a = _artifact_grounding(artifact, "a")
    grounding_b = _artifact_grounding(artifact, "b")

    disagreements: list[DisagreementRow] = build_disagreement_set(
        a, b, grounding_a, grounding_b
    )
    disagree_paths = {row.field_path for row in disagreements}

    # MandatoryReviewSet for THIS case = baseline + per-issue expansion.
    mandatory = set(MANDATORY_REVIEW_FIELDS) | _expected_per_issue_paths(a) | _expected_per_issue_paths(b)

    # Audit overlay: cells that are GROUNDED on both sides AND not
    # already in the disagreement set. We sample by sorted path so the
    # same seed always yields the same selection.
    candidate_paths = sorted(
        p
        for p in (set(grounding_a.field_path) | set(grounding_b.field_path))
        if p not in disagree_paths
        and grounding_a.field_path.get(p, "GROUNDED") == "GROUNDED"
        and grounding_b.field_path.get(p, "GROUNDED") == "GROUNDED"
    )
    rng = random.Random(audit_seed)
    audit_count = max(1, int(round(len(candidate_paths) * audit_fraction))) if candidate_paths else 0
    audit = rng.sample(candidate_paths, audit_count) if audit_count else []

    return {
        "mandatory_review": sorted(mandatory),
        "disagreements": [
            {
                "field_path": row.field_path,
                "a_value": _to_jsonable(row.a_value),
                "b_value": _to_jsonable(row.b_value),
                "reason": row.reason,
            }
            for row in disagreements
        ],
        "audit_overlay": audit,
    }


def _to_jsonable(v: Any) -> Any:
    if hasattr(v, "model_dump"):
        return v.model_dump(mode="json")
    if isinstance(v, list):
        return [_to_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _to_jsonable(x) for k, x in v.items()}
    return v


# ---------------------------------------------------------------------------
# Decisions -> GoldCase
# ---------------------------------------------------------------------------


def build_gold_case(
    artifact: dict[str, Any],
    decisions: dict[str, Any],
    *,
    run_id: str,
    audit_seed: int,
) -> GoldCase:
    """Apply ``decisions`` on top of the artifact to produce a final GoldCase.

    ``decisions`` shape::

        {
          "case": <full GoldCase JSON, with human-confirmed values>,
          "labeling_provenance": {
            "human_adjudicator": "Mohamed",
            "labeler_models": [...],            # echoed from artifact
            "is_human_only_anchor": false,
            "anchor_set_id": null,
            "mandatory_review_completed_at": "2026-05-03T13:00:00+00:00",
            "adjudicated_fields": ["facts", ...],
            "inter_model_agreement_rate": 0.92,
            "audit_flip_rate": 0.04,
            "mandatory_review_flip_rate": 0.10,
            "field_provenance": [ {field_path, source, source_spans, reviewer_rationale}, ... ],
          },
        }
    """
    case_payload = dict(decisions["case"])
    prov_dec = dict(decisions["labeling_provenance"])

    grounding_a = _artifact_grounding(artifact, "a")
    grounding_b = _artifact_grounding(artifact, "b")
    avg_pass = (
        (grounding_a.grounding_pass_rate + grounding_b.grounding_pass_rate) / 2.0
    )

    provenance = LabelingProvenance(
        run_id=run_id,
        labeled_at=datetime.now(timezone.utc),
        labeler_models=prov_dec["labeler_models"],
        source_pdf_sha256=artifact["source_pdf_sha256"],
        ocr_text_sha256=artifact["ocr_text_sha256"],
        prompt_template_hash=artifact["prompt_template_hash"],
        gold_schema_hash=artifact.get("gold_schema_hash") or "UNSET-schema-hash",
        corpus_manifest_hash=artifact.get("corpus_manifest_hash") or "UNSET-corpus-hash",
        canonicalizer_version=artifact.get("canonicalizer_version", CANONICALIZER_VERSION),
        grounder_version=artifact.get("grounder_version", GROUNDER_VERSION),
        audit_seed=audit_seed,
        is_human_only_anchor=prov_dec.get("is_human_only_anchor", False),
        anchor_set_id=prov_dec.get("anchor_set_id"),
        mandatory_review_completed_at=prov_dec.get("mandatory_review_completed_at"),
        human_adjudicator=prov_dec.get("human_adjudicator"),
        adjudicated_fields=list(prov_dec.get("adjudicated_fields", [])),
        inter_model_agreement_rate=float(prov_dec["inter_model_agreement_rate"]),
        grounding_pass_rate=float(prov_dec.get("grounding_pass_rate", avg_pass)),
        audit_flip_rate=float(prov_dec["audit_flip_rate"]),
        mandatory_review_flip_rate=float(prov_dec["mandatory_review_flip_rate"]),
        field_provenance=list(prov_dec.get("field_provenance", [])),
    )
    case_payload["labeling_provenance"] = provenance.model_dump(mode="json")
    return GoldCase.model_validate(case_payload)


# ---------------------------------------------------------------------------
# Append + reviewer-log
# ---------------------------------------------------------------------------


def _append_jsonl(path: Path, gc: GoldCase) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(gc.model_dump_json())
        f.write("\n")


def _append_reviewer_log(path: Path, *, case_id: str, run_id: str, adjudicator: str, fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# Adjudication log\n\n")
    with path.open("a", encoding="utf-8") as f:
        f.write(
            f"- {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
            f"case={case_id} run={run_id} adjudicator={adjudicator} "
            f"fields=[{', '.join(fields)}]\n"
        )


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> int:
    artifacts_root = Path(args.artifacts_root).resolve()
    run_dir = artifacts_root / args.run_id
    if not run_dir.exists():
        print(f"No run directory at {run_dir}", file=sys.stderr)
        return 1
    for artifact_path in sorted(run_dir.glob("*.json")):
        try:
            payload = _load_artifact(artifact_path)
            print(f"{payload.get('case_id', artifact_path.stem)}\t{artifact_path}")
        except json.JSONDecodeError:
            print(f"{artifact_path.stem}\t<invalid-json>", file=sys.stderr)
    return 0


def _cmd_queues(args: argparse.Namespace) -> int:
    artifacts_root = Path(args.artifacts_root).resolve()
    artifact = _load_artifact(_artifact_path(artifacts_root, args.run_id, args.case_id))
    queues = derive_queues(
        artifact,
        audit_seed=args.audit_seed,
        audit_fraction=args.audit_fraction,
    )
    print(json.dumps(queues, indent=2, sort_keys=True))
    return 0


def _cmd_append(args: argparse.Namespace) -> int:
    artifacts_root = Path(args.artifacts_root).resolve()
    artifact_path = _artifact_path(artifacts_root, args.run_id, args.case_id)
    if not artifact_path.exists():
        print(f"No artifact at {artifact_path}", file=sys.stderr)
        return 1
    artifact = _load_artifact(artifact_path)

    decisions = json.loads(Path(args.decisions).read_text())
    try:
        gc = build_gold_case(
            artifact,
            decisions,
            run_id=args.run_id,
            audit_seed=args.audit_seed,
        )
    except Exception as exc:
        print(f"Refusing to append: build_gold_case failed: {exc}", file=sys.stderr)
        return 1

    try:
        assert_real_gold_appendable(gc, run_artifact_path=artifact_path)
    except AppendGateError as exc:
        print(f"Refusing to append: {exc}", file=sys.stderr)
        return 1

    gold_dir = Path(args.gold_dir).resolve() if args.gold_dir else _GOLD_DIR_DEFAULT
    jsonl_path = gold_dir / f"{args.gold_corpus}.jsonl"

    if not args.allow_existing_corpus and jsonl_path.exists():
        # Mirror annotate.py — check duplicate case_id in the corpus.
        for line in jsonl_path.read_text().splitlines():
            if line and json.loads(line).get("case_id") == gc.case_id:
                print(
                    f"Refusing to append: case_id {gc.case_id!r} already in {jsonl_path}",
                    file=sys.stderr,
                )
                return 1

    _append_jsonl(jsonl_path, gc)

    log_path = Path(args.reviewer_log).resolve() if args.reviewer_log else _REVIEWER_LOG
    adjudicator = decisions["labeling_provenance"].get("human_adjudicator", "<unknown>")
    fields = decisions["labeling_provenance"].get("adjudicated_fields", [])
    _append_reviewer_log(
        log_path,
        case_id=gc.case_id,
        run_id=args.run_id,
        adjudicator=adjudicator,
        fields=fields,
    )

    print(f"Appended {gc.case_id} to {jsonl_path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adjudicate.py",
        description="Adjudication + real-gold append (Phase 11).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--artifacts-root",
        default="data/eval_artifacts/labeling",
    )
    common.add_argument("--run-id", required=True)

    lst = sub.add_parser("list", parents=[common], help="List artifacts in a run")
    lst.set_defaults(_dispatch=_cmd_list)

    q = sub.add_parser("queues", parents=[common], help="Show MRS / DS / audit queues")
    q.add_argument("--case-id", required=True)
    q.add_argument("--audit-seed", type=int, default=42)
    q.add_argument("--audit-fraction", type=float, default=0.10)
    q.set_defaults(_dispatch=_cmd_queues)

    ap = sub.add_parser("append", parents=[common], help="Apply decisions and append to gold JSONL")
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--gold-corpus", default="housing_v1")
    ap.add_argument("--gold-dir", default=None)
    ap.add_argument("--reviewer-log", default=None)
    ap.add_argument("--audit-seed", type=int, default=42)
    ap.add_argument(
        "--allow-existing-corpus",
        action="store_true",
        help="Skip duplicate-case-id refusal (test convenience only).",
    )
    ap.set_defaults(_dispatch=_cmd_append)

    return parser


def _cli_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args._dispatch(args)


if __name__ == "__main__":
    raise SystemExit(_cli_main())
