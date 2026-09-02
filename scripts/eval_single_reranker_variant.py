"""Evaluate a single cross-encoder reranker variant in isolation.

Usage:
  PYTHONPATH=. LEGAL_QA_RERANKER_MODEL_PATH=models/reranker-hardneg-v2 \
    .venv/bin/python scripts/eval_single_reranker_variant.py \
    --variant full_with_cross_encoder_reranker_hardneg_v2 \
    --reranker-model-path models/reranker-hardneg-v2 \
    --limit 300 --top-k 20 --report-dir reports
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import scripts._bootstrap as _bootstrap
from scripts.run_paper_experiments import (
    _evaluate_retrieval_variant,
    _variant_cache_path,
    _metrics_from_details,
    _metrics_template,
)
from src.qa.pipeline import LegalQAPipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="full_with_cross_encoder_reranker_hardneg_v2")
    parser.add_argument("--reranker-model-path", default="models/reranker-hardneg-v2")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--report-dir", default="reports")
    parser.add_argument("--retrieval-dataset", default="data/raw/yuitc/test.parquet")
    args = parser.parse_args()

    import os
    os.environ["LEGAL_QA_RERANKER_MODEL_PATH"] = args.reranker_model_path
    pipeline = LegalQAPipeline.build()

    metric_ks = (1, 5, 10, 20)
    pipeline.artifacts.retriever.neural_dense.ensure_available()

    cache_dir = Path(args.report_dir) / ".paper_experiment_cache"
    metrics, details = _evaluate_retrieval_variant(
        pipeline=pipeline,
        variant=args.variant,
        qa_path=args.retrieval_dataset,
        limit=args.limit,
        top_k=args.top_k,
        ks=metric_ks,
        cache_dir=cache_dir,
    )
    metrics["reranker_model_path"] = args.reranker_model_path
    metrics["reranker_mode"] = "cross-encoder"

    out = Path(args.report_dir) / "reranker_hardneg_v2_eval.json"
    with out.open("w") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
