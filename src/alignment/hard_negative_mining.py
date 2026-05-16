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
        negatives = []
        seen_negative_keys: set[tuple[str, str]] = set()
        positive_cid = str(pair.get("positive_cid", ""))

        for item in candidates:
            candidate_key = (str(item.get("cid")), str(item.get("chunk_id")))
            if item["chunk_id"] == pair["positive_chunk_id"]:
                continue
            if str(item.get("cid")) == positive_cid:
                continue
            if candidate_key in seen_negative_keys:
                continue
            seen_negative_keys.add(candidate_key)
            negatives.append(item)
            if len(negatives) >= negatives_per_query:
                break

        if not negatives:
            continue

        records.append(
            {
                "query": pair["query"],
                "positive": pair["positive_text"],
                "negatives": [item["text"] for item in negatives],
                "negative_chunk_ids": [item["chunk_id"] for item in negatives],
                "negative_cids": [item["cid"] for item in negatives],
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
                    "negative_sources": item.get("sources", []),
                    "negative_hybrid_score": item.get("hybrid_score", 0.0),
                }
            )

    ensure_dir("data/aligned")
    save_jsonl(output_path, records)
    save_jsonl("data/aligned/reranker_train.jsonl", reranker_records)
    return records
