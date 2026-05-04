from __future__ import annotations

from pathlib import Path

from src.data.load_qa import load_qa_records, parse_cids
from src.qa.pipeline import LegalQAPipeline


def evaluate_retrieval(
    pipeline: LegalQAPipeline,
    qa_path: str = "data/test.parquet",
    limit: int = 200,
    top_k: int = 10,
) -> dict:
    records = load_qa_records(qa_path)[:limit]
    hits_at_5 = 0
    hits_at_10 = 0
    reciprocal_rank_sum = 0.0

    for record in records:
        gold_cids = set(parse_cids(record.get("cid", "")))
        results = pipeline.retrieval_debug(record["question"], top_k=top_k)["results"]
        ranked_cids = [str(item["cid"]) for item in results]
        if any(cid in gold_cids for cid in ranked_cids[:5]):
            hits_at_5 += 1
        if any(cid in gold_cids for cid in ranked_cids[:10]):
            hits_at_10 += 1
        for rank, cid in enumerate(ranked_cids, start=1):
            if cid in gold_cids:
                reciprocal_rank_sum += 1.0 / rank
                break

    total = max(len(records), 1)
    return {
        "qa_path": str(Path(qa_path)),
        "samples": len(records),
        "recall@5": round(hits_at_5 / total, 4),
        "recall@10": round(hits_at_10 / total, 4),
        "mrr": round(reciprocal_rank_sum / total, 4),
    }
