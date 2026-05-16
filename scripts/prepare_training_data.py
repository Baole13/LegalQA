from __future__ import annotations

import _bootstrap

from src.alignment.hard_negative_mining import build_hard_negatives
from src.alignment.map_qa_to_corpus import build_aligned_pairs
from src.indexing.artifacts import build_full_artifacts
from src.qa.pipeline import LegalQAPipeline
from src.training.raft import build_raft_training_records


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
    raft_records = build_raft_training_records(aligned, lookup)
    print(f"Aligned pairs: {len(aligned)}")
    print(f"Retriever train records: {len(negatives)}")
    print(f"RAFT SFT records: {len(raft_records)}")
    print("Saved: data/aligned/aligned_pairs.jsonl")
    print("Saved: data/aligned/retriever_train.jsonl")
    print("Saved: data/aligned/reranker_train.jsonl")
    print("Saved: data/aligned/raft_sft.jsonl")


if __name__ == "__main__":
    main()
