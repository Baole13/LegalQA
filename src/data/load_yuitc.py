from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pandas as pd


_QUESTION_COLUMNS = ("question", "query")
_POSITIVE_CONTEXT_COLUMNS = (
    "context_list",
    "context",
    "article_content",
    "relevant_context",
    "positive_context",
    "answer_context",
)
_CID_COLUMNS = ("cid", "gold_cid", "positive_cid", "context_id")
_DOC_NAME_COLUMNS = ("doc_name", "title", "document_title")


def load_yuitc_dataframe(path: str | Path) -> pd.DataFrame:
    dataframe = pd.read_parquet(path)
    question_column = _first_available_column(dataframe.columns, _QUESTION_COLUMNS)
    context_column = _first_available_column(dataframe.columns, _POSITIVE_CONTEXT_COLUMNS)
    if question_column is None or context_column is None:
        raise ValueError(
            "YuITC dataset must contain a question column and a positive context column. "
            f"Questions tried: {list(_QUESTION_COLUMNS)}, contexts tried: {list(_POSITIVE_CONTEXT_COLUMNS)}"
        )
    return dataframe.fillna("")


def load_yuitc_retrieval_records(path: str | Path) -> list[dict[str, Any]]:
    dataframe = load_yuitc_dataframe(path)
    question_column = _first_available_column(dataframe.columns, _QUESTION_COLUMNS)
    context_column = _first_available_column(dataframe.columns, _POSITIVE_CONTEXT_COLUMNS)
    cid_column = _first_available_column(dataframe.columns, _CID_COLUMNS)
    doc_name_column = _first_available_column(dataframe.columns, _DOC_NAME_COLUMNS)

    records: list[dict[str, Any]] = []
    for row_index, row in enumerate(dataframe.to_dict(orient="records")):
        question = str(row.get(question_column or "", "")).strip()
        positive_context = _extract_positive_context(row.get(context_column or ""))
        if not question or not positive_context:
            continue
        records.append(
            {
                "query_id": str(row.get("qid") or row.get("query_id") or f"yuitc-{row_index}"),
                "question": question,
                "positive_context": positive_context,
                "positive_cids": _parse_list_like(row.get(cid_column or "")),
                "doc_name": str(row.get(doc_name_column or "", "")).strip(),
                "metadata": _json_safe_dict(
                    {
                        key: value
                        for key, value in row.items()
                        if key not in {question_column, context_column}
                    }
                ),
            }
        )
    return records


def _first_available_column(columns: Any, candidates: tuple[str, ...]) -> str | None:
    available = set(columns)
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


def _parse_list_like(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    try:
        import numpy as np

        if isinstance(raw_value, np.ndarray):
            return [str(item) for item in raw_value.tolist() if str(item).strip()]
    except ImportError:
        pass
    if isinstance(raw_value, (list, tuple, set)):
        return [str(item) for item in raw_value if str(item).strip()]
    text = str(raw_value).strip()
    if not text:
        return []
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, (list, tuple, set)):
            return [str(item) for item in parsed if str(item).strip()]
    return [text]


def _extract_positive_context(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    if isinstance(raw_value, str):
        return raw_value.strip()
    values = _parse_list_like(raw_value)
    if values:
        return values[0].strip()
    try:
        import numpy as np

        if isinstance(raw_value, np.ndarray):
            flattened = [str(item).strip() for item in raw_value.tolist() if str(item).strip()]
            return flattened[0] if flattened else ""
    except ImportError:
        pass
    return str(raw_value).strip()


def _json_safe_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe_value(value) for key, value in data.items()}


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return _json_safe_dict(value)
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return [_json_safe_value(item) for item in value.tolist()]
    except ImportError:
        pass
    return str(value)
