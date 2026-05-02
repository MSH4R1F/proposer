#!/usr/bin/env python3
"""SHA-20 Phase 7 — build a domain gate artifact.

Reads a domain spec, resolves all the contributing hashes (domain spec,
prompt pack, ontology, citation verifier), runs the eval (or accepts a
pre-computed metrics dict for now), and writes
``data/eval_artifacts/domain_gates/{domain_id}.json``.

Signing is intentionally NOT performed by default. The ``--sign``
flag is reserved for Phase 8.5 Ed25519 wiring; today it raises.

Example:

    PYTHONPATH=packages python scripts/eval/build_domain_gate.py \\
        --domain housing.deposit.v1 \\
        --stage production \\
        --metrics-json /tmp/metrics.json \\
        --reviewer-roles housing_legal,product_safety \\
        --approved-by reviewer1@example.com \\
        --out data/eval_artifacts/domain_gates/housing.deposit.v1.json

A successful build does NOT imply the gate verifies; run

    PYTHONPATH=packages python -m eval.gates verify --domain housing.deposit.v1 --stage production

afterwards to actually check thresholds + freshness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Allow running the script directly: prepend packages/ to sys.path.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "packages"))

from eval.gates import build_artifact  # noqa: E402


def _git_sha(default: str = "0" * 40) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(_REPO_ROOT),
        )
        return out.stdout.strip().lower()
    except Exception:
        return default


def _resolve_hashes(domain_id: str) -> dict:
    """Look up hashes for the domain spec, prompt pack, ontology, and
    verifier. Failures are logged but don't abort — gates can be built
    with partial hashes during scaffolding (the verifier will then refuse
    to pass, which is the correct fail-closed posture)."""
    out = {
        "domain_spec_hash": "",
        "prompt_pack_hash": "",
        "ontology_hash": "",
        "verifier_hash": "",
    }

    try:
        from domain_core.hashing import hash_domain_spec
        from domain_core.registry import get_domain_spec

        spec = get_domain_spec(domain_id)
        out["domain_spec_hash"] = hash_domain_spec(spec)
    except Exception as e:
        print(f"warn: domain_spec_hash unavailable: {e}", file=sys.stderr)

    try:
        from llm_orchestrator.prompts.packs import (
            get_prompt_pack,
            hash_prompt_pack,
        )

        pack = get_prompt_pack(domain_id)
        out["prompt_pack_hash"] = hash_prompt_pack(pack)
    except Exception as e:
        print(f"warn: prompt_pack_hash unavailable: {e}", file=sys.stderr)

    try:
        from kg_builder.ontology.registry import (
            get_ontology,
            hash_ontology_spec,
        )

        ont = get_ontology(domain_id)
        out["ontology_hash"] = hash_ontology_spec(ont)
    except Exception as e:
        print(f"warn: ontology_hash unavailable: {e}", file=sys.stderr)

    try:
        import llm_orchestrator.pipeline.citation_verifier as cv_mod

        out["verifier_hash"] = hashlib.sha256(
            Path(cv_mod.__file__).read_bytes()
        ).hexdigest()
    except Exception as e:
        print(f"warn: verifier_hash unavailable: {e}", file=sys.stderr)

    return out


def _resolve_corpus_version(domain_id: str) -> str:
    try:
        from domain_core.registry import get_domain_spec

        spec = get_domain_spec(domain_id)
        if spec.retrieval_namespaces:
            return spec.retrieval_namespaces[0].corpus_version or "unknown"
    except Exception:
        pass
    return "unknown"


def _resolve_gold_set(domain_id: str) -> tuple[str, int]:
    """Return ``(gold_set_path, n_cases)`` from the domain spec.

    For audit D2 fail-closed: when the gold file is missing on disk we
    still record the path but ``n_cases=0`` so the verifier refuses.
    """
    from domain_core.registry import get_domain_spec
    from eval.dataset import load

    spec = get_domain_spec(domain_id)
    path = spec.eval_gate.gold_set_path
    p = Path(path)
    if not p.exists():
        return path, 0
    try:
        result = load(p.stem, base_dir=p.parent, strict=False)
        return path, len(result.cases)
    except Exception:
        return path, 0


def _cli_main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts/eval/build_domain_gate.py")
    parser.add_argument("--domain", required=True)
    parser.add_argument(
        "--stage", required=True, choices=("production", "beta", "research")
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--metrics-json",
        type=Path,
        default=None,
        help="Path to a JSON dict of metric_name -> float. Required for non-research stages.",
    )
    parser.add_argument(
        "--reviewer-roles",
        default="",
        help="Comma-separated role list (e.g. housing_legal,product_safety).",
    )
    parser.add_argument(
        "--approved-by",
        default="",
        help="Comma-separated reviewer ids/emails.",
    )
    parser.add_argument(
        "--notes",
        default=None,
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="Cryptographically sign the artifact (Phase 8.5; raises today).",
    )
    parser.add_argument(
        "--signing-key",
        type=Path,
        default=None,
        help="Path to Ed25519 private key (Phase 8.5).",
    )

    args = parser.parse_args(argv)

    if args.sign:
        raise NotImplementedError(
            "Phase 8.5 cryptographic signing — Ed25519 wiring deferred. "
            "Use --sign in a follow-up commit when keys are provisioned."
        )

    metrics: dict = {}
    if args.metrics_json is not None:
        if not args.metrics_json.exists():
            print(
                f"--metrics-json file missing: {args.metrics_json}",
                file=sys.stderr,
            )
            return 1
        metrics = json.loads(args.metrics_json.read_text())
        if not isinstance(metrics, dict):
            print("--metrics-json must contain a JSON dict", file=sys.stderr)
            return 1

    if args.stage in {"production", "beta"} and not metrics:
        print(
            f"warning: building {args.stage!r} gate with empty metrics; "
            f"verify step will refuse the artifact.",
            file=sys.stderr,
        )

    hashes = _resolve_hashes(args.domain)
    corpus_version = _resolve_corpus_version(args.domain)
    gold_set_path, n_cases = _resolve_gold_set(args.domain)

    artifact = build_artifact(
        domain_id=args.domain,
        stage_requested=args.stage,
        git_sha=_git_sha(),
        corpus_version=corpus_version,
        gold_set_path=gold_set_path,
        n_cases=n_cases,
        metrics=metrics,
        prompt_pack_hash=hashes["prompt_pack_hash"],
        ontology_hash=hashes["ontology_hash"],
        domain_spec_hash=hashes["domain_spec_hash"],
        verifier_hash=hashes["verifier_hash"],
        reviewer_roles=[r.strip() for r in args.reviewer_roles.split(",") if r.strip()],
        approved_by=[r.strip() for r in args.approved_by.split(",") if r.strip()],
        notes=args.notes,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact.model_dump(mode="json"), indent=2))
    print(
        f"wrote gate artifact: {args.out}\n"
        f"  domain_id={artifact.domain_id} stage={artifact.stage_requested}\n"
        f"  artifact_hash={artifact.artifact_hash}\n"
        f"  n_cases={artifact.n_cases} corpus_version={artifact.corpus_version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
