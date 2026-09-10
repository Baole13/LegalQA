#!/usr/bin/env python3
"""Official retrieval benchmark script for Vietnamese LegalQA (Phase 1).

Runs evaluation across 6 retrieval variants on the YuITC test dataset,
computes bootstrap confidence intervals, and outputs standardized CSV and JSON reports.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import csv
import datetime
import json
import os
import random

from scripts.run_paper_experiments import (
    _CROSS_ENCODER_DEPTHS,
    _evaluate_retrieval_variant,
    _metrics_from_details,
    _metrics_template,
    _qa_memory_disabled,
)
from src.data.load_qa import load_qa_records, parse_cids
from src.evaluation.retrieval_eval import ndcg_at_k
from src.evaluation.significance import bootstrap_ci
from src.qa.pipeline import LegalQAPipeline

VARIANTS = [
    ("bm25_only", "BM25 (Hashing)"),
    ("bm25_okapi_only", "BM25 (Okapi)"),
    ("dense_only", "Dense"),
    ("hybrid_no_qa_memory", "Hybrid"),
    ("hybrid_with_qa_memory", "Hybrid + QA-Memory"),
    ("full_with_cross_encoder_reranker", "Hybrid + QA-Memory + Cross-Encoder"),
]


def per_query_retrieval_metrics(
    details: list[dict], ks: tuple[int, ...] = (1, 5, 10, 20)
) -> dict[str, list[float]]:
    """Compute per-query values for recall@k, mrr@10, and ndcg@10."""
    metrics: dict[str, list[float]] = {f"r@{k}": [] for k in ks}
    metrics["mrr@10"] = []
    metrics["ndcg@10"] = []

    for item in details:
        gold = {str(cid) for cid in item.get("gold_cids", [])}
        ranked = [str(hit.get("cid", "")) for hit in (item.get("retrieved") or [])]

        for k in ks:
            metrics[f"r@{k}"].append(float(any(cid in gold for cid in ranked[:k])))

        # MRR@10
        mrr = 0.0
        for rank, cid in enumerate(ranked[:10], start=1):
            if cid in gold:
                mrr = 1.0 / rank
                break
        metrics["mrr@10"].append(mrr)

        # nDCG@10
        metrics["ndcg@10"].append(ndcg_at_k(ranked, gold, 10))

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run official retrieval benchmark on Vietnamese LegalQA (YuITC test set)."
    )
    parser.add_argument(
        "--qa-path", default="data/raw/yuitc/test.parquet", help="Path to test QA dataset."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Number of samples to evaluate (0 for all records).",
    )
    parser.add_argument("--top-k", type=int, default=20, help="Top-K candidates to retrieve.")
    parser.add_argument(
        "--report-dir",
        default="reports",
        help="Base report directory for cache.",
    )
    parser.add_argument(
        "--output-dir",
        default="results",
        help="Output directory for benchmark CSV/JSON.",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Custom cache dir (defaults to <report-dir>/.benchmark_cache).",
    )
    parser.add_argument(
        "--reranker-model-path",
        default=None,
        help="Override reranker model path in environment.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for bootstrap CI.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect dataset and configuration without running retrieval.",
    )
    args = parser.parse_args()

    qa_records = load_qa_records(args.qa_path)
    total_records = len(qa_records)
    eval_limit = total_records if args.limit <= 0 else min(args.limit, total_records)

    print(f"=== Vietnamese LegalQA Official Retrieval Benchmark ===")
    print(f"Test Dataset : {args.qa_path} (Total: {total_records}, Evaluating: {eval_limit})")
    print(f"Top-K        : {args.top_k}")
    print(f"Reranker     : {args.reranker_model_path or 'default'}")

    if args.dry_run:
        print("Dry run completed successfully. Configuration is valid.")
        return

    if args.reranker_model_path:
        os.environ["LEGAL_QA_RERANKER_MODEL_PATH"] = args.reranker_model_path

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = (
        Path(args.cache_dir)
        if args.cache_dir
        else Path(args.report_dir) / ".benchmark_cache"
    )
    cache_dir.mkdir(parents=True, exist_ok=True)

    pipeline = LegalQAPipeline.build()
    pipeline.artifacts.retriever.neural_dense.ensure_available()

    metric_ks = (1, 5, 10, 20)
    all_results: list[dict] = []
    csv_rows: list[dict] = []
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    rng = random.Random(args.seed)

    for variant_id, method_name in VARIANTS:
        print(f"\nEvaluating variant: {variant_id} ({method_name})...")
        if variant_id == "hybrid_no_qa_memory":
            with _qa_memory_disabled(pipeline):
                metrics, details = _evaluate_retrieval_variant(
                    pipeline=pipeline,
                    variant=variant_id,
                    qa_path=args.qa_path,
                    limit=eval_limit,
                    top_k=args.top_k,
                    ks=metric_ks,
                    cache_dir=cache_dir,
                )
        else:
            metrics, details = _evaluate_retrieval_variant(
                pipeline=pipeline,
                variant=variant_id,
                qa_path=args.qa_path,
                limit=eval_limit,
                top_k=args.top_k,
                ks=metric_ks,
                cache_dir=cache_dir,
            )

        # Bootstrap CIs
        per_query = per_query_retrieval_metrics(details, metric_ks)
        ci_summary = {}
        for metric_name, values in per_query.items():
            ci = bootstrap_ci(values, iterations=1000, rng=rng)
            ci_summary[metric_name] = ci

        result_entry = {
            "variant": variant_id,
            "method": method_name,
            "metrics": metrics,
            "confidence_intervals": ci_summary,
            "samples": eval_limit,
            "timestamp": timestamp,
        }
        all_results.append(result_entry)

        csv_rows.append(
            {
                "method": method_name,
                "variant": variant_id,
                "n_samples": eval_limit,
                "r@1": metrics.get("recall@1", 0.0),
                "r@5": metrics.get("recall@5", 0.0),
                "r@10": metrics.get("recall@10", 0.0),
                "r@20": metrics.get("recall@20", 0.0),
                "mrr@10": metrics.get("mrr", 0.0),
                "ndcg@10": metrics.get("ndcg@10", 0.0),
                "gold_coverage": metrics.get("gold_coverage_in_index", 0.0),
                "timestamp": timestamp,
            }
        )

        print(
            f"  R@1: {metrics.get('recall@1', 0.0):.4f} | "
            f"R@5: {metrics.get('recall@5', 0.0):.4f} | "
            f"R@10: {metrics.get('recall@10', 0.0):.4f} | "
            f"MRR: {metrics.get('mrr', 0.0):.4f} | "
            f"nDCG@10: {metrics.get('ndcg@10', 0.0):.4f}"
        )

    # Save CSV
    csv_path = output_dir / "retrieval_benchmark.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "method",
            "variant",
            "n_samples",
            "r@1",
            "r@5",
            "r@10",
            "r@20",
            "mrr@10",
            "ndcg@10",
            "gold_coverage",
            "timestamp",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"\nSaved CSV to: {csv_path}")

    # Save JSON
    json_path = output_dir / "retrieval_benchmark.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"Saved JSON to: {json_path}")

    # Print summary Markdown table
    print("\n### Official Retrieval Benchmark Summary")
    print("| Method | R@1 | R@5 | R@10 | R@20 | MRR@10 | nDCG@10 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for row in csv_rows:
        print(
            f"| {row['method']} | {row['r@1']:.4f} | {row['r@5']:.4f} | "
            f"{row['r@10']:.4f} | {row['r@20']:.4f} | {row['mrr@10']:.4f} | {row['ndcg@10']:.4f} |"
        )


if __name__ == "__main__":
    main()
