from __future__ import annotations

from dataclasses import dataclass

from src.utils.io import load_json


@dataclass
class ServingConfig:
    use_llm_reasoning: bool
    llm_config_path: str
    reranker_model_path: str
    retriever_model_path: str


def load_serving_config(path: str = "configs/serving/serving.json") -> ServingConfig:
    payload = load_json(path)
    return ServingConfig(
        use_llm_reasoning=bool(payload.get("use_llm_reasoning", True)),
        llm_config_path=str(payload.get("llm_config_path", "configs/serving/llm.qwen.json")),
        reranker_model_path=str(payload.get("reranker_model_path", "models/reranker-best")),
        retriever_model_path=str(payload.get("retriever_model_path", "models/retriever-best")),
    )
