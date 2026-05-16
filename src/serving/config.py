from __future__ import annotations

import os
from dataclasses import dataclass

from src.utils.io import load_json


@dataclass
class ServingConfig:
    use_llm_reasoning: bool
    llm_config_path: str
    reranker_model_path: str
    retriever_model_path: str
    retriever_config_path: str


def load_serving_config(path: str = "configs/serving/serving.json") -> ServingConfig:
    payload = load_json(path)
    return ServingConfig(
        use_llm_reasoning=bool(int(os.getenv("LEGAL_QA_USE_LLM_REASONING", "1")) if os.getenv("LEGAL_QA_USE_LLM_REASONING") else payload.get("use_llm_reasoning", True)),
        llm_config_path=str(os.getenv("LEGAL_QA_LLM_CONFIG_PATH") or payload.get("llm_config_path", "configs/serving/llm.qwen.json")),
        reranker_model_path=str(os.getenv("LEGAL_QA_RERANKER_MODEL_PATH") or payload.get("reranker_model_path", "models/reranker-best")),
        retriever_model_path=str(os.getenv("LEGAL_QA_RETRIEVER_MODEL_PATH") or payload.get("retriever_model_path", "models/retriever-best")),
        retriever_config_path=str(os.getenv("LEGAL_QA_RETRIEVER_CONFIG_PATH") or payload.get("retriever_config_path", "configs/serving/retrieval.hybrid.json")),
    )
