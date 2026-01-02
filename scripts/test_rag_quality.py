#!/usr/bin/env python3
"""
Test RAG retrieval quality with hybrid vs semantic-only comparison.

This script tests retrieval on a set of sample queries and compares
hybrid search (semantic + BM25) against semantic-only search.
"""

import sys
from pathlib import Path
import json
import asyncio

# Add packages directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "packages"))

import os
os.chdir(str(project_root))

from rag_engine.config import RAGConfig
from rag_engine.pipeline import RAGPipeline

# Test queries with expected topics/keywords
TEST_QUERIES = [
    {
        "query": "landlord didn't protect deposit",
        "expected_topics": ["deposit", "protection", "section 213", "section 214"],
        "expected_case_types": ["HMF", "HTC"],
    },
    {
        "query": "cleaning costs disputed",
        "expected_topics": ["cleaning", "clean", "professional clean"],
        "expected_case_types": ["LSC", "HMF", "LDC"],
    },
    {
        "query": "damage to carpet fair wear and tear",
        "expected_topics": ["damage", "carpet", "wear", "tear", "betterment"],
        "expected_case_types": ["HMF", "LDC", "LBC"],
    },
    {
        "query": "deposit not protected section 213",
        "expected_topics": ["section 213", "protected", "deposit", "prescribed information"],
        "expected_case_types": ["HMF", "HTC"],
    },
    {
        "query": "rent repayment order housing act",
        "expected_topics": ["rent repayment", "RRO", "housing act", "offence"],
        "expected_case_types": ["HMF", "HMG", "HNA"],
    },
]


def check_relevance(result, expected_topics):
    """Check if result text contains expected topics."""
    text_lower = result.chunk_text.lower()
    matches = []
    for topic in expected_topics:
        if topic.lower() in text_lower:
            matches.append(topic)
    return matches


async def main():
    print("=" * 70)
    print("RAG RETRIEVAL QUALITY TEST")
    print("=" * 70)
    
    # Initialize pipeline with default config
    config = RAGConfig(
        data_dir=Path("data"),
        chroma_persist_dir=Path("data/embeddings"),
        bm25_index_path=Path("data/embeddings/bm25_index.pkl"),
        bm25_lite_mode=True,
    )
    
    print("\nInitializing RAG pipeline...")
    pipeline = RAGPipeline(config=config)
    
    results_summary = []
    
    for i, test in enumerate(TEST_QUERIES, 1):
        query = test["query"]
        expected_topics = test["expected_topics"]
        expected_case_types = test["expected_case_types"]
        
        print(f"\n{'=' * 70}")
        print(f"TEST {i}: {query}")
        print("=" * 70)
        
        # Run retrieval
        result = await pipeline.retrieve(query=query, top_k=5)
        
        print(f"\nConfidence: {result.confidence:.1%}")
        print(f"Uncertain: {result.is_uncertain}")
        print(f"Time: {result.retrieval_time_ms:.0f}ms")
        print(f"Total candidates: {result.total_candidates}")
        
        # Analyze results
        topic_hits = 0
        case_type_hits = 0
        
        print(f"\n{'Top 5 Results':^70}")
        print("-" * 70)
        
        for j, r in enumerate(result.results, 1):
            matches = check_relevance(r, expected_topics)
            has_expected_case = any(ct in r.case_reference for ct in expected_case_types)
            
            if matches:
                topic_hits += 1
            if has_expected_case:
                case_type_hits += 1
            
            topic_indicator = "✓" if matches else "✗"
            case_indicator = "✓" if has_expected_case else "✗"
            
            print(f"  #{j} {r.case_reference}")
            print(f"      Scores: sem={r.semantic_score:.3f}, bm25={r.bm25_score:.3f}, combined={r.combined_score:.4f}")
            print(f"      Topics {topic_indicator}: {matches if matches else 'No matches'}")
            print(f"      Case type {case_indicator}: {r.case_type or 'Unknown'}")
        
        # Calculate metrics
        topic_precision = topic_hits / len(result.results) if result.results else 0
        case_type_precision = case_type_hits / len(result.results) if result.results else 0
        
        print(f"\nMetrics:")
        print(f"  Topic precision (top 5): {topic_precision:.1%} ({topic_hits}/5)")
        print(f"  Case type precision: {case_type_precision:.1%} ({case_type_hits}/5)")
        print(f"  Avg semantic score: {sum(r.semantic_score for r in result.results) / len(result.results):.3f}")
        print(f"  Avg BM25 score: {sum(r.bm25_score for r in result.results) / len(result.results):.3f}")
        
        results_summary.append({
            "query": query,
            "confidence": result.confidence,
            "topic_precision": topic_precision,
            "case_type_precision": case_type_precision,
            "avg_semantic": sum(r.semantic_score for r in result.results) / len(result.results) if result.results else 0,
            "avg_bm25": sum(r.bm25_score for r in result.results) / len(result.results) if result.results else 0,
            "retrieval_time_ms": result.retrieval_time_ms,
        })
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    avg_confidence = sum(r["confidence"] for r in results_summary) / len(results_summary)
    avg_topic_precision = sum(r["topic_precision"] for r in results_summary) / len(results_summary)
    avg_case_type_precision = sum(r["case_type_precision"] for r in results_summary) / len(results_summary)
    avg_time = sum(r["retrieval_time_ms"] for r in results_summary) / len(results_summary)
    
    print(f"\nOverall Metrics (across {len(results_summary)} queries):")
    print(f"  Average confidence: {avg_confidence:.1%}")
    print(f"  Average topic precision: {avg_topic_precision:.1%}")
    print(f"  Average case type precision: {avg_case_type_precision:.1%}")
    print(f"  Average retrieval time: {avg_time:.0f}ms")
    
    # BM25 contribution analysis
    total_with_bm25 = sum(1 for r in results_summary if r["avg_bm25"] > 0)
    print(f"\n  Queries with BM25 hits: {total_with_bm25}/{len(results_summary)}")
    
    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
