from __future__ import annotations

from src.utils.io import ensure_dir, save_jsonl


def build_hard_negatives(
    aligned_pairs: list[dict],
    retrieval_lookup: dict[str, list[dict]],
    output_path: str = "data/aligned/retriever_train.jsonl",
    negatives_per_query: int = 3,
) -> list[dict]:
    records: list[dict] = []
    reranker_records: list[dict] = []

    for pair in aligned_pairs:
        candidates = retrieval_lookup.get(pair["query"], [])
        negatives = [
            item
            for item in candidates
            if item["chunk_id"] != pair["positive_chunk_id"]
        ][:negatives_per_query]
        if not negatives:
            continue

        records.append(
            {
                "query": pair["query"],
                "positive": pair["positive_text"],
                "negatives": [item["text"] for item in negatives],
            }
        )

        reranker_records.append(
            {
                "query": pair["query"],
                "passage": pair["positive_text"],
                "label": 1,
                "positive_chunk_id": pair["positive_chunk_id"],
                "positive_cid": pair["positive_cid"],
            }
        )
        for item in negatives:
            reranker_records.append(
                {
                    "query": pair["query"],
                    "passage": item["text"],
                    "label": 0,
                    "negative_chunk_id": item["chunk_id"],
                    "negative_cid": item["cid"],
                }
            )

    ensure_dir("data/aligned")
    save_jsonl(output_path, records)
    save_jsonl("data/aligned/reranker_train.jsonl", reranker_records)
    return records
