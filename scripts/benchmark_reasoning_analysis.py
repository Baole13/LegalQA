#!/usr/bin/env python3
"""Reasoning and difficulty breakdown analysis (Phase 5 & 6).

Groups generation performance by:
1. question_type: factual, interpretation, analytical, application
2. difficulty: easy, medium, hard

Outputs results/reasoning_analysis.csv and paper-ready tables.
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
from collections import defaultdict
from statistics import mean

from src.utils.io import load_json


def load_test_metadata(test_path: str | Path) -> dict[str, dict]:
    """Map question text to its metadata (question_type, difficulty, doc_name)."""
    meta_map = {}
    with Path(test_path).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            messages = record.get("messages", [])
            user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
            q_text = user_msg
            if "Cau hoi:\n" in user_msg:
                parts = user_msg.split("Cau hoi:\n", 1)[1]
                q_text = parts.split("\nYeu cau:", 1)[0].strip()

            metadata = record.get("metadata", {})
            q_type = metadata.get("question_type", "unclassified").lower()
            diff = metadata.get("difficulty", "unclassified").lower()

            meta_map[q_text] = {
                "question_type": q_type,
                "difficulty": diff,
                "doc_name": metadata.get("doc_name", ""),
                "record_id": metadata.get("record_id", ""),
            }
    return meta_map


def load_model_details(output_dir: Path) -> dict[str, list[dict]]:
    """Load per-sample details for available models from results/."""
    models = {}
    for jsonl_file in sorted(output_dir.glob("generation_details_*.jsonl")):
        cfg_name = jsonl_file.stem.replace("generation_details_", "")
        records = []
        with jsonl_file.open("r", encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    records.append(json.loads(l))
        if records:
            models[cfg_name] = records
    return models


def analyze_by_category(
    models: dict[str, list[dict]],
    meta_map: dict[str, dict],
    category_key: str,
) -> list[dict]:
    grouped = defaultdict(lambda: defaultdict(list))

    for model_name, details in models.items():
        for d in details:
            q = str(d.get("question", "")).strip()
            meta = meta_map.get(q, {})
            cat_val = meta.get(category_key, "unknown")

            f1 = float(d.get("token_f1", 0.0))
            rouge = float(d.get("rouge_l", 0.0))
            faith = float(d.get("faithfulness_score", 0.0))

            grouped[cat_val][model_name].append(
                {"f1": f1, "rouge": rouge, "faith": faith}
            )

    rows = []
    for cat_val, model_dict in sorted(grouped.items()):
        row = {"dimension": category_key, "category": cat_val}
        for model_name, samples in model_dict.items():
            if samples:
                avg_f1 = mean(s["f1"] for s in samples)
                avg_rouge = mean(s["rouge"] for s in samples)
                row[f"{model_name}_count"] = len(samples)
                row[f"{model_name}_f1"] = round(avg_f1, 4)
                row[f"{model_name}_rouge"] = round(avg_rouge, 4)
        rows.append(row)

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze reasoning and difficulty breakdown (Phase 5 & 6).")
    parser.add_argument(
        "--test-path",
        default="data/processed/thangvip_legalqa/test.jsonl",
        help="Path to thangvip test split with metadata.",
    )
    parser.add_argument("--output-dir", default="results")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading test metadata...")
    meta_map = load_test_metadata(args.test_path)
    print(f"Loaded metadata for {len(meta_map)} questions.")

    models = load_model_details(output_dir)
    print(f"Loaded details for model configurations: {list(models.keys())}")

    if not models:
        print("No generation detail reports found in results/. Run scripts/benchmark_generation.py first.")
        return

    type_rows = analyze_by_category(models, meta_map, "question_type")
    diff_rows = analyze_by_category(models, meta_map, "difficulty")
    all_rows = type_rows + diff_rows

    all_keys = ["dimension", "category"]
    for r in all_rows:
        for k in r.keys():
            if k not in all_keys:
                all_keys.append(k)

    csv_path = output_dir / "reasoning_analysis.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nSaved reasoning breakdown CSV to: {csv_path}")

    # Print Table 6: Question-Type Breakdown
    print("\n### Table 6: Performance by Question Type (Token F1)")
    print("| Question Type | Samples | Extractive | Base Qwen (Oracle) | QLoRA (Oracle) | Base Qwen + RAG | QLoRA + RAG | QLoRA Gain (Oracle) |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in type_rows:
        cat = r["category"]
        cnt = r.get("qwen_qlora_oracle_count", "-")
        ext = r.get("extractive_only_f1", 0.0)
        base_ora = r.get("qwen_prompt_only_oracle_f1", 0.0)
        qlora_ora = r.get("qwen_qlora_oracle_f1", 0.0)
        base_rag = r.get("qwen_prompt_only_rag_f1", 0.0)
        qlora_rag = r.get("qwen_qlora_rag_f1", 0.0)
        gain = qlora_ora - base_ora
        print(f"| {cat.capitalize()} | {cnt} | {ext:.4f} | {base_ora:.4f} | {qlora_ora:.4f} | {base_rag:.4f} | {qlora_rag:.4f} | **+{gain:+.4f}** |")

    # Print Table 7: Difficulty Breakdown
    print("\n### Table 7: Performance by Difficulty Level (Token F1)")
    print("| Difficulty | Samples | Extractive | Base Qwen (Oracle) | QLoRA (Oracle) | Base Qwen + RAG | QLoRA + RAG | QLoRA Gain (Oracle) |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in diff_rows:
        cat = r["category"]
        cnt = r.get("qwen_qlora_oracle_count", "-")
        ext = r.get("extractive_only_f1", 0.0)
        base_ora = r.get("qwen_prompt_only_oracle_f1", 0.0)
        qlora_ora = r.get("qwen_qlora_oracle_f1", 0.0)
        base_rag = r.get("qwen_prompt_only_rag_f1", 0.0)
        qlora_rag = r.get("qwen_qlora_rag_f1", 0.0)
        gain = qlora_ora - base_ora
        print(f"| {cat.capitalize()} | {cnt} | {ext:.4f} | {base_ora:.4f} | {qlora_ora:.4f} | {base_rag:.4f} | {qlora_rag:.4f} | **+{gain:+.4f}** |")


if __name__ == "__main__":
    main()
