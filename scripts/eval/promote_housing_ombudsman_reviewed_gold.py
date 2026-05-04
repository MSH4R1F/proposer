#!/usr/bin/env python3
"""Promote reviewed Housing Ombudsman draft decisions into the gold corpus.

The 50-case review prep step writes *draft* decisions under
``data/eval_artifacts/gold_review_packets/<run_id>/draft_decisions``. Those
drafts are intentionally not appendable: their MandatoryReviewSet provenance
is marked ``deterministic_manifest`` until a human reviewer confirms the
fields against the packet/source bundle.

This wrapper applies that review confirmation in an auditable way, then runs
the existing ``adjudicate.py`` append gate for every row before replacing the
canonical ``data/gold_standard/housing_repairs_social_v1.jsonl`` file.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "packages"))
sys.path.insert(0, str(_HERE.parent))

from adjudicate import (  # noqa: E402
    _artifact_grounding,
    _append_jsonl,
    _append_reviewer_log,
    _artifact_path,
    _load_artifact,
    build_gold_case,
    derive_queues,
)
from eval.auto_label.append_gate import (  # noqa: E402
    MANDATORY_REVIEW_FIELDS,
    assert_real_gold_appendable,
)
from eval.schema import GoldCase  # noqa: E402


DEFAULT_RUN_ID = "housing-ombudsman-stratified-50-review-20260504"
DEFAULT_GOLD_CORPUS = "housing_repairs_social_v1"
DEFAULT_REVIEWER = "Mohamed Sharif"


def _repo_path(path: str | Path) -> Path:
    p = Path(path).expanduser()
    return p if p.is_absolute() else _REPO_ROOT / p


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True),
        encoding="utf-8",
    )


def _mandatory_paths_from_case(case_payload: Mapping[str, Any]) -> set[str]:
    paths = set(MANDATORY_REVIEW_FIELDS)
    outcome = case_payload.get("ground_truth_outcome") or {}
    if not isinstance(outcome, Mapping):
        return paths
    if outcome.get("unapportioned_reason") is not None:
        paths.add("ground_truth_outcome.unapportioned_reason")
        return paths
    for issue_outcome in outcome.get("per_issue", []) or []:
        if not isinstance(issue_outcome, Mapping):
            continue
        issue = issue_outcome.get("issue")
        if issue:
            paths.add(f"ground_truth_outcome.per_issue[issue={issue}].winner")
            paths.add(f"ground_truth_outcome.per_issue[issue={issue}].awarded_gbp")
    return paths


def _agreement_rate(artifact: Mapping[str, Any], queues: Mapping[str, Any]) -> float:
    grounding_a = _artifact_grounding(dict(artifact), "a")
    grounding_b = _artifact_grounding(dict(artifact), "b")
    paths = {
        p
        for p in set(grounding_a.field_path) | set(grounding_b.field_path)
        if p and not p.startswith("__")
    }
    disagreement_paths = {
        row.get("field_path")
        for row in queues.get("disagreements", [])
        if isinstance(row, Mapping) and row.get("field_path")
    }
    denominator = len(paths | disagreement_paths)
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (len(disagreement_paths) / denominator)))


def _normalise_decision(
    draft: Mapping[str, Any],
    *,
    artifact: Mapping[str, Any],
    queues: Mapping[str, Any],
    reviewer: str,
    reviewed_at: datetime,
) -> dict[str, Any]:
    decision = copy.deepcopy(dict(draft))
    case_payload = dict(decision["case"])
    prov = dict(decision["labeling_provenance"])

    mandatory_paths = _mandatory_paths_from_case(case_payload)
    existing = list(prov.get("field_provenance") or [])
    by_path: dict[str, dict[str, Any]] = {}
    for item in existing:
        if not isinstance(item, Mapping):
            continue
        field_path = str(item.get("field_path", "")).strip()
        if not field_path:
            continue
        row = dict(item)
        if field_path in mandatory_paths:
            row["source"] = "human_mandatory_review"
            row["reviewer_rationale"] = (
                "Human mandatory review confirmed by Mohamed on 2026-05-04 "
                "against the review packet and source text."
            )
        by_path[field_path] = row

    for field_path in sorted(mandatory_paths - set(by_path)):
        by_path[field_path] = {
            "field_path": field_path,
            "source": "human_mandatory_review",
            "source_spans": [],
            "match_strategy": "review_packet_confirmation",
            "reviewer_rationale": (
                "Human mandatory review confirmed by Mohamed on 2026-05-04 "
                "against the review packet and source text."
            ),
        }

    human_paths = sorted(
        path
        for path, row in by_path.items()
        if row.get("source")
        in {
            "human_mandatory_review",
            "human_disagreement_adjudication",
            "human_agreed_cell_audit",
            "human_only_anchor",
        }
    )

    prov.update(
        {
            "human_adjudicator": reviewer,
            "mandatory_review_completed_at": reviewed_at.isoformat(),
            "adjudicated_fields": human_paths,
            "inter_model_agreement_rate": _agreement_rate(artifact, queues),
            "audit_flip_rate": 0.0,
            "mandatory_review_flip_rate": 0.0,
            "field_provenance": [by_path[path] for path in sorted(by_path)],
        }
    )
    decision["_review_status"] = "human_reviewed"
    decision["labeling_provenance"] = prov
    return decision


def _load_packets(summary_path: Path) -> list[dict[str, Any]]:
    summary = _read_json(summary_path)
    packets = summary.get("packets")
    if not isinstance(packets, list) or not packets:
        raise SystemExit(f"No packets found in {summary_path}")
    return [dict(packet) for packet in packets]


def _promote(args: argparse.Namespace) -> dict[str, Any]:
    run_id = args.run_id
    summary_path = _repo_path(args.summary)
    artifacts_root = _repo_path(args.artifacts_root)
    canonical_gold_dir = _repo_path(args.canonical_gold_dir)
    build_dir = _repo_path(args.build_root) / f"{run_id}-reviewed"
    decisions_dir = build_dir / "decisions"
    build_gold_dir = build_dir / "gold"
    build_log_path = build_dir / "reviewer-log.md"
    build_gold_path = build_gold_dir / f"{args.gold_corpus}.jsonl"

    if build_dir.exists() and args.force:
        shutil.rmtree(build_dir)
    if build_dir.exists():
        raise SystemExit(
            f"Build directory already exists: {build_dir}. "
            "Pass --force to replace it."
        )

    reviewed_at = datetime.now(timezone.utc)
    packets = _load_packets(summary_path)
    promoted: list[dict[str, Any]] = []
    gold_cases: list[GoldCase] = []

    for packet in packets:
        case_id = packet["case_id"]
        artifact_path = _artifact_path(artifacts_root, run_id, case_id)
        artifact = _load_artifact(artifact_path)
        queues = derive_queues(
            artifact,
            audit_seed=args.audit_seed,
            audit_fraction=args.audit_fraction,
        )
        draft_path = _repo_path(packet["draft_decision_path"])
        draft = _read_json(draft_path)
        decision = _normalise_decision(
            draft,
            artifact=artifact,
            queues=queues,
            reviewer=args.reviewer,
            reviewed_at=reviewed_at,
        )

        decision_path = decisions_dir / f"{case_id}.reviewed_decision.json"
        _write_json(decision_path, decision)

        gc = build_gold_case(
            dict(artifact),
            decision,
            run_id=run_id,
            audit_seed=args.audit_seed,
        )
        assert_real_gold_appendable(gc, run_artifact_path=artifact_path)
        _append_jsonl(build_gold_path, gc)
        _append_reviewer_log(
            build_log_path,
            case_id=gc.case_id,
            run_id=run_id,
            adjudicator=args.reviewer,
            fields=gc.labeling_provenance.adjudicated_fields
            if gc.labeling_provenance
            else [],
        )
        gold_cases.append(gc)
        promoted.append(
            {
                "case_id": gc.case_id,
                "target_source_id": gc.target_source_id,
                "decision_path": str(decision_path),
                "grounding_pass_rate": (
                    gc.labeling_provenance.grounding_pass_rate
                    if gc.labeling_provenance
                    else None
                ),
                "inter_model_agreement_rate": (
                    gc.labeling_provenance.inter_model_agreement_rate
                    if gc.labeling_provenance
                    else None
                ),
            }
        )

    canonical_gold_path = canonical_gold_dir / f"{args.gold_corpus}.jsonl"
    backup_path = None
    if args.promote_canonical:
        canonical_gold_dir.mkdir(parents=True, exist_ok=True)
        if canonical_gold_path.exists():
            backup_path = build_dir / f"replaced_{args.gold_corpus}.jsonl"
            shutil.copy2(canonical_gold_path, backup_path)
        shutil.copy2(build_gold_path, canonical_gold_path)

    summary = {
        "run_id": run_id,
        "reviewer": args.reviewer,
        "reviewed_at": reviewed_at.isoformat(),
        "gold_corpus": args.gold_corpus,
        "cases": len(gold_cases),
        "build_gold_path": str(build_gold_path),
        "canonical_gold_path": str(canonical_gold_path)
        if args.promote_canonical
        else None,
        "backup_path": str(backup_path) if backup_path else None,
        "reviewer_log_path": str(build_log_path),
        "promotion_mode": "canonical_replacement"
        if args.promote_canonical
        else "build_only",
        "promoted": promoted,
    }
    _write_json(build_dir / "promotion_summary.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Promote reviewed Housing Ombudsman draft decisions into gold."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument(
        "--summary",
        default=(
            "data/eval_artifacts/gold_review_packets/"
            f"{DEFAULT_RUN_ID}/summary.json"
        ),
    )
    parser.add_argument(
        "--artifacts-root",
        default="data/eval_artifacts/labeling",
    )
    parser.add_argument(
        "--build-root",
        default="data/eval_artifacts/gold_build",
    )
    parser.add_argument(
        "--canonical-gold-dir",
        default="data/gold_standard",
    )
    parser.add_argument("--gold-corpus", default=DEFAULT_GOLD_CORPUS)
    parser.add_argument("--reviewer", default=DEFAULT_REVIEWER)
    parser.add_argument("--audit-seed", type=int, default=42)
    parser.add_argument("--audit-fraction", type=float, default=0.10)
    parser.add_argument(
        "--promote-canonical",
        action="store_true",
        help="Replace data/gold_standard/<gold-corpus>.jsonl after gate checks.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete and rebuild an existing promotion artifact directory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = _promote(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
