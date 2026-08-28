from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from src.indexing.artifacts import IndexedArtifactStore
from src.retrieval.bm25_okapi_retriever import BM25OkapiRetriever
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
        description="Mine BM25 hard negatives for cross-encoder reranker training."
    )
    parser.add_argument("--pairs", default="data/aligned/retrieval_pairs.jsonl")
    parser.add_argument("--output", default="data/aligned/reranker_train_hardneg.jsonl")
    parser.add_argument("--manifest", default="data/aligned/reranker_hardneg_manifest.json")
    parser.add_argument("--limit", type=int, default=30000, help="0 means all pairs.")
    parser.add_argument("--negatives-per-query", type=int, default=3)
    parser.add_argument("--candidate-depth", type=int, default=30)
    parser.add_argument(
        "--skip-top",
        type=int,
        default=2,
        help="Drop the highest-ranked non-gold hits; they are often unlabeled positives.",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    store = IndexedArtifactStore()
    retriever = BM25OkapiRetriever(store)
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
            for hit in hits[args.skip_top :]:
                if str(hit.get("cid", "")) in gold_cids:
                    continue
                text = str(hit.get("text", "")).strip()
                if not text or text in seen_texts:
                    continue
                seen_texts.add(text)
                candidates.append((text, str(hit.get("cid", "")), float(hit.get("bm25_score", 0.0))))

            if not candidates:
                empty_negatives += 1
                continue
            rng.shuffle(candidates)
            negatives = candidates[: args.negatives_per_query]

            sink.write(
                json.dumps(
                    {
                        "query": question,
                        "passage": positive,
                        "label": 1,
                        "query_id": pair.get("query_id"),
                        "negative_source": "bm25_okapi_hard",
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
                            "negative_bm25_score": round(score, 6),
                            "negative_source": "bm25_okapi_hard",
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
        "negative_strategy": "bm25_okapi_top_ranked_non_gold",
    }
    save_json(args.manifest, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
