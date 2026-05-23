#!/usr/bin/env python3
"""Shard + parallelise the RRO 4-mode x N-seed ablation.

predict_all.py processes gold cases SEQUENTIALLY and each gpt-5.5
prediction is ~60-130s, so a full run is impractical without sharding.
This orchestrator:

  1. Splits the gold JSONL into ``--shards`` shard files (round-robin so
     each shard has a balanced winner mix).
  2. For each (seed, shard) launches one ``predict_all.py`` subprocess
     covering ALL four modes, writing to
     ``<out-root>/seed<S>/shard<I>/<mode>.jsonl``.
  3. Bounds concurrency to ``--max-parallel`` subprocesses (to respect the
     OpenAI TPM rate limit on gpt-5.5).
  4. After all shards for a seed finish, concatenates
     ``shard*/<mode>.jsonl`` into ``<out-root>/seed<S>/<mode>.jsonl``.

Each seed re-runs the same gold with a distinct ``--run-id`` so that
gpt-5.5 reasoning-token drift yields independent samples (the model is
non-deterministic even at temperature handling internal to the engine).

Usage:
    PYTHONPATH=packages python scripts/eval/run_rro_sweep.py \
        --gold data/gold_standard/housing_property_chamber_rro_v1_eval60.jsonl \
        --out-root data/eval_artifacts/runs/rro_eval60 \
        --shards 10 --seeds 3 --max-parallel 5 --top-k 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_ALL_MODES = ("hybrid", "rag_only", "kg_only", "llm_only")


def _split_gold(gold_path: Path, n_shards: int, work_dir: Path) -> list[Path]:
    rows = [l for l in gold_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    shard_lines: list[list[str]] = [[] for _ in range(n_shards)]
    for i, line in enumerate(rows):
        shard_lines[i % n_shards].append(line)
    work_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, lines in enumerate(shard_lines):
        if not lines:
            continue
        p = work_dir / f"{gold_path.stem}__shard{i}.jsonl"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        paths.append(p)
    return paths


async def _run_one(
    sem: asyncio.Semaphore,
    *,
    shard_gold: Path,
    out_dir: Path,
    seed: int,
    shard_idx: int,
    rag_index_root: str,
    top_k: int,
    sidecar: Path | None,
    log_dir: Path,
    modes: tuple[str, ...],
) -> tuple[int, int, int]:
    async with sem:
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "eval" / "predict_all.py"),
            "--gold", str(shard_gold),
            "--out-dir", str(out_dir),
            "--engine", "live",
            "--client", "openai",
            "--modes", ",".join(modes),
            "--rag-index-root", rag_index_root,
            "--top-k", str(top_k),
            "--run-id", f"rro-seed{seed}-shard{shard_idx}",
        ]
        if sidecar is not None:
            cmd += ["--factor-assertion-sidecar", str(sidecar)]
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{REPO_ROOT}/packages:{env.get('PYTHONPATH','')}"
        log_path = log_dir / f"seed{seed}_shard{shard_idx}.log"
        log_dir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        with log_path.open("w") as logf:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=logf, stderr=asyncio.subprocess.STDOUT, cwd=str(REPO_ROOT), env=env
            )
            rc = await proc.wait()
        dt = int(time.time() - t0)
        print(f"[seed{seed} shard{shard_idx}] rc={rc} in {dt}s -> {out_dir}", flush=True)
        return seed, shard_idx, rc


def _concat_seed(out_root: Path, seed: int, shard_dirs: list[Path], modes: tuple[str, ...]) -> None:
    seed_dir = out_root / f"seed{seed}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    for mode in modes:
        merged = seed_dir / f"{mode}.jsonl"
        with merged.open("w", encoding="utf-8") as out:
            for sd in shard_dirs:
                p = sd / f"{mode}.jsonl"
                if p.exists():
                    out.write(p.read_text(encoding="utf-8"))


async def run(args: argparse.Namespace) -> int:
    gold_path = Path(args.gold)
    if not gold_path.is_absolute():
        gold_path = REPO_ROOT / gold_path
    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        out_root = REPO_ROOT / out_root
    out_root.mkdir(parents=True, exist_ok=True)

    sidecar = None
    if args.sidecar:
        sidecar = Path(args.sidecar)
        if not sidecar.is_absolute():
            sidecar = REPO_ROOT / sidecar

    modes = tuple(m.strip() for m in args.modes.split(",") if m.strip())
    for m in modes:
        assert m in _ALL_MODES, f"unknown mode {m}"

    work_dir = out_root / "_shards"
    shard_golds = _split_gold(gold_path, args.shards, work_dir)
    print(f"split {gold_path.name} into {len(shard_golds)} shards", flush=True)

    log_dir = out_root / "_logs"
    sem = asyncio.Semaphore(args.max_parallel)

    seed_lo = args.seed_start
    seed_hi = args.seed_start + args.seeds
    tasks = []
    seed_shard_dirs: dict[int, list[Path]] = {s: [] for s in range(seed_lo, seed_hi)}
    for seed in range(seed_lo, seed_hi):
        for shard_idx, sg in enumerate(shard_golds):
            out_dir = out_root / f"seed{seed}" / f"shard{shard_idx}"
            seed_shard_dirs[seed].append(out_dir)
            tasks.append(
                _run_one(
                    sem,
                    shard_gold=sg,
                    out_dir=out_dir,
                    seed=seed,
                    shard_idx=shard_idx,
                    rag_index_root=args.rag_index_root,
                    top_k=args.top_k,
                    sidecar=sidecar,
                    log_dir=log_dir,
                    modes=modes,
                )
            )

    results = await asyncio.gather(*tasks)
    n_fail = sum(1 for _, _, rc in results if rc != 0)
    print(f"all shards done; {n_fail} non-zero exit", flush=True)

    for seed in range(seed_lo, seed_hi):
        _concat_seed(out_root, seed, seed_shard_dirs[seed], modes)
        print(f"concatenated seed{seed} -> {out_root / f'seed{seed}'}", flush=True)

    print(json.dumps({
        "gold": str(gold_path),
        "out_root": str(out_root),
        "seeds": args.seeds,
        "shards": len(shard_golds),
        "n_shard_runs": len(results),
        "n_failed": n_fail,
    }, indent=2))
    return 1 if n_fail else 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Shard + parallelise the RRO 4-mode x N-seed ablation.")
    p.add_argument("--gold", required=True)
    p.add_argument("--out-root", required=True)
    p.add_argument("--shards", type=int, default=10)
    p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--seed-start", type=int, default=0, help="first seed index (for resuming specific seeds)")
    p.add_argument("--max-parallel", type=int, default=5)
    p.add_argument("--rag-index-root", default="data/indices")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--modes", default="hybrid,rag_only,kg_only,llm_only")
    p.add_argument("--sidecar", default=None, help="explicit factor sidecar path (else predict_all auto-resolves)")
    return p


def main(argv=None) -> int:
    return asyncio.run(run(_parser().parse_args(argv)))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
