from __future__ import annotations

from src.alignment.hard_negative_mining import build_hard_negatives
from src.alignment.map_qa_to_corpus import build_aligned_pairs
from src.indexing.artifacts import build_full_artifacts
from src.qa.pipeline import LegalQAPipeline


def main() -> None:
    manifest = build_full_artifacts(force=False)
    print(f"Artifacts ready: {manifest['corpus_chunks']} chunks, {manifest['qa_memory_records']} QA-memory rows")

    pipeline = LegalQAPipeline.build()
    aligned = build_aligned_pairs(pipeline, limit=1000, top_k=30)
    lookup = {
        pair["query"]: pipeline.retrieval_debug(pair["query"], top_k=30)["results"]
        for pair in aligned
    }
    negatives = build_hard_negatives(aligned, lookup, negatives_per_query=4)
    print(f"Aligned pairs: {len(aligned)}")
    print(f"Retriever train records: {len(negatives)}")
    print("Saved: data/aligned/aligned_pairs.jsonl")
    print("Saved: data/aligned/retriever_train.jsonl")
    print("Saved: data/aligned/reranker_train.jsonl")


if __name__ == "__main__":
    main()
