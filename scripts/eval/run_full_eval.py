#!/usr/bin/env python3
"""Run the full gold-set eval bundle for one prediction run.

This is a thin orchestrator around the existing eval CLIs:

* ``python -m eval.dataset audit``
* ``python -m eval.run`` for accuracy/Brier/ECE per mode
* ``python -m eval.ablate`` for the four-mode comparison report

It intentionally does not fabricate labels. The ``--gold`` input must be an
adjudicated GoldCase JSONL, not a selection manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODES = ("hybrid", "rag_only", "kg_only", "llm_only")
DEFAULT_METRICS = ("accuracy", "brier", "ece")


def _env() -> dict[str, str]:
    env = dict(os.environ)
    packages = str(REPO_ROOT / "packages")
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = packages if not current else f"{packages}{os.pathsep}{current}"
    return env


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _require_ok(proc: subprocess.CompletedProcess[str]) -> None:
    if proc.stdout.strip():
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _default_out_dir(gold: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return REPO_ROOT / "eval" / "results" / f"{gold.stem}_full_eval_{timestamp}"


def run(args: argparse.Namespace) -> None:
    gold = args.gold.expanduser()
    if not gold.is_absolute():
        gold = REPO_ROOT / gold

    predictions_dir = args.predictions_dir.expanduser()
    if not predictions_dir.is_absolute():
        predictions_dir = REPO_ROOT / predictions_dir

    out_dir = args.out_dir or _default_out_dir(gold)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]

    prediction_paths = {
        mode: predictions_dir / f"{mode}.jsonl"
        for mode in modes
    }
    missing = [str(path) for path in prediction_paths.values() if not path.exists()]
    if missing:
        raise SystemExit("missing prediction file(s): " + ", ".join(missing))

    audit_path = out_dir / "audit.json"
    metric_dir = out_dir / "metrics"
    ablation_path = out_dir / "ablation.json"

    audit_cmd = [
        sys.executable,
        "-m",
        "eval.dataset",
        "audit",
        str(gold),
        "--json",
        str(audit_path),
    ]
    if args.strict_audit:
        audit_cmd.append("--strict")
    audit_proc = _run(audit_cmd)
    _require_ok(audit_proc)

    metric_outputs: dict[str, dict[str, str]] = {}
    for mode, pred_path in prediction_paths.items():
        metric_outputs[mode] = {}
        for metric in metrics:
            out_path = metric_dir / f"{mode}_{metric}.json"
            cmd = [
                sys.executable,
                "-m",
                "eval.run",
                "--metric",
                metric,
                "--gold",
                str(gold),
                "--predictions",
                str(pred_path),
                "--out",
                str(out_path),
                "--seed",
                str(args.seed),
            ]
            if args.no_bootstrap:
                cmd.append("--no-bootstrap")
            else:
                cmd.extend(["--n-resamples", str(args.n_resamples)])
            proc = _run(cmd)
            _require_ok(proc)
            metric_outputs[mode][metric] = str(out_path)

    ablate_cmd = [
        sys.executable,
        "-m",
        "eval.ablate",
        "--gold",
        str(gold),
        "--out",
        str(ablation_path),
        "--seed",
        str(args.seed),
        "--amount-threshold-pct",
        str(args.amount_threshold_pct),
        "--min-case-count",
        str(args.min_case_count),
    ]
    if args.no_bootstrap:
        ablate_cmd.append("--no-bootstrap")
    else:
        ablate_cmd.extend(["--n-resamples", str(args.n_resamples)])
    if args.domain:
        ablate_cmd.extend(["--domain", args.domain])
    for mode, pred_path in prediction_paths.items():
        ablate_cmd.extend(["--predictions", f"{mode}={pred_path}"])

    ablate_proc = _run(ablate_cmd)
    _require_ok(ablate_proc)

    ablation = _read_json(ablation_path)
    audit = _read_json(audit_path)
    by_mode = {
        row["mode"]: {
            "accuracy": row["accuracy"]["point"],
            "accuracy_ci": [row["accuracy"]["lower_95"], row["accuracy"]["upper_95"]],
            "brier": row["brier"]["point"],
            "brier_ci": [row["brier"]["lower_95"], row["brier"]["upper_95"]],
            "ece": row["ece"]["point"],
            "amount_threshold": row["amount_threshold"]["point"],
            "n": row["accuracy"]["n"],
        }
        for row in ablation["modes"]
    }
    summary = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "gold": str(gold),
        "predictions_dir": str(predictions_dir),
        "out_dir": str(out_dir),
        "audit": audit,
        "modes": by_mode,
        "metric_outputs": metric_outputs,
        "ablation": str(ablation_path),
        "seed": args.seed,
        "n_resamples": 0 if args.no_bootstrap else args.n_resamples,
    }
    summary_path = out_dir / "summary.json"
    _write_json(summary_path, summary)

    print("\nFull eval complete")
    print(f"out_dir: {out_dir}")
    print(f"audit: {audit_path}")
    print(f"ablation: {ablation_path}")
    print(f"summary: {summary_path}")
    print("\nPoint estimates:")
    for mode, row in by_mode.items():
        print(
            f"  {mode}: "
            f"accuracy={row['accuracy']:.3f}, "
            f"brier={row['brier']:.3f}, "
            f"ece={row['ece']:.3f}, "
            f"amount@20%={row['amount_threshold']:.3f}, "
            f"n={row['n']}"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run audit, per-mode metrics, and ablation for a gold set."
    )
    parser.add_argument(
        "--gold",
        type=Path,
        default=Path("data/gold_standard/housing_repairs_social_v1.jsonl"),
    )
    parser.add_argument(
        "--predictions-dir",
        type=Path,
        default=Path("eval/predictions/housing_ombudsman_gold_pilot_20260504"),
    )
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--modes", default=",".join(DEFAULT_MODES))
    parser.add_argument("--metrics", default=",".join(DEFAULT_METRICS))
    parser.add_argument("--domain", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-resamples", type=int, default=1000)
    parser.add_argument("--no-bootstrap", action="store_true")
    parser.add_argument("--strict-audit", action="store_true")
    parser.add_argument("--min-case-count", type=int, default=10)
    parser.add_argument("--amount-threshold-pct", type=float, default=0.20)
    return parser


def main(argv: list[str] | None = None) -> int:
    run(_parser().parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
