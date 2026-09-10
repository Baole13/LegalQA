#!/usr/bin/env python3
"""Generation benchmark suite for Vietnamese LegalQA (Phase 4).

Evaluates 5 standardized generation configurations on the thangvip test set:
1. extractive_only (oracle context)
2. qwen_prompt_only (oracle context)
3. qwen_qlora (oracle context)
4. qwen_prompt_only_rag (retrieved top-5 context)
5. qwen_qlora_rag (retrieved top-5 context, Full system)

Saves summary to results/generation_benchmark.csv and per-configuration details.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import csv
import datetime
import json

from scripts.eval_answer_generation import (
    _evaluate_variant,
    _replace_with_retrieved_context,
    load_answer_eval_samples,
)
from src.utils.io import load_json


CONFIGS = [
    {
        "id": "extractive_only",
        "name": "Extractive (Oracle)",
        "variant": "extractive_only",
        "evidence_mode": "oracle_context",
        "cached_report": "reports/answer_generation_report.json",
        "is_llm": False,
    },
    {
        "id": "qwen_prompt_only_oracle",
        "name": "Base Qwen (Oracle)",
        "variant": "qwen_prompt_only",
        "evidence_mode": "oracle_context",
        "cached_report": "reports/answer_generation_qwen_prompt_only_report.json",
        "is_llm": True,
    },
    {
        "id": "qwen_qlora_oracle",
        "name": "Qwen QLoRA (Oracle)",
        "variant": "qwen_qlora",
        "evidence_mode": "oracle_context",
        "cached_report": "reports/answer_generation_report.json",
        "is_llm": True,
    },
    {
        "id": "qwen_prompt_only_rag",
        "name": "Base Qwen + RAG",
        "variant": "qwen_prompt_only",
        "evidence_mode": "retrieved_context",
        "cached_report": "reports/answer_generation_qwen_prompt_only_retrieved_report.json",
        "is_llm": True,
    },
    {
        "id": "qwen_qlora_rag",
        "name": "Qwen QLoRA + RAG (Full)",
        "variant": "qwen_qlora",
        "evidence_mode": "retrieved_context",
        "cached_report": "reports/answer_generation_qwen_qlora_retrieved_report.json",
        "is_llm": True,
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full generation benchmark suite (Phase 4).")
    parser.add_argument(
        "--dataset",
        default="data/processed/thangvip_legalqa/test.jsonl",
        help="Path to thangvip test dataset.",
    )
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--adapter", default="models/qwen2.5-7b-legalqa-qlora")
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Number of samples to evaluate (0 for full test set).",
    )
    parser.add_argument("--retrieval-top-k", type=int, default=5)
    parser.add_argument(
        "--retrieval-variant",
        default="full_with_cross_encoder_reranker",
    )
    parser.add_argument(
        "--reuse-cached-reports",
        action="store_true",
        default=True,
        help="Reuse existing reports in reports/ if sample count and config match.",
    )
    parser.add_argument("--force-run", action="store_true", help="Force live model inference.")
    parser.add_argument("--skip-llm", action="store_true", help="Skip heavy LLM generation.")
    parser.add_argument("--output-dir", default="results")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    csv_rows = []
    all_reports = []

    model_cache = {}

    print("=== Vietnamese LegalQA Generation Benchmark Suite (Phase 4) ===")
    print(f"Dataset : {args.dataset} (Limit: {args.limit})")
    print(f"Base LLM: {args.base_model} | Adapter: {args.adapter}")

    for cfg in CONFIGS:
        cfg_id = cfg["id"]
        cfg_name = cfg["name"]
        variant = cfg["variant"]
        evidence_mode = cfg["evidence_mode"]
        cached_file = Path(cfg["cached_report"])

        print(f"\n--- Benchmark: {cfg_name} ({cfg_id}) ---")

        metrics = None
        # Check if we can reuse existing report
        if args.reuse_cached_reports and not args.force_run and cached_file.exists():
            try:
                cached_data = load_json(cached_file)
                # If cached_file has baselines array (like generation_baselines_report.json)
                if "baselines" in cached_data:
                    for b in cached_data["baselines"]:
                        if b.get("variant") == variant:
                            metrics = b
                            break
                elif cached_data.get("variant") == variant or (variant == "qwen_qlora" and "token_f1" in cached_data):
                    metrics = cached_data
                if metrics and (args.limit == 0 or metrics.get("samples") == args.limit):
                    print(f"Reusing verified cached metrics from {cached_file}")
            except Exception as e:
                print(f"Could not load cached report {cached_file}: {e}")

        # If not cached or force-run, run inference
        if metrics is None:
            if cfg["is_llm"] and args.skip_llm:
                print(f"Skipping LLM configuration {cfg_name} (--skip-llm)")
                continue

            print(f"Loading samples and preparing context for {cfg_name}...")
            samples = load_answer_eval_samples(args.dataset, limit=args.limit)
            retrieval_meta = []
            if evidence_mode == "retrieved_context":
                samples, retrieval_meta = _replace_with_retrieved_context(
                    samples, top_k=args.retrieval_top_k
                )

            args.evidence_mode = evidence_mode
            args.prompt_style = "default"
            args.max_new_tokens = 256
            metrics = _evaluate_variant(
                args,
                samples,
                variant,
                model_cache=model_cache,
                retrieval_metadata=retrieval_meta,
            )

        # Extract details to write per-config jsonl if details exist
        if "details" in metrics and metrics["details"]:
            details_path = output_dir / f"generation_details_{cfg_id}.jsonl"
            with details_path.open("w", encoding="utf-8") as f:
                for d in metrics["details"]:
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
            print(f"Saved details to: {details_path}")

        row = {
            "configuration": cfg_name,
            "id": cfg_id,
            "variant": variant,
            "evidence_mode": evidence_mode,
            "samples": metrics.get("samples", args.limit),
            "token_f1": round(float(metrics.get("token_f1", 0.0)), 4),
            "rouge_l": round(float(metrics.get("rouge_l", 0.0)), 4),
            "exact_match": round(float(metrics.get("exact_match", 0.0)), 4),
            "citation_presence": round(float(metrics.get("citation_presence", 0.0)), 4),
            "faithfulness_score": round(float(metrics.get("faithfulness_score", 0.0)), 4),
            "directness_score": round(float(metrics.get("directness_score", 0.0)), 4),
            "citation_correctness": round(float(metrics.get("citation_correctness", 0.0)), 4),
            "timestamp": timestamp,
        }
        csv_rows.append(row)
        all_reports.append({k: v for k, v in metrics.items() if k != "details"})
        print(
            f"Result: Token F1={row['token_f1']:.4f}, ROUGE-L={row['rouge_l']:.4f}, "
            f"Faithfulness={row['faithfulness_score']:.4f}, Citation Correctness={row['citation_correctness']:.4f}"
        )

    # Save CSV
    csv_path = output_dir / "generation_benchmark.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"\nSaved generation benchmark CSV to: {csv_path}")

    # Save JSON
    json_path = output_dir / "generation_benchmark.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(all_reports, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON to: {json_path}")

    # Summary table
    print("\n### Generation Benchmark Summary Table (Table 5)")
    print("| Method | Evidence Mode | Token F1 | ROUGE-L | Faithfulness | Citation Presence |")
    print("|---|---|---:|---:|---:|---:|")
    for r in csv_rows:
        print(
            f"| {r['configuration']} | {r['evidence_mode']} | "
            f"{r['token_f1']:.4f} | {r['rouge_l']:.4f} | "
            f"{r['faithfulness_score']:.4f} | {r['citation_presence']:.4f} |"
        )


if __name__ == "__main__":
    main()
