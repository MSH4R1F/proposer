#!/usr/bin/env python
"""Annotation CLI for the gold-set corpus.

Subcommands:
  template               Print a starter JSON case to stdout
  validate <path>        Validate a draft case JSON against the schema
  append <path>          Validate then append the case to data/gold_standard/<corpus>.jsonl
  list                   Print one-line summaries of every case in the corpus
  show <case_id>         Pretty-print one case as JSON

See docs/eval/reviewer-guide.md for the full annotation workflow.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

# Path bootstrap so this script runs as a top-level executable.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "packages"))

from eval.dataset import load  # noqa: E402  (path bootstrap above)
from eval.schema import GoldCase  # noqa: E402


def _template() -> dict:
    """Return a starter dict with placeholders.

    Intentionally INVALID — the literal `REPLACE_ME` `source_pdf_sha256`
    fails the 64-lowercase-hex check. The reviewer must replace placeholders
    before `append` succeeds. This stops a template-pasted draft from
    polluting the corpus.
    """
    return {
        "schema_version": "v1",
        "case_id": "REPLACE_ME-2023-0000",
        "decision_date": "2023-01-01",
        "region": "london",
        "region_source": "REPLACE_ME",
        "case_size": "small",
        "disputed_amount_gbp": "0.00",
        "claim_types": ["cleaning"],
        "source_pdf_sha256": "REPLACE_ME (must be 64 lowercase hex chars)",
        "ocr_confidence": None,
        "parties": [
            {"role": "tenant", "represented": False},
            {"role": "landlord", "represented": False},
        ],
        "facts": (
            "REPLACE_ME with at least 50 characters of plain English summary "
            "of the dispute including parties, timeline, and disputed amounts."
        ),
        "evidence": [],
        "evidence_unavailable_reason": (
            "REPLACE_ME — describe why no evidence was captured "
            "(or remove this field and add evidence items)."
        ),
        "statutory_basis": [],
        "statutory_basis_unavailable_reason": (
            "REPLACE_ME — describe why no statutes were captured "
            "(or remove this field and add statute references)."
        ),
        "cited_authorities": [],
        "claimed_amounts": [
            {
                "issue": "REPLACE_ME",
                "amount_gbp": "0.00",
                "by_party": "landlord",
            },
        ],
        "ground_truth_outcome": {
            "overall_winner": "tenant",
            "total_awarded_gbp": "0.00",
            "per_issue": [
                {
                    "issue": "REPLACE_ME",
                    "winner": "tenant",
                    "awarded_gbp": "0.00",
                },
            ],
        },
        "key_reasoning_quotes": [
            {
                "text": "REPLACE_ME — verbatim quote from the decision.",
                "provenance": {"page": 1, "paragraph": 1},
            },
        ],
    }


def _resolve_base_dir(base_dir: Optional[str]) -> Path:
    return Path(base_dir) if base_dir else Path.cwd() / "data" / "gold_standard"


def _cmd_template(_args: argparse.Namespace) -> int:
    print(json.dumps(_template(), indent=2))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.path).read_text())
    try:
        GoldCase.model_validate(payload)
    except Exception as e:
        print(f"Invalid: {e}", file=sys.stderr)
        return 1
    print("Valid.")
    return 0


def _cmd_append(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.path).read_text())
    try:
        gc = GoldCase.model_validate(payload)
    except Exception as e:
        print(f"Invalid: {e}", file=sys.stderr)
        return 1

    base_dir = _resolve_base_dir(args.base_dir)
    corpus_path = base_dir / f"{args.corpus}.jsonl"

    if corpus_path.exists():
        try:
            existing = load(args.corpus, base_dir=base_dir, strict=True)
        except Exception as e:
            print(
                f"Refusing to append: existing corpus {corpus_path} is invalid: {e}",
                file=sys.stderr,
            )
            return 1
        if any(c.case_id == gc.case_id for c in existing.cases):
            print(
                f"Refusing to append: case_id {gc.case_id!r} already in {corpus_path}",
                file=sys.stderr,
            )
            return 1
    else:
        corpus_path.parent.mkdir(parents=True, exist_ok=True)

    with corpus_path.open("a") as f:
        f.write(gc.model_dump_json())
        f.write("\n")
    print(f"Appended {gc.case_id} to {corpus_path}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    base_dir = _resolve_base_dir(args.base_dir)
    result = load(args.corpus, base_dir=base_dir)
    for c in sorted(result.cases, key=lambda x: x.case_id):
        types = ",".join(t.value for t in c.claim_types)
        print(
            f"{c.case_id}\t{c.decision_date}\t{types}\t{c.region.value}"
        )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    base_dir = _resolve_base_dir(args.base_dir)
    result = load(args.corpus, base_dir=base_dir)
    for c in result.cases:
        if c.case_id == args.case_id:
            print(c.model_dump_json(indent=2))
            return 0
    print(
        f"case_id {args.case_id!r} not found in corpus {args.corpus}",
        file=sys.stderr,
    )
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="annotate.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("template", help="Print a starter JSON case to stdout")

    val = sub.add_parser("validate", help="Validate a draft case JSON")
    val.add_argument("path", type=str)

    app = sub.add_parser("append", help="Validate then append to the corpus JSONL")
    app.add_argument("path", type=str)
    app.add_argument("--corpus", default="housing_v1")
    app.add_argument("--base-dir", default=None)

    lst = sub.add_parser("list", help="List one-line summaries of corpus cases")
    lst.add_argument("--corpus", default="housing_v1")
    lst.add_argument("--base-dir", default=None)

    shw = sub.add_parser("show", help="Pretty-print one case as JSON")
    shw.add_argument("case_id")
    shw.add_argument("--corpus", default="housing_v1")
    shw.add_argument("--base-dir", default=None)

    return parser


def _cli_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    dispatch = {
        "template": _cmd_template,
        "validate": _cmd_validate,
        "append": _cmd_append,
        "list": _cmd_list,
        "show": _cmd_show,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(_cli_main())
