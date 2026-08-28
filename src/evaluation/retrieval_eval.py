from __future__ import annotations

import math
from pathlib import Path

from src.data.load_qa import load_qa_records, parse_cids
from src.qa.pipeline import LegalQAPipeline


def ndcg_at_k(ranked_cids: list[str], gold_cids: set[str], k: int) -> float:
    """
    Binary-relevance nDCG@k over deduplicated citation IDs.

    Chunks are deduplicated by cid first: the corpus stores several chunks per
    citation, so an un-deduplicated ranking would credit the same gold citation
    at multiple positions.
    """
    seen: set[str] = set()
    deduped: list[str] = []
    for cid in ranked_cids:
        if cid not in seen:
            seen.add(cid)
            deduped.append(cid)

    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, cid in enumerate(deduped[:k], start=1)
        if cid in gold_cids
    )
    ideal_hits = min(len(gold_cids), k)
    if ideal_hits == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg


def evaluate_retrieval(
    pipeline: LegalQAPipeline,
    qa_path: str = "data/test.parquet",
    limit: int = 200,
    top_k: int = 10,
    ks: tuple[int, ...] = (1, 5, 10, 20),
) -> dict:
    records = load_qa_records(qa_path)[:limit]
    hit_counts = {k: 0 for k in ks}
    covered_hit_counts = {k: 0 for k in ks}
    reciprocal_rank_sum = 0.0
    covered_reciprocal_rank_sum = 0.0
    covered_questions = 0
    questions_without_gold_in_index = 0

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

        results = pipeline.retrieval_debug(record["question"], top_k=top_k)["results"]
        ranked_cids = [str(item["cid"]) for item in results]
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
    metrics = {
        "qa_path": str(Path(qa_path)),
        "samples": len(records),
        "indexed_chunks": len(pipeline.artifacts.store.corpus_meta),
        "indexed_unique_cids": len(indexed_cids),
        "gold_coverage_in_index": round(covered_questions / total, 4),
        "questions_with_gold_in_index": covered_questions,
        "questions_without_gold_in_index": questions_without_gold_in_index,
        "mrr": round(reciprocal_rank_sum / total, 4),
        "conditional_mrr": round(covered_reciprocal_rank_sum / covered_total, 4),
    }
    for k in ks:
        metrics[f"recall@{k}"] = round(hit_counts[k] / total, 4)
        metrics[f"conditional_recall@{k}"] = round(covered_hit_counts[k] / covered_total, 4)
    return metrics
