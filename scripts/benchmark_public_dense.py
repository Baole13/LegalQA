#!/usr/bin/env python3
"""Benchmark public dense embedding models vs fine-tuned legal retriever (Phase 2).

Evaluates models such as BAAI/bge-m3, multilingual-e5, and fine-tuned retriever-best
on the Vietnamese LegalQA retrieval task.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import csv
import datetime
import json
import random
from typing import Sequence

import numpy as np

from src.data.load_qa import load_qa_records, parse_cids
from src.evaluation.retrieval_eval import ndcg_at_k
from src.evaluation.significance import bootstrap_ci
from src.indexing.artifacts import IndexedArtifactStore


def get_query_prefix(model_name: str) -> str:
    """Return specific query prefix required by different model families."""
    lower = model_name.lower()
    if "bge" in lower:
        return "Represent this sentence for retrieval: "
    if "e5" in lower:
        return "query: "
    return ""


def get_passage_prefix(model_name: str) -> str:
    """Return specific passage prefix required by different model families."""
    lower = model_name.lower()
    if "e5" in lower:
        return "passage: "
    return ""


def ensure_dense_index(
    model_name: str,
    store: IndexedArtifactStore,
    cache_dir: Path,
    batch_size: int = 64,
    max_chunks: int = 0,
    force_reindex: bool = False,
) -> tuple[object, np.ndarray, object]:
    """Load or build a normalized FAISS index for the given embedding model."""
    try:
        import faiss
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            f"Missing dependencies (faiss or sentence_transformers): {exc}. "
            "Please run inside .venv with required packages installed."
        ) from exc

    slug = model_name.replace("/", "_").replace("\\", "_")
    index_path = cache_dir / f"dense_index_{slug}.faiss"
    row_ids_path = cache_dir / f"dense_row_ids_{slug}.npy"
    meta_path = cache_dir / f"dense_meta_{slug}.json"

    # If this is our retriever-best and standard index exists, reuse it
    if "retriever-best" in model_name and Path("data/indexes/corpus_dense_v1.faiss").exists() and not force_reindex and max_chunks == 0:
        print(f"Reusing existing canonical dense index from data/indexes/corpus_dense_v1.faiss")
        index = faiss.read_index("data/indexes/corpus_dense_v1.faiss")
        row_ids = np.load("data/indexes/corpus_dense_row_ids_v1.npy", allow_pickle=False)
        model = SentenceTransformer(model_name)
        return index, row_ids, model

    print(f"Loading SentenceTransformer model: {model_name}...")
    model = SentenceTransformer(model_name)
    dimension = int(model.get_sentence_embedding_dimension())

    if index_path.exists() and row_ids_path.exists() and not force_reindex:
        print(f"Loading cached FAISS index from {index_path}...")
        index = faiss.read_index(str(index_path))
        row_ids = np.load(str(row_ids_path), allow_pickle=False)
        return index, row_ids, model

    print(f"Building new FAISS index for {model_name} (dim={dimension})...")
    index = faiss.IndexFlatIP(dimension)
    row_ids_list: list[int] = []

    prefix = get_passage_prefix(model_name)
    all_chunks = store.corpus_meta
    if max_chunks > 0:
        all_chunks = all_chunks[:max_chunks]

    total_chunks = len(all_chunks)
    print(f"Encoding {total_chunks} chunks (batch_size={batch_size})...")

    texts = [prefix + str(item.get("text", "")) for item in all_chunks]
    for start in range(0, total_chunks, batch_size):
        batch_texts = texts[start : start + batch_size]
        emb = model.encode(
            batch_texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype("float32", copy=False)
        index.add(emb)
        row_ids_list.extend(int(item["row_id"]) for item in all_chunks[start : start + len(batch_texts)])

        if (start // batch_size) % 50 == 0 or (start + batch_size) >= total_chunks:
            print(f"  Processed {min(start + len(batch_texts), total_chunks)}/{total_chunks} chunks")

    row_ids_arr = np.asarray(row_ids_list, dtype=np.int64)
    faiss.write_index(index, str(index_path))
    np.save(str(row_ids_path), row_ids_arr, allow_pickle=False)
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "model_name": model_name,
                "dimension": dimension,
                "chunks": len(row_ids_arr),
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
            f,
            indent=2,
        )
    print(f"Saved FAISS index to {index_path}")
    return index, row_ids_arr, model


def evaluate_dense_model(
    model_name: str,
    records: list[dict],
    store: IndexedArtifactStore,
    cache_dir: Path,
    top_k: int = 20,
    batch_size: int = 64,
    max_chunks: int = 0,
    force_reindex: bool = False,
    ks: tuple[int, ...] = (1, 5, 10, 20),
) -> tuple[dict, list[dict]]:
    index, row_ids, model = ensure_dense_index(
        model_name=model_name,
        store=store,
        cache_dir=cache_dir,
        batch_size=batch_size,
        max_chunks=max_chunks,
        force_reindex=force_reindex,
    )

    query_prefix = get_query_prefix(model_name)
    hit_counts = {k: 0 for k in ks}
    reciprocal_rank_sum = 0.0
    ndcg_sum = 0.0
    details: list[dict] = []
    indexed_cids = {str(item["cid"]) for item in store.corpus_meta}

    print(f"Evaluating {len(records)} test queries for {model_name}...")
    for idx, rec in enumerate(records):
        question = str(rec.get("question", ""))
        gold_cids = set(parse_cids(rec.get("cid", "")))
        if not gold_cids:
            continue

        prefixed_q = query_prefix + question
        q_emb = model.encode(
            [prefixed_q],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype("float32", copy=False)

        scores, positions = index.search(q_emb, min(top_k, len(row_ids)))
        ranked_cids = []
        retrieved_items = []
        for rank, (score, pos) in enumerate(zip(scores[0], positions[0]), start=1):
            if int(pos) < 0:
                continue
            r_id = int(row_ids[int(pos)])
            meta = store.corpus_meta[r_id]
            cid_str = str(meta["cid"])
            ranked_cids.append(cid_str)
            retrieved_items.append(
                {
                    "rank": rank,
                    "cid": cid_str,
                    "chunk_id": meta.get("chunk_id"),
                    "title": meta.get("title"),
                    "score": float(score),
                }
            )

        ndcg_sum += ndcg_at_k(ranked_cids, gold_cids, 10)
        for k in ks:
            hit = any(cid in gold_cids for cid in ranked_cids[:k])
            hit_counts[k] += int(hit)

        for rank, cid in enumerate(ranked_cids, start=1):
            if cid in gold_cids:
                reciprocal_rank_sum += 1.0 / rank
                break

        details.append(
            {
                "sample_index": idx,
                "question": question,
                "gold_cids": sorted(gold_cids),
                "retrieved": retrieved_items,
            }
        )

    n = max(len(records), 1)
    metrics = {
        "model": model_name,
        "samples": len(records),
        "mrr@10": round(reciprocal_rank_sum / n, 4),
        "ndcg@10": round(ndcg_sum / n, 4),
    }
    for k in ks:
        metrics[f"recall@{k}"] = round(hit_counts[k] / n, 4)

    return metrics, details


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark public dense models vs fine-tuned.")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["models/retriever-best", "BAAI/bge-m3", "intfloat/multilingual-e5-base"],
        help="List of model names or local paths to evaluate.",
    )
    parser.add_argument(
        "--qa-path", default="data/raw/yuitc/test.parquet", help="Path to QA test dataset."
    )
    parser.add_argument("--limit", type=int, default=300, help="Number of queries to evaluate.")
    parser.add_argument("--top-k", type=int, default=20, help="Top-K candidates.")
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding batch size.")
    parser.add_argument(
        "--max-corpus-chunks",
        type=int,
        default=0,
        help="Limit number of chunks for faster testing (0 = full corpus).",
    )
    parser.add_argument(
        "--output-dir", default="results", help="Directory for output CSV and JSON."
    )
    parser.add_argument(
        "--cache-dir",
        default="reports/.benchmark_cache",
        help="Directory to cache FAISS indexes.",
    )
    parser.add_argument("--force-reindex", action="store_true", help="Force rebuilding FAISS index.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    store = IndexedArtifactStore()
    records = load_qa_records(args.qa_path)[: args.limit]
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    csv_rows = []
    all_metrics = []

    print(f"=== Vietnamese LegalQA Public Dense Benchmark ===")
    print(f"Test Queries: {len(records)} | Models to evaluate: {args.models}")

    for model_name in args.models:
        is_fine_tuned = "retriever-best" in model_name or "legal" in model_name.lower()
        print(f"\n--- Testing {model_name} (fine_tuned={is_fine_tuned}) ---")
        metrics, details = evaluate_dense_model(
            model_name=model_name,
            records=records,
            store=store,
            cache_dir=cache_dir,
            top_k=args.top_k,
            batch_size=args.batch_size,
            max_chunks=args.max_corpus_chunks,
            force_reindex=args.force_reindex,
        )

        row = {
            "model": model_name,
            "fine_tuned": "Yes" if is_fine_tuned else "No",
            "n_samples": len(records),
            "r@1": metrics.get("recall@1", 0.0),
            "r@5": metrics.get("recall@5", 0.0),
            "r@10": metrics.get("recall@10", 0.0),
            "r@20": metrics.get("recall@20", 0.0),
            "mrr@10": metrics.get("mrr@10", 0.0),
            "ndcg@10": metrics.get("ndcg@10", 0.0),
            "timestamp": timestamp,
        }
        csv_rows.append(row)
        all_metrics.append({"metrics": metrics, "model": model_name, "fine_tuned": is_fine_tuned})

        print(
            f"Result: R@1={row['r@1']:.4f}, R@5={row['r@5']:.4f}, "
            f"R@10={row['r@10']:.4f}, MRR@10={row['mrr@10']:.4f}, nDCG@10={row['ndcg@10']:.4f}"
        )

    csv_path = output_dir / "retrieval_public_benchmark.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"\nSaved CSV to: {csv_path}")

    json_path = output_dir / "retrieval_public_benchmark.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON to: {json_path}")

    print("\n### Public Dense Retriever Benchmark Table")
    print("| Dense Model | Fine-tuned | R@5 | R@10 | MRR@10 | nDCG@10 |")
    print("|---|---|---:|---:|---:|---:|")
    for r in csv_rows:
        print(
            f"| {r['model']} | {r['fine_tuned']} | {r['r@5']:.4f} | "
            f"{r['r@10']:.4f} | {r['mrr@10']:.4f} | {r['ndcg@10']:.4f} |"
        )


if __name__ == "__main__":
    main()
