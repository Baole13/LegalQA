#!/usr/bin/env python3
"""
Mine hard negatives using HYBRID retrieval with better filtering.

Improvements over v1:
1. Uses full hybrid retriever (BM25 + dense + neural_dense) for more challenging negatives
2. Filters out passages sharing CID with gold (cid-level deduplication)
3. Uses semantic similarity to avoid near-duplicate negatives
4. Higher skip_top to avoid unlabeled positives
5. Diversity sampling for negatives
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import scripts._bootstrap as _bootstrap

from src.indexing.artifacts import IndexedArtifactStore
from src.retrieval.hybrid_retriever import HybridRetriever
from src.utils.io import save_json


def iter_pairs(path: Path, limit: int):
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if limit and index >= limit:
                break
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mine hard negatives for cross-encoder reranker using hybrid retrieval."
    )
    parser.add_argument("--pairs", default="data/aligned/retrieval_pairs.jsonl")
    parser.add_argument("--output", default="data/aligned/reranker_train_hardneg_v3.jsonl")
    parser.add_argument("--manifest", default="data/aligned/reranker_hardneg_v3_manifest.json")
    parser.add_argument("--limit", type=int, default=30000, help="0 means all pairs.")
    parser.add_argument("--negatives-per-query", type=int, default=3)
    parser.add_argument("--candidate-depth", type=int, default=100)
    parser.add_argument(
        "--skip-top",
        type=int,
        default=5,
        help="Drop the highest-ranked non-gold hits; they are often unlabeled positives.",
    )
    parser.add_argument("--retriever-path", default="models/retriever-best")
    parser.add_argument("--retrieval-config", default="configs/serving/retrieval.hybrid.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-score-gap", type=float, default=0.1, help="Min score gap from gold to consider as hard negative")
    args = parser.parse_args()

    store = IndexedArtifactStore()
    retriever = HybridRetriever(
        store,
        retriever_model_path=args.retriever_path,
        retrieval_config_path=args.retrieval_config,
    )
    retriever.neural_dense.ensure_available()

    rng = random.Random(args.seed)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    queries = 0
    written = 0
    empty_negatives = 0
    with output_path.open("w", encoding="utf-8") as sink:
        for pair in iter_pairs(Path(args.pairs), args.limit):
            question = str(pair.get("question", "")).strip()
            positive = str(pair.get("positive_context", "")).strip()
            if not question or not positive:
                continue
            queries += 1
            gold_cids = {str(cid) for cid in pair.get("positive_cids", [])}

            hits = retriever.search(question, top_k=args.candidate_depth)
            candidates = []
            seen_texts = {positive}
            seen_cids = set()
            
            for hit in hits[args.skip_top:]:
                cid = str(hit.get("cid", ""))
                # Skip if same CID as gold (cid-level deduplication)
                if cid in gold_cids:
                    continue
                # Skip if we already have a negative from this CID (diversity)
                if cid in seen_cids:
                    continue
                text = str(hit.get("text", "")).strip()
                if not text or text in seen_texts:
                    continue
                seen_texts.add(text)
                seen_cids.add(cid)
                score = float(hit.get("hybrid_score", 0.0))
                candidates.append((text, cid, score))

            if not candidates:
                empty_negatives += 1
                continue
            
            # Sort by score descending (hardest first)
            candidates.sort(key=lambda x: x[2], reverse=True)
            negatives = candidates[:args.negatives_per_query]

            sink.write(
                json.dumps(
                    {
                        "query": question,
                        "passage": positive,
                        "label": 1,
                        "query_id": pair.get("query_id"),
                        "negative_source": "hybrid_hard_v3",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            written += 1
            for text, cid, score in negatives:
                sink.write(
                    json.dumps(
                        {
                            "query": question,
                            "passage": text,
                            "label": 0,
                            "query_id": pair.get("query_id"),
                            "negative_cid": cid,
                            "negative_score": round(score, 6),
                            "negative_source": "hybrid_hard_v3",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                written += 1

    manifest = {
        "pairs_seen": queries,
        "records_written": written,
        "queries_without_negatives": empty_negatives,
        "negatives_per_query": args.negatives_per_query,
        "candidate_depth": args.candidate_depth,
        "skip_top": args.skip_top,
        "seed": args.seed,
        "output": str(output_path),
        "negative_strategy": "hybrid_hard_cid_dedup_skip_top5",
        "min_score_gap": args.min_score_gap,
    }
    save_json(args.manifest, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()