from __future__ import annotations

from src.alignment.hard_negative_mining import build_hard_negatives
from src.alignment.map_qa_to_corpus import build_aligned_pairs
from src.qa.pipeline import LegalQAPipeline


def main() -> None:
    pipeline = LegalQAPipeline.build()
    aligned = build_aligned_pairs(pipeline)
    lookup = {
        pair["query"]: pipeline.retrieval_debug(pair["query"], top_k=20)["results"]
        for pair in aligned
    }
    negatives = build_hard_negatives(aligned, lookup)
    print(f"Aligned pairs: {len(aligned)}")
    print(f"Retriever train records: {len(negatives)}")


if __name__ == "__main__":
    main()
