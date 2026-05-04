from __future__ import annotations

from src.indexing.artifacts import build_full_artifacts


def build_index_manifest(force: bool = False) -> dict:
    return build_full_artifacts(force=force)
