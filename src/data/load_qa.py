from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd


def load_qa_dataframe(path: str | Path) -> pd.DataFrame:
    dataframe = pd.read_parquet(path)
    expected = {"question", "qid", "cid"}
    missing = expected - set(dataframe.columns)
    if missing:
        raise ValueError(f"QA file missing columns: {sorted(missing)}")
    return dataframe


def load_qa_records(path: str | Path) -> list[dict]:
    dataframe = load_qa_dataframe(path)
    return dataframe.fillna("").to_dict(orient="records")


def parse_cids(raw_value: object) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, (list, tuple, set)):
        return [str(item) for item in raw_value]
    try:
        import numpy as np

        if isinstance(raw_value, np.ndarray):
            return [str(item) for item in raw_value.tolist()]
    except ImportError:  # pragma: no cover
        pass
    text = str(raw_value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        parsed = [text]
    if isinstance(parsed, (list, tuple, set)):
        return [str(item) for item in parsed]
    return [str(parsed)]


def parse_context_list(raw_value: object) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, (list, tuple, set)):
        return [str(item) for item in raw_value if str(item).strip()]
    text = str(raw_value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return [text]
    if isinstance(parsed, (list, tuple, set)):
        return [str(item) for item in parsed if str(item).strip()]
    return [str(parsed)]
