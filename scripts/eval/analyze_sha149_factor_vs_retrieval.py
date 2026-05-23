"""Compare SHA-149 factor signals vs retrieval signals on the ET corpus.

Computes per-case factor score (sum pro_claimant conf - sum pro_respondent conf)
and per-case retrieval score (#claimant_success precedents - #respondent_success)
from the production RAG pipeline, then classifies agreement and inspects how
hybrid resolves disagreements.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from rag_engine.config import RAGConfig, RetrievalFilterEnvelope  # noqa: E402
from rag_engine.pipeline import RAGPipeline  # noqa: E402
from domain_core.registry import get_domain_spec  # noqa: E402
from domain_core.spec import Forum, SourceKind, SourcePublisher  # noqa: E402

DOMAIN_ID = "employment.unfair_dismissal.v1"
TOP_K = 5

GOLD_PATH = REPO_ROOT / "data" / "gold_standard" / "employment_unfair_dismissal_v1.jsonl"
FACTOR_PATH = (
    REPO_ROOT / "data" / "eval_artifacts" / "factor_assertions"
    / "employment_unfair_dismissal_v1.factor_assertions.json"
)
RUN_DIR = (
    REPO_ROOT / "data" / "eval_artifacts" / "runs" / "employment_unfair_dismissal_v1"
    / "sha149-run-a-1779018524"
)


def load_gold() -> list[dict[str, Any]]:
    rows = []
    with GOLD_PATH.open() as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_predictions(mode: str) -> dict[str, dict[str, Any]]:
    path = RUN_DIR / f"predictions_{mode}.jsonl"
    out = {}
    with path.open() as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                out[d["case_id"]] = d
    return out


def compute_factor_scores() -> dict[str, dict[str, Any]]:
    payload = json.loads(FACTOR_PATH.read_text())
    fa_by_case = payload["factor_assertions_by_case_id"]
    out: dict[str, dict[str, Any]] = {}
    for case_id, fas in fa_by_case.items():
        pro_c = 0.0
        pro_r = 0.0
        c_factors = []
        r_factors = []
        for fa in fas:
            pol = fa.get("polarity")
            conf = float(fa.get("confidence") or 0.0)
            fid = fa.get("factor_id")
            value = (fa.get("value") or {}).get("boolean")
            # Only count factors where the assertion is positively detected (boolean=true)
            # OR where polarity itself carries the direction regardless of value.
            # Sidecar entries with boolean=false and polarity=pro_claimant still indicate
            # the factor wasn't found in a pro-claimant direction; treat them as zero weight.
            if value is False:
                continue
            if pol == "pro_claimant":
                pro_c += conf
                c_factors.append(f"{fid}@{conf:.2f}")
            elif pol == "pro_respondent":
                pro_r += conf
                r_factors.append(f"{fid}@{conf:.2f}")
        out[case_id] = {
            "factor_score": round(pro_c - pro_r, 3),
            "pro_claimant_sum": round(pro_c, 3),
            "pro_respondent_sum": round(pro_r, 3),
            "pro_claimant_factors": c_factors,
            "pro_respondent_factors": r_factors,
            "n_factors_total": len(fas),
        }
    return out


async def compute_retrieval_scores(gold: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    spec = get_domain_spec(DOMAIN_ID)
    ns = spec.retrieval_namespaces[0]
    cfg = RAGConfig.from_namespace(ns, base=RAGConfig.from_env(), project_root=REPO_ROOT)
    rag = RAGPipeline(config=cfg, namespace=ns)

    # case_id -> gold winner
    winner_lookup = {
        gc["case_id"]: gc["ground_truth_outcome"]["overall_winner"] for gc in gold
    }

    out: dict[str, dict[str, Any]] = {}

    async def _one(gc: dict[str, Any]) -> None:
        case_id = gc["case_id"]
        facts = (gc.get("facts") or "").strip()
        query = facts[:1800] if facts else f"unfair dismissal {case_id}"
        exclude = {case_id}
        if gc.get("target_source_id"):
            exclude.add(str(gc["target_source_id"]))
        if gc.get("source_url"):
            exclude.add(str(gc["source_url"]))
        filters = RetrievalFilterEnvelope(
            excluded_source_ids=sorted(exclude),
            forum=Forum.EMPLOYMENT_TRIBUNAL,
            source_kind=SourceKind.CASE_DECISION,
            source_publisher=SourcePublisher.GOVUK,
            matter_type="unfair_dismissal",
            eval_only=True,
        )
        result = await rag.retrieve(query, top_k=TOP_K, filters=filters, requesting_namespace=ns)
        seen_cases: dict[str, str | None] = {}
        for r in getattr(result, "results", []) or []:
            ref = getattr(r, "case_reference", "") or ""
            if ref and ref not in seen_cases:
                seen_cases[ref] = winner_lookup.get(ref)
        winners = list(seen_cases.values())
        n_c = sum(1 for w in winners if w == "claimant")
        n_r = sum(1 for w in winners if w == "respondent")
        out[case_id] = {
            "retrieval_score": n_c - n_r,
            "n_claimant_precedents": n_c,
            "n_respondent_precedents": n_r,
            "n_unique_precedents": len(seen_cases),
            "precedent_refs": [(ref, w) for ref, w in seen_cases.items()],
        }

    sem = asyncio.Semaphore(4)

    async def _bound(gc: dict[str, Any]) -> None:
        async with sem:
            try:
                await _one(gc)
            except Exception as e:
                print(f"retrieval failed on {gc['case_id']}: {e!r}", file=sys.stderr)
                out[gc["case_id"]] = {
                    "retrieval_score": 0,
                    "n_claimant_precedents": 0,
                    "n_respondent_precedents": 0,
                    "n_unique_precedents": 0,
                    "precedent_refs": [],
                    "error": repr(e),
                }

    await asyncio.gather(*[_bound(gc) for gc in gold])
    return out


def classify(fs: float, rs: int) -> str:
    if fs == 0 or rs == 0:
        return "silent"
    if fs > 0 and rs > 0:
        return "agree_claimant"
    if fs < 0 and rs < 0:
        return "agree_respondent"
    return "disagree"


async def main() -> None:
    gold = load_gold()
    print(f"loaded {len(gold)} gold rows", file=sys.stderr)
    factor_scores = compute_factor_scores()
    retrieval_scores = await compute_retrieval_scores(gold)
    preds = {m: load_predictions(m) for m in ("llm_only", "rag_only", "kg_only", "hybrid")}

    by_case = []
    cat_counter: Counter[str] = Counter()
    for gc in gold:
        cid = gc["case_id"]
        gw = gc["ground_truth_outcome"]["overall_winner"]
        fs = factor_scores.get(cid, {}).get("factor_score", 0.0)
        rs_d = retrieval_scores.get(cid, {})
        rs = rs_d.get("retrieval_score", 0)
        cat = classify(fs, rs)
        cat_counter[cat] += 1
        row = {
            "case_id": cid,
            "gold_winner": gw,
            "factor_score": fs,
            "retrieval_score": rs,
            "category": cat,
            "factor_details": factor_scores.get(cid, {}),
            "retrieval_details": rs_d,
        }
        for m, table in preds.items():
            p = table.get(cid, {})
            row[f"{m}_winner"] = p.get("overall_winner")
            row[f"{m}_p_resp"] = p.get("overall_win_probability_respondent")
            row[f"{m}_rationale"] = (p.get("rationale") or "")[:300]
        by_case.append(row)

    # Save per-case rows for downstream inspection
    out_path = RUN_DIR / "factor_vs_retrieval_analysis.json"
    out_path.write_text(json.dumps({
        "categories": dict(cat_counter),
        "rows": by_case,
    }, indent=2, default=str))

    # ---- Reports ----
    print(f"\n=== Categories (N=49) ===")
    for k, v in cat_counter.most_common():
        print(f"  {k}: {v}")

    # Disagree diagnostics
    disagree = [r for r in by_case if r["category"] == "disagree"]
    print(f"\n=== Disagree cases: {len(disagree)} ===")
    for r in disagree:
        fs = r["factor_score"]; rs = r["retrieval_score"]
        gw = r["gold_winner"]
        fact_dir = "pro_claimant" if fs > 0 else "pro_respondent"
        ret_dir = "pro_claimant" if rs > 0 else "pro_respondent"
        which_right = (
            "factor" if (fact_dir == f"pro_{gw}") else
            "retrieval" if (ret_dir == f"pro_{gw}") else "neither"
        )
        print(
            f"  {r['case_id']} | gold={gw} | factor={fs:+.2f}({fact_dir}) "
            f"retr={rs:+d}({ret_dir}) -> right={which_right} | "
            f"hybrid={r['hybrid_winner']}/{r['hybrid_p_resp']:.2f} "
            f"kg={r['kg_only_winner']}/{r['kg_only_p_resp']:.2f} "
            f"rag={r['rag_only_winner']}/{r['rag_only_p_resp']:.2f}"
        )

    # Question: when factors and retrieval disagree, which signal matches gold?
    factor_right = sum(
        1 for r in disagree
        if (r["factor_score"] > 0 and r["gold_winner"] == "claimant")
        or (r["factor_score"] < 0 and r["gold_winner"] == "respondent")
    )
    retr_right = sum(
        1 for r in disagree
        if (r["retrieval_score"] > 0 and r["gold_winner"] == "claimant")
        or (r["retrieval_score"] < 0 and r["gold_winner"] == "respondent")
    )
    print(f"\n  factor matches gold: {factor_right}/{len(disagree)}")
    print(f"  retrieval matches gold: {retr_right}/{len(disagree)}")

    hybrid_sides_with_retr = sum(
        1 for r in disagree
        if (r["retrieval_score"] > 0 and r["hybrid_winner"] == "claimant")
        or (r["retrieval_score"] < 0 and r["hybrid_winner"] == "respondent")
    )
    hybrid_sides_with_factor = sum(
        1 for r in disagree
        if (r["factor_score"] > 0 and r["hybrid_winner"] == "claimant")
        or (r["factor_score"] < 0 and r["hybrid_winner"] == "respondent")
    )
    print(f"  hybrid sides with retrieval: {hybrid_sides_with_retr}/{len(disagree)}")
    print(f"  hybrid sides with factor: {hybrid_sides_with_factor}/{len(disagree)}")

    # Direction of error on hybrid losses
    hybrid_losses = [r for r in by_case if r["hybrid_winner"] != r["gold_winner"]]
    kg_would_have_been_right = sum(
        1 for r in hybrid_losses if r["kg_only_winner"] == r["gold_winner"]
    )
    rag_would_have_been_right = sum(
        1 for r in hybrid_losses if r["rag_only_winner"] == r["gold_winner"]
    )
    print(f"\n=== Hybrid losses (N={len(hybrid_losses)}) ===")
    print(f"  kg_only would have been right on: {kg_would_have_been_right}")
    print(f"  rag_only would have been right on: {rag_would_have_been_right}")

    # Mean P(resp) on disagree cases
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    print(f"\n=== Mean P(resp) on disagree cases ===")
    for m in ("kg_only", "rag_only", "hybrid"):
        ps = [r[f"{m}_p_resp"] for r in disagree]
        print(f"  {m}: {mean(ps):.3f}" if mean(ps) is not None else f"  {m}: n/a")

    # Bonus: mean P(resp) on factor-pro-claimant disagree subset
    sub = [r for r in disagree if r["factor_score"] > 0]
    print(f"\n=== Mean P(resp) on factor-pro-claimant + retrieval-pro-respondent ({len(sub)}) ===")
    for m in ("kg_only", "rag_only", "hybrid"):
        ps = [r[f"{m}_p_resp"] for r in sub]
        v = mean(ps)
        print(f"  {m}: {v:.3f}" if v is not None else f"  {m}: n/a")

    print(f"\nSaved per-case analysis -> {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
