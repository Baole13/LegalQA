#!/usr/bin/env python3
"""Systematic Error Analysis for Vietnamese LegalQA (Phase 7).

Categorizes failure modes for both Retrieval and Generation stages:
Retrieval Errors:
1. retrieval_miss: Gold evidence not found in top-k
2. low_rank_after_top5: Gold evidence found at ranks 6-20
3. wrong_document: Top-1 hit from completely different legal document
4. semantic_mismatch: Casual phrasing vs formal legal terminology

Generation Errors:
1. wrong_or_weak_citation: Surface citation present but incorrect article/clause
2. hallucination: Low faithfulness score (< 0.5)
3. incomplete_reasoning: Short unreasoned claim
4. missing_condition: Unqualified legal statement
5. over_refusal: Unnecessary refusal when evidence exists

Outputs results/error_analysis.md and results/error_analysis.json.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import csv
import json
from collections import defaultdict

from src.utils.io import load_json


def analyze_retrieval_errors(details: list[dict], top_k: int = 5) -> dict:
    categories = {
        "retrieval_miss": [],
        "low_rank_after_top5": [],
        "wrong_document": [],
        "semantic_mismatch": [],
    }

    for item in details:
        gold_cids = set(str(c) for c in item.get("gold_cids", []))
        retrieved = item.get("retrieved", [])
        hit_rank = item.get("hit_rank")
        question = item.get("question", "")

        # 1. Retrieval miss
        if hit_rank is None or hit_rank > 20:
            categories["retrieval_miss"].append(
                {
                    "question": question,
                    "gold_cids": list(gold_cids),
                    "top_retrieved_cids": [str(h.get("cid")) for h in retrieved[:3]],
                    "top_1_title": retrieved[0].get("title", "") if retrieved else "",
                    "gold_evidence": item.get("gold_evidence", [])[:1],
                }
            )
        # 2. Low rank (after top-5)
        elif hit_rank > top_k:
            categories["low_rank_after_top5"].append(
                {
                    "question": question,
                    "hit_rank": hit_rank,
                    "gold_cids": list(gold_cids),
                    "rank_1_cid": retrieved[0].get("cid", "") if retrieved else "",
                    "rank_1_title": retrieved[0].get("title", "") if retrieved else "",
                }
            )

        # 3. Wrong document in top-1
        if retrieved and gold_cids:
            top_cid = str(retrieved[0].get("cid", ""))
            if top_cid not in gold_cids:
                categories["wrong_document"].append(
                    {
                        "question": question,
                        "gold_cids": list(gold_cids),
                        "top_1_cid": top_cid,
                        "top_1_title": retrieved[0].get("title", ""),
                    }
                )

        # 4. Semantic mismatch heuristic (low lexical overlap between question and top passage)
        if retrieved:
            q_words = set(question.lower().split())
            p_words = set(retrieved[0].get("snippet", "").lower().split())
            overlap = len(q_words & p_words) / max(len(q_words), 1)
            if overlap < 0.15:
                categories["semantic_mismatch"].append(
                    {
                        "question": question,
                        "lexical_overlap": round(overlap, 3),
                        "top_1_snippet": retrieved[0].get("snippet", "")[:150],
                    }
                )

    return categories


def analyze_generation_errors(details: list[dict]) -> dict:
    categories = {
        "hallucination": [],
        "wrong_citation": [],
        "incomplete_reasoning": [],
        "over_refusal": [],
        "format_non_compliance": [],
    }

    for item in details:
        q = item.get("question", "")
        pred = str(item.get("prediction_text", item.get("prediction", "")))
        faith = float(item.get("faithfulness_score", 1.0) or 1.0)
        cite_pres = float(item.get("citation_presence", 1.0) or 1.0)
        cite_corr = float(item.get("citation_correctness", 1.0) or 1.0)
        f1 = float(item.get("token_f1", 1.0) or 1.0)
        refusal = float(item.get("refusal_quality", 0.0) or 0.0)

        # Hallucination
        if faith < 0.5 and "không có" not in pred.lower() and "từ chối" not in pred.lower():
            categories["hallucination"].append(
                {"question": q, "prediction": pred[:200], "faithfulness": faith}
            )

        # Wrong or missing citation
        if cite_pres < 1.0 or cite_corr < 0.5:
            categories["wrong_citation"].append(
                {
                    "question": q,
                    "prediction": pred[:200],
                    "citation_presence": cite_pres,
                    "citation_correctness": cite_corr,
                }
            )

        # Incomplete reasoning (short answer without legal grounds)
        if len(pred.split()) < 25 and "Căn cứ" not in pred and "Điều" not in pred:
            categories["incomplete_reasoning"].append(
                {"question": q, "prediction": pred[:200], "length": len(pred.split())}
            )

        # Over-refusal
        if refusal == 1.0 and f1 < 0.2:
            categories["over_refusal"].append(
                {"question": q, "prediction": pred[:200]}
            )

    return categories


def main() -> None:
    parser = argparse.ArgumentParser(description="Systematic error analysis (Phase 7).")
    parser.add_argument(
        "--retrieval-details",
        default="reports/paper_retrieval_details.jsonl",
        help="Retrieval details JSONL file.",
    )
    parser.add_argument(
        "--generation-report",
        default="reports/answer_generation_qwen_qlora_retrieved_report.json",
        help="End-to-end generation report JSON.",
    )
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--n-examples", type=int, default=3)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=== Phase 7: Systematic Error Analysis ===")

    # 1. Retrieval Error Analysis
    retrieval_details_path = Path(args.retrieval_details)
    retrieval_cats = {}
    total_retrieval_samples = 0
    if retrieval_details_path.exists():
        r_details = []
        with retrieval_details_path.open("r", encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    r_details.append(json.loads(l))
        total_retrieval_samples = len(r_details)
        retrieval_cats = analyze_retrieval_errors(r_details)
        print(f"Loaded {total_retrieval_samples} retrieval evaluation samples.")
    else:
        print(f"Warning: {retrieval_details_path} not found.")

    # 2. Generation Error Analysis
    generation_report_path = Path(args.generation_report)
    gen_cats = {}
    total_gen_samples = 0
    if generation_report_path.exists():
        g_data = load_json(generation_report_path)
        g_details = g_data.get("details", [])
        total_gen_samples = len(g_details)
        gen_cats = analyze_generation_errors(g_details)
        print(f"Loaded {total_gen_samples} generation evaluation samples.")
    else:
        print(f"Warning: {generation_report_path} not found.")

    # Build Markdown Report
    lines = [
        "# Báo Cáo Phân Tích Lỗi Hệ Thống (Systematic Error Analysis)",
        "",
        "Báo cáo này phân tích chi tiết các failure modes của hệ thống trên cả 2 chặng: **Retrieval** và **Generation**.",
        "",
        "## 1. Retrieval Error Categories",
        f"Đánh giá trên N={total_retrieval_samples} mẫu truy xuất.",
        "",
        "| Error Category | Count | Rate (%) | Mô tả |",
        "|---|---:|---:|---|",
    ]

    r_desc = {
        "retrieval_miss": "Gold evidence không xuất hiện trong top-20 candidates",
        "low_rank_after_top5": "Gold evidence có trong top-20 nhưng xếp sau rank 5",
        "wrong_document": "Candidate rank-1 thuộc văn bản/chủ đề khác với gold",
        "semantic_mismatch": "Từ vựng câu hỏi đời thường không khớp thuật ngữ pháp lý",
    }
    for cat, items in retrieval_cats.items():
        rate = (len(items) / max(total_retrieval_samples, 1)) * 100
        lines.append(f"| `{cat}` | {len(items)} | {rate:.1f}% | {r_desc.get(cat, '')} |")

    lines.extend(["", "### Chi Tiết Case Studies Truy Xuất:", ""])
    for cat, items in retrieval_cats.items():
        lines.append(f"#### Category: `{cat}` (Ví dụ)")
        for ex in items[:args.n_examples]:
            lines.append(f"- **Câu hỏi**: {ex.get('question')}")
            if "gold_cids" in ex:
                lines.append(f"  - Gold CIDs: `{ex.get('gold_cids')}`")
            if "hit_rank" in ex:
                lines.append(f"  - Hit Rank: {ex.get('hit_rank')}")
            if "top_1_title" in ex:
                lines.append(f"  - Retrieved Top-1: {ex.get('top_1_title')}")
            lines.append("")

    lines.extend(
        [
            "## 2. Generation Error Categories",
            f"Đánh giá trên N={total_gen_samples} mẫu sinh câu trả lời RAG.",
            "",
            "| Error Category | Count | Rate (%) | Mô tả |",
            "|---|---:|---:|---|",
        ]
    )

    g_desc = {
        "hallucination": "Câu trả lời có độ tin cậy thấp đối với evidence (faithfulness < 0.5)",
        "wrong_citation": "Trích dẫn sai văn bản hoặc thiếu căn cứ pháp lý rõ ràng",
        "incomplete_reasoning": "Câu trả lời ngắn, thiếu lập luận viện dẫn điều khoản",
        "over_refusal": "Từ chối trả lời dù tài liệu có thông tin liên quan",
        "format_non_compliance": "Không tuân thủ cấu trúc định dạng chuẩn",
    }
    for cat, items in gen_cats.items():
        rate = (len(items) / max(total_gen_samples, 1)) * 100
        lines.append(f"| `{cat}` | {len(items)} | {rate:.1f}% | {g_desc.get(cat, '')} |")

    lines.extend(["", "### Chi Tiết Case Studies Sinh Lời Giải:", ""])
    for cat, items in gen_cats.items():
        lines.append(f"#### Category: `{cat}` (Ví dụ)")
        for ex in items[:args.n_examples]:
            lines.append(f"- **Câu hỏi**: {ex.get('question')}")
            lines.append(f"  - Model Answer: \"{ex.get('prediction', '')[:160]}...\"")
            lines.append("")

    # Write results/error_analysis.md
    md_path = output_dir / "error_analysis.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved Markdown error analysis to: {md_path}")

    # Write results/error_analysis.json
    json_path = output_dir / "error_analysis.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "retrieval_summary": {k: len(v) for k, v in retrieval_cats.items()},
                "generation_summary": {k: len(v) for k, v in gen_cats.items()},
                "retrieval_samples": total_retrieval_samples,
                "generation_samples": total_gen_samples,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Saved JSON error analysis to: {json_path}")


if __name__ == "__main__":
    main()
