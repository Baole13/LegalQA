from __future__ import annotations

from pathlib import Path

from src.utils.io import load_json, load_jsonl


def load_json_config(path: str | Path) -> dict:
    return load_json(path)


def load_training_records(path: str | Path, max_samples: int = 0) -> list[dict]:
    records = load_jsonl(path)
    if max_samples and max_samples > 0:
        return records[:max_samples]
    return records
