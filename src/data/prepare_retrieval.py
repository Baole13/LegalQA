from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from src.utils.io import ensure_dir, save_json, save_jsonl


@dataclass(frozen=True)
class RetrievalBuildConfig:
    output_dir: str = "data/aligned"
    negatives_per_query: int = 3
    random_seed: int = 42
    max_samples: int = 0


def build_retrieval_training_sets(records: list[dict], config: RetrievalBuildConfig | None = None) -> dict[str, Path]:
    active_config = config or RetrievalBuildConfig()
    filtered = [record for record in records if record.get("question") and record.get("positive_context")]
    if active_config.max_samples and active_config.max_samples > 0:
        filtered = filtered[: active_config.max_samples]

    retriever_records, reranker_records = _build_training_records(filtered, active_config)
    output_dir = ensure_dir(active_config.output_dir)
    paths = {
        "retriever_train": output_dir / "retriever_train.jsonl",
        "reranker_train": output_dir / "reranker_train.jsonl",
        "retrieval_pairs": output_dir / "retrieval_pairs.jsonl",
        "manifest": output_dir / "retrieval_manifest.json",
    }

    save_jsonl(paths["retriever_train"], retriever_records)
    save_jsonl(paths["reranker_train"], reranker_records)
    save_jsonl(paths["retrieval_pairs"], filtered)
    save_json(
        paths["manifest"],
        {
            "records": len(filtered),
            "retriever_records": len(retriever_records),
            "reranker_records": len(reranker_records),
            "negatives_per_query": active_config.negatives_per_query,
        },
    )
    return paths


def _build_training_records(records: list[dict], config: RetrievalBuildConfig) -> tuple[list[dict], list[dict]]:
    rng = random.Random(config.random_seed)
    retriever_records: list[dict] = []
    reranker_records: list[dict] = []

    for index, record in enumerate(records):
        query = str(record["question"]).strip()
        positive = str(record["positive_context"]).strip()
        if not query or not positive:
            continue

        negatives = _select_bounded_negatives(records, index, positive, config.negatives_per_query, rng)
        if not negatives:
            continue

        retriever_records.append(
            {
                "query": query,
                "positive": positive,
                "negatives": negatives,
                "query_id": record.get("query_id"),
                "positive_cids": record.get("positive_cids", []),
                "doc_name": record.get("doc_name", ""),
            }
        )

        reranker_records.append(
            {
                "query": query,
                "passage": positive,
                "label": 1,
                "query_id": record.get("query_id"),
                "doc_name": record.get("doc_name", ""),
            }
        )
        for negative in negatives:
            reranker_records.append(
                {
                    "query": query,
                    "passage": negative,
                    "label": 0,
                    "query_id": record.get("query_id"),
                    "doc_name": record.get("doc_name", ""),
                }
            )

    return retriever_records, reranker_records


def _select_bounded_negatives(
    records: list[dict],
    anchor_index: int,
    positive: str,
    negatives_per_query: int,
    rng: random.Random,
) -> list[str]:
    if negatives_per_query <= 0 or len(records) <= 1:
        return []
    scan_limit = min(len(records) - 1, max(negatives_per_query * 16, 64))
    offsets = list(range(1, scan_limit + 1))
    rng.shuffle(offsets)
    negatives: list[str] = []
    seen = {positive}
    for offset in offsets:
        candidate = records[(anchor_index + offset) % len(records)]
        text = str(candidate.get("positive_context", "")).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        negatives.append(text)
        if len(negatives) >= negatives_per_query:
            break
    return negatives
