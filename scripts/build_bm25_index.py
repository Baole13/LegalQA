from __future__ import annotations

import argparse
import json

from src.indexing.artifacts import IndexedArtifactStore
from src.retrieval.bm25_okapi_retriever import DEFAULT_INDEX_DIR, build_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an Okapi BM25 index over the chunk corpus")
    parser.add_argument("--index-dir", default=str(DEFAULT_INDEX_DIR))
    parser.add_argument("--k1", type=float, default=1.5)
    parser.add_argument("--b", type=float, default=0.75)
    args = parser.parse_args()

    store = IndexedArtifactStore()
    manifest = build_index(store, index_dir=args.index_dir, k1=args.k1, b=args.b)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
