"""One-shot migration: Housing Ombudsman v1 gold -> v2 with determination ontology.

Reads a Housing Ombudsman gold corpus (e.g. balanced-50 or stratified-50) and
its associated review packets (which carry `outcome_normalized` per case),
then emits a new gold JSONL with each row populated under the new schema:

* `determination`: from `outcome_normalized` via the canonical mapping.
* `amount_ordered_now_gbp` / `amount_previously_offered_gbp` /
  `amount_global_unapportioned_gbp`: split per the default rule in
  `docs/eval/housing-ombudsman-determination-ontology-2026-05-06.md`.
* `overall_winner_legacy`: derived deterministically from `determination`.

Cases that need human escalation (mixed determinations, internal £
inconsistencies, missing packets) are written to
`migration_review_queue.jsonl`.

Usage from the repo root:

    python -m scripts.eval.migrate_balanced50_to_determination_schema \\
        --gold-in data/gold_standard/housing_repairs_social_v1.jsonl \\
        --gold-out data/gold_standard/housing_repairs_social_v2.jsonl \\
        --review-packets data/eval_artifacts/gold_review_packets/housing-ombudsman-balanced-50-review-20260506/ \\
        --audit-out data/eval_artifacts/migration/balanced_50_2026_05_06/

Read-only on inputs.
"""
from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal
from pathlib import Path

from eval.schema import (
    Determination,
    _legacy_winner_for,
)


_OUTCOME_NORMALIZED_TO_DETERMINATION: dict[str, Determination] = {
    "maladministration": Determination.MALADMINISTRATION,
    "severe-maladministration": Determination.SEVERE_MALADMINISTRATION,
    "service-failure": Determination.SERVICE_FAILURE,
    "reasonable-redress": Determination.REASONABLE_REDRESS,
    "no-maladministration": Determination.NO_MALADMINISTRATION,
    "outside-jurisdiction": Determination.OUTSIDE_JURISDICTION,
    "resolved-with-intervention": Determination.RESOLVED_WITH_INTERVENTION,
}


_OUTCOME_NORMALIZED_RE = re.compile(
    r"^[\-\*\s]*[Oo]utcome[ _]normalized\s*[:\-]\s*[`'\"]?([a-z\-]+)[`'\"]?\s*$",
    re.MULTILINE,
)
_OUTCOME_RAW_RE = re.compile(
    r"^[\-\*\s]*[Oo]utcome[ _]raw\s*[:\-]\s*[`'\"]?(.+?)[`'\"]?\s*$",
    re.MULTILINE,
)


def map_outcome_normalized_to_determination(tag: str) -> Determination:
    """Return the canonical Determination for a manifest outcome_normalized tag.

    Raises KeyError on an unknown tag.
    """
    try:
        return _OUTCOME_NORMALIZED_TO_DETERMINATION[tag]
    except KeyError as exc:
        raise KeyError(f"unknown outcome_normalized tag {tag!r}") from exc


def split_amount_by_determination(
    determination: Determination, total_awarded_gbp: Decimal
) -> dict[str, Decimal | None]:
    """Default deterministic amount split.

    See docs/eval/housing-ombudsman-determination-ontology-2026-05-06.md §3.
    """
    if determination == Determination.OUTSIDE_JURISDICTION:
        if total_awarded_gbp != Decimal("0"):
            raise ValueError(
                f"outside_jurisdiction case has non-zero total {total_awarded_gbp}; "
                "needs human review"
            )
        return {
            "amount_ordered_now_gbp": None,
            "amount_previously_offered_gbp": None,
            "amount_global_unapportioned_gbp": None,
        }
    if determination == Determination.NO_MALADMINISTRATION:
        return {
            "amount_ordered_now_gbp": None,
            "amount_previously_offered_gbp": None,
            "amount_global_unapportioned_gbp": None,
        }
    if determination in (
        Determination.MALADMINISTRATION,
        Determination.SEVERE_MALADMINISTRATION,
        Determination.SERVICE_FAILURE,
    ):
        return {
            "amount_ordered_now_gbp": total_awarded_gbp,
            "amount_previously_offered_gbp": None,
            "amount_global_unapportioned_gbp": None,
        }
    if determination == Determination.REASONABLE_REDRESS:
        return {
            "amount_ordered_now_gbp": None,
            "amount_previously_offered_gbp": total_awarded_gbp,
            "amount_global_unapportioned_gbp": None,
        }
    if determination == Determination.RESOLVED_WITH_INTERVENTION:
        return {
            "amount_ordered_now_gbp": None,
            "amount_previously_offered_gbp": None,
            "amount_global_unapportioned_gbp": total_awarded_gbp,
        }
    raise ValueError(f"unhandled determination: {determination!r}")


