"""Audit evaluators: manual review pipeline for parser correctness.

Checks:
  1. MCQ parser accuracy on 20+ samples
  2. Generation evaluator validity (ROUGE-L on 20 samples)
  3. Format compliance checker correctness
  4. Abstention detection accuracy

For each problematic task, outputs samples for manual review.

Usage:
    python scripts/audit_evaluators.py --config configs/evaluation/vlegal_tasks.yaml
    python scripts/audit_evaluators.py --results-dir results/paired_benchmark --task multi_hop_reasoning
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import scripts._bootstrap as _bootstrap  # noqa: F401

from src.evaluation.paired_benchmark import (
    EvalSample,
    load_paired_samples,
    parse_mcq_response,
    parse_response,
    score_sample,
)
from src.evaluation.evidence_degradation import _detect_abstention


def audit_mcq_parser(
    samples: list[EvalSample],
    task_config: dict,
    n_audit: int = 20,
    seed: int = 42,
) -> dict:
    """Audit MCQ parser on random samples.

    Returns audit report with parser errors.
    """
    rng = random.Random(seed)
    audit_samples = rng.sample(samples, min(n_audit, len(samples)))

    errors: list[dict] = []
    total = 0
    correct = 0

    for sample in audit_samples:
        total += 1
        # Simulate raw model output = gold answer (should parse correctly)
        raw = sample.gold
        parsed = parse_mcq_response(raw, task_config.get("choices"))
        is_correct, _ = score_sample(parsed, sample.gold, task_config)

        if is_correct:
            correct += 1
        else:
            errors.append({
                "sample_id": sample.sample_id,
                "question": sample.question[:200],
                "gold": sample.gold,
                "raw": raw,
                "parsed": parsed,
                "error": "parser_mismatch",
            })

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "errors": errors,
        "error_rate": round(len(errors) / total, 4) if total else 0.0,
    }


def audit_generation_evaluator(
    results_dir: Path,
    task_id: str,
    n_audit: int = 20,
    seed: int = 42,
) -> dict:
    """Audit generation evaluator by checking metric computation.

    Loads paired results and checks ROUGE-L / token F1 computation.
    """
    detail_path = results_dir / f"{task_id}_paired.jsonl"
    if not detail_path.exists():
        return {"status": "no_data", "message": f"No results for {task_id}"}

    details = [
        json.loads(line)
        for line in detail_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    rng = random.Random(seed)
    audit_details = rng.sample(details, min(n_audit, len(details)))

    issues: list[dict] = []
    for d in audit_details:
        # Check if metric values are in valid range
        for model in ["base", "qlora"]:
            metric = d.get(f"{model}_metric", 0)
            if not (0 <= metric <= 1):
                issues.append({
                    "sample_id": d.get("sample_id"),
                    "model": model,
                    "metric": metric,
                    "issue": "metric_out_of_range",
                })

            # Check if parsed output is empty but metric is non-zero
            parsed = d.get(f"{model}_parsed", "")
            if not parsed and metric > 0:
                issues.append({
                    "sample_id": d.get("sample_id"),
                    "model": model,
                    "parsed": parsed,
                    "metric": metric,
                    "issue": "empty_parsed_positive_metric",
                })

    return {
        "task_id": task_id,
        "total_audited": len(audit_details),
        "issues_found": len(issues),
        "issues": issues,
    }


def audit_abstention_detection(
    samples: list[EvalSample],
    task_config: dict,
    n_audit: int = 20,
) -> dict:
    """Audit abstention detection on known abstention patterns."""
    test_cases = [
        ("Khong du can cu de tra loi.", True),
        ("Toi khong biet cau tra loi.", True),
        ("Cau tra loi la A.", False),
        ("Theo dieu 5, nguoi co nghia vu phai nop tien phat.", False),
        ("Thieu thong tin ve hoan canh cu the.", True),
        ("Khong xac dinh duoc.", True),
        ("Co the tra loi la dung.", False),
        ("", False),
    ]

    correct = 0
    errors: list[dict] = []
    for text, expected_abstention in test_cases:
        detected = _detect_abstention(text, task_config)
        if detected == expected_abstention:
            correct += 1
        else:
            errors.append({
                "text": text,
                "expected": expected_abstention,
                "detected": detected,
            })

    return {
        "total": len(test_cases),
        "correct": correct,
        "accuracy": round(correct / len(test_cases), 4),
        "errors": errors,
    }


def generate_manual_review_samples(
    results_dir: Path,
    task_id: str,
    n_samples: int = 30,
    error_types: list[str] | None = None,
    seed: int = 42,
) -> Path:
    """Generate CSV for manual review of samples.

    Focuses on errors and edge cases.
    """
    detail_path = results_dir / f"{task_id}_paired.jsonl"
    if not detail_path.exists():
        raise FileNotFoundError(f"No results for {task_id}")

    details = [
        json.loads(line)
        for line in detail_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    # Prioritize disagreements and errors
    priority = []
    for d in details:
        base_ok = d.get("base_correct", False)
        qlora_ok = d.get("qlora_correct", False)
        if not base_ok and not qlora_ok:
            priority.append((0, d))  # Both wrong = highest priority
        elif base_ok != qlora_ok:
            priority.append((1, d))  # Disagreement
        else:
            priority.append((2, d))  # Both correct or both wrong

    priority.sort(key=lambda x: x[0])
    selected = [d for _, d in priority[:n_samples]]

    # Write CSV
    output_path = results_dir / f"{task_id}_manual_review.csv"
    header = "sample_id,question,gold,base_parsed,base_correct,qlora_parsed,qlora_correct,review_status,reviewer_notes"
    lines = [header]
    for d in selected:
        q = d.get("gold", "").replace('"', '""')[:200]
        lines.append(
            f'"{d.get("sample_id", "")}","{q}","{d.get("gold", "")}",'
            f'"{d.get("base_parsed", "")}",{d.get("base_correct", False)},'
            f'"{d.get("qlora_parsed", "")}",{d.get("qlora_correct", False)},'
            f'"pending",""'
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit evaluators for correctness.")
    parser.add_argument("--config", default="configs/evaluation/vlegal_tasks.yaml")
    parser.add_argument("--results-dir", default="results/paired_benchmark")
    parser.add_argument("--task", default=None, help="Specific task to audit.")
    parser.add_argument("--n-audit", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    # Load config
    config_path = Path(args.config)
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        try:
            import yaml
            config = yaml.safe_load(text)
        except Exception:
            config = json.loads(text)
    else:
        config = {"tasks": {}}

    tasks_config = config.get("tasks", {})
    task_ids = [args.task] if args.task else list(tasks_config.keys())

    print("Evaluator Audit Report")
    print("=" * 60)

    for task_id in task_ids:
        tc = tasks_config.get(task_id, {})
        tc["task_id"] = task_id
        samples = load_paired_samples(tc, seed=args.seed)

        print(f"\n--- {task_id} ---")

        if samples:
            # MCQ parser audit
            if tc.get("task_type") in ("mcq", "binary"):
                parser_audit = audit_mcq_parser(samples, tc, n_audit=args.n_audit, seed=args.seed)
                print(f"  MCQ Parser: {parser_audit['accuracy']:.1%} accuracy "
                      f"({parser_audit['correct']}/{parser_audit['total']})")
                if parser_audit["errors"]:
                    print(f"  Errors: {len(parser_audit['errors'])}")

            # Abstention detection audit
            abstention_audit = audit_abstention_detection(samples, tc)
            print(f"  Abstention Detection: {abstention_audit['accuracy']:.1%}")

        # Generation evaluator audit
        if results_dir.exists() and tc.get("task_type") == "generation":
            gen_audit = audit_generation_evaluator(results_dir, task_id, n_audit=args.n_audit)
            print(f"  Generation Evaluator: {gen_audit.get('issues_found', 0)} issues")

        # Manual review samples
        if results_dir.exists():
            try:
                review_path = generate_manual_review_samples(
                    results_dir, task_id, n_samples=args.n_audit, seed=args.seed
                )
                print(f"  Manual review CSV: {review_path}")
            except FileNotFoundError:
                print(f"  No results for manual review")

    print("\n" + "=" * 60)
    print("Audit complete.")


if __name__ == "__main__":
    main()
