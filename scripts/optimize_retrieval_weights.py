#!/usr/bin/env python3
"""
Optimize hybrid retrieval weights by sweeping through configurations.

Usage:
    PYTHONPATH=. python scripts/optimize_retrieval_weights.py --limit 300 --top-k 20
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import scripts._bootstrap as _bootstrap

from src.data.load_qa import load_qa_records, parse_cids
from src.evaluation.retrieval_eval import evaluate_retrieval, ndcg_at_k
from src.qa.pipeline import LegalQAPipeline
from src.utils.io import load_json, save_json


WEIGHT_CONFIGS = [
    {"name": "current", "merge_weights": {"bm25": 0.5, "dense": 0.3, "neural_dense": 0.9, "elasticsearch": 0.15, "rank_bonus": 0.35, "keyword_coverage": 0.2, "phrase_coverage": 0.35, "qa_boost": 0.8}},
    {"name": "bm25_heavy", "merge_weights": {"bm25": 0.7, "dense": 0.2, "neural_dense": 0.8, "elasticsearch": 0.1, "rank_bonus": 0.3, "keyword_coverage": 0.15, "phrase_coverage": 0.3, "qa_boost": 0.7}},
    {"name": "dense_heavy", "merge_weights": {"bm25": 0.3, "dense": 0.5, "neural_dense": 1.0, "elasticsearch": 0.1, "rank_bonus": 0.4, "keyword_coverage": 0.25, "phrase_coverage": 0.4, "qa_boost": 0.9}},
    {"name": "balanced_v2", "merge_weights": {"bm25": 0.4, "dense": 0.4, "neural_dense": 0.95, "elasticsearch": 0.1, "rank_bonus": 0.4, "keyword_coverage": 0.25, "phrase_coverage": 0.35, "qa_boost": 0.85}},
    {"name": "phrase_focused", "merge_weights": {"bm25": 0.35, "dense": 0.35, "neural_dense": 1.0, "elasticsearch": 0.05, "rank_bonus": 0.3, "keyword_coverage": 0.15, "phrase_coverage": 0.5, "qa_boost": 0.9}},
    {"name": "qa_boost_heavy", "merge_weights": {"bm25": 0.4, "dense": 0.3, "neural_dense": 0.9, "elasticsearch": 0.1, "rank_bonus": 0.35, "keyword_coverage": 0.2, "phrase_coverage": 0.3, "qa_boost": 1.2}},
    {"name": "rank_bonus_heavy", "merge_weights": {"bm25": 0.4, "dense": 0.3, "neural_dense": 0.9, "elasticsearch": 0.1, "rank_bonus": 0.5, "keyword_coverage": 0.2, "phrase_coverage": 0.35, "qa_boost": 0.8}},
    {"name": "keyword_focused", "merge_weights": {"bm25": 0.45, "dense": 0.25, "neural_dense": 0.85, "elasticsearch": 0.1, "rank_bonus": 0.3, "keyword_coverage": 0.4, "phrase_coverage": 0.25, "qa_boost": 0.7}},
    {"name": "no_elasticsearch", "merge_weights": {"bm25": 0.5, "dense": 0.3, "neural_dense": 0.9, "elasticsearch": 0.0, "rank_bonus": 0.35, "keyword_coverage": 0.2, "phrase_coverage": 0.35, "qa_boost": 0.8}},
    {"name": "procedural_penalty_varied", "merge_weights": {"bm25": 0.5, "dense": 0.3, "neural_dense": 0.9, "elasticsearch": 0.15, "rank_bonus": 0.35, "keyword_coverage": 0.2, "phrase_coverage": 0.35, "qa_boost": 0.8, "procedural_noise_penalty": 0.3}},
]

QA_MEMORY_CONFIGS = [
    {"name": "current", "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.6, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 2}},
    {"name": "more_seeds", "qa_memory": {"top_k": 15, "seed_top_hits": 8, "seed_score_threshold": 0.55, "seed_cids_per_hit": 3, "seed_chunks_per_cid": 2}},
    {"name": "fewer_seeds", "qa_memory": {"top_k": 10, "seed_top_hits": 4, "seed_score_threshold": 0.65, "seed_cids_per_hit": 1, "seed_chunks_per_cid": 2}},
    {"name": "lower_threshold", "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.5, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 2}},
    {"name": "higher_threshold", "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.7, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 2}},
    {"name": "more_chunks_per_cid", "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.6, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 3}},
]


def run_single_config(
    pipeline: LegalQAPipeline,
    weight_config: dict,
    qa_config: dict,
    qa_path: str,
    limit: int,
    top_k: int,
    ks: tuple[int, ...],
) -> dict:
    base_config = load_json("configs/serving/retrieval.hybrid.json")
    test_config = copy.deepcopy(base_config)
    test_config["merge_weights"] = weight_config["merge_weights"]
    test_config["qa_memory"] = qa_config["qa_memory"]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(test_config, f)
        config_path = f.name

    try:
        test_retriever = pipeline.artifacts.retriever.__class__(
            pipeline.artifacts.store,
            retriever_model_path=pipeline.serving_config.retriever_model_path,
            retrieval_config_path=config_path,
        )
    finally:
        os.unlink(config_path)

    records = load_qa_records(qa_path)[:limit]
    hit_counts = {k: 0 for k in ks}
    covered_hit_counts = {k: 0 for k in ks}
    reciprocal_rank_sum = 0.0
    covered_reciprocal_rank_sum = 0.0
    covered_questions = 0
    questions_without_gold_in_index = 0
    ndcg_sum = 0.0

    indexed_cids = {str(item["cid"]) for item in pipeline.artifacts.store.corpus_meta}

    for record in records:
        gold_cids = set(parse_cids(record.get("cid", "")))
        if not gold_cids:
            continue

        gold_in_index = any(cid in indexed_cids for cid in gold_cids)
        if gold_in_index:
            covered_questions += 1
        else:
            questions_without_gold_in_index += 1

        results = test_retriever.search(record["question"], top_k=top_k)
        ranked_cids = [str(item["cid"]) for item in results]
        ndcg_sum += ndcg_at_k(ranked_cids, gold_cids, 10)

        for k in ks:
            hit = any(cid in gold_cids for cid in ranked_cids[:k])
            if hit:
                hit_counts[k] += 1
            if gold_in_index and hit:
                covered_hit_counts[k] += 1

        for rank, cid in enumerate(ranked_cids, start=1):
            if cid in gold_cids:
                reciprocal_rank_sum += 1.0 / rank
                if gold_in_index:
                    covered_reciprocal_rank_sum += 1.0 / rank
                break

    total = max(len(records), 1)
    covered_total = max(covered_questions, 1)

    return {
        "weight_config": weight_config["name"],
        "qa_config": qa_config["name"],
        "samples": len(records),
        "top_k": top_k,
        "gold_coverage_in_index": round(covered_questions / total, 4),
        "mrr": round(reciprocal_rank_sum / total, 4),
        "conditional_mrr": round(covered_reciprocal_rank_sum / covered_total, 4),
        "ndcg@10": round(ndcg_sum / total, 4),
        **{f"recall@{k}": round(hit_counts[k] / total, 4) for k in ks},
        **{f"conditional_recall@{k}": round(covered_hit_counts[k] / covered_total, 4) for k in ks},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize hybrid retrieval weights")
    parser.add_argument("--qa-path", default="data/raw/yuitc/test.parquet")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--output", default="reports/retrieval_weight_optimization.json")
    args = parser.parse_args()

    pipeline = LegalQAPipeline.build()
    pipeline.artifacts.retriever.neural_dense.ensure_available()

    ks = (1, 5, 10, 20)
    all_results = []

    for weight_config in WEIGHT_CONFIGS:
        for qa_config in QA_MEMORY_CONFIGS:
            print(f"Testing {weight_config['name']} + {qa_config['name']}...")
            result = run_single_config(
                pipeline, weight_config, qa_config, args.qa_path, args.limit, args.top_k, ks
            )
            all_results.append(result)
            print(f"  recall@1: {result['recall@1']:.4f}, recall@5: {result['recall@5']:.4f}, mrr: {result['mrr']:.4f}")

    best = max(all_results, key=lambda r: r["recall@5"])
    print(f"\nBest config: {best['weight_config']} + {best['qa_config']}")
    print(f"  recall@1: {best['recall@1']:.4f}, recall@5: {best['recall@5']:.4f}, mrr: {best['mrr']:.4f}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(output_path, {"results": all_results, "best": best})
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()