def _read_review_packet_outcome_tag(packet_path: Path) -> str | None:
    if not packet_path.exists():
        return None
    text = packet_path.read_text(encoding="utf-8")
    match = _OUTCOME_NORMALIZED_RE.search(text)
    if not match:
        return None
    return match.group(1).strip().lower()


def _read_review_packet_outcome_raw(packet_path: Path) -> str:
    if not packet_path.exists():
        return ""
    text = packet_path.read_text(encoding="utf-8")
    match = _OUTCOME_RAW_RE.search(text)
    if not match:
        return ""
    return match.group(1).strip()


def _packet_path_for_case(packets_root: Path, case_id: str) -> Path | None:
    if not packets_root.exists():
        return None
    candidates = sorted(packets_root.glob(f"*-{case_id}.review.md"))
    if not candidates:
        return None
    return candidates[0]


def migrate_one_case(
    raw_row: dict, packets_root: Path
) -> tuple[dict, list[str]]:
    """Apply the migration to one gold row.

    Returns (new_row, review_flags). review_flags=[] means clean migration.
    Non-empty flags means the row should be flagged for human review even if
    written to the v2 corpus (or returned unchanged when the script could not
    derive a determination at all).
    """
    review_flags: list[str] = []
    case_id = raw_row["case_id"]
    packet = _packet_path_for_case(packets_root, case_id)
    if packet is None:
        review_flags.append("packet_not_found")
        return raw_row, review_flags

    tag = _read_review_packet_outcome_tag(packet)
    if tag is None:
        review_flags.append("outcome_normalized_not_extractable")
        return raw_row, review_flags

    try:
        determination = map_outcome_normalized_to_determination(tag)
    except KeyError:
        review_flags.append(f"unknown_outcome_normalized_tag:{tag}")
        return raw_row, review_flags

    gto = raw_row["ground_truth_outcome"]
    total = Decimal(str(gto["total_awarded_gbp"]))

    try:
        split = split_amount_by_determination(determination, total)
    except ValueError as exc:
        review_flags.append(str(exc))
        return raw_row, review_flags

    legacy_winner = _legacy_winner_for(determination)
    new_gto = dict(gto)
    new_gto["determination"] = determination.value
    new_gto["overall_winner_legacy"] = legacy_winner.value
    for k, v in split.items():
        new_gto[k] = str(v) if v is not None else None
    new_row = dict(raw_row)
    new_row["ground_truth_outcome"] = new_gto

    raw_outcome = _read_review_packet_outcome_raw(packet)
    if ";" in raw_outcome:
        review_flags.append(f"mixed_outcome_raw:{raw_outcome}")

    return new_row, review_flags


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-in", type=Path, required=True)
    parser.add_argument("--gold-out", type=Path, required=True)
    parser.add_argument("--review-packets", type=Path, required=True)
    parser.add_argument("--audit-out", type=Path, required=True)
    args = parser.parse_args()

    args.audit_out.mkdir(parents=True, exist_ok=True)
    review_queue_path = args.audit_out / "migration_review_queue.jsonl"
    audit_path = args.audit_out / "audit.json"

    in_count = 0
    out_count = 0
    flagged_count = 0
    determination_counts: dict[str, int] = {}

    args.gold_out.parent.mkdir(parents=True, exist_ok=True)
    with (
        args.gold_in.open("r", encoding="utf-8") as fin,
        args.gold_out.open("w", encoding="utf-8") as fout,
        review_queue_path.open("w", encoding="utf-8") as fqueue,
    ):
        for line in fin:
            in_count += 1
            row = json.loads(line)
            new_row, flags = migrate_one_case(row, args.review_packets)
            fout.write(json.dumps(new_row, default=str) + "\n")
            out_count += 1
            if flags:
                flagged_count += 1
                fqueue.write(
                    json.dumps({"case_id": new_row["case_id"], "flags": flags}, default=str) + "\n"
                )
            det = new_row.get("ground_truth_outcome", {}).get("determination")
            if det:
                determination_counts[det] = determination_counts.get(det, 0) + 1

    audit = {
        "input_rows": in_count,
        "output_rows": out_count,
        "flagged_for_review": flagged_count,
        "determination_counts": determination_counts,
    }
    audit_path.write_text(json.dumps(audit, indent=2))
    print(
        f"Migrated {out_count} rows; {flagged_count} flagged for review; "
        f"audit at {audit_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
