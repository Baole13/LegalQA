from __future__ import annotations

import _bootstrap

from src.indexing.artifacts import build_full_artifacts


def main() -> None:
    manifest = build_full_artifacts(force=True)
    print(f"Built {manifest['corpus_chunks']} corpus chunks.")
    print(f"Built {manifest['qa_memory_records']} QA memory records.")


if __name__ == "__main__":
    main()
