from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pandas as pd


def load_thangvip_dataframe(path: str | Path) -> pd.DataFrame:
    dataframe = pd.read_parquet(path)
    expected = {"article_content", "generated_qa_pairs"}
    missing = expected - set(dataframe.columns)
    if missing:
        raise ValueError(f"Thangvip dataset missing columns: {sorted(missing)}")
    return dataframe.fillna("")


def load_thangvip_qa_records(path: str | Path) -> list[dict[str, Any]]:
    dataframe = load_thangvip_dataframe(path)
    flattened: list[dict[str, Any]] = []
    for row_index, row in enumerate(dataframe.to_dict(orient="records")):
        qa_pairs = _parse_generated_pairs(row.get("generated_qa_pairs"))
        if not qa_pairs:
            continue
        article_content = str(row.get("article_content", "")).strip()
        if not article_content:
            continue
        for pair_index, pair in enumerate(qa_pairs):
            question = str(pair.get("question") or pair.get("query") or "").strip()
            answer = str(pair.get("answer") or pair.get("response") or "").strip()
            if not question or not answer:
                continue
            flattened.append(
                {
                    "record_id": f"thangvip-{row_index}-{pair_index}",
                    "source_row_index": row_index,
                    "pair_index": pair_index,
                    "doc_name": str(row.get("doc_name", "")).strip(),
                    "doc_type_name": str(row.get("doc_type_name", "")).strip(),
                    "article_content": article_content,
                    "question": question,
                    "answer": answer,
                    "question_type": str(pair.get("question_type") or pair.get("type") or "").strip().lower(),
                    "difficulty": str(pair.get("difficulty") or "").strip().lower(),
                }
            )
    return flattened


def load_thangvip_records(path: str | Path) -> list[dict[str, Any]]:
    return load_thangvip_qa_records(path)


def _parse_generated_pairs(raw_value: Any) -> list[dict[str, Any]]:
    if raw_value is None:
        return []
    try:
        import numpy as np

        if isinstance(raw_value, np.ndarray):
            return [item for item in raw_value.tolist() if isinstance(item, dict)]
    except ImportError:
        pass
    if isinstance(raw_value, list):
        return [item for item in raw_value if isinstance(item, dict)]
    if isinstance(raw_value, tuple):
        return [item for item in raw_value if isinstance(item, dict)]
    text = str(raw_value).strip()
    if not text:
        return []
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []
