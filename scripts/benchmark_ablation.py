#!/usr/bin/env python3
"""Ablation study script for Vietnamese LegalQA (Phase 9).

Measures the marginal contribution of each architectural component:
1. Full System: Hybrid + QA-Memory + Cross-Encoder
2. - Cross-Encoder Reranker
3. - QA-Memory
4. - Dense Retriever (BM25 Okapi only)
5. - BM25 Lexical (Dense only)

Outputs results/ablation.csv and paper-ready Table 8.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import csv
import datetime
import json

from scripts.run_paper_experiments import (
    _evaluate_retrieval_variant,
    _qa_memory_disabled,
)
from src.qa.pipeline import LegalQAPipeline
from src.utils.io import load_json

ABLATION_CONFIGS = [
    {
        "id": "full_with_cross_encoder_reranker",
        "name": "Full System (Cross-Encoder + QA-Mem + Hybrid)",
        "removed": "None (Full)",
    },
    {
        "id": "hybrid_with_qa_memory",
        "name": "— Cross-Encoder Reranker",
        "removed": "Cross-Encoder",
    },
    {
        "id": "hybrid_no_qa_memory",
        "name": "— QA-Memory (Hybrid Lexical + Dense)",
        "removed": "QA-Memory",
    },
    {
        "id": "bm25_okapi_only",
        "name": "— Dense Retrieval (BM25 Okapi Only)",
        "removed": "Dense Retrieval",
    },
    {
        "id": "dense_only",
        "name": "— Sparse BM25 (Dense Only)",
        "removed": "BM25 Retrieval",
    },
    {
        "id": "bm25_only",
        "name": "— Okapi & Dense (BM25 Hashing Baseline)",
        "removed": "Okapi & Dense",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ablation study on system components (Phase 9).")
    parser.add_argument("--qa-path", default="data/raw/yuitc/test.parquet")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--cache-dir", default="reports/.paper_experiment_cache")
    parser.add_argument("--output-dir", default="results")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline = LegalQAPipeline.build()
    pipeline.artifacts.retriever.neural_dense.ensure_available()

    metric_ks = (1, 5, 10, 20)
    results = {}

    print("=== Phase 9: System Component Ablation Study ===")
    print(f"Evaluating {len(ABLATION_CONFIGS)} configurations on {args.limit} samples...")

    for cfg in ABLATION_CONFIGS:
        vid = cfg["id"]
        print(f"\nEvaluating ablation: {cfg['name']} ({vid})...")
        if vid == "hybrid_no_qa_memory":
            with _qa_memory_disabled(pipeline):
                m, _ = _evaluate_retrieval_variant(
                    pipeline=pipeline,
                    variant=vid,
                    qa_path=args.qa_path,
                    limit=args.limit,
                    top_k=args.top_k,
                    ks=metric_ks,
                    cache_dir=cache_dir,
                )
        else:
            m, _ = _evaluate_retrieval_variant(
                pipeline=pipeline,
                variant=vid,
                qa_path=args.qa_path,
                limit=args.limit,
                top_k=args.top_k,
                ks=metric_ks,
                cache_dir=cache_dir,
            )
        results[vid] = m

    full_r5 = results["full_with_cross_encoder_reranker"].get("recall@5", 0.0)
    full_mrr = results["full_with_cross_encoder_reranker"].get("mrr", 0.0)

    csv_rows = []
    for cfg in ABLATION_CONFIGS:
        vid = cfg["id"]
        m = results[vid]
        r5 = m.get("recall@5", 0.0)
        r10 = m.get("recall@10", 0.0)
        mrr = m.get("mrr", 0.0)
        ndcg = m.get("ndcg@10", 0.0)
        delta_r5 = r5 - full_r5
        delta_mrr = mrr - full_mrr

        csv_rows.append(
            {
                "configuration": cfg["name"],
                "variant": vid,
                "removed_component": cfg["removed"],
                "r@5": round(r5, 4),
                "r@10": round(r10, 4),
                "mrr@10": round(mrr, 4),
                "ndcg@10": round(ndcg, 4),
                "delta_r@5": round(delta_r5, 4),
                "delta_mrr": round(delta_mrr, 4),
            }
        )

    csv_path = output_dir / "ablation.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"\nSaved ablation study CSV to: {csv_path}")

    # Print Table 8
    print("\n### Table 8: Retrieval Component Ablation Study")
    print("| Configuration | Removed Component | R@5 | Δ R@5 | R@10 | MRR@10 | Δ MRR | nDCG@10 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    for r in csv_rows:
        delta_r5_str = f"{r['delta_r@5']:+.4f}" if r['delta_r@5'] != 0 else "—"
        delta_mrr_str = f"{r['delta_mrr']:+.4f}" if r['delta_mrr'] != 0 else "—"
        print(
            f"| {r['configuration']} | {r['removed_component']} | "
            f"{r['r@5']:.4f} | {delta_r5_str} | {r['r@10']:.4f} | "
            f"{r['mrr@10']:.4f} | {delta_mrr_str} | {r['ndcg@10']:.4f} |"
        )


if __name__ == "__main__":
    main()
