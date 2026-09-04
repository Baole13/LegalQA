#!/usr/bin/env python3
"""
Cached retrieval weight optimization - reuses loaded models across configs.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import scripts._bootstrap as _bootstrap

from src.data.load_qa import load_qa_records, parse_cids
from src.evaluation.retrieval_eval import ndcg_at_k
from src.qa.pipeline import LegalQAPipeline
from src.retrieval.hybrid_retriever import HybridRetriever
from src.utils.io import load_json, save_json


FOCUSED_CONFIGS = [
    {"name": "current", "merge_weights": {"bm25": 0.5, "dense": 0.3, "neural_dense": 0.9, "elasticsearch": 0.15, "rank_bonus": 0.35, "keyword_coverage": 0.2, "phrase_coverage": 0.35, "qa_boost": 0.8}, "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.6, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 2}},
    {"name": "dense_heavy", "merge_weights": {"bm25": 0.3, "dense": 0.5, "neural_dense": 1.0, "elasticsearch": 0.1, "rank_bonus": 0.4, "keyword_coverage": 0.25, "phrase_coverage": 0.4, "qa_boost": 0.9}, "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.6, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 2}},
    {"name": "phrase_focused", "merge_weights": {"bm25": 0.35, "dense": 0.35, "neural_dense": 1.0, "elasticsearch": 0.05, "rank_bonus": 0.3, "keyword_coverage": 0.15, "phrase_coverage": 0.5, "qa_boost": 0.9}, "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.6, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 2}},
    {"name": "qa_boost_heavy", "merge_weights": {"bm25": 0.4, "dense": 0.3, "neural_dense": 0.9, "elasticsearch": 0.1, "rank_bonus": 0.35, "keyword_coverage": 0.2, "phrase_coverage": 0.3, "qa_boost": 1.2}, "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.6, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 2}},
    {"name": "rank_bonus_heavy", "merge_weights": {"bm25": 0.4, "dense": 0.3, "neural_dense": 0.9, "elasticsearch": 0.1, "rank_bonus": 0.5, "keyword_coverage": 0.2, "phrase_coverage": 0.35, "qa_boost": 0.8}, "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.6, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 2}},
    {"name": "more_qa_seeds", "merge_weights": {"bm25": 0.5, "dense": 0.3, "neural_dense": 0.9, "elasticsearch": 0.15, "rank_bonus": 0.35, "keyword_coverage": 0.2, "phrase_coverage": 0.35, "qa_boost": 0.8}, "qa_memory": {"top_k": 15, "seed_top_hits": 8, "seed_score_threshold": 0.55, "seed_cids_per_hit": 3, "seed_chunks_per_cid": 2}},
    {"name": "lower_qa_threshold", "merge_weights": {"bm25": 0.5, "dense": 0.3, "neural_dense": 0.9, "elasticsearch": 0.15, "rank_bonus": 0.35, "keyword_coverage": 0.2, "phrase_coverage": 0.35, "qa_boost": 0.8}, "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.5, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 2}},
    {"name": "more_chunks_per_cid", "merge_weights": {"bm25": 0.5, "dense": 0.3, "neural_dense": 0.9, "elasticsearch": 0.15, "rank_bonus": 0.35, "keyword_coverage": 0.2, "phrase_coverage": 0.35, "qa_boost": 0.8}, "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.6, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 3}},
    {"name": "balanced_v2", "merge_weights": {"bm25": 0.4, "dense": 0.4, "neural_dense": 0.95, "elasticsearch": 0.1, "rank_bonus": 0.4, "keyword_coverage": 0.25, "phrase_coverage": 0.35, "qa_boost": 0.85}, "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.6, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 2}},
    {"name": "no_elasticsearch", "merge_weights": {"bm25": 0.5, "dense": 0.3, "neural_dense": 0.9, "elasticsearch": 0.0, "rank_bonus": 0.35, "keyword_coverage": 0.2, "phrase_coverage": 0.35, "qa_boost": 0.8}, "qa_memory": {"top_k": 12, "seed_top_hits": 6, "seed_score_threshold": 0.6, "seed_cids_per_hit": 2, "seed_chunks_per_cid": 2}},
]


class CachedHybridRetriever:
    """Wrapper that reuses loaded components across different weight configs."""

    def __init__(self, base_retriever: HybridRetriever):
        self.base = base_retriever
        self.store = base_retriever.store
        self.config = base_retriever.config
        self.weights = base_retriever.weights
        self.qa_config = base_retriever.qa_config
        self.bm25 = base_retriever.bm25
        self.dense = base_retriever.dense
        self.neural_dense = base_retriever.neural_dense
        self.embedding_retriever = base_retriever.embedding_retriever
        self.embedding_ensemble = base_retriever.embedding_ensemble
        self.elasticsearch = base_retriever.elasticsearch

    def update_config(self, merge_weights: dict, qa_memory: dict):
        self.weights = merge_weights
        self.qa_config = qa_memory

    def search(self, query: str, top_k: int = 10, per_source_k: int = 120) -> list[dict]:
        from collections import defaultdict
        from src.utils.text import (
            direct_answer_score,
            expand_query,
            keyword_coverage_score,
            keyword_text,
            phrase_coverage_score,
            procedural_noise_score,
        )

        expanded_query = expand_query(query)
        per_source_k = int(per_source_k or self.config.get("per_source_k", 120))
        bm25_hits = self.bm25.search(expanded_query, top_k=per_source_k)
        dense_hits = self.dense.search(expanded_query, top_k=per_source_k)
        neural_dense_hits = self.neural_dense.search(query, top_k=per_source_k) if self.neural_dense.available() else []
        es_top_k = min(per_source_k, int((self.config.get("elasticsearch") or {}).get("top_k", 60)))
        es_hits = self.elasticsearch.search(expanded_query, top_k=es_top_k)
        qa_hits = self._search_similar_questions(expanded_query, top_k=int(self.qa_config.get("top_k", 12)))

        cid_boosts: dict[str, float] = defaultdict(float)
        for hit in qa_hits:
            for cid in hit["cids"]:
                cid_boosts[str(cid)] = max(float(hit["qa_score"]), cid_boosts[str(cid)])

        merged: dict[str, dict] = {}
        rank_bonus = defaultdict(float)

        for rank, item in enumerate(bm25_hits, start=1):
            key = item["chunk_id"]
            merged[key] = {**item, "sources": ["bm25"]}
            rank_bonus[key] += 1.0 / rank

        for rank, item in enumerate(dense_hits, start=1):
            key = item["chunk_id"]
            current = merged.get(key, {})
            merged[key] = {**current, **item, "sources": sorted(set((current.get("sources") or []) + ["char-dense"]))}
            rank_bonus[key] += 1.0 / rank
        for rank, item in enumerate(neural_dense_hits, start=1):
            key = item["chunk_id"]
            current = merged.get(key, {})
            merged[key] = {
                **current,
                **item,
                "sources": sorted(set((current.get("sources") or []) + ["neural-dense"])),
            }
            rank_bonus[key] += 1.0 / rank

        for rank, item in enumerate(es_hits, start=1):
            key = item["chunk_id"]
            current = merged.get(key, {})
            merged[key] = {**current, **item, "sources": sorted(set((current.get("sources") or []) + ["elasticsearch"]))}
            rank_bonus[key] += 1.0 / rank

        qa_seed_cids = [
            str(cid)
            for hit in qa_hits[: int(self.qa_config.get("seed_top_hits", 6))]
            if float(hit.get("qa_score", 0.0)) >= float(self.qa_config.get("seed_score_threshold", 0.6))
            for cid in (hit.get("cids") or [])[: int(self.qa_config.get("seed_cids_per_hit", 2))]
        ]
        for item in self.store.fetch_chunks_by_cids(
            qa_seed_cids,
            limit_per_cid=int(self.qa_config.get("seed_chunks_per_cid", 2)),
        ):
            key = item["chunk_id"]
            current = merged.get(key, {})
            merged[key] = {**item, **current, "sources": sorted(set((current.get("sources") or []) + ["qa-cid-seed"]))}

        results = []
        for key, item in merged.items():
            bm25_score = float(item.get("bm25_score", 0.0))
            dense_score = float(item.get("dense_score", 0.0))
            neural_dense_score = float(item.get("neural_dense_score", 0.0))
            es_score = float(item.get("es_score", 0.0))
            coverage = keyword_coverage_score(query, item.get("text", ""))
            phrase_coverage = phrase_coverage_score(query, item.get("text", ""))
            direct_score = direct_answer_score(query, item.get("text", ""))
            procedural_noise = procedural_noise_score(item.get("text", ""))
            raw_qa_boost = float(cid_boosts.get(str(item["cid"]), 0.0))
            qa_boost = raw_qa_boost * (0.25 + (0.55 * coverage) + (0.7 * phrase_coverage))
            fused = (
                (float(self.weights.get("bm25", 0.5)) * bm25_score)
                + (float(self.weights.get("dense", 0.3)) * dense_score)
                + (float(self.weights.get("neural_dense", 0.9)) * neural_dense_score)
                + (float(self.weights.get("elasticsearch", 0.15)) * es_score)
                + (float(self.weights.get("rank_bonus", 0.35)) * rank_bonus[key])
                + (float(self.weights.get("keyword_coverage", 0.2)) * coverage)
                + (float(self.weights.get("phrase_coverage", 0.35)) * phrase_coverage)
                + (float(self.weights.get("direct_answer", 0.6)) * direct_score)
                + (float(self.weights.get("qa_boost", 0.8)) * qa_boost)
                - (float(self.weights.get("procedural_noise_penalty", 0.15)) * procedural_noise)
            )
            results.append(
                {
                    **item,
                    "qa_boost": round(qa_boost, 6),
                    "es_score": round(es_score, 6),
                    "keyword_coverage": round(coverage, 4),
                    "phrase_coverage": round(phrase_coverage, 4),
                    "direct_answer_score": round(direct_score, 4),
                    "procedural_noise": round(procedural_noise, 4),
                    "hybrid_score": round(fused, 6),
                    "sources": item.get("sources") or ["bm25"],
                }
            )

        results.sort(key=lambda item: item["hybrid_score"], reverse=True)
        preselect_k = max(
            top_k * int(self.config.get("preselect_multiplier", 8)),
            int(self.config.get("preselect_min", 80)),
        )
        top_results = results[:preselect_k]
        texts = self.store.fetch_chunk_texts([int(item["row_id"]) for item in top_results])
        for item in top_results:
            item["text"] = texts.get(int(item["row_id"]), "")
        if not self.neural_dense.available():
            top_results = self.embedding_retriever.score_candidates(query, top_results)
        top_results = self.embedding_ensemble.score_candidates(query, top_results)
        top_results = self._limit_chunks_per_cid(
            top_results,
            top_k=top_k,
            max_chunks_per_cid=int(self.config.get("max_chunks_per_cid", 1)),
        )
        return top_results[:top_k]

    def _limit_chunks_per_cid(self, items: list[dict], top_k: int, max_chunks_per_cid: int = 1) -> list[dict]:
        from collections import defaultdict
        limited: list[dict] = []
        counts: dict[str, int] = defaultdict(int)
        for item in items:
            cid = str(item.get("cid"))
            if counts[cid] >= max_chunks_per_cid:
                continue
            counts[cid] += 1
            limited.append(item)
            if len(limited) >= top_k:
                break
        return limited

    def _search_similar_questions(self, query: str, top_k: int = 5) -> list[dict]:
        from src.retrieval.bm25_retriever import top_sparse_scores
        from src.utils.text import keyword_text

        vector = self.store.qa_vectorizer.transform([keyword_text(query)])
        hits = top_sparse_scores(self.store.qa_question_matrix, vector, top_k=top_k)
        return [
            {
                **self.store.qa_meta[row_id],
                "qa_score": round(score, 6),
            }
            for row_id, score in hits
        ]


def run_single_config(cached_retriever: CachedHybridRetriever, config: dict, qa_path: str, limit: int, top_k: int, ks: tuple[int, ...]) -> dict:
    cached_retriever.update_config(config["merge_weights"], config["qa_memory"])

    records = load_qa_records(qa_path)[:limit]
    hit_counts = {k: 0 for k in ks}
    covered_hit_counts = {k: 0 for k in ks}
    reciprocal_rank_sum = 0.0
    covered_reciprocal_rank_sum = 0.0
    covered_questions = 0
    questions_without_gold_in_index = 0
    ndcg_sum = 0.0

    indexed_cids = {str(item["cid"]) for item in cached_retriever.store.corpus_meta}

    for record in records:
        gold_cids = set(parse_cids(record.get("cid", "")))
        if not gold_cids:
            continue

        gold_in_index = any(cid in indexed_cids for cid in gold_cids)
        if gold_in_index:
            covered_questions += 1
        else:
            questions_without_gold_in_index += 1

        results = cached_retriever.search(record["question"], top_k=top_k)
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
        "name": config["name"],
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
    parser = argparse.ArgumentParser(description="Cached retrieval weight optimization")
    parser.add_argument("--qa-path", default="data/raw/yuitc/test.parquet")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--output", default="reports/retrieval_weight_optimization_cached.json")
    args = parser.parse_args()

    pipeline = LegalQAPipeline.build()
    pipeline.artifacts.retriever.neural_dense.ensure_available()

    # Wrap the retriever to cache loaded models
    cached_retriever = CachedHybridRetriever(pipeline.artifacts.retriever)

    ks = (1, 5, 10, 20)
    all_results = []

    for config in FOCUSED_CONFIGS:
        print(f"Testing {config['name']}...")
        result = run_single_config(cached_retriever, config, args.qa_path, args.limit, args.top_k, ks)
        all_results.append(result)
        print(f"  recall@1: {result['recall@1']:.4f}, recall@5: {result['recall@5']:.4f}, mrr: {result['mrr']:.4f}, ndcg@10: {result['ndcg@10']:.4f}")

    best = max(all_results, key=lambda r: r["recall@5"])
    print(f"\nBest config: {best['name']}")
    print(f"  recall@1: {best['recall@1']:.4f}, recall@5: {best['recall@5']:.4f}, mrr: {best['mrr']:.4f}, ndcg@10: {best['ndcg@10']:.4f}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(output_path, {"results": all_results, "best": best})
    print(f"\nSaved to {output_path}")

    # Print summary table
    print("\nSummary:")
    print(f"{'Config':<25} {'r@1':>6} {'r@5':>6} {'r@10':>6} {'r@20':>6} {'MRR':>6} {'nDCG@10':>7}")
    for r in all_results:
        print(f"{r['name']:<25} {r['recall@1']:>6.4f} {r['recall@5']:>6.4f} {r['recall@10']:>6.4f} {r['recall@20']:>6.4f} {r['mrr']:>6.4f} {r['ndcg@10']:>7.4f}")


if __name__ == "__main__":
    main()