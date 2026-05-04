from __future__ import annotations

from src.evaluation.retrieval_eval import evaluate_retrieval
from src.qa.pipeline import LegalQAPipeline


def main() -> None:
    pipeline = LegalQAPipeline.build()
    metrics = evaluate_retrieval(pipeline)
    for key, value in metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
