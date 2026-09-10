#!/usr/bin/env python3
"""Benchmark public rerankers vs fine-tuned legal reranker on identical candidates (Phase 3).

Keeps candidate pool from Hybrid + QA-memory retrieval constant,
and evaluates different rerankers:
1. No reranker (Hybrid + QA-memory ranking)
2. Pretrained Cross-Encoder (cross-encoder/ms-marco-MiniLM-L-6-v2)
3. Public Multilingual Reranker (BAAI/bge-reranker-v2-m3 or base)
4. Ours Fine-tuned Reranker (models/reranker-best)
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
import random

from src.data.load_qa import load_qa_records, parse_cids
from src.evaluation.retrieval_eval import ndcg_at_k
from src.evaluation.significance import bootstrap_ci
from src.qa.pipeline import LegalQAPipeline


def load_or_generate_candidates(
    pipeline: LegalQAPipeline,
    qa_path: str,
    limit: int,
    depth: int = 50,
    candidate_cache_path: Path | None = None,
) -> list[dict]:
    """Load or generate the base candidate pool from Hybrid + QA-memory."""
    if candidate_cache_path and candidate_cache_path.exists():
        print(f"Loading candidate pool from cache: {candidate_cache_path}...")
        records = []
        with candidate_cache_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        if len(records) >= limit:
            return records[:limit]

    print(f"Generating candidate pool for {limit} queries (depth={depth})...")
    raw_records = load_qa_records(qa_path)[:limit]
    pipeline.artifacts.retriever.neural_dense.ensure_available()

    candidates_list: list[dict] = []
    for idx, rec in enumerate(raw_records):
        question = str(rec.get("question", ""))
        gold_cids = set(parse_cids(rec.get("cid", "")))
        similar_questions = pipeline.artifacts.retriever.similar_questions(question, top_k=5)
        heuristic_hits = pipeline._heuristic_retrieval(question, similar_questions, top_k=depth)

        candidates_list.append(
            {
                "sample_index": idx,
                "question": question,
                "gold_cids": sorted(gold_cids),
                "retrieved": heuristic_hits,
            }
        )
        if (idx + 1) % 50 == 0 or (idx + 1) == limit:
            print(f"  Retrieved candidates for {idx + 1}/{limit} queries")

    if candidate_cache_path:
        candidate_cache_path.parent.mkdir(parents=True, exist_ok=True)
        with candidate_cache_path.open("w", encoding="utf-8") as f:
            for item in candidates_list:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"Cached candidate pool to {candidate_cache_path}")

    return candidates_list


def rerank_with_cross_encoder(
    model: object,
    question: str,
    candidates: list[dict],
    top_k: int = 20,
) -> list[dict]:
    """Score (question, chunk_text) pairs using a CrossEncoder model."""
    if not candidates:
        return []
    pairs = [(question, str(c.get("text", ""))) for c in candidates]
    scores = model.predict(pairs)
    scored = []
    for candidate, score in zip(candidates, scores):
        scored.append({**candidate, "rerank_score": float(score)})
    scored.sort(key=lambda x: x["rerank_score"], reverse=True)
    return scored[:top_k]


def evaluate_reranker(
    reranker_name: str,
    model: object | None,
    candidate_pool: list[dict],
    top_k: int = 20,
    ks: tuple[int, ...] = (1, 5, 10, 20),
) -> dict:
    """Evaluate ranking metrics for a reranker over the constant candidate pool."""
    hit_counts = {k: 0 for k in ks}
    reciprocal_rank_sum = 0.0
    ndcg_sum = 0.0
    total = len(candidate_pool)

    for item in candidate_pool:
        question = item["question"]
        gold = set(item["gold_cids"])
        candidates = item["retrieved"]

        if model is None:
            # Baseline: no model reranker
            ranked = candidates[:top_k]
        else:
            ranked = rerank_with_cross_encoder(model, question, candidates, top_k=top_k)

        ranked_cids = [str(hit.get("cid", "")) for hit in ranked]
        ndcg_sum += ndcg_at_k(ranked_cids, gold, 10)

        for k in ks:
            hit = any(cid in gold for cid in ranked_cids[:k])
            hit_counts[k] += int(hit)

        for rank, cid in enumerate(ranked_cids, start=1):
            if cid in gold:
                reciprocal_rank_sum += 1.0 / rank
                break

    n = max(total, 1)
    metrics = {
        "samples": total,
        "mrr@10": round(reciprocal_rank_sum / n, 4),
        "ndcg@10": round(ndcg_sum / n, 4),
    }
    for k in ks:
        metrics[f"recall@{k}"] = round(hit_counts[k] / n, 4)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark public vs fine-tuned rerankers (Phase 3).")
    parser.add_argument("--qa-path", default="data/raw/yuitc/test.parquet", help="Test QA dataset.")
    parser.add_argument("--limit", type=int, default=300, help="Number of queries to evaluate.")
    parser.add_argument("--top-k", type=int, default=20, help="Top-K final ranked candidates.")
    parser.add_argument("--reranker-depth", type=int, default=50, help="Candidate pool depth to rerank.")
    parser.add_argument(
        "--ours-model-path",
        default="models/reranker-best",
        help="Path to our fine-tuned reranker model.",
    )
    parser.add_argument(
        "--public-models",
        nargs="+",
        default=["cross-encoder/ms-marco-MiniLM-L-6-v2", "BAAI/bge-reranker-v2-m3"],
        help="Public cross-encoder rerankers to test.",
    )
    parser.add_argument("--output-dir", default="results", help="Output directory.")
    parser.add_argument("--cache-dir", default="reports/.benchmark_cache", help="Cache directory.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate_cache = cache_dir / f"candidate_pool_hybrid_limit{args.limit}_depth{args.reranker_depth}.jsonl"
    pipeline = LegalQAPipeline.build()
    candidate_pool = load_or_generate_candidates(
        pipeline=pipeline,
        qa_path=args.qa_path,
        limit=args.limit,
        depth=args.reranker_depth,
        candidate_cache_path=candidate_cache,
    )

    try:
        from sentence_transformers.cross_encoder import CrossEncoder
    except ImportError as exc:
        raise SystemExit(f"sentence_transformers.cross_encoder import failed: {exc}") from exc

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    csv_rows = []
    all_results = []

    # 1. No reranker baseline
    print("\n--- Evaluating: No Reranker (Hybrid + QA-memory) ---")
    metrics_none = evaluate_reranker("No Reranker", None, candidate_pool, top_k=args.top_k)
    row_none = {
        "reranker": "Hybrid (No Reranker)",
        "model_name": "none",
        "fine_tuned": "No",
        "n_samples": len(candidate_pool),
        "r@5": metrics_none["recall@5"],
        "r@10": metrics_none["recall@10"],
        "mrr@10": metrics_none["mrr@10"],
        "ndcg@10": metrics_none["ndcg@10"],
        "timestamp": timestamp,
    }
    csv_rows.append(row_none)
    all_results.append({"name": "No Reranker", "metrics": metrics_none})
    print(f"Result: R@5={row_none['r@5']:.4f}, R@10={row_none['r@10']:.4f}, MRR={row_none['mrr@10']:.4f}, nDCG@10={row_none['ndcg@10']:.4f}")

    # 2. Public pretrained rerankers
    for pub_model in args.public_models:
        print(f"\n--- Evaluating Public Reranker: {pub_model} ---")
        try:
            model = CrossEncoder(pub_model, max_length=512)
            m = evaluate_reranker(pub_model, model, candidate_pool, top_k=args.top_k)
            row = {
                "reranker": f"Hybrid + Public ({Path(pub_model).name})",
                "model_name": pub_model,
                "fine_tuned": "No",
                "n_samples": len(candidate_pool),
                "r@5": m["recall@5"],
                "r@10": m["recall@10"],
                "mrr@10": m["mrr@10"],
                "ndcg@10": m["ndcg@10"],
                "timestamp": timestamp,
            }
            csv_rows.append(row)
            all_results.append({"name": pub_model, "metrics": m})
            print(f"Result: R@5={row['r@5']:.4f}, R@10={row['r@10']:.4f}, MRR={row['mrr@10']:.4f}, nDCG@10={row['ndcg@10']:.4f}")
        except Exception as exc:
            print(f"Warning: Could not evaluate public model {pub_model}: {exc}")

    # 3. Ours fine-tuned reranker
    ours_path = Path(args.ours_model_path)
    if ours_path.exists():
        print(f"\n--- Evaluating Ours Fine-tuned Reranker ({ours_path}) ---")
        model = CrossEncoder(str(ours_path), max_length=512)
        m = evaluate_reranker("Ours (reranker-best)", model, candidate_pool, top_k=args.top_k)
        row = {
            "reranker": "Hybrid + Ours Reranker",
            "model_name": str(ours_path),
            "fine_tuned": "Yes",
            "n_samples": len(candidate_pool),
            "r@5": m["recall@5"],
            "r@10": m["recall@10"],
            "mrr@10": m["mrr@10"],
            "ndcg@10": m["ndcg@10"],
            "timestamp": timestamp,
        }
        csv_rows.append(row)
        all_results.append({"name": "Ours Reranker", "metrics": m})
        print(f"Result: R@5={row['r@5']:.4f}, R@10={row['r@10']:.4f}, MRR={row['mrr@10']:.4f}, nDCG@10={row['ndcg@10']:.4f}")

    # Save CSV
    csv_path = output_dir / "reranker_benchmark.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"\nSaved CSV to: {csv_path}")

    # Save JSON
    json_path = output_dir / "reranker_benchmark.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON to: {json_path}")

    # Summary Table
    print("\n### Public Reranker Benchmark Table")
    print("| Method | Model | Fine-tuned | R@5 | R@10 | MRR@10 | nDCG@10 |")
    print("|---|---|---|---:|---:|---:|---:|")
    for r in csv_rows:
        print(f"| {r['reranker']} | {r['model_name']} | {r['fine_tuned']} | {r['r@5']:.4f} | {r['r@10']:.4f} | {r['mrr@10']:.4f} | {r['ndcg@10']:.4f} |")


if __name__ == "__main__":
    main()
