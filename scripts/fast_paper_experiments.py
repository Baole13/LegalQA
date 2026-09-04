#!/usr/bin/env python3
"""
Fast paper experiments - uses cached results and only runs cross-encoder once.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts._bootstrap as _bootstrap

from src.data.load_qa import load_qa_records, parse_cids
from src.evaluation.retrieval_eval import ndcg_at_k
from src.qa.pipeline import LegalQAPipeline
from src.utils.io import load_json, save_json, save_jsonl


def load_cached_metrics(cache_dir: Path, variant: str, limit: int, top_k: int) -> dict | None:
    """Load cached metrics from JSONL file."""
    cache_file = cache_dir / f"retrieval_v2_{variant}_limit{limit}_top{top_k}.jsonl"
    if not cache_file.exists():
        return None
    
    details = []
    with cache_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                details.append(json.loads(line))
    
    if len(details) < limit:
        return None
    
    return compute_metrics_from_details(details, variant, limit, top_k)


def compute_metrics_from_details(details: list[dict], variant: str, limit: int, top_k: int, ks: tuple = (1, 5, 10, 20)) -> dict:
    """Compute metrics from cached details."""
    total = max(len(details), 1)
    covered_questions = sum(1 for item in details if item.get("gold_in_index"))
    covered_total = max(covered_questions, 1)
    
    hit_counts = {k: 0 for k in ks}
    covered_hit_counts = {k: 0 for k in ks}
    reciprocal_rank_sum = 0.0
    covered_reciprocal_rank_sum = 0.0
    ndcg_sum = 0.0
    
    for item in details:
        gold_cids = set(str(cid) for cid in item.get("gold_cids", []))
        capped = (item.get("retrieved") or [])[:top_k]
        ranked_cids = [str(hit.get("cid", "")) for hit in capped]
        ndcg_sum += ndcg_at_k(ranked_cids, gold_cids, 10)
        
        for k in ks:
            hit = any(cid in gold_cids for cid in ranked_cids[:k])
            hit_counts[k] += int(hit)
            covered_hit_counts[k] += int(item.get("gold_in_index") and hit)
        
        for rank, cid in enumerate(ranked_cids, start=1):
            if cid in gold_cids:
                reciprocal_rank_sum += 1.0 / rank
                if item.get("gold_in_index"):
                    covered_reciprocal_rank_sum += 1.0 / rank
                break
    
    indexed_cids = len(set(str(item.get("cid", "")) for item in details[0].get("retrieved", []))) if details else 0
    
    return {
        "variant": variant,
        "qa_path": "data/raw/yuitc/test.parquet",
        "samples": len(details),
        "top_k": top_k,
        "indexed_chunks": 643469,
        "indexed_unique_cids": 261440,
        "gold_coverage_in_index": round(covered_questions / total, 4),
        "questions_with_gold_in_index": covered_questions,
        "questions_without_gold_in_index": len(details) - covered_questions,
        "mrr": round(reciprocal_rank_sum / total, 4),
        "conditional_mrr": round(covered_reciprocal_rank_sum / covered_total, 4),
        "ndcg@10": round(ndcg_sum / total, 4),
        **{f"recall@{k}": round(hit_counts[k] / total, 4) for k in ks},
        **{f"conditional_recall@{k}": round(covered_hit_counts[k] / covered_total, 4) for k in ks},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast paper experiments using cached results")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--report-dir", default="reports")
    parser.add_argument("--retrieval-dataset", default="data/raw/yuitc/test.parquet")
    parser.add_argument("--answer-report", default="reports/answer_generation_report.json")
    parser.add_argument("--retrieved-generation-report", default="reports/answer_generation_qwen_qlora_retrieved_report.json")
    parser.add_argument("--retrieved-prompt-only-report", default="reports/answer_generation_qwen_prompt_only_retrieved_report.json")
    parser.add_argument("--retrieved-schema-report", default="reports/answer_generation_qwen_qlora_retrieved_schema_report.json")
    parser.add_argument("--qa-memory-leakage-report", default="reports/qa_memory_leakage_audit.json")
    parser.add_argument("--generation-baselines-report", default="reports/generation_baselines_report.json")
    parser.add_argument("--human-eval", default=None)
    parser.add_argument("--human-sample-size", type=int, default=75)
    parser.add_argument("--end-to-end-human-eval", default=None)
    parser.add_argument("--end-to-end-human-sample-size", type=int, default=50)
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    retrieval_cache_dir = report_dir / ".paper_experiment_cache"
    
    print("Building pipeline...")
    pipeline = LegalQAPipeline.build()
    pipeline.artifacts.retriever.neural_dense.ensure_available()
    
    metric_ks = (1, 5, 10, 20)
    max_eval_k = max(args.top_k, 20)
    
    # Load cached retrieval results for non-cross-encoder variants
    print("Loading cached retrieval results...")
    cached_variants = [
        "bm25_only",
        "bm25_okapi_only", 
        "dense_only",
        "hybrid_no_qa_memory",
        "hybrid_with_qa_memory",
        "full",  # heuristic full
    ]
    
    retrieval_ablations = []
    for variant in cached_variants:
        metrics = load_cached_metrics(retrieval_cache_dir, variant, args.limit, max_eval_k)
        if metrics:
            retrieval_ablations.append(metrics)
            print(f"  Loaded {variant}: recall@5={metrics.get('recall@5', 0):.4f}")
        else:
            print(f"  WARNING: No cache for {variant}")
    
    # Run cross-encoder variant (the main one)
    print("Running cross-encoder reranker evaluation (this takes ~10 min)...")
    from scripts.run_paper_experiments import _evaluate_retrieval_variant
    
    cross_encoder_metrics, cross_encoder_details = _evaluate_retrieval_variant(
        pipeline=pipeline,
        variant="full_with_cross_encoder_reranker",
        qa_path=args.retrieval_dataset,
        limit=args.limit,
        top_k=max_eval_k,
        ks=metric_ks,
        cache_dir=retrieval_cache_dir,
    )
    cross_encoder_metrics["reranker_mode"] = "cross-encoder"
    cross_encoder_metrics["reranker_model_path"] = pipeline.serving_config.reranker_model_path
    cross_encoder_metrics["main_result_note"] = "Main retrieval result uses the trained cross-encoder reranker; heuristic retrieval is retained as an ablation."
    retrieval_ablations.append(cross_encoder_metrics)
    print(f"  Cross-encoder: recall@5={cross_encoder_metrics.get('recall@5', 0):.4f}")
    
    # Cross-encoder k100
    ce_k100_metrics, _ = _evaluate_retrieval_variant(
        pipeline=pipeline,
        variant="full_with_cross_encoder_reranker_k100",
        qa_path=args.retrieval_dataset,
        limit=args.limit,
        top_k=max_eval_k,
        ks=metric_ks,
        cache_dir=retrieval_cache_dir,
    )
    ce_k100_metrics["reranker_mode"] = "cross-encoder"
    ce_k100_metrics["reranker_model_path"] = pipeline.serving_config.reranker_model_path
    retrieval_ablations.append(ce_k100_metrics)
    
    # Cross-encoder hardneg
    ce_hardneg_metrics, _ = _evaluate_retrieval_variant(
        pipeline=pipeline,
        variant="full_with_cross_encoder_reranker_hardneg",
        qa_path=args.retrieval_dataset,
        limit=args.limit,
        top_k=max_eval_k,
        ks=metric_ks,
        cache_dir=retrieval_cache_dir,
    )
    ce_hardneg_metrics["reranker_mode"] = "cross-encoder-hardneg"
    ce_hardneg_metrics["reranker_model_path"] = pipeline.serving_config.reranker_model_path
    retrieval_ablations.append(ce_hardneg_metrics)
    
    # Top-k ablations from full heuristic details
    print("Computing top-k ablations...")
    # Load full heuristic details
    full_cache = retrieval_cache_dir / f"retrieval_v2_full_limit{args.limit}_top{max_eval_k}.jsonl"
    if full_cache.exists():
        full_details = []
        with full_cache.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    full_details.append(json.loads(line))
        
        for top_k in [3, 5, 8]:
            metrics = compute_metrics_from_details(
                full_details, f"full_top_k_{top_k}", args.limit, top_k, metric_ks
            )
            retrieval_ablations.append(metrics)
    
    # Select main retrieval result (cross-encoder)
    main_retrieval = cross_encoder_metrics
    
    # Load other reports
    print("Loading generation reports...")
    answer_report = load_json(args.answer_report)
    retrieved_generation = load_json(args.retrieved_generation_report)
    retrieved_prompt_only = load_json(args.retrieved_prompt_only_report)
    retrieved_schema = load_json(args.retrieved_schema_report)
    qa_memory_leakage = load_json(args.qa_memory_leakage_report)
    generation_baselines = load_json(args.generation_baselines_report)
    
    # Build minimal payload
    dataset_stats = {
        "corpus_chunks": 643469,
        "qa_memory_records": 89261,
        "index_created_at": "2026-05-16T09:33:28.558616+00:00",
        "sft_total_records": 29145,
        "sft_train_records": 26230,
        "sft_val_records": 1457,
        "sft_test_records": 1458,
        "retriever_records": 89261,
        "reranker_records": 357044,
        "negatives_per_query": 3,
        "base_model": "Qwen/Qwen2.5-7B-Instruct",
        "qlora_train_records": 26230,
        "qlora_eval_records": 500,
    }
    
    payload = {
        "dataset_stats": dataset_stats,
        "retrieval": main_retrieval,
        "retrieval_ablations": retrieval_ablations,
        "answer_generation": {k: v for k, v in answer_report.items() if k != "details"},
        "retrieved_answer_generation": {k: v for k, v in retrieved_generation.items() if k != "details"},
        "retrieved_prompt_only_generation": {k: v for k, v in retrieved_prompt_only.items() if k != "details"},
        "retrieved_schema_generation": {k: v for k, v in retrieved_schema.items() if k != "details"},
        "generation_baselines": generation_baselines,
        "qa_memory_leakage": qa_memory_leakage,
        "notes": [
            "Faithfulness, reasoning, directness, citation correctness, and refusal quality are proxy metrics.",
            "Human evaluation uses a single LLM-as-annotator pass (AI-assisted scoring), so there is no inter-annotator agreement and no Cohen's kappa; it is a preliminary assessment, not expert legal validation.",
            "The hybrid_no_qa_memory ablation disables QA-memory seeding/boosting during retrieval evaluation only.",
            "Top-k ablation rows cap the number of retrieved evidence chunks available to downstream generation.",
            "The main retrieval table uses the trained cross-encoder reranker when the full_with_cross_encoder_reranker row is available; heuristic full retrieval is reported as an ablation.",
            "Format compliance measures adherence to the expected structured output format, not legal correctness; low values are treated as a formatting limitation.",
            "oracle_evidence_qwen is diagnostic only: the current SFT prompt already contains oracle/gold context, so it is not a distinct upper-bound baseline.",
        ],
    }
    
    # Save
    json_path = report_dir / "paper_experiments.json"
    md_path = report_dir / "paper_experiments.md"
    details_path = report_dir / "paper_retrieval_details.jsonl"
    
    save_json(json_path, payload)
    save_jsonl(details_path, cross_encoder_details)
    
    # Generate markdown
    md_content = render_markdown(payload)
    md_path.write_text(md_content, encoding="utf-8")
    
    print(f"Saved: {json_path}")
    print(f"Saved: {md_path}")
    print(f"Saved: {details_path}")


def render_markdown(payload: dict) -> str:
    """Render markdown report (simplified version)."""
    lines = [
        "# Paper Experiments Report",
        "",
        "All grounding-oriented answer metrics in this report are proxy metrics, not legal-expert judgments.",
        "",
        "## Dataset Statistics",
        "",
    ]
    
    for k, v in payload["dataset_stats"].items():
        lines.append(f"| {k} | {v} |")
    
    lines.extend(["", "## Retrieval Results", ""])
    
    r = payload["retrieval"]
    lines.append("| samples | top_k | gold_coverage_in_index | recall@1 | recall@5 | recall@10 | recall@20 | mrr | ndcg@10 | conditional_mrr |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    lines.append(f"| {r['samples']} | {r['top_k']} | {r['gold_coverage_in_index']} | {r['recall@1']} | {r['recall@5']} | {r['recall@10']} | {r['recall@20']} | {r['mrr']} | {r['ndcg@10']} | {r['conditional_mrr']} |")
    
    lines.extend(["", "## Retrieval Ablation", ""])
    lines.append("| variant | samples | top_k | gold_coverage_in_index | recall@1 | recall@5 | recall@10 | recall@20 | mrr | ndcg@10 | conditional_mrr |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    
    for row in payload["retrieval_ablations"]:
        lines.append(f"| {row['variant']} | {row['samples']} | {row['top_k']} | {row['gold_coverage_in_index']} | {row['recall@1']} | {row['recall@5']} | {row['recall@10']} | {row['recall@20']} | {row['mrr']} | {row['ndcg@10']} | {row['conditional_mrr']} |")
    
    lines.extend(["", "## Generation Results", ""])
    for k, v in payload["answer_generation"].items():
        lines.append(f"| {k} | {v} |")
    
    lines.extend(["", "## End-to-End RAG Generation", ""])
    rag = payload["retrieved_answer_generation"]
    lines.append("| variant | evidence_mode | retrieval_variant | retrieval_top_k | samples | token_f1 | rouge_l | citation_presence | format_compliance | faithfulness_score | directness_score | citation_correctness | refusal_quality |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    lines.append(f"| {rag.get('variant', '')} | {rag.get('evidence_mode', '')} | {rag.get('retrieval_variant', '')} | {rag.get('retrieval_top_k', '')} | {rag.get('samples', '')} | {rag.get('token_f1', '')} | {rag.get('rouge_l', '')} | {rag.get('citation_presence', '')} | {rag.get('format_compliance', '')} | {rag.get('faithfulness_score', '')} | {rag.get('directness_score', '')} | {rag.get('citation_correctness', '')} | {rag.get('refusal_quality', '')} |")
    
    lines.extend(["", "## Notes", ""])
    for note in payload["notes"]:
        lines.append(f"- {note}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    main()