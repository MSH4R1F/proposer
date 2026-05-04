#!/usr/bin/env python3
"""Smoke-test Housing Ombudsman repairs/social RAG retrieval quality.

This is intentionally separate from ``test_deposit_rag_quality.py`` because
the Housing Ombudsman corpus lives in a different namespace, Chroma collection,
and BM25 pickle.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = PROJECT_ROOT / "packages"
for path in (PROJECT_ROOT, PACKAGES_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.chdir(PROJECT_ROOT)

from rag_engine.config import RAGConfig  # noqa: E402
from rag_engine.pipeline import RAGPipeline  # noqa: E402


NAMESPACE_ID = "housing_repairs_social_v1"
CORPUS_VERSION = "research_seed_2026_05"
COLLECTION_NAME = "housing_ombudsman_determinations_v1"

TEST_QUERIES: list[dict[str, Any]] = [
    {
        "query": "resident reported damp and mould in the property and landlord delayed repairs",
        "expected_terms": ["damp", "mould", "repair"],
        "expected_matter_type": "repairs_damp_mould",
    },
    {
        "query": "roof leak and water ingress repairs took too long",
        "expected_terms": ["leak", "water", "repair"],
        "expected_matter_type": "repairs_disrepair",
    },
    {
        "query": "complaint handling delays after repair reports and missed appointments",
        "expected_terms": ["complaint", "stage", "repair"],
        "expected_matter_type": "complaint_handling_failure",
    },
    {
        "query": "heating or hot water repair delay caused distress and inconvenience",
        "expected_terms": ["heating", "hot water", "repair"],
        "expected_matter_type": "repairs_disrepair",
    },
    {
        "query": "reasonable redress offered for damp mould complaint handling failures",
        "expected_terms": ["reasonable redress", "damp", "complaint"],
        "expected_matter_type": "repairs_damp_mould",
        "expected_outcome": "reasonable-redress",
    },
]


def _resolve_data_dir(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser().resolve()
    env_value = os.getenv("DATA_DIR")
    if env_value:
        return Path(env_value).expanduser().resolve()
    if (PROJECT_ROOT / "indices" / NAMESPACE_ID / CORPUS_VERSION).exists():
        return PROJECT_ROOT
    return PROJECT_ROOT / "data"


def _metadata_for_result(pipeline: RAGPipeline, chunk_id: str) -> dict[str, Any]:
    chunk = pipeline.bm25_index.get_chunk_by_id(chunk_id)
    if not chunk or not chunk.source_metadata:
        return {}
    return chunk.source_metadata.to_chroma_metadata()


def _matter_types(meta: dict[str, Any]) -> list[str]:
    raw = meta.get("matter_types", "")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return [item for item in str(raw).split("|") if item]


def _term_hits(text: str, expected_terms: list[str]) -> list[str]:
    text_lower = text.lower()
    return [term for term in expected_terms if term.lower() in text_lower]


async def _run(args: argparse.Namespace) -> int:
    data_dir = _resolve_data_dir(args.data_dir)
    namespace_dir = data_dir / "indices" / NAMESPACE_ID / CORPUS_VERSION
    chroma_dir = namespace_dir / "chroma"
    bm25_path = namespace_dir / "bm25.pkl"

    config = RAGConfig(
        data_dir=data_dir,
        chroma_persist_dir=chroma_dir,
        bm25_index_path=bm25_path,
        collection_name=COLLECTION_NAME,
        bm25_lite_mode=True,
    )
    pipeline = RAGPipeline(config=config)

    print("=" * 78)
    print("HOUSING OMBUDSMAN RAG RETRIEVAL QUALITY SMOKE")
    print("=" * 78)
    print(f"data_dir: {data_dir}")
    print(f"chroma:   {chroma_dir}")
    print(f"bm25:     {bm25_path}")

    summaries: list[dict[str, float]] = []

    for index, test in enumerate(TEST_QUERIES, start=1):
        result = await pipeline.retrieve(query=test["query"], top_k=args.top_k)

        print("\n" + "-" * 78)
        print(f"TEST {index}: {test['query']}")
        print(
            f"confidence={result.confidence:.1%} "
            f"uncertain={result.is_uncertain} "
            f"candidates={result.total_candidates} "
            f"time={result.retrieval_time_ms:.0f}ms"
        )

        topic_hits = 0
        matter_hits = 0
        outcome_hits = 0
        seen_cases: set[str] = set()

        for rank, item in enumerate(result.results, start=1):
            if item.case_reference in seen_cases:
                continue
            seen_cases.add(item.case_reference)

            meta = _metadata_for_result(pipeline, item.chunk_id)
            terms = _term_hits(item.chunk_text, test["expected_terms"])
            matters = _matter_types(meta)
            outcome = str(meta.get("outcome_normalized") or "unknown")

            if terms:
                topic_hits += 1
            if test["expected_matter_type"] in matters:
                matter_hits += 1
            if test.get("expected_outcome") and outcome == test["expected_outcome"]:
                outcome_hits += 1

            print(
                f"#{rank} {item.case_reference} "
                f"score={item.combined_score:.4f} "
                f"sem={item.semantic_score:.3f} "
                f"bm25={item.bm25_score:.3f}"
            )
            print(f"   matter={matters or ['unknown']} outcome={outcome}")
            print(f"   term_hits={terms or ['none']}")

        denom = max(1, len(seen_cases))
        summary = {
            "topic_precision": topic_hits / denom,
            "matter_precision": matter_hits / denom,
            "outcome_precision": outcome_hits / denom
            if test.get("expected_outcome")
            else 0.0,
        }
        summaries.append(summary)
        print(
            "metrics: "
            f"topic@{denom}={summary['topic_precision']:.1%} "
            f"matter@{denom}={summary['matter_precision']:.1%}"
        )
        if test.get("expected_outcome"):
            print(f"         outcome@{denom}={summary['outcome_precision']:.1%}")

    avg_topic = mean(item["topic_precision"] for item in summaries)
    avg_matter = mean(item["matter_precision"] for item in summaries)

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"Average topic precision:  {avg_topic:.1%}")
    print(f"Average matter precision: {avg_matter:.1%}")
    print("Done.")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Smoke-test retrieval over the Housing Ombudsman corpus."
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help=(
            "Base data directory containing indices/. Defaults to DATA_DIR, "
            "then repo root if ./indices exists, else ./data."
        ),
    )
    parser.add_argument("--top-k", type=int, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
