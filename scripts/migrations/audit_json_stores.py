"""Audit JSON storage directories before migration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DIRS: tuple[str, ...] = (
    "sessions",
    "disputes",
    "predictions",
    "dispute_predictions",
    "knowledge_graphs",
    "mediations",
    "evidence_metadata",
)


def audit(data_dir: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for d in DIRS:
        sub = data_dir / d
        if not sub.exists() or not sub.is_dir():
            counts[d] = 0
        elif d == "evidence_metadata":
            counts[d] = len(list(sub.rglob("*.json")))
        else:
            counts[d] = len(list(sub.glob("*.json")))
    return {"counts": counts}


def main() -> None:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    report = audit(args.data_dir)
    out = args.out or (args.data_dir / "_migration_audit_report.json")
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
