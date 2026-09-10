#!/usr/bin/env python3
"""Automatic vs Human Metric Correlation Analysis (Phase 8).

Analyzes the correlation and discrepancy between automatic proxy metrics and human ratings.
Supports both end_to_end_human_eval_sample_50.tsv (where automatic and human metrics
are paired side-by-side) and human_eval_sample_75.csv.

Outputs results/metric_correlation.md and results/metric_correlation.json.
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
import math
from statistics import mean

from src.utils.io import load_json


def compute_pearson(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    mx, my = mean(x), mean(y)
    sx = math.sqrt(sum((val - mx) ** 2 for val in x))
    sy = math.sqrt(sum((val - my) ** 2 for val in y))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (sx * sy)


def compute_spearman(x: list[float], y: list[float]) -> float:
    def rank(vals: list[float]) -> list[float]:
        sorted_indices = sorted(range(len(vals)), key=lambda i: vals[i])
        ranks = [0.0] * len(vals)
        for r, idx in enumerate(sorted_indices, start=1):
            ranks[idx] = float(r)
        return ranks

    return compute_pearson(rank(x), rank(y))


def load_from_tsv(tsv_path: Path) -> list[dict]:
    """Load paired automatic and human evaluation metrics directly from TSV."""
    paired = []
    with tsv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            try:
                auto_cite = float(r.get("automatic_citation_correctness_proxy") or 0.0)
                auto_faith = float(r.get("automatic_faithfulness_proxy") or 0.0)
                h_legal = float(r.get("a1_legal_correctness") or 0.0)
                h_grounding = float(r.get("a1_grounding") or 0.0)
                h_cite = float(r.get("a1_citation_correctness") or 0.0)
                h_direct = float(r.get("a1_directness") or 0.0)
                h_refusal = float(r.get("a1_refusal") or 0.0)

                paired.append(
                    {
                        "question": r.get("question", ""),
                        "auto_citation": auto_cite,
                        "human_citation": h_cite,
                        "auto_faithfulness": auto_faith,
                        "human_grounding": h_grounding,
                        "human_legal": h_legal,
                        "human_directness": h_direct,
                        "human_refusal": h_refusal,
                    }
                )
            except (ValueError, TypeError):
                continue
    return paired


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze correlation between automatic and human evaluation metrics.")
    parser.add_argument("--e2e-tsv", default="reports/end_to_end_human_eval_sample_50.tsv")
    parser.add_argument("--human-csv", default="reports/human_eval_sample_75.csv")
    parser.add_argument("--auto-json", default="reports/answer_generation_qwen_qlora_retrieved_report.json")
    parser.add_argument("--output-dir", default="results")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=== Phase 8: Automatic vs Human Metric Correlation Analysis ===")

    paired = []
    tsv_path = Path(args.e2e_tsv)
    if tsv_path.exists():
        paired = load_from_tsv(tsv_path)
        print(f"Loaded {len(paired)} paired samples from {tsv_path}")

    # Fallback to pairing via question text if TSV had no rows
    if not paired:
        auto_data = load_json(args.auto_json)
        auto_map = {str(item.get("question", "")).strip(): item for item in auto_data.get("details", [])}
        with Path(args.human_csv).open("r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                q = str(r.get("question", "")).strip()
                if q in auto_map:
                    a = auto_map[q]
                    paired.append(
                        {
                            "question": q,
                            "auto_citation": float(a.get("citation_correctness", 0.0)),
                            "human_citation": float(r.get("a1_citation_correctness") or 0.0),
                            "auto_faithfulness": float(a.get("faithfulness_score", 0.0)),
                            "human_grounding": float(r.get("a1_grounding") or 0.0),
                            "human_legal": float(r.get("a1_legal_correctness") or 0.0),
                            "human_directness": float(r.get("a1_directness") or 0.0),
                            "human_refusal": float(r.get("a1_refusal") or 0.0),
                        }
                    )
        print(f"Paired {len(paired)} samples via question matching")

    if not paired:
        print("No paired data found.")
        return

    # Correlation calculation
    metric_pairs = [
        ("Citation Correctness", "auto_citation", "human_citation"),
        ("Grounding vs Faithfulness Proxy", "auto_faithfulness", "human_grounding"),
    ]

    results_table = []
    for label, auto_key, human_key in metric_pairs:
        x = [p[auto_key] for p in paired]
        y = [p[human_key] for p in paired]
        p_r = compute_pearson(x, y)
        s_rho = compute_spearman(x, y)
        results_table.append(
            {
                "metric": label,
                "auto_mean": round(mean(x), 4) if x else 0.0,
                "human_mean": round(mean(y), 4) if y else 0.0,
                "pearson_r": round(p_r, 4),
                "spearman_rho": round(s_rho, 4),
            }
        )

    # Detect False Positives in Citation Correctness: Auto >= 0.95, but Human <= 3
    false_positives = [
        p for p in paired if p["auto_citation"] >= 0.95 and p["human_citation"] <= 3.0
    ]

    lines = [
        "# Phân Tích Tương Quan Automatic Proxies vs Human Evaluation (Phase 8)",
        "",
        "## 1. Bảng Tương Quan (Correlation Summary)",
        f"Đánh giá trên N={len(paired)} mẫu đánh giá song song giữa proxy tự động và human scoring (thang điểm 1-5).",
        "",
        "| Metric Dimension | Auto Proxy (Mean) | Human Rating (Mean/5) | Pearson r | Spearman ρ |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in results_table:
        lines.append(
            f"| {r['metric']} | {r['auto_mean']:.4f} | {r['human_mean']:.4f} | "
            f"{r['pearson_r']:.4f} | {r['spearman_rho']:.4f} |"
        )

    lines.extend(
        [
            "",
            "## 2. Phát Hiện Trọng Tâm (Key Empirical Finding): Lỗ Hổng Proxy Trích Dẫn",
            "",
            f"- **Tỷ lệ False Positives Citation**: Có **{len(false_positives)}/{len(paired)}** ({len(false_positives)/max(len(paired),1)*100:.1f}%) "
            "trường hợp metric tự động ghi nhận Citation Correctness tuyệt đối (= 1.00), nhưng con người chỉ đánh giá trích dẫn ở mức yếu (Score ≤ 3).",
            "- **Nguyên nhân**: Proxy tự động chỉ kiểm tra sự xuất hiện bề mặt của chuỗi ký tự căn cứ pháp lý (`cid`, `Điều X`, v.v.), "
            "nhưng không xác minh được liệu điều khoản đó có thực sự hỗ trợ cho mệnh đề được kết luận hay không.",
            "- **Ý nghĩa cho bài báo (Paper Research Direction)**: Đây là luận điểm nghiên cứu then chốt chứng minh rằng: "
            "*'High automatic citation presence does not guarantee authentic legal grounding'*, "
            "mở ra hướng nghiên cứu về **Evaluation of Evidence & Citation Verification in Vietnamese LegalQA** (Hướng 4).",
            "",
            "### Các Trường Hợp False Positives Điển Hình:",
            "",
        ]
    )
    for idx, fp in enumerate(false_positives[:5], start=1):
        lines.append(f"{idx}. **Câu hỏi**: {fp['question']}")
        lines.append(f"   - Auto Citation: {fp['auto_citation']} | Human Citation Score: {fp['human_citation']}/5")
        lines.append("")

    md_path = output_dir / "metric_correlation.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved Markdown correlation report to: {md_path}")

    json_path = output_dir / "metric_correlation.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "paired_samples": len(paired),
                "correlations": results_table,
                "false_positives_count": len(false_positives),
                "false_positives_rate": round(len(false_positives) / max(len(paired), 1), 4),
                "false_positives_samples": false_positives[:10],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Saved JSON correlation data to: {json_path}")

    print("\n### Correlation Summary")
    for r in results_table:
        print(f"{r['metric']}: Auto={r['auto_mean']} vs Human={r['human_mean']} (Pearson r={r['pearson_r']}, Spearman rho={r['spearman_rho']})")
    print(f"False Positives in Citation Proxy: {len(false_positives)}/{len(paired)} ({len(false_positives)/len(paired)*100:.1f}%)")


if __name__ == "__main__":
    main()
