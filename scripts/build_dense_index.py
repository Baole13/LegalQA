from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import _bootstrap
from src.indexing.artifacts import IndexedArtifactStore
from src.utils.io import save_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a normalized FAISS index for neural dense retrieval.")
    parser.add_argument("--model-path", default="models/retriever-best")
    parser.add_argument("--index-path", default="data/indexes/corpus_dense_v1.faiss")
    parser.add_argument("--row-ids-path", default="data/indexes/corpus_dense_row_ids_v1.npy")
    parser.add_argument("--metadata-path", default="data/indexes/corpus_dense_v1.json")
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()

    try:
        import faiss
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Missing dense-index dependencies. Install requirements-runpod.txt.") from exc

    store = IndexedArtifactStore()
    model_path = Path(args.model_path)
    if not model_path.exists():
        raise SystemExit(f"Dense retriever model not found: {model_path}")
    model = SentenceTransformer(str(model_path))
    dimension = int(model.get_sentence_embedding_dimension())
    index = faiss.IndexFlatIP(dimension)

    row_ids: list[int] = []
    texts = [str(item.get("text", "")) for item in store.corpus_meta]
    for start in range(0, len(texts), args.batch_size):
        batch = texts[start : start + args.batch_size]
        embeddings = model.encode(
            batch, batch_size=args.batch_size, normalize_embeddings=True,
            convert_to_numpy=True, show_progress_bar=False,
        ).astype("float32", copy=False)
        if embeddings.ndim != 2 or embeddings.shape[1] != dimension:
            raise RuntimeError(f"Unexpected embedding shape: {embeddings.shape}; expected (*, {dimension})")
        index.add(embeddings)
        row_ids.extend(int(item["row_id"]) for item in store.corpus_meta[start : start + len(batch)])

    index_path = Path(args.index_path)
    row_ids_path = Path(args.row_ids_path)
    metadata_path = Path(args.metadata_path)
    for path in (index_path, row_ids_path, metadata_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))
    np.save(row_ids_path, np.asarray(row_ids, dtype=np.int64), allow_pickle=False)
    save_json(metadata_path, {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_path": model_path.as_posix(),
        "dimension": dimension,
        "metric": "cosine_via_normalized_inner_product",
        "corpus_chunks": len(row_ids),
        "artifact_version": int(store.manifest.get("version", -1)),
        "index_type": "IndexFlatIP",
    })
    print(f"Built dense index with {len(row_ids)} vectors at {index_path}")


if __name__ == "__main__":
    main()
