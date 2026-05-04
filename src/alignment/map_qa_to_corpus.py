from __future__ import annotations

from src.data.load_qa import load_qa_records, parse_cids
from src.qa.pipeline import LegalQAPipeline
from src.utils.io import ensure_dir, save_jsonl


def build_aligned_pairs(
    pipeline: LegalQAPipeline,
    qa_path: str = "data/train.parquet",
    limit: int = 1000,
    top_k: int = 20,
    output_path: str = "data/aligned/aligned_pairs.jsonl",
) -> list[dict]:
    records = load_qa_records(qa_path)[:limit]
    aligned: list[dict] = []

    for record in records:
        gold_cids = set(parse_cids(record.get("cid", "")))
        if not gold_cids:
            continue
        results = pipeline.retrieval_debug(record["question"], top_k=top_k)["results"]
        positive = next((item for item in results if str(item["cid"]) in gold_cids), None)
        if positive is None:
            continue
        aligned.append(
            {
                "qa_id": str(record.get("qid", "")),
                "query": record["question"],
                "answer": "",
                "gold_cids": sorted(gold_cids),
                "positive_chunk_id": positive["chunk_id"],
                "positive_cid": positive["cid"],
                "positive_text": positive["text"],
            }
        )

    ensure_dir("data/aligned")
    save_jsonl(output_path, aligned)
    return aligned
